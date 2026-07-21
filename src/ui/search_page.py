"""程序说明：承载“知识库检索”页的组件构建与事件绑定，供主页面总装配复用。"""

from __future__ import annotations

from collections.abc import Callable

import gradio as gr

from src.common.errors import AppError
from src.retrieval.service import RetrievalService
from src.ui.page_helpers import (
    change_table_page,
    format_table_pagination_html,
    get_selected_search_item_from_page_rows,
    normalize_table_rows,
    paginate_table_rows,
    ui_button,
)
from src.ui.viewmodels import (
    build_search_result_rows,
    format_operation_result_html,
    format_search_export_markdown,
    format_search_help_html,
    format_search_result_detail_html,
    format_search_results,
    format_search_summary_html,
    normalize_search_query,
)


def build_search_table_page_outputs(
    search_rows: list[dict] | None,
    page: int | float | None = 1,
) -> tuple[list[list[object]], int, str]:
    """构建检索结果表格分页输出。"""

    full_rows = build_search_result_rows({"table": search_rows or []})
    page_rows, resolved_page, _total_pages, page_info = paginate_table_rows(
        full_rows,
        page,
        prepend_sequence=False,
    )
    return page_rows, resolved_page, format_table_pagination_html(page_info)


def build_search_detail_payload(
    search_row: dict | None,
    *,
    retrieval_service: RetrievalService,
) -> dict | None:
    """根据检索结果行补齐原文详情。"""

    if not search_row:
        return None
    detail = retrieval_service.get_chunk_detail(search_row.get("chunk_id", "")) or {}
    return {**search_row, **detail}


def build_search_detail(
    search_row: dict | None,
    query_text: str,
    *,
    retrieval_service: RetrievalService,
) -> str:
    """根据检索结果行构建原文详情。"""

    return format_search_result_detail_html(
        build_search_detail_payload(search_row, retrieval_service=retrieval_service),
        query_text=query_text,
    )


def export_search_results(
    search_rows: list[dict],
    selected_search_row: dict | None,
    query_text: str,
    *,
    export_markdown_result: Callable[..., str],
) -> str:
    """导出当前检索结果。"""

    formatted = {
        "count": len(search_rows or []),
        "query_text": normalize_search_query(query_text),
        "table": search_rows or [],
    }
    markdown_text = format_search_export_markdown(
        formatted,
        selected_search_row or (search_rows[0] if search_rows else None),
        query_text=query_text,
    )
    selected_chunk_id = str((selected_search_row or {}).get("chunk_id") or "")
    return export_markdown_result(
        "文档检索",
        "检索结果",
        markdown_text,
        linked_id=selected_chunk_id or None,
    )


def run_search(
    query: str,
    top_k: int,
    knowledge_base_choice: str | None = None,
    login_session: dict[str, object] | None = None,
    *,
    retrieval_service: RetrievalService,
    has_tab_access: Callable[[dict[str, object] | None, str], bool],
    resolve_authorized_knowledge_base: Callable[[str | None, dict[str, object] | None], str | None],
) -> tuple[str, list[list[str]], list[dict], str, str, dict]:
    """执行授权知识库混合检索并构建页面结果。"""

    normalized_query = normalize_search_query(query)
    if not normalized_query:
        return (
            format_operation_result_html(
                {"success": False, "message": "请输入关键词、短语或整句后再检索"},
                title="检索结果",
            ),
            [],
            [],
            "",
            format_search_result_detail_html(None, query_text=""),
            {},
        )
    if not has_tab_access(login_session, "知识库检索"):
        return (
            format_operation_result_html(
                {"success": False, "message": "当前账号没有知识库检索权限。"},
                title="检索结果",
            ),
            [],
            [],
            normalized_query,
            format_search_result_detail_html(None, query_text=normalized_query),
            {},
        )
    knowledge_base_id = resolve_authorized_knowledge_base(knowledge_base_choice, login_session)
    if not knowledge_base_id:
        return (
            format_operation_result_html(
                {"success": False, "message": "当前账号没有可用知识库，请联系管理员开通知识库权限。"},
                title="检索结果",
            ),
            [],
            [],
            normalized_query,
            format_search_result_detail_html(None, query_text=normalized_query),
            {},
        )
    try:
        items = retrieval_service.hybrid_search(
            normalized_query,
            top_k=top_k,
            knowledge_base_id=knowledge_base_id,
            use_rerank=True,
        )
    except AppError as exc:
        return (
            format_operation_result_html(
                {"success": False, "message": exc.message, "error_code": exc.error_code},
                title="检索结果",
            ),
            [],
            [],
            normalized_query,
            format_search_result_detail_html(None, query_text=normalized_query),
            {},
        )
    formatted = format_search_results(items, query_text=normalized_query)
    selected_row = (
        build_search_detail_payload(formatted["table"][0], retrieval_service=retrieval_service)
        if formatted["table"]
        else {}
    ) or {}
    detail_html = (
        format_search_result_detail_html(selected_row, query_text=normalized_query)
        if selected_row
        else format_search_result_detail_html(None, query_text=normalized_query)
    )
    return (
        format_search_summary_html(formatted),
        build_search_result_rows(formatted, selected_row_index=0 if formatted["table"] else None),
        formatted["table"],
        normalized_query,
        detail_html,
        selected_row,
    )


def run_search_ui(
    query: str,
    top_k: int,
    knowledge_base_choice: str | None = None,
    login_session: dict[str, object] | None = None,
    *,
    retrieval_service: RetrievalService,
    has_tab_access: Callable[[dict[str, object] | None, str], bool],
    resolve_authorized_knowledge_base: Callable[[str | None, dict[str, object] | None], str | None],
) -> tuple[str, list[list[object]], list[dict], str, str, dict, int, str]:
    """执行检索并返回分页后的界面输出。"""

    effective_session = login_session
    if effective_session is None:
        effective_session = {
            "is_admin": False,
            "permissions": {"tab_names": [], "kb_ids": []},
        }
    summary_html, _full_rows, search_rows, normalized_query, detail_html, selected_row = run_search(
        query,
        top_k,
        knowledge_base_choice,
        effective_session,
        retrieval_service=retrieval_service,
        has_tab_access=has_tab_access,
        resolve_authorized_knowledge_base=resolve_authorized_knowledge_base,
    )
    page_rows, page_value, page_info = build_search_table_page_outputs(search_rows, page=1)
    return summary_html, page_rows, search_rows, normalized_query, detail_html, selected_row, page_value, page_info


def reset_search_workspace_ui(
    knowledge_base_choice: str | None = None,
) -> tuple[str, list[list[object]], list[dict], str, str, dict, int, str]:
    """切换知识库后清空旧检索结果，避免跨库误读。"""

    _ = knowledge_base_choice
    page_rows, page_value, page_info = build_search_table_page_outputs([], page=1)
    return (
        format_operation_result_html(
            {"success": True, "message": "已切换知识库，请重新执行检索。"},
            title="检索结果",
        ),
        page_rows,
        [],
        "",
        format_search_result_detail_html(None, query_text=""),
        {},
        page_value,
        page_info,
    )


def change_search_page(
    search_rows: list[dict],
    current_page: int | float,
    action: str,
) -> tuple[list[list[object]], int, str]:
    """切换检索结果分页。"""

    _current_page_rows, page_value, _page_info = build_search_table_page_outputs(
        search_rows,
        page=current_page,
    )
    full_rows = build_search_result_rows({"table": search_rows or []})
    page_rows, new_page, new_page_info = change_table_page(
        full_rows,
        page_value,
        action=action,
        prepend_sequence=False,
    )
    return page_rows, new_page, format_table_pagination_html(new_page_info)


def select_search_result(
    current_page_rows: list[list[object]],
    search_rows: list[dict],
    query_text: str,
    evt: gr.SelectData,
    *,
    retrieval_service: RetrievalService,
) -> tuple[str, list[list[object]], dict]:
    """点击检索结果表格后展示对应原文。"""

    page_rows = normalize_table_rows(current_page_rows)
    if not search_rows or not page_rows:
        return format_search_result_detail_html(None, query_text=query_text), page_rows, {}
    matched_row = get_selected_search_item_from_page_rows(page_rows, search_rows, evt)
    selected_row = build_search_detail_payload(matched_row, retrieval_service=retrieval_service) or {}
    return (
        format_search_result_detail_html(selected_row, query_text=query_text),
        page_rows,
        selected_row,
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
