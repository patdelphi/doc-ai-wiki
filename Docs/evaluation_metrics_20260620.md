# 2026-06-20 评测集与指标说明

## 当前状态

- 检索评测集：`tests/evaluation/retrieval_cases.jsonl`，当前 50 条。
- Claim 评测集：`tests/evaluation/claim_check_cases.jsonl`，当前 50 条。
- 规则评测集：`tests/evaluation/rule_cases.jsonl`，当前覆盖命中与非命中样例。
- PageIndex 评测集：`tests/evaluation/pageindex_cases.jsonl`，当前 50 条，并通过 `requires_llm` / `mode` 区分真实 LLM 推理与离线降级样例。
- 指标实现：`src/retrieval/evaluation.py`。

## 固定指标

| 指标 | 字段 | 说明 |
|---|---|---|
| Top-K 命中率 | `top_k_hit_rate` | 检索结果前 K 条命中标准 chunk 或标准 doc 的比例 |
| 证据追溯率 | `traceability_rate` | 检索结果具备标题路径、原文行号和 chunk 类型的比例 |
| Claim 准确率 | `verdict_accuracy` | 实际 verdict 与人工标注 verdict 一致的比例 |
| 无证据 verified 率 | `no_evidence_verified_rate` | 没有证据详情却输出 `verified` 的比例 |

## 已验证命令

```powershell
python -m pytest "tests/unit/test_retrieval_evaluation.py" "tests/unit/test_evaluation_fixtures.py" -q
```

结果：`11 passed`。

```powershell
python -m pytest "tests/unit/test_evaluation_fixtures.py" -q
```

结果：`4 passed`。

## 本地运行结果

- 报告文件：`Docs/retrieval_evaluation_run_20260620.md`。
- 证据目录：`Docs/evidence_catalog_20260620.md`。
- 对齐建议：`Docs/retrieval_alignment_suggestions_20260621.md`。
- 命令类型：只读检索评测，不写入质检历史。
- 数据库：`index/app.db`。
- 样例数：`50`。
- Top-K 命中率：`0.0`。
- 证据追溯率：`0.0`。

当前差距：评测样例中的标准 `doc_uid` / `chunk_id` 是正式标注框架，尚未与本机真实知识库 ID 对齐，因此本次运行只证明评测链路可执行，不能代表最终检索质量。

已补充真实库候选证据目录，后续可基于该目录人工修正 `tests/evaluation/retrieval_cases.jsonl` 的标准证据 ID。

已补充 50 条检索样例的候选对齐建议，建议覆盖率为 `1.0`。该建议仅供人工复核，不自动替换金标。

## 未完成

- 尚未将 50 条检索样例的标准证据 ID 与本机真实知识库对齐。
- 尚未基于真实本地知识库运行 Claim 准确率报告。
- 尚未基于真实本地知识库运行 PageIndex 真实 LLM / 离线降级分组报告。
