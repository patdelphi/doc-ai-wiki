"""程序说明：提供最小可用的 Gradio 页面，覆盖文档管理、检索、质检与审核。"""

from __future__ import annotations

import gradio as gr

from src.common.errors import AppError
from src.ui.viewmodels import (
    build_claim_evidence_rows,
    build_database_summary_rows,
    build_document_action_updates,
    build_document_management_state,
    build_quality_claim_rows,
    build_recent_claim_navigation,
    build_recent_quality_rows,
    build_review_candidate_rows,
    build_review_history_rows,
    build_search_result_rows,
    build_template_choices,
    format_claim_detail_for_review,
    format_claim_detail_html,
    format_database_summary_html,
    format_document_detail_html,
    format_document_summary_html,
    format_evidence_detail_html,
    format_ingest_result,
    format_operation_result_html,
    format_quality_help_html,
    format_quality_progress_html,
    format_quality_result,
    format_quality_result_html,
    format_quality_template_html,
    format_recent_quality_checks,
    format_review_candidates,
    format_review_help_html,
    format_review_history,
    format_review_record_detail_html,
    format_search_help_html,
    format_search_result_detail_html,
    format_search_results,
    format_search_summary_html,
    get_document_detail,
    get_review_record_detail,
    get_review_target_claim_id,
    normalize_search_query,
    parse_claim_choice,
    parse_document_choice,
    parse_template_choice,
    scan_input_documents,
)


UI_CSS = """
#search-top-row {
  align-items: stretch !important;
}
#search-input-panel,
#search-help-panel {
  height: 100%;
  min-height: 260px;
  align-self: stretch !important;
}
#search-input-panel {
  border: none;
  background: transparent;
  border-radius: 0;
  padding: 0;
  min-height: 260px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  box-sizing: border-box;
}
#search-input-panel > div,
#search-help-panel > div {
  height: 100%;
}
#search-input-panel .gradio-container-3-42-0,
#search-input-panel .gradio-container-4-44-1 {
  background: transparent !important;
}
#search-input-panel button {
  margin-top: auto;
}
#quality-top-row {
  align-items: stretch !important;
}
#quality-top-row > .gradio-column,
#quality-template-row > .gradio-column,
#quality-summary-row > .gradio-column,
#quality-claim-row > .gradio-column,
#quality-evidence-row > .gradio-column,
#quality-history-row > .gradio-column {
  align-self: stretch !important;
}
#quality-input-panel {
  min-height: 260px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  box-sizing: border-box;
}
#quality-help-panel,
#quality-template-panel,
#quality-progress-panel,
#quality-result-panel,
#quality-claim-detail,
#quality-evidence-detail,
#quality-history-panel {
  height: 100%;
}
#quality-help-panel {
  min-height: 260px;
}
#quality-template-row {
  align-items: stretch !important;
}
#quality-template-panel {
  width: 100%;
}
#quality-claim-row,
#quality-evidence-row {
  align-items: stretch !important;
}
#quality-history-row {
  align-items: stretch !important;
}
#quality-template-panel > div,
#quality-help-panel > div,
#quality-progress-panel > div,
#quality-result-panel > div,
#quality-claim-detail > div,
#quality-evidence-detail > div,
#quality-history-panel > div {
  height: 100%;
}
#quality-history-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
#quality-history-note {
  font-size: 13px !important;
  line-height: 1.7 !important;
  color: var(--body-text-color-subdued) !important;
  margin: 0 !important;
}
#quality-input-panel button {
  margin-top: 8px;
}
#quality-claims-table table td,
#quality-recent-table table td,
#quality-evidence-table table td {
  white-space: pre-wrap !important;
  word-break: break-word !important;
  line-height: 1.7 !important;
  vertical-align: top !important;
}
#quality-claims-table button[aria-label="Select column"],
#quality-claims-table button[aria-label="Select row"],
#quality-evidence-table button[aria-label="Select column"],
#quality-evidence-table button[aria-label="Select row"],
#quality-recent-table button[aria-label="Select column"],
#quality-recent-table button[aria-label="Select row"] {
  display: none !important;
}
#quality-claims-table tr:has(td:focus-within) td,
#quality-claims-table tr:has(button:focus) td,
#quality-claims-table tr:has(.selected) td,
#quality-claims-table td.selected,
#quality-evidence-table tr:has(td:focus-within) td,
#quality-evidence-table tr:has(button:focus) td,
#quality-evidence-table tr:has(.selected) td,
#quality-evidence-table td.selected,
#quality-recent-table tr:has(td:focus-within) td,
#quality-recent-table tr:has(button:focus) td,
#quality-recent-table tr:has(.selected) td,
#quality-recent-table td.selected {
  background: rgba(127, 127, 127, 0.16) !important;
}
#quality-claims-table tr:has(td:focus-within) td:first-child,
#quality-claims-table tr:has(button:focus) td:first-child,
#quality-claims-table tr:has(.selected) td:first-child,
#quality-evidence-table tr:has(td:focus-within) td:first-child,
#quality-evidence-table tr:has(button:focus) td:first-child,
#quality-evidence-table tr:has(.selected) td:first-child,
#quality-recent-table tr:has(td:focus-within) td:first-child,
#quality-recent-table tr:has(button:focus) td:first-child,
#quality-recent-table tr:has(.selected) td:first-child {
  box-shadow: inset 5px 0 0 0 rgba(127, 127, 127, 0.62) !important;
}
#quality-claims-table tr:has(td:focus-within) td,
#quality-claims-table tr:has(button:focus) td,
#quality-evidence-table tr:has(td:focus-within) td,
#quality-evidence-table tr:has(button:focus) td,
#quality-recent-table tr:has(td:focus-within) td,
#quality-recent-table tr:has(button:focus) td {
  font-weight: 600 !important;
}
#review-top-row {
  align-items: stretch !important;
}
#review-top-row > .gradio-column,
#review-summary-row > .gradio-column,
#review-action-row > .gradio-column,
#review-record-row > .gradio-column,
#review-evidence-row > .gradio-column {
  align-self: stretch !important;
}
#review-summary-row,
#review-action-row,
#review-record-row,
#review-evidence-row {
  align-items: stretch !important;
}
#review-action-panel {
  min-height: 260px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  box-sizing: border-box;
}
#review-help-panel,
#review-result-panel,
#review-claim-detail,
#review-record-detail,
#review-evidence-detail {
  height: 100%;
}
#review-help-panel > div,
#review-result-panel > div,
#review-claim-detail > div,
#review-record-detail > div,
#review-evidence-detail > div {
  height: 100%;
}
#review-help-panel {
  min-height: 260px;
}
#review-result-panel {
  min-height: 260px;
}
#review-action-panel button {
  margin-top: 8px;
}
#review-pending-table table th,
#review-pending-table table td,
#review-processed-table table th,
#review-processed-table table td,
#review-history-table table th,
#review-history-table table td,
#review-evidence-table table th,
#review-evidence-table table td {
  font-size: 14px !important;
  white-space: pre-wrap !important;
  word-break: break-word !important;
  line-height: 1.7 !important;
  vertical-align: top !important;
}
#review-pending-table table tbody tr,
#review-processed-table table tbody tr,
#review-history-table table tbody tr,
#review-evidence-table table tbody tr {
  transition: background 0.2s ease, box-shadow 0.2s ease;
}
#review-pending-table button[aria-label="Select column"],
#review-pending-table button[aria-label="Select row"],
#review-processed-table button[aria-label="Select column"],
#review-processed-table button[aria-label="Select row"],
#review-history-table button[aria-label="Select column"],
#review-history-table button[aria-label="Select row"],
#review-evidence-table button[aria-label="Select column"],
#review-evidence-table button[aria-label="Select row"] {
  display: none !important;
}
#review-pending-table tr:has(td:focus-within) td,
#review-pending-table tr:has(button:focus) td,
#review-pending-table tr:has(.selected) td,
#review-pending-table td.selected,
#review-processed-table tr:has(td:focus-within) td,
#review-processed-table tr:has(button:focus) td,
#review-processed-table tr:has(.selected) td,
#review-processed-table td.selected,
#review-history-table tr:has(td:focus-within) td,
#review-history-table tr:has(button:focus) td,
#review-history-table tr:has(.selected) td,
#review-history-table td.selected,
#review-evidence-table tr:has(td:focus-within) td,
#review-evidence-table tr:has(button:focus) td,
#review-evidence-table tr:has(.selected) td,
#review-evidence-table td.selected {
  background: rgba(68, 68, 68, 0.22) !important;
  box-shadow: inset 0 1px 0 0 rgba(68, 68, 68, 0.28), inset 0 -1px 0 0 rgba(68, 68, 68, 0.28);
}
#review-pending-table tr:has(td:focus-within) td:first-child,
#review-pending-table tr:has(button:focus) td:first-child,
#review-pending-table tr:has(.selected) td:first-child,
#review-processed-table tr:has(td:focus-within) td:first-child,
#review-processed-table tr:has(button:focus) td:first-child,
#review-processed-table tr:has(.selected) td:first-child,
#review-history-table tr:has(td:focus-within) td:first-child,
#review-history-table tr:has(button:focus) td:first-child,
#review-history-table tr:has(.selected) td:first-child,
#review-evidence-table tr:has(td:focus-within) td:first-child,
#review-evidence-table tr:has(button:focus) td:first-child,
#review-evidence-table tr:has(.selected) td:first-child {
  box-shadow: inset 6px 0 0 0 rgba(68, 68, 68, 0.72) !important;
}
#review-pending-table tr:has(td:focus-within) td,
#review-pending-table tr:has(button:focus) td,
#review-processed-table tr:has(td:focus-within) td,
#review-processed-table tr:has(button:focus) td,
#review-history-table tr:has(td:focus-within) td,
#review-history-table tr:has(button:focus) td,
#review-evidence-table tr:has(td:focus-within) td,
#review-evidence-table tr:has(button:focus) td {
  font-weight: 700 !important;
}
#review-claim-detail,
#review-record-detail,
#review-evidence-detail,
#review-result-panel {
  font-size: 14px !important;
}
#search-results-table table th,
#search-results-table table td {
  font-size: 14px !important;
  white-space: pre-wrap !important;
  word-break: break-word !important;
  line-height: 1.7 !important;
  vertical-align: top !important;
}
#search-results-table button[aria-label="Select column"],
#search-results-table button[aria-label="Select row"] {
  display: none !important;
}
#search-results-table .search-result-cell-selected {
  display: block;
  margin: -8px -10px;
  padding: 8px 10px;
  background: rgba(68, 68, 68, 0.22) !important;
  border-top: 1px solid rgba(68, 68, 68, 0.45);
  border-bottom: 1px solid rgba(68, 68, 68, 0.45);
  font-weight: 600;
}
#search-results-table .search-result-cell-selected-first {
  border-left: 5px solid rgba(68, 68, 68, 0.72);
  padding-left: 12px;
}
#search-results-table tr:has(td:focus-within) td,
#search-results-table tr:has(button:focus) td,
#search-results-table tr:has(.selected) td,
#search-results-table td.selected {
  background: rgba(127, 127, 127, 0.14) !important;
}
#search-results-table tr:has(td:focus-within) td:first-child,
#search-results-table tr:has(button:focus) td:first-child,
#search-results-table tr:has(.selected) td:first-child {
  box-shadow: inset 3px 0 0 0 rgba(127, 127, 127, 0.45) !important;
}
#search-results-table mark,
#search-result-detail mark {
  background: rgba(245, 158, 11, 0.20);
  color: #b45309;
  font-weight: 700;
  padding: 0 3px;
  border-radius: 4px;
  border: 1px solid rgba(245, 158, 11, 0.32);
}
#search-result-detail,
#search-result-summary {
  font-size: 14px !important;
}
"""


def build_ui(*, ingest_service, retrieval_service, quality_service, review_service) -> gr.Blocks:
    """构建最小可用界面。"""

    template_items = quality_service.list_templates()
    template_choices = build_template_choices(template_items)
    default_template_choice = template_choices[0] if template_choices else None
    default_template = quality_service.get_template(parse_template_choice(default_template_choice)) if default_template_choice else None

    def get_document_management_state(selected_choice: str | None = None) -> dict:
        """统一构建文档管理页的当前视图状态。"""

        documents = scan_input_documents(ingest_service.settings.input_root)
        status_items, _ = ingest_service.list_status(doc_uid=None, status=None, page=1, page_size=50)
        database_summary = ingest_service.get_database_summary()
        state = build_document_management_state(documents, status_items)
        active_choice = selected_choice if selected_choice in state["document_choices"] else state["default_choice"]
        selected_detail = get_document_detail(active_choice, state["document_detail_map"])
        register_button_state, rebuild_button_state = build_document_action_updates(selected_detail)
        return {
            "scan_summary": state["scan_summary"],
            "database_summary": database_summary,
            "table_rows": state["table_rows"],
            "document_choices": state["document_choices"],
            "active_choice": active_choice,
            "selected_detail": selected_detail,
            "register_interactive": register_button_state["interactive"],
            "rebuild_interactive": rebuild_button_state["interactive"],
        }

    def build_document_page_outputs(state: dict) -> tuple[str, str, list[list[str]], gr.Dropdown, str, list[list[str]], gr.Button, gr.Button]:
        """将文档管理状态转换为页面组件输出。"""

        return (
            format_document_summary_html(state["scan_summary"]),
            format_database_summary_html(state["database_summary"]),
            build_database_summary_rows(state["database_summary"]),
            state["table_rows"],
            gr.Dropdown(choices=state["document_choices"], value=state["active_choice"]),
            format_document_detail_html(state["selected_detail"]),
            gr.Button(interactive=state["register_interactive"]),
            gr.Button(interactive=state["rebuild_interactive"]),
        )

    def load_document_management_state() -> tuple[str, str, list[list[str]], gr.Dropdown, str, list[list[str]], gr.Button, gr.Button]:
        return build_document_page_outputs(get_document_management_state())

    def refresh_document_management_state(
        selected_choice: str | None = None,
    ) -> tuple[str, str, list[list[str]], gr.Dropdown, str, list[list[str]], gr.Button, gr.Button]:
        return build_document_page_outputs(get_document_management_state(selected_choice))

    def inspect_document(choice: str) -> tuple[str, gr.Button, gr.Button]:
        state = get_document_management_state(choice)
        return (
            format_document_detail_html(state["selected_detail"]),
            gr.Button(interactive=state["register_interactive"]),
            gr.Button(interactive=state["rebuild_interactive"]),
        )

    def register_selected_document(
        choice: str,
        progress=gr.Progress(track_tqdm=False),
    ) -> tuple[str, str, str, list[list[str]], gr.Dropdown, str, list[list[str]], gr.Button, gr.Button]:
        file_path = parse_document_choice(choice)
        if not file_path:
            summary, database_summary, database_rows, table_rows, dropdown, detail, register_state, rebuild_state = refresh_document_management_state(choice)
            return (
                format_operation_result_html({"success": False, "message": "请选择文档"}, title="注册结果"),
                summary,
                database_summary,
                database_rows,
                table_rows,
                dropdown,
                detail,
                register_state,
                rebuild_state,
            )
            
        progress(0, desc="准备执行当前文档注册")
        try:
            job = ingest_service.register_document(
                {"file_path": file_path},
                rebuild_if_exists=False,
                progress_callback=lambda info: progress(
                    info["percent"] / 100,
                    desc=f'{info["message"]}（{info["percent"]}%）',
                ),
            )
            payload = format_ingest_result({"success": True, "job": job}, job.get("progress_events", []))
        except AppError as exc:
            payload = {"success": False, "message": exc.message, "error_code": exc.error_code, "details": exc.details}

        summary, database_summary, database_rows, table_rows, dropdown, detail, register_state, rebuild_state = refresh_document_management_state(choice)
        return (
            format_operation_result_html(payload, title="注册结果"),
                summary,
                database_summary,
                database_rows,
                table_rows,
                dropdown,
                detail,
                register_state,
                rebuild_state,
            )

    def register_all_documents(
        progress=gr.Progress(track_tqdm=False),
    ) -> tuple[str, str, str, list[list[str]], gr.Dropdown, str, list[list[str]], gr.Button, gr.Button]:
        documents = scan_input_documents(ingest_service.settings.input_root)
        if not documents:
            summary, database_summary, database_rows, table_rows, dropdown, detail, register_state, rebuild_state = refresh_document_management_state()
            return (
                format_operation_result_html({"success": False, "message": "Input 目录下没有可注册文档"}, title="批量注册结果"),
                summary,
                database_summary,
                database_rows,
                table_rows,
                dropdown,
                detail,
                register_state,
                rebuild_state,
            )

        progress(0, desc="准备批量注册文档")
        try:
            jobs = ingest_service.register_documents(
                [{"file_path": item["file_path"]} for item in documents],
                rebuild_if_exists=False,
                progress_callback=lambda info: progress(
                    info["overall_percent"] / 100,
                    desc=(
                        f'第 {info["current_document"]}/{info["total_documents"]} 篇：'
                        f'{info["message"]}（总进度 {info["overall_percent"]}%）'
                    ),
                ),
            )
            merged_progress: list[dict] = []
            for job in jobs:
                merged_progress.extend(job.get("progress_events", []))
            payload = format_ingest_result({"success": True, "jobs": jobs}, merged_progress)
        except AppError as exc:
            payload = {"success": False, "message": exc.message, "error_code": exc.error_code, "details": exc.details}

        summary, database_summary, database_rows, table_rows, dropdown, detail, register_state, rebuild_state = refresh_document_management_state()
        return (
            format_operation_result_html(payload, title="批量注册结果"),
            summary,
            database_summary,
            database_rows,
            table_rows,
            dropdown,
            detail,
            register_state,
            rebuild_state,
        )

    def query_ingest_status() -> tuple[str, str, list[list[str]], gr.Dropdown, str, list[list[str]], gr.Button, gr.Button]:
        return refresh_document_management_state()

    def rebuild_selected_document(
        choice: str,
        progress=gr.Progress(track_tqdm=False),
    ) -> tuple[str, str, str, list[list[str]], gr.Dropdown, str, list[list[str]], gr.Button, gr.Button]:
        current_state = get_document_management_state(choice)
        doc_uid = current_state["selected_detail"].get("doc_uid")
        if not doc_uid:
            summary, database_summary, database_rows, table_rows, dropdown, current_detail, register_state, rebuild_state = refresh_document_management_state(choice)
            return (
                format_operation_result_html({"success": False, "message": "当前文档尚未入库，无法重建"}, title="重建结果"),
                summary,
                database_summary,
                database_rows,
                table_rows,
                dropdown,
                current_detail,
                register_state,
                rebuild_state,
            )

        progress(0, desc="准备执行索引重建")
        try:
            accepted = ingest_service.rebuild_documents(
                [doc_uid],
                rebuild_fulltext=True,
                rebuild_vector=True,
                progress_callback=lambda info: progress(
                    info["overall_percent"] / 100,
                    desc=f'{info["message"]}（{info["overall_percent"]}%）',
                ),
            )
            payload = {"success": True, "accepted": accepted}
        except AppError as exc:
            payload = {"success": False, "message": exc.message, "error_code": exc.error_code, "details": exc.details}

        summary, database_summary, database_rows, table_rows, dropdown, current_detail, register_state, rebuild_state = refresh_document_management_state(choice)
        return (
            format_operation_result_html(payload, title="重建结果"),
            summary,
            database_summary,
            database_rows,
            table_rows,
            dropdown,
            current_detail,
            register_state,
            rebuild_state,
        )

    def build_search_detail(search_row: dict | None, query_text: str) -> str:
        """根据检索结果行构建原文详情。"""

        if not search_row:
            return format_search_result_detail_html(None, query_text=query_text)
        detail = retrieval_service.get_chunk_detail(search_row.get("chunk_id", "")) or {}
        return format_search_result_detail_html({**search_row, **detail}, query_text=query_text)

    def run_search(query: str, top_k: int) -> tuple[str, list[list[str]], list[dict], str, str]:
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
            )
        try:
            items = retrieval_service.hybrid_search(normalized_query, top_k=top_k, use_rerank=True)
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
            )
        formatted = format_search_results(items, query_text=normalized_query)
        detail_html = build_search_detail(formatted["table"][0], normalized_query) if formatted["table"] else format_search_result_detail_html(None, query_text=normalized_query)
        return (
            format_search_summary_html(formatted),
            build_search_result_rows(formatted, selected_row_index=0 if formatted["table"] else None),
            formatted["table"],
            normalized_query,
            detail_html,
        )

    def select_search_result(search_rows: list[dict], query_text: str, evt: gr.SelectData) -> tuple[str, list[list[str]]]:
        """点击检索结果表格后展示对应原文。"""

        if not search_rows:
            return format_search_result_detail_html(None, query_text=query_text), []
        index = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        try:
            row_index = int(index)
        except (TypeError, ValueError):
            return format_search_result_detail_html(None, query_text=query_text), build_search_result_rows({"table": search_rows})
        if row_index < 0 or row_index >= len(search_rows):
            return format_search_result_detail_html(None, query_text=query_text), build_search_result_rows({"table": search_rows})
        return (
            build_search_detail(search_rows[row_index], query_text),
            build_search_result_rows({"table": search_rows}, selected_row_index=row_index),
        )

    def render_claim_views(claim_choice: str, claim_detail_map: dict | None) -> tuple[str, list[list[str]], str, list[dict], str]:
        """统一渲染 Claim 摘要与证据表。"""

        detail = format_claim_detail_for_review(claim_choice, claim_detail_map)
        detail_html = format_claim_detail_html(detail)
        evidence_items = detail.get("evidence_table") or []
        evidence_detail_html = format_evidence_detail_html(evidence_items[0] if evidence_items else None)
        return detail_html, build_claim_evidence_rows(detail), detail_html, evidence_items, evidence_detail_html

    def select_quality_claim(
        claim_rows: list[list[str]],
        claim_detail_map: dict | None,
        evt: gr.SelectData,
    ) -> tuple[str, list[list[str]], str, str, list[dict], str]:
        """点击 Claim 列表后联动详情与证据区域。"""

        normalized_rows = claim_rows.values.tolist() if hasattr(claim_rows, "values") else claim_rows
        if not normalized_rows:
            claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views("", claim_detail_map)
            return claim_view, evidence_rows, review_view, "", evidence_items, evidence_detail_html
        index = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        try:
            row_index = int(index)
        except (TypeError, ValueError):
            claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views("", claim_detail_map)
            return claim_view, evidence_rows, review_view, "", evidence_items, evidence_detail_html
        if row_index < 0 or row_index >= len(normalized_rows):
            claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views("", claim_detail_map)
            return claim_view, evidence_rows, review_view, "", evidence_items, evidence_detail_html
        selected_claim_id = str(normalized_rows[row_index][0]) if normalized_rows[row_index] else ""
        claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(selected_claim_id, claim_detail_map)
        return claim_view, evidence_rows, review_view, selected_claim_id, evidence_items, evidence_detail_html

    def select_quality_evidence(
        evidence_items: list[dict] | None,
        evt: gr.SelectData,
    ) -> str:
        """点击证据列表后联动证据详情。"""

        items = evidence_items or []
        if not items:
            return format_evidence_detail_html(None)
        index = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        try:
            row_index = int(index)
        except (TypeError, ValueError):
            return format_evidence_detail_html(None)
        if row_index < 0 or row_index >= len(items):
            return format_evidence_detail_html(None)
        return format_evidence_detail_html(items[row_index])

    def render_quality_template(template_choice: str) -> str:
        """根据当前模板选择展示模板内容。"""

        try:
            template = quality_service.get_template(parse_template_choice(template_choice))
        except AppError as exc:
            return format_operation_result_html(
                {"success": False, "message": exc.message, "error_code": exc.error_code},
                title="模板内容",
            )
        return format_quality_template_html(template)

    def build_quality_outputs(
        *,
        progress_html: str,
        result_html: str,
        claim_rows: list[list[str]] | None = None,
        selected_claim: str | None = None,
        claim_detail_map: dict | None = None,
        claim_view: str | None = None,
        evidence_rows: list[list[str]] | None = None,
        review_view: str | None = None,
        evidence_items: list[dict] | None = None,
        evidence_detail_html: str | None = None,
        recent_results: list[dict] | None = None,
        recent_rows: list[list[str]] | None = None,
    ) -> tuple[str, str, list[list[str]], str, dict, str, list[list[str]], str, list[dict], str, list[dict], list[list[str]]]:
        """统一构建 AI 质检页输出。"""

        empty_claim_view, empty_evidence_rows, empty_review_view, empty_evidence_items, empty_evidence_detail_html = render_claim_views("", {})
        return (
            progress_html,
            result_html,
            claim_rows or [],
            selected_claim or "",
            claim_detail_map or {},
            claim_view or empty_claim_view,
            evidence_rows or empty_evidence_rows,
            review_view or empty_review_view,
            evidence_items or empty_evidence_items,
            evidence_detail_html or empty_evidence_detail_html,
            recent_results or [],
            recent_rows or [],
        )

    def build_recent_quality_view_outputs(
        recent_results: list[dict] | None,
        *,
        selected_index: int = 0,
        preferred_claim_id: str | None = None,
    ) -> tuple[str, str, list[list[str]], str, dict, str, list[list[str]], str, list[dict], str, list[dict], list[list[str]]]:
        """根据最近质检记录构建当前页面展示状态。"""

        results = recent_results or []
        recent_payload = format_recent_quality_checks(results)
        recent_rows = build_recent_quality_rows(recent_payload)
        if not results:
            return build_quality_outputs(
                progress_html=format_quality_progress_html(None),
                result_html=format_quality_result_html(None),
                recent_results=[],
                recent_rows=[],
            )

        normalized_index = selected_index if 0 <= selected_index < len(results) else 0
        selected_result = results[normalized_index]
        selected_formatted = format_quality_result(
            {
                "check": selected_result,
                "claims": selected_result.get("claims", []),
                "rule_hits": [],
            }
        )
        navigation = build_recent_claim_navigation([selected_result], preferred_claim_id=preferred_claim_id)
        claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(
            navigation["selected_choice"],
            navigation["claim_detail_map"],
        )
        progress_html = format_quality_progress_html(
            {
                "status": "success",
                "stage": "loaded",
                "message": "已加载历史质检记录。",
                "claim_index": len(selected_result.get("claims", [])),
                "claim_total": len(selected_result.get("claims", [])),
                "template_name": selected_result.get("template_name"),
                "model_status": "历史记录",
            }
        )
        return build_quality_outputs(
            progress_html=progress_html,
            result_html=format_quality_result_html(selected_formatted),
            claim_rows=build_quality_claim_rows(selected_formatted),
            selected_claim=navigation["selected_choice"],
            claim_detail_map=navigation["claim_detail_map"],
            claim_view=claim_view,
            evidence_rows=evidence_rows,
            review_view=review_view,
            evidence_items=evidence_items,
            evidence_detail_html=evidence_detail_html,
            recent_results=results,
            recent_rows=recent_rows,
        )

    def run_quality_check(
        input_text: str,
        template_choice: str,
    ):
        selected_template_id = parse_template_choice(template_choice)
        initial_result_html = format_quality_result_html(None)
        try:
            for event in quality_service.run_check_stream(
                input_text,
                template_id=selected_template_id,
            ):
                if event.get("type") == "progress":
                    yield build_quality_outputs(
                        progress_html=format_quality_progress_html(event),
                        result_html=initial_result_html,
                    )
                    continue

                result = event.get("result", {})
                formatted = format_quality_result(result)
                recent_results = [
                    {
                        "check_id": formatted["check"].get("check_id"),
                        "template_name": formatted["check"].get("template_name"),
                        "created_at": formatted["check"].get("created_at"),
                        "overall_verdict": formatted["check"].get("overall_verdict"),
                        "input_text": input_text,
                        "claims": formatted["claims"],
                    }
                ]
                navigation = build_recent_claim_navigation(recent_results)
                claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(navigation["selected_choice"], navigation["claim_detail_map"])
                yield build_quality_outputs(
                    progress_html=format_quality_progress_html(event),
                    result_html=format_quality_result_html(formatted),
                    claim_rows=build_quality_claim_rows(formatted),
                    selected_claim=navigation["selected_choice"],
                    claim_detail_map=navigation["claim_detail_map"],
                    claim_view=claim_view,
                    evidence_rows=evidence_rows,
                    review_view=review_view,
                    evidence_items=evidence_items,
                    evidence_detail_html=evidence_detail_html,
                    recent_results=recent_results,
                    recent_rows=build_recent_quality_rows(recent_results),
                )
                return
        except AppError as exc:
            yield build_quality_outputs(
                progress_html=format_quality_progress_html(
                    {"status": "error", "stage": "persist", "message": exc.message, "model_status": "-"},
                ),
                result_html=format_operation_result_html(
                    {"success": False, "message": exc.message, "error_code": exc.error_code},
                    title="质检结果",
                ),
            )
            return

    review_action_choices = ["通过", "不通过", "更新结论"]
    review_scope_choices = ["全部记录", "仅待处理", "仅已处理"]
    review_risk_choices = ["全部风险", "仅高风险", "仅中风险", "仅低风险"]
    review_candidate_fetch_limit = 200

    def normalize_review_action_value(action_value: str) -> str:
        """将中文审核动作转换为内部值。"""

        mapping = {
            "通过": "approved",
            "不通过": "rejected",
            "更新结论": "updated",
            "approved": "approved",
            "rejected": "rejected",
            "updated": "updated",
        }
        return mapping.get(str(action_value or "").strip(), "approved")

    def display_review_action_value(action_value: str) -> str:
        """将内部审核动作转换为中文值。"""

        mapping = {
            "approved": "通过",
            "rejected": "不通过",
            "updated": "更新结论",
        }
        return mapping.get(str(action_value or "").strip().lower(), "通过")

    def find_latest_review_for_claim(review_items: list[dict], claim_id: str) -> dict | None:
        """从审核历史中找到指定 Claim 最近的一条审核记录。"""

        return next((item for item in (review_items or []) if str(item.get("claim_id") or "") == claim_id), None)

    def normalize_review_scope_value(scope_value: str | None) -> str:
        """规范人工审核范围筛选值。"""

        value = str(scope_value or "").strip()
        return value if value in review_scope_choices else review_scope_choices[0]

    def normalize_review_risk_value(risk_value: str | None) -> str:
        """规范人工审核风险筛选值。"""

        value = str(risk_value or "").strip()
        return value if value in review_risk_choices else review_risk_choices[0]

    def filter_review_candidates(
        review_candidates: list[dict] | None,
        *,
        scope_value: str,
        risk_value: str,
    ) -> list[dict]:
        """按范围与风险等级过滤可审核 Claim。"""

        normalized_scope = normalize_review_scope_value(scope_value)
        normalized_risk = normalize_review_risk_value(risk_value)
        risk_mapping = {
            "仅高风险": "high",
            "仅中风险": "medium",
            "仅低风险": "low",
        }
        filtered_items: list[dict] = []
        for item in review_candidates or []:
            review_status = str(item.get("review_status") or "pending").lower()
            if normalized_scope == "仅待处理" and review_status != "pending":
                continue
            if normalized_scope == "仅已处理" and review_status == "pending":
                continue
            expected_risk = risk_mapping.get(normalized_risk)
            if expected_risk and str(item.get("risk_level") or "").lower() != expected_risk:
                continue
            filtered_items.append(item)
        return filtered_items

    def split_review_candidates(review_candidates: list[dict] | None) -> tuple[list[dict], list[dict]]:
        """将可审核 Claim 分为待处理和已处理两组。"""

        pending_items: list[dict] = []
        processed_items: list[dict] = []
        for item in review_candidates or []:
            if str(item.get("review_status") or "pending").lower() == "pending":
                pending_items.append(item)
            else:
                processed_items.append(item)
        return pending_items, processed_items

    def build_review_workspace_outputs(
        review_candidates: list[dict] | None,
        review_items: list[dict] | None,
        *,
        selected_claim_id: str | None = None,
        preferred_review_id: str | None = None,
        review_action_value: str | None = None,
        review_note_value: str | None = None,
        scope_value: str | None = None,
        risk_value: str | None = None,
    ) -> tuple[list[list[str]], list[list[str]], list[dict], str, dict, str, list[list[str]], list[dict], str, str, str, list[list[str]], list[dict], str, str]:
        """构建人工审核页主工作区输出。"""

        normalized_scope = normalize_review_scope_value(scope_value)
        normalized_risk = normalize_review_risk_value(risk_value)
        filtered_candidates = filter_review_candidates(
            review_candidates,
            scope_value=normalized_scope,
            risk_value=normalized_risk,
        )
        pending_candidates, processed_candidates = split_review_candidates(filtered_candidates)
        pending_rows = build_review_candidate_rows(format_review_candidates(pending_candidates))
        processed_rows = build_review_candidate_rows(format_review_candidates(processed_candidates))
        # 状态里保留全量候选集，避免切换筛选条件时只能基于上一次筛选结果继续过滤。
        candidate_items = list(review_candidates or [])
        normalized_claim_id = str(selected_claim_id or "")
        formatted_candidates = format_review_candidates(filtered_candidates)
        claim_detail_map = formatted_candidates.get("claim_detail_map", {})
        if normalized_claim_id not in claim_detail_map and formatted_candidates.get("items"):
            normalized_claim_id = str(formatted_candidates["items"][0].get("claim_id") or "")
        claim_view, evidence_rows, _unused_review_view, evidence_items, evidence_detail_html = render_claim_views(
            normalized_claim_id,
            claim_detail_map,
        )

        formatted_history = format_review_history(review_items or [])
        review_rows = build_review_history_rows(formatted_history)
        selected_review_record: dict | None = None
        if preferred_review_id:
            selected_review_record = next(
                (item for item in formatted_history["items"] if item.get("review_id") == preferred_review_id),
                None,
            )
        if selected_review_record is None and normalized_claim_id:
            selected_review_record = find_latest_review_for_claim(formatted_history["items"], normalized_claim_id)
        if selected_review_record is None and not normalized_claim_id and formatted_history["items"]:
            selected_review_record = formatted_history["items"][0]

        resolved_action_value = review_action_value
        resolved_note_value = review_note_value
        if resolved_action_value is None:
            resolved_action_value = (
                display_review_action_value(str(selected_review_record.get("review_action") or ""))
                if selected_review_record
                else review_action_choices[0]
            )
        if resolved_note_value is None:
            resolved_note_value = str(selected_review_record.get("review_note") or "") if selected_review_record else ""

        return (
            pending_rows,
            processed_rows,
            candidate_items,
            normalized_claim_id,
            claim_detail_map,
            claim_view,
            evidence_rows,
            evidence_items,
            evidence_detail_html,
            resolved_action_value or review_action_choices[0],
            resolved_note_value or "",
            review_rows,
            formatted_history["items"],
            str(selected_review_record.get("review_id") or "") if selected_review_record else "",
            format_review_record_detail_html(selected_review_record),
        )

    def list_review_workspace(
        scope_value: str,
        risk_value: str,
        selected_claim_id: str,
    ) -> tuple[list[list[str]], list[list[str]], list[dict], str, dict, str, list[list[str]], list[dict], str, str, str, list[list[str]], list[dict], str, str]:
        """读取人工审核页所需的待审核列表与审核历史。"""

        try:
            review_candidates = review_service.list_review_candidates(limit=review_candidate_fetch_limit)
            review_items, _ = review_service.list_reviews(page=1, page_size=20)
        except AppError:
            return build_review_workspace_outputs([], [], scope_value=scope_value, risk_value=risk_value)
        return build_review_workspace_outputs(
            review_candidates,
            review_items,
            selected_claim_id=selected_claim_id,
            scope_value=scope_value,
            risk_value=risk_value,
        )

    def change_review_filters(
        review_candidates: list[dict],
        review_items: list[dict],
        selected_claim_id: str,
        scope_value: str,
        risk_value: str,
    ) -> tuple[list[list[str]], list[list[str]], str, dict, str, list[list[str]], list[dict], str, str, str, str, str]:
        """切换筛选条件后刷新待处理/已处理列表与详情。"""

        outputs = build_review_workspace_outputs(
            review_candidates,
            review_items,
            selected_claim_id=selected_claim_id,
            scope_value=scope_value,
            risk_value=risk_value,
        )
        return outputs[0], outputs[1], outputs[3], outputs[4], outputs[5], outputs[6], outputs[7], outputs[8], outputs[9], outputs[10], outputs[13], outputs[14]

    def select_review_candidate(
        candidate_rows: list[list[str]],
        review_candidates: list[dict],
        review_items: list[dict],
        evt: gr.SelectData,
        scope_value: str,
        risk_value: str,
    ) -> tuple[str, dict, str, list[list[str]], list[dict], str, str, str, str, str]:
        """点击可审核记录后联动 Claim、证据和审核输入区。"""

        normalized_rows = candidate_rows.values.tolist() if hasattr(candidate_rows, "values") else candidate_rows
        if not normalized_rows:
            empty_outputs = build_review_workspace_outputs(
                review_candidates,
                review_items,
                scope_value=scope_value,
                risk_value=risk_value,
            )
            return empty_outputs[3], empty_outputs[4], empty_outputs[5], empty_outputs[6], empty_outputs[7], empty_outputs[8], empty_outputs[9], empty_outputs[10], empty_outputs[13], empty_outputs[14]
        index = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        try:
            row_index = int(index)
        except (TypeError, ValueError):
            row_index = 0
        if row_index < 0 or row_index >= len(normalized_rows):
            row_index = 0
        selected_claim_id = str(normalized_rows[row_index][0]) if normalized_rows[row_index] else ""
        outputs = build_review_workspace_outputs(
            review_candidates,
            review_items,
            selected_claim_id=selected_claim_id,
            scope_value=scope_value,
            risk_value=risk_value,
        )
        return outputs[3], outputs[4], outputs[5], outputs[6], outputs[7], outputs[8], outputs[9], outputs[10], outputs[13], outputs[14]

    def select_review_history_record(
        review_items: list[dict],
        review_candidates: list[dict],
        evt: gr.SelectData,
        scope_value: str,
        risk_value: str,
    ) -> tuple[str, dict, str, list[list[str]], list[dict], str, str, str, str, str]:
        """点击已审核记录后回放对应 Claim、证据与审核结论。"""

        items = review_items or []
        if not items:
            empty_outputs = build_review_workspace_outputs(
                review_candidates,
                [],
                scope_value=scope_value,
                risk_value=risk_value,
            )
            return empty_outputs[3], empty_outputs[4], empty_outputs[5], empty_outputs[6], empty_outputs[7], empty_outputs[8], empty_outputs[9], empty_outputs[10], empty_outputs[13], empty_outputs[14]
        index = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        try:
            row_index = int(index)
        except (TypeError, ValueError):
            row_index = 0
        if row_index < 0 or row_index >= len(items):
            row_index = 0
        selected_record = items[row_index]
        outputs = build_review_workspace_outputs(
            review_candidates,
            review_items,
            selected_claim_id=str(selected_record.get("claim_id") or ""),
            preferred_review_id=str(selected_record.get("review_id") or ""),
            scope_value=scope_value,
            risk_value=risk_value,
        )
        return outputs[3], outputs[4], outputs[5], outputs[6], outputs[7], outputs[8], outputs[9], outputs[10], outputs[13], outputs[14]

    def submit_review_action(
        claim_choice: str,
        review_action: str,
        review_note: str,
        scope_value: str,
        risk_value: str,
    ) -> tuple[str, list[list[str]], list[list[str]], list[dict], str, dict, str, list[list[str]], list[dict], str, str, str, list[list[str]], list[dict], str, str]:
        claim_id = parse_claim_choice(claim_choice)
        if not claim_id:
            empty_outputs = build_review_workspace_outputs([], [], scope_value=scope_value, risk_value=risk_value)
            return (
                format_operation_result_html({"success": False, "message": "请先选择要审核的记录"}, title="审核结果"),
                *empty_outputs,
            )
        try:
            result = review_service.submit_review(
                claim_id=claim_id,
                review_action=normalize_review_action_value(review_action),
                reviewed_verdict=None,
                review_note=review_note,
                reviewer="ui_user",
            )
            review_candidates = review_service.list_review_candidates(limit=review_candidate_fetch_limit)
            review_items, _ = review_service.list_reviews(page=1, page_size=20)
        except AppError as exc:
            try:
                current_candidates = review_service.list_review_candidates(limit=review_candidate_fetch_limit)
            except AppError:
                current_candidates = []
            try:
                current_review_items, _ = review_service.list_reviews(page=1, page_size=20)
            except AppError:
                current_review_items = []
            current_outputs = build_review_workspace_outputs(
                current_candidates,
                current_review_items,
                selected_claim_id=claim_id,
                review_action_value=review_action,
                review_note_value=review_note,
                scope_value=scope_value,
                risk_value=risk_value,
            )
            return (
                format_operation_result_html(
                    {"success": False, "message": exc.message, "error_code": exc.error_code},
                    title="审核结果",
                ),
                *current_outputs,
            )

        current_outputs = build_review_workspace_outputs(
            review_candidates,
            review_items,
            selected_claim_id=claim_id,
            preferred_review_id=result["review_id"],
            review_action_value=display_review_action_value(result["review_action"]),
            review_note_value=str(result.get("review_note") or ""),
            scope_value=scope_value,
            risk_value=risk_value,
        )
        return (
            format_operation_result_html(
                {
                    "success": True,
                    "message": "审核记录已保存，待审核列表与历史记录已刷新。",
                    **result,
                    "linked_claim_id": claim_id,
                    "review_action": display_review_action_value(result["review_action"]),
                },
                title="审核结果",
            ),
            *current_outputs,
        )

    def list_recent_quality_results() -> tuple[str, str, list[list[str]], str, dict, str, list[list[str]], str, list[dict], str, list[dict], list[list[str]]]:
        try:
            results = quality_service.list_recent_results(limit=10)
        except AppError:
            return build_quality_outputs(
                progress_html=format_quality_progress_html(None),
                result_html=format_quality_result_html(None),
                recent_results=[],
                recent_rows=[],
            )
        return build_recent_quality_view_outputs(results, selected_index=0)

    def select_recent_quality_result(
        recent_results: list[dict],
        evt: gr.SelectData,
    ) -> tuple[str, str, list[list[str]], str, dict, str, list[list[str]], str, list[dict], str]:
        """点击最近质检记录后回放对应结果。"""

        results = recent_results or []
        if not results:
            empty_outputs = build_recent_quality_view_outputs([])
            return empty_outputs[:10]
        index = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        try:
            row_index = int(index)
        except (TypeError, ValueError):
            row_index = 0
        selected_outputs = build_recent_quality_view_outputs(results, selected_index=row_index)
        return selected_outputs[:10]

    initial_document_state = get_document_management_state()
    initial_document_summary = format_document_summary_html(initial_document_state["scan_summary"])
    initial_database_summary = format_database_summary_html(initial_document_state["database_summary"])
    initial_database_rows = build_database_summary_rows(initial_document_state["database_summary"])
    initial_document_detail = format_document_detail_html(initial_document_state["selected_detail"])
    try:
        initial_recent_results = quality_service.list_recent_results(limit=10)
    except AppError:
        initial_recent_results = []
    (
        initial_progress_html,
        initial_result_html,
        initial_claim_rows,
        initial_selected_claim,
        initial_claim_detail_map,
        initial_claim_view,
        initial_evidence_rows,
        initial_review_view,
        initial_evidence_items,
        initial_evidence_detail_html,
        _initial_recent_results_state,
        initial_recent_rows,
    ) = build_recent_quality_view_outputs(initial_recent_results, selected_index=0)
    try:
        initial_review_candidates = review_service.list_review_candidates(limit=review_candidate_fetch_limit)
    except AppError:
        initial_review_candidates = []
    try:
        initial_review_items, _ = review_service.list_reviews(page=1, page_size=20)
    except AppError:
        initial_review_items = []
    (
        initial_review_pending_rows,
        initial_review_processed_rows,
        initial_review_candidate_items_state,
        initial_review_selected_claim_id,
        initial_review_claim_detail_map,
        initial_review_claim_view,
        initial_review_evidence_rows,
        initial_review_evidence_items,
        initial_review_evidence_detail_html,
        initial_review_action_value,
        initial_review_note_value,
        initial_review_rows,
        initial_review_items_state,
        initial_selected_review_id,
        initial_review_record_detail_html,
    ) = build_review_workspace_outputs(initial_review_candidates, initial_review_items)

    with gr.Blocks(title="中文知识库系统") as demo:
        gr.Markdown("# 中文知识库系统 MVP")

        with gr.Tabs():
            with gr.Tab("文档管理"):
                gr.Markdown(
                    """
### 功能说明
- 左侧用于查看和选择当前 `"Input"` 目录中的文档，并自动展示是否已入库、是否需要重建。
- 右侧用于执行注册、批量注册、重建索引，并实时查看当前步骤、完成数量和进度摘要。
                    """
                )
                scan_button = gr.Button("刷新文档列表")
                with gr.Row():
                    with gr.Column(scale=1):
                        document_summary = gr.HTML(value=initial_document_summary)
                    with gr.Column(scale=1):
                        database_summary = gr.HTML(value=initial_database_summary)
                with gr.Row():
                    with gr.Column(scale=1):
                        database_summary_table = gr.Dataframe(
                            headers=["指标", "数量"],
                            datatype=["str", "str"],
                            interactive=False,
                            row_count=0,
                            column_count=2,
                            label="数据库统计",
                            value=initial_database_rows,
                        )
                    with gr.Column(scale=1):
                        document_choices = gr.Dropdown(
                            label="当前选中文档",
                            choices=initial_document_state["document_choices"],
                            value=initial_document_state["active_choice"],
                            interactive=True,
                        )
                        document_detail = gr.HTML(value=initial_document_detail)
                document_table = gr.Dataframe(
                    headers=["文件名", "文档名称", "大小", "入库时间", "已注册", "索引状态", "需重建", "推荐动作", "错误信息"],
                    datatype=["str"] * 9,
                    interactive=False,
                    row_count=0,
                    column_count=9,
                    label="现有文档列表",
                    value=initial_document_state["table_rows"],
                )
                with gr.Row():
                    with gr.Column(scale=1):
                        register_button = gr.Button("注册当前文档", interactive=initial_document_state["register_interactive"])
                        register_all_button = gr.Button("注册全部待处理文档")
                    with gr.Column(scale=1):
                        rebuild_button = gr.Button("重建当前文档索引", interactive=initial_document_state["rebuild_interactive"])
                        status_button = gr.Button("刷新状态")
                with gr.Row():
                    with gr.Column(scale=1):
                        register_result = gr.HTML(value=format_operation_result_html(None, title="注册结果"))
                    with gr.Column(scale=1):
                        rebuild_result = gr.HTML(value=format_operation_result_html(None, title="重建结果"))

            with gr.Tab("文档检索"):
                with gr.Row(elem_id="search-top-row", equal_height=True):
                    with gr.Column(scale=5):
                        with gr.Group(elem_id="search-input-panel"):
                            search_query = gr.Textbox(
                                label="检索内容",
                                lines=3,
                                placeholder="可输入关键词、短语、整句，或多组关键词（建议用空格、逗号分隔）",
                            )
                            search_top_k = gr.Slider(label="返回数量", minimum=1, maximum=100, step=1, value=10)
                            search_button = gr.Button("执行检索")
                    with gr.Column(scale=4):
                        search_help = gr.HTML(value=format_search_help_html(), elem_id="search-help-panel")
                search_result_summary = gr.HTML(value=format_search_summary_html(None), elem_id="search-result-summary")
                search_result_state = gr.State([])
                search_query_state = gr.State("")
                search_result = gr.Dataframe(
                    headers=["序号", "文档名称", "定位", "片段 ID", "检索来源", "相关度", "重排分", "匹配来源", "内容摘要"],
                    datatype=["markdown"] * 9,
                    interactive=False,
                    row_count=0,
                    column_count=9,
                    label="检索结果列表",
                    elem_id="search-results-table",
                )
                search_result_detail = gr.HTML(value=format_search_result_detail_html(None), elem_id="search-result-detail")

            with gr.Tab("AI 质检"):
                with gr.Row(elem_id="quality-top-row"):
                    with gr.Column(scale=5):
                        with gr.Group(elem_id="quality-input-panel"):
                            quality_input = gr.Textbox(
                                label="待质检文本",
                                lines=8,
                                placeholder="建议一行或一句输入一个明确说法，系统会拆成多条 Claim 逐条质检。",
                            )
                            quality_template = gr.Dropdown(
                                label="质检模板",
                                choices=template_choices,
                                value=default_template_choice,
                                interactive=True,
                            )
                            quality_button = gr.Button("开始质检")
                            recent_quality_button = gr.Button("加载最近质检结果")
                    with gr.Column(scale=4):
                        quality_help = gr.HTML(value=format_quality_help_html(), elem_id="quality-help-panel")
                with gr.Row(elem_id="quality-template-row"):
                    quality_template_detail = gr.HTML(
                        value=format_quality_template_html(default_template),
                        elem_id="quality-template-panel",
                    )
                with gr.Row(elem_id="quality-summary-row", equal_height=True):
                    with gr.Column(scale=1):
                        quality_progress = gr.HTML(value=initial_progress_html, elem_id="quality-progress-panel")
                    with gr.Column(scale=1):
                        quality_result = gr.HTML(value=initial_result_html, elem_id="quality-result-panel")
                with gr.Row(elem_id="quality-claim-row", equal_height=True):
                    with gr.Column(scale=5):
                        quality_claims = gr.Dataframe(
                            headers=["Claim ID", "Claim 内容", "当前判定", "风险等级", "置信度", "来源文档", "来源位置"],
                            datatype=["str"] * 7,
                            interactive=False,
                            row_count=0,
                            column_count=7,
                            label="Claim 列表",
                            elem_id="quality-claims-table",
                            value=initial_claim_rows,
                        )
                    with gr.Column(scale=4):
                        selected_claim_state = gr.State(initial_selected_claim)
                        claim_detail_state = gr.State(initial_claim_detail_map)
                        recent_quality_state = gr.State(_initial_recent_results_state)
                        evidence_items_state = gr.State(initial_evidence_items)
                        claim_detail_view = gr.HTML(value=initial_claim_view, elem_id="quality-claim-detail")
                        quality_review_claim_detail = gr.HTML(value=initial_review_view, visible=False)
                with gr.Row(elem_id="quality-evidence-row", equal_height=True):
                    with gr.Column(scale=5):
                        claim_evidence_table = gr.Dataframe(
                            headers=["片段 ID", "文档", "定位", "检索来源", "匹配来源", "重排分", "证据摘要"],
                            datatype=["str"] * 7,
                            interactive=False,
                            row_count=0,
                            column_count=7,
                            label="证据列表",
                            elem_id="quality-evidence-table",
                            value=initial_evidence_rows,
                        )
                    with gr.Column(scale=4):
                        claim_evidence_detail = gr.HTML(
                            value=initial_evidence_detail_html,
                            elem_id="quality-evidence-detail",
                        )
                with gr.Row(elem_id="quality-history-row", equal_height=True):
                    with gr.Column(scale=1):
                        with gr.Group(elem_id="quality-history-panel"):
                            recent_quality_note = gr.HTML(
                                value=(
                                    "<div>最近质检记录用于回看历史质检任务。"
                                    "切换历史记录后，可重新查看当次的 Claim 与证据。</div>"
                                ),
                                elem_id="quality-history-note",
                            )
                            recent_quality_checks = gr.Dataframe(
                                headers=["质检 ID", "模板", "总体结论", "Claim 数", "时间", "输入摘要"],
                                datatype=["str"] * 6,
                                interactive=False,
                                row_count=0,
                                column_count=6,
                                label="最近质检记录",
                                elem_id="quality-recent-table",
                                value=initial_recent_rows,
                            )

            with gr.Tab("人工审核"):
                review_candidate_state = gr.State(initial_review_candidate_items_state)
                review_history_state = gr.State(initial_review_items_state)
                review_selected_record_state = gr.State(initial_selected_review_id)
                review_selected_claim_state = gr.State(initial_review_selected_claim_id)
                review_claim_detail_state = gr.State(initial_review_claim_detail_map)
                review_evidence_items_state = gr.State(initial_review_evidence_items)
                with gr.Row(elem_id="review-top-row", equal_height=True):
                    with gr.Column(scale=5):
                        with gr.Row():
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
                        review_pending_candidates = gr.Dataframe(
                            headers=["Claim ID", "Claim 摘要", "当前判定", "风险等级", "审核状态", "来源文档", "质检模板", "质检时间"],
                            datatype=["str"] * 8,
                            interactive=False,
                            row_count=0,
                            column_count=8,
                            label="待处理记录",
                            elem_id="review-pending-table",
                            value=initial_review_pending_rows,
                        )
                        review_processed_candidates = gr.Dataframe(
                            headers=["Claim ID", "Claim 摘要", "当前判定", "风险等级", "审核状态", "来源文档", "质检模板", "质检时间"],
                            datatype=["str"] * 8,
                            interactive=False,
                            row_count=0,
                            column_count=8,
                            label="已处理 Claim",
                            elem_id="review-processed-table",
                            value=initial_review_processed_rows,
                        )
                    with gr.Column(scale=4):
                        review_help = gr.HTML(value=format_review_help_html(), elem_id="review-help-panel")
                with gr.Row(elem_id="review-summary-row", equal_height=True):
                    with gr.Column(scale=5):
                        review_claim_detail_panel = gr.HTML(value=initial_review_claim_view, elem_id="review-claim-detail")
                    with gr.Column(scale=4):
                        review_evidence_detail = gr.HTML(
                            value=initial_review_evidence_detail_html,
                            elem_id="review-evidence-detail",
                        )
                with gr.Row(elem_id="review-evidence-row", equal_height=True):
                    with gr.Column(scale=5):
                        review_evidence_table = gr.Dataframe(
                            headers=["片段 ID", "文档", "定位", "检索来源", "匹配来源", "重排分", "证据摘要"],
                            datatype=["str"] * 7,
                            interactive=False,
                            row_count=0,
                            column_count=7,
                            label="关联证据列表",
                            elem_id="review-evidence-table",
                            value=initial_review_evidence_rows,
                        )
                    with gr.Column(scale=4):
                        with gr.Group(elem_id="review-action-panel"):
                            review_action_input = gr.Dropdown(
                                choices=review_action_choices,
                                value=initial_review_action_value,
                                label="审核动作",
                                interactive=True,
                            )
                            review_note_input = gr.Textbox(label="审核备注", lines=4, value=initial_review_note_value)
                            review_button = gr.Button("提交审核")
                            review_history_button = gr.Button("刷新审核列表")
                            review_result = gr.HTML(
                                value=format_operation_result_html(None, title="审核结果"),
                                elem_id="review-result-panel",
                            )
                with gr.Row(elem_id="review-record-row", equal_height=True):
                    with gr.Column(scale=5):
                        review_history = gr.Dataframe(
                            headers=["审核 ID", "Claim ID", "审核动作", "审核状态", "审核人", "审核时间", "审核备注", "Claim 摘要"],
                            datatype=["str"] * 8,
                            interactive=False,
                            row_count=0,
                            column_count=8,
                            label="已审核记录",
                            elem_id="review-history-table",
                            value=initial_review_rows,
                        )
                    with gr.Column(scale=4):
                        review_record_detail = gr.HTML(
                            value=initial_review_record_detail_html,
                            elem_id="review-record-detail",
                        )

        scan_button.click(
            fn=load_document_management_state,
            outputs=[
                document_summary,
                database_summary,
                database_summary_table,
                document_table,
                document_choices,
                document_detail,
                register_button,
                rebuild_button,
            ],
        )
        document_choices.change(
            fn=inspect_document,
            inputs=document_choices,
            outputs=[document_detail, register_button, rebuild_button],
        )
        register_button.click(
            fn=register_selected_document,
            inputs=document_choices,
            outputs=[
                register_result,
                document_summary,
                database_summary,
                database_summary_table,
                document_table,
                document_choices,
                document_detail,
                register_button,
                rebuild_button,
            ],
        )
        register_all_button.click(
            fn=register_all_documents,
            outputs=[
                register_result,
                document_summary,
                database_summary,
                database_summary_table,
                document_table,
                document_choices,
                document_detail,
                register_button,
                rebuild_button,
            ],
        )
        status_button.click(
            fn=query_ingest_status,
            outputs=[
                document_summary,
                database_summary,
                database_summary_table,
                document_table,
                document_choices,
                document_detail,
                register_button,
                rebuild_button,
            ],
        )
        rebuild_button.click(
            fn=rebuild_selected_document,
            inputs=document_choices,
            outputs=[
                rebuild_result,
                document_summary,
                database_summary,
                database_summary_table,
                document_table,
                document_choices,
                document_detail,
                register_button,
                rebuild_button,
            ],
        )
        search_button.click(
            fn=run_search,
            inputs=[search_query, search_top_k],
            outputs=[search_result_summary, search_result, search_result_state, search_query_state, search_result_detail],
        )
        search_result.select(
            fn=select_search_result,
            inputs=[search_result_state, search_query_state],
            outputs=[search_result_detail, search_result],
        )
        quality_button.click(
            fn=run_quality_check,
            inputs=[quality_input, quality_template],
            outputs=[
                quality_progress,
                quality_result,
                quality_claims,
                selected_claim_state,
                claim_detail_state,
                claim_detail_view,
                claim_evidence_table,
                quality_review_claim_detail,
                evidence_items_state,
                claim_evidence_detail,
                recent_quality_state,
                recent_quality_checks,
            ],
        )
        quality_template.change(
            fn=render_quality_template,
            inputs=quality_template,
            outputs=quality_template_detail,
        )
        recent_quality_button.click(
            fn=list_recent_quality_results,
            outputs=[
                quality_progress,
                quality_result,
                quality_claims,
                selected_claim_state,
                claim_detail_state,
                claim_detail_view,
                claim_evidence_table,
                quality_review_claim_detail,
                evidence_items_state,
                claim_evidence_detail,
                recent_quality_checks,
                recent_quality_state,
            ],
        )
        recent_quality_checks.select(
            fn=select_recent_quality_result,
            inputs=[recent_quality_state],
            outputs=[
                quality_progress,
                quality_result,
                quality_claims,
                selected_claim_state,
                claim_detail_state,
                claim_detail_view,
                claim_evidence_table,
                quality_review_claim_detail,
                evidence_items_state,
                claim_evidence_detail,
            ],
        )
        quality_claims.select(
            fn=select_quality_claim,
            inputs=[quality_claims, claim_detail_state],
            outputs=[claim_detail_view, claim_evidence_table, quality_review_claim_detail, selected_claim_state, evidence_items_state, claim_evidence_detail],
        )
        claim_evidence_table.select(
            fn=select_quality_evidence,
            inputs=[evidence_items_state],
            outputs=[claim_evidence_detail],
        )
        review_history_button.click(
            fn=list_review_workspace,
            inputs=[review_scope_filter, review_risk_filter, review_selected_claim_state],
            outputs=[
                review_pending_candidates,
                review_processed_candidates,
                review_candidate_state,
                review_selected_claim_state,
                review_claim_detail_state,
                review_claim_detail_panel,
                review_evidence_table,
                review_evidence_items_state,
                review_evidence_detail,
                review_action_input,
                review_note_input,
                review_history,
                review_history_state,
                review_selected_record_state,
                review_record_detail,
            ],
        )
        review_scope_filter.change(
            fn=list_review_workspace,
            inputs=[review_scope_filter, review_risk_filter, review_selected_claim_state],
            outputs=[
                review_pending_candidates,
                review_processed_candidates,
                review_candidate_state,
                review_selected_claim_state,
                review_claim_detail_state,
                review_claim_detail_panel,
                review_evidence_table,
                review_evidence_items_state,
                review_evidence_detail,
                review_action_input,
                review_note_input,
                review_history,
                review_history_state,
                review_selected_record_state,
                review_record_detail,
            ],
        )
        review_risk_filter.change(
            fn=list_review_workspace,
            inputs=[review_scope_filter, review_risk_filter, review_selected_claim_state],
            outputs=[
                review_pending_candidates,
                review_processed_candidates,
                review_candidate_state,
                review_selected_claim_state,
                review_claim_detail_state,
                review_claim_detail_panel,
                review_evidence_table,
                review_evidence_items_state,
                review_evidence_detail,
                review_action_input,
                review_note_input,
                review_history,
                review_history_state,
                review_selected_record_state,
                review_record_detail,
            ],
        )
        review_pending_candidates.select(
            fn=select_review_candidate,
            inputs=[review_pending_candidates, review_candidate_state, review_history_state, review_scope_filter, review_risk_filter],
            outputs=[
                review_selected_claim_state,
                review_claim_detail_state,
                review_claim_detail_panel,
                review_evidence_table,
                review_evidence_items_state,
                review_evidence_detail,
                review_action_input,
                review_note_input,
                review_selected_record_state,
                review_record_detail,
            ],
        )
        review_processed_candidates.select(
            fn=select_review_candidate,
            inputs=[review_processed_candidates, review_candidate_state, review_history_state, review_scope_filter, review_risk_filter],
            outputs=[
                review_selected_claim_state,
                review_claim_detail_state,
                review_claim_detail_panel,
                review_evidence_table,
                review_evidence_items_state,
                review_evidence_detail,
                review_action_input,
                review_note_input,
                review_selected_record_state,
                review_record_detail,
            ],
        )
        review_history.select(
            fn=select_review_history_record,
            inputs=[review_history_state, review_candidate_state, review_scope_filter, review_risk_filter],
            outputs=[
                review_selected_claim_state,
                review_claim_detail_state,
                review_claim_detail_panel,
                review_evidence_table,
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
            inputs=[review_evidence_items_state],
            outputs=[review_evidence_detail],
        )
        review_button.click(
            fn=submit_review_action,
            inputs=[review_selected_claim_state, review_action_input, review_note_input, review_scope_filter, review_risk_filter],
            outputs=[
                review_result,
                review_pending_candidates,
                review_processed_candidates,
                review_candidate_state,
                review_selected_claim_state,
                review_claim_detail_state,
                review_claim_detail_panel,
                review_evidence_table,
                review_evidence_items_state,
                review_evidence_detail,
                review_action_input,
                review_note_input,
                review_history,
                review_history_state,
                review_selected_record_state,
                review_record_detail,
            ],
        )
    return demo
