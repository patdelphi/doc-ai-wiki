# Debug Plan：人工审核页 Dataframe 点击导致 Tab 跳转

> 时间：2026-05-17
> 状态：根因已确认，修复方案待定

## 问题描述

admin/admin 登录后，切到"人工审核"页，点击"待处理记录"表格中任意一行，页面跳转到"AI 质检"tab。

## 确认的根因

**Gradio 6.x (6.13.0) 前端 bug**：当任何后端事件曾经对 `gr.Tabs` 组件设置过 `selected` 值（无论是通过 `gr.Tabs(selected=...)` 构造参数还是 `gr.update(selected=...)`），Gradio 前端会在后续 Dataframe `.select` 事件处理时将 Tabs 重置到该缓存的 `selected` 值。

### 验证过程

1. 去掉 `gr.Tabs(selected=...)` + 所有事件都不设置 `main_tabs.selected` → **人工审核不跳转**
2. 只要任何事件（`_do_login`、`persisted_login_state.change`、`demo.load`）曾设置过 `selected` → **跳转复现**
3. 简化版测试（无 `BrowserState`、无 tab visibility 变化）→ **不跳转**
4. 把 `gr.Tabs(selected=...)` 改为"人工审核" → 点击 AI 质检历史记录会跳到人工审核（证明是重置到初始 selected 值）

### 核心矛盾

- **不跳转**需要：永远不对 `main_tabs` 设置 `selected`
- **F5 刷新正常**需要：刷新后有一个 tab 被选中（否则只显示菜单项无内容）
- Gradio 6.x 中，任何事件更新 Tabs 容器内的组件都会触发 Tabs 重新渲染并丢失选中状态

## 可选修复方案

### 方案 1：升级 Gradio 到 6.14.x

当前版本 6.13.0，最新 6.14.x。可能已修复此 bug。

**风险**：可能引入其他兼容性问题
**操作**：`pip install --upgrade gradio`

### 方案 2：降级 Gradio 到 5.x

Gradio 5.x 可能没有这个 Tabs 重置 bug。

**风险**：API 变化大，需要大量适配
**操作**：不推荐

### 方案 3：用 HTML 表格替代 Dataframe

把人工审核页的 `gr.Dataframe` 替换为 `gr.HTML` 渲染的可点击表格，通过隐藏按钮触发后端事件。

**已验证**：不跳转（因为不触发 Dataframe.select 事件）
**问题**：Gradio 6.x 中 `visible=False` 的按钮不在 DOM 中，JS 无法点击；`gr.HTML` 不执行 `<script>`；原生 DOM 事件不触发 Svelte 组件更新
**改动量**：大（需要改所有返回 Dataframe 数据的函数）

### 方案 4：接受跳转，用 CSS 动画掩盖

在 Dataframe select 后用 JS setTimeout 延迟切回当前 tab。

**已验证**：JS 的 `.click()` 对 Gradio tab 按钮无效（Svelte 不响应程序化点击）

### 方案 5（推荐）：升级 Gradio + 如果仍有问题则用方案 3

1. 先升级到 6.14.x 测试
2. 如果仍有问题，用 HTML 表格方案（需要解决 JS 触发后端事件的问题）

## 技术细节

### 事件链路

```
用户点击审核记录
  → Gradio 前端触发 Dataframe.select
  → 前端处理响应时重置 Tabs 到缓存的 selected 值
  → 页面跳转到 AI 质检
```

### 关键代码位置

- `src/ui/pages.py` line 5111: `gr.Tabs(elem_id="main-tabs", selected=MAIN_TAB_IDS["AI 质检"])`
- `src/ui/pages.py` line 4988: `gr.update(selected=_resolve_default_main_tab_id(session))`
- `src/ui/pages.py` line 6214: `persisted_login_state.change(...)` — 在每次前端交互时触发
- `src/ui/review_page.py` line 404: `review_pending_candidates.select(...)`

### Gradio 版本信息

- 当前：6.13.0
- 最新：6.14.x
- 依赖约束：`gradio>=6.0.0,<7.0.0`
