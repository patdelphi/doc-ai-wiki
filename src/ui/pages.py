"""程序说明：提供最小可用的 Gradio 页面，覆盖文档管理、检索、质检与审核。"""

from __future__ import annotations

import gradio as gr

from src.ui.viewmodels import (
    build_doc_uid_choices,
    build_document_management_state,
    build_document_choices,
    format_quality_result,
    format_recent_quality_checks,
    parse_claim_choice,
    parse_doc_uid_choice,
    parse_document_choice,
    scan_input_documents,
)


def build_ui(*, ingest_service, retrieval_service, quality_service, review_service) -> gr.Blocks:
    """构建最小可用界面。"""

    def load_document_management_state() -> tuple[gr.Dropdown, dict, list[dict], gr.Dropdown]:
        documents = scan_input_documents(ingest_service.settings.input_root)
        status_items, _ = ingest_service.list_status(doc_uid=None, status=None, page=1, page_size=50)
        state = build_document_management_state(documents, status_items)
        return (
            gr.Dropdown(
                choices=state["document_choices"],
                value=state["document_choices"][0] if state["document_choices"] else None,
            ),
            state["scan_summary"],
            state["status_items"],
            gr.Dropdown(
                choices=state["rebuild_choices"],
                value=state["rebuild_choices"][0] if state["rebuild_choices"] else None,
            ),
        )

    def register_selected_document(choice: str) -> tuple[dict, list[dict], gr.Dropdown]:
        file_path = parse_document_choice(choice)
        if not file_path:
            status_items, dropdown = query_ingest_status()
            return {"success": False, "message": "请选择文档"}, status_items, dropdown
        jobs = ingest_service.register_documents(
            [{"file_path": file_path}],
            rebuild_if_exists=False,
        )
        status_items, dropdown = query_ingest_status()
        return {"success": True, "jobs": jobs}, status_items, dropdown

    def register_all_documents() -> tuple[dict, list[dict], gr.Dropdown]:
        documents = scan_input_documents(ingest_service.settings.input_root)
        if not documents:
            status_items, dropdown = query_ingest_status()
            return {"success": False, "message": "Input 目录下没有可注册文档"}, status_items, dropdown
        jobs = ingest_service.register_documents(
            [{"file_path": item["file_path"]} for item in documents],
            rebuild_if_exists=False,
        )
        status_items, dropdown = query_ingest_status()
        return {"success": True, "jobs": jobs}, status_items, dropdown

    def query_ingest_status() -> tuple[list[dict], gr.Dropdown]:
        items, _ = ingest_service.list_status(doc_uid=None, status=None, page=1, page_size=50)
        choices = build_doc_uid_choices(items)
        return items, gr.Dropdown(choices=choices, value=choices[0] if choices else None)

    def rebuild_selected_document(doc_choice: str) -> tuple[dict, list[dict], gr.Dropdown]:
        doc_uid = parse_doc_uid_choice(doc_choice)
        if not doc_uid:
            status_items, dropdown = query_ingest_status()
            return {"success": False, "message": "请选择待重建文档"}, status_items, dropdown
        accepted = ingest_service.rebuild_documents(
            [doc_uid],
            rebuild_fulltext=True,
            rebuild_vector=True,
        )
        status_items, dropdown = query_ingest_status()
        return {"success": True, "accepted": accepted}, status_items, dropdown

    def run_search(query: str, top_k: int) -> list[dict]:
        return retrieval_service.hybrid_search(query, top_k=top_k)

    def run_quality_check(input_text: str) -> tuple[dict, gr.Dropdown]:
        result = quality_service.run_check(input_text)
        formatted = format_quality_result(result)
        default_choice = formatted["claim_choices"][0] if formatted["claim_choices"] else None
        return formatted, gr.Dropdown(choices=formatted["claim_choices"], value=default_choice)

    def submit_review_action(claim_choice: str, review_action: str, review_note: str) -> tuple[dict, list[dict]]:
        claim_id = parse_claim_choice(claim_choice)
        result = review_service.submit_review(
            claim_id=claim_id,
            review_action=review_action,
            reviewed_verdict=None,
            review_note=review_note,
            reviewer="ui_user",
        )
        review_items, _ = review_service.list_reviews(page=1, page_size=20)
        return result, review_items

    def list_recent_quality_results() -> tuple[list[dict], gr.Dropdown]:
        results = quality_service.list_recent_results(limit=10)
        formatted = format_recent_quality_checks(results)
        choices = formatted[0]["claim_choices"] if formatted else []
        return formatted, gr.Dropdown(choices=choices, value=choices[0] if choices else None)

    with gr.Blocks(title="中文知识库系统") as demo:
        gr.Markdown("# 中文知识库系统 MVP")

        with gr.Tab("文档管理"):
            scan_button = gr.Button("扫描 Input 文档")
            document_choices = gr.Dropdown(label="可注册文档", choices=[], interactive=True)
            register_button = gr.Button("注册选中文档")
            register_all_button = gr.Button("注册全部文档")
            register_result = gr.JSON(label="注册结果")
            rebuild_doc_choice = gr.Dropdown(label="可重建文档", choices=[], interactive=True)
            rebuild_button = gr.Button("重建选中文档索引")
            rebuild_result = gr.JSON(label="重建结果")
            status_button = gr.Button("刷新入库状态")
            status_table = gr.JSON(label="文档状态")
            scan_button.click(
                fn=load_document_management_state,
                outputs=[document_choices, register_result, status_table, rebuild_doc_choice],
            )
            register_button.click(
                fn=register_selected_document,
                inputs=document_choices,
                outputs=[register_result, status_table, rebuild_doc_choice],
            )
            register_all_button.click(
                fn=register_all_documents,
                outputs=[register_result, status_table, rebuild_doc_choice],
            )
            status_button.click(fn=query_ingest_status, outputs=[status_table, rebuild_doc_choice])
            rebuild_button.click(
                fn=rebuild_selected_document,
                inputs=rebuild_doc_choice,
                outputs=[rebuild_result, status_table, rebuild_doc_choice],
            )

        with gr.Tab("文档检索"):
            search_query = gr.Textbox(label="检索内容")
            search_top_k = gr.Slider(label="返回数量", minimum=1, maximum=10, step=1, value=5)
            search_button = gr.Button("执行检索")
            search_result = gr.JSON(label="检索结果")
            search_button.click(fn=run_search, inputs=[search_query, search_top_k], outputs=search_result)

        with gr.Tab("AI 质检"):
            quality_input = gr.Textbox(label="待质检文本", lines=8)
            quality_button = gr.Button("开始质检")
            quality_result = gr.JSON(label="质检结果")
            review_claim_selector = gr.Dropdown(label="可审核 Claim", choices=[], interactive=True)
            recent_quality_button = gr.Button("加载最近质检结果")
            recent_quality_checks = gr.JSON(label="最近质检结果")
            quality_button.click(
                fn=run_quality_check,
                inputs=quality_input,
                outputs=[quality_result, review_claim_selector],
            )
            recent_quality_button.click(
                fn=list_recent_quality_results,
                outputs=[recent_quality_checks, review_claim_selector],
            )

        with gr.Tab("人工审核"):
            review_action_input = gr.Dropdown(
                choices=["approved", "rejected", "updated"],
                value="approved",
                label="审核动作",
            )
            review_note_input = gr.Textbox(label="审核备注", lines=3)
            review_button = gr.Button("提交审核")
            review_result = gr.JSON(label="审核结果")
            review_history = gr.JSON(label="最近审核记录")
            review_button.click(
                fn=submit_review_action,
                inputs=[review_claim_selector, review_action_input, review_note_input],
                outputs=[review_result, review_history],
            )
    return demo
