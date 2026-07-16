"""程序说明：提供中文词法检索的独立实现。"""

from __future__ import annotations

import re
import sqlite3

from src.db.connection import create_connection
from src.retrieval.query_normalizer import expand_query_texts


class LexicalRetriever:
    """封装 SQLite FTS5 与受控短词检索。"""

    def __init__(self, database_path) -> None:
        self.database_path = database_path

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> list[dict]:
        """执行中文词法检索。"""

        limit = max(int(top_k), 1)
        collected: list[dict] = []
        seen_chunk_ids: set[str] = set()
        with create_connection(self.database_path) as connection:
            for query_text in expand_query_texts(query, limit=6):
                compact_query = re.sub(r"\s+", "", query_text)
                rows: list[sqlite3.Row] = []
                match_type = "fts_bm25"
                if len(compact_query) >= 3:
                    rows = self._search_fts(
                        connection,
                        query_text,
                        top_k=limit,
                        doc_uid=doc_uid,
                        knowledge_base_id=knowledge_base_id,
                    )
                if not rows and len(compact_query) == 2:
                    rows = self._search_short_term(
                        connection,
                        compact_query,
                        top_k=limit,
                        doc_uid=doc_uid,
                        knowledge_base_id=knowledge_base_id,
                    )
                    match_type = "short_term_fallback"

                for row in rows:
                    item = dict(row)
                    chunk_id = str(item.get("chunk_id") or "")
                    if not chunk_id or chunk_id in seen_chunk_ids:
                        continue
                    item["lexical_match_type"] = match_type
                    collected.append(item)
                    seen_chunk_ids.add(chunk_id)
                    if len(collected) >= limit:
                        break
                if len(collected) >= limit:
                    break

        for rank, item in enumerate(collected, start=1):
            item["lexical_rank"] = rank
            item["retrieval_source"] = "fulltext"
        return collected

    @staticmethod
    def _search_fts(
        connection: sqlite3.Connection,
        query: str,
        *,
        top_k: int,
        doc_uid: str | None,
        knowledge_base_id: str | None,
    ) -> list[sqlite3.Row]:
        """使用 Trigram FTS5 和 BM25 执行相关性排序。"""

        doc_filter = " AND c.doc_uid = ?" if doc_uid else ""
        kb_filter = " AND d.knowledge_base_id = ?" if knowledge_base_id else ""
        params: list[object] = [query]
        if doc_uid:
            params.append(doc_uid)
        if knowledge_base_id:
            params.append(knowledge_base_id)
        params.append(top_k)
        try:
            return connection.execute(
                f"""
                SELECT c.chunk_id, c.doc_uid, d.doc_title, d.author, d.source_name, d.tags_json,
                       c.source_span, c.heading_path, c.source_start_line, c.source_end_line,
                       c.page_no, c.chunk_type, c.content_hash, c.source_anchor, c.content,
                       bm25(chunk_fts) AS bm25_score
                FROM chunk_fts
                JOIN chunks c ON c.chunk_id = chunk_fts.chunk_id
                JOIN documents d ON d.doc_uid = c.doc_uid
                WHERE chunk_fts MATCH ?
                {doc_filter}
                {kb_filter}
                ORDER BY bm25_score ASC, c.chunk_index ASC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    @staticmethod
    def _search_short_term(
        connection: sqlite3.Connection,
        query: str,
        *,
        top_k: int,
        doc_uid: str | None,
        knowledge_base_id: str | None,
    ) -> list[sqlite3.Row]:
        """仅对两字短词执行受控 LIKE，并使用稳定相关性排序。"""

        doc_filter = " AND c.doc_uid = ?" if doc_uid else ""
        kb_filter = " AND d.knowledge_base_id = ?" if knowledge_base_id else ""
        like_query = f"%{query}%"
        params: list[object] = [like_query, query, query, like_query, like_query]
        if doc_uid:
            params.append(doc_uid)
        if knowledge_base_id:
            params.append(knowledge_base_id)
        params.append(top_k)
        return connection.execute(
            f"""
            SELECT c.chunk_id, c.doc_uid, d.doc_title, d.author, d.source_name, d.tags_json,
                   c.source_span, c.heading_path, c.source_start_line, c.source_end_line,
                   c.page_no, c.chunk_type, c.content_hash, c.source_anchor, c.content,
                   0.0 AS bm25_score,
                   CASE WHEN d.doc_title LIKE ? THEN 1 ELSE 0 END AS title_match,
                   ((length(c.content) - length(replace(c.content, ?, ''))) / length(?)) AS term_frequency
            FROM chunks c
            JOIN documents d ON d.doc_uid = c.doc_uid
            WHERE (c.content LIKE ? OR d.doc_title LIKE ?)
            {doc_filter}
            {kb_filter}
            ORDER BY title_match DESC, term_frequency DESC, c.chunk_index ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
