"""程序说明：提供 Embedding 客户端抽象，支持本地回退与 OpenAI 兼容接口。"""

from __future__ import annotations

from hashlib import md5

import httpx

from src.common.config import AppSettings
from src.common.errors import ExternalServiceAppError, ValidationAppError


class BaseEmbeddingClient:
    """Embedding 客户端抽象基类。"""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量。"""

        raise NotImplementedError


class DeterministicEmbeddingClient(BaseEmbeddingClient):
    """基于字符哈希的本地确定性向量，便于测试与离线回退。"""

    def __init__(self, dimension: int = 64) -> None:
        self.dimension = dimension

    def embed_text(self, text: str) -> list[float]:
        """将文本映射为固定维度向量。"""

        vector = [0.0] * self.dimension
        normalized = text.strip()
        if not normalized:
            return vector

        for char in normalized:
            digest = md5(char.encode("utf-8"), usedforsecurity=False).digest()
            index = digest[0] % self.dimension
            vector[index] += ((digest[1] % 17) + 1) / 17.0

        scale = float(len(normalized))
        return [value / scale for value in vector]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文本。"""

        return [self.embed_text(text) for text in texts]


class OpenAICompatibleEmbeddingClient(BaseEmbeddingClient):
    """OpenAI 兼容 Embedding 接口。"""

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI 兼容接口生成向量。"""

        if not texts:
            return []

        try:
            return self._request_embeddings(texts)
        except httpx.HTTPStatusError as exc:
            # 某些 OpenAI 兼容服务只支持单条 input，不支持批量数组输入。
            if len(texts) > 1:
                return [self._request_embeddings([text])[0] for text in texts]
            raise ExternalServiceAppError(
                "Embedding 服务调用失败",
                details=self._build_error_details(exc, input_count=len(texts)),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceAppError(
                "Embedding 服务调用失败",
                details={"provider": "openai", "model": self.model, "input_count": len(texts)},
            ) from exc

    def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        """向兼容接口发起一次 embedding 请求。"""

        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": texts},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return [item["embedding"] for item in payload.get("data", [])]

    def _build_error_details(self, exc: httpx.HTTPStatusError, *, input_count: int) -> dict:
        """提取兼容接口错误上下文，便于快速排查配置或协议问题。"""

        response_text = ""
        try:
            response_text = exc.response.text[:300]
        except Exception:  # noqa: BLE001
            response_text = ""
        return {
            "provider": "openai",
            "model": self.model,
            "status_code": exc.response.status_code,
            "input_count": input_count,
            "response_text": response_text,
        }


def build_embedding_client(settings: AppSettings) -> BaseEmbeddingClient:
    """根据配置构建 Embedding 客户端。"""

    provider = settings.embedding_provider.lower().strip()
    if provider == "local":
        return DeterministicEmbeddingClient()
    if provider == "openai":
        if not settings.embedding_api_key:
            raise ValidationAppError("缺少 EMBEDDING_API_KEY", details={"provider": provider})
        return OpenAICompatibleEmbeddingClient(
            base_url=settings.embedding_base_url or "https://api.openai.com/v1",
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            timeout_seconds=settings.embedding_timeout_seconds,
        )
    raise ValidationAppError("不支持的 EMBEDDING_PROVIDER", details={"provider": settings.embedding_provider})
