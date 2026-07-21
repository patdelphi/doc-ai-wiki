# P1 PageIndex 历史导出职责迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本项目禁止使用 Subagent。

**Goal:** 将八个无状态的 PageIndex 历史解析与 Markdown 格式化方法迁入独立模块，同时保持数据库访问、公开接口和导出内容不变。

**Architecture:** 新建 `src/pageindex/history_export.py` 承载两个公开纯函数与六个模块私有 helper。`PageIndexService` 继续校验范围和执行参数化 SQL，只把数据库行与规范化历史交给新模块；迁移后删除类内旧方法，不保留包装层。

**Tech Stack:** Python 3.11+、SQLite、Pytest、Ruff、Mypy。

## Global Constraints

- 不改变 PageIndex 检索、路由、Question Plan、预算、证据判断和回答算法。
- 不改变 `PageIndexService` 公开历史查询/导出方法签名、Markdown 文案与字段顺序。
- 不新增第三方依赖、类层级、配置项、数据库表或索引格式。
- 测试不调用真实 LLM、Embedding、Rerank、PageIndex vendor 或外部 API。
- 不重建索引，不执行数据库迁移、部署、commit、push、merge 或 pull。
- 修改的 Python 与 Markdown 使用 UTF-8 BOM + CRLF。

---

### Task 1：建立纯历史导出模块的失败测试

**Files:**

- Create: `tests/unit/test_pageindex_history_export.py`
- Modify: `tests/unit/test_quality_gates.py`

**Interfaces:**

- Consumes: SQLite `sqlite3.Row` 与规范化历史字典。
- Produces: 对 `parse_history_rows()`、`format_history_markdown()` 和类职责边界的回归门禁。

- [x] **Step 1：新增直接单测**

新建测试文件，使用以下内存行 helper 与断言：

```python
"""程序说明：直接验证 PageIndex 历史行解析与 Markdown 导出纯函数。"""

from __future__ import annotations

import sqlite3

from src.pageindex.history_export import format_history_markdown, parse_history_rows


def build_history_row(*, evidence_json: str, debug_json: str) -> sqlite3.Row:
    """构建不依赖项目数据库的 SQLite 历史行。"""

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    return connection.execute(
        """
        SELECT
            'query_1' AS query_id,
            'kb_alpha' AS knowledge_base_id,
            'doc_alpha' AS doc_uid,
            '阿胶是什么' AS question,
            '{"结论":"属于中药材","依据":["原文证据"]}' AS answer,
            ? AS evidence_json,
            ? AS debug_json,
            '2026-07-18T00:00:00+00:00' AS created_at
        """,
        (evidence_json, debug_json),
    ).fetchone()


def test_parse_history_rows_should_decode_evidence_and_debug() -> None:
    row = build_history_row(
        evidence_json='[{"title":"第一章","position":"1.1","content":"证据内容"}]',
        debug_json='{"question_plan":{"question_type":"fact"}}',
    )

    items = parse_history_rows([row])

    assert items[0]["evidence"][0]["title"] == "第一章"
    assert items[0]["debug"]["question_plan"]["question_type"] == "fact"
    assert "evidence_json" not in items[0]
    assert "debug_json" not in items[0]


def test_parse_history_rows_should_fallback_for_invalid_json() -> None:
    items = parse_history_rows([build_history_row(evidence_json="invalid", debug_json="invalid")])

    assert items[0]["evidence"] == []
    assert items[0]["debug"] == {}


def test_format_history_markdown_should_keep_structured_answer_and_evidence() -> None:
    item = parse_history_rows(
        [
            build_history_row(
                evidence_json='[{"title":"第一章","position":"1.1","content":"证据内容"}]',
                debug_json='{"question_plan":{"question_type":"fact"}}',
            )
        ]
    )[0]

    markdown = format_history_markdown(
        knowledge_base_id="kb_alpha",
        doc_uid="doc_alpha",
        history=[item],
    )

    assert "# PageIndex 深度检索导出" in markdown
    assert "#### 结论" in markdown
    assert "- 原文证据" in markdown
    assert "问题类型：fact" in markdown
    assert "#### 第一章" in markdown
    assert "证据内容" in markdown


def test_format_history_markdown_should_preserve_python_dict_and_empty_fallbacks() -> None:
    history = [
        {
            "created_at": "2026-07-18T00:00:00+00:00",
            "question": "问题",
            "answer": "{'结论': '保留', '自定义字段': {'来源': '原文'}}",
            "evidence": [],
            "debug": {},
        },
        {"created_at": "", "question": "空回答", "answer": "", "evidence": [], "debug": {}},
    ]

    markdown = format_history_markdown(
        knowledge_base_id="kb_alpha",
        doc_uid="doc_alpha",
        history=history,
    )

    assert "#### 自定义字段" in markdown
    assert "- **来源**：原文" in markdown
    assert "暂无回答" in markdown
    assert "暂无证据" in markdown
```

- [x] **Step 2：增加 AST 职责门禁**

在 `tests/unit/test_quality_gates.py` 增加：

```python
def test_pageindex_service_should_not_own_history_export_formatters() -> None:
    """PageIndex 巨型服务不得重新吸收已迁移的历史导出纯函数。"""

    project_root = Path(__file__).resolve().parents[2]
    source = (project_root / "src" / "pageindex" / "service.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    service_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PageIndexService"
    )
    method_names = {
        node.name
        for node in service_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    migrated_methods = {
        "_parse_history_rows",
        "_format_history_markdown",
        "_format_history_answer_markdown",
        "_parse_structured_answer",
        "_format_markdown_value",
        "_format_markdown_list_item",
        "_stringify_markdown_scalar",
        "_history_question_type",
    }

    assert method_names.isdisjoint(migrated_methods)
```

- [x] **Step 3：运行 Red 测试**

Run:

```powershell
python -m pytest "tests/unit/test_pageindex_history_export.py" "tests/unit/test_quality_gates.py::test_pageindex_service_should_not_own_history_export_formatters" -q
```

Expected: 收集阶段因 `src.pageindex.history_export` 不存在而失败；创建空模块后 AST 门禁仍因旧方法存在而失败。

---

### Task 2：实现纯历史导出模块

**Files:**

- Create: `src/pageindex/history_export.py`
- Test: `tests/unit/test_pageindex_history_export.py`

**Interfaces:**

- Produces: `parse_history_rows(rows: list[sqlite3.Row]) -> list[dict]`。
- Produces: `format_history_markdown(*, knowledge_base_id: str, doc_uid: str, history: list[dict]) -> str`。

- [x] **Step 1：新增最小完整模块**

实现以下模块；两个无下划线函数是服务层调用接口，其余 helper 保持模块私有：

```python
"""程序说明：解析 PageIndex 历史数据库行并格式化 Markdown 导出内容。"""

from __future__ import annotations

import ast
import json
import sqlite3


def parse_history_rows(rows: list[sqlite3.Row]) -> list[dict]:
    """将 PageIndex 历史查询行转换为规范化字典。"""

    items: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            evidence = json.loads(str(item.pop("evidence_json") or "[]"))
        except json.JSONDecodeError:
            evidence = []
        try:
            debug = json.loads(str(item.pop("debug_json", "{}") or "{}"))
        except json.JSONDecodeError:
            debug = {}
        item["evidence"] = evidence if isinstance(evidence, list) else []
        item["debug"] = debug if isinstance(debug, dict) else {}
        items.append(item)
    return items


def format_history_markdown(*, knowledge_base_id: str, doc_uid: str, history: list[dict]) -> str:
    """格式化 PageIndex 历史导出内容，供全量与单条导出复用。"""

    lines = [
        "# PageIndex 深度检索导出",
        "",
        f"- 知识库：{knowledge_base_id}",
        f"- 文档：{doc_uid}",
        "",
    ]
    for index, item in enumerate(history, start=1):
        lines.extend(
            [
                f"## 记录 {index}",
                "",
                f"- 时间：{item.get('created_at', '')}",
                f"- 问题：{item.get('question', '')}",
                "",
                "### 回答",
                "",
            ]
        )
        lines.extend(_format_history_answer_markdown(str(item.get("answer") or "")))
        lines.extend(
            [
                "",
                "### 调试信息",
                "",
                f"- 问题类型：{_history_question_type(item)}",
                "",
                "### 证据",
                "",
            ]
        )
        evidence_items = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        if not evidence_items:
            lines.extend(["- 暂无证据", ""])
            continue
        for evidence in evidence_items:
            lines.extend(
                [
                    f"#### {evidence.get('title', '')}",
                    "",
                    f"- 位置：{evidence.get('position', '')}",
                    "",
                    str(evidence.get("content") or evidence.get("summary") or ""),
                    "",
                ]
            )
    return "\n".join(lines).strip()


def _format_history_answer_markdown(answer: str) -> list[str]:
    """将历史答案格式化为 Markdown；兼容 LLM 返回的 dict 字符串。"""

    normalized_answer = str(answer or "").strip()
    structured_answer = _parse_structured_answer(normalized_answer)
    if not structured_answer:
        return [normalized_answer] if normalized_answer else ["暂无回答"]

    ordered_keys = ["结论", "证据判断", "依据", "来源", "不确定点"]
    lines: list[str] = []
    for key in ordered_keys:
        if key not in structured_answer:
            continue
        lines.extend([f"#### {key}", ""])
        lines.extend(_format_markdown_value(structured_answer.get(key)))
        lines.append("")
    for key in (key for key in structured_answer if key not in ordered_keys):
        lines.extend([f"#### {key}", ""])
        lines.extend(_format_markdown_value(structured_answer.get(key)))
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines or ["暂无回答"]


def _parse_structured_answer(answer: str) -> dict | None:
    """解析 JSON 或 Python dict 字符串答案；失败时返回 None 保持原文。"""

    text = str(answer or "").strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            payload = parser(text)
        except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _format_markdown_value(value: object) -> list[str]:
    """将结构化字段值转换成 Markdown 段落或列表。"""

    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            lines.extend(_format_markdown_list_item(item))
        return lines or ["- 无"]
    if isinstance(value, dict):
        return [f"- **{key}**：{_stringify_markdown_scalar(item)}" for key, item in value.items()] or ["- 无"]
    text = str(value or "").strip()
    return text.splitlines() if text else ["无"]


def _format_markdown_list_item(item: object) -> list[str]:
    """将列表项转换为 Markdown，支持列表中嵌套 dict。"""

    if isinstance(item, dict):
        return [
            f"{'- ' if index == 0 else '  '}**{key}**：{_stringify_markdown_scalar(value)}"
            for index, (key, value) in enumerate(item.items())
        ]
    if isinstance(item, list):
        return [f"- {_stringify_markdown_scalar(value)}" for value in item]
    text = str(item or "").strip()
    return [f"- {text}"] if text else []


def _stringify_markdown_scalar(value: object) -> str:
    """把嵌套标量转换为 Markdown 友好的字符串。"""

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "").strip()


def _history_question_type(item: dict) -> str:
    """从历史 debug 中读取 Question Plan 类型，供导出排查使用。"""

    debug = item.get("debug") if isinstance(item.get("debug"), dict) else {}
    question_plan = debug.get("question_plan") if isinstance(debug.get("question_plan"), dict) else {}
    return str(question_plan.get("question_type") or "unknown")
```

- [x] **Step 2：运行直接单测**

Run:

```powershell
python -m pytest "tests/unit/test_pageindex_history_export.py" -q
```

Expected: 四项直接测试通过。

---

### Task 3：接入 PageIndexService 并删除旧方法

**Files:**

- Modify: `src/pageindex/service.py:1-675`
- Modify: `tests/unit/test_quality_gates.py`
- Test: `tests/unit/test_pageindex_service.py`

**Interfaces:**

- Consumes: `parse_history_rows()`、`format_history_markdown()`。
- Preserves: `list_query_history()`、`list_knowledge_base_query_history()`、`get_query_history_record()`、`get_knowledge_base_query_history_record()`、`export_query_markdown()`、`export_knowledge_base_query_markdown()`、`export_history_markdown()`。

- [x] **Step 1：替换服务内部调用**

在 `src/pageindex/service.py` 删除只为旧格式化方法使用的 `ast` 导入，新增：

```python
from src.pageindex.history_export import format_history_markdown, parse_history_rows
```

将调用统一替换为：

```python
return parse_history_rows(rows)
```

单条记录解析改为：

```python
items = parse_history_rows([row])
return items[0]
```

三个导出方法改为：

```python
return format_history_markdown(
    knowledge_base_id=resolved_knowledge_base_id,
    doc_uid=resolved_doc_uid,
    history=history,
)
```

- [x] **Step 2：删除八个类内旧方法**

删除 `_parse_history_rows()`、`_format_history_markdown()`、`_format_history_answer_markdown()`、`_parse_structured_answer()`、`_format_markdown_value()`、`_format_markdown_list_item()`、`_stringify_markdown_scalar()`、`_history_question_type()`；不保留委托 wrapper。

- [x] **Step 3：运行职责门禁与 PageIndex 回归**

Run:

```powershell
python -m pytest "tests/unit/test_pageindex_history_export.py" "tests/unit/test_quality_gates.py" "tests/unit/test_pageindex_service.py" -q
```

Expected: 新模块、AST 门禁与既有 PageIndex 服务测试全部通过。

- [x] **Step 4：运行聚焦静态检查**

Run:

```powershell
python -m ruff check "src/pageindex/history_export.py" "src/pageindex/service.py" "tests/unit/test_pageindex_history_export.py" "tests/unit/test_quality_gates.py"
python -m mypy "src/pageindex/history_export.py" "src/pageindex/service.py"
```

Expected: 两个命令退出码均为 0；PageIndex 服务的既有 Mypy 豁免不因本批次扩大。

---

### Task 4：文档与完整验收

**Files:**

- Modify: `todo.md`
- Modify: `Docs/changelog/retrieval_pageindex_20260716.md`
- Modify: `Docs/acceptance.MD`
- Modify: `Docs/optimization-plan/vibe_coding_code_quality_audit_20260716.md`
- Modify: `Docs/optimization-plan/knowledge_base_maturity_assessment_20260716.md`
- Modify: `chat_history.md`

**Interfaces:**

- Produces: 本批次范围、服务行数变化、验证结果与未迁移职责的可审计记录。

- [x] **Step 1：同步项目文档**

记录八个迁移方法、`service.py` 净减少行数、直接测试数量、完整测试结果，以及历史 SQL/写入仍留在服务中的事实；不得把本批次描述为 PageIndex 服务拆分全部完成。

- [x] **Step 2：运行完整质量门禁**

Run:

```powershell
python -m ruff check src tests .aipython Docs/migrations
python -m mypy src/retrieval src/pageindex src/quality/service.py
python -m pytest tests --maxfail=1 -q
python -m build
python -m compileall -q src tests .aipython Docs/migrations
```

Expected: 所有命令退出码为 0；测试不访问外部模型。

- [x] **Step 3：验证格式与差异**

验证本批次 Python/Markdown 均为 UTF-8 BOM + CRLF；排除三份既有行尾噪声文档后运行：

```powershell
git diff --check -- . ":(exclude)Docs/evidence_catalog_20260620.md" ":(exclude)Docs/pageindex-llm-evaluation-20260618.md" ":(exclude)Docs/retrieval_alignment_suggestions_20260621.md"
```

Expected: 退出码为 0。

- [x] **Step 4：保持 Git 与外部操作边界**

报告工作区状态；不执行 commit、push、索引重建、数据库迁移、部署或外部 API，等待用户单独确认。
