# 2026-06-21 检索样例证据 ID 对齐建议说明

## 当前文件

- 对齐建议：`Docs/retrieval_alignment_suggestions_20260621.md`
- 评测集：`tests/evaluation/retrieval_cases.jsonl`
- 数据库：`index/app.db`
- 知识库：`default`
- 候选来源：`export_evidence_catalog()`

## 结果

- 样例数：`50`
- 有候选建议样例数：`50`
- 建议覆盖率：`1.0`

## 使用原则

该文件只是候选建议，不自动改写金标。

人工确认后，才能把候选中的真实 `doc_uid` / `chunk_id` 写回 `tests/evaluation/retrieval_cases.jsonl`。

## 下一步

1. 逐条复核候选证据是否真正支持 query 的标准证据。
2. 将确认后的真实 ID 写回评测集。
3. 重新运行本地只读检索评测。
