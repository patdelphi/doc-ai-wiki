"""程序说明：验证单知识库与多知识库检索范围的统一语义。"""

from __future__ import annotations

import pytest

from src.retrieval.scope import normalize_knowledge_base_scope


def test_scope_should_keep_unrestricted_state() -> None:
    """未传范围时表示不限制知识库。"""

    assert normalize_knowledge_base_scope(None, None) is None


def test_scope_should_normalize_single_knowledge_base() -> None:
    """单知识库参数应转换为统一元组。"""

    assert normalize_knowledge_base_scope(" default ", None) == ("default",)


def test_scope_should_deduplicate_multiple_knowledge_bases() -> None:
    """多知识库范围应去空值并保序去重。"""

    assert normalize_knowledge_base_scope(None, ["medical", "", "default", "medical"]) == (
        "medical",
        "default",
    )


def test_scope_should_keep_explicit_empty_scope() -> None:
    """空列表表示无权限，不能退化为无限制。"""

    assert normalize_knowledge_base_scope(None, []) == ()


def test_scope_should_reject_single_and_multiple_values() -> None:
    """单值和多值同时出现时应拒绝歧义。"""

    with pytest.raises(ValueError, match="不能同时"):
        normalize_knowledge_base_scope("default", ["medical"])
