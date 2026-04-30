"""程序说明：提供 Rerank 客户端抽象，支持禁用、本地降级、OpenAI 兼容接口与 DashScope。"""

from __future__ import annotations

import httpx

from src.common.config import AppSettings


class BaseReranker:
    """Rerank 客户端抽象基类。"""

    def rerank(self, *, query: str, items: list[dict], top_k: int) -> list[dict]:
        """根据查询对候选结果重排。"""

        raise NotImplementedError

    @property
    def enabled(self) -> bool:
        """返回当前客户端是否启用。"""

        return True


class DisabledReranker(BaseReranker):
    """禁用状态占位客户端。"""

    def rerank(self, *, query: str, items: list[dict], top_k: int) -> list[dict]:
        """禁用时保持原顺序返回。"""

        return items[:top_k]

    @property
    def enabled(self) -> bool:
        """禁用状态。"""

        return False


class OpenAICompatibleReranker(BaseReranker):
    """OpenAI 兼容 Rerank 接口。"""

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def rerank(self, *, query: str, items: list[dict], top_k: int) -> list[dict]:
        """调用 OpenAI 风格重排接口。"""

        if len(items) <= 1:
            return items[:top_k]

        response = httpx.post(
            self._resolve_endpoint(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "query": query,
                "documents": [item.get("content", "") for item in items],
                "top_n": top_k,
                "return_documents": False,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return _apply_rerank_results(items, payload.get("results", []), top_k=top_k)

    def _resolve_endpoint(self) -> str:
        """兼容传入根路径或完整 rerank 路径。"""

        if self.base_url.endswith("/rerank"):
            return self.base_url
        return f"{self.base_url}/rerank"


class DashScopeReranker(BaseReranker):
    """DashScope 文本重排接口。"""

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def rerank(self, *, query: str, items: list[dict], top_k: int) -> list[dict]:
        """调用 DashScope 文本重排接口。"""

        if len(items) <= 1:
            return items[:top_k]

        response = httpx.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": {
                    "query": query,
                    "documents": [item.get("content", "") for item in items],
                },
                "parameters": {
                    "top_n": top_k,
                    "return_documents": False,
                },
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return _apply_rerank_results(items, payload.get("output", {}).get("results", []), top_k=top_k)


def build_reranker(settings: AppSettings) -> BaseReranker:
    """根据配置构建 Rerank 客户端。"""

    if not settings.rerank_enabled:
        return DisabledReranker()

    provider = settings.rerank_provider.lower().strip()
    api_key = settings.rerank_api_key
    if not api_key:
        return DisabledReranker()

    if provider == "openai":
        return OpenAICompatibleReranker(
            base_url=settings.rerank_base_url or "https://api.openai.com/v1",
            api_key=api_key,
            model=settings.rerank_model,
            timeout_seconds=settings.rerank_timeout_seconds,
        )
    if provider == "dashscope":
        return DashScopeReranker(
            base_url=(
                settings.rerank_base_url
                or "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
            ),
            api_key=api_key,
            model=settings.rerank_model,
            timeout_seconds=settings.rerank_timeout_seconds,
        )
    return DisabledReranker()


def _apply_rerank_results(items: list[dict], results: list[dict], *, top_k: int) -> list[dict]:
    """按重排结果重建候选列表，并保留原始字段。"""

    reranked_items: list[dict] = []
    for result in results:
        index = result.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(items):
            continue
        reranked_items.append(
            {
                **items[index],
                "rerank_score": float(result.get("relevance_score", 0.0)),
            }
        )

    if reranked_items:
        return reranked_items[:top_k]
    return items[:top_k]
