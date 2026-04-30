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

    claim_choices = [
        f'{item["claim_id"]} | {item["verdict"]} | {item["claim_text"][:30]}'
        for item in claims
    ]
    claims_table = [
        {
            "claim_id": item["claim_id"],
            "claim_text": item["claim_text"],
            "verdict": item["verdict"],
            "risk_level": item.get("risk_level", ""),
            "confidence": item["confidence"],
            "source_doc": item.get("source_doc"),
            "source_span": item.get("source_span"),
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
    }


def parse_claim_choice(choice: str) -> str:
    """从审核下拉项中解析 claim_id。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=1)[0]


def parse_doc_uid_choice(choice: str) -> str:
    """从下拉项中解析 doc_uid。"""

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
                "input_text": item.get("input_text"),
                "created_at": item.get("created_at"),
                "claim_choices": [
                    f'{claim["claim_id"]} | {claim["verdict"]} | {claim["claim_text"][:30]}'
                    for claim in claims
                ],
                "claims": claims,
            }
        )
    return formatted
