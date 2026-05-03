"""程序说明：提供最小可用的全文检索、向量检索与混合检索接口。"""

from __future__ import annotations

import json

from src.ai.rerank import BaseReranker, DisabledReranker
from src.db.connection import create_connection
from src.retrieval.vector_store import VectorStore


class RetrievalService:
    """检索服务。"""

    def __init__(self, database_path) -> None:
        self.database_path = database_path
        self.vector_store = None
        self.reranker: BaseReranker = DisabledReranker()

    def set_vector_store(self, vector_store: VectorStore) -> None:
        """注入向量存储实例。"""

        self.vector_store = vector_store

    def set_reranker(self, reranker: BaseReranker) -> None:
        """注入重排客户端。"""

        self.reranker = reranker

    def fulltext_search(
        self,
        query: str,
        top_k: int = 10,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> list[dict]:
        """执行全文检索，优先 FTS5，中文场景下对未命中结果使用 LIKE 兜底。"""

        doc_uid_filter = " AND c.doc_uid = ?" if doc_uid else ""
        knowledge_base_filter = " AND d.knowledge_base_id = ?" if knowledge_base_id else ""
        like_doc_uid_filter = " AND c.doc_uid = ?" if doc_uid else ""
        like_knowledge_base_filter = " AND d.knowledge_base_id = ?" if knowledge_base_id else ""
        params_list: list = [query]
        if doc_uid:
            params_list.append(doc_uid)
        if knowledge_base_id:
            params_list.append(knowledge_base_id)
        params_list.append(top_k)
        params = tuple(params_list)
        like_params_list: list = [f"%{query}%"]
        if doc_uid:
            like_params_list.append(doc_uid)
        if knowledge_base_id:
            like_params_list.append(knowledge_base_id)
        like_params_list.append(top_k)
        like_params = tuple(like_params_list)

        with create_connection(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT c.chunk_id, c.doc_uid, d.doc_title, d.author, d.source_name, d.tags_json, c.source_span, c.content
                FROM chunk_fts f
                JOIN chunks c ON c.chunk_id = f.chunk_id
                JOIN documents d ON d.doc_uid = c.doc_uid
                WHERE chunk_fts MATCH ?
                {doc_uid_filter}
                {knowledge_base_filter}
                LIMIT ?
                """,
                params,
            ).fetchall()
            if not rows:
                rows = connection.execute(
                    f"""
                    SELECT c.chunk_id, c.doc_uid, d.doc_title, d.author, d.source_name, d.tags_json, c.source_span, c.content
                    FROM chunks c
                    JOIN documents d ON d.doc_uid = c.doc_uid
                    WHERE content LIKE ?
                    {like_doc_uid_filter}
                    {like_knowledge_base_filter}
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                    """,
                    like_params,
                ).fetchall()
        return [self._with_source(self._normalize_metadata_fields(dict(row)), "fulltext") for row in rows]

    def vector_search(
        self,
        query: str,
        top_k: int = 10,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> list[dict]:
        """当前阶段先以简单相似替代向量检索占位。"""

        if self.vector_store is None:
            return []
        items = self.vector_store.query(query, top_k=top_k, doc_uid=doc_uid)
        return self._attach_document_metadata(
            items,
            retrieval_source="vector",
            knowledge_base_id=knowledge_base_id,
        )

    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
        *,
        fulltext_top_k: int | None = None,
        vector_top_k: int | None = None,
        use_rerank: bool | None = None,
    ) -> list[dict]:
        """合并全文与向量检索结果，并按 chunk_id 去重。"""

        merged: dict[str, dict] = {}
        for item in self.fulltext_search(
            query,
            top_k=fulltext_top_k or top_k,
            doc_uid=doc_uid,
            knowledge_base_id=knowledge_base_id,
        ):
            merged[item["chunk_id"]] = {
                **item,
                "matched_sources": ["fulltext"],
            }
        for item in self.vector_search(
            query,
            top_k=vector_top_k or top_k,
            doc_uid=doc_uid,
            knowledge_base_id=knowledge_base_id,
        ):
            existing = merged.get(item["chunk_id"])
            if existing:
                matched_sources = set(existing.get("matched_sources", []))
                matched_sources.add("vector")
                existing["matched_sources"] = sorted(matched_sources)
                existing["score"] = max(float(existing.get("score", 0.0)), float(item.get("score", 0.0)))
                if len(existing["matched_sources"]) > 1:
                    existing["retrieval_source"] = "hybrid"
                continue
            merged[item["chunk_id"]] = {
                **item,
                "matched_sources": ["vector"],
            }
        items = list(merged.values())
        should_rerank = self.reranker.enabled if use_rerank is None else use_rerank and self.reranker.enabled
        if should_rerank:
            return self.reranker.rerank(query=query, items=items, top_k=top_k)
        return items[:top_k]

    def get_chunk_detail(self, chunk_id: str) -> dict | None:
        """按 chunk_id 读取检索结果详情。"""

        if not chunk_id:
            return None

        with create_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT c.chunk_id, c.doc_uid, c.section_id, c.chunk_index, c.source_span, c.content,
                       d.doc_title, d.author, d.source_name, d.tags_json, s.section_title
                FROM chunks c
                JOIN documents d ON d.doc_uid = c.doc_uid
                LEFT JOIN document_sections s ON s.section_id = c.section_id
                WHERE c.chunk_id = ?
                """,
                (chunk_id,),
            ).fetchone()
        if not row:
            return None
        detail = self._normalize_metadata_fields(dict(row))
        detail["expanded_content"] = detail.get("content", "")
        return detail

    def expand_evidence_context(
        self,
        items: list[dict],
        *,
        neighbor_window: int = 0,
        include_section_context: bool = False,
        section_max_chars: int = 500,
    ) -> list[dict]:
        """按模板策略为证据补充邻接片段或章节级上下文。"""

        if not items:
            return []

        expanded_items: list[dict] = []
        with create_connection(self.database_path) as connection:
            for item in items:
                expanded_items.append(
                    self._build_expanded_item(
                        connection,
                        item,
                        neighbor_window=neighbor_window,
                        include_section_context=include_section_context,
                        section_max_chars=section_max_chars,
                    )
                )
        return expanded_items

    def _build_expanded_item(
        self,
        connection,
        item: dict,
        *,
        neighbor_window: int,
        include_section_context: bool,
        section_max_chars: int,
    ) -> dict:
        """为单条证据构建扩展上下文。"""

        chunk_id = item.get("chunk_id")
        if not chunk_id:
            return item

        chunk_row = connection.execute(
            """
            SELECT c.chunk_id, c.doc_uid, c.section_id, c.chunk_index, c.source_span, c.content,
                   d.doc_title, s.section_title, s.content AS section_content
            FROM chunks c
            JOIN documents d ON d.doc_uid = c.doc_uid
            LEFT JOIN document_sections s ON s.section_id = c.section_id
            WHERE c.chunk_id = ?
            """,
            (chunk_id,),
        ).fetchone()
        if not chunk_row:
            return item

        row = dict(chunk_row)
        expanded_content = row["content"]
        context_mode = "chunk"
        if neighbor_window > 0:
            if row.get("section_id"):
                neighbor_rows = connection.execute(
                    """
                    SELECT chunk_index, source_span, content
                    FROM chunks
                    WHERE section_id = ? AND chunk_index BETWEEN ? AND ?
                    ORDER BY chunk_index ASC
                    """,
                    (
                        row["section_id"],
                        max(int(row["chunk_index"]) - neighbor_window, 0),
                        int(row["chunk_index"]) + neighbor_window,
                    ),
                ).fetchall()
            else:
                neighbor_rows = connection.execute(
                    """
                    SELECT chunk_index, source_span, content
                    FROM chunks
                    WHERE doc_uid = ? AND chunk_index BETWEEN ? AND ?
                    ORDER BY chunk_index ASC
                    """,
                    (
                        row["doc_uid"],
                        max(int(row["chunk_index"]) - neighbor_window, 0),
                        int(row["chunk_index"]) + neighbor_window,
                    ),
                ).fetchall()
            expanded_content = "\n".join(
                f'[{neighbor["source_span"]}] {neighbor["content"]}'
                for neighbor in neighbor_rows
            )
            context_mode = "neighbor_chunks"

        if include_section_context and row.get("section_content"):
            section_excerpt = str(row["section_content"])[:section_max_chars]
            expanded_content = f"{expanded_content}\n\n[章节上下文] {section_excerpt}".strip()
            context_mode = "section_context"

        return self._with_source(
            {
                **item,
                "doc_title": row.get("doc_title", item.get("doc_title", "")),
                "section_title": row.get("section_title") or "",
                "expanded_content": expanded_content,
                "context_mode": context_mode,
            },
            item.get("retrieval_source", ""),
        )

    def _attach_document_metadata(
        self,
        items: list[dict],
        *,
        retrieval_source: str,
        knowledge_base_id: str | None = None,
    ) -> list[dict]:
        """为检索结果补全文档元数据与来源字段。"""

        if not items:
            return []

        doc_uids = sorted({item["doc_uid"] for item in items if item.get("doc_uid")})
        metadata_map: dict[str, dict] = {}
        with create_connection(self.database_path) as connection:
            placeholders = ",".join("?" for _ in doc_uids)
            knowledge_base_filter = " AND knowledge_base_id = ?" if knowledge_base_id else ""
            params: tuple = (
                (*doc_uids, knowledge_base_id) if knowledge_base_id else tuple(doc_uids)
            )
            rows = connection.execute(
                f"""
                SELECT doc_uid, knowledge_base_id, doc_title, author, source_name, tags_json
                FROM documents
                WHERE doc_uid IN ({placeholders})
                {knowledge_base_filter}
                """,
                params,
            ).fetchall()
            metadata_map = {
                row["doc_uid"]: self._normalize_metadata_fields(dict(row))
                for row in rows
            }

        filtered_items = [
            item
            for item in items
            if item.get("doc_uid") in metadata_map
        ]
        return [
            self._with_source(
                {
                    **item,
                    **metadata_map.get(item.get("doc_uid"), {}),
                },
                retrieval_source,
            )
            for item in filtered_items
        ]

    @staticmethod
    def _normalize_metadata_fields(item: dict) -> dict:
        """将 tags_json 等字段转换为前端友好的展示结构。"""

        raw_tags = item.pop("tags_json", None)
        if raw_tags:
            try:
                item["tags"] = json.loads(raw_tags)
            except json.JSONDecodeError:
                item["tags"] = []
        else:
            item["tags"] = item.get("tags", [])

        item["author"] = item.get("author") or ""
        item["source_name"] = item.get("source_name") or ""
        item["doc_title"] = item.get("doc_title") or ""
        return item

    @staticmethod
    def _with_source(item: dict, retrieval_source: str) -> dict:
        """补齐统一展示字段。"""

        return {
            **item,
            "doc_title": item.get("doc_title", ""),
            "author": item.get("author", ""),
            "source_name": item.get("source_name", ""),
            "tags": item.get("tags", []),
            "retrieval_source": retrieval_source,
        }
