"""程序说明：验证 PageIndex 文档粗排和全局检索预算。"""

from __future__ import annotations

import pytest

from src.pageindex.routing import (
    PageIndexBudget,
    RetrievalBudgetExceededError,
    route_documents,
)


def test_route_documents_should_limit_candidates_to_three() -> None:
    """本地粗排应优先质量检测文档并限制 Top-3。"""

    records = [
        {"doc_uid": "history_doc", "doc_title": "阿胶历史"},
        {"doc_uid": "quality_doc", "doc_title": "阿胶质量检测方法"},
        {"doc_uid": "risk_doc", "doc_title": "服用风险"},
        {"doc_uid": "culture_doc", "doc_title": "文化通典"},
    ]

    routed = route_documents(
        "质量检测",
        records,
        analysis={"keywords": ["质量", "检测"]},
        limit=3,
    )

    assert len(routed) == 3
    assert routed[0]["doc_uid"] == "quality_doc"
    assert routed[0]["routing_score"] > routed[1]["routing_score"]


def test_budget_should_stop_before_seventh_single_document_call() -> None:
    """预算达到上限后必须在下一次 LLM 调用前阻断。"""

    budget = PageIndexBudget(
        max_llm_calls=6,
        max_rounds=3,
        max_documents=1,
        max_evidence=8,
    )
    for _ in range(6):
        budget.consume_llm("test")

    with pytest.raises(RetrievalBudgetExceededError):
        budget.consume_llm("overflow")

    assert budget.snapshot()["llm_calls"] == 6
    assert budget.snapshot()["status"] == "budget_exhausted"


def test_budget_should_limit_documents_rounds_and_evidence() -> None:
    """文档、轮次和证据均应受同一个预算对象约束。"""

    budget = PageIndexBudget(
        max_llm_calls=7,
        max_rounds=2,
        max_documents=2,
        max_evidence=3,
    )

    assert budget.limit_documents([{"doc_uid": str(index)} for index in range(4)]) == [
        {"doc_uid": "0"},
        {"doc_uid": "1"},
    ]
    budget.consume_round("first")
    budget.consume_round("second")
    with pytest.raises(RetrievalBudgetExceededError):
        budget.consume_round("overflow")
    assert budget.limit_evidence([{"id": index} for index in range(5)]) == [
        {"id": 0},
        {"id": 1},
        {"id": 2},
    ]
