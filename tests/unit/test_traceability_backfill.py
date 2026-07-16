"""程序说明：验证历史文档追溯字段回填的预检与事务写入。"""

from pathlib import Path

from src.db.connection import create_connection, initialize_database
from src.metadata.traceability import backfill_traceability


def test_backfill_traceability_should_preserve_ids_and_update_sections_and_chunks(tmp_path: Path) -> None:
    """回填应按 source_span 关联，不改变章节和 chunk 标识。"""

    input_root = tmp_path / "Input"
    source_path = input_root / "default" / "sample.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("# 根标题\n\n正文一\n\n## 子标题\n\n正文二\n", encoding="utf-8")
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    with create_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                doc_uid, knowledge_base_id, doc_id, doc_title, source_path, source_hash,
                ingest_status, index_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("doc_1", "default", "doc_1", "样例", "default/sample.md", "hash", "completed", "indexed", "now", "now"),
        )
        for index in (1, 2):
            connection.execute(
                """
                INSERT INTO document_sections (
                    section_id, doc_uid, section_title, section_level, source_span, content,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"sec_{index}", "doc_1", f"标题{index}", 1, f"section-{index}", f"正文{index}", "now", "now"),
            )
            connection.execute(
                """
                INSERT INTO chunks (
                    chunk_id, doc_uid, section_id, chunk_index, content, source_span,
                    chunk_type, token_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"chunk_{index}", "doc_1", f"sec_{index}", index - 1, f"正文{index}", f"section-{index}:chunk-{index - 1}", "paragraph", 3, "now", "now"),
            )

    preview = backfill_traceability(database_path, input_root, apply=False)
    assert preview["success"] is True
    assert preview["section_update_count"] == 2
    with create_connection(database_path) as connection:
        assert connection.execute("SELECT heading_path FROM chunks WHERE chunk_id = 'chunk_1'").fetchone()[0] is None

    result = backfill_traceability(database_path, input_root, apply=True)

    assert result["success"] is True
    assert result["chunk_update_count"] == 2
    with create_connection(database_path) as connection:
        row = connection.execute(
            "SELECT chunk_id, heading_path, source_start_line, source_anchor FROM chunks WHERE chunk_id = 'chunk_2'"
        ).fetchone()
    assert tuple(row) == ("chunk_2", "根标题 > 子标题", 5, "L5-L7")
