"""程序说明：验证正式评测集文件数量和基础字段。"""

from __future__ import annotations

from pathlib import Path

from src.retrieval.evaluation import load_jsonl_cases


EVALUATION_DIR = Path("tests/evaluation")


def test_retrieval_evaluation_cases_should_have_minimum_50_items() -> None:
    """检索评测集至少应包含 50 条问题与标准证据。"""

    cases = load_jsonl_cases(EVALUATION_DIR / "retrieval_cases.jsonl")

    assert len(cases) >= 50
    assert all(case.get("case_id") and case.get("query") for case in cases)
    assert all(case.get("expected_chunk_ids") or case.get("expected_doc_uids") for case in cases)


def test_claim_check_evaluation_cases_should_have_minimum_50_items() -> None:
    """Claim 评测集至少应包含 50 条人工标注 verdict。"""

    cases = load_jsonl_cases(EVALUATION_DIR / "claim_check_cases.jsonl")

    assert len(cases) >= 50
    assert all(case.get("case_id") and case.get("claim_text") for case in cases)
    assert all(case.get("expected_verdict") in {"verified", "needs_review", "rejected"} for case in cases)


def test_rule_evaluation_cases_should_cover_hit_and_non_hit_items() -> None:
    """规则评测集应同时覆盖命中与非命中样例。"""

    cases = load_jsonl_cases(EVALUATION_DIR / "rule_cases.jsonl")

    assert cases
    assert any(case.get("expected_hit") is True for case in cases)
    assert any(case.get("expected_hit") is False for case in cases)


def test_pageindex_evaluation_cases_should_have_minimum_50_items_and_modes() -> None:
    """PageIndex 评测集至少应包含 50 条，并区分真实 LLM 与离线降级模式。"""

    cases = load_jsonl_cases(EVALUATION_DIR / "pageindex_cases.jsonl")

    assert len(cases) >= 50
    assert all(case.get("case_id") and case.get("question") for case in cases)
    assert all(case.get("expected_doc_uid") or case.get("expected_node_title") for case in cases)
    assert any(case.get("requires_llm") is True for case in cases)
    assert any(case.get("requires_llm") is False for case in cases)
