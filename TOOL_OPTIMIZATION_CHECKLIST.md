# 工具系统优化清单

基于代码审查和审查报告，整理工具系统需要优化的问题。

## 🔴 P0 - 紧急修复（PR #151相关）

### 1. session_send功能损坏
- **问题**：AI输出打码ID（usr_1001），但`_send_cross_session`期望数字ID
- **影响**：跨会话消息功能完全失效
- **修复**：在`core/main.py:_send_cross_session()`添加ID还原逻辑
- **状态**：fix-pr151-issues agent执行中

### 2. query_group_list泄露真实群ID
- **位置**：`core/main.py:1286-1302`
- **问题**：返回的group_id未打码，安全漏洞
- **修复**：返回前调用`self._id_sanitizer.sanitize_group_id()`
- **状态**：fix-pr151-issues agent执行中

### 3. IDSanitizer内存泄漏
- **位置**：`core/utils/id_sanitizer.py`
- **问题**：_counter永久递增无上限
- **修复**：添加循环复用逻辑（1000-9999）
- **状态**：fix-pr151-issues agent执行中

---

## 🟡 P1 - 高优先级优化

### 4. 工具注册表重复定义
- **位置**：`core/function_caller.py:31`, `core/tools/registry.py`
- **问题**：AVAILABLE_TOOLS从registry动态生成，但handler仍在function_caller硬编码
- **建议**：将handler也注册到ToolRegistry，实现完全统一
- **预计工时**：2小时

### 5. 工具失败提示优化（已在PR #159）
- **位置**：`core/main.py:_execute_actions()`
- **改进**：工具不存在时自动返回工具列表
- **状态**：PR #159已实现 ✅

### 6. 插件工具注册机制
- **位置**：`core/function_caller.py:19-26`
- **问题**：plugin handler单独维护，与registry不统一
- **建议**：插件工具也通过ToolRegistry注册
- **预计工时**：3小时

---

## 🟢 P2 - 中优先级优化

### 7. Function Calling prompt生成
- **位置**：`core/tools/registry.py:259-262`
- **问题**：FC_FORMAT_TEMPLATE在prompt.py硬编码，与registry分离
- **建议**：由registry生成完整FC prompt
- **预计工时**：1小时

### 8. 工具参数验证
- **当前**：只在LLM端验证
- **建议**：在execute_function中添加参数类型/必填验证
- **预计工时**：2小时

### 9. 工具执行日志
- **当前**：分散在各处
- **建议**：统一的工具调用日志记录（工具名、参数、结果、耗时）
- **预计工时**：1小时

---

## 执行计划

### 立即执行（今晚）
- ✅ P0问题1-3：fix-pr151-issues agent执行中

### 明日执行
- P1问题4：工具注册表统一
- P1问题6：插件工具统一

### 后续迭代
- P2问题7-9：纳入Issue #152

---

最后更新：2026-07-30
