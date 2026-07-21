# P1 PageIndex 持久化职责拆分实施计划

> **执行要求：** 使用 `superpowers:executing-plans` 在当前会话逐项执行；用户明确禁止 Subagent。步骤使用复选框跟踪。

**目标：** 将 PageIndex 自有表的初始化、索引记录和问答历史持久化迁入单一 `PageIndexRepository`，并从 `PageIndexService` 删除相关 SQL 与两个私有读取包装层。

**架构：** 新建 `src/pageindex/index_repository.py`，仓储只依赖数据库连接、事务与应用错误。`PageIndexService` 保留公开接口、输入校验、业务错误、检索编排和历史格式化，直接委托仓储。

**技术栈：** Python 3.11、SQLite、Pytest、Ruff、Mypy、AST 质量门禁。

## 全局约束

- 不新增依赖、Repository 基类、Factory、额外配置或数据库 schema。
- 不改变 PageIndex 检索、路由、证据、回答和导出算法。
- 所有写操作继续使用 `transaction()`；读取继续使用 `create_connection()`。
- 保留公开服务接口和已有读取错误文案；新增写入/初始化数据库错误使用结构化 `DatabaseAppError`。
- 删除 `_get_index_record()` 与 `_list_index_records()`，不保留生产兼容包装层。
- 不调用外部 API，不迁移正式数据库，不重建正式索引，不部署。
- Git commit、push、merge 或 pull 必须另行获得明确授权，本计划不执行 Git 写操作。
- 新增或修改的 Python、Markdown 文件统一为 UTF-8 BOM 与 CRLF。

---

### Task 1：建立仓储契约与索引记录 TDD

**Files:**

- Create: `tests/unit/test_pageindex_repository.py`
- Create: `src/pageindex/index_repository.py`

**Interfaces:**

- Consumes: `Path`、`create_connection(Path)`、`transaction(Path)`、`DatabaseAppError`。
- Produces: `PageIndexRepository(database_path: Path)`、`initialize_schema()`、`upsert_index_record(...)`、`get_index_record(...)`、`list_index_records(...)`。

- [x] **Step 1：写缺失模块与索引契约测试**

测试文件先导入尚不存在的类，并用临时 SQLite 初始化知识库和文档。核心断言：

```python
repository = PageIndexRepository(database_path)
repository.initialize_schema()
repository.upsert_index_record(
    knowledge_base_id="kb_alpha",
    doc_uid="doc_alpha",
    pageindex_doc_id="page_alpha_v1",
    workspace_path="workspace/alpha",
    source_hash="hash_v1",
    created_at="2026-07-18T00:00:00+00:00",
    updated_at="2026-07-18T00:00:00+00:00",
)
repository.upsert_index_record(
    knowledge_base_id="kb_alpha",
    doc_uid="doc_alpha",
    pageindex_doc_id="page_alpha_v2",
    workspace_path="workspace/alpha",
    source_hash="hash_v2",
    created_at="2026-07-18T00:00:00+00:00",
    updated_at="2026-07-18T01:00:00+00:00",
)

record = repository.get_index_record("kb_alpha", "doc_alpha")
assert record is not None
assert record["pageindex_doc_id"] == "page_alpha_v2"
assert record["current_source_hash"] == "hash_v2"
assert [item["doc_uid"] for item in repository.list_index_records("kb_alpha")] == ["doc_alpha"]
```

- [x] **Step 2：运行测试确认 Red**

Run: `python -m pytest tests/unit/test_pageindex_repository.py -q`

Expected: 收集阶段因 `src.pageindex.index_repository` 不存在而失败。

- [x] **Step 3：实现最小索引仓储**

新文件以程序说明开头，定义单一生产类：

```python
class PageIndexRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize_schema(self) -> None: ...

    def upsert_index_record(
        self,
        *,
        knowledge_base_id: str,
        doc_uid: str,
        pageindex_doc_id: str,
        workspace_path: str,
        source_hash: str,
        created_at: str,
        updated_at: str,
    ) -> None: ...

    def get_index_record(self, knowledge_base_id: str, doc_uid: str) -> dict | None: ...

    def list_index_records(self, knowledge_base_id: str) -> list[dict]: ...
```

`initialize_schema()` 迁移现有两张表、两个索引和 `debug_json` 兼容列 DDL；`upsert_index_record()` 保持现有 `ON CONFLICT` 更新字段；两个读取方法保持现有 JOIN、字段和排序。

- [x] **Step 4：运行仓储测试确认 Green**

Run: `python -m pytest tests/unit/test_pageindex_repository.py -q`

Expected: 索引仓储测试通过，无外部调用。

---

### Task 2：完成问答历史持久化与异常 TDD

**Files:**

- Modify: `tests/unit/test_pageindex_repository.py`
- Modify: `src/pageindex/index_repository.py`

**Interfaces:**

- Consumes: Task 1 的 `PageIndexRepository` 与已存在的 PageIndex 历史表。
- Produces: `insert_query_history(...)`、两个列表方法、两个单条读取方法。

- [x] **Step 1：写历史范围、排序、limit 和单条读取失败测试**

使用以下接口写入两条不同文档、不同时间的记录：

```python
repository.insert_query_history(
    query_id="piq_alpha",
    knowledge_base_id="kb_alpha",
    doc_uid="doc_alpha",
    question="问题 A",
    answer="回答 A",
    evidence_json="[]",
    debug_json="{}",
    created_at="2026-07-18T00:00:00+00:00",
)
```

断言文档列表和知识库列表按 `created_at DESC`，`limit=1` 只返回最新记录，两个 get 方法在范围不匹配时返回 `None`。

- [x] **Step 2：运行新增测试确认 Red**

Run: `python -m pytest tests/unit/test_pageindex_repository.py -q`

Expected: 因历史方法尚未定义而失败。

- [x] **Step 3：实现五个显式历史方法**

```python
def insert_query_history(self, *, query_id: str, knowledge_base_id: str, doc_uid: str,
                         question: str, answer: str, evidence_json: str,
                         debug_json: str, created_at: str) -> None: ...
def list_query_history(self, knowledge_base_id: str, doc_uid: str, limit: int) -> list[dict]: ...
def list_knowledge_base_query_history(self, knowledge_base_id: str, limit: int) -> list[dict]: ...
def get_query_history_record(self, knowledge_base_id: str, doc_uid: str, query_id: str) -> dict | None: ...
def get_knowledge_base_query_history_record(self, knowledge_base_id: str, query_id: str) -> dict | None: ...
```

INSERT 使用事务；读取 SQL 保持现有字段、过滤范围和排序；所有返回值在仓储内转换为普通字典。

- [x] **Step 4：写数据库错误转换失败测试**

为仓储使用不存在父目录下的数据库路径，分别调用初始化、索引写入和读取，断言抛出 `DatabaseAppError` 且 `details["reason"]` 非空。

- [x] **Step 5：为每个仓储入口转换数据库错误**

捕获 `sqlite3.DatabaseError`，使用以下固定文案：

```text
初始化 PageIndex 元数据表失败
写入 PageIndex 索引记录失败
读取 PageIndex 索引记录失败
写入 PageIndex 问答历史失败
读取 PageIndex 历史失败
读取 PageIndex 历史记录失败
```

- [x] **Step 6：运行仓储测试确认 Green**

Run: `python -m pytest tests/unit/test_pageindex_repository.py -q`

Expected: 全部仓储测试通过。

---

### Task 3：接入 PageIndexService 并删除持久化实现

**Files:**

- Modify: `src/pageindex/service.py`
- Modify: `src/pageindex/history_export.py`
- Modify: `tests/unit/test_pageindex_service.py`
- Modify: `tests/unit/test_pageindex_ui.py`
- Modify: `tests/integration/test_pageindex_rebuild.py`
- Modify: `tests/unit/test_pageindex_history_export.py`

**Interfaces:**

- Consumes: Task 1-2 的九个仓储方法。
- Produces: 保持原签名的 `PageIndexService` 公开接口，服务不再持有 PageIndex 自有表 SQL。

- [x] **Step 1：写服务委托与普通映射解析失败测试**

在历史导出测试中直接传入 `list[dict]`；在服务测试中断言 `service.index_repository` 是 `PageIndexRepository`，并继续通过公开方法验证 upsert、提问保存和历史导出。

- [x] **Step 2：运行聚焦测试确认 Red**

Run: `python -m pytest tests/unit/test_pageindex_repository.py tests/unit/test_pageindex_history_export.py tests/unit/test_pageindex_service.py -q --maxfail=1`

Expected: 服务尚未暴露仓储，或历史解析类型尚未放宽，测试失败。

- [x] **Step 3：接入仓储并迁移 SQL**

在服务初始化中执行：

```python
self.index_repository = PageIndexRepository(settings.sqlite_db_path)
self.index_repository.initialize_schema()
```

公开 `upsert_index_record()` 保留校验、工作区和时间计算，随后调用仓储。两个问答方法将现有 JSON 字符串交给 `insert_query_history()`。四个历史查询方法委托对应仓储方法后继续调用 `parse_history_rows()`。

- [x] **Step 4：删除旧实现与私有包装层**

删除 `_ensure_tables()`、`_ensure_pageindex_history_debug_column()`、`_get_index_record()`、`_list_index_records()` 及 PageIndex 自有表 SQL。内部读取索引处先执行现有 `_require_*` 校验，再直接调用仓储并保留原 `NotFoundAppError`。

- [x] **Step 5：放宽历史解析输入类型并更新测试调用**

```python
def parse_history_rows(rows: Sequence[Mapping[str, object]]) -> list[dict]: ...
```

将测试中对两个已删除私有方法的调用改为 `service.index_repository.get_index_record(...)`，并显式断言结果非空后继续原测试逻辑。

- [x] **Step 6：运行 PageIndex 服务/UI/集成回归**

Run: `python -m pytest tests/unit/test_pageindex_repository.py tests/unit/test_pageindex_history_export.py tests/unit/test_pageindex_service.py tests/unit/test_pageindex_ui.py tests/integration/test_pageindex_rebuild.py -q`

Expected: 全部通过，现有检索与历史行为不变。

---

### Task 4：增加职责门禁并完成静态验证

**Files:**

- Modify: `tests/unit/test_quality_gates.py`

**Interfaces:**

- Consumes: Task 3 完成后的源码边界。
- Produces: 防止 PageIndex SQL 或已删除私有包装层回流的 AST/源码门禁。

- [x] **Step 1：写门禁测试并确认旧代码能触发失败**

门禁断言：

```python
assert "pageindex_indexes" not in service_source
assert "pageindex_query_history" not in service_source
assert {"_get_index_record", "_list_index_records"}.isdisjoint(service_method_names)
assert "src.pageindex.service" not in repository_source
```

在完成迁移前临时针对当前基线运行，确认至少表名和私有方法断言失败；随后保留测试并完成迁移。

- [x] **Step 2：运行职责门禁和 Mypy**

Run: `python -m pytest tests/unit/test_quality_gates.py -q`

Run: `python -m mypy src/pageindex src/retrieval src/quality/service.py`

Expected: 门禁通过，Mypy 无问题。

- [x] **Step 3：运行 Ruff 与格式检查**

Run: `python -m ruff check src tests .aipython Docs/migrations`

Expected: 退出码 0。

---

### Task 5：同步文档并执行完整验收

**Files:**

- Modify: `todo.md`
- Modify: `Docs/changelog/retrieval_pageindex_20260716.md`
- Modify: `Docs/acceptance.MD`
- Modify: `Docs/optimization-plan/vibe_coding_code_quality_audit_20260716.md`
- Modify: `Docs/optimization-plan/knowledge_base_maturity_assessment_20260716.md`
- Modify: `chat_history.md`

**Interfaces:**

- Consumes: 已通过聚焦测试和静态检查的实现。
- Produces: 可追踪的设计、计划、变更、验收、审计与聊天记录。

- [x] **Step 1：记录代码净变化与验证结果**

记录迁移前基线 `service.py=2542` 行、`PageIndexService=88` 个方法；用物理行数与 `git diff --numstat` 记录迁移后服务、新仓储和合计净变化。

- [x] **Step 2：更新项目文档**

将本批次标记为 P1 第五批，记录接口保持、SQL 迁移、两个私有包装层删除、Red/Green 证据、完整验证以及未执行的外部操作。同步修正 `retrieval_pageindex_implementation_plan_20260716.md` Task 1-12 复选框与既有执行记录的文档漂移。

- [x] **Step 3：规范文本格式并检查差异**

确保本批次涉及的 Python/Markdown 文本为 UTF-8 BOM、CRLF；不修改三份既有噪声文档。运行 `git diff --check` 时排除：

```text
Docs/evidence_catalog_20260620.md
Docs/pageindex-llm-evaluation-20260618.md
Docs/retrieval_alignment_suggestions_20260621.md
```

- [x] **Step 4：执行完整质量验证**

Run: `python -m ruff check src tests .aipython Docs/migrations`

Run: `python -m mypy src/retrieval src/pageindex src/quality/service.py`

Run: `python -m pytest tests -q`

Run: `python -m build`

Run: `python -m compileall -q src tests .aipython`

Expected: 所有命令退出码 0；测试数量不低于迁移前的 `422 passed`。

- [x] **Step 5：Git 决策门禁**

只报告未提交差异和验证结果。未经用户再次确认，不执行 commit 或 push。

