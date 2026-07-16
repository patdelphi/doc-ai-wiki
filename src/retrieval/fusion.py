"""程序说明：提供多路检索结果的 RRF 融合。"""

from __future__ import annotations


def reciprocal_rank_fusion(
    result_sets: dict[str, list[dict]],
    *,
    rank_constant: int = 60,
) -> list[dict]:
    """按倒数排名融合多个候选列表。"""

    resolved_constant = max(int(rank_constant), 1)
    merged: dict[str, dict] = {}
    scores: dict[str, float] = {}
    best_ranks: dict[str, int] = {}
    traces: dict[str, list[dict]] = {}
    sources: dict[str, list[str]] = {}

    for source, items in result_sets.items():
        normalized_source = str(source or "").strip()
        if not normalized_source:
            continue
        for rank, candidate in enumerate(items, start=1):
            chunk_id = str(candidate.get("chunk_id") or "").strip()
            if not chunk_id:
                continue
            contribution = 1.0 / (resolved_constant + rank)
            if chunk_id not in merged:
                merged[chunk_id] = dict(candidate)
                traces[chunk_id] = []
                sources[chunk_id] = []
            elif len(str(candidate.get("content") or "")) > len(str(merged[chunk_id].get("content") or "")):
                # 同一片段以内容更完整的候选为主，同时保留首个候选的元数据。
                merged[chunk_id] = {**candidate, **merged[chunk_id], "content": candidate.get("content")}
            scores[chunk_id] = scores.get(chunk_id, 0.0) + contribution
            best_ranks[chunk_id] = min(best_ranks.get(chunk_id, rank), rank)
            traces[chunk_id].append(
                {
                    "source": normalized_source,
                    "rank": rank,
                    "contribution": contribution,
                }
            )
            if normalized_source not in sources[chunk_id]:
                sources[chunk_id].append(normalized_source)

    fused: list[dict] = []
    for chunk_id, item in merged.items():
        matched_sources = sources[chunk_id]
        fused.append(
            {
                **item,
                "rrf_score": scores[chunk_id],
                "matched_sources": matched_sources,
                "retrieval_source": "hybrid" if len(matched_sources) > 1 else matched_sources[0],
                "retrieval_trace": traces[chunk_id],
            }
        )
    return sorted(
        fused,
        key=lambda item: (
            -float(item.get("rrf_score") or 0.0),
            best_ranks[str(item.get("chunk_id") or "")],
            str(item.get("chunk_id") or ""),
        ),
    )
