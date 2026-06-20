"""程序说明：提供离线检索评测与 Claim 评测指标计算工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_jsonl_cases(path: str | Path) -> list[dict]:
    """读取 JSONL 评测集；跳过空行和非对象行，文件异常时返回空列表。"""

    case_path = Path(path)
    try:
        lines = case_path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []

    cases: list[dict] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            cases.append(item)
    return cases


def evaluate_retrieval_cases(
    retrieval_service: Any,
    cases: list[dict],
    *,
    top_k: int = 5,
    knowledge_base_id: str | None = None,
) -> dict:
    """运行检索评测，输出 Top-K 命中率和证据追溯率。"""

    rows: list[dict] = []
    limit = max(int(top_k), 1)
    for index, case in enumerate(cases, start=1):
        query = str(case.get("query") or "").strip()
        expected_chunk_ids = _to_string_set(case.get("expected_chunk_ids"))
        expected_doc_uids = _to_string_set(case.get("expected_doc_uids"))
        try:
            items = retrieval_service.hybrid_search(
                query,
                top_k=limit,
                knowledge_base_id=case.get("knowledge_base_id") or knowledge_base_id,
            )
        except Exception as exc:  # noqa: BLE001
            items = []
            error_message = str(exc)
        else:
            error_message = ""

        returned_chunk_ids = [str(item.get("chunk_id") or "") for item in items if item.get("chunk_id")]
        returned_doc_uids = [str(item.get("doc_uid") or "") for item in items if item.get("doc_uid")]
        top_k_hit = bool(expected_chunk_ids.intersection(returned_chunk_ids))
        if not top_k_hit and expected_doc_uids:
            top_k_hit = bool(expected_doc_uids.intersection(returned_doc_uids))
        traceable = bool(items) and all(_is_traceable_item(item) for item in items)
        rows.append(
            {
                "case_id": str(case.get("case_id") or f"case_{index}"),
                "query": query,
                "expected_chunk_ids": sorted(expected_chunk_ids),
                "expected_doc_uids": sorted(expected_doc_uids),
                "returned_chunk_ids": returned_chunk_ids,
                "returned_doc_uids": returned_doc_uids,
                "top_k": limit,
                "top_k_hit": top_k_hit,
                "traceable": traceable,
                "error_message": error_message,
            }
        )
    return {
        "summary": _build_retrieval_summary(rows),
        "rows": rows,
    }


def evaluate_claim_results(cases: list[dict], actual_results: list[dict]) -> dict:
    """对 Claim 评测结果计算 verdict 准确率和无证据 verified 风险。"""

    actual_by_case_id = {
        str(item.get("case_id") or ""): item
        for item in actual_results
        if str(item.get("case_id") or "")
    }
    rows: list[dict] = []
    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("case_id") or f"case_{index}")
        actual = actual_by_case_id.get(case_id, {})
        expected_verdict = str(case.get("expected_verdict") or "").strip()
        actual_verdict = str(actual.get("actual_verdict") or actual.get("verdict") or "").strip()
        evidence_details = actual.get("evidence_details") or []
        has_evidence = bool(evidence_details)
        verdict_matched = bool(expected_verdict) and expected_verdict == actual_verdict
        rows.append(
            {
                "case_id": case_id,
                "claim_text": str(case.get("claim_text") or ""),
                "expected_verdict": expected_verdict,
                "actual_verdict": actual_verdict,
                "verdict_matched": verdict_matched,
                "has_evidence": has_evidence,
                "no_evidence_verified": actual_verdict == "verified" and not has_evidence,
            }
        )
    return {
        "summary": _build_claim_summary(rows),
        "rows": rows,
    }


def _build_retrieval_summary(rows: list[dict]) -> dict:
    """汇总检索评测指标。"""

    case_count = len(rows)
    hit_count = sum(1 for row in rows if row["top_k_hit"])
    traceable_count = sum(1 for row in rows if row["traceable"])
    return {
        "case_count": case_count,
        "top_k_hit_count": hit_count,
        "top_k_hit_rate": _safe_rate(hit_count, case_count),
        "traceable_case_count": traceable_count,
        "traceability_rate": _safe_rate(traceable_count, case_count),
    }


def _build_claim_summary(rows: list[dict]) -> dict:
    """汇总 Claim 评测指标。"""

    case_count = len(rows)
    match_count = sum(1 for row in rows if row["verdict_matched"])
    no_evidence_verified_count = sum(1 for row in rows if row["no_evidence_verified"])
    return {
        "case_count": case_count,
        "verdict_match_count": match_count,
        "verdict_accuracy": _safe_rate(match_count, case_count),
        "no_evidence_verified_count": no_evidence_verified_count,
        "no_evidence_verified_rate": _safe_rate(no_evidence_verified_count, case_count),
    }


def _to_string_set(value: object) -> set[str]:
    """将评测字段规范为字符串集合。"""

    if value is None:
        return set()
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, list | tuple | set):
        return {str(item) for item in value if str(item)}
    return {str(value)} if str(value) else set()


def _is_traceable_item(item: dict) -> bool:
    """判断单条证据是否具备人工复核所需的基本出处字段。"""

    return bool(item.get("heading_path")) and item.get("source_start_line") is not None and item.get("chunk_type")


def _safe_rate(numerator: int, denominator: int) -> float:
    """安全计算比例，统一保留四位小数。"""

    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
