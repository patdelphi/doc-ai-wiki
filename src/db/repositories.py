"""程序说明：提供文档、任务、质检与审核的基础数据访问接口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.common.utils import utc_now_iso
from src.db.connection import create_connection
from src.db.transaction import transaction


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
        return dict(row) if row else None

    def upsert_document(self, payload: dict[str, Any]) -> None:
        """插入或更新文档。"""

        now = utc_now_iso()
        with transaction(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    doc_uid, doc_id, doc_title, edition, source_path, source_hash,
                    ingest_status, index_status, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_uid) DO UPDATE SET
                    doc_id = excluded.doc_id,
                    doc_title = excluded.doc_title,
                    edition = excluded.edition,
                    source_path = excluded.source_path,
                    source_hash = excluded.source_hash,
                    ingest_status = excluded.ingest_status,
                    index_status = excluded.index_status,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["doc_uid"],
                    payload["doc_id"],
                    payload["doc_title"],
                    payload.get("edition"),
                    payload["source_path"],
                    payload["source_hash"],
                    payload["ingest_status"],
                    payload["index_status"],
                    payload.get("error_message"),
                    payload.get("created_at", now),
                    now,
                ),
            )

    def list_documents(
        self,
        *,
        doc_uid: str | None = None,
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

        return [dict(row) for row in rows], int(total_row["total"])


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
    ) -> None:
        """保存质检主记录与 claim 明细。"""

        with transaction(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO quality_checks (
                    check_id, input_text, overall_verdict, risk_level, summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quality_check["check_id"],
                    quality_check["input_text"],
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
                    claim_id, check_id, claim_text, verdict, confidence, evidence,
                    source_doc, source_span, review_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        claim["claim_id"],
                        claim["check_id"],
                        claim["claim_text"],
                        claim["verdict"],
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

        return {
            "check": dict(check_row),
            "claims": [dict(row) for row in claim_rows],
        }

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

    def list_reviews(self, page: int = 1, page_size: int = 20) -> tuple[list[dict[str, Any]], int]:
        """分页查询审核记录。"""

        offset = max(page - 1, 0) * page_size
        with create_connection(self.database_path) as connection:
            total_row = connection.execute(
                "SELECT COUNT(1) AS total FROM review_records",
            ).fetchone()
            rows = connection.execute(
                """
                SELECT *
                FROM review_records
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()

        return [dict(row) for row in rows], int(total_row["total"])
