"""
数据目录初始化器
================
首次启动时自动创建 data/ 目录结构和默认配置文件。
当 data/ 被 .gitignore 忽略后，新克隆的项目首次运行会缺少这些文件，
此模块确保目录结构和必要配置在启动时自动就绪。
"""

import os
import json
import secrets
import string
from pathlib import Path

# 项目根目录（core/data_initializer.py -> core/ -> root）
PROJECT_ROOT = Path(__file__).parent.parent

# ============ 默认配置内容 ============

DEFAULT_CHARACTER_YAML = """\
character:
  ChineseName: ''
  EnglishName: ''
  NickNames: []
  age: ''
  appearance: ''
  birthday: ''
  dialogue_style_imitation: []
  expressions: ''
  gender: ''
  hobbies: []
  language:
    primary: Chinese
    style: casual
  values: []
  views: []
"""

DEFAULT_BEHAVIOR_YAML = """\
# ============================================
# 机器人行为配置 - behavior.yaml
# 定义机器人的行为参数
# ============================================

bot:
  max_memory_length: 10
  max_message_interval: 2
  max_buffer_messages: 5
  min_message_delay: 0.8
  max_message_delay: 1.5

selfie:
  path: ""
"""

DEFAULT_PLATFORMS_YAML = """\
# ============================================
# 平台适配器配置 - platforms.yaml
# 定义各平台适配器的连接参数
# ============================================

# QQ Adapter 示例（默认禁用）
# qq:
#   enabled: false
#   adapter_type: qq
#   ws_url: ws://127.0.0.1:3002
#   http_url: http://localhost:3000
#   access_token: ""
#   auto_reconnect: true
#   reconnect_interval: 5
"""

DEFAULT_ROUTING_YAML = """\
# ============================================
# 模型路由配置 - routing.yaml
# 定义不同功能使用的提供商
# ============================================

main_llm:
  provider: ""

tool_llm:
  provider: ""

plan_llm:
  provider: ""
"""

DEFAULT_SERVICES_YAML = """\
# ============================================
# 服务提供商配置 - services.yaml
# 定义各种 AI 服务提供商的 API 配置
# ============================================

# 示例：DeepSeek V3
# DeepSeek/DeepSeek-V3:
#   type: llm
#   format: openai
#   api_key: "your-api-key"
#   base_url: https://api.siliconflow.cn/v1
#   model: deepseek-ai/DeepSeek-V3
"""

DEFAULT_PLUGINS_YAML = """\
# ============================================
# 插件配置 - plugins.yaml
# 启用/禁用插件，覆盖默认配置
# ============================================

plugins:
  # 示例：
  # my_plugin:
  #   enabled: true
  #   config:
  #     key: value
"""

DEFAULT_CONVERSATIONS_INDEX = {
    "current_id": 1,
    "conversations": [
        {
            "id": 1,
            "title": "默认会话",
            "last_message": "",
            "time": "",
            "count": 0,
            "created_at": "",
        }
    ],
}


def ensure_data_dirs():
    """确保所有 data/ 子目录存在"""
    dirs = [
        "data/config/presets",
        "data/conversations",
        "data/diary",
        "data/files",
        "plugins",
    ]
    for d in dirs:
        dir_path = PROJECT_ROOT / d
        dir_path.mkdir(parents=True, exist_ok=True)


def _write_if_missing(rel_path: str, content: str):
    """仅在文件不存在时写入默认内容"""
    file_path = PROJECT_ROOT / rel_path
    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)


def _write_json_if_missing(rel_path: str, data: dict):
    """仅在 JSON 文件不存在时写入默认内容"""
    file_path = PROJECT_ROOT / rel_path
    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def initialize_data():
    """
    初始化 data 目录：创建目录结构和默认配置文件。

    幂等操作——已存在的文件不会被覆盖。
    应在程序最早期（main.py 入口）调用。
    """
    # 1. 确保目录结构
    ensure_data_dirs()

    # 2. 写入默认配置文件（仅在文件不存在时）
    _write_if_missing("data/config/character.yaml", DEFAULT_CHARACTER_YAML)
    _write_if_missing("data/config/behavior.yaml", DEFAULT_BEHAVIOR_YAML)
    _write_if_missing("data/config/platforms.yaml", DEFAULT_PLATFORMS_YAML)
    _write_if_missing("data/config/routing.yaml", DEFAULT_ROUTING_YAML)
    _write_if_missing("data/config/services.yaml", DEFAULT_SERVICES_YAML)
    _write_if_missing("data/config/plugins.yaml", DEFAULT_PLUGINS_YAML)

    # 3. 生成 WebUI 认证 token（仅在文件不存在时）
    _token_path = PROJECT_ROOT / "data" / "config" / "webui_token"
    if not _token_path.exists():
        _token_chars = string.ascii_letters + string.digits
        _token = ''.join(secrets.choice(_token_chars) for _ in range(6))
        _token_path.parent.mkdir(parents=True, exist_ok=True)
        _token_path.write_text(_token, encoding="utf-8")
        print(f"\n  WebUI 认证令牌: {_token}\n")

    # 4. 写入默认会话索引
    _write_json_if_missing("data/conversations/index.json", DEFAULT_CONVERSATIONS_INDEX)
