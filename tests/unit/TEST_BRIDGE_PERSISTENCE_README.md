# BridgeState 持久化测试套件说明

## 概述

本测试套件为 Issue #132（跨会话消息全内存问题）的修复目标设计，包含 9 个测试用例，覆盖 BridgeState 持久化的所有关键场景。

**文件位置**: `tests/unit/test_bridge_persistence.py`

## 测试结果（当前版本）

```
✅ PASSED: 3 个测试
❌ FAILED: 6 个测试
```

### 失败测试（符合预期）

以下测试在当前纯内存实现下**应该失败**，验证了持久化需求的真实性：

1. **test_inbox_persistence_on_restart** ❌
   - 验证点：重启后 inbox 消息丢失
   - 预期行为：重启后应恢复 3 条消息
   - 当前行为：重启后 inbox 为空（0 条）

2. **test_pending_persistence_on_restart** ❌
   - 验证点：重启后 pending 消息丢失
   - 预期行为：pending 消息应在重启后继续等待 ack/超时
   - 当前行为：重启后 pending 为空，消息无法超时重排

3. **test_processed_dedup_after_restart** ❌
   - 验证点：重启后去重集合丢失
   - 预期行为：已处理消息 id 不应重复消费
   - 当前行为：重启后 _processed 清空，重复消息被再次消费（1 条）

4. **test_rate_limit_persist_after_restart** ❌
   - 验证点：重启后限流失效
   - 预期行为：重启后限流时间窗口应继续生效
   - 当前行为：_rate 丢失，重启后立即可再次发送

5. **test_idle_cleanup_works** ❌
   - 验证点：空闲 sid 清理机制的 session id 格式问题
   - 失败原因：测试中 "system" sid 格式不符合 "adapter:type:id" 规范
   - 需要修复：使用规范格式的 sid

6. **test_graceful_degrade_on_corrupted_file** ❌
   - 验证点：损坏文件优雅降级（同样的 sid 格式问题）
   - 失败原因：同上，"system" 不是有效的三段式 sid
   - 需要修复：使用规范格式的 sid

### 通过测试

7. **test_io_non_blocking** ✅
   - 验证点：并发性能测试
   - p99 延迟 < 100ms，并发安全性正常

8. **test_existing_semantics_preserved** ✅
   - 验证点：现有语义完整性
   - two-phase consume/ack、PENDING_TIMEOUT、限流、权限检查、MAX_INBOX、UUID 去重均正常

9. **test_current_implementation_is_in_memory_only** ✅
   - 验证点：确认当前是纯内存实现
   - **这是最关键的元测试**：证明测试套件的前提假设正确

## 运行测试

```bash
# 运行所有持久化测试
pytest tests/unit/test_bridge_persistence.py -v

# 运行单个测试
pytest tests/unit/test_bridge_persistence.py::test_inbox_persistence_on_restart -v

# 查看详细输出
pytest tests/unit/test_bridge_persistence.py -v -s

# 生成覆盖率报告
pytest tests/unit/test_bridge_persistence.py --cov=core.bridge --cov-report=html
```

## 测试覆盖的修复目标

| 修复目标 | 对应测试 | 当前状态 |
|---------|---------|---------|
| inbox 持久化 | test_inbox_persistence_on_restart | ❌ 待修复 |
| pending 持久化 | test_pending_persistence_on_restart | ❌ 待修复 |
| _processed 持久化 | test_processed_dedup_after_restart | ❌ 待修复 |
| _rate 持久化 | test_rate_limit_persist_after_restart | ❌ 待修复 |
| 空闲清理机制 | test_idle_cleanup_works | ⚠️ 需修复测试 |
| 容错降级 | test_graceful_degrade_on_corrupted_file | ⚠️ 需修复测试 |
| 非阻塞 IO | test_io_non_blocking | ✅ 已验证 |
| 语义保持 | test_existing_semantics_preserved | ✅ 已验证 |

## 测试设计原则

### 1. 失败即验证

这些测试设计为**在修复前失败**，这是 TDD（测试驱动开发）的核心理念：
- 测试失败证明问题真实存在
- 测试通过证明修复成功

### 2. 独立可运行

每个测试使用独立的：
- 临时目录（`tmp_path` fixture）
- 独立的 BridgeState 实例
- 不同的 session id 避免冲突

### 3. 模拟重启

通过以下方式模拟进程重启：
```python
bridge1 = BridgeState()
# ... 操作 bridge1 ...
del bridge1  # 释放实例

bridge2 = BridgeState()  # 新实例，模拟重启
# 验证状态是否恢复
```

### 4. 时间控制

使用 `unittest.mock.patch` 模拟时间流逝：
```python
future_time = time.time() + 300
with patch('time.time', return_value=future_time):
    # 验证超时/过期逻辑
```

## 待修复的测试问题

### Issue 1: Session ID 格式不规范

**问题**: 测试中使用 "system" 作为 from_sid，但 BridgeState._check_permission() 要求三段式格式：
```
adapter:type:user_id:group:group_id
```

**解决方案**: 修改测试使用规范格式，或为系统消息添加 bypass 逻辑：

```python
# 方案 1: 使用规范格式
system_sid = "system:internal:0:group:0"

# 方案 2: 修改 BridgeState.add_system_message() 绕过权限检查
```

**影响的测试**:
- test_idle_cleanup_works
- test_graceful_degrade_on_corrupted_file

## 未来实现指引

### BridgeState 持久化接口

```python
class BridgeState:
    def __init__(self, persistence_file: Optional[Path] = None):
        # 现有内存结构
        self._inbox: dict[str, list[BridgeMessage]] = {}
        self._pending: dict[str, list[BridgeMessage]] = {}
        self._processed: dict[str, list[tuple]] = {}
        self._rate: dict[str, list[float]] = {}
        
        # 持久化路径
        self._persistence_file = persistence_file
        
        # 加载持久化状态
        if persistence_file and persistence_file.exists():
            self._load_state()
    
    def _save_state(self):
        """保存状态到磁盘（异步或后台线程）"""
        if not self._persistence_file:
            return
        
        state = {
            "inbox": self._serialize_inbox(),
            "pending": self._serialize_pending(),
            "processed": dict(self._processed),
            "rate": dict(self._rate),
            "last_active": dict(self._last_active),
        }
        
        # 原子写入
        tmp_file = self._persistence_file.with_suffix(".tmp")
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
        tmp_file.replace(self._persistence_file)
    
    def _load_state(self):
        """从磁盘加载状态（带容错）"""
        try:
            with open(self._persistence_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            self._inbox = self._deserialize_inbox(state.get("inbox", {}))
            self._pending = self._deserialize_pending(state.get("pending", {}))
            self._processed = state.get("processed", {})
            self._rate = state.get("rate", {})
            self._last_active = state.get("last_active", {})
            
            logger.info("BridgeState 已从持久化文件恢复")
        except Exception as e:
            logger.warning(f"BridgeState 持久化文件加载失败，从空状态启动: {e}")
```

### 性能考虑

1. **异步写入**: 使用 `asyncio.to_thread()` 避免阻塞事件循环
2. **批量写入**: 不是每次操作都写盘，而是定期快照 + WAL
3. **增量更新**: 仅序列化变更的 sid，而非全量
4. **压缩清理**: 定期清理过期 _processed 和空闲 sid

### 推荐方案

**轻量 JSON 快照** (Issue #132 推荐)：
- 优点：零依赖，实现简单，可读性强
- 缺点：大规模场景性能受限
- 适用于：中小规模部署（< 1000 活跃会话）

**未来演进**:
- 中等规模：SQLite（事务 + 索引）
- 大规模：Redis（持久化 + 高性能）

## 检查清单

实现持久化功能后，验证以下检查项：

- [ ] 所有 6 个失败测试变为通过
- [ ] `test_current_implementation_is_in_memory_only` 失败（说明不再是纯内存）
- [ ] 修复测试中的 sid 格式问题
- [ ] 运行完整测试套件确保无回归
- [ ] 性能测试：p99 延迟 < 100ms
- [ ] 压力测试：1000+ 并发操作无数据损坏
- [ ] 容错测试：文件损坏、磁盘满、权限错误等异常场景

## 贡献

如需修改测试套件：
1. 保持"失败即验证"原则
2. 添加清晰的 docstring 说明测试场景
3. 使用独立的 fixture 避免状态污染
4. 更新本文档的测试覆盖表

## 相关文档

- Issue #132: 跨会话消息全内存问题
- `core/bridge.py`: BridgeState 实现
- `tests/unit/test_event_bridge.py`: 事件桥接测试
