# Prompt Cache 优化测试套件

## 概述

本测试套件为 **Issue #131: Prompt 缓存失效问题** 提供完整的单元测试覆盖。

### 问题背景

Tale-AI 当前实现中，`core/config/prompt.py` 的 `CHAT_BASE_TEMPLATE` 将时间戳和今日计划直接烤进 system prompt：
- 每次调用时间戳变化
- 导致 OpenAI/DeepSeek/Qwen 的前缀缓存全部 miss
- 实际结果：每条消息都重付相同的 prompt token 费用

### 修复目标

1. **System prompt 字节级稳定**：不含易变内容（时间戳、日程）
2. **易变段移至 user message**：用 `<system_reminder>` 包裹，挪到最新一条 user message 头部
3. **易变段不持久化**：`persist=False`，不写入历史记录
4. **缓存命中率提升**：从 ~0% 提升到 > 70%

---

## 测试用例

### Test 1: `test_system_prompt_stability`
**System prompt 字节级稳定性**

**验证内容：**
- 连续调用 10 次（不同时间戳）
- 断言：system prompt 内容字节完全一致
- 验证：不包含时间戳、今日计划

**修复前状态：** ❌ **FAILED**
```
AssertionError: System prompt 不应包含时间戳
assert '当前时间' not in system_content
```

**修复后预期：** ✅ **PASSED**

---

### Test 2: `test_dynamic_content_in_user_message`
**动态内容移至 user message**

**验证内容：**
- 调用 `build_messages()`
- 断言：时间戳/今日计划出现在最后一条 user message 的前缀
- 验证：用 `<system_reminder>` 标签包裹

**修复前状态：** ❌ **FAILED**
```
AttributeError: 动态内容尚未移至 user message
```

**修复后预期：** ✅ **PASSED**

---

### Test 3: `test_dynamic_section_not_persisted`
**动态段不持久化到历史**

**验证内容：**
- 添加 dynamic section（时间戳、今日计划）
- 调用写历史的逻辑
- 断言：历史记录中不包含 `persist=False` 的段

**修复前状态：** ⏭️ **SKIPPED**
```
pytest.skip("persist 字段尚未实现，等待修复")
```

**修复后预期：** ✅ **PASSED**

---

### Test 4: `test_cache_hit_rate_improvement`
**缓存命中率提升**

**验证内容：**
- Mock provider 返回 cache hit 信息
- 连续 20 次调用（模拟对话）
- 断言：缓存命中率 > 70%

**修复前状态：** ✅ **PASSED** (mock 通过，实际场景会失败)

**修复后预期：** ✅ **PASSED** (真实场景也通过)

---

### Test 5: `test_semantic_preservation`
**语义完整性验证**

**验证内容：**
- 验证修复后 prompt 渲染的语义完整性
- 断言：时间戳/今日计划信息仍然传达给 LLM
- 验证：中文渲染不退化

**修复前状态：** ✅ **PASSED**

**修复后预期：** ✅ **PASSED**

---

### Test 6: `test_prompt_section_fields`
**PromptSection 新增字段验证**

**验证内容：**
- 验证 PromptSection 新增字段正确：
  - `dynamic: bool` 字段存在
  - `persist: bool` 字段存在
- 测试默认值正确

**修复前状态：** ⏭️ **SKIPPED**
```
pytest.skip("dynamic 和 persist 字段尚未实现")
```

**修复后预期：** ✅ **PASSED**

---

### Test 7: `test_context_cache_strategy`
**Context 缓存策略验证**

**验证内容：**
- 验证 `multi_message` 策略正确分离静态和动态内容
- 断言：静态内容在第一条 system 消息，动态内容在第二条

**修复前状态：** ✅ **PASSED**

**修复后预期：** ✅ **PASSED**

---

### Test 8: `test_timestamp_isolation`
**时间戳隔离验证**

**验证内容：**
- 多次调用，每次检查 system prompt
- 断言：system prompt 中完全不包含时间戳

**修复前状态：** ❌ **FAILED**
```
AssertionError: System prompt 不应包含时间相关内容: 当前时间
```

**修复后预期：** ✅ **PASSED**

---

### Test 9: `test_plan_content_isolation`
**日程内容隔离验证**

**验证内容：**
- 验证 system prompt 中不包含今日日程
- 断言：不包含 "## 早晨"、"## 中午"、"## 晚上" 等具体日程

**修复前状态：** ✅ **PASSED** (当前实现未注入日程)

**修复后预期：** ✅ **PASSED**

---

## 运行测试

### 完整测试套件
```bash
pytest tests/unit/test_prompt_cache.py -v
```

### 运行单个测试
```bash
pytest tests/unit/test_prompt_cache.py::TestPromptCacheOptimization::test_system_prompt_stability -v
```

### 显示详细输出
```bash
pytest tests/unit/test_prompt_cache.py -v --tb=long
```

### 生成覆盖率报告
```bash
pytest tests/unit/test_prompt_cache.py --cov=core.llm --cov-report=html
```

---

## 当前测试状态

**运行环境：** Python 3.11.9, pytest 9.0.3

**测试结果（修复前）：**
```
===================== test session starts ======================
tests/unit/test_prompt_cache.py::TestPromptCacheOptimization::
  test_system_prompt_stability              FAILED  [ 11%]
  test_dynamic_content_in_user_message      FAILED  [ 22%]
  test_dynamic_section_not_persisted        SKIPPED [ 33%]
  test_cache_hit_rate_improvement           PASSED  [ 44%]
  test_semantic_preservation                PASSED  [ 55%]
  test_prompt_section_fields                SKIPPED [ 66%]
  test_context_cache_strategy               PASSED  [ 77%]
  test_timestamp_isolation                  FAILED  [ 88%]
  test_plan_content_isolation               PASSED  [100%]

========= 3 failed, 4 passed, 2 skipped in 4.33s ==============
```

**关键失败点：**
1. ❌ `test_system_prompt_stability` - system prompt 包含 "当前时间"
2. ❌ `test_dynamic_content_in_user_message` - 动态内容未移至 user message
3. ❌ `test_timestamp_isolation` - system prompt 包含时间戳

**预期修复后：**
```
================= 9 passed in X.XXs ================
```

---

## 实现检查清单

修复 Issue #131 时，确保以下所有测试通过：

- [ ] **Test 1** - System prompt 字节级稳定（不含时间戳）
- [ ] **Test 2** - 动态内容移至 user message（用 `<system_reminder>` 包裹）
- [ ] **Test 3** - 动态段不持久化（`persist=False`）
- [ ] **Test 4** - 缓存命中率 > 70%
- [ ] **Test 5** - 语义完整性保持
- [ ] **Test 6** - PromptSection 支持 `dynamic` 和 `persist` 字段
- [ ] **Test 7** - `multi_message` 策略正确分离静态/动态
- [ ] **Test 8** - System prompt 完全不含时间戳
- [ ] **Test 9** - System prompt 不含具体日程

---

## 依赖项

测试依赖以下 Python 包：
```
pytest>=9.0.3
pytest-asyncio>=1.3.0
pytest-mock>=3.15.1
```

已在 `tests/requirements.txt` 中声明。

---

## 相关文件

- **测试文件：** `tests/unit/test_prompt_cache.py`
- **被测模块：**
  - `core/llm/chatllm.py` - ChatLLM 主类
  - `core/llm/context/agent_context.py` - AgentContext 上下文管理
  - `core/llm/context/section.py` - PromptSection 数据结构
  - `core/config/prompt.py` - 提示词模板

---

## 修复指南

### Step 1: 添加 PromptSection 新字段
在 `core/llm/context/section.py` 中：
```python
@dataclass
class PromptSection:
    name: str
    content: str = ""
    cacheable: bool = False
    order: int = 0
    description: str = ""
    dynamic: bool = False      # 新增：是否为动态内容
    persist: bool = True        # 新增：是否持久化到历史
    _content_provider: Optional[Callable[[], str]] = field(default=None, repr=False)
```

### Step 2: 分离静态和动态内容
在 `core/config/prompt.py` 中，确保：
- `CHAT_BASE_TEMPLATE` 不包含时间戳、日程等易变内容
- 静态提示词标记为 `cacheable=True`

### Step 3: 动态内容注入 user message
在 `core/llm/chatllm.py` 的 `chat()` 方法中：
```python
def chat(self, user_input, ...):
    # 构建动态段
    dynamic_content = self._build_dynamic_section()
    
    # 注入到 user message 头部
    if dynamic_content:
        user_input = f"<system_reminder>\n{dynamic_content}\n</system_reminder>\n\n{user_input}"
    
    # ... 继续原有逻辑
```

### Step 4: 动态段不持久化
在持久化逻辑中：
```python
def _save_session_memory(self, persist_content: str = None):
    # 移除 <system_reminder> 包裹的动态段
    cleaned_content = self._strip_dynamic_sections(persist_content)
    # ... 持久化 cleaned_content
```

---

## 验证方法

### 1. 运行测试套件
```bash
pytest tests/unit/test_prompt_cache.py -v
```

### 2. 手动验证缓存命中
修复后，观察 LLM API 返回的 `usage` 字段：
```python
{
  "usage": {
    "prompt_tokens": 1500,
    "completion_tokens": 100,
    "prompt_cache_hit_tokens": 1400,  # 应该 > 0
    "prompt_cache_miss_tokens": 100
  }
}
```

### 3. 观察 Token 成本
- **修复前：** 每次对话都支付全部 prompt tokens
- **修复后：** 第二次起只支付 cache miss 部分（动态内容）

---

## 注意事项

1. **向后兼容**：`persist` 默认为 `True`，保持现有行为
2. **多 Provider 支持**：OpenAI、DeepSeek、Qwen 均支持 prompt caching
3. **缓存过期**：Provider 通常在 5-10 分钟后过期缓存
4. **最小缓存单位**：通常为 1024 tokens（小于此值不触发缓存）

---

## 参考资料

- **Issue #131:** Prompt 缓存失效问题
- **OpenAI Prompt Caching:** https://platform.openai.com/docs/guides/prompt-caching
- **相关 PR:** 待修复后关联

---

## 维护者

- **创建日期：** 2026-08-03
- **最后更新：** 2026-08-03
- **测试覆盖率：** 9 个测试用例，覆盖 ChatLLM、AgentContext、PromptSection

---

## 许可证

与 Tale-AI 项目主许可证一致。
