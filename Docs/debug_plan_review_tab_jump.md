# Gradio 6.x Tabs 跳转 Bug 调试总结

> 归档说明：本文件仅保留为历史排障记录，当前问题已修复，请勿将其作为现役操作手册。

> 时间：2026-05-17
> Gradio 版本：6.13.0 / 6.14.0（均存在此问题）
> 状态：✅ 已修复（跳转问题已解决，F5 刷新白屏为已知限制）

## 问题描述

admin 登录后，切到"人工审核"页，点击"待处理记录"Dataframe 中任意一行，页面自动跳转到"AI 质检"tab。预期应停留在人工审核页并显示对应记录详情。

## 确认的根因

**Gradio 6.x 前端 bug**：当 `gr.Tabs` 组件曾经被设置过 `selected` 值（无论通过构造参数还是 `gr.update(selected=...)`），前端会缓存该值，并在后续 Dataframe `.select` 事件处理时将 Tabs 重置到该缓存值。

## 最终修复

`src/ui/pages.py` 中 2 处改动：

```python
# 改动 1：去掉 gr.Tabs 的 selected 构造参数
# 之前：
with gr.Tabs(elem_id="main-tabs", selected=MAIN_TAB_IDS["AI 质检"]) as main_tabs:
# 之后：
with gr.Tabs(elem_id="main-tabs") as main_tabs:

# 改动 2：_build_permission_ui_updates 中 main_tabs 不设置 selected
# 之前：
gr.update(selected=_resolve_default_main_tab_id(session)),
# 之后：
gr.update(),
```

## 已知副作用

F5 刷新后 Tabs 选中状态丢失（只显示菜单项，需要手动点击 tab 恢复）。这是 Gradio 6.x 的根本性限制，无法在不引入跳转 bug 的情况下解决。

## 调试过程中验证的关键结论

### 1. 触发条件精确定位

| 条件 | 是否跳转 |
|------|---------|
| `gr.Tabs(selected=...)` 存在 | ✅ 跳转 |
| `gr.Tabs()` 无 selected + `gr.update(selected=...)` 曾被返回 | ✅ 跳转 |
| `gr.Tabs()` 无 selected + 所有事件都不设置 selected | ❌ 不跳转 |

**结论**：只要 `main_tabs` 曾经被设置过 `selected`（不管是构造时还是运行时），后续 Dataframe select 就会跳转。

### 2. 与 `persisted_login_state.change` 的关系

- Gradio 6.x 的 `BrowserState.change` 在**每次前端交互时**都会重新触发（不仅仅是值变化时）
- 该事件的触发本身（即使返回全部 `gr.update()`）也会导致 Tabs 丢失选中状态
- 这是 F5 刷新白屏的原因——`persisted_login_state.change` 触发后 Tabs 被重置

### 3. 排除的错误假设

| 假设 | 验证结果 |
|------|---------|
| 是 `select_review_candidate_ui` 的 outputs 导致的 | ❌ 简化版不跳转 |
| 是 `persisted_login_state.change` 反复触发导致的 | ❌ 用 `demo.load` 替代也跳转 |
| 是后端设置 `main_tabs.selected` 导致的 | ❌ 从所有 outputs 中移除 `main_tabs` 仍跳转（只要构造参数有 selected） |
| 是 Dataframe 组件特有的 | ✅ 只有 Dataframe.select 触发，其他事件（button.click 等）不触发 |
| 升级 Gradio 到 6.14.0 能修复 | ❌ 6.14.0 同样存在 |

### 4. 尝试过但无效的方案

| 方案 | 结果 |
|------|------|
| 在 select handler outputs 中加 `main_tabs` 返回 `selected="人工审核"` | 无效——Gradio 先应用我们的值，然后又重置 |
| 用 `.then(js=...)` 在前端 setTimeout 点击 tab 按钮 | 无效——Gradio Svelte 组件不响应程序化 `.click()` |
| 用隐藏 Button + JS 触发后端事件 | 无效——`visible=False` 的按钮不在 DOM 中；`gr.HTML` 不执行 `<script>` |
| 用 `demo.load` 的 `js` 参数注入 JS | 无效——JS 的 `.click()` 对 Gradio tab 按钮无效 |
| 从 `persisted_login_state.change` outputs 中移除所有 Tab 组件 | 无效——事件触发本身就导致 Tabs 重置 |
| 用 `demo.load` 替代 `persisted_login_state.change` | 无效——`demo.load` 也导致 Tabs 重置 |
| 升级 Gradio 到 6.14.0 | 无效——bug 仍存在 |
| 用 CSS 强制第一个 tab panel 显示 | 无效——Gradio 的 Tabs 结构与假设不同 |
| 用 HTML 表格替代 Dataframe | 部分有效但 JS 无法触发 Gradio 后端事件 |

### 5. Gradio 6.x 中 `gr.HTML` 和 JS 的限制

- `gr.HTML` 组件**不执行** `<script>` 标签（安全限制）
- `visible=False` 的组件**不在 DOM 中**（无法通过 JS 操作）
- 原生 DOM 事件（`dispatchEvent`）**不触发** Svelte 组件的响应式更新
- `gr.Textbox` 的 `.input`/`.change` 事件无法通过 JS `dispatchEvent` 触发
- `gr.Button` 的 `.click()` 在 CSS 隐藏状态下可能不工作

### 6. Gradio 6.x `BrowserState` 行为

- `.change` 事件在**每次前端-后端交互时**都会触发（不仅仅是值变化时）
- 这意味着用户点击任何按钮、选择任何下拉框、点击任何表格行，都会触发 `BrowserState.change`
- 该事件的响应（即使是空的 `gr.update()`）会导致 Tabs 组件重新渲染

## 后续建议

1. **等待 Gradio 官方修复**：在 GitHub 提 issue 描述此 bug
2. **F5 白屏的临时方案**：可以在页面顶部加一个提示"如果页面显示异常，请点击任意菜单项"
3. **长期方案**：如果 Gradio 不修复，考虑将 Tabs 替换为自定义的 HTML/JS tab 实现
4. **降级方案**：评估 Gradio 5.x 是否有此问题（API 变化较大，需要适配）

## 修复后清理

### 移除的冗余代码

- `_resolve_default_main_tab_id` 函数：不再需要，因为 `main_tabs` 不再设置 `selected`
- `build_recent_quality_rows` 的 `active_check_id` 参数：移除"当前"列后该参数无实际作用
- `evt: gr.SelectData` 参数位置修正：Gradio 6.x 要求 `evt` 作为事件处理函数的第一个参数（在 `select_review_candidate_ui` 等函数中修正）

### 关于"当前"列

历史质检记录表格中的"当前"列（用于标记当前选中的质检记录）已移除。原因：
- 该列依赖 `active_check_id` 参数，但在 Tabs 跳转修复后不再需要通过视觉标记来提示用户当前位置
- 简化了表格结构，减少了不必要的状态传递

## 关键代码位置

- `src/ui/pages.py` line ~5111: `gr.Tabs` 定义
- `src/ui/pages.py` line ~4988: `_build_permission_ui_updates` 返回 `main_tabs` 更新
- `src/ui/pages.py` line ~6214: `persisted_login_state.change` 事件绑定
- `src/ui/pages.py` line ~4929: `_resolve_default_main_tab_id` 决定默认 tab
- `src/ui/review_page.py` line ~404: `review_pending_candidates.select` 事件绑定
