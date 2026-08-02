# PR #117 配置热更新功能测试文档

## 测试概述

本测试套件为 PR #117 的配置热更新功能提供全面的单元测试覆盖。

## 测试文件

- `tests/test_config_hot_reload.py` - 配置热更新功能完整测试套件

## 测试覆盖范围

### 1. ToolLLM 热更新测试 (6个测试)

测试 `ToolLLM._on_config_reloaded()` 方法：

- ✅ `test_on_config_reloaded_updates_api_key` - 验证 api_key 正确更新
- ✅ `test_on_config_reloaded_updates_base_url` - 验证 base_url 正确更新
- ✅ `test_on_config_reloaded_updates_model` - 验证 model 正确更新
- ✅ `test_on_config_reloaded_reinitializes_provider` - 验证 provider 重新初始化
- ✅ `test_on_config_reloaded_logs_message` - 验证日志输出
- ✅ `test_on_config_reloaded_with_empty_config` - 验证空配置容错

### 2. AdapterManager.restart_adapter 测试 (5个测试)

测试适配器重启功能：

- ✅ `test_restart_adapter_success` - 成功重启场景
- ✅ `test_restart_adapter_not_running` - 重启不存在的适配器
- ✅ `test_restart_adapter_stop_failure` - stop 失败的容错
- ✅ `test_restart_adapter_start_failure` - start 失败返回 False
- ✅ `test_restart_adapter_with_different_type` - 更换适配器类型

### 3. AdapterBridge 配置同步测试 (7个测试)

测试 `_sync_adapter_configs` 和 `_do_sync_adapter_configs` 方法：

- ✅ `test_sync_starts_new_adapter` - 检测并启动新增适配器
- ✅ `test_sync_stops_deleted_adapter` - 检测并停止已删除适配器
- ✅ `test_sync_restarts_changed_adapter` - 检测并重启配置变更的适配器
- ✅ `test_sync_unchanged_adapter_not_restarted` - 配置未变不触发重启
- ✅ `test_sync_handles_yaml_load_failure` - YAML 读取失败容错
- ✅ `test_sync_ignores_disabled_adapters` - 忽略 enabled=False 的适配器
- ✅ `test_sync_ignores_unsupported_adapter_types` - 忽略不支持的类型

### 4. 集成测试 (4个测试)

测试完整的事件触发链路：

- ✅ `test_eventbus_triggers_toolllm_reload` - EventBus → ToolLLM
- ✅ `test_eventbus_triggers_adapter_sync` - EventBus → AdapterBridge
- ✅ `test_talecore_on_config_reloaded_calls_toolllm` - TaleCore 调用链
- ✅ `test_full_integration_eventbus_to_all_components` - 完整集成测试

## 运行测试

### 安装依赖

```bash
pip install pytest pytest-asyncio pytest-mock
```

### 运行所有测试

```bash
# 运行完整测试套件
pytest tests/test_config_hot_reload.py -v

# 运行所有测试（包括其他测试文件）
pytest tests/ -v
```

### 运行特定测试类

```bash
# 只运行 ToolLLM 热更新测试
pytest tests/test_config_hot_reload.py::TestToolLLMConfigReload -v

# 只运行适配器重启测试
pytest tests/test_config_hot_reload.py::TestAdapterManagerRestart -v

# 只运行配置同步测试
pytest tests/test_config_hot_reload.py::TestAdapterBridgeSync -v

# 只运行集成测试
pytest tests/test_config_hot_reload.py::TestConfigReloadIntegration -v
```

### 运行特定测试用例

```bash
# 运行单个测试
pytest tests/test_config_hot_reload.py::TestToolLLMConfigReload::test_on_config_reloaded_updates_api_key -v
```

### 显示详细输出

```bash
# 显示测试覆盖率
pytest tests/test_config_hot_reload.py --cov=core.llm.toolllm --cov=core.adapter.manager --cov=core.adapter.integration -v

# 显示失败详情
pytest tests/test_config_hot_reload.py -v --tb=long

# 显示 print 输出
pytest tests/test_config_hot_reload.py -v -s
```

## 测试策略

### Mock 使用

所有测试使用 `unittest.mock` 进行依赖隔离：

- **ToolLLM 测试**: Mock `provider_manager`, `get_registry`, `create_tool_context`, `OpenAICompatibleProvider`
- **AdapterManager 测试**: Mock 适配器类和实例，模拟异步操作
- **AdapterBridge 测试**: Mock `config_loader`, EventBus, 适配器管理器
- **集成测试**: 最小化 Mock，验证真实交互

### 异步测试

使用 `@pytest.mark.asyncio` 装饰器标记异步测试：

```python
@pytest.mark.asyncio
async def test_restart_adapter_success(self):
    # 测试代码
    await manager.restart_adapter(...)
```

### 容错测试

每个功能都包含异常处理测试：

- 空配置
- 文件读取失败
- 网络异常
- 适配器启动/停止失败

## 代码覆盖

### 变更文件覆盖率

| 文件 | 变更方法 | 测试覆盖 |
|------|----------|----------|
| `core/llm/toolllm.py` | `_on_config_reloaded()` | ✅ 6个测试 |
| `core/adapter/manager.py` | `restart_adapter()` | ✅ 5个测试 |
| `core/adapter/integration.py` | `_sync_adapter_configs()`, `_do_sync_adapter_configs()` | ✅ 7个测试 |
| `core/main.py` | `_on_config_reloaded()` | ✅ 1个测试 |

### 场景覆盖

- ✅ 正常流程: 配置变更 → 热更新生效
- ✅ 边界条件: 空配置、不存在的适配器
- ✅ 异常处理: 文件读取失败、适配器启动失败
- ✅ 并发安全: 多个适配器同时变更
- ✅ 集成测试: EventBus 事件链路完整性

## 测试结果

### 预期结果

所有 22 个测试应该通过：

```
tests/test_config_hot_reload.py::TestToolLLMConfigReload::test_on_config_reloaded_updates_api_key PASSED
tests/test_config_hot_reload.py::TestToolLLMConfigReload::test_on_config_reloaded_updates_base_url PASSED
tests/test_config_hot_reload.py::TestToolLLMConfigReload::test_on_config_reloaded_updates_model PASSED
tests/test_config_hot_reload.py::TestToolLLMConfigReload::test_on_config_reloaded_reinitializes_provider PASSED
tests/test_config_hot_reload.py::TestToolLLMConfigReload::test_on_config_reloaded_logs_message PASSED
tests/test_config_hot_reload.py::TestToolLLMConfigReload::test_on_config_reloaded_with_empty_config PASSED
tests/test_config_hot_reload.py::TestAdapterManagerRestart::test_restart_adapter_success PASSED
tests/test_config_hot_reload.py::TestAdapterManagerRestart::test_restart_adapter_not_running PASSED
tests/test_config_hot_reload.py::TestAdapterManagerRestart::test_restart_adapter_stop_failure PASSED
tests/test_config_hot_reload.py::TestAdapterManagerRestart::test_restart_adapter_start_failure PASSED
tests/test_config_hot_reload.py::TestAdapterManagerRestart::test_restart_adapter_with_different_type PASSED
tests/test_config_hot_reload.py::TestAdapterBridgeSync::test_sync_starts_new_adapter PASSED
tests/test_config_hot_reload.py::TestAdapterBridgeSync::test_sync_stops_deleted_adapter PASSED
tests/test_config_hot_reload.py::TestAdapterBridgeSync::test_sync_restarts_changed_adapter PASSED
tests/test_config_hot_reload.py::TestAdapterBridgeSync::test_sync_unchanged_adapter_not_restarted PASSED
tests/test_config_hot_reload.py::TestAdapterBridgeSync::test_sync_handles_yaml_load_failure PASSED
tests/test_config_hot_reload.py::TestAdapterBridgeSync::test_sync_ignores_disabled_adapters PASSED
tests/test_config_hot_reload.py::TestAdapterBridgeSync::test_sync_ignores_unsupported_adapter_types PASSED
tests/test_config_hot_reload.py::TestConfigReloadIntegration::test_eventbus_triggers_toolllm_reload PASSED
tests/test_config_hot_reload.py::TestConfigReloadIntegration::test_eventbus_triggers_adapter_sync PASSED
tests/test_config_hot_reload.py::TestConfigReloadIntegration::test_talecore_on_config_reloaded_calls_toolllm PASSED
tests/test_config_hot_reload.py::TestConfigReloadIntegration::test_full_integration_eventbus_to_all_components PASSED

===================== 22 passed in X.XXs =====================
```

## CI/CD 集成

### GitHub Actions 配置示例

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-asyncio pytest-mock pytest-cov
      - run: pytest tests/test_config_hot_reload.py -v --cov=core --cov-report=xml
      - uses: codecov/codecov-action@v3
```

## 常见问题

### Q: 测试运行很慢

A: 异步测试需要时间启动事件循环。可以使用 `-n auto` 并行运行测试（需要安装 `pytest-xdist`）。

### Q: Mock 对象行为不符合预期

A: 确保使用 `AsyncMock` 而非 `Mock` 来模拟异步方法。

### Q: 导入错误

A: 确保在项目根目录运行测试，并且 `core` 模块在 Python 路径中。

## 维护指南

### 添加新测试

1. 在对应的测试类中添加新方法
2. 使用清晰的 docstring 说明测试目的
3. 遵循现有的 Mock 模式
4. 更新本文档的覆盖列表

### 更新测试

当功能变更时：

1. 先运行测试确认失败
2. 更新测试以反映新行为
3. 验证所有测试通过
4. 更新文档说明

## 参考资料

- [pytest 文档](https://docs.pytest.org/)
- [pytest-asyncio 文档](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock 文档](https://docs.python.org/3/library/unittest.mock.html)
- [PR #117 设计文档](../docs/pr117_config_hot_reload.md)
