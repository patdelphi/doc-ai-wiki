"""程序说明：封装 SQLite 连接创建与初始化逻辑。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.db.schema import SCHEMA_SQL


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
