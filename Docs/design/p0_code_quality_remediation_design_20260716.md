# P0 正确性与质量门禁修复设计

> 日期：2026-07-16
>
> 分支：`codex/retrieval-pageindex-optimization`
>
> 状态：已确认并实施

## 1. 目标

本轮只处理前期成熟度评估和 Vibe Coding 代码审查中已确认的三个 P0 问题：

1. Rerank 生产查询静默降级；
2. 受限用户跨知识库检索按知识库顺序截断，无法形成全局相关性排序；
3. Mypy 对本轮将修改的检索核心模块使用精确 `ignore_errors`，CI 对这些模块的门禁失真。

同时把完整 P0/P1/P2 升级路线整合到根目录 `todo.md`，本轮只执行 P0，P1/P2 保持未完成状态。

## 2. 非目标

本轮不处理：

- `src/ui/pages.py` 和 `src/pageindex/service.py` 的模块拆分；
- 180 个 UI 未使用导入和变量的批量清理；
- 人工金标、线上监控、用户反馈和上传功能；
- PageIndex 多文档规模扩展；
- 数据库迁移；
- 向量库或模型更换；
- 外部 API 调用；
- Git commit、push、merge 或部署。

## 3. 方案比较与选择

### 3.1 跨知识库检索

方案一：强制非管理员选择单一知识库。

- 优点：改动最少。
- 缺点：破坏现有跨授权知识库检索能力，属于功能退化。

方案二：检索层原生支持 `knowledge_base_ids` 多值过滤。

- 优点：只执行一次全局召回、融合和 Rerank；结果不依赖知识库 ID 顺序；模型调用次数稳定。
- 缺点：需要同时调整 API 编排、全文检索和向量检索接口。

方案三：每个知识库分别检索，再在应用层合并。

- 优点：底层接口改动较少。
- 缺点：模型调用次数随知识库数增长；不同批次 Rerank 分数不适合直接比较；仍容易形成排序偏置。

选择方案二。

### 3.2 Mypy 门禁

方案一：一次性删除全部 `ignore_errors` 并修复所有类型错误。

- 优点：最终状态最严格。
- 缺点：会把 P0 扩大为大规模重构，违反最小修改原则。

方案二：删除本轮涉及的 `src.retrieval.service` 和 `src.retrieval.vector_store` 精确豁免；未修改的遗留巨型模块继续保留精确模块豁免。

- 优点：门禁开始真实生效，同时限制本轮范围。
- 缺点：遗留大模块尚未全部纳入类型检查。

方案三：保持当前配置，只在文档中说明 Mypy 有限。

- 优点：无代码改动。
- 缺点：CI 继续假绿，无法阻止新增问题。

选择方案二。当前配置并不存在检索或 PageIndex 的目录通配豁免；后续 P1 继续逐模块删除其余精确豁免。

## 4. Rerank 修复设计

### 4.1 当前根因

`OpenAICompatibleReranker` 和 `DashScopeReranker` 在 HTTP 失败时直接返回原始候选。`RetrievalService` 只有捕获到异常时才写入 `degraded_reason=rerank_unavailable`，因此异常被客户端吞掉后，调用方无法识别真实降级。

空或无效 Rerank 响应也会通过 `_apply_rerank_results()` 返回原始候选，形成另一条静默降级路径。

### 4.2 目标行为

- 候选数为 0 或 1 时，不调用外部 Rerank，正常返回。
- HTTP、超时、连接、JSON 或无有效结果异常向上抛出。
- `RetrievalService.hybrid_search()` 和 `search_queries()` 统一捕获异常。
- 降级结果保留原始 RRF 顺序，并写入 `degraded_reason=rerank_unavailable`。
- 不在业务结果中暴露外部服务原始异常文本。

### 4.3 最小实现

- 修改 `src/ai/rerank.py`：删除客户端内部网络异常回退；无有效 Rerank 结果时抛出 `ValueError`。
- 保留 `src/retrieval/service.py` 现有统一捕获逻辑。
- 新增回归测试覆盖 HTTP 失败和空结果。

## 5. 多知识库全局检索设计

### 5.1 当前根因

非管理员不传 `knowledge_base_id` 时，`src/app.py` 按允许知识库 ID 排序逐库执行检索；结果达到 `top_k` 后立即返回。第一个知识库可能完全占据结果，且每个知识库都会重复执行 Embedding/Rerank。

### 5.2 接口约定

在现有单值参数之外增加可选多值参数：

```python
knowledge_base_ids: list[str] | None = None
```

规则：

- 单值 `knowledge_base_id` 与多值 `knowledge_base_ids` 不同时使用；
- 空列表返回空结果，不能解释为“不限制知识库”；
- 去除空值并保序去重；
- 管理员无筛选时维持全库检索；
- 受限用户无单库参数时传入全部授权知识库 ID；
- FTS、向量和 SQLite 元数据回填使用同一过滤范围。

### 5.3 数据流

```text
API 身份与知识库权限
-> 解析单库或授权知识库集合
-> RetrievalService
-> LexicalRetriever: SQL IN 过滤
-> VectorStore: Chroma $in 过滤
-> RRF 全局融合
-> 单次 Rerank
-> SQLite 元数据范围校验
-> Top-K
```

### 5.4 修改边界

- `src/app.py`：停止逐库循环，传递授权知识库集合。
- `src/retrieval/service.py`：全文、向量、混合和多查询接口透传多值范围。
- `src/retrieval/lexical.py`：构造参数化 SQL `IN` 条件。
- `src/retrieval/vector_store.py`：构造 Chroma `$in` 过滤条件。
- 测试覆盖知识库顺序、空授权集合、单库兼容和跨库全局排序。

不新增 Repository、Filter Builder 或 Strategy 类。

## 6. Mypy 门禁设计

### 6.1 目标

CI 中显示通过且被本轮修改的模块必须真正接受类型检查，不能继续被精确 `ignore_errors` 跳过。

### 6.2 配置调整

- 删除 `src.retrieval.service` 和 `src.retrieval.vector_store` 两条精确豁免。
- 对本轮未治理的 `src.pageindex.service`、`src.pageindex.templates`、`src.pageindex.evidence_judge` 等遗留模块继续保留精确豁免。
- CI 继续检查检索/PageIndex目录，并让本轮修改的检索模块真实参与检查。
- 为配置增加测试，禁止重新豁免上述两个检索模块，并禁止新增检索/PageIndex目录通配豁免。

本轮新增或修改的检索底层模块必须通过 Mypy；遗留巨型服务在 P1 中逐项治理。

## 7. 测试策略

严格采用 Red-Green-Refactor：

1. 先写 Rerank 静默降级失败测试并确认失败；
2. 实现最小 Rerank 修复并确认通过；
3. 先写多知识库全局检索失败测试并确认失败；
4. 实现多值过滤并确认通过；
5. 先写 Mypy 配置门禁测试并确认失败；
6. 调整配置和 CI 并确认通过；
7. 执行相关单元和集成测试；
8. 执行 Ruff、Mypy、完整 Pytest、build 和 compileall。

测试不调用真实外部模型，使用 HTTP mock 或可控 Fake 验证错误传播和降级状态。

## 8. 错误处理

- 外部 Rerank 异常只在检索编排层转换为稳定降级标记。
- 不向用户暴露 API Key、URL、响应正文或堆栈。
- 多知识库空权限集合直接返回空结果。
- 单值与多值冲突由内部调用约定避免；如同时出现，服务抛出明确 `ValueError`，不猜测优先级。
- Chroma 不支持预期 `$in` 语法时，测试必须先暴露问题，不增加静默客户端循环兜底。

## 9. 文档与验收

实施完成后更新：

- `todo.md`；
- `Docs/changelog/retrieval_pageindex_20260716.md`；
- `Docs/acceptance.MD`；
- `Docs/optimization-plan/vibe_coding_code_quality_audit_20260716.md`；
- `chat_history.md`。

完成标准：

- Rerank 失败结果始终包含 `degraded_reason=rerank_unavailable`；
- 受限用户跨库检索只执行一次全局检索，不依赖知识库 ID 顺序；
- `src.retrieval.service` 和 `src.retrieval.vector_store` 不再被 `ignore_errors` 跳过；
- 新增测试完成红绿验证；
- Ruff、Mypy目标、完整Pytest、build和compileall均以最新运行结果为准；
- 不执行外部API、commit、push、merge和部署。
