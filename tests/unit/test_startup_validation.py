"""程序说明：验证 API 与 UI 在启动阶段会执行 Embedding 维度自检。"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from src.common.config import AppSettings
from src.common.errors import ValidationAppError


class StubEmbeddingClient:
    """测试用 Embedding 客户端。"""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dimension for _ in texts]


class StubCollection:
    """测试用 Chroma 集合。"""

    def __init__(self, *, ids: list[str] | None = None, embeddings: list[list[float]] | None = None) -> None:
        self._ids = ids or []
        self._embeddings = embeddings or []

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


def build_test_settings(tmp_path: Path) -> AppSettings:
    """构造测试专用配置。"""

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "base_rules.yaml").write_text("[]", encoding="utf-8")

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    return AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=rules_dir,
        TEMPLATES_DIR=templates_dir,
    )


def import_app_module_with_mismatch(monkeypatch: pytest.MonkeyPatch, collection: StubCollection):
    """在导入应用模块前注入测试桩，确保启动时走到维度冲突逻辑。"""

    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: StubClient(collection),
    )
    monkeypatch.setattr(
        "src.ai.embedding.build_embedding_client",
        lambda settings: StubEmbeddingClient(dimension=1024),
    )
    sys.modules.pop("src.app", None)
    return importlib.import_module("src.app")


def import_ui_module_with_mismatch(monkeypatch: pytest.MonkeyPatch, collection: StubCollection):
    """在导入 UI 模块前注入测试桩，确保启动时走到维度冲突逻辑。"""

    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: StubClient(collection),
    )
    monkeypatch.setattr(
        "src.ai.embedding.build_embedding_client",
        lambda settings: StubEmbeddingClient(dimension=1024),
    )
    sys.modules.pop("src.ui.app", None)
    return importlib.import_module("src.ui.app")


def test_create_app_should_raise_clear_error_when_embedding_dimension_mismatch_at_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """API 初始化时发现维度不一致，应直接抛出明确错误。"""

    collection = StubCollection(ids=["chunk_1"], embeddings=[[0.0] * 64])
    with pytest.raises(ValidationAppError) as exc_info:
        app_module = import_app_module_with_mismatch(monkeypatch, collection)
        app_module.create_app(build_test_settings(tmp_path))

    assert "Embedding 维度与现有向量索引不一致" in exc_info.value.message
    assert exc_info.value.details["stored_dimension"] == 64
    assert exc_info.value.details["current_dimension"] == 1024
    assert exc_info.value.details["recommended_action"]


def test_create_ui_app_should_raise_clear_error_when_embedding_dimension_mismatch_at_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """UI 初始化时发现维度不一致，应直接抛出明确错误。"""

    collection = StubCollection(ids=["chunk_1"], embeddings=[[0.0] * 64])
    with pytest.raises(ValidationAppError) as exc_info:
        ui_module = import_ui_module_with_mismatch(monkeypatch, collection)
        ui_module.create_ui_app(build_test_settings(tmp_path))

    assert "Embedding 维度与现有向量索引不一致" in exc_info.value.message
    assert exc_info.value.details["stored_dimension"] == 64
    assert exc_info.value.details["current_dimension"] == 1024
    assert exc_info.value.details["recommended_action"]
