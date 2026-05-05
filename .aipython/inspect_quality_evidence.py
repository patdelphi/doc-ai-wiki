"""程序说明：查看最近 AI 质检 Claim 的证据明细存储情况。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parents[1] / "index" / "app.db"


def inspect_quality_evidence(knowledge_base_id: str = "default", limit: int = 20) -> list[dict]:
    """读取最近 Claim 的证据 JSON 长度，辅助排查历史记录证据缺失问题。"""

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                qc.check_id,
                qc.claim_id,
                LENGTH(COALESCE(qc.evidence_details_json, '')) AS details_len,
                q.created_at
            FROM quality_claims qc
            JOIN quality_checks q ON q.check_id = qc.check_id
            WHERE q.knowledge_base_id = ?
            ORDER BY q.created_at DESC, qc.created_at ASC
            LIMIT ?
            """,
            (knowledge_base_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(inspect_quality_evidence(), ensure_ascii=False, indent=2))
