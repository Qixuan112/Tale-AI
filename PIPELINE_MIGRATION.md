# StandardPipeline 灰度迁移指南

## 概述

本文档描述从旧版消息处理流程（`_handle_respond_message`）迁移到新版 StandardPipeline（`_handle_respond_message_v2`）的灰度策略。

## 当前状态

- **默认状态**: `use_pipeline=false`（使用旧版流程）
- **新流程状态**: 已实现，待激活
- **切换方式**: 
  - 修改 `data/config/behavior.yaml` 中 `bot.use_pipeline` 为 `true`
  - 或设置环境变量 `TALE_USE_PIPELINE=true`（暂不支持，未来可扩展）

## 架构差异

### 旧版流程（Legacy Path）
```
_handle_respond_message() → 
  直接调用 LLM → 
  解析 XML → 
  执行工具 → 
  发送回复
```

### 新版流程（Pipeline Path）
```
_handle_respond_message_v2() → 
  StandardPipeline.execute() →
    8个标准化 Stage（可扩展、可插件化） →
      BuildUserInput → NameMapping → SessionInit → 
      ContextBuild → LLMCall → MessageParse → 
      ToolExecute → ReplyDeliver
```

## 新流程优势

1. **模块化**: 每个 Stage 独立可测试
2. **可扩展**: 通过 EventBus 插件钩子扩展
3. **错误恢复**: 每个 Stage 支持 `on_error()` 重试/降级
4. **并发控制**: Semaphore + per-session lock，修复 P0-1 并发 bug
5. **早期终止**: 支持 `ctx.should_stop` 提前退出
6. **监控友好**: 每个 Stage 发出 `pipeline_stage_before/after` 事件

## 灰度计划

### Phase 1: 本地验证（Day 1-2）
- [ ] 开发环境设置 `use_pipeline=true`
- [ ] 测试基本消息收发
- [ ] 测试工具调用（浏览器、搜索、计算器）
- [ ] 测试群聊 @mention
- [ ] 测试错误场景（LLM 超时、工具失败）
- [ ] 对比日志输出：`[Legacy Path]` vs `[Pipeline Path]`

### Phase 2: 小范围灰度（Day 3-4）
- [ ] 生产环境 10% 流量（可通过单独实例配置）
- [ ] 监控错误率、响应延迟
- [ ] 收集用户反馈
- [ ] 确认无严重回归

### Phase 3: 扩大灰度（Day 5-6）
- [ ] 扩大到 50% 流量
- [ ] 持续监控指标
- [ ] 对比两条路径性能

### Phase 4: 全量切换（Day 7+）
- [ ] 设置 `use_pipeline=true` 为默认值
- [ ] 观察 3-7 天
- [ ] 确认稳定后删除旧代码（`_handle_respond_message` 标记为 deprecated）

## 日志监控

### 识别当前路径
```bash
# 旧版流程
grep "\[Legacy Path\]" logs/tale.log

# 新版流程
grep "\[Pipeline Path\]" logs/tale.log
```

### 关键指标
- **消息处理延迟**: `_handle_respond_message` 耗时 vs `StandardPipeline.execute` 耗时
- **错误率**: 两条路径异常捕获对比
- **Stage 失败率**: `pipeline_stage_after_{name}` 事件中的 error 字段

## 回滚方案

### 立即回滚
```yaml
# data/config/behavior.yaml
bot:
  use_pipeline: false  # 改回 false
```

无需重启，ConfigLoader 支持热重载（部分配置），但 `use_pipeline` 在消息分发时读取，需重启生效。

### 紧急回滚（环境变量，未来支持）
```bash
export TALE_USE_PIPELINE=false
# 重启服务
```

## 已知限制

1. **配置热重载**: `use_pipeline` 修改需要重启 Tale 进程才能生效
2. **会话状态**: 切换路径时，进行中的消息可能出现不一致（极低概率）
3. **日志格式**: Pipeline 路径日志更详细，可能增加日志体积

## 风险评估

| 风险 | 严重性 | 缓解措施 |
|------|--------|----------|
| Pipeline 实现 bug | 高 | 小范围灰度 + 快速回滚 |
| 性能回归 | 中 | 监控延迟指标，8 Stage 顺序执行可能略慢 |
| 工具调用兼容性 | 低 | 已复用相同 `FunctionCaller` 实现 |
| 并发控制副作用 | 低 | Semaphore 限制可能降低高并发场景吞吐 |

## 测试检查清单

- [ ] 单轮对话（私聊/群聊）
- [ ] 多轮对话记忆
- [ ] 工具调用（browser_open, browser_search, calculator, weather_query）
- [ ] @mention 名称映射
- [ ] 唤醒词（关键词/引用）
- [ ] 黑白名单过滤
- [ ] 错误重试（LLM 超时）
- [ ] 并发消息处理（同会话 + 不同会话）
- [ ] 适配器消息回复（QQ/WeChat/WebSocket）

## 未来清理

全量稳定后（预计 2-3 周）：

1. 删除 `_handle_respond_message()` 旧方法
2. 重命名 `_handle_respond_message_v2()` 为 `_handle_respond_message()`
3. 移除 Feature Flag 配置
4. 更新文档移除迁移相关说明

## 联系与反馈

- **问题上报**: GitHub Issues
- **紧急回滚**: 直接修改 `behavior.yaml` 并重启

---

*最后更新: 2026-08-04*
