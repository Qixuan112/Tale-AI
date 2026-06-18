# QQ 适配器改进计划

对比调研后梳理的 QQ 适配器缺口，按优先级排列。

## P0 — 高优先级

- [ ] **`post_type: notice` 事件支持**
  - `poke`（戳一戳）— 最常见的轻交互
  - `group_increase`（新人入群）— 可做欢迎
  - `group_ban`（禁言通知）— 了解自己被禁言
  - 在 `_on_raw_message` 中增加 `notice` 分支，转为 `PlatformEvent` 上抛
  - 当前仅 `poke` 有文案解析，其余 notice 需后续补充

- [x] **引用消息追溯原文**
  - 收到 `reply` 段时，调用 `get_msg` API 获取被回复消息的原文内容
  - 填充到 `MessageContent.reply_text` 字段，让 ChatLLM 能理解上下文

- [x] **撤回消息 API**
  - 封装 `delete_msg` 为 `QQApiClient` 方法
  - 注册为 ToolLLM 可用的工具

## P1 — 中优先级

- [ ] **`forward` 转发消息链解析**
  - 调用 `get_forward_msg` API 递归展开每条子消息
  - 提取文字拼入 `text`，供 LLM 理解

- [ ] **发送戳一戳**
  - 封装 `group_poke` / `friend_poke` API
  - 作为轻量交互反馈

- [ ] **发送表情/贴图**
  - `face` 段发送指定 QQ 表情
  - `mface` 段发送动画表情

## P2 — 低优先级

- [x] **`record` 语音消息接收**
  - 解析 `record` 段，提取 URL 信息
  - 配合语音转文字（需外部 STT 服务）

- [ ] **`file` 文件传输**
  - 接收文件段，下载到本地
  - 可配合 ToolLLM 处理文件内容

- [ ] **`image` base64 支持**
  - 入站解析 base64 图片（NapCat 通常返回 URL，部分场景返回 base64）
  - 发送时支持 base64 格式

- [ ] **群管理 API 扩展**
  - `set_group_ban` 禁言/解禁
  - `set_group_kick` 踢人
  - `set_group_admin` 设置管理
  - `send_group_notice` 群公告

- [ ] **`location` / `share` / `redbag` 等小众段解析**
  - 解析后记入日志或结构化字段

- [ ] **HTTP 回调作为 WebSocket 降级**
  - 实现通过 `http_url` 调用 API（当前只写了配置但从未使用）

## 架构改进

- [ ] **图片自动 LLM 描述**
  - 收到图片时，调用 ChatLLM / VLM 生成本地语言描述，拼入上下文
  - 让 bot "看到"图片内容而不是只收到 url
