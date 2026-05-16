# Tale Dashboard 分析面板改进方案

> **文档版本**: v1.1  
> **编写日期**: 2026-05-02  
> **适用范围**: `webui/` 管理面板 - Dashboard 页面  
> **关联文件**: `webui/templates/dashboard.html`, `webui/app.py`, `webui/static/js/main.js`

---

## 一、现状概述

当前 Dashboard 作为 Tale 系统的管理入口，提供了四大统计卡片（运行状态、内存、适配器数、会话数）、一张 24 小时系统活动折线图、日程与适配器状态列表，以及四个快捷操作按钮。整体布局清晰，但在数据真实性、功能完整性和实时性方面存在明显短板。

**已实现的特性**（无需重复开发）：
- 系统状态 `/api/status` 已提供运行状态、内存占用、会话数、适配器列表
- 适配器列表 `/api/adapters` 已返回所有适配器的元信息及 `running` 状态
- 今日日程 `/api/plan/today` 已对接计划系统
- Canvas 折线图已使用 CSS 变量读取主题色，支持 DPR 适配
- 国际化（i18n）骨架已嵌入，通过 `window.t()` 调用

---

## 二、现存问题诊断

### 🔴 严重

| 编号 | 问题 | 影响 | 位置 |
|---|---|---|---|
| D-01 | 图表数据为随机生成 | 用户无法获取真实的系统活动趋势，完全丧失分析价值 | `app.py /api/dashboard/chart` |
| D-02 | "清空日志"与"系统重启"按钮仅弹出 alert，无实际功能 | 功能残缺，用户操作后系统无响应，产生信任危机 | `dashboard.html` 底部 action-row |
| D-03 | Mini Bar（适配器/会话）高度为客户端随机生成 | 视觉高度不具备指标含义，但 active 计数是真实的 | `dashboard.html` JS `renderMiniBars` |

### 🟡 中等

| 编号 | 问题 | 影响 |
|---|---|---|
| D-04 | Dashboard 仅在页面加载时刷新一次，无定时轮询 | 内存、适配器状态、日程等数据很快过时 |
| D-05 | 图表仅支持单一 24h 维度，无法切换时间范围 | 无法满足不同时间粒度的观察需求 |
| D-06 | 图表无交互（无 Tooltip、无下钻） | 只能看大致走势，无法读取精确数值 |
| D-07 | 缺少核心系统指标：消息吞吐量、LLM Token 消耗、响应延迟、错误率 | 管理员无法评估系统负载和成本 |
| D-08 | 适配器面板仅显示名称与 `running` 布尔值，缺少健康详情 | 无法判断适配器是"在线但无消息"还是"真正繁忙" |

### 🟢 轻微

| 编号 | 问题 | 影响 |
|---|---|---|
| D-09 | 移动端下 `mid-row` 挤压为单列，图表固定 220px 过高 | 小屏设备体验不佳 |
| D-10 | 折线图填充色 fallback 仍硬编码 RGB `[96, 165, 250]` | 若 CSS 变量非 hex 格式时颜色解析失败，与 Design System.md 的"禁止硬编码"规范冲突 |
| D-11 | `api_dashboard_chart()` 使用 `random.randint`，无持久化数据 | 每次刷新图表形状完全改变，用户无法建立趋势认知 |

---

## 三、功能扩展规划

### 3.1 数据层：真实指标采集（渐进式）

考虑到当前项目规模，**不建议**在 `core/` 中大规模埋点。优先在 `app.py` 中维护内存级指标缓存，对核心路径做最小侵入式记录：

```python
# 建议新增：webui/metrics.py（与 app.py 同级，避免污染 core/）
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class HourlyMetrics:
    hour: str                      # "2026-05-02 14:00"
    messages_in: int = 0
    messages_out: int = 0
    llm_calls: int = 0
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    avg_latency_ms: float = 0.0
    error_count: int = 0

class MetricsStore:
    """内存级 24h 滚动指标缓存"""
    def __init__(self):
        self.hourly = deque(maxlen=24)
        self._current_hour = datetime.now().strftime("%Y-%m-%d %H:00")
        self._ensure_hour()

    def _ensure_hour(self):
        now_hour = datetime.now().strftime("%Y-%m-%d %H:00")
        if now_hour != self._current_hour:
            self._current_hour = now_hour
            self.hourly.append(HourlyMetrics(hour=now_hour))

    def record_message(self, direction: str):
        self._ensure_hour()
        m = self.hourly[-1]
        if direction == "in":
            m.messages_in += 1
        else:
            m.messages_out += 1

    def record_llm(self, latency_ms: float, tokens_in: int, tokens_out: int):
        self._ensure_hour()
        m = self.hourly[-1]
        m.llm_calls += 1
        m.llm_tokens_in += tokens_in
        m.llm_tokens_out += tokens_out
        # 增量更新平均延迟
        m.avg_latency_ms = (m.avg_latency_ms * (m.llm_calls - 1) + latency_ms) / m.llm_calls

    def to_list(self):
        self._ensure_hour()
        return [m.__dict__ for m in self.hourly]
```

**采集点建议**（最小侵入）：
- `webui/app.py` 的 `api_chat_send()` 中：用户发送消息时 `record_message("in")`，收到回复时 `record_message("out")`
- `webui/app.py` 的 `api_plan_generate()` 中：记录 LLM 调用耗时
- `core/function_caller.py`：工具调用失败时记录 `error_count`（可选）

**替代方案**（若不想改动后端逻辑）：
- 让 `/api/dashboard/chart` 先返回全零数组或静态演示数据
- 在图表下方添加文字标注："系统活动数据采集开发中"，避免误导用户

### 3.2 图表体系：多维度可视化

| 图表名称 | 类型 | 维度切换 | 数据来源 | 优先级 |
|---|---|---|---|---|
| **消息趋势** | 折线图 | 近 24h / 近 7d / 近 30d | `messages_in` + `messages_out` | P1 |
| **适配器流量占比** | 环形图 (Donut) | 今日 / 本周 | 各适配器 `messages_in` 汇总 | P2 |
| **LLM Token 消耗** | 堆叠柱状图 | 近 24h / 近 7d | `llm_tokens_in` + `llm_tokens_out` | P2 |
| **响应延迟分布** | 折线图 + P99 线 | 近 24h | `avg_latency_ms` | P3 |

**前端实现建议**：
- 当前仅有一个简单折线图，**不需要**引入完整 ChartRenderer 类库
- 在现有 `drawLineChart()` 基础上逐步增强：
  1. 增加 `mousemove` Tooltip（读取最近数据点）
  2. 增加时间维度切换按钮（24h/7d），切换时调用不同 API
  3. 新增图表时再考虑抽象公共函数
- 颜色全部读取 CSS 变量 `--accent`、`--success`、`--warning`、`--danger`
- **移除** fallback 硬编码 RGB `[96, 165, 250]`，改为读取 CSS 变量并解析，或使用 `currentColor` 机制

### 3.3 实时刷新机制

```javascript
// dashboard.html 中增加
let refreshTimer = null;
const REFRESH_INTERVAL = 10000; // 10s

function startRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(loadDashboard, REFRESH_INTERVAL);
}

// 页面不可见时暂停，节省资源
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        clearInterval(refreshTimer);
    } else {
        startRefresh();
    }
});

loadDashboard().then(startRefresh);
```

**API 侧配套**：
- `/api/status` 已存在，建议扩展返回字段：
  ```json
  {
    "running": true,
    "time": "2026-05-02T14:32:00",
    "conversations": 12,
    "adapters": [
      {"id": "qq", "name": "QQ", "running": true},
      {"id": "wechat_pc", "name": "WeChat PC", "running": false}
    ],
    "memory": 42.5,
    "metrics": {
      "messages_last_hour": 173,
      "llm_calls_last_hour": 45,
      "errors_last_hour": 2
    },
    "alerts": [
      {"level": "warning", "message": "WeChat PC 适配器已离线"}
    ]
  }
  ```
- 新增 `/api/metrics?range=24h` 返回结构化时间序列数据（Phase 2）

### 3.4 快捷操作功能化

| 按钮 | 当前行为 | 目标行为 | 所需 API / 修改 |
|---|---|---|---|
| **Generate Daily Plan** | 已可用 | 增加 Loading 状态与成功/失败 Toast（替代 `alert`） | 已有 `/api/plan/generate` |
| **Clear Logs** | `alert(demo)` | 清空服务端 `LOG_QUEUE`，前端同步清空列表 | 在 `app.py` 的 `/api/logs` 上增加 `DELETE` 方法 |
| **System Reboot** | `alert(demo)` | 提供"重载配置"确认流程（安全且可回退） | 新增 `POST /api/system/reload`，调用 `config_loader.reload()` |
| **Open Conversation** | 跳转 `/chat` | 保持不变 | — |

### 3.5 适配器健康面板增强

当前仅显示名称与 `running` 布尔值，扩展为：

```
┌──────────────────────────────────────────┐
│  Adapter Status                          │
├──────────────────────────────────────────┤
│ [●] QQ        ACTIVE    128 msg/h        │
│ [●] WeChat    ACTIVE     45 msg/h        │
│ [○] WebSocket IDLE      last: 2h ago     │
└──────────────────────────────────────────┘
```

新增字段（需要后端配合）：
- `message_rate`: 最近一小时的收发消息总量（从 MetricsStore 读取）
- `last_activity`: 最后一条消息的时间戳（人文化显示："2分钟前"）
- `uptime`: 适配器运行时长（若 AdapterManager 能维护启动时间）

**前端兼容**：如果后端暂不提供新字段，前端应优雅降级，仅显示现有信息，不显示 `undefined`。

### 3.6 告警横幅（Alert Banner）

在 Dashboard 顶部增加一个可关闭的全局通知条：

- **适配器离线**：当某适配器从 `running=true` 变为 `running=false` 且非用户主动停止时触发
- **LLM 异常**：连续 3 次调用失败时触发
- **内存告警**：`memory > 85%` 时触发

实现方式：在 `loadDashboard()` 返回的数据中增加 `alerts: []` 数组，前端动态渲染。

---

## 四、API 设计草案

### 4.1 扩展现有接口

**`GET /api/status`**（扩展后）
```json
{
  "running": true,
  "time": "2026-05-02T14:32:00",
  "conversations": 12,
  "adapters": [...],
  "memory": 42.5,
  "metrics": {
    "messages_last_hour": 173,
    "llm_calls_last_hour": 45,
    "errors_last_hour": 2
  }
}
```

### 4.2 新增接口

**`GET /api/metrics?range=24h|7d|30d`**
```json
[
  {"hour": "2026-05-02 00:00", "messages_in": 12, "messages_out": 10, "llm_calls": 3, "llm_tokens_in": 1200, "llm_tokens_out": 800, "avg_latency_ms": 1200, "error_count": 0},
  {"hour": "2026-05-02 01:00", "messages_in": 5, "messages_out": 5, "llm_calls": 1, ...}
]
```

**`DELETE /api/logs`**
```json
{"ok": true, "cleared": 500}
```

**`POST /api/system/reload`**
```json
{"ok": true, "message": "配置已重载"}
```

---

## 五、实施路线图

### Phase 1：修复信任问题（1 天）
- [ ] **修复 D-02**：实现 `DELETE /api/logs` 并绑定"清空日志"按钮（真正清空 `LOG_QUEUE`）
- [ ] **修复 D-02**：实现 `POST /api/system/reload`（调用 `config_loader.reload()`）并绑定"重载配置"按钮，将"System Reboot"文案改为"Reload Config"以避免误解
- [ ] **修复 D-01 / D-11**：将 `/api/dashboard/chart` 改为返回空数组或带标注的静态数据，移除 `random.randint`；前端图表区域在无数据时显示 "暂无数据" 占位
- [ ] **修复 D-10**：移除 `drawLineChart` 中硬编码 RGB fallback `[96, 165, 250]`，统一通过 CSS 变量获取颜色

### Phase 2：实时化与体验优化（1 天）
- [ ] **修复 D-04**：Dashboard 增加 `setInterval` 自动刷新（10s），配合 `visibilitychange` 暂停/恢复
- [ ] **修复 D-03**：移除 `renderMiniBars` 中的随机高度，改为基于实际数值的比例渲染（若当前无历史数据，可显示等高水平条仅作视觉占位）
- [ ] **改进**：`btnGenPlan` 增加 Loading 状态，成功后使用轻量 Toast 替代 `alert`
- [ ] **修复 D-09**：移动端 `< 640px` 下统计卡片支持横向滚动（`overflow-x: auto`），避免图表过高挤压布局

### Phase 3：真实指标与图表增强（2~3 天）
- [ ] 新建 `webui/metrics.py`，实现内存级 `MetricsStore`
- [ ] 在 `app.py` 的 `api_chat_send()` 和 `api_plan_generate()` 中埋点，记录消息数与 LLM 调用
- [ ] 新增 `GET /api/metrics?range=24h` 接口，返回 `MetricsStore.to_list()`
- [ ] `/api/dashboard/chart` 改为读取 `MetricsStore` 的 `messages_in` + `messages_out` 汇总
- [ ] 折线图增加 Hover Tooltip（显示精确数值与时间点）
- [ ] 支持 24h / 7d 维度切换（通过 Panel header 添加切换按钮）

### Phase 4：高级面板（2~3 天）
- [ ] 适配器面板增加 `message_rate` 与 `last_activity`（需要 `AdapterManager` 暴露相关统计）
- [ ] Dashboard 增加 LLM Token 消耗图、适配器流量环形图（右侧 `adapter-panel` 下方新增小面板）
- [ ] 顶部告警横幅组件，读取 `/api/status` 返回的 `alerts` 数组
- [ ] 新增响应延迟分布图（P3，可选）

---

## 六、前端架构建议

### 6.1 文件组织

```
webui/static/js/
  main.js          # 全局导航、主题、语言（保持现有）
  dashboard.js     # 建议新增：Dashboard 专属逻辑，从 dashboard.html 中剥离
webui/templates/
  dashboard.html   # 保留模板结构与样式，JS 逻辑外移至 dashboard.js
webui/
  metrics.py       # 建议新增：内存级指标缓存
```

**说明**：当前 `dashboard.html` 内嵌了约 250 行 JS，随着功能增加会变得难以维护。建议将 JS 逻辑迁移到 `dashboard.js`，`dashboard.html` 仅保留模板、样式和内联初始化代码。

### 6.2 图表增强建议（渐进式）

无需引入重型图表库，继续基于原生 Canvas 增强：

```javascript
// dashboard.js 中逐步增强 drawLineChart
function drawLineChart(canvasId, dataPoints, options = {}) {
    const { tooltip = true, timeLabels = [] } = options;
    // ... 现有代码 ...

    if (tooltip) {
        canvas.addEventListener('mousemove', (e) => {
            // 计算最近数据点，绘制浮动提示框
        });
    }
}
```

**颜色获取工具函数**：
```javascript
function getCssVar(name, fallback) {
    const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    if (!val && fallback) return fallback;
    // 统一解析 hex -> rgb，避免硬编码
    if (val.startsWith('#')) {
        const r = parseInt(val.slice(1, 3), 16);
        const g = parseInt(val.slice(3, 5), 16);
        const b = parseInt(val.slice(5, 7), 16);
        return [r, g, b];
    }
    return val;
}
```

---

## 七、兼容性要求

- **零外部依赖**：继续使用原生 Canvas + CSS 变量，不引入 ECharts/Chart.js 等库，保持项目轻量。
- **主题自适应**：所有图表颜色必须通过 `getComputedStyle(document.documentElement)` 读取 CSS 变量，禁止硬编码色值。
- **降级策略**：当 `/api/metrics` 返回空数组时，图表区域显示 "暂无数据" 占位，而非空白或假数据。
- **移动端友好**：统计卡片在 `< 640px` 下可横向滚动（`overflow-x: auto`），避免纵向过长；图表高度在移动端降至 `160px`。
- **渐进增强**：新字段（如 `message_rate`、`last_activity`）后端未实现时，前端不报错、不显示 `undefined`。

---

## 八、附录：相关代码定位

| 功能 | 文件 | 行号/区域 |
|---|---|---|
| 随机图表数据 | `webui/app.py` | `api_dashboard_chart()` — 使用 `random.randint(10, 85)` |
| 图表颜色 fallback 硬编码 | `webui/templates/dashboard.html` | `drawLineChart()` 中 `accentRgb` 的 else 分支 `[96, 165, 250]` |
| Mini Bar 随机高度 | `webui/templates/dashboard.html` | `renderMiniBars()` 中 `Math.random() * 70` |
| 未实现按钮 | `webui/templates/dashboard.html` | `btnClearLogs`, `btnReboot` 事件监听仅 `alert(demo)` |
| 一次性加载 | `webui/templates/dashboard.html` | `loadDashboard()` 末尾无定时器 |
| 日志队列 | `webui/app.py` | `LOG_QUEUE`, `MAX_LOGS` — 需增加 DELETE 支持 |
| 配置重载 | `webui/app.py` | `config_loader.reload()` 已存在，只需暴露为 API |
| 适配器状态字段 | `webui/app.py` | `api_adapters()` 返回 `running: true/false` |
| 国际化函数 | `webui/static/js/i18n.js` | `window.t(key)` — Dashboard 中已部分使用 |

---

## 九、变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-02 | 初始版本 |
| v1.1 | 2026-05-02 | 修正适配器状态字段描述（`running` 而非 `ACTIVE/IDLE`）；补充 D-10/D-11；简化 ChartRenderer 建议为渐进增强；明确 Phase 1 将"Reboot"改为"Reload Config"以避免误解；增加"已实现的特性"章节；补充 `metrics.py` 渐进式采集方案；增加附录代码定位准确性 |
---

*本方案由 AI 辅助生成，具体实现时应结合业务实际数据流进行调整。*
