"""程序说明：验证中文 Trigram/BM25 检索与两字短词兜底。"""

from __future__ import annotations

from pathlib import Path

from src.db.connection import create_connection, initialize_database
from src.retrieval.lexical import LexicalRetriever


def _build_lexical_database(tmp_path: Path) -> Path:
    """构造包含短语频次和标题命中的本地检索库。"""

    database_path = tmp_path / "lexical.db"
    initialize_database(database_path)
    now = "2026-07-16T00:00:00+00:00"
    documents = [
        ("doc_exact", "阿胶质量检测指南"),
        ("doc_single", "质量研究资料"),
        ("doc_body", "其他研究资料"),
    ]
    chunks = [
        ("quality_exact", "doc_exact", 0, "阿胶质量检测包括真伪鉴别，阿胶质量检测还包括理化检测。"),
        ("quality_single", "doc_single", 1, "本研究介绍阿胶质量检测的基本流程。"),
        ("body_match", "doc_body", 2, "阿胶阿胶阿胶的历史资料。"),
    ]
    with create_connection(database_path) as connection:
        for doc_uid, title in documents:
            connection.execute(
                """
                INSERT INTO documents (
                    doc_uid, knowledge_base_id, doc_id, doc_title, source_path, source_hash,
                    ingest_status, index_status, created_at, updated_at
                ) VALUES (?, 'default', ?, ?, ?, ?, 'completed', 'indexed', ?, ?)
                """,
                (doc_uid, doc_uid, title, f"default/{doc_uid}.md", f"hash-{doc_uid}", now, now),
            )
        for chunk_id, doc_uid, chunk_index, content in chunks:
            connection.execute(
                """
                INSERT INTO chunks (
                    chunk_id, doc_uid, chunk_index, content, token_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, doc_uid, chunk_index, content, len(content), now, now),
            )
            connection.execute(
                "INSERT INTO chunk_fts (chunk_id, doc_uid, content) VALUES (?, ?, ?)",
                (chunk_id, doc_uid, content),
            )
        connection.commit()
    return database_path


def test_lexical_search_should_rank_repeated_chinese_phrase_first(tmp_path: Path) -> None:
    """BM25 应将包含更多完整中文短语的片段排在前面。"""

    database_path = _build_lexical_database(tmp_path)

    items = LexicalRetriever(database_path).search("阿胶质量检测", top_k=5)

    assert [item["chunk_id"] for item in items[:2]] == ["quality_exact", "quality_single"]
    assert items[0]["lexical_rank"] == 1
    assert items[0]["bm25_score"] <= items[1]["bm25_score"]


def test_lexical_search_should_prioritize_title_for_two_character_fallback(tmp_path: Path) -> None:
    """两字短词使用受控 LIKE 时，应先考虑文档标题而不是更新时间。"""

    database_path = _build_lexical_database(tmp_path)

    items = LexicalRetriever(database_path).search("阿胶", top_k=5)

    assert items[0]["chunk_id"] == "quality_exact"
    assert items[0]["lexical_match_type"] == "short_term_fallback"
    chunk_ids = [item["chunk_id"] for item in items]
    assert chunk_ids.index("body_match") < chunk_ids.index("quality_single")
