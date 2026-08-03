# Concurrency Lock Tests (Issue #130)

## 概述

本测试套件为 Issue #130 的全局锁并发问题编写，用于验证修复前后的系统行为。

## 问题背景

当前实现存在全局锁瓶颈：
- `core/main.py:82` 的 `self._chat_lock = asyncio.Lock()` 是全局锁
- 所有会话消息串行处理，一个带图消息能卡半分钟，其他用户全排队
- 根因：`ChatLLM` 是有状态单例（`self.messages`/`self.current_sid`）

## 修复目标

1. **ChatLLM 无状态化**：`chat()` 改为纯函数，去掉 `self.messages`/`self.current_sid`
2. **Per-session 锁**：每个会话独立锁，不同会话可并行
3. **Semaphore(3) 限流**：全局最多 3 个并发请求，防止爆线程池
4. **同会话串行**：同一会话内消息仍然串行，保证顺序

## 测试套件结构

### Test 1: `test_parallel_different_sessions`
**目标**：验证不同会话可以并行执行

- 创建 3 个不同 session（group_A, group_B, group_C）
- 同时调用 `_handle_respond_message`
- **断言**：3 个 LLM 调用时间戳有重叠（并行执行）
- **修复前预期**：❌ FAIL - 全局锁导致串行，耗时 ~600ms
- **修复后预期**：✅ PASS - 并行执行，耗时 ~200ms

### Test 2: `test_serial_same_session`
**目标**：验证同会话消息串行执行，保证顺序

- 同一 session 发送 2 条消息
- **断言**：第二条必须等第一条完成后才开始
- **修复前预期**：✅ PASS（全局锁天然保证顺序）
- **修复后预期**：✅ PASS（per-session 锁保证顺序）

### Test 3: `test_semaphore_limit`
**目标**：验证 Semaphore(3) 限制并发数

- 同时发 10 个请求（不同 session）
- **断言**：同时执行的最多 3 个，其余排队
- 记录每个时刻的活跃任务数，验证峰值 ≤ 3
- **修复前预期**：❌ FAIL - 全局锁限制为 1，max_active=1
- **修复后预期**：✅ PASS - Semaphore(3) 生效，max_active=3

### Test 4: `test_chatllm_stateless`
**目标**：验证 ChatLLM 无状态化

- 调用 `ChatLLM.chat()` 前后
- **断言**：实例的 `self.messages`/`self.current_sid` 等状态属性不变（或不存在）
- 验证连续两次调用不互相污染
- **修复前预期**：❌ FAIL - `self.messages`/`self.current_sid` 会变化
- **修复后预期**：✅ PASS - 无状态，属性不存在或不变

### Test 5: `test_high_concurrency_stability`
**目标**：压力测试，验证系统稳定性

- 50 个并发请求（随机 session）
- **断言**：全部成功完成，无 OOM，无死锁
- 记录内存/耗时，验证性能可接受
- **修复前预期**：⚠️ SLOW - 串行执行慢但能完成
- **修复后预期**：✅ FAST - 并行执行，显著提速

### Test 6: `test_lock_acquisition_order`
**目标**：验证锁获取顺序和独立性

- 交错发送 A, B, A, B 四条消息（2 个 session）
- **断言**：不同 session 的锁持有时间有重叠
- **修复前预期**：❌ FAIL - 全局锁无重叠
- **修复后预期**：✅ PASS - per-session 锁有重叠

## 运行测试

### 运行完整测试套件
```bash
pytest tests/unit/test_concurrency_lock.py -v
```

### 运行单个测试
```bash
pytest tests/unit/test_concurrency_lock.py::test_parallel_different_sessions -v -s
```

### 查看详细输出（包括时间线）
```bash
pytest tests/unit/test_concurrency_lock.py -v -s
```

### 生成测试报告
```bash
pytest tests/unit/test_concurrency_lock.py --html=report.html --self-contained-html
```

## 预期结果

### 修复前（当前实现）
```
tests/unit/test_concurrency_lock.py::test_parallel_different_sessions FAILED
tests/unit/test_concurrency_lock.py::test_serial_same_session PASSED
tests/unit/test_concurrency_lock.py::test_semaphore_limit FAILED
tests/unit/test_concurrency_lock.py::test_chatllm_stateless FAILED
tests/unit/test_concurrency_lock.py::test_high_concurrency_stability PASSED (但很慢)
tests/unit/test_concurrency_lock.py::test_lock_acquisition_order FAILED

总结: 4 FAILED, 2 PASSED
```

### 修复后（目标状态）
```
tests/unit/test_concurrency_lock.py::test_parallel_different_sessions PASSED
tests/unit/test_concurrency_lock.py::test_serial_same_session PASSED
tests/unit/test_concurrency_lock.py::test_semaphore_limit PASSED
tests/unit/test_concurrency_lock.py::test_chatllm_stateless PASSED
tests/unit/test_concurrency_lock.py::test_high_concurrency_stability PASSED
tests/unit/test_concurrency_lock.py::test_lock_acquisition_order PASSED

总结: 6 PASSED
```

## Mock 说明

测试使用了以下 mock 对象：

1. **mock_chatllm**：模拟 ChatLLM，包含：
   - `chat()` 方法，200ms 延迟模拟网络 I/O
   - `set_session()` 方法，模拟会话状态切换
   - `messages` 和 `current_sid` 状态属性（验证无状态化）

2. **mock_adapter_bridge**：模拟消息发送适配器
   - 快速返回成功，避免测试被发送逻辑拖慢

3. **tale_core_with_mocks**：组装完整的 TaleCore 实例
   - 注入 mock 依赖
   - 禁用持久化（`session_manager=None`）
   - 配置线程池用于测试

## 时间线分析

测试会输出详细的执行时间线，格式如下：

```
=== Execution Timeline (test_parallel_different_sessions) ===
  [   5.2ms] start - Hello from A
  [   7.8ms] start - Hello from B
  [  10.1ms] start - Hello from C
  [ 205.3ms] end   - Hello from A
  [ 207.9ms] end   - Hello from B
  [ 210.2ms] end   - Hello from C

Start time window: 4.9ms
Overlapping executions: 3 out of 3 possible
Total execution time: 210.5ms
```

这个时间线清楚展示：
- 3 个请求几乎同时启动（5-10ms 窗口）
- 同时执行 200ms
- 几乎同时结束（205-210ms）
- **总耗时 ~210ms，而非串行的 600ms**

## 注意事项

1. **测试设计为"修复前必须失败"**
   - 这验证了测试确实在检测问题
   - 不是假阳性（恒通过的无效测试）

2. **时间容差设置**
   - 考虑了 CI 环境的性能波动
   - 允许 ±50ms 的误差范围

3. **线程安全**
   - 所有共享状态访问都使用 `threading.Lock()` 保护
   - 避免测试本身引入竞态条件

4. **隔离性**
   - 每个测试独立运行，不依赖其他测试
   - 可以单独运行或任意顺序运行

## 后续工作

修复实施后，需要：

1. ✅ 运行测试套件，确保全部通过
2. ✅ 检查代码覆盖率（目标 >80%）
3. ✅ 性能基准测试（对比修复前后）
4. ✅ 集成测试（真实 QQ/WeChat 适配器）
5. ✅ 压力测试（100+ 并发用户）

## 参考

- Issue #130: https://github.com/your-repo/Tale-AI/issues/130
- 修复 PR: (待创建)
- 设计文档: (待补充)
