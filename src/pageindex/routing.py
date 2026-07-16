"""程序说明：提供 PageIndex 文档本地粗排与跨流程统一调用预算。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.common.errors import ValidationAppError


class RetrievalBudgetExceededError(ValidationAppError):
    """PageIndex 检索预算耗尽。"""

    def __init__(self, dimension: str, *, limit: int, used: int) -> None:
        super().__init__(
            "PageIndex 检索预算已耗尽",
            details={
                "dimension": dimension,
                "limit": int(limit),
                "used": int(used),
                "status": "budget_exhausted",
            },
        )


@dataclass
class PageIndexBudget:
    """记录单次 PageIndex 请求的 LLM、轮次、文档和证据上限。"""

    max_llm_calls: int
    max_rounds: int
    max_documents: int
    max_evidence: int
    llm_calls: int = 0
    rounds: int = 0
    exhausted: bool = False
    call_trace: list[str] = field(default_factory=list)
    round_trace: list[str] = field(default_factory=list)

    def consume_llm(self, reason: str) -> None:
        """在发起 LLM 请求前消费一次调用额度。"""

        if self.llm_calls >= max(int(self.max_llm_calls), 0):
            self.exhausted = True
            raise RetrievalBudgetExceededError(
                "llm_calls",
                limit=self.max_llm_calls,
                used=self.llm_calls,
            )
        self.llm_calls += 1
        self.call_trace.append(str(reason or "unspecified"))

    def consume_round(self, reason: str) -> None:
        """在开始新一轮节点选择前消费一次轮次额度。"""

        if self.rounds >= max(int(self.max_rounds), 0):
            self.exhausted = True
            raise RetrievalBudgetExceededError(
                "rounds",
                limit=self.max_rounds,
                used=self.rounds,
            )
        self.rounds += 1
        self.round_trace.append(str(reason or "unspecified"))

    def limit_documents(self, records: list[dict]) -> list[dict]:
        """限制本次请求最多处理的 PageIndex 文档数。"""

        return list(records[: max(int(self.max_documents), 0)])

    def limit_evidence(self, evidence: list[dict]) -> list[dict]:
        """限制进入判定和最终回答的证据总数。"""

        return list(evidence[: max(int(self.max_evidence), 0)])

    def snapshot(self) -> dict:
        """输出可写入调试信息的预算使用快照。"""

        return {
            "status": "budget_exhausted" if self.exhausted else "active",
            "llm_calls": self.llm_calls,
            "max_llm_calls": int(self.max_llm_calls),
            "rounds": self.rounds,
            "max_rounds": int(self.max_rounds),
            "max_documents": int(self.max_documents),
            "max_evidence": int(self.max_evidence),
            "call_trace": list(self.call_trace),
            "round_trace": list(self.round_trace),
        }


def route_documents(
    question: str,
    records: list[dict],
    analysis: dict,
    *,
    limit: int = 3,
) -> list[dict]:
    """按标题、描述、来源和问题分析词对文档做确定性本地粗排。"""

    normalized_question = _normalize_text(question)
    terms = _routing_terms(question, analysis)
    routed: list[dict] = []
    for original_index, record in enumerate(records if isinstance(records, list) else []):
        if not isinstance(record, dict):
            continue
        title = str(record.get("doc_title") or record.get("doc_name") or "")
        summary = " ".join(
            str(record.get(field) or "")
            for field in ("doc_description", "tree_summary", "summary", "source_path")
        )
        normalized_title = _normalize_text(title)
        normalized_summary = _normalize_text(summary)
        matched_terms: list[str] = []
        score = 0
        if normalized_question and normalized_question in normalized_title:
            score += 12
        for term in terms:
            normalized_term = _normalize_text(term)
            if not normalized_term:
                continue
            if normalized_term in normalized_title:
                score += 5
                matched_terms.append(term)
            elif normalized_term in normalized_summary:
                score += 2
                matched_terms.append(term)
        routed.append(
            {
                **record,
                "routing_score": score,
                "routing_reason": "、".join(dict.fromkeys(matched_terms)) or "稳定顺序兜底",
                "_routing_original_index": original_index,
            }
        )

    routed.sort(
        key=lambda item: (
            -int(item.get("routing_score") or 0),
            int(item.get("_routing_original_index") or 0),
            str(item.get("doc_uid") or ""),
        )
    )
    result: list[dict] = []
    for item in routed[: max(int(limit), 0)]:
        item = dict(item)
        item.pop("_routing_original_index", None)
        result.append(item)
    return result


def _routing_terms(question: str, analysis: dict) -> list[str]:
    """合并问题原词和分析结果，保持首次出现顺序。"""

    terms: list[str] = []
    for value in [question, *(analysis.get("entities") or []), *(analysis.get("keywords") or []), *(analysis.get("expanded_terms") or [])]:
        text = str(value or "").strip()
        if not text:
            continue
        if text not in terms:
            terms.append(text)
    return terms


def _normalize_text(value: object) -> str:
    """移除标点与空白，供中文标题做稳定包含匹配。"""

    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(value or "")).casefold()
