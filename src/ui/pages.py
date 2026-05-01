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
    format_review_history,
    format_search_help_html,
    format_search_result_detail_html,
    format_search_results,
    format_search_summary_html,
    get_document_detail,
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

    def list_review_history() -> tuple[list[list[str]], gr.Dropdown, dict]:
        try:
            review_items, _ = review_service.list_reviews(page=1, page_size=20)
        except AppError:
            return [], gr.Dropdown(choices=[], value=None), {}
        formatted = format_review_history(review_items)
        default_choice = formatted["review_choices"][0] if formatted["review_choices"] else None
        return (
            build_review_history_rows(formatted),
            gr.Dropdown(choices=formatted["review_choices"], value=default_choice),
            formatted["review_map"],
        )

    def submit_review_action(
        claim_choice: str,
        review_action: str,
        review_note: str,
    ) -> tuple[str, list[list[str]], gr.Dropdown, dict, list[list[str]], list[dict], str, dict, str, list[list[str]], str, list[dict], str]:
        claim_id = parse_claim_choice(claim_choice)
        try:
            result = review_service.submit_review(
                claim_id=claim_id,
                review_action=review_action,
                reviewed_verdict=None,
                review_note=review_note,
                reviewer="ui_user",
            )
            review_items, _ = review_service.list_reviews(page=1, page_size=20)
            recent_results = quality_service.list_recent_results(limit=10)
        except AppError as exc:
            claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(claim_choice, {})
            return (
                format_operation_result_html(
                    {"success": False, "message": exc.message, "error_code": exc.error_code},
                    title="审核结果",
                ),
                [],
                gr.Dropdown(choices=[], value=None),
                {},
                [],
                [],
                "",
                {},
                claim_view,
                evidence_rows,
                review_view,
                evidence_items,
                evidence_detail_html,
            )

        review_history_payload = format_review_history(review_items)
        recent_quality_payload = format_recent_quality_checks(recent_results)
        navigation = build_recent_claim_navigation(recent_results, preferred_claim_id=claim_id)
        claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(navigation["selected_choice"], navigation["claim_detail_map"])
        return (
            format_operation_result_html(
                {
                    **result,
                    "linked_claim_id": claim_id,
                    "linked_check_id": navigation["selected_detail"].get("summary", {}).get("check_id"),
                },
                title="审核结果",
            ),
            build_review_history_rows(review_history_payload),
            gr.Dropdown(
                choices=review_history_payload["review_choices"],
                value=review_history_payload["review_choices"][0] if review_history_payload["review_choices"] else None,
            ),
            review_history_payload["review_map"],
            build_recent_quality_rows(recent_quality_payload),
            recent_results,
            navigation["selected_choice"] or "",
            navigation["claim_detail_map"],
            claim_view,
            evidence_rows,
            review_view,
            evidence_items,
            evidence_detail_html,
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

    def focus_review_record(
        review_choice: str,
        review_history_state: dict,
        recent_quality_state: list[dict],
    ) -> tuple[str, dict, str, list[list[str]], str, list[dict], str]:
        claim_id = get_review_target_claim_id(review_choice, review_history_state)
        navigation = build_recent_claim_navigation(recent_quality_state, preferred_claim_id=claim_id)
        claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(navigation["selected_choice"], navigation["claim_detail_map"])
        return (
            navigation["selected_choice"] or "",
            navigation["claim_detail_map"],
            claim_view,
            evidence_rows,
            review_view,
            evidence_items,
            evidence_detail_html,
        )

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
                with gr.Row():
                    with gr.Column(scale=4):
                        review_action_input = gr.Dropdown(
                            choices=["approved", "rejected", "updated"],
                            value="approved",
                            label="审核动作",
                        )
                        review_note_input = gr.Textbox(label="审核备注", lines=3)
                        review_button = gr.Button("提交审核")
                        review_history_button = gr.Button("加载最近审核记录")
                        review_history_selector = gr.Dropdown(label="最近审核定位", choices=[], interactive=True)
                        review_history_state = gr.State({})
                    with gr.Column(scale=5):
                        review_claim_detail = gr.HTML(value=format_claim_detail_html(None))
                        review_result = gr.HTML(value=format_operation_result_html(None, title="审核结果"))
                review_history = gr.Dataframe(
                    headers=["审核 ID", "Claim ID", "审核动作", "审核状态", "审核人", "审核时间", "审核备注", "Claim 摘要"],
                    datatype=["str"] * 8,
                    interactive=False,
                    row_count=0,
                    column_count=8,
                    label="最近审核记录",
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
                review_claim_detail,
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
                review_claim_detail,
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
                review_claim_detail,
                evidence_items_state,
                claim_evidence_detail,
            ],
        )
        quality_claims.select(
            fn=select_quality_claim,
            inputs=[quality_claims, claim_detail_state],
            outputs=[claim_detail_view, claim_evidence_table, review_claim_detail, selected_claim_state, evidence_items_state, claim_evidence_detail],
        )
        claim_evidence_table.select(
            fn=select_quality_evidence,
            inputs=[evidence_items_state],
            outputs=[claim_evidence_detail],
        )
        review_history_button.click(
            fn=list_review_history,
            outputs=[review_history, review_history_selector, review_history_state],
        )
        review_history_selector.change(
            fn=focus_review_record,
            inputs=[review_history_selector, review_history_state, recent_quality_state],
            outputs=[selected_claim_state, claim_detail_state, claim_detail_view, claim_evidence_table, review_claim_detail, evidence_items_state, claim_evidence_detail],
        )
        review_button.click(
            fn=submit_review_action,
            inputs=[selected_claim_state, review_action_input, review_note_input],
            outputs=[
                review_result,
                review_history,
                review_history_selector,
                review_history_state,
                recent_quality_checks,
                recent_quality_state,
                selected_claim_state,
                claim_detail_state,
                claim_detail_view,
                claim_evidence_table,
                review_claim_detail,
                evidence_items_state,
                claim_evidence_detail,
            ],
        )
    return demo
