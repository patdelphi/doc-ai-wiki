"""程序说明：验证 RRF 融合、检索轨迹和外部服务降级。"""

from __future__ import annotations

from pathlib import Path

from src.common.errors import ExternalServiceAppError
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.service import RetrievalService


def test_rrf_should_prefer_item_found_by_both_retrievers() -> None:
    """双路召回的候选应优先于仅单路高排名候选。"""

    items = reciprocal_rank_fusion(
        {
            "fulltext": [
                {"chunk_id": "lexical_only", "content": "词法候选"},
                {"chunk_id": "shared", "content": "双路候选"},
            ],
            "vector": [
                {"chunk_id": "shared", "content": "双路候选"},
                {"chunk_id": "vector_only", "content": "向量候选"},
            ],
        }
    )

    assert items[0]["chunk_id"] == "shared"
    assert items[0]["matched_sources"] == ["fulltext", "vector"]
    assert items[0]["retrieval_source"] == "hybrid"
    assert [trace["source"] for trace in items[0]["retrieval_trace"]] == ["fulltext", "vector"]


def test_hybrid_search_should_keep_lexical_results_when_vector_fails() -> None:
    """向量服务不可用时，应保留本地词法结果并标明降级。"""

    service = RetrievalService(Path("unused.db"))
    service.fulltext_search = lambda *args, **kwargs: [  # type: ignore[method-assign]
        {"chunk_id": "local", "content": "本地证据", "retrieval_source": "fulltext"}
    ]

    def raise_vector_error(*_args, **_kwargs) -> list[dict]:
        raise ExternalServiceAppError("向量服务不可用")

    service.vector_search = raise_vector_error  # type: ignore[method-assign]

    items = service.hybrid_search("质量检测", top_k=3, use_rerank=False)

    assert items[0]["chunk_id"] == "local"
    assert items[0]["degraded_reason"] == "vector_unavailable"
    assert items[0]["matched_sources"] == ["fulltext"]


def test_hybrid_search_should_keep_rrf_order_when_rerank_fails() -> None:
    """Rerank 调用失败时，应返回 RRF 结果并标明降级。"""

    class FailingReranker:
        enabled = True

        def rerank(self, *, query: str, items: list[dict], top_k: int) -> list[dict]:
            raise ExternalServiceAppError("Rerank 服务不可用")

    service = RetrievalService(Path("unused.db"))
    service.set_reranker(FailingReranker())
    service.fulltext_search = lambda *args, **kwargs: [  # type: ignore[method-assign]
        {"chunk_id": "shared", "content": "双路证据", "retrieval_source": "fulltext"}
    ]
    service.vector_search = lambda *args, **kwargs: [  # type: ignore[method-assign]
        {"chunk_id": "shared", "content": "双路证据", "retrieval_source": "vector"},
        {"chunk_id": "vector_only", "content": "向量证据", "retrieval_source": "vector"},
    ]

    items = service.hybrid_search("质量检测", top_k=2, use_rerank=True)

    assert items[0]["chunk_id"] == "shared"
    assert items[0]["degraded_reason"] == "rerank_unavailable"


def test_search_queries_should_rerank_merged_candidates_only_once() -> None:
    """多查询应先合并候选，再执行一次批量 Rerank。"""

    class CountingReranker:
        enabled = True

        def __init__(self) -> None:
            self.call_count = 0

        def rerank(self, *, query: str, items: list[dict], top_k: int) -> list[dict]:
            self.call_count += 1
            return items[:top_k]

    reranker = CountingReranker()
    service = RetrievalService(Path("unused.db"))
    service.set_reranker(reranker)
    per_query_use_rerank: list[bool | None] = []

    def fake_hybrid_search(query: str, *, use_rerank: bool | None = None, **_kwargs) -> list[dict]:
        per_query_use_rerank.append(use_rerank)
        return [{"chunk_id": f"chunk_{query}", "content": query}]

    service.hybrid_search = fake_hybrid_search  # type: ignore[method-assign]

    items = service.search_queries(
        [
            {"label": "claim_literal", "query": "q1"},
            {"label": "semantic_normalized", "query": "q2"},
            {"label": "counter_probe", "query": "q3"},
        ],
        top_k=5,
        knowledge_base_id="default",
        use_rerank=True,
    )

    assert len(items) == 3
    assert per_query_use_rerank == [False, False, False]
    assert reranker.call_count == 1
