# AI 质检页面优化 Todo

> 时间：2026-05-10
> 范围："src/ui/pages.py" AI 质检页面结构优化
> 原则：参照 `Docs/ui_redesign_design.MD` 规范，只改结构与样式，不动业务逻辑

## 审计结论

AI 质检页面整体符合设计规范，以下为待优化项（按优先级排列）：

## 待优化项

### P0：冗余 Row 包裹

1. `quality-history-row`（L6817）只包含一个子 Column（`quality-history-panel`），冗余
2. `quality-bottom-row`（L6853）只包含一个子 Column（`quality-action-panel`），冗余
3. `quality-relation-note`（L6748）是裸 HTML，无卡片样式但有外框感

**方案**：去掉 `quality-history-row` 和 `quality-bottom-row` 的 Row 壳，让 Column 直接挂在 Tab 下

### P1：Claim 详情侧包含 State 组件

- L6783-6788：`quality-claim-row` 右列包含大量 State 组件（无视觉输出），占空间但不可见
- 这些 State 不需要和 Claim 列表并排，应移到其他地方

**方案**：将 State 组件移至 Row 外部或移至左列，避免占右列空间

### P2：证据列表 9 列被压缩到 50% 宽度

- `quality-evidence-row` 中证据表格和证据详情各占一半
- 9 列数据在半宽下横向滚动较多

**方案**：改为证据表格单栏全宽，证据详情下沉为独立模块

### P3：quality-relation-note 无归属

- 当前是裸 HTML 漂浮在 Claim 和证据之间
- 无卡片样式、无标题，视觉上像断裂带

**方案**：将其融入 `quality-claim-list-panel` 或 `quality-evidence-list-panel` 头部说明

## 已完成项（本次不改动）

- [x] 按钮统一由 `ui_button()` + 语义类驱动（已完成）
- [x] 效果评测默认折叠（已完成）
- [x] 无三层以上视觉卡片嵌套（已通过）
- [x] 动作与结果闭环清晰（已通过）

## 验收标准

- 去掉冗余 Row 包裹，不破坏事件绑定
- 证据表格单栏全宽，横向滚动减少
- Claim 详情不再被 State 占位影响
- 通过 py_compile 和 UI 单测
