"""程序说明：验证 PageIndex 持久化仓储的表结构、范围隔离与读写契约。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.common.errors import DatabaseAppError
from src.db.connection import create_connection, initialize_database
from src.db.transaction import transaction
from src.pageindex.index_repository import PageIndexRepository


def _prepare_database(tmp_path: Path) -> Path:
    """创建包含两个知识库和两篇文档的临时数据库。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    now = "2026-07-18T00:00:00+00:00"
    with transaction(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO knowledge_bases (
                knowledge_base_id,
                knowledge_base_name,
                description,
                status,
                is_default,
                created_at,
                updated_at
            )
            VALUES (?, ?, '', 'active', 0, ?, ?)
            """,
            [
                ("kb_alpha", "Alpha", now, now),
                ("kb_beta", "Beta", now, now),
            ],
        )
        connection.executemany(
            """
            INSERT INTO documents (
                doc_uid,
                knowledge_base_id,
                doc_id,
                doc_title,
                source_path,
                source_hash,
                ingest_status,
                index_status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'completed', 'ready', ?, ?)
            """,
            [
                ("doc_alpha", "kb_alpha", "alpha", "Alpha", "kb_alpha/alpha.md", "hash_alpha_v2", now, now),
                (
                    "doc_alpha_2",
                    "kb_alpha",
                    "alpha_2",
                    "Alpha 2",
                    "kb_alpha/alpha_2.md",
                    "hash_alpha_2",
                    now,
                    now,
                ),
                ("doc_beta", "kb_beta", "beta", "Beta", "kb_beta/beta.md", "hash_beta", now, now),
            ],
        )
    return database_path


def test_pageindex_repository_should_initialize_owned_schema(tmp_path: Path) -> None:
    """仓储初始化必须创建索引表、历史表和现有 debug 兼容列。"""

    database_path = _prepare_database(tmp_path)

    PageIndexRepository(database_path).initialize_schema()

    with create_connection(database_path) as connection:
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'pageindex_%'"
            ).fetchall()
        }
        history_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(pageindex_query_history)").fetchall()
        }
    assert tables == {"pageindex_indexes", "pageindex_query_history"}
    assert "debug_json" in history_columns


def test_pageindex_repository_should_upsert_and_scope_index_records(tmp_path: Path) -> None:
    """索引 upsert 必须更新同一范围记录，且查询不能跨知识库。"""

    database_path = _prepare_database(tmp_path)
    repository = PageIndexRepository(database_path)
    repository.initialize_schema()

    repository.upsert_index_record(
        knowledge_base_id="kb_alpha",
        doc_uid="doc_alpha",
        pageindex_doc_id="page_alpha_v1",
        workspace_path="workspace/alpha",
        source_hash="hash_alpha_v1",
        created_at="2026-07-18T00:00:00+00:00",
        updated_at="2026-07-18T00:00:00+00:00",
    )
    repository.upsert_index_record(
        knowledge_base_id="kb_alpha",
        doc_uid="doc_alpha",
        pageindex_doc_id="page_alpha_v2",
        workspace_path="workspace/alpha",
        source_hash="hash_alpha_v2",
        created_at="2026-07-18T00:00:00+00:00",
        updated_at="2026-07-18T01:00:00+00:00",
    )
    repository.upsert_index_record(
        knowledge_base_id="kb_beta",
        doc_uid="doc_beta",
        pageindex_doc_id="page_beta",
        workspace_path="workspace/beta",
        source_hash="hash_beta",
        created_at="2026-07-18T00:00:00+00:00",
        updated_at="2026-07-18T00:30:00+00:00",
    )

    record = repository.get_index_record("kb_alpha", "doc_alpha")
    assert record is not None
    assert record["pageindex_doc_id"] == "page_alpha_v2"
    assert record["source_hash"] == "hash_alpha_v2"
    assert record["current_source_hash"] == "hash_alpha_v2"
    assert repository.get_index_record("kb_beta", "doc_alpha") is None
    assert [item["doc_uid"] for item in repository.list_index_records("kb_alpha")] == ["doc_alpha"]


def test_pageindex_repository_should_store_and_scope_query_history(tmp_path: Path) -> None:
    """历史查询必须保持文档/知识库范围、倒序和 limit 语义。"""

    database_path = _prepare_database(tmp_path)
    repository = PageIndexRepository(database_path)
    repository.initialize_schema()
    for knowledge_base_id, doc_uid in (
        ("kb_alpha", "doc_alpha"),
        ("kb_alpha", "doc_alpha_2"),
        ("kb_beta", "doc_beta"),
    ):
        repository.upsert_index_record(
            knowledge_base_id=knowledge_base_id,
            doc_uid=doc_uid,
            pageindex_doc_id=f"page_{doc_uid}",
            workspace_path=f"workspace/{doc_uid}",
            source_hash=f"hash_{doc_uid}",
            created_at="2026-07-18T00:00:00+00:00",
            updated_at="2026-07-18T00:00:00+00:00",
        )

    history_rows = (
        ("piq_alpha", "kb_alpha", "doc_alpha", "问题 A", "回答 A", "2026-07-18T00:00:00+00:00"),
        ("piq_alpha_2", "kb_alpha", "doc_alpha_2", "问题 A2", "回答 A2", "2026-07-18T01:00:00+00:00"),
        ("piq_beta", "kb_beta", "doc_beta", "问题 B", "回答 B", "2026-07-18T02:00:00+00:00"),
    )
    for query_id, knowledge_base_id, doc_uid, question, answer, created_at in history_rows:
        repository.insert_query_history(
            query_id=query_id,
            knowledge_base_id=knowledge_base_id,
            doc_uid=doc_uid,
            question=question,
            answer=answer,
            evidence_json="[]",
            debug_json="{}",
            created_at=created_at,
        )

    document_history = repository.list_query_history("kb_alpha", "doc_alpha", 50)
    knowledge_base_history = repository.list_knowledge_base_query_history("kb_alpha", 1)

    assert [item["query_id"] for item in document_history] == ["piq_alpha"]
    assert [item["query_id"] for item in knowledge_base_history] == ["piq_alpha_2"]
    assert repository.get_query_history_record("kb_alpha", "doc_alpha", "piq_alpha") is not None
    assert repository.get_query_history_record("kb_alpha", "doc_alpha_2", "piq_alpha") is None
    assert repository.get_knowledge_base_query_history_record("kb_alpha", "piq_alpha_2") is not None
    assert repository.get_knowledge_base_query_history_record("kb_beta", "piq_alpha_2") is None


@pytest.mark.parametrize(
    ("method_name", "args", "kwargs", "expected_message"),
    [
        ("initialize_schema", (), {}, "初始化 PageIndex 元数据表失败"),
        (
            "upsert_index_record",
            (),
            {
                "knowledge_base_id": "kb_alpha",
                "doc_uid": "doc_alpha",
                "pageindex_doc_id": "page_alpha",
                "workspace_path": "workspace/alpha",
                "source_hash": "hash_alpha",
                "created_at": "2026-07-18T00:00:00+00:00",
                "updated_at": "2026-07-18T00:00:00+00:00",
            },
            "写入 PageIndex 索引记录失败",
        ),
        ("get_index_record", ("kb_alpha", "doc_alpha"), {}, "读取 PageIndex 索引记录失败"),
        ("list_index_records", ("kb_alpha",), {}, "读取 PageIndex 索引记录失败"),
        (
            "insert_query_history",
            (),
            {
                "query_id": "piq_alpha",
                "knowledge_base_id": "kb_alpha",
                "doc_uid": "doc_alpha",
                "question": "问题",
                "answer": "回答",
                "evidence_json": "[]",
                "debug_json": "{}",
                "created_at": "2026-07-18T00:00:00+00:00",
            },
            "写入 PageIndex 问答历史失败",
        ),
        ("list_query_history", ("kb_alpha", "doc_alpha", 50), {}, "读取 PageIndex 历史失败"),
        ("list_knowledge_base_query_history", ("kb_alpha", 50), {}, "读取 PageIndex 历史失败"),
        (
            "get_query_history_record",
            ("kb_alpha", "doc_alpha", "piq_alpha"),
            {},
            "读取 PageIndex 历史记录失败",
        ),
        (
            "get_knowledge_base_query_history_record",
            ("kb_alpha", "piq_alpha"),
            {},
            "读取 PageIndex 历史记录失败",
        ),
    ],
)
def test_pageindex_repository_should_convert_database_errors(
    tmp_path: Path,
    method_name: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    expected_message: str,
) -> None:
    """每个仓储入口都必须把 SQLite 失败转换为结构化应用错误。"""

    repository = PageIndexRepository(tmp_path / "missing" / "app.db")

    with pytest.raises(DatabaseAppError) as exc_info:
        getattr(repository, method_name)(*args, **kwargs)

    assert exc_info.value.message == expected_message
    assert exc_info.value.details.get("reason")

