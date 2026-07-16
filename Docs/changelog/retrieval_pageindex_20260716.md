# AI 检索与 PageIndex 优化变更记录

## 1. 变更范围

本次变更围绕两条主链路完成结构化收敛：AI 检索负责词法、向量、RRF、单次重排和统一证据轨迹；PageIndex 负责长文档层级结构、文档路由、动态焦点、多轮预算和结构化证据定位。vendor 仅修改 JSON 读取编码兼容性，使其可读取 UTF-8 BOM workspace 文件。

## 2. 核心算法

- 中文词法检索：新建 FTS 使用 Trigram tokenizer；三字及以上使用 BM25，两字查询使用受控标题/词频兜底。
- 混合召回：词法与向量排名通过 RRF 融合，公式为 `sum(1 / (60 + rank))`，不再直接比较异构原始分数。
- 查询规划：每个 Claim 最多生成字面、语义归一、反证探测三类查询；候选合并后最多执行一次 Rerank。
- PageIndex：Markdown 标题栈生成层级树，以文档、标题路径和原文范围生成稳定节点 ID；结构通过覆盖率、深度、空节点、孤立节点和追溯率门禁后才能发布。
- 调用预算：单文档最多 6 次 LLM、3 轮；知识库最多 7 次 LLM、3 篇候选文档、8 条证据。预算和调用轨迹写入 debug。
- 统一补充召回：PageIndex 不再维护第二套 FTS/LIKE SQL，统一调用 `RetrievalService.hybrid_search()`。

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
