"""程序说明：验证 PageIndex 深度检索 Gradio 页的组件构建与事件绑定。"""

from __future__ import annotations

import gradio as gr
import pandas as pd

from src.db.connection import create_connection, initialize_database
from src.pageindex.service import PageIndexService
from src.ui.app import create_ui_app
from src.ui.pageindex_page import build_pageindex_tab
from src.ui.settings_page import build_settings_tab
from tests.unit.test_pageindex_service import (
    build_pageindex_test_settings,
    seed_markdown_document,
    seed_pageindex_workspace,
)


def build_settings_tab_initial_values() -> dict[str, object]:
    """构造设置页组件测试所需的最小初始值。"""

    return {
        "runtime_html": "<div>运行配置</div>",
        "template_table_rows": [],
        "template_page_info": "第 1 / 1 页，共 0 条，每页最多 10 行",
        "template_detail_html": "<div>模板详情</div>",
        "template_id": "",
        "template_name": "",
        "template_description": "",
        "rule_tags": "",
        "fulltext_top_k": 3,
        "vector_top_k": 3,
        "final_top_k": 3,
        "neighbor_window": 0,
        "section_max_chars": 400,
        "use_rerank": False,
        "include_section_context": False,
        "system_prompt": "",
        "user_prompt_template": "",
        "delete_confirm": False,
        "knowledge_base_choices": [],
        "knowledge_base_selected_choice": None,
        "knowledge_base_page_info": "第 1 / 1 页，共 0 条，每页最多 10 行",
        "knowledge_base_detail_html": "<div>知识库详情</div>",
        "knowledge_base_id": "",
        "knowledge_base_name": "",
        "knowledge_base_description": "",
        "knowledge_base_status": "active",
        "knowledge_base_is_default": False,
        "knowledge_base_result_html": "",
        "result_html": "",
        "user_choices": [],
        "user_selected_choice": None,
        "user_detail_html": "",
        "user_result_html": "",
        "permission_user_choices": [],
        "permission_user_selected_choice": None,
        "permission_detail_html": "",
        "permission_tab_choices": [],
        "permission_tab_values": [],
        "permission_kb_choices": [],
        "permission_kb_values": [],
        "permission_result_html": "",
    }


def test_build_pageindex_tab_should_return_expected_components() -> None:
    """PageIndex 页应沿用 Gradio builder 模式，并返回后续绑定所需组件。"""

    with gr.Blocks():
        components = build_pageindex_tab(
            knowledge_base_choices=["kb_alpha | Alpha 知识库"],
            initial_knowledge_base_choice="kb_alpha | Alpha 知识库",
            document_choices=["doc_1 | Alpha 文档"],
            initial_document_choice="doc_1 | Alpha 文档",
            template_choices=["strict_qa | 严谨问答"],
            initial_template_choice="strict_qa | 严谨问答",
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
        "pageindex_template",
        "pageindex_build_button",
        "pageindex_rebuild_button",
        "pageindex_question",
        "pageindex_ask_button",
        "pageindex_tree_panel",
        "pageindex_tree",
        "pageindex_answer",
        "pageindex_evidence_table",
        "pageindex_debug_table",
        "pageindex_history_table",
        "pageindex_history_state",
        "pageindex_active_query_id",
        "pageindex_export_button",
        "pageindex_export_result",
        "pageindex_download_file",
    }
    assert expected_keys.issubset(components.keys())
    assert isinstance(components["pageindex_knowledge_base"], gr.Dropdown)
    assert components["pageindex_knowledge_base"].elem_id == "pageindex-knowledge-base"
    assert isinstance(components["pageindex_template"], gr.Dropdown)
    assert components["pageindex_template"].elem_id == "pageindex-template"
    assert isinstance(components["pageindex_tree_panel"], gr.Accordion)
    assert components["pageindex_tree_panel"].open is False
    assert isinstance(components["pageindex_tree"], gr.Dataframe)
    assert components["pageindex_tree"].elem_id == "pageindex-tree"
    assert components["pageindex_history_table"].label == "当前知识库历史记录"
    assert components["pageindex_history_table"].headers == ["时间", "文档", "问题", "回答摘要", "问题类型"]
    assert "ui-button--primary" in (components["pageindex_export_button"].elem_classes or [])


def test_build_settings_tab_should_include_pageindex_template_kind_selector() -> None:
    """设置页模板管理应支持选择 AI 质检或 PageIndex 模板。"""

    with gr.Blocks():
        components = build_settings_tab(initial_values=build_settings_tab_initial_values())

    assert "settings_template_kind" in components
    assert isinstance(components["settings_template_kind"], gr.Radio)
    assert components["settings_template_kind"].elem_id == "settings-template-kind"
    assert "PageIndex" in {value for _label, value in components["settings_template_kind"].choices}


def test_save_settings_template_should_support_pageindex_templates(tmp_path) -> None:
    """设置页保存 PageIndex 模板后，应持久化并刷新 PageIndex 问答模板下拉。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    demo = create_ui_app(settings)
    save_handler = next(
        (block_fn.fn for block_fn in demo.fns.values() if getattr(block_fn.fn, "__name__", "") == "save_settings_template_ui"),
        None,
    )
    assert save_handler is not None

    outputs = save_handler(
        "PageIndex",
        "",
        "cardiac_safety",
        "心脏病安全回答",
        "面向医学安全问答的模板。",
        "",
        3,
        3,
        3,
        False,
        0,
        False,
        400,
        "你是严谨的医学知识库问答助手。",
        "问题：{{ question }}\n证据：{{ evidence_json }}",
    )

    saved_template = PageIndexService(settings).template_service.get_template("cardiac_safety")
    pageindex_template_update = outputs[-1]
    assert saved_template["template_name"] == "心脏病安全回答"
    assert "cardiac_safety | 心脏病安全回答" in pageindex_template_update["choices"]
    assert pageindex_template_update["value"] == "cardiac_safety | 心脏病安全回答"


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

    answer_html, evidence_rows, debug_rows, history_rows, history_state, active_query_id, export_result_html, download_file = ask_handler(
        "kb_alpha | kb_alpha 知识库",
        f'{document["doc_uid"]} | alpha',
        "strict_qa | 严谨问答",
        "风险",
    )

    assert "风险" in answer_html
    assert "本次检索模式" in answer_html
    assert "知识库多文档检索" in answer_html
    assert "LLM 状态" not in answer_html
    assert "索引状态" not in answer_html
    assert evidence_rows[0][1] == "风险"
    assert evidence_rows[0][4] in {
        "直接支持",
        "直接反驳",
        "部分支持",
        "仅背景相关",
        "仅案例",
        "方法/组合语境",
        "条件或限制",
        "证据不足",
    }
    assert debug_rows[0][1] == "风险"
    assert "本地候选召回" in debug_rows[0][5]
    assert history_rows[0][2] == "风险"
    assert history_rows[0][4] == "unknown"
    assert history_state[0]["question"] == "风险"
    assert active_query_id == history_state[0]["query_id"]
    assert "已激活当前结果，可下载。" in export_result_html
    assert download_file is None


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

    status_html, _tree_rows, _answer_html, _evidence_rows, _debug_rows, _history_rows, _history_state, _active_query_id, _export_result_html, _download_file = change_handler(
        "default | 默认知识库",
        "",
    )

    assert "LLM 状态" in status_html
    assert "LLM 不可用" in status_html
    assert "本地关键词降级" in status_html
    assert "未选择文档" in status_html
    assert "状态说明" not in status_html
    assert "失败" not in status_html


def test_pageindex_answer_placeholder_should_not_duplicate_status_card(tmp_path) -> None:
    """PageIndex 回答区占位不应重复显示顶部状态卡中的索引与 LLM 状态。"""

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

    status_html, _tree_rows, answer_html, _evidence_rows, _debug_rows, _history_rows, _history_state, _active_query_id, _export_result_html, _download_file = change_handler(
        "default | 默认知识库",
        "",
    )

    assert "LLM 状态" in status_html
    assert "索引状态" in status_html
    assert "LLM 状态" not in answer_html
    assert "索引状态" not in answer_html
    assert "尚未提问" in answer_html


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

    pageindex_service = PageIndexService(settings)
    pageindex_service.ask_question("kb_alpha", document["doc_uid"], "风险")

    status_html, tree_rows, _answer_html, _evidence_rows, debug_rows, history_rows, history_state, active_query_id, _export_result_html, _download_file = change_handler(
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
    assert history_rows[0][2] == "风险"
    assert history_state[0]["question"] == "风险"
    assert active_query_id == history_state[0]["query_id"]


def test_pageindex_document_change_should_show_knowledge_base_history(tmp_path) -> None:
    """PageIndex 历史应展示当前知识库历史，而不是只展示当前选中文档。"""

    settings = build_pageindex_test_settings(tmp_path, llm_provider="openai")
    settings.llm_api_key = "test-key"
    settings.llm_model = "gpt-test"
    initialize_database(settings.sqlite_db_path)
    first_document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    second_document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="beta.md")
    first_pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=first_document["doc_uid"],
        file_name="alpha.md",
    )
    second_pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=second_document["doc_uid"],
        file_name="beta.md",
    )
    pageindex_service = PageIndexService(settings)
    pageindex_service.upsert_index_record("kb_alpha", first_document["doc_uid"], first_pageindex_doc_id, source_hash="hash_alpha")
    pageindex_service.upsert_index_record("kb_alpha", second_document["doc_uid"], second_pageindex_doc_id, source_hash="hash_beta")
    pageindex_service.ask_question("kb_alpha", second_document["doc_uid"], "风险")

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

    _status_html, _tree_rows, _answer_html, _evidence_rows, _debug_rows, history_rows, history_state, active_query_id, _export_result_html, _download_file = change_handler(
        "kb_alpha | kb_alpha 知识库",
        f'{first_document["doc_uid"]} | alpha',
    )

    assert history_rows[0][1] == second_document["doc_uid"]
    assert history_rows[0][2] == "风险"
    assert history_state[0]["doc_uid"] == second_document["doc_uid"]
    assert active_query_id == history_state[0]["query_id"]


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

    status_html, tree_rows, _answer_html, _evidence_rows, debug_rows, history_rows, history_state, active_query_id, _export_result_html, _download_file = change_handler(
        "kb_alpha | kb_alpha 知识库",
        f'{document["doc_uid"]} | alpha',
    )

    assert "索引异常" in status_html
    assert "未构建" not in status_html
    assert tree_rows == []
    assert debug_rows == []
    assert history_rows == []
    assert history_state == []
    assert active_query_id == ""


def test_pageindex_history_select_should_activate_record_for_download(tmp_path) -> None:
    """点击 PageIndex 历史记录后，应回显该记录并设置为当前下载对象。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service = PageIndexService(settings)
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    first = service.ask_question("kb_alpha", document["doc_uid"], "风险")
    second = service.ask_question("kb_alpha", document["doc_uid"], "知识库")

    demo = create_ui_app(settings)
    select_handler = next(
        (
            block_fn.fn
            for block_fn in demo.fns.values()
            if getattr(block_fn.fn, "__name__", "") == "select_pageindex_history_ui"
        ),
        None,
    )
    assert select_handler is not None

    class FakeSelectData:
        """测试用选择事件，模拟点击历史表第二行。"""

        index = (1, 0)

    history_state = [second, first]
    history_rows = [
        [second["created_at"], second["doc_uid"], second["question"], second["answer"][:300], "unknown"],
        [first["created_at"], first["doc_uid"], first["question"], first["answer"][:300], "unknown"],
    ]

    answer_html, evidence_rows, debug_rows, active_query_id, export_result_html, download_file = select_handler(
        "kb_alpha | kb_alpha 知识库",
        f'{document["doc_uid"]} | alpha',
        history_state,
        pd.DataFrame(history_rows, columns=["时间", "文档", "问题", "回答摘要", "问题类型"]),
        FakeSelectData(),
    )

    assert first["answer"] in answer_html
    assert evidence_rows[0][1] == "风险"
    assert debug_rows == []
    assert active_query_id == first["query_id"]
    assert "已激活历史记录，可下载。" in export_result_html
    assert download_file is None


def test_pageindex_export_should_download_active_history_record_only(tmp_path) -> None:
    """PageIndex 下载结果应只导出当前激活的历史记录。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service = PageIndexService(settings)
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    active = service.ask_question("kb_alpha", document["doc_uid"], "风险")
    service.ask_question("kb_alpha", document["doc_uid"], "不要导出这个问题")

    demo = create_ui_app(settings)
    export_handler = next(
        (
            block_fn.fn
            for block_fn in demo.fns.values()
            if getattr(block_fn.fn, "__name__", "") == "export_pageindex_results_ui"
        ),
        None,
    )
    assert export_handler is not None

    result_html, download_file = export_handler(
        "kb_alpha | kb_alpha 知识库",
        f'{document["doc_uid"]} | alpha',
        active["query_id"],
    )

    assert "已生成 PageIndex 下载文件" in result_html
    assert download_file
    assert download_file.endswith(".md")
    assert "查看渲染效果" in result_html
    assert ".preview.html" in result_html
    assert "下载地址" not in result_html
    with open(download_file, encoding="utf-8") as file:
        exported_text = file.read()
    assert "# PageIndex 深度检索导出" in exported_text
    assert "问题：风险" in exported_text
    assert "不要导出这个问题" not in exported_text
