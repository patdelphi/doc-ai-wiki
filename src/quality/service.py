"""程序说明：提供最小可用的结构化 claim 质检流程。"""

from __future__ import annotations

from uuid import uuid4

from src.common.utils import utc_now_iso
from src.db.repositories import QualityRepository
from src.retrieval.service import RetrievalService


class QualityService:
    """质检服务。"""

    def __init__(self, database_path) -> None:
        self.database_path = database_path
        self.repository = QualityRepository(database_path)
        self.retrieval_service = RetrievalService(database_path)

    def run_check(self, input_text: str, doc_uid: str | None = None) -> dict:
        """执行最小 claim 质检。"""

        claims = self._split_claims(input_text)
        check_id = f"chkres_{uuid4().hex[:12]}"
        now = utc_now_iso()
        claim_items: list[dict] = []
        for claim_text in claims:
            evidence_list = self.retrieval_service.hybrid_search(claim_text, top_k=3)
            has_evidence = bool(evidence_list)
            verdict = "verified" if has_evidence else "needs_review"
            confidence = 0.8 if has_evidence else 0.2
            evidence_text = (
                evidence_list[0]["content"][:200]
                if has_evidence
                else "未检索到足够证据，需人工复核"
            )
            claim_items.append(
                {
                    "claim_id": f"claim_{uuid4().hex[:12]}",
                    "check_id": check_id,
                    "claim_text": claim_text,
                    "verdict": verdict,
                    "confidence": confidence,
                    "evidence": evidence_text,
                    "source_doc": evidence_list[0]["doc_uid"] if has_evidence else doc_uid,
                    "source_span": evidence_list[0]["source_span"] if has_evidence else None,
                    "review_status": "pending",
                    "created_at": now,
                    "updated_at": now,
                }
            )

        overall_verdict = "passed" if all(item["verdict"] == "verified" for item in claim_items) else "needs_review"
        result = {
            "check": {
                "check_id": check_id,
                "input_text": input_text,
                "overall_verdict": overall_verdict,
                "risk_level": "medium" if overall_verdict == "needs_review" else "low",
                "summary": "系统已生成最小质检结果",
                "created_at": now,
                "updated_at": now,
            },
            "claims": claim_items,
        }
        self.repository.create_quality_result(
            quality_check=result["check"],
            claims=result["claims"],
        )
        return result

    def get_result(self, check_id: str) -> dict | None:
        """读取质检结果。"""

        return self.repository.get_quality_result(check_id)

    @staticmethod
    def _split_claims(input_text: str) -> list[str]:
        """按句号、分号和换行进行简单切分。"""

        normalized = (
            input_text.replace("；", "。")
            .replace(";", "。")
            .replace("\n", "。")
        )
        claims = [item.strip() for item in normalized.split("。") if item.strip()]
        return claims or [input_text.strip()]
