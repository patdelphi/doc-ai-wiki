"""程序说明：验证 UI 视图数据转换逻辑。"""

from pathlib import Path

from src.ui.viewmodels import (
    build_doc_uid_choices,
    build_document_management_state,
    build_document_choices,
    format_quality_result,
    format_recent_quality_checks,
    parse_claim_choice,
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
                }
            ],
            "rule_hits": [{"rule_code": "R001"}],
        }
    )

    assert formatted["summary"] == "测试摘要"
    assert formatted["claim_choices"]
    assert parse_claim_choice(formatted["claim_choices"][0]) == "claim_1"


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
    assert parse_claim_choice(formatted_checks[0]["claim_choices"][0]) == "claim_1"
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
