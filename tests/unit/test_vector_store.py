"""程序说明：验证 Windows 稳定本地向量索引的持久化、过滤与重建。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.common.errors import ValidationAppError
from src.db.connection import initialize_database
from src.db.transaction import transaction
from src.retrieval.vector_store import VectorStore


class StubEmbeddingClient:
    """测试用确定性 embedding 客户端。"""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            if self.dimension:
                vector[0] = 1.0 if "目标" in text else 0.0
                if self.dimension > 1:
                    vector[1] = 1.0 if "其他" in text else 0.0
            vectors.append(vector)
        return vectors


def item(chunk_id: str, content: str, *, doc_uid: str = "doc-1", kb: str = "default") -> dict:
    """构造最小合法 chunk。"""

    return {"chunk_id": chunk_id, "doc_uid": doc_uid, "knowledge_base_id": kb, "content": content}


def test_empty_store_should_initialize_without_persisting_invalid_dimension(tmp_path: Path) -> None:
    store = VectorStore(tmp_path / "chroma", embedding_client=StubEmbeddingClient(4))
    assert store.inspect_index()["total_count"] == 0
    assert store.embedding_dimension == 4


def test_store_should_persist_more_than_hnsw_flush_threshold_and_reopen(tmp_path: Path) -> None:
    """Windows 回归：写入 120 条不能触发 Chroma 原生崩溃，重开后仍完整。"""

    path = tmp_path / "chroma"
    store = VectorStore(path, embedding_client=StubEmbeddingClient(8))
    store.upsert_chunks([item(f"chunk-{index:03d}", f"内容 {index}") for index in range(120)])
    assert store.inspect_index()["total_count"] == 120
    reopened = VectorStore(path, embedding_client=StubEmbeddingClient(8))
    assert reopened.count_by_doc_uid("doc-1") == 120
    assert (path / "vectors.npz").exists()


def test_query_should_rank_and_filter_by_knowledge_base(tmp_path: Path) -> None:
    store = VectorStore(tmp_path / "chroma", embedding_client=StubEmbeddingClient(3))
    store.upsert_chunks([
        item("a", "目标", kb="medical"),
        item("b", "其他", kb="medical"),
        item("c", "目标", kb="default"),
    ])
    results = store.query("目标", knowledge_base_ids=["medical"])
    assert [result["chunk_id"] for result in results] == ["a", "b"]
    assert store.query("目标", knowledge_base_ids=[]) == []


def test_dimension_mismatch_should_be_explicit(tmp_path: Path) -> None:
    path = tmp_path / "chroma"
    VectorStore(path, embedding_client=StubEmbeddingClient(4)).upsert_chunks([item("a", "目标")])
    with pytest.raises(ValidationAppError, match="Embedding 维度与现有向量索引不一致"):
        VectorStore(path, embedding_client=StubEmbeddingClient(8))


def test_delete_and_metadata_inspection(tmp_path: Path) -> None:
    store = VectorStore(tmp_path / "chroma", embedding_client=StubEmbeddingClient(4), embedding_model="test-v2")
    store.upsert_chunks([item("a", "目标", doc_uid="doc-a"), item("b", "其他", doc_uid="doc-b", kb="medical")])
    assert store.count_by_doc_uid("doc-a") == 1
    report = store.inspect_index()
    assert report["embedding_models"] == ["test-v2"]
    assert report["embedding_dimensions"] == [4]
    store.delete_by_doc_uid("doc-a")
    assert store.inspect_index()["total_count"] == 1


def seed_chunk_database(database_path: Path) -> None:
    """写入最小 SQLite 文档与 chunk，验证全量重建继承知识库。"""

    initialize_database(database_path)
    now = "2026-05-03T19:10:00+08:00"
    with transaction(database_path) as connection:
        connection.execute(
            """INSERT INTO documents (doc_uid, knowledge_base_id, doc_id, doc_title, edition, author, source_name, tags_json, source_path, source_hash, ingest_status, index_status, error_message, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("doc-1", "default", "doc-1", "验收文档", "default", "tester", "acceptance.MD", "[]", str(database_path.parent / "acceptance.MD"), "hash", "completed", "indexed", None, now, now),
        )
        connection.execute(
            """INSERT INTO document_sections (section_id, doc_uid, section_title, section_level, source_span, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("sec-1", "doc-1", "说明", 1, "section-1", "目标", now, now),
        )
        connection.execute(
            """INSERT INTO chunks (chunk_id, doc_uid, section_id, chunk_index, content, source_span, token_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("chunk-1", "doc-1", "sec-1", 0, "目标", "section-1:chunk-1", 1, now, now),
        )


def test_rebuild_from_sqlite_should_inherit_document_knowledge_base(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    seed_chunk_database(database_path)
    store = VectorStore(tmp_path / "chroma", embedding_client=StubEmbeddingClient(4), sqlite_db_path=database_path)
    assert store.rebuild_from_sqlite() == (1, 1)
    assert store.inspect_index()["by_knowledge_base"] == {"default": 1}


def test_close_is_compatible_noop(tmp_path: Path) -> None:
    store = VectorStore(tmp_path / "chroma", embedding_client=StubEmbeddingClient(4))
    store.close()
