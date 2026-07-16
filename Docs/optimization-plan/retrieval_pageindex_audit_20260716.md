# AI 检索与 PageIndex 双流程专项审计

> 日期：2026-07-16
> 范围：文档入库、FTS、向量检索、混合召回、重排、AI 质检证据检索、PageIndex 建树与问答
> 性质：只读审计；未修改业务代码、未调用外部 API、未安装依赖、未执行 Git 操作

## 1. 结论摘要

项目已经具备两套完整但定位不同的检索能力：

1. **AI 检索主链路**适合知识库级快速召回：SQLite FTS/LIKE、Chroma 向量检索、去重、可选 Rerank，并被知识库检索页和 AI 质检复用。
2. **PageIndex 链路**适合长文档结构化定位：先生成章节树，再由 LLM 分析问题、选择节点、判断证据充分性并生成回答。

当前最大问题不是功能缺失，而是**真实索引状态、算法实现与产品描述不完全一致**：

- SQLite 有 `4207` 个 chunk，Chroma 只有 `2145` 条向量；默认知识库向量缺少 `knowledge_base_id` 元数据，按知识库过滤时无法正常召回。
- 真实数据库中 `4207/4207` 个 chunk 的标题路径、行号、来源锚点和内容 hash 均为空，当前证据追溯能力只存在于新代码和新入库流程中，没有落实到现存数据。
- 当前 FTS 没有使用 BM25 排序；中文短语大量退化为 LIKE，混合检索在不重排时也没有可靠的融合排序。
- 两份真实 PageIndex 索引分别有 `352` 和 `953` 个节点，但最大深度都只有 `1`。当前运行效果更接近“平铺章节候选 + LLM 选择”，不是有效的层级树导航。
- 现有 50 条正式检索评测使用的是示例 `doc_uid/chunk_id`，与真实数据库不一致，历史报告 Top-5 命中率为 `0.0`，目前没有可信的真实质量基线。

因此，建议先修复索引一致性与评测可信度，再优化召回融合和 PageIndex 推理。暂不建议先做大型架构重构。

## 2. 两套流程的真实结构

### 2.1 AI 检索主链路

```text
文档读取
  -> Markdown 章节解析
  -> 语义块优先、500 字符兜底切分
  -> SQLite chunks + FTS 索引
  -> Chroma 向量写入
  -> 查询别名归一与扩展
  -> FTS/LIKE 召回 + 向量召回
  -> chunk_id 去重
  -> 可选 Rerank
  -> 知识库检索页 / AI 质检证据检索
```

实际算法特征：

- FTS 表使用默认 FTS5 tokenizer，没有中文分词或 trigram 配置。
- FTS 查询没有 `bm25()` 和 `ORDER BY rank`。
- FTS 无结果或报错时使用 `%query%` LIKE，并按 `updated_at` 或 `chunk_index` 排序。
- 混合检索先放入全文结果，再追加向量结果；没有 RRF、加权融合或分数归一。
- 向量分数使用 `1 - distance`，但 Chroma 默认距离空间与全文分数不在同一量纲。
- Rerank 启用时能纠正部分顺序；禁用、失败或无 API Key 时会保留原始合并顺序。

AI 质检在主检索之上又增加了一层查询生成：原始 Claim、实体别名、逻辑放宽、主题聚焦、关键词聚焦和反证探测。普通 Claim 最多可生成约 `15` 个查询，每个查询都会独立执行混合召回和可能的 Rerank，质量思路合理，但调用次数、成本和重复召回偏高。

### 2.2 PageIndex 建树与问答链路

```text
Markdown/PDF
  -> 清洗副本
  -> vendor PageIndex 解析标题或 PDF 目录
  -> 构建节点、摘要和文档描述
  -> workspace JSON + pageindex_indexes
  -> LLM 问题分析
  -> LLM Question Plan
  -> 本地关键词评分筛出候选节点
  -> LLM 最多 3 轮选择节点并判断充分性
  -> 加载节点原文
  -> 条件性 RAG/FTS 补证据
  -> Evidence Judge 分类
  -> LLM 最终回答
  -> pageindex_query_history
```

需要明确：vendor 负责**建树和按节点读取内容**，项目自己的 `PageIndexService` 才负责查询分析、候选打分、迭代选择、RAG 补证据和回答。当前不是 vendor 提供的完整 agentic tree search，而是项目自定义的“本地预筛 + LLM 节点选择”。

知识库级问答会对所有已建索引文档逐篇执行完整流程，再汇总证据并生成一次聚合答案。当前两个文档在最坏情况下可能触发十余次 LLM 调用，尚未实现文档级路由和预算控制。

## 3. 主要问题与优化建议

### P0-1：SQLite 与 Chroma 索引严重不一致

证据：

- SQLite `chunks`：`4207`。
- Chroma `embeddings`：`2145`。
- `阿胶历史文化通典_default`：SQLite `669`，Chroma `0`。
- `阿胶学术论文全集_default`：SQLite `3537`，Chroma `2144`。
- Chroma 现有 metadata 没有 `knowledge_base_id`；当前向量查询会附带该过滤条件。
- 三篇文档仍全部标记为 `index_status=indexed`。

影响：

- 默认知识库的向量召回可能为空或严重不完整。
- UI 显示“已索引”，但真实向量覆盖不完整，属于状态假绿。
- 混合检索实际上可能退化为全文/LIKE + Rerank。

建议：

1. 先增加只读一致性检查：SQLite chunk 数、Chroma 向量数、metadata 完整率、embedding 维度和模型指纹。
2. 经备份和确认后重建向量索引，并补齐 `knowledge_base_id`。
3. `index_status=indexed` 必须以 SQLite/Chroma 计数和模型指纹一致为条件。
4. 启动时不要静默执行破坏性自动修复；应先输出修复预览并要求确认。

### P0-2：现存数据的证据追溯字段全部缺失

证据：

- `4207/4207` 个 chunk 缺少 `heading_path`、`source_start_line`、`source_anchor`、`content_hash`。
- `1165/1165` 个 section 缺少标题路径、起始行和来源锚点。

影响：

- 当前评测的证据追溯率无法达标。
- AI 质检和人工审核无法稳定定位到原文位置。
- 新代码的追溯能力只对重新入库的数据有效。

建议：

1. 把“补列”与“补数据”分开处理；目前数据库只完成了前者。
2. 设计可回滚的重建流程，从源文档重新生成 section/chunk 追溯信息。
3. 重建前固定旧 `chunk_id` 到新证据的映射策略，否则历史质检记录会失去引用。

### P0-3：全文与混合检索没有可信排序

证据：

- FTS SQL 没有 BM25 排序。
- `质量检测`、`制作工艺` 等中文短语的直接 FTS 查询无结果，实际走 LIKE。
- `阿胶 贫血` 的当前返回顺序与 BM25 顺序明显不同；当前第一条是噪声较大的实验片段，BM25 第一条是直接讨论贫血的片段。
- `质量检测` 当前第一条是目录内容，不是具体检测方法。
- 无 Rerank 时，混合结果保持“全文优先、向量追加”的插入顺序。

建议采用简单、可解释的两阶段方案：

1. 中文词法召回使用 FTS5 trigram（当前 SQLite `3.50.4` 已验证支持）并应用 BM25；两字短词保留受控 LIKE 补充。
2. 向量召回与词法召回先分别取候选，再用 RRF 融合，避免直接比较不同量纲分数。
3. 只对融合后的候选批量 Rerank 一次。
4. 输出 `lexical_rank`、`vector_rank`、`rrf_score`、`rerank_score` 和降级原因，保证可诊断。
5. 增加最低相关性或无答案阈值，不能只依赖 Top-K 必然返回结果。

### P0-4：PageIndex 真实结构已退化为平铺节点

证据：

| 文档 | 节点数 | 根节点数 | 最大深度 | 有摘要节点 |
|---|---:|---:|---:|---:|
| 阿胶历史文化通典 | 352 | 352 | 1 | 94 |
| 阿胶学术论文全集 | 953 | 953 | 1 | 307 |

影响：

- 父子层级、树导航、从概览逐步下钻等 PageIndex 核心优势无法发挥。
- 当前“迭代检索”实际上是在平铺候选中多轮选取节点。
- 大量节点只能依赖本地关键词预筛，否则无法直接放入 LLM 上下文。

建议：

1. 建索引后增加树质量门禁：最大深度、根节点比例、摘要覆盖率、空标题率、超大节点率。
2. 对论文合集先识别文章边界，再修复标题层级；不要把整套论文当成一个平铺目录。
3. 树质量不合格时明确标记为 `flat_section_index`，不要在 UI 中宣称为层级树检索。
4. 重新建树前先用 1 至 2 篇代表文档做离线验收，不直接全量重建。

### P0-5：正式评测集与真实数据库没有对齐

证据：

- `tests/evaluation/retrieval_cases.jsonl` 使用 `doc_ejiao`、`ejiao_effect_001` 等示例 ID。
- 真实数据库使用 `阿胶学术论文全集_default` 和随机 `chk_*` ID。
- 当前正式报告 50 条样例 Top-5 命中率为 `0.0`，证据追溯率为 `0.0`。

影响：

- 无法判断算法改动是提升还是退化。
- 单元测试通过只能证明接口行为，不能证明真实召回质量。

建议：

1. 冻结一个小型、可版本化的离线评测知识库，ID 必须稳定。
2. 将真实知识库评测与合成 fixture 评测分开。
3. AI 检索至少记录 Recall@5、Recall@10、MRR、nDCG@10、无答案准确率和追溯率。
4. PageIndex 至少记录文档命中率、节点命中率、无证据拒答准确率、平均轮次和 LLM 调用数。
5. 负例必须覆盖“感冒”“不孕不育”等无直接证据问题。

### P0-6：知识库级 PageIndex 异常处理存在明确缺陷

`PageIndexService` 使用 `except AppError`，但模块没有导入 `AppError`。某篇文档抛出应用异常时，该分支会触发 `NameError`，导致知识库级容错失效。

建议先增加失败测试，再补充正确导入；同时验证一篇文档失败时其它文档仍可继续贡献证据。

### P1-1：“迭代检索”没有使用下一轮搜索焦点

LLM 会返回 `missing_information` 和 `next_search_focus`，但下一轮仍使用相同的原问题和问题分析重新构造候选，仅排除已选节点并加入交叉引用节点。

建议：

- 把 `next_search_focus` 合并到下一轮查询分析和候选打分词。
- 允许按父节点、子节点、同级节点和交叉引用定向扩展。
- 每轮记录候选变化原因；如果候选集合没有变化，应提前停止。

### P1-2：知识库级 PageIndex 缺少文档路由和全局证据预算

当前实现逐篇读取全部已索引文档，成本随文档数线性增长，聚合后也没有统一的全局证据 Top-K。

建议：

1. 先用文档描述、标题树摘要和 Question Plan 做文档级候选排序。
2. 默认只读 2 至 3 篇文档；比较/汇总类问题可扩大预算。
3. 聚合后按统一 Evidence Schema 排序、去重和限制总证据数。
4. 多文档冲突必须显示文档来源和冲突关系。

### P1-3：PageIndex 的 RAG/FTS 补证据重复实现主检索逻辑

PageIndex 内部再次直接查询 `chunk_fts` 和 LIKE，并维护独立的查询词过滤、实体扩展和医学场景规则。这与 `RetrievalService` 形成两套词法召回实现，容易继续漂移。

建议：

- PageIndex 只负责“何时补证据、补哪个文档”，实际召回统一调用 `RetrievalService`。
- 保留 PageIndex 专属的补证据门禁，但不要复制 SQL、token 规则和实体扩展。
- 将医学专属规则移入模板或领域策略，不继续写入通用服务类。

### P1-4：AI 质检查询扩展过多，外部调用成本偏高

当前一个普通 Claim 可生成约 15 个检索查询；每个查询可能各自调用 Embedding 和 Rerank。建议先合并查询意图、限制高价值变体为 3 至 5 个，再统一融合和执行一次 Rerank。

建议保留的查询类型：

1. 原始 Claim。
2. 标准实体 + 核心关系。
3. 反证/边界查询。
4. 必要时一个别名查询。

### P1-5：分块策略缺少跨语义块上下文

当前 `500/100` overlap 只用于超长普通段落的固定长度切分；不同 Markdown 语义块之间没有 overlap。表格、代码块和列表即使超过 500 字符也不会再切分。

建议：

- 保留语义块优先策略。
- 为相邻段落增加轻量窗口，不重复整块。
- 对超长表格/列表设计按行切分并保留表头。
- 记录 chunk 的字符数、结构类型和父 section，评测不同 chunk 策略。

### P1-6：数据库运行参数未符合项目规则

真实数据库当前为 `journal_mode=delete`、`synchronous=FULL`；`create_connection()` 只启用了外键，没有设置 WAL 和 `synchronous=NORMAL`。

这不是本轮直接修改项。后续变更前必须先备份，并验证多连接、迁移和 Windows 文件锁行为。

### P1-7：测试环境仍会读取真实 `.env`

全量测试首个失败为默认管理员启用状态不符合预期，原因是本地 `.env` 的初始管理员密码进入测试配置。该现象与此前外部 Embedding 配置泄漏属于同一类问题：测试没有完全隔离真实运行配置。

建议测试设置统一声明 `_env_file=None` 或使用专用环境工厂，确保单元测试不会读取真实凭据或外部服务配置。

## 4. 推荐目标架构

不建议把两套算法强行合并成一个复杂流程。应保持两个检索引擎，统一编排和证据格式：

```text
Query Router
  ├─ 普通事实、短问题、全库搜索 -> Hybrid Retrieval
  │    lexical(BM25) + vector -> RRF -> one rerank -> evidence
  └─ 长文档定位、跨章节推理、比较/汇总 -> PageIndex Retrieval
       document routing -> tree navigation -> optional hybrid supplement -> evidence

Unified Evidence Schema
  -> source identity
  -> document/node/chunk position
  -> lexical/vector/rerank trace
  -> evidence relation
  -> final answer or explicit no-answer
```

边界原则：

- Hybrid Retrieval 负责通用召回和排序。
- PageIndex 负责文档结构导航和充分性判断。
- AI 质检负责 Claim 拆解、反证策略和 verdict，不再自行实现底层检索。
- Evidence Judge 负责证据关系，粗粒度映射应统一，但允许不同业务保留细分类别。

## 5. 推荐实施顺序

### 第一阶段：恢复真实可信状态

1. 修复 PageIndex `AppError` 导入缺陷并增加失败测试。
2. 增加 SQLite/Chroma/PageIndex 只读一致性检查。
3. 对现有索引做备份方案和重建预演。
4. 对齐真实评测集 ID，建立可用基线。
5. 为测试彻底关闭真实 `.env` 注入。

### 第二阶段：优化 AI 检索

1. 引入中文 trigram FTS + BM25。
2. 使用 RRF 融合词法与向量结果。
3. 合并 AI 质检查询，统一批量 Rerank。
4. 增加无答案阈值、检索 trace 和延迟指标。

### 第三阶段：恢复 PageIndex 的结构优势

1. 增加建树质量门禁。
2. 修复论文合集文章边界和标题层级。
3. 让 `next_search_focus` 真正驱动下一轮检索。
4. 实现文档路由、预算和全局证据 Top-K。
5. 将 PageIndex 补证据统一接入 `RetrievalService`。

### 第四阶段：收敛代码结构

优先拆分 `src/pageindex/service.py` 和 `src/quality/service.py`，但只在前述行为被测试锁定后进行。建议边界：

- `pageindex/indexing.py`
- `pageindex/candidate_search.py`
- `pageindex/reasoning.py`
- `pageindex/evidence.py`
- `retrieval/lexical.py`
- `retrieval/fusion.py`
- `quality/query_planner.py`

## 6. 验收指标

| 维度 | 建议指标 |
|---|---|
| 索引一致性 | SQLite chunk 与 Chroma embedding 覆盖率 100%；metadata 完整率 100% |
| AI 检索 | Recall@5、Recall@10、MRR、nDCG@10、无答案准确率 |
| PageIndex 树 | 根节点比例、最大深度、摘要覆盖率、空标题率 |
| PageIndex 检索 | 文档命中率、节点命中率、证据充分性准确率、平均轮次 |
| 证据质量 | 追溯率 100%；无证据时不输出确定结论 |
| 性能 | p50/p95 延迟、Embedding/Rerank/LLM 调用次数、单次问题成本 |
| 稳定性 | 离线测试不读取真实 `.env`，不调用外部服务 |

## 7. 本次验证记录

- `python -m pytest --collect-only -q`：`350 tests collected`。
- 主检索专项：`29 passed in 4.06s`。
- PageIndex 专项：`83 passed in 63.08s`。
- 全量首错定位：`1 failed, 40 passed`；失败为测试读取真实初始管理员配置。
- SQLite 版本：`3.50.4`；内存验证 FTS5 trigram 可命中“质量检测”。
- 未执行外部 LLM、Embedding、Rerank 调用。
- 未执行索引重建、数据库迁移、依赖安装、Git 操作或业务代码修改。

## 8. 本轮未执行事项

- 未修复上述问题。
- 未重建 SQLite、Chroma 或 PageIndex。
- 未运行真实 LLM PageIndex 质量评测。
- 未进行真实外部 Embedding/Rerank 延迟与费用测试。
- 未提交或推送任何文件。
