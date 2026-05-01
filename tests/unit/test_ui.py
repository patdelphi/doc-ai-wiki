"""程序说明：验证最小 UI 可构建。"""

from pathlib import Path

import gradio as gr

from src.common.config import AppSettings
from src.db.connection import initialize_database
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
