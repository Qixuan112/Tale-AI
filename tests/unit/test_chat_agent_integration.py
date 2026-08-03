"""集成测试：ChatAgent 路径的 system 头注入（P1）与无持久化上下文漂移（P2）

覆盖 core/main.py 中 ChatAgent（#183 集成）的两个运行时缺陷：

- P1: ChatLLMAdapter.chat() 只把传入列表的其余部分作为 history 传给
  ChatLLM.chat(messages=...)，而无状态模式只对传入列表追加/裁剪，
  system 头（角色人格/对话示例等，仅存在于 self.messages 实例状态）
  完全丢失。修复：adapter 显式 prepend ``context.build_messages_head()``。
  本文件验证 provider 实际收到的 messages 含 system 头，且内容与
  ChatLLM 实例状态（旧路径 set_session 后 self.messages）完全一致。

- P2: 无持久化模式（session_manager=None）下 _persist_snapshot 直接
  return，快照只进不出，第二轮会带上第一轮的全部消息原文（上下文漂移）。
  修复：无 session_manager 时快照在本轮结束即清空，下轮不读取。
  本文件验证连续两轮调用后，第二轮 provider 收到的消息不含第一轮的
  追加段（仅系统头 + 本轮 user 消息）。

测试直接驱动 TaleCore._call_chatllm（ChatAgent 分支），不依赖网络、
不发事件、不用真实 SessionManager。系统头断言基于 ChatLLM 自身组装
的 build_messages_head() 输出，与具体人格内容解耦。
"""
import sys
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

# ---------------------------------------------------------------------------
# import 提速：本测试只需要 ChatLLMAdapter / TaleCore._call_chatllm 分支，
# core.main 顶层导入链中的 numpy/bs4 只被知识库/工具模块使用，与这些逻辑
# 无关，用轻量 stub 顶替（避免每次导入 ~4-6s 的 numpy/bs4 链，仅本文件
# 生效，不影响其他测试）。openai 是 provider.py 的硬依赖，保持真实导入。
# ---------------------------------------------------------------------------
_stub_modules = [
    "numpy",
    "numpy._core",
    "numpy._core._multiarray_umath",
    "bs4",
    "bs4.dammit",
]
for _name in _stub_modules:
    if _name not in sys.modules:
        sys.modules[_name] = type(sys)(_name)

from core.llm.chatllm import ChatLLM  # noqa: E402
from core.llm.context import create_chat_context  # noqa: E402
from core.main import ChatLLMAdapter, TaleCore  # noqa: E402
from core.agent import ChatAgent  # noqa: E402


class _CaptureProvider:
    """伪 provider：记录最后一次调用收到的完整消息列表，返回固定回复。

    与 OpenAICompatibleProvider 的调用协议兼容
    （chat(messages=..., model=...)），记录 provider 最终收到的消息。
    """

    def __init__(self):
        self.last_messages = None

    def chat(self, messages, model=None, **kwargs):
        self.last_messages = list(messages)
        return "OK"


class _StubSessionManager:
    """内联最小 SessionManager 替身：只提供 ChatAgent 路径用到的三个接口。

    之所以不用真实 SessionManager：其构造函数会 mkdir data/sessions 并
    读写磁盘 JSON，测试不应触碰用户数据目录。
    """

    def __init__(self, memory):
        self._memory = dict(memory)

    def get_memory(self, sid):
        return list(self._memory.get(sid, []))

    def get_session(self, sid):
        return None  # 元数据未知 → 视为启用会话

    def append_memory(self, sid, user_msg, asst_msg):
        self._memory.setdefault(sid, []).append(
            {"role": "user", "content": user_msg.get("content", "")}
        )
        self._memory.setdefault(sid, []).append(
            {"role": "assistant", "content": asst_msg.get("content", "")}
        )


@pytest.fixture
def mock_config_loader():
    """模拟 config_loader：bot 配置只读字段对齐真实模型默认值。"""
    class _Bot:
        typing_speed = 200.0
        typing_min_delay = 2.0
        typing_inter_delay = 2.0
        max_agent_steps = 3
        per_step_timeout = 60.0
        max_concurrent_llm = 3

    class _Ctx:
        chat_context_enabled = False
        chat_context_window = 0

    class _BotConfig:
        bot = _Bot()
        context = _Ctx()

    class _Loader:
        bot = _BotConfig()

    with patch("core.main.config_loader", _Loader()):
        yield


@pytest.fixture
def chatllm():
    """构造真实 ChatLLM：真实 AgentContext（固定人格内容）+ 伪 provider。

    返回 (chatllm, provider)。context 内容固定，system 头断言完全由
    build_messages_head() 决定，不随 data/config/ 下的真实配置变化。
    """
    ctx = create_chat_context(
        character_prompt="TEST_SYSTEM_PERSONA",
        dialogue_examples="",
        persona_additional_prompt="",
    )
    chat = ChatLLM(
        api_key="sk-test",
        model="test-model",
        url="http://localhost/v1",
        context=ctx,
    )
    provider = _CaptureProvider()
    chat._provider = provider
    return chat, provider


@pytest.fixture
def core(chatllm, mock_config_loader):
    """构造 TaleCore：ChatAgent 分支可用，_llm_executor 用直接执行占位。

    chat_agent 直接包 ChatLLMAdapter(chatllm)；session_manager 由测试
    自行设置（None 或 _StubSessionManager），验证 P2 两种模式。
    """
    chatllm, _provider = chatllm
    core = TaleCore()
    core.chat = chatllm
    core.chat_agent = ChatAgent(ChatLLMAdapter(chatllm))
    core._llm_executor = None  # 直接执行（等价 8 线程池）
    return core


def _capture_provider_messages(core):
    """返回 ChatLLM 底层 provider 捕获的最新消息列表。

    链路：ChatAgent._provider（ChatLLMAdapter）→ ChatLLM.chat() →
    chatllm._provider（_CaptureProvider）。
    """
    return core.chat._provider.last_messages


# ============================================================================
# P1: ChatAgent 路径的 system 头
# ============================================================================


class TestSystemHeadInChatAgentPath:
    """P1：ChatAgent 路径的消息必须含 system 头（人格设定）。

    旧路径（有状态）在 set_session()/refresh_context() 时把
    build_messages_head() 写入 self.messages；本测试验证 ChatAgent
    路径下 provider 收到的消息同样以该 system 头开头。
    """

    @pytest.mark.asyncio
    async def test_system_head_present(self, core):
        """单轮调用后 provider 收到的消息以 system 头开头。"""
        reply = await core._call_chatllm(
            "Hello", persist_content="Hello", save_to_session=False,
            sid="qq:dm:u1",
        )
        assert reply == "OK"
        messages = _capture_provider_messages(core)
        assert messages, "provider 应收到消息列表"
        assert messages[0]["role"] == "system", "消息列表第一条应为 system 头"
        assert "TEST_SYSTEM_PERSONA" in messages[0]["content"], (
            "system 头应包含角色人格（缺失则 AI 失去人格设定）"
        )

    @pytest.mark.asyncio
    async def test_system_head_matches_instance_state(self, core):
        """ChatAgent 路径的 system 头与旧路径 set_session 后 self.messages 一致。

        旧路径 set_session() 组装 self.messages = system_head + session_memory；
        断言两者 system 头逐条一致，证明修复后行为与旧路径无差异。
        """
        # 旧路径基准：真实 ChatLLM.set_session 的组装结果
        memory = [
            {"role": "user", "content": "旧历史1"},
            {"role": "assistant", "content": "旧回复1"},
        ]
        core.session_manager = _StubSessionManager({"qq:dm:u1": memory})
        core.chat.set_session("qq:dm:u1", load_history=True)
        old_messages = list(core.chat.messages)
        old_system_head = [m for m in old_messages if m.get("role") == "system"]

        assert old_system_head, "旧路径 self.messages 应含 system 头"

        await core._call_chatllm(
            "Hello", persist_content="Hello", save_to_session=False,
            sid="qq:dm:u1",
        )
        new_messages = _capture_provider_messages(core)
        new_system_head = [m for m in new_messages if m.get("role") == "system"]

        assert new_system_head, "ChatAgent 路径消息应含 system 头"
        assert new_system_head == old_system_head, (
            "ChatAgent 路径的 system 头应与旧路径（set_session 实例状态）逐条一致"
        )

    @pytest.mark.asyncio
    async def test_system_head_survives_follow_up_rounds(self, core):
        """Agent 多轮循环（工具轮次）同样携带 system 头。"""
        core.session_manager = _StubSessionManager({"qq:dm:u1": []})
        # 第一轮：初始用户消息
        await core._call_chatllm(
            "查询天气", persist_content="查询天气", save_to_session=False,
            sid="qq:dm:u1",
        )
        first = _capture_provider_messages(core)
        # 第二轮：工具执行结果回送（persist_content=None 的 agent 内部轮）
        await core._call_chatllm(
            "[Agent 第 1/3 轮] 工具执行结果：晴",
            persist_content=None, save_to_session=False,
            sid="qq:dm:u1",
        )
        second = _capture_provider_messages(core)
        for i, messages in enumerate((first, second)):
            assert messages and messages[0]["role"] == "system", f"第 {i + 1} 轮应含 system 头"
        assert second[0] == first[0], "多轮间 system 头应保持一致（前缀缓存命中前提）"

    @pytest.mark.asyncio
    async def test_chatllm_stateless_detection_unaffected(self, core):
        """回归：_check_chatllm_stateless 对无状态接口的检测不受影响。"""
        assert core._check_chatllm_stateless() is True


# ============================================================================
# P2: 无持久化模式下的上下文漂移
# ============================================================================


class TestNoPersistenceContextDrift:
    """P2：session_manager 为 None 时，快照只保留本轮，下轮不读取。

    修复前：_persist_snapshot 开头 return，快照只进不出；第二轮消息 =
    system 头 + 第一轮全部追加段 + 本轮 user 消息（上下文漂移）。
    修复后：无 session_manager 时快照在 _persist_snapshot 中清空，
    第二轮消息 = system 头 + 本轮 user 消息。
    """

    @pytest.mark.asyncio
    async def test_second_round_has_no_first_round_snapshot(self, core):
        """连续两轮调用：第二轮消息不含第一轮的追加段。"""
        await core._call_chatllm(
            "第一轮消息", persist_content="第一轮消息", save_to_session=False,
            sid="qq:dm:u1",
        )
        # 无持久化模式：模拟 _persist_and_ack 在轮次结束时的落库清理
        core._persist_snapshot("qq:dm:u1")
        assert "qq:dm:u1" not in core._chat_snapshots, "无 session_manager 时快照应已清空"

        await core._call_chatllm(
            "第二轮消息", persist_content="第二轮消息", save_to_session=False,
            sid="qq:dm:u1",
        )
        second = _capture_provider_messages(core)

        user_second = [m for m in second if m.get("role") == "user"]
        assert len(user_second) == 1, (
            f"第二轮应只含本轮一条 user 消息，实际 {len(user_second)} 条"
            f"（含此前所有消息原文 = 上下文漂移）：{user_second}"
        )
        # ChatLLM.chat() 会在用户消息前注入 dynamic reminder（当前时间/今日日程），
        # 与旧路径行为一致；断言原文出现在该消息末尾即可
        assert user_second[0]["content"].endswith("第二轮消息"), (
            "第二轮 user 消息应为本轮内容，而非混入第一轮原文"
        )
        assert all("第一轮消息" not in m.get("content", "") for m in second), (
            "第二轮消息不应残留第一轮的追加段"
        )

    @pytest.mark.asyncio
    async def test_first_round_user_content_is_pure(self, core):
        """第一轮消息只含本轮 user 内容，无跨轮残留。"""
        await core._call_chatllm(
            "第一条消息", persist_content="第一条消息", save_to_session=False,
            sid="qq:dm:u1",
        )
        first = _capture_provider_messages(core)
        user_first = [m for m in first if m.get("role") == "user"]
        assert len(user_first) == 1
        assert user_first[0]["content"].endswith("第一条消息")

    @pytest.mark.asyncio
    async def test_snapshot_cleared_without_session_manager(self, core):
        """_persist_snapshot 在无 session_manager 时清空该会话快照。"""
        core._chat_snapshots["qq:dm:u1"] = [
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
        ]
        core._persist_snapshot("qq:dm:u1")
        assert "qq:dm:u1" not in core._chat_snapshots

    @pytest.mark.asyncio
    async def test_snapshot_survives_until_persist_with_manager(self, core):
        """有 session_manager 时快照保留到 _persist_snapshot 落库为止。"""
        core.session_manager = _StubSessionManager({})
        await core._call_chatllm(
            "第一轮消息", persist_content="第一轮消息", save_to_session=False,
            sid="qq:dm:u1",
        )
        # 落库前快照仍保留（Agent 多轮循环上下文连续依赖它）
        assert "qq:dm:u1" in core._chat_snapshots
        # 落库后：快照清空，记忆写入，下轮从记忆读取
        core._persist_snapshot("qq:dm:u1")
        assert "qq:dm:u1" not in core._chat_snapshots
        memory = core.session_manager.get_memory("qq:dm:u1")
        assert len(memory) == 2, "应写入 user+assistant 各一条"
        assert memory[0]["content"] == "第一轮消息"

        await core._call_chatllm(
            "第二轮消息", persist_content="第二轮消息", save_to_session=False,
            sid="qq:dm:u1",
        )
        second = _capture_provider_messages(core)
        # 持久化模式：system 头 + 记忆(user,assistant) + 本轮 user
        # （user 消息含 dynamic reminder 前缀，故用 endswith 匹配）
        user_msgs = [m for m in second if m.get("role") == "user"]
        assert [m["content"].endswith(t) for m, t in zip(user_msgs, ["第一轮消息", "第二轮消息"])] == [True, True], (
            "持久化模式应从 SessionManager 记忆读取历史"
        )

    @pytest.mark.asyncio
    async def test_no_snapshots_keyed_under_empty_sid(self, core):
        """无持久化 + 未显式传 sid（控制台模式）不应产生 '' 键快照残留。"""
        await core._call_chatllm(
            "控制台消息", persist_content="控制台消息", save_to_session=False,
        )
        # 控制台路径不落库（无 _persist_and_ack 调用），但快照键不应泄漏为 ''
        assert "" not in core._chat_snapshots or not core._chat_snapshots.get(""), (
            "不应产生空 sid 的快照残留"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
