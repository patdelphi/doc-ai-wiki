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

结果：`7 passed`。

```powershell
python -m pytest "tests/unit/test_evaluation_fixtures.py" -q
```

结果：`4 passed`。

## 未完成

- 尚未基于真实本地知识库运行完整 Top-5 / Claim 准确率报告。
- 尚未基于真实本地知识库运行 PageIndex 真实 LLM / 离线降级分组报告。
