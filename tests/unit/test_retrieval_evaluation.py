"""程序说明：验证离线检索与 Claim 评测指标计算。"""

from __future__ import annotations

from pathlib import Path

from src.retrieval.evaluation import (
    evaluate_claim_results,
    evaluate_retrieval_cases,
    load_jsonl_cases,
)


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
            }
        ][:top_k]


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
    assert result["rows"][0]["top_k_hit"] is True
    assert result["rows"][1]["top_k_hit"] is False


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
