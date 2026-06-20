"""程序说明：封装 SQLite 连接创建与初始化逻辑。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.auth.service import normalize_auth_tab_name
from src.db.schema import SCHEMA_SQL


DOCUMENT_METADATA_COLUMNS = {
    "knowledge_base_id": "TEXT NOT NULL DEFAULT 'default'",
    "author": "TEXT",
    "source_name": "TEXT",
    "tags_json": "TEXT",
}

QUALITY_CLAIM_COLUMNS = {
    "risk_level": "TEXT NOT NULL DEFAULT 'medium'",
    "evidence_details_json": "TEXT NOT NULL DEFAULT '[]'",
}

QUALITY_CHECK_COLUMNS = {
    "knowledge_base_id": "TEXT NOT NULL DEFAULT 'default'",
    "template_id": "TEXT",
    "template_name": "TEXT",
}

SECTION_TRACEABILITY_COLUMNS = {
    "heading_path": "TEXT",
    "source_start_line": "INTEGER",
    "source_end_line": "INTEGER",
    "source_anchor": "TEXT",
}

CHUNK_TRACEABILITY_COLUMNS = {
    "heading_path": "TEXT",
    "source_start_line": "INTEGER",
    "source_end_line": "INTEGER",
    "page_no": "INTEGER",
    "chunk_type": "TEXT NOT NULL DEFAULT 'paragraph'",
    "content_hash": "TEXT",
    "source_anchor": "TEXT",
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
        _ensure_auth_tables(connection)
        _ensure_user_permissions_table(connection)
        # 兼容旧库：先补齐会被 schema 中索引立即引用的关键列，避免 executescript 提前失败。
        _preflight_legacy_columns(connection)
        connection.executescript(SCHEMA_SQL)
        _ensure_default_knowledge_base(connection)
        _ensure_document_columns(connection)
        _ensure_section_traceability_columns(connection)
        _ensure_chunk_traceability_columns(connection)
        _ensure_quality_check_columns(connection)
        _ensure_quality_claim_columns(connection)
        _ensure_review_record_foreign_key(connection)
        _backfill_knowledge_base_columns(connection)
        _ensure_default_admin(connection)


def _ensure_auth_tables(connection: sqlite3.Connection) -> None:
    """补齐认证与授权相关表，确保登录页可直接使用。"""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_tab_access (
            user_id TEXT NOT NULL,
            tab_name TEXT NOT NULL,
            PRIMARY KEY (user_id, tab_name),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_kb_access (
            user_id TEXT NOT NULL,
            knowledge_base_id TEXT NOT NULL,
            PRIMARY KEY (user_id, knowledge_base_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_permissions (
            user_id TEXT PRIMARY KEY,
            permissions_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """
    )


def _ensure_user_permissions_table(connection: sqlite3.Connection) -> None:
    """将历史 user_permissions 表升级为新结构，并迁移旧权限数据。"""

    rows = connection.execute("PRAGMA table_info(user_permissions)").fetchall()
    if not rows:
        return

    existing_columns = {str(row["name"]).strip() for row in rows}
    if "permissions_json" in existing_columns and "updated_at" in existing_columns:
        return

    legacy_rows = [
        dict(row)
        for row in connection.execute("SELECT * FROM user_permissions").fetchall()
    ]
    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for row in legacy_rows:
        user_id = str(row.get("user_id") or "").strip()
        if not user_id:
            continue

        user_exists = connection.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not user_exists:
            continue

        for tab_name in _load_legacy_permission_list(row.get("tab_names")):
            normalized_tab_name = normalize_auth_tab_name(tab_name)
            if not normalized_tab_name:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO user_tab_access (user_id, tab_name)
                VALUES (?, ?)
                """,
                (user_id, normalized_tab_name),
            )

        for knowledge_base_id in _load_legacy_permission_list(row.get("kb_ids")):
            normalized_knowledge_base_id = str(knowledge_base_id or "").strip()
            if not normalized_knowledge_base_id:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO user_kb_access (user_id, knowledge_base_id)
                VALUES (?, ?)
                """,
                (user_id, normalized_knowledge_base_id),
            )

    connection.executescript(
        """
        CREATE TABLE user_permissions__new (
            user_id TEXT PRIMARY KEY,
            permissions_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );

        DROP TABLE user_permissions;
        ALTER TABLE user_permissions__new RENAME TO user_permissions;
        """
    )

    for row in legacy_rows:
        user_id = str(row.get("user_id") or "").strip()
        if not user_id:
            continue
        user_exists = connection.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not user_exists:
            continue
        connection.execute(
            """
            INSERT OR IGNORE INTO user_permissions (user_id, permissions_json, updated_at)
            VALUES (?, '{}', ?)
            """,
            (user_id, updated_at),
        )


def _preflight_legacy_columns(connection: sqlite3.Connection) -> None:
    """在执行完整 schema 前，先为旧表补齐关键列。"""

    _ensure_table_columns(connection, "documents", {"knowledge_base_id": DOCUMENT_METADATA_COLUMNS["knowledge_base_id"]})
    _ensure_table_columns(connection, "quality_checks", {"knowledge_base_id": QUALITY_CHECK_COLUMNS["knowledge_base_id"]})


def _ensure_default_knowledge_base(connection: sqlite3.Connection) -> None:
    """确保默认知识库存在，兼容历史单知识库数据。"""

    connection.execute(
        """
        INSERT INTO knowledge_bases (
            knowledge_base_id, knowledge_base_name, description, status, is_default, created_at, updated_at
        )
        SELECT 'default', '默认知识库', '历史数据兼容用默认知识库', 'active', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1 FROM knowledge_bases WHERE knowledge_base_id = 'default'
        )
        """
    )


def _ensure_document_columns(connection: sqlite3.Connection) -> None:
    """为历史数据库补齐新增的文档元数据列。"""

    _ensure_table_columns(connection, "documents", DOCUMENT_METADATA_COLUMNS)


def _ensure_section_traceability_columns(connection: sqlite3.Connection) -> None:
    """为历史章节表补齐出处追溯字段。"""

    _ensure_table_columns(connection, "document_sections", SECTION_TRACEABILITY_COLUMNS)


def _ensure_chunk_traceability_columns(connection: sqlite3.Connection) -> None:
    """为历史分块表补齐出处追溯字段。"""

    _ensure_table_columns(connection, "chunks", CHUNK_TRACEABILITY_COLUMNS)


def _ensure_quality_check_columns(connection: sqlite3.Connection) -> None:
    """为历史数据库补齐新增的质检主表字段。"""

    _ensure_table_columns(connection, "quality_checks", QUALITY_CHECK_COLUMNS)


def _ensure_quality_claim_columns(connection: sqlite3.Connection) -> None:
    """为历史数据库补齐新增的质检 claim 字段。"""

    _ensure_table_columns(connection, "quality_claims", QUALITY_CLAIM_COLUMNS)


def _ensure_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
    column_definitions: dict[str, str],
) -> None:
    """为指定表补齐缺失列；若表不存在则跳过。"""

    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    if not rows:
        return

    existing_columns = {row["name"] for row in rows}
    for column_name, column_type in column_definitions.items():
        if column_name in existing_columns:
            continue
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _load_legacy_permission_list(raw_value: object) -> list[str]:
    """解析旧权限表中的 JSON 数组文本，兼容空值和脏数据。"""

    text = str(raw_value or "").strip()
    if not text:
        return []
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def _backfill_knowledge_base_columns(connection: sqlite3.Connection) -> None:
    """为历史数据回填默认知识库归属。"""

    connection.execute(
        """
        UPDATE documents
        SET knowledge_base_id = 'default'
        WHERE knowledge_base_id IS NULL OR TRIM(knowledge_base_id) = ''
        """
    )


def _ensure_default_admin(connection: sqlite3.Connection) -> None:
    """确保存在默认 admin 用户（用户名/密码均为 admin），并开通全部权限。"""

    import hashlib
    import os
    import time
    import uuid

    row = connection.execute("SELECT user_id, is_admin FROM users WHERE username = ?", ("admin",)).fetchone()
    if row:
        # admin 已存在，确保是管理员且拥有全部权限
        user_id = row[0]
        connection.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
    else:
        # admin 不存在，创建之
        user_id = str(uuid.uuid4())
        salt = os.urandom(16).hex()
        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            b"admin",
            salt.encode("utf-8"),
            390000,
        ).hex()
        password_hash = f"pbkdf2_sha256$390000${salt}${password_hash}"
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")

        connection.execute(
            "INSERT INTO users (user_id, username, password_hash, is_active, is_admin, created_at, updated_at) VALUES (?, ?, ?, 1, 1, ?, ?)",
            (user_id, "admin", password_hash, created_at, created_at)
        )

    # 确保 admin 拥有所有 tab 和知识库的访问权限
    user_id_row = connection.execute("SELECT user_id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not user_id_row:
        return
    user_id = user_id_row[0]

    # 赋予所有 tab 权限
    tab_names = [
        "AI 质检",
        "人工审核",
        "知识库管理",
        "知识库检索",
        "PageIndex 深度检索",
        "功能设置",
    ]
    for tab_name in tab_names:
        connection.execute(
            "INSERT OR IGNORE INTO user_tab_access (user_id, tab_name) VALUES (?, ?)",
            (user_id, tab_name)
        )

    # 赋予所有知识库权限
    kb_rows = connection.execute("SELECT knowledge_base_id FROM knowledge_bases").fetchall()
    for kb_row in kb_rows:
        connection.execute(
            "INSERT OR IGNORE INTO user_kb_access (user_id, knowledge_base_id) VALUES (?, ?)",
            (user_id, kb_row[0])
        )

    # 确保 user_permissions 标记存在
    updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    connection.execute(
        """
        INSERT INTO user_permissions (user_id, permissions_json, updated_at)
        VALUES (?, '{}', ?)
        ON CONFLICT(user_id) DO UPDATE SET
            permissions_json = excluded.permissions_json,
            updated_at = excluded.updated_at
        """,
        (user_id, updated_at),
    )

    connection.commit()


def _ensure_review_record_foreign_key(connection: sqlite3.Connection) -> None:
    """将审核记录表升级为带 claim 级联外键的结构。"""

    table_rows = connection.execute("PRAGMA table_info(review_records)").fetchall()
    if not table_rows:
        return

    foreign_keys = connection.execute("PRAGMA foreign_key_list(review_records)").fetchall()
    has_claim_foreign_key = any(
        str(row["from"]).strip() == "claim_id" and str(row["table"]).strip() == "quality_claims"
        for row in foreign_keys
    )
    if has_claim_foreign_key:
        return

    connection.executescript(
        """
        CREATE TABLE review_records__new (
            review_id TEXT PRIMARY KEY,
            claim_id TEXT NOT NULL,
            review_action TEXT NOT NULL,
            reviewed_verdict TEXT,
            review_note TEXT,
            reviewer TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (claim_id) REFERENCES quality_claims (claim_id) ON DELETE CASCADE
        );

        INSERT INTO review_records__new (
            review_id, claim_id, review_action, reviewed_verdict, review_note, reviewer, created_at
        )
        SELECT
            rr.review_id,
            rr.claim_id,
            rr.review_action,
            rr.reviewed_verdict,
            rr.review_note,
            rr.reviewer,
            rr.created_at
        FROM review_records rr
        JOIN quality_claims qc ON qc.claim_id = rr.claim_id;

        DROP TABLE review_records;
        ALTER TABLE review_records__new RENAME TO review_records;
        """
    )
    connection.execute(
        """
        UPDATE quality_checks
        SET knowledge_base_id = 'default'
        WHERE knowledge_base_id IS NULL OR TRIM(knowledge_base_id) = ''
        """
    )
