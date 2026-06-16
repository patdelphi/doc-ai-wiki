"""程序说明：承载 AI 质检优化 Dummy 页签的静态展示结构。"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import gradio as gr

from src.ui.page_helpers import ui_button


def build_quality_dummy_tab(
    *,
    claim_choices: Sequence[str],
    evidence_rows: Sequence[Sequence[str]],
    history_rows: Sequence[Sequence[str]],
    build_top_help_html: Callable[[], str],
    build_template_html: Callable[[], str],
    build_progress_html: Callable[[], str],
    build_result_html: Callable[[], str],
    build_active_check_html: Callable[[], str],
    build_focus_html: Callable[[], str],
    build_evidence_detail_html: Callable[[], str],
    build_export_result_html: Callable[[], str],
    build_actions_html: Callable[[], str],
    build_evaluation_help_html: Callable[[], str],
    build_evaluation_summary_html: Callable[[], str],
    build_evaluation_rows: Callable[[], list[list[str]]],
    build_help_html: Callable[[], str],
) -> None:
    """构建 AI 质检优化 Dummy 页签，用于承接静态布局演示。"""

    with gr.Tab("AI 质检优化 Dummy", visible=False):
        with gr.Row(elem_id="quality-dummy-row-1", equal_height=True):
            with gr.Column(scale=1, elem_id="quality-dummy-intake-panel"):
                gr.Markdown("### 1. 输入与执行")
                gr.Textbox(
                    label="待质检文本",
                    value="阿胶可以直接替代所有补血药，并且《神农本草经》明确记载它可以延年不老。",
                    lines=8,
                )
                with gr.Row():
                    gr.Dropdown(
                        label="目标知识库",
                        choices=["default（默认）", "古籍专题库", "人工校审库"],
                        value="古籍专题库",
                        interactive=True,
                        elem_id="quality-dummy-knowledge-base",
                    )
                    gr.Dropdown(
                        label="质检模板",
                        choices=["general_fact_check", "classical_claim_review", "risk_first_screening"],
                        value="classical_claim_review",
                        interactive=True,
                        elem_id="quality-dummy-template",
                    )
                gr.Radio(
                    label="工作模式",
                    choices=["快速初筛", "证据优先", "人工复核优先"],
                    value="证据优先",
                    elem_id="quality-dummy-mode",
                )
                with gr.Row():
                    ui_button("开始模拟质检", variant="primary")
                    ui_button("导出模拟结果")
            with gr.Column(scale=1, elem_id="quality-dummy-help-panel"):
                gr.HTML(
                    value=build_top_help_html(),
                    elem_id="quality-dummy-help-card",
                )
        with gr.Row(elem_id="quality-dummy-template-row"):
            gr.HTML(
                value=build_template_html(),
                elem_id="quality-dummy-template-panel",
            )
        with gr.Row(elem_id="quality-dummy-summary-row", equal_height=True):
            with gr.Column(scale=1, elem_id="quality-dummy-progress-panel"):
                gr.HTML(
                    value=build_progress_html(),
                    elem_id="quality-dummy-progress-card",
                )
            with gr.Column(scale=1, elem_id="quality-dummy-result-panel"):
                gr.HTML(
                    value=build_result_html(),
                    elem_id="quality-dummy-status-panel",
                )
        gr.HTML(
            value=(
                "<div class='quality-dummy-note'>"
                "Claim 详情会展示本次判断的证据关系。证据列表会进一步区分支持、矛盾、证据不足，"
                "并显示该证据来自原句检索还是放宽逻辑约束后的补充检索。"
                "</div>"
            ),
            elem_id="quality-dummy-relation-note",
        )
        with gr.Row(elem_id="quality-dummy-row-2", equal_height=True):
            with gr.Column(scale=1, elem_id="quality-dummy-claim-list-panel"):
                gr.Markdown("### 2. Claim 列表")
                gr.HTML(
                    value=build_active_check_html(),
                    elem_id="quality-dummy-active-check",
                )
                gr.Radio(
                    label="Claim 列表",
                    choices=list(claim_choices),
                    value=claim_choices[0],
                    elem_id="quality-dummy-claims",
                )
                with gr.Row(elem_id="quality-dummy-claim-pagination-row"):
                    ui_button("上一页")
                    ui_button("下一页")
                gr.HTML(
                    value="<div class='quality-dummy-note'>第 1 / 1 页，共 4 条 Claim</div>",
                    elem_id="quality-dummy-claim-page-info",
                )
            with gr.Column(scale=1):
                gr.HTML(
                    value=build_focus_html(),
                    elem_id="quality-dummy-focus-panel",
                )
        with gr.Row(elem_id="quality-dummy-row-3", equal_height=True):
            with gr.Column(scale=1, elem_id="quality-dummy-evidence-panel"):
                gr.Markdown("### 3. 证据列表")
                gr.Dataframe(
                    headers=["序号", "片段 ID", "文档", "定位", "证据关系", "检索来源", "检索路径", "重排分", "证据摘要"],
                    datatype=["str"] * 9,
                    interactive=False,
                    row_count=3,
                    column_count=9,
                    label="证据列表",
                    elem_id="quality-dummy-evidence-table",
                    value=[list(row) for row in evidence_rows],
                    max_height=420,
                )
                with gr.Row(elem_id="quality-dummy-evidence-pagination-row"):
                    ui_button("上一页")
                    ui_button("下一页")
                gr.HTML(
                    value="<div class='quality-dummy-note'>第 1 / 1 页，共 3 条证据</div>",
                    elem_id="quality-dummy-evidence-page-info",
                )
            with gr.Column(scale=1):
                gr.HTML(
                    value=build_evidence_detail_html(),
                    elem_id="quality-dummy-evidence-detail",
                )
        with gr.Row(elem_id="quality-dummy-row-4", equal_height=True):
            with gr.Column(scale=1, elem_id="quality-dummy-history-panel"):
                gr.Markdown("### 4. 历史质检记录")
                gr.HTML(
                    value=(
                        "<div class='quality-dummy-note'>"
                        "最近质检记录用于回看历史质检任务。切换历史记录后，可重新查看当次的 Claim 与证据。"
                        "</div>"
                    ),
                    elem_id="quality-dummy-history-note",
                )
                gr.Dropdown(
                    label="历史任务范围",
                    choices=["全部历史任务", "仅当前知识库", "仅高风险任务"],
                    value="全部历史任务",
                    interactive=True,
                    elem_id="quality-dummy-history-scope",
                )
                gr.Dataframe(
                    headers=["质检 ID", "模板", "总体结论", "Claim 数", "待处理 Claim", "时间", "输入摘要"],
                    datatype=["str"] * 7,
                    interactive=False,
                    row_count=3,
                    column_count=7,
                    label="最近质检记录",
                    elem_id="quality-dummy-history-table",
                    value=[list(row) for row in history_rows],
                    max_height=420,
                )
                with gr.Row(elem_id="quality-dummy-history-pagination-row"):
                    ui_button("上一页")
                    ui_button("下一页")
                gr.HTML(
                    value="<div class='quality-dummy-note'>第 1 / 1 页，共 3 条记录</div>",
                    elem_id="quality-dummy-history-page-info",
                )
            with gr.Column(scale=1, elem_id="quality-dummy-action-panel"):
                gr.Markdown("### 5. 下载结果与动作")
                with gr.Row(elem_id="quality-dummy-export-row"):
                    ui_button("下载结果")
                gr.HTML(
                    value=build_export_result_html(),
                    elem_id="quality-dummy-export-result",
                )
                gr.HTML(
                    value=build_actions_html(),
                    elem_id="quality-dummy-actions-result",
                )
        with gr.Accordion("效果评测", open=False, elem_id="quality-dummy-evaluation-accordion"):
            with gr.Column(scale=1, elem_id="quality-dummy-evaluation-panel"):
                gr.HTML(
                    value=build_evaluation_help_html(),
                    elem_id="quality-dummy-evaluation-help",
                )
                gr.Textbox(
                    label="效果评测样例 JSON",
                    lines=8,
                    value='[{"sample_id":"case-001","input_text":"阿胶可以直接替代所有补血药"}]',
                    interactive=False,
                    elem_id="quality-dummy-evaluation-cases",
                )
                with gr.Row(elem_id="quality-dummy-evaluation-action-row", equal_height=True):
                    with gr.Column(scale=1):
                        ui_button("执行效果评测")
                    with gr.Column(scale=1):
                        ui_button("下载评测结果")
                        gr.HTML(
                            value=build_export_result_html(),
                            elem_id="quality-dummy-evaluation-export-result",
                        )
                gr.HTML(
                    value=build_evaluation_summary_html(),
                    elem_id="quality-dummy-evaluation-summary",
                )
                gr.Dataframe(
                    headers=[
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
                    datatype=["str"] * 15,
                    interactive=False,
                    row_count=2,
                    column_count=15,
                    label="效果评测明细",
                    elem_id="quality-dummy-evaluation-table",
                    value=build_evaluation_rows(),
                )
        with gr.Row(elem_id="quality-dummy-bottom-row", equal_height=True):
            with gr.Column(scale=1):
                gr.HTML(
                    value=build_help_html(),
                    elem_id="quality-dummy-detail-help",
                )
