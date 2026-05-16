from .bus import bus


from ..utils import get_logger

logger = get_logger(__name__)

class NextBus:
    def __init__(self):
        self.bus = bus
        
    def on_user_login(self, username):
        logger.info(f"[登录模块] 用户 {username} 登录成功")


    def on_send_message(self, content, to_user):
        logger.info(f"[消息模块] 发送消息 '{content}' 给 {to_user}")
        bus.emit("message_sent", content, to_user)


    def on_message_sent(self, content, to_user):
        logger.info(f"[通知模块] 消息已送达: {to_user} 收到 '{content}'")


    def on_app_start(self):
        logger.info("[系统] 应用启动完成")    


# def main():
#     bus.on("user_login", on_user_login)
#     bus.on("send_message", on_send_message)
#     bus.on("message_sent", on_message_sent)
#     bus.once("app_start", on_app_start)

#     print("=== 应用启动 ===")
#     bus.emit("app_start")
#     bus.emit("app_start")

#     print("\n=== 用户登录 ===")
#     bus.emit("user_login", "张三")

#     print("\n=== 发送消息 ===")
#     bus.emit("send_message", "你好啊！", "李四")


if __name__ == "__main__":
    main()
