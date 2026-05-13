"""程序说明：验证人工审核服务的写入、删除与状态回退逻辑。"""

from pathlib import Path

import pytest

from src.common.errors import NotFoundAppError
from src.db.connection import create_connection, initialize_database
from src.db.repositories import QualityRepository
from src.review.service import ReviewService


def _create_review_target_claim(repository: QualityRepository, *, check_id: str, claim_id: str) -> None:
    """创建可供人工审核使用的测试 Claim。"""

    repository.create_quality_result(
        quality_check={
            "check_id": check_id,
            "input_text": "测试输入",
            "template_id": "template_demo",
            "template_name": "测试模板",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "需要人工复核",
            "created_at": "2026-05-01T10:00:00+00:00",
            "updated_at": "2026-05-01T10:00:00+00:00",
        },
        claims=[
            {
                "claim_id": claim_id,
                "check_id": check_id,
                "claim_text": "测试 Claim",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.8,
                "evidence": "测试证据",
                "evidence_details": [
                    {
                        "chunk_id": "chunk_review_1",
                        "doc_uid": "doc_review_1",
                        "doc_title": "测试文档",
                        "source_span": "section-1",
                        "retrieval_source": "vector",
                        "matched_sources": ["vector"],
                        "matched_queries": ["claim_literal"],
                        "rerank_score": 0.91,
                        "context_mode": "section_context",
                        "section_title": "测试章节",
                        "evidence_relation": "support",
                        "relation_reason": "直接支持测试 Claim。",
                        "content_preview": "测试证据详情",
                    }
                ],
                "source_doc": "测试文档",
                "source_span": "section-1",
                "review_status": "pending",
                "created_at": "2026-05-01T10:00:00+00:00",
                "updated_at": "2026-05-01T10:00:00+00:00",
            }
        ],
        rule_hits=[],
    )


def test_delete_review_should_restore_previous_claim_status(tmp_path: Path) -> None:
    """删除最新审核记录后，应恢复到上一条审核状态。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    repository = QualityRepository(database_path)
    review_service = ReviewService(database_path)
    _create_review_target_claim(repository, check_id="check_restore", claim_id="claim_restore")

    repository.insert_review_record(
        {
            "review_id": "rev_restore_1",
            "claim_id": "claim_restore",
            "review_action": "approved",
            "reviewed_verdict": None,
            "review_note": "第一轮通过",
            "reviewer": "tester",
            "created_at": "2026-05-01T10:10:00+00:00",
        }
    )
    repository.insert_review_record(
        {
            "review_id": "rev_restore_2",
            "claim_id": "claim_restore",
            "review_action": "rejected",
            "reviewed_verdict": None,
            "review_note": "第二轮驳回",
            "reviewer": "tester",
            "created_at": "2026-05-01T10:20:00+00:00",
        }
    )

    deleted_record = review_service.delete_review("rev_restore_2")
    review_items, total = review_service.list_reviews()
    result = repository.get_quality_result("check_restore")

    assert deleted_record["review_id"] == "rev_restore_2"
    assert deleted_record["restored_review_status"] == "approved"
    assert total == 1
    assert review_items[0]["review_id"] == "rev_restore_1"
    assert result is not None
    assert result["claims"][0]["review_status"] == "approved"


def test_delete_review_should_reset_claim_status_to_pending(tmp_path: Path) -> None:
    """删除某个 Claim 的最后一条审核记录后，应回到待处理状态。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    repository = QualityRepository(database_path)
    review_service = ReviewService(database_path)
    _create_review_target_claim(repository, check_id="check_pending", claim_id="claim_pending")

    repository.insert_review_record(
        {
            "review_id": "rev_pending_1",
            "claim_id": "claim_pending",
            "review_action": "approved",
            "reviewed_verdict": None,
            "review_note": "确认通过",
            "reviewer": "tester",
            "created_at": "2026-05-01T11:10:00+00:00",
        }
    )

    deleted_record = review_service.delete_review("rev_pending_1")
    review_items, total = review_service.list_reviews()
    result = repository.get_quality_result("check_pending")

    assert deleted_record["review_id"] == "rev_pending_1"
    assert deleted_record["restored_review_status"] == "pending"
    assert total == 0
    assert review_items == []
    assert result is not None
    assert result["claims"][0]["review_status"] == "pending"


def test_quality_result_and_recent_results_should_preserve_evidence_details(tmp_path: Path) -> None:
    """质检结果与最近质检记录回读时应保留完整证据明细。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    repository = QualityRepository(database_path)
    _create_review_target_claim(repository, check_id="check_evidence", claim_id="claim_evidence")

    quality_result = repository.get_quality_result("check_evidence")
    recent_results = repository.list_recent_quality_results(limit=10)
    review_candidates = repository.list_review_candidates(limit=10)

    assert quality_result is not None
    assert quality_result["claims"][0]["evidence_details"][0]["chunk_id"] == "chunk_review_1"
    assert quality_result["claims"][0]["evidence_details"][0]["content_preview"] == "测试证据详情"
    assert recent_results[0]["claims"][0]["evidence_details"][0]["chunk_id"] == "chunk_review_1"
    assert review_candidates[0]["evidence_details"][0]["retrieval_source"] == "vector"


def test_delete_review_should_raise_not_found_for_missing_record(tmp_path: Path) -> None:
    """删除不存在的审核记录时，应抛出明确异常。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    review_service = ReviewService(database_path)

    with pytest.raises(NotFoundAppError, match="审核记录不存在"):
        review_service.delete_review("rev_missing")


def test_review_records_should_cascade_when_quality_check_deleted(tmp_path: Path) -> None:
    """删除上游质检记录后，不应残留孤儿审核记录。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    repository = QualityRepository(database_path)
    _create_review_target_claim(repository, check_id="check_cascade", claim_id="claim_cascade")
    repository.insert_review_record(
        {
            "review_id": "rev_cascade_1",
            "claim_id": "claim_cascade",
            "review_action": "approved",
            "reviewed_verdict": None,
            "review_note": "用于级联删除测试",
            "reviewer": "tester",
            "created_at": "2026-05-01T12:00:00+00:00",
        }
    )

    with create_connection(database_path) as connection:
        connection.execute("DELETE FROM quality_checks WHERE check_id = ?", ("check_cascade",))
        connection.commit()
        review_count = connection.execute("SELECT COUNT(1) FROM review_records WHERE claim_id = ?", ("claim_cascade",)).fetchone()[0]
        claim_count = connection.execute("SELECT COUNT(1) FROM quality_claims WHERE claim_id = ?", ("claim_cascade",)).fetchone()[0]

    assert claim_count == 0
    assert review_count == 0


def test_list_review_candidates_should_prioritize_recently_updated_processed_claims(tmp_path: Path) -> None:
    """刚处理的旧 Claim 在已处理分组中应按最新更新时间靠前。"""

    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    repository = QualityRepository(database_path)
    review_service = ReviewService(database_path)

    repository.create_quality_result(
        quality_check={
            "check_id": "check_old",
            "input_text": "旧 Claim 输入",
            "template_id": "template_demo",
            "template_name": "测试模板",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "需要人工复核",
            "created_at": "2026-05-01T09:00:00+00:00",
            "updated_at": "2026-05-01T09:00:00+00:00",
        },
        claims=[
            {
                "claim_id": "claim_old",
                "check_id": "check_old",
                "claim_text": "旧 Claim",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.8,
                "evidence": "旧证据",
                "source_doc": "旧文档",
                "source_span": "section-old",
                "review_status": "pending",
                "created_at": "2026-05-01T09:00:00+00:00",
                "updated_at": "2026-05-01T09:00:00+00:00",
            }
        ],
        rule_hits=[],
    )
    repository.create_quality_result(
        quality_check={
            "check_id": "check_newer",
            "input_text": "较新 Claim 输入",
            "template_id": "template_demo",
            "template_name": "测试模板",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "需要人工复核",
            "created_at": "2026-05-01T10:00:00+00:00",
            "updated_at": "2026-05-01T10:00:00+00:00",
        },
        claims=[
            {
                "claim_id": "claim_newer",
                "check_id": "check_newer",
                "claim_text": "较新 Claim",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.8,
                "evidence": "较新证据",
                "source_doc": "较新文档",
                "source_span": "section-newer",
                "review_status": "pending",
                "created_at": "2026-05-01T10:00:00+00:00",
                "updated_at": "2026-05-01T10:00:00+00:00",
            }
        ],
        rule_hits=[],
    )

    repository.insert_review_record(
        {
            "review_id": "rev_newer_first",
            "claim_id": "claim_newer",
            "review_action": "rejected",
            "reviewed_verdict": None,
            "review_note": "较早处理",
            "reviewer": "tester",
            "created_at": "2026-05-01T10:30:00+00:00",
        }
    )
    repository.insert_review_record(
        {
            "review_id": "rev_old_later",
            "claim_id": "claim_old",
            "review_action": "approved",
            "reviewed_verdict": None,
            "review_note": "刚处理完成",
            "reviewer": "tester",
            "created_at": "2026-05-01T11:30:00+00:00",
        }
    )

    candidate_items = review_service.list_review_candidates(limit=10)

    assert [item["claim_id"] for item in candidate_items] == ["claim_old", "claim_newer"]
    assert candidate_items[0]["review_status"] == "approved"
    assert candidate_items[1]["review_status"] == "rejected"
