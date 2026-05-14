"""程序说明：承载“知识库管理”页的组件构建与事件绑定，供主页面总装配复用。"""

from __future__ import annotations

from collections.abc import Callable

import gradio as gr

from src.ui.page_helpers import format_table_pagination_html, ui_button
from src.ui.viewmodels import format_document_management_help_html, format_operation_result_html


def build_document_tab(*, initial_values: dict[str, object]) -> dict[str, gr.components.Component]:
    """构建知识库管理页组件，并返回后续事件绑定所需的组件集合。"""

    with gr.Row(elem_id="document-management-top-row"):
        with gr.Column(scale=1):
            document_management_help = gr.HTML(
                value=format_document_management_help_html(),
                elem_id="document-management-help-panel",
            )
        with gr.Column(scale=1):
            with gr.Group(elem_id="document-management-selector-panel"):
                document_knowledge_base = gr.Dropdown(
                    label="当前知识库",
                    choices=initial_values["knowledge_base_choices"],
                    value=initial_values["initial_knowledge_base_choice"],
                    interactive=True,
                    elem_id="document-knowledge-base",
                )
                scan_button = ui_button("刷新文档列表")
    with gr.Row(elem_id="document-management-summary-row"):
        with gr.Column(scale=1):
            with gr.Group(elem_id="document-summary-panel"):
                document_summary = gr.HTML(value=initial_values["document_summary"])
        with gr.Column(scale=1):
            with gr.Group(elem_id="database-summary-panel"):
                database_summary = gr.HTML(value=initial_values["database_summary"])

    with gr.Group(elem_id="document-current-panel"):
        gr.Markdown("### 当前选中文档", elem_id="document-current-title")
        gr.HTML(
            value="<p>优先在这里选择目标文档，再执行注册、重建或入库质检。</p>",
            elem_id="document-current-note",
        )
        document_choices = gr.Dropdown(
            label="选择文档",
            choices=initial_values["document_choices"],
            value=initial_values["active_choice"],
            interactive=True,
        )
        document_detail = gr.HTML(value=initial_values["document_detail"], elem_id="document-current-detail")
        document_target_knowledge_base = gr.Dropdown(
            label="调整归属到",
            choices=initial_values["knowledge_base_choices"],
            value=initial_values["initial_knowledge_base_choice"],
            interactive=True,
            elem_id="document-target-knowledge-base",
        )
        with gr.Row(elem_id="document-current-actions-row"):
            register_button = ui_button("注册当前文档", interactive=bool(initial_values["register_interactive"]))
            rebuild_button = ui_button("重建当前文档索引", interactive=bool(initial_values["rebuild_interactive"]))
            status_button = ui_button("刷新状态")
            move_document_button = ui_button("调整文档归属", elem_id="document-move-button")

    with gr.Column(elem_id="database-summary-table-panel"):
        database_summary_table = gr.Dataframe(
            headers=["序号", "指标", "数量"],
            datatype=["str", "str", "str"],
            interactive=False,
            row_count=0,
            column_count=3,
            label="数据库统计",
            buttons=[],
            elem_id="database-summary-table",
            value=initial_values["database_table_rows"],
        )
        with gr.Row(elem_id="database-pagination-row"):
            database_prev_button = ui_button("上一页")
            database_next_button = ui_button("下一页")
        database_page_info = gr.HTML(
            value=format_table_pagination_html(str(initial_values["database_page_info"])),
            elem_id="database-page-info",
        )

    with gr.Column(elem_id="document-list-panel"):
        document_table = gr.Dataframe(
            headers=["序号", "文件名", "文档名称", "归属知识库", "大小", "入库时间", "已注册", "索引状态", "需重建", "推荐动作", "错误信息"],
            datatype=["str"] * 11,
            interactive=False,
            row_count=0,
            column_count=11,
            label="现有文档列表",
            buttons=[],
            elem_id="document-table",
            value=initial_values["document_table_rows"],
        )
        with gr.Row(elem_id="document-pagination-row"):
            document_prev_button = ui_button("上一页")
            document_next_button = ui_button("下一页")
        document_page_info = gr.HTML(
            value=format_table_pagination_html(str(initial_values["document_page_info"])),
            elem_id="document-page-info",
        )
    with gr.Row(elem_id="document-management-actions-row"):
        register_all_button = ui_button("注册全部待处理文档")
    with gr.Row(elem_id="document-management-result-row"):
        with gr.Column(scale=1):
            register_result = gr.HTML(
                value=format_operation_result_html(None, title="注册结果"),
                elem_id="document-register-result",
            )
        with gr.Column(scale=1):
            rebuild_result = gr.HTML(
                value=format_operation_result_html(None, title="重建结果"),
                elem_id="document-rebuild-result",
            )
    with gr.Accordion("入库质检", open=False, elem_id="document-quality-accordion"):
        with gr.Group(elem_id="document-quality-panel"):
            with gr.Row(elem_id="document-quality-top-actions"):
                document_quality_run_button = ui_button("执行入库质检")
                document_quality_result_export_button = ui_button("下载质检结果")
            document_quality_result_export_result = gr.HTML(
                value=format_operation_result_html(None, title="下载结果"),
                elem_id="document-quality-export-result",
            )
            with gr.Row(elem_id="document-quality-summary-row", equal_height=True):
                with gr.Column(scale=1):
                    document_quality_report = gr.HTML(
                        value=initial_values["document_quality_report"],
                        elem_id="document-quality-report",
                    )
                with gr.Column(scale=1):
                    document_quality_checks = gr.HTML(
                        value=initial_values["document_quality_checks"],
                        elem_id="document-quality-checks",
                    )
            with gr.Row(elem_id="document-quality-sample-row", equal_height=True):
                with gr.Column(scale=1):
                    document_quality_sections = gr.Dataframe(
                        headers=["序号", "定位", "章节标题", "层级", "章节字数", "内容预览"],
                        datatype=["str"] * 6,
                        interactive=False,
                        row_count=0,
                        column_count=6,
                        label="章节抽样",
                        buttons=[],
                        elem_id="document-quality-sections-table",
                        value=initial_values["document_quality_sections_table_rows"],
                    )
                    with gr.Row(elem_id="document-quality-sections-pagination-row"):
                        document_quality_sections_prev_button = ui_button("上一页")
                        document_quality_sections_next_button = ui_button("下一页")
                    document_quality_sections_page_info = gr.HTML(
                        value=format_table_pagination_html(str(initial_values["document_quality_sections_page_info"])),
                        elem_id="document-quality-sections-page-info",
                    )
                with gr.Column(scale=1):
                    document_quality_chunks = gr.Dataframe(
                        headers=["序号", "片段 ID", "序号", "所属章节", "定位", "长度", "内容预览"],
                        datatype=["str"] * 7,
                        interactive=False,
                        row_count=0,
                        column_count=7,
                        label="分块抽样",
                        buttons=[],
                        elem_id="document-quality-chunks-table",
                        value=initial_values["document_quality_chunks_table_rows"],
                    )
                    with gr.Row(elem_id="document-quality-chunks-pagination-row"):
                        document_quality_chunks_prev_button = ui_button("上一页")
                        document_quality_chunks_next_button = ui_button("下一页")
                    document_quality_chunks_page_info = gr.HTML(
                        value=format_table_pagination_html(str(initial_values["document_quality_chunks_page_info"])),
                        elem_id="document-quality-chunks-page-info",
                    )
            with gr.Row(elem_id="document-quality-search-row"):
                with gr.Column(scale=1):
                    document_quality_search_query = gr.Textbox(
                        label="文档内检索验证",
                        lines=2,
                        placeholder="输入当前文档中应当命中的标题、专有词或关键句，用于验证索引效果",
                    )
                    with gr.Row(elem_id="document-quality-search-action-row"):
                        document_quality_search_button = ui_button("验证当前文档检索")
                        document_quality_search_export_button = ui_button("下载检索结果")
                with gr.Column(scale=1):
                    document_quality_search_summary = gr.HTML(
                        value=initial_values["document_quality_search_summary"],
                        elem_id="document-quality-search-summary",
                    )
            document_quality_search_export_result = gr.HTML(
                value=format_operation_result_html(None, title="下载结果"),
                elem_id="document-quality-search-export-result",
            )
            document_quality_search_results = gr.Dataframe(
                headers=["序号", "文档名称", "定位", "检索来源", "匹配来源", "内容摘要"],
                datatype=["markdown"] * 6,
                interactive=False,
                row_count=0,
                column_count=6,
                label="文档内检索结果",
                buttons=[],
                elem_id="document-quality-search-results",
                value=initial_values["document_quality_search_table_rows"],
            )
            with gr.Row(elem_id="document-quality-search-pagination-row"):
                document_quality_search_prev_button = ui_button("上一页")
                document_quality_search_next_button = ui_button("下一页")
            document_quality_search_page_info = gr.HTML(
                value=format_table_pagination_html(str(initial_values["document_quality_search_page_info"])),
                elem_id="document-quality-search-page-info",
            )
            document_quality_search_detail = gr.HTML(
                value=initial_values["document_quality_search_detail"],
                elem_id="document-quality-search-detail",
            )
            with gr.Row(elem_id="document-quality-batch-action-row"):
                document_quality_batch_button = ui_button("执行全部文档质检")
                document_quality_csv_export_button = ui_button("导出质检 CSV")
                document_quality_batch_export_button = ui_button("下载批量结果")
            with gr.Column(elem_id="document-quality-batch-panel"):
                document_quality_batch_summary = gr.HTML(
                    value=initial_values["document_quality_batch_summary"],
                    elem_id="document-quality-batch-summary",
                )
                document_quality_csv_export_result = gr.HTML(
                    value=format_operation_result_html(None, title="导出结果"),
                    elem_id="document-quality-csv-export-result",
                )
                document_quality_batch_export_result = gr.HTML(
                    value=format_operation_result_html(None, title="下载结果"),
                    elem_id="document-quality-batch-export-result",
                )
                document_quality_batch_table = gr.Dataframe(
                    headers=["序号", "文档名称", "文档 UID", "索引状态", "章节数", "分块数", "全文索引", "向量数", "质检等级", "风险摘要"],
                    datatype=["str"] * 10,
                    interactive=False,
                    row_count=0,
                    column_count=10,
                    label="批量质检结果",
                    buttons=[],
                    elem_id="document-quality-batch-table",
                    value=initial_values["document_quality_batch_table_rows"],
                )
                with gr.Row(elem_id="document-quality-batch-pagination-row"):
                    document_quality_batch_prev_button = ui_button("上一页")
                    document_quality_batch_next_button = ui_button("下一页")
                document_quality_batch_page_info = gr.HTML(
                    value=format_table_pagination_html(str(initial_values["document_quality_batch_page_info"])),
                    elem_id="document-quality-batch-page-info",
                )
            with gr.Column(elem_id="document-quality-config-panel"):
                document_quality_config_panel = gr.HTML(
                    value=initial_values["document_quality_config_html"],
                    elem_id="document-quality-config-panel-html",
                )
                document_quality_config_result = gr.HTML(
                    value=initial_values["document_quality_config_result"],
                    elem_id="document-quality-config-result",
                )
                with gr.Group(elem_id="document-quality-config-form"):
                    gr.Markdown("### 质检阈值配置")
                    with gr.Row(elem_id="document-quality-config-form-row-1"):
                        document_quality_sample_limit = gr.Number(
                            label="抽样数量",
                            value=initial_values["quality_sample_limit"],
                            precision=0,
                        )
                        document_quality_long_document_char_threshold = gr.Number(
                            label="长文字数阈值",
                            value=initial_values["quality_long_document_char_threshold"],
                            precision=0,
                        )
                    with gr.Row(elem_id="document-quality-config-form-row-2"):
                        document_quality_min_sections_for_long_doc = gr.Number(
                            label="长文最少章节",
                            value=initial_values["quality_min_sections_for_long_doc"],
                            precision=0,
                        )
                        document_quality_max_avg_chunks_per_section = gr.Number(
                            label="每章分块上限",
                            value=initial_values["quality_max_avg_chunks_per_section"],
                            precision=0,
                        )
                    with gr.Row(elem_id="document-quality-config-form-row-3"):
                        document_quality_max_chunk_chars = gr.Number(
                            label="超长分块阈值",
                            value=initial_values["quality_max_chunk_chars"],
                            precision=0,
                        )
                        document_quality_short_chunk_chars = gr.Number(
                            label="过短分块阈值",
                            value=initial_values["quality_short_chunk_chars"],
                            precision=0,
                        )
                    with gr.Row(elem_id="document-quality-config-form-row-4"):
                        document_quality_short_chunk_warn_min_chunk_count = gr.Number(
                            label="过短分块告警起点",
                            value=initial_values["quality_short_chunk_warn_min_chunk_count"],
                            precision=0,
                        )
                    with gr.Row(elem_id="document-quality-config-action-row"):
                        document_quality_config_save_button = ui_button("保存质检阈值", variant="primary")
                        document_quality_config_export_button = ui_button("下载当前配置")
                    document_quality_config_export_result = gr.HTML(
                        value=format_operation_result_html(None, title="下载结果"),
                        elem_id="document-quality-config-export-result",
                    )

    return {
        "document_management_help": document_management_help,
        "document_knowledge_base": document_knowledge_base,
        "scan_button": scan_button,
        "document_summary": document_summary,
        "database_summary": database_summary,
        "document_choices": document_choices,
        "document_detail": document_detail,
        "document_target_knowledge_base": document_target_knowledge_base,
        "register_button": register_button,
        "rebuild_button": rebuild_button,
        "status_button": status_button,
        "move_document_button": move_document_button,
        "database_summary_table": database_summary_table,
        "database_prev_button": database_prev_button,
        "database_next_button": database_next_button,
        "database_page_info": database_page_info,
        "document_table": document_table,
        "document_prev_button": document_prev_button,
        "document_next_button": document_next_button,
        "document_page_info": document_page_info,
        "register_all_button": register_all_button,
        "register_result": register_result,
        "rebuild_result": rebuild_result,
        "document_quality_run_button": document_quality_run_button,
        "document_quality_result_export_button": document_quality_result_export_button,
        "document_quality_result_export_result": document_quality_result_export_result,
        "document_quality_report": document_quality_report,
        "document_quality_checks": document_quality_checks,
        "document_quality_sections": document_quality_sections,
        "document_quality_sections_prev_button": document_quality_sections_prev_button,
        "document_quality_sections_next_button": document_quality_sections_next_button,
        "document_quality_sections_page_info": document_quality_sections_page_info,
        "document_quality_chunks": document_quality_chunks,
        "document_quality_chunks_prev_button": document_quality_chunks_prev_button,
        "document_quality_chunks_next_button": document_quality_chunks_next_button,
        "document_quality_chunks_page_info": document_quality_chunks_page_info,
        "document_quality_search_query": document_quality_search_query,
        "document_quality_search_button": document_quality_search_button,
        "document_quality_search_export_button": document_quality_search_export_button,
        "document_quality_search_summary": document_quality_search_summary,
        "document_quality_search_export_result": document_quality_search_export_result,
        "document_quality_search_results": document_quality_search_results,
        "document_quality_search_prev_button": document_quality_search_prev_button,
        "document_quality_search_next_button": document_quality_search_next_button,
        "document_quality_search_page_info": document_quality_search_page_info,
        "document_quality_search_detail": document_quality_search_detail,
        "document_quality_batch_button": document_quality_batch_button,
        "document_quality_csv_export_button": document_quality_csv_export_button,
        "document_quality_batch_export_button": document_quality_batch_export_button,
        "document_quality_batch_summary": document_quality_batch_summary,
        "document_quality_csv_export_result": document_quality_csv_export_result,
        "document_quality_batch_export_result": document_quality_batch_export_result,
        "document_quality_batch_table": document_quality_batch_table,
        "document_quality_batch_prev_button": document_quality_batch_prev_button,
        "document_quality_batch_next_button": document_quality_batch_next_button,
        "document_quality_batch_page_info": document_quality_batch_page_info,
        "document_quality_config_panel": document_quality_config_panel,
        "document_quality_config_result": document_quality_config_result,
        "document_quality_sample_limit": document_quality_sample_limit,
        "document_quality_long_document_char_threshold": document_quality_long_document_char_threshold,
        "document_quality_min_sections_for_long_doc": document_quality_min_sections_for_long_doc,
        "document_quality_max_avg_chunks_per_section": document_quality_max_avg_chunks_per_section,
        "document_quality_max_chunk_chars": document_quality_max_chunk_chars,
        "document_quality_short_chunk_chars": document_quality_short_chunk_chars,
        "document_quality_short_chunk_warn_min_chunk_count": document_quality_short_chunk_warn_min_chunk_count,
        "document_quality_config_save_button": document_quality_config_save_button,
        "document_quality_config_export_button": document_quality_config_export_button,
        "document_quality_config_export_result": document_quality_config_export_result,
    }


def bind_document_events(
    *,
    components: dict[str, gr.components.Component],
    login_state,
    search_knowledge_base,
    quality_knowledge_base,
    review_knowledge_base,
    database_page_state,
    document_page_state,
    document_quality_sections_page_state,
    document_quality_chunks_page_state,
    document_quality_search_page_state,
    document_quality_batch_page_state,
    document_quality_search_state,
    document_quality_search_query_state,
    load_document_management_state_ui: Callable,
    change_document_knowledge_base_ui: Callable,
    reassign_selected_document_ui: Callable,
    inspect_document_ui: Callable,
    register_selected_document_ui: Callable,
    register_all_documents_ui: Callable,
    query_ingest_status_ui: Callable,
    rebuild_selected_document_ui: Callable,
    inspect_selected_document_quality_ui: Callable,
    run_document_quality_search_ui: Callable,
    select_document_quality_search_result: Callable,
    export_document_quality_result: Callable,
    export_document_quality_search_result: Callable,
    run_batch_document_quality_ui: Callable,
    export_document_quality_batch_result: Callable,
    export_document_quality_csv: Callable,
    save_document_quality_config: Callable,
    export_document_quality_config_result: Callable,
    change_database_summary_page: Callable,
    change_document_list_page: Callable,
    change_document_quality_sections_page: Callable,
    change_document_quality_chunks_page: Callable,
    change_document_table_page: Callable,
    change_document_quality_batch_page: Callable,
) -> None:
    """绑定知识库管理页事件，保持对外行为与原实现一致。"""

    document_knowledge_base = components["document_knowledge_base"]
    scan_button = components["scan_button"]
    document_summary = components["document_summary"]
    database_summary = components["database_summary"]
    database_summary_table = components["database_summary_table"]
    database_page_info = components["database_page_info"]
    document_table = components["document_table"]
    document_page_info = components["document_page_info"]
    document_choices = components["document_choices"]
    document_detail = components["document_detail"]
    register_button = components["register_button"]
    rebuild_button = components["rebuild_button"]
    document_quality_report = components["document_quality_report"]
    document_quality_checks = components["document_quality_checks"]
    document_quality_sections = components["document_quality_sections"]
    document_quality_sections_page_info = components["document_quality_sections_page_info"]
    document_quality_chunks = components["document_quality_chunks"]
    document_quality_chunks_page_info = components["document_quality_chunks_page_info"]
    document_quality_search_summary = components["document_quality_search_summary"]
    document_quality_search_results = components["document_quality_search_results"]
    document_quality_search_page_info = components["document_quality_search_page_info"]
    document_quality_search_detail = components["document_quality_search_detail"]
    document_quality_batch_summary = components["document_quality_batch_summary"]
    document_quality_batch_table = components["document_quality_batch_table"]
    document_quality_batch_page_info = components["document_quality_batch_page_info"]
    document_quality_config_panel = components["document_quality_config_panel"]
    document_quality_sample_limit = components["document_quality_sample_limit"]
    document_quality_long_document_char_threshold = components["document_quality_long_document_char_threshold"]
    document_quality_min_sections_for_long_doc = components["document_quality_min_sections_for_long_doc"]
    document_quality_max_avg_chunks_per_section = components["document_quality_max_avg_chunks_per_section"]
    document_quality_max_chunk_chars = components["document_quality_max_chunk_chars"]
    document_quality_short_chunk_chars = components["document_quality_short_chunk_chars"]
    document_quality_short_chunk_warn_min_chunk_count = components["document_quality_short_chunk_warn_min_chunk_count"]
    document_quality_config_result = components["document_quality_config_result"]
    document_quality_csv_export_result = components["document_quality_csv_export_result"]
    document_target_knowledge_base = components["document_target_knowledge_base"]
    register_result = components["register_result"]
    move_document_button = components["move_document_button"]
    register_all_button = components["register_all_button"]
    status_button = components["status_button"]
    rebuild_result = components["rebuild_result"]
    document_quality_result_export_result = components["document_quality_result_export_result"]
    document_quality_run_button = components["document_quality_run_button"]
    document_quality_search_query = components["document_quality_search_query"]
    document_quality_search_button = components["document_quality_search_button"]
    document_quality_search_export_button = components["document_quality_search_export_button"]
    document_quality_search_export_result = components["document_quality_search_export_result"]
    document_quality_result_export_button = components["document_quality_result_export_button"]
    document_quality_batch_button = components["document_quality_batch_button"]
    document_quality_batch_export_button = components["document_quality_batch_export_button"]
    document_quality_batch_export_result = components["document_quality_batch_export_result"]
    document_quality_csv_export_button = components["document_quality_csv_export_button"]
    document_quality_config_save_button = components["document_quality_config_save_button"]
    document_quality_config_export_button = components["document_quality_config_export_button"]
    document_quality_config_export_result = components["document_quality_config_export_result"]
    database_prev_button = components["database_prev_button"]
    database_next_button = components["database_next_button"]
    document_prev_button = components["document_prev_button"]
    document_next_button = components["document_next_button"]
    document_quality_sections_prev_button = components["document_quality_sections_prev_button"]
    document_quality_sections_next_button = components["document_quality_sections_next_button"]
    document_quality_chunks_prev_button = components["document_quality_chunks_prev_button"]
    document_quality_chunks_next_button = components["document_quality_chunks_next_button"]
    document_quality_search_prev_button = components["document_quality_search_prev_button"]
    document_quality_search_next_button = components["document_quality_search_next_button"]
    document_quality_batch_prev_button = components["document_quality_batch_prev_button"]
    document_quality_batch_next_button = components["document_quality_batch_next_button"]

    document_outputs = [
        document_knowledge_base,
        search_knowledge_base,
        quality_knowledge_base,
        review_knowledge_base,
        document_summary,
        database_summary,
        database_summary_table,
        database_page_state,
        database_page_info,
        document_table,
        document_page_state,
        document_page_info,
        document_choices,
        document_detail,
        register_button,
        rebuild_button,
        document_quality_report,
        document_quality_checks,
        document_quality_sections,
        document_quality_sections_page_state,
        document_quality_sections_page_info,
        document_quality_chunks,
        document_quality_chunks_page_state,
        document_quality_chunks_page_info,
        document_quality_search_summary,
        document_quality_search_results,
        document_quality_search_page_state,
        document_quality_search_page_info,
        document_quality_search_state,
        document_quality_search_detail,
        document_quality_batch_summary,
        document_quality_batch_table,
        document_quality_batch_page_state,
        document_quality_batch_page_info,
        document_quality_config_panel,
        document_quality_sample_limit,
        document_quality_long_document_char_threshold,
        document_quality_min_sections_for_long_doc,
        document_quality_max_avg_chunks_per_section,
        document_quality_max_chunk_chars,
        document_quality_short_chunk_chars,
        document_quality_short_chunk_warn_min_chunk_count,
        document_quality_config_result,
        document_quality_csv_export_result,
    ]

    document_knowledge_base.input(
        fn=change_document_knowledge_base_ui,
        inputs=[document_knowledge_base, login_state],
        outputs=document_outputs,
        queue=False,
    )
    document_knowledge_base.input(
        fn=lambda choice: gr.Dropdown(value=choice),
        inputs=[document_knowledge_base],
        outputs=[document_target_knowledge_base],
        queue=False,
    )
    scan_button.click(
        fn=load_document_management_state_ui,
        inputs=[document_knowledge_base, login_state],
        outputs=document_outputs[4:],
    )
    move_document_button.click(
        fn=reassign_selected_document_ui,
        inputs=[document_choices, document_target_knowledge_base, document_knowledge_base, login_state],
        outputs=[register_result, *document_outputs[4:]],
    )
    document_choices.input(
        fn=inspect_document_ui,
        inputs=[document_choices, document_knowledge_base, login_state],
        outputs=[
            document_detail,
            register_button,
            rebuild_button,
            document_quality_report,
            document_quality_checks,
            document_quality_sections,
            document_quality_sections_page_state,
            document_quality_sections_page_info,
            document_quality_chunks,
            document_quality_chunks_page_state,
            document_quality_chunks_page_info,
            document_quality_search_summary,
            document_quality_search_results,
            document_quality_search_page_state,
            document_quality_search_page_info,
            document_quality_search_state,
            document_quality_search_detail,
            document_quality_batch_summary,
            document_quality_batch_table,
            document_quality_batch_page_state,
            document_quality_batch_page_info,
            document_quality_config_panel,
            document_quality_sample_limit,
            document_quality_long_document_char_threshold,
            document_quality_min_sections_for_long_doc,
            document_quality_max_avg_chunks_per_section,
            document_quality_max_chunk_chars,
            document_quality_short_chunk_chars,
            document_quality_short_chunk_warn_min_chunk_count,
            document_quality_config_result,
            document_quality_csv_export_result,
        ],
        queue=False,
    )
    register_button.click(
        fn=register_selected_document_ui,
        inputs=[document_choices, document_knowledge_base, login_state],
        outputs=[register_result, *document_outputs[4:]],
    )
    register_all_button.click(
        fn=register_all_documents_ui,
        inputs=[document_knowledge_base, login_state],
        outputs=[register_result, *document_outputs[4:]],
    )
    status_button.click(
        fn=query_ingest_status_ui,
        inputs=[document_knowledge_base, login_state],
        outputs=document_outputs[4:],
    )
    rebuild_button.click(
        fn=rebuild_selected_document_ui,
        inputs=[document_choices, document_knowledge_base, login_state],
        outputs=[rebuild_result, *document_outputs[4:-1], document_quality_result_export_result],
    )
    document_quality_run_button.click(
        fn=inspect_selected_document_quality_ui,
        inputs=[document_choices, document_knowledge_base],
        outputs=[
            document_quality_report,
            document_quality_checks,
            document_quality_sections,
            document_quality_sections_page_state,
            document_quality_sections_page_info,
            document_quality_chunks,
            document_quality_chunks_page_state,
            document_quality_chunks_page_info,
            document_quality_search_summary,
            document_quality_search_results,
            document_quality_search_page_state,
            document_quality_search_page_info,
            document_quality_search_state,
            document_quality_search_detail,
        ],
    )
    document_quality_search_button.click(
        fn=run_document_quality_search_ui,
        inputs=[document_choices, document_quality_search_query, document_knowledge_base],
        outputs=[
            document_quality_search_summary,
            document_quality_search_results,
            document_quality_search_page_state,
            document_quality_search_page_info,
            document_quality_search_state,
            document_quality_search_query_state,
            document_quality_search_detail,
        ],
    )
    document_quality_search_results.select(
        fn=select_document_quality_search_result,
        inputs=[document_quality_search_state, document_quality_search_query_state, document_quality_search_results],
        outputs=[document_quality_search_detail, document_quality_search_results],
    )
    document_quality_result_export_button.click(
        fn=export_document_quality_result,
        inputs=[document_choices, document_quality_search_state, document_quality_search_query_state, document_knowledge_base],
        outputs=[document_quality_result_export_result],
    )
    document_quality_search_export_button.click(
        fn=export_document_quality_search_result,
        inputs=[document_choices, document_quality_search_state, document_quality_search_query_state, document_knowledge_base],
        outputs=[document_quality_search_export_result],
    )
    document_quality_batch_button.click(
        fn=run_batch_document_quality_ui,
        inputs=[document_knowledge_base],
        outputs=[document_quality_batch_summary, document_quality_batch_table, document_quality_batch_page_state, document_quality_batch_page_info],
    )
    document_quality_batch_export_button.click(
        fn=export_document_quality_batch_result,
        inputs=[document_knowledge_base],
        outputs=[document_quality_batch_export_result],
    )
    document_quality_csv_export_button.click(
        fn=export_document_quality_csv,
        inputs=[document_knowledge_base],
        outputs=[document_quality_csv_export_result],
    )
    document_quality_config_save_button.click(
        fn=save_document_quality_config,
        inputs=[
            document_quality_sample_limit,
            document_quality_long_document_char_threshold,
            document_quality_min_sections_for_long_doc,
            document_quality_max_avg_chunks_per_section,
            document_quality_max_chunk_chars,
            document_quality_short_chunk_chars,
            document_quality_short_chunk_warn_min_chunk_count,
        ],
        outputs=[
            document_quality_config_panel,
            document_quality_sample_limit,
            document_quality_long_document_char_threshold,
            document_quality_min_sections_for_long_doc,
            document_quality_max_avg_chunks_per_section,
            document_quality_max_chunk_chars,
            document_quality_short_chunk_chars,
            document_quality_short_chunk_warn_min_chunk_count,
            document_quality_config_result,
        ],
    )
    document_quality_config_export_button.click(
        fn=export_document_quality_config_result,
        inputs=[
            document_quality_sample_limit,
            document_quality_long_document_char_threshold,
            document_quality_min_sections_for_long_doc,
            document_quality_max_avg_chunks_per_section,
            document_quality_max_chunk_chars,
            document_quality_short_chunk_chars,
            document_quality_short_chunk_warn_min_chunk_count,
        ],
        outputs=[document_quality_config_export_result],
    )
    database_prev_button.click(
        fn=lambda choice, knowledge_base, page: change_database_summary_page(choice, knowledge_base, page, "prev"),
        inputs=[document_choices, document_knowledge_base, database_page_state],
        outputs=[database_summary_table, database_page_state, database_page_info],
    )
    database_next_button.click(
        fn=lambda choice, knowledge_base, page: change_database_summary_page(choice, knowledge_base, page, "next"),
        inputs=[document_choices, document_knowledge_base, database_page_state],
        outputs=[database_summary_table, database_page_state, database_page_info],
    )
    document_prev_button.click(
        fn=lambda choice, knowledge_base, page: change_document_list_page(choice, knowledge_base, page, "prev"),
        inputs=[document_choices, document_knowledge_base, document_page_state],
        outputs=[document_table, document_page_state, document_page_info],
    )
    document_next_button.click(
        fn=lambda choice, knowledge_base, page: change_document_list_page(choice, knowledge_base, page, "next"),
        inputs=[document_choices, document_knowledge_base, document_page_state],
        outputs=[document_table, document_page_state, document_page_info],
    )
    document_quality_sections_prev_button.click(
        fn=lambda choice, knowledge_base, page: change_document_quality_sections_page(choice, knowledge_base, page, "prev"),
        inputs=[document_choices, document_knowledge_base, document_quality_sections_page_state],
        outputs=[document_quality_sections, document_quality_sections_page_state, document_quality_sections_page_info],
    )
    document_quality_sections_next_button.click(
        fn=lambda choice, knowledge_base, page: change_document_quality_sections_page(choice, knowledge_base, page, "next"),
        inputs=[document_choices, document_knowledge_base, document_quality_sections_page_state],
        outputs=[document_quality_sections, document_quality_sections_page_state, document_quality_sections_page_info],
    )
    document_quality_chunks_prev_button.click(
        fn=lambda choice, knowledge_base, page: change_document_quality_chunks_page(choice, knowledge_base, page, "prev"),
        inputs=[document_choices, document_knowledge_base, document_quality_chunks_page_state],
        outputs=[document_quality_chunks, document_quality_chunks_page_state, document_quality_chunks_page_info],
    )
    document_quality_chunks_next_button.click(
        fn=lambda choice, knowledge_base, page: change_document_quality_chunks_page(choice, knowledge_base, page, "next"),
        inputs=[document_choices, document_knowledge_base, document_quality_chunks_page_state],
        outputs=[document_quality_chunks, document_quality_chunks_page_state, document_quality_chunks_page_info],
    )
    document_quality_search_prev_button.click(
        fn=lambda rows, page: change_document_table_page(rows, page, "prev", prepend_sequence=False),
        inputs=[document_quality_search_state, document_quality_search_page_state],
        outputs=[document_quality_search_results, document_quality_search_page_state, document_quality_search_page_info],
    )
    document_quality_search_next_button.click(
        fn=lambda rows, page: change_document_table_page(rows, page, "next", prepend_sequence=False),
        inputs=[document_quality_search_state, document_quality_search_page_state],
        outputs=[document_quality_search_results, document_quality_search_page_state, document_quality_search_page_info],
    )
    document_quality_batch_prev_button.click(
        fn=lambda knowledge_base, page: change_document_quality_batch_page(knowledge_base, page, "prev"),
        inputs=[document_knowledge_base, document_quality_batch_page_state],
        outputs=[document_quality_batch_table, document_quality_batch_page_state, document_quality_batch_page_info],
    )
    document_quality_batch_next_button.click(
        fn=lambda knowledge_base, page: change_document_quality_batch_page(knowledge_base, page, "next"),
        inputs=[document_knowledge_base, document_quality_batch_page_state],
        outputs=[document_quality_batch_table, document_quality_batch_page_state, document_quality_batch_page_info],
    )
