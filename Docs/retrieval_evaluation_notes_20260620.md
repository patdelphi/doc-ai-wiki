# 2026-06-20 本地检索评测说明

## 运行结果

- 报告文件：`Docs/retrieval_evaluation_run_20260620.md`
- 证据目录：`Docs/evidence_catalog_20260620.md`
- 对齐建议：`Docs/retrieval_alignment_suggestions_20260621.md`
- 数据库：`index/app.db`
- 评测集：`tests/evaluation/retrieval_cases.jsonl`
- 样例数：`50`
- Top-K 命中率：`0.0`
- 证据追溯率：`0.0`

## 结论

本次结果说明评测链路已经可以在本地只读运行，但不能代表最终检索质量。

主要原因是当前 50 条检索样例先建立了标准评测框架，里面的 `expected_doc_uids` / `expected_chunk_ids` 尚未与本机真实知识库中的 ID 对齐。

## 下一步

1. 从真实入库数据导出候选 `doc_uid`、`chunk_id`、标题路径和原文范围。
2. 基于 `Docs/evidence_catalog_20260620.md` 将 50 条检索样例的标准证据 ID 对齐到真实库。
3. 参考 `Docs/retrieval_alignment_suggestions_20260621.md` 人工确认候选证据。
4. 重新运行 Top-5 命中率和证据追溯率。
5. 再运行 Claim 准确率和 PageIndex 分组评测。
