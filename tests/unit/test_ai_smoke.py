"""程序说明：验证模型连通性自检模块的结果结构与异常回退逻辑。"""

from __future__ import annotations

from pathlib import Path

from src.common.config import AppSettings


def test_run_model_smoke_test_should_return_skipped_llm_and_local_embedding(tmp_path: Path) -> None:
    """禁用 LLM 且使用本地 Embedding 时，应返回可解释的自检结果。"""

    from src.ai.smoke import run_model_smoke_test

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
        LLM_PROVIDER="disabled",
        EMBEDDING_PROVIDER="local",
    )

    result = run_model_smoke_test(settings)

    assert result["llm"]["ok"] is False
    assert result["llm"]["enabled"] is False
    assert result["embedding"]["ok"] is True
    assert result["embedding"]["dimension"] == 64
    assert result["rerank"]["ok"] is False
    assert result["rerank"]["enabled"] is False


def test_run_model_smoke_test_should_return_client_results(monkeypatch, tmp_path: Path) -> None:
    """启用外部客户端时，应返回统一的自检结果结构。"""

    from src.ai.smoke import run_model_smoke_test

    class StubLLMClient:
        """测试用 LLM 客户端。"""

        def evaluate_claim(
            self,
            *,
            claim_text: str,
            evidence_list: list[dict],
            matched_rules: list[dict],
            prompt_template: dict | None = None,
        ) -> dict:
            return {
                "verdict": "verified",
                "confidence": 0.91,
                "risk_level": "low",
                "reason": f"llm:{claim_text}:{len(evidence_list)}",
            }

    class StubEmbeddingClient:
        """测试用 Embedding 客户端。"""

        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2, 0.3] for _ in texts]

    class StubReranker:
        """测试用 Rerank 客户端。"""

        def rerank(self, *, query: str, items: list[dict], top_k: int) -> list[dict]:
            return [{**items[1], "rerank_score": 0.88}, {**items[0], "rerank_score": 0.33}][:top_k]

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
        LLM_PROVIDER="openai",
        LLM_BASE_URL="https://example.com/v1",
        LLM_API_KEY="test-key",
        LLM_MODEL="gpt-test",
        EMBEDDING_PROVIDER="openai",
        EMBEDDING_BASE_URL="https://example.com/v1",
        EMBEDDING_API_KEY="test-key",
        EMBEDDING_MODEL="embedding-test",
        RERANK_ENABLED=True,
        RERANK_PROVIDER="openai",
        RERANK_MODEL="rerank-test",
        RERANK_API_KEY="test-key",
    )

    monkeypatch.setattr("src.ai.smoke.build_llm_client", lambda _: StubLLMClient())
    monkeypatch.setattr("src.ai.smoke.build_embedding_client", lambda _: StubEmbeddingClient())
    monkeypatch.setattr("src.ai.smoke.build_reranker", lambda _: StubReranker())

    result = run_model_smoke_test(settings)

    assert result["llm"]["ok"] is True
    assert result["llm"]["result"]["verdict"] == "verified"
    assert result["embedding"]["ok"] is True
    assert result["embedding"]["dimension"] == 3
    assert result["rerank"]["ok"] is True
    assert result["rerank"]["top_chunk_id"] == "smoke_2"


def test_rerank_smoke_should_reject_silent_fallback(monkeypatch, tmp_path: Path) -> None:
    """Rerank 请求静默降级为原顺序时，不得把连通性标记为成功。"""

    from src.ai.smoke import run_model_smoke_test

    class StubReranker:
        """模拟 HTTP 失败后返回原始候选的生产降级行为。"""

        def rerank(self, *, query: str, items: list[dict], top_k: int) -> list[dict]:
            return items[:top_k]

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
        LLM_PROVIDER="disabled",
        EMBEDDING_PROVIDER="local",
        RERANK_ENABLED=True,
        RERANK_PROVIDER="openai",
        RERANK_MODEL="rerank-test",
        RERANK_API_KEY="test-key",
    )
    monkeypatch.setattr("src.ai.smoke.build_reranker", lambda _: StubReranker())

    result = run_model_smoke_test(settings)

    assert result["rerank"]["ok"] is False
    assert result["rerank"]["message"] == "Rerank 请求未返回有效分数"
