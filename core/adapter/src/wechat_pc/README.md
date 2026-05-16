# WeChat PC 适配器

基于 [wxauto](https://github.com/cluic/wxauto) 的微信 PC 客户端 UI 自动化适配器。

> ⚠️ **Windows 限定**：依赖 UIA (UI Automation) + COM，仅支持 Windows 平台。

---

## 功能特性

| 功能 | 状态 |
|---|---|
| 接收文本消息 | ✅ |
| 接收图片/文件/语音 | ✅（可选自动保存到本地） |
| 发送文本消息 | ✅（支持真正的微信 @ 提醒） |
| 发送图片/文件/视频/语音 | ✅ |
| 群聊 @ 唤醒 / 关键词唤醒 | ✅ |
| 白名单 / 黑名单权限控制 | ✅ |
| 消息去重 | ✅（RuntimeId + 内容指纹双层兜底） |
| 窗口丢失自动重连 | ✅（最多 5 次） |
| 群聊 / 私聊自动识别 | ✅（启发式 + 缓存持久化） |

---

## 配置项

在 WebUI 适配器配置页面中填写以下参数：

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `poll_interval` | float | `2.0` | 轮询新消息间隔（秒） |
| `language` | enum | `cn` | 微信客户端语言：`cn` / `cn_t` / `en` |
| `save_pic` | switch | `false` | 收到图片自动保存到 `data/files/wechat_pc` |
| `save_file` | switch | `false` | 收到文件自动保存到本地 |
| `save_voice` | switch | `false` | 收到语音自动转文字 |
| `debug` | switch | `false` | 开启 wxauto 内部 debug 日志 |
| `self_nickname` | string | `""` | 当前登录微信昵称，用于过滤自己消息 |
| `permission_mode` | enum | `allow_list` | `allow_list`（白名单）/ `deny_list`（黑名单） |
| `group_allow_list` | list | `[]` | 允许响应的群名称列表 |
| `user_allow_list` | list | `[]` | 允许响应的好友昵称/备注列表 |
| `group_deny_list` | list | `[]` | 屏蔽的群名称列表 |
| `user_deny_list` | list | `[]` | 屏蔽的好友昵称/备注列表 |
| `group_at_me_only` | switch | `false` | 群聊中仅当被 @ 或含关键词时才响应 |
| `group_wake_words` | list | `[]` | 群聊唤醒关键词列表（如 `["Kira", "助手"]`） |

---

## 权限控制

### 白名单模式（`allow_list`）

- 列表**为空**时：允许所有群/用户
- 列表**非空**时：只允许列表中的群/用户

```
示例：
  permission_mode = "allow_list"
  user_allow_list = ["张三", "李四"]
  → 只回复张三和李四的私聊消息
```

### 黑名单模式（`deny_list`）

- 列表**为空**时：允许所有群/用户
- 列表**非空**时：屏蔽列表中的群/用户

```
示例：
  permission_mode = "deny_list"
  group_deny_list = ["广告群"]
  → 不处理"广告群"的任何消息
```

### 群聊 @ 唤醒（`group_at_me_only`）

开启后，群聊消息必须满足以下任一条件才会触发 AI 响应：

1. 消息文本中包含 `@self_nickname`
2. 消息文本中包含 `self_nickname`
3. 消息文本匹配 `group_wake_words` 中的任一关键词

私聊消息不受影响，始终响应。

---

## 技术细节

### 消息获取方式

采用双层轮询策略：

1. **`GetNextNewMessage`**：标准轮询，可获取其他聊天窗口的新消息
2. **`GetAllMessage` + ID 差集**：兜底对比当前窗口，补全 RuntimeId 变化导致的漏检

### 群聊识别

- 通过 `GetGroupMembers()` 探测群属性
- 结果缓存到 `data/files/wechat_pc/group_cache.json`，重启后自动加载
- 启发式修正：若 `sender_name == session_name`，则判定为私聊（修正误判）

### 消息去重

采用双层去重策略，防止消息重复处理：

1. **`msg_id` 去重**：基于 wxauto 的 RuntimeId，滚动窗口保留最近 300 条（上限 500）
2. **内容指纹兜底**：当 RuntimeId 变化或失效时，使用 `session:sender:type:content[:80]` 指纹去重，保留最近 600 条（上限 1000）

### 线程模型

- 单线程 `ThreadPoolExecutor` 串行化所有 wxauto 调用
- 每次调用前强制 `CoInitialize()` 确保 COM 线程安全
- `asyncio.run_in_executor` 桥接同步 wxauto API 到 async 框架

---

## 已知限制

| 限制 | 说明 |
|---|---|
| **Windows 专属** | 依赖 UIA + COM，无法跨平台 |
| **RuntimeId 不稳定** | 消息 ID 基于 UIA RuntimeId，微信重启后失效；已通过内容指纹兜底缓解 |
| **UI 自动化固有缺陷** | 窗口不能最小化/遮挡，微信布局变化可能导致控件查找失败 |
| **首次轮询漏消息** | 新会话首次 poll 时记录 ID 但不返回消息，避免历史消息风暴 |
| **群名/昵称作为 ID** | 权限判断依赖名称而非稳定 ID，改名后需同步更新配置 |

---

## 文件结构

```
core/adapter/src/wechat_pc/
├── __init__.py          # 导出 WeChatPCAdapter
├── manifest.json        # 适配器元信息
├── schema.json          # WebUI 配置表单定义
├── README.md            # 本文档
├── wechat_pc.py         # 适配器主类（IMAdapter 实现）
├── wechat_client.py     # wxauto 底层封装 + 消息模型
└── wxauto/              # 内嵌 wxauto 库（Apache 2.0）
    ├── __init__.py
    ├── wxauto.py
    ├── elements.py
    ├── uiautomation.py
    ├── ...
    └── LICENSE
```

---

## 依赖

- `uiautomation>=2.0.0`（Windows only）
- `pywin32>=306`（Windows only）
- `tenacity`, `pyperclip`, `pillow`, `colorama`, `comtypes`

---

## 更新日志

### v1.0.1（2026-05-01）

- **修复**：`wechat_client.py` 补充缺失的 `import time`，解决轮询时 `NameError` 崩溃
- **修复**：媒体消息（图片/文件/语音）内容无效时自动降级为 `Text`，避免 `ValueError` 崩溃
- **修复**：语音消息在有效路径时正确构造 `Record` 元素，而非仅映射为 `Text`
- **修复**：`start()` 启动失败时重新抛出异常，不再静默吞掉错误
- **优化**：发送文本时真正调用 wxauto 的 `@` 能力，产生微信端的 @ 提醒效果
- **优化**：消息去重增加内容指纹兜底（`session:sender:type:content`），应对 RuntimeId 变化
- **优化**：群聊 `is_mentioned` 不再硬编码，根据 `group_at_me_only` 和唤醒关键词动态判断

---

## License

适配器代码：**项目主 License**

内嵌 wxauto 库：**Apache License 2.0**（见 `wxauto/LICENSE`）
