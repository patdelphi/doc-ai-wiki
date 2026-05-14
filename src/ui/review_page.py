"""程序说明：承载“人工审核”页的组件构建与事件绑定，供主页面总装配复用。"""

from __future__ import annotations

from collections.abc import Callable

import gradio as gr

from src.ui.page_helpers import format_table_pagination_html, ui_button
from src.ui.viewmodels import format_operation_result_html, format_review_help_html


def build_review_tab(
    *,
    knowledge_base_choices: list[str],
    initial_knowledge_base_choice: str | None,
    review_scope_choices: list[str],
    review_risk_choices: list[str],
    review_action_choices: list[str],
    initial_review_pending_table_rows: list[list[object]],
    initial_review_pending_page_info: str,
    initial_review_processed_table_rows: list[list[object]],
    initial_review_processed_page_info: str,
    initial_review_claim_view: str,
    initial_review_evidence_detail_html: str,
    initial_review_evidence_table_rows: list[list[object]],
    initial_review_evidence_page_info: str,
    initial_review_action_value: str,
    initial_review_note_value: str,
    initial_review_history_table_rows: list[list[object]],
    initial_review_history_page_info: str,
    initial_review_record_detail_html: str,
) -> dict[str, gr.components.Component]:
    """构建人工审核页组件，并返回后续事件绑定所需的组件集合。"""

    with gr.Group(elem_id="review-focus-panel"):
        with gr.Row(elem_id="review-filter-row"):
            review_knowledge_base = gr.Dropdown(
                label="当前知识库",
                choices=knowledge_base_choices,
                value=initial_knowledge_base_choice,
                interactive=True,
                elem_id="review-knowledge-base",
            )
            review_scope_filter = gr.Dropdown(
                label="列表范围",
                choices=review_scope_choices,
                value=review_scope_choices[0],
                interactive=True,
            )
            review_risk_filter = gr.Dropdown(
                label="风险筛选",
                choices=review_risk_choices,
                value=review_risk_choices[0],
                interactive=True,
            )
        review_help = gr.HTML(value=format_review_help_html(), elem_id="review-help-panel")

        with gr.Column(elem_id="review-pending-panel"):
            review_pending_candidates = gr.Dataframe(
                headers=["序号", "Claim ID", "Claim 摘要", "当前判定", "风险等级", "审核状态", "来源文档", "质检模板", "质检时间"],
                datatype=["str"] * 9,
                interactive=False,
                row_count=0,
                column_count=9,
                label="待处理记录",
                buttons=[],
                elem_id="review-pending-table",
                value=initial_review_pending_table_rows,
            )
            with gr.Row(elem_id="review-pending-pagination-row"):
                review_pending_prev_button = ui_button("上一页")
                review_pending_next_button = ui_button("下一页")
            review_pending_page_info = gr.HTML(
                value=format_table_pagination_html(initial_review_pending_page_info),
                elem_id="review-pending-page-info",
            )

        with gr.Column(elem_id="review-processed-panel"):
            review_processed_candidates = gr.Dataframe(
                headers=["序号", "Claim ID", "Claim 摘要", "当前判定", "风险等级", "审核状态", "来源文档", "质检模板", "质检时间"],
                datatype=["str"] * 9,
                interactive=False,
                row_count=0,
                column_count=9,
                label="已处理 Claim",
                buttons=[],
                elem_id="review-processed-table",
                value=initial_review_processed_table_rows,
            )
            with gr.Row(elem_id="review-processed-pagination-row"):
                review_processed_prev_button = ui_button("上一页")
                review_processed_next_button = ui_button("下一页")
            review_processed_page_info = gr.HTML(
                value=format_table_pagination_html(initial_review_processed_page_info),
                elem_id="review-processed-page-info",
            )

    with gr.Row(elem_id="review-summary-row", equal_height=True):
        with gr.Column(scale=1):
            review_claim_detail_panel = gr.HTML(value=initial_review_claim_view, elem_id="review-claim-detail")
        with gr.Column(scale=1):
            review_evidence_detail = gr.HTML(
                value=initial_review_evidence_detail_html,
                elem_id="review-evidence-detail",
            )

    with gr.Column(elem_id="review-evidence-list-panel"):
        review_evidence_table = gr.Dataframe(
            headers=["序号", "片段 ID", "文档", "定位", "证据关系", "检索来源", "检索路径", "重排分", "证据摘要"],
            datatype=["str"] * 9,
            interactive=False,
            row_count=0,
            column_count=9,
            label="关联证据列表",
            buttons=[],
            elem_id="review-evidence-table",
            value=initial_review_evidence_table_rows,
        )
        with gr.Row(elem_id="review-evidence-pagination-row"):
            review_evidence_prev_button = ui_button("上一页")
            review_evidence_next_button = ui_button("下一页")
        review_evidence_page_info = gr.HTML(
            value=format_table_pagination_html(initial_review_evidence_page_info),
            elem_id="review-evidence-page-info",
        )

    with gr.Group(elem_id="review-action-panel"):
        with gr.Group(elem_id="review-action-form"):
            review_action_input = gr.Dropdown(
                choices=review_action_choices,
                value=initial_review_action_value,
                label="审核动作",
                interactive=True,
            )
            review_note_input = gr.Textbox(
                label="审核备注",
                lines=4,
                value=initial_review_note_value,
            )
        with gr.Row(elem_id="review-action-buttons"):
            review_button = ui_button("提交审核")
            review_history_button = ui_button("刷新审核列表")
            review_export_button = ui_button("下载当前审核结果")
        with gr.Row(elem_id="review-action-feedback-row"):
            with gr.Column(scale=1):
                review_result = gr.HTML(
                    value=format_operation_result_html(None, title="审核结果"),
                    elem_id="review-result-panel",
                )
            with gr.Column(scale=1):
                review_export_result = gr.HTML(
                    value=format_operation_result_html(None, title="下载结果"),
                    elem_id="review-export-result",
                )

    with gr.Column(elem_id="review-history-panel"):
        review_history = gr.Dataframe(
            headers=["序号", "审核 ID", "Claim ID", "审核动作", "审核状态", "审核人", "审核时间", "审核备注", "Claim 摘要"],
            datatype=["str"] * 9,
            interactive=False,
            row_count=0,
            column_count=9,
            label="已审核记录",
            buttons=[],
            elem_id="review-history-table",
            value=initial_review_history_table_rows,
        )
        with gr.Row(elem_id="review-history-pagination-row"):
            review_history_prev_button = ui_button("上一页")
            review_history_next_button = ui_button("下一页")
        review_history_page_info = gr.HTML(
            value=format_table_pagination_html(initial_review_history_page_info),
            elem_id="review-history-page-info",
        )
        review_record_detail = gr.HTML(
            value=initial_review_record_detail_html,
            elem_id="review-record-detail",
        )

    return {
        "review_knowledge_base": review_knowledge_base,
        "review_scope_filter": review_scope_filter,
        "review_risk_filter": review_risk_filter,
        "review_help": review_help,
        "review_pending_candidates": review_pending_candidates,
        "review_pending_prev_button": review_pending_prev_button,
        "review_pending_next_button": review_pending_next_button,
        "review_pending_page_info": review_pending_page_info,
        "review_processed_candidates": review_processed_candidates,
        "review_processed_prev_button": review_processed_prev_button,
        "review_processed_next_button": review_processed_next_button,
        "review_processed_page_info": review_processed_page_info,
        "review_claim_detail_panel": review_claim_detail_panel,
        "review_evidence_detail": review_evidence_detail,
        "review_evidence_table": review_evidence_table,
        "review_evidence_prev_button": review_evidence_prev_button,
        "review_evidence_next_button": review_evidence_next_button,
        "review_evidence_page_info": review_evidence_page_info,
        "review_action_input": review_action_input,
        "review_note_input": review_note_input,
        "review_button": review_button,
        "review_history_button": review_history_button,
        "review_export_button": review_export_button,
        "review_result": review_result,
        "review_export_result": review_export_result,
        "review_history": review_history,
        "review_history_prev_button": review_history_prev_button,
        "review_history_next_button": review_history_next_button,
        "review_history_page_info": review_history_page_info,
        "review_record_detail": review_record_detail,
    }


def bind_review_events(
    *,
    components: dict[str, gr.components.Component],
    review_candidate_state,
    review_history_state,
    review_selected_record_state,
    review_selected_claim_state,
    review_claim_detail_state,
    review_evidence_items_state,
    review_pending_page_state,
    review_processed_page_state,
    review_evidence_page_state,
    review_history_page_state,
    login_state,
    document_knowledge_base,
    search_knowledge_base,
    quality_knowledge_base,
    list_review_workspace_ui: Callable,
    change_review_knowledge_base_ui: Callable,
    export_review_results: Callable,
    change_review_filters_ui: Callable,
    select_review_candidate_ui: Callable,
    select_review_history_record_ui: Callable,
    select_quality_evidence: Callable,
    submit_review_action_ui: Callable,
    change_review_candidate_page: Callable,
    change_review_evidence_page: Callable,
    change_review_history_page: Callable,
) -> None:
    """绑定人工审核页事件，保持对外行为与原实现一致。"""

    review_knowledge_base = components["review_knowledge_base"]
    review_scope_filter = components["review_scope_filter"]
    review_risk_filter = components["review_risk_filter"]
    review_pending_candidates = components["review_pending_candidates"]
    review_pending_page_info = components["review_pending_page_info"]
    review_processed_candidates = components["review_processed_candidates"]
    review_processed_page_info = components["review_processed_page_info"]
    review_claim_detail_panel = components["review_claim_detail_panel"]
    review_evidence_detail = components["review_evidence_detail"]
    review_evidence_table = components["review_evidence_table"]
    review_evidence_page_info = components["review_evidence_page_info"]
    review_action_input = components["review_action_input"]
    review_note_input = components["review_note_input"]
    review_button = components["review_button"]
    review_history_button = components["review_history_button"]
    review_export_button = components["review_export_button"]
    review_result = components["review_result"]
    review_export_result = components["review_export_result"]
    review_history = components["review_history"]
    review_history_page_info = components["review_history_page_info"]
    review_record_detail = components["review_record_detail"]
    review_pending_prev_button = components["review_pending_prev_button"]
    review_pending_next_button = components["review_pending_next_button"]
    review_processed_prev_button = components["review_processed_prev_button"]
    review_processed_next_button = components["review_processed_next_button"]
    review_evidence_prev_button = components["review_evidence_prev_button"]
    review_evidence_next_button = components["review_evidence_next_button"]
    review_history_prev_button = components["review_history_prev_button"]
    review_history_next_button = components["review_history_next_button"]

    review_history_button.click(
        fn=list_review_workspace_ui,
        inputs=[review_scope_filter, review_risk_filter, review_selected_claim_state, review_knowledge_base, login_state],
        outputs=[
            review_pending_candidates,
            review_pending_page_state,
            review_pending_page_info,
            review_processed_candidates,
            review_processed_page_state,
            review_processed_page_info,
            review_candidate_state,
            review_selected_claim_state,
            review_claim_detail_state,
            review_claim_detail_panel,
            review_evidence_table,
            review_evidence_page_state,
            review_evidence_page_info,
            review_evidence_items_state,
            review_evidence_detail,
            review_action_input,
            review_note_input,
            review_history,
            review_history_page_state,
            review_history_page_info,
            review_history_state,
            review_selected_record_state,
            review_record_detail,
        ],
    )
    review_knowledge_base.input(
        fn=change_review_knowledge_base_ui,
        inputs=[review_scope_filter, review_risk_filter, review_selected_claim_state, review_knowledge_base, login_state],
        outputs=[
            document_knowledge_base,
            search_knowledge_base,
            quality_knowledge_base,
            review_knowledge_base,
            review_pending_candidates,
            review_pending_page_state,
            review_pending_page_info,
            review_processed_candidates,
            review_processed_page_state,
            review_processed_page_info,
            review_candidate_state,
            review_selected_claim_state,
            review_claim_detail_state,
            review_claim_detail_panel,
            review_evidence_table,
            review_evidence_page_state,
            review_evidence_page_info,
            review_evidence_items_state,
            review_evidence_detail,
            review_action_input,
            review_note_input,
            review_history,
            review_history_page_state,
            review_history_page_info,
            review_history_state,
            review_selected_record_state,
            review_record_detail,
        ],
        queue=False,
    )
    review_export_button.click(
        fn=export_review_results,
        inputs=[review_selected_claim_state, review_claim_detail_state, review_evidence_items_state, review_selected_record_state, review_history_state],
        outputs=[review_export_result],
    )
    review_scope_filter.input(
        fn=change_review_filters_ui,
        inputs=[review_candidate_state, review_history_state, review_selected_claim_state, review_scope_filter, review_risk_filter],
        outputs=[
            review_pending_candidates,
            review_pending_page_state,
            review_pending_page_info,
            review_processed_candidates,
            review_processed_page_state,
            review_processed_page_info,
            review_candidate_state,
            review_selected_claim_state,
            review_claim_detail_state,
            review_claim_detail_panel,
            review_evidence_table,
            review_evidence_page_state,
            review_evidence_page_info,
            review_evidence_items_state,
            review_evidence_detail,
            review_action_input,
            review_note_input,
            review_history,
            review_history_page_state,
            review_history_page_info,
            review_history_state,
            review_selected_record_state,
            review_record_detail,
        ],
        queue=False,
    )
    review_risk_filter.input(
        fn=change_review_filters_ui,
        inputs=[review_candidate_state, review_history_state, review_selected_claim_state, review_scope_filter, review_risk_filter],
        outputs=[
            review_pending_candidates,
            review_pending_page_state,
            review_pending_page_info,
            review_processed_candidates,
            review_processed_page_state,
            review_processed_page_info,
            review_candidate_state,
            review_selected_claim_state,
            review_claim_detail_state,
            review_claim_detail_panel,
            review_evidence_table,
            review_evidence_page_state,
            review_evidence_page_info,
            review_evidence_items_state,
            review_evidence_detail,
            review_action_input,
            review_note_input,
            review_history,
            review_history_page_state,
            review_history_page_info,
            review_history_state,
            review_selected_record_state,
            review_record_detail,
        ],
        queue=False,
    )
    review_pending_candidates.select(
        fn=select_review_candidate_ui,
        inputs=[review_pending_candidates, review_candidate_state, review_history_state, review_scope_filter, review_risk_filter],
        outputs=[
            review_selected_claim_state,
            review_claim_detail_state,
            review_claim_detail_panel,
            review_evidence_table,
            review_evidence_page_state,
            review_evidence_page_info,
            review_evidence_items_state,
            review_evidence_detail,
            review_action_input,
            review_note_input,
            review_selected_record_state,
            review_record_detail,
        ],
    )
    review_processed_candidates.select(
        fn=select_review_candidate_ui,
        inputs=[review_processed_candidates, review_candidate_state, review_history_state, review_scope_filter, review_risk_filter],
        outputs=[
            review_selected_claim_state,
            review_claim_detail_state,
            review_claim_detail_panel,
            review_evidence_table,
            review_evidence_page_state,
            review_evidence_page_info,
            review_evidence_items_state,
            review_evidence_detail,
            review_action_input,
            review_note_input,
            review_selected_record_state,
            review_record_detail,
        ],
    )
    review_history.select(
        fn=select_review_history_record_ui,
        inputs=[review_history_state, review_candidate_state, review_scope_filter, review_risk_filter, review_history],
        outputs=[
            review_selected_claim_state,
            review_claim_detail_state,
            review_claim_detail_panel,
            review_evidence_table,
            review_evidence_page_state,
            review_evidence_page_info,
            review_evidence_items_state,
            review_evidence_detail,
            review_action_input,
            review_note_input,
            review_selected_record_state,
            review_record_detail,
        ],
    )
    review_evidence_table.select(
        fn=select_quality_evidence,
        inputs=[review_evidence_items_state, review_evidence_table],
        outputs=[review_evidence_detail],
    )
    review_button.click(
        fn=submit_review_action_ui,
        inputs=[review_selected_claim_state, review_action_input, review_note_input, review_scope_filter, review_risk_filter, review_knowledge_base, login_state],
        outputs=[
            review_result,
            review_pending_candidates,
            review_pending_page_state,
            review_pending_page_info,
            review_processed_candidates,
            review_processed_page_state,
            review_processed_page_info,
            review_candidate_state,
            review_selected_claim_state,
            review_claim_detail_state,
            review_claim_detail_panel,
            review_evidence_table,
            review_evidence_page_state,
            review_evidence_page_info,
            review_evidence_items_state,
            review_evidence_detail,
            review_action_input,
            review_note_input,
            review_history,
            review_history_page_state,
            review_history_page_info,
            review_history_state,
            review_selected_record_state,
            review_record_detail,
        ],
    )
    review_pending_prev_button.click(
        fn=lambda items, scope, risk, page: change_review_candidate_page(items, scope, risk, page, "prev", processed=False),
        inputs=[review_candidate_state, review_scope_filter, review_risk_filter, review_pending_page_state],
        outputs=[review_pending_candidates, review_pending_page_state, review_pending_page_info],
    )
    review_pending_next_button.click(
        fn=lambda items, scope, risk, page: change_review_candidate_page(items, scope, risk, page, "next", processed=False),
        inputs=[review_candidate_state, review_scope_filter, review_risk_filter, review_pending_page_state],
        outputs=[review_pending_candidates, review_pending_page_state, review_pending_page_info],
    )
    review_processed_prev_button.click(
        fn=lambda items, scope, risk, page: change_review_candidate_page(items, scope, risk, page, "prev", processed=True),
        inputs=[review_candidate_state, review_scope_filter, review_risk_filter, review_processed_page_state],
        outputs=[review_processed_candidates, review_processed_page_state, review_processed_page_info],
    )
    review_processed_next_button.click(
        fn=lambda items, scope, risk, page: change_review_candidate_page(items, scope, risk, page, "next", processed=True),
        inputs=[review_candidate_state, review_scope_filter, review_risk_filter, review_processed_page_state],
        outputs=[review_processed_candidates, review_processed_page_state, review_processed_page_info],
    )
    review_evidence_prev_button.click(
        fn=lambda items, page: change_review_evidence_page(items, page, "prev"),
        inputs=[review_evidence_items_state, review_evidence_page_state],
        outputs=[review_evidence_table, review_evidence_page_state, review_evidence_page_info],
    )
    review_evidence_next_button.click(
        fn=lambda items, page: change_review_evidence_page(items, page, "next"),
        inputs=[review_evidence_items_state, review_evidence_page_state],
        outputs=[review_evidence_table, review_evidence_page_state, review_evidence_page_info],
    )
    review_history_prev_button.click(
        fn=lambda items, page: change_review_history_page(items, page, "prev"),
        inputs=[review_history_state, review_history_page_state],
        outputs=[review_history, review_history_page_state, review_history_page_info],
    )
    review_history_next_button.click(
        fn=lambda items, page: change_review_history_page(items, page, "next"),
        inputs=[review_history_state, review_history_page_state],
        outputs=[review_history, review_history_page_state, review_history_page_info],
    )
