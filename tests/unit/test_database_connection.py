"""程序说明：验证测试环境隔离与 SQLite 连接安全参数。"""

from __future__ import annotations

import os
from pathlib import Path

from src.db.connection import create_connection


def test_test_environment_should_disable_real_model_and_admin_settings() -> None:
    """测试运行不得继承真实模型或初始管理员配置。"""

    assert os.environ.get("DOC_AI_WIKI_INITIAL_ADMIN_PASSWORD") == ""
    assert os.environ.get("LLM_PROVIDER") == "disabled"
    assert os.environ.get("LLM_MODEL") == "disabled"
    assert os.environ.get("EMBEDDING_PROVIDER") == "local"
    assert os.environ.get("RERANK_ENABLED") == "false"


def test_create_connection_should_enable_wal_and_normal(tmp_path: Path) -> None:
    """项目 SQLite 连接应统一启用 WAL 和 NORMAL。"""

    connection = create_connection(tmp_path / "app.db")
    try:
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        synchronous = int(connection.execute("PRAGMA synchronous").fetchone()[0])
    finally:
        connection.close()

    assert journal_mode == "wal"
    assert synchronous == 1
