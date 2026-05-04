"""程序说明：验证知识库模型、服务与过滤行为。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.common.config import AppSettings
from src.common.errors import ValidationAppError
from src.db.connection import create_connection, initialize_database
from src.db.repositories import DocumentRepository, QualityRepository
from src.ingest.service import IngestService
from src.knowledge_base.service import KnowledgeBaseService
from src.review.service import ReviewService


def _insert_knowledge_base(database_path: Path, knowledge_base_id: str, knowledge_base_name: str) -> None:
    """插入测试知识库，避免每个用例重复写样板 SQL。"""

    with create_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO knowledge_bases (
                knowledge_base_id, knowledge_base_name, description, status, is_default, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                knowledge_base_id,
                knowledge_base_name,
                "",
                "active",
                0,
                "2026-05-03T00:00:00+00:00",
                "2026-05-03T00:00:00+00:00",
            ),
        )
        connection.commit()


def _create_quality_result(
    repository: QualityRepository,
    *,
    check_id: str,
    knowledge_base_id: str,
    claim_id: str,
    created_at: str,
) -> None:
    """创建最小质检结果，供过滤测试复用。"""

    repository.create_quality_result(
        quality_check={
            "check_id": check_id,
            "knowledge_base_id": knowledge_base_id,
            "input_text": f"{knowledge_base_id} 内容",
            "template_id": "general_fact_check",
            "template_name": "通用事实核检",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "check",
            "created_at": created_at,
            "updated_at": created_at,
        },
        claims=[
            {
                "claim_id": claim_id,
                "check_id": check_id,
                "claim_text": f"{knowledge_base_id} Claim",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.5,
                "evidence": "evidence",
                "source_doc": f"doc_{knowledge_base_id}",
                "source_span": "s1",
                "review_status": "pending",
                "created_at": created_at,
                "updated_at": created_at,
            }
        ],
    )


def _insert_section_and_chunk(
    database_path: Path,
    *,
    doc_uid: str,
    section_id: str,
    chunk_id: str,
    created_at: str = "2026-05-03T00:00:00+00:00",
) -> None:
    """补齐摘要统计所需的章节和分块记录。"""

    with create_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO document_sections (
                section_id, doc_uid, section_title, section_level, source_span, content, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (section_id, doc_uid, "章节", 1, "1-10", "测试章节内容", created_at, created_at),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, doc_uid, section_id, chunk_index, content, source_span, token_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chunk_id, doc_uid, section_id, 1, "测试分块内容", "1-10", 8, created_at, created_at),
        )
        connection.commit()


def test_initialize_database_should_create_default_knowledge_base(tmp_path: Path) -> None:
    """初始化数据库后应自动创建默认知识库。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)

    with create_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT knowledge_base_id, knowledge_base_name, is_default
            FROM knowledge_bases
            WHERE knowledge_base_id = 'default'
            """
        ).fetchone()

    assert row is not None
    assert row["knowledge_base_name"] == "默认知识库"
    assert int(row["is_default"]) == 1


def test_initialize_database_should_upgrade_legacy_tables_before_creating_indexes(tmp_path: Path) -> None:
    """旧库缺少 knowledge_base_id 时，初始化应先补列再执行 schema。"""

    database_path = tmp_path / "legacy.db"
    with create_connection(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE documents (
                doc_uid TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                doc_title TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                ingest_status TEXT NOT NULL,
                index_status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE quality_checks (
                check_id TEXT PRIMARY KEY,
                input_text TEXT NOT NULL,
                overall_verdict TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

    initialize_database(database_path)

    with create_connection(database_path) as connection:
        document_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
        quality_check_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(quality_checks)").fetchall()
        }

    assert "knowledge_base_id" in document_columns
    assert "knowledge_base_id" in quality_check_columns


def test_knowledge_base_service_should_block_delete_when_documents_exist(tmp_path: Path) -> None:
    """已有归属文档的知识库不允许删除。"""

    database_path = tmp_path / "app.db"
    input_root = tmp_path / "Input"
    initialize_database(database_path)
    service = KnowledgeBaseService(database_path, input_root)
    repository = DocumentRepository(database_path)

    item = service.save_knowledge_base(
        {
            "knowledge_base_id": "test_kb",
            "knowledge_base_name": "测试知识库",
            "description": "用于测试",
        }
    )
    repository.upsert_document(
        {
            "doc_uid": "doc_1",
            "knowledge_base_id": "test_kb",
            "doc_id": "doc",
            "doc_title": "测试文档",
            "source_path": str((input_root / "test_kb" / "a.md").resolve()),
            "source_hash": "hash-1",
            "ingest_status": "completed",
            "index_status": "indexed",
            "error_message": None,
        }
    )

    assert item["knowledge_base_id"] == "test_kb"
    assert (input_root / "test_kb").exists()

    with pytest.raises(ValidationAppError):
        service.delete_knowledge_base("test_kb")


def test_quality_repository_should_filter_recent_results_by_knowledge_base(tmp_path: Path) -> None:
    """最近质检记录应支持按知识库过滤。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    repository = QualityRepository(database_path)

    repository.create_quality_result(
        quality_check={
            "check_id": "chk_1",
            "knowledge_base_id": "default",
            "input_text": "默认知识库内容",
            "template_id": "general_fact_check",
            "template_name": "通用事实核检",
            "overall_verdict": "passed",
            "risk_level": "low",
            "summary": "ok",
            "created_at": "2026-05-03T00:00:00+00:00",
            "updated_at": "2026-05-03T00:00:00+00:00",
        },
        claims=[
            {
                "claim_id": "claim_1",
                "check_id": "chk_1",
                "claim_text": "默认 Claim",
                "verdict": "verified",
                "risk_level": "low",
                "confidence": 0.9,
                "evidence": "e1",
                "source_doc": "doc_1",
                "source_span": "s1",
                "review_status": "pending",
                "created_at": "2026-05-03T00:00:00+00:00",
                "updated_at": "2026-05-03T00:00:00+00:00",
            }
        ],
    )

    with create_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO knowledge_bases (
                knowledge_base_id, knowledge_base_name, description, status, is_default, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("kb_b", "知识库B", "", "active", 0, "2026-05-03T00:00:00+00:00", "2026-05-03T00:00:00+00:00"),
        )
        connection.commit()

    repository.create_quality_result(
        quality_check={
            "check_id": "chk_2",
            "knowledge_base_id": "kb_b",
            "input_text": "知识库B内容",
            "template_id": "general_fact_check",
            "template_name": "通用事实核检",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "check",
            "created_at": "2026-05-03T01:00:00+00:00",
            "updated_at": "2026-05-03T01:00:00+00:00",
        },
        claims=[
            {
                "claim_id": "claim_2",
                "check_id": "chk_2",
                "claim_text": "B Claim",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.5,
                "evidence": "e2",
                "source_doc": "doc_2",
                "source_span": "s2",
                "review_status": "pending",
                "created_at": "2026-05-03T01:00:00+00:00",
                "updated_at": "2026-05-03T01:00:00+00:00",
            }
        ],
    )

    default_results = repository.list_recent_quality_results(limit=10, knowledge_base_id="default")
    kb_b_results = repository.list_recent_quality_results(limit=10, knowledge_base_id="kb_b")

    assert [item["check_id"] for item in default_results] == ["chk_1"]
    assert [item["check_id"] for item in kb_b_results] == ["chk_2"]


def test_document_repository_should_filter_documents_by_knowledge_base(tmp_path: Path) -> None:
    """文档状态列表应只返回当前知识库下的文档。"""

    database_path = tmp_path / "app.db"
    input_root = tmp_path / "Input"
    initialize_database(database_path)
    _insert_knowledge_base(database_path, "kb_b", "知识库B")
    repository = DocumentRepository(database_path)

    repository.upsert_document(
        {
            "doc_uid": "doc_default",
            "knowledge_base_id": "default",
            "doc_id": "doc-default",
            "doc_title": "默认文档",
            "source_path": str((input_root / "default" / "default.md").resolve()),
            "source_hash": "hash-default",
            "ingest_status": "completed",
            "index_status": "indexed",
            "error_message": None,
        }
    )
    repository.upsert_document(
        {
            "doc_uid": "doc_kb_b",
            "knowledge_base_id": "kb_b",
            "doc_id": "doc-kb-b",
            "doc_title": "B 文档",
            "source_path": str((input_root / "kb_b" / "b.md").resolve()),
            "source_hash": "hash-kb-b",
            "ingest_status": "completed",
            "index_status": "indexed",
            "error_message": None,
        }
    )

    default_items, default_total = repository.list_documents(knowledge_base_id="default", page=1, page_size=10)
    kb_b_items, kb_b_total = repository.list_documents(knowledge_base_id="kb_b", page=1, page_size=10)

    assert default_total == 1
    assert kb_b_total == 1
    assert [item["doc_uid"] for item in default_items] == ["doc_default"]
    assert [item["doc_uid"] for item in kb_b_items] == ["doc_kb_b"]


def test_document_repository_should_build_database_summary_by_knowledge_base(tmp_path: Path) -> None:
    """数据库摘要应按知识库隔离统计文档、分块、质检与审核数量。"""

    database_path = tmp_path / "app.db"
    input_root = tmp_path / "Input"
    initialize_database(database_path)
    _insert_knowledge_base(database_path, "kb_b", "知识库B")
    document_repository = DocumentRepository(database_path)
    quality_repository = QualityRepository(database_path)

    document_repository.upsert_document(
        {
            "doc_uid": "doc_default",
            "knowledge_base_id": "default",
            "doc_id": "doc-default",
            "doc_title": "默认文档",
            "source_path": str((input_root / "default" / "default.md").resolve()),
            "source_hash": "hash-default",
            "ingest_status": "completed",
            "index_status": "indexed",
            "error_message": None,
        }
    )
    document_repository.upsert_document(
        {
            "doc_uid": "doc_kb_b",
            "knowledge_base_id": "kb_b",
            "doc_id": "doc-kb-b",
            "doc_title": "B 文档",
            "source_path": str((input_root / "kb_b" / "b.md").resolve()),
            "source_hash": "hash-kb-b",
            "ingest_status": "processing",
            "index_status": "pending",
            "error_message": None,
        }
    )
    _insert_section_and_chunk(database_path, doc_uid="doc_default", section_id="sec_default", chunk_id="chunk_default")
    _insert_section_and_chunk(database_path, doc_uid="doc_kb_b", section_id="sec_kb_b", chunk_id="chunk_kb_b")

    _create_quality_result(
        quality_repository,
        check_id="chk_default",
        knowledge_base_id="default",
        claim_id="claim_default",
        created_at="2026-05-03T00:00:00+00:00",
    )
    _create_quality_result(
        quality_repository,
        check_id="chk_kb_b",
        knowledge_base_id="kb_b",
        claim_id="claim_kb_b",
        created_at="2026-05-03T01:00:00+00:00",
    )
    quality_repository.insert_review_record(
        {
            "review_id": "rev_default",
            "claim_id": "claim_default",
            "review_action": "approved",
            "reviewed_verdict": "verified",
            "review_note": "ok",
            "reviewer": "tester",
            "created_at": "2026-05-03T02:00:00+00:00",
        }
    )

    default_summary = document_repository.get_database_summary(knowledge_base_id="default")
    kb_b_summary = document_repository.get_database_summary(knowledge_base_id="kb_b")

    assert default_summary["document_count"] == 1
    assert default_summary["completed_document_count"] == 1
    assert default_summary["indexed_document_count"] == 1
    assert default_summary["rebuild_pending_document_count"] == 0
    assert default_summary["failed_document_count"] == 0
    assert default_summary["section_count"] == 1
    assert default_summary["chunk_count"] == 1
    assert default_summary["quality_check_count"] == 1
    assert default_summary["claim_count"] == 1
    assert default_summary["review_count"] == 1

    assert kb_b_summary["document_count"] == 1
    assert kb_b_summary["completed_document_count"] == 0
    assert kb_b_summary["indexed_document_count"] == 0
    assert kb_b_summary["rebuild_pending_document_count"] == 1
    assert kb_b_summary["failed_document_count"] == 0
    assert kb_b_summary["section_count"] == 1
    assert kb_b_summary["chunk_count"] == 1
    assert kb_b_summary["quality_check_count"] == 1
    assert kb_b_summary["claim_count"] == 1
    assert kb_b_summary["review_count"] == 0


def test_ingest_service_should_relocate_document_to_target_knowledge_base(tmp_path: Path) -> None:
    """调整文档归属时，应同时移动源文件并更新数据库归属。"""

    input_root = tmp_path / "Input"
    default_dir = input_root / "default"
    default_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = input_root / "legacy.md"
    legacy_file.write_text("# 旧文档\n\n用于迁移测试。", encoding="utf-8")

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=input_root,
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)

    service = IngestService(settings)
    service.vector_store.upsert_chunks = lambda items, **kwargs: None  # type: ignore[method-assign]
    service.save_knowledge_base(
        {
            "knowledge_base_id": "kb_b",
            "knowledge_base_name": "知识库B",
            "description": "用于迁移测试",
        }
    )
    job = service.register_document({"file_path": str(legacy_file)}, knowledge_base_id="default")

    moved_item = service.relocate_document_to_knowledge_base(
        source_path=str(default_dir / "legacy.md"),
        target_knowledge_base_id="kb_b",
        doc_uid=job["doc_uid"],
    )

    assert moved_item["knowledge_base_id"] == "kb_b"
    assert not (default_dir / "legacy.md").exists()
    assert (input_root / "kb_b" / "legacy.md").exists()

    repository = DocumentRepository(settings.sqlite_db_path)
    moved_document = repository.get_by_doc_uid(job["doc_uid"])
    assert moved_document is not None
    assert moved_document["knowledge_base_id"] == "kb_b"
    assert Path(moved_document["source_path"]).resolve() == (input_root / "kb_b" / "legacy.md").resolve()


def test_review_service_should_filter_review_candidates_by_knowledge_base(tmp_path: Path) -> None:
    """人工审核候选列表应只返回当前知识库的 Claim。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    _insert_knowledge_base(database_path, "kb_b", "知识库B")
    repository = QualityRepository(database_path)
    service = ReviewService(database_path)

    _create_quality_result(
        repository,
        check_id="chk_default",
        knowledge_base_id="default",
        claim_id="claim_default",
        created_at="2026-05-03T00:00:00+00:00",
    )
    _create_quality_result(
        repository,
        check_id="chk_kb_b",
        knowledge_base_id="kb_b",
        claim_id="claim_kb_b",
        created_at="2026-05-03T01:00:00+00:00",
    )

    default_candidates = service.list_review_candidates(limit=10, knowledge_base_id="default")
    kb_b_candidates = service.list_review_candidates(limit=10, knowledge_base_id="kb_b")

    assert [item["claim_id"] for item in default_candidates] == ["claim_default"]
    assert [item["claim_id"] for item in kb_b_candidates] == ["claim_kb_b"]


def test_review_service_should_filter_review_history_by_knowledge_base(tmp_path: Path) -> None:
    """人工审核历史分页列表也应按知识库隔离。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    _insert_knowledge_base(database_path, "kb_b", "知识库B")
    repository = QualityRepository(database_path)
    service = ReviewService(database_path)

    _create_quality_result(
        repository,
        check_id="chk_default",
        knowledge_base_id="default",
        claim_id="claim_default",
        created_at="2026-05-03T00:00:00+00:00",
    )
    _create_quality_result(
        repository,
        check_id="chk_kb_b",
        knowledge_base_id="kb_b",
        claim_id="claim_kb_b",
        created_at="2026-05-03T01:00:00+00:00",
    )
    repository.insert_review_record(
        {
            "review_id": "rev_default",
            "claim_id": "claim_default",
            "review_action": "approved",
            "reviewed_verdict": "verified",
            "review_note": "ok",
            "reviewer": "tester",
            "created_at": "2026-05-03T02:00:00+00:00",
        }
    )
    repository.insert_review_record(
        {
            "review_id": "rev_kb_b",
            "claim_id": "claim_kb_b",
            "review_action": "rejected",
            "reviewed_verdict": "rejected",
            "review_note": "not ok",
            "reviewer": "tester",
            "created_at": "2026-05-03T03:00:00+00:00",
        }
    )

    default_reviews, default_total = service.list_reviews(page=1, page_size=10, knowledge_base_id="default")
    kb_b_reviews, kb_b_total = service.list_reviews(page=1, page_size=10, knowledge_base_id="kb_b")

    assert default_total == 1
    assert kb_b_total == 1
    assert [item["review_id"] for item in default_reviews] == ["rev_default"]
    assert [item["review_id"] for item in kb_b_reviews] == ["rev_kb_b"]
