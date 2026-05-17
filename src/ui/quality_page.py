"""程序说明：承载“AI 质检”页的组件构建与事件绑定，供主页面总装配复用。"""

from __future__ import annotations

from collections.abc import Callable

import gradio as gr

from src.ui.page_helpers import TABLE_PAGE_SIZE, format_table_pagination_html, ui_button
from src.ui.viewmodels import (
    format_active_quality_check_html,
    format_operation_result_html,
    format_quality_evaluation_help_html,
    format_quality_help_html,
    format_quality_template_html,
)


def build_quality_tab(
    *,
    knowledge_base_choices: list[str],
    initial_knowledge_base_choice: str | None,
    template_choices: list[str],
    default_template_choice: str | None,
    default_template,
    initial_formatted_quality_result: dict | None,
    initial_quality_claim_page: int,
    initial_quality_claim_choices: list[str],
    initial_selected_claim_choice: str | None,
    initial_selected_claim: str,
    initial_quality_claim_page_info: str,
    initial_claim_view: str,
    initial_claim_detail_map: dict,
    initial_review_view: str,
    initial_evidence_items: list[dict],
    initial_claim_evidence_page: int,
    initial_claim_evidence_table_rows: list[list[object]],
    initial_claim_evidence_page_info: str,
    initial_evidence_detail_html: str,
    recent_quality_scope_choices: list[str],
    initial_recent_quality_scope_value: str,
    initial_recent_results_state: list[dict],
    initial_recent_quality_page: int,
    initial_recent_quality_table_rows: list[list[object]],
    initial_recent_quality_page_info: str,
    initial_progress_html: str,
    initial_result_html: str,
    initial_active_quality_check_html: str,
    initial_quality_evaluation_cases: str,
    initial_quality_evaluation_summary: str,
    initial_quality_evaluation_result: dict,
    initial_quality_evaluation_page: int,
    initial_quality_evaluation_table_rows: list[list[object]],
    initial_quality_evaluation_page_info: str,
) -> dict[str, gr.components.Component]:
    """构建 AI 质检页组件，并返回后续事件绑定所需的组件集合。"""

    with gr.Row(elem_id="quality-top-row"):
        with gr.Column(scale=1, elem_id="quality-input-panel"):
            gr.Markdown("### 1. 输入与执行")
            with gr.Row():
                quality_input = gr.Textbox(
                    label="待质检文本",
                    lines=8,
                    placeholder="建议一行或一句输入一个明确说法，系统会拆成多条 Claim 逐条质检。",
                )
            with gr.Row():
                quality_knowledge_base = gr.Dropdown(
                    label="当前知识库",
                    choices=knowledge_base_choices,
                    value=initial_knowledge_base_choice,
                    interactive=True,
                    elem_id="quality-knowledge-base",
                )
                quality_template = gr.Dropdown(
                    label="质检模板",
                    choices=template_choices,
                    value=default_template_choice,
                    interactive=True,
                )
            with gr.Row():
                quality_button = ui_button("开始质检")
                recent_quality_button = ui_button("加载最近质检结果")
        with gr.Column(scale=1):
            quality_help = gr.HTML(value=format_quality_help_html(), elem_id="quality-help-panel")
    with gr.Row(elem_id="quality-template-row"):
        quality_template_detail = gr.HTML(
            value=format_quality_template_html(default_template),
            elem_id="quality-template-panel",
        )
    formatted_quality_result_state = gr.State(initial_formatted_quality_result)
    quality_claim_page_state = gr.State(initial_quality_claim_page)
    quality_evidence_page_state = gr.State(initial_claim_evidence_page)
    recent_quality_page_state = gr.State(initial_recent_quality_page)
    quality_evaluation_page_state = gr.State(initial_quality_evaluation_page)
    with gr.Row(elem_id="quality-summary-row", equal_height=True):
        with gr.Column(scale=1):
            quality_progress = gr.HTML(value=initial_progress_html, elem_id="quality-progress-panel")
        with gr.Column(scale=1):
            quality_result = gr.HTML(value=initial_result_html, elem_id="quality-result-panel")

    selected_claim_state = gr.State(initial_selected_claim)
    claim_detail_state = gr.State(initial_claim_detail_map)
    recent_quality_state = gr.State(initial_recent_results_state)
    evidence_items_state = gr.State(initial_evidence_items)

    with gr.Row(elem_id="quality-claim-row", equal_height=True):
        with gr.Column(scale=1, elem_id="quality-claim-list-panel"):
            gr.Markdown("### 2. Claim 列表")
            quality_active_check = gr.HTML(
                value=initial_active_quality_check_html or format_active_quality_check_html(initial_formatted_quality_result),
                elem_id="quality-active-check",
            )
            quality_claims = gr.Radio(
                choices=initial_quality_claim_choices,
                value=initial_selected_claim_choice,
                interactive=True,
                label="Claim 列表",
                elem_id="quality-claims-table",
            )
            with gr.Row(elem_id="quality-claim-pagination-row"):
                quality_claim_prev_button = ui_button("上一页")
                quality_claim_next_button = ui_button("下一页")
            quality_claim_page_info = gr.HTML(
                value=format_table_pagination_html(initial_quality_claim_page_info),
                elem_id="quality-claim-page-info",
            )
        with gr.Column(scale=1):
            claim_detail_view = gr.HTML(value=initial_claim_view, elem_id="quality-claim-detail")
            quality_review_claim_detail = gr.HTML(value=initial_review_view, visible=False)

    with gr.Column(elem_id="quality-evidence-list-panel"):
        gr.Markdown("### 3. 证据列表")
        claim_evidence_table = gr.Dataframe(
            headers=["序号", "片段 ID", "文档", "定位", "证据关系", "检索来源", "检索路径", "重排分", "证据摘要"],
            datatype=["str"] * 9,
            interactive=False,
            row_count=0,
            column_count=9,
            label="证据列表",
            buttons=[],
            elem_id="quality-evidence-table",
            value=initial_claim_evidence_table_rows,
            max_height=420,
        )
        with gr.Row(elem_id="quality-evidence-pagination-row"):
            quality_evidence_prev_button = ui_button("上一页")
            quality_evidence_next_button = ui_button("下一页")
        quality_evidence_page_info = gr.HTML(
            value=format_table_pagination_html(initial_claim_evidence_page_info),
            elem_id="quality-evidence-page-info",
        )
    claim_evidence_detail = gr.HTML(
        value=initial_evidence_detail_html,
        elem_id="quality-evidence-detail",
    )

    with gr.Column(scale=1, elem_id="quality-history-panel"):
        gr.Markdown("### 4. 历史质检记录")
        recent_quality_note = gr.HTML(
            value=(
                "<div>最近质检记录用于回看历史质检任务。"
                "切换历史记录后，可重新查看当次的 Claim 与证据。</div>"
            ),
            elem_id="quality-history-note",
        )
        recent_quality_scope_filter = gr.Dropdown(
            label="历史任务范围",
            choices=recent_quality_scope_choices,
            value=initial_recent_quality_scope_value,
            interactive=True,
            elem_id="quality-history-scope",
        )
        recent_quality_checks = gr.Dataframe(
            headers=["序号", "质检 ID", "模板", "总体结论", "Claim 数", "待处理 Claim", "时间", "输入摘要"],
            datatype=["str"] * 8,
            interactive=False,
            row_count=TABLE_PAGE_SIZE,
            column_count=8,
            label="最近质检记录",
            buttons=[],
            elem_id="quality-recent-table",
            value=initial_recent_quality_table_rows,
            max_height=420,
        )
        with gr.Row(elem_id="quality-recent-pagination-row"):
            recent_quality_prev_button = ui_button("上一页")
            recent_quality_next_button = ui_button("下一页")
        recent_quality_page_info = gr.HTML(
            value=format_table_pagination_html(initial_recent_quality_page_info),
            elem_id="quality-recent-page-info",
        )

    with gr.Column(scale=1, elem_id="quality-action-panel"):
        gr.Markdown("### 5. 下载结果与动作")
        with gr.Row(elem_id="quality-export-row"):
            quality_export_button = ui_button("下载结果")
        quality_export_result = gr.HTML(
            value=format_operation_result_html(None, title="下载结果"),
            elem_id="quality-export-result",
        )
    with gr.Accordion("效果评测", open=False, elem_id="quality-evaluation-accordion"):
        with gr.Column(scale=1, elem_id="quality-evaluation-panel"):
            quality_evaluation_help = gr.HTML(
                value=format_quality_evaluation_help_html(),
                elem_id="quality-evaluation-help",
            )
            quality_evaluation_cases = gr.Textbox(
                label="效果评测样例 JSON",
                lines=12,
                value=initial_quality_evaluation_cases,
                placeholder="输入 JSON 数组，每项至少包含 input_text，可选 expected_overall_verdict / expected_risk_level / expected_claim_count",
            )
            with gr.Row(elem_id="quality-evaluation-action-row", equal_height=True):
                with gr.Column(scale=1):
                    quality_evaluation_button = ui_button("执行效果评测")
                with gr.Column(scale=1):
                    quality_evaluation_export_button = ui_button("下载评测结果")
                    quality_evaluation_export_result = gr.HTML(
                        value=format_operation_result_html(None, title="下载结果"),
                        elem_id="quality-evaluation-export-result",
                    )
            quality_evaluation_summary = gr.HTML(
                value=initial_quality_evaluation_summary,
                elem_id="quality-evaluation-summary",
            )
            quality_evaluation_result_state = gr.State(initial_quality_evaluation_result)
            quality_evaluation_table = gr.Dataframe(
                headers=[
                    "序号",
                    "样例 ID",
                    "预期结论",
                    "实际结论",
                    "结论命中",
                    "预期风险",
                    "实际风险",
                    "风险命中",
                    "预期 Claim 数",
                    "实际 Claim 数",
                    "Claim 数命中",
                    "宽松命中",
                    "完全命中",
                    "差异说明",
                    "建议排查方向",
                    "输入摘要",
                ],
                datatype=["str"] * 16,
                interactive=False,
                row_count=0,
                column_count=16,
                label="效果评测明细",
                buttons=[],
                elem_id="quality-evaluation-table",
                value=initial_quality_evaluation_table_rows,
            )
            with gr.Row(elem_id="quality-evaluation-pagination-row"):
                quality_evaluation_prev_button = ui_button("上一页")
                quality_evaluation_next_button = ui_button("下一页")
            quality_evaluation_page_info = gr.HTML(
                value=format_table_pagination_html(initial_quality_evaluation_page_info),
                elem_id="quality-evaluation-page-info",
            )

    return {
        "quality_input": quality_input,
        "quality_knowledge_base": quality_knowledge_base,
        "quality_template": quality_template,
        "quality_button": quality_button,
        "recent_quality_button": recent_quality_button,
        "quality_help": quality_help,
        "quality_template_detail": quality_template_detail,
        "formatted_quality_result_state": formatted_quality_result_state,
        "quality_claim_page_state": quality_claim_page_state,
        "quality_evidence_page_state": quality_evidence_page_state,
        "recent_quality_page_state": recent_quality_page_state,
        "quality_evaluation_page_state": quality_evaluation_page_state,
        "quality_progress": quality_progress,
        "quality_result": quality_result,
        "selected_claim_state": selected_claim_state,
        "claim_detail_state": claim_detail_state,
        "recent_quality_state": recent_quality_state,
        "evidence_items_state": evidence_items_state,
        "quality_active_check": quality_active_check,
        "quality_claims": quality_claims,
        "quality_claim_prev_button": quality_claim_prev_button,
        "quality_claim_next_button": quality_claim_next_button,
        "quality_claim_page_info": quality_claim_page_info,
        "claim_detail_view": claim_detail_view,
        "quality_review_claim_detail": quality_review_claim_detail,
        "claim_evidence_table": claim_evidence_table,
        "quality_evidence_prev_button": quality_evidence_prev_button,
        "quality_evidence_next_button": quality_evidence_next_button,
        "quality_evidence_page_info": quality_evidence_page_info,
        "claim_evidence_detail": claim_evidence_detail,
        "recent_quality_note": recent_quality_note,
        "recent_quality_scope_filter": recent_quality_scope_filter,
        "recent_quality_checks": recent_quality_checks,
        "recent_quality_prev_button": recent_quality_prev_button,
        "recent_quality_next_button": recent_quality_next_button,
        "recent_quality_page_info": recent_quality_page_info,
        "quality_export_button": quality_export_button,
        "quality_export_result": quality_export_result,
        "quality_evaluation_help": quality_evaluation_help,
        "quality_evaluation_cases": quality_evaluation_cases,
        "quality_evaluation_button": quality_evaluation_button,
        "quality_evaluation_export_button": quality_evaluation_export_button,
        "quality_evaluation_export_result": quality_evaluation_export_result,
        "quality_evaluation_summary": quality_evaluation_summary,
        "quality_evaluation_result_state": quality_evaluation_result_state,
        "quality_evaluation_table": quality_evaluation_table,
        "quality_evaluation_prev_button": quality_evaluation_prev_button,
        "quality_evaluation_next_button": quality_evaluation_next_button,
        "quality_evaluation_page_info": quality_evaluation_page_info,
    }


def bind_quality_events(
    *,
    components: dict[str, gr.components.Component],
    login_state,
    document_knowledge_base,
    search_knowledge_base,
    review_knowledge_base,
    run_quality_check_ui: Callable,
    render_quality_template: Callable,
    list_recent_quality_results_ui: Callable,
    change_quality_knowledge_base_ui: Callable,
    select_recent_quality_result_ui: Callable,
    select_quality_claim_ui: Callable,
    select_quality_evidence: Callable,
    change_quality_claim_page: Callable,
    change_quality_evidence_page: Callable,
    change_recent_quality_page: Callable,
    export_quality_results: Callable,
    run_quality_evaluation_ui: Callable,
    change_quality_evaluation_page: Callable,
    export_quality_evaluation_results: Callable,
) -> None:
    """绑定 AI 质检页事件，保持对外行为与原实现一致。"""

    quality_input = components["quality_input"]
    quality_knowledge_base = components["quality_knowledge_base"]
    quality_template = components["quality_template"]
    quality_button = components["quality_button"]
    recent_quality_button = components["recent_quality_button"]
    quality_template_detail = components["quality_template_detail"]
    formatted_quality_result_state = components["formatted_quality_result_state"]
    quality_claim_page_state = components["quality_claim_page_state"]
    quality_evidence_page_state = components["quality_evidence_page_state"]
    recent_quality_page_state = components["recent_quality_page_state"]
    quality_evaluation_page_state = components["quality_evaluation_page_state"]
    quality_progress = components["quality_progress"]
    quality_result = components["quality_result"]
    selected_claim_state = components["selected_claim_state"]
    claim_detail_state = components["claim_detail_state"]
    recent_quality_state = components["recent_quality_state"]
    evidence_items_state = components["evidence_items_state"]
    quality_active_check = components["quality_active_check"]
    quality_claims = components["quality_claims"]
    quality_claim_prev_button = components["quality_claim_prev_button"]
    quality_claim_next_button = components["quality_claim_next_button"]
    quality_claim_page_info = components["quality_claim_page_info"]
    claim_detail_view = components["claim_detail_view"]
    quality_review_claim_detail = components["quality_review_claim_detail"]
    claim_evidence_table = components["claim_evidence_table"]
    quality_evidence_prev_button = components["quality_evidence_prev_button"]
    quality_evidence_next_button = components["quality_evidence_next_button"]
    quality_evidence_page_info = components["quality_evidence_page_info"]
    claim_evidence_detail = components["claim_evidence_detail"]
    recent_quality_scope_filter = components["recent_quality_scope_filter"]
    recent_quality_checks = components["recent_quality_checks"]
    recent_quality_prev_button = components["recent_quality_prev_button"]
    recent_quality_next_button = components["recent_quality_next_button"]
    recent_quality_page_info = components["recent_quality_page_info"]
    quality_export_button = components["quality_export_button"]
    quality_export_result = components["quality_export_result"]
    quality_evaluation_cases = components["quality_evaluation_cases"]
    quality_evaluation_button = components["quality_evaluation_button"]
    quality_evaluation_export_button = components["quality_evaluation_export_button"]
    quality_evaluation_export_result = components["quality_evaluation_export_result"]
    quality_evaluation_summary = components["quality_evaluation_summary"]
    quality_evaluation_result_state = components["quality_evaluation_result_state"]
    quality_evaluation_table = components["quality_evaluation_table"]
    quality_evaluation_prev_button = components["quality_evaluation_prev_button"]
    quality_evaluation_next_button = components["quality_evaluation_next_button"]
    quality_evaluation_page_info = components["quality_evaluation_page_info"]

    quality_button.click(
        fn=run_quality_check_ui,
        inputs=[quality_input, quality_template, quality_knowledge_base, login_state],
        outputs=[
            quality_progress,
            quality_result,
            quality_active_check,
            formatted_quality_result_state,
            quality_claims,
            quality_claim_page_state,
            quality_claim_page_info,
            selected_claim_state,
            claim_detail_state,
            claim_detail_view,
            claim_evidence_table,
            quality_evidence_page_state,
            quality_evidence_page_info,
            quality_review_claim_detail,
            evidence_items_state,
            claim_evidence_detail,
            recent_quality_state,
            recent_quality_checks,
            recent_quality_page_state,
            recent_quality_page_info,
            quality_evaluation_cases,
        ],
    )
    quality_template.input(
        fn=render_quality_template,
        inputs=quality_template,
        outputs=quality_template_detail,
        queue=False,
        show_progress="hidden",
    )
    recent_quality_button.click(
        fn=list_recent_quality_results_ui,
        inputs=[quality_knowledge_base, recent_quality_scope_filter, login_state],
        outputs=[
            quality_progress,
            quality_result,
            quality_active_check,
            formatted_quality_result_state,
            quality_claims,
            quality_claim_page_state,
            quality_claim_page_info,
            selected_claim_state,
            claim_detail_state,
            claim_detail_view,
            claim_evidence_table,
            quality_evidence_page_state,
            quality_evidence_page_info,
            quality_review_claim_detail,
            evidence_items_state,
            claim_evidence_detail,
            recent_quality_state,
            recent_quality_checks,
            recent_quality_page_state,
            recent_quality_page_info,
            quality_evaluation_cases,
        ],
    )
    quality_knowledge_base.input(
        fn=change_quality_knowledge_base_ui,
        inputs=[quality_knowledge_base, recent_quality_scope_filter, login_state],
        outputs=[
            document_knowledge_base,
            search_knowledge_base,
            quality_knowledge_base,
            review_knowledge_base,
            quality_progress,
            quality_result,
            quality_active_check,
            formatted_quality_result_state,
            quality_claims,
            quality_claim_page_state,
            quality_claim_page_info,
            selected_claim_state,
            claim_detail_state,
            claim_detail_view,
            claim_evidence_table,
            quality_evidence_page_state,
            quality_evidence_page_info,
            quality_review_claim_detail,
            evidence_items_state,
            claim_evidence_detail,
            recent_quality_state,
            recent_quality_checks,
            recent_quality_page_state,
            recent_quality_page_info,
            quality_evaluation_cases,
        ],
        queue=False,
        show_progress="hidden",
    )
    recent_quality_scope_filter.input(
        fn=list_recent_quality_results_ui,
        inputs=[quality_knowledge_base, recent_quality_scope_filter, login_state],
        outputs=[
            quality_progress,
            quality_result,
            quality_active_check,
            formatted_quality_result_state,
            quality_claims,
            quality_claim_page_state,
            quality_claim_page_info,
            selected_claim_state,
            claim_detail_state,
            claim_detail_view,
            claim_evidence_table,
            quality_evidence_page_state,
            quality_evidence_page_info,
            quality_review_claim_detail,
            evidence_items_state,
            claim_evidence_detail,
            recent_quality_state,
            recent_quality_checks,
            recent_quality_page_state,
            recent_quality_page_info,
            quality_evaluation_cases,
        ],
        queue=False,
        show_progress="hidden",
    )
    recent_quality_checks.select(
        fn=select_recent_quality_result_ui,
        inputs=[recent_quality_checks, recent_quality_state, recent_quality_page_state, quality_knowledge_base, recent_quality_scope_filter, login_state],
        outputs=[
            quality_progress,
            quality_result,
            quality_active_check,
            formatted_quality_result_state,
            quality_claims,
            quality_claim_page_state,
            quality_claim_page_info,
            selected_claim_state,
            claim_detail_state,
            claim_detail_view,
            claim_evidence_table,
            quality_evidence_page_state,
            quality_evidence_page_info,
            quality_review_claim_detail,
            evidence_items_state,
            claim_evidence_detail,
            recent_quality_state,
            recent_quality_checks,
            recent_quality_page_state,
            recent_quality_page_info,
            quality_evaluation_cases,
        ],
        queue=False,
        show_progress="hidden",
    )
    quality_claims.input(
        fn=select_quality_claim_ui,
        inputs=[quality_claims, claim_detail_state, formatted_quality_result_state],
        outputs=[
            claim_detail_view,
            claim_evidence_table,
            quality_evidence_page_state,
            quality_evidence_page_info,
            quality_review_claim_detail,
            selected_claim_state,
            evidence_items_state,
            claim_evidence_detail,
            quality_evaluation_cases,
        ],
        queue=False,
        show_progress="hidden",
    )
    claim_evidence_table.select(
        fn=select_quality_evidence,
        inputs=[evidence_items_state, claim_evidence_table],
        outputs=[claim_evidence_detail],
        queue=False,
        show_progress="hidden",
    )
    quality_claim_prev_button.click(
        fn=lambda formatted, detail_map, page, selected: change_quality_claim_page(formatted, detail_map, page, "prev", selected),
        inputs=[formatted_quality_result_state, claim_detail_state, quality_claim_page_state, selected_claim_state],
        outputs=[
            quality_claims,
            quality_claim_page_state,
            quality_claim_page_info,
            selected_claim_state,
            claim_detail_view,
            claim_evidence_table,
            quality_evidence_page_state,
            quality_evidence_page_info,
            quality_review_claim_detail,
            evidence_items_state,
            claim_evidence_detail,
            quality_evaluation_cases,
        ],
        queue=False,
    )
    quality_claim_next_button.click(
        fn=lambda formatted, detail_map, page, selected: change_quality_claim_page(formatted, detail_map, page, "next", selected),
        inputs=[formatted_quality_result_state, claim_detail_state, quality_claim_page_state, selected_claim_state],
        outputs=[
            quality_claims,
            quality_claim_page_state,
            quality_claim_page_info,
            selected_claim_state,
            claim_detail_view,
            claim_evidence_table,
            quality_evidence_page_state,
            quality_evidence_page_info,
            quality_review_claim_detail,
            evidence_items_state,
            claim_evidence_detail,
            quality_evaluation_cases,
        ],
        queue=False,
    )
    quality_evidence_prev_button.click(
        fn=lambda items, page: change_quality_evidence_page(items, page, "prev"),
        inputs=[evidence_items_state, quality_evidence_page_state],
        outputs=[claim_evidence_table, quality_evidence_page_state, quality_evidence_page_info],
        queue=False,
    )
    quality_evidence_next_button.click(
        fn=lambda items, page: change_quality_evidence_page(items, page, "next"),
        inputs=[evidence_items_state, quality_evidence_page_state],
        outputs=[claim_evidence_table, quality_evidence_page_state, quality_evidence_page_info],
        queue=False,
    )
    recent_quality_prev_button.click(
        fn=lambda page, knowledge_base, scope, results: change_recent_quality_page(page, "prev", knowledge_base, scope, results),
        inputs=[recent_quality_page_state, quality_knowledge_base, recent_quality_scope_filter, recent_quality_state],
        outputs=[recent_quality_checks, recent_quality_page_state, recent_quality_page_info],
        queue=False,
    )
    recent_quality_next_button.click(
        fn=lambda page, knowledge_base, scope, results: change_recent_quality_page(page, "next", knowledge_base, scope, results),
        inputs=[recent_quality_page_state, quality_knowledge_base, recent_quality_scope_filter, recent_quality_state],
        outputs=[recent_quality_checks, recent_quality_page_state, recent_quality_page_info],
        queue=False,
    )
    quality_export_button.click(
        fn=export_quality_results,
        inputs=[formatted_quality_result_state, selected_claim_state, claim_detail_state, evidence_items_state],
        outputs=[quality_export_result],
    )
    quality_evaluation_button.click(
        fn=run_quality_evaluation_ui,
        inputs=[quality_evaluation_cases, quality_template, quality_knowledge_base],
        outputs=[quality_evaluation_summary, quality_evaluation_table, quality_evaluation_result_state, quality_evaluation_page_state, quality_evaluation_page_info],
    )
    quality_evaluation_prev_button.click(
        fn=lambda result, page: change_quality_evaluation_page(result, page, "prev"),
        inputs=[quality_evaluation_result_state, quality_evaluation_page_state],
        outputs=[quality_evaluation_table, quality_evaluation_page_state, quality_evaluation_page_info],
    )
    quality_evaluation_next_button.click(
        fn=lambda result, page: change_quality_evaluation_page(result, page, "next"),
        inputs=[quality_evaluation_result_state, quality_evaluation_page_state],
        outputs=[quality_evaluation_table, quality_evaluation_page_state, quality_evaluation_page_info],
    )
    quality_evaluation_export_button.click(
        fn=export_quality_evaluation_results,
        inputs=[quality_evaluation_result_state],
        outputs=[quality_evaluation_export_result],
    )
