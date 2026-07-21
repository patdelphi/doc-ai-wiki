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
    """合法 JSON 应转换为规范化 evidence/debug 字段。"""

    row = build_history_row(
        evidence_json='[{"title":"第一章","position":"1.1","content":"证据内容"}]',
        debug_json='{"question_plan":{"question_type":"fact"}}',
    )

    items = parse_history_rows([row])

    assert items[0]["evidence"][0]["title"] == "第一章"
    assert items[0]["debug"]["question_plan"]["question_type"] == "fact"
    assert "evidence_json" not in items[0]
    assert "debug_json" not in items[0]


def test_parse_history_rows_should_accept_repository_dict_rows() -> None:
    """历史解析应接受仓储返回的普通字典，不依赖 SQLite Row。"""

    items = parse_history_rows(
        [
            {
                "query_id": "query_1",
                "knowledge_base_id": "kb_alpha",
                "doc_uid": "doc_alpha",
                "question": "问题",
                "answer": "回答",
                "evidence_json": "[]",
                "debug_json": "{}",
                "created_at": "2026-07-18T00:00:00+00:00",
            }
        ]
    )

    assert items[0]["query_id"] == "query_1"
    assert items[0]["evidence"] == []
    assert items[0]["debug"] == {}


def test_parse_history_rows_should_fallback_for_invalid_json() -> None:
    """损坏的历史 JSON 不应阻断历史列表读取。"""

    items = parse_history_rows([build_history_row(evidence_json="invalid", debug_json="invalid")])

    assert items[0]["evidence"] == []
    assert items[0]["debug"] == {}


def test_format_history_markdown_should_keep_structured_answer_and_evidence() -> None:
    """结构化回答、问题类型和证据应完整进入 Markdown。"""

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
    """Python dict 字符串、自定义字段和空值回退应保持兼容。"""

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
