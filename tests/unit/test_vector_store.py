"""程序说明：验证向量索引启动时的 embedding 维度自检逻辑。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.common.errors import ValidationAppError
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


class StubClient:
    """测试用 Chroma 客户端。"""

    def __init__(self, collection: StubCollection) -> None:
        self._collection = collection

    def get_or_create_collection(self, *, name: str) -> StubCollection:
        assert name == "knowledge_chunks"
        return self._collection


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
