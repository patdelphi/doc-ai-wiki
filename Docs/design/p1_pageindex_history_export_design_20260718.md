# P1 PageIndex 历史导出职责迁移设计

> 日期：2026-07-18
>
> 分支：`codex/retrieval-pageindex-optimization`
>
> 状态：已实施并通过验收

## 1. 目标

在不改变 PageIndex 查询、数据库结构、公开服务接口和导出内容的前提下，将历史记录解析与 Markdown 格式化职责从 `src/pageindex/service.py` 迁入独立的纯函数模块 `src/pageindex/history_export.py`。

本批次只拆历史导出的无状态逻辑。数据库读取、历史写入、知识库权限校验和 `PageIndexService` 的公开方法继续保留，避免把一次小步拆分扩大为仓储层重写。

## 2. 当前问题

`PageIndexService` 同时承担索引、检索编排、历史数据库访问和历史导出格式化。历史导出相关的以下八个无状态方法约占 160 行：

- `_parse_history_rows()`；
- `_format_history_markdown()`；
- `_format_history_answer_markdown()`；
- `_parse_structured_answer()`；
- `_format_markdown_value()`；
- `_format_markdown_list_item()`；
- `_stringify_markdown_scalar()`；
- `_history_question_type()`。

这些方法不依赖服务实例状态，只依赖输入行、历史数据以及标准库 `ast/json`。继续放在巨型服务中会增加理解成本，也让导出格式只能通过完整 `PageIndexService` 间接测试。

## 3. 方案比较

### 方案 A：只迁移纯解析与格式化函数（采用）

- 新建一个 `history_export.py`，提供模块级纯函数。
- `PageIndexService` 的历史查询和导出公开方法保持原签名，只调用新模块。
- 优点：最小风险、无新类、无依赖注入、可直接单测；服务文件立即减少无状态职责。
- 缺点：历史数据库访问仍在 `PageIndexService`，需要后续批次再评估是否迁移。

### 方案 B：一次迁移数据库访问与格式化

- 新建带数据库路径状态的 `PageIndexHistoryStore`。
- 优点：历史职责一次集中。
- 缺点：需要新增类、服务委托层和更多数据库测试，本批次回归范围明显扩大。

### 方案 C：直接改变调用方接口

- UI 直接调用新历史组件，不再通过 `PageIndexService`。
- 优点：服务表面更小。
- 缺点：改变公开接口与调用关系，UI、测试和未来 API 都需同步调整，不符合小步迁移原则。

选择方案 A。它能够真实降低 `PageIndexService` 的职责密度，同时不引入投机性抽象。

## 4. 模块边界

### `src/pageindex/history_export.py`

负责：

- 将 SQLite 历史行中的 `evidence_json/debug_json` 安全解析为前端字典；
- 将单条或多条 PageIndex 历史格式化为 Markdown；
- 兼容 JSON 字符串、Python dict 字符串和普通文本答案；
- 格式化嵌套列表、字典、标量和 Question Plan 类型。

不负责：

- 打开数据库连接或执行 SQL；
- 校验知识库、文档或查询 ID；
- 写入历史记录；
- 保存导出文件或生成下载链接。

### `src/pageindex/service.py`

继续负责：

- 历史记录的查询范围校验与数据库读取；
- `list_query_history()`、`get_query_history_record()` 和三个导出公开方法；
- 把数据库行交给 `parse_history_rows()`；
- 把规范化历史交给 `format_history_markdown()`。

迁移完成后删除服务类中的八个旧私有方法，不保留平行包装层。

## 5. 接口设计

新模块只暴露两个供服务调用的函数：

```python
def parse_history_rows(rows: list[sqlite3.Row]) -> list[dict]:
    """将数据库历史行解析为规范化字典。"""


def format_history_markdown(
    *,
    knowledge_base_id: str,
    doc_uid: str,
    history: list[dict],
) -> str:
    """将规范化 PageIndex 历史格式化为 Markdown。"""
```

其余格式化函数保持模块私有。新模块不持有配置、数据库路径、服务实例或全局缓存。

## 6. 数据流

```text
PageIndexService 公共方法
-> 校验 knowledge_base_id/doc_uid/query_id
-> SQLite 参数化查询
-> history_export.parse_history_rows()
-> history_export.format_history_markdown()
-> 原有字符串结果
```

UI、下载文件保存和调用方输入输出均不改变。

## 7. 错误处理

- SQL 异常继续由 `PageIndexService` 转换为 `DatabaseAppError`。
- 无历史、缺少查询 ID和记录不存在继续使用当前 `ValidationAppError/NotFoundAppError` 文案。
- 无效 `evidence_json` 继续退化为空列表；无效 `debug_json` 继续退化为空字典。
- 结构化答案解析失败时继续保留原始文本，不新增宽泛异常捕获。
- 新模块不调用外部 API，不读取环境变量，不写文件。

## 8. 测试策略

新增 `tests/unit/test_pageindex_history_export.py`，直接覆盖：

1. 正常历史行解析；
2. 无效 evidence/debug JSON 的稳定降级；
3. 普通文本与空回答；
4. JSON 和 Python dict 字符串答案；
5. 任意结构化 key 与嵌套 list/dict；
6. 有证据和无证据的 Markdown；
7. Question Plan 类型输出。

保留现有 `tests/unit/test_pageindex_service.py` 作为公开服务接口回归，并在质量门禁中用 AST 断言八个纯方法不再定义在 `PageIndexService`。

严格执行 Red-Green-Refactor；测试使用临时 SQLite 或内存行数据，不调用真实 LLM、Embedding、Rerank 或 PageIndex vendor。

## 9. 非目标

- 不迁移历史 SQL、表结构升级或历史写入；
- 不修改 PageIndex 检索、路由、Question Plan、预算、证据判断或回答算法；
- 不改变 Markdown 标题、字段顺序、中文文案和空值回退；
- 不新增第三方依赖、类层级、配置项或数据库表；
- 不重建 PageIndex、检索索引或数据库；
- 不执行外部 API、部署、commit、push、merge 或 pull。

## 10. 完成标准

- `history_export.py` 可以在不创建 `PageIndexService` 的情况下直接测试；
- 八个旧私有方法从 `PageIndexService` 删除且没有平行包装层；
- 现有公开历史查询和导出接口签名不变；
- 直接单测、PageIndex 服务测试和 AST 门禁通过；
- 扩展 Ruff、目标 Mypy、完整 Pytest、build 和 compileall 通过；
- Todo、变更记录、验收、代码质量审查和聊天历史同步更新。
