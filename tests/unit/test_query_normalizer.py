"""程序说明：验证查询归一化与实体别名扩展能力。"""

from __future__ import annotations

from src.retrieval.query_normalizer import build_normalized_index_text, expand_query_texts, normalize_query_text


def test_normalize_query_text_should_apply_variants_and_aliases() -> None:
    """繁体/异体和别名应归一到标准实体名称，便于后续检索复用。"""

    normalized = normalize_query_text("驢皮膠能改善贫血吗")

    assert normalized == "阿胶能改善贫血吗"


def test_expand_query_texts_should_include_alias_and_canonical_queries() -> None:
    """别名查询应补充标准名和常见别名查询，并保持顺序稳定与去重。"""

    queries = expand_query_texts("驴皮胶 贫血", limit=6)

    assert queries[0] == "驴皮胶 贫血"
    assert "阿胶 贫血" in queries
    assert "东阿阿胶 贫血" in queries
    assert len(queries) == len(set(queries))


def test_expand_query_texts_should_include_population_aliases() -> None:
    """人群类同义表达应由外部实体词表统一扩展。"""

    queries = expand_query_texts("女性", limit=6)

    assert queries[0] == "女性"
    assert "妇女" in queries


def test_build_normalized_index_text_should_keep_source_and_add_canonical_terms() -> None:
    """入库索引文本应保留原文，同时追加归一后的标准实体，避免改写原始 chunk。"""

    index_text = build_normalized_index_text("驢皮膠是传统中药材料")

    assert "驢皮膠是传统中药材料" in index_text
    assert "阿胶是传统中药材料" in index_text
