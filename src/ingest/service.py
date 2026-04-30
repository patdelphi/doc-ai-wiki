"""程序说明：实现 Markdown 文档注册、分块与基础入库流程。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from src.chunking.splitter import split_text
from src.common.config import AppSettings
from src.common.errors import DatabaseAppError, NotFoundAppError, ValidationAppError
from src.common.utils import read_text_file, sha256_of_text, utc_now_iso
from src.db.repositories import DocumentRepository, IngestJobRepository
from src.db.transaction import transaction
from src.metadata.extractor import extract_basic_metadata
from src.metadata.sections import parse_markdown_sections
from src.retrieval.vector_store import VectorStore


class IngestService:
    """文档入库服务。"""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.document_repository = DocumentRepository(settings.sqlite_db_path)
        self.job_repository = IngestJobRepository(settings.sqlite_db_path)
        self.vector_store = VectorStore(settings.chroma_persist_dir)

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

            chunk_items = self._save_document_and_chunks(
                doc_uid=doc_uid,
                doc_id=doc_id,
                doc_title=document.get("doc_title") or metadata["doc_title"],
                edition=edition,
                file_path=file_path,
                source_hash=source_hash,
                content=content,
            )
            self._sync_vector_index(doc_uid=doc_uid, chunk_items=chunk_items)

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
        """根据现有文档记录重新构建 SQLite 索引与向量索引。"""

        if not doc_uids:
            raise ValidationAppError("doc_uids 不能为空")

        accepted: list[str] = []
        for doc_uid in doc_uids:
            document = self.document_repository.get_by_doc_uid(doc_uid)
            if not document:
                raise NotFoundAppError("文档不存在", details={"doc_uid": doc_uid})

            file_path = Path(document["source_path"])
            if not file_path.exists():
                raise NotFoundAppError("源文档不存在", details={"doc_uid": doc_uid, "file_path": str(file_path)})

            content = read_text_file(file_path)
            chunk_items = self._save_document_and_chunks(
                doc_uid=document["doc_uid"],
                doc_id=document["doc_id"],
                doc_title=document["doc_title"],
                edition=document.get("edition") or "default",
                file_path=file_path,
                source_hash=sha256_of_text(content),
                content=content,
            )
            self._sync_vector_index(doc_uid=doc_uid, chunk_items=chunk_items)
            accepted.append(doc_uid)

        return accepted

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
    ) -> list[dict]:
        """保存文档主记录并构建最小 chunk 与 FTS 数据。"""

        now = utc_now_iso()
        sections = parse_markdown_sections(content, fallback_title=doc_title)
        chunk_items: list[dict] = []
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
            chunk_index = 0
            for section in sections:
                section_id = f"sec_{uuid4().hex[:12]}"
                connection.execute(
                    """
                    INSERT INTO document_sections (
                        section_id, doc_uid, section_title, section_level, source_span,
                        content, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        section_id,
                        doc_uid,
                        section["section_title"],
                        section["section_level"],
                        section["source_span"],
                        section["content"],
                        now,
                        now,
                    ),
                )

                for chunk_content in split_text(section["content"]):
                    chunk_id = f"chk_{uuid4().hex[:12]}"
                    source_span = f"{section['source_span']}:chunk-{chunk_index}"
                    chunk_item = {
                        "chunk_id": chunk_id,
                        "doc_uid": doc_uid,
                        "section_id": section_id,
                        "source_span": source_span,
                        "content": chunk_content,
                    }
                    chunk_items.append(chunk_item)
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
                            section_id,
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
                    chunk_index += 1
        return chunk_items

    def _sync_vector_index(self, *, doc_uid: str, chunk_items: list[dict]) -> None:
        """同步写入 ChromaDB，失败时标记部分失败状态。"""

        try:
            self.vector_store.delete_by_doc_uid(doc_uid)
            self.vector_store.upsert_chunks(chunk_items)
        except Exception as exc:  # noqa: BLE001
            self.document_repository.update_index_status(
                doc_uid=doc_uid,
                index_status="partial_failed",
                error_message=f"vector_index: {exc}",
            )
            raise DatabaseAppError(
                "向量索引写入失败",
                details={"doc_uid": doc_uid, "stage": "vector_index"},
            ) from exc
