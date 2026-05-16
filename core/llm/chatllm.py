from openai import OpenAI
from ..config import MAX_CONTEXT
from ..config.prompt import CHAT_PROMPT
from ..utils import get_logger

logger = get_logger(__name__)


class ChatLLM:
    def __init__(self, api_key, model, url, max_context=MAX_CONTEXT):
        """
        初始化 ChatLLM

        Args:
            api_key: OpenAI API 密钥
            model: 使用的模型
            max_context: 最大上下文消息数（包括 system 消息），建议 10-20 条
        """
        self.client = OpenAI(api_key=api_key, base_url=url)
        self.model = model
        self.max_context = max_context
        self.messages = [
            {"role": "system", "content": CHAT_PROMPT}
        ]

    def chat(self, user_input):
        """
        发送消息并获取回复，自动维护上下文
        """
        self.messages.append({"role": "user", "content": user_input})
        self._trim_context()

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages
            )
        except Exception as e:
            logger.error("ChatLLM API 调用失败: %s", e)
            raise

        assistant_reply = response.choices[0].message.content
        self.messages.append({"role": "assistant", "content": assistant_reply})

        return assistant_reply

    def _trim_context(self):
        """
        修剪上下文，确保不超过 max_context 限制
        策略：始终保留 system 消息，删除最早的用户-对话消息
        """
        while len(self.messages) > self.max_context:
            if len(self.messages) >= 3:
                del self.messages[1:3]
            else:
                # 安全兜底：消息不足3条时直接截断到保留 system 消息
                logger.warning("上下文不足3条但超过限制，强制保留 system 消息")
                self.messages = [self.messages[0]]
                break

    def clear_history(self):
        """清空对话历史，只保留 system 消息"""
        system_msg = self.messages[0]
        self.messages = [system_msg]

    def get_history(self):
        """获取当前对话历史"""
        return self.messages.copy()

    def set_history(self, messages: list):
        """设置对话历史（供外部如 WebUI 切换会话时使用）"""
        if not messages:
            self.clear_history()
            return
        # 确保第一条是 system 消息
        if messages and messages[0].get("role") == "system":
            self.messages = list(messages)
        else:
            # 如果不包含 system 消息，保留当前的 system 消息并追加
            self.messages = [self.messages[0]] + list(messages)
        self._trim_context()





if __name__ == "__main__":
    pass
