"""程序说明：验证检索服务在不同 SQLite 环境下的兜底行为。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.db.connection import create_connection, initialize_database
from src.retrieval.service import RetrievalService


class _FakeCursor:
    """程序说明：模拟 SQLite 游标返回 fetchall 结果。"""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict]:
        return self._rows


class _FakeConnection:
    """程序说明：首个 FTS 查询抛错，后续 LIKE 查询正常返回。"""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.executed_sql: list[str] = []

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, sql: str, params: tuple) -> _FakeCursor:
        self.executed_sql.append(sql)
        if "MATCH ?" in sql:
            raise sqlite3.OperationalError('fts5: syntax error near "?"')
        return _FakeCursor(self._rows)


def test_fulltext_search_should_fallback_to_like_when_fts_match_binding_fails(monkeypatch) -> None:
    """FTS5 参数查询失败时，应自动回退到 LIKE，避免中断上层质检链路。"""

    fake_rows = [
        {
            "chunk_id": "chunk_1",
            "doc_uid": "doc_1",
            "doc_title": "测试文档",
            "author": "测试作者",
            "source_name": "sample.MD",
            "tags_json": '["检索"]',
            "source_span": "section-1:chunk-0",
            "heading_path": "总论 > 产地",
            "source_start_line": 3,
            "source_end_line": 6,
            "page_no": None,
            "chunk_type": "paragraph",
            "content_hash": "a" * 64,
            "source_anchor": "L3-L6",
            "content": "东阿相关内容",
        }
    ]
    fake_connection = _FakeConnection(fake_rows)
    monkeypatch.setattr(
        "src.retrieval.service.create_connection",
        lambda database_path: fake_connection,
    )

    service = RetrievalService("unused.db")
    items = service.fulltext_search("东阿", top_k=5, knowledge_base_id="default")

    assert len(fake_connection.executed_sql) == 2
    assert "MATCH ?" in fake_connection.executed_sql[0]
    assert "content LIKE ?" in fake_connection.executed_sql[1]
    assert len(items) == 1
    assert items[0]["doc_title"] == "测试文档"
    assert items[0]["retrieval_source"] == "fulltext"
    assert items[0]["tags"] == ["检索"]
    assert items[0]["heading_path"] == "总论 > 产地"
    assert items[0]["source_start_line"] == 3
    assert items[0]["source_end_line"] == 6
    assert items[0]["chunk_type"] == "paragraph"
    assert items[0]["content_hash"] == "a" * 64
    assert items[0]["source_anchor"] == "L3-L6"


def test_fulltext_search_should_return_traceability_fields_from_sqlite(tmp_path: Path) -> None:
    """真实 SQLite 检索结果应带出 chunk 级追溯字段。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    now = "2026-06-20T00:00:00+00:00"
    with create_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                doc_uid, knowledge_base_id, doc_id, doc_title, source_path, source_hash,
                ingest_status, index_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("doc_1", "default", "doc_1", "追溯文档", "default/doc.md", "hash", "completed", "indexed", now, now),
        )
        connection.execute(
            """
            INSERT INTO document_sections (
                section_id, doc_uid, section_title, section_level, heading_path,
                source_start_line, source_end_line, source_anchor, source_span,
                content, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("sec_1", "doc_1", "产地", 2, "总论 > 产地", 3, 6, "L3-L6", "section-1", "东阿相关内容", now, now),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, doc_uid, section_id, chunk_index, content, source_span,
                heading_path, source_start_line, source_end_line, page_no, chunk_type,
                content_hash, source_anchor, token_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "chunk_1",
                "doc_1",
                "sec_1",
                0,
                "东阿相关内容",
                "section-1:chunk-0",
                "总论 > 产地",
                3,
                6,
                None,
                "paragraph",
                "b" * 64,
                "L3-L6",
                6,
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO chunk_fts (chunk_id, doc_uid, content) VALUES (?, ?, ?)",
            ("chunk_1", "doc_1", "东阿相关内容"),
        )
        connection.commit()

    items = RetrievalService(database_path).fulltext_search("东阿", top_k=5)

    assert len(items) == 1
    assert items[0]["heading_path"] == "总论 > 产地"
    assert items[0]["source_start_line"] == 3
    assert items[0]["source_end_line"] == 6
    assert items[0]["chunk_type"] == "paragraph"
    assert items[0]["content_hash"] == "b" * 64
    assert items[0]["source_anchor"] == "L3-L6"
