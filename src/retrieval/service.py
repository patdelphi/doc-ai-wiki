"""程序说明：提供最小可用的全文检索、向量检索与混合检索接口。"""

from __future__ import annotations

import json
from typing import Any

from src.ai.rerank import BaseReranker, DisabledReranker
from src.db.connection import create_connection
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.lexical import LexicalRetriever
from src.retrieval.scope import normalize_knowledge_base_scope
from src.retrieval.vector_store import VectorStore


class RetrievalService:
    """检索服务。"""

    def __init__(self, database_path) -> None:
        self.database_path = database_path
        self.lexical = LexicalRetriever(database_path)
        self.vector_store: VectorStore | None = None
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
        knowledge_base_ids: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict]:
        """执行 Trigram/BM25 全文检索，并规范化返回元数据。"""

        search_kwargs: dict[str, Any] = {
            "top_k": top_k,
            "doc_uid": doc_uid,
            "knowledge_base_id": knowledge_base_id,
        }
        if knowledge_base_ids is not None:
            search_kwargs["knowledge_base_ids"] = knowledge_base_ids
        rows = self.lexical.search(query, **search_kwargs)
        return [self._with_source(self._normalize_metadata_fields(row), "fulltext") for row in rows]

    def vector_search(
        self,
        query: str,
        top_k: int = 10,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
        knowledge_base_ids: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict]:
        """执行支持单知识库或授权知识库集合过滤的向量检索。"""

        if self.vector_store is None:
            return []
        # 权限范围必须下推到向量存储层，不能在 Top-K 截断后再过滤。
        query_kwargs: dict[str, Any] = {
            "top_k": top_k,
            "doc_uid": doc_uid,
            "knowledge_base_id": knowledge_base_id,
        }
        if knowledge_base_ids is not None:
            query_kwargs["knowledge_base_ids"] = knowledge_base_ids
        items = self.vector_store.query(query, **query_kwargs)
        return self._attach_document_metadata(
            items,
            retrieval_source="vector",
            knowledge_base_id=knowledge_base_id,
            knowledge_base_ids=knowledge_base_ids,
        )

    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
        knowledge_base_ids: list[str] | tuple[str, ...] | None = None,
        *,
        fulltext_top_k: int | None = None,
        vector_top_k: int | None = None,
        use_rerank: bool | None = None,
    ) -> list[dict]:
        """使用 RRF 合并全文与向量结果，并在外部服务失败时显式降级。"""

        scope_kwargs: dict[str, Any] = {"knowledge_base_id": knowledge_base_id}
        if knowledge_base_ids is not None:
            scope_kwargs["knowledge_base_ids"] = knowledge_base_ids
        lexical_items = self.fulltext_search(
            query, top_k=fulltext_top_k or top_k, doc_uid=doc_uid, **scope_kwargs
        )
        degraded_reason = ""
        try:
            vector_items = self.vector_search(
                query,
                top_k=vector_top_k or top_k,
                doc_uid=doc_uid,
                **scope_kwargs,
            )
        except Exception:  # noqa: BLE001
            # 外部 Embedding 或向量存储异常时保留本地检索结果。
            vector_items = []
            degraded_reason = "vector_unavailable"

        items = reciprocal_rank_fusion(
            {
                "fulltext": lexical_items,
                "vector": vector_items,
            }
        )
        if degraded_reason:
            items = [{**item, "degraded_reason": degraded_reason} for item in items]
        should_rerank = self.reranker.enabled if use_rerank is None else use_rerank and self.reranker.enabled
        if should_rerank:
            try:
                return self.reranker.rerank(query=query, items=items, top_k=top_k)
            except Exception:  # noqa: BLE001
                return [{**item, "degraded_reason": "rerank_unavailable"} for item in items[:top_k]]
        return items[:top_k]

    def search_queries(
        self,
        query_specs: list[dict],
        *,
        top_k: int,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
        knowledge_base_ids: list[str] | tuple[str, ...] | None = None,
        fulltext_top_k: int | None = None,
        vector_top_k: int | None = None,
        use_rerank: bool = True,
    ) -> list[dict]:
        """合并最多三类查询的候选，并只执行一次批量 Rerank。"""

        limit = max(int(top_k), 1)
        merged: dict[str, dict] = {}
        query_scores: dict[str, float] = {}
        normalized_specs = [
            {
                "label": str(item.get("label") or "").strip(),
                "query": str(item.get("query") or "").strip(),
            }
            for item in query_specs[:3]
            if str(item.get("label") or "").strip() and str(item.get("query") or "").strip()
        ]
        for query_spec in normalized_specs:
            items = self.hybrid_search(
                query_spec["query"],
                top_k=limit,
                doc_uid=doc_uid,
                knowledge_base_id=knowledge_base_id,
                knowledge_base_ids=knowledge_base_ids,
                fulltext_top_k=fulltext_top_k,
                vector_top_k=vector_top_k,
                use_rerank=False,
            )
            for rank, item in enumerate(items, start=1):
                chunk_id = str(item.get("chunk_id") or "").strip()
                if not chunk_id:
                    continue
                query_scores[chunk_id] = query_scores.get(chunk_id, 0.0) + 1.0 / (60 + rank)
                if chunk_id not in merged:
                    merged[chunk_id] = {
                        **item,
                        "matched_queries": [query_spec["label"]],
                    }
                    continue
                existing = merged[chunk_id]
                existing_queries = list(existing.get("matched_queries") or [])
                if query_spec["label"] not in existing_queries:
                    existing_queries.append(query_spec["label"])
                existing["matched_queries"] = existing_queries
                existing_sources = list(existing.get("matched_sources") or [])
                for source in item.get("matched_sources") or []:
                    if source not in existing_sources:
                        existing_sources.append(source)
                existing["matched_sources"] = existing_sources

        candidates = sorted(
            (
                {**item, "query_rrf_score": query_scores[chunk_id]}
                for chunk_id, item in merged.items()
            ),
            key=lambda item: (
                -float(item.get("query_rrf_score") or 0.0),
                str(item.get("chunk_id") or ""),
            ),
        )
        should_rerank = bool(use_rerank and self.reranker.enabled and candidates)
        if should_rerank:
            combined_query = "；".join(item["query"] for item in normalized_specs)
            try:
                return self.reranker.rerank(query=combined_query, items=candidates, top_k=limit)
            except Exception:  # noqa: BLE001
                return [{**item, "degraded_reason": "rerank_unavailable"} for item in candidates[:limit]]
        return candidates[:limit]

    def get_chunk_detail(self, chunk_id: str) -> dict | None:
        """按 chunk_id 读取检索结果详情。"""

        if not chunk_id:
            return None

        with create_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT c.chunk_id, c.doc_uid, c.section_id, c.chunk_index, c.source_span,
                       c.heading_path, c.source_start_line, c.source_end_line, c.page_no,
                       c.chunk_type, c.content_hash, c.source_anchor, c.content,
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
            SELECT c.chunk_id, c.doc_uid, c.section_id, c.chunk_index, c.source_span,
                   c.heading_path, c.source_start_line, c.source_end_line, c.page_no,
                   c.chunk_type, c.content_hash, c.source_anchor, c.content,
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
        knowledge_base_ids: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict]:
        """以 SQLite 为准补全向量结果的文档与 chunk 追溯元数据。"""

        knowledge_base_scope = normalize_knowledge_base_scope(knowledge_base_id, knowledge_base_ids)
        if not items or knowledge_base_scope == ():
            return []

        chunk_ids = sorted({str(item["chunk_id"]) for item in items if item.get("chunk_id")})
        if not chunk_ids:
            return []
        metadata_map: dict[str, dict] = {}
        with create_connection(self.database_path) as connection:
            placeholders = ",".join("?" for _ in chunk_ids)
            knowledge_base_filter = ""
            params: tuple[object, ...] = tuple(chunk_ids)
            if knowledge_base_scope:
                kb_placeholders = ",".join("?" for _ in knowledge_base_scope)
                knowledge_base_filter = f" AND d.knowledge_base_id IN ({kb_placeholders})"
                params = (*chunk_ids, *knowledge_base_scope)
            rows = connection.execute(
                f"""
                SELECT c.chunk_id, c.doc_uid, c.source_span, c.heading_path,
                       c.source_start_line, c.source_end_line, c.page_no, c.chunk_type,
                       c.content_hash, c.source_anchor, c.content,
                       d.knowledge_base_id, d.doc_title, d.author, d.source_name, d.tags_json
                FROM chunks c
                JOIN documents d ON d.doc_uid = c.doc_uid
                WHERE c.chunk_id IN ({placeholders})
                {knowledge_base_filter}
                """,
                params,
            ).fetchall()
            metadata_map = {
                row["chunk_id"]: self._normalize_metadata_fields(dict(row))
                for row in rows
            }

        filtered_items = [
            item
            for item in items
            if item.get("chunk_id") in metadata_map
        ]
        return [
            self._with_source(
                {
                    **item,
                    # SQLite 是元数据事实源，可覆盖向量索引中的历史追溯字段。
                    **metadata_map.get(str(item.get("chunk_id") or ""), {}),
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
