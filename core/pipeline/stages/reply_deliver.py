"""ReplyDeliverStage - 消息发送

Order: 800
职责：批量发送消息，处理打字延迟、文件失败、跨会话消息
"""

import asyncio
import logging
from typing import Optional, List, Any

from core.pipeline.stage import PipelineStage
from core.pipeline.context import PipelineContext
from core.parse_xml import format_message_for_display
from core.config import MAX_SPLIT_COUNT
from core.config.provide import config_loader

logger = logging.getLogger(__name__)


def calculate_split_interval(text_length: int) -> float:
    """模拟真人打字的发送延迟

    延迟 = max(字数 * 打字速度(ms/字) / 1000, 最小延迟)
    """
    bot = config_loader.bot.bot
    speed_ms = getattr(bot, 'typing_speed', 200.0)
    min_delay = getattr(bot, 'typing_min_delay', 2.0)
    delay = max(text_length * speed_ms / 1000.0, min_delay)
    return round(delay, 2)


class ReplyDeliverStage(PipelineStage):
    """消息发送 Stage

    支持：
    1. 批量发送消息（打字延迟 + 句间停顿）
    2. 解析 AI 的 <at_targets> 和 <reply> 标签
    3. 处理文件发送失败（记录到 ctx.failed_files）
    4. 处理跨会话消息发送（<session_send>）

    依赖注入：
    - adapter_bridge: AdapterEventBridge - 适配器桥
    - bridge: BridgeState - 跨会话消息桥
    - name_to_id_cache: BoundedCache - 昵称到ID的映射缓存
    - id_sanitizer: IDSanitizer - ID 打码/还原工具
    """

    def __init__(
        self,
        adapter_bridge: Optional[Any] = None,
        bridge: Optional[Any] = None,
        name_to_id_cache: Optional[Any] = None,
        id_sanitizer: Optional[Any] = None,
        max_messages: Optional[int] = None,
    ):
        super().__init__(order=800, name="reply_deliver")
        self.adapter_bridge = adapter_bridge
        self.bridge = bridge
        self.name_to_id_cache = name_to_id_cache or {}
        self.id_sanitizer = id_sanitizer
        self.max_messages = max_messages or MAX_SPLIT_COUNT

    async def process(self, ctx: PipelineContext) -> None:
        """发送消息"""
        # 如果 AI 主动选择不回复（<msg></msg>）
        if ctx.skip_reply:
            logger.info("AI 选择不回复（skip_reply=True），跳过消息发送")
            return

        # 处理解析错误的回退：发送原始回复
        if ctx.parsed and ctx.parsed.get("parse_error"):
            await self._send_fallback_reply(ctx)
            return

        # 发送常规消息
        messages = ctx.parsed.get("messages", []) if ctx.parsed else []
        if messages:
            await self._send_message_batch(ctx, messages)

        # 处理跨会话消息
        session_sends = ctx.parsed.get("session_sends", []) if ctx.parsed else []
        if session_sends:
            await self._send_cross_session_messages(ctx, session_sends)

    async def _send_fallback_reply(self, ctx: PipelineContext) -> None:
        """发送解析失败时的原始回复"""
        if not ctx.chatllm_reply:
            return

        if not self.adapter_bridge:
            logger.warning("adapter_bridge 未初始化，无法发送消息")
            return

        try:
            await self.adapter_bridge.send_message(
                adapter_id=ctx.platform_name,
                target_id=ctx.target_id,
                text=ctx.chatllm_reply,
                reply_to=ctx.processed.message_id,
                is_group=ctx.is_group,
            )
            logger.info("已发送 fallback 回复 [%s] -> %s", ctx.platform_name, ctx.target_id)
        except Exception as e:
            logger.error("Fallback 回复发送失败: %s", e)

    async def _send_message_batch(self, ctx: PipelineContext, messages: List[Any]) -> None:
        """批量发送消息，每条消息前模拟打字延迟（包括第一条），句间额外停顿"""
        if not self.adapter_bridge:
            logger.warning("adapter_bridge 未初始化，无法发送消息")
            return

        # 限制发送数量
        messages_to_send = messages[:self.max_messages]
        if len(messages) > self.max_messages:
            logger.warning("消息数量超过限制 (%d > %d)，只发送前 %d 条",
                          len(messages), self.max_messages, self.max_messages)

        inter_delay = getattr(config_loader.bot.bot, 'typing_inter_delay', 2.0)

        for idx, msg in enumerate(messages_to_send):
            reply_text = self._extract_message_text(msg)

            if reply_text or msg.images or msg.files:
                # 打字延迟：每条消息发送前等待，模拟真人逐条打字
                # 纯图片消息（reply_text 为空）给一个基础延迟，避免瞬发像机器人
                text_len = len(reply_text) if reply_text else 20
                await asyncio.sleep(calculate_split_interval(text_len))

                # 解析 @目标
                at_targets = self._resolve_at_targets(ctx, msg)

                # 解析 reply_to
                reply_to = msg.reply_to or None

                # 发送消息
                failed = await self._send_single_message(
                    ctx,
                    reply_text,
                    reply_to=reply_to,
                    at_targets=at_targets,
                    images=msg.images or None,
                    files=msg.files or None,
                )

                # 记录失败的文件
                if failed:
                    ctx.failed_files.extend(failed)

                # 句与句之间的额外停顿（最后一条不等待）
                if idx < len(messages_to_send) - 1:
                    await asyncio.sleep(inter_delay)

    def _extract_message_text(self, message: Any) -> str:
        """从单个 Message 对象中提取文本"""
        return format_message_for_display(message)

    def _resolve_at_targets(self, ctx: PipelineContext, message: Any) -> Optional[List[str]]:
        """解析 @ 目标列表

        AI 可主动通过 <at_targets> 指定 @ 谁（用昵称）；不写就不 @
        """
        raw_at = message.at_targets or []
        if not raw_at:
            return None

        at_list = []
        group_key = ctx.processed.group_id or "_private"
        name_map = self.name_to_id_cache.get(group_key, {})

        for name in raw_at:
            qq_id = "all" if name == "all" else name_map.get(name)
            if qq_id:
                # 如果AI输出了打码ID（usr_xxx），还原为真实ID
                if self.id_sanitizer and self.id_sanitizer.is_masked_user_id(qq_id):
                    qq_id = self.id_sanitizer.restore_user_id(qq_id)
                at_list.append(qq_id)

        return at_list if at_list else None

    async def _send_single_message(
        self,
        ctx: PipelineContext,
        reply_text: str,
        reply_to: Optional[str] = None,
        at_targets: Optional[List[str]] = None,
        images: Optional[List[str]] = None,
        files: Optional[List] = None,
    ) -> List[str]:
        """发送单条消息

        Returns:
            发送失败的文件列表
        """
        if not reply_text and not images and not files:
            return []

        try:
            send_kwargs = dict(
                adapter_id=ctx.platform_name,
                target_id=ctx.target_id,
                text=reply_text,
                images=images,
                reply_to=reply_to,
                is_group=ctx.is_group,
                at_targets=at_targets,
            )
            if files:
                send_kwargs["files"] = files

            result = await self.adapter_bridge.send_message(**send_kwargs)
            success = bool(result)
            failed_files = getattr(result, 'failed_files', []) if hasattr(result, 'failed_files') else []

            if success:
                logger.info("发送成功 [%s] -> %s", ctx.platform_name, ctx.target_id)
            else:
                logger.warning("发送失败 [%s] -> %s", ctx.platform_name, ctx.target_id)

            if failed_files:
                logger.warning("[文件发送失败] %s -> %s: %s",
                              ctx.platform_name, ctx.target_id, failed_files)

            return failed_files

        except Exception as e:
            logger.error("发送错误: %s", e)
            # 异常时所有文件视为未送达，保证失败通知能触发
            return [
                (f.name if hasattr(f, "name") else f.get("name", "file"))
                for f in (files or [])
            ]

    async def _send_cross_session_messages(self, ctx: PipelineContext, session_sends: List[dict]) -> None:
        """发送跨会话消息

        流程：
        1. bridge.send 做权限校验 + 限流 + 写 inbox（持目标锁，释放后返回）
        2. 解析 to_sid，通过 adapter_bridge 真实发送（不持锁）
        3. 推送成功后 ack 标记已处理，避免目标会话 consume 时重复注入
        4. 失败时反向写系统消息到源会话 inbox，AI 下轮可感知
        """
        if not self.bridge:
            logger.warning("bridge 未初始化，无法发送跨会话消息")
            return

        from_sid = ctx.sid
        if not from_sid:
            logger.warning("ctx.sid 为空，无法发送跨会话消息")
            return

        for item in session_sends:
            target = item.get("target", "")
            text = item.get("text", "")
            if not target or not text:
                continue

            await self._send_cross_session(from_sid, target, text)

    async def _send_cross_session(self, from_sid: str, to_sid: str, text: str):
        """主动推送跨会话消息

        复用 bridge.send 的权限/限流校验，主动推送不绕过安全策略。
        """
        try:
            # 1. 权限 + 限流 + 写 inbox（send 内部持目标锁，释放后返回）
            result = await asyncio.wait_for(
                self.bridge.send(from_sid, to_sid, text),
                timeout=10,
            )
            if result.startswith("error:"):
                logger.warning("跨会话权限/限流拒绝: %s → %s: %s", from_sid, to_sid, result)
                # 失败反馈直接写源会话 inbox，绕过权限/限流校验
                await self.bridge.add_system_message(from_sid, f"[系统] 跨会话发送失败：{result[6:]}")
                return
            msg_id = result

            # 2. 主动推送：解析 sid，通过适配器真实发送（不持任何会话锁）
            parts = to_sid.split(":", 2)
            if len(parts) == 3 and self.adapter_bridge:
                adapter_name, stype, target_id = parts

                # 还原打码ID：AI可能输出 usr_1001 或 grp_1002，需要还原为真实ID
                if self.id_sanitizer:
                    if target_id.startswith("usr_"):
                        target_id = self.id_sanitizer.restore_user_id(target_id)
                    elif target_id.startswith("grp_"):
                        target_id = self.id_sanitizer.restore_group_id(target_id)

                # 校验 target_id 必须是纯数字（群号/QQ号），拒绝群名/占位符
                if not target_id.isdigit():
                    logger.warning("跨会话 sid 的 id 非数字: %s", to_sid)
                    await self.bridge.add_system_message(
                        from_sid,
                        f"[系统] 跨会话发送失败：id 必须是纯数字群号或用户号，收到 '{target_id}'"
                    )
                    await self.bridge.ack(to_sid, [msg_id])
                    return

                result = await self.adapter_bridge.send_message(
                    adapter_id=adapter_name,
                    target_id=target_id,
                    text=text,
                    is_group=(stype == "gm"),
                )
                success = bool(result)
                logger.info("跨会话主动推送: %s → %s (success=%s)", from_sid, to_sid, success)

                # 3. 推送成功后立即 ack，避免目标会话 consume 时重复注入
                if success:
                    await self.bridge.ack(to_sid, [msg_id])
                else:
                    logger.warning("跨会话推送失败，消息保留在 inbox: %s → %s", from_sid, to_sid)
            else:
                logger.warning("跨会话 sid 格式无效: %s", to_sid)
        except asyncio.TimeoutError:
            logger.warning("跨会话发送超时: %s → %s", from_sid, to_sid)
        except Exception as e:
            logger.error("跨会话发送异常: %s → %s: %s", from_sid, to_sid, e, exc_info=True)
