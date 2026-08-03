# 贡献指南

## 欢迎贡献

感谢你对 Tale-AI 的关注！我们欢迎所有形式的贡献：

- 报告 Bug
- 提出新功能建议
- 改进文档
- 提交代码修复或新功能
- 翻译文档
- 改进 WebUI 设计

## 行为准则

- 尊重所有贡献者
- 接受建设性批评
- 专注于对项目最有利的事情
- 对新手友好，耐心解答问题

## 开始之前

### 1. 熟悉项目

阅读以下文档了解项目架构：

- [README.md](../../README.md) — 项目概览
- [CLAUDE.md](../../CLAUDE.md) — 架构详解
- [docs/architecture/](../architecture/) — 架构文档

### 2. 搭建开发环境

```bash
# 克隆仓库
git clone https://github.com/your-org/Tale-AI.git
cd Tale-AI

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 运行项目
python main.py
```

### 3. 检查现有 Issue

在 [GitHub Issues](https://github.com/your-org/Tale-AI/issues) 中搜索，避免重复工作。

## Git 工作流

### 分支策略

Tale-AI 采用基于功能分支的工作流：

```
main (稳定版本)
  ├── feat/new-feature    # 新功能
  ├── fix/bug-123         # Bug 修复
  ├── docs/api-guide      # 文档更新
  ├── refactor/pipeline   # 重构
  └── ci/github-actions   # CI/CD 改进
```

**分支命名规范**：

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat/` | 新功能 | `feat/voice-adapter` |
| `fix/` | Bug 修复 | `fix/memory-leak` |
| `docs/` | 文档 | `docs/plugin-guide` |
| `refactor/` | 重构 | `refactor/llm-context` |
| `perf/` | 性能优化 | `perf/reduce-latency` |
| `test/` | 测试 | `test/adapter-unit-tests` |
| `ci/` | CI/CD | `ci/add-linter` |
| `chore/` | 杂项 | `chore/update-deps` |

### 开发流程

#### 1. Fork 并克隆

```bash
# Fork 仓库到你的 GitHub 账号
# 然后克隆你的 fork
git clone https://github.com/YOUR_USERNAME/Tale-AI.git
cd Tale-AI

# 添加上游仓库
git remote add upstream https://github.com/original-org/Tale-AI.git
```

#### 2. 创建功能分支

```bash
# 从最新的 main 分支创建
git checkout main
git pull upstream main
git checkout -b feat/my-feature
```

#### 3. 开发与提交

**重要原则**：
- 每次独立修改后立即提交（细粒度提交）
- 提交前先测试（确保功能可用）
- 重大修改前先创建 commit（安全回滚点）

```bash
# 开发功能...

# 测试修改
python main.py  # 手动测试
# 或运行自动化测试（如果有）

# 添加修改的文件（避免使用 git add .）
git add core/adapter/src/voice/adapter.py
git add core/adapter/event.py

# 提交（使用规范的 commit message）
git commit -m "feat(adapter): 添加语音适配器基础实现"

# 继续开发下一个独立单元...
git add tests/unit/adapter/test_voice.py
git commit -m "test(adapter): 添加语音适配器单元测试"
```

#### 4. 同步上游更新

```bash
# 定期同步上游 main 分支
git fetch upstream
git rebase upstream/main

# 解决冲突（如果有）
# 编辑冲突文件...
git add <resolved-files>
git rebase --continue
```

#### 5. 推送到你的 Fork

```bash
git push origin feat/my-feature
```

#### 6. 创建 Pull Request

1. 访问你的 GitHub fork 页面
2. 点击 "Compare & pull request"
3. 填写 PR 信息（见下文"PR 规范"）
4. 提交 PR 等待审查

## 提交规范

### Commit Message 格式

采用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**示例**：

```
feat(adapter): 添加 Discord 适配器

实现基于 discord.py 的适配器，支持：
- 接收文本/图片/语音消息
- 发送消息和文件
- 自动重连机制

Closes #123
```

### Type 类型

| Type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(plugin): 添加天气插件` |
| `fix` | Bug 修复 | `fix(llm): 修复上下文截断问题` |
| `docs` | 文档 | `docs(api): 更新适配器开发指南` |
| `style` | 代码格式（不影响功能） | `style: 统一使用双引号` |
| `refactor` | 重构 | `refactor(pipeline): 简化 Stage 注册逻辑` |
| `perf` | 性能优化 | `perf(context): 使用 LRU 缓存提升速度` |
| `test` | 测试 | `test(adapter): 添加 QQ 适配器集成测试` |
| `build` | 构建系统/依赖 | `build: 升级 anthropic SDK 到 0.28.0` |
| `ci` | CI/CD | `ci: 添加 GitHub Actions 自动测试` |
| `chore` | 杂项 | `chore: 更新 .gitignore` |
| `revert` | 回滚 | `revert: 回滚 commit abc123` |

### Scope 范围

常用 scope：

- `adapter` — 适配器相关
- `plugin` — 插件系统
- `llm` — LLM 调用
- `pipeline` — Pipeline 系统
- `webui` — WebUI
- `config` — 配置管理
- `bus` — 事件总线
- `tool` — 工具系统
- `session` — 会话管理

### Subject 主题

- 使用祈使句（"添加"而非"添加了"）
- 不超过 50 个字符
- 不以句号结尾
- 中英文皆可（项目主要使用中文）

### Body 正文（可选）

- 详细说明修改内容和原因
- 每行不超过 72 个字符
- 与 subject 之间空一行

### Footer 页脚（可选）

- `Closes #123` — 关闭 Issue
- `Refs #456` — 引用 Issue
- `Breaking Change: ...` — 破坏性变更说明

## Pull Request 规范

### PR 标题

与 commit message 格式相同：

```
feat(adapter): 添加 Discord 适配器
fix(llm): 修复上下文截断导致的响应不完整问题
docs(plugin): 完善插件开发指南
```

### PR 描述模板

```markdown
## 概述

简要描述此 PR 的目的和主要修改。

## 修改内容

- [ ] 添加 Discord 适配器基础实现
- [ ] 实现消息接收和发送功能
- [ ] 添加单元测试和集成测试
- [ ] 更新文档

## 测试

### 测试环境
- Python 3.10
- Discord Bot Token: (已测试)
- 测试服务器: Tale-AI Dev Server

### 测试步骤
1. 配置 Discord Bot Token
2. 启动 Tale-AI
3. 在 Discord 发送消息
4. 验证 AI 正常回复

### 测试结果
- [x] 接收私聊消息
- [x] 接收群组消息
- [x] 发送文本消息
- [x] 发送图片消息
- [x] 自动重连功能

## 截图/演示

（如有 UI 变更，请提供截图或 GIF）

## 相关 Issue

Closes #123
Refs #456

## 破坏性变更

无

（如有，请详细说明）

## Checklist

- [x] 代码遵循项目风格指南
- [x] 已添加必要的注释和文档
- [x] 已测试功能正常工作
- [x] 更新了相关文档
- [x] Git commit 符合规范
- [ ] 添加了单元测试（如适用）
```

### PR 大小建议

- **小型 PR**（推荐）：< 300 行修改，专注单一功能
- **中型 PR**：300-800 行，包含相关功能
- **大型 PR**：> 800 行，应拆分为多个 PR

**拆分策略**：
```
# 不好：一个巨大的 PR
feat(voice): 添加完整语音系统（2000+ 行）

# 好：拆分为多个 PR
1. feat(adapter): 添加语音适配器基础框架
2. feat(voice): 实现语音识别功能
3. feat(voice): 实现语音合成功能
4. test(voice): 添加语音系统测试
5. docs(voice): 添加语音功能文档
```

## 代码规范

### Python 风格

遵循 [PEP 8](https://pep8.org/)，但有以下调整：

```python
# 1. 行长度：建议 88 字符（Black 默认）
# 2. 字符串：优先使用双引号
# 3. 导入顺序：标准库 → 第三方库 → 本地模块

from typing import Dict, List, Optional
import asyncio
import json

from anthropic import Anthropic
import requests

from core.utils import get_logger
from core.adapter.base import BaseAdapter
```

### 命名约定

```python
# 类名：大驼峰
class QQAdapter(BaseAdapter):
    pass

# 函数/变量：小写+下划线
def send_message(target_id: str, content: str):
    user_input = content.strip()
    return user_input

# 常量：全大写+下划线
MAX_CONTEXT_LENGTH = 32000
DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

# 私有成员：单下划线前缀
class MyClass:
    def __init__(self):
        self._internal_state = {}
    
    def _private_method(self):
        pass

# 类型注解：使用 typing
def process_event(event: PlatformEvent) -> Optional[str]:
    pass
```

### 文档字符串

```python
def send_message(target_id: str, content: MessageContent, **kwargs) -> SendResult:
    """发送消息到指定目标
    
    将统一的 MessageContent 转换为平台特定格式并发送。
    
    Args:
        target_id: 目标 ID（用户 ID 或群组 ID）
        content: 标准化的消息内容
        **kwargs: 平台特定参数
            - is_group (bool): 是否为群消息
            - at_targets (List[str]): @目标列表
    
    Returns:
        SendResult: 发送结果，包含成功状态和失败文件列表
    
    Raises:
        ConnectionError: 连接未建立时抛出
        TimeoutError: 发送超时时抛出
    
    Example:
        >>> content = MessageContent(text="你好", images=["img.jpg"])
        >>> result = await adapter.send_message("123456", content, is_group=True)
        >>> if result.success:
        ...     print("发送成功")
    """
    pass
```

### 错误处理

```python
# 1. 具体的异常类型
try:
    result = process_data(data)
except ValueError as e:
    logger.error(f"数据格式错误: {e}")
except KeyError as e:
    logger.error(f"缺少必需字段: {e}")
except Exception as e:
    logger.error(f"未预期的错误: {e}", exc_info=True)

# 2. 使用上下文管理器
with open("file.txt", "r") as f:
    content = f.read()

# 3. 异步资源清理
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()
```

### 日志记录

```python
from core.utils import get_logger

logger = get_logger(__name__)

# 日志级别使用建议
logger.debug("详细调试信息：变量值、执行流程")
logger.info("重要操作：启动、连接、关键步骤")
logger.warning("警告信息：非致命错误、降级处理")
logger.error("错误信息：异常捕获、操作失败")

# 格式化日志
logger.info(f"[QQ] 收到消息: user={user_id}, text={text[:50]}...")

# 包含异常堆栈
try:
    risky_operation()
except Exception as e:
    logger.error(f"操作失败: {e}", exc_info=True)
```

### 类型注解

```python
from typing import Dict, List, Optional, Union, Any, Callable

# 函数签名
async def process_event(
    event: PlatformEvent,
    callback: Optional[Callable[[str], None]] = None
) -> Optional[Dict[str, Any]]:
    pass

# 类属性
class MyAdapter:
    config: Dict[str, Any]
    _running: bool
    websocket: Optional[Any]
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
```

## 测试要求

### 测试覆盖

- **新功能**：必须包含单元测试
- **Bug 修复**：添加回归测试防止复发
- **重构**：确保所有现有测试通过

### 测试结构

```
tests/
├── unit/              # 单元测试
│   ├── adapter/
│   │   ├── test_qq_adapter.py
│   │   └── test_base_adapter.py
│   ├── plugin/
│   │   └── test_manager.py
│   └── pipeline/
│       └── test_stages.py
└── integration/       # 集成测试
    ├── test_qq_flow.py
    └── test_plugin_loading.py
```

### 编写测试

```python
import pytest
import asyncio
from core.adapter.src.qq.adapter import QQAdapter

@pytest.fixture
def mock_config():
    """测试配置"""
    return {
        "ws_url": "ws://localhost:3001",
        "bot_uin": "123456"
    }

@pytest.fixture
async def adapter(mock_config):
    """适配器实例"""
    adapter = QQAdapter(mock_config)
    yield adapter
    await adapter.stop()

@pytest.mark.asyncio
async def test_parse_private_message(adapter):
    """测试私聊消息解析"""
    raw_event = {
        "post_type": "message",
        "message_type": "private",
        "user_id": 789,
        "message": [{"type": "text", "data": {"text": "你好"}}]
    }
    
    event = await adapter.parse_event(raw_event)
    
    assert event is not None
    assert event.event_type == EventType.PRIVATE_MESSAGE
    assert event.sender.id == "789"
    assert event.content.text == "你好"

@pytest.mark.asyncio
async def test_send_message_success(adapter, mocker):
    """测试消息发送成功"""
    # Mock WebSocket
    mock_ws = mocker.Mock()
    adapter.websocket = mock_ws
    
    content = MessageContent(text="测试")
    result = await adapter.send_message("123", content)
    
    assert result.success is True
    mock_ws.send.assert_called_once()
```

### 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio pytest-mock

# 运行所有测试
pytest

# 运行特定文件
pytest tests/unit/adapter/test_qq_adapter.py

# 运行特定测试
pytest tests/unit/adapter/test_qq_adapter.py::test_parse_private_message

# 查看覆盖率
pytest --cov=core --cov-report=html
```

## 代码审查

### 审查者指南

审查时关注：

1. **功能性**
   - 代码是否实现了 PR 描述的功能
   - 是否有边界情况未处理
   - 错误处理是否完善

2. **代码质量**
   - 是否遵循项目代码规范
   - 命名是否清晰易懂
   - 是否有重复代码（DRY 原则）
   - 复杂逻辑是否有注释

3. **性能**
   - 是否有明显的性能问题
   - 是否适当使用异步
   - 是否有内存泄漏风险

4. **安全性**
   - 输入是否经过验证
   - 是否有 SQL 注入/路径遍历等风险
   - 敏感信息是否正确处理

5. **测试**
   - 测试覆盖是否充分
   - 测试用例是否合理

### 评审反馈示例

**好的反馈**：
```
建议在这里添加输入验证，防止空字符串导致的异常：

if not city or len(city) > 50:
    return {"error": "城市名称无效"}
```

**不好的反馈**：
- "这段代码写得太烂了"

**更好的表达**：
- "建议将此函数拆分为更小的单元，提高可读性"

### 提交者响应指南

- 感谢审查者的时间和建议
- 对建议进行讨论（如有不同意见）
- 及时修复问题并更新 PR
- 修复后回复评论通知审查者

## 文档贡献

### 文档类型

| 类型 | 位置 | 用途 |
|------|------|------|
| API 文档 | 代码 docstring | 函数/类使用说明 |
| 开发指南 | `docs/development/` | 插件/适配器开发 |
| 架构文档 | `docs/architecture/` | 系统设计说明 |
| 用户手册 | `docs/user/` | 最终用户指南 |
| README | 根目录 | 项目概览 |

### 文档规范

```markdown
# 标题使用 ATX 风格（#）

## 二级标题

### 三级标题

**粗体** 用于强调关键概念

*斜体* 用于术语首次出现

`代码` 用于代码、文件名、命令

## 代码块带语言标识

```python
def example():
    pass
```

## 链接格式
- 外部链接：[显示文本](https://example.com)
- 内部链接：[其他文档](../path/to/doc.md)

## 列表
- 无序列表使用 `-`
- 保持一致的缩进

1. 有序列表使用数字
2. 自动递增

## 表格对齐

| 列1 | 列2 | 列3 |
|-----|-----|-----|
| 值1 | 值2 | 值3 |

## 警告框（如支持）

> **警告**：此操作不可逆

> **提示**：建议先阅读相关文档
```

## 发布流程

### 版本号规范

遵循 [语义化版本](https://semver.org/lang/zh-CN/)：

```
MAJOR.MINOR.PATCH

- MAJOR: 不兼容的 API 修改
- MINOR: 向下兼容的功能新增
- PATCH: 向下兼容的问题修复
```

**示例**：
- `1.0.0` → `1.0.1` — Bug 修复
- `1.0.1` → `1.1.0` — 新增功能
- `1.1.0` → `2.0.0` — 破坏性变更

### Release Notes

创建 GitHub Release 时，**必须使用中英双语**：

```markdown
## Tale-AI v1.2.0

### 新增功能 / New Features

- 添加 Discord 适配器支持 / Added Discord adapter support
- 插件系统支持热重载 / Plugin system now supports hot reload
- WebUI 新增日志查看器 / Added log viewer to WebUI

### Bug 修复 / Bug Fixes

- 修复上下文截断导致的响应不完整 (#123) / Fixed incomplete response due to context truncation (#123)
- 修复内存泄漏问题 (#145) / Fixed memory leak issue (#145)

### 破坏性变更 / Breaking Changes

- `BaseAdapter.send_message` 现在返回 `SendResult` 而非 `bool`
- `BaseAdapter.send_message` now returns `SendResult` instead of `bool`

### 依赖更新 / Dependencies

- 升级 anthropic SDK 至 0.28.0 / Upgraded anthropic SDK to 0.28.0
- 升级 Flask 至 3.0.0 / Upgraded Flask to 3.0.0

### 文档 / Documentation

- 新增插件开发指南 / Added plugin development guide
- 更新适配器开发文档 / Updated adapter development docs
```

### 发布命令

```bash
# 1. 更新版本号
# 编辑 version.py 或 setup.py

# 2. 提交版本变更
git add version.py
git commit -m "chore: bump version to 1.2.0"

# 3. 创建 tag
git tag -a v1.2.0 -m "Release v1.2.0"

# 4. 推送到远程
git push origin main
git push origin v1.2.0

# 5. 创建 GitHub Release
gh release create v1.2.0 \
  --title "Tale-AI v1.2.0" \
  --notes-file release-notes.md \
  dist/Tale-AI-v1.2.0.zip
```

## 获取帮助

### 提问渠道

- **GitHub Issues** — Bug 报告、功能请求
- **GitHub Discussions** — 使用问题、设计讨论
- **Discord/QQ 群** — 实时交流（如有）

### 提问模板

```markdown
## 问题描述

简要描述你遇到的问题。

## 复现步骤

1. 启动 Tale-AI
2. 配置 QQ 适配器
3. 发送消息 "你好"
4. 观察到错误

## 期望行为

AI 应该回复消息。

## 实际行为

收到 `ConnectionError: WebSocket not connected`。

## 环境信息

- OS: Windows 10
- Python: 3.10.11
- Tale-AI 版本: 1.1.0
- 相关配置:
  ```yaml
  adapters:
    - type: qq
      enabled: true
      config:
        ws_url: "ws://localhost:3001"
  ```

## 日志

```
[2024-01-15 10:30:45] [ERROR] [QQ] WebSocket not connected
Traceback (most recent call last):
  ...
```

## 已尝试的解决方法

- 重启 Tale-AI
- 检查 NapCat 状态（运行正常）
```

## 致谢

感谢所有为 Tale-AI 做出贡献的开发者！

你的贡献将出现在：
- GitHub Contributors 列表
- Release Notes 致谢部分
- 项目 README

---

**再次感谢你的贡献！**

如有任何问题，欢迎在 Issue 中提问或联系维护者。
