"""程序说明：封装数据库事务上下文，统一提交与回滚逻辑。"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from sqlite3 import Connection

from src.common.errors import DatabaseAppError
from src.db.connection import create_connection


@contextmanager
def transaction(database_path: Path) -> Iterator[Connection]:
    """提供带自动提交和回滚的事务上下文。"""

    connection = create_connection(database_path)
    try:
        yield connection
        connection.commit()
    except Exception as exc:  # noqa: BLE001
        connection.rollback()
        raise DatabaseAppError("数据库事务执行失败", details={"reason": str(exc)}) from exc
    finally:
        connection.close()
