"""程序说明：验证最小 UI 可构建。"""

from pathlib import Path

import gradio as gr
import pandas as pd

from src.common.config import AppSettings
from src.db.connection import initialize_database
from src.db.repositories import QualityRepository
from src.ingest.service import IngestService
from src.quality.service import QualityService
from src.review.service import ReviewService
from src.retrieval.service import RetrievalService
from src.retrieval.vector_store import VectorStore
from src.ui.app import create_ui_app
from src.ui.pages import UI_CSS


def test_create_ui_app_should_return_gradio_blocks(tmp_path: Path) -> None:
    """UI 启动入口应返回可用的 Gradio Blocks。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)

    assert isinstance(demo, gr.Blocks)


def test_create_ui_app_should_not_register_startup_load_event(tmp_path: Path) -> None:
    """UI 首屏应直接渲染默认数据，避免依赖启动 load 队列。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    dependencies = demo.config.get("dependencies", [])

    assert all(dep.get("targets") != [(0, "load")] for dep in dependencies)


def test_create_ui_app_should_not_render_raw_json_components(tmp_path: Path) -> None:
    """界面应避免直接向普通用户展示原始 JSON 组件。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    components = demo.config.get("components", [])

    assert all(component.get("type") != "json" for component in components)


def test_create_ui_app_should_include_database_status_module(tmp_path: Path) -> None:
    """文档管理页应包含数据库状态展示模块。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    components = demo.config.get("components", [])
    html_values = [
        str(component.get("props", {}).get("value", ""))
        for component in components
        if component.get("type") == "html"
    ]

    assert any("数据库状态" in value for value in html_values)


def test_create_ui_app_should_use_html_status_panels(tmp_path: Path) -> None:
    """关键状态模块应通过 HTML 卡片展示。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    components = demo.config.get("components", [])
    html_values = [
        str(component.get("props", {}).get("value", ""))
        for component in components
        if component.get("type") == "html"
    ]

    assert any("文档概览" in value for value in html_values)
    assert any("检索结果" in value for value in html_values)
    assert any("质检结果" in value for value in html_values)
    assert any("审核结果" in value for value in html_values)
    assert any("未开始" in value for value in html_values)


def test_create_ui_app_should_configure_search_controls_and_detail_panel(tmp_path: Path) -> None:
    """检索页应按输入说明、结果状态、结果列表、原文详情的顺序布局。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    components = demo.config.get("components", [])
    html_values = [
        str(component.get("props", {}).get("value", ""))
        for component in components
        if component.get("type") == "html"
    ]
    elem_ids = [str(component.get("props", {}).get("elem_id", "")) for component in components]
    sliders = [
        component.get("props", {})
        for component in components
        if component.get("type") == "slider" and component.get("props", {}).get("label") == "返回数量"
    ]
    dataframes = [
        component.get("props", {})
        for component in components
        if component.get("type") == "dataframe" and component.get("props", {}).get("elem_id") == "search-results-table"
    ]

    assert any("支持关键词、短语、整句" in value for value in html_values)
    assert any("原文详情" in value for value in html_values)
    assert sliders
    assert sliders[0].get("value") == 10
    assert sliders[0].get("maximum") == 100
    assert dataframes
    assert dataframes[0].get("headers", [])[0] == "序号"
    assert dataframes[0].get("column_count", [])[0] == 9
    assert "search-input-panel" in elem_ids
    assert "search-top-row" in elem_ids
    assert elem_ids.index("search-help-panel") < elem_ids.index("search-result-summary")
    assert elem_ids.index("search-result-summary") < elem_ids.index("search-results-table")
    assert elem_ids.index("search-results-table") < elem_ids.index("search-result-detail")


def test_create_ui_app_should_configure_quality_help_progress_and_template_panel(tmp_path: Path) -> None:
    """AI 质检页应包含功能说明、模板内容和执行进度模块。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    components = demo.config.get("components", [])
    html_values = [
        str(component.get("props", {}).get("value", ""))
        for component in components
        if component.get("type") == "html"
    ]
    elem_ids = [str(component.get("props", {}).get("elem_id", "")) for component in components]
    labels = [str(component.get("props", {}).get("label", "")) for component in components]

    assert any("AI 质检会把输入内容拆成多条 Claim" in value for value in html_values)
    assert any("模板内容" in value for value in html_values)
    assert any("执行进度" in value for value in html_values)
    assert "可审核 Claim" not in labels
    assert "quality-top-row" in elem_ids
    assert "quality-template-row" in elem_ids
    assert "quality-summary-row" in elem_ids
    assert "quality-claim-row" in elem_ids
    assert "quality-evidence-row" in elem_ids
    assert "quality-history-row" in elem_ids
    assert "quality-help-panel" in elem_ids
    assert "quality-template-panel" in elem_ids
    assert "quality-progress-panel" in elem_ids
    assert "quality-result-panel" in elem_ids
    assert "quality-claims-table" in elem_ids
    assert "quality-recent-table" in elem_ids
    assert "quality-history-panel" in elem_ids
    assert "quality-history-note" in elem_ids
    assert "quality-evidence-table" in elem_ids
    assert "quality-evidence-detail" in elem_ids


def test_create_ui_app_should_preload_recent_quality_records(tmp_path: Path) -> None:
    """AI 质检页进入时应自动显示最近质检记录。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)
    repository = QualityRepository(settings.sqlite_db_path)
    repository.create_quality_result(
        quality_check={
            "check_id": "chkres_demo_001",
            "input_text": "阿胶源于驴皮熬制。",
            "template_id": "ancient_text_review",
            "template_name": "古文审慎解读",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "存在需要人工复核的表述。",
            "created_at": "2026-05-01T12:00:00+00:00",
            "updated_at": "2026-05-01T12:00:00+00:00",
        },
        claims=[
            {
                "claim_id": "claim_demo_001",
                "check_id": "chkres_demo_001",
                "claim_text": "阿胶源于驴皮熬制。",
                "verdict": "supported",
                "risk_level": "medium",
                "confidence": 0.82,
                "evidence": "阿胶的传统制备与驴皮相关。",
                "source_doc": "阿胶历史文献",
                "source_span": "section-1",
                "review_status": "pending",
                "created_at": "2026-05-01T12:00:00+00:00",
                "updated_at": "2026-05-01T12:00:00+00:00",
            }
        ],
        rule_hits=[],
    )

    demo = create_ui_app(settings)
    components = demo.config.get("components", [])
    recent_tables = [
        component.get("props", {})
        for component in components
        if component.get("type") == "dataframe" and component.get("props", {}).get("elem_id") == "quality-recent-table"
    ]
    claim_tables = [
        component.get("props", {})
        for component in components
        if component.get("type") == "dataframe" and component.get("props", {}).get("elem_id") == "quality-claims-table"
    ]

    assert recent_tables
    assert claim_tables
    assert recent_tables[0].get("value")
    assert recent_tables[0]["value"]["data"][0][0] == "chkres_demo_001"
    assert claim_tables[0].get("value")
    assert claim_tables[0]["value"]["data"][0][0] == "claim_demo_001"


def test_quality_claim_select_handler_should_switch_detail_and_evidence(tmp_path: Path) -> None:
    """点击 Claim 列表时应能切换到对应 Claim 的详情和证据。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    select_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "select_quality_claim"
    )
    claim_rows = pd.DataFrame(
        [
            ["claim_1", "第一条 Claim", "rejected", "high", "1.000", "标题一", "section-1:chunk-1"],
            ["claim_2", "第二条 Claim", "needs_review", "medium", "0.800", "标题二", "section-2:chunk-2"],
        ],
        columns=["Claim ID", "Claim 内容", "当前判定", "风险等级", "置信度", "来源文档", "来源位置"],
    )
    claim_detail_map = {
        "claim_1": {
            "claim_id": "claim_1",
            "claim_text": "第一条 Claim",
            "verdict": "rejected",
            "risk_level": "high",
            "confidence": 1.0,
            "review_status": "pending",
            "source_doc": "标题一",
            "source_span": "section-1:chunk-1",
            "evidence": "第一条证据摘要",
            "evidence_reason": "第一条说明",
            "evidence_details": [
                {
                    "chunk_id": "chunk_1",
                    "doc_title": "标题一",
                    "source_span": "section-1:chunk-1",
                    "retrieval_source": "vector",
                    "matched_sources": ["vector"],
                    "rerank_score": None,
                    "content_preview": "第一条证据内容",
                }
            ],
        },
        "claim_2": {
            "claim_id": "claim_2",
            "claim_text": "第二条 Claim",
            "verdict": "needs_review",
            "risk_level": "medium",
            "confidence": 0.8,
            "review_status": "pending",
            "source_doc": "标题二",
            "source_span": "section-2:chunk-2",
            "evidence": "第二条证据摘要",
            "evidence_reason": "第二条说明",
            "evidence_details": [
                {
                    "chunk_id": "chunk_2",
                    "doc_title": "标题二",
                    "source_span": "section-2:chunk-2",
                    "retrieval_source": "fulltext",
                    "matched_sources": ["fulltext"],
                    "rerank_score": 0.7,
                    "content_preview": "第二条证据内容",
                }
            ],
        },
    }
    event = gr.SelectData(None, {"index": [1, 0], "value": "claim_2"})

    claim_view, evidence_rows, review_view, selected_claim_id, evidence_items, evidence_detail = select_handler(
        claim_rows,
        claim_detail_map,
        event,
    )

    assert selected_claim_id == "claim_2"
    assert "第二条 Claim" in claim_view
    assert "section-2:chunk-2" in claim_view
    assert "第二条 Claim" in review_view
    assert len(evidence_items) == 1
    assert "第二条证据内容" in evidence_detail
    assert evidence_rows == [["chunk_2", "标题二", "section-2:chunk-2", "fulltext", "fulltext", "0.700", "第二条证据内容"]]


def test_quality_evidence_select_handler_should_switch_evidence_detail(tmp_path: Path) -> None:
    """点击证据列表时应能切换到对应证据详情。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    select_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "select_quality_evidence"
    )
    evidence_items = [
        {
            "chunk_id": "chunk_1",
            "doc_title": "标题一",
            "source_span": "section-1:chunk-1",
            "retrieval_source": "vector",
            "matched_sources": ["vector"],
            "rerank_score": None,
            "content_preview": "第一条证据内容",
        },
        {
            "chunk_id": "chunk_2",
            "doc_title": "标题二",
            "source_span": "section-2:chunk-2",
            "retrieval_source": "fulltext",
            "matched_sources": ["fulltext"],
            "rerank_score": 0.7,
            "content_preview": "第二条证据内容",
        },
    ]
    event = gr.SelectData(None, {"index": [1, 0], "value": "chunk_2"})

    evidence_detail = select_handler(evidence_items, event)

    assert "证据详情" in evidence_detail
    assert "标题二" in evidence_detail
    assert "section-2:chunk-2" in evidence_detail
    assert "第二条证据内容" in evidence_detail


def test_recent_quality_select_handler_should_restore_selected_result(tmp_path: Path) -> None:
    """点击最近质检记录时应回放对应那次质检结果。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    select_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "select_recent_quality_result"
    )
    recent_results = [
        {
            "check_id": "chkres_a",
            "input_text": "第一条输入",
            "template_id": "t1",
            "template_name": "模板一",
            "overall_verdict": "supported",
            "risk_level": "low",
            "created_at": "2026-05-01T12:00:00+00:00",
            "claims": [
                {
                    "claim_id": "claim_a1",
                    "claim_text": "第一条 Claim",
                    "verdict": "supported",
                    "risk_level": "low",
                    "confidence": 0.95,
                    "evidence": "第一条证据摘要",
                    "evidence_reason": "第一条说明",
                    "source_doc": "文档一",
                    "source_span": "section-1",
                    "review_status": "pending",
                    "evidence_details": [
                        {
                            "chunk_id": "chunk_a1",
                            "doc_title": "文档一",
                            "source_span": "section-1",
                            "retrieval_source": "vector",
                            "matched_sources": ["vector"],
                            "rerank_score": 0.91,
                            "content_preview": "第一条证据内容",
                        }
                    ],
                }
            ],
        },
        {
            "check_id": "chkres_b",
            "input_text": "第二条输入",
            "template_id": "t2",
            "template_name": "模板二",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "created_at": "2026-05-01T13:00:00+00:00",
            "claims": [
                {
                    "claim_id": "claim_b1",
                    "claim_text": "第二条 Claim",
                    "verdict": "needs_review",
                    "risk_level": "medium",
                    "confidence": 0.82,
                    "evidence": "第二条证据摘要",
                    "evidence_reason": "第二条说明",
                    "source_doc": "文档二",
                    "source_span": "section-2",
                    "review_status": "pending",
                    "evidence_details": [
                        {
                            "chunk_id": "chunk_b1",
                            "doc_title": "文档二",
                            "source_span": "section-2",
                            "retrieval_source": "fulltext",
                            "matched_sources": ["fulltext"],
                            "rerank_score": 0.73,
                            "content_preview": "第二条证据内容",
                        }
                    ],
                }
            ],
        },
    ]
    event = gr.SelectData(None, {"index": [1, 0], "value": "chkres_b"})

    (
        progress_html,
        result_html,
        claim_rows,
        selected_claim_id,
        claim_detail_map,
        claim_detail_html,
        evidence_rows,
        review_view,
        evidence_items,
        evidence_detail_html,
    ) = select_handler(recent_results, event)

    assert "已加载历史质检记录" in progress_html
    assert "模板二" in result_html
    assert "第二条 Claim" in claim_detail_html
    assert "第二条 Claim" in review_view
    assert selected_claim_id.startswith("claim_b1 |")
    assert "claim_b1" in claim_detail_map
    assert claim_rows == [["claim_b1", "第二条 Claim", "需复核", "中级", "0.820", "文档二", "section-2"]]
    assert evidence_rows == [["chunk_b1", "文档二", "section-2", "fulltext", "fulltext", "0.730", "第二条证据内容"]]
    assert len(evidence_items) == 1
    assert "第二条证据内容" in evidence_detail_html


def test_search_ui_css_should_hide_cell_selection_buttons_and_use_normal_font_size() -> None:
    """检索页样式应隐藏整行整列选择按钮，并使用常规字号。"""

    assert "Select column" in UI_CSS
    assert "Select row" in UI_CSS
    assert "display:none" in UI_CSS.replace(" ", "")
    assert "font-size:14px" in UI_CSS.replace(" ", "")
    assert "#search-top-row" in UI_CSS
    assert "#search-input-panel" in UI_CSS
    assert "min-height:260px" in UI_CSS.replace(" ", "")
    assert ".search-result-cell-selected" in UI_CSS
    assert "border-left:5pxsolid" in UI_CSS.replace(" ", "")
    assert "font-weight:700" in UI_CSS.replace(" ", "")
    assert "#b45309" in UI_CSS
    assert "tr:has(td:focus-within) td" in UI_CSS
    assert "tr:has(button:focus) td" in UI_CSS
    assert "td.selected" in UI_CSS
    assert "#quality-top-row" in UI_CSS
    assert "#quality-template-row" in UI_CSS
    assert "#quality-summary-row" in UI_CSS
    assert "#quality-claim-row" in UI_CSS
    assert "#quality-evidence-row" in UI_CSS
    assert "#quality-history-row" in UI_CSS
    assert "#quality-input-panel" in UI_CSS
    assert "#quality-history-panel" in UI_CSS
    assert "#quality-claims-table" in UI_CSS
    assert "#quality-recent-table" in UI_CSS
    assert "#quality-evidence-table" in UI_CSS
    assert "#quality-evidence-detail" in UI_CSS
    assert "#quality-claims-table tr:has(td:focus-within) td" in UI_CSS
    assert "#quality-evidence-table tr:has(button:focus) td" in UI_CSS
    assert "#quality-recent-table tr:has(.selected) td" in UI_CSS
    assert "box-shadow: inset 5px 0 0 0" in UI_CSS
