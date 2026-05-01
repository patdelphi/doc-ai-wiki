"""程序说明：提供最小可用的结构化 claim 质检流程。"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

from src.ai.llm import BaseLLMClient
from src.ai.rerank import BaseReranker
from src.common.errors import ExternalServiceAppError, ValidationAppError
from src.common.utils import utc_now_iso
from src.db.repositories import QualityRepository
from src.quality.templates import QualityTemplateService
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
        templates_dir=None,
        vector_store: VectorStore | None = None,
        reranker: BaseReranker | None = None,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.database_path = database_path
        self.repository = QualityRepository(database_path)
        self.retrieval_service = RetrievalService(database_path)
        self.rule_service = RuleService(rules_dir) if rules_dir is not None else None
        self.template_service = QualityTemplateService(templates_dir)
        self.llm_client = llm_client
        if vector_store is not None:
            self.retrieval_service.set_vector_store(vector_store)
        if reranker is not None:
            self.retrieval_service.set_reranker(reranker)

    def list_templates(self) -> list[dict]:
        """列出可选质检模板。"""

        return self.template_service.list_templates()

    def get_template(self, template_id: str | None = None) -> dict:
        """读取指定质检模板内容。"""

        return self.template_service.get_template(template_id)

    def run_check(
        self,
        input_text: str,
        doc_uid: str | None = None,
        template_id: str | None = None,
    ) -> dict:
        """执行最小 claim 质检。"""

        final_result: dict | None = None
        for event in self.run_check_stream(input_text, doc_uid=doc_uid, template_id=template_id):
            if event.get("type") == "result":
                final_result = event.get("result")
        return final_result or {"check": {}, "claims": [], "rule_hits": []}

    def run_check_stream(
        self,
        input_text: str,
        doc_uid: str | None = None,
        template_id: str | None = None,
    ) -> Iterator[dict]:
        """流式执行质检，逐步返回进度事件和最终结果。"""

        claims = self._split_claims(input_text)
        selected_template = self.template_service.get_template(template_id)
        retrieval_policy = self._build_retrieval_policy(selected_template)
        active_rule_tags = selected_template.get("rule_tags", [])
        check_id = f"chkres_{uuid4().hex[:12]}"
        now = utc_now_iso()
        claim_items: list[dict] = []
        rule_hits: list[dict] = []
        total_claims = len(claims)
        llm_enabled = self.llm_client is not None

        yield {
            "type": "progress",
            "status": "running",
            "stage": "prepare",
            "message": "正在解析输入内容并准备本次质检。",
            "claim_index": 0,
            "claim_total": total_claims,
            "template_name": selected_template.get("template_name"),
            "model_status": "已配置模型" if llm_enabled else "未配置模型，将使用规则与启发式判定",
        }
        yield {
            "type": "progress",
            "status": "running",
            "stage": "template",
            "message": f'已加载模板“{selected_template.get("template_name", "")}”，准备开始逐条质检。',
            "claim_index": 0,
            "claim_total": total_claims,
            "template_name": selected_template.get("template_name"),
            "model_status": "已配置模型" if llm_enabled else "未配置模型，将使用规则与启发式判定",
        }

        for index, claim_text in enumerate(claims, start=1):
            claim_id = f"claim_{uuid4().hex[:12]}"
            claim_preview = claim_text[:60]
            yield {
                "type": "progress",
                "status": "running",
                "stage": "rules",
                "message": f"正在匹配规则：第 {index}/{total_claims} 条 Claim",
                "claim_index": index,
                "claim_total": total_claims,
                "claim_text": claim_preview,
                "template_name": selected_template.get("template_name"),
                "model_status": "已配置模型" if llm_enabled else "未配置模型，将使用规则与启发式判定",
            }
            matched_rules = (
                self.rule_service.match_claim(claim_text, active_tags=active_rule_tags)
                if self.rule_service
                else []
            )

            yield {
                "type": "progress",
                "status": "running",
                "stage": "retrieval",
                "message": f"正在检索证据：第 {index}/{total_claims} 条 Claim",
                "claim_index": index,
                "claim_total": total_claims,
                "claim_text": claim_preview,
                "template_name": selected_template.get("template_name"),
                "model_status": "已配置模型" if llm_enabled else "未配置模型，将使用规则与启发式判定",
            }
            evidence_list = self.retrieval_service.hybrid_search(
                claim_text,
                top_k=retrieval_policy["final_top_k"],
                doc_uid=doc_uid,
                fulltext_top_k=retrieval_policy["fulltext_top_k"],
                vector_top_k=retrieval_policy["vector_top_k"],
                use_rerank=retrieval_policy["use_rerank"],
            )

            yield {
                "type": "progress",
                "status": "running",
                "stage": "context",
                "message": f"正在整理证据上下文：第 {index}/{total_claims} 条 Claim",
                "claim_index": index,
                "claim_total": total_claims,
                "claim_text": claim_preview,
                "template_name": selected_template.get("template_name"),
                "model_status": "已配置模型" if llm_enabled else "未配置模型，将使用规则与启发式判定",
            }
            evidence_list = self.retrieval_service.expand_evidence_context(
                evidence_list,
                neighbor_window=retrieval_policy["neighbor_window"],
                include_section_context=retrieval_policy["include_section_context"],
                section_max_chars=retrieval_policy["section_max_chars"],
            )

            yield {
                "type": "progress",
                "status": "running",
                "stage": "model",
                "message": (
                    f"正在调用模型判定：第 {index}/{total_claims} 条 Claim"
                    if llm_enabled
                    else f"当前未配置模型，使用规则与启发式判定：第 {index}/{total_claims} 条 Claim"
                ),
                "claim_index": index,
                "claim_total": total_claims,
                "claim_text": claim_preview,
                "template_name": selected_template.get("template_name"),
                "model_status": "正在调用模型" if llm_enabled else "未调用模型",
            }
            evaluation = self._evaluate_claim_with_fallback(
                claim_text=claim_text,
                evidence_list=evidence_list,
                matched_rules=matched_rules,
                prompt_template=selected_template,
            )
            evidence_text = (
                (evidence_list[0].get("expanded_content") or evidence_list[0]["content"])[:200]
                if evaluation["has_evidence"]
                else "未检索到足够证据，需人工复核"
            )
            evidence_details = self._build_evidence_details(evidence_list)
            claim_items.append(
                {
                    "claim_id": claim_id,
                    "check_id": check_id,
                    "claim_text": claim_text,
                    "verdict": evaluation["verdict"],
                    "confidence": evaluation["confidence"],
                    "risk_level": evaluation["risk_level"],
                    "evidence": evidence_text,
                    "evidence_details": evidence_details,
                    "evidence_reason": evaluation.get("reason", ""),
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

        yield {
            "type": "progress",
            "status": "running",
            "stage": "persist",
            "message": "正在写入质检结果和 Claim 记录。",
            "claim_index": total_claims,
            "claim_total": total_claims,
            "template_name": selected_template.get("template_name"),
            "model_status": "已完成模型判定" if llm_enabled else "本次未调用模型",
        }
        overall_verdict = self._build_overall_verdict(claim_items)
        result = {
            "check": {
                "check_id": check_id,
                "input_text": input_text,
                "template_id": selected_template["template_id"],
                "template_name": selected_template["template_name"],
                "active_rule_tags": active_rule_tags,
                "retrieval_policy": retrieval_policy,
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
        yield {
            "type": "result",
            "status": "success",
            "stage": "persist",
            "result": result,
            "message": "质检已完成。",
            "claim_total": total_claims,
            "template_name": selected_template.get("template_name"),
            "model_status": "模型已参与判定" if llm_enabled else "本次未调用模型",
        }

    def _evaluate_claim_with_fallback(
        self,
        *,
        claim_text: str,
        evidence_list: list[dict],
        matched_rules: list[dict],
        prompt_template: dict | None = None,
    ) -> dict:
        """优先使用 LLM 判定，失败时回退到启发式逻辑。"""

        heuristic = self._evaluate_claim(evidence_list=evidence_list, matched_rules=matched_rules)
        heuristic["reason"] = "heuristic"
        if self.llm_client is None:
            return heuristic

        try:
            llm_result = self.llm_client.evaluate_claim(
                claim_text=claim_text,
                evidence_list=evidence_list,
                matched_rules=matched_rules,
                prompt_template=prompt_template,
            )
            return {
                "verdict": llm_result.get("verdict", heuristic["verdict"]),
                "confidence": float(llm_result.get("confidence", heuristic["confidence"])),
                "risk_level": llm_result.get("risk_level", heuristic["risk_level"]),
                "has_evidence": bool(evidence_list),
                "reason": llm_result.get("reason", ""),
            }
        except (ExternalServiceAppError, ValidationAppError):
            return heuristic

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

    @staticmethod
    def _build_retrieval_policy(template: dict) -> dict:
        """基于模板读取检索策略，并补齐默认值。"""

        policy = template.get("retrieval_policy", {}) if isinstance(template.get("retrieval_policy", {}), dict) else {}
        return {
            "fulltext_top_k": int(policy.get("fulltext_top_k", 3)),
            "vector_top_k": int(policy.get("vector_top_k", 3)),
            "final_top_k": int(policy.get("final_top_k", 3)),
            "use_rerank": bool(policy.get("use_rerank", False)),
            "neighbor_window": int(policy.get("neighbor_window", 0)),
            "include_section_context": bool(policy.get("include_section_context", False)),
            "section_max_chars": int(policy.get("section_max_chars", 400)),
        }

    @staticmethod
    def _build_evidence_details(evidence_list: list[dict]) -> list[dict]:
        """提取证据级解释字段，便于接口和 UI 展示。"""

        return [
            {
                "chunk_id": item.get("chunk_id"),
                "doc_uid": item.get("doc_uid"),
                "doc_title": item.get("doc_title", ""),
                "source_span": item.get("source_span"),
                "retrieval_source": item.get("retrieval_source", ""),
                "matched_sources": item.get("matched_sources", []),
                "rerank_score": item.get("rerank_score"),
                "context_mode": item.get("context_mode", "chunk"),
                "section_title": item.get("section_title", ""),
                "content_preview": str(item.get("expanded_content") or item.get("content", ""))[:300],
            }
            for item in evidence_list
        ]
