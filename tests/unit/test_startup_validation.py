"""程序说明：验证 API 与 UI 在向量维度冲突时安全阻断，并校验版本一致性。"""

from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path

import pytest

from src.common.config import AppSettings
from src.common.errors import ValidationAppError
from src.db.connection import initialize_database
from src.retrieval.vector_store import VectorStore


class StubEmbeddingClient:
    """测试用 Embedding 客户端。"""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] * self.dimension for _ in texts]


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


def seed_legacy_index(settings: AppSettings) -> None:
    """创建旧维度索引，供启动阻断测试使用。"""

    initialize_database(settings.sqlite_db_path)
    VectorStore(settings.chroma_persist_dir, embedding_client=StubEmbeddingClient(64)).upsert_chunks(
        [{"chunk_id": "chunk_legacy", "doc_uid": "doc_legacy", "content": "legacy"}]
    )


def import_app_module_with_mismatch(monkeypatch: pytest.MonkeyPatch, settings: AppSettings):
    """在导入应用模块前注入 1024 维 embedding。"""

    monkeypatch.setattr("src.ai.embedding.build_embedding_client", lambda settings: StubEmbeddingClient(1024))
    monkeypatch.setattr("src.common.config.get_settings", lambda: settings)
    sys.modules.pop("src.app", None)
    return importlib.import_module("src.app")


def import_ui_module_with_mismatch(monkeypatch: pytest.MonkeyPatch):
    """在导入 UI 模块前注入 1024 维 embedding。"""

    monkeypatch.setattr("src.ai.embedding.build_embedding_client", lambda settings: StubEmbeddingClient(1024))
    sys.modules.pop("src.ui.app", None)
    return importlib.import_module("src.ui.app")


def test_create_app_should_reject_embedding_dimension_mismatch_without_auto_rebuild(monkeypatch, tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    seed_legacy_index(settings)
    with pytest.raises(ValidationAppError, match="Embedding 维度"):
        import_app_module_with_mismatch(monkeypatch, settings)


def test_create_ui_app_should_reject_embedding_dimension_mismatch_without_auto_rebuild(monkeypatch, tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    seed_legacy_index(settings)
    ui_module = import_ui_module_with_mismatch(monkeypatch)
    with pytest.raises(ValidationAppError, match="Embedding 维度"):
        ui_module.create_ui_app(settings)


def test_create_app_should_keep_legacy_index_when_sqlite_has_no_chunks(monkeypatch, tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path)
    seed_legacy_index(settings)
    with pytest.raises(ValidationAppError, match="Embedding 维度"):
        import_app_module_with_mismatch(monkeypatch, settings)


def test_create_app_should_initialize_database_before_creating_vector_store(monkeypatch, tmp_path: Path) -> None:
    """create_app() 应先完成数据库初始化，再构造 VectorStore。"""

    settings = build_test_settings(tmp_path)
    app_module = import_app_module_with_mismatch(monkeypatch, settings)
    call_order: list[str] = []
    original_initialize_database = app_module.initialize_database

    def record_initialize_database(database_path: Path) -> None:
        call_order.append("initialize_database")
        original_initialize_database(database_path)

    class RecordingVectorStore:
        def __init__(self, *args, **kwargs) -> None:
            _ = args, kwargs
            call_order.append("vector_store")

    monkeypatch.setattr(app_module, "initialize_database", record_initialize_database)
    monkeypatch.setattr(app_module, "VectorStore", RecordingVectorStore)
    app = app_module.create_app(settings)
    assert app is not None
    assert call_order[:2] == ["initialize_database", "vector_store"]


def test_project_version_should_match_fastapi_app_version() -> None:
    project_root = Path(__file__).resolve().parents[2]
    pyproject_data = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8-sig"))
    expected_version = str(pyproject_data["project"]["version"])
    app_module = importlib.import_module("src.app")
    assert expected_version == "0.6"
    assert app_module.app.version == expected_version
