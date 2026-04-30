"""程序说明：提供最小可用的全文检索、向量检索与混合检索接口。"""

from __future__ import annotations

from src.db.connection import create_connection
from src.retrieval.vector_store import VectorStore


class RetrievalService:
    """检索服务。"""

    def __init__(self, database_path) -> None:
        self.database_path = database_path
        self.vector_store = None

    def set_vector_store(self, vector_store: VectorStore) -> None:
        """注入向量存储实例。"""

        self.vector_store = vector_store

    def fulltext_search(self, query: str, top_k: int = 5) -> list[dict]:
        """执行全文检索，优先 FTS5，中文场景下对未命中结果使用 LIKE 兜底。"""

        with create_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT c.chunk_id, c.doc_uid, c.source_span, c.content
                FROM chunk_fts f
                JOIN chunks c ON c.chunk_id = f.chunk_id
                WHERE chunk_fts MATCH ?
                LIMIT ?
                """,
                (query, top_k),
            ).fetchall()
            if not rows:
                rows = connection.execute(
                    """
                    SELECT chunk_id, doc_uid, source_span, content
                    FROM chunks
                    WHERE content LIKE ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (f"%{query}%", top_k),
                ).fetchall()
        return [dict(row) for row in rows]

    def vector_search(self, query: str, top_k: int = 5) -> list[dict]:
        """当前阶段先以简单相似替代向量检索占位。"""

        if self.vector_store is None:
            return []
        return self.vector_store.query(query, top_k=top_k)

    def hybrid_search(self, query: str, top_k: int = 5) -> list[dict]:
        """合并全文与向量检索结果，并按 chunk_id 去重。"""

        merged: dict[str, dict] = {}
        for item in self.fulltext_search(query, top_k=top_k):
            merged[item["chunk_id"]] = item
        for item in self.vector_search(query, top_k=top_k):
            merged.setdefault(item["chunk_id"], item)
        return list(merged.values())[:top_k]
