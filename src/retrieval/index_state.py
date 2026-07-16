"""程序说明：检查并记录检索索引的一致性与模型指纹。"""

from __future__ import annotations

import json
from pathlib import Path

from src.common.utils import utc_now_iso
from src.db.connection import create_connection
from src.retrieval.vector_store import VectorStore


def build_retrieval_index_report(
    database_path: Path,
    vector_store: VectorStore,
    *,
    embedding_provider: str,
    embedding_model: str,
    index_version: str,
) -> dict:
    """生成 SQLite、FTS 与向量索引的一致性报告。"""

    with create_connection(database_path) as connection:
        sqlite_chunk_count = int(connection.execute("SELECT COUNT(1) FROM chunks").fetchone()[0])
        fts_chunk_count = int(connection.execute("SELECT COUNT(1) FROM chunk_fts").fetchone()[0])
        fts_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'chunk_fts'"
        ).fetchone()
    fts_sql = str(fts_row[0] or "") if fts_row else ""
    fts_tokenizer = "trigram" if "trigram" in fts_sql.lower() else "unicode61"
    vector_report = vector_store.inspect_index()
    vector_count = int(vector_report.get("total_count") or 0)

    errors: list[str] = []
    if sqlite_chunk_count != fts_chunk_count:
        errors.append("fts_count_mismatch")
    if sqlite_chunk_count != vector_count:
        errors.append("vector_count_mismatch")
    if int(vector_report.get("missing_metadata_count") or 0) > 0:
        errors.append("missing_vector_metadata")
    if vector_count and vector_report.get("embedding_models") != [embedding_model]:
        errors.append("embedding_model_mismatch")
    if vector_count and vector_report.get("index_versions") != [index_version]:
        errors.append("index_version_mismatch")
    if fts_tokenizer != "trigram":
        errors.append("fts_tokenizer_mismatch")

    return {
        "generated_at": utc_now_iso(),
        "index_version": index_version,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_dimensions": vector_report.get("embedding_dimensions") or [],
        "sqlite_chunk_count": sqlite_chunk_count,
        "fts_chunk_count": fts_chunk_count,
        "fts_tokenizer": fts_tokenizer,
        "vector_count": vector_count,
        "vector_by_knowledge_base": vector_report.get("by_knowledge_base") or {},
        "vector_by_document": vector_report.get("by_document") or {},
        "missing_vector_metadata_count": int(vector_report.get("missing_metadata_count") or 0),
        "errors": errors,
        "consistent": not errors,
    }


def write_index_manifest(path: Path, report: dict) -> None:
    """使用临时文件原子写入 UTF-8 BOM 索引清单。"""

    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = manifest_path.with_suffix(f"{manifest_path.suffix}.tmp")
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    temporary_path.write_text(payload, encoding="utf-8-sig", newline="\r\n")
    temporary_path.replace(manifest_path)
