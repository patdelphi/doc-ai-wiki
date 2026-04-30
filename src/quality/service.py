"""程序说明：提供最小可用的结构化 claim 质检流程。"""

from __future__ import annotations

from uuid import uuid4

from src.common.utils import utc_now_iso
from src.db.repositories import QualityRepository
from src.retrieval.service import RetrievalService
from src.retrieval.vector_store import VectorStore
from src.rules.service import RuleService


class QualityService:
    """质检服务。"""

    def __init__(
        self,
        database_path,
        *,
        rules_dir=None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.database_path = database_path
        self.repository = QualityRepository(database_path)
        self.retrieval_service = RetrievalService(database_path)
        self.rule_service = RuleService(rules_dir) if rules_dir is not None else None
        if vector_store is not None:
            self.retrieval_service.set_vector_store(vector_store)

    def run_check(self, input_text: str, doc_uid: str | None = None) -> dict:
        """执行最小 claim 质检。"""

        claims = self._split_claims(input_text)
        check_id = f"chkres_{uuid4().hex[:12]}"
        now = utc_now_iso()
        claim_items: list[dict] = []
        rule_hits: list[dict] = []
        for claim_text in claims:
            claim_id = f"claim_{uuid4().hex[:12]}"
            matched_rules = self.rule_service.match_claim(claim_text) if self.rule_service else []
            evidence_list = self.retrieval_service.hybrid_search(claim_text, top_k=3)
            evaluation = self._evaluate_claim(evidence_list=evidence_list, matched_rules=matched_rules)
            evidence_text = (
                evidence_list[0]["content"][:200]
                if evaluation["has_evidence"]
                else "未检索到足够证据，需人工复核"
            )
            claim_items.append(
                {
                    "claim_id": claim_id,
                    "check_id": check_id,
                    "claim_text": claim_text,
                    "verdict": evaluation["verdict"],
                    "confidence": evaluation["confidence"],
                    "risk_level": evaluation["risk_level"],
                    "evidence": evidence_text,
                    "source_doc": evidence_list[0]["doc_uid"] if evaluation["has_evidence"] else doc_uid,
                    "source_span": evidence_list[0]["source_span"] if evaluation["has_evidence"] else None,
                    "review_status": "pending",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            for matched_rule in matched_rules:
                rule_hits.append(
                    {
                        "rule_hit_id": f"rhit_{uuid4().hex[:12]}",
                        "check_id": check_id,
                        "claim_id": claim_id,
                        "rule_code": matched_rule["rule_code"],
                        "rule_name": matched_rule["rule_name"],
                        "hit_level": matched_rule["hit_level"],
                        "hit_message": matched_rule["hit_message"],
                        "created_at": now,
                    }
                )

        overall_verdict = self._build_overall_verdict(claim_items)
        result = {
            "check": {
                "check_id": check_id,
                "input_text": input_text,
                "overall_verdict": overall_verdict,
                "risk_level": self._build_overall_risk_level(claim_items),
                "summary": self._build_summary(claim_items, rule_hits),
                "created_at": now,
                "updated_at": now,
            },
            "claims": claim_items,
            "rule_hits": rule_hits,
        }
        self.repository.create_quality_result(
            quality_check=result["check"],
            claims=result["claims"],
            rule_hits=result["rule_hits"],
        )
        return result

    def get_result(self, check_id: str) -> dict | None:
        """读取质检结果。"""

        return self.repository.get_quality_result(check_id)

    def list_recent_results(self, limit: int = 10) -> list[dict]:
        """读取最近质检结果。"""

        return self.repository.list_recent_quality_results(limit=limit)

    @staticmethod
    def _evaluate_claim(*, evidence_list: list[dict], matched_rules: list[dict]) -> dict:
        """综合证据与规则命中生成 claim 级结论。"""

        has_evidence = bool(evidence_list)
        max_hit_level = QualityService._max_rule_level(matched_rules)

        if max_hit_level == "block":
            return {"verdict": "rejected", "confidence": 0.15, "risk_level": "high", "has_evidence": has_evidence}
        if max_hit_level == "error":
            return {"verdict": "needs_review", "confidence": 0.35, "risk_level": "high", "has_evidence": has_evidence}
        if max_hit_level == "warn":
            return {"verdict": "needs_review", "confidence": 0.55, "risk_level": "medium", "has_evidence": has_evidence}
        if has_evidence:
            return {"verdict": "verified", "confidence": 0.85, "risk_level": "low", "has_evidence": True}
        return {"verdict": "needs_review", "confidence": 0.2, "risk_level": "medium", "has_evidence": False}

    @staticmethod
    def _max_rule_level(matched_rules: list[dict]) -> str | None:
        """取命中规则中的最高风险等级。"""

        if not matched_rules:
            return None
        priority = {"info": 0, "warn": 1, "error": 2, "block": 3}
        return max(
            (rule.get("hit_level", "warn") for rule in matched_rules),
            key=lambda level: priority.get(level, 1),
        )

    @staticmethod
    def _build_overall_verdict(claim_items: list[dict]) -> str:
        """根据 claim 结果生成总体结论。"""

        verdicts = {item["verdict"] for item in claim_items}
        if "rejected" in verdicts:
            return "rejected"
        if verdicts == {"verified"}:
            return "passed"
        return "needs_review"

    @staticmethod
    def _build_overall_risk_level(claim_items: list[dict]) -> str:
        """聚合 claim 风险为整体风险等级。"""

        priority = {"low": 0, "medium": 1, "high": 2}
        max_level = max(
            (item.get("risk_level", "low") for item in claim_items),
            key=lambda level: priority.get(level, 0),
        )
        return max_level

    @staticmethod
    def _build_summary(claim_items: list[dict], rule_hits: list[dict]) -> str:
        """生成简要摘要，便于前端直接展示。"""

        verified_count = sum(1 for item in claim_items if item["verdict"] == "verified")
        review_count = sum(1 for item in claim_items if item["verdict"] == "needs_review")
        rejected_count = sum(1 for item in claim_items if item["verdict"] == "rejected")
        return (
            f"共 {len(claim_items)} 条 claim，"
            f"verified {verified_count} 条，"
            f"needs_review {review_count} 条，"
            f"rejected {rejected_count} 条，"
            f"命中规则 {len(rule_hits)} 条。"
        )

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
