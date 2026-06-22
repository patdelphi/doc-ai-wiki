# 2026-06-20 证据目录导出说明

## 当前文件

- 证据目录：`Docs/evidence_catalog_20260620.md`
- 数据库：`index/app.db`
- 知识库：`default`
- 查询词：`阿胶`
- 候选数：`200`

## 用途

该目录用于人工对齐 `tests/evaluation/retrieval_cases.jsonl` 中的标准证据 ID。

每条候选证据包含：

- `doc_uid`
- `chunk_id`
- 文档标题
- 标题路径
- 原文行号范围
- 内容摘要

## 下一步

1. 按 50 条检索样例逐条查找最匹配候选证据。
2. 将样例中的 `expected_doc_uids` 与 `expected_chunk_ids` 替换为真实 ID。
3. 重新运行本地只读检索评测。
