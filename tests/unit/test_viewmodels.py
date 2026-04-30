"""程序说明：验证 UI 视图数据转换逻辑。"""

from pathlib import Path

from src.ui.viewmodels import (
    build_claim_detail_map,
    build_recent_claim_navigation,
    build_doc_uid_choices,
    build_document_management_state,
    build_document_choices,
    build_template_choices,
    format_search_results,
    format_quality_result,
    format_recent_quality_checks,
    format_claim_detail_for_review,
    format_review_history,
    get_claim_detail,
    get_review_target_claim_id,
    parse_claim_choice,
    parse_review_choice,
    parse_template_choice,
    parse_document_choice,
    scan_input_documents,
)


def test_scan_input_documents_should_only_return_md_and_json(tmp_path: Path) -> None:
    """应只扫描业务输入目录中的 md 和 json 文件。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    (input_root / "a1.md").write_text("# 文档一", encoding="utf-8")
    (input_root / "a2.json").write_text("{}", encoding="utf-8")
    (input_root / "ignore.txt").write_text("x", encoding="utf-8")

    documents = scan_input_documents(input_root)
    choices = build_document_choices(documents)

    assert len(documents) == 2
    assert len(choices) == 2
    assert parse_document_choice(choices[0]).endswith((".md", ".json"))


def test_format_quality_result_should_build_claim_choices() -> None:
    """质检结果应转换为便于审核的 claim 选项。"""

    formatted = format_quality_result(
        {
            "check": {"summary": "测试摘要"},
            "claims": [
                {
                    "claim_id": "claim_1",
                    "claim_text": "第一条结论",
                    "verdict": "needs_review",
                    "risk_level": "medium",
                    "confidence": 0.55,
                    "source_doc": "doc_1",
                    "source_span": "section-1:chunk-0",
                    "evidence_details": [{"chunk_id": "chk_1", "rerank_score": 0.88}],
                }
            ],
            "rule_hits": [{"rule_code": "R001"}],
        }
    )

    assert formatted["summary"] == "测试摘要"
    assert formatted["claim_choices"]
    assert parse_claim_choice(formatted["claim_choices"][0]) == "claim_1"
    assert formatted["claims_table"][0]["evidence_details"][0]["chunk_id"] == "chk_1"


def test_recent_quality_helpers_should_build_reviewable_choices() -> None:
    """最近质检结果应能转换为 claim 下拉选项与文档重建选项。"""

    quality_results = [
        {
            "check_id": "check_1",
            "overall_verdict": "needs_review",
            "input_text": "测试输入",
            "created_at": "2026-04-30T12:00:00Z",
            "claims": [
                {
                    "claim_id": "claim_1",
                    "claim_text": "第一条",
                    "verdict": "needs_review",
                    "risk_level": "medium",
                }
            ],
        }
    ]

    formatted_checks = format_recent_quality_checks(quality_results)
    doc_uid_choices = build_doc_uid_choices(
        [{"doc_uid": "doc_1", "doc_title": "标题一"}, {"doc_uid": "doc_2", "doc_title": "标题二"}]
    )

    assert formatted_checks[0]["check_id"] == "check_1"
    assert formatted_checks[0]["claim_choices"]
    assert formatted_checks[0]["claim_detail_map"]["claim_1"]["claim_text"] == "第一条"
    assert parse_claim_choice(formatted_checks[0]["claim_choices"][0]) == "claim_1"
    assert "pending" in formatted_checks[0]["claim_choices"][0]
    assert doc_uid_choices == ["doc_1 | 标题一", "doc_2 | 标题二"]


def test_parse_doc_uid_choice_should_return_doc_uid() -> None:
    """应能从重建下拉项中解析 doc_uid。"""

    from src.ui.viewmodels import parse_doc_uid_choice

    assert parse_doc_uid_choice("doc_1 | 标题一") == "doc_1"


def test_build_document_management_state_should_include_rebuild_choices() -> None:
    """文档管理页状态应同时包含扫描结果与重建选项。"""

    state = build_document_management_state(
        [{"file_name": "a1.md", "file_type": "md", "file_path": "C:/Input/a1.md"}],
        [{"doc_uid": "doc_1", "doc_title": "标题一"}],
    )

    assert state["scan_summary"]["count"] == 1
    assert state["document_choices"] == ["a1.md | md | C:/Input/a1.md"]
    assert state["status_items"] == [{"doc_uid": "doc_1", "doc_title": "标题一"}]
    assert state["rebuild_choices"] == ["doc_1 | 标题一"]


def test_template_choice_helpers_should_build_and_parse_template_id() -> None:
    """应能构建并解析模板下拉选项。"""

    choices = build_template_choices(
        [{"template_id": "general_fact_check", "template_name": "通用事实核验"}]
    )

    assert choices == ["general_fact_check | 通用事实核验"]
    assert parse_template_choice(choices[0]) == "general_fact_check"


def test_format_search_results_should_include_rerank_fields() -> None:
    """检索结果格式化后应保留重排和来源字段。"""

    formatted = format_search_results(
        [
            {
                "chunk_id": "chunk_1",
                "doc_uid": "doc_1",
                "doc_title": "标题一",
                "author": "张三",
                "source_name": "来源库",
                "tags": ["古文"],
                "source_span": "章节1",
                "retrieval_source": "hybrid",
                "matched_sources": ["fulltext", "vector"],
                "score": 0.75,
                "rerank_score": 0.95,
                "content": "这是一段很长的检索内容",
            }
        ]
    )

    assert formatted["count"] == 1
    assert formatted["table"][0]["retrieval_source"] == "hybrid"
    assert formatted["table"][0]["matched_sources"] == ["fulltext", "vector"]
    assert formatted["table"][0]["rerank_score"] == 0.95


def test_claim_detail_helpers_should_return_selected_claim_detail() -> None:
    """应能根据下拉选项返回 claim 详情。"""

    detail_map = build_claim_detail_map(
        [
            {
                "claim_id": "claim_1",
                "claim_text": "第一条结论",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.5,
                "evidence": "证据摘要",
                "evidence_reason": "heuristic",
                "evidence_details": [{"chunk_id": "chk_1"}],
            }
        ]
    )

    detail = get_claim_detail("claim_1 | needs_review | 第一条结论", detail_map)

    assert detail["claim_id"] == "claim_1"
    assert detail["evidence_details"][0]["chunk_id"] == "chk_1"


def test_format_claim_detail_for_review_should_build_summary_and_evidence_table() -> None:
    """审核详情格式化后应生成摘要与证据表。"""

    detail_map = build_claim_detail_map(
        [
            {
                "claim_id": "claim_1",
                "claim_text": "第一条结论",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.5,
                "evidence": "证据摘要",
                "evidence_reason": "heuristic",
                "evidence_details": [
                    {
                        "chunk_id": "chk_1",
                        "doc_uid": "doc_1",
                        "doc_title": "标题一",
                        "matched_sources": ["fulltext", "vector"],
                        "rerank_score": 0.9,
                    }
                ],
            }
        ]
    )

    detail = format_claim_detail_for_review("claim_1 | needs_review | 第一条结论", detail_map)

    assert detail["summary"]["claim_id"] == "claim_1"
    assert detail["evidence_count"] == 1
    assert detail["evidence_table"][0]["matched_sources"] == ["fulltext", "vector"]


def test_build_recent_claim_navigation_should_focus_preferred_claim() -> None:
    """最近质检导航应能定位到指定 claim。"""

    navigation = build_recent_claim_navigation(
        [
            {
                "check_id": "check_1",
                "template_name": "严格证据核验",
                "created_at": "2026-04-30T12:00:00Z",
                "claims": [
                    {"claim_id": "claim_1", "claim_text": "第一条", "verdict": "needs_review"},
                    {"claim_id": "claim_2", "claim_text": "第二条", "verdict": "verified"},
                ],
            }
        ],
        preferred_claim_id="claim_2",
    )

    assert navigation["selected_choice"].startswith("claim_2 |")
    assert navigation["selected_detail"]["summary"]["template_name"] == "严格证据核验"


def test_review_history_helpers_should_build_choices_and_target_claim() -> None:
    """审核记录格式化后应可定位回对应 claim。"""

    formatted = format_review_history(
        [
            {
                "review_id": "rev_1",
                "claim_id": "claim_1",
                "check_id": "check_1",
                "template_name": "严格证据核验",
                "claim_text": "第一条结论",
                "review_action": "approved",
                "review_status": "approved",
                "review_note": "通过",
                "reviewer": "tester",
                "created_at": "2026-04-30T12:30:00Z",
            }
        ]
    )

    assert formatted["count"] == 1
    assert parse_review_choice(formatted["review_choices"][0]) == "rev_1"
    assert get_review_target_claim_id(formatted["review_choices"][0], formatted["review_map"]) == "claim_1"
