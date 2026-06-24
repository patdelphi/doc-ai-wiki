"""程序说明：承载“知识库检索”页的组件构建与事件绑定，供主页面总装配复用。"""

from __future__ import annotations

from collections.abc import Callable

import gradio as gr

from src.ui.page_helpers import format_table_pagination_html, ui_button
from src.ui.viewmodels import (
    format_operation_result_html,
    format_search_help_html,
    format_search_result_detail_html,
    format_search_summary_html,
)


def build_search_tab(
    *,
    knowledge_base_choices: list[str],
    initial_knowledge_base_choice: str | None,
    initial_search_table_rows: list[list[object]],
    initial_search_page: int,
    initial_search_page_info: str,
) -> dict[str, gr.components.Component]:
    """构建知识库检索页组件，并返回后续事件绑定所需的组件集合。"""

    with gr.Row(elem_id="search-top-row"):
        with gr.Column(scale=1):
            with gr.Group(elem_id="search-input-panel"):
                search_query = gr.Textbox(
                    label="检索内容",
                    lines=3,
                    placeholder="可输入关键词、短语、整句，或多组关键词（建议用空格、逗号分隔）",
                )
                search_knowledge_base = gr.Dropdown(
                    label="当前知识库",
                    choices=knowledge_base_choices,
                    value=initial_knowledge_base_choice,
                    interactive=True,
                    elem_id="search-knowledge-base",
                )
                search_top_k = gr.Slider(label="返回数量", minimum=1, maximum=100, step=1, value=10)
                search_button = ui_button("执行检索")
        with gr.Column(scale=1):
            search_help = gr.HTML(value=format_search_help_html(), elem_id="search-help-panel")
    with gr.Group(elem_id="search-result-workspace"):
        search_result_state = gr.State([])
        search_query_state = gr.State("")
        search_selected_row_state = gr.State({})
        search_page_state = gr.State(initial_search_page)
        search_result_summary = gr.HTML(
            value=format_search_summary_html(None),
            elem_id="search-result-summary",
        )
        search_result = gr.Dataframe(
            headers=["序号", "文档名称", "定位", "检索来源", "匹配来源", "内容摘要"],
            datatype=["markdown"] * 6,
            interactive=False,
            row_count=0,
            column_count=6,
            label="检索结果列表",
            buttons=[],
            elem_id="search-results-table",
            value=initial_search_table_rows,
        )
        with gr.Row(elem_id="search-pagination-row"):
            search_prev_button = ui_button("上一页")
            search_next_button = ui_button("下一页")
        search_page_info = gr.HTML(
            value=format_table_pagination_html(initial_search_page_info),
            elem_id="search-page-info",
        )
    search_result_detail = gr.HTML(value=format_search_result_detail_html(None), elem_id="search-result-detail")
    with gr.Group(elem_id="search-action-panel"):
        with gr.Row(elem_id="search-export-row"):
            search_export_button = ui_button("下载结果")
        search_export_result = gr.HTML(
            value=format_operation_result_html(None, title="下载结果"),
            elem_id="search-export-result",
        )

    return {
        "search_help": search_help,
        "search_query": search_query,
        "search_knowledge_base": search_knowledge_base,
        "search_top_k": search_top_k,
        "search_button": search_button,
        "search_result_summary": search_result_summary,
        "search_result": search_result,
        "search_result_state": search_result_state,
        "search_query_state": search_query_state,
        "search_selected_row_state": search_selected_row_state,
        "search_page_state": search_page_state,
        "search_prev_button": search_prev_button,
        "search_next_button": search_next_button,
        "search_page_info": search_page_info,
        "search_result_detail": search_result_detail,
        "search_export_button": search_export_button,
        "search_export_result": search_export_result,
    }


def bind_search_events(
    *,
    components: dict[str, gr.components.Component],
    login_state,
    document_knowledge_base,
    quality_knowledge_base,
    review_knowledge_base,
    run_search_ui: Callable,
    change_search_knowledge_base_ui: Callable,
    select_search_result: Callable,
    change_search_page: Callable,
    export_search_results: Callable,
) -> None:
    """绑定知识库检索页事件，保持对外行为与原实现一致。"""

    search_button = components["search_button"]
    search_query = components["search_query"]
    search_top_k = components["search_top_k"]
    search_knowledge_base = components["search_knowledge_base"]
    search_result_summary = components["search_result_summary"]
    search_result = components["search_result"]
    search_result_state = components["search_result_state"]
    search_query_state = components["search_query_state"]
    search_result_detail = components["search_result_detail"]
    search_selected_row_state = components["search_selected_row_state"]
    search_page_state = components["search_page_state"]
    search_page_info = components["search_page_info"]
    search_prev_button = components["search_prev_button"]
    search_next_button = components["search_next_button"]
    search_export_button = components["search_export_button"]
    search_export_result = components["search_export_result"]

    search_button.click(
        fn=run_search_ui,
        inputs=[search_query, search_top_k, search_knowledge_base, login_state],
        outputs=[
            search_result_summary,
            search_result,
            search_result_state,
            search_query_state,
            search_result_detail,
            search_selected_row_state,
            search_page_state,
            search_page_info,
        ],
    )
    search_knowledge_base.input(
        fn=change_search_knowledge_base_ui,
        inputs=[search_knowledge_base, login_state],
        outputs=[
            document_knowledge_base,
            search_knowledge_base,
            quality_knowledge_base,
            review_knowledge_base,
            search_result_summary,
            search_result,
            search_result_state,
            search_query_state,
            search_result_detail,
            search_selected_row_state,
            search_page_state,
            search_page_info,
        ],
        queue=False,
    )
    search_result.select(
        fn=select_search_result,
        inputs=[search_result, search_result_state, search_query_state],
        outputs=[search_result_detail, search_result, search_selected_row_state],
    )
    search_prev_button.click(
        fn=lambda items, page: change_search_page(items, page, "prev"),
        inputs=[search_result_state, search_page_state],
        outputs=[search_result, search_page_state, search_page_info],
    )
    search_next_button.click(
        fn=lambda items, page: change_search_page(items, page, "next"),
        inputs=[search_result_state, search_page_state],
        outputs=[search_result, search_page_state, search_page_info],
    )
    search_export_button.click(
        fn=export_search_results,
        inputs=[search_result_state, search_selected_row_state, search_query_state],
        outputs=[search_export_result],
    )
