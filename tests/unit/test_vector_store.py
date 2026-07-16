"""程序说明：验证向量索引启动时的 embedding 维度自检逻辑。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.common.errors import ValidationAppError
from src.db.connection import initialize_database
from src.db.transaction import transaction
from src.retrieval.vector_store import VectorStore


class StubEmbeddingClient:
    """测试用 embedding 客户端。"""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dimension for _ in texts]


class StubCollection:
    """测试用 Chroma 集合。"""

    def __init__(self, *, ids: list[str] | None = None, embeddings: list[list[float]] | None = None) -> None:
        self._ids = ids if ids is not None else []
        self._embeddings = embeddings if embeddings is not None else []
        self._metadatas: list[dict] = []

    def peek(self, limit: int = 1) -> dict:
        return {
            "ids": self._ids[:limit],
            "embeddings": self._embeddings[:limit],
        }

    def get(self, *, ids: list[str], include: list[str]) -> dict:
        assert ids
        assert "embeddings" in include
        return {
            "ids": ids,
            "embeddings": self._embeddings[:1],
        }

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        assert len(ids) == len(documents) == len(metadatas) == len(embeddings)
        self._ids = list(ids)
        self._embeddings = [list(item) for item in embeddings]
        self._metadatas = [dict(item) for item in metadatas]

    def delete(self, *, where: dict) -> None:
        _ = where


class CountStubCollection(StubCollection):
    """测试 count_by_doc_uid() 时使用的集合桩。"""

    def __init__(self, ids_result) -> None:
        super().__init__()
        self.ids_result = ids_result

    def get(self, *, where: dict, include: list[str]) -> dict:
        assert where == {"doc_uid": "doc_1"}
        assert include == []
        return {"ids": self.ids_result}


class StubClient:
    """测试用 Chroma 客户端。"""

    def __init__(self, collection: StubCollection) -> None:
        self._collections = {"knowledge_chunks": collection}
        self.closed = False

    def get_or_create_collection(self, *, name: str) -> StubCollection:
        assert name == "knowledge_chunks"
        return self._collections.setdefault(name, StubCollection())

    def delete_collection(self, *, name: str) -> None:
        self._collections.pop(name, None)

    def close(self) -> None:
        """记录客户端句柄已释放。"""

        self.closed = True


class RaisingLegacyConfigClient(StubClient):
    """测试用客户端：首次打开集合时模拟旧版 Chroma 配置格式异常。"""

    def __init__(self, collection: StubCollection) -> None:
        super().__init__(collection)
        self._raised = False

    def get_or_create_collection(self, *, name: str) -> StubCollection:
        if not self._raised:
            self._raised = True
            raise KeyError("_type")
        return super().get_or_create_collection(name=name)


def seed_chunk_database(database_path: Path) -> None:
    """写入最小 chunk 记录，供自动修复重建向量集合。"""

    initialize_database(database_path)
    now = "2026-05-03T19:10:00+08:00"
    with transaction(database_path) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                doc_uid, knowledge_base_id, doc_id, doc_title, edition, author, source_name, tags_json, source_path,
                source_hash, ingest_status, index_status, error_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc_1",
                "default",
                "doc_1",
                "维度修复验收文档",
                "default",
                "tester",
                "acceptance.MD",
                "[]",
                str(database_path.parent / "acceptance.MD"),
                "hash-doc-1",
                "completed",
                "indexed",
                None,
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO document_sections (
                section_id, doc_uid, section_title, section_level, source_span, content, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sec_1",
                "doc_1",
                "说明",
                1,
                "section-1",
                "阿胶并非只有东阿可生产。",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, doc_uid, section_id, chunk_index, content, source_span, token_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "chunk_1",
                "doc_1",
                "sec_1",
                0,
                "阿胶并非只有东阿可生产。",
                "section-1:chunk-1",
                14,
                now,
                now,
            ),
        )


def test_vector_store_should_allow_empty_collection_without_dimension_conflict(monkeypatch, tmp_path: Path) -> None:
    """空集合启动时不应触发维度冲突。"""

    collection = StubCollection()
    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: StubClient(collection),
    )

    store = VectorStore(
        tmp_path / "chroma",
        embedding_client=StubEmbeddingClient(dimension=1024),
    )

    assert store.collection is collection


def test_vector_store_should_raise_clear_error_when_embedding_dimension_mismatch(monkeypatch, tmp_path: Path) -> None:
    """现有集合维度与当前 embedding 维度不一致时，应给出明确报错。"""

    collection = StubCollection(ids=["chunk_1"], embeddings=[[0.0] * 64])
    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: StubClient(collection),
    )

    with pytest.raises(ValidationAppError) as exc_info:
        VectorStore(
            tmp_path / "chroma",
            embedding_client=StubEmbeddingClient(dimension=1024),
        )

    assert "Embedding 维度与现有向量索引不一致" in exc_info.value.message
    assert exc_info.value.details["stored_dimension"] == 64
    assert exc_info.value.details["current_dimension"] == 1024


def test_vector_store_should_support_ndarray_embeddings_when_inferring_stored_dimension(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """读取 Chroma 返回的 ndarray 向量时，不应触发真值判断异常。"""

    collection = StubCollection(ids=["chunk_1"], embeddings=np.array([[0.0] * 64]))
    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: StubClient(collection),
    )

    with pytest.raises(ValidationAppError) as exc_info:
        VectorStore(
            tmp_path / "chroma",
            embedding_client=StubEmbeddingClient(dimension=1024),
        )

    assert "Embedding 维度与现有向量索引不一致" in exc_info.value.message
    assert exc_info.value.details["stored_dimension"] == 64


def test_vector_store_should_auto_rebuild_collection_from_sqlite_when_enabled(monkeypatch, tmp_path: Path) -> None:
    """开启自动修复后，应基于 SQLite 的 chunks 重建新维度向量集合。"""

    database_path = tmp_path / "app.db"
    seed_chunk_database(database_path)
    client = StubClient(StubCollection(ids=["chunk_legacy"], embeddings=[[0.0] * 64]))
    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: client,
    )

    store = VectorStore(
        tmp_path / "chroma",
        embedding_client=StubEmbeddingClient(dimension=1024),
        sqlite_db_path=database_path,
        auto_repair_dimension_mismatch=True,
    )

    assert store.collection.peek(limit=1)["ids"] == ["chunk_1"]
    assert len(store.collection.peek(limit=1)["embeddings"][0]) == 1024
    assert store.last_repair_summary["repaired"] is True
    assert store.last_repair_summary["repaired_docs"] == 1
    assert store.last_repair_summary["repaired_chunks"] == 1


def test_vector_store_should_clear_legacy_collection_when_auto_repair_enabled_but_sqlite_has_no_chunks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """旧索引维度冲突但 SQLite 还没有 chunk 时，应清空旧集合并允许系统继续启动。"""

    database_path = tmp_path / "empty.db"
    initialize_database(database_path)
    client = StubClient(StubCollection(ids=["chunk_legacy"], embeddings=[[0.0] * 64]))
    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: client,
    )

    store = VectorStore(
        tmp_path / "chroma",
        embedding_client=StubEmbeddingClient(dimension=1024),
        sqlite_db_path=database_path,
        auto_repair_dimension_mismatch=True,
    )

    assert store.collection.peek(limit=1)["ids"] == []
    assert store.last_repair_summary["repaired"] is True
    assert store.last_repair_summary["repaired_docs"] == 0
    assert store.last_repair_summary["repaired_chunks"] == 0


def test_vector_store_should_rebuild_from_sqlite_when_legacy_collection_config_is_incompatible(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """旧版 Chroma 集合配置不兼容时，应重建目录并从 SQLite 回填向量。"""

    database_path = tmp_path / "app.db"
    persist_directory = tmp_path / "chroma"
    seed_chunk_database(database_path)
    persist_directory.mkdir(parents=True, exist_ok=True)
    (persist_directory / "legacy.txt").write_text("legacy", encoding="utf-8")
    client = RaisingLegacyConfigClient(StubCollection())
    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: client,
    )

    store = VectorStore(
        persist_directory,
        embedding_client=StubEmbeddingClient(dimension=1024),
        sqlite_db_path=database_path,
        auto_repair_dimension_mismatch=True,
    )

    assert store.collection.peek(limit=1)["ids"] == ["chunk_1"]
    assert store.last_repair_summary["repaired"] is True
    assert store.last_repair_summary["repair_reason"] == "legacy_collection_config"
    assert store.last_repair_summary["repaired_docs"] == 1
    assert store.last_repair_summary["repaired_chunks"] == 1
    assert store.last_repair_summary["legacy_backup_path"].endswith("chroma_legacy_backup")


def test_vector_store_count_by_doc_uid_should_support_nested_id_sequences(monkeypatch, tmp_path: Path) -> None:
    """统计向量数量时应兼容部分客户端返回的嵌套 ids 结构。"""

    collection = CountStubCollection(ids_result=[["chunk_1", "chunk_2"]])
    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: StubClient(collection),
    )

    store = VectorStore(
        tmp_path / "chroma",
        embedding_client=StubEmbeddingClient(dimension=8),
    )

    assert store.count_by_doc_uid("doc_1") == 2


def test_vector_store_should_write_model_dimension_and_index_version_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """每条向量必须携带知识库、模型、维度和索引版本。"""

    collection = StubCollection()
    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: StubClient(collection),
    )
    store = VectorStore(
        tmp_path / "chroma",
        embedding_client=StubEmbeddingClient(dimension=8),
        embedding_model="test-embedding-v2",
        index_version="retrieval-v2",
    )

    store.upsert_chunks(
        [
            {
                "chunk_id": "chunk_meta",
                "doc_uid": "doc_meta",
                "knowledge_base_id": "default",
                "content": "向量元数据测试",
            }
        ]
    )

    metadata = collection._metadatas[0]
    assert metadata["knowledge_base_id"] == "default"
    assert metadata["embedding_model"] == "test-embedding-v2"
    assert metadata["embedding_dimension"] == 8
    assert metadata["index_version"] == "retrieval-v2"


def test_rebuild_from_sqlite_should_inherit_document_knowledge_base(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """全量重建时，应把 documents.knowledge_base_id 写入每条向量元数据。"""

    database_path = tmp_path / "app.db"
    seed_chunk_database(database_path)
    collection = StubCollection()
    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: StubClient(collection),
    )
    store = VectorStore(
        tmp_path / "chroma",
        embedding_client=StubEmbeddingClient(dimension=8),
        sqlite_db_path=database_path,
    )

    store.rebuild_from_sqlite()

    assert collection._metadatas[0]["knowledge_base_id"] == "default"


def test_vector_store_close_should_release_chroma_client(monkeypatch, tmp_path: Path) -> None:
    """关闭向量存储时，应显式释放 Windows 下持有目录的 Chroma 客户端。"""

    client = StubClient(StubCollection())
    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: client,
    )
    store = VectorStore(
        tmp_path / "chroma",
        embedding_client=StubEmbeddingClient(dimension=8),
    )

    store.close()

    assert client.closed is True
