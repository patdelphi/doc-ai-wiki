"""程序说明：承载“PageIndex 深度检索”页的组件构建与事件绑定。"""

from __future__ import annotations

from collections.abc import Callable

import gradio as gr

from src.ui.page_helpers import ui_button


def build_pageindex_tab(
    *,
    knowledge_base_choices: list[str],
    initial_knowledge_base_choice: str | None,
    document_choices: list[str],
    initial_document_choice: str | None,
    initial_status_html: str,
    initial_tree_rows: list[list[object]],
    initial_answer_html: str,
    initial_evidence_rows: list[list[object]],
    initial_debug_rows: list[list[object]],
    initial_history_rows: list[list[object]],
    initial_history_state: list[dict] | None = None,
    initial_active_query_id: str = "",
    initial_export_result_html: str = "",
) -> dict[str, gr.components.Component]:
    """构建 PageIndex 深度检索页组件，并返回后续事件绑定所需组件。"""

    pageindex_active_query_id = gr.State(initial_active_query_id)
    pageindex_history_state = gr.State(initial_history_state or [])

    with gr.Row(elem_id="pageindex-top-row"):
        with gr.Column(scale=1):
            with gr.Group(elem_id="pageindex-control-panel"):
                pageindex_knowledge_base = gr.Dropdown(
                    label="当前知识库",
                    choices=knowledge_base_choices,
                    value=initial_knowledge_base_choice,
                    interactive=True,
                    elem_id="pageindex-knowledge-base",
                )
                pageindex_document = gr.Dropdown(
                    label="当前文档",
                    choices=document_choices,
                    value=initial_document_choice,
                    interactive=True,
                    elem_id="pageindex-document",
                )
                with gr.Row(elem_id="pageindex-build-row"):
                    pageindex_build_button = ui_button("构建索引", variant="primary")
                    pageindex_rebuild_button = ui_button("重建索引")
        with gr.Column(scale=1):
            pageindex_status = gr.HTML(
                value=initial_status_html,
                elem_id="pageindex-status",
            )

    with gr.Accordion("文档结构", open=False, elem_id="pageindex-tree-panel") as pageindex_tree_panel:
        pageindex_tree = gr.Dataframe(
            headers=["层级", "标题", "位置", "摘要"],
            datatype=["number", "markdown", "str", "markdown"],
            interactive=False,
            row_count=0,
            column_count=4,
            label="文档结构",
            buttons=[],
            elem_id="pageindex-tree",
            value=initial_tree_rows,
        )

    with gr.Group(elem_id="pageindex-query-panel"):
        pageindex_question = gr.Textbox(
            label="问题",
            lines=3,
            placeholder="围绕当前文档提问，PageIndex 会基于文档结构定位相关内容",
            elem_id="pageindex-question",
        )
        pageindex_ask_button = ui_button("提问", variant="primary")
        pageindex_answer = gr.HTML(
            value=initial_answer_html,
            elem_id="pageindex-answer",
        )
        pageindex_evidence_table = gr.Dataframe(
            headers=["序号", "标题", "位置", "证据摘要", "证据类型", "来源"],
            datatype=["number", "markdown", "str", "markdown", "str", "str"],
            interactive=False,
            row_count=0,
            column_count=6,
            label="定位证据",
            buttons=[],
            elem_id="pageindex-evidence-table",
            value=initial_evidence_rows,
        )
        pageindex_debug_table = gr.Dataframe(
            headers=["序号", "候选节点", "位置", "分数", "检索模式", "选择理由"],
            datatype=["number", "markdown", "str", "number", "str", "markdown"],
            interactive=False,
            row_count=0,
            column_count=6,
            label="检索诊断",
            buttons=[],
            elem_id="pageindex-debug-table",
            value=initial_debug_rows,
        )

    with gr.Group(elem_id="pageindex-history-panel"):
        pageindex_history_table = gr.Dataframe(
            headers=["时间", "文档", "问题", "回答摘要"],
            datatype=["str", "markdown", "markdown", "markdown"],
            interactive=True,
            row_count=0,
            column_count=4,
            label="当前文档历史",
            buttons=[],
            elem_id="pageindex-history-table",
            value=initial_history_rows,
        )
        pageindex_export_button = ui_button("下载结果", tone="primary")
        pageindex_export_result = gr.HTML(
            value=initial_export_result_html,
            elem_id="pageindex-export-result",
        )
        pageindex_download_file = gr.File(
            label="下载文件",
            interactive=False,
            elem_id="pageindex-download-file",
        )

    return {
        "pageindex_knowledge_base": pageindex_knowledge_base,
        "pageindex_document": pageindex_document,
        "pageindex_status": pageindex_status,
        "pageindex_build_button": pageindex_build_button,
        "pageindex_rebuild_button": pageindex_rebuild_button,
        "pageindex_tree_panel": pageindex_tree_panel,
        "pageindex_tree": pageindex_tree,
        "pageindex_question": pageindex_question,
        "pageindex_ask_button": pageindex_ask_button,
        "pageindex_answer": pageindex_answer,
        "pageindex_evidence_table": pageindex_evidence_table,
        "pageindex_debug_table": pageindex_debug_table,
        "pageindex_history_table": pageindex_history_table,
        "pageindex_history_state": pageindex_history_state,
        "pageindex_active_query_id": pageindex_active_query_id,
        "pageindex_export_button": pageindex_export_button,
        "pageindex_export_result": pageindex_export_result,
        "pageindex_download_file": pageindex_download_file,
    }


def bind_pageindex_events(
    *,
    components: dict[str, gr.components.Component],
    change_knowledge_base: Callable | None = None,
    change_document: Callable | None = None,
    build_index: Callable | None = None,
    ask_question: Callable | None = None,
    select_history: Callable | None = None,
    export_results: Callable | None = None,
) -> None:
    """绑定 PageIndex 页事件；未传处理函数时保持组件可独立测试。"""

    if change_knowledge_base:
        components["pageindex_knowledge_base"].input(
            fn=change_knowledge_base,
            inputs=[components["pageindex_knowledge_base"]],
            outputs=[
                components["pageindex_document"],
                components["pageindex_status"],
                components["pageindex_tree"],
                components["pageindex_answer"],
                components["pageindex_evidence_table"],
                components["pageindex_debug_table"],
                components["pageindex_history_table"],
                components["pageindex_history_state"],
                components["pageindex_active_query_id"],
                components["pageindex_export_result"],
                components["pageindex_download_file"],
            ],
            queue=False,
        )
    if change_document:
        components["pageindex_document"].input(
            fn=change_document,
            inputs=[components["pageindex_knowledge_base"], components["pageindex_document"]],
            outputs=[
                components["pageindex_status"],
                components["pageindex_tree"],
                components["pageindex_answer"],
                components["pageindex_evidence_table"],
                components["pageindex_debug_table"],
                components["pageindex_history_table"],
                components["pageindex_history_state"],
                components["pageindex_active_query_id"],
                components["pageindex_export_result"],
                components["pageindex_download_file"],
            ],
            queue=False,
        )
    if build_index:
        components["pageindex_build_button"].click(
            fn=lambda knowledge_base, document: build_index(knowledge_base, document, False),
            inputs=[components["pageindex_knowledge_base"], components["pageindex_document"]],
            outputs=[components["pageindex_status"], components["pageindex_tree"]],
        )
        components["pageindex_rebuild_button"].click(
            fn=lambda knowledge_base, document: build_index(knowledge_base, document, True),
            inputs=[components["pageindex_knowledge_base"], components["pageindex_document"]],
            outputs=[components["pageindex_status"], components["pageindex_tree"]],
        )
    if ask_question:
        components["pageindex_ask_button"].click(
            fn=ask_question,
            inputs=[
                components["pageindex_knowledge_base"],
                components["pageindex_document"],
                components["pageindex_question"],
            ],
            outputs=[
                components["pageindex_answer"],
                components["pageindex_evidence_table"],
                components["pageindex_debug_table"],
                components["pageindex_history_table"],
                components["pageindex_history_state"],
                components["pageindex_active_query_id"],
                components["pageindex_export_result"],
                components["pageindex_download_file"],
            ],
        )
    if select_history:
        components["pageindex_history_table"].select(
            fn=select_history,
            inputs=[
                components["pageindex_knowledge_base"],
                components["pageindex_document"],
                components["pageindex_history_state"],
                components["pageindex_history_table"],
            ],
            outputs=[
                components["pageindex_answer"],
                components["pageindex_evidence_table"],
                components["pageindex_debug_table"],
                components["pageindex_active_query_id"],
                components["pageindex_export_result"],
                components["pageindex_download_file"],
            ],
        )
    if export_results:
        components["pageindex_export_button"].click(
            fn=export_results,
            inputs=[
                components["pageindex_knowledge_base"],
                components["pageindex_document"],
                components["pageindex_active_query_id"],
            ],
            outputs=[components["pageindex_export_result"], components["pageindex_download_file"]],
        )
