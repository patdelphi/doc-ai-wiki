# P1 PageIndex 最终回答编排职责拆分设计

> 日期：2026-07-19
> 状态：已实施并完成本地验收
> 范围：`src/pageindex`、PageIndex 单元测试、质量门禁与项目交付文档

## 1. 背景与目标

完成历史导出、持久化和确定性树检索拆分后，`PageIndexService` 仍有 2165 行、75 个方法。当前服务同时包含两类不同职责：

- 检索侧：文档路由、多轮树检索、RAG/FTS 补充、预算生命周期、vendor 原文读取；
- 最终回答侧：Question Plan、证据分类、模板渲染、LLM 最终回答、本地保守回答和来源格式化。

本批次采用已确认的 A 方案：新增一个具体的 `PageIndexAnswerOrchestrator`，只迁移最终回答侧职责；检索侧继续留在服务中。目标是形成真实边界，而不是把整个服务复制到新类或增加回调、Protocol、Factory 等间接层。

完成后应满足：

- 最终回答可在不创建数据库、RetrievalService、vendor PageIndex client 或 workspace 的情况下直接测试；
- 公开 PageIndex 服务接口、返回结构、Prompt、预算计数和异常降级保持不变；
- LLM 明确未选择节点时，不启用宽松关键词或 RAG 兜底；
- 删除无调用的旧单轮 LLM 树检索路径和无用包装方法；
- 不迁移多轮检索、RAG、文档路由或领域词规则。

## 2. 方案比较

### A：只迁移最终回答层（采用）

新编排器负责 Question Plan、证据分类、模板渲染、最终 LLM 回答和本地保守回答；服务保留检索生命周期。

优点：

- 依赖仅限模板服务、Question Plan、证据判断和预算对象；
- 不需要把 PageIndex client、RetrievalService 或 Service 自身注入新类；
- 可以删除多项无状态方法和包装层；
- 不改变检索算法与真实 LLM 调用顺序。

代价：

- `_answer_with_iterative_tree_reasoning()` 和多文档聚合仍在服务中；
- “回答编排”在本设计中特指证据到最终回答，不包含检索编排。

### B：迁移完整检索与回答生命周期

同时迁移单文档、多轮检索、多文档聚合、RAG 和最终回答。服务行数下降更多，但新类必须依赖 vendor client、检索服务、路由、候选构建和大量回调，容易形成第二个巨型服务，不采用。

### C：只迁移本地回答纯函数

风险最低，但 Question Plan、模板和最终 LLM 调用仍散落在服务中，不能形成完整回答边界，不采用。

## 3. 新模块与公开接口

新增 `src/pageindex/answer_orchestrator.py`，只定义一个具体类，不增加接口层或工厂。构造函数接收现有 `PageIndexTemplateService`，公开四个方法：

- `build_question_plan(llm_client, question, evidence, budget=None) -> dict`；
- `classify_evidence_items(question, evidence) -> list[dict]`；
- `build_local_answer(question, evidence) -> str`；
- `generate_llm_answer_payload(llm_client, question, evidence, template_id=None, question_plan=None, budget=None) -> dict`。

结构上下文、证据判断摘要、证据要点、来源列表和不确定性说明作为模块私有函数存在，不暴露新的公共配置对象。

## 4. 服务边界

### 4.1 从服务迁移或删除的方法

以下十四个回答方法从 `PageIndexService` 删除：

- `_generate_llm_answer()`：无生产调用的包装方法，直接删除；
- `_generate_llm_answer_payload()`：迁入编排器；
- `_build_question_plan()`：迁入编排器；
- `_build_answer_structure_context()`：迁为模块私有函数；
- `_build_local_answer()`：迁入编排器；
- `_classify_evidence_items()`：迁入编排器；
- `_classify_single_evidence()`：无生产调用，直接删除；
- `_build_local_evidence_judgement()`：迁为模块私有函数；
- `_build_local_evidence_points()`：迁为模块私有函数；
- `_build_local_source_points()`：迁为模块私有函数；
- `_infer_local_conclusion()`：删除包装，模块直接调用 `infer_conclusion()`；
- `_infer_local_uncertainty()`：迁为模块私有函数；
- `_is_benefit_or_treatment_question()`：无调用，直接删除；
- `_is_formula_context_for_single_herb_question()`：无调用且职责已由 Evidence Judge 承担，直接删除。

同时删除两个已无生产入口的旧单轮树检索方法：

- `_answer_with_llm_tree_reasoning()`；
- `_build_tree_reasoning_prompts()`。

这条旧路径已被迭代式树检索取代，源码检索确认只有定义和互相调用，没有生产入口。删除后不保留兼容别名。

### 4.2 服务保留的职责

- `ask_question()` 与知识库范围公开入口；
- `_answer_knowledge_base_with_reasoning_or_fallback()`；
- `_answer_with_reasoning_or_fallback()`；
- `_answer_with_iterative_tree_reasoning()`；
- 问题分析、文档路由、候选构建和多轮 sufficiency 判断；
- RAG/FTS 补充、证据合并和预算生命周期；
- vendor client 创建、节点原文读取、数据库与 workspace 访问；
- 检索策略读取和领域词处理。

### 4.3 服务初始化

服务继续创建现有 `PageIndexTemplateService`，随后创建：

```python
self.answer_orchestrator = PageIndexAnswerOrchestrator(self.template_service)
```

调用点直接使用 `self.answer_orchestrator`，不保留服务方法包装层。

## 5. 数据流

```text
问题
  -> PageIndexService 文档路由与多轮检索
  -> PageIndexService 合并 PageIndex 与 RAG/FTS 证据
  -> PageIndexAnswerOrchestrator.classify_evidence_items
  -> 有证据且预算允许
       -> build_question_plan
       -> 模板渲染
       -> generate_llm_answer_payload
     无证据或 LLM 失败
       -> build_local_answer
  -> PageIndexService 组装原有返回结构和 debug
```

知识库多文档流程继续由服务依次检索文档；所有文档证据合并后，调用同一个回答编排器生成聚合答案。

## 6. 行为不变量

迁移必须逐项保持：

- Question Plan 的 Prompt、标准化和异常回退不变；
- 预算消费顺序保持 `question_plan`、`final_answer`；
- 已提供 `question_plan` 时不重复调用 Planner；
- 模板 ID、模板变量、structure context、evidence judgement 和 citation rules 不变；
- 最终答案仍只读取 LLM JSON 的 `answer` 字段；
- 无证据回答继续包含“结论、依据、来源、不确定点”；
- 有证据的本地回答继续包含“结论、证据判断、依据、来源、不确定点”；
- 证据分类字段、结论策略、内容截断和来源顺序不变；
- 最终 LLM 失败时由现有调用者回退，不在新模块吞掉异常；
- LLM 明确返回空节点时仍返回空证据，不触发宽松 fallback；
- 服务公开结果中的 `retrieval_mode`、`llm_error`、`debug` 和历史字段不变。

本批次不修改任何 Prompt 文本、规则词、阈值、模板 YAML 或证据判断规则。

## 7. 错误处理

- Question Plan 调用继续捕获普通模型异常并使用 `normalize_question_plan()` 生成结构化兜底；
- `RetrievalBudgetExceededError` 继续原样抛出；
- 最终回答 LLM 调用异常继续向上传播，由现有单文档或多文档调用点记录 `llm_error` 或生成本地回答；
- 模板读取和渲染异常不增加新的静默降级；
- 新模块不访问数据库、文件系统、网络客户端或 vendor workspace，因此不新增数据库事务与 IO 异常边界。

## 8. 测试设计

新增 `tests/unit/test_pageindex_answer_orchestrator.py`，直接覆盖：

1. Question Plan 正常返回、模型失败兜底与预算超限传播；
2. 已提供 Question Plan 时不重复调用 Planner；
3. 模板渲染参数、结构上下文、证据判断和 citation rules；
4. 最终 LLM 回答 payload 与预算计数；
5. 无证据本地拒答；
6. 有证据本地答案的五段结构；
7. 证据分类、保守结论、来源定位和不确定性；
8. 最终回答异常不被新模块吞掉。

现有服务测试继续覆盖：

- 单文档与知识库多文档回答；
- 迭代式节点选择、交叉引用、RAG 补充和 sufficiency；
- LLM 明确空选择时不 fallback；
- 模板策略、Question Plan、预算和历史持久化；
- 本地关键词降级与错误可观测性。

质量门禁新增断言：

- 十四个回答方法不再定义于服务；
- 旧单轮树检索方法和旧 Prompt 构造器不存在；
- `answer_orchestrator.py` 不导入 `PageIndexService`、数据库、RetrievalService、设置或 vendor `PageIndexClient`；
- 服务只有一个 `PageIndexAnswerOrchestrator` 实例，不存在回答包装层。

## 9. 验收标准

- 新编排器直接测试先 Red 后 Green；
- 服务职责门禁先因旧方法存在而 Red，迁移后 Green；
- 十六个旧服务方法删除且没有兼容别名；
- 公开行为、Prompt、预算、异常和返回结构逐项兼容；
- 服务方法数至少减少十六，服务与新模块生产代码合计不增加；
- Ruff、PageIndex/质量门禁聚焦测试、CI 范围 Mypy、完整 Pytest、build 和 compileall 全部通过；
- 变更同步到设计、计划、Todo、Changelog、验收、代码质量审计、成熟度评估和聊天记录；
- 不调用真实外部 API，不执行正式数据库迁移、索引重建、部署、commit 或 push。

## 10. 不在本批范围

- 不迁移多轮检索、RAG/FTS、文档路由和预算对象创建；
- 不配置化阿胶、疾病、方剂或评测主题词；
- 不修改 Evidence Judge 规则或模板 YAML；
- 不修复整个 `src` 的既有 Mypy 动态 UI 问题；
- 不新增 Provider、缓存、事件总线、接口层或依赖注入框架。

## 11. 回滚边界

本批次不修改数据库、索引、模板文件或运行数据。若验证失败，只需回滚编排器初始化、调用点迁移、旧方法删除和对应测试，无需恢复数据库或索引。

## 12. 实施结果

- 新增 `PageIndexAnswerOrchestrator`，集中 Question Plan、证据分类、本地保守回答和 LLM 最终回答载荷生成。
- `PageIndexService` 直接持有单一编排器实例，不保留同名包装方法或平行兼容层。
- 服务共删除十四个回答相关方法和两个旧单轮树检索方法，共十六个方法。
- `service.py` 从 2165 行、75 个方法降至 1834 行、59 个方法；新模块为 172 行、5 个类方法，两文件合计 2006 行，较迁移前净减少 159 行。
- 新增八项编排器直接测试和职责门禁；TDD 已完成 Red→Green，聚焦回归 `75 passed, 6 warnings`，完整回归 `455 passed, 6 warnings in 194.02s`。
- Ruff、CI 范围 Mypy（23 个源文件）、sdist/wheel 构建和 `compileall` 均通过。
- 未调用真实外部 API，未执行数据库迁移、索引重建、部署、commit 或 push。
