"""程序说明：验证最小 UI 可构建，并确保 UI 测试不受模块重载污染。"""

import importlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import gradio as gr
import pandas as pd
import pytest

from src.auth.service import normalize_auth_tab_name
from src.common.config import AppSettings
from src.db.connection import initialize_database
from src.db.repositories import DocumentRepository, QualityRepository
from src.ingest.service import IngestService
from src.quality.service import QualityService
from src.review.service import ReviewService
from src.ui.app import create_ui_app
from src.ui.css import UI_CSS
from src.ui.document_page import build_document_tab
from src.ui.page_helpers import (
    build_visible_knowledge_base_bundle,
    filter_visible_knowledge_base_items,
    get_selected_search_item_from_page_rows,
    paginate_table_rows,
)


def get_current_ui_app_module():
    """返回当前 ``sys.modules`` 中最新的 UI 应用模块，避免测试受模块重载污染。"""

    return importlib.import_module("src.ui.app")


def build_admin_login_session() -> dict[str, object]:
    """构造 UI handler 测试用管理员登录态。"""

    return {
        "user_id": "admin-test",
        "username": "admin",
        "is_admin": True,
        "permissions": {"tab_names": [], "kb_ids": []},
    }


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


def test_normalize_auth_tab_name_should_compat_legacy_tab_labels() -> None:
    """旧权限表中的历史页签名称应映射到当前 UI 名称。"""

    assert normalize_auth_tab_name("文档管理") == "知识库管理"
    assert normalize_auth_tab_name("文档检索") == "知识库检索"
    assert normalize_auth_tab_name("AI 质检") == "AI 质检"


def test_filter_visible_knowledge_base_items_should_only_keep_authorized_items() -> None:
    """知识库下拉选项应按授权范围过滤。"""

    items = [
        {"knowledge_base_id": "default", "knowledge_base_name": "默认知识库"},
        {"knowledge_base_id": "medical", "knowledge_base_name": "医学知识库"},
    ]

    filtered_items = filter_visible_knowledge_base_items(items, {"medical"}, is_admin=False)
    admin_items = filter_visible_knowledge_base_items(items, {"medical"}, is_admin=True)

    assert [item["knowledge_base_id"] for item in filtered_items] == ["medical"]
    assert [item["knowledge_base_id"] for item in admin_items] == ["default", "medical"]


def test_build_visible_knowledge_base_bundle_should_fallback_to_authorized_default() -> None:
    """选中未授权知识库时，应回退到权限范围内的默认选项。"""

    items = [
        {"knowledge_base_id": "default", "knowledge_base_name": "默认知识库", "is_default": True},
        {"knowledge_base_id": "medical", "knowledge_base_name": "医学知识库", "is_default": False},
    ]

    visible_items, visible_choices, selected_choice = build_visible_knowledge_base_bundle(
        items,
        {"medical"},
        is_admin=False,
        selected_knowledge_base_id="default",
    )

    assert [item["knowledge_base_id"] for item in visible_items] == ["medical"]
    assert len(visible_choices) == 1
    assert "medical" in str(selected_choice)


def test_paginate_table_rows_should_clamp_page_and_prepend_sequence() -> None:
    """分页 helper 应限制页码范围，并在需要时补自然序号。"""

    rows = [[f"id_{index}", f"value_{index}"] for index in range(1, 14)]

    page_rows, resolved_page, total_pages, page_info = paginate_table_rows(
        rows,
        page=99,
        prepend_sequence=True,
    )

    assert resolved_page == 2
    assert total_pages == 2
    assert len(page_rows) == 3
    assert page_rows[0] == ["11", "id_11", "value_11"]
    assert "第 2 / 2 页" in page_info


def test_get_selected_search_item_from_page_rows_should_map_sequence_to_raw_row() -> None:
    """检索结果点击应按当前页序号映射回原始结果行。"""

    page_rows = [
        ["11", "文档甲", "定位甲", "全文", "标题命中", "摘要甲"],
        ["12", "文档乙", "定位乙", "向量", "语义命中", "摘要乙"],
    ]
    raw_rows = [
        {"chunk_id": f"chunk_{index}", "doc_title": f"标题{index}"}
        for index in range(1, 13)
    ]

    selected_row = get_selected_search_item_from_page_rows(
        page_rows,
        raw_rows,
        SimpleNamespace(index=[1, 0]),
    )

    assert selected_row == {"chunk_id": "chunk_12", "doc_title": "标题12"}


def test_build_document_tab_should_return_expected_component_bundle() -> None:
    """文档页 builder 应返回后续接线所需的关键组件集合。"""

    with gr.Blocks():
        components = build_document_tab(
            initial_values={
                "knowledge_base_choices": ["default | 默认知识库"],
                "initial_knowledge_base_choice": "default | 默认知识库",
                "document_summary": "<div>文档概览</div>",
                "database_summary": "<div>数据库状态</div>",
                "document_choices": ["a.md"],
                "active_choice": "a.md",
                "document_detail": "<div>当前文档</div>",
                "register_interactive": True,
                "rebuild_interactive": False,
                "database_table_rows": [["1", "文档总数", "1"]],
                "database_page_info": "第 1 / 1 页，共 1 条，每页最多 10 行",
                "document_table_rows": [["1", "a.md", "a", "default", "10", "-", "是", "完成", "否", "查看", ""]],
                "document_page_info": "第 1 / 1 页，共 1 条，每页最多 10 行",
                "document_quality_report": "<div>未开始</div>",
                "document_quality_checks": "<div>未开始</div>",
                "document_quality_sections_table_rows": [],
                "document_quality_sections_page_info": "第 1 / 1 页，共 0 条，每页最多 10 行",
                "document_quality_chunks_table_rows": [],
                "document_quality_chunks_page_info": "第 1 / 1 页，共 0 条，每页最多 10 行",
                "document_quality_search_summary": "<div>未开始</div>",
                "document_quality_search_table_rows": [],
                "document_quality_search_page_info": "第 1 / 1 页，共 0 条，每页最多 10 行",
                "document_quality_search_detail": "<div>未开始</div>",
                "document_quality_batch_summary": "<div>未开始</div>",
                "document_quality_batch_table_rows": [],
                "document_quality_batch_page_info": "第 1 / 1 页，共 0 条，每页最多 10 行",
                "document_quality_config_html": "<div>配置</div>",
                "document_quality_config_result": "<div>未开始</div>",
                "quality_sample_limit": 3,
                "quality_long_document_char_threshold": 2000,
                "quality_min_sections_for_long_doc": 5,
                "quality_max_avg_chunks_per_section": 8,
                "quality_max_chunk_chars": 1200,
                "quality_short_chunk_chars": 80,
                "quality_short_chunk_warn_min_chunk_count": 10,
            }
        )

    expected_keys = {
        "document_knowledge_base",
        "document_target_knowledge_base",
        "document_choices",
        "register_button",
        "rebuild_button",
        "document_quality_search_query",
        "document_quality_search_results",
        "document_quality_batch_table",
        "document_quality_config_save_button",
        "document_quality_config_export_button",
    }

    assert expected_keys.issubset(components.keys())
    assert isinstance(components["document_knowledge_base"], gr.Dropdown)
    assert components["document_knowledge_base"].elem_id == "document-knowledge-base"
    assert isinstance(components["document_quality_search_results"], gr.Dataframe)
    assert components["document_quality_search_results"].elem_id == "document-quality-search-results"
    assert isinstance(components["document_quality_config_save_button"], gr.Button)
    assert components["document_quality_config_save_button"].value == "保存质检阈值"


def test_connection_scoped_auth_service_should_open_and_close_connection_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """认证包装层应按调用粒度创建并关闭数据库连接。"""

    lifecycle: list[str] = []
    ui_app_module = get_current_ui_app_module()

    class DummyConnection:
        def __enter__(self):
            lifecycle.append("enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            lifecycle.append("exit")
            return False

    class DummyAuthService:
        def __init__(self, connection) -> None:
            assert isinstance(connection, DummyConnection)
            lifecycle.append("auth_init")

        def authenticate(self, username: str, password: str):
            lifecycle.append(f"authenticate:{username}")
            return {"username": username, "password": password}

    monkeypatch.setattr(ui_app_module, "create_connection", lambda database_path: DummyConnection())
    monkeypatch.setattr(ui_app_module, "AuthService", DummyAuthService)

    service = ui_app_module.ConnectionScopedAuthService("test.db")
    result = service.authenticate("tester", "secret")

    assert result == {"username": "tester", "password": "secret"}
    assert lifecycle == ["enter", "auth_init", "authenticate:tester", "exit"]


def test_create_ui_app_should_not_register_startup_load_event(tmp_path: Path) -> None:
    """UI 首屏应直接渲染默认数据，避免依赖启动 load 事件队列。"""

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
    elem_ids = [str(component.get("props", {}).get("elem_id", "")) for component in components]

    assert any("数据库状态" in value for value in html_values)
    assert "document-management-help-panel" in elem_ids
    assert "document-management-actions-row" in elem_ids
    assert "document-management-result-row" in elem_ids
    assert any("知识库管理用于查看输入文档、执行入库与重建" in value for value in html_values)


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
    assert dataframes[0].get("column_count", [])[0] == 6
    assert "search-knowledge-base" in elem_ids
    assert "search-input-panel" in elem_ids
    assert "search-top-row" in elem_ids
    assert "search-result-workspace" in elem_ids
    assert "search-results-table" in elem_ids
    assert "search-export-row" in elem_ids
    assert "search-export-result" in elem_ids
    assert elem_ids.index("search-help-panel") < elem_ids.index("search-result-summary")
    assert elem_ids.index("search-top-row") < elem_ids.index("search-result-workspace")
    assert elem_ids.index("search-results-table") < elem_ids.index("search-result-detail")
    assert elem_ids.index("search-export-row") < elem_ids.index("search-export-result")


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
    claim_selectors = [
        component.get("props", {})
        for component in components
        if component.get("type") == "radio" and component.get("props", {}).get("elem_id") == "quality-claims-table"
    ]
    evidence_tables = [
        component.get("props", {})
        for component in components
        if component.get("type") == "dataframe" and component.get("props", {}).get("elem_id") == "quality-evidence-table"
    ]
    recent_tables = [
        component.get("props", {})
        for component in components
        if component.get("type") == "dataframe" and component.get("props", {}).get("elem_id") == "quality-recent-table"
    ]
    quality_download_files = [
        component.get("props", {})
        for component in components
        if component.get("type") == "file" and component.get("props", {}).get("elem_id") == "quality-download-file"
    ]

    assert any("AI 质检会把输入内容拆成多条 Claim" in value for value in html_values)
    assert any("模板内容" in value for value in html_values)
    assert any("执行进度" in value for value in html_values)
    assert "可审核 Claim" not in labels
    assert "quality-top-row" in elem_ids
    assert "quality-template-row" in elem_ids
    assert "quality-summary-row" in elem_ids
    assert "quality-claim-row" in elem_ids
    assert "quality-evidence-list-panel" in elem_ids
    assert "quality-action-panel" in elem_ids
    assert "quality-history-panel" in elem_ids
    assert "quality-evaluation-action-row" in elem_ids
    assert "quality-evaluation-accordion" in elem_ids
    assert "quality-help-panel" in elem_ids
    assert "quality-template-panel" in elem_ids
    assert "quality-progress-panel" in elem_ids
    assert "quality-result-panel" in elem_ids
    assert "quality-claim-list-panel" in elem_ids
    assert "quality-evaluation-panel" in elem_ids
    assert "quality-knowledge-base" in elem_ids
    assert "quality-claims-table" in elem_ids
    assert "quality-recent-table" in elem_ids
    assert "quality-history-note" in elem_ids
    assert "quality-history-scope" in elem_ids
    assert "quality-evidence-table" in elem_ids
    assert "quality-evidence-page-info" in elem_ids
    assert "quality-evidence-detail" in elem_ids
    assert "quality-recent-page-info" in elem_ids
    assert "quality-export-result" in elem_ids
    assert "quality-download-file" in elem_ids
    assert "quality-evaluation-export-result" in elem_ids
    assert claim_selectors
    assert claim_selectors[0].get("label") == "Claim 列表"
    assert evidence_tables and evidence_tables[0].get("max_height") == 420
    assert recent_tables and recent_tables[0].get("max_height") == 420
    assert quality_download_files and quality_download_files[0].get("label") == "下载文件"
    assert recent_tables[0].get("column_count", [])[0] == 8
    # 验证面板顺序：summary → claim → evidence → history → action → evaluation
    assert elem_ids.index("quality-summary-row") < elem_ids.index("quality-claim-row")
    assert elem_ids.index("quality-claim-row") < elem_ids.index("quality-evidence-list-panel")
    assert elem_ids.index("quality-evidence-list-panel") < elem_ids.index("quality-evidence-detail")
    assert elem_ids.index("quality-evidence-detail") < elem_ids.index("quality-history-panel")
    assert elem_ids.index("quality-history-panel") < elem_ids.index("quality-action-panel")
    assert elem_ids.index("quality-action-panel") < elem_ids.index("quality-evaluation-accordion")


def test_export_quality_results_should_return_md_download_file(tmp_path: Path) -> None:
    """AI 质检下载应返回 Markdown 文件路径，由 Gradio 文件组件下载。"""

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
    export_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "export_quality_results"
    )
    formatted_result = {
        "check": {
            "check_id": "chk_export_quality",
            "template_name": "通用事实核检",
            "overall_verdict": "passed",
            "summary": "1 条 Claim 已通过。",
        },
        "claims": [
            {
                "claim_id": "claim_export_quality",
                "claim_text": "阿胶在资料中常被归入滋补类内容",
                "verdict": "verified",
                "risk_level": "low",
                "confidence": 0.85,
                "evidence": "滋补证据",
                "evidence_details": [],
            }
        ],
    }

    result_html, download_file = export_handler(formatted_result, "claim_export_quality", {}, [])

    assert "已生成 AI 质检下载文件" in result_html
    assert "查看渲染效果" in result_html
    assert ".preview.html" in result_html
    assert download_file
    assert download_file.endswith(".md")
    with open(download_file, encoding="utf-8") as file:
        exported_text = file.read()
    assert "### 质检结果" in exported_text
    assert "阿胶在资料中常被归入滋补类内容" in exported_text


def test_create_ui_app_should_include_quality_dummy_workspace(tmp_path: Path) -> None:
    """AI 质检优化 dummy 页应完整映射正式页模块，但只承载静态内容。"""

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
    evidence_tables = [
        component.get("props", {})
        for component in components
        if component.get("type") == "dataframe" and component.get("props", {}).get("elem_id") == "quality-dummy-evidence-table"
    ]
    history_tables = [
        component.get("props", {})
        for component in components
        if component.get("type") == "dataframe" and component.get("props", {}).get("elem_id") == "quality-dummy-history-table"
    ]
    evaluation_tables = [
        component.get("props", {})
        for component in components
        if component.get("type") == "dataframe" and component.get("props", {}).get("elem_id") == "quality-dummy-evaluation-table"
    ]

    assert any("总体结论：需复核" in value for value in html_values)
    assert any("详细功能说明" in value for value in html_values)
    assert any("模板内容" in value for value in html_values)
    assert any("执行进度" in value for value in html_values)
    assert any("质检结果" in value for value in html_values)
    assert "quality-dummy-row-1" in elem_ids
    assert "quality-dummy-template-row" in elem_ids
    assert "quality-dummy-summary-row" in elem_ids
    assert "quality-dummy-row-2" in elem_ids
    assert "quality-dummy-row-3" in elem_ids
    assert "quality-dummy-row-4" in elem_ids
    assert "quality-dummy-bottom-row" in elem_ids
    assert "quality-dummy-intake-panel" in elem_ids
    assert "quality-dummy-help-panel" in elem_ids
    assert "quality-dummy-template-panel" in elem_ids
    assert "quality-dummy-progress-panel" in elem_ids
    assert "quality-dummy-result-panel" in elem_ids
    assert "quality-dummy-relation-note" in elem_ids
    assert "quality-dummy-active-check" in elem_ids
    assert "quality-dummy-claim-list-panel" in elem_ids
    assert "quality-dummy-status-panel" in elem_ids
    assert "quality-dummy-focus-panel" in elem_ids
    assert "quality-dummy-evidence-panel" in elem_ids
    assert "quality-dummy-evidence-table" in elem_ids
    assert "quality-dummy-evidence-page-info" in elem_ids
    assert "quality-dummy-evidence-detail" in elem_ids
    assert "quality-dummy-history-panel" in elem_ids
    assert "quality-dummy-history-note" in elem_ids
    assert "quality-dummy-history-scope" in elem_ids
    assert "quality-dummy-history-table" in elem_ids
    assert "quality-dummy-history-page-info" in elem_ids
    assert "quality-dummy-action-panel" in elem_ids
    assert "quality-dummy-export-result" in elem_ids
    assert "quality-dummy-actions-result" in elem_ids
    assert "quality-dummy-evaluation-accordion" in elem_ids
    assert "quality-dummy-evaluation-panel" in elem_ids
    assert "quality-dummy-evaluation-help" in elem_ids
    assert "quality-dummy-evaluation-export-result" in elem_ids
    assert "quality-dummy-evaluation-summary" in elem_ids
    assert "quality-dummy-evaluation-table" in elem_ids
    assert "quality-dummy-detail-help" in elem_ids
    assert "Claim 列表" in labels
    assert "证据列表" in labels
    assert "最近质检记录" in labels
    assert "历史任务范围" in labels
    assert "效果评测样例 JSON" in labels
    assert evidence_tables and evidence_tables[0].get("column_count", [])[0] == 9
    assert evidence_tables[0].get("max_height") == 420
    assert history_tables and history_tables[0].get("column_count", [])[0] == 7
    assert history_tables[0].get("max_height") == 420
    assert evaluation_tables and evaluation_tables[0].get("column_count", [])[0] == 15
    assert elem_ids.index("quality-dummy-row-1") < elem_ids.index("quality-dummy-template-panel")
    assert elem_ids.index("quality-dummy-template-panel") < elem_ids.index("quality-dummy-summary-row")
    assert elem_ids.index("quality-dummy-summary-row") < elem_ids.index("quality-dummy-row-2")
    assert elem_ids.index("quality-dummy-row-2") < elem_ids.index("quality-dummy-row-3")
    assert elem_ids.index("quality-dummy-row-3") < elem_ids.index("quality-dummy-row-4")
    assert elem_ids.index("quality-dummy-row-4") < elem_ids.index("quality-dummy-evaluation-accordion")
    assert elem_ids.index("quality-dummy-evaluation-accordion") < elem_ids.index("quality-dummy-detail-help")


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

    assert any("人工审核用于处理 AI 质检产生的待审核 Claim" in value for value in html_values)
    assert "review-summary-row" in elem_ids
    assert "review-pending-panel" in elem_ids
    assert "review-processed-panel" in elem_ids
    assert "review-evidence-list-panel" in elem_ids
    assert "review-history-panel" in elem_ids
    assert "review-knowledge-base" in elem_ids
    assert "review-focus-panel" in elem_ids
    assert "review-action-panel" in elem_ids
    assert "review-filter-row" in elem_ids
    assert "review-action-form" in elem_ids
    assert "review-action-feedback-row" in elem_ids
    assert "review-action-buttons" in elem_ids
    assert "review-help-panel" in elem_ids
    assert "review-result-panel" in elem_ids
    assert "review-claim-detail" in elem_ids
    assert "review-record-detail" in elem_ids
    assert "review-pending-table" in elem_ids
    assert "review-processed-table" in elem_ids
    assert "review-history-table" in elem_ids
    assert "review-evidence-table" in elem_ids
    assert "review-evidence-detail" in elem_ids
    assert "review-export-result" in elem_ids
    assert "最近审核定位" not in labels
    assert "待处理记录" in labels
    assert "已处理 Claim" in labels
    assert "已审核记录" in labels
    assert "列表范围" in labels
    assert "风险筛选" in labels
    assert elem_ids.index("review-focus-panel") < elem_ids.index("review-summary-row")
    assert elem_ids.index("review-summary-row") < elem_ids.index("review-evidence-list-panel")
    assert elem_ids.index("review-evidence-list-panel") < elem_ids.index("review-action-panel")
    assert elem_ids.index("review-action-panel") < elem_ids.index("review-history-panel")


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
    [
        str(component.get("props", {}).get("value", ""))
        for component in components
        if component.get("type") == "html"
    ]
    elem_ids = [str(component.get("props", {}).get("elem_id", "")) for component in components]
    labels = [str(component.get("props", {}).get("label", "")) for component in components]
    button_components = [component for component in components if component.get("type") == "button"]
    tab_components = [component for component in components if component.get("type") == "tabitem"]
    tab_labels = [str(component.get("props", {}).get("label", "")) for component in tab_components]
    visible_tab_labels = [
        str(component.get("props", {}).get("label", ""))
        for component in tab_components
        if component.get("props", {}).get("visible", True) is not False
    ]
    dummy_tabs = [
        component
        for component in tab_components
        if str(component.get("props", {}).get("label", "")) == "AI 质检优化 Dummy"
    ]
    pending_tabs = [
        component
        for component in tab_components
        if str(component.get("props", {}).get("label", "")) == "待开通"
    ]

    assert {"AI 质检", "人工审核", "知识库管理", "知识库检索", "PageIndex 深度检索", "功能设置"}.issubset(set(tab_labels))
    assert "pageindex-knowledge-base" in elem_ids
    assert "pageindex-document" in elem_ids
    assert "pageindex-tree" in elem_ids
    assert {"配置管理", "用户管理", "用户权限管理"}.issubset(set(visible_tab_labels))
    assert len(dummy_tabs) == 1
    assert dummy_tabs[0].get("props", {}).get("visible", True) is False
    assert len(pending_tabs) == 1
    assert pending_tabs[0].get("props", {}).get("visible", True) is False
    assert "settings-subtabs" in elem_ids
    assert "pending-access-view" in elem_ids
    assert "settings-config-tab" in elem_ids
    assert "settings-user-tab" in elem_ids
    assert "settings-permission-tab" in elem_ids
    assert "settings-config-subtabs" in elem_ids
    assert "settings-template-tab" in elem_ids
    assert "settings-knowledge-base-tab" in elem_ids
    assert "settings-workspace-panel" in elem_ids
    assert "settings-knowledge-base-panel" in elem_ids
    assert "settings-user-management-panel" in elem_ids
    assert "settings-user-list-panel" in elem_ids
    assert "settings-user-table" in elem_ids
    assert "settings-user-detail" in elem_ids
    assert "settings-user-actions" in elem_ids
    assert "settings-user-result" in elem_ids
    assert "settings-permission-management-panel" in elem_ids
    assert "settings-permission-user-panel" in elem_ids
    assert "settings-permission-user-table" in elem_ids
    assert "settings-permission-form-panel" in elem_ids
    assert "settings-permission-tab-access" in elem_ids
    assert "settings-permission-kb-access" in elem_ids
    assert "settings-permission-actions" in elem_ids
    assert "settings-permission-result" in elem_ids
    assert "settings-footer-panel" in elem_ids
    assert "settings-runtime-panel" in elem_ids
    assert "settings-main-row" in elem_ids
    assert "settings-list-actions" in elem_ids
    assert "settings-form-actions" in elem_ids
    assert "settings-basic-group" in elem_ids
    assert "settings-policy-group" in elem_ids
    assert "settings-prompt-group" in elem_ids
    assert "settings-template-list-panel" in elem_ids
    assert "settings-template-table" in elem_ids
    assert "settings-template-detail" in elem_ids
    assert "settings-template-form" in elem_ids
    assert "settings-list-actions" in elem_ids
    assert "settings-form-actions" in elem_ids
    assert "settings-knowledge-base-list-panel" in elem_ids
    assert "settings-knowledge-base-table" in elem_ids
    assert "settings-knowledge-base-detail" in elem_ids
    assert "settings-knowledge-base-form" in elem_ids
    assert "settings-knowledge-base-basic-group" in elem_ids
    assert "settings-knowledge-base-status-group" in elem_ids
    assert "settings-knowledge-base-list-actions" in elem_ids
    assert "settings-knowledge-base-actions" in elem_ids
    assert "settings-knowledge-base-result" in elem_ids
    assert "settings-export-panel" in elem_ids
    assert "settings-knowledge-base-actions" in elem_ids
    assert "settings-export-row" in elem_ids
    assert "settings-export-result" in elem_ids
    assert "模板列表" in labels
    assert "模板 ID" in labels
    assert "模板名称" in labels
    assert "知识库列表" in labels
    assert "知识库 ID" in labels
    assert "知识库名称" in labels
    assert "设为默认" in labels
    assert "系统提示词" in labels
    assert "用户提示模板" in labels
    assert "我确认删除当前模板" in labels
    assert "用户列表" in labels
    assert "权限用户" in labels
    assert "可访问菜单" in labels
    assert "可访问知识库" in labels
    assert elem_ids.index("settings-config-tab") < elem_ids.index("settings-user-tab")
    assert elem_ids.index("settings-user-tab") < elem_ids.index("settings-permission-tab")
    assert elem_ids.index("settings-config-subtabs") < elem_ids.index("settings-workspace-panel")
    assert elem_ids.index("settings-workspace-panel") < elem_ids.index("settings-knowledge-base-panel")
    assert elem_ids.index("settings-knowledge-base-panel") < elem_ids.index("settings-footer-panel")
    assert elem_ids.index("settings-template-tab") < elem_ids.index("settings-knowledge-base-tab")
    assert elem_ids.index("settings-runtime-panel") < elem_ids.index("settings-workspace-panel")
    assert elem_ids.index("settings-template-table") < elem_ids.index("settings-template-detail")
    assert elem_ids.index("settings-template-detail") < elem_ids.index("settings-template-form")
    assert elem_ids.index("settings-basic-group") < elem_ids.index("settings-policy-group")
    assert elem_ids.index("settings-policy-group") < elem_ids.index("settings-prompt-group")
    assert elem_ids.index("settings-knowledge-base-basic-group") < elem_ids.index("settings-knowledge-base-status-group")
    assert elem_ids.index("settings-export-panel") < elem_ids.index("settings-export-result")
    assert elem_ids.index("settings-export-row") < elem_ids.index("settings-export-result")
    assert any(
        component.get("props", {}).get("value") == "保存模板"
        and "ui-button--primary" in (component.get("props", {}).get("elem_classes") or [])
        for component in button_components
    )
    assert any(
        component.get("props", {}).get("value") == "删除模板"
        and "ui-button--danger" in (component.get("props", {}).get("elem_classes") or [])
        for component in button_components
    )
    assert any(
        component.get("props", {}).get("value") == "下载当前配置"
        and "ui-button--secondary" in (component.get("props", {}).get("elem_classes") or [])
        for component in button_components
    )
    assert any(
        component.get("props", {}).get("value") == "上一页"
        and "ui-button--pagination" in (component.get("props", {}).get("elem_classes") or [])
        for component in button_components
    )


def test_create_ui_app_should_place_auth_controls_beside_tab_header(tmp_path: Path) -> None:
    """登录后的用户名与退出按钮应独立挂在主 Tabs 顶部区域。"""

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
    elem_ids = [str(component.get("props", {}).get("elem_id", "")) for component in components]
    html_components = {
        str(component.get("props", {}).get("elem_id", "")): component.get("props", {})
        for component in components
        if component.get("type") == "html"
    }
    button_components = [component.get("props", {}) for component in components if component.get("type") == "button"]

    assert "main-content" in elem_ids
    assert "main-tabs" in elem_ids
    assert "auth-header-actions" in elem_ids
    assert "auth-user-display" in elem_ids
    assert "auth-logout-btn" in elem_ids
    assert elem_ids.index("auth-header-actions") < elem_ids.index("main-tabs")
    assert elem_ids.index("auth-user-display") > elem_ids.index("auth-header-actions")
    assert elem_ids.index("auth-logout-btn") > elem_ids.index("auth-header-actions")
    assert html_components["auth-user-display"].get("value") == ""
    assert any(
        props.get("value") == "退出登录" and props.get("elem_id") == "auth-logout-btn"
        for props in button_components
    )
    assert any(
        str(component.get("props", {}).get("elem_id", "")) == "auth-page"
        and component.get("props", {}).get("visible") is False
        for component in components
    )


def test_auth_interactions_should_disable_queue_to_avoid_stuck_pending_state(tmp_path: Path) -> None:
    """登录、注册与登出是轻量事件，应禁用队列避免前端持续显示处理中。"""

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
    dependency_pairs = [
        (getattr(block_fn.fn, "__name__", ""), dependency)
        for dependency in dependencies
        for block_fn in demo.fns.values()
        if block_fn._id == dependency.get("id")
    ]

    assert any(name == "_do_login" and dependency.get("queue") is False for name, dependency in dependency_pairs)
    assert any(name == "_do_register" and dependency.get("queue") is False for name, dependency in dependency_pairs)
    assert any(name == "<lambda>" and dependency.get("queue") is False for name, dependency in dependency_pairs)


def test_create_ui_app_should_only_render_three_register_inputs(tmp_path: Path) -> None:
    """注册区应只保留用户名、密码、重复密码三项输入。"""

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
    textbox_components = {
        str(component.get("props", {}).get("elem_id", "")): component.get("props", {})
        for component in components
        if component.get("type") == "textbox"
    }

    register_input_ids = {
        "auth-register-username",
        "auth-register-password",
        "auth-register-password-confirm",
    }

    assert register_input_ids.issubset(textbox_components.keys())
    assert textbox_components["auth-register-username"].get("label") == "用户名"
    assert textbox_components["auth-register-password"].get("label") == "密码"
    assert textbox_components["auth-register-password-confirm"].get("label") == "重复密码"
    assert all(
        elem_id in register_input_ids
        for elem_id in textbox_components
        if elem_id.startswith("auth-register-")
    )


def test_create_ui_app_should_hide_register_section_on_auth_page_by_default(tmp_path: Path) -> None:
    """登录页默认只显示登录区，注册区应先隐藏。"""

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
    component_props = {
        str(component.get("props", {}).get("elem_id", "")): component.get("props", {})
        for component in components
        if component.get("props", {}).get("elem_id")
    }

    assert component_props["auth-login-form"].get("visible") is True
    assert component_props["auth-register-form"].get("visible") is False


def test_restore_login_session_should_show_pending_access_tab_for_zero_permission_user(tmp_path: Path) -> None:
    """零权限用户恢复登录态后，应只显示待开通页而不显示业务菜单。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    auth_service = get_current_ui_app_module().ConnectionScopedAuthService(settings.sqlite_db_path)
    success, _message = auth_service.register_user("pending_user", "StrongPass#123")
    assert success is True

    with sqlite3.connect(settings.sqlite_db_path) as connection:
        user_id = connection.execute(
            "SELECT user_id FROM users WHERE username = ?",
            ("pending_user",),
        ).fetchone()[0]

    demo = create_ui_app(settings)
    restore_fn = next((block_fn.fn for block_fn in demo.fns.values() if getattr(block_fn.fn, "__name__", "") == "_restore_login_session"), None)
    assert restore_fn is not None

    outputs = restore_fn({"user_id": user_id, "username": "pending_user"})
    result_session = outputs[0]
    result_label = outputs[1]
    result_login = outputs[2]
    result_menu = outputs[3]
    pending_tab_update = outputs[4]
    quality_tab_update = outputs[5]
    review_tab_update = outputs[6]
    document_tab_update = outputs[7]
    search_tab_update = outputs[8]
    pageindex_tab_update = outputs[9]
    settings_tab_update = outputs[10]
    pending_access_update = outputs[11]

    assert result_session.get("user_id") == user_id
    assert result_label == "<span>pending_user</span>"
    assert result_login.get("visible") is False
    assert result_menu.get("visible") is True
    assert pending_tab_update["visible"] is True
    assert quality_tab_update["visible"] is False
    assert review_tab_update["visible"] is False
    assert document_tab_update["visible"] is False
    assert search_tab_update["visible"] is False
    assert pageindex_tab_update["visible"] is False
    assert settings_tab_update["visible"] is False
    assert "功能待开通" in pending_access_update["value"]
    assert "pending_user" in pending_access_update["value"]


def test_restore_login_session_should_preserve_active_tab_for_admin(tmp_path: Path) -> None:
    """admin 恢复登录态时只恢复权限，不得覆盖用户当前选择的 PageIndex 等标签页。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)
    with sqlite3.connect(settings.sqlite_db_path) as connection:
        # admin 已由 initialize_database 自动创建，只需更新密码
        connection.execute(
            "UPDATE users SET password_hash = ?, user_id = ?, is_active = 1 WHERE username = 'admin'",
            ("pbkdf2_sha256$1$test$hash", "admin-user-001")
        )
        connection.commit()
    with sqlite3.connect(settings.sqlite_db_path) as connection:
        admin_user_id = connection.execute(
            "SELECT user_id FROM users WHERE username = ?",
            ("admin",),
        ).fetchone()[0]

    demo = create_ui_app(settings)
    restore_fn = next((block_fn.fn for block_fn in demo.fns.values() if getattr(block_fn.fn, "__name__", "") == "_restore_login_session"), None)
    assert restore_fn is not None

    outputs = restore_fn({"user_id": admin_user_id, "username": "admin"})
    pending_tab_update = outputs[4]
    quality_tab_update = outputs[5]
    pageindex_tab_update = outputs[9]
    main_tabs_update = outputs[12]
    document_knowledge_base_update = outputs[13]
    document_target_knowledge_base_update = outputs[14]
    quality_knowledge_base_update = outputs[15]
    review_knowledge_base_update = outputs[16]
    search_knowledge_base_update = outputs[17]
    pageindex_knowledge_base_update = outputs[18]

    assert pending_tab_update["visible"] is False
    assert quality_tab_update["visible"] is True
    assert pageindex_tab_update["visible"] is True
    for knowledge_base_update in (
        document_knowledge_base_update,
        document_target_knowledge_base_update,
        quality_knowledge_base_update,
        review_knowledge_base_update,
        search_knowledge_base_update,
        pageindex_knowledge_base_update,
    ):
        assert knowledge_base_update["value"].startswith("default | ")
    assert "selected" not in main_tabs_update


def test_repeated_login_session_restore_should_not_override_active_main_tab(tmp_path: Path) -> None:
    """首次及后续登录态恢复均不得把当前页签强制切回 AI 质检。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)
    with sqlite3.connect(settings.sqlite_db_path) as connection:
        connection.execute("UPDATE users SET is_active = 1 WHERE username = 'admin'")
        admin_user_id = connection.execute(
            "SELECT user_id FROM users WHERE username = 'admin'"
        ).fetchone()[0]
        connection.commit()

    demo = create_ui_app(settings)
    restore_fn = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "_restore_login_session"
    )
    stored_session = {"user_id": admin_user_id, "username": "admin"}

    first_outputs = restore_fn(stored_session, False)
    repeated_outputs = restore_fn(stored_session, True)

    assert "selected" not in first_outputs[12]
    assert first_outputs[-1] is True
    assert "selected" not in repeated_outputs[12]
    assert repeated_outputs[-1] is True


def test_auth_refresh_should_reload_document_management_after_startup_snapshot(tmp_path: Path) -> None:
    """登录或会话恢复后，知识库管理页必须重新读取启动后发生变化的数据库状态。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)
    with sqlite3.connect(settings.sqlite_db_path) as connection:
        connection.execute("UPDATE users SET is_active = 1 WHERE username = 'admin'")
        connection.commit()

    # 先构建 UI，再写入文档，复现服务启动快照仍为 0 的场景。
    demo = create_ui_app(settings)
    document_path = settings.input_root / "default" / "after_startup.md"
    document_path.write_text("# 启动后文档\n\n用于验证认证完成后的实时刷新。", encoding="utf-8")
    DocumentRepository(settings.sqlite_db_path).upsert_document(
        {
            "doc_uid": "after_startup_default",
            "knowledge_base_id": "default",
            "doc_id": "after_startup",
            "doc_title": "启动后文档",
            "source_path": "default/after_startup.md",
            "source_hash": "startup-snapshot-test",
            "ingest_status": "completed",
            "index_status": "indexed",
            "error_message": None,
        }
    )

    with sqlite3.connect(settings.sqlite_db_path) as connection:
        admin_user_id = connection.execute(
            "SELECT user_id FROM users WHERE username = 'admin'"
        ).fetchone()[0]

    restore_fn = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "_restore_login_session"
    )
    outputs = restore_fn({"user_id": admin_user_id, "username": "admin"})
    document_outputs = outputs[-64:-24]
    assert document_outputs[2][0] == ["1", "已入库文档", "1"]
    assert document_outputs[5][0][1] == "after_startup.md"

    change_knowledge_base_fn = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "change_document_knowledge_base_ui"
    )
    changed_outputs = change_knowledge_base_fn("default | 默认知识库", build_admin_login_session())
    assert changed_outputs[6][0] == ["1", "已入库文档", "1"]
    assert changed_outputs[9][0][1] == "after_startup.md"

    dependencies = demo.config.get("dependencies", [])
    dependency_names = {
        dependency.get("id"): getattr(block_fn.fn, "__name__", "")
        for dependency in dependencies
        for block_fn in demo.fns.values()
        if block_fn._id == dependency.get("id")
    }
    auth_dependencies = [
        dependency
        for dependency in dependencies
        if dependency_names.get(dependency.get("id")) in {"_do_login", "_restore_login_session"}
    ]
    component_ids = {
        str(component.get("props", {}).get("elem_id", "")): component.get("id")
        for component in demo.config.get("components", [])
    }
    required_document_output_ids = {
        component_ids["database-summary-table"],
        component_ids["document-table"],
    }

    # 登录按钮、密码回车和浏览器会话恢复三条认证入口都必须直接刷新整页输出。
    assert len(auth_dependencies) == 3
    assert all(required_document_output_ids.issubset(set(dependency.get("outputs", []))) for dependency in auth_dependencies)


def test_restore_login_session_should_clear_review_workspace_without_kb_permission(tmp_path: Path) -> None:
    """只有人工审核菜单权限、没有知识库权限时，恢复登录后不应残留审核历史。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    auth_service = get_current_ui_app_module().ConnectionScopedAuthService(settings.sqlite_db_path)
    success, _message = auth_service.register_user("review_no_kb_user", "StrongPass#123")
    assert success is True

    with sqlite3.connect(settings.sqlite_db_path) as connection:
        user_id = connection.execute(
            "SELECT user_id FROM users WHERE username = ?",
            ("review_no_kb_user",),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO user_tab_access (user_id, tab_name) VALUES (?, ?)",
            (user_id, "人工审核"),
        )
        connection.commit()

    demo = create_ui_app(settings)
    restore_fn = next((block_fn.fn for block_fn in demo.fns.values() if getattr(block_fn.fn, "__name__", "") == "_restore_login_session"), None)
    assert restore_fn is not None

    outputs = restore_fn({"user_id": user_id, "username": "review_no_kb_user"})
    review_outputs = outputs[-24:-1]

    assert review_outputs[0] == []
    assert review_outputs[3] == []
    assert review_outputs[17] == []
    assert review_outputs[20] == []


def test_save_settings_user_permissions_ui_should_persist_selected_permissions(tmp_path: Path) -> None:
    """权限管理子页保存后，应把菜单权限和知识库权限写入数据库。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    auth_service = get_current_ui_app_module().ConnectionScopedAuthService(settings.sqlite_db_path)
    success, _message = auth_service.register_user("perm_ui_user", "StrongPass#123")
    assert success is True

    with sqlite3.connect(settings.sqlite_db_path) as connection:
        user_id = connection.execute(
            "SELECT user_id FROM users WHERE username = ?",
            ("perm_ui_user",),
        ).fetchone()[0]

    demo = create_ui_app(settings)
    save_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "save_settings_user_permissions_ui"
    )

    _outputs = save_handler(
        user_id,
        ["知识库检索", "功能设置"],
        ["default | 默认知识库"],
    )

    with sqlite3.connect(settings.sqlite_db_path) as connection:
        tab_names = [
            row[0]
            for row in connection.execute(
                "SELECT tab_name FROM user_tab_access WHERE user_id = ? ORDER BY tab_name",
                (user_id,),
            ).fetchall()
        ]
        kb_ids = [
            row[0]
            for row in connection.execute(
                "SELECT knowledge_base_id FROM user_kb_access WHERE user_id = ? ORDER BY knowledge_base_id",
                (user_id,),
            ).fetchall()
        ]

    assert tab_names == ["功能设置", "知识库检索"]
    assert kb_ids == ["default"]


def test_save_settings_user_permissions_ui_should_refresh_current_login_session(tmp_path: Path) -> None:
    """若修改的是当前登录用户，权限保存后应即时刷新登录态和主菜单可见性。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)

    auth_service = get_current_ui_app_module().ConnectionScopedAuthService(settings.sqlite_db_path)
    success, _message = auth_service.register_user("self_perm_user", "StrongPass#123")
    assert success is True

    with sqlite3.connect(settings.sqlite_db_path) as connection:
        user_id = connection.execute(
            "SELECT user_id FROM users WHERE username = ?",
            ("self_perm_user",),
        ).fetchone()[0]

    demo = create_ui_app(settings)
    save_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "save_settings_user_permissions_ui"
    )
    current_session = {
        "user_id": user_id,
        "username": "self_perm_user",
        "is_admin": False,
        "permissions": {"tab_names": ["功能设置"], "kb_ids": []},
    }

    outputs = save_handler(
        user_id,
        ["知识库检索"],
        [],
        current_session,
    )

    refreshed_session = outputs[10]
    pending_tab_update = outputs[15]
    main_tabs_update = outputs[22]
    search_tab_update = outputs[19]
    settings_tab_update = outputs[20]
    refreshed_document_rows = outputs[-43]
    refreshed_search_state = outputs[-6]
    refreshed_search_query = outputs[-5]
    refreshed_search_selected = outputs[-3]

    assert refreshed_session["user_id"] == user_id
    assert refreshed_session["permissions"]["tab_names"] == ["知识库检索"]
    assert refreshed_session["permissions"]["kb_ids"] == []
    assert pending_tab_update["visible"] is False
    assert "selected" not in main_tabs_update
    assert settings_tab_update["visible"] is False
    assert search_tab_update["visible"] is True
    assert refreshed_document_rows == []
    assert refreshed_search_state == []
    assert refreshed_search_query == ""
    assert refreshed_search_selected == {}


def test_login_state_should_use_browser_persistence_and_restore_handler(tmp_path: Path) -> None:
    """登录态应持久化到浏览器，并在刷新后通过 change 事件恢复。"""

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
    dependencies = demo.config.get("dependencies", [])
    component_types = {component.get("id"): str(component.get("type", "")) for component in components}

    browser_state_components = [component for component in components if component.get("type") == "browserstate"]
    assert browser_state_components
    assert browser_state_components[0].get("props", {}).get("storage_key") == "doc-ai-wiki-auth-session"

    dependency_pairs = [
        (getattr(block_fn.fn, "__name__", ""), dependency)
        for dependency in dependencies
        for block_fn in demo.fns.values()
        if block_fn._id == dependency.get("id")
    ]

    assert any(
        name == "_restore_login_session"
        and any(target[1] == "change" for target in dependency.get("targets", []))
        and "state" in {component_types.get(output_id, "") for output_id in dependency.get("outputs", [])}
        for name, dependency in dependency_pairs
    )


def test_input_driven_controls_should_not_use_change_events_on_startup(tmp_path: Path) -> None:
    """知识库切换、筛选和 Claim 选择应只响应用户输入，避免首屏自动触发 processing。"""

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
    dependency_pairs = [
        (getattr(block_fn.fn, "__name__", ""), dependency)
        for dependency in dependencies
        for block_fn in demo.fns.values()
        if block_fn._id == dependency.get("id")
    ]

    expected_input_handlers = {
        "change_document_knowledge_base_ui",
        "change_search_knowledge_base_ui",
        "render_quality_template",
        "change_quality_knowledge_base_ui",
        "select_quality_claim",
        "select_settings_knowledge_base",
        "change_review_knowledge_base_ui",
        "change_review_filters",
    }

    for handler_name in expected_input_handlers:
        assert any(
            name == handler_name and any(target[1] == "input" for target in dependency.get("targets", []))
            for name, dependency in dependency_pairs
        ), handler_name

    assert any(
        name == "list_recent_quality_results_ui" and any(target[1] == "input" for target in dependency.get("targets", []))
        for name, dependency in dependency_pairs
    )


def test_create_ui_app_should_register_document_management_event_handlers(tmp_path: Path) -> None:
    """文档管理页 builder / binder 接线后，关键交互处理器仍应被注册。"""

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
    dependency_pairs = [
        (getattr(block_fn.fn, "__name__", ""), dependency)
        for dependency in dependencies
        for block_fn in demo.fns.values()
        if block_fn._id == dependency.get("id")
    ]

    expected_handlers = {
        "change_document_knowledge_base_ui": "input",
        "load_document_management_state_ui": "click",
        "reassign_selected_document_ui": "click",
        "inspect_document_ui": "input",
        "register_selected_document_ui": "click",
        "register_all_documents_ui": "click",
        "query_ingest_status_ui": "click",
        "rebuild_selected_document_ui": "click",
        "inspect_selected_document_quality_ui": "click",
        "run_document_quality_search_ui": "click",
        "select_document_quality_search_result": "select",
        "export_document_quality_result": "click",
        "export_document_quality_search_result": "click",
        "run_batch_document_quality_ui": "click",
        "export_document_quality_batch_result": "click",
        "export_document_quality_csv": "click",
        "save_document_quality_config": "click",
        "export_document_quality_config_result": "click",
    }

    for handler_name, event_name in expected_handlers.items():
        assert any(
            name == handler_name and any(target[1] == event_name for target in dependency.get("targets", []))
            for name, dependency in dependency_pairs
        ), handler_name


def test_create_ui_app_should_include_document_quality_workspace(tmp_path: Path) -> None:
    """文档管理页应提供突出显示的当前文档区，以及底部折叠的入库质检区。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)
    document_path = settings.input_root / "a1.md"
    document_path.write_text("# 总论\n阿胶历史资料。\n\n## 典籍\n《本草纲目》记载。\n", encoding="utf-8")
    IngestService(settings).register_document({"file_path": str(document_path)})

    demo = create_ui_app(settings)
    components = demo.config.get("components", [])
    elem_ids = [str(component.get("props", {}).get("elem_id", "")) for component in components]
    labels = [str(component.get("props", {}).get("label", "")) for component in components]
    html_values = [
        str(component.get("props", {}).get("value", ""))
        for component in components
        if component.get("type") == "html"
    ]
    dataframes = {
        str(component.get("props", {}).get("elem_id", "")): component.get("props", {})
        for component in components
        if component.get("type") == "dataframe"
    }
    layout_components = {
        str(component.get("props", {}).get("elem_id", "")): component.get("props", {})
        for component in components
        if component.get("props", {}).get("elem_id")
    }

    assert "document-current-panel" in elem_ids
    assert "document-knowledge-base" in elem_ids
    assert "document-target-knowledge-base" in elem_ids
    assert "document-move-button" in elem_ids
    assert "document-current-actions-row" in elem_ids
    assert "document-current-title" in elem_ids
    assert "document-quality-accordion" in elem_ids
    assert "document-quality-panel" in elem_ids
    assert "document-quality-top-actions" in elem_ids
    assert "document-quality-report" in elem_ids
    assert "document-quality-checks" in elem_ids
    assert "document-quality-sections-table" in elem_ids
    assert "document-quality-chunks-table" in elem_ids
    assert "document-quality-search-summary" in elem_ids
    assert "document-quality-search-action-row" in elem_ids
    assert "document-quality-search-results" in elem_ids
    assert "document-quality-search-detail" in elem_ids
    assert "document-quality-search-export-result" in elem_ids
    assert "document-quality-batch-summary" in elem_ids
    assert "document-quality-batch-table" in elem_ids
    assert "document-quality-config-panel" in elem_ids
    assert "document-quality-config-result" in elem_ids
    assert "document-quality-config-action-row" in elem_ids
    assert "document-quality-config-form" in elem_ids
    assert "document-quality-config-form-row-1" in elem_ids
    assert "document-quality-config-form-row-2" in elem_ids
    assert "document-quality-config-form-row-3" in elem_ids
    assert "document-quality-config-form-row-4" in elem_ids
    assert "document-quality-export-result" in elem_ids
    assert "document-quality-csv-export-result" in elem_ids
    assert "document-quality-batch-export-result" in elem_ids
    assert "document-quality-config-export-result" in elem_ids
    assert "database-page-info" in elem_ids
    assert "document-page-info" in elem_ids
    assert "document-register-result" in elem_ids
    assert "document-rebuild-result" in elem_ids
    assert "document-quality-sections-page-info" in elem_ids
    assert "document-quality-chunks-page-info" in elem_ids
    assert "document-quality-search-page-info" in elem_ids
    assert "document-quality-batch-page-info" in elem_ids
    assert "search-page-info" in elem_ids
    assert "settings-template-page-info" in elem_ids
    assert "settings-knowledge-base-page-info" in elem_ids
    assert "章节抽样" in labels
    assert "分块抽样" in labels
    assert "文档内检索验证" in labels
    assert "批量质检结果" in labels
    assert "抽样数量" in labels
    assert "长文字数阈值" in labels
    assert "长文最少章节" in labels
    assert "每章分块上限" in labels
    assert "超长分块阈值" in labels
    assert "过短分块阈值" in labels
    assert "过短分块告警起点" in labels
    assert any("入库质检" in value for value in html_values)
    assert any("当前选中文档" in str(component.get("props", {}).get("value", "")) for component in components)
    assert dataframes["document-quality-sections-table"]["headers"][0] == "序号"
    assert dataframes["document-quality-chunks-table"]["headers"][0] == "序号"
    assert dataframes["document-quality-batch-table"]["headers"][0] == "序号"
    assert layout_components["document-quality-search-row"].get("equal_height") in (None, False)
    assert elem_ids.index("document-quality-search-row") < elem_ids.index("document-quality-search-export-result")
    assert elem_ids.index("document-quality-config-action-row") < elem_ids.index("document-quality-config-export-result")


def test_create_ui_app_should_include_quality_evaluation_workspace(tmp_path: Path) -> None:
    """AI 质检页应提供效果评测输入、摘要和明细表。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    components = demo.config.get("components", [])
    elem_ids = [str(component.get("props", {}).get("elem_id", "")) for component in components]
    labels = [str(component.get("props", {}).get("label", "")) for component in components]
    template_dropdowns = [
        component.get("props", {})
        for component in components
        if component.get("type") == "dropdown" and component.get("props", {}).get("label") == "质检模板"
    ]

    assert "quality-evaluation-panel" in elem_ids
    assert "quality-evaluation-help" in elem_ids
    assert "quality-evaluation-summary" in elem_ids
    assert "quality-evaluation-table" in elem_ids
    assert "效果评测样例 JSON" in labels
    assert "效果评测明细" in labels
    assert template_dropdowns
    assert "general_fact_check" in str(template_dropdowns[0].get("value"))

    evaluation_help_panels = [
        component.get("props", {})
        for component in components
        if component.get("type") == "html" and component.get("props", {}).get("elem_id") == "quality-evaluation-help"
    ]
    assert evaluation_help_panels
    assert "效果评测用于验证 AI 质检结果是否符合你的预期" in str(evaluation_help_panels[0].get("value", ""))
    assert "核心命中" in str(evaluation_help_panels[0].get("value", ""))
    assert "宽松命中" in str(evaluation_help_panels[0].get("value", ""))


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
    assert candidate_tables[0]["value"]["data"][0][1] == "claim_review_demo"
    assert "Claim 详情" in str(claim_details[0].get("value", ""))
    assert "阿胶源于驴皮熬制" in str(claim_details[0].get("value", ""))


def test_create_ui_app_should_preload_recent_quality_records_without_replaying_result(tmp_path: Path) -> None:
    """AI 质检页首次进入时应加载历史列表，但不自动回放旧质检结果。"""

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
    claim_selectors = [
        component.get("props", {})
        for component in components
        if component.get("type") == "radio" and component.get("props", {}).get("elem_id") == "quality-claims-table"
    ]
    result_panels = [
        str(component.get("props", {}).get("value", ""))
        for component in components
        if component.get("type") == "html" and component.get("props", {}).get("elem_id") == "quality-result-panel"
    ]

    assert recent_tables
    assert claim_selectors
    # 历史列表可自动展示，但不能把旧结果回放成当前质检结果。
    recent_rows = recent_tables[0].get("value", {}).get("data", [])
    assert recent_rows
    assert recent_rows[0][1] == "chkres_demo_001"
    assert claim_selectors[0].get("choices", []) == []
    assert result_panels
    assert "chkres_demo_001" not in result_panels[0]


def test_create_ui_app_should_paginate_more_than_ten_recent_quality_records(tmp_path: Path) -> None:
    """主动加载最近质检记录后，超过 10 条时应通过分页继续展示后续数据。"""

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
    for index in range(12):
        check_id = f"chkres_demo_{index:03d}"
        claim_id = f"claim_demo_{index:03d}"
        repository.create_quality_result(
            quality_check={
                "check_id": check_id,
                "input_text": f"样例输入 {index}",
                "template_id": "general_fact_check",
                "template_name": "通用事实核检",
                "overall_verdict": "needs_review",
                "risk_level": "medium",
                "summary": f"样例摘要 {index}",
                "created_at": f"2026-05-01T12:{index:02d}:00+00:00",
                "updated_at": f"2026-05-01T12:{index:02d}:00+00:00",
            },
            claims=[
                {
                    "claim_id": claim_id,
                    "check_id": check_id,
                    "claim_text": f"样例 Claim {index}",
                    "verdict": "needs_review",
                    "risk_level": "medium",
                    "confidence": 0.8,
                    "evidence": f"样例证据 {index}",
                    "source_doc": "测试文档",
                    "source_span": f"section-{index}",
                    "review_status": "pending",
                    "created_at": f"2026-05-01T12:{index:02d}:00+00:00",
                    "updated_at": f"2026-05-01T12:{index:02d}:00+00:00",
                }
            ],
            rule_hits=[],
        )

    demo = create_ui_app(settings)
    list_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "list_recent_quality_results_ui"
    )

    outputs = list_handler("default | 默认知识库", "全部历史", build_admin_login_session())
    recent_state = outputs[16]
    recent_rows = outputs[17]

    assert len(recent_state) == 12
    assert len(recent_rows) == 10


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
    claim_detail_map = {
        "claim_1": {
            "claim_id": "claim_1",
            "claim_text": "第一条 Claim",
            "verdict": "rejected",
            "risk_level": "high",
            "confidence": 1.0,
            "evidence_judgement": "contradict",
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
                    "evidence_relation": "contradict",
                    "retrieval_source": "vector",
                    "matched_sources": ["vector"],
                    "matched_queries": ["claim_literal"],
                    "rerank_score": None,
                    "relation_reason": "存在反证。",
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
            "evidence_judgement": "insufficient",
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
                    "evidence_relation": "insufficient",
                    "retrieval_source": "fulltext",
                    "matched_sources": ["fulltext"],
                    "matched_queries": ["logic_relaxed"],
                    "rerank_score": 0.7,
                    "relation_reason": "边界证据不足。",
                    "content_preview": "第二条证据内容",
                }
            ],
        },
    }
    formatted_result = {"check": {"overall_verdict": "needs_review", "risk_level": "medium"}}

    (
        claim_view,
        evidence_rows,
        evidence_page,
        evidence_page_info,
        review_view,
        selected_claim_id,
        evidence_items,
        evidence_detail,
        evaluation_cases,
    ) = select_handler(
        "claim_2 | 第 2 条 | 需复核 | 中级 | 第二条 Claim",
        claim_detail_map,
        formatted_result,
    )

    assert evidence_page == 1
    assert "第 1 / 1 页" in evidence_page_info
    assert selected_claim_id.startswith("claim_2")
    assert "第二条 Claim" in claim_view
    assert "证据关系" in claim_view
    assert "证据不足" in claim_view
    assert "section-2:chunk-2" in claim_view
    assert "第二条 Claim" in review_view
    assert len(evidence_items) == 1
    assert "第二条证据内容" in evidence_detail
    assert evidence_rows == [["1", "chunk_2", "标题二", "section-2:chunk-2", "证据不足", "fulltext", "logic_relaxed", "0.700", "第二条证据内容"]]
    assert "claim_2" in evaluation_cases
    assert "第二条 Claim" in evaluation_cases


def test_quality_check_ui_should_finish_with_error_when_stream_crashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """质检流异常时，前端必须收到终态错误，而不能一直停在运行中。"""

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
    quality_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "run_quality_check_ui"
    )
    def failing_stream(*args, **kwargs):
        yield {
            "type": "progress",
            "status": "running",
            "stage": "prepare",
            "message": "开始执行",
            "claim_index": 0,
            "claim_total": 1,
        }
        raise RuntimeError("simulated quality stream failure")

    monkeypatch.setattr(QualityService, "run_check_stream", failing_stream)

    outputs = list(
        quality_handler(
            "测试质检异常",
            "general_fact_check | 通用事实核检",
            "default | 默认知识库",
            None,
        )
    )

    assert len(outputs) == 2
    assert "错误代码：QUALITY_CHECK_FAILED" in outputs[-1][1]
    assert "失败" in outputs[-1][0]


def test_quality_check_ui_should_render_final_result_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """质检流返回 result 事件时，前端应展示最终质检 ID。"""

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
    quality_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "run_quality_check_ui"
    )

    def successful_stream(*args, **kwargs):
        yield {
            "type": "progress",
            "status": "running",
            "stage": "prepare",
            "message": "开始执行",
            "claim_index": 0,
            "claim_total": 1,
        }
        yield {
            "type": "result",
            "status": "success",
            "stage": "persist",
            "message": "质检已完成",
            "result": {
                "check": {
                    "check_id": "chkres_ui_success",
                    "template_name": "通用事实核检",
                    "overall_verdict": "passed",
                    "summary": "共 1 条 claim，verified 1 条。",
                    "created_at": "2026-07-21T00:00:00+00:00",
                    "updated_at": "2026-07-21T00:00:00+00:00",
                    "persist_verified": True,
                },
                "claims": [
                    {
                        "claim_id": "claim_ui_success",
                        "claim_text": "测试事实",
                        "verdict": "passed",
                        "risk_level": "low",
                        "confidence": 1.0,
                        "evidence_judgement": "support",
                        "review_status": "pending",
                        "evidence_details": [],
                    }
                ],
                "rule_hits": [],
            },
        }

    monkeypatch.setattr(QualityService, "run_check_stream", successful_stream)

    outputs = list(
        quality_handler(
            "测试事实",
            "general_fact_check | 通用事实核检",
            "default | 默认知识库",
            None,
        )
    )

    assert len(outputs) == 2
    assert "chkres_ui_success" in outputs[-1][1]
    assert "已完成" in outputs[-1][0]


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
            "evidence_relation": "support",
            "retrieval_source": "vector",
            "matched_sources": ["vector"],
            "matched_queries": ["claim_literal"],
            "rerank_score": None,
            "relation_reason": "直接支持。",
            "content_preview": "第一条证据内容",
        },
        {
            "chunk_id": "chunk_2",
            "doc_title": "标题二",
            "source_span": "section-2:chunk-2",
            "evidence_relation": "contradict",
            "retrieval_source": "fulltext",
            "matched_sources": ["fulltext"],
            "matched_queries": ["logic_relaxed"],
            "rerank_score": 0.7,
            "relation_reason": "出现反证。",
            "content_preview": "第二条证据内容",
        },
    ]
    event = gr.SelectData(None, {"index": [1, 0], "value": "chunk_2"})

    current_page_rows = [
        ["1", "chunk_1", "标题一", "section-1:chunk-1", "支持", "vector", "claim_literal", "-", "第一条证据内容"],
        ["2", "chunk_2", "标题二", "section-2:chunk-2", "矛盾", "fulltext", "logic_relaxed", "0.700", "第二条证据内容"],
    ]
    evidence_detail = select_handler(evidence_items, event, current_page_rows)

    assert "证据详情" in evidence_detail
    assert "标题二" in evidence_detail
    assert "section-2:chunk-2" in evidence_detail
    assert "矛盾" in evidence_detail
    assert "第二条证据内容" in evidence_detail


def test_settings_knowledge_base_refresh_should_return_all_selector_choices(tmp_path: Path) -> None:
    """功能设置页知识库列表刷新后应返回完整选择项，而不是只保留首条。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)
    ingest_service = IngestService(settings)
    ingest_service.save_knowledge_base(
        {
            "knowledge_base_id": "kb_acceptance_7860",
            "knowledge_base_name": "验收知识库7860",
            "description": "7860端口联动验收用",
        }
    )

    demo = create_ui_app(settings)
    refresh_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "refresh_settings_knowledge_base_workspace_ui"
    )

    outputs = refresh_handler("default")
    selector_update = outputs[0]

    assert len(selector_update["choices"]) == 2
    assert any(choice.startswith("default | ") for choice in selector_update["choices"])
    assert any(choice.startswith("kb_acceptance_7860 | ") for choice in selector_update["choices"])
    assert outputs[4] == "default"


def test_save_knowledge_base_ui_should_refresh_all_page_dropdown_choices(tmp_path: Path) -> None:
    """保存知识库后，四个页面顶部下拉都应同步拿到新知识库选项。"""

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
    save_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "save_settings_knowledge_base_ui"
    )

    outputs = save_handler(
        "",
        "kb_sync_acceptance",
        "联动验收知识库",
        "用于验证四个页面顶部下拉联动",
        "active",
        False,
    )

    settings_selector_update = outputs[0]
    document_selector_update = outputs[12]
    search_selector_update = outputs[13]
    quality_selector_update = outputs[14]
    review_selector_update = outputs[15]

    for selector_update in (
        settings_selector_update,
        document_selector_update,
        search_selector_update,
        quality_selector_update,
        review_selector_update,
    ):
        assert any(choice.startswith("default | ") for choice in selector_update["choices"])
        assert any(choice.startswith("kb_sync_acceptance | ") for choice in selector_update["choices"])

    assert document_selector_update["value"].startswith("kb_sync_acceptance | ")
    assert search_selector_update["value"].startswith("kb_sync_acceptance | ")
    assert quality_selector_update["value"].startswith("kb_sync_acceptance | ")
    assert review_selector_update["value"].startswith("kb_sync_acceptance | ")
    assert (settings.input_root / "kb_sync_acceptance").exists()


def test_load_document_management_state_ui_should_migrate_legacy_root_files_and_keep_kb_isolated(tmp_path: Path) -> None:
    """文档管理页加载时，应迁移默认知识库历史文件，并且切换知识库后不串库。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)

    legacy_root_file = settings.input_root / "a1.md"
    default_file = settings.input_root / "default" / "a2.md"
    legacy_root_file.write_text("# 历史文档\n\n默认知识库历史文件。", encoding="utf-8")
    default_file.write_text("# 默认文档\n\n默认知识库目录文件。", encoding="utf-8")

    ingest_service = IngestService(settings)
    ingest_service.save_knowledge_base(
        {
            "knowledge_base_id": "kb_isolated",
            "knowledge_base_name": "隔离知识库",
            "description": "用于验证知识库切换隔离",
        }
    )
    kb_file = settings.input_root / "kb_isolated" / "kb.md"
    kb_file.write_text("# 隔离文档\n\n只属于 kb_isolated。", encoding="utf-8")

    demo = create_ui_app(settings)
    load_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "load_document_management_state_ui"
    )

    default_outputs = load_handler("default | 默认知识库", build_admin_login_session())
    isolated_outputs = load_handler("kb_isolated | 隔离知识库", build_admin_login_session())

    migrated_file = settings.input_root / "default" / "a1.md"
    default_file_names = {row[1] for row in default_outputs[5]}
    isolated_file_names = {row[1] for row in isolated_outputs[5]}

    assert not legacy_root_file.exists()
    assert migrated_file.exists()
    assert default_file_names == {"a1.md", "a2.md"}
    assert isolated_file_names == {"kb.md"}


def test_load_document_management_state_ui_should_deduplicate_default_documents_when_db_uses_legacy_root_paths(
    tmp_path: Path,
) -> None:
    """默认知识库文件已迁移后，页面加载应自动修正旧路径，避免同一文档显示两次。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)

    first_file = settings.input_root / "default" / "a1.md"
    second_file = settings.input_root / "default" / "a2.md"
    first_file.write_text("# 文档一\n\n默认知识库文件一。", encoding="utf-8")
    second_file.write_text("# 文档二\n\n默认知识库文件二。", encoding="utf-8")

    repository = DocumentRepository(settings.sqlite_db_path)
    repository.upsert_document(
        {
            "doc_uid": "doc_default_1",
            "knowledge_base_id": "default",
            "doc_id": "default_1",
            "doc_title": "阿胶历史文化通典",
            "source_path": str((settings.input_root / "a1.md").resolve()),
            "source_hash": "hash-default-1",
            "ingest_status": "completed",
            "index_status": "indexed",
            "error_message": None,
        }
    )
    repository.upsert_document(
        {
            "doc_uid": "doc_default_2",
            "knowledge_base_id": "default",
            "doc_id": "default_2",
            "doc_title": "阿胶学术论文全集",
            "source_path": str((settings.input_root / "a2.md").resolve()),
            "source_hash": "hash-default-2",
            "ingest_status": "completed",
            "index_status": "indexed",
            "error_message": None,
        }
    )

    demo = create_ui_app(settings)
    load_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "load_document_management_state_ui"
    )

    default_outputs = load_handler("default | 默认知识库", build_admin_login_session())
    default_rows = default_outputs[5]
    default_file_names = {row[1] for row in default_rows}
    registered_labels = {row[1]: row[6] for row in default_rows}

    assert len(default_rows) == 2
    assert default_file_names == {"a1.md", "a2.md"}
    assert registered_labels == {"a1.md": "是", "a2.md": "是"}

    with sqlite3.connect(settings.sqlite_db_path) as connection:
        repaired_paths = {
            row[0]: row[1]
            for row in connection.execute(
                "select doc_uid, source_path from documents where knowledge_base_id = 'default'"
            ).fetchall()
        }

    assert repaired_paths["doc_default_1"] == "default/a1.md"
    assert repaired_paths["doc_default_2"] == "default/a2.md"


def test_register_all_documents_ui_should_only_register_current_knowledge_base_files(tmp_path: Path) -> None:
    """批量注册应只处理当前知识库子目录中的文档。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)

    ingest_service = IngestService(settings)
    ingest_service.save_knowledge_base(
        {
            "knowledge_base_id": "kb_batch_only",
            "knowledge_base_name": "批量隔离知识库",
            "description": "用于验证批量注册隔离",
        }
    )
    (settings.input_root / "default" / "default_only.md").write_text("# 默认文档\n\n只属于 default。", encoding="utf-8")
    (settings.input_root / "kb_batch_only" / "batch_only.md").write_text(
        "# 目标文档\n\n只属于 kb_batch_only。",
        encoding="utf-8",
    )

    demo = create_ui_app(settings)
    register_all_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "register_all_documents_ui"
    )

    admin_session = build_admin_login_session()
    default_outputs = register_all_handler("default | 默认知识库", admin_session)
    with sqlite3.connect(settings.sqlite_db_path) as connection:
        default_count = connection.execute("select count(*) from documents where knowledge_base_id = 'default'").fetchone()[0]
        other_count = connection.execute(
            "select count(*) from documents where knowledge_base_id = 'kb_batch_only'"
        ).fetchone()[0]

    assert "批量注册结果" in default_outputs[0]
    assert "成功" in default_outputs[0]
    assert default_count == 1
    assert other_count == 0

    other_outputs = register_all_handler("kb_batch_only | 批量隔离知识库", admin_session)
    with sqlite3.connect(settings.sqlite_db_path) as connection:
        default_count_after = connection.execute("select count(*) from documents where knowledge_base_id = 'default'").fetchone()[0]
        other_count_after = connection.execute(
            "select count(*) from documents where knowledge_base_id = 'kb_batch_only'"
        ).fetchone()[0]

    assert "批量注册结果" in other_outputs[0]
    assert "成功" in other_outputs[0]
    assert default_count_after == 1
    assert other_count_after == 1


def test_document_management_handlers_should_reject_missing_login_session(tmp_path: Path) -> None:
    """知识库管理页关键 handler 缺少登录态时，不应扫描或注册文档。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)
    (settings.input_root / "default" / "missing_session.md").write_text(
        "# 未登录文档\n\n缺少登录态时不应被扫描或注册。",
        encoding="utf-8",
    )

    demo = create_ui_app(settings)
    load_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "load_document_management_state_ui"
    )
    register_all_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "register_all_documents_ui"
    )

    load_outputs = load_handler("default | 默认知识库")
    register_outputs = register_all_handler("default | 默认知识库")
    with sqlite3.connect(settings.sqlite_db_path) as connection:
        document_count = connection.execute("select count(*) from documents").fetchone()[0]

    assert load_outputs[5] == []
    assert "当前账号没有知识库管理权限或可用知识库" in register_outputs[0]
    assert document_count == 0


def test_reassign_selected_document_ui_should_move_file_and_refresh_workspace(tmp_path: Path) -> None:
    """调整归属后，应移动文件、更新数据库，并刷新当前知识库列表。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)

    ingest_service = IngestService(settings)
    ingest_service.save_knowledge_base(
        {
            "knowledge_base_id": "kb_reassign_target",
            "knowledge_base_name": "归属目标知识库",
            "description": "用于验证归属调整",
        }
    )
    source_file = settings.input_root / "default" / "to_move.md"
    source_file.write_text("# 待迁移文档\n\n需要调整知识库归属。", encoding="utf-8")

    demo = create_ui_app(settings)
    load_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "load_document_management_state_ui"
    )
    register_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "register_selected_document_ui"
    )
    reassign_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "reassign_selected_document_ui"
    )

    admin_session = build_admin_login_session()
    default_workspace = load_handler("default | 默认知识库", admin_session)
    selected_choice = default_workspace[8].value
    register_handler(selected_choice, "default | 默认知识库", admin_session)
    reassign_outputs = reassign_handler(
        selected_choice,
        "kb_reassign_target | 归属目标知识库",
        "default | 默认知识库",
        admin_session,
    )
    target_workspace = load_handler("kb_reassign_target | 归属目标知识库", admin_session)

    target_file = settings.input_root / "kb_reassign_target" / "to_move.md"
    with sqlite3.connect(settings.sqlite_db_path) as connection:
        moved_document = connection.execute(
            "select knowledge_base_id, source_path from documents where doc_title = ?",
            ("待迁移文档",),
        ).fetchone()

    assert "归属调整结果" in reassign_outputs[0]
    assert "kb_reassign_target" in reassign_outputs[0]
    assert not source_file.exists()
    assert target_file.exists()
    assert moved_document is not None
    assert moved_document[0] == "kb_reassign_target"
    assert moved_document[1] == "kb_reassign_target/to_move.md"
    assert reassign_outputs[6] == []
    assert {row[1] for row in target_workspace[5]} == {"to_move.md"}


def test_rebuild_selected_document_ui_should_reject_uningested_document(tmp_path: Path) -> None:
    """未入库文档点击重建时，应返回明确错误而不是静默失败。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)

    pending_file = settings.input_root / "default" / "pending.md"
    pending_file.write_text("# 待重建文档\n\n尚未注册。", encoding="utf-8")

    demo = create_ui_app(settings)
    load_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "load_document_management_state_ui"
    )
    rebuild_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "rebuild_selected_document_ui"
    )

    default_workspace = load_handler("default | 默认知识库", build_admin_login_session())
    selected_choice = default_workspace[8].value
    rebuild_outputs = rebuild_handler(selected_choice, "default | 默认知识库", build_admin_login_session())

    assert "重建结果" in rebuild_outputs[0]
    assert "当前文档尚未入库，无法重建" in rebuild_outputs[0]
    assert {row[1] for row in rebuild_outputs[6]} == {"pending.md"}


def test_change_quality_knowledge_base_ui_should_sync_all_page_dropdown_values(tmp_path: Path) -> None:
    """切换 AI 质检页知识库后，四个页面顶部下拉都应同步当前值。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)
    ingest_service = IngestService(settings)
    ingest_service.save_knowledge_base(
        {
            "knowledge_base_id": "kb_sync_runtime",
            "knowledge_base_name": "运行时联动知识库",
            "description": "验证页面切换时同步当前值",
        }
    )

    demo = create_ui_app(settings)
    change_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "change_quality_knowledge_base_ui"
    )

    outputs = change_handler("kb_sync_runtime | 运行时联动知识库")

    document_selector_update = outputs[0]
    search_selector_update = outputs[1]
    quality_selector_update = outputs[2]
    review_selector_update = outputs[3]

    for selector_update in (
        document_selector_update,
        search_selector_update,
        quality_selector_update,
        review_selector_update,
    ):
        assert selector_update["value"].startswith("kb_sync_runtime | ")
        assert any(choice.startswith("default | ") for choice in selector_update["choices"])
        assert any(choice.startswith("kb_sync_runtime | ") for choice in selector_update["choices"])
    # 切换知识库只同步选择器，不自动回放历史质检记录。
    assert outputs[7].get("claims", []) == []
    assert outputs[20] == []
    assert outputs[21] == []


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
    recent_results = []
    for index in range(10):
        recent_results.append(
            {
                "check_id": f"chkres_pre_{index}",
                "input_text": f"前置输入 {index}",
                "template_id": "t_pre",
                "template_name": f"模板前置{index}",
                "overall_verdict": "supported",
                "risk_level": "low",
                "created_at": f"2026-05-01T0{index}:00:00+00:00",
                "claims": [
                    {
                        "claim_id": f"claim_pre_{index}",
                        "claim_text": f"前置 Claim {index}",
                        "verdict": "supported",
                        "risk_level": "low",
                        "confidence": 0.95,
                        "evidence_judgement": "support",
                        "evidence": f"前置证据摘要 {index}",
                        "evidence_reason": f"前置说明 {index}",
                        "source_doc": "文档前置",
                        "source_span": f"section-pre-{index}",
                        "review_status": "pending",
                        "evidence_details": [],
                    }
                ],
            }
        )
    recent_results.extend(
        [
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
                        "evidence_judgement": "support",
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
                                "evidence_relation": "support",
                                "retrieval_source": "vector",
                                "matched_sources": ["vector"],
                                "matched_queries": ["claim_literal"],
                                "rerank_score": 0.91,
                                "relation_reason": "直接支持。",
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
                        "claim_text": "第二条 Claim 1",
                        "verdict": "needs_review",
                        "risk_level": "medium",
                        "confidence": 0.82,
                        "evidence_judgement": "insufficient",
                        "evidence": "第二条证据摘要 1",
                        "evidence_reason": "第二条说明 1",
                        "source_doc": "文档二",
                        "source_span": "section-2",
                        "review_status": "pending",
                        "evidence_details": [
                            {
                                "chunk_id": "chunk_b1",
                                "doc_title": "文档二",
                                "source_span": "section-2",
                                "evidence_relation": "contradict",
                                "retrieval_source": "fulltext",
                                "matched_sources": ["fulltext"],
                                "matched_queries": ["logic_relaxed"],
                                "rerank_score": 0.73,
                                "relation_reason": "补充检索命中反证。",
                                "content_preview": "第二条证据内容 1",
                            }
                        ],
                    },
                    {
                        "claim_id": "claim_b2",
                        "claim_text": "第二条 Claim 2",
                        "verdict": "rejected",
                        "risk_level": "high",
                        "confidence": 0.88,
                        "evidence_judgement": "contradict",
                        "evidence": "第二条证据摘要 2",
                        "evidence_reason": "第二条说明 2",
                        "source_doc": "文档二",
                        "source_span": "section-3",
                        "review_status": "pending",
                        "evidence_details": [],
                    },
                    {
                        "claim_id": "claim_b3",
                        "claim_text": "第二条 Claim 3",
                        "verdict": "supported",
                        "risk_level": "low",
                        "confidence": 0.77,
                        "evidence_judgement": "support",
                        "evidence": "第二条证据摘要 3",
                        "evidence_reason": "第二条说明 3",
                        "source_doc": "文档二",
                        "source_span": "section-4",
                        "review_status": "pending",
                        "evidence_details": [],
                    },
                    {
                        "claim_id": "claim_b4",
                        "claim_text": "第二条 Claim 4",
                        "verdict": "needs_review",
                        "risk_level": "medium",
                        "confidence": 0.69,
                        "evidence_judgement": "insufficient",
                        "evidence": "第二条证据摘要 4",
                        "evidence_reason": "第二条说明 4",
                        "source_doc": "文档二",
                        "source_span": "section-5",
                        "review_status": "pending",
                        "evidence_details": [],
                    },
                ],
            },
        ]
    )
    event = gr.SelectData(None, {"index": [1, 0], "value": "chkres_b"})

    current_page_rows = [["11", "", "chkres_a", "模板一", "通过", "1", "0", "26-05-01 20:00", "第一条输入"], ["12", "", "chkres_a", "模板一", "通过", "1", "0", "26-05-01 20:00", "第一条输入"]]
    (
        progress_html,
        result_html,
        active_check_html,
        formatted_result,
        claim_rows,
        claim_page,
        claim_page_info,
        selected_claim_id,
        claim_detail_map,
        claim_detail_html,
        evidence_rows,
        evidence_page,
        evidence_page_info,
        review_view,
        evidence_items,
        evidence_detail_html,
        recent_state,
        recent_rows,
        recent_page,
        recent_page_info,
        evaluation_cases,
    ) = select_handler(current_page_rows, recent_results, 2, None, "全部历史任务", event)

    assert claim_rows.get("__type__") == "update"
    assert claim_page == 1
    assert evidence_page == 1
    assert recent_page == 2
    assert "第 1 / 1 页" in claim_page_info["value"]
    assert "第 1 / 1 页" in evidence_page_info["value"]
    assert "第 2 / 2 页" in recent_page_info["value"]
    assert recent_state == recent_results
    assert recent_rows.get("__type__") == "update"
    assert recent_rows.get("value", [])[0][1] == "chkres_a"
    assert recent_rows.get("value", [])[1][1] == "chkres_b"
    assert recent_rows.get("value", [])[1][5] == "4"
    assert "已加载历史质检记录" in progress_html["value"]
    assert "模板二" in result_html["value"]
    assert "当前激活质检" in active_check_html["value"]
    assert "chkres_b" in active_check_html["value"]
    assert formatted_result["check"]["check_id"] == "chkres_b"
    assert "第二条 Claim 1" in claim_detail_html["value"]
    assert "证据关系" in claim_detail_html["value"]
    assert "第二条 Claim 1" in review_view["value"]
    assert selected_claim_id.startswith("claim_b1 |")
    assert "claim_b1" in claim_detail_map
    assert len(claim_rows.get("choices", [])) == 4
    assert "claim_b1" in str(claim_rows.get("value"))
    assert "claim_b1" in str(claim_rows.get("choices", [])[0])
    assert "claim_b4" in str(claim_rows.get("choices", [])[3])
    assert evidence_rows.get("__type__") == "update"
    assert evidence_rows.get("row_count") == 1
    assert evidence_rows.get("value") == [["1", "chunk_b1", "文档二", "section-2", "矛盾", "fulltext", "logic_relaxed", "0.730", "第二条证据内容 1"]]
    assert len(evidence_items) == 1
    assert "claim_b1" in evaluation_cases["value"]
    assert "claim_b1" in evaluation_cases["value"]
    assert "第二条证据内容 1" in evidence_detail_html["value"]


def test_list_recent_quality_results_ui_should_support_pending_history_filter(tmp_path: Path) -> None:
    """历史质检记录应支持只看含待处理 Claim 的任务。"""

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
            "check_id": "chkres_pending_only",
            "input_text": "待处理任务",
            "template_id": "t1",
            "template_name": "模板一",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "存在待处理 Claim",
            "created_at": "2026-05-01T12:00:00+00:00",
            "updated_at": "2026-05-01T12:00:00+00:00",
        },
        claims=[
            {
                "claim_id": "claim_pending_only",
                "check_id": "chkres_pending_only",
                "claim_text": "仍待人工审核",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.80,
                "evidence": "待处理证据",
                "source_doc": "文档一",
                "source_span": "section-1",
                "review_status": "pending",
                "created_at": "2026-05-01T12:00:00+00:00",
                "updated_at": "2026-05-01T12:00:00+00:00",
            }
        ],
        rule_hits=[],
    )
    repository.create_quality_result(
        quality_check={
            "check_id": "chkres_all_reviewed",
            "input_text": "已审核任务",
            "template_id": "t2",
            "template_name": "模板二",
            "overall_verdict": "supported",
            "risk_level": "low",
            "summary": "全部已审核",
            "created_at": "2026-05-01T13:00:00+00:00",
            "updated_at": "2026-05-01T13:00:00+00:00",
        },
        claims=[
            {
                "claim_id": "claim_reviewed_only",
                "check_id": "chkres_all_reviewed",
                "claim_text": "已经审核完成",
                "verdict": "supported",
                "risk_level": "low",
                "confidence": 0.95,
                "evidence": "已审核证据",
                "source_doc": "文档二",
                "source_span": "section-2",
                "review_status": "approved",
                "created_at": "2026-05-01T13:00:00+00:00",
                "updated_at": "2026-05-01T13:00:00+00:00",
            }
        ],
        rule_hits=[],
    )

    demo = create_ui_app(settings)
    list_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "list_recent_quality_results_ui"
    )

    outputs = list_handler(None, "仅看含待处理 Claim", build_admin_login_session())
    recent_state = outputs[16]
    recent_rows = outputs[17]

    assert len(recent_state) == 1
    assert recent_state[0]["check_id"] == "chkres_pending_only"
    assert recent_rows == [["1", "chkres_pending_only", "模板一", "需复核", "1", "1", "26-05-01 20:00", "待处理任务"]]


def test_list_recent_quality_results_ui_should_hide_history_without_kb_permission(tmp_path: Path) -> None:
    """只有菜单权限但没有知识库权限时，不应看到默认知识库历史质检记录。"""

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
            "check_id": "chkres_default_only",
            "input_text": "默认知识库历史记录",
            "template_id": "t1",
            "template_name": "模板一",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "默认库中存在记录",
            "created_at": "2026-05-01T12:00:00+00:00",
            "updated_at": "2026-05-01T12:00:00+00:00",
            "knowledge_base_id": "default",
        },
        claims=[
            {
                "claim_id": "claim_default_only",
                "check_id": "chkres_default_only",
                "claim_text": "默认库 claim",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.80,
                "evidence": "默认库证据",
                "source_doc": "文档一",
                "source_span": "section-1",
                "review_status": "pending",
                "created_at": "2026-05-01T12:00:00+00:00",
                "updated_at": "2026-05-01T12:00:00+00:00",
                "knowledge_base_id": "default",
            }
        ],
        rule_hits=[],
    )

    demo = create_ui_app(settings)
    list_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "list_recent_quality_results_ui"
    )
    restricted_session = {
        "user_id": "user_test",
        "username": "test_user",
        "is_admin": False,
        "permissions": {"tab_names": ["AI 质检"], "kb_ids": []},
    }

    outputs = list_handler(None, "全部历史任务", restricted_session)
    progress_html = outputs[0]
    result_html = outputs[1]
    recent_state = outputs[16]
    recent_rows = outputs[17]

    assert "质检结果" in result_html
    assert "处理中" not in progress_html
    assert recent_state == []
    assert recent_rows == []


def test_list_recent_quality_results_ui_should_hide_history_without_quality_tab(tmp_path: Path) -> None:
    """没有 AI 质检菜单权限时，即使有知识库权限也不应看到历史质检记录。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    initialize_database(settings.sqlite_db_path)
    QualityRepository(settings.sqlite_db_path).create_quality_result(
        quality_check={
            "check_id": "chkres_quality_tab_blocked",
            "input_text": "默认知识库历史记录",
            "template_id": "t1",
            "template_name": "模板一",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "默认库中存在记录",
            "created_at": "2026-05-01T12:00:00+00:00",
            "updated_at": "2026-05-01T12:00:00+00:00",
            "knowledge_base_id": "default",
        },
        claims=[],
        rule_hits=[],
    )

    demo = create_ui_app(settings)
    list_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "list_recent_quality_results_ui"
    )
    restricted_session = {
        "user_id": "user_test",
        "username": "test_user",
        "is_admin": False,
        "permissions": {"tab_names": ["知识库检索"], "kb_ids": ["default"]},
    }

    outputs = list_handler(None, "全部历史任务", restricted_session)

    assert outputs[16] == []
    assert outputs[17] == []


def test_run_search_ui_should_reject_missing_login_session(tmp_path: Path) -> None:
    """知识库检索页执行搜索必须显式带登录态。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
    )
    settings.ensure_runtime_directories()
    initialize_database(settings.sqlite_db_path)
    sample_file = settings.input_root / "default" / "search_session.md"
    sample_file.write_text("# 检索登录态\n\n共享检索关键词。", encoding="utf-8")
    IngestService(settings).register_document({"file_path": str(sample_file)}, knowledge_base_id="default")

    demo = create_ui_app(settings)
    search_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "run_search_ui"
    )

    outputs = search_handler("共享检索关键词", 10, "default | 默认知识库")

    assert "当前账号没有知识库检索权限" in outputs[0]
    assert outputs[2] == []


def test_list_review_workspace_ui_should_hide_review_data_without_kb_permission(tmp_path: Path) -> None:
    """只有人工审核菜单权限、没有知识库权限时，不应看到待审核或审核历史。"""

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
            "check_id": "review_chk_default_only",
            "input_text": "默认库待审核记录",
            "template_id": "t1",
            "template_name": "模板一",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "默认库审核数据",
            "created_at": "2026-05-01T12:00:00+00:00",
            "updated_at": "2026-05-01T12:00:00+00:00",
            "knowledge_base_id": "default",
        },
        claims=[
            {
                "claim_id": "review_claim_default_only",
                "check_id": "review_chk_default_only",
                "claim_text": "默认库待审核 claim",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.78,
                "evidence": "默认库证据",
                "source_doc": "文档一",
                "source_span": "section-1",
                "review_status": "pending",
                "created_at": "2026-05-01T12:00:00+00:00",
                "updated_at": "2026-05-01T12:00:00+00:00",
                "knowledge_base_id": "default",
            }
        ],
        rule_hits=[],
    )
    ReviewService(settings.sqlite_db_path).submit_review(
        claim_id="review_claim_default_only",
        review_action="approved",
        reviewed_verdict=None,
        review_note="默认库审核记录",
        reviewer="reviewer_1",
    )

    demo = create_ui_app(settings)
    list_handler = next(
        block_fn.fn
        for block_fn in demo.fns.values()
        if getattr(block_fn.fn, "__name__", "") == "list_review_workspace_ui"
    )
    restricted_session = {
        "user_id": "user_review",
        "username": "review_user",
        "is_admin": False,
        "permissions": {"tab_names": ["人工审核"], "kb_ids": []},
    }

    outputs = list_handler("全部记录", "全部风险", "", None, restricted_session)

    assert outputs[0] == []
    assert outputs[3] == []
    assert outputs[6] == []
    assert outputs[17] == []
    assert outputs[20] == []



def test_quality_interactions_should_disable_queue_for_table_refresh(tmp_path: Path) -> None:
    """最近记录与 Claim/证据表轻量联动应禁用队列，避免前端刷新中断。"""

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
    dependency_pairs = [
        (getattr(block_fn.fn, "__name__", ""), dependency)
        for dependency in dependencies
        for block_fn in demo.fns.values()
        if block_fn._id == dependency.get("id")
    ]

    assert any(name == "select_recent_quality_result" and dependency.get("queue") is False for name, dependency in dependency_pairs)
    assert any(name == "select_quality_claim" and dependency.get("queue") is False for name, dependency in dependency_pairs)
    assert any(
        name == "select_quality_evidence"
        and dependency.get("queue") is False
        and dependency.get("api_name") == "select_quality_evidence"
        for name, dependency in dependency_pairs
    )


def test_logout_should_clear_auth_inputs_and_messages(tmp_path: Path) -> None:
    """退出登录时应重置登录页可见状态、输入框和提示信息。"""

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
    dependencies = demo.config.get("dependencies", [])
    component_elem_ids = {
        component.get("id"): str(component.get("props", {}).get("elem_id", ""))
        for component in components
    }
    component_types = {
        component.get("id"): str(component.get("type", ""))
        for component in components
    }
    dependency_pairs = [
        (getattr(block_fn.fn, "__name__", ""), dependency)
        for dependency in dependencies
        for block_fn in demo.fns.values()
        if block_fn._id == dependency.get("id")
    ]

    assert any(elem_id == "auth-login-username" for elem_id in component_elem_ids.values())
    assert any(elem_id == "auth-login-password" for elem_id in component_elem_ids.values())

    expected_reset_outputs = {
        "auth-page",
        "main-content",
        "auth-login-form",
        "auth-register-form",
        "auth-login-username",
        "auth-login-password",
        "auth-login-result",
        "auth-register-username",
        "auth-register-password",
        "auth-register-password-confirm",
        "auth-register-result",
    }

    assert any(
        name == "_reset_auth_forms"
        and expected_reset_outputs.issubset({component_elem_ids.get(output_id, "") for output_id in dependency.get("outputs", [])})
        and dependency.get("queue") is False
        for name, dependency in dependency_pairs
    )
    assert any(
        name == "<lambda>"
        and "browserstate" in {component_types.get(output_id, "") for output_id in dependency.get("outputs", [])}
        and "auth-user-display" in {component_elem_ids.get(output_id, "") for output_id in dependency.get("outputs", [])}
        and dependency.get("queue") is False
        for name, dependency in dependency_pairs
    )


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
            ["claim_review_a", "第一条 Claim", "已支持", "低级", "已通过", "文档一", "模板一", "26-05-01 20:00"],
            ["claim_review_b", "第二条 Claim", "需复核", "中级", "待处理", "文档二", "模板二", "26-05-01 21-00"],
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
        review_evidence_page,
        review_evidence_page_info,
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
    assert review_evidence_page == 1
    assert "第 1 / 1 页" in review_evidence_page_info
    assert review_evidence_rows == [["1", "section-2", "文档二", "section-2", "证据不足", "history", "history", "-", "第二条证据摘要"]]
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
        pending_page,
        pending_page_info,
        processed_rows,
        processed_page,
        processed_page_info,
        review_candidate_state,
        selected_claim_id,
        review_claim_detail_map,
        review_claim_detail_html,
        review_evidence_rows,
        review_evidence_page,
        review_evidence_page_info,
        review_evidence_items,
        review_evidence_detail_html,
        review_action_value,
        review_note_value,
        review_history_rows,
        review_history_page,
        review_history_page_info,
        review_history_state,
        selected_review_id,
        review_record_detail_html,
    ) = filter_handler(review_candidates, review_items, "", "全部记录", "仅高风险")

    assert pending_page == 1
    assert processed_page == 1
    assert review_evidence_page == 1
    assert review_history_page == 1
    assert "第 1 / 1 页" in pending_page_info
    assert "第 1 / 1 页" in processed_page_info
    assert "第 1 / 1 页" in review_evidence_page_info
    assert "第 1 / 1 页" in review_history_page_info
    assert pending_rows == [["1", "claim_pending_high", "高风险待处理 Claim", "需复核", "高级", "待处理", "文档一", "模板一", "26-05-01 20:00"]]
    assert processed_rows == [["1", "claim_processed_high", "高风险已处理 Claim", "不通过", "高级", "已通过", "文档三", "模板三", "26-05-01 22:00"]]
    assert review_candidate_state == review_candidates
    assert selected_claim_id == "claim_pending_high"
    assert "claim_pending_high" in review_claim_detail_map
    assert "高风险待处理 Claim" in review_claim_detail_html
    assert review_evidence_rows == [["1", "section-1", "文档一", "section-1", "证据不足", "history", "history", "-", "高风险证据"]]
    assert len(review_evidence_items) == 1
    assert "高风险证据" in review_evidence_detail_html
    assert review_action_value == "通过"
    assert review_note_value == ""
    assert review_history_rows == [["1", "rev_processed_high", "claim_processed_high", "通过", "已通过", "ui_user", "26-05-01 22:10", "已通过", "高风险已处理 Claim"]]
    assert review_history_state == review_items
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
        "default | 默认知识库",
        build_admin_login_session(),
    )
    review_candidate_state = submit_outputs[7]
    review_selected_claim_state = submit_outputs[8]
    review_history_state = submit_outputs[21]

    (
        pending_rows,
        _pending_page,
        _pending_page_info,
        processed_rows,
        _processed_page,
        _processed_page_info,
        _review_candidate_state,
        selected_claim_id,
        review_claim_detail_map,
        review_claim_detail_html,
        _review_evidence_rows,
        _review_evidence_page,
        _review_evidence_page_info,
        _review_evidence_items,
        _review_evidence_detail_html,
        review_action_value,
        review_note_value,
        _review_history_rows,
        _review_history_page,
        _review_history_page_info,
        _review_history_state,
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
        "1",
        "claim_submit_review_demo",
        "这是一条刚提交审核的 Claim",
        "需复核",
        "中级",
        "已通过",
        "文档一",
        "模板一",
        "26-05-01 20:00",
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
        review_evidence_page,
        review_evidence_page_info,
        review_evidence_items,
        review_evidence_detail_html,
        review_action_value,
        review_note_value,
        selected_review_id,
        review_record_detail,
    ) = select_handler(review_items, review_candidates, "全部记录", "全部风险", build_review_history_dataframe := [["1", "rev_review_b", "claim_review_b", "不通过", "已驳回", "ui_user", "26-05-01 21-10", "需要驳回", "第二条 Claim"], ["2", "rev_review_a", "claim_review_a", "通过", "已通过", "ui_user", "26-05-01 20-10", "确认通过", "第一条 Claim"]], event)

    assert selected_claim_id == "claim_review_a"
    assert selected_review_id == "rev_review_a"
    assert "claim_review_a" in review_claim_detail_map
    assert "确认通过" in review_record_detail
    assert "第一条 Claim" in review_claim_detail_html
    assert review_action_value == "通过"
    assert review_note_value == "确认通过"
    assert review_evidence_page == 1
    assert "第 1 / 1 页" in review_evidence_page_info
    assert review_evidence_rows == [["1", "section-1", "文档一", "section-1", "证据不足", "history", "history", "-", "第一条证据摘要"]]
    assert len(review_evidence_items) == 1
    assert "第一条证据摘要" in review_evidence_detail_html


def test_search_ui_css_should_hide_cell_selection_buttons_and_use_normal_font_size() -> None:
    """检索页样式应隐藏整行整列选择按钮，并使用常规字号。"""

    assert "Select column" in UI_CSS
    assert "Select row" in UI_CSS
    assert "display:none" in UI_CSS.replace(" ", "")
    assert "font-size:14px" in UI_CSS.replace(" ", "")
    assert "#search-top-row" in UI_CSS
    assert "#search-results-table" in UI_CSS
    assert "#search-export-row" in UI_CSS
    assert "#search-export-result" in UI_CSS
    assert "#document-quality-search-export-result" in UI_CSS
    assert "#document-quality-config-action-row" in UI_CSS
    assert "#settings-export-row" in UI_CSS
    assert "#settings-export-result" in UI_CSS
    assert "#search-input-panel" in UI_CSS
    assert "min-height:260px" in UI_CSS.replace(" ", "")
    assert "table-layout:fixed" in UI_CSS.replace(" ", "")
    assert "overflow-wrap:anywhere" in UI_CSS.replace(" ", "")
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
    assert "#quality-input-panel" in UI_CSS
    assert "#quality-history-panel" in UI_CSS
    assert "#quality-action-panel" in UI_CSS
    assert "#quality-evidence-list-panel" in UI_CSS
    assert "#quality-evidence-detail" in UI_CSS
    assert "#quality-active-check" in UI_CSS
    assert "#quality-claims-table" in UI_CSS
    assert "#quality-recent-table" in UI_CSS
    assert "#quality-evidence-table" in UI_CSS
    assert "#quality-evidence-page-info" in UI_CSS
    assert "#quality-recent-page-info" in UI_CSS
    assert "#quality-export-row" in UI_CSS
    assert "#quality-export-result" in UI_CSS
    assert "#quality-export-result a" in UI_CSS
    assert "#quality-recent-table table td:nth-child(2)" in UI_CSS
    assert "#quality-recent-table tr:has(td:nth-child(2) button:not(:empty)) td" in UI_CSS
    assert "#quality-claims-table tr:has(td:focus-within) td" in UI_CSS
    assert "#quality-evidence-table tr:has(button:focus) td" in UI_CSS
    assert "#quality-recent-table tr:has(.selected) td" in UI_CSS
    assert "box-shadow: inset 5px 0 0 0" in UI_CSS
    assert "#review-summary-row" in UI_CSS
    assert "#review-filter-row" in UI_CSS
    assert "#review-action-form" in UI_CSS
    assert "#review-action-feedback-row" in UI_CSS
    assert "#review-result-panel" in UI_CSS
    assert "#review-export-result" in UI_CSS
    assert "#review-action-buttons" in UI_CSS
    assert "#review-help-panel > div" in UI_CSS
    assert "#review-pending-panel" in UI_CSS
    assert "#review-processed-panel" in UI_CSS
    assert "#review-evidence-list-panel" in UI_CSS
    assert "#review-history-panel" in UI_CSS
    assert "#document-summary-panel" in UI_CSS
    assert "#database-summary-panel" in UI_CSS
    assert "#document-current-panel" in UI_CSS
    assert "#database-summary-table-panel" in UI_CSS
    assert "#document-list-panel" in UI_CSS
    assert "#document-management-actions-row" in UI_CSS
    assert "#document-management-result-row" in UI_CSS
    assert "#document-pagination-row" in UI_CSS
    assert "#document-page-info" in UI_CSS
    assert "#document-register-result" in UI_CSS
    assert "#document-rebuild-result" in UI_CSS
    assert "#document-quality-summary-row" in UI_CSS
    assert "#document-quality-sample-row" in UI_CSS
    assert "#document-quality-search-row" in UI_CSS
    assert "#document-quality-search-action-row" in UI_CSS
    assert "#document-quality-result-panel" in UI_CSS
    assert "#document-quality-config-panel" in UI_CSS
    assert "#document-quality-batch-panel" in UI_CSS
    assert "#document-quality-batch-summary" in UI_CSS
    assert "#document-quality-search-page-info" in UI_CSS
    assert "#document-quality-batch-page-info" in UI_CSS
    assert "#document-quality-config-form" in UI_CSS
    assert "#document-quality-config-form-row-1" in UI_CSS
    assert "#document-quality-config-form-row-4" in UI_CSS
    assert "#search-page-info" in UI_CSS
    assert "#search-results-table" in UI_CSS
    assert "#settings-template-page-info" in UI_CSS
    assert "#settings-knowledge-base-page-info" in UI_CSS
    assert "#settings-template-list-panel" in UI_CSS
    assert "#settings-template-table" in UI_CSS
    assert "#settings-knowledge-base-list-panel" in UI_CSS
    assert "#settings-knowledge-base-table" in UI_CSS
    assert "#settings-main-row > .gradio-column" in UI_CSS
    assert "#settings-knowledge-base-row > .gradio-column" in UI_CSS
    assert "#review-pending-table" in UI_CSS
    assert "#review-processed-table" in UI_CSS
    assert "#review-history-table" in UI_CSS
    assert "#review-evidence-table" in UI_CSS
    assert "#review-pending-table table th" in UI_CSS
    assert "#review-processed-table table th" in UI_CSS
    assert "#review-history-table table th" in UI_CSS
    assert "#review-evidence-table table th" in UI_CSS
    assert "#review-evidence-detail pre" not in UI_CSS
    assert "#settings-knowledge-base-row" in UI_CSS
    assert "#settings-list-actions" in UI_CSS
    assert "#settings-form-actions" in UI_CSS
    assert "#settings-knowledge-base-list-actions" in UI_CSS
    assert "#settings-knowledge-base-actions" in UI_CSS
    assert "button.ui-button" in UI_CSS
    assert "button.ui-button--primary" in UI_CSS
    assert "button.ui-button--danger" in UI_CSS
    assert "button.ui-button--warning" in UI_CSS
    assert "button.ui-button--pagination" in UI_CSS
    assert "rgba(127, 29, 29, 0.88)" not in UI_CSS
    assert "rgba(251, 191, 36, 0.95)" not in UI_CSS
    assert "border-radius:14px" in UI_CSS.replace(" ", "")
    assert "transform:translateY(-1px)" in UI_CSS.replace(" ", "")
    assert "transform:scale(0.98)" in UI_CSS.replace(" ", "")
    assert "#settings-template-detail" in UI_CSS
    assert "#settings-knowledge-base-detail" in UI_CSS
    assert "rgba(68, 68, 68, 0.22)" in UI_CSS
    assert "inset 6px 0 0 0" in UI_CSS
    assert "#review-claim-detail" in UI_CSS
    assert "font-weight:700" in UI_CSS.replace(" ", "")
    assert "overflow-wrap:anywhere" in UI_CSS.replace(" ", "")


def test_restore_login_session_should_handle_invalid_stored_session(tmp_path: Path) -> None:
    """测试_restore_login_session应能处理非字典类型异常输入。"""
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

    restore_fn = next((block_fn.fn for block_fn in demo.fns.values() if getattr(block_fn.fn, "__name__", "") == "_restore_login_session"), None)
    assert restore_fn is not None

    outputs = restore_fn("invalid_string")
    result_session, result_label, result_login, result_menu = outputs[:4]
    document_knowledge_base_update = outputs[13]
    quality_knowledge_base_update = outputs[15]
    search_knowledge_base_update = outputs[17]
    assert result_session.get("user_id") is None
    assert result_label == ""
    assert result_login.get("visible") is True
    assert result_menu.get("visible") is False
    assert document_knowledge_base_update["value"].startswith("default | ")
    assert quality_knowledge_base_update["value"].startswith("default | ")
    assert search_knowledge_base_update["value"].startswith("default | ")


def test_restore_login_session_should_handle_empty_user_id(tmp_path: Path) -> None:
    """测试_restore_login_session应能处理空user_id情况。"""
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

    restore_fn = next((block_fn.fn for block_fn in demo.fns.values() if getattr(block_fn.fn, "__name__", "") == "_restore_login_session"), None)
    assert restore_fn is not None

    stored = {"user_id": None, "username": None}
    outputs = restore_fn(stored)
    result_session, result_label, result_login, result_menu = outputs[:4]
    document_knowledge_base_update = outputs[13]
    quality_knowledge_base_update = outputs[15]
    search_knowledge_base_update = outputs[17]
    assert result_session.get("user_id") is None
    assert result_label == ""
    assert result_login.get("visible") is True
    assert result_menu.get("visible") is False
    assert document_knowledge_base_update["value"].startswith("default | ")
    assert quality_knowledge_base_update["value"].startswith("default | ")
    assert search_knowledge_base_update["value"].startswith("default | ")


def test_restore_login_session_should_handle_deleted_user(tmp_path: Path) -> None:
    """测试_restore_login_session应能处理用户已被删除的情况（数据库不存在该用户时应返回空session并显示登录页）。"""
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

    restore_fn = next((block_fn.fn for block_fn in demo.fns.values() if getattr(block_fn.fn, "__name__", "") == "_restore_login_session"), None)
    assert restore_fn is not None

    stored = {"user_id": "deleted_user_001", "username": "deleted_user"}
    result_session, result_label, result_login, result_menu, *_extra_outputs = restore_fn(stored)
    assert result_session.get("user_id") is None
    assert result_label == ""
    assert result_login.get("visible") is True
    assert result_menu.get("visible") is False
