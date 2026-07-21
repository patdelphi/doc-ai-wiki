"""程序说明：集中管理 PageIndex 自有表、索引记录与问答历史的 SQLite 持久化。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src.common.errors import DatabaseAppError
from src.db.connection import create_connection
from src.db.transaction import transaction


@contextmanager
def _translate_database_error(message: str) -> Iterator[None]:
    """将 SQLite 异常统一转换为带原因的应用错误。"""

    try:
        yield
    except sqlite3.DatabaseError as exc:
        raise DatabaseAppError(message, details={"reason": str(exc)}) from exc


class PageIndexRepository:
    """PageIndex 元数据与问答历史访问对象。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize_schema(self) -> None:
        """创建 PageIndex 自有表，并补齐现有历史兼容列。"""

        with _translate_database_error("初始化 PageIndex 元数据表失败"):
            with transaction(self.database_path) as connection:
                connection.executescript(
                    """
                CREATE TABLE IF NOT EXISTS pageindex_indexes (
                    knowledge_base_id TEXT NOT NULL,
                    doc_uid TEXT NOT NULL,
                    pageindex_doc_id TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (knowledge_base_id, doc_uid),
                    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases (knowledge_base_id),
                    FOREIGN KEY (doc_uid) REFERENCES documents (doc_uid) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_pageindex_indexes_kb
                    ON pageindex_indexes (knowledge_base_id);

                CREATE TABLE IF NOT EXISTS pageindex_query_history (
                    query_id TEXT PRIMARY KEY,
                    knowledge_base_id TEXT NOT NULL,
                    doc_uid TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    debug_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (knowledge_base_id, doc_uid)
                        REFERENCES pageindex_indexes (knowledge_base_id, doc_uid)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_pageindex_query_history_scope
                    ON pageindex_query_history (knowledge_base_id, doc_uid, created_at);
                    """
                )
                self._ensure_history_debug_column(connection)

    @staticmethod
    def _ensure_history_debug_column(connection: sqlite3.Connection) -> None:
        """兼容旧数据库，为 PageIndex 历史表补齐 debug_json 字段。"""

        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(pageindex_query_history)").fetchall()
        }
        if "debug_json" not in columns:
            connection.execute("ALTER TABLE pageindex_query_history ADD COLUMN debug_json TEXT NOT NULL DEFAULT '{}'")

    def upsert_index_record(
        self,
        *,
        knowledge_base_id: str,
        doc_uid: str,
        pageindex_doc_id: str,
        workspace_path: str,
        source_hash: str,
        created_at: str,
        updated_at: str,
    ) -> None:
        """写入或更新一条 PageIndex 索引记录。"""

        with _translate_database_error("写入 PageIndex 索引记录失败"):
            with transaction(self.database_path) as connection:
                connection.execute(
                    """
                INSERT INTO pageindex_indexes (
                    knowledge_base_id,
                    doc_uid,
                    pageindex_doc_id,
                    workspace_path,
                    source_hash,
                    status,
                    error_message,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'ready', NULL, ?, ?)
                ON CONFLICT(knowledge_base_id, doc_uid) DO UPDATE SET
                    pageindex_doc_id = excluded.pageindex_doc_id,
                    workspace_path = excluded.workspace_path,
                    source_hash = excluded.source_hash,
                    status = excluded.status,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                    """,
                    (
                        knowledge_base_id,
                        doc_uid,
                        pageindex_doc_id,
                        workspace_path,
                        source_hash,
                        created_at,
                        updated_at,
                    ),
                )

    def get_index_record(self, knowledge_base_id: str, doc_uid: str) -> dict | None:
        """读取知识库与文档范围内的一条 PageIndex 索引记录。"""

        with _translate_database_error("读取 PageIndex 索引记录失败"):
            with create_connection(self.database_path) as connection:
                row = connection.execute(
                    """
                SELECT
                    p.knowledge_base_id,
                    p.doc_uid,
                    p.pageindex_doc_id,
                    p.workspace_path,
                    p.source_hash,
                    p.status,
                    d.source_hash AS current_source_hash
                FROM pageindex_indexes p
                JOIN documents d ON d.doc_uid = p.doc_uid
                WHERE p.knowledge_base_id = ? AND p.doc_uid = ?
                    """,
                    (knowledge_base_id, doc_uid),
                ).fetchone()
        return dict(row) if row else None

    def list_index_records(self, knowledge_base_id: str) -> list[dict]:
        """读取知识库范围内的全部 PageIndex 索引记录。"""

        with _translate_database_error("读取 PageIndex 索引记录失败"):
            with create_connection(self.database_path) as connection:
                rows = connection.execute(
                    """
                SELECT
                    p.knowledge_base_id,
                    p.doc_uid,
                    p.pageindex_doc_id,
                    p.workspace_path,
                    p.source_hash,
                    p.status,
                    d.doc_title,
                    d.source_path,
                    d.source_hash AS current_source_hash
                FROM pageindex_indexes p
                JOIN documents d ON d.doc_uid = p.doc_uid
                WHERE p.knowledge_base_id = ?
                ORDER BY p.updated_at DESC, p.doc_uid COLLATE NOCASE
                    """,
                    (knowledge_base_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def insert_query_history(
        self,
        *,
        query_id: str,
        knowledge_base_id: str,
        doc_uid: str,
        question: str,
        answer: str,
        evidence_json: str,
        debug_json: str,
        created_at: str,
    ) -> None:
        """写入一条 PageIndex 问答历史。"""

        with _translate_database_error("写入 PageIndex 问答历史失败"):
            with transaction(self.database_path) as connection:
                connection.execute(
                    """
                INSERT INTO pageindex_query_history (
                    query_id,
                    knowledge_base_id,
                    doc_uid,
                    question,
                    answer,
                    evidence_json,
                    debug_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        query_id,
                        knowledge_base_id,
                        doc_uid,
                        question,
                        answer,
                        evidence_json,
                        debug_json,
                        created_at,
                    ),
                )

    def list_query_history(self, knowledge_base_id: str, doc_uid: str, limit: int) -> list[dict]:
        """读取知识库与文档范围内的 PageIndex 问答历史。"""

        with _translate_database_error("读取 PageIndex 历史失败"):
            with create_connection(self.database_path) as connection:
                rows = connection.execute(
                    """
                SELECT query_id, knowledge_base_id, doc_uid, question, answer, evidence_json, debug_json, created_at
                FROM pageindex_query_history
                WHERE knowledge_base_id = ? AND doc_uid = ?
                ORDER BY created_at DESC
                LIMIT ?
                    """,
                    (knowledge_base_id, doc_uid, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def list_knowledge_base_query_history(self, knowledge_base_id: str, limit: int) -> list[dict]:
        """读取知识库范围内的 PageIndex 问答历史。"""

        with _translate_database_error("读取 PageIndex 历史失败"):
            with create_connection(self.database_path) as connection:
                rows = connection.execute(
                    """
                SELECT query_id, knowledge_base_id, doc_uid, question, answer, evidence_json, debug_json, created_at
                FROM pageindex_query_history
                WHERE knowledge_base_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                    """,
                    (knowledge_base_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_query_history_record(self, knowledge_base_id: str, doc_uid: str, query_id: str) -> dict | None:
        """读取知识库与文档范围内的一条 PageIndex 问答历史。"""

        with _translate_database_error("读取 PageIndex 历史记录失败"):
            with create_connection(self.database_path) as connection:
                row = connection.execute(
                    """
                SELECT query_id, knowledge_base_id, doc_uid, question, answer, evidence_json, debug_json, created_at
                FROM pageindex_query_history
                WHERE knowledge_base_id = ? AND doc_uid = ? AND query_id = ?
                    """,
                    (knowledge_base_id, doc_uid, query_id),
                ).fetchone()
        return dict(row) if row else None

    def get_knowledge_base_query_history_record(self, knowledge_base_id: str, query_id: str) -> dict | None:
        """读取知识库范围内的一条 PageIndex 问答历史。"""

        with _translate_database_error("读取 PageIndex 历史记录失败"):
            with create_connection(self.database_path) as connection:
                row = connection.execute(
                    """
                SELECT query_id, knowledge_base_id, doc_uid, question, answer, evidence_json, debug_json, created_at
                FROM pageindex_query_history
                WHERE knowledge_base_id = ? AND query_id = ?
                    """,
                    (knowledge_base_id, query_id),
                ).fetchone()
        return dict(row) if row else None

