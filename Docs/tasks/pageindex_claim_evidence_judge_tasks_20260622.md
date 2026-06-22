# PageIndex Claim-Evidence Judge 执行任务

## 目标

第一批先完成 PageIndex 本地答案链路的根因修复：通用判断证据与用户命题的关系，并按关系生成明确结论。

## 文件范围

- 新增：`src/pageindex/evidence_judge.py`
- 修改：`src/pageindex/service.py`
- 修改：`src/pageindex/templates.py`
- 新增：`tests/unit/test_pageindex_evidence_judge.py`
- 修改：`tests/unit/test_pageindex_service.py`
- 修改：`Docs/optimization-plan/pageindex_claim_evidence_judge_plan_20260622.md`

## 执行步骤

- [x] 写 Evidence Judge 失败测试，覆盖 `direct_support`、`direct_refute`、`context_only`、`example_only`、`method_or_formula_context`、`risk_or_condition`。
- [x] 实现 `src/pageindex/evidence_judge.py`，提供 `classify_evidence_relation()` 和 `infer_conclusion()`。
- [x] 新增 `templates/pageindex/evidence_judge.yaml`，将证据关系词表和结论文案外置。
- [x] 将 `PageIndexService._classify_single_evidence()` 和 `_infer_local_conclusion()` 改为调用 Evidence Judge。
- [x] 更新 PageIndex 模板变量说明，要求 LLM 区分证据关系。
- [x] 跑 PageIndex 聚焦测试。
- [ ] 跑全量测试。
- [ ] 重启本地服务。

## 完成标准

- 本地降级答案不再输出“找到相关证据，具体判断需结合依据”这类模糊结论。
- 只有背景、案例、方法/组合方案语境时，结论明确说明不能证明用户命题。
- 保持现有 UI 表格字段兼容。
