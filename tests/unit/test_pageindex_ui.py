"""程序说明：验证 PageIndex 深度检索 Gradio 页的组件构建与事件绑定。"""

from __future__ import annotations

import gradio as gr

from src.db.connection import create_connection, initialize_database
from src.pageindex.service import PageIndexService
from src.ui.app import create_ui_app
from src.ui.pageindex_page import build_pageindex_tab
from tests.unit.test_pageindex_service import (
    build_pageindex_test_settings,
    seed_markdown_document,
    seed_pageindex_workspace,
)


def test_build_pageindex_tab_should_return_expected_components() -> None:
    """PageIndex 页应沿用 Gradio builder 模式，并返回后续绑定所需组件。"""

    with gr.Blocks():
        components = build_pageindex_tab(
            knowledge_base_choices=["kb_alpha | Alpha 知识库"],
            initial_knowledge_base_choice="kb_alpha | Alpha 知识库",
            document_choices=["doc_1 | Alpha 文档"],
            initial_document_choice="doc_1 | Alpha 文档",
            initial_status_html="<div>未构建</div>",
            initial_tree_rows=[],
            initial_answer_html="<div>尚未提问</div>",
            initial_evidence_rows=[],
            initial_debug_rows=[],
            initial_history_rows=[],
        )

    expected_keys = {
        "pageindex_knowledge_base",
        "pageindex_document",
        "pageindex_build_button",
        "pageindex_rebuild_button",
        "pageindex_question",
        "pageindex_ask_button",
        "pageindex_tree",
        "pageindex_answer",
        "pageindex_evidence_table",
        "pageindex_debug_table",
        "pageindex_history_table",
        "pageindex_export_button",
    }
    assert expected_keys.issubset(components.keys())
    assert isinstance(components["pageindex_knowledge_base"], gr.Dropdown)
    assert components["pageindex_knowledge_base"].elem_id == "pageindex-knowledge-base"
    assert isinstance(components["pageindex_tree"], gr.Dataframe)
    assert components["pageindex_tree"].elem_id == "pageindex-tree"


def test_pageindex_question_handler_should_return_answer_evidence_and_history(tmp_path) -> None:
    """PageIndex 提问事件应调用本地服务，而不是返回占位提示。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    PageIndexService(settings).upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    demo = create_ui_app(settings)
    ask_handler = next((block_fn.fn for block_fn in demo.fns.values() if getattr(block_fn.fn, "__name__", "") == "ask_pageindex_question_ui"), None)
    assert ask_handler is not None

    answer_html, evidence_rows, debug_rows, history_rows = ask_handler(
        "kb_alpha | kb_alpha 知识库",
        f'{document["doc_uid"]} | alpha',
        "风险",
    )

    assert "风险" in answer_html
    assert "本次检索模式" in answer_html
    assert "本地关键词降级" in answer_html
    assert evidence_rows[0][1] == "风险"
    assert debug_rows[0][1] == "风险"
    assert "本地候选召回" in debug_rows[0][5]
    assert history_rows[0][2] == "风险"


def test_pageindex_status_should_show_llm_availability(tmp_path) -> None:
    """PageIndex 页面状态卡应显示当前 LLM 是否支持语义检索。"""

    settings = build_pageindex_test_settings(tmp_path, llm_provider="disabled")
    initialize_database(settings.sqlite_db_path)

    demo = create_ui_app(settings)
    change_handler = next(
        (
            block_fn.fn
            for block_fn in demo.fns.values()
            if getattr(block_fn.fn, "__name__", "") == "change_pageindex_document_ui"
        ),
        None,
    )
    assert change_handler is not None

    status_html, _tree_rows, _answer_html, _evidence_rows, _debug_rows = change_handler(
        "default | 默认知识库",
        "",
    )

    assert "LLM 状态" in status_html
    assert "LLM 不可用" in status_html
    assert "本地关键词降级" in status_html
    assert "未选择文档" in status_html
    assert "状态说明" not in status_html
    assert "失败" not in status_html


def test_pageindex_document_change_should_show_ready_when_index_already_exists(tmp_path) -> None:
    """重新进入已构建文档时，应显示已构建状态并加载结构树。"""

    settings = build_pageindex_test_settings(tmp_path, llm_provider="openai")
    settings.llm_api_key = "test-key"
    settings.llm_model = "gpt-test"
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    PageIndexService(settings).upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    demo = create_ui_app(settings)
    change_handler = next(
        (
            block_fn.fn
            for block_fn in demo.fns.values()
            if getattr(block_fn.fn, "__name__", "") == "change_pageindex_document_ui"
        ),
        None,
    )
    assert change_handler is not None

    status_html, tree_rows, _answer_html, _evidence_rows, debug_rows = change_handler(
        "kb_alpha | kb_alpha 知识库",
        f'{document["doc_uid"]} | alpha',
    )

    assert "索引状态" in status_html
    assert "已构建" in status_html
    assert "LLM 可用" in status_html
    assert "PageIndex 已构建，可直接提问" in status_html
    assert "状态说明" not in status_html
    assert "执行状态" not in status_html
    assert "失败" not in status_html
    assert tree_rows[0][1] == "总论"
    assert debug_rows == []


def test_pageindex_initial_state_should_show_ready_when_default_document_index_exists(tmp_path) -> None:
    """重新打开系统时，PageIndex 初始状态应按默认选中文档显示已构建。"""

    settings = build_pageindex_test_settings(tmp_path, llm_provider="openai")
    settings.llm_api_key = "test-key"
    settings.llm_model = "gpt-test"
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="default", file_name="alpha.md")
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="default",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    PageIndexService(settings).upsert_index_record("default", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    demo = create_ui_app(settings)
    components = {getattr(component, "elem_id", None): component for component in demo.blocks.values()}

    status_html = components["pageindex-status"].value
    tree_value = components["pageindex-tree"].value

    assert "PageIndex 已构建，可直接提问" in status_html
    assert "已构建" in status_html
    assert "执行状态" not in status_html
    assert tree_value["data"][0][1] == "总论"


def test_pageindex_document_change_should_not_report_unbuilt_when_index_record_is_broken(tmp_path) -> None:
    """索引记录存在但 PageIndex 文件损坏时，应显示索引异常而不是未构建。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    service.upsert_index_record("kb_alpha", document["doc_uid"], "missing_doc", source_hash="hash_alpha")
    with create_connection(settings.sqlite_db_path) as connection:
        connection.execute(
            "UPDATE pageindex_indexes SET workspace_path = ? WHERE knowledge_base_id = ? AND doc_uid = ?",
            (str(tmp_path / "missing_workspace"), "kb_alpha", document["doc_uid"]),
        )
        connection.commit()

    demo = create_ui_app(settings)
    change_handler = next(
        (
            block_fn.fn
            for block_fn in demo.fns.values()
            if getattr(block_fn.fn, "__name__", "") == "change_pageindex_document_ui"
        ),
        None,
    )
    assert change_handler is not None

    status_html, tree_rows, _answer_html, _evidence_rows, debug_rows = change_handler(
        "kb_alpha | kb_alpha 知识库",
        f'{document["doc_uid"]} | alpha',
    )

    assert "索引异常" in status_html
    assert "未构建" not in status_html
    assert tree_rows == []
    assert debug_rows == []
