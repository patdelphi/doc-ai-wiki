"""程序说明：定义接口层通用请求与响应模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field
from typing import Literal


def build_request_id() -> str:
    """生成请求标识，便于排查接口问题。"""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"req_{timestamp}_{uuid4().hex[:8]}"


class ApiResponse(BaseModel):
    """统一接口响应结构。"""

    success: bool
    message: str
    data: dict = Field(default_factory=dict)
    request_id: str = Field(default_factory=build_request_id)
    error_code: str | None = None
    details: dict | None = None


class Pagination(BaseModel):
    """分页结果结构。"""

    page: int = 1
    page_size: int = 20
    total: int = 0


class DocumentRegisterItem(BaseModel):
    """文档注册请求项。"""

    file_path: str
    knowledge_base_id: str | None = None
    doc_title: str | None = None
    edition: str | None = None
    author: str | None = None
    source_name: str | None = None
    tags: list[str] | None = None


class DocumentRegisterRequest(BaseModel):
    """文档注册请求。"""

    documents: list[DocumentRegisterItem]
    rebuild_if_exists: bool = False


class IngestStatusQuery(BaseModel):
    """入库状态查询参数。"""

    doc_uid: str | None = None
    knowledge_base_id: str | None = None
    status: str | None = None
    page: int = 1
    page_size: int = 20


class IngestRebuildRequest(BaseModel):
    """索引重建请求。"""

    doc_uids: list[str]
    rebuild_fulltext: bool = True
    rebuild_vector: bool = True


class KnowledgeBaseUpsertRequest(BaseModel):
    """知识库新增或更新请求。"""

    knowledge_base_id: str | None = None
    knowledge_base_name: str
    description: str = ""
    status: str = "active"
    is_default: bool = False


class ReviewSubmitRequest(BaseModel):
    """审核提交请求。H6 修复：review_action 限定合法枚举值。"""

    claim_id: str
    review_action: Literal["approved", "rejected", "updated"]
    reviewed_verdict: str | None = None
    review_note: str = ""
    reviewer: str = "system"


class QualityCheckRequest(BaseModel):
    """质检请求。"""

    input_text: str
    doc_uid: str | None = None
    knowledge_base_id: str | None = None
    template_id: str | None = None
