"""程序说明：验证离线检索与 Claim 评测指标计算。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.db.connection import create_connection, initialize_database
from src.retrieval.evaluation import (
    build_provisional_aligned_cases,
    export_evidence_catalog,
    evaluate_claim_cases,
    evaluate_claim_results,
    evaluate_retrieval_cases,
    evaluate_ranked_rows,
    format_evidence_catalog_markdown,
    format_evaluation_report_markdown,
    load_jsonl_cases,
    suggest_retrieval_case_alignments,
)


def test_build_provisional_aligned_cases_should_use_first_real_chunk_only() -> None:
    """候选对齐集应采用首个真实 chunk，且不使用容易虚高的文档级金标。"""

    markdown = """
### ret_001

| score | doc_uid | chunk_id | 文档 | 标题路径 | 位置 | 摘要 |
|---:|---|---|---|---|---|---|
| 9 | doc_real | chunk_best | 文档 | 路径 | L1-L2 | 最佳候选 |
| 8 | doc_real | chunk_other | 文档 | 路径 | L3-L4 | 次选候选 |
"""

    result = build_provisional_aligned_cases(
        [
            {
                "case_id": "ret_001",
                "query": "阿胶 贫血",
                "expected_doc_uids": ["fake_doc"],
                "expected_chunk_ids": ["fake_chunk"],
            }
        ],
        markdown,
        knowledge_base_id_by_doc_uid={"doc_real": "kb_real"},
    )

    assert result[0]["expected_doc_uids"] == []
    assert result[0]["expected_chunk_ids"] == ["chunk_best"]
    assert result[0]["aligned_candidate_doc_uid"] == "doc_real"
    assert result[0]["knowledge_base_id"] == "kb_real"
    assert result[0]["alignment_status"] == "provisional_first_candidate"


class _FakeRetrievalService:
    """程序说明：用固定返回结果模拟检索服务。"""

    def hybrid_search(self, query: str, top_k: int = 5, knowledge_base_id: str | None = None, **kwargs) -> list[dict]:
        if query == "阿胶 贫血":
            return [
                {
                    "chunk_id": "chk_support",
                    "doc_uid": "doc_ejiao",
                    "content": "阿胶相关证据",
                    "heading_path": "总论 > 功效",
                    "source_start_line": 10,
                    "source_end_line": 12,
                    "chunk_type": "paragraph",
                    "rerank_score": 0.93,
                }
            ][:top_k]
        return [
            {
                "chunk_id": "chk_other",
                "doc_uid": "doc_other",
                "content": "其他证据",
                "heading_path": "",
                "source_start_line": None,
                "source_end_line": None,
                "chunk_type": "",
                "degraded_reason": "rerank_unavailable",
            }
        ][:top_k]


class _FakeQualityService:
    """程序说明：用固定返回结果模拟真实质检服务。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run_check(
        self,
        input_text: str,
        *,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
        template_id: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "input_text": input_text,
                "doc_uid": doc_uid,
                "knowledge_base_id": knowledge_base_id,
                "template_id": template_id,
            }
        )
        if input_text == "阿胶能补血。":
            return {
                "check": {"check_id": "chk_1"},
                "claims": [
                    {
                        "verdict": "verified",
                        "evidence_details": [{"chunk_id": "chunk_1"}],
                    }
                ],
            }
        return {
            "check": {"check_id": "chk_2"},
            "claims": [
                {
                    "verdict": "needs_review",
                    "evidence_details": [],
                }
            ],
        }


def test_load_jsonl_cases_should_skip_blank_lines_and_validate_objects(tmp_path: Path) -> None:
    """JSONL 评测集应跳过空行，并拒绝非对象行。"""

    case_path = tmp_path / "cases.jsonl"
    case_path.write_text('{"case_id":"c1","query":"阿胶"}\n\n[]\n', encoding="utf-8")

    cases = load_jsonl_cases(case_path)

    assert cases == [{"case_id": "c1", "query": "阿胶"}]


def test_evaluate_retrieval_cases_should_report_top_k_hit_and_traceability() -> None:
    """检索评测应输出 Top-K 命中率和证据追溯率。"""

    result = evaluate_retrieval_cases(
        _FakeRetrievalService(),
        [
            {"case_id": "hit", "query": "阿胶 贫血", "expected_chunk_ids": ["chk_support"]},
            {"case_id": "miss", "query": "鹿角胶", "expected_chunk_ids": ["chk_missing"]},
        ],
        top_k=5,
    )

    assert result["summary"]["case_count"] == 2
    assert result["summary"]["top_k_hit_count"] == 1
    assert result["summary"]["top_k_hit_rate"] == 0.5
    assert result["summary"]["traceable_case_count"] == 1
    assert result["summary"]["traceability_rate"] == 0.5
    assert result["summary"]["rerank_coverage_rate"] == 0.5
    assert result["summary"]["degraded_case_count"] == 1
    assert result["rows"][0]["top_k_hit"] is True
    assert result["rows"][1]["top_k_hit"] is False


def test_retrieval_metrics_should_calculate_recall_mrr_and_ndcg() -> None:
    """标准排名指标应按首个相关结果和折损累计增益计算。"""

    result = evaluate_ranked_rows(
        [
            {
                "case_id": "rank_1",
                "expected_chunk_ids": ["a"],
                "returned_chunk_ids": ["a", "x", "y"],
                "traceable": True,
            },
            {
                "case_id": "rank_2",
                "expected_chunk_ids": ["b"],
                "returned_chunk_ids": ["x", "b", "y"],
                "traceable": True,
            },
        ]
    )

    summary = result["summary"]
    assert summary["recall_at_5"] == 1.0
    assert summary["mrr_at_10"] == 0.75
    assert summary["ndcg_at_10"] == pytest.approx(0.8155, abs=0.0001)


def test_evaluate_claim_results_should_report_accuracy_and_no_evidence_verified_rate() -> None:
    """Claim 评测应输出准确率，并统计无证据 verified 风险。"""

    result = evaluate_claim_results(
        [
            {"case_id": "ok", "expected_verdict": "verified"},
            {"case_id": "bad", "expected_verdict": "needs_review"},
        ],
        [
            {"case_id": "ok", "actual_verdict": "verified", "evidence_details": [{"chunk_id": "c1"}]},
            {"case_id": "bad", "actual_verdict": "verified", "evidence_details": []},
        ],
    )

    assert result["summary"]["case_count"] == 2
    assert result["summary"]["verdict_match_count"] == 1
    assert result["summary"]["verdict_accuracy"] == 0.5
    assert result["summary"]["no_evidence_verified_count"] == 1
    assert result["summary"]["no_evidence_verified_rate"] == 0.5


def test_evaluate_claim_cases_should_run_quality_service_and_collect_metrics() -> None:
    """Claim 评测应逐条调用真实质检服务，并保留 check_id 便于回查历史。"""

    service = _FakeQualityService()

    result = evaluate_claim_cases(
        service,
        [
            {"case_id": "claim_hit", "claim_text": "阿胶能补血。", "expected_verdict": "verified"},
            {"case_id": "claim_miss", "claim_text": "阿胶能治疗未知疾病。", "expected_verdict": "rejected"},
        ],
        knowledge_base_id="default",
        template_id="general_fact_check",
    )

    assert result["summary"]["case_count"] == 2
    assert result["summary"]["verdict_match_count"] == 1
    assert result["summary"]["verdict_accuracy"] == 0.5
    assert result["rows"][0]["check_id"] == "chk_1"
    assert result["rows"][0]["has_evidence"] is True
    assert result["rows"][1]["actual_verdict"] == "needs_review"
    assert result["rows"][1]["verdict_matched"] is False
    assert service.calls[0]["knowledge_base_id"] == "default"
    assert service.calls[0]["template_id"] == "general_fact_check"


def test_format_evaluation_report_markdown_should_include_core_metrics() -> None:
    """评测报告 Markdown 应集中展示固定指标和样例明细。"""

    markdown = format_evaluation_report_markdown(
        title="本地评测报告",
        retrieval_result={
            "summary": {
                "case_count": 2,
                "top_k_hit_count": 1,
                "top_k_hit_rate": 0.5,
                "traceable_case_count": 1,
                "traceability_rate": 0.5,
            },
            "rows": [
                {"case_id": "ret_001", "query": "阿胶", "top_k_hit": True, "traceable": True},
            ],
        },
        claim_result={
            "summary": {
                "case_count": 2,
                "verdict_match_count": 1,
                "verdict_accuracy": 0.5,
                "no_evidence_verified_count": 1,
                "no_evidence_verified_rate": 0.5,
            },
            "rows": [
                {
                    "case_id": "claim_001",
                    "claim_text": "阿胶是一种传统中药材料。",
                    "expected_verdict": "verified",
                    "actual_verdict": "verified",
                    "verdict_matched": True,
                    "check_id": "chk_markdown_1",
                },
            ],
        },
    )

    assert "# 本地评测报告" in markdown
    assert "| Top-K 命中率 | 0.5 |" in markdown
    assert "| Claim 准确率 | 0.5 |" in markdown
    assert "| 无证据 verified 率 | 0.5 |" in markdown
    assert "ret_001" in markdown
    assert "claim_001" in markdown
    assert "chk_markdown_1" in markdown


def test_export_evidence_catalog_should_read_traceable_chunks_from_sqlite(tmp_path: Path) -> None:
    """证据目录应从 SQLite 只读导出可用于人工标注的 chunk 元数据。"""

    db_path = tmp_path / "app.db"
    initialize_database(db_path)
    now = "2026-06-20T00:00:00+00:00"
    with create_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                doc_uid, knowledge_base_id, doc_id, doc_title, source_path, source_hash,
                ingest_status, index_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("doc_real", "default", "doc_real", "真实阿胶资料", "default/doc.md", "hash", "completed", "indexed", now, now),
        )
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, doc_uid, section_id, chunk_index, content, source_span,
                heading_path, source_start_line, source_end_line, chunk_type,
                token_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "chunk_real",
                "doc_real",
                None,
                0,
                "阿胶可能与贫血相关人群辅助调理有关。",
                "section-1:chunk-0",
                "总论 > 功效",
                8,
                10,
                "paragraph",
                20,
                now,
                now,
            ),
        )
        connection.commit()

    catalog = export_evidence_catalog(db_path, knowledge_base_id="default", query="阿胶", limit=10)

    assert catalog["summary"]["item_count"] == 1
    assert catalog["items"][0]["doc_uid"] == "doc_real"
    assert catalog["items"][0]["chunk_id"] == "chunk_real"
    assert catalog["items"][0]["heading_path"] == "总论 > 功效"
    assert catalog["items"][0]["source_anchor"] == "L8-L10"


def test_format_evidence_catalog_markdown_should_include_catalog_rows() -> None:
    """证据目录 Markdown 应展示真实 ID 和可人工复核的片段。"""

    markdown = format_evidence_catalog_markdown(
        {
            "summary": {"item_count": 1, "knowledge_base_id": "default", "query": "阿胶"},
            "items": [
                {
                    "doc_uid": "doc_real",
                    "chunk_id": "chunk_real",
                    "doc_title": "真实阿胶资料",
                    "heading_path": "总论 > 功效",
                    "source_anchor": "L8-L10",
                    "content_excerpt": "阿胶可能与贫血相关人群辅助调理有关。",
                }
            ],
        },
        title="证据目录",
    )

    assert "# 证据目录" in markdown
    assert "chunk_real" in markdown
    assert "L8-L10" in markdown
    assert "阿胶可能" in markdown


def test_suggest_retrieval_case_alignments_should_rank_catalog_candidates() -> None:
    """对齐建议应按 query 与候选证据的文本重合度排序，保留真实 ID。"""

    suggestions = suggest_retrieval_case_alignments(
        [
            {"case_id": "ret_001", "query": "阿胶 贫血", "expected_evidence": "贫血相关证据"},
            {"case_id": "ret_002", "query": "鹿角胶 功效", "expected_evidence": "鹿角胶功效"},
        ],
        {
            "items": [
                {
                    "doc_uid": "doc_a",
                    "chunk_id": "chunk_a",
                    "doc_title": "阿胶资料",
                    "heading_path": "总论 > 功效",
                    "source_anchor": "L1-L3",
                    "content_excerpt": "阿胶可能与贫血相关人群辅助调理有关。",
                },
                {
                    "doc_uid": "doc_b",
                    "chunk_id": "chunk_b",
                    "doc_title": "鹿角胶资料",
                    "heading_path": "鹿角胶功效",
                    "source_anchor": "L4-L6",
                    "content_excerpt": "鹿角胶功效说明。",
                },
            ]
        },
        max_candidates=1,
    )

    assert suggestions["summary"]["case_count"] == 2
    assert suggestions["summary"]["suggested_case_count"] == 2
    assert suggestions["rows"][0]["candidates"][0]["chunk_id"] == "chunk_a"
    assert suggestions["rows"][1]["candidates"][0]["chunk_id"] == "chunk_b"
