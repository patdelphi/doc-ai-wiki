"""程序说明：提供人工审核记录写入与查询能力。"""

from __future__ import annotations

from uuid import uuid4

from src.common.errors import ValidationAppError
from src.common.utils import utc_now_iso
from src.db.repositories import QualityRepository


class ReviewService:
    """审核服务。"""

    # H6 修复：合法审核动作白名单
    VALID_REVIEW_ACTIONS = {"approved", "rejected", "updated"}

    def __init__(self, database_path) -> None:
        self.repository = QualityRepository(database_path)

    def submit_review(
        self,
        *,
        claim_id: str,
        review_action: str,
        reviewed_verdict: str | None,
        review_note: str,
        reviewer: str,
    ) -> dict:
        """写入审核记录。H6 修复：校验 review_action 合法值。"""

        # 服务端二次校验，防止绕过 Pydantic 直接调用
        if review_action not in self.VALID_REVIEW_ACTIONS:
            raise ValidationAppError(
                "review_action 不合法",
                details={"allowed": list(self.VALID_REVIEW_ACTIONS), "received": review_action},
            )
        if not self.repository.get_claim_by_id(claim_id):
            raise ValidationAppError("Claim 不存在", details={"claim_id": claim_id})
        now = utc_now_iso()
        payload = {
            "review_id": f"rev_{uuid4().hex[:12]}",
            "claim_id": claim_id,
            "review_action": review_action,
            "reviewed_verdict": reviewed_verdict,
            "review_note": review_note,
            "reviewer": reviewer,
            "created_at": now,
        }
        self.repository.insert_review_record(payload)
        return payload

    def list_reviews(
        self,
        page: int = 1,
        page_size: int = 20,
        *,
        knowledge_base_id: str | None = None,
    ) -> tuple[list[dict], int]:
        """读取审核记录。"""

        return self.repository.list_reviews(
            page=page,
            page_size=page_size,
            knowledge_base_id=knowledge_base_id,
        )

    def list_review_candidates(self, limit: int = 50, *, knowledge_base_id: str | None = None) -> list[dict]:
        """读取可审核的 Claim 列表。"""

        return self.repository.list_review_candidates(limit=limit, knowledge_base_id=knowledge_base_id)

    def delete_review(self, review_id: str) -> dict:
        """删除指定审核记录。"""

        normalized_review_id = str(review_id or "").strip()
        if not normalized_review_id:
            raise ValidationAppError("review_id 不能为空")
        return self.repository.delete_review_record(normalized_review_id)
