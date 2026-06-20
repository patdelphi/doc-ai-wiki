"""程序说明：集中定义质检 verdict、证据关系和保守合并规则。"""

from __future__ import annotations

from enum import StrEnum


class QualityVerdict(StrEnum):
    """当前 API 使用的 claim 级 verdict。"""

    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class EvidenceRelation(StrEnum):
    """证据与 claim 的关系。"""

    SUPPORT = "support"
    CONTRADICT = "contradict"
    INSUFFICIENT = "insufficient"


VERDICT_PRIORITY = {
    QualityVerdict.VERIFIED: 0,
    QualityVerdict.NEEDS_REVIEW: 1,
    QualityVerdict.REJECTED: 2,
}


def coerce_verdict(value: object, *, default: QualityVerdict = QualityVerdict.NEEDS_REVIEW) -> QualityVerdict:
    """将外部 verdict 值规范为内部枚举。"""

    try:
        return QualityVerdict(str(value or ""))
    except ValueError:
        return default


def coerce_evidence_relation(value: object, *, default: EvidenceRelation = EvidenceRelation.INSUFFICIENT) -> EvidenceRelation:
    """将外部证据关系值规范为内部枚举。"""

    try:
        return EvidenceRelation(str(value or "").lower())
    except ValueError:
        return default


def merge_verdict_with_evidence_relation(verdict: object, evidence_relation: object) -> QualityVerdict:
    """根据证据关系修正模型 verdict，避免过度放行。"""

    normalized_verdict = coerce_verdict(verdict)
    normalized_relation = coerce_evidence_relation(evidence_relation)
    if normalized_relation == EvidenceRelation.CONTRADICT:
        return QualityVerdict.REJECTED
    if normalized_relation == EvidenceRelation.INSUFFICIENT and normalized_verdict == QualityVerdict.VERIFIED:
        return QualityVerdict.NEEDS_REVIEW
    return normalized_verdict


def most_conservative_verdict(*verdicts: object) -> QualityVerdict:
    """从多个 verdict 中选择最保守的结果。"""

    normalized = [coerce_verdict(verdict) for verdict in verdicts]
    if not normalized:
        return QualityVerdict.NEEDS_REVIEW
    return max(normalized, key=lambda verdict: VERDICT_PRIORITY.get(verdict, 1))


def build_overall_verdict(verdicts: list[object]) -> str:
    """根据 claim verdict 生成当前 API 的总体 verdict。"""

    if not verdicts:
        return QualityVerdict.NEEDS_REVIEW.value
    normalized = {coerce_verdict(verdict) for verdict in verdicts}
    if QualityVerdict.REJECTED in normalized:
        return QualityVerdict.REJECTED.value
    if normalized == {QualityVerdict.VERIFIED}:
        return "passed"
    return QualityVerdict.NEEDS_REVIEW.value
