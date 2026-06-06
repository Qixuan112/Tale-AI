"""
Tale AI — 统一入口
==================
启动核心引擎 + WebUI 管理面板。
"""

import os
import threading

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# 首次启动时确保 data/ 目录和默认配置就绪
from core.data_initializer import initialize_data
initialize_data()


def _start_webui():
    """后台启动 WebUI"""
    from webui.app import app
    print("=" * 50)
    print("  Tale WebUI 启动中...")
    print("  访问: http://127.0.0.1:32456")
    print("=" * 50)
    app.run(host="127.0.0.1", port=32456, debug=False, threaded=True)


def main():
    """统一入口：WebUI + 核心引擎一起启动"""
    threading.Thread(target=_start_webui, daemon=True, name="webui").start()

    from core.main import main as core_main
    core_main()


if __name__ == "__main__":
    main()