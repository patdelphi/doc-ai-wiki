"""程序说明：Gradio UI 启动入口，负责组装服务实例并构建页面。"""

from __future__ import annotations

import gradio as gr

from src.common.config import AppSettings, get_settings
from src.db.connection import initialize_database
from src.ingest.service import IngestService
from src.quality.service import QualityService
from src.review.service import ReviewService
from src.retrieval.service import RetrievalService
from src.retrieval.vector_store import VectorStore
from src.ui.pages import build_ui


def create_ui_app(settings_override: AppSettings | None = None) -> gr.Blocks:
    """创建 Gradio UI 实例。"""

    settings = settings_override or get_settings()
    initialize_database(settings.sqlite_db_path)

    vector_store = VectorStore(settings.chroma_persist_dir)
    ingest_service = IngestService(settings)
    retrieval_service = RetrievalService(settings.sqlite_db_path)
    retrieval_service.set_vector_store(vector_store)
    quality_service = QualityService(
        settings.sqlite_db_path,
        rules_dir=settings.rules_dir,
        vector_store=vector_store,
    )
    review_service = ReviewService(settings.sqlite_db_path)

    return build_ui(
        ingest_service=ingest_service,
        retrieval_service=retrieval_service,
        quality_service=quality_service,
        review_service=review_service,
    )


def launch_ui(settings_override: AppSettings | None = None) -> None:
    """启动本地 Gradio 页面。"""

    settings = settings_override or get_settings()
    demo = create_ui_app(settings)
    demo.launch(server_name=settings.app_host, server_port=settings.gradio_port, show_error=True)


if __name__ == "__main__":
    launch_ui()
