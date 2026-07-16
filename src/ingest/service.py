"""程序说明：实现 Markdown 文档注册、分块与基础入库流程。"""

from __future__ import annotations

import json
import csv
from pathlib import Path
from uuid import uuid4

from src.ai.embedding import build_embedding_client
from src.chunking.splitter import split_text
from src.common.config import AppSettings
from src.common.errors import DatabaseAppError, NotFoundAppError, ValidationAppError
from src.common.paths import resolve_input_path, to_input_relative_path
from src.common.utils import read_text_file, sha256_of_text, utc_now_iso
from src.db.repositories import DocumentRepository, IngestJobRepository
from src.db.transaction import transaction
from src.ingest.quality_config import IngestQualityConfigService
from src.knowledge_base.service import KnowledgeBaseService
from src.metadata.extractor import extract_basic_metadata
from src.metadata.sections import parse_markdown_sections
from src.retrieval.query_normalizer import build_normalized_index_text
from src.retrieval.vector_store import VectorStore


class IngestService:
    """文档入库服务。"""

    def __init__(self, settings: AppSettings, *, vector_store: VectorStore | None = None) -> None:
        """初始化入库服务。C4 修复：接受外部注入 vector_store 避免重复创建。"""
        self.settings = settings
        self.document_repository = DocumentRepository(settings.sqlite_db_path)
        self.job_repository = IngestJobRepository(settings.sqlite_db_path)
        self.quality_config_service = IngestQualityConfigService(settings.templates_dir)
        self.knowledge_base_service = KnowledgeBaseService(settings.sqlite_db_path, settings.input_root)
        self.vector_store = vector_store or VectorStore(
            settings.chroma_persist_dir,
            embedding_client=build_embedding_client(settings),
            sqlite_db_path=settings.sqlite_db_path,
            auto_repair_dimension_mismatch=False,
            embedding_model=settings.embedding_model,
            index_version="retrieval-v2",
        )

    def register_documents(
        self,
        documents: list[dict],
        *,
        knowledge_base_id: str | None = None,
        rebuild_if_exists: bool = False,
        progress_callback=None,
    ) -> list[dict]:
        """注册文档，并完成最小可用入库流程。"""

        if not documents:
            raise ValidationAppError("documents 不能为空")

        jobs: list[dict] = []
        total_documents = len(documents)
        for index, document in enumerate(documents, start=1):
            child_callback = None
            if progress_callback:
                child_callback = lambda info, current=index: progress_callback(  # noqa: E731
                    {
                        **info,
                        "current_document": current,
                        "total_documents": total_documents,
                        "overall_percent": int(((current - 1) + (info["percent"] / 100)) / total_documents * 100),
                    }
                )
            jobs.append(
                self.register_document(
                    document,
                    knowledge_base_id=knowledge_base_id or document.get("knowledge_base_id"),
                    rebuild_if_exists=rebuild_if_exists,
                    progress_callback=child_callback,
                )
            )

        return jobs

    def register_document(
        self,
        document: dict,
        *,
        knowledge_base_id: str | None = None,
        rebuild_if_exists: bool = False,
        progress_callback=None,
    ) -> dict:
        """注册单篇文档，并返回更细粒度的进度信息。"""

        progress_events: list[dict] = []

        def report(stage: str, message: str, percent: int, **extra) -> None:
            payload = {
                "stage": stage,
                "message": message,
                "percent": percent,
                **extra,
            }
            progress_events.append(payload)
            if progress_callback:
                progress_callback(payload)

        # C5 修复：校验文件路径是否在允许的输入目录内，防止路径遍历。
        file_path = resolve_input_path(document["file_path"], self.settings.input_root)
        if not file_path.exists():
            raise NotFoundAppError("文档文件不存在", details={"file_path": str(file_path)})
        resolved_knowledge_base_id = self.knowledge_base_service.get_knowledge_base(
            knowledge_base_id or document.get("knowledge_base_id")
        )["knowledge_base_id"]
        file_path = self.knowledge_base_service.relocate_document_file(file_path, resolved_knowledge_base_id)

        report("prepare", "开始读取输入文档", 5, file_path=str(file_path))
        try:
            content = read_text_file(file_path)
            metadata = extract_basic_metadata(file_path, content)
        except ValueError as exc:
            raise ValidationAppError(
                "输入文档格式无效",
                details={"file_path": str(file_path), "reason": str(exc)},
            ) from exc
        source_hash = sha256_of_text(content)
        doc_id = metadata["doc_id"]
        edition = document.get("edition") or metadata.get("edition") or "default"
        doc_uid = f"{doc_id}_{edition}".replace(" ", "_")
        stored_source_path = to_input_relative_path(file_path, self.settings.input_root)
        existing = self.document_repository.get_by_source_path(stored_source_path)

        if existing and existing["source_hash"] == source_hash and not rebuild_if_exists:
            if str(existing.get("knowledge_base_id") or "") != resolved_knowledge_base_id:
                self.document_repository.reassign_document_knowledge_base(
                    doc_uid=existing["doc_uid"],
                    knowledge_base_id=resolved_knowledge_base_id,
                    source_path=stored_source_path,
                )
            return {
                "job_id": f"job_{uuid4().hex[:12]}",
                "doc_uid": existing["doc_uid"],
                "status": "skipped",
                "progress_events": progress_events + [
                    {
                        "stage": "skip",
                        "message": "文档内容未变化，跳过注册",
                        "percent": 100,
                    }
                ],
            }

        self.document_repository.update_ingest_state(
            doc_uid=doc_uid,
            ingest_status="processing",
            index_status="pending",
            error_message=None,
        ) if existing else None
        report("parse", "完成文本读取，开始解析章节与元数据", 15, doc_uid=doc_uid)
        chunk_items = self._save_document_and_chunks(
            doc_uid=doc_uid,
            knowledge_base_id=resolved_knowledge_base_id,
            doc_id=doc_id,
            doc_title=document.get("doc_title") or metadata["doc_title"],
            edition=edition,
            author=document.get("author") or metadata.get("author"),
            source_name=document.get("source_name") or metadata.get("source_name"),
            tags=document.get("tags") or metadata.get("tags", []),
            file_path=file_path,
            source_hash=source_hash,
            content=content,
        )
        report(
            "fulltext_index",
            "已写入文档、章节、分块与全文索引",
            45,
            chunk_total=len(chunk_items),
        )
        self._sync_vector_index(
            doc_uid=doc_uid,
            chunk_items=chunk_items,
            progress_callback=lambda info: report(
                "vector_index",
                f'正在写入向量索引（{info["completed_chunks"]}/{info["total_chunks"]}）',
                min(95, 45 + int(info["completed_chunks"] * 50 / max(info["total_chunks"], 1))),
                **info,
            ),
        )
        self.document_repository.update_ingest_state(
            doc_uid=doc_uid,
            ingest_status="completed",
            index_status="indexed",
            error_message=None,
        )
        report("completed", "文档注册完成", 100, chunk_total=len(chunk_items))

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
        return {"job_id": job_id, "doc_uid": doc_uid, "status": "completed", "progress_events": progress_events}

    def list_status(
        self,
        *,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """查询文档入库状态。"""

        return self.document_repository.list_documents(
            doc_uid=doc_uid,
            knowledge_base_id=knowledge_base_id,
            status=status,
            page=page,
            page_size=page_size,
        )

    def get_database_summary(self, *, knowledge_base_id: str | None = None) -> dict[str, int]:
        """读取数据库中与文档管理相关的关键统计信息。"""

        return self.document_repository.get_database_summary(knowledge_base_id=knowledge_base_id)

    def inspect_document_quality(self, doc_uid: str, *, sample_limit: int | None = None) -> dict:
        """汇总单篇文档的入库质检结果。"""

        if not doc_uid:
            raise ValidationAppError("doc_uid 不能为空")

        quality_config = self.quality_config_service.get_config()
        resolved_sample_limit = int(sample_limit or quality_config["sample_limit"])
        snapshot = self.document_repository.get_document_quality_snapshot(doc_uid, sample_limit=resolved_sample_limit)
        if not snapshot:
            raise NotFoundAppError("文档不存在", details={"doc_uid": doc_uid})

        metrics = snapshot["metrics"]
        document = snapshot["document"]
        issues: list[dict] = []
        checks: list[dict] = []

        def append_check(name: str, passed: bool, message: str, *, level: str | None = None) -> None:
            resolved_level = level or ("success" if passed else "danger")
            checks.append({"name": name, "passed": passed, "message": message, "level": resolved_level})
            if not passed:
                issues.append({"level": resolved_level, "message": message})

        append_check(
            "入库状态",
            str(document.get("ingest_status")) == "completed",
            "文档已完成入库。" if str(document.get("ingest_status")) == "completed" else f'当前入库状态为 {document.get("ingest_status")}',
        )
        append_check(
            "章节解析",
            int(metrics.get("section_count") or 0) > 0,
            (
                f'已解析 {metrics.get("section_count")} 个章节。'
                if int(metrics.get("section_count") or 0) > 0
                else "未解析出任何章节。"
            ),
        )
        append_check(
            "分块生成",
            int(metrics.get("chunk_count") or 0) > 0,
            (
                f'已生成 {metrics.get("chunk_count")} 个分块。'
                if int(metrics.get("chunk_count") or 0) > 0
                else "未生成任何分块。"
            ),
        )
        fulltext_index_consistent = int(metrics.get("chunk_count") or 0) == int(metrics.get("fts_chunk_count") or 0)
        append_check(
            "全文索引",
            fulltext_index_consistent,
            (
                f'全文索引条数与分块一致，共 {metrics.get("fts_chunk_count")} 条。'
                if fulltext_index_consistent
                else f'全文索引条数 {metrics.get("fts_chunk_count")} 与分块数 {metrics.get("chunk_count")} 不一致。'
            ),
            level="warning" if not fulltext_index_consistent else None,
        )

        vector_chunk_count: int | None
        try:
            vector_chunk_count = self.vector_store.count_by_doc_uid(doc_uid)
        except Exception:  # noqa: BLE001
            vector_chunk_count = None
            checks.append(
                {
                    "name": "向量索引",
                    "passed": False,
                    "message": "当前无法读取向量索引条数，请检查向量库状态。",
                    "level": "warning",
                }
            )
            issues.append({"level": "warning", "message": "当前无法读取向量索引条数，请检查向量库状态。"})
        else:
            vector_index_consistent = vector_chunk_count == int(metrics.get("chunk_count") or 0)
            append_check(
                "向量索引",
                vector_index_consistent,
                (
                    f'向量索引条数与分块一致，共 {vector_chunk_count} 条。'
                    if vector_index_consistent
                    else f'向量索引条数 {vector_chunk_count} 与分块数 {metrics.get("chunk_count")} 不一致。'
                ),
                level="warning" if not vector_index_consistent or str(document.get("index_status")) == "partial_failed" else None,
            )

        if str(document.get("index_status")) != "indexed":
            issues.append({"level": "warning", "message": f'当前索引状态为 {document.get("index_status")}，建议执行重建。'})
            checks.append(
                {
                    "name": "索引状态",
                    "passed": False,
                    "message": f'当前索引状态为 {document.get("index_status")}，建议执行重建。',
                    "level": "warning",
                }
            )
        else:
            checks.append({"name": "索引状态", "passed": True, "message": "当前索引状态正常。", "level": "success"})

        if (
            int(metrics.get("section_count") or 0) < int(quality_config["min_sections_for_long_doc"])
            and int(metrics.get("total_chunk_chars") or 0) >= int(quality_config["long_document_char_threshold"])
        ):
            issues.append({"level": "warning", "message": "章节数偏少，长文档可能没有按标题切开。"})
        if float(metrics.get("avg_chunks_per_section") or 0.0) >= float(quality_config["max_avg_chunks_per_section"]):
            issues.append({"level": "warning", "message": "平均每章分块数偏高，可能切得过碎。"})
        if int(metrics.get("max_chunk_chars") or 0) >= int(quality_config["max_chunk_chars"]):
            issues.append({"level": "warning", "message": "存在超长分块，建议抽样检查分块边界。"})
        if (
            int(metrics.get("min_chunk_chars") or 0) > 0
            and int(metrics.get("min_chunk_chars") or 0) <= int(quality_config["short_chunk_chars"])
            and int(metrics.get("chunk_count") or 0) >= int(quality_config["short_chunk_warn_min_chunk_count"])
        ):
            issues.append({"level": "warning", "message": "存在过短分块，可能影响检索效果。"})

        overall_level = "success"
        if any(item["level"] == "danger" for item in issues):
            overall_level = "danger"
        elif issues:
            overall_level = "warning"
        summary_message = (
            "入库结构与索引看起来正常。"
            if overall_level == "success"
            else "发现需要复核的问题，请结合抽样结果进一步检查。"
        )
        return {
            **snapshot,
            "metrics": {
                **metrics,
                "vector_chunk_count": vector_chunk_count,
            },
            "checks": checks,
            "issues": issues,
            "summary": {
                "level": overall_level,
                "message": summary_message,
            },
            "applied_thresholds": quality_config,
        }

    def list_document_quality_reports(
        self,
        *,
        doc_uids: list[str] | None = None,
        knowledge_base_id: str | None = None,
        page_size: int = 200,
    ) -> dict:
        """批量读取文档入库质检结果。"""

        if doc_uids:
            documents = [
                self.document_repository.get_by_doc_uid(doc_uid)
                for doc_uid in doc_uids
            ]
            documents = [item for item in documents if item]
        else:
            documents, _ = self.list_status(
                doc_uid=None,
                knowledge_base_id=knowledge_base_id,
                status=None,
                page=1,
                page_size=page_size,
            )

        reports = [self.inspect_document_quality(str(document["doc_uid"])) for document in documents if document.get("doc_uid")]
        summary = {
            "document_count": len(reports),
            "success_count": sum(1 for item in reports if item["summary"]["level"] == "success"),
            "warning_count": sum(1 for item in reports if item["summary"]["level"] == "warning"),
            "danger_count": sum(1 for item in reports if item["summary"]["level"] == "danger"),
        }
        return {"reports": reports, "summary": summary}

    def export_document_quality_reports_csv(
        self,
        *,
        doc_uids: list[str] | None = None,
        knowledge_base_id: str | None = None,
    ) -> dict:
        """导出批量入库质检结果 CSV。"""

        batch_result = self.list_document_quality_reports(doc_uids=doc_uids, knowledge_base_id=knowledge_base_id)
        docs_dir = Path("Docs")
        docs_dir.mkdir(parents=True, exist_ok=True)
        file_path = docs_dir / f'document_ingest_quality_{utc_now_iso().replace(":", "").replace("-", "").replace("+", "_").replace("T", "_")}.csv'
        fieldnames = [
            "doc_uid",
            "doc_title",
            "ingest_status",
            "index_status",
            "section_count",
            "chunk_count",
            "fts_chunk_count",
            "vector_chunk_count",
            "avg_chunk_chars",
            "avg_chunks_per_section",
            "quality_level",
            "quality_message",
            "issues",
            "source_path",
        ]
        with file_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for report in batch_result["reports"]:
                document = report["document"]
                metrics = report["metrics"]
                writer.writerow(
                    {
                        "doc_uid": document.get("doc_uid"),
                        "doc_title": document.get("doc_title"),
                        "ingest_status": document.get("ingest_status"),
                        "index_status": document.get("index_status"),
                        "section_count": metrics.get("section_count"),
                        "chunk_count": metrics.get("chunk_count"),
                        "fts_chunk_count": metrics.get("fts_chunk_count"),
                        "vector_chunk_count": metrics.get("vector_chunk_count"),
                        "avg_chunk_chars": metrics.get("avg_chunk_chars"),
                        "avg_chunks_per_section": metrics.get("avg_chunks_per_section"),
                        "quality_level": report["summary"].get("level"),
                        "quality_message": report["summary"].get("message"),
                        "issues": "；".join(str(item.get("message") or "") for item in report.get("issues", [])),
                        "source_path": document.get("source_path"),
                    }
                )
        return {
            "file_path": str(file_path.resolve()),
            "row_count": len(batch_result["reports"]),
            "summary": batch_result["summary"],
        }

    def get_document_quality_config(self) -> dict:
        """读取入库质检阈值配置。"""

        return self.quality_config_service.get_config()

    def save_document_quality_config(self, payload: dict) -> dict:
        """保存入库质检阈值配置。"""

        return self.quality_config_service.save_config(payload)

    def list_knowledge_bases(self) -> list[dict]:
        """列出知识库。"""

        return self.knowledge_base_service.list_knowledge_bases()

    def get_knowledge_base(self, knowledge_base_id: str | None) -> dict:
        """读取知识库配置。"""

        return self.knowledge_base_service.get_knowledge_base(knowledge_base_id)

    def save_knowledge_base(self, payload: dict) -> dict:
        """保存知识库配置。"""

        return self.knowledge_base_service.save_knowledge_base(payload)

    def normalize_legacy_default_documents(self) -> list[dict]:
        """迁移 Input 根目录历史文档到默认知识库目录。"""

        return self.knowledge_base_service.normalize_legacy_default_documents()

    def delete_knowledge_base(self, knowledge_base_id: str) -> dict:
        """删除知识库配置。"""

        return self.knowledge_base_service.delete_knowledge_base(knowledge_base_id)

    def relocate_document_to_knowledge_base(
        self,
        *,
        source_path: str,
        target_knowledge_base_id: str,
        doc_uid: str | None = None,
    ) -> dict:
        """调整文档归属知识库，并在可能时同步移动输入文件。"""

        if not source_path:
            raise ValidationAppError("source_path 不能为空")
        resolved_knowledge_base_id = self.knowledge_base_service.get_knowledge_base(target_knowledge_base_id)[
            "knowledge_base_id"
        ]
        original_source_path = to_input_relative_path(source_path, self.settings.input_root)
        resolved_path = self.knowledge_base_service.relocate_document_file(source_path, resolved_knowledge_base_id)
        stored_source_path = to_input_relative_path(resolved_path, self.settings.input_root)

        document = self.document_repository.get_by_doc_uid(doc_uid) if doc_uid else None
        if not document:
            document = self.document_repository.get_by_source_path(original_source_path)
        if not document:
            document = self.document_repository.get_by_source_path(stored_source_path)
        if not document:
            document = self.document_repository.get_by_source_path(source_path)
        if document:
            self.document_repository.reassign_document_knowledge_base(
                doc_uid=document["doc_uid"],
                knowledge_base_id=resolved_knowledge_base_id,
                source_path=stored_source_path,
            )
            return self.document_repository.get_by_doc_uid(document["doc_uid"]) or document

        return {
            "doc_uid": "",
            "knowledge_base_id": resolved_knowledge_base_id,
            "source_path": stored_source_path,
        }

    def rebuild_documents(
        self,
        doc_uids: list[str],
        *,
        rebuild_fulltext: bool = True,
        rebuild_vector: bool = True,
        progress_callback=None,
    ) -> list[str]:
        """根据现有文档记录重新构建 SQLite 索引与向量索引。"""

        if not doc_uids:
            raise ValidationAppError("doc_uids 不能为空")
        if not rebuild_fulltext and not rebuild_vector:
            raise ValidationAppError("至少选择一种重建类型")

        accepted: list[str] = []
        total_documents = len(doc_uids)
        for index, doc_uid in enumerate(doc_uids, start=1):
            def report(stage: str, message: str, percent: int, **extra) -> None:
                if progress_callback:
                    progress_callback(
                        {
                            "stage": stage,
                            "message": message,
                            "percent": percent,
                            "current_document": index,
                            "total_documents": total_documents,
                            "overall_percent": int(((index - 1) + (percent / 100)) / total_documents * 100),
                            **extra,
                        }
                    )

            document = self.document_repository.get_by_doc_uid(doc_uid)
            if not document:
                raise NotFoundAppError("文档不存在", details={"doc_uid": doc_uid})

            file_path = resolve_input_path(document["source_path"], self.settings.input_root)
            if not file_path.exists():
                raise NotFoundAppError("源文档不存在", details={"doc_uid": doc_uid, "file_path": str(file_path)})

            chunk_items: list[dict] = []
            if rebuild_fulltext:
                report("prepare", "开始读取源文档", 5, doc_uid=doc_uid)
                try:
                    content = read_text_file(file_path)
                except ValueError as exc:
                    raise ValidationAppError(
                        "输入文档格式无效",
                        details={"file_path": str(file_path), "reason": str(exc)},
                    ) from exc
                self.document_repository.update_ingest_state(
                    doc_uid=document["doc_uid"],
                    ingest_status="processing",
                    index_status="rebuilding",
                    error_message=None,
                )
                report("fulltext_index", "正在重建章节、分块与全文索引", 40, doc_uid=doc_uid)
                chunk_items = self._save_document_and_chunks(
                    doc_uid=document["doc_uid"],
                    knowledge_base_id=str(document.get("knowledge_base_id") or "default"),
                    doc_id=document["doc_id"],
                    doc_title=document["doc_title"],
                    edition=document.get("edition") or "default",
                    author=document.get("author"),
                    source_name=document.get("source_name"),
                    tags=document.get("tags", []),
                    file_path=file_path,
                    source_hash=sha256_of_text(content),
                    content=content,
                )

            if rebuild_vector:
                if not chunk_items:
                    chunk_items = self.document_repository.list_chunks_by_doc_uid(doc_uid)
                self._sync_vector_index(
                    doc_uid=doc_uid,
                    chunk_items=chunk_items,
                    progress_callback=lambda info: report(
                        "vector_index",
                        f'正在重建向量索引（{info["completed_chunks"]}/{info["total_chunks"]}）',
                        min(95, 40 + int(info["completed_chunks"] * 55 / max(info["total_chunks"], 1))),
                        doc_uid=doc_uid,
                        **info,
                    ),
                )
            self.document_repository.update_ingest_state(
                doc_uid=doc_uid,
                ingest_status="completed",
                index_status="indexed",
                error_message=None,
            )
            report("completed", "重建完成", 100, doc_uid=doc_uid)
            accepted.append(doc_uid)

        return accepted

    def _save_document_and_chunks(
        self,
        *,
        doc_uid: str,
        knowledge_base_id: str,
        doc_id: str,
        doc_title: str,
        edition: str,
        author: str | None,
        source_name: str | None,
        tags: list[str],
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
                    doc_uid,
                    knowledge_base_id,
                    doc_id,
                    doc_title,
                    edition,
                    author,
                    source_name,
                    json.dumps(tags, ensure_ascii=False),
                    to_input_relative_path(file_path, self.settings.input_root),
                    source_hash,
                    "processing",
                    "pending",
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
                        section_id, doc_uid, section_title, section_level, heading_path,
                        source_start_line, source_end_line, source_anchor, source_span,
                        content, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        section_id,
                        doc_uid,
                        section["section_title"],
                        section["section_level"],
                        section.get("heading_path"),
                        section.get("source_start_line"),
                        section.get("source_end_line"),
                        section.get("source_anchor"),
                        section["source_span"],
                        section["content"],
                        now,
                        now,
                    ),
                )

                for chunk_content in split_text(section["content"]):
                    chunk_id = f"chk_{uuid4().hex[:12]}"
                    source_span = f"{section['source_span']}:chunk-{chunk_index}"
                    chunk_type = _detect_chunk_type(chunk_content)
                    content_hash = sha256_of_text(chunk_content)
                    chunk_item = {
                        "chunk_id": chunk_id,
                        "doc_uid": doc_uid,
                        "section_id": section_id,
                        "source_span": source_span,
                        "heading_path": section.get("heading_path"),
                        "source_start_line": section.get("source_start_line"),
                        "source_end_line": section.get("source_end_line"),
                        "page_no": None,
                        "chunk_type": chunk_type,
                        "content_hash": content_hash,
                        "source_anchor": section.get("source_anchor"),
                        "content": chunk_content,
                        # H7 修复：写入知识库 ID，供向量检索按知识库过滤
                        "knowledge_base_id": knowledge_base_id,
                    }
                    chunk_items.append(chunk_item)
                    connection.execute(
                        """
                        INSERT INTO chunks (
                            chunk_id, doc_uid, section_id, chunk_index, content, source_span,
                            heading_path, source_start_line, source_end_line, page_no, chunk_type,
                            content_hash, source_anchor, token_count, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chunk_id,
                            doc_uid,
                            section_id,
                            chunk_index,
                            chunk_content,
                            source_span,
                            section.get("heading_path"),
                            section.get("source_start_line"),
                            section.get("source_end_line"),
                            None,
                            chunk_type,
                            content_hash,
                            section.get("source_anchor"),
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
                        (chunk_id, doc_uid, build_normalized_index_text(chunk_content)),
                    )
                    chunk_index += 1
        return chunk_items

    def _sync_vector_index(self, *, doc_uid: str, chunk_items: list[dict], progress_callback=None) -> None:
        """同步写入 ChromaDB，失败时标记部分失败状态。"""

        try:
            self.vector_store.delete_by_doc_uid(doc_uid)
            self.vector_store.upsert_chunks(chunk_items, progress_callback=progress_callback)
        except Exception as exc:  # noqa: BLE001
            self.document_repository.update_ingest_state(
                doc_uid=doc_uid,
                ingest_status="completed",
                index_status="partial_failed",
                error_message=f"vector_index: {exc}",
            )
            raise DatabaseAppError(
                "向量索引写入失败",
                details={"doc_uid": doc_uid, "stage": "vector_index"},
            ) from exc


def _detect_chunk_type(chunk_content: str) -> str:
    """根据 chunk 首个有效行识别基础 Markdown 类型。"""

    for line in chunk_content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            return "code"
        if stripped.startswith("|") and stripped.endswith("|"):
            return "table"
        if stripped.startswith(">"):
            return "blockquote"
        if stripped.startswith(("- ", "* ", "+ ")) or _is_ordered_list_line(stripped):
            return "list"
        return "paragraph"
    return "paragraph"


def _is_ordered_list_line(stripped_line: str) -> bool:
    """判断是否为有序列表行。"""

    dot_index = stripped_line.find(". ")
    if dot_index <= 0:
        return False
    return stripped_line[:dot_index].isdigit()
