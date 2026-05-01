"""程序说明：验证 UI 视图数据转换逻辑。"""

from pathlib import Path

from src.ui.viewmodels import (
    build_claim_evidence_rows,
    build_database_summary_rows,
    build_quality_claim_rows,
    build_recent_quality_rows,
    build_review_history_rows,
    build_search_result_rows,
    build_claim_detail_map,
    build_document_action_updates,
    build_recent_claim_navigation,
    build_doc_uid_choices,
    build_document_management_state,
    build_document_choices,
    build_template_choices,
    format_ingest_result,
    format_search_help_html,
    format_search_result_detail_html,
    format_search_results,
    format_quality_result,
    format_recent_quality_checks,
    format_claim_detail_for_review,
    format_claim_detail_html,
    format_claim_detail_markdown,
    format_database_summary_html,
    format_database_summary_markdown,
    format_document_detail_html,
    format_document_detail_markdown,
    format_document_summary_html,
    format_document_summary_markdown,
    format_operation_result_html,
    format_operation_result_markdown,
    format_review_history,
    get_document_detail,
    get_claim_detail,
    get_review_target_claim_id,
    parse_claim_choice,
    parse_review_choice,
    parse_template_choice,
    parse_document_choice,
    normalize_search_query,
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
    assert documents[0]["size_display"]
    assert Path(documents[0]["file_path"]).is_absolute()


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
        [{"file_name": "a1.md", "file_type": "md", "file_path": "C:/Input/a1.md", "size_display": "1.0 KB"}],
        [{"doc_uid": "doc_1", "doc_title": "标题一", "source_path": "C:/Input/a1.md", "index_status": "indexed"}],
    )

    assert state["scan_summary"]["total_files"] == 1
    assert parse_document_choice(state["document_choices"][0]) == str(Path("C:/Input/a1.md").resolve())
    assert state["status_items"] == [{"doc_uid": "doc_1", "doc_title": "标题一", "source_path": "C:/Input/a1.md", "index_status": "indexed"}]
    assert state["rebuild_choices"] == ["doc_1 | 标题一"]
    assert state["selected_detail"]["registered_label"] == "是"


def test_document_markdown_helpers_should_generate_human_readable_text() -> None:
    """文档概览与详情应转换为普通用户可读的中文摘要。"""

    summary_markdown = format_document_summary_markdown(
        {
            "total_files": 2,
            "registered_files": 2,
            "pending_register_files": 0,
            "needs_rebuild_files": 0,
        }
    )
    detail_markdown = format_document_detail_markdown(
        {
            "file_name": "a1.md",
            "doc_title": "阿胶历史文化通典",
            "size_display": "588.4 KB",
            "registered_label": "是",
            "index_status": "indexed",
            "needs_rebuild_label": "否",
            "action_hint": "已就绪",
            "source_path": "C:/Input/a1.md",
        }
    )

    assert "文档总数：2" in summary_markdown
    assert "全部文档已注册" in summary_markdown
    assert "文件名：a1.md" in detail_markdown
    assert "当前状态：已就绪" in detail_markdown


def test_document_html_helpers_should_generate_card_layout() -> None:
    """文档概览与详情应支持卡片式 HTML 展示。"""

    summary_html = format_document_summary_html(
        {
            "total_files": 2,
            "registered_files": 2,
            "pending_register_files": 0,
            "needs_rebuild_files": 0,
        }
    )
    detail_html = format_document_detail_html(
        {
            "file_name": "a1.md",
            "doc_title": "阿胶历史文化通典",
            "size_display": "588.4 KB",
            "registered_label": "是",
            "index_status": "indexed",
            "needs_rebuild_label": "否",
            "action_hint": "已就绪",
            "source_path": "C:/Input/a1.md",
        }
    )

    assert "<div" in summary_html
    assert "文档概览" in summary_html
    assert "全部文档已注册" in summary_html
    assert "<div" in detail_html
    assert "文件名" in detail_html
    assert "阿胶历史文化通典" in detail_html
    assert "var(--body-text-color)" in summary_html
    assert "min-height:260px" in summary_html


def test_database_summary_helpers_should_generate_natural_language_text() -> None:
    """数据库状态应转换为用户可读摘要与表格。"""

    summary_markdown = format_database_summary_markdown(
        {
            "document_count": 2,
            "completed_document_count": 2,
            "indexed_document_count": 2,
            "rebuild_pending_document_count": 0,
            "failed_document_count": 0,
            "chunk_count": 128,
            "section_count": 16,
            "quality_check_count": 3,
            "claim_count": 12,
            "review_count": 5,
        }
    )
    summary_rows = build_database_summary_rows(
        {
            "document_count": 2,
            "completed_document_count": 2,
            "indexed_document_count": 2,
            "rebuild_pending_document_count": 0,
            "failed_document_count": 0,
            "chunk_count": 128,
            "section_count": 16,
            "quality_check_count": 3,
            "claim_count": 12,
            "review_count": 5,
        }
    )

    assert "当前数据库已入库 2 篇文档" in summary_markdown
    assert "生成 128 条分块" in summary_markdown
    assert "12 条 Claim" in summary_markdown
    assert ["已入库文档", "2"] in summary_rows
    assert ["分块总数", "128"] in summary_rows
    assert ["审核记录", "5"] in summary_rows


def test_database_summary_html_should_generate_card_layout() -> None:
    """数据库状态应支持卡片式 HTML 展示。"""

    summary_html = format_database_summary_html(
        {
            "document_count": 2,
            "completed_document_count": 2,
            "indexed_document_count": 2,
            "rebuild_pending_document_count": 0,
            "failed_document_count": 0,
            "chunk_count": 128,
            "section_count": 16,
            "quality_check_count": 3,
            "claim_count": 12,
            "review_count": 5,
        }
    )

    assert "<div" in summary_html
    assert "数据库状态" in summary_html
    assert "分块总数" in summary_html
    assert "Claim 总数" in summary_html
    assert "var(--block-background-fill)" in summary_html
    assert "min-height:260px" in summary_html


def test_search_helpers_should_normalize_query_and_build_help_panel() -> None:
    """检索页应提供清晰规则说明，并规范化多组关键词输入。"""

    normalized = normalize_search_query("阿胶， 补血； 驴皮  \n 古籍")
    help_html = format_search_help_html()

    assert normalized == "阿胶 补血 驴皮 古籍"
    assert "支持关键词、短语、整句" in help_html
    assert "不支持正则表达式" in help_html
    assert "多组关键词" in help_html
    assert "font-size:20px" not in help_html
    assert "font-size:18px" not in help_html


def test_build_document_management_state_should_merge_relative_and_absolute_paths() -> None:
    """相对路径和绝对路径指向同一文件时不应重复显示。"""

    state = build_document_management_state(
        [{"file_name": "a1.md", "file_type": "md", "file_path": "Input/a1.md", "size_display": "1.0 KB"}],
        [{"doc_uid": "doc_1", "doc_title": "标题一", "source_path": str(Path("Input/a1.md").resolve()), "index_status": "indexed"}],
    )

    assert len(state["table_rows"]) == 1
    assert len(state["document_choices"]) == 1
    assert state["selected_detail"]["registered_label"] == "是"


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


def test_search_display_helpers_should_build_readable_rows() -> None:
    """检索结果应转换为适合表格展示的行数据。"""

    formatted = format_search_results(
        [
            {
                "chunk_id": "chunk_1",
                "doc_uid": "doc_1",
                "doc_title": "标题一",
                "source_name": "来源库",
                "retrieval_source": "hybrid",
                "matched_sources": ["fulltext", "vector"],
                "score": 0.75,
                "rerank_score": 0.95,
                "content": "这是一段很长的检索内容",
            }
        ],
        query_text="很长 检索",
    )

    rows = build_search_result_rows(formatted)

    assert rows == [["1", "标题一", "-", "chunk_1", "hybrid", "0.750", "0.950", "fulltext、vector", "这是一段<mark>很长</mark>的<mark>检索</mark>内容"]]


def test_search_display_helpers_should_mark_selected_row() -> None:
    """选中检索结果时应为当前行添加可见高亮。"""

    formatted = format_search_results(
        [
            {
                "chunk_id": "chunk_1",
                "doc_uid": "doc_1",
                "doc_title": "标题一",
                "source_name": "来源库",
                "retrieval_source": "hybrid",
                "matched_sources": ["fulltext"],
                "score": 0.75,
                "rerank_score": 0.95,
                "content": "第一段内容",
            },
            {
                "chunk_id": "chunk_2",
                "doc_uid": "doc_2",
                "doc_title": "标题二",
                "source_name": "来源库",
                "retrieval_source": "vector",
                "matched_sources": ["vector"],
                "score": 0.66,
                "rerank_score": 0.88,
                "content": "第二段内容",
            },
        ]
    )

    rows = build_search_result_rows(formatted, selected_row_index=1)

    assert rows[0][0] == "1"
    assert "search-result-cell-selected" in rows[1][0]
    assert "search-result-cell-selected-first" in rows[1][0]
    assert "标题二" in rows[1][1]


def test_search_result_detail_html_should_include_original_content() -> None:
    """点击检索结果后应能展示原文详情。"""

    formatted = format_search_results(
        [
            {
                "chunk_id": "chunk_1",
                "doc_uid": "doc_1",
                "doc_title": "阿胶文献",
                "source_name": "来源库",
                "source_span": "卷一 / 第3段",
                "retrieval_source": "hybrid",
                "matched_sources": ["fulltext", "vector"],
                "score": 0.91,
                "rerank_score": 0.93,
                "content": "阿胶有补血作用，古籍中常用于调理。",
            }
        ],
        query_text="阿胶 补血",
    )

    detail_html = format_search_result_detail_html(formatted["items"][0], query_text="阿胶 补血")

    assert "原文详情" in detail_html
    assert "阿胶文献" in detail_html
    assert "chunk_1" in detail_html
    assert "卷一 / 第3段" in detail_html
    assert "<mark>阿胶</mark>" in detail_html
    assert "<mark>补血</mark>" in detail_html
    assert "font-size:20px" not in detail_html
    assert "font-size:18px" not in detail_html


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


def test_claim_display_helpers_should_generate_markdown_and_rows() -> None:
    """Claim 详情应转换为中文摘要与证据表行。"""

    detail_markdown = format_claim_detail_markdown(
        {
            "summary": {
                "claim_id": "claim_1",
                "claim_text": "第一条结论",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.5,
                "review_status": "pending",
                "source_doc": "标题一",
                "source_span": "章节1",
                "evidence": "证据摘要",
                "evidence_reason": "heuristic",
            },
            "evidence_count": 1,
        }
    )
    evidence_rows = build_claim_evidence_rows(
        {
            "evidence_table": [
                {
                    "chunk_id": "chk_1",
                    "doc_title": "标题一",
                    "source_span": "章节1",
                    "retrieval_source": "hybrid",
                    "matched_sources": ["fulltext", "vector"],
                    "rerank_score": 0.91,
                    "content_preview": "证据内容",
                }
            ]
        }
    )

    assert "Claim ID：claim_1" in detail_markdown
    assert "证据条数：1" in detail_markdown
    assert evidence_rows == [["chk_1", "标题一", "章节1", "hybrid", "fulltext、vector", "0.910", "证据内容"]]


def test_claim_detail_html_should_generate_card_layout() -> None:
    """Claim 详情应支持卡片式 HTML 展示。"""

    detail_html = format_claim_detail_html(
        {
            "summary": {
                "claim_id": "claim_1",
                "claim_text": "第一条结论",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.5,
                "review_status": "pending",
                "source_doc": "标题一",
                "source_span": "章节1",
                "evidence": "证据摘要",
                "evidence_reason": "heuristic",
            },
            "evidence_count": 1,
        }
    )

    assert "<div" in detail_html
    assert "Claim 详情" in detail_html
    assert "claim_1" in detail_html
    assert "证据条数" in detail_html


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


def test_operation_and_history_display_helpers_should_generate_readable_content() -> None:
    """操作结果、质检记录和审核记录应转换为可读文本与表格。"""

    operation_markdown = format_operation_result_markdown(
        {
            "success": True,
            "message": "处理完成",
            "progress_summary": {
                "step_count": 2,
                "last_stage": "completed",
                "last_percent": 100,
            },
        },
        title="注册结果",
    )
    quality_rows = build_recent_quality_rows(
        [
            {
                "check_id": "check_1",
                "template_name": "严格证据核验",
                "overall_verdict": "needs_review",
                "created_at": "2026-04-30T12:00:00Z",
                "input_text": "测试输入",
                "claims": [{"claim_id": "claim_1"}, {"claim_id": "claim_2"}],
            }
        ]
    )
    review_rows = build_review_history_rows(
        {
            "items": [
                {
                    "review_id": "rev_1",
                    "claim_id": "claim_1",
                    "review_action": "approved",
                    "review_status": "approved",
                    "reviewer": "tester",
                    "created_at": "2026-04-30T12:30:00Z",
                    "review_note": "通过",
                    "claim_text": "第一条结论",
                }
            ]
        }
    )

    assert "执行状态：成功" in operation_markdown
    assert "最后进度：100%" in operation_markdown
    assert quality_rows == [["check_1", "严格证据核验", "needs_review", "2", "2026-04-30T12:00:00Z", "测试输入"]]
    assert review_rows == [["rev_1", "claim_1", "approved", "approved", "tester", "2026-04-30T12:30:00Z", "通过", "第一条结论"]]


def test_operation_result_html_should_generate_card_layout() -> None:
    """操作结果应支持卡片式 HTML 展示。"""

    operation_html = format_operation_result_html(
        {
            "success": True,
            "message": "处理完成",
            "progress_summary": {
                "step_count": 2,
                "last_stage": "completed",
                "last_percent": 100,
            },
        },
        title="注册结果",
    )

    assert "<div" in operation_html
    assert "注册结果" in operation_html
    assert "处理完成" in operation_html
    assert "最后进度" in operation_html


def test_operation_result_html_should_show_pending_state_when_not_started() -> None:
    """未执行前不应显示失败，而应显示未开始。"""

    operation_html = format_operation_result_html(None, title="注册结果")

    assert "暂无执行记录" in operation_html
    assert "未开始" in operation_html
    assert "失败" not in operation_html


def test_document_management_helpers_should_return_detail_and_button_states() -> None:
    """文档管理辅助函数应能返回详情与按钮状态。"""

    state = build_document_management_state(
        [{"file_name": "a1.md", "file_type": "md", "file_path": "C:/Input/a1.md", "size_display": "1.0 KB"}],
        [],
    )

    detail = get_document_detail(state["document_choices"][0], state["document_detail_map"])
    register_state, rebuild_state = build_document_action_updates(detail)

    assert detail["registered_label"] == "否"
    assert register_state["interactive"] is True
    assert rebuild_state["interactive"] is False


def test_format_ingest_result_should_include_progress_summary() -> None:
    """入库结果应附带进度摘要。"""

    result = format_ingest_result(
        {"success": True},
        [
            {"stage": "prepare", "percent": 5},
            {"stage": "completed", "percent": 100},
        ],
    )

    assert result["progress_summary"]["step_count"] == 2
    assert result["progress_summary"]["last_percent"] == 100


def test_quality_display_helpers_should_build_claim_rows() -> None:
    """质检结果应能转换为适合普通用户阅读的表格行。"""

    formatted = format_quality_result(
        {
            "check": {
                "summary": "需要人工复核",
                "template_name": "严格证据核验",
            },
            "claims": [
                {
                    "claim_id": "claim_1",
                    "claim_text": "第一条结论",
                    "verdict": "needs_review",
                    "risk_level": "medium",
                    "confidence": 0.55,
                    "source_doc": "标题一",
                    "source_span": "章节1",
                }
            ],
        }
    )

    rows = build_quality_claim_rows(formatted)

    assert rows == [["claim_1", "第一条结论", "needs_review", "medium", "0.550", "标题一", "章节1"]]
