# P1 PageIndex 持久化职责拆分设计

> 日期：2026-07-18
> 状态：已实施并通过工程验收
> 范围：`src/pageindex`、PageIndex 单元测试、质量门禁与项目交付文档

## 1. 背景与目标

`PageIndexService` 当前仍直接负责 PageIndex 表初始化、索引记录读写和问答历史读写。历史 Markdown 格式化已经迁入 `history_export.py`，但持久化 SQL 仍与检索、回答和文件处理混在同一个服务中。

本批次采用已确认的 B 方案：新增一个 `PageIndexRepository`，统一承载 PageIndex 自有表的持久化职责，同时保持 `PageIndexService` 的公开接口、检索算法和用户可见行为稳定。

完成后应满足：

- `PageIndexService` 不再包含 `pageindex_indexes` 或 `pageindex_query_history` 的 SQL；
- PageIndex 表初始化、索引记录和问答历史由一个仓储负责；
- 删除 `_get_index_record()` 与 `_list_index_records()`，不保留平行兼容包装层；
- 所有 PageIndex 写操作继续使用事务；
- SQLite 连接继续统一启用 WAL 与 `synchronous=NORMAL`；
- 不改变检索、路由、证据合并、回答或导出算法。

## 2. 已选方案与取舍

### 方案 A：只迁移索引记录

只迁移索引表的初始化、写入和读取，历史 SQL 继续留在服务中。改动最小，但会保留已经明确识别出的持久化职责混杂，并需要后续再次拆分。

### 方案 B：统一 PageIndex 持久化仓储（采用）

使用单一仓储统一管理 PageIndex 表结构、索引记录和问答历史。服务保留业务校验、检索编排与公开接口。

优点：

- 一次形成清晰的 PageIndex 数据访问边界；
- 不新增第五类“历史仓储”模块；
- 可直接测试 SQL 范围、事务和错误转换；
- 服务删除的代码多于仓储新增代码，避免文件和代码膨胀。

代价：

- 本批次需要同步调整较多直接调用私有索引读取方法的测试；
- 服务初始化会新增一个明确的仓储依赖。

### 方案 C：并入通用 `src/db/repositories.py`

可以减少一个文件，但会把 PageIndex 专用表结构、兼容升级和历史 JSON 约定塞入已经较大的通用仓储文件，增加跨领域耦合，因此不采用。

## 3. 模块边界

### 3.1 新增 `src/pageindex/index_repository.py`

文件只定义一个生产类：

```python
class PageIndexRepository:
    def __init__(self, database_path: Path) -> None: ...
```

该类只依赖：

- SQLite 标准库；
- `src.db.connection.create_connection`；
- `src.db.transaction.transaction`；
- `src.common.errors.DatabaseAppError`。

它不依赖 `PageIndexService`、LLM、RetrievalService、模板、工作区文件或 UI。

### 3.2 仓储公开方法

采用与现有业务操作一一对应的显式方法，不引入通用查询构造器或 Repository 基类：

```python
initialize_schema() -> None
upsert_index_record(...) -> None
get_index_record(knowledge_base_id, doc_uid) -> dict | None
list_index_records(knowledge_base_id) -> list[dict]
insert_query_history(...) -> None
list_query_history(knowledge_base_id, doc_uid, limit) -> list[dict]
list_knowledge_base_query_history(knowledge_base_id, limit) -> list[dict]
get_query_history_record(knowledge_base_id, doc_uid, query_id) -> dict | None
get_knowledge_base_query_history_record(knowledge_base_id, query_id) -> dict | None
```

仓储返回普通字典或 `None`，不抛业务范围的 `NotFoundAppError`。这样，数据库访问与用户业务语义不会混在同一层。

### 3.3 继续留在 `PageIndexService` 的职责

以下内容不迁移：

- `list_available_documents()`、`_get_document()` 和 `_update_document_source_path()`：它们属于文档主表与文件路径修复，不属于 PageIndex 自有表；
- 知识库、文档和查询 ID 的输入校验；
- 未构建索引、未找到历史等 `NotFoundAppError`；
- 工作区路径计算和源文件处理；
- PageIndex 树读取、文档路由、检索预算、证据合并和回答；
- 历史 JSON 解析和 Markdown 格式化。

`PageIndexService.upsert_index_record()` 是现有公开服务接口，继续保留并委托仓储。两个私有读取包装方法则直接删除。

## 4. 数据流

### 4.1 初始化

```text
PageIndexService.__init__
    -> PageIndexRepository(database_path)
    -> repository.initialize_schema()
```

现有两个表、两个索引和 `debug_json` 兼容列逻辑原样迁移。不会新增表、列、索引或独立迁移命令。

### 4.2 索引写入与读取

```text
build_index / public upsert_index_record
    -> 服务校验知识库、文档和 PageIndex 文档 ID
    -> 服务计算 workspace_path 与时间
    -> repository.upsert_index_record

get_tree_rows / ask_question
    -> 服务校验知识库与文档 ID
    -> repository.get_index_record
    -> 服务处理 None 并抛 NotFoundAppError
    -> 原树读取或问答流程

ask_knowledge_base_question
    -> 服务校验知识库 ID
    -> repository.list_index_records
    -> 原文档路由与回答流程
```

### 4.3 历史写入与导出

```text
ask_question / ask_knowledge_base_question
    -> 原检索与回答流程
    -> 服务生成 query_id、created_at 和 JSON 字符串
    -> repository.insert_query_history

公开历史查询方法
    -> 服务校验输入
    -> repository 读取普通字典
    -> history_export.parse_history_rows
    -> 原返回结构或 Markdown 导出
```

`history_export.parse_history_rows()` 的输入类型从 SQLite 专用 `list[sqlite3.Row]` 放宽为普通映射序列，使导出模块不依赖仓储实现。

## 5. 事务与异常处理

### 5.1 事务

以下操作继续通过 `transaction(database_path)` 执行：

- 创建 PageIndex 表、索引和兼容列；
- upsert 索引记录；
- 写入问答历史。

读取使用 `create_connection(database_path)`。该统一连接入口已经启用外键、WAL 和 `synchronous=NORMAL`。

### 5.2 错误边界

仓储捕获 `sqlite3.DatabaseError`，转换为带原始 `reason` 的 `DatabaseAppError`。已有读取错误文案保持不变：

- `读取 PageIndex 索引记录失败`；
- `读取 PageIndex 历史失败`；
- `读取 PageIndex 历史记录失败`。

表初始化、索引写入和历史写入补充明确的结构化错误文案：

- `初始化 PageIndex 元数据表失败`；
- `写入 PageIndex 索引记录失败`；
- `写入 PageIndex 问答历史失败`。

服务继续负责 `ValidationAppError` 与 `NotFoundAppError`，仓储不解释业务权限或范围。

## 6. 代码迁移范围

从 `PageIndexService` 迁出：

- `_ensure_tables()`；
- `_ensure_pageindex_history_debug_column()`；
- `upsert_index_record()` 内的 SQL 与事务；
- 两个问答方法中的历史 INSERT；
- 四个公开历史读取方法中的 SQL；
- `_get_index_record()`；
- `_list_index_records()`。

从服务删除 `_get_index_record()` 和 `_list_index_records()` 后，内部调用直接使用 `self.index_repository`。测试同步改用仓储或公开服务行为，不在生产代码中保留兼容别名。

本批次不迁移文档主表访问，不拆树检索或回答编排，不修改领域词表，不改变数据库 schema。

## 7. 测试设计

### 7.1 TDD 直接测试

新增 `tests/unit/test_pageindex_repository.py`，至少覆盖：

1. 初始化能创建 PageIndex 索引表、历史表及 `debug_json`；
2. 索引 upsert 能更新同一知识库/文档记录，并保持不同知识库范围隔离；
3. 单条与知识库范围索引查询返回原字段；
4. 历史写入、文档范围列表、知识库范围列表和单条读取保持排序与 limit 语义；
5. 数据库错误转换为对应 `DatabaseAppError`；
6. 所有写操作通过事务完成。

### 7.2 服务回归

现有 `test_pageindex_service.py`、`test_pageindex_ui.py` 和 PageIndex 集成测试继续验证：

- 公开方法签名和返回结构；
- 知识库/文档范围隔离；
- 索引过期判断；
- 历史解析、导出和问答保存；
- PageIndex 检索与回答行为不变。

### 7.3 质量门禁

在 `tests/unit/test_quality_gates.py` 增加 AST/源码门禁：

- `PageIndexService` 不再定义 `_get_index_record` 或 `_list_index_records`；
- `service.py` 不再包含 `pageindex_indexes` 或 `pageindex_query_history` SQL 表名；
- 新仓储不依赖 `src.pageindex.service`。

代码净变化在验收记录中通过 Git diff 与物理行数核对，不把易碎的固定行数写入自动化测试。

## 8. 验收标准

- 新仓储直接测试先 Red 后 Green；
- `PageIndexService` 不包含 PageIndex 自有表 SQL；
- 两个私有读取包装层已删除；
- PageIndex 公开服务接口、检索算法和返回数据保持兼容；
- 写操作均使用事务，数据库异常均为结构化应用错误；
- 服务持久化职责和方法数下降，不增加 Repository 基类、Factory、额外配置或平行兼容层；
- Ruff、PageIndex/质量门禁聚焦测试、Mypy、完整 Pytest、build 和 compileall 全部通过；
- 变更同步到 `todo.md`、changelog、acceptance、代码质量审计、成熟度评估和 `chat_history.md`；
- 不执行外部 API、数据库迁移、正式索引重建、部署、commit 或 push。

## 9. 回滚边界

本批次只迁移代码职责，不改变现有数据库结构和运行数据。若验证失败，回滚新仓储接入和对应测试即可；无需恢复数据库或索引。

## 10. 实施偏差记录

迁移后 `PageIndexService` 减少 188 行和 4 个方法，新仓储为 289 行、11 个方法，生产代码合计增加 101 行，没有达到设计阶段“合计净减少”的期望。增加部分来自九个显式仓储接口、三类写事务和所有入口的数据库异常转换；服务已无 PageIndex 自有表 SQL，且没有保留兼容包装层。

本次不通过压缩 SQL、引入通用查询构造器或减少异常处理来追求物理行数。后续拆分继续以职责门禁、服务复杂度和生产代码总量三项共同判断，避免只优化单一行数指标。

