"""ToolExecuteStage - 工具执行阶段

Order: 700
职责：执行工具调用（<act>/<plan>/function_call），支持 Agent 多轮循环
"""

import asyncio
import logging
from typing import Optional, Any, Dict, List
from concurrent.futures import ThreadPoolExecutor

from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext
from core.parse_xml import parse_xml_msg
from core.function_caller import handle_function_call, parse_function_call, execute_function
from core.config.provide import config_loader

logger = logging.getLogger(__name__)


class ToolExecuteStage(PipelineStage):
    """工具执行阶段

    多轮 Agent 循环：
    1. 检测 <act>/<plan>/function_call
    2. 执行工具并收集结果
    3. 将结果反馈给 ChatLLM
    4. 重复直到无工具调用或达到最大轮数

    依赖注入：
    - tool_llm: ToolLLM 实例（执行 <act> 标签）
    - plan_llm: PlanLLM 实例（执行 <plan> 标签）
    - chat_llm: ChatLLM 实例（有状态模式，follow-up 调用）
    - chat_agent: ChatAgent 实例（无状态模式，follow-up 调用）
    - llm_executor: ThreadPoolExecutor（LLM 线程池）
    - session_manager: SessionManager（会话管理）
    - chat_snapshots: Dict[str, List[Dict]]（快照缓存）
    - max_steps: int（最大迭代轮数，默认从配置读取）
    """

    def __init__(
        self,
        tool_llm: Optional[Any] = None,
        plan_llm: Optional[Any] = None,
        chat_llm: Optional[Any] = None,
        chat_agent: Optional[Any] = None,
        llm_executor: Optional[ThreadPoolExecutor] = None,
        session_manager: Optional[Any] = None,
        chat_snapshots: Optional[Dict[str, List[Dict]]] = None,
        max_steps: Optional[int] = None,
    ):
        super().__init__(order=700, name="tool_execute")
        self.tool_llm = tool_llm
        self.plan_llm = plan_llm
        self.chat_llm = chat_llm
        self.chat_agent = chat_agent
        self.llm_executor = llm_executor
        self.session_manager = session_manager
        self.chat_snapshots = chat_snapshots or {}
        self.max_steps = max_steps

    async def process(self, ctx: PipelineContext) -> None:
        """执行工具调用的 Agent 循环"""
        # 检查是否需要工具执行
        if not self._has_tool_content(ctx.parsed, ctx.chatllm_reply):
            logger.debug("无工具调用，跳过 tool_execute 阶段")
            return

        # 获取最大步数配置
        max_steps = self._get_max_steps()

        # 执行 Agent 多轮循环
        final_messages = await self._resolve_follow_up(
            chatllm_reply=ctx.chatllm_reply,
            parsed=ctx.parsed,
            sid=ctx.sid,
            max_steps=max_steps,
        )

        # 更新上下文
        ctx.messages_to_send = final_messages

    def _get_max_steps(self) -> int:
        """获取最大步数配置"""
        if self.max_steps is not None:
            return self.max_steps

        try:
            bot_config = config_loader.bot.bot
            return getattr(bot_config, 'max_agent_steps', 5)
        except Exception:
            return 5

    def _has_tool_content(self, parsed: Optional[dict], raw_reply: str = "") -> bool:
        """检查是否包含工具调用内容"""
        if not parsed:
            return False

        # 检查 <act> 标签
        if parsed.get("actions") or parsed.get("action"):
            return True

        # 检查 <plan> 标签
        if parsed.get("plan"):
            return True

        # 检查 function_call 格式
        if raw_reply and parse_function_call(raw_reply):
            return True

        return False

    async def _resolve_follow_up(
        self,
        chatllm_reply: str,
        parsed: Optional[dict] = None,
        sid: str = None,
        max_steps: int = 5,
    ) -> list:
        """Agent 多步骤推理循环

        Args:
            chatllm_reply: 首轮 ChatLLM 原始回复
            parsed: 解析结果，None 时内部解析
            sid: 会话标识
            max_steps: 最大轮数

        Returns:
            最终消息列表
        """
        if parsed is None:
            parsed = parse_xml_msg(chatllm_reply)

        current_reply = chatllm_reply
        current_parsed = parsed
        iteration = 0

        while iteration < max_steps:
            iteration += 1
            logger.debug("Agent 第 %d/%d 轮", iteration, max_steps)
            remaining = max_steps - iteration

            # 批量收集本轮所有可执行操作
            result_parts = []  # [(title, content), ...]

            # Phase A: 内嵌 Function Calling
            has_func, func_result = handle_function_call(current_reply)
            if has_func:
                logger.info("[Agent %d/%d] 内嵌 FC", iteration, max_steps)
                result_parts.append(("工具执行结果", str(func_result)))

            # Phase B: <act> 标签
            if current_parsed.get("actions"):
                logger.info("[Agent %d/%d] 执行动作: %s",
                            iteration, max_steps, current_parsed["actions"])
                results = await self._execute_actions(current_parsed["actions"])
                if results:
                    texts = []
                    for i, r in enumerate(results, 1):
                        texts.append(f"[{i}] {r}")
                    result_parts.append((
                        "动作执行结果",
                        f"共执行 {len(results)} 个工具：\n" + "\n".join(texts)
                    ))
                else:
                    result_parts.append(("动作执行失败", "所有工具执行均失败，请告知用户。"))

            # Phase C: <plan> 标签
            if current_parsed.get("plan"):
                logger.info("[Agent %d/%d] 制定计划", iteration, max_steps)
                plan_result = await self._execute_plan(current_parsed["plan"])
                first_reply = self._extract_reply_text(current_parsed)
                plan_content = (
                    f'你刚才对用户说："{first_reply}"\n\n'
                    f"现在我已经获取到日程信息：\n{plan_result}\n\n"
                    "请整合以上信息，给用户一个完整的回复。"
                    "如果日程为空，可以说'今天还没有安排呢，要不要添加一些？'"
                    "如果有安排，请列出具体事项。"
                )
                result_parts.append(("日程信息", plan_content))

            # 本轮无任何操作 → 退出循环
            if not result_parts:
                break

            # 合并结果
            if len(result_parts) == 1:
                combined_result = result_parts[0][1]
            else:
                combined_result = "\n\n---\n\n".join(
                    f"【{title}】\n{content}" for title, content in result_parts
                )

            # 构建 follow-up prompt
            follow_up_prompt = self._build_agent_prompt(
                iteration, max_steps, combined_result,
                f"第 {iteration} 轮执行结果", remaining,
            )

            # 调用 ChatLLM 获取下一轮回复
            current_reply = await self._call_chatllm_follow_up(
                follow_up_prompt, sid
            )
            current_parsed = parse_xml_msg(current_reply)

        # 检查是否达到最大轮数但仍有工具调用
        if iteration >= max_steps and self._has_tool_content(current_parsed, current_reply):
            logger.warning(
                "Agent 已达最大轮数 (%d)，仍有未处理的工具调用，"
                "最终回复可能不完整", max_steps
            )

        return current_parsed.get("messages", [])

    async def _execute_actions(self, actions: list) -> list:
        """执行动作列表，返回所有执行结果

        Args:
            actions: 动作列表（<act> 标签内容）

        Returns:
            执行结果列表
        """
        results = []

        # ToolLLM 未配置时无法执行
        if self.tool_llm is None:
            logger.warning("ToolLLM 未初始化，跳过 %d 个动作", len(actions))
            return ["工具能力未配置，无法执行该动作。"]

        loop = asyncio.get_running_loop()

        for i, action in enumerate(actions, 1):
            logger.info("ToolLLM 处理动作 %d/%d: %s", i, len(actions), action)

            try:
                # 调用 ToolLLM 生成 function call
                if self.llm_executor is not None:
                    fc_output = await loop.run_in_executor(
                        self.llm_executor, self.tool_llm.generate_fc, action
                    )
                else:
                    # 无线程池时直接同步调用（测试场景）
                    fc_output = self.tool_llm.generate_fc(action)

                logger.debug("ToolLLM 输出: %s", fc_output)
            except Exception as e:
                logger.error("ToolLLM generate_fc 失败: %s", e)
                results.append({"status": "failed", "error": f"ToolLLM 调用失败: {str(e)}"})
                continue

            # 解析 function call
            func_call = parse_function_call(fc_output)
            if func_call:
                logger.info("执行工具: %s", func_call["name"])

                # 执行工具
                if self.llm_executor is not None:
                    tool_result = await loop.run_in_executor(
                        self.llm_executor,
                        execute_function, func_call["name"], func_call["parameters"]
                    )
                else:
                    tool_result = execute_function(func_call["name"], func_call["parameters"])

                logger.info("执行结果: %s", tool_result)

                # 工具执行失败时，检查是否为"未知的函数"错误
                if isinstance(tool_result, dict) and tool_result.get("status") == "failed":
                    error_msg = tool_result.get("error", "")
                    if "未知的函数" in error_msg:
                        logger.info("工具不存在，返回可用工具列表")
                        tools_list = self.tool_llm.query_tools()
                        tool_result = {
                            "status": "failed",
                            "error": error_msg,
                            "available_tools": tools_list,
                            "message": f"工具不存在。当前可用工具：\n{tools_list}"
                        }

                results.append(tool_result)
            else:
                logger.warning("无法解析 Function Calling")
                results.append({"status": "failed", "error": "无法解析 Function Calling"})

        return results

    async def _execute_plan(self, plan_prompt: str) -> str:
        """执行计划生成

        Args:
            plan_prompt: 计划提示词

        Returns:
            计划结果文本
        """
        if self.plan_llm is None:
            logger.warning("PlanLLM 未初始化，跳过计划生成")
            return "日程功能未配置。"

        try:
            result = await self.plan_llm.generate_async(plan_prompt)
            return result
        except Exception as e:
            logger.error("PlanLLM 调用失败: %s", e)
            return f"日程生成失败: {str(e)}"

    async def _call_chatllm_follow_up(self, user_input: str, sid: Optional[str]) -> str:
        """调用 ChatLLM 进行 follow-up（工具结果反馈）

        Args:
            user_input: 用户输入（工具执行结果）
            sid: 会话 ID

        Returns:
            AI 回复文本
        """
        if not user_input:
            return ""

        try:
            # ChatAgent 模式（无状态）
            if self.chat_agent is not None:
                return await self._call_chat_agent_follow_up(user_input, sid)
            # ChatLLM 模式（有状态）
            elif self.chat_llm is not None:
                return await self._call_chat_llm_follow_up_impl(user_input, sid)
            else:
                logger.error("ChatLLM 和 ChatAgent 均未初始化")
                return ""
        except Exception as e:
            logger.error("ChatLLM follow-up 调用失败: %s", e)
            return ""

    async def _call_chat_agent_follow_up(self, user_input: str, sid: Optional[str]) -> str:
        """ChatAgent 模式的 follow-up 调用"""
        # 组装消息列表：历史 + 快照 + 当前工具结果
        messages = self._get_session_messages(sid or "")
        messages.append({"role": "user", "content": user_input})

        # 调用 ChatAgent
        reply = await self.chat_agent.generate(
            messages=messages,
            session_id=sid or "",
            timeout=60.0,
        )

        if reply is None:
            logger.error("ChatAgent 返回空响应")
            reply = ""

        # 更新快照缓存（工具轮次不写入用户消息）
        if reply and sid:
            snap = self.chat_snapshots.setdefault(sid, [])
            if snap and snap[-1].get("role") == "assistant":
                # 更新上一条 assistant 回复
                snap[-1] = {"role": "assistant", "content": reply}
            else:
                # 追加新回复
                snap.append({"role": "assistant", "content": reply})

            # 限制快照长度
            if len(snap) > 40:
                self.chat_snapshots[sid] = snap[-20:]

        return reply

    async def _call_chat_llm_follow_up_impl(self, user_input: str, sid: Optional[str]) -> str:
        """ChatLLM 模式的 follow-up 调用"""
        if self.llm_executor is not None:
            loop = asyncio.get_running_loop()
            reply = await loop.run_in_executor(
                self.llm_executor,
                self.chat_llm.chat,
                user_input,
                None,  # persist_content
                False,  # save_to_session (Agent 内部步骤不落库)
            )
        else:
            # 无线程池时直接同步调用
            reply = self.chat_llm.chat(user_input, None, False)

        return reply

    def _get_session_messages(self, sid: str) -> List[Dict]:
        """组装 ChatAgent 模式的会话消息列表"""
        messages: List[Dict] = []

        # 1. 加载持久化历史
        if self.session_manager is not None:
            try:
                session = self.session_manager.get_session(sid)
                if session is None or session.enabled:
                    messages.extend(self.session_manager.get_memory(sid))
            except Exception as e:
                logger.debug("读取会话历史失败: %s", e)

        # 2. 追加快照
        messages.extend(self.chat_snapshots.get(sid, []))

        return messages

    def _build_agent_prompt(
        self,
        iteration: int,
        max_steps: int,
        result: str,
        title: str,
        remaining: int
    ) -> str:
        """构建带步数感知的 Agent 提示词"""
        if remaining > 0:
            return (
                f"[Agent 第 {iteration}/{max_steps} 轮] {title}：\n"
                f"{result}\n\n"
                f"这是第 {iteration} 次工具调用（最多允许 {max_steps} 次推理步骤）。"
                f"你还有 {remaining} 次机会。\n"
                f"如果任务已完成，请直接回复用户；如果还需要查询更多信息、执行更多操作，\n"
                f"可以继续使用 <act>/<plan> 标签。"
            )
        else:
            return (
                f"[Agent 第 {iteration}/{max_steps} 轮 — 最后一轮] {title}：\n"
                f"{result}\n\n"
                f"这是最后一轮推理。请根据已有信息给用户一个完整回复，"
                f"不要再使用 <act>/<plan> 标签。"
            )

    def _extract_reply_text(self, parsed: dict) -> str:
        """从解析结果中提取回复文本"""
        texts = []
        if parsed.get("messages"):
            for msg in parsed["messages"]:
                for elem in msg.elements:
                    texts.append(elem.content)
        return " ".join(texts)
