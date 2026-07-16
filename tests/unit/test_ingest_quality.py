"""程序说明：验证文档入库质检结果的统计与异常提示。"""

import sqlite3
from pathlib import Path

import pytest

from src.common.config import AppSettings
from src.db.connection import create_connection, initialize_database

pytest.importorskip("chromadb")

from src.ingest.service import IngestService


def _build_ingest_service(tmp_path: Path) -> IngestService:
    """程序说明：创建用于入库质检测试的最小服务实例。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)
    return IngestService(settings)


def test_ingest_service_should_pass_embedding_fingerprint_without_auto_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """启动期只校验索引，不得无备份自动重建，并应传递模型指纹。"""

    captured: dict = {}

    class CapturingVectorStore:
        """记录 IngestService 创建向量存储时的关键参数。"""

        def __init__(self, persist_directory, **kwargs) -> None:
            captured.update({"persist_directory": persist_directory, **kwargs})

    monkeypatch.setattr("src.ingest.service.VectorStore", CapturingVectorStore)
    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
        EMBEDDING_MODEL="test-embedding-v2",
    )

    IngestService(settings)

    assert captured["embedding_model"] == "test-embedding-v2"
    assert captured["index_version"] == "retrieval-v2"
    assert captured["auto_repair_dimension_mismatch"] is False


def test_inspect_document_quality_should_report_complete_metrics(tmp_path: Path) -> None:
    """正常入库后，应返回章节、分块、全文索引和向量数量。"""

    service = _build_ingest_service(tmp_path)
    document_path = tmp_path / "Input" / "a1.md"
    document_path.write_text(
        "# 总论\n阿胶为传统中药材，常见于历代本草文献。\n\n## 产地\n东阿一带历史记载较多。\n",
        encoding="utf-8",
    )

    job = service.register_document({"file_path": str(document_path)})
    report = service.inspect_document_quality(job["doc_uid"])

    assert report["document"]["doc_uid"] == job["doc_uid"]
    assert report["metrics"]["section_count"] == 2
    assert report["metrics"]["chunk_count"] >= 2
    assert report["metrics"]["chunk_count"] == report["metrics"]["fts_chunk_count"]
    assert report["metrics"]["chunk_count"] == report["metrics"]["vector_chunk_count"]
    assert report["summary"]["level"] == "success"
    assert report["first_section_title"] == "总论"
    assert report["last_section_title"] == "产地"


def test_initialize_database_should_add_traceability_columns_to_legacy_tables(tmp_path: Path) -> None:
    """旧版章节与分块表初始化后应自动补齐追溯字段。"""

    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE document_sections (
            section_id TEXT PRIMARY KEY,
            doc_uid TEXT NOT NULL,
            section_title TEXT NOT NULL,
            section_level INTEGER NOT NULL,
            source_span TEXT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            doc_uid TEXT NOT NULL,
            section_id TEXT,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            source_span TEXT,
            token_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    connection.close()

    initialize_database(database_path)

    with create_connection(database_path) as upgraded_connection:
        section_columns = {
            row["name"]
            for row in upgraded_connection.execute("PRAGMA table_info(document_sections)").fetchall()
        }
        chunk_columns = {
            row["name"]
            for row in upgraded_connection.execute("PRAGMA table_info(chunks)").fetchall()
        }

    assert {"heading_path", "source_start_line", "source_end_line", "source_anchor"}.issubset(section_columns)
    assert {
        "heading_path",
        "source_start_line",
        "source_end_line",
        "page_no",
        "chunk_type",
        "content_hash",
        "source_anchor",
    }.issubset(chunk_columns)


def test_register_document_should_store_traceability_metadata(tmp_path: Path) -> None:
    """Markdown 入库应为章节和 chunk 写入标题路径、行号、类型与内容 hash。"""

    service = _build_ingest_service(tmp_path)
    document_path = tmp_path / "Input" / "trace.md"
    document_path.write_text(
        "# 总论\n第一段。\n\n## 表格\n| 项目 | 说明 |\n|---|---|\n| 阿胶 | 说明 |\n",
        encoding="utf-8",
    )

    job = service.register_document({"file_path": str(document_path)})

    with create_connection(service.settings.sqlite_db_path) as connection:
        section_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT section_title, heading_path, source_start_line, source_end_line, source_anchor
                FROM document_sections
                WHERE doc_uid = ?
                ORDER BY source_start_line ASC
                """,
                (job["doc_uid"],),
            ).fetchall()
        ]
        table_chunk = dict(
            connection.execute(
                """
                SELECT heading_path, source_start_line, source_end_line, chunk_type, content_hash, source_anchor, content
                FROM chunks
                WHERE doc_uid = ? AND content LIKE ?
                """,
                (job["doc_uid"], "%| 项目 | 说明 |%"),
            ).fetchone()
        )

    assert section_rows[0]["heading_path"] == "总论"
    assert section_rows[0]["source_start_line"] == 1
    assert section_rows[0]["source_end_line"] == 3
    assert section_rows[0]["source_anchor"] == "L1-L3"
    assert section_rows[1]["heading_path"] == "总论 > 表格"
    assert section_rows[1]["source_start_line"] == 4
    assert section_rows[1]["source_end_line"] == 7
    assert table_chunk["heading_path"] == "总论 > 表格"
    assert table_chunk["source_start_line"] == 4
    assert table_chunk["source_end_line"] == 7
    assert table_chunk["chunk_type"] == "table"
    assert len(table_chunk["content_hash"]) == 64
    assert table_chunk["source_anchor"] == "L4-L7"


def test_inspect_document_quality_should_warn_when_index_counts_mismatch(tmp_path: Path) -> None:
    """当全文索引或向量数量缺失时，应给出风险提示。"""

    service = _build_ingest_service(tmp_path)
    document_path = tmp_path / "Input" / "a2.md"
    document_path.write_text(
        "# 总论\n阿胶入药历史悠久。\n\n## 典籍\n《本草纲目》中有相关记载。\n",
        encoding="utf-8",
    )

    job = service.register_document({"file_path": str(document_path)})
    doc_uid = job["doc_uid"]
    service.vector_store.delete_by_doc_uid(doc_uid)
    with create_connection(service.settings.sqlite_db_path) as connection:
        connection.execute(
            """
            DELETE FROM chunk_fts
            WHERE chunk_id IN (
                SELECT chunk_id FROM chunks WHERE doc_uid = ? ORDER BY chunk_index ASC LIMIT 1
            )
            """,
            (doc_uid,),
        )
        connection.commit()

    report = service.inspect_document_quality(doc_uid)
    issue_messages = [item["message"] for item in report["issues"]]

    assert report["summary"]["level"] == "warning"
    assert any("全文索引条数" in message for message in issue_messages)
    assert any("向量索引条数" in message for message in issue_messages)


def test_document_quality_config_should_be_persisted_and_affect_report(tmp_path: Path) -> None:
    """保存阈值配置后，后续质检应使用新阈值。"""

    service = _build_ingest_service(tmp_path)
    document_path = tmp_path / "Input" / "a3.md"
    document_path.write_text(
        "# 长文\n" + ("阿胶文献内容。 " * 220),
        encoding="utf-8",
    )

    saved_config = service.save_document_quality_config(
        {
            "sample_limit": 2,
            "long_document_char_threshold": 300,
            "min_sections_for_long_doc": 3,
            "max_avg_chunks_per_section": 20,
            "max_chunk_chars": 900,
            "short_chunk_chars": 10,
            "short_chunk_warn_min_chunk_count": 2,
        }
    )
    job = service.register_document({"file_path": str(document_path)})
    report = service.inspect_document_quality(job["doc_uid"])

    assert saved_config["sample_limit"] == 2
    assert report["applied_thresholds"]["min_sections_for_long_doc"] == 3
    assert any("章节数偏少" in item["message"] for item in report["issues"])
    assert len(report["section_samples"]) <= 2


def test_export_document_quality_reports_csv_should_write_bom_csv(tmp_path: Path) -> None:
    """批量质检导出应生成 UTF-8 BOM CSV 文件。"""

    service = _build_ingest_service(tmp_path)
    first_document = tmp_path / "Input" / "a4.md"
    second_document = tmp_path / "Input" / "a5.md"
    first_document.write_text("# 文档一\n阿胶内容一。", encoding="utf-8")
    second_document.write_text("# 文档二\n阿胶内容二。", encoding="utf-8")

    service.register_document({"file_path": str(first_document)})
    service.register_document({"file_path": str(second_document)})
    export_result = service.export_document_quality_reports_csv()
    export_path = Path(export_result["file_path"])
    raw_bytes = export_path.read_bytes()
    csv_text = export_path.read_text(encoding="utf-8-sig")

    assert export_result["row_count"] == 2
    assert export_path.exists()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")
    assert "doc_uid,doc_title,ingest_status,index_status" in csv_text
