"""程序说明：承载“功能设置”页的组件构建与事件绑定，供主页面总装配复用。"""

from __future__ import annotations

from collections.abc import Callable

import gradio as gr

from src.ui.page_helpers import format_table_pagination_html, ui_button
from src.ui.viewmodels import format_operation_result_html


def build_settings_tab(*, initial_values: dict[str, object]) -> dict[str, gr.components.Component]:
    """构建功能设置页组件，并返回后续事件绑定所需的组件集合。"""

    with gr.Tabs(elem_id="settings-subtabs"):
        with gr.Tab("配置管理", elem_id="settings-config-tab"):
            settings_runtime = gr.HTML(value=initial_values["runtime_html"], elem_id="settings-runtime-panel")
            with gr.Tabs(elem_id="settings-config-subtabs"):
                with gr.Tab("模板管理", elem_id="settings-template-tab"):
                    with gr.Group(elem_id="settings-workspace-panel"):
                        with gr.Group(elem_id="settings-template-list-panel"):
                            gr.HTML(
                                value="""
                                                <div class="settings-list-header">
                                                  <div>
                                                    <h3 class="settings-list-header__title">模板列表</h3>
                                                    <p class="settings-list-header__desc">先在这里选模板，再去右侧查看详情和编辑，避免标题贴角和工具栏占位过高。</p>
                                                  </div>
                                                </div>
                                                """,
                                elem_id="settings-template-list-header",
                            )
                            settings_template_table = gr.Dataframe(
                                headers=["序号", "模板 ID", "模板名称", "来源", "规则标签", "最终返回", "可删除"],
                                datatype=["str"] * 7,
                                interactive=False,
                                row_count=0,
                                column_count=7,
                                label="模板列表",
                                show_label=False,
                                buttons=[],
                                elem_id="settings-template-table",
                                value=initial_values["template_table_rows"],
                            )
                            with gr.Row(elem_id="settings-pagination-row"):
                                settings_template_prev_button = ui_button("上一页")
                                settings_template_next_button = ui_button("下一页")
                            settings_template_page_info = gr.HTML(
                                value=format_table_pagination_html(str(initial_values["template_page_info"])),
                                elem_id="settings-template-page-info",
                            )
                            with gr.Row(elem_id="settings-list-actions"):
                                settings_new_button = ui_button("新建模板")
                                settings_refresh_button = ui_button("刷新模板")
                        with gr.Row(elem_id="settings-main-row"):
                            with gr.Column(scale=1):
                                settings_template_detail = gr.HTML(
                                    value=initial_values["template_detail_html"],
                                    elem_id="settings-template-detail",
                                )
                            with gr.Column(scale=2):
                                with gr.Group(elem_id="settings-template-form"):
                                    gr.Markdown("### 基础信息")
                                    with gr.Group(elem_id="settings-basic-group"):
                                        with gr.Row():
                                            settings_template_id = gr.Textbox(label="模板 ID", value=initial_values["template_id"], scale=2)
                                            settings_template_name = gr.Textbox(label="模板名称", value=initial_values["template_name"], scale=3)
                                        settings_template_description = gr.Textbox(
                                            label="模板说明",
                                            lines=3,
                                            value=initial_values["template_description"],
                                        )
                                        settings_rule_tags = gr.Textbox(
                                            label="规则标签",
                                            value=initial_values["rule_tags"],
                                            placeholder="多个标签用逗号、顿号或换行分隔",
                                        )
                                    gr.Markdown("### 检索策略")
                                    with gr.Group(elem_id="settings-policy-group"):
                                        with gr.Row():
                                            settings_fulltext_top_k = gr.Number(label="全文召回", value=initial_values["fulltext_top_k"], precision=0)
                                            settings_vector_top_k = gr.Number(label="向量召回", value=initial_values["vector_top_k"], precision=0)
                                            settings_final_top_k = gr.Number(label="最终返回", value=initial_values["final_top_k"], precision=0)
                                        with gr.Row():
                                            settings_neighbor_window = gr.Number(label="邻居窗口", value=initial_values["neighbor_window"], precision=0)
                                            settings_section_max_chars = gr.Number(label="章节最大字数", value=initial_values["section_max_chars"], precision=0)
                                        with gr.Row():
                                            settings_use_rerank = gr.Checkbox(label="启用重排", value=initial_values["use_rerank"])
                                            settings_include_section_context = gr.Checkbox(label="章节上下文", value=initial_values["include_section_context"])
                                    gr.Markdown("### Prompt 配置")
                                    with gr.Group(elem_id="settings-prompt-group"):
                                        settings_system_prompt = gr.Textbox(label="系统提示词", lines=8, value=initial_values["system_prompt"])
                                        settings_user_prompt_template = gr.Textbox(
                                            label="用户提示模板",
                                            lines=8,
                                            value=initial_values["user_prompt_template"],
                                        )
                                    settings_delete_confirm = gr.Checkbox(
                                        label="我确认删除当前模板",
                                        value=initial_values["delete_confirm"],
                                    )
                                    with gr.Row(elem_id="settings-form-actions"):
                                        settings_save_button = ui_button("保存模板", variant="primary")
                                        settings_delete_button = ui_button("删除模板", variant="stop")
                with gr.Tab("知识库管理", elem_id="settings-knowledge-base-tab"):
                    with gr.Group(elem_id="settings-knowledge-base-panel"):
                        with gr.Group(elem_id="settings-knowledge-base-list-panel"):
                            gr.HTML(
                                value="""
                                                <div class="settings-list-header">
                                                  <div>
                                                    <h3 class="settings-list-header__title">知识库列表</h3>
                                                    <p class="settings-list-header__desc">先选中目标知识库，再在右侧维护详情与默认状态，保持操作路径稳定。</p>
                                                  </div>
                                                </div>
                                                """,
                                elem_id="settings-knowledge-base-list-header",
                            )
                            settings_knowledge_base_table = gr.Radio(
                                label="知识库列表",
                                elem_id="settings-knowledge-base-table",
                                choices=initial_values["knowledge_base_choices"],
                                value=initial_values["knowledge_base_selected_choice"],
                            )
                            with gr.Row(elem_id="settings-knowledge-base-pagination-row"):
                                settings_knowledge_base_prev_button = ui_button("上一页")
                                settings_knowledge_base_next_button = ui_button("下一页")
                            settings_knowledge_base_page_info = gr.HTML(
                                value=format_table_pagination_html(str(initial_values["knowledge_base_page_info"])),
                                elem_id="settings-knowledge-base-page-info",
                            )
                            with gr.Row(elem_id="settings-knowledge-base-list-actions"):
                                settings_knowledge_base_new_button = ui_button("新建知识库")
                                settings_knowledge_base_refresh_button = ui_button("刷新知识库")
                        with gr.Row(elem_id="settings-knowledge-base-row"):
                            with gr.Column(scale=1):
                                settings_knowledge_base_detail = gr.HTML(
                                    value=initial_values["knowledge_base_detail_html"],
                                    elem_id="settings-knowledge-base-detail",
                                )
                            with gr.Column(scale=2):
                                with gr.Group(elem_id="settings-knowledge-base-form"):
                                    gr.Markdown("### 基础信息")
                                    with gr.Group(elem_id="settings-knowledge-base-basic-group"):
                                        with gr.Row():
                                            settings_knowledge_base_id = gr.Textbox(
                                                label="知识库 ID",
                                                value=initial_values["knowledge_base_id"],
                                                scale=2,
                                            )
                                            settings_knowledge_base_name = gr.Textbox(
                                                label="知识库名称",
                                                value=initial_values["knowledge_base_name"],
                                                scale=3,
                                            )
                                        settings_knowledge_base_description = gr.Textbox(
                                            label="知识库说明",
                                            lines=3,
                                            value=initial_values["knowledge_base_description"],
                                        )
                                    gr.Markdown("### 状态设置")
                                    with gr.Group(elem_id="settings-knowledge-base-status-group"):
                                        with gr.Row():
                                            settings_knowledge_base_status = gr.Dropdown(
                                                label="状态",
                                                choices=["active", "disabled"],
                                                value=initial_values["knowledge_base_status"],
                                                interactive=True,
                                            )
                                            settings_knowledge_base_is_default = gr.Checkbox(
                                                label="设为默认",
                                                value=initial_values["knowledge_base_is_default"],
                                            )
                                    with gr.Row(elem_id="settings-knowledge-base-actions"):
                                        settings_knowledge_base_save_button = ui_button("保存知识库", variant="primary")
                                        settings_knowledge_base_delete_button = ui_button("删除知识库", variant="stop")
                                settings_knowledge_base_result = gr.HTML(
                                    value=initial_values["knowledge_base_result_html"],
                                    elem_id="settings-knowledge-base-result",
                                )
            with gr.Group(elem_id="settings-footer-panel"):
                settings_result = gr.HTML(
                    value=initial_values["result_html"],
                    elem_id="settings-result-panel",
                )
                with gr.Group(elem_id="settings-export-panel"):
                    with gr.Row(elem_id="settings-export-row"):
                        settings_export_button = ui_button("下载当前配置")
                settings_export_result = gr.HTML(
                    value=format_operation_result_html(None, title="下载结果"),
                    elem_id="settings-export-result",
                )

        with gr.Tab("用户管理", elem_id="settings-user-tab"):
            with gr.Group(elem_id="settings-user-management-panel"):
                with gr.Group(elem_id="settings-user-list-panel"):
                    settings_user_table = gr.Radio(
                        label="用户列表",
                        elem_id="settings-user-table",
                        choices=initial_values["user_choices"],
                        value=initial_values["user_selected_choice"],
                    )
                settings_user_detail = gr.HTML(
                    value=initial_values["user_detail_html"],
                    elem_id="settings-user-detail",
                )
                with gr.Row(elem_id="settings-user-actions"):
                    settings_user_refresh_button = ui_button("刷新用户")
                    settings_user_delete_button = ui_button("删除用户", variant="stop")
                settings_user_result = gr.HTML(
                    value=initial_values["user_result_html"],
                    elem_id="settings-user-result",
                )

        with gr.Tab("用户权限管理", elem_id="settings-permission-tab"):
            with gr.Group(elem_id="settings-permission-management-panel"):
                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_id="settings-permission-user-panel"):
                            settings_permission_user_table = gr.Radio(
                                label="权限用户",
                                elem_id="settings-permission-user-table",
                                choices=initial_values["permission_user_choices"],
                                value=initial_values["permission_user_selected_choice"],
                            )
                            settings_permission_refresh_button = ui_button("刷新权限用户")
                    with gr.Column(scale=2):
                        with gr.Group(elem_id="settings-permission-form-panel"):
                            settings_permission_detail = gr.HTML(
                                value=initial_values["permission_detail_html"],
                                elem_id="settings-permission-detail",
                            )
                            settings_permission_tab_access = gr.CheckboxGroup(
                                label="可访问菜单",
                                choices=initial_values["permission_tab_choices"],
                                value=initial_values["permission_tab_values"],
                                elem_id="settings-permission-tab-access",
                            )
                            settings_permission_kb_access = gr.CheckboxGroup(
                                label="可访问知识库",
                                choices=initial_values["permission_kb_choices"],
                                value=initial_values["permission_kb_values"],
                                elem_id="settings-permission-kb-access",
                            )
                            with gr.Row(elem_id="settings-permission-actions"):
                                settings_permission_save_button = ui_button("保存用户权限", variant="primary")
                            settings_permission_result = gr.HTML(
                                value=initial_values["permission_result_html"],
                                elem_id="settings-permission-result",
                            )

    return {
        "settings_runtime": settings_runtime,
        "settings_template_table": settings_template_table,
        "settings_template_prev_button": settings_template_prev_button,
        "settings_template_next_button": settings_template_next_button,
        "settings_template_page_info": settings_template_page_info,
        "settings_new_button": settings_new_button,
        "settings_refresh_button": settings_refresh_button,
        "settings_template_detail": settings_template_detail,
        "settings_template_id": settings_template_id,
        "settings_template_name": settings_template_name,
        "settings_template_description": settings_template_description,
        "settings_rule_tags": settings_rule_tags,
        "settings_fulltext_top_k": settings_fulltext_top_k,
        "settings_vector_top_k": settings_vector_top_k,
        "settings_final_top_k": settings_final_top_k,
        "settings_neighbor_window": settings_neighbor_window,
        "settings_section_max_chars": settings_section_max_chars,
        "settings_use_rerank": settings_use_rerank,
        "settings_include_section_context": settings_include_section_context,
        "settings_system_prompt": settings_system_prompt,
        "settings_user_prompt_template": settings_user_prompt_template,
        "settings_delete_confirm": settings_delete_confirm,
        "settings_save_button": settings_save_button,
        "settings_delete_button": settings_delete_button,
        "settings_knowledge_base_table": settings_knowledge_base_table,
        "settings_knowledge_base_prev_button": settings_knowledge_base_prev_button,
        "settings_knowledge_base_next_button": settings_knowledge_base_next_button,
        "settings_knowledge_base_page_info": settings_knowledge_base_page_info,
        "settings_knowledge_base_new_button": settings_knowledge_base_new_button,
        "settings_knowledge_base_refresh_button": settings_knowledge_base_refresh_button,
        "settings_knowledge_base_detail": settings_knowledge_base_detail,
        "settings_knowledge_base_id": settings_knowledge_base_id,
        "settings_knowledge_base_name": settings_knowledge_base_name,
        "settings_knowledge_base_description": settings_knowledge_base_description,
        "settings_knowledge_base_status": settings_knowledge_base_status,
        "settings_knowledge_base_is_default": settings_knowledge_base_is_default,
        "settings_knowledge_base_save_button": settings_knowledge_base_save_button,
        "settings_knowledge_base_delete_button": settings_knowledge_base_delete_button,
        "settings_knowledge_base_result": settings_knowledge_base_result,
        "settings_result": settings_result,
        "settings_export_button": settings_export_button,
        "settings_export_result": settings_export_result,
        "settings_user_table": settings_user_table,
        "settings_user_detail": settings_user_detail,
        "settings_user_refresh_button": settings_user_refresh_button,
        "settings_user_delete_button": settings_user_delete_button,
        "settings_user_result": settings_user_result,
        "settings_permission_user_table": settings_permission_user_table,
        "settings_permission_refresh_button": settings_permission_refresh_button,
        "settings_permission_detail": settings_permission_detail,
        "settings_permission_tab_access": settings_permission_tab_access,
        "settings_permission_kb_access": settings_permission_kb_access,
        "settings_permission_save_button": settings_permission_save_button,
        "settings_permission_result": settings_permission_result,
    }


def bind_settings_events(
    *,
    components: dict[str, gr.components.Component],
    settings_template_state,
    settings_selected_template_state,
    settings_template_page_state,
    settings_knowledge_base_state,
    settings_selected_knowledge_base_state,
    settings_knowledge_base_page_state,
    settings_user_state,
    settings_selected_user_state,
    login_state,
    persisted_login_state,
    auth_user_display,
    auth_page,
    main_content,
    quality_tab,
    review_tab,
    document_tab,
    search_tab,
    settings_tab,
    quality_template,
    quality_template_detail,
    document_knowledge_base,
    document_target_knowledge_base,
    search_knowledge_base,
    quality_knowledge_base,
    review_knowledge_base,
    refresh_settings_workspace_ui: Callable,
    select_settings_template: Callable,
    prepare_new_template: Callable,
    save_settings_template_ui: Callable,
    delete_settings_template_ui: Callable,
    change_settings_template_page: Callable,
    export_settings_result: Callable,
    refresh_settings_knowledge_base_workspace_ui: Callable,
    select_settings_knowledge_base: Callable,
    prepare_new_knowledge_base: Callable,
    save_settings_knowledge_base_ui: Callable,
    delete_settings_knowledge_base_ui: Callable,
    change_settings_knowledge_base_page: Callable,
    refresh_settings_user_workspace_ui: Callable,
    select_settings_user_ui: Callable,
    delete_settings_user_ui: Callable,
    save_settings_user_permissions_ui: Callable,
) -> None:
    """绑定功能设置页事件，保持对外行为与原实现一致。"""

    settings_refresh_button = components["settings_refresh_button"]
    settings_template_table = components["settings_template_table"]
    settings_template_page_info = components["settings_template_page_info"]
    settings_template_detail = components["settings_template_detail"]
    settings_template_id = components["settings_template_id"]
    settings_template_name = components["settings_template_name"]
    settings_template_description = components["settings_template_description"]
    settings_rule_tags = components["settings_rule_tags"]
    settings_fulltext_top_k = components["settings_fulltext_top_k"]
    settings_vector_top_k = components["settings_vector_top_k"]
    settings_final_top_k = components["settings_final_top_k"]
    settings_use_rerank = components["settings_use_rerank"]
    settings_neighbor_window = components["settings_neighbor_window"]
    settings_include_section_context = components["settings_include_section_context"]
    settings_section_max_chars = components["settings_section_max_chars"]
    settings_system_prompt = components["settings_system_prompt"]
    settings_user_prompt_template = components["settings_user_prompt_template"]
    settings_result = components["settings_result"]
    settings_delete_confirm = components["settings_delete_confirm"]
    settings_new_button = components["settings_new_button"]
    settings_save_button = components["settings_save_button"]
    settings_delete_button = components["settings_delete_button"]
    settings_template_prev_button = components["settings_template_prev_button"]
    settings_template_next_button = components["settings_template_next_button"]
    settings_export_button = components["settings_export_button"]
    settings_export_result = components["settings_export_result"]
    settings_runtime = components["settings_runtime"]

    settings_knowledge_base_refresh_button = components["settings_knowledge_base_refresh_button"]
    settings_knowledge_base_table = components["settings_knowledge_base_table"]
    settings_knowledge_base_page_info = components["settings_knowledge_base_page_info"]
    settings_knowledge_base_detail = components["settings_knowledge_base_detail"]
    settings_knowledge_base_id = components["settings_knowledge_base_id"]
    settings_knowledge_base_name = components["settings_knowledge_base_name"]
    settings_knowledge_base_description = components["settings_knowledge_base_description"]
    settings_knowledge_base_status = components["settings_knowledge_base_status"]
    settings_knowledge_base_is_default = components["settings_knowledge_base_is_default"]
    settings_knowledge_base_result = components["settings_knowledge_base_result"]
    settings_knowledge_base_new_button = components["settings_knowledge_base_new_button"]
    settings_knowledge_base_save_button = components["settings_knowledge_base_save_button"]
    settings_knowledge_base_delete_button = components["settings_knowledge_base_delete_button"]
    settings_knowledge_base_prev_button = components["settings_knowledge_base_prev_button"]
    settings_knowledge_base_next_button = components["settings_knowledge_base_next_button"]
    settings_user_table = components["settings_user_table"]
    settings_user_detail = components["settings_user_detail"]
    settings_user_refresh_button = components["settings_user_refresh_button"]
    settings_user_delete_button = components["settings_user_delete_button"]
    settings_user_result = components["settings_user_result"]
    settings_permission_user_table = components["settings_permission_user_table"]
    settings_permission_refresh_button = components["settings_permission_refresh_button"]
    settings_permission_detail = components["settings_permission_detail"]
    settings_permission_tab_access = components["settings_permission_tab_access"]
    settings_permission_kb_access = components["settings_permission_kb_access"]
    settings_permission_save_button = components["settings_permission_save_button"]
    settings_permission_result = components["settings_permission_result"]

    settings_refresh_button.click(
        fn=refresh_settings_workspace_ui,
        inputs=[settings_selected_template_state],
        outputs=[
            settings_template_table,
            settings_template_page_state,
            settings_template_page_info,
            settings_template_state,
            settings_selected_template_state,
            settings_template_detail,
            settings_template_id,
            settings_template_name,
            settings_template_description,
            settings_rule_tags,
            settings_fulltext_top_k,
            settings_vector_top_k,
            settings_final_top_k,
            settings_use_rerank,
            settings_neighbor_window,
            settings_include_section_context,
            settings_section_max_chars,
            settings_system_prompt,
            settings_user_prompt_template,
            settings_result,
            settings_runtime,
            settings_delete_confirm,
        ],
    )
    settings_template_table.select(
        fn=select_settings_template,
        inputs=[settings_template_state, settings_template_table],
        outputs=[
            settings_selected_template_state,
            settings_template_detail,
            settings_template_id,
            settings_template_name,
            settings_template_description,
            settings_rule_tags,
            settings_fulltext_top_k,
            settings_vector_top_k,
            settings_final_top_k,
            settings_use_rerank,
            settings_neighbor_window,
            settings_include_section_context,
            settings_section_max_chars,
            settings_system_prompt,
            settings_user_prompt_template,
            settings_result,
            settings_delete_confirm,
        ],
    )
    settings_new_button.click(
        fn=prepare_new_template,
        outputs=[
            settings_selected_template_state,
            settings_template_detail,
            settings_template_id,
            settings_template_name,
            settings_template_description,
            settings_rule_tags,
            settings_fulltext_top_k,
            settings_vector_top_k,
            settings_final_top_k,
            settings_use_rerank,
            settings_neighbor_window,
            settings_include_section_context,
            settings_section_max_chars,
            settings_system_prompt,
            settings_user_prompt_template,
            settings_result,
            settings_delete_confirm,
        ],
    )
    settings_save_button.click(
        fn=save_settings_template_ui,
        inputs=[
            settings_selected_template_state,
            settings_template_id,
            settings_template_name,
            settings_template_description,
            settings_rule_tags,
            settings_fulltext_top_k,
            settings_vector_top_k,
            settings_final_top_k,
            settings_use_rerank,
            settings_neighbor_window,
            settings_include_section_context,
            settings_section_max_chars,
            settings_system_prompt,
            settings_user_prompt_template,
        ],
        outputs=[
            settings_template_table,
            settings_template_page_state,
            settings_template_page_info,
            settings_template_state,
            settings_selected_template_state,
            settings_template_detail,
            settings_template_id,
            settings_template_name,
            settings_template_description,
            settings_rule_tags,
            settings_fulltext_top_k,
            settings_vector_top_k,
            settings_final_top_k,
            settings_use_rerank,
            settings_neighbor_window,
            settings_include_section_context,
            settings_section_max_chars,
            settings_system_prompt,
            settings_user_prompt_template,
            settings_result,
            settings_runtime,
            settings_delete_confirm,
            quality_template,
            quality_template_detail,
        ],
    )
    settings_delete_button.click(
        fn=delete_settings_template_ui,
        inputs=[settings_selected_template_state, settings_template_id, settings_delete_confirm],
        outputs=[
            settings_template_table,
            settings_template_page_state,
            settings_template_page_info,
            settings_template_state,
            settings_selected_template_state,
            settings_template_detail,
            settings_template_id,
            settings_template_name,
            settings_template_description,
            settings_rule_tags,
            settings_fulltext_top_k,
            settings_vector_top_k,
            settings_final_top_k,
            settings_use_rerank,
            settings_neighbor_window,
            settings_include_section_context,
            settings_section_max_chars,
            settings_system_prompt,
            settings_user_prompt_template,
            settings_result,
            settings_runtime,
            settings_delete_confirm,
            quality_template,
            quality_template_detail,
        ],
    )
    settings_template_prev_button.click(
        fn=lambda items, page: change_settings_template_page(items, page, "prev"),
        inputs=[settings_template_state, settings_template_page_state],
        outputs=[settings_template_table, settings_template_page_state, settings_template_page_info],
    )
    settings_template_next_button.click(
        fn=lambda items, page: change_settings_template_page(items, page, "next"),
        inputs=[settings_template_state, settings_template_page_state],
        outputs=[settings_template_table, settings_template_page_state, settings_template_page_info],
    )
    settings_export_button.click(
        fn=export_settings_result,
        inputs=[settings_selected_template_state],
        outputs=[settings_export_result],
    )
    settings_knowledge_base_refresh_button.click(
        fn=refresh_settings_knowledge_base_workspace_ui,
        inputs=[settings_selected_knowledge_base_state, login_state],
        outputs=[
            settings_knowledge_base_table,
            settings_knowledge_base_page_state,
            settings_knowledge_base_page_info,
            settings_knowledge_base_state,
            settings_selected_knowledge_base_state,
            settings_knowledge_base_detail,
            settings_knowledge_base_id,
            settings_knowledge_base_name,
            settings_knowledge_base_description,
            settings_knowledge_base_status,
            settings_knowledge_base_is_default,
            settings_knowledge_base_result,
        ],
    )
    settings_knowledge_base_table.input(
        fn=select_settings_knowledge_base,
        inputs=[settings_knowledge_base_table, settings_knowledge_base_state, login_state],
        outputs=[
            settings_selected_knowledge_base_state,
            settings_knowledge_base_detail,
            settings_knowledge_base_id,
            settings_knowledge_base_name,
            settings_knowledge_base_description,
            settings_knowledge_base_status,
            settings_knowledge_base_is_default,
            settings_knowledge_base_result,
        ],
        queue=False,
    )
    settings_knowledge_base_new_button.click(
        fn=prepare_new_knowledge_base,
        inputs=[login_state],
        outputs=[
            settings_selected_knowledge_base_state,
            settings_knowledge_base_detail,
            settings_knowledge_base_id,
            settings_knowledge_base_name,
            settings_knowledge_base_description,
            settings_knowledge_base_status,
            settings_knowledge_base_is_default,
            settings_knowledge_base_result,
        ],
    )
    settings_knowledge_base_save_button.click(
        fn=save_settings_knowledge_base_ui,
        inputs=[
            settings_selected_knowledge_base_state,
            settings_knowledge_base_id,
            settings_knowledge_base_name,
            settings_knowledge_base_description,
            settings_knowledge_base_status,
            settings_knowledge_base_is_default,
            login_state,
        ],
        outputs=[
            settings_knowledge_base_table,
            settings_knowledge_base_page_state,
            settings_knowledge_base_page_info,
            settings_knowledge_base_state,
            settings_selected_knowledge_base_state,
            settings_knowledge_base_detail,
            settings_knowledge_base_id,
            settings_knowledge_base_name,
            settings_knowledge_base_description,
            settings_knowledge_base_status,
            settings_knowledge_base_is_default,
            settings_knowledge_base_result,
            document_knowledge_base,
            search_knowledge_base,
            quality_knowledge_base,
            review_knowledge_base,
        ],
    )
    settings_knowledge_base_delete_button.click(
        fn=delete_settings_knowledge_base_ui,
        inputs=[
            settings_selected_knowledge_base_state,
            settings_knowledge_base_id,
            login_state,
        ],
        outputs=[
            settings_knowledge_base_table,
            settings_knowledge_base_page_state,
            settings_knowledge_base_page_info,
            settings_knowledge_base_state,
            settings_selected_knowledge_base_state,
            settings_knowledge_base_detail,
            settings_knowledge_base_id,
            settings_knowledge_base_name,
            settings_knowledge_base_description,
            settings_knowledge_base_status,
            settings_knowledge_base_is_default,
            settings_knowledge_base_result,
            document_knowledge_base,
            search_knowledge_base,
            quality_knowledge_base,
            review_knowledge_base,
        ],
    )
    settings_knowledge_base_prev_button.click(
        fn=lambda items, page, selected: change_settings_knowledge_base_page(items, page, "prev", selected),
        inputs=[settings_knowledge_base_state, settings_knowledge_base_page_state, settings_selected_knowledge_base_state],
        outputs=[
            settings_knowledge_base_table,
            settings_knowledge_base_page_state,
            settings_knowledge_base_page_info,
            settings_selected_knowledge_base_state,
            settings_knowledge_base_detail,
            settings_knowledge_base_id,
            settings_knowledge_base_name,
            settings_knowledge_base_description,
            settings_knowledge_base_status,
            settings_knowledge_base_is_default,
            settings_knowledge_base_result,
        ],
    )
    settings_knowledge_base_next_button.click(
        fn=lambda items, page, selected: change_settings_knowledge_base_page(items, page, "next", selected),
        inputs=[settings_knowledge_base_state, settings_knowledge_base_page_state, settings_selected_knowledge_base_state],
        outputs=[
            settings_knowledge_base_table,
            settings_knowledge_base_page_state,
            settings_knowledge_base_page_info,
            settings_selected_knowledge_base_state,
            settings_knowledge_base_detail,
            settings_knowledge_base_id,
            settings_knowledge_base_name,
            settings_knowledge_base_description,
            settings_knowledge_base_status,
            settings_knowledge_base_is_default,
            settings_knowledge_base_result,
        ],
    )

    user_permission_outputs = [
        settings_user_table,
        settings_user_state,
        settings_selected_user_state,
        settings_user_detail,
        settings_user_result,
        settings_permission_user_table,
        settings_permission_detail,
        settings_permission_tab_access,
        settings_permission_kb_access,
        settings_permission_result,
    ]
    current_session_permission_outputs = [
        login_state,
        persisted_login_state,
        auth_user_display,
        auth_page,
        main_content,
        quality_tab,
        review_tab,
        document_tab,
        search_tab,
        settings_tab,
        document_knowledge_base,
        document_target_knowledge_base,
        quality_knowledge_base,
        review_knowledge_base,
        search_knowledge_base,
        settings_knowledge_base_state,
        settings_knowledge_base_table,
        settings_knowledge_base_page_state,
        settings_knowledge_base_page_info,
    ]

    settings_user_refresh_button.click(
        fn=refresh_settings_user_workspace_ui,
        inputs=[settings_selected_user_state],
        outputs=user_permission_outputs,
    )
    settings_permission_refresh_button.click(
        fn=refresh_settings_user_workspace_ui,
        inputs=[settings_selected_user_state],
        outputs=user_permission_outputs,
    )
    settings_user_table.input(
        fn=select_settings_user_ui,
        inputs=[settings_user_table, settings_user_state],
        outputs=user_permission_outputs,
        queue=False,
    )
    settings_permission_user_table.input(
        fn=select_settings_user_ui,
        inputs=[settings_permission_user_table, settings_user_state],
        outputs=user_permission_outputs,
        queue=False,
    )
    settings_user_delete_button.click(
        fn=delete_settings_user_ui,
        inputs=[settings_selected_user_state, login_state],
        outputs=[*user_permission_outputs, *current_session_permission_outputs],
    )
    settings_permission_save_button.click(
        fn=save_settings_user_permissions_ui,
        inputs=[
            settings_selected_user_state,
            settings_permission_tab_access,
            settings_permission_kb_access,
            login_state,
        ],
        outputs=[*user_permission_outputs, *current_session_permission_outputs],
    )
