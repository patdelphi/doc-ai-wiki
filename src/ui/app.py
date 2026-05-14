"""程序说明：Gradio UI 启动入口，负责组装服务实例并构建页面。"""

from __future__ import annotations

import gradio as gr

from src.ai.embedding import build_embedding_client
from src.ai.llm import DisabledLLMClient, build_llm_client
from src.ai.rerank import build_reranker
from src.auth.service import AuthService
from src.common.config import AppSettings, get_settings
from src.db.connection import create_connection, initialize_database
from src.ingest.service import IngestService
from src.quality.service import QualityService
from src.review.service import ReviewService
from src.retrieval.service import RetrievalService
from src.retrieval.vector_store import VectorStore
from src.ui.exporters import resolve_export_docs_dir
from src.ui.pages import build_ui
from src.ui.css import UI_CSS


class ConnectionScopedAuthService:
    """按调用粒度创建认证连接，避免 UI 长期持有 SQLite 连接。"""

    def __init__(self, database_path) -> None:
        self.database_path = database_path

    def _call(self, method_name: str, *args, **kwargs):
        """为每次认证调用创建独立连接，用后立即关闭。"""

        with create_connection(self.database_path) as connection:
            method = getattr(AuthService(connection), method_name)
            return method(*args, **kwargs)

    def authenticate(self, username: str, password: str):
        return self._call("authenticate", username, password)

    def register_user(self, username: str, password: str):
        return self._call("register_user", username, password)

    def get_user_by_id(self, user_id: str):
        return self._call("get_user_by_id", user_id)

    def get_user_permissions(self, user_id: str):
        return self._call("get_user_permissions", user_id)

    def list_users(self):
        return self._call("list_users")

    def delete_user(self, user_id: str):
        return self._call("delete_user", user_id)

    def update_user_permissions(self, user_id: str, tab_names: list[str], kb_ids: list[str]):
        return self._call("update_user_permissions", user_id, tab_names, kb_ids)


def create_ui_app(settings_override: AppSettings | None = None) -> gr.Blocks:
    """创建 Gradio UI 实例。"""

    settings = settings_override or get_settings()
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)

    auth_service = ConnectionScopedAuthService(settings.sqlite_db_path)

    embedding_client = build_embedding_client(settings)
    llm_client = build_llm_client(settings)
    reranker = build_reranker(settings)
    vector_store = VectorStore(
        settings.chroma_persist_dir,
        embedding_client=embedding_client,
        sqlite_db_path=settings.sqlite_db_path,
        auto_repair_dimension_mismatch=True,
    )
    ingest_service = IngestService(settings)
    retrieval_service = RetrievalService(settings.sqlite_db_path)
    retrieval_service.set_vector_store(vector_store)
    retrieval_service.set_reranker(reranker)
    quality_service = QualityService(
        settings.sqlite_db_path,
        rules_dir=settings.rules_dir,
        templates_dir=settings.templates_dir,
        vector_store=vector_store,
        reranker=reranker,
        llm_client=None if isinstance(llm_client, DisabledLLMClient) else llm_client,
    )
    review_service = ReviewService(settings.sqlite_db_path)

    return build_ui(
        ingest_service=ingest_service,
        retrieval_service=retrieval_service,
        quality_service=quality_service,
        review_service=review_service,
        auth_service=auth_service,
        runtime_config={
            "input_root": str(settings.input_root),
            "templates_dir": str(settings.templates_dir),
            "sqlite_db_path": str(settings.sqlite_db_path),
            "llm_provider": settings.llm_provider,
            "embedding_provider": settings.embedding_provider,
            "rerank_provider": settings.rerank_provider,
            "rerank_enabled": settings.rerank_enabled,
            "app_host": settings.app_host,
            "gradio_port": settings.gradio_port,
        },
    )


def launch_ui(settings_override: AppSettings | None = None) -> None:
    """启动本地 Gradio 页面。"""

    settings = settings_override or get_settings()
    demo = create_ui_app(settings)
    docs_dir = resolve_export_docs_dir(settings.sqlite_db_path)
    demo.launch(
        server_name=settings.app_host,
        server_port=settings.gradio_port,
        show_error=True,
        css=UI_CSS,
        allowed_paths=[str(docs_dir.resolve())],
    )


if __name__ == "__main__":
    launch_ui()
