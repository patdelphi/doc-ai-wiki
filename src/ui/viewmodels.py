"""程序说明：为 Gradio 页面准备可直接展示的视图数据。"""

from __future__ import annotations

from pathlib import Path


def scan_input_documents(input_root: Path) -> list[dict]:
    """扫描知识库输入目录，返回可注册的文档列表。"""

    if not input_root.exists():
        return []

    items: list[dict] = []
    for file_path in sorted(input_root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".md", ".json"}:
            continue
        items.append(
            {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "file_type": file_path.suffix.lower().lstrip("."),
                "size_bytes": file_path.stat().st_size,
                "size_display": format_file_size(file_path.stat().st_size),
            }
        )
    return items


def format_file_size(size_bytes: int) -> str:
    """将文件字节数格式化为更易读的大小文本。"""

    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def build_document_choices(documents: list[dict]) -> list[str]:
    """构建下拉框可用的文档选项。"""

    return [build_document_choice(item) for item in documents]


def build_doc_uid_choices(documents: list[dict]) -> list[str]:
    """构建可用于重建索引的文档选项。"""

    return [f'{item["doc_uid"]} | {item.get("doc_title", "")}' for item in documents if item.get("doc_uid")]


def build_template_choices(templates: list[dict]) -> list[str]:
    """构建质检模板下拉选项。"""

    return [f'{item["template_id"]} | {item.get("template_name", "")}' for item in templates if item.get("template_id")]


def format_search_results(items: list[dict]) -> dict:
    """将检索结果转换为更适合 UI 展示的结构。"""

    rows = [
        {
            "chunk_id": item.get("chunk_id"),
            "doc_uid": item.get("doc_uid"),
            "doc_title": item.get("doc_title", ""),
            "author": item.get("author", ""),
            "source_name": item.get("source_name", ""),
            "tags": item.get("tags", []),
            "source_span": item.get("source_span"),
            "retrieval_source": item.get("retrieval_source", ""),
            "matched_sources": item.get("matched_sources", []),
            "score": item.get("score"),
            "rerank_score": item.get("rerank_score"),
            "content_preview": str(item.get("content", ""))[:200],
        }
        for item in items
    ]
    return {
        "count": len(rows),
        "items": items,
        "table": rows,
    }


def build_document_management_state(input_documents: list[dict], status_items: list[dict]) -> dict:
    """构建文档管理页所需的扫描、状态与重建选项数据。"""
    status_by_path = {
        str(item.get("source_path")): item
        for item in status_items
        if item.get("source_path")
    }
    rows: list[dict] = []
    seen_paths: set[str] = set()

    for document in input_documents:
        source_path = str(document["file_path"])
        seen_paths.add(source_path)
        status_item = status_by_path.get(source_path)
        rows.append(_build_document_row(document, status_item))

    for status_item in status_items:
        source_path = str(status_item.get("source_path") or "")
        if not source_path or source_path in seen_paths:
            continue
        rows.append(_build_document_row(None, status_item))

    rows.sort(key=lambda item: (item["registered_sort"], item["file_name"].lower()))
    table_rows = [
        [
            item["file_name"],
            item["doc_title"],
            item["size_display"],
            item["ingested_at"],
            item["registered_label"],
            item["index_status"],
            item["needs_rebuild_label"],
            item["action_hint"],
            item["error_message"],
        ]
        for item in rows
    ]
    detail_map = {item["source_path"]: item for item in rows if item.get("source_path")}
    choices = [build_document_choice(item) for item in rows if item.get("source_path")]
    default_choice = choices[0] if choices else None
    return {
        "scan_summary": {
            "total_files": len(input_documents),
            "registered_files": sum(1 for item in rows if item["is_registered"]),
            "pending_register_files": sum(1 for item in rows if not item["is_registered"] and item["source_exists"]),
            "needs_rebuild_files": sum(1 for item in rows if item["needs_rebuild"]),
        },
        "table_headers": ["文件名", "文档名称", "大小", "入库时间", "已注册", "索引状态", "需重建", "推荐动作", "错误信息"],
        "table_rows": table_rows,
        "document_choices": choices,
        "default_choice": default_choice,
        "document_detail_map": detail_map,
        "selected_detail": get_document_detail(default_choice, detail_map),
        "status_items": status_items,
        "rebuild_choices": build_doc_uid_choices(status_items),
    }


def parse_document_choice(choice: str) -> str:
    """从下拉选项中解析出文件路径。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=2)[-1]


def build_document_choice(document: dict) -> str:
    """构建文档管理页的文档选择项。"""

    return (
        f'{document.get("file_name", "")} | {document.get("action_hint", "")} | '
        f'{document.get("source_path") or document.get("file_path", "")}'
    )


def get_document_detail(choice: str, document_detail_map: dict | None) -> dict:
    """根据文档选择项读取详情。"""

    source_path = parse_document_choice(choice)
    if not source_path or not document_detail_map:
        return {"message": "请选择文档"}
    return document_detail_map.get(source_path, {"message": "未找到对应文档"})


def build_document_action_updates(detail: dict | None) -> tuple[dict, dict]:
    """根据当前文档详情决定按钮是否可操作。"""

    resolved = detail or {}
    if "source_path" not in resolved:
        return {"interactive": False}, {"interactive": False}
    return (
        {"interactive": bool(resolved.get("can_register"))},
        {"interactive": bool(resolved.get("can_rebuild"))},
    )


def _build_document_row(input_document: dict | None, status_item: dict | None) -> dict:
    """合并 Input 扫描结果和数据库状态，构造成文档管理行。"""

    source_path = str(
        (input_document or {}).get("file_path")
        or (status_item or {}).get("source_path")
        or ""
    )
    file_name = (input_document or {}).get("file_name") or Path(source_path).name
    size_bytes = int((input_document or {}).get("size_bytes") or 0)
    size_display = (input_document or {}).get("size_display") or ("-" if not size_bytes else format_file_size(size_bytes))
    is_registered = bool(status_item)
    source_exists = bool(input_document)
    index_status = (status_item or {}).get("index_status") or "not_registered"
    error_message = str((status_item or {}).get("error_message") or "")
    needs_rebuild = bool(status_item) and index_status != "indexed"
    action_hint = "可注册"
    if is_registered and needs_rebuild:
        action_hint = "建议重建"
    elif is_registered and not needs_rebuild:
        action_hint = "已就绪"
    elif not source_exists:
        action_hint = "源文件缺失"
    doc_title = (
        (status_item or {}).get("doc_title")
        or Path(file_name).stem
    )
    return {
        "source_path": source_path,
        "file_name": file_name,
        "doc_title": doc_title,
        "doc_uid": (status_item or {}).get("doc_uid", ""),
        "file_type": (input_document or {}).get("file_type") or Path(file_name).suffix.lstrip("."),
        "size_bytes": size_bytes,
        "size_display": size_display,
        "is_registered": is_registered,
        "registered_label": "是" if is_registered else "否",
        "registered_sort": 0 if is_registered else 1,
        "source_exists": source_exists,
        "ingested_at": str((status_item or {}).get("created_at") or "-"),
        "ingest_status": str((status_item or {}).get("ingest_status") or "not_registered"),
        "index_status": index_status,
        "needs_rebuild": needs_rebuild,
        "needs_rebuild_label": "是" if needs_rebuild else "否",
        "action_hint": action_hint,
        "error_message": error_message[:120],
        "can_register": source_exists and not is_registered,
        "can_rebuild": source_exists and is_registered,
    }


def format_ingest_result(payload: dict, progress_events: list[dict]) -> dict:
    """整理文档管理操作结果与进度快照。"""

    return {
        **payload,
        "progress_summary": {
            "steps": progress_events,
            "step_count": len(progress_events),
            "last_stage": progress_events[-1]["stage"] if progress_events else None,
            "last_percent": progress_events[-1]["percent"] if progress_events else 0,
        },
    }


def format_quality_result(result: dict) -> dict:
    """将质检结果转换为更适合前端展示的结构。"""

    claims = result.get("claims", [])
    rule_hits = result.get("rule_hits", [])

    claim_choices = [build_claim_choice(item) for item in claims]
    claims_table = [
        {
            "claim_id": item["claim_id"],
            "claim_text": item["claim_text"],
            "verdict": item["verdict"],
            "risk_level": item.get("risk_level", ""),
            "confidence": item["confidence"],
            "source_doc": item.get("source_doc"),
            "source_span": item.get("source_span"),
            "evidence_details": item.get("evidence_details", []),
        }
        for item in claims
    ]

    return {
        "summary": result.get("check", {}).get("summary", ""),
        "check": result.get("check", {}),
        "claims": claims,
        "claims_table": claims_table,
        "rule_hits": rule_hits,
        "claim_choices": claim_choices,
        "claim_detail_map": build_claim_detail_map(claims),
    }


def parse_claim_choice(choice: str) -> str:
    """从审核下拉项中解析 claim_id。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=1)[0]


def build_claim_detail_map(claims: list[dict]) -> dict:
    """构建 claim_id 到 claim 详情的映射。"""

    return {
        item["claim_id"]: {
            "claim_id": item["claim_id"],
            "claim_text": item.get("claim_text", ""),
            "verdict": item.get("verdict", ""),
            "risk_level": item.get("risk_level", ""),
            "confidence": item.get("confidence"),
            "review_status": item.get("review_status", "pending"),
            "source_doc": item.get("source_doc"),
            "source_span": item.get("source_span"),
            "check_id": item.get("check_id"),
            "template_name": item.get("template_name"),
            "check_created_at": item.get("check_created_at"),
            "evidence": item.get("evidence", ""),
            "evidence_reason": item.get("evidence_reason", ""),
            "evidence_details": item.get("evidence_details", []),
        }
        for item in claims
        if item.get("claim_id")
    }


def get_claim_detail(claim_choice: str, claim_detail_map: dict | None) -> dict:
    """根据下拉选项读取 claim 详情。"""

    claim_id = parse_claim_choice(claim_choice)
    if not claim_id or not claim_detail_map:
        return {"message": "请选择 Claim"}
    return claim_detail_map.get(claim_id, {"message": "未找到对应 Claim 详情"})


def format_claim_detail_for_review(claim_choice: str, claim_detail_map: dict | None) -> dict:
    """将 claim 详情转换为更适合审核页展示的结构。"""

    detail = get_claim_detail(claim_choice, claim_detail_map)
    if "claim_id" not in detail:
        return detail

    evidence_details = detail.get("evidence_details", [])
    evidence_table = [
        {
            "chunk_id": item.get("chunk_id"),
            "doc_uid": item.get("doc_uid"),
            "doc_title": item.get("doc_title", ""),
            "source_span": item.get("source_span"),
            "retrieval_source": item.get("retrieval_source", ""),
            "matched_sources": item.get("matched_sources", []),
            "rerank_score": item.get("rerank_score"),
            "context_mode": item.get("context_mode", ""),
            "section_title": item.get("section_title", ""),
            "content_preview": item.get("content_preview", ""),
        }
        for item in evidence_details
    ]
    return {
        "summary": {
            "claim_id": detail.get("claim_id"),
            "claim_text": detail.get("claim_text", ""),
            "verdict": detail.get("verdict", ""),
            "risk_level": detail.get("risk_level", ""),
            "confidence": detail.get("confidence"),
            "review_status": detail.get("review_status", "pending"),
            "source_doc": detail.get("source_doc"),
            "source_span": detail.get("source_span"),
            "check_id": detail.get("check_id"),
            "template_name": detail.get("template_name"),
            "check_created_at": detail.get("check_created_at"),
            "evidence": detail.get("evidence", ""),
            "evidence_reason": detail.get("evidence_reason", ""),
        },
        "evidence_table": evidence_table,
        "evidence_count": len(evidence_table),
    }


def parse_doc_uid_choice(choice: str) -> str:
    """从下拉项中解析 doc_uid。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=1)[0]


def parse_template_choice(choice: str) -> str:
    """从模板下拉项中解析 template_id。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=1)[0]


def format_recent_quality_checks(quality_results: list[dict]) -> list[dict]:
    """将最近质检记录转换为 UI 可展示结构。"""

    formatted: list[dict] = []
    for item in quality_results:
        claims = item.get("claims", [])
        formatted.append(
            {
                "check_id": item.get("check_id"),
                "overall_verdict": item.get("overall_verdict"),
                "template_name": item.get("template_name"),
                "input_text": item.get("input_text"),
                "created_at": item.get("created_at"),
                "claim_choices": [
                    build_claim_choice(
                        {
                            **claim,
                            "check_id": item.get("check_id"),
                            "template_name": item.get("template_name"),
                            "check_created_at": item.get("created_at"),
                        }
                    )
                    for claim in claims
                ],
                "claim_detail_map": build_claim_detail_map(
                    [
                        {
                            **claim,
                            "check_id": item.get("check_id"),
                            "template_name": item.get("template_name"),
                            "check_created_at": item.get("created_at"),
                        }
                        for claim in claims
                    ]
                ),
                "claims": claims,
            }
        )
    return formatted


def build_claim_choice(claim: dict) -> str:
    """构建 claim 下拉选项。"""

    return (
        f'{claim["claim_id"]} | {claim.get("verdict", "")} | '
        f'{claim.get("review_status", "pending")} | {claim.get("claim_text", "")[:30]}'
    )


def build_recent_claim_navigation(quality_results: list[dict], preferred_claim_id: str | None = None) -> dict:
    """根据最近质检结果构建统一的 Claim 导航状态。"""

    merged_claims: list[dict] = []
    for item in quality_results:
        for claim in item.get("claims", []):
            merged_claims.append(
                {
                    **claim,
                    "check_id": item.get("check_id"),
                    "template_name": item.get("template_name"),
                    "check_created_at": item.get("created_at"),
                }
            )

    claim_choices = [build_claim_choice(item) for item in merged_claims]
    claim_detail_map = build_claim_detail_map(merged_claims)
    selected_claim_id = preferred_claim_id if preferred_claim_id in claim_detail_map else ""
    if not selected_claim_id and merged_claims:
        selected_claim_id = merged_claims[0]["claim_id"]
    selected_choice = next(
        (choice for choice in claim_choices if choice.startswith(f"{selected_claim_id} |")),
        None,
    )
    selected_detail = format_claim_detail_for_review(selected_choice, claim_detail_map)
    return {
        "claim_choices": claim_choices,
        "selected_choice": selected_choice,
        "claim_detail_map": claim_detail_map,
        "selected_detail": selected_detail,
    }


def format_review_history(review_items: list[dict]) -> dict:
    """将审核记录转换为更适合 UI 展示的结构。"""

    rows = [
        {
            "review_id": item.get("review_id"),
            "claim_id": item.get("claim_id"),
            "check_id": item.get("check_id"),
            "template_name": item.get("template_name", ""),
            "claim_text": item.get("claim_text", ""),
            "review_action": item.get("review_action"),
            "review_status": item.get("review_status"),
            "review_note": item.get("review_note"),
            "reviewer": item.get("reviewer"),
            "created_at": item.get("created_at"),
        }
        for item in review_items
    ]
    review_choices = [
        f'{item["review_id"]} | {item.get("review_action", "")} | {item.get("claim_text", "")[:30]}'
        for item in rows
        if item.get("review_id")
    ]
    review_map = {item["review_id"]: item for item in rows if item.get("review_id")}
    return {
        "count": len(rows),
        "items": rows,
        "review_choices": review_choices,
        "review_map": review_map,
    }


def parse_review_choice(choice: str) -> str:
    """从审核记录下拉项中解析 review_id。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=1)[0]


def get_review_target_claim_id(review_choice: str, review_map: dict | None) -> str:
    """从审核记录中提取要定位的 claim_id。"""

    review_id = parse_review_choice(review_choice)
    if not review_id or not review_map:
        return ""
    return str(review_map.get(review_id, {}).get("claim_id", ""))
