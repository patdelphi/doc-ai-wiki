"""程序说明：实现 Markdown 文档注册、分块与基础入库流程。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from src.chunking.splitter import split_text
from src.common.config import AppSettings
from src.common.errors import NotFoundAppError, ValidationAppError
from src.common.utils import read_text_file, sha256_of_text, utc_now_iso
from src.db.connection import create_connection
from src.db.repositories import DocumentRepository, IngestJobRepository
from src.db.transaction import transaction
from src.metadata.extractor import extract_basic_metadata


class IngestService:
    """文档入库服务。"""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.document_repository = DocumentRepository(settings.sqlite_db_path)
        self.job_repository = IngestJobRepository(settings.sqlite_db_path)

    def register_documents(self, documents: list[dict], rebuild_if_exists: bool = False) -> list[dict]:
        """注册文档，并完成最小可用入库流程。"""

        if not documents:
            raise ValidationAppError("documents 不能为空")

        jobs: list[dict] = []
        for document in documents:
            file_path = Path(document["file_path"])
            if not file_path.is_absolute():
                file_path = Path.cwd() / file_path
            if not file_path.exists():
                raise NotFoundAppError("文档文件不存在", details={"file_path": str(file_path)})

            content = read_text_file(file_path)
            metadata = extract_basic_metadata(file_path, content)
            source_hash = sha256_of_text(content)
            doc_id = metadata["doc_id"]
            edition = document.get("edition") or metadata.get("edition") or "default"
            doc_uid = f"{doc_id}_{edition}".replace(" ", "_")
            existing = self.document_repository.get_by_source_path(str(file_path))

            if existing and existing["source_hash"] == source_hash and not rebuild_if_exists:
                jobs.append(
                    {
                        "job_id": f"job_{uuid4().hex[:12]}",
                        "doc_uid": existing["doc_uid"],
                        "status": "skipped",
                    }
                )
                continue

            self._save_document_and_chunks(
                doc_uid=doc_uid,
                doc_id=doc_id,
                doc_title=document.get("doc_title") or metadata["doc_title"],
                edition=edition,
                file_path=file_path,
                source_hash=source_hash,
                content=content,
            )

            job_id = f"job_{uuid4().hex[:12]}"
            now = utc_now_iso()
            self.job_repository.insert_job(
                {
                    "job_id": job_id,
                    "doc_uid": doc_uid,
                    "stage": "ingest",
                    "status": "completed",
                    "started_at": now,
                    "finished_at": now,
                }
            )
            jobs.append({"job_id": job_id, "doc_uid": doc_uid, "status": "completed"})

        return jobs

    def list_status(self, *, doc_uid: str | None, status: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
        """查询文档入库状态。"""

        return self.document_repository.list_documents(
            doc_uid=doc_uid,
            status=status,
            page=page,
            page_size=page_size,
        )

    def rebuild_documents(self, doc_uids: list[str]) -> list[str]:
        """最小重建逻辑：当前版本仅接受请求并回传 accepted 列表。"""

        if not doc_uids:
            raise ValidationAppError("doc_uids 不能为空")
        return doc_uids

    def _save_document_and_chunks(
        self,
        *,
        doc_uid: str,
        doc_id: str,
        doc_title: str,
        edition: str,
        file_path: Path,
        source_hash: str,
        content: str,
    ) -> None:
        """保存文档主记录并构建最小 chunk 与 FTS 数据。"""

        now = utc_now_iso()
        chunks = split_text(content)
        with transaction(self.settings.sqlite_db_path) as connection:
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
                    doc_uid,
                    doc_id,
                    doc_title,
                    edition,
                    str(file_path),
                    source_hash,
                    "completed",
                    "indexed",
                    None,
                    now,
                    now,
                ),
            )
            connection.execute("DELETE FROM document_sections WHERE doc_uid = ?", (doc_uid,))
            connection.execute("DELETE FROM chunks WHERE doc_uid = ?", (doc_uid,))
            connection.execute("DELETE FROM chunk_fts WHERE doc_uid = ?", (doc_uid,))
            connection.execute(
                """
                INSERT INTO document_sections (
                    section_id, doc_uid, section_title, section_level, source_span,
                    content, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"sec_{uuid4().hex[:12]}",
                    doc_uid,
                    doc_title,
                    1,
                    "全文",
                    content,
                    now,
                    now,
                ),
            )
            for chunk_index, chunk_content in enumerate(chunks):
                chunk_id = f"chk_{uuid4().hex[:12]}"
                source_span = f"chunk-{chunk_index}"
                connection.execute(
                    """
                    INSERT INTO chunks (
                        chunk_id, doc_uid, section_id, chunk_index, content, source_span,
                        token_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        doc_uid,
                        None,
                        chunk_index,
                        chunk_content,
                        source_span,
                        len(chunk_content),
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO chunk_fts (chunk_id, doc_uid, content)
                    VALUES (?, ?, ?)
                    """,
                    (chunk_id, doc_uid, chunk_content),
                )
