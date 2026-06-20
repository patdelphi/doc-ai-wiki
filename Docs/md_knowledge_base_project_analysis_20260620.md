# 基于 Markdown 文档的知识库项目现状评估与改进建议

> **项目**：doc-ai-wiki  
> **评估对象**：作为基于 Markdown 文档的中文知识库与 AI 质检系统，当前项目是否满足需求  
> **评估日期**：2026-06-20  
> **评估范围**：项目文档、源码结构、核心服务代码、测试目录、PageIndex 评测报告、Git 状态  
> **结论口径**：面向内部研发决策与后续迭代规划

---

## 1. 执行摘要

当前项目已经形成一个较完整的本地知识库工作台雏形，具备 Markdown / JSON 文档入库、SQLite 元数据与 FTS5 全文索引、ChromaDB 向量索引、全文 / 向量 / 混合检索、AI 质检、规则校验、人工审核、多知识库管理、用户权限控制、PageIndex 长文档增强等能力。

从“能否作为 Markdown 文档知识库 MVP 使用”的角度看，项目已经基本可用；从“能否作为高可信、可验收、可长期维护的证据型知识库系统”的角度看，仍存在关键短板，主要集中在 Markdown 语义分块、元数据与出处追溯、实体归一、质检 verdict 体系、评测闭环、验收状态同步和运行期数据管理等方面。

综合判断：

| 评估维度 | 当前判断 | 说明 |
|---|---|---|
| 本地 Demo / 内部试用 | 基本可用 | 主链路已打通，页面和接口均有实现基础 |
| Markdown 知识库 MVP | 基本满足 | 可入库、可检索、可质检、可审核，但需补正式验收 |
| 高可信证据型知识库 | 部分满足 | 证据追溯和评测不足，误判风险仍需控制 |
| 生产级部署 | 暂不建议直接上生产 | 需要测试环境、索引资产、监控、验收报告和数据治理收口 |

建议总体定位为：

> 项目已经具备可运行 MVP 雏形，适合作为后续扩展的基础；下一阶段应优先补齐 Markdown 语义分块、元数据追溯、实体归一、verdict 标准化和自动化评测，而不是继续堆叠新功能。

---

## 2. 评估依据

### 2.1 已检查的核心文档

| 文档 | 主要用途 | 评估发现 |
|---|---|---|
| `Docs/中文知识库系统MVP实施方案_v2.1_20260430.MD` | MVP 范围与目标 | 明确首版只解决 Markdown 入库、检索证据、claim 质检、人工审核 4 个问题 |
| `Docs/design.MD` | 详细设计 | 对模块边界、数据表、流程、事务、异常、缓存、测试均有设计 |
| `Docs/tasks.MD` | 任务清单 | 任务分期清楚，但部分设计目标与当前实现仍有差距 |
| `Docs/acceptance.MD` | 验收清单 | 多数功能验收项仍未勾选，说明验收状态未同步 |
| `Docs/pageindex-evaluation-20260618.md` | PageIndex 离线评测 | 10 个问题均返回证据，未发现跨文档证据混入，但样本量较小 |
| `readme.md` | 当前能力说明 | 说明项目已扩展到多知识库、多用户、权限、PageIndex 等较完整工作台 |

### 2.2 已检查的核心代码

| 模块 | 代表文件 | 主要发现 |
|---|---|---|
| 数据库 Schema | `src/db/schema.py` | 核心表基本齐全，支持文档、分块、FTS、质检、规则、审核、多知识库 |
| 文档入库 | `src/ingest/service.py` | 已实现文档注册、hash、章节解析、分块、FTS、向量写入、重建、质量检查 |
| 元数据 | `src/metadata/extractor.py`、`src/metadata/sections.py` | 当前元数据和章节解析较轻量，缺少行号、页码、稳定标题路径等追溯信息 |
| 分块 | `src/chunking/splitter.py` | 当前仍是固定字符长度切块，与设计中“禁止简单按固定字数粗暴截断”不一致 |
| 检索 | `src/retrieval/service.py`、`src/retrieval/vector_store.py` | 已有 FTS5、LIKE 兜底、ChromaDB、混合检索、知识库过滤和上下文扩展 |
| 质检 | `src/quality/service.py` | 已串联 claim、规则、检索、证据、LLM/启发式、持久化，但 verdict 体系需统一 |
| PageIndex | `src/pageindex/service.py` | 已集成本地 PageIndex，支持结构检索、LLM 语义树推理、RAG/FTS 补证据 |
| API | `src/app.py` | 已有 `/ingest`、`/search`、`/quality`、`/review`、`/knowledge-bases` 等接口 |
| 测试 | `tests/` | 测试覆盖面较广；当前环境可收集 264 条测试，单元与集成测试已可分组验证 |

### 2.3 Git 与运行环境状态

当前 Git 状态显示：

```text
## dev...origin/dev
?? Docs/md_knowledge_base_project_analysis_20260620.md
?? index/
```

说明当前已跟踪代码基本无修改，但本评估文档自身和 `index/` 运行期目录未跟踪。根据 `readme.md` 的说明，`index/app.db`、`index/chroma` 属于本地运行期数据，不建议直接同步到远端仓库；复核后确认 `.gitignore` 已覆盖数据库与 Chroma，但此前未覆盖 `index/pageindex_workspace/`。

复核时当前工具执行环境已具备命令入口：

```text
python --version -> Python 3.13.13
pytest --version -> pytest 9.0.3
python -m pytest --collect-only -q -> 264 tests collected
```

后续已完成验证：`tests/unit` 235 条通过，`tests/integration/test_app.py` 29 条通过；P1 分块升级后完整 `python -m pytest tests -q` 267 条通过。完整测试仍建议在 CI 中持续执行，以避免单机环境和耗时差异影响判断。

---

## 3. 当前能力符合度评估

### 3.1 Markdown 文档入库

当前状态：**基本满足 MVP**。

已具备能力：

- 从输入路径读取文档
- 校验路径在允许的 `Input` 根目录下
- 计算文档 hash
- 识别重复文档并跳过
- 识别文档更新并重建
- 写入 `documents`
- 解析 Markdown 标题为 `document_sections`
- 生成 `chunks`
- 写入 `chunk_fts`
- 写入 ChromaDB 向量索引
- 支持重建全文索引和向量索引
- 支持入库质量检查和 CSV 导出

主要差距：

- Markdown 解析较粗，仅按标题切章节
- 分块仍是固定字符长度切分
- 缺少 line range、page_no、heading_path、chunk_type 等强追溯字段
- 对表格、列表、引用块、代码块、脚注等 Markdown 结构缺少专门处理
- JSON 文档也被纳入支持范围，但 MVP 原始目标是优先 Markdown，应明确是否继续扩展 JSON 为正式输入类型

判断：当前能完成基础入库，但还不够“高质量入库”。

---

### 3.2 全文检索、向量检索与混合检索

当前状态：**基本满足 MVP，但排序和评测不足**。

已具备能力：

- SQLite FTS5 全文检索
- 中文场景下 FTS 失败或无结果时使用 LIKE 兜底
- ChromaDB 向量检索
- 按 `doc_uid` 过滤
- 按 `knowledge_base_id` 过滤
- 全文与向量结果按 `chunk_id` 合并去重
- 支持可选 reranker
- 支持 chunk detail 查询
- 支持邻接 chunk 和章节上下文扩展

主要差距：

- 未启用 reranker 时，混合检索排序逻辑偏简单
- FTS 与向量分数缺少统一归一化
- `score = 1 - distance` 对不同距离度量不一定稳定
- LIKE 兜底可能带来噪声召回
- 缺少正式 Top-5 / Top-10 命中率评测结果
- 缺少对不同文档类型、长短文档、术语问法变化的召回对比

判断：检索功能可用，但还需要评测驱动优化。

---

### 3.3 AI 质检能力

当前状态：**主链路已打通，可信度仍需增强**。

已具备能力：

- 输入文本校验
- 2000 字长度限制
- claim 拆分
- 质检模板加载
- 规则匹配
- 证据检索
- 证据上下文扩展
- LLM 可用时调用模型
- LLM 不可用时走规则与启发式降级
- 结构化结果持久化
- rule_hits 持久化
- 最近结果与历史查询
- 低置信 / 证据不足倾向保守处理

主要差距：

- 当前代码主要使用 `verified`、`needs_review`、`rejected`，与设计文档中的 `verified`、`contradicted`、`suspected`、`insufficient_evidence`、`manual_review_required` 不一致
- 证据相关不等于证据支持，当前仍存在“检索到相关证据即较容易 verified”的风险
- 反证、弱证据、范围扩大、绝对化表述、唯一性表述等复杂 claim 还需要更多评测验证
- 缺少正式 claim 评测集和准确率指标
- 高风险专业内容的规则包和保守策略还需强化

判断：适合辅助质检，不应直接作为最终判断；需要人工审核闭环和评测约束。

---

### 3.4 人工审核能力

当前状态：**基本满足 MVP**。

已具备能力：

- `review_records` 表
- `quality_claims` 与审核记录关联
- 审核提交接口
- 审核列表接口
- 保留原始模型输出和人工审核结论的设计
- 按知识库过滤审核候选与历史
- UI 测试中覆盖审核工作区和历史回看

主要差距：

- 需要确认 UI 实际操作流程是否已经完整跑通
- `acceptance.MD` 中审核相关功能仍未勾选
- 审核结果如何反哺规则、模板、检索权重，目前仍是扩展位

判断：MVP 审核闭环基本具备，但验收状态需要同步。

---

### 3.5 多知识库与权限体系

当前状态：**超过原始 MVP 要求，完成度较高**。

已具备能力：

- `knowledge_bases` 表
- 文档绑定 `knowledge_base_id`
- 检索、质检、审核按知识库过滤
- 用户注册、登录、退出
- 管理员和普通用户权限区分
- 菜单权限和知识库权限
- 对象级访问控制
- 零权限用户默认入口页

主要风险：

- 权限系统增加了项目复杂度，需要持续用测试保障
- 多知识库隔离依赖所有查询路径都正确传递 `knowledge_base_id`
- PageIndex、向量检索、历史记录等增强模块都必须保持一致隔离

判断：这是项目亮点，但也需要持续回归测试。

---

### 3.6 PageIndex 长文档增强

当前状态：**实验性可用，不应替代主链路验收**。

已具备能力：

- 本地集成 `vendor/pageindex`
- 支持 Markdown / PDF 构建 PageIndex
- 支持知识库和文档范围隔离
- 支持读取树结构
- 支持问题分析、候选节点打分、LLM 语义树推理
- 支持本地关键词降级
- 支持当前文档内 RAG/FTS 补证据
- 支持问答历史保存和导出

已有评测结果：

- 10/10 问题均返回证据
- 10/10 问题均补充当前文档内 RAG/FTS 原文证据
- 未发现跨文档证据混入
- 已降低标题、课题组、CIP、参考文献等前置泛化节点权重

主要差距：

- 样本量只有 10 问，不足以作为质量结论
- 离线评测主要验证本地降级链路，不等于真实 LLM 效果
- 论文合集类文档仍需文章边界识别
- 需要检查 PageIndex 主证据与 RAG/FTS 补充证据是否稳定合并，而不是被覆盖
- 缺少跨文档 PageIndex 问答策略

判断：PageIndex 是值得保留的增强方向，但当前应定位为长文档辅助检索模块，而不是主检索的替代品。

---

## 4. 主要问题清单

### 4.1 P0 问题：测试与验收报告需要同步

复核后，当前工具环境已经可以运行 Python 与 pytest：

```bash
python --version
pytest --version
python -m pytest --collect-only -q
python -m pytest tests/unit -q
python -m pytest tests/integration/test_app.py -q
```

当前验证结果：

- `python --version` 返回 `Python 3.13.13`
- `pytest --version` 返回 `pytest 9.0.3`
- `python -m pytest --collect-only -q` 成功收集 264 条测试
- `python -m pytest tests/unit -q` 结果 235 passed
- `python -m pytest tests/integration/test_app.py -q` 结果 29 passed
- `python -m pytest tests -q` 结果 267 passed

影响：

- 原“测试环境无法验证”的判断已经过期
- 需要将最新测试结果写入测试报告和验收报告
- 需要把验收清单与实际测试状态同步

建议优先级：**最高**。

---

### 4.2 P0 问题：验收清单未同步

`Docs/acceptance.MD` 中大量功能项仍未勾选，但 README 和代码显示很多能力已经实现。

影响：

- 项目状态不可控
- 难以判断是否达到 MVP
- 后续交接、验收、客户演示时容易产生争议

建议：

- 新增 `Docs/acceptance_report_20260620.md`
- 对每项验收标准给出：已通过 / 部分通过 / 未通过 / 未验证
- 附测试命令、测试结果和证据文件

---

### 4.3 P0 问题：运行期索引目录需要继续收口

当前 Git 状态存在：

```text
?? index/
```

而 README 说明 `index/app.db`、`index/chroma` 不建议直接同步。复核发现 `.gitignore` 已忽略数据库和 Chroma，但此前未忽略 `index/pageindex_workspace/`，因此 PageIndex JSON 仍可能显示为未跟踪。

影响：

- 可能误提交大体积运行期数据
- 可能泄露本地知识库数据
- ChromaDB 与 SQLite 状态可能在不同机器上不一致

建议：

- 明确 `.gitignore` 对 `index/` 各类运行期产物的边界
- 忽略 `index/pageindex_workspace/`
- 若需要保存样例数据，应转为 fixture 或导出脚本
- 保留可重建流程，而不是提交运行期数据库

---

### 4.4 P1 问题：固定长度分块不适合可信知识库

当前 `split_text` 是 500 字符 + 100 重叠的固定切分。

影响：

- 语义边界被截断
- 表格、引用、条文可能被切断
- 检索结果证据不完整
- 向量召回质量下降
- 质检证据可能不准确

建议：

将分块升级为 Markdown 结构感知分块：

```text
Markdown 解析
→ 标题树
→ 段落 / 列表 / 表格 / 引用块 / 代码块识别
→ 语义块合并
→ 超长块保守二次切分
→ 保存 heading_path、line range、chunk_type
```

---

### 4.5 P1 问题：元数据和出处追溯不足

当前 Markdown 元数据主要来自第一个标题和文件名。

缺少：

- 页码
- 起止行号
- 稳定章节路径
- 原始 span id
- 作者、来源、版本
- 原文引用范围
- chunk 类型

影响：

- 证据可追溯率不足
- 质检结果难以人工复核
- 多版本对照无法可靠扩展
- 客户或业务方难以信任结果

建议：

在 `documents`、`document_sections`、`chunks` 中补充或派生以下字段：

```text
heading_path
source_start_line
source_end_line
page_no
chunk_type
content_hash
source_anchor
```

---

### 4.6 P1 问题：实体归一尚未真正落地

设计文档要求最小实体归一，但当前实现中未看到完整词表和归一流程。

影响：

- 别名、异体字、繁简、同义词召回不稳定
- 中文长文档问法变化时召回下降
- PageIndex 与普通 RAG 的关键词提取需要大量硬编码补丁

建议：

补齐：

```text
data/entities/
├── term_dictionary.json
├── aliases.json
├── variant_map.json
└── domain_terms.json
```

并在入库、检索、质检三处复用。

---

### 4.7 P1 问题：verdict 体系需要统一

当前代码与文档使用不同 verdict 枚举。

建议统一为：

```text
verified
contradicted
suspected
insufficient_evidence
manual_review_required
```

或明确保留当前简化版本：

```text
verified
needs_review
rejected
```

但不建议文档、代码、UI、报表长期不一致。

---

### 4.8 P2 问题：正式评测集不足

MVP 文档要求：

- 检索测试集：50 条问题与标准证据
- claim 测试集：50 条待核验陈述与人工标注结果
- 规则测试集：30 条命中样例与 30 条非命中样例
- 跨领域样例集：10 条

当前已有 PageIndex 10 问评测，但不足以覆盖主链路。

建议新增：

```text
tests/evaluation/
├── retrieval_cases.jsonl
├── claim_check_cases.jsonl
├── rule_cases.jsonl
└── pageindex_cases.jsonl
```

并输出固定指标。

---

## 5. 风险评估

| 风险 | 等级 | 说明 | 建议 |
|---|---|---|---|
| 测试报告未同步 | 中高 | 当前测试可运行，但报告与验收清单仍需同步 | 记录单元、集成、收集结果并更新验收报告 |
| 固定长度分块 | 高 | 直接影响检索和证据质量 | 升级 Markdown 结构感知分块 |
| 证据追溯不足 | 高 | 无法满足高可信质检 | 增加行号、标题路径、chunk 类型 |
| verdict 不一致 | 中高 | 影响 API、UI、评测、审核统计 | 统一内部枚举和迁移映射 |
| 实体归一缺失 | 中高 | 中文知识库召回不稳定 | 建实体词表与 query expansion |
| 评测集不足 | 中高 | 无法判断优化有效性 | 建正式评测集和自动化指标 |
| PageIndex 仍偏实验 | 中 | 适合增强，不宜作为唯一依据 | 与普通 RAG 合并证据并评测 |
| 运行期数据未治理 | 中 | 可能误提交、泄露或状态不一致 | 明确 `.gitignore` 和数据重建流程 |
| 权限系统复杂度 | 中 | 多知识库、多用户增加回归风险 | 持续保留对象级权限测试 |

---

## 6. 改进路线建议

### Phase 1：工程与验收收口

目标：明确当前项目真实可用范围。

建议任务：

1. 记录当前 Python / pytest 版本
2. 分组运行单元测试和集成测试
3. 生成测试结果报告
4. 更新 `Docs/acceptance.MD`
5. 新增 `Docs/acceptance_report_20260620.md`
6. 明确 `.gitignore` 对 `index/`、`logs/`、`*.db` 的处理
7. 清理或归档历史运行输出

交付物：

```text
Docs/acceptance_report_20260620.md
Docs/test_report_20260620.md
更新后的 .gitignore
```

---

### Phase 2：Markdown 入库质量升级

目标：从“能入库”升级到“高质量可追溯入库”。

建议任务：

1. 替换固定长度分块器
2. 增加 Markdown 结构解析
3. 增加 heading_path
4. 增加 source_start_line / source_end_line
5. 增加 chunk_type
6. 表格、列表、引用块、代码块单独处理
7. 增加入库质量检查规则

交付物：

```text
src/chunking/markdown_splitter.py
src/metadata/markdown_parser.py
新增或迁移后的 chunk schema
新增分块回归测试
```

---

### Phase 3：检索质量升级

目标：提升证据召回的稳定性和可解释性。

建议任务：

1. 建立 query normalization
2. 接入实体词表和别名扩展
3. 优化全文 / 向量融合排序
4. 增加 rerank 失败降级记录
5. 增加检索 debug 输出
6. 建立 Top-K 评测脚本

交付物：

```text
src/retrieval/query_normalizer.py
src/retrieval/fusion.py
src/retrieval/evaluation.py
tests/evaluation/retrieval_cases.jsonl
```

---

### Phase 4：质检可信度升级

目标：降低错误 verified 的风险。

建议任务：

1. 统一 verdict schema
2. 区分 support / contradict / insufficient / related
3. 强化绝对化、唯一性、否定性 claim 判断
4. 引入证据关系打分
5. 增加无证据、弱证据、反证测试集
6. 低置信和高风险自动进入人工审核

交付物：

```text
src/quality/verdicts.py
src/quality/evidence_judgement.py
tests/evaluation/claim_check_cases.jsonl
质检评测报告
```

---

### Phase 5：PageIndex 与 RAG 融合

目标：让 PageIndex 成为长文档结构增强，而不是孤立模块。

建议任务：

1. 明确普通 RAG 与 PageIndex 的职责边界
2. 合并 PageIndex 节点证据与 RAG/FTS 原文证据
3. 支持论文合集文章边界识别
4. 增加 PageIndex 评测样本到 50 问
5. 支持跨文档 PageIndex 检索策略设计

交付物：

```text
Docs/pageindex_integration_design.md
PageIndex 50 问评测集
PageIndex 与 RAG 融合策略实现
```

---

## 7. 建议验收标准

下一阶段可以按以下标准判断是否从“可用 MVP”进入“可信 MVP”：

| 维度 | 标准 |
|---|---|
| 测试 | `python -m pytest tests` 全部通过 |
| 入库 | 10 份 Markdown 文档入库成功，失败原因可见 |
| 分块 | 每个 chunk 有标题路径、起止行号、chunk 类型 |
| 检索 | 50 条检索样例 Top-5 命中率 >= 80% |
| 质检 | 50 条 claim 样例准确率 >= 80% |
| 证据追溯 | 质检结果证据可追溯率 >= 95% |
| 安全 | 无证据时不输出 verified |
| 审核 | 审核动作可保存、可查询、原始 verdict 不被覆盖 |
| 权限 | 未授权用户无法访问其他知识库的数据 |
| 运行数据 | `index/`、日志、数据库不会误提交 |

---

## 8. 总体建议

当前项目已经完成了从“概念设计”到“可运行系统雏形”的跨越。后续不建议继续优先增加新模块，而应先补齐以下基础质量能力：

1. 测试可运行
2. 验收状态可追踪
3. Markdown 分块可信
4. 元数据和证据追溯可信
5. verdict 和输出 schema 统一
6. 检索与质检有正式评测集
7. 运行期数据治理清晰

只有这些完成后，PageIndex、知识图谱、多版本比对、多模型投票、批量质检等增强能力才有稳定基础。

最终判断：

> 该项目作为基于 Markdown 文档的中文知识库 MVP，已经具备主链路可用性；但作为高可信证据型知识库，还需要围绕分块、元数据、评测、验收和运行数据治理进行一轮工程化收口。下一阶段应优先做质量闭环，而不是扩大功能范围。
