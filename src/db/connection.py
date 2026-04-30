"""程序说明：封装 SQLite 连接创建与初始化逻辑。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.db.schema import SCHEMA_SQL


DOCUMENT_METADATA_COLUMNS = {
    "author": "TEXT",
    "source_name": "TEXT",
    "tags_json": "TEXT",
}

QUALITY_CLAIM_COLUMNS = {
    "risk_level": "TEXT NOT NULL DEFAULT 'medium'",
}

QUALITY_CHECK_COLUMNS = {
    "template_id": "TEXT",
    "template_name": "TEXT",
}


def create_connection(database_path: Path) -> sqlite3.Connection:
    """创建 SQLite 连接，并启用行字典访问。"""

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def initialize_database(database_path: Path) -> None:
    """初始化数据库结构。"""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    with create_connection(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
        _ensure_document_columns(connection)
        _ensure_quality_check_columns(connection)
        _ensure_quality_claim_columns(connection)


def _ensure_document_columns(connection: sqlite3.Connection) -> None:
    """为历史数据库补齐新增的文档元数据列。"""

    rows = connection.execute("PRAGMA table_info(documents)").fetchall()
    existing_columns = {row["name"] for row in rows}
    for column_name, column_type in DOCUMENT_METADATA_COLUMNS.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE documents ADD COLUMN {column_name} {column_type}")


def _ensure_quality_check_columns(connection: sqlite3.Connection) -> None:
    """为历史数据库补齐新增的质检主表字段。"""

    rows = connection.execute("PRAGMA table_info(quality_checks)").fetchall()
    if not rows:
        return

    existing_columns = {row["name"] for row in rows}
    for column_name, column_type in QUALITY_CHECK_COLUMNS.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE quality_checks ADD COLUMN {column_name} {column_type}")


def _ensure_quality_claim_columns(connection: sqlite3.Connection) -> None:
    """为历史数据库补齐新增的质检 claim 字段。"""

    rows = connection.execute("PRAGMA table_info(quality_claims)").fetchall()
    if not rows:
        return

    existing_columns = {row["name"] for row in rows}
    for column_name, column_type in QUALITY_CLAIM_COLUMNS.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE quality_claims ADD COLUMN {column_name} {column_type}")
