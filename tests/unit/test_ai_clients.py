"""程序说明：验证 LLM 与 Embedding 客户端的配置选择与回退逻辑。"""

from pathlib import Path

from src.common.config import AppSettings
from src.db.connection import initialize_database
from src.quality.service import QualityService


def test_openai_compatible_llm_client_should_send_enable_thinking_flag(monkeypatch) -> None:
    """OpenAI 兼容客户端应按配置传递 enable_thinking。"""

    from src.ai.llm import OpenAICompatibleLLMClient

    captured_payload: dict = {}

    class StubResponse:
        """测试用响应对象。"""

        def raise_for_status(self) -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"verdict":"verified","confidence":0.9,"risk_level":"low","reason":"ok"}'
                        }
                    }
                ]
            }

    def fake_post(*args, **kwargs):  # noqa: ANN002, ANN003
        captured_payload.update(kwargs["json"])
        return StubResponse()

    monkeypatch.setattr("src.ai.llm.httpx.post", fake_post)
    client = OpenAICompatibleLLMClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=30,
        max_tokens=256,
        temperature=0,
        top_p=1,
        enable_thinking=False,
    )

    result = client.evaluate_claim(
        claim_text="测试 claim",
        evidence_list=[{"doc_uid": "doc_1", "source_span": "s1", "content": "证据"}],
        matched_rules=[],
    )

    assert captured_payload["enable_thinking"] is False
    assert result["verdict"] == "verified"


def test_parse_llm_result_should_support_nested_interpretation() -> None:
    """解析器应兼容部分模型返回的 interpretation 包装结构。"""

    from src.ai.llm import _parse_llm_result

    result = _parse_llm_result(
        '{"status":"valid_json","interpretation":{"verdict":"needs_review","confidence":0.5,"risk_level":"medium","reason":"smoke"}}'
    )

    assert result["verdict"] == "needs_review"
    assert result["evidence_judgement"] == "insufficient"
    assert result["confidence"] == 0.5
    assert result["risk_level"] == "medium"
    assert result["reason"] == "smoke"


def test_build_llm_client_should_support_disabled_openai_and_anthropic(tmp_path: Path) -> None:
    """LLM 客户端工厂应支持 disabled、openai 和 anthropic 三种模式。"""

    from src.ai.llm import AnthropicLLMClient, DisabledLLMClient, OpenAICompatibleLLMClient, build_llm_client

    disabled_settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
        LLM_PROVIDER="disabled",
    )
    openai_settings = AppSettings(
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
        LLM_ENABLE_THINKING=False,
    )
    anthropic_settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
        LLM_PROVIDER="anthropic",
        LLM_API_KEY="test-key",
        LLM_MODEL="claude-test",
    )

    assert isinstance(build_llm_client(disabled_settings), DisabledLLMClient)
    assert isinstance(build_llm_client(openai_settings), OpenAICompatibleLLMClient)
    assert isinstance(build_llm_client(anthropic_settings), AnthropicLLMClient)


def test_build_embedding_client_should_support_local_and_openai(tmp_path: Path) -> None:
    """Embedding 客户端工厂应支持本地回退和 OpenAI 兼容接口。"""

    from src.ai.embedding import DeterministicEmbeddingClient, OpenAICompatibleEmbeddingClient, build_embedding_client

    local_settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
        EMBEDDING_PROVIDER="local",
    )
    openai_settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
        EMBEDDING_PROVIDER="openai",
        EMBEDDING_BASE_URL="https://example.com/v1",
        EMBEDDING_API_KEY="test-key",
        EMBEDDING_MODEL="text-embedding-test",
    )

    assert isinstance(build_embedding_client(local_settings), DeterministicEmbeddingClient)
    assert isinstance(build_embedding_client(openai_settings), OpenAICompatibleEmbeddingClient)


def test_openai_embedding_client_should_fallback_to_single_input_when_batch_rejected(monkeypatch) -> None:
    """批量 embedding 被兼容服务拒绝时，应自动退化为逐条请求。"""

    import httpx

    from src.ai.embedding import OpenAICompatibleEmbeddingClient

    call_inputs: list[list[str]] = []

    class StubResponse:
        """测试用响应对象。"""

        def __init__(self, *, status_code: int, payload: dict | None = None) -> None:
            self.status_code = status_code
            self._payload = payload or {}
            self.text = '{"error":"batch input not supported"}'
            self.request = httpx.Request("POST", "https://example.com/v1/embeddings")

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "Client error",
                    request=self.request,
                    response=httpx.Response(self.status_code, request=self.request, text=self.text),
                )

        def json(self) -> dict:
            return self._payload

    def fake_post(*args, **kwargs):  # noqa: ANN002, ANN003
        input_value = kwargs["json"]["input"]
        call_inputs.append(input_value)
        if len(input_value) > 1:
            return StubResponse(status_code=400)
        return StubResponse(
            status_code=200,
            payload={"data": [{"embedding": [float(len(input_value[0]))]}]},
        )

    monkeypatch.setattr("src.ai.embedding.httpx.Client.post", fake_post)
    client = OpenAICompatibleEmbeddingClient(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="embed-test",
        timeout_seconds=30,
    )

    result = client.embed_texts(["第一段", "第二段"])

    assert call_inputs == [["第一段", "第二段"], ["第一段"], ["第二段"]]
    assert result == [[3.0], [3.0]]


def test_quality_service_should_prefer_llm_client_when_available(tmp_path: Path) -> None:
    """配置了 LLM 客户端时，质检应优先使用 LLM 评估结果。"""

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
                "verdict": "needs_review",
                "confidence": 0.66,
                "risk_level": "medium",
                "reason": f'llm:{prompt_template.get("template_id") if prompt_template else "none"}:{claim_text}:{len(evidence_list)}:{len(matched_rules)}',
            }

    db_path = tmp_path / "app.db"
    initialize_database(db_path)

    service = QualityService(db_path, llm_client=StubLLMClient())
    service.retrieval_service.hybrid_search = lambda query, top_k=3, doc_uid=None, **kwargs: [  # type: ignore[method-assign]
        {"doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "证据内容"}
    ]

    result = service.run_check("需要 LLM 评估。", template_id="general_fact_check")

    assert result["claims"][0]["verdict"] == "needs_review"
    assert result["claims"][0]["confidence"] == 0.66
    assert result["claims"][0]["risk_level"] == "medium"
    assert result["claims"][0]["evidence_reason"].startswith("llm:general_fact_check:")
