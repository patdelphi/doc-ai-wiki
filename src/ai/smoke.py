"""程序说明：提供 LLM、Embedding 与 Rerank 的最小连通性自检能力，便于快速验证 .env 配置是否可用。"""

from __future__ import annotations

import json

from src.ai.embedding import BaseEmbeddingClient, build_embedding_client
from src.ai.llm import BaseLLMClient, DisabledLLMClient, build_llm_client
from src.ai.rerank import BaseReranker, DisabledReranker, build_reranker
from src.common.config import AppSettings, get_settings
from src.common.errors import AppError


def run_model_smoke_test(settings: AppSettings | None = None) -> dict:
    """执行模型连通性自检并返回结构化结果。"""

    resolved_settings = settings or get_settings()
    llm_client = build_llm_client(resolved_settings)
    embedding_client = build_embedding_client(resolved_settings)
    reranker = build_reranker(resolved_settings)
    return {
        "llm": _run_llm_smoke_test(llm_client, resolved_settings),
        "embedding": _run_embedding_smoke_test(embedding_client, resolved_settings),
        "rerank": _run_rerank_smoke_test(reranker, resolved_settings),
    }


def print_model_smoke_test(settings: AppSettings | None = None) -> None:
    """打印模型自检结果，便于命令行直接使用。"""

    print(json.dumps(run_model_smoke_test(settings), ensure_ascii=False, indent=2))


def _run_llm_smoke_test(llm_client: BaseLLMClient, settings: AppSettings) -> dict:
    """执行 LLM 最小结构化调用。"""

    if isinstance(llm_client, DisabledLLMClient):
        return {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "enabled": False,
            "ok": False,
            "message": "LLM_PROVIDER 已禁用",
        }

    try:
        result = llm_client.evaluate_claim(
            claim_text="这是一个模型自检 claim。",
            evidence_list=[
                {
                    "doc_uid": "smoke_doc",
                    "source_span": "section-1:chunk-0",
                    "content": "这是用于模型连通性测试的证据片段。",
                }
            ],
            matched_rules=[],
        )
        return {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "enabled": True,
            "ok": True,
            "result": result,
        }
    except AppError as exc:
        return {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "enabled": True,
            "ok": False,
            "message": exc.message,
            "details": exc.details,
        }


def _run_embedding_smoke_test(embedding_client: BaseEmbeddingClient, settings: AppSettings) -> dict:
    """执行 Embedding 最小向量化调用。"""

    try:
        vectors = embedding_client.embed_texts(["这是一个 Embedding 连通性测试。"])
        dimension = len(vectors[0]) if vectors else 0
        return {
            "provider": settings.embedding_provider,
            "model": settings.embedding_model,
            "ok": True,
            "vector_count": len(vectors),
            "dimension": dimension,
        }
    except AppError as exc:
        return {
            "provider": settings.embedding_provider,
            "model": settings.embedding_model,
            "ok": False,
            "message": exc.message,
            "details": exc.details,
        }


def _run_rerank_smoke_test(reranker: BaseReranker, settings: AppSettings) -> dict:
    """执行 Rerank 最小重排调用。"""

    if isinstance(reranker, DisabledReranker):
        return {
            "provider": settings.rerank_provider,
            "model": settings.rerank_model,
            "enabled": False,
            "ok": False,
            "message": "Rerank 未启用或缺少密钥",
        }

    try:
        result = reranker.rerank(
            query="这是一个 rerank 自检 query。",
            items=[
                {"chunk_id": "smoke_1", "content": "这是第一条用于重排测试的候选内容。"},
                {"chunk_id": "smoke_2", "content": "这是第二条用于重排测试的候选内容。"},
            ],
            top_k=2,
        )
        # 生产检索允许 Rerank 失败后静默降级，但连通性门禁必须识别这种降级，避免假绿。
        if not result or not any(isinstance(item.get("rerank_score"), (int, float)) for item in result):
            return {
                "provider": settings.rerank_provider,
                "model": settings.rerank_model,
                "enabled": True,
                "ok": False,
                "message": "Rerank 请求未返回有效分数",
            }
        return {
            "provider": settings.rerank_provider,
            "model": settings.rerank_model,
            "enabled": True,
            "ok": True,
            "result_count": len(result),
            "top_chunk_id": result[0].get("chunk_id") if result else None,
            "top_score": result[0].get("rerank_score") if result else None,
        }
    except AppError as exc:
        return {
            "provider": settings.rerank_provider,
            "model": settings.rerank_model,
            "enabled": True,
            "ok": False,
            "message": exc.message,
            "details": exc.details,
        }


if __name__ == "__main__":
    print_model_smoke_test()
