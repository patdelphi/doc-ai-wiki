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
            }
        )
    return items


def build_document_choices(documents: list[dict]) -> list[str]:
    """构建下拉框可用的文档选项。"""

    return [f'{item["file_name"]} | {item["file_type"]} | {item["file_path"]}' for item in documents]


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

    return {
        "scan_summary": {"documents": input_documents, "count": len(input_documents)},
        "document_choices": build_document_choices(input_documents),
        "status_items": status_items,
        "rebuild_choices": build_doc_uid_choices(status_items),
    }


def parse_document_choice(choice: str) -> str:
    """从下拉选项中解析出文件路径。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=2)[-1]


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
