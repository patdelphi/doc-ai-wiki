"""程序说明：提供最小可用的结构化 claim 质检流程。"""

from __future__ import annotations

from collections.abc import Iterator
import re
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

    _STRICT_EXCLUSIVE_MARKERS = ("只有", "唯一", "仅有", "仅限", "独家")
    _STRICT_UNIVERSAL_MARKERS = ("全部", "所有", "一律", "必然", "总是", "完全")
    _STRICT_NEGATION_MARKERS = ("不会", "不能", "没有", "不存在", "绝不", "从不")
    _LOGIC_STOPWORDS = (
        "只有",
        "唯一",
        "仅有",
        "仅限",
        "独家",
        "全部",
        "所有",
        "一律",
        "必然",
        "总是",
        "完全",
        "不会",
        "不能",
        "没有",
        "不存在",
        "绝不",
        "从不",
    )
    _COUNTER_EVIDENCE_MARKERS = (
        "也有",
        "还有",
        "并有",
        "不止",
        "不仅",
        "并非唯一",
        "之一",
        "多地",
        "各地",
        "多家",
        "多个",
        "均有",
    )

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

    def save_template(self, payload: dict) -> dict:
        """保存质检模板。"""

        return self.template_service.save_template(payload)

    def delete_template(self, template_id: str) -> dict:
        """删除质检模板。"""

        return self.template_service.delete_template(template_id)

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
            claim_logic = self._build_claim_logic_snapshot(claim_text)
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
            evidence_list = self._retrieve_evidence_candidates(
                claim_text=claim_text,
                doc_uid=doc_uid,
                retrieval_policy=retrieval_policy,
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
            evidence_list = self._annotate_evidence_relations(
                claim_text=claim_text,
                evidence_list=evidence_list,
                claim_logic=claim_logic,
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
                claim_logic=claim_logic,
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
                    "evidence_judgement": evaluation.get("evidence_judgement", "insufficient"),
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
        claim_logic: dict | None = None,
    ) -> dict:
        """优先使用 LLM 判定，失败时回退到启发式逻辑。"""

        heuristic = self._evaluate_claim(
            claim_text=claim_text,
            evidence_list=evidence_list,
            matched_rules=matched_rules,
            claim_logic=claim_logic,
        )
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
            merged_result = {
                "verdict": llm_result.get("verdict", heuristic["verdict"]),
                "confidence": float(llm_result.get("confidence", heuristic["confidence"])),
                "risk_level": llm_result.get("risk_level", heuristic["risk_level"]),
                "has_evidence": bool(evidence_list),
                "reason": llm_result.get("reason", ""),
                "evidence_judgement": llm_result.get("evidence_judgement", ""),
            }
            return self._merge_evaluation_result(heuristic=heuristic, llm_result=merged_result)
        except (ExternalServiceAppError, ValidationAppError):
            return heuristic

    def get_result(self, check_id: str) -> dict | None:
        """读取质检结果。"""

        return self.repository.get_quality_result(check_id)

    def list_recent_results(self, limit: int = 10) -> list[dict]:
        """读取最近质检结果。"""

        return self.repository.list_recent_quality_results(limit=limit)

    def run_evaluation_suite(
        self,
        cases: list[dict],
        *,
        doc_uid: str | None = None,
        template_id: str | None = None,
    ) -> dict:
        """批量执行 AI 质检效果评测，并输出汇总指标。"""

        if not cases:
            raise ValidationAppError("评测样例不能为空")

        rows: list[dict] = []
        for index, case in enumerate(cases, start=1):
            input_text = str(case.get("input_text") or "").strip()
            if not input_text:
                raise ValidationAppError(
                    "评测样例缺少 input_text",
                    details={"case_index": index, "case_id": case.get("case_id")},
                )

            result = self.run_check(input_text, doc_uid=doc_uid, template_id=template_id)
            check = result.get("check", {})
            claims = result.get("claims", [])

            expected_overall_verdict = case.get("expected_overall_verdict")
            expected_risk_level = case.get("expected_risk_level")
            expected_claim_count = case.get("expected_claim_count")

            actual_overall_verdict = check.get("overall_verdict")
            actual_risk_level = check.get("risk_level")
            actual_claim_count = len(claims)

            overall_verdict_matched = (
                True
                if expected_overall_verdict in (None, "")
                else str(expected_overall_verdict) == str(actual_overall_verdict)
            )
            risk_level_matched = (
                True
                if expected_risk_level in (None, "")
                else str(expected_risk_level) == str(actual_risk_level)
            )
            claim_count_matched = (
                True
                if expected_claim_count in (None, "")
                else int(expected_claim_count) == actual_claim_count
            )

            rows.append(
                {
                    "case_id": str(case.get("case_id") or f"case_{index}"),
                    "input_text": input_text,
                    "expected_overall_verdict": expected_overall_verdict,
                    "actual_overall_verdict": actual_overall_verdict,
                    "overall_verdict_matched": overall_verdict_matched,
                    "expected_risk_level": expected_risk_level,
                    "actual_risk_level": actual_risk_level,
                    "risk_level_matched": risk_level_matched,
                    "expected_claim_count": expected_claim_count,
                    "actual_claim_count": actual_claim_count,
                    "claim_count_matched": claim_count_matched,
                    "all_matched": overall_verdict_matched and risk_level_matched and claim_count_matched,
                    "check_id": check.get("check_id"),
                    "template_name": check.get("template_name"),
                    "summary": check.get("summary"),
                }
            )

        return {
            "summary": {
                "case_count": len(rows),
                "overall_verdict_match_count": sum(1 for item in rows if item["overall_verdict_matched"]),
                "risk_level_match_count": sum(1 for item in rows if item["risk_level_matched"]),
                "claim_count_match_count": sum(1 for item in rows if item["claim_count_matched"]),
                "exact_match_count": sum(1 for item in rows if item["all_matched"]),
            },
            "rows": rows,
        }

    @staticmethod
    def _evaluate_claim(
        *,
        claim_text: str,
        evidence_list: list[dict],
        matched_rules: list[dict],
        claim_logic: dict | None = None,
    ) -> dict:
        """综合证据、逻辑约束与规则命中生成 claim 级结论。"""

        has_evidence = bool(evidence_list)
        max_hit_level = QualityService._max_rule_level(matched_rules)
        logic_snapshot = claim_logic or QualityService._build_claim_logic_snapshot(claim_text)

        if max_hit_level == "block":
            return {"verdict": "rejected", "confidence": 0.15, "risk_level": "high", "has_evidence": has_evidence, "evidence_judgement": "contradict"}
        if QualityService._has_counter_evidence(evidence_list, logic_snapshot):
            return {"verdict": "rejected", "confidence": 0.25, "risk_level": "high", "has_evidence": has_evidence, "evidence_judgement": "contradict"}
        if max_hit_level == "error":
            return {"verdict": "needs_review", "confidence": 0.35, "risk_level": "high", "has_evidence": has_evidence, "evidence_judgement": "insufficient"}
        if max_hit_level == "warn":
            return {"verdict": "needs_review", "confidence": 0.55, "risk_level": "medium", "has_evidence": has_evidence, "evidence_judgement": "insufficient"}
        if logic_snapshot.get("requires_strict_evidence"):
            return {
                "verdict": "needs_review",
                "confidence": 0.45 if has_evidence else 0.2,
                "risk_level": "high" if logic_snapshot.get("has_exclusive") or logic_snapshot.get("has_negation") else "medium",
                "has_evidence": has_evidence,
                "evidence_judgement": "insufficient",
            }
        if has_evidence:
            return {"verdict": "verified", "confidence": 0.85, "risk_level": "low", "has_evidence": True, "evidence_judgement": "support"}
        return {"verdict": "needs_review", "confidence": 0.2, "risk_level": "medium", "has_evidence": False, "evidence_judgement": "insufficient"}

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
    def _merge_evaluation_result(*, heuristic: dict, llm_result: dict) -> dict:
        """合并启发式和模型结论，始终选择更保守的判定。"""

        verdict_priority = {"verified": 0, "needs_review": 1, "rejected": 2}
        risk_priority = {"low": 0, "medium": 1, "high": 2}

        heuristic_verdict = str(heuristic.get("verdict") or "needs_review")
        llm_verdict = str(llm_result.get("verdict") or heuristic_verdict)
        evidence_judgement = str(llm_result.get("evidence_judgement") or "").lower()
        if evidence_judgement == "contradict":
            llm_verdict = "rejected"
        elif evidence_judgement == "insufficient" and llm_verdict == "verified":
            llm_verdict = "needs_review"
        final_verdict = max(
            (heuristic_verdict, llm_verdict),
            key=lambda value: verdict_priority.get(value, 1),
        )

        heuristic_risk = str(heuristic.get("risk_level") or "medium")
        llm_risk = str(llm_result.get("risk_level") or heuristic_risk)
        final_risk = max(
            (heuristic_risk, llm_risk),
            key=lambda value: risk_priority.get(value, 1),
        )

        llm_confidence = float(llm_result.get("confidence", heuristic.get("confidence", 0.2)))
        heuristic_confidence = float(heuristic.get("confidence", llm_confidence))
        final_confidence = llm_confidence if final_verdict == llm_verdict else min(llm_confidence, heuristic_confidence)

        return {
            "verdict": final_verdict,
            "confidence": final_confidence,
            "risk_level": final_risk,
            "has_evidence": bool(llm_result.get("has_evidence", heuristic.get("has_evidence", False))),
            "evidence_judgement": evidence_judgement or str(heuristic.get("evidence_judgement") or "insufficient"),
            "reason": str(llm_result.get("reason") or heuristic.get("reason") or ""),
        }

    def _retrieve_evidence_candidates(self, *, claim_text: str, doc_uid: str | None, retrieval_policy: dict) -> list[dict]:
        """围绕原始 claim 和放宽后的逻辑查询召回支持证据与潜在反证。"""

        query_specs = self._build_retrieval_queries(claim_text)
        per_query_limit = max(int(retrieval_policy["final_top_k"]), 4)
        merged: dict[str, dict] = {}
        for query_spec in query_specs:
            items = self.retrieval_service.hybrid_search(
                query_spec["query"],
                top_k=per_query_limit,
                doc_uid=doc_uid,
                fulltext_top_k=max(int(retrieval_policy["fulltext_top_k"]), per_query_limit),
                vector_top_k=max(int(retrieval_policy["vector_top_k"]), per_query_limit),
                use_rerank=retrieval_policy["use_rerank"],
            )
            for item in items:
                chunk_id = str(item.get("chunk_id") or "")
                if not chunk_id:
                    continue
                existing = merged.get(chunk_id)
                if existing:
                    existing_queries = set(existing.get("matched_queries", []))
                    existing_queries.add(query_spec["label"])
                    existing["matched_queries"] = sorted(existing_queries)
                    continue
                merged[chunk_id] = {
                    **item,
                    "matched_queries": [query_spec["label"]],
                }

        return list(merged.values())[: max(per_query_limit, 6)]

    @classmethod
    def _build_retrieval_queries(cls, claim_text: str) -> list[dict]:
        """构建原始查询与放宽逻辑约束后的查询。"""

        query_specs = [{"label": "claim_literal", "query": claim_text.strip()}]
        normalized_query = cls._normalize_claim_query_for_retrieval(claim_text)
        if normalized_query and normalized_query != claim_text.strip():
            query_specs.append({"label": "logic_relaxed", "query": normalized_query})
        return query_specs

    @classmethod
    def _normalize_claim_query_for_retrieval(cls, claim_text: str) -> str:
        """移除逻辑约束词，保留主题实体与关系词，便于补召回反证。"""

        normalized = str(claim_text or "")
        for marker in cls._LOGIC_STOPWORDS:
            normalized = normalized.replace(marker, " ")
        normalized = re.sub(r"[，。！？；：、“”‘’\"'（）()\[\]{}<>《》]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @classmethod
    def _build_claim_logic_snapshot(cls, claim_text: str) -> dict:
        """识别 claim 中的逻辑约束类型，供检索与判定使用。"""

        text = str(claim_text or "")
        has_exclusive = any(marker in text for marker in cls._STRICT_EXCLUSIVE_MARKERS)
        has_universal = any(marker in text for marker in cls._STRICT_UNIVERSAL_MARKERS)
        has_negation = any(marker in text for marker in cls._STRICT_NEGATION_MARKERS)
        return {
            "has_exclusive": has_exclusive,
            "has_universal": has_universal,
            "has_negation": has_negation,
            "requires_strict_evidence": has_exclusive or has_universal or has_negation,
        }

    @classmethod
    def _has_counter_evidence(cls, evidence_list: list[dict], claim_logic: dict) -> bool:
        """根据逻辑约束判断当前证据中是否已出现明显反证信号。"""

        if not evidence_list or not claim_logic.get("requires_strict_evidence"):
            return False

        if any(str(item.get("evidence_relation") or "") == "contradict" for item in evidence_list):
            return True

        evidence_text = "\n".join(
            str(item.get("expanded_content") or item.get("content") or "")
            for item in evidence_list
        )
        if claim_logic.get("has_exclusive") and any(marker in evidence_text for marker in cls._COUNTER_EVIDENCE_MARKERS):
            return True
        if claim_logic.get("has_universal") and any(marker in evidence_text for marker in ("部分", "有些", "可能", "未必", "不一定", "之一")):
            return True
        return False

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
                "matched_queries": item.get("matched_queries", []),
                "rerank_score": item.get("rerank_score"),
                "context_mode": item.get("context_mode", "chunk"),
                "section_title": item.get("section_title", ""),
                "evidence_relation": item.get("evidence_relation", "insufficient"),
                "relation_reason": item.get("relation_reason", ""),
                "content_preview": str(item.get("expanded_content") or item.get("content", ""))[:300],
            }
            for item in evidence_list
        ]

    @classmethod
    def _annotate_evidence_relations(cls, *, claim_text: str, evidence_list: list[dict], claim_logic: dict) -> list[dict]:
        """为每条证据补充支持/矛盾/不足关系，便于前端解释。"""

        annotated_items: list[dict] = []
        for item in evidence_list:
            content = str(item.get("expanded_content") or item.get("content") or "")
            relation = "support"
            reason = "检索结果与当前 Claim 主题相关。"

            if claim_logic.get("requires_strict_evidence"):
                relation = "insufficient"
                reason = "该 Claim 含强逻辑约束，需要更直接的边界或排他性证据。"
                if cls._content_contains_counter_signal(content, claim_logic):
                    relation = "contradict"
                    reason = "证据中出现例外、并列对象或范围放宽，和 Claim 的强约束相冲突。"
                elif "logic_relaxed" in item.get("matched_queries", []):
                    reason = "该证据来自放宽逻辑约束后的补充检索，用于检查例外、边界或反证。"
            annotated_items.append(
                {
                    **item,
                    "evidence_relation": relation,
                    "relation_reason": reason,
                }
            )

        return sorted(annotated_items, key=cls._evidence_relation_sort_key)

    @classmethod
    def _content_contains_counter_signal(cls, content: str, claim_logic: dict) -> bool:
        """判断证据文本中是否含有与 Claim 强约束相冲突的信号。"""

        if not content:
            return False
        if claim_logic.get("has_exclusive") and any(marker in content for marker in cls._COUNTER_EVIDENCE_MARKERS):
            return True
        if claim_logic.get("has_universal") and any(marker in content for marker in ("部分", "有些", "可能", "未必", "不一定", "之一")):
            return True
        return False

    @staticmethod
    def _evidence_relation_sort_key(item: dict) -> tuple[int, float]:
        """让矛盾证据优先展示，其次支持证据。"""

        priority = {"contradict": 0, "support": 1, "insufficient": 2}
        relation = str(item.get("evidence_relation") or "insufficient")
        rerank_score = item.get("rerank_score")
        try:
            score = -float(rerank_score) if rerank_score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        return (priority.get(relation, 2), score)
