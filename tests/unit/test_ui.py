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


def test_create_ui_app_should_configure_review_workspace(tmp_path: Path) -> None:
    """人工审核页应包含待审核列表、审核操作、历史记录和证据区域。"""

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

    assert any("先从可审核记录列表中选择一条 Claim" in value for value in html_values)
    assert "review-top-row" in elem_ids
    assert "review-summary-row" in elem_ids
    assert "review-record-row" in elem_ids
    assert "review-evidence-row" in elem_ids
    assert "review-action-panel" in elem_ids
    assert "review-help-panel" in elem_ids
    assert "review-result-panel" in elem_ids
    assert "review-claim-detail" in elem_ids
    assert "review-record-detail" in elem_ids
    assert "review-pending-table" in elem_ids
    assert "review-processed-table" in elem_ids
    assert "review-history-table" in elem_ids
    assert "review-evidence-table" in elem_ids
    assert "review-evidence-detail" in elem_ids
    assert "最近审核定位" not in labels
    assert "待处理记录" in labels
    assert "已处理 Claim" in labels
    assert "已审核记录" in labels
    assert "列表范围" in labels
    assert "风险筛选" in labels


def test_create_ui_app_should_include_settings_workspace(tmp_path: Path) -> None:
    """系统菜单应包含功能设置页，且布局顺序符合操作主线。"""

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
    tab_labels = [
        str(component.get("props", {}).get("label", ""))
        for component in components
        if component.get("type") == "tabitem"
    ]

    assert any("功能设置" in value for value in html_values)
    assert tab_labels[-1] == "功能设置"
    assert "settings-top-row" in elem_ids
    assert "settings-main-row" in elem_ids
    assert "settings-bottom-row" in elem_ids
    assert "settings-list-actions" in elem_ids
    assert "settings-form-actions" in elem_ids
    assert "settings-basic-group" in elem_ids
    assert "settings-policy-group" in elem_ids
    assert "settings-prompt-group" in elem_ids
    assert "settings-help-panel" in elem_ids
    assert "settings-runtime-panel" in elem_ids
    assert "settings-template-table" in elem_ids
    assert "settings-template-detail" in elem_ids
    assert "settings-template-form" in elem_ids
    assert "模板列表" in labels
    assert "模板 ID" in labels
    assert "模板名称" in labels
    assert "系统提示词" in labels
    assert "用户提示模板" in labels
    assert "我确认删除当前模板" in labels
    assert elem_ids.index("settings-top-row") < elem_ids.index("settings-main-row")
    assert elem_ids.index("settings-main-row") < elem_ids.index("settings-bottom-row")
    assert elem_ids.index("settings-template-table") < elem_ids.index("settings-template-detail")
    assert elem_ids.index("settings-template-detail") < elem_ids.index("settings-template-form")
    assert elem_ids.index("settings-basic-group") < elem_ids.index("settings-policy-group")
    assert elem_ids.index("settings-policy-group") < elem_ids.index("settings-prompt-group")


def test_create_ui_app_should_preload_review_candidates_from_quality_history(tmp_path: Path) -> None:
    """人工审核页进入时应优先显示 AI 质检产生的可审核 Claim。"""

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
            "check_id": "chkres_review_demo",
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
                "claim_id": "claim_review_demo",
                "check_id": "chkres_review_demo",
                "claim_text": "阿胶源于驴皮熬制。",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.82,
                "evidence": "阿胶与驴皮存在传统制备关系。",
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
    candidate_tables = [
        component.get("props", {})
        for component in components
        if component.get("type") == "dataframe" and component.get("props", {}).get("elem_id") == "review-pending-table"
    ]
    claim_details = [
        component.get("props", {})
        for component in components
        if component.get("type") == "html" and component.get("props", {}).get("elem_id") == "review-claim-detail"
    ]

    assert candidate_tables
    assert claim_details
    assert candidate_tables[0].get("value")
    assert candidate_tables[0]["value"]["data"][0][0] == "claim_review_demo"
    assert "Claim 详情" in str(claim_details[0].get("value", ""))
    assert "阿胶源于驴皮熬制" in str(claim_details[0].get("value", ""))


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


def test_review_candidate_select_handler_should_restore_selected_claim(tmp_path: Path) -> None:
    """点击可审核记录时应联动 Claim、证据和审核输入区。"""

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
        if getattr(block_fn.fn, "__name__", "") == "select_review_candidate"
    )
    candidate_rows = pd.DataFrame(
        [
            ["claim_review_a", "第一条 Claim", "已支持", "低级", "已通过", "文档一", "模板一", "2026-05-01T12:00:00+00:00"],
            ["claim_review_b", "第二条 Claim", "需复核", "中级", "待处理", "文档二", "模板二", "2026-05-01T13:00:00+00:00"],
        ],
        columns=["Claim ID", "Claim 摘要", "当前判定", "风险等级", "审核状态", "来源文档", "质检模板", "质检时间"],
    )
    review_candidates = [
        {
            "claim_id": "claim_review_a",
            "check_id": "chkres_review_a",
            "claim_text": "第一条 Claim",
            "verdict": "supported",
            "risk_level": "low",
            "confidence": 0.91,
            "evidence": "第一条证据摘要",
            "source_doc": "文档一",
            "source_span": "section-1",
            "review_status": "approved",
            "template_name": "模板一",
            "check_created_at": "2026-05-01T12:00:00+00:00",
        },
        {
            "claim_id": "claim_review_b",
            "check_id": "chkres_review_b",
            "claim_text": "第二条 Claim",
            "verdict": "needs_review",
            "risk_level": "medium",
            "confidence": 0.82,
            "evidence": "第二条证据摘要",
            "source_doc": "文档二",
            "source_span": "section-2",
            "review_status": "pending",
            "template_name": "模板二",
            "check_created_at": "2026-05-01T13:00:00+00:00",
        },
    ]
    review_items = [
        {
            "review_id": "rev_review_a",
            "claim_id": "claim_review_a",
            "check_id": "chkres_review_a",
            "template_name": "模板一",
            "claim_text": "第一条 Claim",
            "review_action": "approved",
            "review_status": "approved",
            "review_note": "确认通过",
            "reviewer": "ui_user",
            "created_at": "2026-05-01T12:10:00+00:00",
        }
    ]
    event = gr.SelectData(None, {"index": [1, 0], "value": "claim_review_b"})

    (
        selected_claim_id,
        review_claim_detail_map,
        review_claim_detail_html,
        review_evidence_rows,
        review_evidence_items,
        review_evidence_detail_html,
        review_action_value,
        review_note_value,
        selected_review_id,
        review_record_detail_html,
    ) = select_handler(candidate_rows, review_candidates, review_items, event, "全部记录", "全部风险")

    assert selected_claim_id == "claim_review_b"
    assert "claim_review_b" in review_claim_detail_map
    assert "第二条 Claim" in review_claim_detail_html
    assert review_evidence_rows == [["section-2", "文档二", "section-2", "history", "history", "-", "第二条证据摘要"]]
    assert len(review_evidence_items) == 1
    assert "第二条证据摘要" in review_evidence_detail_html
    assert review_action_value == "通过"
    assert review_note_value == ""
    assert selected_review_id == ""
    assert "未选择审核记录" in review_record_detail_html


def test_review_filter_handler_should_split_candidates_by_scope_and_risk(tmp_path: Path) -> None:
    """切换人工审核筛选后，应同步刷新待处理与已处理分区。"""

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
    filter_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "change_review_filters"
    )
    review_candidates = [
        {
            "claim_id": "claim_pending_high",
            "check_id": "chk_1",
            "claim_text": "高风险待处理 Claim",
            "verdict": "needs_review",
            "risk_level": "high",
            "confidence": 0.92,
            "evidence": "高风险证据",
            "source_doc": "文档一",
            "source_span": "section-1",
            "review_status": "pending",
            "template_name": "模板一",
            "check_created_at": "2026-05-01T12:00:00+00:00",
        },
        {
            "claim_id": "claim_pending_medium",
            "check_id": "chk_2",
            "claim_text": "中风险待处理 Claim",
            "verdict": "needs_review",
            "risk_level": "medium",
            "confidence": 0.83,
            "evidence": "中风险证据",
            "source_doc": "文档二",
            "source_span": "section-2",
            "review_status": "pending",
            "template_name": "模板二",
            "check_created_at": "2026-05-01T13:00:00+00:00",
        },
        {
            "claim_id": "claim_processed_high",
            "check_id": "chk_3",
            "claim_text": "高风险已处理 Claim",
            "verdict": "rejected",
            "risk_level": "high",
            "confidence": 0.96,
            "evidence": "已处理证据",
            "source_doc": "文档三",
            "source_span": "section-3",
            "review_status": "approved",
            "template_name": "模板三",
            "check_created_at": "2026-05-01T14:00:00+00:00",
        },
    ]
    review_items = [
        {
            "review_id": "rev_processed_high",
            "claim_id": "claim_processed_high",
            "check_id": "chk_3",
            "template_name": "模板三",
            "claim_text": "高风险已处理 Claim",
            "review_action": "approved",
            "review_status": "approved",
            "review_note": "已通过",
            "reviewer": "ui_user",
            "created_at": "2026-05-01T14:10:00+00:00",
        }
    ]

    (
        pending_rows,
        processed_rows,
        selected_claim_id,
        review_claim_detail_map,
        review_claim_detail_html,
        review_evidence_rows,
        review_evidence_items,
        review_evidence_detail_html,
        review_action_value,
        review_note_value,
        selected_review_id,
        review_record_detail_html,
    ) = filter_handler(review_candidates, review_items, "", "全部记录", "仅高风险")

    assert pending_rows == [["claim_pending_high", "高风险待处理 Claim", "需复核", "高级", "待处理", "文档一", "模板一", "2026-05-01T12:00:00+00:00"]]
    assert processed_rows == [["claim_processed_high", "高风险已处理 Claim", "不通过", "高级", "已通过", "文档三", "模板三", "2026-05-01T14:00:00+00:00"]]
    assert selected_claim_id == "claim_pending_high"
    assert "claim_pending_high" in review_claim_detail_map
    assert "高风险待处理 Claim" in review_claim_detail_html
    assert review_evidence_rows == [["section-1", "文档一", "section-1", "history", "history", "-", "高风险证据"]]
    assert len(review_evidence_items) == 1
    assert "高风险证据" in review_evidence_detail_html
    assert review_action_value == "通过"
    assert review_note_value == ""
    assert selected_review_id == ""
    assert "未选择审核记录" in review_record_detail_html


def test_submit_review_then_switch_to_processed_scope_should_show_latest_record(tmp_path: Path) -> None:
    """刚提交审核后，切换到仅已处理时应能看到最新处理的 Claim。"""

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
            "check_id": "chk_submit_review_demo",
            "input_text": "待审核输入",
            "template_id": "t1",
            "template_name": "模板一",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "需要人工复核",
            "created_at": "2026-05-01T12:00:00+00:00",
            "updated_at": "2026-05-01T12:00:00+00:00",
        },
        claims=[
            {
                "claim_id": "claim_submit_review_demo",
                "check_id": "chk_submit_review_demo",
                "claim_text": "这是一条刚提交审核的 Claim",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.86,
                "evidence": "提交审核后的证据摘要",
                "source_doc": "文档一",
                "source_span": "section-1",
                "review_status": "pending",
                "created_at": "2026-05-01T12:00:00+00:00",
                "updated_at": "2026-05-01T12:00:00+00:00",
            }
        ],
        rule_hits=[],
    )

    demo = create_ui_app(settings)
    submit_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "submit_review_action"
    )
    filter_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "change_review_filters"
    )

    submit_outputs = submit_handler(
        "claim_submit_review_demo",
        "通过",
        "人工审核通过",
        "仅待处理",
        "全部风险",
    )
    review_candidate_state = submit_outputs[3]
    review_selected_claim_state = submit_outputs[4]
    review_history_state = submit_outputs[13]

    (
        pending_rows,
        processed_rows,
        selected_claim_id,
        review_claim_detail_map,
        review_claim_detail_html,
        _review_evidence_rows,
        _review_evidence_items,
        _review_evidence_detail_html,
        review_action_value,
        review_note_value,
        selected_review_id,
        review_record_detail_html,
    ) = filter_handler(
        review_candidate_state,
        review_history_state,
        review_selected_claim_state,
        "仅已处理",
        "全部风险",
    )

    assert pending_rows == []
    assert processed_rows == [[
        "claim_submit_review_demo",
        "这是一条刚提交审核的 Claim",
        "需复核",
        "中级",
        "已通过",
        "文档一",
        "模板一",
        "2026-05-01T12:00:00+00:00",
    ]]
    assert selected_claim_id == "claim_submit_review_demo"
    assert "claim_submit_review_demo" in review_claim_detail_map
    assert "这是一条刚提交审核的 Claim" in review_claim_detail_html
    assert review_action_value == "通过"
    assert review_note_value == "人工审核通过"
    assert selected_review_id
    assert "人工审核通过" in review_record_detail_html


def test_review_history_select_handler_should_restore_selected_record(tmp_path: Path) -> None:
    """点击已审核记录时应回放对应 Claim 与证据。"""

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
            "check_id": "chkres_review_a",
            "input_text": "第一条输入",
            "template_id": "t1",
            "template_name": "模板一",
            "overall_verdict": "supported",
            "risk_level": "low",
            "summary": "第一条摘要",
            "created_at": "2026-05-01T12:00:00+00:00",
            "updated_at": "2026-05-01T12:00:00+00:00",
        },
        claims=[
            {
                "claim_id": "claim_review_a",
                "check_id": "chkres_review_a",
                "claim_text": "第一条 Claim",
                "verdict": "supported",
                "risk_level": "low",
                "confidence": 0.91,
                "evidence": "第一条证据摘要",
                "evidence_reason": "第一条说明",
                "source_doc": "文档一",
                "source_span": "section-1",
                "review_status": "approved",
                "created_at": "2026-05-01T12:00:00+00:00",
                "updated_at": "2026-05-01T12:00:00+00:00",
                "evidence_details": [
                    {
                        "chunk_id": "chunk_review_a",
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
        rule_hits=[],
    )
    repository.create_quality_result(
        quality_check={
            "check_id": "chkres_review_b",
            "input_text": "第二条输入",
            "template_id": "t2",
            "template_name": "模板二",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "第二条摘要",
            "created_at": "2026-05-01T13:00:00+00:00",
            "updated_at": "2026-05-01T13:00:00+00:00",
        },
        claims=[
            {
                "claim_id": "claim_review_b",
                "check_id": "chkres_review_b",
                "claim_text": "第二条 Claim",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.82,
                "evidence": "第二条证据摘要",
                "evidence_reason": "第二条说明",
                "source_doc": "文档二",
                "source_span": "section-2",
                "review_status": "rejected",
                "created_at": "2026-05-01T13:00:00+00:00",
                "updated_at": "2026-05-01T13:00:00+00:00",
                "evidence_details": [
                    {
                        "chunk_id": "chunk_review_b",
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
        rule_hits=[],
    )

    demo = create_ui_app(settings)
    select_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "select_review_history_record"
    )
    review_items = [
        {
            "review_id": "rev_review_b",
            "claim_id": "claim_review_b",
            "check_id": "chkres_review_b",
            "template_name": "模板二",
            "claim_text": "第二条 Claim",
            "review_action": "rejected",
            "review_status": "rejected",
            "review_note": "需要驳回",
            "reviewer": "ui_user",
            "created_at": "2026-05-01T13:10:00+00:00",
        },
        {
            "review_id": "rev_review_a",
            "claim_id": "claim_review_a",
            "check_id": "chkres_review_a",
            "template_name": "模板一",
            "claim_text": "第一条 Claim",
            "review_action": "approved",
            "review_status": "approved",
            "review_note": "确认通过",
            "reviewer": "ui_user",
            "created_at": "2026-05-01T12:10:00+00:00",
        },
    ]
    event = gr.SelectData(None, {"index": [1, 0], "value": "rev_review_a"})

    review_candidates = [
        {
            "claim_id": "claim_review_b",
            "check_id": "chkres_review_b",
            "claim_text": "第二条 Claim",
            "verdict": "needs_review",
            "risk_level": "medium",
            "confidence": 0.82,
            "evidence": "第二条证据摘要",
            "source_doc": "文档二",
            "source_span": "section-2",
            "review_status": "rejected",
            "template_name": "模板二",
            "check_created_at": "2026-05-01T13:00:00+00:00",
        },
        {
            "claim_id": "claim_review_a",
            "check_id": "chkres_review_a",
            "claim_text": "第一条 Claim",
            "verdict": "supported",
            "risk_level": "low",
            "confidence": 0.91,
            "evidence": "第一条证据摘要",
            "source_doc": "文档一",
            "source_span": "section-1",
            "review_status": "approved",
            "template_name": "模板一",
            "check_created_at": "2026-05-01T12:00:00+00:00",
        },
    ]

    (
        selected_claim_id,
        review_claim_detail_map,
        review_claim_detail_html,
        review_evidence_rows,
        review_evidence_items,
        review_evidence_detail_html,
        review_action_value,
        review_note_value,
        selected_review_id,
        review_record_detail,
    ) = select_handler(review_items, review_candidates, event, "全部记录", "全部风险")

    assert selected_claim_id == "claim_review_a"
    assert selected_review_id == "rev_review_a"
    assert "claim_review_a" in review_claim_detail_map
    assert "确认通过" in review_record_detail
    assert "第一条 Claim" in review_claim_detail_html
    assert review_action_value == "通过"
    assert review_note_value == "确认通过"
    assert review_evidence_rows == [["section-1", "文档一", "section-1", "history", "history", "-", "第一条证据摘要"]]
    assert len(review_evidence_items) == 1
    assert "第一条证据摘要" in review_evidence_detail_html


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
    assert "#review-top-row" in UI_CSS
    assert "#review-summary-row" in UI_CSS
    assert "#review-record-row" in UI_CSS
    assert "#review-evidence-row" in UI_CSS
    assert "#review-result-panel" in UI_CSS
    assert "#review-help-panel > div" in UI_CSS
    assert "#review-pending-table" in UI_CSS
    assert "#review-processed-table" in UI_CSS
    assert "#review-history-table" in UI_CSS
    assert "#review-evidence-table" in UI_CSS
    assert "#review-pending-table table th" in UI_CSS
    assert "#review-processed-table table th" in UI_CSS
    assert "#review-history-table table th" in UI_CSS
    assert "#review-evidence-table table th" in UI_CSS
    assert "rgba(68, 68, 68, 0.22)" in UI_CSS
    assert "inset 6px 0 0 0" in UI_CSS
    assert "#review-claim-detail" in UI_CSS
    assert "font-weight:700" in UI_CSS.replace(" ", "")
