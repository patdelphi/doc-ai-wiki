# 2026-06-20 MVP 验收状态报告

> 项目：doc-ai-wiki
> 依据：`Docs/acceptance.MD`、`Docs/test_report_20260620.md`、当前源码与测试结果

## 总体结论

当前项目已具备 Markdown / JSON 入库、SQLite + FTS5、Chroma 向量检索、混合检索、AI 质检、人工审核、多知识库与权限控制、PageIndex 长文档增强等能力。从 MVP 主链路看，当前状态可判定为“基本通过，仍需补正式质量评测集”。

## 验收项状态

| 模块 | 状态 | 依据 |
|---|---|---|
| 文档入库 | 已通过 | 集成测试覆盖注册、状态查询、重复/更新相关重建、JSON 入库、索引写入 |
| 全文检索 | 已通过 | 集成测试与检索单测覆盖 FTS/LIKE 兜底和结果返回 |
| 向量检索 | 已通过 | 集成测试覆盖入库后向量与混合检索；向量存储单测覆盖维度与重建 |
| 混合检索 | 已通过 | 集成测试覆盖混合检索返回，单测覆盖 rerank |
| AI 质检 | 已通过 | 质检单测覆盖规则、模板、证据关系、保守 verdict、评测套件 |
| 人工审核 | 已通过 | 审核单测覆盖提交、删除、历史、候选过滤和原始结果保留 |
| 多知识库隔离 | 已通过 | 知识库、检索、审核、PageIndex 单测与集成测试覆盖隔离 |
| UI 回归 | 已通过 | UI 单测覆盖主要页面构建、联动、权限、分页和导出 |
| PageIndex | 部分通过 | 10 问离线评测通过；仍需扩展到 50 问并区分真实 LLM 与离线降级 |
| 高可信证据追溯 | 部分通过 | 当前已补 `heading_path`、起止行号、`chunk_type`、`content_hash` 与 `source_anchor`，并在证据详情与导出中展示；仍缺正式可追溯率评测 |
| verdict 体系 | 已通过 | 当前保留 `verified / needs_review / rejected` 简化枚举，证据关系用 `support / contradict / insufficient` 细分，并集中到 `src/quality/verdicts.py` |
| 正式质量指标 | 未完成 | 尚缺 50 条检索样例、50 条 claim 样例和固定指标报告 |

## 已完成验证

- `python -m pytest --collect-only -q`：264 collected
- `python -m pytest tests/unit -q`：235 passed
- `python -m pytest tests/integration/test_app.py -q`：29 passed
- `python -m pytest tests -q`：275 passed
- `python -m pytest tests/unit/test_chunking.py tests/unit/test_sections.py tests/unit/test_quality.py -q`：20 passed
- `python -m pytest tests/unit/test_retrieval.py tests/unit/test_review.py tests/unit/test_knowledge_base.py -q`：20 passed
- `python -m pytest tests/unit/test_startup_scripts.py -q`：6 passed

## 未完成事项

- Markdown 结构感知分块仍未实现，当前仍是固定字符长度切分。
- 仍需建立正式证据可追溯率评测。
- 若未来需要更细的 `contradicted`、`insufficient_evidence` 等枚举，应按兼容迁移单独规划。
- 若未来迁移到更细 verdict 枚举，需单独规划兼容映射、历史展示和 API 口径。
- 正式评测集不足，PageIndex 仅有 10 问离线评测。
- 生产级部署仍需补监控、数据治理、CI 报告和更严格权限回归。

## 建议结论

MVP 主链路可进入内部验收；高可信证据型知识库仍需按 `todo.md` 的 2026-06-20 优化计划继续推进 P1/P2。
