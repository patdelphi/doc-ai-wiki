# P0 检索正确性与质量门禁实施计划

> 日期：2026-07-16
>
> 设计依据：`Docs/design/p0_code_quality_remediation_design_20260716.md`
>
> 执行方式：当前会话内按任务顺序执行，不使用 Subagent
>
> 状态：已完成；最终验收见变更记录与 `Docs/acceptance.MD`

## 目标与边界

本计划只实施三个已确认 P0：Rerank 显式降级、授权知识库全局检索、Mypy 真实覆盖本轮修改模块。测试只使用 Fake/Mock，不调用外部 API；不执行数据库迁移、部署或 Git 写操作。

## Task 1：Rerank 失败显式化

涉及文件：

- `tests/unit/test_rerank.py`
- `src/ai/rerank.py`

步骤：

1. 新增 OpenAI 兼容 Rerank 连接失败和空结果测试。
2. 运行聚焦测试，确认现状因静默返回原顺序而失败。
3. 删除网络异常吞并；空或无有效结果时抛出 `ValueError`。
4. 运行 Rerank 和检索融合测试，确认编排层统一产生 `rerank_unavailable`。

完成标准：客户端异常能到达 `RetrievalService`，最终结果保留原排序并带稳定降级标记。

## Task 2：统一知识库范围语义

涉及文件：

- `tests/unit/test_retrieval_scope.py`
- `src/retrieval/scope.py`

步骤：

1. 先写单值、多值、空列表、去重和冲突测试。
2. 确认测试因模块不存在而失败。
3. 实现最小 `normalize_knowledge_base_scope()`，不新增类或依赖。

完成标准：`None` 表示无限制，空元组表示显式无权限，单值和多值冲突抛出 `ValueError`。

## Task 3：词法与向量层支持多知识库过滤

涉及文件：

- `tests/unit/test_lexical.py`
- `tests/unit/test_vector_store.py`
- `src/retrieval/lexical.py`
- `src/retrieval/vector_store.py`

步骤：

1. 新增 SQL `IN`、Chroma `$in`、空范围和单值兼容测试。
2. 运行聚焦测试并确认失败。
3. 在词法检索中增加参数化 `IN` 条件。
4. 在 Chroma 查询中增加 `$in` 条件；同时有文档范围时使用 `$and`。
5. 运行聚焦测试确认通过。

完成标准：所有检索后端使用同一授权范围，空授权集合不会退化为全库查询。

## Task 4：服务与 API 改为一次全局检索

涉及文件：

- `tests/unit/test_retrieval.py`
- `tests/unit/test_retrieval_fusion.py`
- `tests/integration/test_app.py`
- `src/retrieval/service.py`
- `src/app.py`

步骤：

1. 新增参数透传、元数据范围校验和受限用户单次全局检索测试。
2. 运行聚焦测试，确认当前逐库循环造成失败。
3. 在全文、向量、混合和多查询路径透传 `knowledge_base_ids`。
4. 将 API 逐库循环替换为一次授权集合查询。
5. 运行聚焦测试确认通过，并确认单知识库接口兼容。

完成标准：受限用户未指定单库时只执行一次全局召回、融合和 Rerank。

## Task 5：恢复本轮模块 Mypy 门禁

涉及文件：

- `tests/unit/test_quality_gates.py`
- `pyproject.toml`
- `src/retrieval/service.py`
- `src/retrieval/vector_store.py`

步骤：

1. 新增配置测试，禁止豁免 `src.retrieval.service`、`src.retrieval.vector_store`，并禁止检索/PageIndex目录通配豁免。
2. 运行配置测试，确认当前精确豁免导致失败。
3. 删除两条精确豁免。
4. 运行 Mypy，精准修复上述模块真实报告的类型错误。
5. 再次运行配置测试与 Mypy。

完成标准：两个本轮修改模块不再被跳过，且真实通过现有 Mypy 命令。

## Task 6：完整验证与文档闭环

涉及文件：

- `todo.md`
- `Docs/changelog/retrieval_pageindex_20260716.md`
- `Docs/acceptance.MD`
- `Docs/optimization-plan/vibe_coding_code_quality_audit_20260716.md`
- `chat_history.md`

步骤：

1. 执行聚焦测试。
2. 执行 `python -m ruff check src tests .aipython`。
3. 执行 `python -m mypy src/retrieval src/pageindex src/quality/service.py`。
4. 执行 `python -m pytest tests --maxfail=1 -q`。
5. 执行 `python -m build` 和 `python -m compileall -q src tests .aipython`。
6. 更新 Todo、变更记录、验收文档、评估结论和聊天历史。
7. 检查差异、UTF-8 BOM、CRLF 和未授权操作边界。

完成标准：文档只记录当前实测结果；未通过项明确保留，不伪造绿色状态。
