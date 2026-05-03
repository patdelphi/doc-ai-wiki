"""程序说明：提供文档、任务、质检与审核的基础数据访问接口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.common.errors import NotFoundAppError
from src.common.utils import utc_now_iso
from src.db.connection import create_connection
from src.db.transaction import transaction


class KnowledgeBaseRepository:
    """知识库配置访问对象。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def list_knowledge_bases(self) -> list[dict[str, Any]]:
        """按默认优先、名称排序列出知识库。"""

        with create_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT knowledge_base_id, knowledge_base_name, description, status, is_default, created_at, updated_at
                FROM knowledge_bases
                ORDER BY is_default DESC, updated_at DESC, knowledge_base_name ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_by_id(self, knowledge_base_id: str) -> dict[str, Any] | None:
        """按知识库标识读取配置。"""

        with create_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT knowledge_base_id, knowledge_base_name, description, status, is_default, created_at, updated_at
                FROM knowledge_bases
                WHERE knowledge_base_id = ?
                """,
                (knowledge_base_id,),
            ).fetchone()
        return dict(row) if row else None

    def save_knowledge_base(self, payload: dict[str, Any]) -> dict[str, Any]:
        """新增或更新知识库。"""

        now = utc_now_iso()
        with transaction(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO knowledge_bases (
                    knowledge_base_id, knowledge_base_name, description, status, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(knowledge_base_id) DO UPDATE SET
                    knowledge_base_name = excluded.knowledge_base_name,
                    description = excluded.description,
                    status = excluded.status,
                    is_default = excluded.is_default,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["knowledge_base_id"],
                    payload["knowledge_base_name"],
                    payload.get("description"),
                    payload.get("status", "active"),
                    1 if payload.get("is_default") else 0,
                    payload.get("created_at") or now,
                    now,
                ),
            )
            if payload.get("is_default"):
                connection.execute(
                    """
                    UPDATE knowledge_bases
                    SET is_default = CASE WHEN knowledge_base_id = ? THEN 1 ELSE 0 END,
                        updated_at = ?
                    """,
                    (payload["knowledge_base_id"], now),
                )
        return self.get_by_id(payload["knowledge_base_id"]) or {}

    def count_documents(self, knowledge_base_id: str) -> int:
        """统计指定知识库下的文档数量。"""

        with create_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(1) AS total
                FROM documents
                WHERE knowledge_base_id = ?
                """,
                (knowledge_base_id,),
            ).fetchone()
        return int(row["total"] or 0) if row else 0

    def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        """删除知识库。"""

        with transaction(self.database_path) as connection:
            connection.execute(
                """
                DELETE FROM knowledge_bases
                WHERE knowledge_base_id = ?
                """,
                (knowledge_base_id,),
            )


class DocumentRepository:
    """文档主表访问对象。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def get_by_source_path(self, source_path: str) -> dict[str, Any] | None:
        """按源文件路径查询文档。"""

        with create_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM documents
                WHERE source_path = ?
                """,
                (source_path,),
            ).fetchone()
        return self._normalize_document_row(row)

    def get_by_doc_uid(self, doc_uid: str) -> dict[str, Any] | None:
        """按文档唯一标识查询文档。"""

        with create_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM documents
                WHERE doc_uid = ?
                """,
                (doc_uid,),
            ).fetchone()
        return self._normalize_document_row(row)

    def upsert_document(self, payload: dict[str, Any]) -> None:
        """插入或更新文档。"""

        now = utc_now_iso()
        with transaction(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    doc_uid, knowledge_base_id, doc_id, doc_title, edition, author, source_name, tags_json, source_path, source_hash,
                    ingest_status, index_status, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_uid) DO UPDATE SET
                    knowledge_base_id = excluded.knowledge_base_id,
                    doc_id = excluded.doc_id,
                    doc_title = excluded.doc_title,
                    edition = excluded.edition,
                    author = excluded.author,
                    source_name = excluded.source_name,
                    tags_json = excluded.tags_json,
                    source_path = excluded.source_path,
                    source_hash = excluded.source_hash,
                    ingest_status = excluded.ingest_status,
                    index_status = excluded.index_status,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["doc_uid"],
                    payload.get("knowledge_base_id", "default"),
                    payload["doc_id"],
                    payload["doc_title"],
                    payload.get("edition"),
                    payload.get("author"),
                    payload.get("source_name"),
                    json.dumps(payload.get("tags", []), ensure_ascii=False),
                    payload["source_path"],
                    payload["source_hash"],
                    payload["ingest_status"],
                    payload["index_status"],
                    payload.get("error_message"),
                    payload.get("created_at", now),
                    now,
                ),
            )

    def update_index_status(
        self,
        *,
        doc_uid: str,
        index_status: str,
        error_message: str | None = None,
    ) -> None:
        """更新文档索引状态。"""

        with transaction(self.database_path) as connection:
            connection.execute(
                """
                UPDATE documents
                SET index_status = ?, error_message = ?, updated_at = ?
                WHERE doc_uid = ?
                """,
                (index_status, error_message, utc_now_iso(), doc_uid),
            )

    def update_ingest_state(
        self,
        *,
        doc_uid: str,
        ingest_status: str,
        index_status: str,
        error_message: str | None = None,
    ) -> None:
        """统一更新文档入库与索引状态。"""

        with transaction(self.database_path) as connection:
            connection.execute(
                """
                UPDATE documents
                SET ingest_status = ?, index_status = ?, error_message = ?, updated_at = ?
                WHERE doc_uid = ?
                """,
                (ingest_status, index_status, error_message, utc_now_iso(), doc_uid),
            )

    def list_documents(
        self,
        *,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """分页查询文档状态。"""

        where_clauses: list[str] = []
        params: list[Any] = []

        if doc_uid:
            where_clauses.append("doc_uid = ?")
            params.append(doc_uid)
        if knowledge_base_id:
            where_clauses.append("knowledge_base_id = ?")
            params.append(knowledge_base_id)
        if status:
            where_clauses.append("ingest_status = ?")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        offset = max(page - 1, 0) * page_size

        with create_connection(self.database_path) as connection:
            total_row = connection.execute(
                f"SELECT COUNT(1) AS total FROM documents {where_sql}",
                tuple(params),
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT *
                FROM documents
                {where_sql}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()

        return [self._normalize_document_row(row) for row in rows], int(total_row["total"])

    def list_chunks_by_doc_uid(self, doc_uid: str) -> list[dict[str, Any]]:
        """读取指定文档的全部 chunk，用于向量重建。"""

        with create_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, doc_uid, section_id, source_span, content
                FROM chunks
                WHERE doc_uid = ?
                ORDER BY chunk_index ASC
                """,
                (doc_uid,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_document_quality_snapshot(self, doc_uid: str, *, sample_limit: int = 3) -> dict[str, Any] | None:
        """读取单篇文档的章节、分块与全文索引质检快照。"""

        document = self.get_by_doc_uid(doc_uid)
        if not document:
            return None

        with create_connection(self.database_path) as connection:
            section_rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT section_id, section_title, section_level, source_span,
                           LENGTH(content) AS content_length,
                           SUBSTR(content, 1, 160) AS content_preview
                    FROM document_sections
                    WHERE doc_uid = ?
                    ORDER BY rowid ASC
                    """,
                    (doc_uid,),
                ).fetchall()
            ]
            chunk_rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT c.chunk_id, c.chunk_index, c.source_span, c.token_count,
                           SUBSTR(c.content, 1, 160) AS content_preview,
                           s.section_title
                    FROM chunks c
                    LEFT JOIN document_sections s ON s.section_id = c.section_id
                    WHERE c.doc_uid = ?
                    ORDER BY c.chunk_index ASC
                    """,
                    (doc_uid,),
                ).fetchall()
            ]
            fts_row = connection.execute(
                """
                SELECT COUNT(1) AS fts_chunk_count
                FROM chunk_fts
                WHERE doc_uid = ?
                """,
                (doc_uid,),
            ).fetchone()

        section_count = len(section_rows)
        chunk_count = len(chunk_rows)
        total_chunk_chars = sum(int(row.get("token_count") or 0) for row in chunk_rows)
        avg_chunk_chars = round(total_chunk_chars / chunk_count, 1) if chunk_count else 0.0
        avg_chunks_per_section = round(chunk_count / section_count, 1) if section_count else 0.0
        return {
            "document": document,
            "metrics": {
                "section_count": section_count,
                "chunk_count": chunk_count,
                "fts_chunk_count": int(fts_row["fts_chunk_count"] or 0) if fts_row else 0,
                "avg_chunk_chars": avg_chunk_chars,
                "min_chunk_chars": min((int(row.get("token_count") or 0) for row in chunk_rows), default=0),
                "max_chunk_chars": max((int(row.get("token_count") or 0) for row in chunk_rows), default=0),
                "total_chunk_chars": total_chunk_chars,
                "avg_chunks_per_section": avg_chunks_per_section,
            },
            "first_section_title": section_rows[0]["section_title"] if section_rows else "",
            "last_section_title": section_rows[-1]["section_title"] if section_rows else "",
            "section_samples": self._sample_rows(section_rows, sample_limit),
            "chunk_samples": self._sample_rows(chunk_rows, sample_limit),
        }

    def get_database_summary(self, *, knowledge_base_id: str | None = None) -> dict[str, int]:
        """汇总数据库中的文档、分块、质检与审核统计。"""

        with create_connection(self.database_path) as connection:
            if knowledge_base_id:
                row = connection.execute(
                    """
                    SELECT
                        (SELECT COUNT(1) FROM documents WHERE knowledge_base_id = ?) AS document_count,
                        (SELECT COUNT(1) FROM documents WHERE knowledge_base_id = ? AND ingest_status = 'completed') AS completed_document_count,
                        (SELECT COUNT(1) FROM documents WHERE knowledge_base_id = ? AND index_status = 'indexed') AS indexed_document_count,
                        (SELECT COUNT(1) FROM documents WHERE knowledge_base_id = ? AND index_status IN ('pending', 'rebuilding')) AS rebuild_pending_document_count,
                        (SELECT COUNT(1) FROM documents WHERE knowledge_base_id = ? AND (index_status = 'partial_failed' OR ingest_status = 'failed')) AS failed_document_count,
                        (SELECT COUNT(1) FROM document_sections WHERE doc_uid IN (SELECT doc_uid FROM documents WHERE knowledge_base_id = ?)) AS section_count,
                        (SELECT COUNT(1) FROM chunks WHERE doc_uid IN (SELECT doc_uid FROM documents WHERE knowledge_base_id = ?)) AS chunk_count,
                        (SELECT COUNT(1) FROM quality_checks WHERE knowledge_base_id = ?) AS quality_check_count,
                        (SELECT COUNT(1) FROM quality_claims WHERE check_id IN (SELECT check_id FROM quality_checks WHERE knowledge_base_id = ?)) AS claim_count,
                        (SELECT COUNT(1) FROM review_records WHERE claim_id IN (
                            SELECT qc.claim_id
                            FROM quality_claims qc
                            JOIN quality_checks q ON q.check_id = qc.check_id
                            WHERE q.knowledge_base_id = ?
                        )) AS review_count
                    """,
                    (knowledge_base_id,) * 10,
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT
                        (SELECT COUNT(1) FROM documents) AS document_count,
                        (SELECT COUNT(1) FROM documents WHERE ingest_status = 'completed') AS completed_document_count,
                        (SELECT COUNT(1) FROM documents WHERE index_status = 'indexed') AS indexed_document_count,
                        (SELECT COUNT(1) FROM documents WHERE index_status IN ('pending', 'rebuilding')) AS rebuild_pending_document_count,
                        (SELECT COUNT(1) FROM documents WHERE index_status = 'partial_failed' OR ingest_status = 'failed') AS failed_document_count,
                        (SELECT COUNT(1) FROM document_sections) AS section_count,
                        (SELECT COUNT(1) FROM chunks) AS chunk_count,
                        (SELECT COUNT(1) FROM quality_checks) AS quality_check_count,
                        (SELECT COUNT(1) FROM quality_claims) AS claim_count,
                        (SELECT COUNT(1) FROM review_records) AS review_count
                    """
                ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}

    @staticmethod
    def _sample_rows(rows: list[dict[str, Any]], sample_limit: int) -> list[dict[str, Any]]:
        """按首中尾均匀抽样，避免长文档只看前几条。"""

        if sample_limit <= 0 or not rows:
            return []
        if len(rows) <= sample_limit:
            return rows

        last_index = len(rows) - 1
        sample_indexes: list[int] = []
        for sample_index in range(sample_limit):
            computed_index = round(sample_index * last_index / max(sample_limit - 1, 1))
            if computed_index not in sample_indexes:
                sample_indexes.append(computed_index)
        return [rows[index] for index in sample_indexes]

    @staticmethod
    def _normalize_document_row(row: Any) -> dict[str, Any] | None:
        """将 documents 表记录转换为接口友好的结构。"""

        if not row:
            return None
        item = dict(row)
        raw_tags = item.get("tags_json")
        if raw_tags:
            try:
                item["tags"] = json.loads(raw_tags)
            except json.JSONDecodeError:
                item["tags"] = []
        else:
            item["tags"] = []
        item.pop("tags_json", None)
        return item


class IngestJobRepository:
    """入库任务表访问对象。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def insert_job(self, payload: dict[str, Any]) -> None:
        """写入任务记录。"""

        with transaction(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO ingest_jobs (
                    job_id, doc_uid, stage, status, error_message, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["job_id"],
                    payload["doc_uid"],
                    payload["stage"],
                    payload["status"],
                    payload.get("error_message"),
                    payload["started_at"],
                    payload.get("finished_at"),
                ),
            )


class QualityRepository:
    """质检与审核基础访问对象。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def create_quality_result(
        self,
        *,
        quality_check: dict[str, Any],
        claims: list[dict[str, Any]],
        rule_hits: list[dict[str, Any]] | None = None,
    ) -> None:
        """保存质检主记录与 claim 明细。"""

        with transaction(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO quality_checks (
                    check_id, knowledge_base_id, input_text, template_id, template_name, overall_verdict, risk_level, summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quality_check["check_id"],
                    quality_check.get("knowledge_base_id", "default"),
                    quality_check["input_text"],
                    quality_check.get("template_id"),
                    quality_check.get("template_name"),
                    quality_check["overall_verdict"],
                    quality_check["risk_level"],
                    quality_check["summary"],
                    quality_check["created_at"],
                    quality_check["updated_at"],
                ),
            )
            connection.executemany(
                """
                INSERT INTO quality_claims (
                    claim_id, check_id, claim_text, verdict, risk_level, confidence, evidence,
                    source_doc, source_span, review_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        claim["claim_id"],
                        claim["check_id"],
                        claim["claim_text"],
                        claim["verdict"],
                        claim.get("risk_level", "medium"),
                        claim["confidence"],
                        claim["evidence"],
                        claim.get("source_doc"),
                        claim.get("source_span"),
                        claim["review_status"],
                        claim["created_at"],
                        claim["updated_at"],
                    )
                    for claim in claims
                ],
            )
            if rule_hits:
                connection.executemany(
                    """
                    INSERT INTO rule_hits (
                        rule_hit_id, check_id, claim_id, rule_code, rule_name,
                        hit_level, hit_message, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            hit["rule_hit_id"],
                            hit["check_id"],
                            hit.get("claim_id"),
                            hit["rule_code"],
                            hit["rule_name"],
                            hit["hit_level"],
                            hit["hit_message"],
                            hit["created_at"],
                        )
                        for hit in rule_hits
                    ],
                )

    def get_quality_result(self, check_id: str) -> dict[str, Any] | None:
        """读取质检结果。"""

        with create_connection(self.database_path) as connection:
            check_row = connection.execute(
                "SELECT * FROM quality_checks WHERE check_id = ?",
                (check_id,),
            ).fetchone()
            if not check_row:
                return None
            claim_rows = connection.execute(
                """
                SELECT *
                FROM quality_claims
                WHERE check_id = ?
                ORDER BY created_at ASC
                """,
                (check_id,),
            ).fetchall()
            rule_hit_rows = connection.execute(
                """
                SELECT *
                FROM rule_hits
                WHERE check_id = ?
                ORDER BY created_at ASC
                """,
                (check_id,),
            ).fetchall()

        return {
            "check": dict(check_row),
            "claims": [dict(row) for row in claim_rows],
            "rule_hits": [dict(row) for row in rule_hit_rows],
        }

    def list_recent_quality_results(
        self,
        limit: int = 10,
        *,
        knowledge_base_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """读取最近质检结果及其 claim 列表。"""

        where_sql = "WHERE knowledge_base_id = ?" if knowledge_base_id else ""
        params: tuple[Any, ...] = (knowledge_base_id, limit) if knowledge_base_id else (limit,)
        with create_connection(self.database_path) as connection:
            check_rows = connection.execute(
                f"""
                SELECT *
                FROM quality_checks
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

            results: list[dict[str, Any]] = []
            for check_row in check_rows:
                claim_rows = connection.execute(
                    """
                    SELECT *
                    FROM quality_claims
                    WHERE check_id = ?
                    ORDER BY created_at ASC
                    """,
                    (check_row["check_id"],),
                ).fetchall()
                results.append(
                    {
                        "check_id": check_row["check_id"],
                        "knowledge_base_id": check_row["knowledge_base_id"],
                        "input_text": check_row["input_text"],
                        "template_id": check_row["template_id"],
                        "template_name": check_row["template_name"],
                        "overall_verdict": check_row["overall_verdict"],
                        "risk_level": check_row["risk_level"],
                        "created_at": check_row["created_at"],
                        "claims": [dict(row) for row in claim_rows],
                    }
                )

        return results

    def list_review_candidates(
        self,
        limit: int = 50,
        *,
        knowledge_base_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """读取可进入人工审核的 Claim 列表，按待处理优先、时间倒序排列。"""

        where_sql = "WHERE q.knowledge_base_id = ?" if knowledge_base_id else ""
        params: tuple[Any, ...] = (knowledge_base_id, limit) if knowledge_base_id else (limit,)
        with create_connection(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    qc.claim_id,
                    qc.check_id,
                    qc.claim_text,
                    qc.verdict,
                    qc.risk_level,
                    qc.confidence,
                    qc.evidence,
                    qc.source_doc,
                    qc.source_span,
                    qc.review_status,
                    qc.created_at,
                    qc.updated_at,
                    q.knowledge_base_id,
                    q.template_name,
                    q.input_text,
                    q.created_at AS check_created_at
                FROM quality_claims qc
                JOIN quality_checks q ON q.check_id = qc.check_id
                {where_sql}
                ORDER BY
                    CASE WHEN COALESCE(qc.review_status, 'pending') = 'pending' THEN 0 ELSE 1 END ASC,
                    COALESCE(qc.updated_at, qc.created_at, q.created_at) DESC,
                    q.created_at DESC,
                    qc.created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_review_record(self, payload: dict[str, Any]) -> None:
        """保存审核记录并同步 claim 审核状态。"""

        with transaction(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO review_records (
                    review_id, claim_id, review_action, reviewed_verdict, review_note, reviewer, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["review_id"],
                    payload["claim_id"],
                    payload["review_action"],
                    payload.get("reviewed_verdict"),
                    payload.get("review_note"),
                    payload["reviewer"],
                    payload["created_at"],
                ),
            )
            connection.execute(
                """
                UPDATE quality_claims
                SET review_status = ?, updated_at = ?
                WHERE claim_id = ?
                """,
                (
                    payload["review_action"],
                    payload["created_at"],
                    payload["claim_id"],
                ),
            )

    def delete_review_record(self, review_id: str) -> dict[str, Any]:
        """删除指定审核记录，并回退对应 claim 的审核状态。"""

        with create_connection(self.database_path) as connection:
            review_row = connection.execute(
                """
                SELECT review_id, claim_id, review_action, reviewed_verdict, review_note, reviewer, created_at
                FROM review_records
                WHERE review_id = ?
                """,
                (review_id,),
            ).fetchone()
        if not review_row:
            raise NotFoundAppError("审核记录不存在", details={"review_id": review_id})

        deleted_record = dict(review_row)
        claim_id = str(review_row["claim_id"])
        with transaction(self.database_path) as connection:
            connection.execute(
                """
                DELETE FROM review_records
                WHERE review_id = ?
                """,
                (review_id,),
            )
            latest_review_row = connection.execute(
                """
                SELECT review_action, created_at
                FROM review_records
                WHERE claim_id = ?
                ORDER BY created_at DESC, review_id DESC
                LIMIT 1
                """,
                (claim_id,),
            ).fetchone()
            restored_review_status = str(latest_review_row["review_action"]) if latest_review_row else "pending"
            restored_updated_at = str(latest_review_row["created_at"]) if latest_review_row else utc_now_iso()
            connection.execute(
                """
                UPDATE quality_claims
                SET review_status = ?, updated_at = ?
                WHERE claim_id = ?
                """,
                (
                    restored_review_status,
                    restored_updated_at,
                    claim_id,
                ),
            )

        deleted_record["restored_review_status"] = restored_review_status
        return deleted_record

    def list_reviews(
        self,
        page: int = 1,
        page_size: int = 20,
        *,
        knowledge_base_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """分页查询审核记录。"""

        offset = max(page - 1, 0) * page_size
        where_sql = "WHERE q.knowledge_base_id = ?" if knowledge_base_id else ""
        count_params: tuple[Any, ...] = (knowledge_base_id,) if knowledge_base_id else ()
        list_params: tuple[Any, ...] = (
            (knowledge_base_id, page_size, offset) if knowledge_base_id else (page_size, offset)
        )
        with create_connection(self.database_path) as connection:
            total_row = connection.execute(
                f"""
                SELECT COUNT(1) AS total
                FROM review_records rr
                JOIN quality_claims qc ON qc.claim_id = rr.claim_id
                JOIN quality_checks q ON q.check_id = qc.check_id
                {where_sql}
                """,
                count_params,
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT
                    rr.*,
                    qc.check_id AS check_id,
                    qc.claim_text AS claim_text,
                    qc.review_status AS review_status,
                    q.knowledge_base_id AS knowledge_base_id,
                    q.template_name AS template_name
                FROM review_records rr
                JOIN quality_claims qc ON qc.claim_id = rr.claim_id
                JOIN quality_checks q ON q.check_id = qc.check_id
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                list_params,
            ).fetchall()

        return [dict(row) for row in rows], int(total_row["total"])
