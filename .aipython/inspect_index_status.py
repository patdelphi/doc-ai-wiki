"""程序说明：只读输出文档状态以及 SQLite、FTS、Chroma 的统一一致性报告。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.embedding import build_embedding_client
from src.common.config import AppSettings
from src.db.connection import create_connection
from src.retrieval.index_state import build_retrieval_index_report
from src.retrieval.vector_store import VectorStore


def main() -> None:
    """输出数据库文档状态和向量库计数，便于快速核对真实入库结果。"""

    settings = AppSettings()
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

    vector_store = VectorStore(
        settings.chroma_persist_dir,
        embedding_client=build_embedding_client(settings),
        sqlite_db_path=settings.sqlite_db_path,
        auto_repair_dimension_mismatch=False,
        embedding_model=settings.embedding_model,
        index_version="retrieval-v2",
    )
    collection = vector_store.collection
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
        "index_report": build_retrieval_index_report(
            settings.sqlite_db_path,
            vector_store,
            embedding_provider=settings.embedding_provider,
            embedding_model=settings.embedding_model,
            index_version="retrieval-v2",
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
