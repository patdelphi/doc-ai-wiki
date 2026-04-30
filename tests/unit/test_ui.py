"""程序说明：验证最小 UI 可构建。"""

from pathlib import Path

import gradio as gr

from src.common.config import AppSettings
from src.db.connection import initialize_database
from src.ingest.service import IngestService
from src.quality.service import QualityService
from src.review.service import ReviewService
from src.retrieval.service import RetrievalService
from src.retrieval.vector_store import VectorStore
from src.ui.app import create_ui_app


def test_create_ui_app_should_return_gradio_blocks(tmp_path: Path) -> None:
    """UI 启动入口应返回可用的 Gradio Blocks。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)

    assert isinstance(demo, gr.Blocks)
