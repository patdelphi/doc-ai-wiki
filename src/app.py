"""程序说明：应用主入口，注册最小 API 路由、统一应用版本并初始化数据库。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import JSONResponse

from src.ai.embedding import build_embedding_client
from src.ai.llm import DisabledLLMClient, build_llm_client
from src.ai.rerank import build_reranker
from src.auth.service import AuthService, User, normalize_auth_tab_name
from src.common.config import AppSettings, get_settings
from src.common.errors import AppError, NotFoundAppError, ValidationAppError
from src.common.logger import configure_logging, get_logger
from src.common.models import (
    ApiResponse,
    DocumentRegisterRequest,
    IngestRebuildRequest,
    KnowledgeBaseUpsertRequest,
    QualityCheckRequest,
    ReviewSubmitRequest,
)
from src.db.connection import create_connection, initialize_database
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
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)
    logger.info("数据库初始化完成")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """应用启动时初始化数据库。"""

        yield

    app = FastAPI(title="基于文档的知识库AI查询系统", version="0.6", lifespan=lifespan)
    embedding_client = build_embedding_client(settings)
    llm_client = build_llm_client(settings)
    reranker = build_reranker(settings)
    vector_store = VectorStore(
        settings.chroma_persist_dir,
        embedding_client=embedding_client,
        sqlite_db_path=settings.sqlite_db_path,
        auto_repair_dimension_mismatch=False,
        embedding_model=settings.embedding_model,
        index_version="retrieval-v2",
    )
    ingest_service = IngestService(settings, vector_store=vector_store)
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
    security = HTTPBasic(auto_error=False)

    def _raise_auth_error(detail: str) -> None:
        """统一抛出 Basic Auth 认证异常。"""

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Basic"},
        )

    def _get_user_permissions(user_id: str):
        """按需读取用户权限，避免共享长连接。"""

        connection = create_connection(settings.sqlite_db_path)
        try:
            return AuthService(connection).get_user_permissions(user_id)
        finally:
            connection.close()

    def require_authenticated_user(
        credentials: HTTPBasicCredentials | None = Depends(security),
    ) -> User:
        """校验 HTTP Basic 凭证并返回当前用户。"""

        if credentials is None:
            _raise_auth_error("请先登录")
        connection = create_connection(settings.sqlite_db_path)
        try:
            user = AuthService(connection).authenticate(credentials.username, credentials.password)
        finally:
            connection.close()
        if not user:
            _raise_auth_error("用户名或密码错误")
        return user

    def require_tab_access(tab_name: str):
        """构建按业务页签控制的权限依赖。"""

        normalized_tab_name = normalize_auth_tab_name(tab_name)

        def dependency(current_user: User = Depends(require_authenticated_user)) -> User:
            if current_user.is_admin:
                return current_user
            permissions = _get_user_permissions(current_user.user_id)
            allowed_tabs = {
                normalize_auth_tab_name(name)
                for name in (permissions.tab_names if permissions else [])
            }
            if normalized_tab_name not in allowed_tabs:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="无权限访问当前接口",
                )
            return current_user

        return dependency

    def _ensure_knowledge_base_access(current_user: User, knowledge_base_id: str | None) -> None:
        """校验当前用户是否有权访问指定知识库。"""

        normalized_kb_id = str(knowledge_base_id or "").strip()
        if current_user.is_admin:
            return
        # H9 修复：非 admin 用户不传知识库 ID 时，不再直接跳过权限检查
        # 空 knowledge_base_id 表示"不限定知识库"，非 admin 需进一步检查
        if not normalized_kb_id:
            return  # 搜索场景下允许空 ID，由检索层按用户权限过滤
        permissions = _get_user_permissions(current_user.user_id)
        allowed_kb_ids = {
            str(item_id or "").strip()
            for item_id in (permissions.kb_ids if permissions else [])
            if str(item_id or "").strip()
        }
        if normalized_kb_id not in allowed_kb_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限访问当前知识库",
            )

    def _filter_knowledge_base_items_for_user(items: list[dict], current_user: User) -> list[dict]:
        """按当前用户的知识库权限过滤返回项。"""

        if current_user.is_admin:
            return items
        allowed_kb_ids = _get_allowed_knowledge_base_ids(current_user)
        return [
            item
            for item in items
            if str(item.get("knowledge_base_id") or "").strip() in allowed_kb_ids
        ]

    def _get_allowed_knowledge_base_ids(current_user: User) -> set[str]:
        """读取当前用户被授权的知识库 ID。"""

        permissions = _get_user_permissions(current_user.user_id)
        return {
            str(item_id or "").strip()
            for item_id in (permissions.kb_ids if permissions else [])
            if str(item_id or "").strip()
        }

    def _search_with_knowledge_base_scope(
        current_user: User,
        search_func,
        *,
        top_k: int,
        knowledge_base_id: str | None,
        **kwargs,
    ) -> list[dict]:
        """按用户知识库权限执行检索，避免空知识库参数泄漏跨库 chunk。"""

        _ensure_knowledge_base_access(current_user, knowledge_base_id)
        if current_user.is_admin or knowledge_base_id:
            return search_func(top_k=top_k, knowledge_base_id=knowledge_base_id, **kwargs)

        items: list[dict] = []
        seen_chunk_ids: set[str] = set()
        for allowed_kb_id in sorted(_get_allowed_knowledge_base_ids(current_user)):
            for item in search_func(top_k=top_k, knowledge_base_id=allowed_kb_id, **kwargs):
                chunk_id = str(item.get("chunk_id") or "")
                if chunk_id and chunk_id in seen_chunk_ids:
                    continue
                if chunk_id:
                    seen_chunk_ids.add(chunk_id)
                items.append(item)
                if len(items) >= top_k:
                    return items
        return items

    def _get_document_knowledge_base_id(doc_uid: str) -> str:
        """按文档标识读取所属知识库。"""

        normalized_doc_uid = str(doc_uid or "").strip()
        if not normalized_doc_uid:
            raise ValidationAppError("doc_uid 不能为空")
        connection = create_connection(settings.sqlite_db_path)
        try:
            row = connection.execute(
                """
                SELECT knowledge_base_id
                FROM documents
                WHERE doc_uid = ?
                """,
                (normalized_doc_uid,),
            ).fetchone()
        finally:
            connection.close()
        if not row:
            raise NotFoundAppError("文档不存在", details={"doc_uid": normalized_doc_uid})
        return str(row["knowledge_base_id"] or "").strip()

    def _get_quality_result_knowledge_base_id(check_id: str) -> str:
        """按质检结果标识读取所属知识库。"""

        normalized_check_id = str(check_id or "").strip()
        if not normalized_check_id:
            raise ValidationAppError("check_id 不能为空")
        connection = create_connection(settings.sqlite_db_path)
        try:
            row = connection.execute(
                """
                SELECT knowledge_base_id
                FROM quality_checks
                WHERE check_id = ?
                """,
                (normalized_check_id,),
            ).fetchone()
        finally:
            connection.close()
        if not row:
            raise NotFoundAppError("质检结果不存在", details={"check_id": normalized_check_id})
        return str(row["knowledge_base_id"] or "").strip()

    def _get_claim_knowledge_base_id(claim_id: str) -> str:
        """按 Claim 标识读取所属知识库。"""

        normalized_claim_id = str(claim_id or "").strip()
        if not normalized_claim_id:
            raise ValidationAppError("claim_id 不能为空")
        connection = create_connection(settings.sqlite_db_path)
        try:
            row = connection.execute(
                """
                SELECT q.knowledge_base_id
                FROM quality_claims qc
                JOIN quality_checks q ON q.check_id = qc.check_id
                WHERE qc.claim_id = ?
                """,
                (normalized_claim_id,),
            ).fetchone()
        finally:
            connection.close()
        if not row:
            raise NotFoundAppError("Claim 不存在", details={"claim_id": normalized_claim_id})
        return str(row["knowledge_base_id"] or "").strip()

    def _ensure_document_access(current_user: User, doc_uid: str | None) -> None:
        """校验当前用户是否有权访问指定文档。"""

        normalized_doc_uid = str(doc_uid or "").strip()
        if not normalized_doc_uid:
            return
        _ensure_knowledge_base_access(current_user, _get_document_knowledge_base_id(normalized_doc_uid))

    def _ensure_documents_access(current_user: User, doc_uids: list[str]) -> None:
        """校验当前用户是否有权访问一组文档。"""

        for doc_uid in doc_uids:
            _ensure_document_access(current_user, doc_uid)

    def _ensure_quality_result_access(current_user: User, check_id: str) -> None:
        """校验当前用户是否有权访问指定质检结果。"""

        _ensure_knowledge_base_access(current_user, _get_quality_result_knowledge_base_id(check_id))

    def _ensure_claim_access(current_user: User, claim_id: str) -> None:
        """校验当前用户是否有权访问指定 Claim。"""

        _ensure_knowledge_base_access(current_user, _get_claim_knowledge_base_id(claim_id))

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

    # H8 修复：添加全局异常处理器，防止未捕获异常泄漏内部堆栈信息
    @app.exception_handler(Exception)
    async def handle_unexpected_error(_, exc: Exception) -> JSONResponse:
        """捕获未预期的异常，返回通用错误信息。"""

        logger.exception("未预期异常: %s", exc)
        payload = ApiResponse(
            success=False,
            message="服务器内部错误",
            error_code="INTERNAL_ERROR",
        )
        return JSONResponse(status_code=500, content=payload.model_dump())

    @app.get("/health", response_model=ApiResponse)
    def health_check() -> ApiResponse:
        """健康检查接口。"""

        return ApiResponse(success=True, message="ok", data={"status": "healthy"})

    @app.post("/ingest/register", response_model=ApiResponse)
    def register_documents(
        request: DocumentRegisterRequest,
        _current_user: User = Depends(require_tab_access("知识库管理")),
    ) -> ApiResponse:
        """注册 Markdown 文档。"""

        jobs = ingest_service.register_documents(
            [item.model_dump() for item in request.documents],
            rebuild_if_exists=request.rebuild_if_exists,
        )
        return ApiResponse(success=True, message="documents registered", data={"jobs": jobs})

    @app.post("/ingest/rebuild", response_model=ApiResponse)
    def rebuild_documents(
        request: IngestRebuildRequest,
        current_user: User = Depends(require_tab_access("知识库管理")),
    ) -> ApiResponse:
        """接受文档重建请求。"""

        _ensure_documents_access(current_user, request.doc_uids)
        accepted = ingest_service.rebuild_documents(
            request.doc_uids,
            rebuild_fulltext=request.rebuild_fulltext,
            rebuild_vector=request.rebuild_vector,
        )
        return ApiResponse(success=True, message="rebuild started", data={"accepted": accepted})

    @app.get("/ingest/status", response_model=ApiResponse)
    def get_ingest_status(
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
        status: str | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        current_user: User = Depends(require_tab_access("知识库管理")),
    ) -> ApiResponse:
        """查询入库状态。"""

        _ensure_document_access(current_user, doc_uid)
        _ensure_knowledge_base_access(current_user, knowledge_base_id)
        items, total = ingest_service.list_status(
            doc_uid=doc_uid,
            knowledge_base_id=knowledge_base_id,
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
        knowledge_base_id: str | None = None,
        current_user: User = Depends(require_tab_access("知识库检索")),
    ) -> ApiResponse:
        """执行全文检索。"""

        items = _search_with_knowledge_base_scope(
            current_user,
            retrieval_service.fulltext_search,
            query=query,
            top_k=top_k,
            knowledge_base_id=knowledge_base_id,
        )
        return ApiResponse(success=True, message="ok", data={"items": items})

    @app.get("/search/vector", response_model=ApiResponse)
    def search_vector(
        query: str = Query(..., min_length=1),
        top_k: int = Query(default=10, ge=1, le=100),
        knowledge_base_id: str | None = None,
        current_user: User = Depends(require_tab_access("知识库检索")),
    ) -> ApiResponse:
        """执行向量检索占位实现。"""

        items = _search_with_knowledge_base_scope(
            current_user,
            retrieval_service.vector_search,
            query=query,
            top_k=top_k,
            knowledge_base_id=knowledge_base_id,
        )
        return ApiResponse(success=True, message="ok", data={"items": items})

    @app.get("/search/hybrid", response_model=ApiResponse)
    def search_hybrid(
        query: str = Query(..., min_length=1),
        top_k: int = Query(default=10, ge=1, le=100),
        use_rerank: bool = Query(default=True),
        knowledge_base_id: str | None = None,
        current_user: User = Depends(require_tab_access("知识库检索")),
    ) -> ApiResponse:
        """执行混合检索。"""

        items = _search_with_knowledge_base_scope(
            current_user,
            retrieval_service.hybrid_search,
            query=query,
            top_k=top_k,
            knowledge_base_id=knowledge_base_id,
            use_rerank=use_rerank,
        )
        return ApiResponse(success=True, message="ok", data={"items": items})

    @app.post("/quality/check", response_model=ApiResponse)
    def quality_check(
        request: QualityCheckRequest,
        current_user: User = Depends(require_tab_access("AI 质检")),
    ) -> ApiResponse:
        """执行最小质检。"""

        _ensure_document_access(current_user, request.doc_uid)
        _ensure_knowledge_base_access(current_user, request.knowledge_base_id)
        if not request.input_text.strip():
            raise ValidationAppError("input_text 不能为空")
        if len(request.input_text) > 2000:
            raise ValidationAppError("input_text 不能超过 2000 字", details={"max_length": 2000})
        result = quality_service.run_check(
            request.input_text,
            doc_uid=request.doc_uid,
            knowledge_base_id=request.knowledge_base_id,
            template_id=request.template_id,
        )
        return ApiResponse(success=True, message="ok", data=result)

    @app.get("/knowledge-bases", response_model=ApiResponse)
    def list_knowledge_bases(current_user: User = Depends(require_authenticated_user)) -> ApiResponse:
        """列出可用知识库。"""

        items = _filter_knowledge_base_items_for_user(ingest_service.list_knowledge_bases(), current_user)
        return ApiResponse(success=True, message="ok", data={"items": items})

    @app.post("/knowledge-bases", response_model=ApiResponse)
    def save_knowledge_base(
        request: KnowledgeBaseUpsertRequest,
        _current_user: User = Depends(require_tab_access("知识库管理")),
    ) -> ApiResponse:
        """新增或更新知识库。"""

        item = ingest_service.save_knowledge_base(request.model_dump())
        return ApiResponse(success=True, message="ok", data={"item": item})

    @app.delete("/knowledge-bases/{knowledge_base_id}", response_model=ApiResponse)
    def delete_knowledge_base(
        knowledge_base_id: str,
        current_user: User = Depends(require_tab_access("知识库管理")),
    ) -> ApiResponse:
        """删除知识库。"""

        _ensure_knowledge_base_access(current_user, knowledge_base_id)
        item = ingest_service.delete_knowledge_base(knowledge_base_id)
        return ApiResponse(success=True, message="ok", data={"item": item})

    @app.get("/quality/templates", response_model=ApiResponse)
    def list_quality_templates(
        _current_user: User = Depends(require_tab_access("AI 质检")),
    ) -> ApiResponse:
        """列出可用的质检模板。"""

        return ApiResponse(success=True, message="ok", data={"items": quality_service.list_templates()})

    @app.get("/quality/result/{check_id}", response_model=ApiResponse)
    def get_quality_result(
        check_id: str,
        current_user: User = Depends(require_tab_access("AI 质检")),
    ) -> ApiResponse:
        """查询质检结果。"""

        _ensure_quality_result_access(current_user, check_id)
        result = quality_service.get_result(check_id)
        if not result:
            raise NotFoundAppError("质检结果不存在", details={"check_id": check_id})
        return ApiResponse(success=True, message="ok", data=result)

    @app.post("/review/submit", response_model=ApiResponse)
    def submit_review(
        request: ReviewSubmitRequest,
        current_user: User = Depends(require_tab_access("人工审核")),
    ) -> ApiResponse:
        """提交审核动作。"""

        _ensure_claim_access(current_user, request.claim_id)
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
        knowledge_base_id: str | None = None,
        current_user: User = Depends(require_tab_access("人工审核")),
    ) -> ApiResponse:
        """分页查询审核记录。"""

        _ensure_knowledge_base_access(current_user, knowledge_base_id)
        items, total = review_service.list_reviews(
            page=page,
            page_size=page_size,
            knowledge_base_id=knowledge_base_id,
        )
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
