"""程序说明：清空全部知识库下的 AI 质检历史与审核历史，并输出删除前后统计。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parents[1] / "index" / "app.db"


def read_counts(connection: sqlite3.Connection) -> dict[str, int]:
    """读取与 AI 质检历史相关的表计数。"""

    return {
        "quality_checks": int(connection.execute("SELECT COUNT(1) FROM quality_checks").fetchone()[0]),
        "quality_claims": int(connection.execute("SELECT COUNT(1) FROM quality_claims").fetchone()[0]),
        "rule_hits": int(connection.execute("SELECT COUNT(1) FROM rule_hits").fetchone()[0]),
        "review_records": int(connection.execute("SELECT COUNT(1) FROM review_records").fetchone()[0]),
    }


def clear_quality_history() -> dict[str, dict[str, int]]:
    """在单个事务中删除审核记录和全部 AI 质检历史。"""

    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        before = read_counts(connection)

        # 先删审核记录，再删质检主记录；claim 与 rule_hit 依赖级联删除。
        connection.execute("BEGIN")
        connection.execute("DELETE FROM review_records")
        connection.execute("DELETE FROM quality_checks")
        connection.commit()

        after = read_counts(connection)
        return {"before": before, "after": after}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(clear_quality_history(), ensure_ascii=False, indent=2))
