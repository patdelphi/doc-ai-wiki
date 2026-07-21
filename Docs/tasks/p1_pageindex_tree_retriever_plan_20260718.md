# P1 PageIndex 确定性树检索职责拆分实施计划

> 日期：2026-07-18
> 状态：已完成
> 依据：`Docs/design/p1_pageindex_tree_retriever_design_20260718.md`

## 1. 关键假设与完成标准

- 仅拆分确定性树检索算法，不修改领域词、Prompt、LLM 多轮编排、RAG、数据库或索引。
- `PageIndexService` 只保留一个真实承担问题词准备和 vendor 原文读取的 `_build_tree_candidates()`。
- 新模块不依赖服务、数据库、设置、LLM 或 vendor PageIndex client。
- 完成标准：算法逐字段兼容，九个无状态服务方法删除，聚焦与完整验证全部通过，交付文档同步。

## 2. 执行任务

- [x] **任务 1：建立确定性算法直接测试（TDD Red）**
  - 新增 `tests/unit/test_pageindex_tree_retriever.py`。
  - 覆盖树展开、位置、评分、惩罚、排序、稳定 ID、截断、内容 loader、交叉引用、合并和 debug。
  - 先运行测试并确认因模块不存在而失败。

- [x] **任务 2：实现纯算法模块（TDD Green）**
  - 新增 `src/pageindex/tree_retriever.py`。
  - 迁入九项确定性职责，并保持算法不变量。
  - 运行新模块单元测试，确认通过。

- [x] **任务 3：建立服务边界质量门禁（TDD Red）**
  - 在 `tests/unit/test_quality_gates.py` 增加服务方法与依赖边界断言。
  - 先运行门禁，确认旧方法仍存在时失败。

- [x] **任务 4：收敛服务为 IO 适配层（TDD Green）**
  - 服务直接导入模块函数并替换调用点。
  - `_build_tree_candidates()` 仅准备打分词、构造可选 loader 并调用纯函数。
  - 删除九个无状态方法和重复树展开实现。
  - 更新原有交叉引用测试为模块级测试入口。

- [x] **任务 5：聚焦回归验证**
  - 运行新模块、PageIndex 服务、质量门禁测试。
  - 运行 Ruff 与 Mypy。
  - 核对候选字段、排序、交叉引用和异常传播没有变化。

- [x] **任务 6：完整验证与文档收口**
  - 运行完整 Pytest、build、compileall 和差异检查。
  - 统计服务及生产代码行数、方法数，确认未引入平行算法层。
  - 同步设计、Todo、Changelog、验收、代码质量审计、成熟度评估和聊天记录。

## 3. 明确不执行

- 不调用真实 LLM 或其他外部 API。
- 不执行数据库迁移、索引重建、部署或依赖安装。
- 不执行 Git commit、push、pull 或 merge。
- 不修改三个既有噪声文档。

## 4. 执行结果

- TDD Red 1：模块不存在时，直接测试以 `ModuleNotFoundError` 失败；实现后 8 项通过。
- TDD Red 2：职责门禁确认九个旧服务方法仍存在；迁移删除后通过。
- 服务由 2354 行、84 个方法降至 2165 行、75 个方法；新模块 189 行，生产代码合计不增加。
- 聚焦回归：74 项通过；完整回归：`446 passed, 6 warnings in 215.49s`。
- Ruff 通过；CI 范围 Mypy `22` 个源文件通过；sdist、wheel 和 compileall 通过。
- 扩大到整个 `src` 的 Mypy 仍暴露既有 UI 动态类型与 PyYAML stub 问题，不属于本批精准修改范围，继续保留在统一 Todo 的逐模块治理项。
