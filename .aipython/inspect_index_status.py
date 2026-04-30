"""程序说明：读取 SQLite 与 ChromaDB 的当前状态，输出文档入库和向量索引汇总信息。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.config import get_settings
from src.db.connection import create_connection
from src.retrieval.vector_store import VectorStore


def main() -> None:
    """输出数据库文档状态和向量库计数，便于快速核对真实入库结果。"""

    settings = get_settings()
    with create_connection(settings.sqlite_db_path) as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                (
                    "SELECT doc_uid, doc_title, source_path, ingest_status, index_status, "
                    "error_message, created_at, updated_at "
                    "FROM documents ORDER BY updated_at DESC"
                )
            ).fetchall()
        ]

    collection = VectorStore(settings.chroma_persist_dir).collection
    doc_vector_counts: dict[str, int] = {}
    for row in rows:
        doc_uid = str(row["doc_uid"])
        result = collection.get(where={"doc_uid": doc_uid}, include=[])
        doc_vector_counts[doc_uid] = len(result.get("ids", []))

    summary = {
        "sqlite_document_count": len(rows),
        "chroma_total_count": collection.count(),
        "documents": rows,
        "doc_vector_counts": doc_vector_counts,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
