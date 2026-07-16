"""程序说明：统一单知识库与多知识库检索范围的输入语义。"""

from __future__ import annotations

from collections.abc import Sequence


def normalize_knowledge_base_scope(
    knowledge_base_id: str | None,
    knowledge_base_ids: Sequence[str] | None,
) -> tuple[str, ...] | None:
    """归一化检索范围；空元组表示显式无权限，None 表示不限制。"""

    normalized_single = str(knowledge_base_id or "").strip()
    if normalized_single and knowledge_base_ids is not None:
        raise ValueError("knowledge_base_id 与 knowledge_base_ids 不能同时使用")
    if normalized_single:
        return (normalized_single,)
    if knowledge_base_ids is None:
        return None

    normalized_multiple: list[str] = []
    for value in knowledge_base_ids:
        normalized = str(value or "").strip()
        if normalized and normalized not in normalized_multiple:
            normalized_multiple.append(normalized)
    return tuple(normalized_multiple)
