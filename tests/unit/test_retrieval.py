"""程序说明：验证检索服务在不同 SQLite 环境下的兜底行为。"""

from __future__ import annotations

import sqlite3

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
