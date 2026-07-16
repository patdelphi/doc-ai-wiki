# AI 检索与 PageIndex 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. 当前未授权 Subagent，因此默认只允许当前会话内串行执行；如需 `superpowers:subagent-driven-development`，必须由用户另行明确批准。所有步骤使用 `- [ ]` 跟踪。

**Goal:** 在项目内完成 AI 检索与 PageIndex 两套流程的结构化修复、安全重建、真实评测和可恢复交付。

> **2026-07-16 执行状态：** Task 1-12 的本地代码、隔离测试、类型检查、构建和文档已完成；Ruff 因本机未安装且未获安装确认未执行。Task 13 的外部服务验证、真实数据库迁移、正式索引重建、50 条真实评测和恢复演练仍需再次确认。

**Architecture:** 先建立测试与数据库安全基线，再实现 Trigram/BM25、RRF、统一向量元数据和单次重排；PageIndex 在其上增加层级树、文档路由、动态搜索焦点和调用预算。所有索引均在临时位置构建，经过一致性与质量门禁后切换。

**Tech Stack:** Python 3.11+、SQLite/FTS5、ChromaDB、FastAPI、Gradio、pytest、项目内 PageIndex vendor、OpenAI 兼容 LLM/Embedding、DashScope 兼容 Rerank。

## Global Constraints

- 先写失败测试，再写最小实现。
- 代码文件开头保留中文程序说明，关键逻辑使用中文注释。
- 所有 API 和外部服务调用必须具有明确异常处理。
- 所有数据库写操作使用事务。
- SQLite 统一设置 `PRAGMA journal_mode=WAL` 和 `PRAGMA synchronous=NORMAL`。
- 新增文本和 Markdown 使用 UTF-8 BOM、CRLF。
- 不进行无关 UI 重构，不引入长期双轨架构。
- 正式外部服务调用、依赖安装、数据库迁移和索引重建必须在执行前再次确认。
- 不自动执行 Git commit、push、pull、merge；每个任务只设置人工审查点。
- 正式指标：Top-5 Recall ≥ 0.80、MRR@10 ≥ 0.65、nDCG@10 ≥ 0.70、Node Hit@5 ≥ 0.80、拒答准确率 ≥ 0.90、引用可追溯率 100%。

---

## 1. 文件结构与职责

### 新增文件

- `src/retrieval/lexical.py`：Trigram/BM25 中文词法检索和两字短词兜底。
- `src/retrieval/fusion.py`：RRF 融合、去重和来源轨迹。
- `src/retrieval/index_state.py`：索引清单、模型指纹和一致性报告。
- `src/retrieval/rebuild.py`：检索索引备份、临时构建、校验、切换和恢复。
- `src/pageindex/structure.py`：Markdown 标题树、vendor 节点增强和树质量门禁。
- `src/pageindex/routing.py`：文档路由、节点搜索预算和调用计数。
- `src/pageindex/rebuild.py`：PageIndex 批量备份、重建、校验、切换和恢复。
- `.aipython/rebuild_retrieval_indexes.py`：检索索引运维 CLI。
- `.aipython/rebuild_pageindex.py`：PageIndex 运维 CLI。
- `.aipython/run_retrieval_evaluation.py`：真实检索与 PageIndex 评测 CLI。
- `tests/unit/test_database_connection.py`：SQLite PRAGMA 回归测试。
- `tests/unit/test_lexical_retrieval.py`：中文词法检索测试。
- `tests/unit/test_retrieval_fusion.py`：RRF 和降级测试。
- `tests/unit/test_index_state.py`：索引一致性与模型指纹测试。
- `tests/unit/test_pageindex_structure.py`：层级树与质量门禁测试。
- `tests/unit/test_pageindex_routing.py`：路由和预算测试。
- `tests/integration/test_retrieval_rebuild.py`：检索索引重建与恢复测试。
- `tests/integration/test_pageindex_rebuild.py`：PageIndex 临时构建与恢复测试。
- `.github/workflows/ci.yml`：项目统一检查。

### 重点修改文件

- `src/db/connection.py`、`src/db/schema.py`：WAL/NORMAL 和新建库 Trigram FTS。
- `src/retrieval/service.py`、`src/retrieval/vector_store.py`：统一检索编排、向量元数据和批量查询。
- `src/quality/service.py`：查询收敛和单次批量 Rerank。
- `src/pageindex/service.py`：层级结构、路由、动态多轮搜索、过期保护和统一召回。
- `src/ui/app.py`、`src/ui/pages.py`：向 PageIndex 注入同一 `RetrievalService`。
- `src/retrieval/evaluation.py`：新增 MRR、nDCG、拒答和轨迹指标。
- `tests/conftest.py`：隔离真实 `.env`。
- `pyproject.toml`：统一 lint、type-check、build 工具配置。

---

### Task 1: 测试隔离、SQLite 安全基线和明确异常修复

**Files:**
- Create: `tests/unit/test_database_connection.py`
- Modify: `tests/conftest.py`
- Modify: `src/db/connection.py`
- Modify: `src/pageindex/service.py`
- Test: `tests/unit/test_auth_service.py`
- Test: `tests/unit/test_pageindex_service.py`

**Interfaces:**
- Consumes: `create_connection(database_path: Path) -> sqlite3.Connection`
- Produces: 每个项目连接都启用外键、WAL、NORMAL；测试默认禁用真实模型配置和初始管理员密码。

- [ ] **Step 1: 写入测试环境隔离失败测试**

```python
def test_test_environment_should_not_expose_initial_admin_password() -> None:
    assert os.environ.get("DOC_AI_WIKI_INITIAL_ADMIN_PASSWORD", "") == ""
    assert os.environ["LLM_PROVIDER"] == "disabled"
    assert os.environ["EMBEDDING_PROVIDER"] == "local"
    assert os.environ["RERANK_ENABLED"] == "false"
```

- [ ] **Step 2: 写入 SQLite PRAGMA 失败测试**

```python
def test_create_connection_should_enable_wal_and_normal(tmp_path: Path) -> None:
    connection = create_connection(tmp_path / "app.db")
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert int(connection.execute("PRAGMA synchronous").fetchone()[0]) == 1
    finally:
        connection.close()
```

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest "tests/unit/test_database_connection.py" "tests/unit/test_auth_service.py::test_auth_service_should_create_disabled_admin_without_default_password" -q`

Expected: PRAGMA 测试失败，且认证测试不再受真实 `.env` 密码影响。

- [ ] **Step 4: 在测试导入前覆盖敏感环境变量**

```python
os.environ["DOC_AI_WIKI_INITIAL_ADMIN_PASSWORD"] = ""
os.environ["LLM_PROVIDER"] = "disabled"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["RERANK_ENABLED"] = "false"
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
```

- [ ] **Step 5: 为 SQLite 连接设置 WAL/NORMAL**

```python
connection.execute("PRAGMA foreign_keys = ON;")
connection.execute("PRAGMA journal_mode = WAL;")
connection.execute("PRAGMA synchronous = NORMAL;")
```

- [ ] **Step 6: 修复 PageIndex 异常类型导入**

```python
from src.common.errors import AppError, DatabaseAppError, NotFoundAppError, ValidationAppError
```

- [ ] **Step 7: 运行聚焦测试**

Run: `python -m pytest "tests/unit/test_database_connection.py" "tests/unit/test_auth_service.py" "tests/unit/test_pageindex_service.py" -q`

Expected: 全部 PASS；测试日志不出现外部 HTTP 请求。

- [ ] **Step 8: 人工审查点**

检查仅包含测试隔离、PRAGMA 和 `AppError` 导入，不执行 Git 操作。

---

### Task 2: Trigram/BM25 中文词法检索

**Files:**
- Create: `src/retrieval/lexical.py`
- Create: `tests/unit/test_lexical_retrieval.py`
- Modify: `src/db/schema.py`
- Modify: `src/retrieval/service.py`

**Interfaces:**
- Consumes: SQLite `chunks`、`documents`、`chunk_fts`。
- Produces: `LexicalRetriever.search(query: str, *, top_k: int, doc_uid: str | None, knowledge_base_id: str | None) -> list[dict]`。

- [ ] **Step 1: 写入中文排序与短词失败测试**

```python
def test_lexical_search_should_rank_exact_chinese_phrase_first(lexical_db: Path) -> None:
    items = LexicalRetriever(lexical_db).search("阿胶质量检测", top_k=5)
    assert items[0]["chunk_id"] == "quality_exact"
    assert items[0]["lexical_rank"] == 1


def test_lexical_search_should_use_controlled_fallback_for_two_chars(lexical_db: Path) -> None:
    items = LexicalRetriever(lexical_db).search("阿胶", top_k=5)
    assert [item["chunk_id"] for item in items] == ["title_match", "body_match"]
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest "tests/unit/test_lexical_retrieval.py" -q`

Expected: FAIL，`LexicalRetriever` 尚不存在。

- [ ] **Step 3: 新建库使用 Trigram FTS**

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    chunk_id UNINDEXED,
    doc_uid UNINDEXED,
    content,
    tokenize='trigram'
);
```

- [ ] **Step 4: 实现 BM25 排序**

```python
rows = connection.execute(
    """
    SELECT c.*, bm25(chunk_fts) AS bm25_score
    FROM chunk_fts
    JOIN chunks c ON c.chunk_id = chunk_fts.chunk_id
    JOIN documents d ON d.doc_uid = c.doc_uid
    WHERE chunk_fts MATCH ?
    ORDER BY bm25_score ASC, c.chunk_index ASC
    LIMIT ?
    """,
    (query, top_k),
).fetchall()
```

- [ ] **Step 5: 实现两字短词受控兜底**

仅允许规范化后长度为 2 的中文词进入 `LIKE`；按标题命中、正文出现次数、`chunk_index` 排序，不使用 `updated_at`。

```sql
ORDER BY
    CASE WHEN d.doc_title LIKE ? THEN 0 ELSE 1 END,
    ((length(c.content) - length(replace(c.content, ?, ''))) / length(?)) DESC,
    c.chunk_index ASC
```

- [ ] **Step 6: 将 `RetrievalService.fulltext_search()` 委托给 `LexicalRetriever`**

```python
self.lexical = LexicalRetriever(database_path)

def fulltext_search(
    self,
    query: str,
    top_k: int = 10,
    doc_uid: str | None = None,
    knowledge_base_id: str | None = None,
) -> list[dict]:
    return self.lexical.search(
        query,
        top_k=top_k,
        doc_uid=doc_uid,
        knowledge_base_id=knowledge_base_id,
    )
```

- [ ] **Step 7: 运行词法与原检索测试**

Run: `python -m pytest "tests/unit/test_lexical_retrieval.py" "tests/unit/test_retrieval.py" -q`

Expected: 全部 PASS；结果包含 `bm25_score`、`lexical_rank` 和 `retrieval_source=fulltext`。

- [ ] **Step 8: 人工审查点**

确认此任务只改变新建库 schema 和运行期读取；真实旧库 FTS 不在本任务自动迁移。

---

### Task 3: RRF 融合、统一轨迹和可靠降级

**Files:**
- Create: `src/retrieval/fusion.py`
- Create: `tests/unit/test_retrieval_fusion.py`
- Modify: `src/retrieval/service.py`
- Modify: `tests/unit/test_retrieval.py`

**Interfaces:**
- Consumes: `dict[str, list[dict]]` 形式的词法、向量候选集。
- Produces: `reciprocal_rank_fusion(result_sets: dict[str, list[dict]], *, rank_constant: int = 60) -> list[dict]`。

- [ ] **Step 1: 写入 RRF 排序失败测试**

```python
def test_rrf_should_prefer_item_found_by_both_retrievers() -> None:
    result = reciprocal_rank_fusion(
        {
            "fulltext": [{"chunk_id": "a"}, {"chunk_id": "shared"}],
            "vector": [{"chunk_id": "shared"}, {"chunk_id": "b"}],
        }
    )
    assert result[0]["chunk_id"] == "shared"
    assert result[0]["matched_sources"] == ["fulltext", "vector"]
```

- [ ] **Step 2: 写入外部服务降级失败测试**

```python
def test_hybrid_search_should_keep_lexical_results_when_vector_fails(service) -> None:
    service.vector_store = FailingVectorStore()
    items = service.hybrid_search("质量检测", top_k=3)
    assert items
    assert items[0]["degraded_reason"] == "vector_unavailable"
```

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest "tests/unit/test_retrieval_fusion.py" "tests/unit/test_retrieval.py" -q`

Expected: FAIL，RRF 与降级字段尚不存在。

- [ ] **Step 4: 实现 RRF**

```python
scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rank_constant + rank)
item["rrf_score"] = scores[chunk_id]
item["retrieval_trace"] = trace_by_chunk[chunk_id]
```

- [ ] **Step 5: 改造 `hybrid_search()`**

词法和向量分别召回，捕获向量与 Rerank 异常；先 RRF，再执行最多一次批量 Rerank。降级字段只记录真实失败原因。

```python
fused = reciprocal_rank_fusion({"fulltext": lexical_items, "vector": vector_items})
try:
    return self.reranker.rerank(query=query, items=fused, top_k=top_k)
except ExternalServiceAppError:
    return [{**item, "degraded_reason": "rerank_unavailable"} for item in fused[:top_k]]
```

- [ ] **Step 6: 运行聚焦测试**

Run: `python -m pytest "tests/unit/test_retrieval_fusion.py" "tests/unit/test_retrieval.py" "tests/unit/test_rerank.py" -q`

Expected: 全部 PASS；混合结果按 `rrf_score` 排序，失败时保留本地结果。

- [ ] **Step 7: 人工审查点**

确认未直接比较 BM25、向量距离和 Rerank 原始分数。

---

### Task 4: 向量元数据、模型指纹和索引一致性

**Files:**
- Create: `src/retrieval/index_state.py`
- Create: `tests/unit/test_index_state.py`
- Modify: `src/retrieval/vector_store.py`
- Modify: `src/app.py`
- Modify: `src/ui/app.py`
- Modify: `src/ingest/service.py`
- Test: `tests/unit/test_vector_store.py`
- Test: `tests/unit/test_ingest_quality.py`

**Interfaces:**
- Consumes: SQLite chunk 记录、Chroma metadata、Embedding 配置。
- Produces: `build_retrieval_index_report(database_path: Path, vector_store: VectorStore, *, embedding_provider: str, embedding_model: str, index_version: str) -> dict`、`write_index_manifest(path: Path, report: dict) -> None`、`VectorStore.inspect_index() -> dict`。

- [ ] **Step 1: 写入元数据和一致性失败测试**

```python
def test_vector_metadata_should_include_model_and_index_version(vector_store) -> None:
    vector_store.upsert_chunks([build_chunk("chunk_1", knowledge_base_id="default")])
    metadata = vector_store.collection.get(ids=["chunk_1"], include=["metadatas"])["metadatas"][0]
    assert metadata["knowledge_base_id"] == "default"
    assert metadata["embedding_model"] == "deterministic-v1"
    assert metadata["embedding_dimension"] == 64
    assert metadata["index_version"] == "retrieval-v2"
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest "tests/unit/test_index_state.py" "tests/unit/test_vector_store.py" -q`

Expected: FAIL，模型和索引版本元数据缺失。

- [ ] **Step 3: 扩展 `VectorStore` 构造参数与 metadata**

```python
def __init__(
    self,
    persist_directory,
    collection_name: str = "knowledge_chunks",
    embedding_client: BaseEmbeddingClient | None = None,
    sqlite_db_path=None,
    auto_repair_dimension_mismatch: bool = False,
    embedding_model: str = "deterministic-v1",
    index_version: str = "retrieval-v2",
) -> None:
    self.embedding_model = embedding_model
    self.index_version = index_version
```

```python
metadata.update({
    "embedding_model": self.embedding_model,
    "embedding_dimension": self._infer_current_embedding_dimension(),
    "index_version": self.index_version,
})
```

- [ ] **Step 4: 实现索引报告**

报告必须包含 SQLite 有效 chunk 数、Chroma 总数、按知识库和文档计数、缺失 metadata 数、模型、维度、FTS tokenizer、构建时间和 `consistent`。

- [ ] **Step 5: 原子写入清单**

```python
temporary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8-sig")
temporary_path.replace(manifest_path)
```

- [ ] **Step 6: 索引状态联动**

`IngestService` 只有在 SQLite、Chroma、必填 metadata 全部一致时才写入 `index_status="indexed"`；部分失败使用 `partial_failed` 并保留原因。

- [ ] **Step 7: 运行聚焦测试**

Run: `python -m pytest "tests/unit/test_index_state.py" "tests/unit/test_vector_store.py" "tests/unit/test_ingest_quality.py" -q`

Expected: 全部 PASS；索引数量或模型不一致时 `consistent=false` 且文档不得标记为已完成。

- [ ] **Step 8: 人工审查点**

确认启动过程不再无备份自动删除或重建 Chroma。

---

### Task 5: AI 质检查询收敛与单次批量 Rerank

**Files:**
- Modify: `src/retrieval/service.py`
- Modify: `src/quality/service.py`
- Modify: `tests/unit/test_quality.py`
- Modify: `tests/unit/test_ai_clients.py`

**Interfaces:**
- Consumes: `query_specs: list[dict[str, str]]`，最多三项。
- Produces: `RetrievalService.search_queries(query_specs, *, top_k, doc_uid, knowledge_base_id, use_rerank) -> list[dict]`。

- [ ] **Step 1: 写入查询数量和重排次数失败测试**

```python
def test_quality_retrieval_should_use_at_most_three_queries_and_one_rerank(service) -> None:
    queries = service._build_retrieval_queries("阿胶只有东阿产地才有效")
    service._retrieve_evidence_candidates(
        claim_text="阿胶只有东阿产地才有效",
        doc_uid=None,
        knowledge_base_id="default",
        retrieval_policy={
            "final_top_k": 5,
            "fulltext_top_k": 8,
            "vector_top_k": 8,
            "use_rerank": True,
        },
    )
    assert [item["label"] for item in queries] == ["claim_literal", "semantic_normalized", "counter_probe"]
    assert fake_reranker.call_count == 1
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest "tests/unit/test_quality.py" "tests/unit/test_ai_clients.py" -q`

Expected: FAIL，当前查询变体多于三项且可能多次 Rerank。

- [ ] **Step 3: 收敛查询生成**

```python
query_specs = [{"label": "claim_literal", "query": literal_query}]
if normalized_query != literal_query:
    query_specs.append({"label": "semantic_normalized", "query": normalized_query})
if counter_query:
    query_specs.append({"label": "counter_probe", "query": counter_query})
return query_specs[:3]
```

- [ ] **Step 4: 实现批量查询入口**

每个 query 只做词法、向量和 RRF；所有 query 结果再次按 chunk 合并，最后执行一次 Rerank，并保留 `matched_queries`。

- [ ] **Step 5: 修改质检服务调用**

```python
return self.retrieval_service.search_queries(
    query_specs,
    top_k=candidate_limit,
    doc_uid=doc_uid,
    knowledge_base_id=knowledge_base_id,
    use_rerank=retrieval_policy["use_rerank"],
)
```

- [ ] **Step 6: 运行质检回归**

Run: `python -m pytest "tests/unit/test_quality.py" "tests/unit/test_ai_clients.py" "tests/integration/test_app.py" -k "quality" -q`

Expected: 全部 PASS；每个 claim 的 Rerank 调用不超过一次。

- [ ] **Step 7: 人工审查点**

确认保留强约束 Claim 的反证探测，不用减少查询数量换取假阳性。

---

### Task 6: 检索索引备份、重建、验证和恢复工具

**Files:**
- Create: `src/retrieval/rebuild.py`
- Create: `.aipython/rebuild_retrieval_indexes.py`
- Create: `tests/integration/test_retrieval_rebuild.py`
- Modify: `.aipython/inspect_index_status.py`

**Interfaces:**
- Produces: `RetrievalIndexRebuilder.inspect() -> dict`、`backup() -> Path`、`build_staging() -> dict`、`validate() -> dict`、`publish() -> dict`、`restore_latest() -> dict`。
- CLI: `inspect`、`rebuild --apply`、`restore --latest --apply`。

- [ ] **Step 1: 写入非 `--apply` 不修改文件的失败测试**

```python
def test_rebuild_dry_run_should_not_modify_database_or_chroma(rebuild_fixture) -> None:
    before = snapshot_hashes(rebuild_fixture)
    result = rebuild_fixture.rebuilder.rebuild(apply=False)
    assert result["status"] == "dry_run"
    assert snapshot_hashes(rebuild_fixture) == before
```

- [ ] **Step 2: 写入失败门禁与恢复测试**

```python
def test_failed_validation_should_keep_active_indexes(rebuild_fixture) -> None:
    result = rebuild_fixture.rebuilder.rebuild(apply=True, validator=always_fail)
    assert result["published"] is False
    assert active_index_hashes(rebuild_fixture) == rebuild_fixture.original_hashes
```

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest "tests/integration/test_retrieval_rebuild.py" -q`

Expected: FAIL，重建器尚不存在。

- [ ] **Step 4: 实现带时间戳备份**

备份固定写入 `index/backups/retrieval/YYYYMMDDTHHMMSSZ/`，目录名由脚本按 UTC 自动生成；内容包含 `app.db`、`app.db-wal`、`app.db-shm`、`chroma/` 和 `index_manifest.json`。备份 SQLite 前执行只读 checkpoint，所有复制异常转为 `DatabaseAppError`。

- [ ] **Step 5: 在事务内重建 FTS**

```sql
DROP TABLE IF EXISTS chunk_fts__staging;
CREATE VIRTUAL TABLE chunk_fts__staging USING fts5(
    chunk_id UNINDEXED, doc_uid UNINDEXED, content, tokenize='trigram'
);
INSERT INTO chunk_fts__staging(chunk_id, doc_uid, content)
SELECT chunk_id, doc_uid, content FROM chunks;
```

校验成功后在同一事务中替换活动表；异常必须回滚。

```sql
DROP TABLE chunk_fts;
ALTER TABLE chunk_fts__staging RENAME TO chunk_fts;
```

- [ ] **Step 6: 在 `index/chroma.staging` 构建向量索引**

构建完成后验证数量、知识库、文档、模型和维度；只有 `consistent=true` 才允许将活动目录重命名为备份并将 staging 重命名为 `index/chroma`。

- [ ] **Step 7: 实现 CLI 顶层异常处理**

```python
try:
    result = command(args)
except AppError as exc:
    print(json.dumps({"success": False, "error": exc.to_dict()}, ensure_ascii=False))
    raise SystemExit(1) from exc
```

- [ ] **Step 8: 运行集成测试**

Run: `python -m pytest "tests/integration/test_retrieval_rebuild.py" "tests/unit/test_index_state.py" -q`

Expected: 全部 PASS；失败不会切换，恢复后哈希与备份一致。

- [ ] **Step 9: 人工审查点**

只验证临时目录；不得对真实 `index/` 执行 `--apply`。

---

### Task 7: PageIndex 层级树、稳定节点和质量门禁

**Files:**
- Create: `src/pageindex/structure.py`
- Create: `tests/unit/test_pageindex_structure.py`
- Modify: `src/pageindex/service.py`
- Modify: `tests/unit/test_pageindex_service.py`

**Interfaces:**
- Produces: `build_heading_tree(markdown_text: str) -> list[dict]`、`enrich_vendor_structure(vendor_nodes, heading_tree, doc_uid) -> list[dict]`、`evaluate_tree_quality(structure, source_line_count) -> dict`。

- [ ] **Step 1: 写入层级和稳定 ID 失败测试**

```python
def test_heading_tree_should_preserve_article_chapter_section_hierarchy() -> None:
    tree = build_heading_tree("# 第一篇\n## 第一章\n### 第一节\n正文")
    assert tree[0]["children"][0]["children"][0]["heading_path"] == "第一篇 / 第一章 / 第一节"
    assert tree[0]["children"][0]["children"][0]["source_start_line"] == 3
```

- [ ] **Step 2: 写入扁平树拒绝测试**

```python
def test_tree_quality_should_reject_all_root_nodes() -> None:
    report = evaluate_tree_quality([root_node("一"), root_node("二")], source_line_count=100)
    assert report["passed"] is False
    assert "flat_tree" in report["errors"]
```

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest "tests/unit/test_pageindex_structure.py" -q`

Expected: FAIL，结构模块尚不存在。

- [ ] **Step 4: 实现 Markdown 标题栈和稳定节点 ID**

```python
node_id = sha256(
    f"{doc_uid}|{heading_path}|{source_start_line}|{source_end_line}".encode("utf-8")
).hexdigest()[:20]
```

标题栈按 `#` 数量维护父子关系；文章边界、章、节不得全部压平为一级。

- [ ] **Step 5: 用标题和行号增强 vendor 节点**

映射结果必须保留 vendor `line_num` 以继续调用 `get_page_content()`，同时补充 `node_id`、`parent_id`、`heading_path`、原文范围、锚点和 `content_hash`。

- [ ] **Step 6: 写入 `structure.normalized.json` 和质量报告**

只在正文覆盖率、最大深度、空节点、孤立节点和可追溯率全部通过时保存。JSON 使用临时文件后 `replace()`。

- [ ] **Step 7: 修改 `_load_structure()` 优先读取规范化树**

不存在规范化树时明确返回 `stale_index` 或 legacy 状态，不静默伪装为新树。

- [ ] **Step 8: 运行 PageIndex 结构测试**

Run: `python -m pytest "tests/unit/test_pageindex_structure.py" "tests/unit/test_pageindex_service.py" -k "structure or build_index or tree" -q`

Expected: 全部 PASS；扁平树不能通过新质量门禁。

- [ ] **Step 9: 人工审查点**

确认没有修改 vendor 源码，增强逻辑全部位于项目 `src/pageindex`。

---

### Task 8: 文档路由与全局检索预算

**Files:**
- Create: `src/pageindex/routing.py`
- Create: `tests/unit/test_pageindex_routing.py`
- Modify: `src/pageindex/service.py`
- Modify: `tests/unit/test_pageindex_service.py`

**Interfaces:**
- Produces: `RetrievalBudgetExceededError`、`PageIndexBudget(max_llm_calls: int, max_rounds: int, max_documents: int, max_evidence: int)`、`route_documents(question, records, analysis, *, limit=3) -> list[dict]`。

- [ ] **Step 1: 写入 Top-3 路由失败测试**

```python
def test_route_documents_should_limit_candidates_to_three() -> None:
    routed = route_documents("质量检测", records, analysis={"keywords": ["质量", "检测"]}, limit=3)
    assert len(routed) == 3
    assert routed[0]["doc_uid"] == "quality_doc"
```

- [ ] **Step 2: 写入预算失败测试**

```python
def test_budget_should_stop_before_seventh_single_document_call() -> None:
    budget = PageIndexBudget(max_llm_calls=6, max_rounds=3, max_documents=1, max_evidence=8)
    for _ in range(6):
        budget.consume_llm("test")
    with pytest.raises(RetrievalBudgetExceededError):
        budget.consume_llm("overflow")
```

预算异常直接继承项目校验异常，API 可沿用统一异常处理：

```python
class RetrievalBudgetExceededError(ValidationAppError):
    """PageIndex 检索预算耗尽。"""
```

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest "tests/unit/test_pageindex_routing.py" -q`

Expected: FAIL，路由和预算类型尚不存在。

- [ ] **Step 4: 实现本地文档粗排与可选单次 LLM 路由**

先按文档标题、树摘要和分析关键词得到最多 8 个候选；LLM 启用时只调用一次并限制为 Top 3，失败时使用本地 Top 3。

- [ ] **Step 5: 将预算注入单文档和知识库问答**

单文档默认 `max_llm_calls=6`；知识库默认 `max_llm_calls=7`、`max_documents=3`。预算耗尽返回 `budget_exhausted`，不得继续循环。

- [ ] **Step 6: 运行路由与服务测试**

Run: `python -m pytest "tests/unit/test_pageindex_routing.py" "tests/unit/test_pageindex_service.py" -k "knowledge_base or budget or route" -q`

Expected: 全部 PASS；知识库问答不再遍历所有索引记录。

- [ ] **Step 7: 人工审查点**

确认调用预算计入查询分析、文档路由、节点选择、证据判定和最终回答。

---

### Task 9: 动态搜索焦点、统一补充召回和过期保护

**Files:**
- Modify: `src/pageindex/service.py`
- Modify: `src/ui/pages.py`
- Modify: `src/ui/app.py`
- Modify: `tests/unit/test_pageindex_service.py`
- Modify: `tests/unit/test_pageindex_ui.py`

**Interfaces:**
- Consumes: 已配置的 `RetrievalService`、`PageIndexBudget` 和规范化结构。
- Produces: `PageIndexService(settings, *, llm_client=None, retrieval_service: RetrievalService | None = None)`。

- [ ] **Step 1: 写入下一轮焦点变化失败测试**

```python
def test_next_search_focus_should_change_second_round_candidates(service) -> None:
    result = service.ask_question("default", "doc_1", "质量检测还缺哪些依据")
    rounds = result["debug"]["retrieval_rounds"]
    assert rounds[1]["search_focus"] == rounds[0]["next_search_focus"]
    assert rounds[1]["candidate_node_ids"] != rounds[0]["candidate_node_ids"]
```

- [ ] **Step 2: 写入来源哈希过期失败测试**

```python
def test_pageindex_query_should_reject_stale_source_hash(service) -> None:
    with pytest.raises(ValidationAppError, match="stale_index"):
        service.ask_question("default", "doc_1", "问题")
```

- [ ] **Step 3: 写入统一召回失败测试**

断言 `_search_rag_fts_evidence()` 不再直接执行 SQL，而是调用注入的 `RetrievalService.hybrid_search()`，并继续遵守“LLM 已选择零节点时不生成通用兜底证据”的现有安全规则。

- [ ] **Step 4: 运行失败测试**

Run: `python -m pytest "tests/unit/test_pageindex_service.py" "tests/unit/test_pageindex_ui.py" -q`

Expected: 新增测试 FAIL。

- [ ] **Step 5: 让 `next_search_focus` 驱动下一轮**

```python
round_question = f"{question}\n本轮补充检索重点：{next_search_focus}" if next_search_focus else question
candidates = self._build_tree_candidates(
    record,
    structure,
    question=round_question,
    question_analysis=question_analysis,
    exclude_node_ids=selected_node_ids,
)
```

- [ ] **Step 6: 注入统一检索服务**

```python
pageindex_service = PageIndexService(
    ingest_service.settings,
    retrieval_service=retrieval_service,
)
```

`_search_rag_fts_evidence()` 只负责把统一检索结果转换为 PageIndex 证据格式，不保留重复 FTS/LIKE SQL。

- [ ] **Step 7: 增加来源哈希和索引版本校验**

每次问答前比较 `documents.source_hash`、`pageindex_indexes.source_hash` 和 workspace manifest；不一致返回 `stale_index`。

- [ ] **Step 8: 统一证据轨迹**

每条证据至少包含 `doc_uid`、`node_id` 或 `chunk_id`、`heading_path`、原文范围、来源锚点、轮次、选择原因、RRF/本地分数和降级原因。

- [ ] **Step 9: 运行 PageIndex 全部测试**

Run: `python -m pytest "tests/unit/test_pageindex_service.py" "tests/unit/test_pageindex_ui.py" "tests/unit/test_pageindex_evidence_judge.py" "tests/unit/test_pageindex_question_plan.py" -q`

Expected: 全部 PASS；零节点安全规则、动态焦点和过期保护同时成立。

- [ ] **Step 10: 人工审查点**

确认没有保留第二套 FTS/LIKE 实现，没有扩大无证据回答范围。

---

### Task 10: PageIndex 安全重建和恢复工具

**Files:**
- Create: `src/pageindex/rebuild.py`
- Create: `.aipython/rebuild_pageindex.py`
- Create: `tests/integration/test_pageindex_rebuild.py`
- Modify: `src/pageindex/service.py`

**Interfaces:**
- Produces: `PageIndexRebuilder.inspect() -> dict`、`backup() -> Path`、`rebuild_staging() -> dict`、`validate() -> dict`、`publish() -> dict`、`restore_latest() -> dict`。
- CLI: `inspect`、`rebuild --apply`、`restore --latest --apply`。

- [ ] **Step 1: 写入临时 workspace 与失败保持测试**

```python
def test_pageindex_rebuild_should_publish_only_after_quality_gate(fixture) -> None:
    result = fixture.rebuilder.rebuild(apply=True, quality_gate=always_fail)
    assert result["published"] is False
    assert fixture.active_workspace_hash() == fixture.original_workspace_hash
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest "tests/integration/test_pageindex_rebuild.py" -q`

Expected: FAIL，PageIndex 重建器尚不存在。

- [ ] **Step 3: 实现备份和 staging 目录**

备份写入 `index/backups/pageindex/YYYYMMDDTHHMMSSZ/`，目录名由脚本按 UTC 自动生成；新索引写入 `index/pageindex_workspace.staging/`。备份包含 workspace、数据库 PageIndex 元数据导出和 manifest。

- [ ] **Step 4: 在 staging 中逐文档构建**

每篇文档生成 vendor 索引、`structure.normalized.json`、`tree_quality.json` 和 manifest。任一文档失败即停止，不更新活动数据库记录。

- [ ] **Step 5: 通过事务发布记录**

先原子切换 workspace，再在 `transaction()` 内批量更新 `pageindex_indexes`；异常时恢复目录并回滚数据库。

- [ ] **Step 6: 实现 CLI 异常和确认门禁**

没有 `--apply` 只输出计划、文档数、模型和预计调用上限；不得创建或替换活动索引。

- [ ] **Step 7: 运行集成测试**

Run: `python -m pytest "tests/integration/test_pageindex_rebuild.py" "tests/unit/test_pageindex_structure.py" -q`

Expected: 全部 PASS；失败保持旧 workspace，恢复后记录和目录一致。

- [ ] **Step 8: 人工审查点**

只使用假 PageIndex 客户端验证流程，不调用外部 LLM。

---

### Task 11: 真实评测集和质量指标

**Files:**
- Modify: `src/retrieval/evaluation.py`
- Create: `.aipython/run_retrieval_evaluation.py`
- Modify: `tests/unit/test_retrieval_evaluation.py`
- Modify: `tests/evaluation/retrieval_cases.jsonl`
- Modify: `tests/evaluation/pageindex_cases.jsonl`
- Create during verified run: `Docs/retrieval_pageindex_evaluation_20260716.md`

**Interfaces:**
- Produces: `evaluate_retrieval_cases()` 的 `recall_at_5`、`mrr_at_10`、`ndcg_at_10`、`traceable_rate`；PageIndex 的 `node_hit_at_5`、`refusal_accuracy` 和调用预算统计。

- [ ] **Step 1: 写入指标失败测试**

```python
def test_retrieval_metrics_should_calculate_recall_mrr_and_ndcg() -> None:
    summary = evaluate_ranked_rows(build_ranked_rows())["summary"]
    assert summary["recall_at_5"] == 1.0
    assert summary["mrr_at_10"] == 0.75
    assert summary["ndcg_at_10"] == pytest.approx(0.815, abs=0.001)
```

- [ ] **Step 2: 写入合成 ID 拒绝测试**

```python
def test_formal_cases_should_reference_existing_database_ids(app_db: Path) -> None:
    result = validate_case_references(app_db, load_jsonl_cases(RETRIEVAL_CASES))
    assert result["missing_doc_uids"] == []
    assert result["missing_chunk_ids"] == []
```

- [ ] **Step 3: 运行失败测试**

Run: `python -m pytest "tests/unit/test_retrieval_evaluation.py" "tests/unit/test_evaluation_fixtures.py" -q`

Expected: 新指标测试 FAIL；当前合成 ID 校验 FAIL。

- [ ] **Step 4: 实现标准排名指标**

```python
reciprocal_rank = 0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank
dcg = sum(rel / math.log2(rank + 1) for rank, rel in enumerate(relevance, start=1))
ndcg = 0.0 if ideal_dcg == 0 else dcg / ideal_dcg
```

- [ ] **Step 5: 将正式样例对齐真实项目数据**

从当前数据库选择至少 50 个真实问题，保存准确的 `knowledge_base_id`、`doc_uid`、`chunk_id`、`heading_path`、预期证据和 `answerable`。负例必须包含感冒、不孕不育等无直接证据问题，正例覆盖质量检测、制作工艺、古籍记载和皮肤状态改善。

- [ ] **Step 6: 实现评测 CLI**

CLI 默认只读，输出 JSON 摘要和带 BOM/CRLF 的 Markdown；指标未达阈值时退出码为 1。

- [ ] **Step 7: 运行离线评测测试**

Run: `python -m pytest "tests/unit/test_retrieval_evaluation.py" "tests/unit/test_evaluation_fixtures.py" -q`

Expected: 全部 PASS；评测样例引用均能在当前项目数据库中解析。

- [ ] **Step 8: 人工审查点**

正式评测报告在索引重建后生成；本任务不调用外部模型。

---

### Task 12: CI、全量校验和交付文档

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`
- Modify: `readme.md`
- Modify: `Docs/acceptance.MD`
- Modify: `Docs/tasks.MD`
- Create: `Docs/changelog/retrieval_pageindex_20260716.md`
- Modify: `Docs/design/retrieval_pageindex_optimization_design_20260716.md`
- Modify: `todo.md`

**Interfaces:**
- Produces: 项目统一 `lint`、`test`、`type-check`、`build` 检查和恢复说明。

- [ ] **Step 1: 在 `pyproject.toml` 声明开发检查工具**

```toml
[project.optional-dependencies]
dev = [
  "build>=1.2.0,<2.0.0",
  "mypy>=1.11.0,<2.0.0",
  "pytest>=8.0.0,<9.0.0",
  "ruff>=0.6.0,<1.0.0",
]
```

安装或更新依赖前必须另行确认。

- [ ] **Step 2: 新建 CI 工作流**

```yaml
- run: python -m ruff check src tests .aipython
- run: python -m mypy src/retrieval src/pageindex src/quality/service.py
- run: python -m pytest tests --maxfail=1 -q
- run: python -m build
```

CI 环境显式设置 `LLM_PROVIDER=disabled`、`EMBEDDING_PROVIDER=local`、`RERANK_ENABLED=false` 和空管理员密码。

- [ ] **Step 3: 执行格式和静态检查**

Run: `python -m ruff check src tests .aipython`

Expected: `All checks passed!`

Run: `python -m mypy src/retrieval src/pageindex src/quality/service.py`

Expected: `Success: no issues found`。

- [ ] **Step 4: 执行聚焦测试**

Run: `python -m pytest "tests/unit/test_database_connection.py" "tests/unit/test_lexical_retrieval.py" "tests/unit/test_retrieval_fusion.py" "tests/unit/test_index_state.py" "tests/unit/test_pageindex_structure.py" "tests/unit/test_pageindex_routing.py" "tests/unit/test_pageindex_service.py" -q`

Expected: 全部 PASS。

- [ ] **Step 5: 执行全量测试**

Run: `python -m pytest tests --maxfail=1 -q`

Expected: 全部 PASS；无真实外部 HTTP 请求。

- [ ] **Step 6: 执行构建**

Run: `python -m build`

Expected: `dist/` 生成 sdist 和 wheel，命令退出码 0。

- [ ] **Step 7: 更新项目文档**

记录修改文件、算法公式、配置、索引版本、运行命令、失败恢复、未达指标和兼容性影响。所有 Markdown 作为代码变更参与审查。

- [ ] **Step 8: 人工审查点**

检查 `git diff --check`、`git status --short` 和文档一致性；未经确认不提交或推送。

---

### Task 13: 正式备份、外部验证、单次重建和最终验收

**Files:**
- Runtime outputs: `index/backups/retrieval/`
- Runtime outputs: `index/backups/pageindex/`
- Runtime outputs: `index/index_manifest.json`
- Create: `Docs/retrieval_pageindex_evaluation_20260716.md`
- Modify: `Docs/changelog/retrieval_pageindex_20260716.md`
- Modify: `Docs/acceptance.MD`
- Modify: `todo.md`

**Interfaces:**
- Consumes: 已通过全部离线检查的代码和项目真实 `.env`。
- Produces: 一次正式检索索引重建、一次正式 PageIndex 重建、真实指标报告和可用备份。

- [x] **Step 1: 取得第二次执行确认**

在运行任何外部 API、依赖安装、数据库调整或 `--apply` 前，向用户说明目的、预计调用范围、备份目录、恢复命令和停机要求，并等待明确确认。

- [x] **Step 2: 只读检查当前状态**

Run: `python ".aipython/inspect_index_status.py"`

Expected: 输出 SQLite、FTS、Chroma、PageIndex 数量和不一致项，不修改文件。

- [x] **Step 3: 验证外部模型连通性**

Run: `python ".aipython/check_model_connectivity.py"`

Expected: LLM、Embedding、Rerank 均成功；任一失败立即停止，不重建索引。

- [x] **Step 4: 正式重建检索索引一次**

Run: `python ".aipython/rebuild_retrieval_indexes.py" rebuild --apply`

Expected: 自动备份、Trigram FTS 与 Chroma staging 构建、校验、切换成功；`consistent=true`。

- [x] **Step 5: 正式重建 PageIndex 一次**

Run: `python ".aipython/rebuild_pageindex.py" rebuild --apply`

Expected: 所有文档层级树通过门禁并原子切换；不存在全一级扁平树。

- [x] **Step 6: 运行真实评测**

Run: `python ".aipython/run_retrieval_evaluation.py" --database "index/app.db" --output "Docs/retrieval_pageindex_evaluation_20260716.md"`

Expected: 所有正式指标达到 Global Constraints 阈值，调用预算无超限，报告生成成功。

- [x] **Step 7: 恢复演练**

Run: `python ".aipython/rebuild_pageindex.py" restore --latest --apply`

Run: `python ".aipython/rebuild_retrieval_indexes.py" restore --latest --apply`

Expected: 活动索引、数据库记录和 manifest 恢复到最近备份；恢复后重新执行只读检查。

实际结果：两个恢复命令均完成 `--latest` dry-run。未加 `--apply`，避免用旧备份覆盖已验证活动索引。

- [x] **Step 8: 最终幂等验证**

Run: `python -m pytest tests --maxfail=1 -q`

Run: `python -m ruff check src tests .aipython`

Run: `python -m mypy src/retrieval src/pageindex src/quality/service.py`

Run: `python -m build`

Expected: checks 全绿，真实评测达标，索引一致，恢复命令可用。

- [x] **Step 9: 更新完成记录**

在验收、changelog、评测报告和 `todo.md` 中记录真实数量、模型指纹、测试结果、指标、备份位置、未执行项和残余风险。

- [x] **Step 10: Git 决策门禁**

只报告当前改动；如需 commit 或 push，必须再次获得用户明确授权。

---

## 2. 执行顺序与停止条件

1. Task 1 至 Task 6 完成后，检索链路必须独立可测试、可降级、可恢复。
2. Task 7 至 Task 10 完成后，PageIndex 必须复用检索主链并通过树质量门禁。
3. Task 11 至 Task 12 完成后，才能请求正式外部验证和重建授权。
4. Task 13 任一门禁失败立即停止并保留旧索引；不得为了完成任务降低指标。
5. 未达到真实检索指标、引用可追溯率或恢复验证时，任务保持未完成状态。
