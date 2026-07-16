"""程序说明：验证 Rerank 客户端构建与检索链路重排能力。"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from src.common.config import AppSettings
from src.retrieval.service import RetrievalService


def test_build_reranker_should_return_disabled_when_key_missing(tmp_path: Path) -> None:
    """未配置重排密钥时，应自动降级为禁用客户端。"""

    from src.ai.rerank import DisabledReranker, build_reranker

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
        RERANK_ENABLED=True,
        RERANK_PROVIDER="dashscope",
        RERANK_MODEL="gte-rerank-v2",
    )

    reranker = build_reranker(settings)

    assert isinstance(reranker, DisabledReranker)
    assert reranker.enabled is False


def test_openai_compatible_reranker_should_apply_scores(monkeypatch) -> None:
    """OpenAI 风格重排结果应回填到候选列表。"""

    from src.ai.rerank import OpenAICompatibleReranker

    class StubResponse:
        """测试用 HTTP 响应。"""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.99},
                    {"index": 0, "relevance_score": 0.55},
                ]
            }

    captured: dict = {}

    def fake_post(url, *, headers, json, timeout):  # noqa: ANN001
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return StubResponse()

    monkeypatch.setattr("src.ai.rerank.httpx.post", fake_post)
    reranker = OpenAICompatibleReranker(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="rerank-test",
        timeout_seconds=30,
    )

    result = reranker.rerank(
        query="检索问题",
        items=[
            {"chunk_id": "c1", "content": "第一段"},
            {"chunk_id": "c2", "content": "第二段"},
        ],
        top_k=2,
    )

    assert captured["url"] == "https://example.com/v1/rerank"
    assert captured["json"]["query"] == "检索问题"
    assert result[0]["chunk_id"] == "c2"
    assert result[0]["rerank_score"] == 0.99


def test_openai_compatible_reranker_should_propagate_connection_error(monkeypatch) -> None:
    """网络失败应交由检索编排层统一标记降级。"""

    from src.ai.rerank import OpenAICompatibleReranker

    def fake_post(*args, **kwargs):  # noqa: ANN002, ANN003
        request = httpx.Request("POST", "https://example.com/v1/rerank")
        raise httpx.ConnectError("连接失败", request=request)

    monkeypatch.setattr("src.ai.rerank.httpx.post", fake_post)
    reranker = OpenAICompatibleReranker(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="rerank-test",
        timeout_seconds=30,
    )

    with pytest.raises(httpx.ConnectError):
        reranker.rerank(
            query="检索问题",
            items=[{"content": "第一段"}, {"content": "第二段"}],
            top_k=2,
        )


def test_openai_compatible_reranker_should_reject_empty_results(monkeypatch) -> None:
    """空重排结果不能伪装成成功。"""

    from src.ai.rerank import OpenAICompatibleReranker

    class StubResponse:
        """测试用空结果响应。"""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"results": []}

    monkeypatch.setattr("src.ai.rerank.httpx.post", lambda *args, **kwargs: StubResponse())
    reranker = OpenAICompatibleReranker(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="rerank-test",
        timeout_seconds=30,
    )

    with pytest.raises(ValueError, match="有效结果"):
        reranker.rerank(
            query="检索问题",
            items=[{"content": "第一段"}, {"content": "第二段"}],
            top_k=2,
        )


def test_retrieval_service_should_rerank_hybrid_results() -> None:
    """混合检索启用重排时，应按 rerank 结果返回。"""

    class StubReranker:
        """测试用重排器。"""

        enabled = True

        def rerank(self, *, query: str, items: list[dict], top_k: int) -> list[dict]:
            assert query == "测试问题"
            return [
                {**items[1], "rerank_score": 0.91},
                {**items[0], "rerank_score": 0.33},
            ][:top_k]

    service = RetrievalService(Path("test.db"))
    service.set_reranker(StubReranker())
    service.fulltext_search = lambda query, top_k=5, doc_uid=None, knowledge_base_id=None: [  # type: ignore[method-assign]
        {"chunk_id": "c1", "doc_uid": "doc_1", "doc_title": "文档1", "content": "第一段", "retrieval_source": "fulltext"}
    ]
    service.vector_search = lambda query, top_k=5, doc_uid=None, knowledge_base_id=None: [  # type: ignore[method-assign]
        {"chunk_id": "c2", "doc_uid": "doc_1", "doc_title": "文档1", "content": "第二段", "retrieval_source": "vector"}
    ]

    items = service.hybrid_search("测试问题", top_k=2, use_rerank=True)

    assert items[0]["chunk_id"] == "c2"
    assert items[0]["rerank_score"] == 0.91
    assert items[0]["matched_sources"] == ["vector"]
