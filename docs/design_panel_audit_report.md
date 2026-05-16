# Tale WebUI 设计面板审计报告

> **审计日期**: 2026-05-02  
> **审计范围**: `webui/` 目录下所有前端模板、样式与脚本  
> **审计依据**: `Design System.md` 设计规范文档  
> **问题总数**: 10 项（含 3 项严重、4 项中等、3 项轻微）

---

## 目录

1. [主题默认值与设计规范冲突](#1-主题默认值与设计规范冲突---严重)
2. [侧边栏宽度不一致](#2-侧边栏宽度不一致---中等)
3. [i18n.js 语言切换按钮破坏 DOM 结构](#3-i18njs-语言切换按钮破坏-dom-结构---中等)
4. [全局 Tab 键拦截破坏可访问性](#4-全局-tab-键拦截破坏可访问性---严重)
5. [plan.html 模板字符串语法错误](#5-planhtml-模板字符串语法错误---严重)
6. [Dashboard 图表颜色硬编码](#6-dashboard-图表颜色硬编码---中等)
7. [日志页面分割线颜色硬编码](#7-日志页面分割线颜色硬编码---轻微)
8. [.btn-danger 缺少背景色定义](#8-btndanger-缺少背景色定义---轻微)
9. [配置页无移动端适配](#9-配置页无移动端适配---中等)
10. [Design System 与代码中字号不统一](#10-design-system-与代码中字号不统一---轻微)

---

## 1. 主题默认值与设计规范冲突 — 严重

### 问题描述

`Design System.md` 明确规定暗色主题为默认主题：

> "本项目采用 CSS 自定义属性管理主题色，支持暗色（默认）与亮色双主题"

但在 `base.css` 的 `:root` 中，默认定义的却是**浅色主题**色值：

```css
/* webui/static/css/base.css :root — 实际默认浅色 */
--bg-primary: #f3f4f6;
--bg-secondary: #ffffff;
--text-primary: #111827;
```

### 影响

- 用户首次访问时看到的浅色主题与 `Design System.md` 文档描述不符。
- 文档与代码规范不同步，增加后续维护成本。
- `Design System.md` 中暗色主题色值（如 `--bg-primary: #0b0f18`）未在代码中作为默认生效。

### 相关文件

- `Design System.md` §1 Color Palette
- `webui/static/css/base.css` 第 7~28 行

### 建议修复

将 `base.css` 中 `:root` 的色值与 `Design System.md` 的暗色主题对齐，同时保留 `[data-theme="light"]` 覆盖规则：

```css
:root {
    /* 暗色主题（默认） */
    --bg-primary: #0b0f18;
    --bg-secondary: #0f1117;
    --bg-tertiary: #1a1f2b;
    --text-primary: #e8eaf0;
    --text-secondary: #9ca3af;
    --text-muted: #6b7280;
    --accent: #60a5fa;
    /* ... */
}

[data-theme="light"] {
    /* 亮色主题覆盖 */
    --bg-primary: #f3f4f6;
    --bg-secondary: #ffffff;
    /* ... */
}
```

---

## 2. 侧边栏宽度不一致 — 中等

### 问题描述

`Design System.md` §4.2 定义侧边栏宽度常量为：

> `--sidebar-width: 220px`

但 `base.css` 实际代码中定义的是：

```css
/* webui/static/css/base.css */
--sidebar-width: 240px;
```

### 影响

- 设计文档与实现代码不同步，后续开发者依据文档计算布局时会出现偏差。
- 若未来需要调整侧边栏宽度，可能出现只修改了一处而另一处遗漏的情况。

### 相关文件

- `Design System.md` §4.2
- `webui/static/css/base.css` 第 32 行

### 建议修复

统一两处数值。鉴于当前实际渲染效果基于 `240px`，建议：

1. 将 `Design System.md` 中 `--sidebar-width` 更新为 `240px`；**或**
2. 将 `base.css` 中 `--sidebar-width` 改为 `220px`，并检查所有依赖该变量的布局是否受影响。

---

## 3. i18n.js 语言切换按钮破坏 DOM 结构 — 中等

### 问题描述

`i18n.js` 的 `apply()` 函数在更新语言切换按钮文本时，直接覆写了 `textContent`：

```javascript
// webui/static/js/i18n.js ~第 260 行
const langBtn = document.getElementById('langSwitchBtn');
if (langBtn) {
    langBtn.textContent = getText('lang.switch');  // ❌ 覆盖内部所有子节点
}
```

而 `base.html` 中该按钮的原始结构包含 SVG 图标和 `<span>` 子元素：

```html
<button class="lang-toggle" id="langSwitchBtn">
    <svg width="14" height="14">...</svg>
    <span data-i18n="lang.switch">English</span>
</button>
```

### 影响

- 调用 `apply()` 后，语言切换按钮内的 SVG 地球图标和 `<span>` 标签被完全移除，只剩下纯文本，UI 样式被破坏。
- 用户切换语言后，按钮从带图标样式退化为纯文本按钮。

### 相关文件

- `webui/static/js/i18n.js` `apply()` 函数
- `webui/templates/base.html` 语言切换按钮

### 建议修复

不要直接设置 `textContent`，而是选择内部的 `<span>` 进行更新：

```javascript
const langBtnSpan = langBtn.querySelector('span');
if (langBtnSpan) {
    langBtnSpan.textContent = getText('lang.switch');
}
```

---

## 4. 全局 Tab 键拦截破坏可访问性 — 严重

### 问题描述

`main.js` 中注册了一个**全局**的 `keydown` 监听器，拦截所有页面上的 `Tab` 键事件：

```javascript
// webui/static/js/main.js ~第 40 行
document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
        const isChatPage = document.querySelector('.chat-layout');
        if (isChatPage && typeof toggleCardView === 'function') {
            e.preventDefault();  // ❌ 阻止默认 Tab 行为
            toggleCardView();
        }
    }
});
```

该监听器的注册**没有页面作用域限制**。即使在聊天页，当用户正在输入框中输入时按 `Tab` 键，也会被拦截。

### 影响

- **可访问性灾难**：所有表单控件（`<input>`、`<textarea>`、`<select>`、`<button>`）的 Tab 焦点导航被全局阻断。
- 用户在 `config.html` 的配置表单、`plan.html` 的日程添加表单、`chat.html` 的输入框中均无法使用 Tab 键切换焦点。
- 键盘用户（包括屏幕阅读器用户）几乎无法正常使用界面。
- WCAG 2.1 规范中 "Keyboard Accessible"（准则 2.1）被严重违反。

### 相关文件

- `webui/static/js/main.js` 第 37~47 行

### 建议修复

将 Tab 键触发逻辑限定在**特定元素**上，或改用**不冲突的快捷键**（如 `Ctrl+Tab`、`Esc` 等）：

```javascript
// 方案 A：仅在卡片视图已打开时允许 Tab 切换
// 方案 B：改为不常用的组合键
document.addEventListener('keydown', (e) => {
    // 避免在表单元素中拦截
    const tag = document.activeElement?.tagName;
    if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(tag)) return;
    
    if (e.key === 'Tab' && e.ctrlKey) {  // Ctrl+Tab 触发
        const isChatPage = document.querySelector('.chat-layout');
        if (isChatPage && typeof toggleCardView === 'function') {
            e.preventDefault();
            toggleCardView();
        }
    }
});
```

---

## 5. plan.html 模板字符串语法错误 — 严重

### 问题描述

`plan.html` 中渲染时间轴时，使用了单引号字符串包裹模板变量 `${date}`：

```javascript
// webui/templates/plan.html ~第 120 行
elTimeline.innerHTML = '<div class="timeline-date">${date}</div><div class="empty-tip">...';
```

在 JavaScript 中，**单引号字符串不支持 `${}` 插值语法**，只有反引号（模板字符串）才支持。因此 `${date}` 会被原样输出为字面文本，而不是变量值。

### 影响

- 时间轴顶部显示的日期永远是字面量 `${date}`，而非实际日期值。
- 用户体验受损，用户无法通过日期标题确认当前查看的是哪一天的日程。

### 相关文件

- `webui/templates/plan.html` `renderPlan()` 函数

### 建议修复

将外层单引号改为反引号：

```javascript
elTimeline.innerHTML = `<div class="timeline-date">${date}</div><div class="empty-tip">${window.t ? window.t('plan.noSchedule') : '暂无日程'}</div>`;
```

---

## 6. Dashboard 图表颜色硬编码 — 中等

### 问题描述

`dashboard.html` 中的 Canvas 折线图绘制逻辑使用了硬编码颜色值：

```javascript
// webui/templates/dashboard.html ~第 440 行
const lineColor = '#60a5fa';  // 固定蓝色
ctx.fillStyle = 'rgba(96, 165, 250, 0.08)';  // 固定淡蓝填充
```

这些颜色不会随主题切换（暗色/亮色）而自适应。暗色主题下 `#60a5fa` 虽然勉强可用，但在亮色主题下对比度过高；且一旦设计规范变更，需要多处手动修改。

### 影响

- 主题切换时图表颜色与整体配色不协调。
- 违背 `Design System.md` §1 中 "禁止在业务样式中硬编码色值" 的规范。
- 维护困难：若需调整图表主色调，必须修改 JS 代码而非仅调整 CSS 变量。

### 相关文件

- `Design System.md` §1.3 "使用规范"
- `webui/templates/dashboard.html` `drawLineChart()` 函数

### 建议修复

通过 `getComputedStyle` 动态读取 CSS 变量：

```javascript
function getCssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const lineColor = getCssVar('--accent');
// 填充色可通过 lineColor 动态计算透明度，或新增 --accent-ghost 变量
```

---

## 7. 日志页面分割线颜色硬编码 — 轻微

### 问题描述

`logs.html` 中 `log-line` 的底部边框使用了固定 RGBA 值：

```css
/* webui/templates/logs.html */
.log-line {
    padding: 2px 0;
    border-bottom: 1px solid rgba(255,255,255,0.03);  /* 硬编码 */
}
```

在暗色主题下 `rgba(255,255,255,0.03)` 接近不可见，但这属于预期行为。问题出在**亮色主题**下：亮色背景 `#ffffff` 搭配 `rgba(255,255,255,0.03)` 完全无法看到分割线。

### 影响

- 亮色主题下日志行之间缺少视觉分隔，降低可读性。
- 又一次违反了 "禁止硬编码色值" 的规范。

### 相关文件

- `webui/templates/logs.html` 内联样式

### 建议修复

使用设计系统定义的边框变量：

```css
.log-line {
    border-bottom: 1px solid var(--border);
}
```

---

## 8. .btn-danger 缺少背景色定义 — 轻微

### 问题描述

`base.css` 中 `.btn-danger` 只定义了边框和文字颜色，**未定义背景色**：

```css
/* webui/static/css/base.css */
.btn-danger {
    border-color: var(--danger);
    color: var(--danger);
}

.btn-danger:hover {
    background: rgba(239, 68, 68, 0.08);
}
```

这意味着 `.btn-danger` 的默认状态会继承父级或 `.btn` 的背景色（`var(--bg-secondary)`）。在暗色主题下（`--bg-secondary: #0f1117`，深灰蓝色）与 `var(--danger)`（`#f87171`，柔和红）对比度尚可；但在**亮色主题**下（`--bg-secondary: #ffffff`），按钮看起来几乎像纯文字链接，缺乏危险操作的视觉警示感。

### 影响

- 用户可能无法第一时间识别 `.btn-danger` 为危险操作按钮。
- 与 `.btn-primary`（有实色背景）的视觉层级不一致。

### 相关文件

- `webui/static/css/base.css`

### 建议修复

给 `.btn-danger` 增加默认背景色，使其与 `.btn-primary` 在视觉权重上保持一致：

```css
.btn-danger {
    background: rgba(239, 68, 68, 0.1);  /* 微弱的危险色背景 */
    border-color: var(--danger);
    color: var(--danger);
}

.btn-danger:hover {
    background: rgba(239, 68, 68, 0.18);
}
```

或使用设计系统中的语义化变量（如新增 `--danger-bg`）。

---

## 9. 配置页无移动端适配 — 中等

### 问题描述

`config.html` 的表单网格使用了固定两列布局：

```css
/* webui/templates/config.html 内联样式 */
.form-grid {
    display: grid;
    grid-template-columns: 140px 1fr;
    gap: 12px 16px;
}
```

该布局在桌面端表现良好，但在移动端（屏幕宽度 < 640px）下：
- `140px` 的标签列仍然占据固定宽度，导致输入框被严重挤压。
- 没有 `@media` 查询进行响应式调整。
- 输入框的 `max-width: 480px` 在小屏幕下可能超出容器。

### 影响

- 移动端用户难以正常编辑配置，标签和输入框可能换行错乱。
- 作为管理面板，配置页是高频操作页面，移动端体验差会显著影响可用性。

### 相关文件

- `webui/templates/config.html` 内联样式

### 建议修复

添加响应式断点，在小屏幕下改为单列堆叠布局：

```css
.form-grid {
    display: grid;
    grid-template-columns: 140px 1fr;
    gap: 12px 16px;
}

@media (max-width: 640px) {
    .form-grid {
        grid-template-columns: 1fr;
        gap: 8px 0;
    }
    .form-grid label {
        text-align: left;
        font-weight: 600;
    }
}
```

---

## 10. Design System 与代码中字号不统一 — 轻微

### 问题描述

`Design System.md` §2 定义的最小标准字号为 `11px`（Micro 层级）：

> | 层级 | 字号 | 用途 |
> |------|------|------|
> | Micro / 微量 | `11px` | 元信息、消息条数、角标 |

但在 `dashboard.html` 中，统计卡片的标题使用了 `10px`：

```css
/* webui/templates/dashboard.html */
.stat-title {
    font-size: 10px;  /* 小于设计规范最小值 11px */
    font-weight: 700;
    letter-spacing: 0.8px;
}
```

### 影响

- 设计规范的可信度降低，开发者难以判断 `10px` 是故意为之还是疏漏。
- `10px` 在部分浏览器/设备上可能出现渲染模糊问题（低于某些系统的最小可读字号）。
- 与设计系统 Token 体系不一致，若后续批量替换字号时容易遗漏。

### 相关文件

- `Design System.md` §2 Typography
- `webui/templates/dashboard.html`

### 建议修复

将 `.stat-title` 的 `font-size` 统一为 `11px`：

```css
.stat-title {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    color: var(--text-muted);
}
```

---

## 总结

| 序号 | 问题 | 严重等级 | 影响范围 | 修复优先级 |
|------|------|----------|----------|------------|
| 1 | 主题默认值与设计规范冲突 | 严重 | 全局首屏体验 | P0 |
| 4 | 全局 Tab 键拦截破坏可访问性 | 严重 | 全局键盘操作 | P0 |
| 5 | plan.html 模板字符串语法错误 | 严重 | 日程页日期显示 | P0 |
| 3 | i18n.js 语言切换按钮破坏 DOM | 中等 | 语言切换按钮 | P1 |
| 6 | Dashboard 图表颜色硬编码 | 中等 | 仪表盘图表 | P1 |
| 9 | 配置页无移动端适配 | 中等 | 配置页移动端 | P1 |
| 2 | 侧边栏宽度不一致 | 中等 | 文档与代码同步 | P2 |
| 7 | 日志页面分割线颜色硬编码 | 轻微 | 日志页亮色主题 | P2 |
| 8 | .btn-danger 缺少背景色 | 轻微 | 危险按钮视觉 | P2 |
| 10 | 字号不统一 | 轻微 | 设计规范一致性 | P3 |

### 建议行动

1. **立即修复（P0）**：问题 1、4、5。这三项直接影响核心功能或用户体验，建议在下次发布前必须修复。
2. **短期修复（P1）**：问题 3、6、9。影响特定页面功能，可在下一个迭代中处理。
3. **文档同步（P2）**：问题 2、7、8。以文档更新和样式微调为主。
4. **规范对齐（P3）**：问题 10。纳入设计系统 Token 统一调整计划。
