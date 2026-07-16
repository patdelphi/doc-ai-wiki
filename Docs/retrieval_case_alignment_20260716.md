# 检索评测候选对齐记录

## 结论

- 原始样例：`50` 条。
- 已对齐真实 chunk：`50` 条。
- 引用校验：`通过`。
- 相关性目标：仅使用 `expected_chunk_ids`，不使用文档级命中兜底。

- 检索范围：每条样例继承候选文档的真实 `knowledge_base_id`。

## 适用范围

该数据集取历史候选建议中每条样例的首个候选，用于重建后的算法回归。候选由旧索引自动生成，未经逐条独立人工复核，因此不能作为正式金标或产品质量上限证明。

## 引用校验

```json
{
  "valid": true,
  "missing_knowledge_base_ids": [],
  "missing_doc_uids": [],
  "missing_chunk_ids": []
}
```
