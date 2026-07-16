"""程序说明：提供离线检索评测与 Claim 评测指标计算工具。"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3
from typing import Any
import re

from src.db.connection import create_connection


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


def build_provisional_aligned_cases(
    cases: list[dict],
    suggestions_markdown: str,
    *,
    knowledge_base_id_by_doc_uid: dict[str, str] | None = None,
) -> list[dict]:
    """从候选建议中提取首个真实 chunk，生成不冒充人工金标的回归样例。"""

    candidates_by_case: dict[str, tuple[str, str]] = {}
    section_parts = re.split(r"(?m)^###\s+(\S+)\s*$", str(suggestions_markdown or ""))
    for index in range(1, len(section_parts), 2):
        case_id = section_parts[index].strip()
        section = section_parts[index + 1] if index + 1 < len(section_parts) else ""
        for line in section.splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 3 or cells[0] in {"score", "---:"}:
                continue
            doc_uid, chunk_id = cells[1], cells[2]
            if doc_uid and doc_uid != "-" and chunk_id and chunk_id != "-":
                candidates_by_case[case_id] = (doc_uid, chunk_id)
                break

    aligned_cases: list[dict] = []
    for case in cases:
        case_id = str(case.get("case_id") or "").strip()
        candidate = candidates_by_case.get(case_id)
        aligned = dict(case)
        # 仅以 chunk 为相关性目标，防止少量大文档让文档级命中率失真。
        aligned["expected_doc_uids"] = []
        if candidate is None:
            aligned["expected_chunk_ids"] = []
            aligned["aligned_candidate_doc_uid"] = ""
            aligned["alignment_status"] = "missing_candidate"
        else:
            aligned["expected_chunk_ids"] = [candidate[1]]
            aligned["aligned_candidate_doc_uid"] = candidate[0]
            aligned["alignment_status"] = "provisional_first_candidate"
            knowledge_base_id = (knowledge_base_id_by_doc_uid or {}).get(candidate[0], "")
            if knowledge_base_id:
                aligned["knowledge_base_id"] = knowledge_base_id
        aligned_cases.append(aligned)
    return aligned_cases


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
        reranked = bool(items) and all(
            isinstance(item.get("rerank_score"), int | float) for item in items
        )
        degraded = bool(error_message) or any(item.get("degraded_reason") for item in items)
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
                "reranked": reranked,
                "degraded": degraded,
                "error_message": error_message,
            }
        )
    return {
        "summary": _build_retrieval_summary(rows),
        "rows": rows,
    }


def evaluate_ranked_rows(rows: list[dict]) -> dict:
    """对已生成的排名结果计算 Recall@5、MRR@10 与 nDCG@10。"""

    enriched_rows: list[dict] = []
    reciprocal_ranks: list[float] = []
    ndcg_values: list[float] = []
    recall_hits = 0
    for row in rows:
        expected_chunks = _to_string_set(row.get("expected_chunk_ids"))
        expected_docs = _to_string_set(row.get("expected_doc_uids"))
        returned_chunks = [str(item or "") for item in row.get("returned_chunk_ids") or []]
        returned_docs = [str(item or "") for item in row.get("returned_doc_uids") or []]
        result_count = max(len(returned_chunks), len(returned_docs))
        relevance: list[int] = []
        for index in range(result_count):
            chunk_id = returned_chunks[index] if index < len(returned_chunks) else ""
            doc_uid = returned_docs[index] if index < len(returned_docs) else ""
            relevant = bool(chunk_id and chunk_id in expected_chunks)
            if not relevant and expected_docs:
                relevant = bool(doc_uid and doc_uid in expected_docs)
            relevance.append(1 if relevant else 0)

        first_relevant_rank = next(
            (rank for rank, value in enumerate(relevance[:10], start=1) if value),
            None,
        )
        reciprocal_rank = 0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank
        recall_hit = any(relevance[:5])
        relevant_target_count = max(len(expected_chunks), len(expected_docs), 1 if any(relevance) else 0)
        dcg = sum(
            value / math.log2(rank + 1)
            for rank, value in enumerate(relevance[:10], start=1)
        )
        ideal_relevance = [1] * min(relevant_target_count, 10)
        ideal_dcg = sum(
            value / math.log2(rank + 1)
            for rank, value in enumerate(ideal_relevance, start=1)
        )
        ndcg = 0.0 if ideal_dcg == 0 else dcg / ideal_dcg
        reciprocal_ranks.append(reciprocal_rank)
        ndcg_values.append(ndcg)
        recall_hits += int(recall_hit)
        enriched_rows.append(
            {
                **row,
                "first_relevant_rank": first_relevant_rank,
                "reciprocal_rank": round(reciprocal_rank, 4),
                "ndcg_at_10": round(ndcg, 4),
                "recall_at_5_hit": recall_hit,
            }
        )

    case_count = len(enriched_rows)
    traceable_count = sum(1 for row in enriched_rows if row.get("traceable"))
    return {
        "summary": {
            "case_count": case_count,
            "recall_at_5": _safe_rate(recall_hits, case_count),
            "mrr_at_10": round(sum(reciprocal_ranks) / case_count, 4) if case_count else 0.0,
            "ndcg_at_10": round(sum(ndcg_values) / case_count, 4) if case_count else 0.0,
            "traceable_rate": _safe_rate(traceable_count, case_count),
        },
        "rows": enriched_rows,
    }


def evaluate_pageindex_rows(rows: list[dict]) -> dict:
    """计算 PageIndex Node Hit@5、拒答准确率和调用预算统计。"""

    node_hits = 0
    refusal_matches = 0
    llm_calls: list[int] = []
    enriched: list[dict] = []
    for row in rows:
        expected_nodes = _to_string_set(row.get("expected_node_ids"))
        returned_nodes = [str(item or "") for item in row.get("returned_node_ids") or []]
        node_hit = bool(expected_nodes.intersection(returned_nodes[:5]))
        answerable = bool(row.get("answerable", True))
        refused = bool(row.get("refused"))
        refusal_matched = refused == (not answerable)
        raw_budget = row.get("budget")
        budget: dict = {}
        if isinstance(raw_budget, dict):
            budget = raw_budget
        llm_call_count = int(budget.get("llm_calls") or 0)
        node_hits += int(node_hit)
        refusal_matches += int(refusal_matched)
        llm_calls.append(llm_call_count)
        enriched.append(
            {
                **row,
                "node_hit_at_5": node_hit,
                "refusal_matched": refusal_matched,
                "llm_call_count": llm_call_count,
            }
        )
    case_count = len(enriched)
    return {
        "summary": {
            "case_count": case_count,
            "node_hit_at_5": _safe_rate(node_hits, case_count),
            "refusal_accuracy": _safe_rate(refusal_matches, case_count),
            "average_llm_calls": round(sum(llm_calls) / case_count, 4) if case_count else 0.0,
            "max_llm_calls": max(llm_calls, default=0),
        },
        "rows": enriched,
    }


def validate_case_references(database_path: str | Path, cases: list[dict]) -> dict:
    """校验正式评测样例引用的知识库、文档和 chunk 是否真实存在。"""

    referenced_kbs: set[str] = set()
    referenced_docs: set[str] = set()
    referenced_chunks: set[str] = set()
    for case in cases:
        knowledge_base_id = str(case.get("knowledge_base_id") or "").strip()
        if knowledge_base_id:
            referenced_kbs.add(knowledge_base_id)
        referenced_docs.update(_to_string_set(case.get("expected_doc_uids")))
        referenced_docs.update(_to_string_set(case.get("doc_uid")))
        referenced_chunks.update(_to_string_set(case.get("expected_chunk_ids")))

    connection = create_connection(Path(database_path))
    try:
        existing_kbs = {
            str(row[0])
            for row in connection.execute("SELECT knowledge_base_id FROM knowledge_bases").fetchall()
        }
        existing_docs = {
            str(row[0])
            for row in connection.execute("SELECT doc_uid FROM documents").fetchall()
        }
        existing_chunks = {
            str(row[0])
            for row in connection.execute("SELECT chunk_id FROM chunks").fetchall()
        }
    finally:
        connection.close()
    missing_kbs = sorted(referenced_kbs - existing_kbs)
    missing_docs = sorted(referenced_docs - existing_docs)
    missing_chunks = sorted(referenced_chunks - existing_chunks)
    return {
        "valid": not (missing_kbs or missing_docs or missing_chunks),
        "missing_knowledge_base_ids": missing_kbs,
        "missing_doc_uids": missing_docs,
        "missing_chunk_ids": missing_chunks,
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


def evaluate_claim_cases(
    quality_service: Any,
    cases: list[dict],
    *,
    doc_uid: str | None = None,
    knowledge_base_id: str | None = None,
    template_id: str | None = None,
) -> dict:
    """运行真实 Claim 质检评测，并保留历史 check_id 便于 UI 回查。"""

    actual_results: list[dict] = []
    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("case_id") or f"case_{index}")
        claim_text = str(case.get("claim_text") or case.get("input_text") or "").strip()
        if not claim_text:
            actual_results.append(
                {
                    "case_id": case_id,
                    "actual_verdict": "",
                    "evidence_details": [],
                    "check_id": "",
                    "error_message": "评测样例缺少 claim_text",
                }
            )
            continue
        try:
            result = quality_service.run_check(
                claim_text,
                doc_uid=doc_uid or case.get("doc_uid"),
                knowledge_base_id=case.get("knowledge_base_id") or knowledge_base_id,
                template_id=case.get("template_id") or template_id,
            )
        except Exception as exc:  # noqa: BLE001
            actual_results.append(
                {
                    "case_id": case_id,
                    "actual_verdict": "",
                    "evidence_details": [],
                    "check_id": "",
                    "error_message": str(exc),
                }
            )
            continue

        check = result.get("check") or {}
        claims = result.get("claims") or []
        first_claim = claims[0] if claims else {}
        actual_results.append(
            {
                "case_id": case_id,
                "actual_verdict": first_claim.get("verdict") or "",
                "evidence_details": first_claim.get("evidence_details") or [],
                "check_id": check.get("check_id") or first_claim.get("check_id") or "",
                "error_message": "",
            }
        )

    evaluated = evaluate_claim_results(cases, actual_results)
    actual_by_case_id = {str(item.get("case_id") or ""): item for item in actual_results}
    enriched_rows: list[dict] = []
    for row in evaluated.get("rows") or []:
        actual = actual_by_case_id.get(str(row.get("case_id") or ""), {})
        enriched_rows.append(
            {
                **row,
                "check_id": actual.get("check_id") or "",
                "error_message": actual.get("error_message") or "",
            }
        )
    return {
        "summary": evaluated.get("summary") or {},
        "rows": enriched_rows,
    }


def format_evaluation_report_markdown(
    *,
    title: str,
    retrieval_result: dict | None = None,
    claim_result: dict | None = None,
) -> str:
    """将检索与 Claim 评测结果格式化为 Markdown 报告。"""

    report_title = str(title or "评测报告").strip() or "评测报告"
    lines = [
        f"# {report_title}",
        "",
        "## 指标汇总",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
    ]

    retrieval_summary = (retrieval_result or {}).get("summary") or {}
    claim_summary = (claim_result or {}).get("summary") or {}
    lines.extend(
        [
            f"| 检索样例数 | {_format_metric(retrieval_summary.get('case_count'))} |",
            f"| Top-K 命中数 | {_format_metric(retrieval_summary.get('top_k_hit_count'))} |",
            f"| Top-K 命中率 | {_format_metric(retrieval_summary.get('top_k_hit_rate'))} |",
            f"| Recall@5 | {_format_metric(retrieval_summary.get('recall_at_5'))} |",
            f"| MRR@10 | {_format_metric(retrieval_summary.get('mrr_at_10'))} |",
            f"| nDCG@10 | {_format_metric(retrieval_summary.get('ndcg_at_10'))} |",
            f"| 证据追溯率 | {_format_metric(retrieval_summary.get('traceability_rate'))} |",
            f"| Rerank 覆盖率 | {_format_metric(retrieval_summary.get('rerank_coverage_rate'))} |",
            f"| 降级样例数 | {_format_metric(retrieval_summary.get('degraded_case_count'))} |",
            f"| Claim 样例数 | {_format_metric(claim_summary.get('case_count'))} |",
            f"| Claim 准确率 | {_format_metric(claim_summary.get('verdict_accuracy'))} |",
            f"| 无证据 verified 率 | {_format_metric(claim_summary.get('no_evidence_verified_rate'))} |",
            "",
        ]
    )

    lines.extend(_format_retrieval_rows((retrieval_result or {}).get("rows") or []))
    lines.extend(_format_claim_rows((claim_result or {}).get("rows") or []))
    return "\r\n".join(lines).strip() + "\r\n"


def export_evidence_catalog(
    database_path: str | Path,
    *,
    knowledge_base_id: str | None = None,
    query: str = "",
    limit: int = 200,
) -> dict:
    """从 SQLite 只读导出候选证据目录，用于人工对齐评测集标准 ID。"""

    item_limit = max(int(limit), 1)
    query_text = str(query or "").strip()
    knowledge_filter = " AND d.knowledge_base_id = ?" if knowledge_base_id else ""
    query_filter = " AND c.content LIKE ?" if query_text else ""
    params: list[object] = []
    if knowledge_base_id:
        params.append(knowledge_base_id)
    if query_text:
        params.append(f"%{query_text}%")
    params.append(item_limit)

    try:
        with create_connection(Path(database_path)) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    d.knowledge_base_id,
                    d.doc_uid,
                    d.doc_title,
                    d.source_name,
                    c.chunk_id,
                    c.chunk_index,
                    c.heading_path,
                    c.source_start_line,
                    c.source_end_line,
                    c.source_anchor,
                    c.chunk_type,
                    c.content
                FROM chunks c
                JOIN documents d ON d.doc_uid = c.doc_uid
                WHERE 1 = 1
                {knowledge_filter}
                {query_filter}
                ORDER BY d.doc_title ASC, c.chunk_index ASC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
    except (OSError, sqlite3.Error):
        rows = []

    items = [_build_catalog_item(dict(row)) for row in rows]
    return {
        "summary": {
            "item_count": len(items),
            "knowledge_base_id": knowledge_base_id or "",
            "query": query_text,
            "limit": item_limit,
        },
        "items": items,
    }


def format_evidence_catalog_markdown(catalog: dict, *, title: str = "证据目录") -> str:
    """将候选证据目录格式化为 Markdown，便于人工标注评测集。"""

    summary = catalog.get("summary") or {}
    lines = [
        f"# {str(title or '证据目录').strip() or '证据目录'}",
        "",
        "## 摘要",
        "",
        f"- 知识库：`{summary.get('knowledge_base_id') or '-'}`",
        f"- 查询：`{summary.get('query') or '-'}`",
        f"- 候选数：`{summary.get('item_count') or 0}`",
        "",
        "## 候选证据",
        "",
        "| doc_uid | chunk_id | 文档 | 标题路径 | 位置 | 摘要 |",
        "|---|---|---|---|---|---|",
    ]
    items = catalog.get("items") or []
    if not items:
        lines.append("| - | - | - | - | - | - |")
    for item in items:
        lines.append(
            "| {doc_uid} | {chunk_id} | {doc_title} | {heading_path} | {source_anchor} | {excerpt} |".format(
                doc_uid=_escape_markdown_cell(item.get("doc_uid")),
                chunk_id=_escape_markdown_cell(item.get("chunk_id")),
                doc_title=_escape_markdown_cell(item.get("doc_title")),
                heading_path=_escape_markdown_cell(item.get("heading_path")),
                source_anchor=_escape_markdown_cell(item.get("source_anchor")),
                excerpt=_escape_markdown_cell(item.get("content_excerpt")),
            )
        )
    return "\r\n".join(lines).strip() + "\r\n"


def suggest_retrieval_case_alignments(
    cases: list[dict],
    catalog: dict,
    *,
    max_candidates: int = 3,
) -> dict:
    """基于候选证据目录为检索评测样例生成真实 ID 对齐建议。"""

    candidate_limit = max(int(max_candidates), 1)
    catalog_items = list(catalog.get("items") or [])
    rows: list[dict] = []
    for index, case in enumerate(cases, start=1):
        query_text = str(case.get("query") or "")
        expected_evidence = str(case.get("expected_evidence") or "")
        scored_candidates = [
            _score_alignment_candidate(query_text, expected_evidence, item)
            for item in catalog_items
        ]
        candidates = [
            item
            for item in sorted(scored_candidates, key=lambda value: value["score"], reverse=True)
            if item["score"] > 0
        ][:candidate_limit]
        rows.append(
            {
                "case_id": str(case.get("case_id") or f"case_{index}"),
                "query": query_text,
                "expected_evidence": expected_evidence,
                "candidates": candidates,
            }
        )
    suggested_count = sum(1 for row in rows if row["candidates"])
    return {
        "summary": {
            "case_count": len(rows),
            "suggested_case_count": suggested_count,
            "suggestion_rate": _safe_rate(suggested_count, len(rows)),
        },
        "rows": rows,
    }


def format_alignment_suggestions_markdown(suggestions: dict, *, title: str = "检索样例证据对齐建议") -> str:
    """将检索样例对齐建议格式化为 Markdown，供人工复核后写回评测集。"""

    summary = suggestions.get("summary") or {}
    lines = [
        f"# {str(title or '检索样例证据对齐建议').strip() or '检索样例证据对齐建议'}",
        "",
        "## 摘要",
        "",
        f"- 样例数：`{summary.get('case_count') or 0}`",
        f"- 有候选建议样例数：`{summary.get('suggested_case_count') or 0}`",
        f"- 建议覆盖率：`{summary.get('suggestion_rate') or 0}`",
        "",
        "## 建议明细",
        "",
    ]
    for row in suggestions.get("rows") or []:
        lines.extend(
            [
                f"### {row.get('case_id')}",
                "",
                f"- query：`{row.get('query') or ''}`",
                f"- 期望证据：{row.get('expected_evidence') or ''}",
                "",
                "| score | doc_uid | chunk_id | 文档 | 标题路径 | 位置 | 摘要 |",
                "|---:|---|---|---|---|---|---|",
            ]
        )
        candidates = row.get("candidates") or []
        if not candidates:
            lines.append("| 0 | - | - | - | - | - | - |")
        for candidate in candidates:
            lines.append(
                "| {score} | {doc_uid} | {chunk_id} | {doc_title} | {heading_path} | {source_anchor} | {excerpt} |".format(
                    score=_format_metric(candidate.get("score")),
                    doc_uid=_escape_markdown_cell(candidate.get("doc_uid")),
                    chunk_id=_escape_markdown_cell(candidate.get("chunk_id")),
                    doc_title=_escape_markdown_cell(candidate.get("doc_title")),
                    heading_path=_escape_markdown_cell(candidate.get("heading_path")),
                    source_anchor=_escape_markdown_cell(candidate.get("source_anchor")),
                    excerpt=_escape_markdown_cell(candidate.get("content_excerpt")),
                )
            )
        lines.append("")
    return "\r\n".join(lines).strip() + "\r\n"


def _build_retrieval_summary(rows: list[dict]) -> dict:
    """汇总检索评测指标。"""

    case_count = len(rows)
    hit_count = sum(1 for row in rows if row["top_k_hit"])
    traceable_count = sum(1 for row in rows if row["traceable"])
    reranked_count = sum(1 for row in rows if row.get("reranked"))
    degraded_count = sum(1 for row in rows if row.get("degraded"))
    ranked_summary = evaluate_ranked_rows(rows)["summary"]
    return {
        "case_count": case_count,
        "top_k_hit_count": hit_count,
        "top_k_hit_rate": _safe_rate(hit_count, case_count),
        "traceable_case_count": traceable_count,
        "traceability_rate": _safe_rate(traceable_count, case_count),
        "rerank_case_count": reranked_count,
        "rerank_coverage_rate": _safe_rate(reranked_count, case_count),
        "degraded_case_count": degraded_count,
        "recall_at_5": ranked_summary["recall_at_5"],
        "mrr_at_10": ranked_summary["mrr_at_10"],
        "ndcg_at_10": ranked_summary["ndcg_at_10"],
        "traceable_rate": ranked_summary["traceable_rate"],
    }


def _build_catalog_item(row: dict) -> dict:
    """构造候选证据目录条目。"""

    start_line = row.get("source_start_line")
    end_line = row.get("source_end_line")
    source_anchor = str(row.get("source_anchor") or "").strip()
    if not source_anchor and start_line is not None and end_line is not None:
        source_anchor = f"L{start_line}-L{end_line}"
    content = str(row.get("content") or "")
    return {
        "knowledge_base_id": row.get("knowledge_base_id") or "",
        "doc_uid": row.get("doc_uid") or "",
        "doc_title": row.get("doc_title") or "",
        "source_name": row.get("source_name") or "",
        "chunk_id": row.get("chunk_id") or "",
        "chunk_index": row.get("chunk_index"),
        "heading_path": row.get("heading_path") or "",
        "source_start_line": start_line,
        "source_end_line": end_line,
        "source_anchor": source_anchor,
        "chunk_type": row.get("chunk_type") or "",
        "content_excerpt": content[:160],
    }


def _score_alignment_candidate(query_text: str, expected_evidence: str, item: dict) -> dict:
    """对单个候选证据进行简单文本重合打分。"""

    query_terms = _tokenize_alignment_text(query_text)
    evidence_terms = _tokenize_alignment_text(expected_evidence)
    target_text = " ".join(
        str(item.get(field) or "")
        for field in ("doc_title", "heading_path", "content_excerpt")
    )
    target_terms = _tokenize_alignment_text(target_text)
    query_score = len(query_terms.intersection(target_terms)) * 2
    evidence_score = len(evidence_terms.intersection(target_terms))
    score = query_score + evidence_score
    return {
        "score": score,
        "doc_uid": item.get("doc_uid") or "",
        "chunk_id": item.get("chunk_id") or "",
        "doc_title": item.get("doc_title") or "",
        "heading_path": item.get("heading_path") or "",
        "source_anchor": item.get("source_anchor") or "",
        "content_excerpt": item.get("content_excerpt") or "",
    }


def _tokenize_alignment_text(text: str) -> set[str]:
    """把中英文混合文本切成适合粗排的词集合。"""

    raw = str(text or "").lower()
    ascii_terms = {term for term in re.findall(r"[a-z0-9_]+", raw) if len(term) >= 2}
    cjk_terms = {term for term in re.split(r"[\s，。！？；：、“”‘’\"'（）()\[\]{}<>《》]+", raw) if len(term) >= 2}
    bigrams = {
        raw[index : index + 2]
        for index in range(max(len(raw) - 1, 0))
        if all("\u4e00" <= char <= "\u9fff" for char in raw[index : index + 2])
    }
    return ascii_terms.union(cjk_terms).union(bigrams)


def _format_retrieval_rows(rows: list[dict]) -> list[str]:
    """格式化检索评测明细。"""

    lines = [
        "## 检索样例明细",
        "",
        "| case_id | query | hit | traceable |",
        "|---|---|---:|---:|",
    ]
    if not rows:
        lines.extend(["| - | - | - | - |", ""])
        return lines
    for row in rows[:50]:
        lines.append(
            "| {case_id} | {query} | {hit} | {traceable} |".format(
                case_id=_escape_markdown_cell(row.get("case_id")),
                query=_escape_markdown_cell(row.get("query")),
                hit=_format_bool(row.get("top_k_hit")),
                traceable=_format_bool(row.get("traceable")),
            )
        )
    lines.append("")
    return lines


def _format_claim_rows(rows: list[dict]) -> list[str]:
    """格式化 Claim 评测明细。"""

    lines = [
        "## Claim 样例明细",
        "",
        "| case_id | check_id | claim | expected | actual | matched |",
        "|---|---|---|---|---|---:|",
    ]
    if not rows:
        lines.extend(["| - | - | - | - | - | - |", ""])
        return lines
    for row in rows[:50]:
        lines.append(
            "| {case_id} | {check_id} | {claim} | {expected} | {actual} | {matched} |".format(
                case_id=_escape_markdown_cell(row.get("case_id")),
                check_id=_escape_markdown_cell(row.get("check_id")),
                claim=_escape_markdown_cell(row.get("claim_text")),
                expected=_escape_markdown_cell(row.get("expected_verdict")),
                actual=_escape_markdown_cell(row.get("actual_verdict")),
                matched=_format_bool(row.get("verdict_matched")),
            )
        )
    lines.append("")
    return lines


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

    return bool(
        item.get("heading_path")
        and item.get("source_start_line") is not None
        and item.get("chunk_type")
    )


def _safe_rate(numerator: int, denominator: int) -> float:
    """安全计算比例，统一保留四位小数。"""

    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _format_metric(value: object) -> str:
    """格式化指标值。"""

    if value is None:
        return "0"
    return str(value)


def _format_bool(value: object) -> str:
    """格式化布尔值。"""

    return "是" if bool(value) else "否"


def _escape_markdown_cell(value: object) -> str:
    """转义 Markdown 表格单元格中的竖线。"""

    return str(value or "").replace("|", "\\|")
