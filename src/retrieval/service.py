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
                SELECT c.chunk_id, c.doc_uid, d.doc_title, c.source_span, c.content
                FROM chunk_fts f
                JOIN chunks c ON c.chunk_id = f.chunk_id
                JOIN documents d ON d.doc_uid = c.doc_uid
                WHERE chunk_fts MATCH ?
                LIMIT ?
                """,
                (query, top_k),
            ).fetchall()
            if not rows:
                rows = connection.execute(
                    """
                    SELECT c.chunk_id, c.doc_uid, d.doc_title, c.source_span, c.content
                    FROM chunks c
                    JOIN documents d ON d.doc_uid = c.doc_uid
                    WHERE content LIKE ?
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                    """,
                    (f"%{query}%", top_k),
                ).fetchall()
        return [self._with_source(dict(row), "fulltext") for row in rows]

    def vector_search(self, query: str, top_k: int = 5) -> list[dict]:
        """当前阶段先以简单相似替代向量检索占位。"""

        if self.vector_store is None:
            return []
        items = self.vector_store.query(query, top_k=top_k)
        return self._attach_document_titles(items, retrieval_source="vector")

    def hybrid_search(self, query: str, top_k: int = 5) -> list[dict]:
        """合并全文与向量检索结果，并按 chunk_id 去重。"""

        merged: dict[str, dict] = {}
        for item in self.fulltext_search(query, top_k=top_k):
            merged[item["chunk_id"]] = item
        for item in self.vector_search(query, top_k=top_k):
            merged.setdefault(item["chunk_id"], item)
        return list(merged.values())[:top_k]

    def _attach_document_titles(self, items: list[dict], *, retrieval_source: str) -> list[dict]:
        """为检索结果补全文档标题与来源字段。"""

        if not items:
            return []

        doc_uids = sorted({item["doc_uid"] for item in items if item.get("doc_uid")})
        titles: dict[str, str] = {}
        with create_connection(self.database_path) as connection:
            placeholders = ",".join("?" for _ in doc_uids)
            rows = connection.execute(
                f"""
                SELECT doc_uid, doc_title
                FROM documents
                WHERE doc_uid IN ({placeholders})
                """,
                tuple(doc_uids),
            ).fetchall()
            titles = {row["doc_uid"]: row["doc_title"] for row in rows}

        return [self._with_source({**item, "doc_title": titles.get(item.get("doc_uid"), "")}, retrieval_source) for item in items]

    @staticmethod
    def _with_source(item: dict, retrieval_source: str) -> dict:
        """补齐统一展示字段。"""

        return {
            **item,
            "doc_title": item.get("doc_title", ""),
            "retrieval_source": retrieval_source,
        }
