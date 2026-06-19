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
  typing_speed: 50
  typing_min_delay: 0.5

# 上下文设置
context:
  max_context: 10
  chat_context_window: 10
  chat_context_enabled: true
  memory_enabled: true
  personality_strength: 0.8

selfie:
  path: ""

wake:
  enable_keyword_wake: false
  waking_keywords: []
  enable_quote_wake: false
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

# ============================================
# 通用 LLM — 不绑定固定角色，供以下场景复用：
#   - XML 修复：ChatLLM 输出格式错误时自动调用
#   - 插件调用：后续插件可通过 GenericLLM 进行翻译、摘要、分类等任务
#   - 其他需要 LLM 但无需角色扮演的场景
# 可使用与 main_llm 相同的 provider，推荐使用廉价模型节省成本
# ============================================
generic_llm:
  provider: ""

# ============================================
# 多模态模型 (VLM) — 用于图片识别与视觉理解
# 可复用主对话模型的 provider，需使用支持 vision 的模型
# ============================================
vlm:
  provider: ""

# ============================================
# 图片生成模型 — 文生图，AI 可调用 generate_image 工具生成图片
# 需在 services.yaml 配 type: image_gen 的 provider（如 SiliconFlow）
# ============================================
image_gen:
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

# 示例：SiliconFlow 文生图（type: image_gen）
# SiliconFlow-ImageGen:
#   type: image_gen
#   api_key: "your-api-key"
#   base_url: https://api.siliconflow.cn/v1
#   model: Kwai-Kolors/Kolors
"""

DEFAULT_PLUGINS_YAML = """\
plugins:
  workspace:
    enabled: true
  tavily_search:
    enabled: true
    config:
      api_key: ""
"""

DEFAULT_KNOWLEDGE_YAML = """\
# RAG 知识库配置
# 启用后 ChatLLM 将检索知识库内容来辅助回答
# 首次需配置 openai_embedding_api_key 或将 default_embedder 改为 local

enabled: false
default_embedder: openai
openai_embedding_api_key: ""
openai_embedding_base_url: ""
openai_embedding_model: "text-embedding-3-small"
bge_model_name: "BAAI/bge-small-zh-v1.5"
bge_device: "cpu"
chunk_size: 500
chunk_overlap: 50
top_k: 5
inject_into_chat: true
inject_order: 5
max_context_length: 2000
knowledge_bases:
  - name: default
    enabled: true
    embedder: openai
    top_k: 3
    similarity_threshold: 0.0
    description: "默认知识库"
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
    """确保所有 data/ 子目录及插件目录存在"""
    dirs = [
        "data/config/presets",
        "data/conversations",
        "data/diary",
        "data/files",
        "data/temp",
        "data/custom_plugins",
        "core/plugins",
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


def _migrate_plugins():
    """将旧 plugins/ 中的内置插件迁移到 core/plugins/"""
    import shutil
    old_dir = PROJECT_ROOT / "plugins"
    new_dir = PROJECT_ROOT / "core" / "plugins"

    if not old_dir.exists():
        return
    if new_dir.exists() and any(new_dir.iterdir()):
        return

    new_dir.mkdir(parents=True, exist_ok=True)

    BUILTIN_IDS = {"workspace", "echo_tool", "tavily_search"}
    for plugin_dir in old_dir.iterdir():
        if not plugin_dir.is_dir():
            continue
        pid = plugin_dir.name
        if pid in BUILTIN_IDS and not (new_dir / pid).exists():
            shutil.copytree(str(plugin_dir), str(new_dir / pid))
            print(f"  [migrate] Plugin moved: plugins/{pid} -> core/plugins/{pid}")
        elif pid not in BUILTIN_IDS:
            print(f"  [migrate] Unknown plugin skipped: plugins/{pid} "
                  f"(move to data/custom_plugins/ if needed)")


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
    _write_if_missing("data/config/knowledge.yaml", DEFAULT_KNOWLEDGE_YAML)

    # 3. 生成 WebUI 认证 token（仅在文件不存在时）
    _token_path = PROJECT_ROOT / "data" / "config" / "webui_token"
    if not _token_path.exists():
        _token_chars = string.ascii_letters + string.digits
        _token = ''.join(secrets.choice(_token_chars) for _ in range(16))
        _token_path.parent.mkdir(parents=True, exist_ok=True)
        _token_path.write_text(_token, encoding="utf-8")
        print(f"\n  WebUI 认证令牌: {_token}\n")

    # 4. 写入默认会话索引
    _write_json_if_missing("data/conversations/index.json", DEFAULT_CONVERSATIONS_INDEX)

    # 5. 迁移旧插件目录
    _migrate_plugins()
