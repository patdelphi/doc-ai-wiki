"""程序说明：验证检索索引模型指纹与 SQLite/Chroma 一致性报告。"""

from __future__ import annotations

from pathlib import Path

from src.db.connection import create_connection, initialize_database
from src.retrieval.index_state import build_retrieval_index_report, write_index_manifest


class InspectableVectorStore:
    """测试用向量存储，仅返回预设的索引检查结果。"""

    def __init__(self, *, total_count: int, missing_metadata_count: int = 0) -> None:
        self.total_count = total_count
        self.missing_metadata_count = missing_metadata_count

    def inspect_index(self) -> dict:
        return {
            "total_count": self.total_count,
            "by_knowledge_base": {"default": self.total_count},
            "by_document": {"doc_1": self.total_count},
            "missing_metadata_count": self.missing_metadata_count,
            "embedding_models": ["test-embedding-v2"],
            "embedding_dimensions": [8],
            "index_versions": ["retrieval-v2"],
        }


def _seed_single_chunk(database_path: Path) -> None:
    """写入一篇文档和一个有效 chunk。"""

    initialize_database(database_path)
    now = "2026-07-16T00:00:00+00:00"
    with create_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                doc_uid, knowledge_base_id, doc_id, doc_title, source_path, source_hash,
                ingest_status, index_status, created_at, updated_at
            ) VALUES ('doc_1', 'default', 'doc_1', '测试文档', 'default/doc.md', 'hash',
                      'completed', 'indexed', ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, doc_uid, chunk_index, content, token_count, created_at, updated_at
            ) VALUES ('chunk_1', 'doc_1', 0, '质量检测内容', 6, ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            "INSERT INTO chunk_fts (chunk_id, doc_uid, content) VALUES ('chunk_1', 'doc_1', '质量检测内容')"
        )
        connection.commit()


def test_index_report_should_be_consistent_when_counts_and_fingerprint_match(tmp_path: Path) -> None:
    """数量、模型、维度和版本一致时，报告应通过。"""

    database_path = tmp_path / "app.db"
    _seed_single_chunk(database_path)

    report = build_retrieval_index_report(
        database_path,
        InspectableVectorStore(total_count=1),
        embedding_provider="local",
        embedding_model="test-embedding-v2",
        index_version="retrieval-v2",
    )

    assert report["sqlite_chunk_count"] == 1
    assert report["vector_count"] == 1
    assert report["fts_tokenizer"] == "trigram"
    assert report["consistent"] is True
    assert report["errors"] == []


def test_index_report_should_fail_when_vector_metadata_is_missing(tmp_path: Path) -> None:
    """向量缺失必填 metadata 时，不得报告索引一致。"""

    database_path = tmp_path / "app.db"
    _seed_single_chunk(database_path)

    report = build_retrieval_index_report(
        database_path,
        InspectableVectorStore(total_count=1, missing_metadata_count=1),
        embedding_provider="local",
        embedding_model="test-embedding-v2",
        index_version="retrieval-v2",
    )

    assert report["consistent"] is False
    assert "missing_vector_metadata" in report["errors"]


def test_write_index_manifest_should_use_utf8_bom_and_replace_atomically(tmp_path: Path) -> None:
    """索引清单应使用 UTF-8 BOM 写入，且不遗留临时文件。"""

    manifest_path = tmp_path / "index_manifest.json"

    write_index_manifest(manifest_path, {"consistent": True, "index_version": "retrieval-v2"})

    assert manifest_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert '"consistent": true' in manifest_path.read_text(encoding="utf-8-sig")
    assert not manifest_path.with_suffix(".json.tmp").exists()
