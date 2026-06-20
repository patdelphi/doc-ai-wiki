# 2026-06-20 测试报告

> 项目：doc-ai-wiki
> 日期：2026-06-20
> 范围：P0 验收收口、测试环境复核、启动脚本与相对路径测试修复

## 环境

| 项目 | 结果 |
|---|---|
| `python --version` | Python 3.13.13 |
| `pytest --version` | pytest 9.0.3 |
| `python -m pytest --version` | pytest 8.4.2 |

## 执行结果

| 命令 | 结果 | 说明 |
|---|---:|---|
| `python -m pytest --collect-only -q` | 264 collected | 测试可正常收集 |
| `python -m pytest tests/unit/test_chunking.py tests/unit/test_sections.py tests/unit/test_quality.py -q` | 20 passed | 分块、章节、质检聚焦验证 |
| `python -m pytest tests/unit/test_retrieval.py tests/unit/test_review.py tests/unit/test_knowledge_base.py -q` | 20 passed | 检索、审核、知识库聚焦验证 |
| `python -m pytest tests/integration/test_app.py -q` | 29 passed | API 集成验证 |
| `python -m pytest tests/unit/test_startup_scripts.py -q` | 6 passed | 启动脚本验证 |
| `python -m pytest tests/unit -q` | 235 passed | 单元测试全量验证，耗时约 4 分 29 秒 |
| `python -m pytest tests -q` | 275 passed | P1 verdict 统一后完整测试验证，耗时约 5 分 10 秒 |
| `python -m pytest tests/unit/test_chunking.py -q` | 4 passed | P1 Markdown 结构感知分块验证 |
| `python -m pytest tests/unit/test_sections.py tests/unit/test_ingest_quality.py tests/unit/test_knowledge_base.py -q` | 18 passed | P1 分块影响路径验证 |
| `python -m pytest tests/integration/test_app.py::test_register_document_and_query_status_should_work tests/integration/test_app.py::test_vector_and_hybrid_search_should_return_results_after_ingest tests/integration/test_app.py::test_rebuild_should_support_fulltext_and_vector_separately -q` | 3 passed | P1 入库、检索、重建集成验证 |
| `python -m pytest tests/unit/test_sections.py tests/unit/test_ingest_quality.py tests/unit/test_retrieval.py -q` | 9 passed | P1 元数据追溯、入库与全文检索验证 |
| `python -m pytest tests/unit/test_vector_store.py tests/integration/test_app.py::test_vector_and_hybrid_search_should_return_results_after_ingest tests/integration/test_app.py::test_rebuild_should_support_fulltext_and_vector_separately -q` | 9 passed | P1 向量 metadata 与重建链路验证 |
| `python -m pytest tests/unit/test_viewmodels.py -q` | 45 passed | P1 证据详情与导出展示验证 |
| `python -m pytest tests/unit/test_ui.py -q` | 58 passed | P1 UI 构建与页面回归验证 |
| `python -m pytest tests/unit/test_verdicts.py tests/unit/test_quality.py -q` | 23 passed | P1 verdict helper 与质检行为验证 |
| `python -m pytest tests/unit/test_viewmodels.py::test_claim_display_helpers_should_generate_markdown_and_rows tests/integration/test_app.py::test_quality_and_review_flow_should_persist_result -q` | 2 passed | P1 verdict 展示与质检审核链路验证 |

## 本轮修复的测试预期

- `tests/unit/test_knowledge_base.py`：数据库 `source_path` 已按项目规则保存为 Input 相对路径，测试改为先断言相对路径，再用 `resolve_input_path()` 还原真实路径。
- `tests/integration/test_app.py`：启动脚本当前职责是同时启动 FastAPI 后端与 Gradio 前端，测试改为校验 `src.app:app` 与 `src.ui.app` 同时存在。
- `tests/integration/test_app.py`：重建测试读取数据库相对路径后，改为基于 `input_root` 还原文件路径再写入。
- `tests/unit/test_startup_scripts.py`：启动脚本已支持端口自动 fallback，测试改为校验起始 host/port 与动态环境变量，而不是固定端口字符串。

## P1 Markdown 分块补充验证

- `src/chunking/splitter.py` 已升级为 Markdown 语义块优先切分。
- 表格、围栏代码块、连续引用块会保持在同一 chunk 中。
- 超长普通段落仍按长度和重叠配置做兜底切分，兼容原有 `split_text()` 调用方。

## P1 元数据追溯补充验证

- `document_sections` 已支持标题路径、起止行号和来源锚点。
- `chunks` 已支持标题路径、起止行号、页码占位、chunk 类型、内容 hash 和来源锚点。
- 旧库初始化会通过 `ALTER TABLE` 补齐新增追溯列。
- 入库、全文检索、向量检索、向量重建链路均可保留 chunk 级追溯字段。
- 审核证据详情、证据 HTML 和质检导出会展示标题路径、来源锚点、chunk 类型和内容 hash。

## P1 verdict 体系补充验证

- 当前阶段保留 claim 级简化枚举：`verified`、`needs_review`、`rejected`。
- 证据关系使用 `support`、`contradict`、`insufficient` 表达细分判断。
- `contradict` 会强制收口为 `rejected`，`insufficient` 不允许模型结果升级为 `verified`。
- 总体 verdict 兼容当前 API：全部 claim 为 `verified` 时返回 `passed`。

## 结论

当前环境不是“无法验证测试”。截至本报告，完整测试 `python -m pytest tests -q` 已通过，结果为 `275 passed, 6 warnings`。后续仍建议在 CI 中持续运行完整测试，并把耗时作为质量门禁的一部分记录。
