"""程序说明：验证检索索引重建的只读预检、失败门禁、发布与恢复。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.db.connection import initialize_database
from src.db.transaction import transaction
from src.retrieval.rebuild import RetrievalIndexRebuilder


class _FileBackedVectorStore:
    """测试替身：用标记文件模拟可切换的 Chroma 目录。"""

    def __init__(self, persist_directory: Path, sqlite_db_path: Path) -> None:
        self.persist_directory = Path(persist_directory)
        self.sqlite_db_path = Path(sqlite_db_path)

    def rebuild_from_sqlite(self) -> tuple[int, int]:
        """按 SQLite chunk 数生成测试向量目录。"""

        import sqlite3

        with sqlite3.connect(self.sqlite_db_path) as connection:
            chunk_count = int(connection.execute("SELECT COUNT(1) FROM chunks").fetchone()[0])
        self.persist_directory.mkdir(parents=True, exist_ok=False)
        (self.persist_directory / "state.txt").write_text(
            f"staging:{chunk_count}", encoding="utf-8"
        )
        return (1 if chunk_count else 0, chunk_count)

    def inspect_index(self) -> dict:
        """返回与当前 SQLite 对齐的测试元数据。"""

        import sqlite3

        with sqlite3.connect(self.sqlite_db_path) as connection:
            chunk_count = int(connection.execute("SELECT COUNT(1) FROM chunks").fetchone()[0])
        return {
            "total_count": chunk_count,
            "by_knowledge_base": {"default": chunk_count} if chunk_count else {},
            "by_document": {"doc_1": chunk_count} if chunk_count else {},
            "missing_metadata_count": 0,
            "embedding_models": ["deterministic-v1"] if chunk_count else [],
            "embedding_dimensions": [64] if chunk_count else [],
            "index_versions": ["retrieval-v2"] if chunk_count else [],
        }

    def close(self) -> None:
        """文件替身无需释放资源。"""


class _ClosableFileBackedVectorStore(_FileBackedVectorStore):
    """记录重建器是否在目录切换前释放向量客户端。"""

    def __init__(self, persist_directory: Path, sqlite_db_path: Path) -> None:
        super().__init__(persist_directory, sqlite_db_path)
        self.closed = False

    def close(self) -> None:
        """记录关闭动作。"""

        self.closed = True


def _hash_path(path: Path) -> str:
    """计算文件或目录的稳定内容哈希。"""

    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update(child.read_bytes())
    return digest.hexdigest()


def _active_snapshot(database_path: Path, chroma_path: Path) -> tuple[str, str]:
    """记录活动 FTS 逻辑内容和向量目录哈希。"""

    import sqlite3

    digest = hashlib.sha256()
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT chunk_id, doc_uid, content FROM chunk_fts ORDER BY chunk_id"
        ).fetchall()
    digest.update(repr(rows).encode("utf-8"))
    return digest.hexdigest(), _hash_path(chroma_path)


def _file_snapshot(database_path: Path, chroma_path: Path) -> tuple[str, str]:
    """记录活动文件字节，用于严格验证 dry-run 零修改。"""

    return _hash_path(database_path), _hash_path(chroma_path)


@pytest.fixture
def rebuilder(tmp_path: Path) -> RetrievalIndexRebuilder:
    """创建带一条有效 chunk 的隔离重建环境。"""

    database_path = tmp_path / "index" / "app.db"
    chroma_path = tmp_path / "index" / "chroma"
    initialize_database(database_path)
    with transaction(database_path) as connection:
        connection.execute(
            """
            INSERT INTO documents(
                doc_uid, knowledge_base_id, doc_id, doc_title, source_path, source_hash,
                ingest_status, index_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc_1", "default", "doc-1", "测试文档", "input/test.md", "hash-1",
                "completed", "indexed", "2026-07-16T00:00:00Z", "2026-07-16T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO chunks(
                chunk_id, doc_uid, chunk_index, content, token_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "chunk_1", "doc_1", 0, "阿胶质量检测", 6,
                "2026-07-16T00:00:00Z", "2026-07-16T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO chunk_fts(chunk_id, doc_uid, content) VALUES (?, ?, ?)",
            ("chunk_1", "doc_1", "旧索引内容"),
        )
    chroma_path.mkdir(parents=True)
    (chroma_path / "state.txt").write_text("active-old", encoding="utf-8")

    return RetrievalIndexRebuilder(
        database_path=database_path,
        chroma_path=chroma_path,
        backup_root=tmp_path / "index" / "backups" / "retrieval",
        manifest_path=tmp_path / "index" / "index_manifest.json",
        vector_store_factory=_FileBackedVectorStore,
        embedding_provider="local",
        embedding_model="deterministic-v1",
        index_version="retrieval-v2",
    )


def test_rebuild_dry_run_should_not_modify_database_or_chroma(
    rebuilder: RetrievalIndexRebuilder,
) -> None:
    """未提供 apply 时只能返回预检结果。"""

    before = _file_snapshot(rebuilder.database_path, rebuilder.chroma_path)
    result = rebuilder.rebuild(apply=False)

    assert result["status"] == "dry_run"
    assert _file_snapshot(rebuilder.database_path, rebuilder.chroma_path) == before


def test_failed_validation_should_keep_active_indexes(
    rebuilder: RetrievalIndexRebuilder,
) -> None:
    """候选索引未通过门禁时不得替换活动 FTS 或 Chroma。"""

    before = _active_snapshot(rebuilder.database_path, rebuilder.chroma_path)
    result = rebuilder.rebuild(apply=True, validator=lambda report: False)

    assert result["published"] is False
    assert result["status"] == "validation_failed"
    assert _active_snapshot(rebuilder.database_path, rebuilder.chroma_path) == before


def test_failed_validation_should_report_cleanup_error_without_masking_gate(
    rebuilder: RetrievalIndexRebuilder,
    monkeypatch,
) -> None:
    """失败影子目录无法归档时，仍应返回原始门禁失败报告。"""

    monkeypatch.setattr(rebuilder, "_retire_failed_staging", lambda: "目录仍被占用")

    result = rebuilder.rebuild(apply=True, validator=lambda report: False)

    assert result["status"] == "validation_failed"
    assert result["published"] is False
    assert result["cleanup_error"] == "目录仍被占用"


def test_rebuild_publish_and_restore_should_return_to_original_indexes(
    rebuilder: RetrievalIndexRebuilder,
) -> None:
    """发布后应能从最近备份恢复原活动索引。"""

    original = _active_snapshot(rebuilder.database_path, rebuilder.chroma_path)
    rebuilt = rebuilder.rebuild(apply=True)

    assert rebuilt["published"] is True
    assert (rebuilder.chroma_path / "state.txt").read_text(encoding="utf-8") == "staging:1"

    restored = rebuilder.restore_latest(apply=True)

    assert restored["restored"] is True
    assert _active_snapshot(rebuilder.database_path, rebuilder.chroma_path) == original


def test_rebuild_should_close_all_vector_stores_before_directory_switch(
    rebuilder: RetrievalIndexRebuilder,
) -> None:
    """构建与校验创建的向量客户端必须在发布前全部关闭。"""

    stores: list[_ClosableFileBackedVectorStore] = []

    def factory(persist_directory: Path, sqlite_db_path: Path) -> _ClosableFileBackedVectorStore:
        store = _ClosableFileBackedVectorStore(persist_directory, sqlite_db_path)
        stores.append(store)
        return store

    rebuilder.vector_store_factory = factory

    result = rebuilder.rebuild(apply=True)

    assert result["published"] is True
    assert len(stores) == 2
    assert all(store.closed for store in stores)
