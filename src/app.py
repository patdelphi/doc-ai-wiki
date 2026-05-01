"""程序说明：应用主入口，注册最小 API 路由并初始化数据库。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from src.ai.embedding import build_embedding_client
from src.ai.llm import DisabledLLMClient, build_llm_client
from src.ai.rerank import build_reranker
from src.common.config import AppSettings, get_settings
from src.common.errors import AppError, NotFoundAppError, ValidationAppError
from src.common.logger import configure_logging, get_logger
from src.common.models import (
    ApiResponse,
    DocumentRegisterRequest,
    IngestRebuildRequest,
    QualityCheckRequest,
    ReviewSubmitRequest,
)
from src.db.connection import initialize_database
from src.ingest.service import IngestService
from src.quality.service import QualityService
from src.review.service import ReviewService
from src.retrieval.service import RetrievalService
from src.retrieval.vector_store import VectorStore


def create_app(settings_override: AppSettings | None = None) -> FastAPI:
    """创建可测试的 FastAPI 应用实例。"""

    settings = settings_override or get_settings()
    configure_logging(config_path=Path("config/logging.yaml"), default_level=settings.log_level)
    logger = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """应用启动时初始化数据库。"""

        settings.ensure_runtime_directories()
        initialize_database(settings.sqlite_db_path)
        logger.info("数据库初始化完成")
        yield

    app = FastAPI(title="中文知识库系统 MVP", version="0.1.0", lifespan=lifespan)
    embedding_client = build_embedding_client(settings)
    llm_client = build_llm_client(settings)
    reranker = build_reranker(settings)
    vector_store = VectorStore(settings.chroma_persist_dir, embedding_client=embedding_client)
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

    @app.exception_handler(AppError)
    async def handle_app_error(_, exc: AppError) -> JSONResponse:
        """统一应用异常响应。"""

        payload = ApiResponse(
            success=False,
            message=exc.message,
            error_code=exc.error_code,
            details=exc.details,
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.get("/health", response_model=ApiResponse)
    def health_check() -> ApiResponse:
        """健康检查接口。"""

        return ApiResponse(success=True, message="ok", data={"status": "healthy"})

    @app.post("/ingest/register", response_model=ApiResponse)
    def register_documents(request: DocumentRegisterRequest) -> ApiResponse:
        """注册 Markdown 文档。"""

        jobs = ingest_service.register_documents(
            [item.model_dump() for item in request.documents],
            rebuild_if_exists=request.rebuild_if_exists,
        )
        return ApiResponse(success=True, message="documents registered", data={"jobs": jobs})

    @app.post("/ingest/rebuild", response_model=ApiResponse)
    def rebuild_documents(request: IngestRebuildRequest) -> ApiResponse:
        """接受文档重建请求。"""

        accepted = ingest_service.rebuild_documents(
            request.doc_uids,
            rebuild_fulltext=request.rebuild_fulltext,
            rebuild_vector=request.rebuild_vector,
        )
        return ApiResponse(success=True, message="rebuild started", data={"accepted": accepted})

    @app.get("/ingest/status", response_model=ApiResponse)
    def get_ingest_status(
        doc_uid: str | None = None,
        status: str | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> ApiResponse:
        """查询入库状态。"""

        items, total = ingest_service.list_status(
            doc_uid=doc_uid,
            status=status,
            page=page,
            page_size=page_size,
        )
        return ApiResponse(
            success=True,
            message="ok",
            data={
                "items": items,
                "pagination": {"page": page, "page_size": page_size, "total": total},
            },
        )

    @app.get("/search/fulltext", response_model=ApiResponse)
    def search_fulltext(
        query: str = Query(..., min_length=1),
        top_k: int = Query(default=10, ge=1, le=100),
    ) -> ApiResponse:
        """执行全文检索。"""

        items = retrieval_service.fulltext_search(query, top_k=top_k)
        return ApiResponse(success=True, message="ok", data={"items": items})

    @app.get("/search/vector", response_model=ApiResponse)
    def search_vector(
        query: str = Query(..., min_length=1),
        top_k: int = Query(default=10, ge=1, le=100),
    ) -> ApiResponse:
        """执行向量检索占位实现。"""

        items = retrieval_service.vector_search(query, top_k=top_k)
        return ApiResponse(success=True, message="ok", data={"items": items})

    @app.get("/search/hybrid", response_model=ApiResponse)
    def search_hybrid(
        query: str = Query(..., min_length=1),
        top_k: int = Query(default=10, ge=1, le=100),
        use_rerank: bool = Query(default=True),
    ) -> ApiResponse:
        """执行混合检索。"""

        items = retrieval_service.hybrid_search(query, top_k=top_k, use_rerank=use_rerank)
        return ApiResponse(success=True, message="ok", data={"items": items})

    @app.post("/quality/check", response_model=ApiResponse)
    def quality_check(request: QualityCheckRequest) -> ApiResponse:
        """执行最小质检。"""

        if not request.input_text.strip():
            raise ValidationAppError("input_text 不能为空")
        if len(request.input_text) > 2000:
            raise ValidationAppError("input_text 不能超过 2000 字", details={"max_length": 2000})
        result = quality_service.run_check(
            request.input_text,
            doc_uid=request.doc_uid,
            template_id=request.template_id,
        )
        return ApiResponse(success=True, message="ok", data=result)

    @app.get("/quality/templates", response_model=ApiResponse)
    def list_quality_templates() -> ApiResponse:
        """列出可用的质检模板。"""

        return ApiResponse(success=True, message="ok", data={"items": quality_service.list_templates()})

    @app.get("/quality/result/{check_id}", response_model=ApiResponse)
    def get_quality_result(check_id: str) -> ApiResponse:
        """查询质检结果。"""

        result = quality_service.get_result(check_id)
        if not result:
            raise NotFoundAppError("质检结果不存在", details={"check_id": check_id})
        return ApiResponse(success=True, message="ok", data=result)

    @app.post("/review/submit", response_model=ApiResponse)
    def submit_review(request: ReviewSubmitRequest) -> ApiResponse:
        """提交审核动作。"""

        result = review_service.submit_review(
            claim_id=request.claim_id,
            review_action=request.review_action,
            reviewed_verdict=request.reviewed_verdict,
            review_note=request.review_note,
            reviewer=request.reviewer,
        )
        return ApiResponse(success=True, message="ok", data=result)

    @app.get("/review/list", response_model=ApiResponse)
    def list_reviews(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> ApiResponse:
        """分页查询审核记录。"""

        items, total = review_service.list_reviews(page=page, page_size=page_size)
        return ApiResponse(
            success=True,
            message="ok",
            data={
                "items": items,
                "pagination": {"page": page, "page_size": page_size, "total": total},
            },
        )

    return app


app = create_app()
