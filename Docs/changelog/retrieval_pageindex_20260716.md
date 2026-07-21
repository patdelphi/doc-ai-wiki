# AI 检索与 PageIndex 优化变更记录

## 1. 变更范围

本次变更围绕两条主链路完成结构化收敛：AI 检索负责词法、向量、RRF、单次重排和统一证据轨迹；PageIndex 负责长文档层级结构、文档路由、动态焦点、多轮预算和结构化证据定位。vendor 仅修改 JSON 读取编码兼容性，使其可读取 UTF-8 BOM workspace 文件。

## 2. 核心算法

- 中文词法检索：新建 FTS 使用 Trigram tokenizer；三字及以上使用 BM25，两字查询使用受控标题/词频兜底。
- 混合召回：词法与向量排名通过 RRF 融合，公式为 `sum(1 / (60 + rank))`，不再直接比较异构原始分数。
- 查询规划：每个 Claim 生成字面、实体扩展、逻辑放宽、主题、关键词和反证查询；强约束断言额外生成主体与范围短查询。各查询独立混合检索和 Rerank 后合并，避免长句零召回及拼接查询稀释意图。
- PageIndex：Markdown 标题栈生成层级树，以文档、标题路径和原文范围生成稳定节点 ID；结构通过覆盖率、深度、空节点、孤立节点和追溯率门禁后才能发布。
- 调用预算：单文档最多 6 次 LLM、3 轮；知识库最多 7 次 LLM、3 篇候选文档、8 条证据。预算和调用轨迹写入 debug。
- 统一补充召回：PageIndex 不再维护第二套 FTS/LIKE SQL，统一调用 `RetrievalService.hybrid_search()`。

### 2026-07-21 AI 质检与页面跳转回归修复

- 浏览器登录态恢复仅刷新权限和页面数据，不再选择 AI 质检标签，避免 PageIndex 操作期间被强制跳页。
- 恢复旧版多查询证据召回，并增加强约束主体/范围短查询；“阿胶只有东阿一家有”由零证据提升为 5 条证据，其中包含明确反证。
- 医疗功效证据必须在同一句中同时覆盖 Claim 主体、目标疾病和功效关系；“治疗其他疾病”或“化疗治疗癌症”不再被误标为阿胶治疗癌症的支持证据。
- 真实模型评测使用 Qwen3.7-Plus、Qwen3-Reranker-8B 和真实 SQLite 文档，4 个真实问题全部达到预期结论。
- 目标 worktree 已复制主仓库完整 `.env`。Embedding 连通性通过，但现有 Chroma 1.5.8/Windows 组合存在原生崩溃，真实质检验收暂采用 SQLite 多查询全文检索、Rerank 和 LLM，不把向量链路计入本次通过范围。

## 3. 索引与恢复

### 检索索引

```powershell
python ".aipython/rebuild_retrieval_indexes.py" inspect
python ".aipython/rebuild_retrieval_indexes.py" rebuild
python ".aipython/rebuild_retrieval_indexes.py" rebuild --apply
python ".aipython/rebuild_retrieval_indexes.py" restore --latest
python ".aipython/rebuild_retrieval_indexes.py" restore --latest --apply
```

### PageIndex

```powershell
python ".aipython/rebuild_pageindex.py" inspect
python ".aipython/rebuild_pageindex.py" rebuild
python ".aipython/rebuild_pageindex.py" rebuild --apply
python ".aipython/rebuild_pageindex.py" restore --latest
python ".aipython/rebuild_pageindex.py" restore --latest --apply
```

不带 `--apply` 的重建与恢复命令只输出计划。正式执行前必须停止写入流量、确认外部模型配置、备份目录和恢复命令。

## 4. 兼容性影响

- SQLite 连接统一使用 WAL 与 NORMAL。
- 新建 FTS 为 Trigram；旧数据库不会在应用启动时自动迁移或删除，必须使用重建工具。
- Chroma metadata 增加模型、维度和 `retrieval-v2` 版本指纹；旧向量索引会被一致性报告判为不完整。
- 新建 PageIndex 使用 `structure.normalized.json`；旧 workspace 继续以 `legacy` 状态读取，来源哈希变化时新索引返回 `stale_index`。
- 向量维度不一致时不再在启动阶段无备份自动修复。

## 5. 质量门槛

正式交付门槛为 Recall@5 `>= 0.80`、MRR@10 `>= 0.65`、nDCG@10 `>= 0.70`、Node Hit@5 `>= 0.80`、拒答准确率 `>= 0.90`、引用可追溯率 `100%`。

## 6. 正式执行结果

- 已安装并执行 Ruff 0.15.21；历史格式型 E501/I001 和旧 UI 未使用变量使用明确基线配置，F821/F401 等有效检查继续启用。
- 已验证 LLM、Qwen3-Embedding-8B 和 Qwen3-Reranker-8B；50 条真实运行 Rerank 覆盖率 1.0，降级样例 0。
- 已正式重建检索索引：SQLite/FTS/Chroma 均为 4207 条，缺失向量指纹 0，`consistent=true`。
- 已正式重建两个 Markdown PageIndex：352/953 个节点，最大深度 4/6，追溯率与源覆盖率均为 1.0。
- Markdown PageIndex 改为本地确定性标题树，避免 vendor 对数百节点并发调用 LLM；PDF 仍使用 vendor 流程。
- 已事务化回填历史追溯字段：1164 个章节、4206 个业务 chunk，ID 和内容不变；向量返回前以 SQLite 刷新追溯元数据。
- 已修复 PageIndex 中文长短语拆解，`抗贫血研究` 可同时生成 `抗贫血` 核心词并命中真实节点。
- 已生成候选对齐回归集和真实评测报告，但相关性门槛未通过；当前标签来自旧索引自动候选，不是独立人工金标。
- 已完成检索与 PageIndex 恢复 dry-run；没有实际回滚已验证活动索引。
- 未执行 Git commit、push、pull、merge、部署或生产环境操作。

## 7. 本地验证结果

- Mypy：`Success: no issues found in 18 source files`。历史动态服务层和第三方边界按模块显式豁免，新建算法与重建模块继续参与检查。
- 完整测试：`390 passed, 6 warnings in 204.32s`；警告均来自 PyPDF2/SWIG 第三方弃用提示。
- 构建：成功生成 `doc_ai_wiki-0.6.tar.gz` 和 `doc_ai_wiki-0.6-py3-none-any.whl`。
- Ruff：`python -m ruff check src tests .aipython` 通过。
- 发现并修复了三个既有安全回归：向量维度冲突时启动自动删库、匿名文档管理/检索、无 AI 质检菜单权限读取历史。
- 文本格式复核：本次 Markdown、Python 与 CI YAML 保持 UTF-8 BOM + CRLF；`pyproject.toml` 因 TOML 解析器不接受 BOM，采用 UTF-8 无 BOM + CRLF 的兼容性例外。
- 最终完整测试 `390 passed`；`compileall` 通过。

## 8. 备份与残余风险

- 检索备份：`index/backups/retrieval/20260716T125413Z`。
- PageIndex 备份：`index/backups/pageindex/20260716T132247Z`。
- 追溯字段备份：`index/backups/traceability/20260716T134645Z/app.db`。
- 失败 staging 与 previous 目录仍保留，未在未确认的情况下清理。
- 50 条检索候选回归：Recall@5 0.14、MRR@10 0.1002、nDCG@10 0.1144；需人工重标后才能作为正式质量判断。
- 55 条 PageIndex 样例仍引用虚构 ID；Node Hit@5 与拒答准确率未伪造、未宣称通过。

## 9. P0 正确性与质量门禁修复

### 9.1 Rerank 降级可观测

- OpenAI 兼容和 DashScope Rerank 客户端不再吞掉 HTTP、连接、超时或无有效结果异常。
- 异常统一交给 `RetrievalService`，保留 RRF 候选顺序并写入 `degraded_reason=rerank_unavailable`。
- 单候选和空候选仍直接返回，不产生无意义外部调用。

### 9.2 授权知识库全局排序

- 新增统一知识库范围语义：`None` 表示无限制，空集合表示显式无权限，单值与多值冲突直接拒绝。
- SQLite FTS/短词检索使用参数化 `IN`；Chroma 使用 `$in`，与文档过滤并存时使用 `$and`。
- 受限用户未选择单库时只执行一次授权集合检索，不再按知识库 ID 逐库截断；Embedding、RRF 和 Rerank 均在全局候选上执行一次。
- 向量结果的 SQLite 元数据回填使用同一授权范围，防止历史向量元数据绕过权限事实源。

### 9.3 Mypy 门禁恢复

- 删除 `src.retrieval.service` 和 `src.retrieval.vector_store` 的精确 `ignore_errors`。
- 新增配置回归测试，禁止重新豁免上述模块或新增检索/PageIndex目录通配豁免。
- 当前 Mypy 命令真实检查 19 个源文件并通过。

### 9.4 最新本地验收

- 聚焦回归：63 项通过。
- Ruff：`python -m ruff check src tests .aipython` 通过。
- Mypy：`Success: no issues found in 19 source files`。
- 完整测试：`402 passed, 6 warnings in 196.36s`；警告均为 PyPDF2/SWIG 第三方弃用提示。
- build：sdist 与 wheel 构建成功；compileall 通过。
- 本轮未调用外部模型 API，未执行索引重建、数据库迁移、部署、commit、push、merge 或 pull。

## 10. P1 第一批 UI 死代码治理

- 删除 `src/ui/pages.py` 中重复的 `_has_tab_access()`，权限判断只保留一个实现。
- 删除 21 个无用导入，以及 159 个无用局部赋值或组件字典读取；`pages.py` 净减少 189 行。
- 测试不再依赖 `pages.py` 对 CSS 和知识库 helper 的历史重导出，改为从真实所属模块导入。
- 删除 `src/auth/service.py` 中没有参与权限判断的冗余查询，以及 `test_ui.py` 中未使用的组件值列表。
- `src/ui/pages.py`、`tests/unit/test_ui.py`、`src/auth/service.py` 不再豁免 Ruff `F401/F841`。
- 新增 AST 与配置门禁测试，防止重复权限 helper 和静态检查豁免回归。
- 最终验收：Ruff、Mypy、build、compileall 通过；完整测试 `404 passed, 6 warnings in 200.22s`。

## 11. P1 第二批知识库检索页处理器迁移

- 将检索执行、分页、结果选择、详情、重置和导出等九个处理器迁入现有 `src/ui/search_page.py`，未新增平行 Controller 或兼容层。
- `src/ui/pages.py` 仅通过 `partial` 注入 RetrievalService、权限解析和导出回调，并用 `update_wrapper` 保持 Gradio 回调名称稳定。
- 删除 `build_ui()` 中九个旧实现；跨页面的 `change_search_knowledge_base_ui()` 继续保留在总装配层。
- 新增十项检索页直接单测和一项 AST 门禁，覆盖空查询、权限、知识库范围、异常、分页、选择、详情和导出。
- 本批次 `pages.py` 净减少 149 行；聚焦回归 `76 passed, 6 warnings`。
- 最终验收：Ruff 通过；Mypy 19 个目标文件通过；完整测试 `415 passed, 6 warnings in 191.24s`；sdist、wheel 和 compileall 通过。
- 本批次未调用外部模型 API，未重建索引，未执行数据库迁移、部署或 push。

## 12. P1 第三批兼容债务与 Ruff 范围治理

- 将 `H7/M3/C5 修复` 等无法独立理解的历史标签改为说明路径安全、Top-K 前权限过滤、向量元数据和空输入保护原因的注释。
- 新增 `Docs/optimization-plan/legacy_compatibility_retirement_20260717.md`，为认证、数据库、默认库文档、Chroma、PageIndex 和归档迁移脚本记录删除条件及 1.0.0 评审截止点。
- 修复 `Docs/migrations/_apply_auth.py` 的 Ruff E402；归档脚本仍禁止执行，不转换为正式迁移入口。
- CI 与 PR 模板的 Ruff 命令扩展为 `python -m ruff check src tests .aipython Docs/migrations`，并增加门禁测试防止范围回退。
- 最终验收：扩展 Ruff 通过；Mypy 19 个目标文件通过；完整测试 `417 passed, 6 warnings in 187.47s`；sdist、wheel 和 compileall 通过。
- 本批次未执行归档迁移脚本、外部 API、索引重建、数据库迁移、部署、commit 或 push。

## 13. P1 第四批 PageIndex 历史导出职责迁移

- 新增 `src/pageindex/history_export.py`，集中历史 SQLite 行解析、结构化回答兼容和 Markdown 格式化。
- `PageIndexService` 的历史 SQL、范围校验、写入和七个公开查询/导出方法保持原签名；内部改为调用两个纯函数。
- 删除服务类中八个无状态私有方法，并增加 AST 门禁，防止历史导出格式化职责回流。
- 新增四项直接单测，覆盖合法/损坏 JSON、JSON/Python dict 回答、自定义字段、空回答、空证据和 Question Plan 类型。
- `service.py` 从 2716 行降至 2542 行，方法数从 96 降至 88；新模块 166 行，生产代码合计净减少 8 行。
- 最终验收：扩展 Ruff 通过；Mypy `20` 个目标文件通过；完整测试 `422 passed, 6 warnings in 214.90s`；sdist、wheel 和 compileall 通过。
- 本批次未调用外部模型 API，未执行索引重建、数据库迁移、部署、commit 或 push。

## 14. P1 第五批 PageIndex 持久化职责迁移

- 新增 `src/pageindex/index_repository.py`，单一仓储负责 PageIndex 表初始化、索引记录和问答历史持久化。
- `PageIndexService` 保留公开接口、参数校验、业务错误、工作区、检索编排和历史导出；PageIndex 自有表 SQL 已全部迁出。
- 删除 `_get_index_record()`、`_list_index_records()`、`_ensure_tables()` 和历史兼容列 helper，不保留生产兼容包装层。
- 九个仓储入口统一使用项目 SQLite 连接/事务，并将数据库失败转换为带 `reason` 的 `DatabaseAppError`。
- `history_export.parse_history_rows()` 改为接受普通映射序列，导出模块不再要求 SQLite Row。
- 新增十二项仓储直接测试、普通字典解析测试、服务仓储委托测试和 AST/源码职责门禁；聚焦回归 `98 passed, 6 warnings`。
- `service.py` 从 2542 行、88 个方法降至 2354 行、84 个方法；新仓储为 289 行、11 个方法。生产代码合计增加 101 行，原因是补齐显式仓储接口和所有数据库入口的结构化异常处理；未增加 Repository 基类、Factory、额外配置或平行服务层。
- 最终验收：扩展 Ruff 通过；Mypy `21` 个目标文件通过；完整测试 `437 passed, 6 warnings in 198.70s`；sdist、wheel 和 compileall 通过。
- 本批次未调用外部模型 API，未执行正式数据库迁移、索引重建、部署、commit 或 push。

## 15. P1 第六批 PageIndex 确定性树检索职责迁移

- 新增 `src/pageindex/tree_retriever.py`，集中树展开、节点位置、评分、前置惩罚、候选构造、交叉引用、候选合并和调试字段。
- `PageIndexService._build_tree_candidates()` 收敛为问题词与 vendor 原文 loader 适配，不再实现遍历、评分、排序或候选字典构造。
- 删除九个无状态服务方法和两套重复树展开实现；所有调用点直接使用唯一算法模块，不保留兼容包装层。
- 新增八项算法直接测试和一项 AST/依赖职责门禁；服务交叉引用测试改用模块级入口。
- 修复实施中测试发现的行号定位键映射错误，并通过聚焦回归确认 `page`、`line_num` 和空位置兼容。
- `service.py` 从 2354 行、84 个方法降至 2165 行、75 个方法；新模块 189 行，生产代码合计保持 2354 行。
- 最终验收：扩展 Ruff 通过；CI 范围 Mypy `22` 个源文件通过；完整测试 `446 passed, 6 warnings in 215.49s`；sdist、wheel 和 compileall 通过。
- 整个 `src` 的扩大 Mypy 检查仍有既有 UI 动态类型和 PyYAML stub 问题；本批未顺手修改，继续纳入逐模块门禁治理。
- 本批次未调用外部模型 API，未执行数据库迁移、索引重建、部署、commit 或 push。

## 16. P1 第七批 PageIndex 最终回答编排职责迁移

- 新增 `src/pageindex/answer_orchestrator.py`，集中 Question Plan、证据分类、本地保守回答和最终 LLM 回答载荷生成。
- `PageIndexService` 直接持有唯一编排器，不保留同名包装方法或平行兼容层。
- 删除十四个回答相关方法和两个无生产入口的旧单轮树检索方法，共十六个服务方法。
- 新增八项编排器直接测试和职责门禁，覆盖预算、模板、降级、证据分类、本地回答和 LLM 载荷。
- `service.py` 从 2165 行、75 个方法降至 1834 行、59 个方法；新模块为 172 行、5 个类方法；两文件合计净减少 159 行。
- 最终验收：聚焦回归 `75 passed, 6 warnings`；扩展 Ruff 通过；CI 范围 Mypy `23` 个源文件通过；完整测试 `455 passed, 6 warnings in 194.02s`；sdist、wheel 和 compileall 通过。
- 本批次未调用外部模型 API，未执行数据库迁移、索引重建、部署、commit 或 push。

## 17. 知识库管理页实时状态修复

- 修复知识库管理页沿用 Gradio 服务启动快照的问题：登录、密码回车登录、浏览器会话恢复和退出登录现在都会同步刷新或清空整页 40 个状态输出。
- 修复切换知识库时遗漏登录态的问题，避免合法管理员被当作无权限状态并将文档、数据库、质检和分页结果覆盖为 0。
- 修复长时间入库期间浏览器登录态重复恢复导致页签跳转的问题：首次恢复仍默认进入 AI 质检，后续恢复只刷新权限与数据，不再覆盖用户当前所在页签。
- 新增启动后写入文档的回归测试，覆盖认证恢复、数据库统计、文档列表、三条认证入口输出绑定和知识库切换。
- 新增重复会话恢复回归测试；验证结果：聚焦回归 `4 passed, 6 warnings`，认证/恢复测试集 `7 passed, 57 deselected, 6 warnings`，Ruff 通过；前序完整 UI 与入库 API 回归 `64 passed, 6 warnings in 85.64s`。本次完整重跑因环境耗时超过 180 秒被终止，未产生测试失败。
- 本次未调用外部 API，未执行数据库迁移、索引重建、部署、commit、push、merge 或 pull。

## 18. Windows 向量索引与页面状态最终修复

- 移除运行时对 Chroma/HNSW 原生库的依赖，`VectorStore` 改为 NumPy 精确余弦索引，使用原子替换的 `vectors.npz` 持久化文件；保留 `CHROMA_PERSIST_DIR` 配置名以兼容现有环境。
- 增加 120 条以上批量写入、重开持久化、维度冲突、知识库过滤、SQLite 全量重建和元数据检查回归测试。
- 用完整 `.env` 的 Qwen3-Embedding-8B 重建正式索引：2 个文档、4516 个 chunk、4516 条向量、1024 维、元数据缺失 0。
- 删除失败 Chroma 备份、staging 目录、旧 Chroma 数据库和无用 `.venv`；保留 `index/app.db`、PageIndex 数据及新的 `index/chroma/vectors.npz`。在 SQLite 事务中删除 `chunk_fts__staging` 及其影子表，完整性检查为 `ok`。
- 真实 AI 质检 4/4 通过：补血作用 `verified`；感冒、东阿唯一、癌症均正确拒答/驳回。
- 验证：向量与启动测试 `7 + 12 + 3` 通过；AI 质检、质量门禁、UI 回归 `95 passed`；Ruff 通过。未执行 commit、push、部署。

## 19. PageIndex 真实问答质量收口

- 修复多文档 PageIndex 问答共享固定 3 轮预算的问题：现在按参与文档数分配轮次与 LLM 调用额度，避免第二篇文档或最终回答被误判为预算耗尽。
- 修复信息抽取问题套用真假命题模板的问题；“有哪些/哪些作用”等问题现在输出可提取要点、来源和不确定边界，不再错误输出“当前证据不支持”。
- 限制最终回答 Prompt 中每条证据正文长度，保留标题、位置、文档和定位字段，降低长文档导致的模型超时与退化回答。
- 真实 PageIndex 4 问验证：补血相关作用可分层回答并标注复方/机制边界；感冒问题明确不支持直接治疗；“只有东阿一家”明确驳回；癌症问题区分辅助作用与不能替代正规治疗。
- PageIndex 聚焦测试 `66 passed`，Ruff 与 Mypy 通过；AI 质检真实 4/4 结果保持通过。

## 20. 正式库质检结果落库与医疗证据门禁

- 真实 AI 质检不再只在临时备份库验证；4 条验收问题已直接写入正式 `index/app.db`，每条保留 Claim、证据明细和判定结果。
- 修复同主题论文被 LLM 误当作医疗直接证据的问题：治疗目标未被直接证据覆盖时，最终结果至少为 `needs_review`；发现直接矛盾证据时判为 `rejected`。
- 正式库最新 4 条结果为：补血 `verified`、感冒 `needs_review`、东阿唯一 `rejected`、癌症 `needs_review`。
- 回归验证：质量聚焦 `33 passed`，完整测试 `456 passed, 6 warnings`；正式库核对为 2 个文档、4516 个 chunks、2 个 PageIndex 索引、13 条 PageIndex 历史、9 条质检和 9 条 Claim。

## 21. AI 质检同题证据对齐

- 为癌症、肿瘤、抗肿瘤、感冒、贫血等医疗目标增加主题别名召回，并给医疗目标查询分配更大的候选窗口。
- 证据排序增加“主体与医疗目标同句命中”优先级；复方阿胶浆、阿胶颗粒等具体制剂证据不会再冒充单体阿胶的直接治疗证据。
- 与 PageIndex 同题“阿胶能治疗癌症吗？”复核：AI 质检现在命中肿瘤相关贫血、化疗和“抗肿瘤”节点，判定为高风险 `needs_review`，5 条证据全部标记 `insufficient`。
- 新结果已写入正式库，服务重启后 7860 页面与 8000 API 均返回 200；质量聚焦、Ruff、Mypy 均通过。
