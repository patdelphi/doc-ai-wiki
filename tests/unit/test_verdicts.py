"""程序说明：验证质检 verdict 与证据关系的统一映射规则。"""

from src.quality.verdicts import (
    EvidenceRelation,
    QualityVerdict,
    build_overall_verdict,
    coerce_evidence_relation,
    merge_verdict_with_evidence_relation,
    most_conservative_verdict,
)


def test_merge_verdict_with_evidence_relation_should_reject_contradiction() -> None:
    """证据关系为反证时，模型 verdict 必须收口为 rejected。"""

    verdict = merge_verdict_with_evidence_relation(
        QualityVerdict.VERIFIED,
        EvidenceRelation.CONTRADICT,
    )

    assert verdict == QualityVerdict.REJECTED


def test_merge_verdict_with_evidence_relation_should_not_verify_insufficient_evidence() -> None:
    """证据不足时，即使模型给出 verified，也必须降为 needs_review。"""

    verdict = merge_verdict_with_evidence_relation(
        QualityVerdict.VERIFIED,
        EvidenceRelation.INSUFFICIENT,
    )

    assert verdict == QualityVerdict.NEEDS_REVIEW


def test_most_conservative_verdict_should_pick_highest_risk_value() -> None:
    """多个 verdict 合并时，应选择最保守的结果。"""

    verdict = most_conservative_verdict(
        QualityVerdict.VERIFIED,
        QualityVerdict.NEEDS_REVIEW,
        QualityVerdict.REJECTED,
    )

    assert verdict == QualityVerdict.REJECTED


def test_build_overall_verdict_should_keep_current_api_values() -> None:
    """总体 verdict 保持当前 API 口径：全 verified 输出 passed。"""

    assert build_overall_verdict([]) == QualityVerdict.NEEDS_REVIEW
    assert build_overall_verdict([QualityVerdict.VERIFIED, QualityVerdict.VERIFIED]) == "passed"
    assert build_overall_verdict([QualityVerdict.VERIFIED, QualityVerdict.NEEDS_REVIEW]) == QualityVerdict.NEEDS_REVIEW
    assert build_overall_verdict([QualityVerdict.REJECTED, QualityVerdict.VERIFIED]) == QualityVerdict.REJECTED


def test_coerce_evidence_relation_should_default_to_insufficient() -> None:
    """未知证据关系应默认按证据不足处理。"""

    assert coerce_evidence_relation("unknown") == EvidenceRelation.INSUFFICIENT
