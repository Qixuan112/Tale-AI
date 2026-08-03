# ChatAgent Unit Tests - Stage 3

## 测试目标

为**阶段3：抽取 ChatAgent**编写完整的单元测试套件，验证并发控制修复。

## 测试覆盖范围

### 1. 核心功能测试 (`test_chat_agent_basic.py`)
- ✅ generate() 基础调用
- ✅ 无状态验证（历史由外部传入）
- ✅ 超时参数传递
- ✅ 消息格式保持

### 2. 并发控制测试 (`test_chat_agent_concurrency.py`) **[P0 CRITICAL]**
- ✅ **不同会话并发执行**（证明全局锁已移除）
- ✅ **同一会话严格串行**（验证 per-session lock）
- ✅ **Semaphore 限流**（最多3个并发）
- ✅ 混合并发/串行场景
- ✅ 异常时锁释放
- ✅ 会话锁隔离

### 3. 性能基准测试 (`test_chat_agent_performance.py`) **[P0 CRITICAL]**
- ✅ **3用户并发基准**：<0.8s（证明并发工作）
- ✅ **同用户3消息基准**：~1.5s（证明串行工作）
- ✅ **5用户+限流基准**：~1.0s（证明 semaphore 工作）
- ✅ 混合负载基准：~1.5s
- ✅ 压力测试：10用户并发

### 4. 超时保护测试 (`test_chat_agent_timeout.py`) **[P0 修复 Issue #6]**
- ✅ **首次调用带超时**（修复当前 bug）
- ✅ 后续调用带超时
- ✅ 超时异常传播
- ✅ 超时释放锁
- ✅ 超时不影响其他会话
- ✅ 默认60秒超时
- ✅ 自定义超时

### 5. 锁管理测试 (`test_chat_agent_locks.py`)
- ✅ 按需创建会话锁
- ✅ 锁不可重入（防止递归 bug）
- ✅ 锁管理器线程安全
- ✅ Semaphore 可配置
- ✅ 异常时锁释放
- ✅ Semaphore 不泄漏
- ✅ 锁获取顺序（防死锁）

### 6. 抽象接口测试 (`test_llm_agent_base.py`)
- ✅ LLMAgent 抽象基类
- ✅ generate() 方法契约
- ✅ 无状态要求
- ✅ 超时参数契约

## 运行测试

### 安装依赖
```bash
pip install -r tests/requirements.txt
```

### 运行所有测试
```bash
# 从项目根目录运行
pytest tests/unit/agent/ -v

# 运行并发测试（最关键）
pytest tests/unit/agent/test_chat_agent_concurrency.py -v

# 运行性能基准测试
pytest tests/unit/agent/test_chat_agent_performance.py -v -s  # -s 显示打印输出

# 运行超时测试
pytest tests/unit/agent/test_chat_agent_timeout.py -v

# 查看覆盖率
pytest tests/unit/agent/ --cov=core.llm.agent --cov-report=term-missing
```

### 验收标准

**所有测试必须通过才能进入阶段4：**

1. ✅ **并发性能测试通过**
   - 3用户并发：总耗时 < 0.8s（非 ~1.5s）
   - 证明全局锁已移除

2. ✅ **顺序保证测试通过**
   - 同用户3消息：总耗时 ~1.5s
   - 证明 per-session lock 工作

3. ✅ **限流测试通过**
   - 5用户+Semaphore(3)：总耗时 ~1.0s
   - 证明 semaphore 工作

4. ✅ **超时测试通过**
   - 首次调用60s超时，挂起时抛出 TimeoutError
   - 证明 issue #6 已修复

5. ✅ **测试覆盖率 > 80%**

## 测试策略

### Mock 策略
- **LLMProvider.chat()**: Mock 返回固定延迟 + 固定响应
- **SessionManager**: Mock，不需要真实数据库
- **配置**: 使用默认测试配置

### 性能测试策略
- 使用 `asyncio.sleep()` 模拟 LLM 延迟
- 测量实际执行时间，验证并发 vs 串行
- 允许 0.2-0.5s 误差容限（系统开销）

### 并发测试策略
- 使用 `asyncio.gather()` 启动多个并发任务
- 验证执行顺序和时间
- 测试异常处理和锁释放

## 性能基准参考

| 场景 | LLM延迟 | 预期总时长 | 说明 |
|------|---------|-----------|------|
| 3用户并发 | 0.5s | <0.8s | 证明并发工作 |
| 同用户3消息 | 0.5s | ~1.5s | 证明串行工作 |
| 5用户+限流(3) | 0.5s | ~1.0s | 两波：3+2 |
| 10用户+限流(3) | 0.5s | ~2.0s | 四波：3+3+3+1 |

## 实现后更新

**当 ChatAgent 实现完成后，需要：**

1. 将所有 `pass # Placeholder` 替换为实际测试代码
2. 取消所有测试用例中的注释代码
3. 运行测试并确保全部通过
4. 记录实际性能数据
5. 更新本 README 的性能基准表格

## 测试锁定

**测试通过后，测试用例将被锁定：**
- ❌ 禁止修改测试用例（除非发现 bug）
- ❌ 禁止降低测试标准
- ✅ 可以添加新测试用例
- ✅ 可以优化测试性能

后续阶段的实现必须通过这些测试，不得修改测试来适应实现。
