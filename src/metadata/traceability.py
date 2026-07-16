"""程序说明：为历史 Markdown 入库数据事务化回填标题路径和源码行号。"""

from __future__ import annotations

from pathlib import Path

from src.common.errors import AppError
from src.common.paths import resolve_input_path
from src.db.connection import create_connection
from src.metadata.sections import parse_markdown_sections


def backfill_traceability(
    database_path: str | Path,
    input_root: str | Path,
    *,
    doc_uids: list[str] | None = None,
    apply: bool = False,
) -> dict:
    """按稳定 source_span 预检并回填章节与 chunk 追溯字段。"""

    database = Path(database_path)
    root = Path(input_root)
    plans: list[dict] = []
    errors: list[dict] = []
    with create_connection(database) as connection:
        params: tuple[object, ...] = ()
        where_sql = ""
        if doc_uids:
            normalized_uids = sorted({str(item).strip() for item in doc_uids if str(item).strip()})
            placeholders = ",".join("?" for _ in normalized_uids)
            where_sql = f"WHERE doc_uid IN ({placeholders})"
            params = tuple(normalized_uids)
        documents = connection.execute(
            f"SELECT doc_uid, doc_title, source_path FROM documents {where_sql} ORDER BY doc_uid",
            params,
        ).fetchall()

        for document in documents:
            doc_uid = str(document["doc_uid"])
            try:
                source_path = resolve_input_path(str(document["source_path"]), root)
                if source_path.suffix.lower() not in {".md", ".markdown"}:
                    raise ValueError("仅支持 Markdown 历史数据回填")
                source_content = source_path.read_text(encoding="utf-8-sig")
            except (AppError, OSError, ValueError, RuntimeError) as exc:
                errors.append({"doc_uid": doc_uid, "message": str(exc)})
                continue

            parsed_sections = parse_markdown_sections(
                source_content,
                fallback_title=str(document["doc_title"] or source_path.stem),
            )
            stored_sections = connection.execute(
                "SELECT section_id, source_span FROM document_sections WHERE doc_uid = ? ORDER BY rowid",
                (doc_uid,),
            ).fetchall()
            parsed_by_span = {str(section["source_span"]): section for section in parsed_sections}
            stored_spans = {str(section["source_span"] or "") for section in stored_sections}
            if len(stored_sections) != len(parsed_sections) or stored_spans != set(parsed_by_span):
                errors.append(
                    {
                        "doc_uid": doc_uid,
                        "message": "源码章节与数据库 section-n 映射不一致，已拒绝回填",
                        "stored_section_count": len(stored_sections),
                        "parsed_section_count": len(parsed_sections),
                    }
                )
                continue
            chunk_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM chunks WHERE doc_uid = ? AND section_id IS NOT NULL",
                    (doc_uid,),
                ).fetchone()[0]
            )
            plans.append(
                {
                    "doc_uid": doc_uid,
                    "stored_sections": stored_sections,
                    "parsed_by_span": parsed_by_span,
                    "chunk_count": chunk_count,
                }
            )

        if errors:
            return _build_report(plans, errors, applied=False)
        if apply:
            for plan in plans:
                for stored_section in plan["stored_sections"]:
                    parsed = plan["parsed_by_span"][str(stored_section["source_span"])]
                    connection.execute(
                        """
                        UPDATE document_sections
                        SET section_title = ?, section_level = ?, heading_path = ?,
                            source_start_line = ?, source_end_line = ?, source_anchor = ?
                        WHERE section_id = ? AND doc_uid = ?
                        """,
                        (
                            parsed["section_title"],
                            parsed["section_level"],
                            parsed["heading_path"],
                            parsed["source_start_line"],
                            parsed["source_end_line"],
                            parsed["source_anchor"],
                            stored_section["section_id"],
                            plan["doc_uid"],
                        ),
                    )
                # chunk 沿用所属章节的范围，保持既有 chunk ID 和切分内容不变。
                connection.execute(
                    """
                    UPDATE chunks
                    SET heading_path = (
                            SELECT heading_path FROM document_sections s WHERE s.section_id = chunks.section_id
                        ),
                        source_start_line = (
                            SELECT source_start_line FROM document_sections s WHERE s.section_id = chunks.section_id
                        ),
                        source_end_line = (
                            SELECT source_end_line FROM document_sections s WHERE s.section_id = chunks.section_id
                        ),
                        source_anchor = (
                            SELECT source_anchor FROM document_sections s WHERE s.section_id = chunks.section_id
                        )
                    WHERE doc_uid = ? AND section_id IS NOT NULL
                    """,
                    (plan["doc_uid"],),
                )
    return _build_report(plans, errors, applied=apply)


def _build_report(plans: list[dict], errors: list[dict], *, applied: bool) -> dict:
    """生成稳定、可记录的回填结果。"""

    return {
        "success": not errors,
        "applied": applied,
        "document_count": len(plans),
        "section_update_count": sum(len(plan["stored_sections"]) for plan in plans),
        "chunk_update_count": sum(int(plan["chunk_count"]) for plan in plans),
        "doc_uids": [plan["doc_uid"] for plan in plans],
        "errors": errors,
    }
