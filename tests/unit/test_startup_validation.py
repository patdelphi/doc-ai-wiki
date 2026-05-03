"""程序说明：验证 API 与 UI 在启动阶段遇到向量维度冲突时会自动自愈。"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from src.common.config import AppSettings
from src.db.connection import initialize_database
from src.db.transaction import transaction


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

    def delete(self, *, where: dict) -> None:
        _ = where


class StubClient:
    """测试用 Chroma 客户端。"""

    def __init__(self, collection: StubCollection) -> None:
        self._collections = {"knowledge_chunks": collection}

    def get_or_create_collection(self, *, name: str) -> StubCollection:
        assert name == "knowledge_chunks"
        return self._collections.setdefault(name, StubCollection())

    def delete_collection(self, *, name: str) -> None:
        self._collections.pop(name, None)


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


def seed_chunk_database(settings: AppSettings) -> None:
    """写入最小 chunk 数据，供自动重建测试复用。"""

    initialize_database(settings.sqlite_db_path)
    now = "2026-05-03T19:10:00+08:00"
    with transaction(settings.sqlite_db_path) as connection:
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
                str((settings.input_root / "acceptance.MD").resolve()),
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


def import_app_module_with_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    client: StubClient,
    settings: AppSettings,
):
    """在导入应用模块前注入测试桩，确保启动时走到维度冲突逻辑。"""

    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: client,
    )
    monkeypatch.setattr(
        "src.ai.embedding.build_embedding_client",
        lambda settings: StubEmbeddingClient(dimension=1024),
    )
    monkeypatch.setattr(
        "src.common.config.get_settings",
        lambda: settings,
    )
    sys.modules.pop("src.app", None)
    return importlib.import_module("src.app")


def import_ui_module_with_mismatch(monkeypatch: pytest.MonkeyPatch, client: StubClient):
    """在导入 UI 模块前注入测试桩，确保启动时走到维度冲突逻辑。"""

    monkeypatch.setattr(
        "src.retrieval.vector_store.chromadb.PersistentClient",
        lambda path: client,
    )
    monkeypatch.setattr(
        "src.ai.embedding.build_embedding_client",
        lambda settings: StubEmbeddingClient(dimension=1024),
    )
    sys.modules.pop("src.ui.app", None)
    return importlib.import_module("src.ui.app")


def test_create_app_should_auto_rebuild_vectors_when_embedding_dimension_mismatch_at_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """API 初始化时发现维度不一致，应自动重建旧向量集合。"""

    settings = build_test_settings(tmp_path)
    seed_chunk_database(settings)
    client = StubClient(StubCollection(ids=["chunk_legacy"], embeddings=[[0.0] * 64]))
    app_module = import_app_module_with_mismatch(monkeypatch, client, settings)
    app = app_module.create_app(settings)
    collection = client.get_or_create_collection(name="knowledge_chunks")

    assert app is not None
    assert collection.peek(limit=1)["ids"] == ["chunk_1"]
    assert len(collection.peek(limit=1)["embeddings"][0]) == 1024


def test_create_ui_app_should_auto_rebuild_vectors_when_embedding_dimension_mismatch_at_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """UI 初始化时发现维度不一致，应自动重建旧向量集合。"""

    settings = build_test_settings(tmp_path)
    seed_chunk_database(settings)
    client = StubClient(StubCollection(ids=["chunk_legacy"], embeddings=[[0.0] * 64]))
    ui_module = import_ui_module_with_mismatch(monkeypatch, client)
    demo = ui_module.create_ui_app(settings)
    collection = client.get_or_create_collection(name="knowledge_chunks")

    assert demo is not None
    assert collection.peek(limit=1)["ids"] == ["chunk_1"]
    assert len(collection.peek(limit=1)["embeddings"][0]) == 1024


def test_create_app_should_allow_startup_when_legacy_collection_exists_but_sqlite_has_no_chunks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """新环境仅残留旧 Chroma 索引、SQLite 还无文档时，也应能自动清空并启动。"""

    settings = build_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    client = StubClient(StubCollection(ids=["chunk_legacy"], embeddings=[[0.0] * 64]))
    app_module = import_app_module_with_mismatch(monkeypatch, client, settings)
    app = app_module.create_app(settings)
    collection = client.get_or_create_collection(name="knowledge_chunks")

    assert app is not None
    assert collection.peek(limit=1)["ids"] == []
