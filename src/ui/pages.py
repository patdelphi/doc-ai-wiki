"""程序说明：提供最小可用的 Gradio 页面，覆盖文档管理、检索、质检与审核。"""

from __future__ import annotations

from functools import partial, update_wrapper
import json
import logging

import gradio as gr

from src.auth.service import AUTH_TAB_NAMES, normalize_auth_tab_name
from src.common.errors import AppError, NotFoundAppError
from src.common.paths import resolve_input_path
from src.pageindex.service import PageIndexService
from src.ui.exporters import build_download_url, save_markdown_export
from src.ui.page_helpers import (
    TABLE_PAGE_SIZE,
    build_visible_knowledge_base_bundle,
    change_table_page,
    format_table_pagination_html,
    get_row_from_paged_table,
    get_selected_search_item_from_page_rows,
    normalize_table_rows,
    paginate_table_rows,
    rebuild_readonly_dataframe,
    reset_table_pagination,
    resolve_table_row_count,
    ui_button,
    extract_login_session_permissions as _extract_login_session_permissions,
)
from src.ui.document_page import bind_document_events, build_document_tab
from src.ui.pageindex_page import bind_pageindex_events, build_pageindex_tab
from src.ui.quality_dummy_page import build_quality_dummy_tab
from src.ui.quality_page import bind_quality_events, build_quality_tab
from src.ui.review_page import bind_review_events, build_review_tab
from src.ui.search_page import (
    bind_search_events,
    build_search_detail as search_build_search_detail,
    build_search_detail_payload as search_build_search_detail_payload,
    build_search_tab,
    change_search_page,
    export_search_results as search_export_search_results,
    reset_search_workspace_ui,
    run_search_ui as search_run_search_ui,
    select_search_result as search_select_search_result,
)
from src.ui.settings_page import bind_settings_events, build_settings_tab
from src.ui.viewmodels import (
    build_claim_evidence_rows,
    build_database_summary_rows,
    build_document_action_updates,
    build_document_quality_batch_rows,
    build_document_quality_chunk_rows,
    build_document_quality_section_rows,
    build_document_management_state,
    build_knowledge_base_choices,
    build_quality_claim_rows,
    build_quality_evaluation_rows,
    build_recent_claim_navigation,
    build_recent_quality_rows,
    build_review_candidate_rows,
    build_review_history_rows,
    build_search_result_rows,
    build_settings_template_rows,
    build_settings_knowledge_base_rows,
    build_template_choices,
    format_claim_detail_for_review,
    format_claim_detail_html,
    format_active_quality_check_html,
    format_database_summary_html,
    format_document_detail_html,
    format_document_detail_markdown,
    format_document_quality_batch_export_markdown,
    format_document_quality_batch_summary_html,
    format_document_quality_config_markdown,
    format_document_quality_config_html,
    format_document_quality_checks_html,
    format_document_quality_export_markdown,
    format_document_quality_report_html,
    format_document_quality_search_summary_html,
    format_document_summary_html,
    format_evidence_detail_html,
    format_ingest_result,
    format_operation_result_html,
    format_quality_evaluation_export_markdown,
    format_quality_evaluation_summary_html,
    format_quality_export_markdown,
    format_quality_progress_html,
    format_quality_result,
    format_quality_result_html,
    format_search_export_markdown,
    format_settings_knowledge_base_detail_html,
    format_settings_runtime_markdown,
    format_settings_runtime_html,
    format_settings_template_detail_markdown,
    format_settings_template_detail_html,
    format_quality_template_html,
    format_recent_quality_checks,
    format_review_candidates,
    format_review_export_markdown,
    format_review_history,
    format_review_record_detail_html,
    format_search_result_detail_html,
    format_search_results,
    get_document_detail,
    normalize_search_query,
    parse_claim_choice,
    parse_document_choice,
    parse_knowledge_base_choice,
    parse_template_choice,
    scan_input_documents,
)


RECENT_QUALITY_FETCH_LIMIT = 200
AUTH_SESSION_STORAGE_KEY = "doc-ai-wiki-auth-session"
AUTH_SESSION_SECRET = "doc_ai_wiki_auth_session_v1"
LOGGER = logging.getLogger(__name__)
MAIN_TAB_NAMES = list(AUTH_TAB_NAMES)
MAIN_TAB_IDS = {
    "待开通": "main-tab-pending-access",
    "AI 质检": "main-tab-quality",
    "人工审核": "main-tab-review",
    "知识库管理": "main-tab-document",
    "知识库检索": "main-tab-search",
    "PageIndex 深度检索": "main-tab-pageindex",
    "功能设置": "main-tab-settings",
}


def extract_login_session_permissions(
    session: dict[str, object] | None,
) -> tuple[bool, set[str] | None, set[str] | None]:
    """从登录态中提取管理员标记、页签权限和知识库权限。"""

    return _extract_login_session_permissions(session, normalize_tab_name=normalize_auth_tab_name)


def _build_quality_dummy_card_html(title: str, body: str, *, tone: str = "default") -> str:
    """构建 AI 质检 dummy 页面使用的静态卡片。"""

    return (
        f"<section class='quality-dummy-shell quality-dummy-shell--{tone}'>"
        "<div class='quality-dummy-kicker'>"
        f"{title}</div>"
        f"{body}"
        "</section>"
    )


def _build_quality_dummy_evidence_rows() -> list[list[str]]:
    """返回 AI 质检 dummy 的静态证据行。"""

    return [
        ["SUP-001", "《本草纲目》", "卷一 / 药部", "支持", "原句检索", "阿胶主治与补血相关表述高度一致"],
        ["CHK-014", "《神农本草经》", "上品 / 阿胶", "补充", "扩展检索", "补充说明阿胶长期入药背景，可解释来源脉络"],
        ["CON-003", "《本草拾遗》", "卷三 / 校注", "矛盾", "扩展检索", "存在剂量语义差异，需要人工复核原句上下文"],
    ]


def _build_quality_dummy_history_rows() -> list[list[str]]:
    """返回 AI 质检 dummy 的静态历史记录。"""

    return [
        ["chk_20260504_001", "classical_claim_review", "需复核", "4 条", "2 条", "2026-05-08 15:58", "阿胶可以直接替代所有补血药"],
        ["chk_20260503_004", "general_fact_check", "部分通过", "6 条", "1 条", "2026-05-07 18:20", "《神农本草经》明确记载阿胶用于延年不老"],
        ["chk_20260502_002", "risk_first_screening", "低风险", "5 条", "0 条", "2026-05-06 09:12", "阿胶在古籍中常与补血场景关联"],
    ]


def _build_quality_dummy_evaluation_rows() -> list[list[str]]:
    """返回 AI 质检 dummy 的静态评测明细。"""

    return [
        [
            "case-001",
            "需复核",
            "需复核",
            "是",
            "高风险",
            "高风险",
            "是",
            "4",
            "4",
            "是",
            "是",
            "是",
            "Claim 拆分和风险判断符合预期",
            "无需额外排查",
            "阿胶可以直接替代所有补血药，并且《神农本草经》明确记载它可以延年不老。",
        ],
        [
            "case-002",
            "部分通过",
            "部分通过",
            "是",
            "中风险",
            "中风险",
            "是",
            "3",
            "3",
            "是",
            "是",
            "是",
            "模板对古文引用的风险识别符合预期",
            "继续检查古籍原句上下文",
            "阿胶在古籍中常与补血场景关联，但个别现代转述带有扩大解释。",
        ],
    ]


def _build_quality_dummy_top_help_html() -> str:
    """返回 AI 质检 dummy 的顶部帮助卡。"""

    return _build_quality_dummy_card_html(
        "使用说明",
        """
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>当前页用途</div>
          <p class='quality-dummy-section-text'>这个 dummy 只做 UI 样式验证，不接正式业务事件；但模块编排、功能分区、阅读顺序按正式 `AI 质检` 页完整保留。</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>阅读方式</div>
          <p class='quality-dummy-section-text'>建议按“输入与执行 → 模板内容 → 执行进度/质检结果 → Claim/证据 → 历史记录/下载结果 → 效果评测”的顺序查看。</p>
        </div>
        """,
    )


def _build_quality_dummy_template_html() -> str:
    """返回 AI 质检 dummy 的模板内容卡。"""

    return _build_quality_dummy_card_html(
        "模板内容",
        """
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>当前模板</div>
          <p class='quality-dummy-section-text'><strong>classical_claim_review</strong> · 面向古文、古籍转述、医学相关表述的证据优先核检。</p>
        </div>
        <div class='quality-dummy-stat-grid'>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>全文召回</div>
            <div class='quality-dummy-stat-value'>8</div>
          </div>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>向量召回</div>
            <div class='quality-dummy-stat-value'>8</div>
          </div>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>最终返回</div>
            <div class='quality-dummy-stat-value'>6</div>
          </div>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>工作模式</div>
            <div class='quality-dummy-stat-value'>证据优先</div>
          </div>
        </div>
        <div class='quality-dummy-highlight'>
          <strong>模板说明：</strong>优先保守处理绝对化结论、夸张疗效、古籍出处不稳的现代转述。
        </div>
        """,
        tone="primary",
    )


def _build_quality_dummy_progress_html() -> str:
    """返回 AI 质检 dummy 的执行进度卡。"""

    return _build_quality_dummy_card_html(
        "执行进度",
        """
        <div class='quality-dummy-stat-grid'>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>当前阶段</div>
            <div class='quality-dummy-stat-value'>已完成</div>
          </div>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>耗时</div>
            <div class='quality-dummy-stat-value'>18s</div>
          </div>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>阶段拆解</div>
          <ul class='quality-dummy-list'>
            <li>已完成 Claim 拆分</li>
            <li>已完成检索与证据关系标注</li>
            <li>已完成总体结论生成</li>
            <li>当前等待人工复核决策</li>
          </ul>
        </div>
        """,
    )


def _build_quality_dummy_result_html() -> str:
    """返回 AI 质检 dummy 的结果卡。"""

    return _build_quality_dummy_card_html(
        "质检结果",
        """
        <div class='quality-dummy-title'>总体结论：需复核</div>
        <div class='quality-dummy-chip-row'>
          <span class='quality-dummy-chip quality-dummy-chip--danger'>高风险</span>
          <span class='quality-dummy-chip quality-dummy-chip--warning'>2 条待送审</span>
          <span class='quality-dummy-chip quality-dummy-chip--primary'>4 条 Claim</span>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>结果摘要</div>
          <p class='quality-dummy-section-text'>输入中同时存在绝对化结论、古籍出处不稳的现代转述、以及可保留的弱结论，不能直接整体通过。</p>
        </div>
        """,
        tone="warning",
    )


def _build_quality_dummy_active_check_html() -> str:
    """返回 AI 质检 dummy 的当前任务概览。"""

    return _build_quality_dummy_card_html(
        "当前任务",
        """
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>质检 ID</div>
          <p class='quality-dummy-section-text'>chk_20260504_001</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>当前焦点</div>
          <p class='quality-dummy-section-text'>C1 · 阿胶可以直接替代所有补血药</p>
        </div>
        """,
        tone="primary",
    )


def _build_quality_dummy_status_html() -> str:
    """返回 AI 质检 dummy 的执行状态与总体结果。"""

    return _build_quality_dummy_card_html(
        "执行状态与总体结果",
        """
        <div class='quality-dummy-title'>已完成 1 次模拟质检</div>
        <div class='quality-dummy-subtitle'>这里仍然只负责展示执行状态、总体结论、风险等级和当前焦点，不改动原有功能含义。</div>
        <div class='quality-dummy-stat-grid'>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>当前状态</div>
            <div class='quality-dummy-stat-value'>待人工复核</div>
          </div>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>总体风险</div>
            <div class='quality-dummy-stat-value'>高风险</div>
          </div>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>Claim 数量</div>
            <div class='quality-dummy-stat-value'>4 条</div>
          </div>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>待处理动作</div>
            <div class='quality-dummy-stat-value'>2 项</div>
          </div>
        </div>
        <div class='quality-dummy-highlight'>
          <strong>总体结论：</strong>输入中包含绝对化结论与来源不稳的古籍引用，建议拆分后分别处理。
        </div>
        """,
        tone="primary",
    )


def _build_quality_dummy_focus_html() -> str:
    """返回 AI 质检 dummy 的当前 Claim 详情卡片。"""

    return _build_quality_dummy_card_html(
        "当前 Claim",
        """
        <div class='quality-dummy-title'>阿胶可以直接替代所有补血药</div>
        <div class='quality-dummy-chip-row'>
          <span class='quality-dummy-chip quality-dummy-chip--danger'>高风险</span>
          <span class='quality-dummy-chip quality-dummy-chip--warning'>待人工确认</span>
          <span class='quality-dummy-chip quality-dummy-chip--primary'>证据 3 条</span>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>系统判断</div>
          <p class='quality-dummy-section-text'>绝对化表述过强，现有证据只能支持“常用于补血相关场景”，不能推出“替代所有补血药”。</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>建议动作</div>
          <ul class='quality-dummy-list'>
            <li>保留原始 Claim</li>
            <li>拆出“补血相关用途”作为可保留子结论</li>
            <li>其余部分进入人工审核</li>
          </ul>
        </div>
        """,
        tone="primary",
    )


def _build_quality_dummy_evidence_detail_html() -> str:
    """返回 AI 质检 dummy 的证据详情卡片。"""

    return _build_quality_dummy_card_html(
        "证据详情",
        """
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>当前证据</div>
          <p class='quality-dummy-section-text'><strong>SUP-001</strong> · 《本草纲目》 · 卷一 / 药部</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>原文摘录</div>
          <p class='quality-dummy-section-text'>阿胶，久服轻身益气，常见于补血相关配伍场景。</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>上下文说明</div>
          <p class='quality-dummy-section-text'>原文支持“补血相关用途”，但没有支持“替代所有补血药”的绝对化推断。</p>
        </div>
        <div class='quality-dummy-highlight'>
          <strong>处理建议：</strong>保留“补血相关”结论，删除“直接替代所有补血药”的扩张说法。
        </div>
        """,
    )


def _build_quality_dummy_actions_html() -> str:
    """返回 AI 质检 dummy 的后续动作结果区。"""

    return _build_quality_dummy_card_html(
        "后续动作结果区",
        """
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>当前选中对象</div>
          <p class='quality-dummy-section-text'>质检 ID `chk_20260504_001` / Claim `C1`</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>最近动作反馈</div>
          <ul class='quality-dummy-list'>
            <li>导出结果示例：`Docs/quality_dummy_preview_20260508_1600.MD` 已生成</li>
            <li>提交人工审核示意：已加入待审核队列，审核优先级为“高”</li>
            <li>复核任务示意：已创建 `review_task_001`，要求核对古籍原句与现代转述是否一致</li>
          </ul>
        </div>
        <div class='quality-dummy-highlight'>
          <strong>操作反馈示例：</strong>最近一次模拟操作成功，系统建议先送审再导出最终结果。
        </div>
        """,
        tone="success",
    )


def _build_quality_dummy_export_result_html() -> str:
    """返回 AI 质检 dummy 的下载结果区。"""

    return _build_quality_dummy_card_html(
        "下载结果",
        """
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>最近导出</div>
          <p class='quality-dummy-section-text'>`Docs/quality_dummy_preview_20260508_1615.MD` 已生成，可用于预览本次静态版质检结果。</p>
        </div>
        <div class='quality-dummy-highlight'>
          <strong>说明：</strong>这里保留正式页“下载结果与动作”的位置，只做静态反馈展示，不绑定真实导出逻辑。
        </div>
        """,
        tone="success",
    )


def _build_quality_dummy_evaluation_help_html() -> str:
    """返回 AI 质检 dummy 的评测帮助区。"""

    return _build_quality_dummy_card_html(
        "效果评测说明",
        """
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>用途</div>
          <p class='quality-dummy-section-text'>用于比对模板在多条样例上的结论、风险等级、Claim 数量是否符合预期。</p>
        </div>
        """,
    )


def _build_quality_dummy_evaluation_summary_html() -> str:
    """返回 AI 质检 dummy 的评测摘要。"""

    return _build_quality_dummy_card_html(
        "评测摘要",
        """
        <div class='quality-dummy-stat-grid'>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>样例数量</div>
            <div class='quality-dummy-stat-value'>2</div>
          </div>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>完全命中</div>
            <div class='quality-dummy-stat-value'>2</div>
          </div>
        </div>
        <div class='quality-dummy-highlight'>
          <strong>当前结果：</strong>模拟样例的结论、风险等级、Claim 数量均与预期一致。
        </div>
        """,
        tone="primary",
    )


def _build_quality_dummy_help_html() -> str:
    """返回 AI 质检 dummy 的底部详细功能说明。"""

    return _build_quality_dummy_card_html(
        "详细功能说明",
        """
        <div class='quality-dummy-title'>详细功能说明</div>
        <div class='quality-dummy-stat-grid'>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>布局原则</div>
            <div class='quality-dummy-stat-value'>始终两列以内</div>
          </div>
          <div class='quality-dummy-stat'>
            <div class='quality-dummy-stat-label'>阅读顺序</div>
            <div class='quality-dummy-stat-value'>结果 → Claim → 证据</div>
          </div>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>输入与执行</div>
          <p class='quality-dummy-section-text'>用于填写待质检文本、选择知识库与模板，并触发一次完整的质检流程。</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>执行状态与总体结果</div>
          <p class='quality-dummy-section-text'>集中展示当前任务状态、总体结论、风险等级和 Claim 数量，避免用户在多个区域拼接结果。</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>Claim 列表与当前 Claim</div>
          <p class='quality-dummy-section-text'>左侧看队列，右侧看当前焦点，保证“选什么、看什么”始终对应。</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>证据列表与证据详情</div>
          <p class='quality-dummy-section-text'>左侧看证据清单，右侧看原文与解释，专门承接支持、补充、矛盾三类证据。</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>历史质检记录</div>
          <p class='quality-dummy-section-text'>用于回看最近任务，帮助比较不同输入或不同模板下的质检结果。</p>
        </div>
        <div class='quality-dummy-section'>
          <div class='quality-dummy-section-title'>后续动作结果区</div>
          <p class='quality-dummy-section-text'>用于承接导出、送审、生成复核任务后的结果反馈，确保用户能直接看到动作结果，而不是只看到按钮。</p>
        </div>
        """,
        tone="warning",
    )


def build_ui(*, ingest_service, retrieval_service, quality_service, review_service, auth_service, runtime_config: dict | None = None) -> gr.Blocks:
    """构建最小可用界面。"""

    pageindex_service = PageIndexService(
        ingest_service.settings,
        retrieval_service=retrieval_service,
    )
    knowledge_base_items = ingest_service.list_knowledge_bases()
    knowledge_base_choices = build_knowledge_base_choices(knowledge_base_items)
    default_knowledge_base_choice = next(
        (
            choice
            for choice in knowledge_base_choices
            if any(
                item.get("is_default")
                and parse_knowledge_base_choice(choice) == item.get("knowledge_base_id")
                for item in knowledge_base_items
            )
        ),
        knowledge_base_choices[0] if knowledge_base_choices else None,
    )
    template_items = quality_service.list_templates()
    template_choices = build_template_choices(template_items)
    default_template_choice = next(
        (choice for choice in template_choices if parse_template_choice(choice) == "general_fact_check"),
        template_choices[0] if template_choices else None,
    )
    default_template = quality_service.get_template(parse_template_choice(default_template_choice)) if default_template_choice else None

    def resolve_knowledge_base_choice(choice: str | None) -> str:
        """解析当前知识库选项，未传时回退到默认值。"""

        resolved_choice = choice or default_knowledge_base_choice or ""
        knowledge_base_id = parse_knowledge_base_choice(resolved_choice)
        if knowledge_base_id:
            return knowledge_base_id
        return ingest_service.get_knowledge_base(None)["knowledge_base_id"]

    def refresh_knowledge_base_choices() -> tuple[list[dict], list[str], str | None]:
        """重新加载知识库选项，并返回默认选项。"""

        items = ingest_service.list_knowledge_bases()
        choices = build_knowledge_base_choices(items)
        default_choice = next(
            (
                choice
                for choice in choices
                if any(
                    item.get("is_default")
                    and parse_knowledge_base_choice(choice) == item.get("knowledge_base_id")
                    for item in items
                )
            ),
            choices[0] if choices else None,
        )
        return items, choices, default_choice

    def _build_visible_knowledge_base_bundle(
        session: dict[str, object] | None,
        selected_knowledge_base_id: str | None = None,
    ) -> tuple[list[dict], list[str], str | None]:
        """按当前登录态构建可见知识库列表、选项和默认值。"""

        if session is None:
            return build_visible_knowledge_base_bundle(
                ingest_service.list_knowledge_bases(),
                None,
                is_admin=True,
                selected_knowledge_base_id=selected_knowledge_base_id,
            )
        is_admin, _allowed_tabs, allowed_kb_ids = extract_login_session_permissions(session)
        return build_visible_knowledge_base_bundle(
            ingest_service.list_knowledge_bases(),
            allowed_kb_ids,
            is_admin=is_admin,
            selected_knowledge_base_id=selected_knowledge_base_id,
        )

    def _resolve_authorized_knowledge_base_choice(
        choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> str | None:
        """按当前登录态解析可访问知识库；无权限时返回空。"""

        if login_session is None:
            return resolve_knowledge_base_choice(choice)
        _visible_items, _visible_choices, resolved_choice = _build_visible_knowledge_base_bundle(
            login_session,
            parse_knowledge_base_choice(choice or ""),
        )
        resolved_knowledge_base_id = parse_knowledge_base_choice(resolved_choice or "")
        return resolved_knowledge_base_id or None

    def _build_pageindex_status_html(
        message: str,
        *,
        success: bool | None = None,
        index_status: str | None = None,
        retrieval_mode: str | None = None,
        llm_error: str | None = None,
        include_llm_status: bool = True,
    ) -> str:
        """渲染 PageIndex 状态提示。"""

        status_lines: list[str] = []
        status_value = index_status or ("已构建" if success else "未构建")
        if include_llm_status:
            retrieval_status = pageindex_service.get_retrieval_status()
            llm_label = "LLM 可用" if retrieval_status.get("llm_available") else "LLM 不可用"
            status_lines.extend(
                [
                    f"索引状态：{status_value}",
                    f'LLM 状态：{llm_label}（{retrieval_status.get("llm_status", "-")}）',
                    f'检索模式：{retrieval_status.get("retrieval_mode", "-")}',
                    f'模型：{retrieval_status.get("provider", "-")}/{retrieval_status.get("model", "-")}',
                ]
            )
        if retrieval_mode:
            status_lines.append(f"本次检索模式：{retrieval_mode}")
        if llm_error:
            status_lines.append(f"LLM 降级原因：{llm_error}")
        resolved_message = message
        if status_lines:
            resolved_message = "\n".join([message, "", *status_lines])
        payload = {"message": resolved_message, "status_label": "索引状态", "status_value": status_value}
        return format_operation_result_html(payload, title="PageIndex 状态")

    def _build_pageindex_answer_html(
        message: str,
        *,
        retrieval_mode: str | None = None,
        llm_error: str | None = None,
    ) -> str:
        """渲染 PageIndex 回答区，避免重复顶部索引与 LLM 状态。"""

        answer_lines = [message]
        if retrieval_mode:
            answer_lines.extend(["", f"本次检索模式：{retrieval_mode}"])
        if llm_error:
            answer_lines.append(f"LLM 降级原因：{llm_error}")
        payload = {
            "message": "\n".join(answer_lines),
            "status_label": "回答状态",
            "status_value": "已回答" if retrieval_mode else "尚未提问",
        }
        return format_operation_result_html(payload, title="PageIndex 回答")

    def _build_pageindex_document_choices(knowledge_base_choice: str | None) -> tuple[list[str], str | None]:
        """按知识库生成 PageIndex 文档选择项，避免跨库混用文档。"""

        knowledge_base_id = parse_knowledge_base_choice(knowledge_base_choice or "")
        if not knowledge_base_id:
            return [], None
        try:
            documents = pageindex_service.list_available_documents(knowledge_base_id)
        except AppError:
            return [], None
        choices = [f'{item["doc_uid"]} | {item["doc_title"]}' for item in documents]
        return choices, choices[0] if choices else None

    def _parse_pageindex_document_choice(document_choice: str | None) -> str:
        """从 PageIndex 文档下拉中解析 doc_uid。"""

        return str(document_choice or "").split(" | ", maxsplit=1)[0].strip()

    def change_pageindex_knowledge_base_ui(knowledge_base_choice: str | None):
        """切换 PageIndex 知识库后刷新当前文档与结果区。"""

        document_choices, selected_document = _build_pageindex_document_choices(knowledge_base_choice)
        (
            status_html,
            tree_rows,
            answer_html,
            evidence_rows,
            debug_rows,
            history_rows,
            history_state,
            active_query_id,
            export_result_html,
            download_file,
        ) = _build_pageindex_selected_document_state(
            knowledge_base_choice,
            selected_document,
        )
        return (
            gr.update(choices=document_choices, value=selected_document),
            status_html,
            tree_rows,
            answer_html,
            evidence_rows,
            debug_rows,
            history_rows,
            history_state,
            active_query_id,
            export_result_html,
            download_file,
        )

    def change_pageindex_document_ui(_knowledge_base_choice: str | None, _document_choice: str | None):
        """切换 PageIndex 文档后清空旧结果，避免跨文档误读。"""

        return _build_pageindex_selected_document_state(_knowledge_base_choice, _document_choice)

    def _build_pageindex_selected_document_state(knowledge_base_choice: str | None, document_choice: str | None):
        """读取当前文档 PageIndex 状态；已有索引时直接展示结构树。"""

        knowledge_base_id = parse_knowledge_base_choice(knowledge_base_choice or "")
        doc_uid = _parse_pageindex_document_choice(document_choice)
        if not knowledge_base_id or not doc_uid:
            history = pageindex_service.list_knowledge_base_query_history(knowledge_base_id) if knowledge_base_id else []
            history_rows = _build_pageindex_history_rows(history)
            active_query_id = str(history[0].get("query_id") or "") if history else ""
            return (
                _build_pageindex_status_html("请选择当前知识库与文档，然后构建 PageIndex。", index_status="未选择文档"),
                [],
                _build_pageindex_answer_html("尚未提问。"),
                [],
                [],
                history_rows,
                history,
                active_query_id,
                "",
                None,
            )
        try:
            tree_rows = pageindex_service.get_tree_rows(knowledge_base_id, doc_uid)
            history = pageindex_service.list_knowledge_base_query_history(knowledge_base_id)
            history_rows = _build_pageindex_history_rows(history)
            active_query_id = str(history[0].get("query_id") or "") if history else ""
        except NotFoundAppError:
            history = pageindex_service.list_knowledge_base_query_history(knowledge_base_id)
            history_rows = _build_pageindex_history_rows(history)
            active_query_id = str(history[0].get("query_id") or "") if history else ""
            return (
                _build_pageindex_status_html("已切换文档，请构建或重建 PageIndex。", index_status="未构建"),
                [],
                _build_pageindex_answer_html("尚未提问。"),
                [],
                [],
                history_rows,
                history,
                active_query_id,
                "",
                None,
            )
        except AppError as exc:
            return (
                _build_pageindex_status_html(f"索引记录存在，但读取结构失败：{exc.message}", success=False, index_status="索引异常"),
                [],
                _build_pageindex_answer_html("尚未提问。"),
                [],
                [],
                [],
                [],
                "",
                "",
                None,
            )
        return (
            _build_pageindex_status_html("PageIndex 已构建，可直接提问。", success=True, index_status="已构建"),
            tree_rows,
            _build_pageindex_answer_html("尚未提问。"),
            [],
            [],
            history_rows,
            history,
            active_query_id,
            "",
            None,
        )

    def build_pageindex_index_ui(knowledge_base_choice: str | None, document_choice: str | None, rebuild: bool = False):
        """触发 PageIndex 本地索引构建，并返回状态与结构表。"""

        knowledge_base_id = parse_knowledge_base_choice(knowledge_base_choice or "")
        doc_uid = _parse_pageindex_document_choice(document_choice)
        if not knowledge_base_id or not doc_uid:
            return _build_pageindex_status_html("请先选择知识库和文档。", success=False), []
        try:
            result = pageindex_service.build_index(knowledge_base_id, doc_uid, rebuild=rebuild)
        except AppError as exc:
            return _build_pageindex_status_html(exc.message, success=False), []
        tree_rows = pageindex_service.get_tree_rows(knowledge_base_id, doc_uid)
        return (
            _build_pageindex_status_html(f'PageIndex 已构建：{result["pageindex_doc_id"]}', success=True),
            tree_rows,
        )

    def _build_pageindex_evidence_rows(evidence_items: list[dict] | None) -> list[list[object]]:
        """将 PageIndex 证据转换为表格行。"""

        rows: list[list[object]] = []
        for index, item in enumerate(evidence_items or [], start=1):
            rows.append(
                [
                    index,
                    str(item.get("title") or ""),
                    str(item.get("position") or ""),
                    str(item.get("content") or item.get("summary") or "")[:500],
                    str(item.get("evidence_label") or "未分类"),
                    str(item.get("source_type") or "PageIndex 节点"),
                ]
            )
        return rows

    def _build_pageindex_history_rows(history_items: list[dict] | None) -> list[list[object]]:
        """将 PageIndex 历史转换为表格行。"""

        rows: list[list[object]] = []
        for item in history_items or []:
            debug = item.get("debug") if isinstance(item.get("debug"), dict) else {}
            question_plan = debug.get("question_plan") if isinstance(debug.get("question_plan"), dict) else {}
            rows.append(
                [
                    str(item.get("created_at") or ""),
                    str(item.get("doc_uid") or ""),
                    str(item.get("question") or ""),
                    str(item.get("answer") or "")[:300],
                    str(question_plan.get("question_type") or "unknown"),
                ]
            )
        return rows

    def _build_pageindex_debug_rows(debug: dict | None) -> list[list[object]]:
        """将 PageIndex 检索诊断转换为表格行。"""

        if not isinstance(debug, dict):
            return []
        retrieval_mode = str(debug.get("retrieval_mode") or "")
        selected_ids = {
            str(item.get("candidate_id") or "")
            for item in debug.get("selected_nodes") or []
            if isinstance(item, dict)
        }
        selected_reasons = {
            str(item.get("candidate_id") or ""): str(item.get("reason") or "")
            for item in debug.get("selected_nodes") or []
            if isinstance(item, dict)
        }
        rows: list[list[object]] = []
        for index, item in enumerate(debug.get("candidate_nodes") or [], start=1):
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("candidate_id") or "")
            reason = selected_reasons.get(candidate_id) or str(item.get("reason") or "")
            if candidate_id in selected_ids and reason:
                reason = f"已选中：{reason}"
            rows.append(
                [
                    index,
                    str(item.get("title") or ""),
                    str(item.get("position") or ""),
                    int(item.get("score") or 0),
                    retrieval_mode,
                    reason,
                ]
            )
        for item in debug.get("rag_evidence") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                [
                    len(rows) + 1,
                    str(item.get("title") or "RAG/FTS 原文片段"),
                    str(item.get("position") or ""),
                    0,
                    retrieval_mode,
                    str(item.get("reason") or "当前文档 RAG/FTS 补充命中"),
                ]
            )
        return rows

    def ask_pageindex_question_ui(
        knowledge_base_choice: str | None,
        document_choice: str | None,
        template_choice: str | None,
        question: str | None,
    ):
        """基于 PageIndex 本地结构提问，并刷新证据与历史。"""

        knowledge_base_id = parse_knowledge_base_choice(knowledge_base_choice or "")
        template_id = parse_template_choice(template_choice or "")
        if not knowledge_base_id:
            return _build_pageindex_answer_html("请先选择知识库。"), [], [], [], [], "", "", None
        try:
            result = pageindex_service.ask_knowledge_base_question(knowledge_base_id, question or "", template_id=template_id or None)
            history = pageindex_service.list_knowledge_base_query_history(knowledge_base_id)
        except AppError as exc:
            return _build_pageindex_answer_html(exc.message), [], [], [], [], "", "", None
        return (
            _build_pageindex_answer_html(
                result["answer"],
                retrieval_mode=str(result.get("retrieval_mode") or ""),
                llm_error=str(result.get("llm_error") or ""),
            ),
            _build_pageindex_evidence_rows(result.get("evidence") or []),
            _build_pageindex_debug_rows(result.get("debug") if isinstance(result.get("debug"), dict) else {}),
            _build_pageindex_history_rows(history),
            history,
            str(result.get("query_id") or ""),
            format_operation_result_html(
                {"success": True, "message": "已激活当前结果，可下载。"},
                title="下载结果",
            ),
            None,
        )

    def select_pageindex_history_ui(
        knowledge_base_choice: str | None,
        document_choice: str | None,
        history_state: list[dict] | None,
        current_history_rows: list[list[object]] | None,
        evt: gr.SelectData,
    ):
        """点击历史记录后激活并回显对应 PageIndex 问答结果。"""

        knowledge_base_id = parse_knowledge_base_choice(knowledge_base_choice or "")
        current_rows = [] if current_history_rows is None else current_history_rows
        selected_row = get_row_from_paged_table(current_rows, evt, id_column_index=0)
        row_index = 0
        if selected_row:
            normalized_rows = normalize_table_rows(current_rows)
            row_index = normalized_rows.index(selected_row) if selected_row in normalized_rows else 0
        history_items = history_state or []
        selected_item = history_items[row_index] if 0 <= row_index < len(history_items) else {}
        query_id = str(selected_item.get("query_id") or "").strip()
        if not knowledge_base_id or not query_id:
            return _build_pageindex_status_html("请先选择一条历史记录。", success=False), [], [], "", "", None
        try:
            record = pageindex_service.get_knowledge_base_query_history_record(knowledge_base_id, query_id)
        except AppError as exc:
            return _build_pageindex_status_html(exc.message, success=False), [], [], "", "", None
        return (
            _build_pageindex_status_html(str(record.get("answer") or ""), success=True),
            _build_pageindex_evidence_rows(record.get("evidence") if isinstance(record.get("evidence"), list) else []),
            [],
            str(record.get("query_id") or ""),
            format_operation_result_html(
                {"success": True, "message": "已激活历史记录，可下载。"},
                title="下载结果",
            ),
            None,
        )

    def export_pageindex_results_ui(knowledge_base_choice: str | None, document_choice: str | None, active_query_id: str | None):
        """导出当前激活的 PageIndex 问答记录。"""

        knowledge_base_id = parse_knowledge_base_choice(knowledge_base_choice or "")
        doc_uid = _parse_pageindex_document_choice(document_choice)
        if not knowledge_base_id:
            return _build_pageindex_status_html("请先选择知识库。", success=False), None
        try:
            markdown_text = pageindex_service.export_knowledge_base_query_markdown(knowledge_base_id, active_query_id or "")
            export_result = save_markdown_export(
                settings_runtime_payload.get("sqlite_db_path") or ".",
                module_name="PageIndex",
                result_name="深度检索",
                linked_id=active_query_id or doc_uid,
                markdown_text=markdown_text,
                file_extension="md",
            )
            result_html = format_operation_result_html(
                {
                    "success": True,
                    "message": f'已生成 PageIndex 下载文件：{export_result["file_name"]}。请点击下方“下载文件”。',
                    "preview_url": build_download_url(file_path=export_result["preview_file_path"]),
                    "preview_file_name": export_result["preview_file_name"],
                },
                title="下载结果",
            )
            return result_html, export_result["file_path"]
        except AppError as exc:
            return _build_pageindex_status_html(exc.message, success=False), None

    def _has_tab_access(session: dict[str, object] | None, tab_name: str) -> bool:
        """判断当前登录态是否拥有指定主菜单权限。"""

        if session is None:
            return True
        is_admin, allowed_tabs, _allowed_kb_ids = extract_login_session_permissions(session)
        normalized_tab_name = normalize_auth_tab_name(tab_name)
        return bool(is_admin or allowed_tabs is None or normalized_tab_name in allowed_tabs)

    def _build_empty_document_management_state(selected_choice: str | None = None) -> dict:
        """构建无权限或无可用知识库时的空文档管理状态。"""

        state = build_document_management_state([], [])
        active_choice = selected_choice if selected_choice in state["document_choices"] else state["default_choice"]
        selected_detail = get_document_detail(active_choice, state["document_detail_map"])
        register_button_state, rebuild_button_state = build_document_action_updates(selected_detail)
        return {
            "scan_summary": state["scan_summary"],
            "database_summary": {},
            "table_rows": state["table_rows"],
            "document_choices": state["document_choices"],
            "active_choice": active_choice,
            "selected_detail": selected_detail,
            "knowledge_base_choice": None,
            "register_interactive": register_button_state["interactive"],
            "rebuild_interactive": rebuild_button_state["interactive"],
        }

    def get_document_management_state(
        selected_choice: str | None = None,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> dict:
        """统一构建文档管理页的当前视图状态。"""

        if not _has_tab_access(login_session, "知识库管理"):
            return _build_empty_document_management_state(selected_choice)
        ingest_service.normalize_legacy_default_documents()
        knowledge_base_id = _resolve_authorized_knowledge_base_choice(knowledge_base_choice, login_session)
        if not knowledge_base_id:
            return _build_empty_document_management_state(selected_choice)
        documents = scan_input_documents(ingest_service.settings.input_root, knowledge_base_id)
        status_items, _ = ingest_service.list_status(
            doc_uid=None,
            knowledge_base_id=knowledge_base_id,
            status=None,
            page=1,
            page_size=50,
        )
        status_items = [_resolve_status_item_source_path(item) for item in status_items]
        database_summary = ingest_service.get_database_summary(knowledge_base_id=knowledge_base_id)
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
            "knowledge_base_choice": next(
                (
                    choice
                    for choice in knowledge_base_choices
                    if parse_knowledge_base_choice(choice) == knowledge_base_id
                ),
                default_knowledge_base_choice,
            ),
            "register_interactive": register_button_state["interactive"],
            "rebuild_interactive": rebuild_button_state["interactive"],
        }

    def _resolve_status_item_source_path(item: dict) -> dict:
        """将数据库相对路径转换为 UI 匹配使用的运行期路径。"""

        resolved = dict(item)
        source_path = str(resolved.get("source_path") or "").strip()
        if not source_path:
            return resolved
        try:
            resolved["source_path"] = str(resolve_input_path(source_path, ingest_service.settings.input_root))
        except AppError:
            return resolved
        return resolved

    def build_document_quality_outputs(
        detail: dict | None,
        *,
        query_text: str = "",
    ) -> tuple[str, str, list[list[str]], list[list[str]], str, list[list[str]], list[dict], str]:
        """构建文档管理页中的入库质检与文档内检索验证输出。"""

        resolved_detail = detail or {}
        doc_uid = str(resolved_detail.get("doc_uid") or "")
        doc_title = str(resolved_detail.get("doc_title") or "")
        if not doc_uid:
            return (
                format_operation_result_html({"success": False, "message": "当前文档尚未入库，无法执行入库质检。"}, title="入库质检总览"),
                format_document_quality_checks_html(None),
                [],
                [],
                format_document_quality_search_summary_html(None, doc_title=doc_title),
                [],
                [],
                format_search_result_detail_html(None, query_text=query_text),
            )

        try:
            report = ingest_service.inspect_document_quality(doc_uid)
            report_html = format_document_quality_report_html(report)
            checks_html = format_document_quality_checks_html(report)
            section_rows = build_document_quality_section_rows(report)
            chunk_rows = build_document_quality_chunk_rows(report)
        except AppError as exc:
            report_html = format_operation_result_html(
                {"success": False, "message": exc.message, "error_code": exc.error_code},
                title="入库质检总览",
            )
            checks_html = format_document_quality_checks_html(None)
            section_rows = []
            chunk_rows = []

        normalized_query = normalize_search_query(query_text)
        if not normalized_query:
            return (
                report_html,
                checks_html,
                section_rows,
                chunk_rows,
                format_document_quality_search_summary_html(None, doc_title=doc_title),
                [],
                [],
                format_search_result_detail_html(None, query_text=query_text),
            )

        search_items = retrieval_service.hybrid_search(
            normalized_query,
            top_k=5,
            doc_uid=doc_uid,
            use_rerank=False,
        )
        formatted_search = format_search_results(search_items, query_text=normalized_query)
        search_rows = build_search_result_rows(formatted_search)
        detail_html = format_search_result_detail_html(None, query_text=normalized_query)
        if formatted_search["table"]:
            detail_html = build_search_detail(formatted_search["table"][0], normalized_query)
        return (
            report_html,
            checks_html,
            section_rows,
            chunk_rows,
            format_document_quality_search_summary_html(formatted_search, doc_title=doc_title),
            search_rows,
            formatted_search["table"],
            detail_html,
        )

    def build_document_quality_batch_outputs(
        knowledge_base_choice: str | None = None,
    ) -> tuple[str, list[list[str]]]:
        """构建批量入库质检结果输出。"""

        batch_result = ingest_service.list_document_quality_reports(
            knowledge_base_id=resolve_knowledge_base_choice(knowledge_base_choice),
        )
        return (
            format_document_quality_batch_summary_html(batch_result),
            build_document_quality_batch_rows(batch_result),
        )

    def build_document_quality_config_outputs(
        result_payload: dict | None = None,
    ) -> tuple[str, int, int, int, int, int, int, int, str]:
        """构建入库质检阈值配置输出。"""

        config = ingest_service.get_document_quality_config()
        return (
            format_document_quality_config_html(config),
            int(config["sample_limit"]),
            int(config["long_document_char_threshold"]),
            int(config["min_sections_for_long_doc"]),
            int(config["max_avg_chunks_per_section"]),
            int(config["max_chunk_chars"]),
            int(config["short_chunk_chars"]),
            int(config["short_chunk_warn_min_chunk_count"]),
            format_operation_result_html(result_payload, title="阈值配置结果"),
        )

    def build_document_page_outputs(state: dict) -> tuple[
        str,
        str,
        list[list[str]],
        list[list[str]],
        gr.Dropdown,
        str,
        gr.Button,
        gr.Button,
        str,
        str,
        list[list[str]],
        list[list[str]],
        str,
        list[list[str]],
        list[dict],
        str,
        str,
        list[list[str]],
        str,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        str,
        str,
    ]:
        """将文档管理状态转换为页面组件输出。"""

        quality_outputs = build_document_quality_outputs(state["selected_detail"])
        batch_outputs = build_document_quality_batch_outputs(state.get("knowledge_base_choice"))
        config_outputs = build_document_quality_config_outputs()
        return (
            format_document_summary_html(state["scan_summary"]),
            format_database_summary_html(state["database_summary"]),
            build_database_summary_rows(state["database_summary"]),
            state["table_rows"],
            gr.Dropdown(choices=state["document_choices"], value=state["active_choice"]),
            format_document_detail_html(state["selected_detail"]),
            gr.Button(interactive=state["register_interactive"]),
            gr.Button(interactive=state["rebuild_interactive"]),
            *quality_outputs,
            *batch_outputs,
            *config_outputs,
            format_operation_result_html(None, title="导出结果"),
        )

    def load_document_management_state(
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[
        str,
        str,
        list[list[str]],
        list[list[str]],
        gr.Dropdown,
        str,
        gr.Button,
        gr.Button,
        str,
        str,
        list[list[str]],
        list[list[str]],
        str,
        list[list[str]],
        list[dict],
        str,
        str,
        list[list[str]],
        str,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        str,
        str,
    ]:
        return build_document_page_outputs(
            get_document_management_state(
                knowledge_base_choice=knowledge_base_choice,
                login_session=login_session,
            )
        )

    def load_document_management_state_ui(
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """加载文档管理页，并返回分页后的界面输出。"""

        if login_session is None:
            empty_outputs = build_document_page_outputs(_build_empty_document_management_state())
            return build_document_page_ui_outputs(empty_outputs)
        return build_document_page_ui_outputs(
            load_document_management_state(
                knowledge_base_choice=knowledge_base_choice,
                login_session=login_session,
            )
        )

    def refresh_document_management_state(
        selected_choice: str | None = None,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[
        str,
        str,
        list[list[str]],
        list[list[str]],
        gr.Dropdown,
        str,
        gr.Button,
        gr.Button,
        str,
        str,
        list[list[str]],
        list[list[str]],
        str,
        list[list[str]],
        list[dict],
        str,
        str,
        list[list[str]],
        str,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        str,
        str,
    ]:
        return build_document_page_outputs(
            get_document_management_state(selected_choice, knowledge_base_choice, login_session)
        )

    def refresh_document_management_state_ui(
        selected_choice: str | None = None,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """刷新文档管理页，并返回分页后的界面输出。"""

        return build_document_page_ui_outputs(
            refresh_document_management_state(selected_choice, knowledge_base_choice, login_session)
        )

    def inspect_document(
        choice: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[
        str,
        gr.Button,
        gr.Button,
        str,
        str,
        list[list[str]],
        list[list[str]],
        str,
        list[list[str]],
        list[dict],
        str,
        str,
        list[list[str]],
        str,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        str,
        str,
    ]:
        page_outputs = build_document_page_outputs(
            get_document_management_state(choice, knowledge_base_choice, login_session)
        )
        return page_outputs[5:]

    def inspect_document_ui(
        choice: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """切换文档后，返回分页后的文档详情输出。"""

        outputs = build_document_page_ui_outputs(
            build_document_page_outputs(get_document_management_state(choice, knowledge_base_choice, login_session))
        )
        return outputs[9:]

    def register_selected_document(
        choice: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
        progress=gr.Progress(track_tqdm=False),
    ) -> tuple[
        str,
        str,
        str,
        list[list[str]],
        list[list[str]],
        gr.Dropdown,
        str,
        gr.Button,
        gr.Button,
        str,
        str,
        list[list[str]],
        list[list[str]],
        str,
        list[list[str]],
        list[dict],
        str,
    ]:
        file_path = parse_document_choice(choice)
        knowledge_base_id = _resolve_authorized_knowledge_base_choice(knowledge_base_choice, login_session)
        if not _has_tab_access(login_session, "知识库管理") or not knowledge_base_id:
            refreshed_outputs = refresh_document_management_state(choice, knowledge_base_choice, login_session)
            return (
                format_operation_result_html({"success": False, "message": "当前账号没有知识库管理权限或可用知识库。"}, title="注册结果"),
                *refreshed_outputs,
            )
        if not file_path:
            summary, database_summary, database_rows, table_rows, dropdown, detail, register_state, rebuild_state, qc_report, qc_checks, qc_sections, qc_chunks, qc_search_summary, qc_search_rows, qc_search_state, qc_search_detail, qc_batch_summary, qc_batch_rows, qc_config_panel, qc_sample_limit, qc_long_threshold, qc_min_sections, qc_max_avg_chunks, qc_max_chunk_chars, qc_short_chunk_chars, qc_short_chunk_min_count, qc_config_result, qc_export_result = refresh_document_management_state(choice, knowledge_base_choice, login_session)
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
                qc_report,
                qc_checks,
                qc_sections,
                qc_chunks,
                qc_search_summary,
                qc_search_rows,
                qc_search_state,
                qc_search_detail,
                qc_batch_summary,
                qc_batch_rows,
                qc_config_panel,
                qc_sample_limit,
                qc_long_threshold,
                qc_min_sections,
                qc_max_avg_chunks,
                qc_max_chunk_chars,
                qc_short_chunk_chars,
                qc_short_chunk_min_count,
                qc_config_result,
                qc_export_result,
            )
            
        progress(0, desc="准备执行当前文档注册")
        try:
            job = ingest_service.register_document(
                {"file_path": file_path},
                knowledge_base_id=knowledge_base_id,
                rebuild_if_exists=False,
                progress_callback=lambda info: progress(
                    info["percent"] / 100,
                    desc=f'{info["message"]}（{info["percent"]}%）',
                ),
            )
            payload = format_ingest_result({"success": True, "job": job}, job.get("progress_events", []))
        except AppError as exc:
            payload = {"success": False, "message": exc.message, "error_code": exc.error_code, "details": exc.details}

        summary, database_summary, database_rows, table_rows, dropdown, detail, register_state, rebuild_state, qc_report, qc_checks, qc_sections, qc_chunks, qc_search_summary, qc_search_rows, qc_search_state, qc_search_detail, qc_batch_summary, qc_batch_rows, qc_config_panel, qc_sample_limit, qc_long_threshold, qc_min_sections, qc_max_avg_chunks, qc_max_chunk_chars, qc_short_chunk_chars, qc_short_chunk_min_count, qc_config_result, qc_export_result = refresh_document_management_state(choice, knowledge_base_choice, login_session)
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
            qc_report,
            qc_checks,
            qc_sections,
            qc_chunks,
            qc_search_summary,
            qc_search_rows,
            qc_search_state,
            qc_search_detail,
            qc_batch_summary,
            qc_batch_rows,
            qc_config_panel,
            qc_sample_limit,
            qc_long_threshold,
            qc_min_sections,
            qc_max_avg_chunks,
            qc_max_chunk_chars,
            qc_short_chunk_chars,
            qc_short_chunk_min_count,
            qc_config_result,
            qc_export_result,
        )

    def register_selected_document_ui(
        choice: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
        progress=gr.Progress(track_tqdm=False),
    ) -> tuple:
        """注册当前文档，并返回分页后的文档管理界面输出。"""

        outputs = register_selected_document(choice, knowledge_base_choice, login_session, progress)
        return (outputs[0], *build_document_page_ui_outputs(outputs[1:]))

    def register_all_documents(
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
        progress=gr.Progress(track_tqdm=False),
    ) -> tuple[
        str,
        str,
        str,
        list[list[str]],
        list[list[str]],
        gr.Dropdown,
        str,
        gr.Button,
        gr.Button,
        str,
        str,
        list[list[str]],
        list[list[str]],
        str,
        list[list[str]],
        list[dict],
        str,
    ]:
        knowledge_base_id = _resolve_authorized_knowledge_base_choice(knowledge_base_choice, login_session)
        if not _has_tab_access(login_session, "知识库管理") or not knowledge_base_id:
            refreshed_outputs = refresh_document_management_state(knowledge_base_choice=knowledge_base_choice, login_session=login_session)
            return (
                format_operation_result_html({"success": False, "message": "当前账号没有知识库管理权限或可用知识库。"}, title="批量注册结果"),
                *refreshed_outputs,
            )
        documents = scan_input_documents(ingest_service.settings.input_root, knowledge_base_id)
        if not documents:
            summary, database_summary, database_rows, table_rows, dropdown, detail, register_state, rebuild_state, qc_report, qc_checks, qc_sections, qc_chunks, qc_search_summary, qc_search_rows, qc_search_state, qc_search_detail, qc_batch_summary, qc_batch_rows, qc_config_panel, qc_sample_limit, qc_long_threshold, qc_min_sections, qc_max_avg_chunks, qc_max_chunk_chars, qc_short_chunk_chars, qc_short_chunk_min_count, qc_config_result, qc_export_result = refresh_document_management_state(knowledge_base_choice=knowledge_base_choice, login_session=login_session)
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
                qc_report,
                qc_checks,
                qc_sections,
                qc_chunks,
                qc_search_summary,
                qc_search_rows,
                qc_search_state,
                qc_search_detail,
                qc_batch_summary,
                qc_batch_rows,
                qc_config_panel,
                qc_sample_limit,
                qc_long_threshold,
                qc_min_sections,
                qc_max_avg_chunks,
                qc_max_chunk_chars,
                qc_short_chunk_chars,
                qc_short_chunk_min_count,
                qc_config_result,
                qc_export_result,
            )

        progress(0, desc="准备批量注册文档")
        try:
            jobs = ingest_service.register_documents(
                [{"file_path": item["file_path"]} for item in documents],
                knowledge_base_id=knowledge_base_id,
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

        summary, database_summary, database_rows, table_rows, dropdown, detail, register_state, rebuild_state, qc_report, qc_checks, qc_sections, qc_chunks, qc_search_summary, qc_search_rows, qc_search_state, qc_search_detail, qc_batch_summary, qc_batch_rows, qc_config_panel, qc_sample_limit, qc_long_threshold, qc_min_sections, qc_max_avg_chunks, qc_max_chunk_chars, qc_short_chunk_chars, qc_short_chunk_min_count, qc_config_result, qc_export_result = refresh_document_management_state(knowledge_base_choice=knowledge_base_choice, login_session=login_session)
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
            qc_report,
            qc_checks,
            qc_sections,
            qc_chunks,
            qc_search_summary,
            qc_search_rows,
            qc_search_state,
            qc_search_detail,
            qc_batch_summary,
            qc_batch_rows,
            qc_config_panel,
            qc_sample_limit,
            qc_long_threshold,
            qc_min_sections,
            qc_max_avg_chunks,
            qc_max_chunk_chars,
            qc_short_chunk_chars,
            qc_short_chunk_min_count,
            qc_config_result,
            qc_export_result,
        )

    def register_all_documents_ui(
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
        progress=gr.Progress(track_tqdm=False),
    ) -> tuple:
        """批量注册文档，并返回分页后的文档管理界面输出。"""

        if login_session is None:
            empty_outputs = build_document_page_outputs(_build_empty_document_management_state())
            return (
                format_operation_result_html(
                    {"success": False, "message": "当前账号没有知识库管理权限或可用知识库。"},
                    title="批量注册结果",
                ),
                *build_document_page_ui_outputs(empty_outputs),
            )
        outputs = register_all_documents(knowledge_base_choice, login_session, progress)
        return (outputs[0], *build_document_page_ui_outputs(outputs[1:]))

    def reassign_selected_document(
        choice: str,
        target_knowledge_base_choice: str | None,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[
        str,
        str,
        str,
        list[list[str]],
        list[list[str]],
        gr.Dropdown,
        str,
        gr.Button,
        gr.Button,
        str,
        str,
        list[list[str]],
        list[list[str]],
        str,
        list[list[str]],
        list[dict],
        str,
        str,
        list[list[str]],
        str,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        str,
        str,
    ]:
        """调整当前文档归属知识库，并刷新文档管理页。"""

        file_path = parse_document_choice(choice)
        current_knowledge_base_id = _resolve_authorized_knowledge_base_choice(knowledge_base_choice, login_session)
        target_knowledge_base_id = parse_knowledge_base_choice(target_knowledge_base_choice or "")
        if not _has_tab_access(login_session, "知识库管理") or not current_knowledge_base_id:
            refreshed_outputs = refresh_document_management_state(knowledge_base_choice=knowledge_base_choice, login_session=login_session)
            return (
                format_operation_result_html({"success": False, "message": "当前账号没有知识库管理权限或可用知识库。"}, title="归属调整结果"),
                *refreshed_outputs,
            )
        if not file_path:
            refreshed_outputs = refresh_document_management_state(knowledge_base_choice=knowledge_base_choice, login_session=login_session)
            return (
                format_operation_result_html({"success": False, "message": "请选择文档"}, title="归属调整结果"),
                *refreshed_outputs,
            )
        if not target_knowledge_base_id:
            refreshed_outputs = refresh_document_management_state(choice, knowledge_base_choice, login_session)
            return (
                format_operation_result_html({"success": False, "message": "请选择目标知识库"}, title="归属调整结果"),
                *refreshed_outputs,
            )

        selected_detail = get_document_management_state(choice, knowledge_base_choice, login_session)["selected_detail"]
        try:
            moved_item = ingest_service.relocate_document_to_knowledge_base(
                source_path=file_path,
                target_knowledge_base_id=target_knowledge_base_id,
                doc_uid=str(selected_detail.get("doc_uid") or "") or None,
            )
            payload = {
                "success": True,
                "message": (
                    f'文档已调整到知识库“{target_knowledge_base_id}”，'
                    f'当前路径：{moved_item.get("source_path") or file_path}'
                ),
            }
        except AppError as exc:
            payload = {"success": False, "message": exc.message, "error_code": exc.error_code, "details": exc.details}

        refreshed_outputs = refresh_document_management_state(knowledge_base_choice=knowledge_base_choice, login_session=login_session)
        return (format_operation_result_html(payload, title="归属调整结果"), *refreshed_outputs)

    def reassign_selected_document_ui(
        choice: str,
        target_knowledge_base_choice: str | None,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """调整当前文档归属知识库，并返回分页后的文档管理界面输出。"""

        outputs = reassign_selected_document(choice, target_knowledge_base_choice, knowledge_base_choice, login_session)
        return (outputs[0], *build_document_page_ui_outputs(outputs[1:]))

    def query_ingest_status(
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[
        str,
        str,
        list[list[str]],
        list[list[str]],
        gr.Dropdown,
        str,
        gr.Button,
        gr.Button,
        str,
        str,
        list[list[str]],
        list[list[str]],
        str,
        list[list[str]],
        list[dict],
        str,
    ]:
        return refresh_document_management_state(knowledge_base_choice=knowledge_base_choice, login_session=login_session)

    def query_ingest_status_ui(
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """刷新入库状态，并返回分页后的文档管理界面输出。"""

        return build_document_page_ui_outputs(query_ingest_status(knowledge_base_choice, login_session))

    def rebuild_selected_document(
        choice: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
        progress=gr.Progress(track_tqdm=False),
    ) -> tuple[
        str,
        str,
        str,
        list[list[str]],
        list[list[str]],
        gr.Dropdown,
        str,
        gr.Button,
        gr.Button,
        str,
        str,
        list[list[str]],
        list[list[str]],
        str,
        list[list[str]],
        list[dict],
        str,
    ]:
        current_knowledge_base_id = _resolve_authorized_knowledge_base_choice(knowledge_base_choice, login_session)
        if not _has_tab_access(login_session, "知识库管理") or not current_knowledge_base_id:
            refreshed_outputs = refresh_document_management_state(choice, knowledge_base_choice, login_session)
            return (
                format_operation_result_html({"success": False, "message": "当前账号没有知识库管理权限或可用知识库。"}, title="重建结果"),
                *refreshed_outputs,
            )
        current_state = get_document_management_state(choice, knowledge_base_choice, login_session)
        doc_uid = current_state["selected_detail"].get("doc_uid")
        if not doc_uid:
            summary, database_summary, database_rows, table_rows, dropdown, current_detail, register_state, rebuild_state, qc_report, qc_checks, qc_sections, qc_chunks, qc_search_summary, qc_search_rows, qc_search_state, qc_search_detail, qc_batch_summary, qc_batch_rows, qc_config_panel, qc_sample_limit, qc_long_threshold, qc_min_sections, qc_max_avg_chunks, qc_max_chunk_chars, qc_short_chunk_chars, qc_short_chunk_min_count, qc_config_result, qc_export_result = refresh_document_management_state(choice, knowledge_base_choice, login_session)
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
                qc_report,
                qc_checks,
                qc_sections,
                qc_chunks,
                qc_search_summary,
                qc_search_rows,
                qc_search_state,
                qc_search_detail,
                qc_batch_summary,
                qc_batch_rows,
                qc_config_panel,
                qc_sample_limit,
                qc_long_threshold,
                qc_min_sections,
                qc_max_avg_chunks,
                qc_max_chunk_chars,
                qc_short_chunk_chars,
                qc_short_chunk_min_count,
                qc_config_result,
                qc_export_result,
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

        summary, database_summary, database_rows, table_rows, dropdown, current_detail, register_state, rebuild_state, qc_report, qc_checks, qc_sections, qc_chunks, qc_search_summary, qc_search_rows, qc_search_state, qc_search_detail, qc_batch_summary, qc_batch_rows, qc_config_panel, qc_sample_limit, qc_long_threshold, qc_min_sections, qc_max_avg_chunks, qc_max_chunk_chars, qc_short_chunk_chars, qc_short_chunk_min_count, qc_config_result, qc_export_result = refresh_document_management_state(choice, knowledge_base_choice, login_session)
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
            qc_report,
            qc_checks,
            qc_sections,
            qc_chunks,
            qc_search_summary,
            qc_search_rows,
            qc_search_state,
            qc_search_detail,
            qc_batch_summary,
            qc_batch_rows,
            qc_config_panel,
            qc_sample_limit,
            qc_long_threshold,
            qc_min_sections,
            qc_max_avg_chunks,
            qc_max_chunk_chars,
            qc_short_chunk_chars,
            qc_short_chunk_min_count,
            qc_config_result,
            qc_export_result,
        )

    def rebuild_selected_document_ui(
        choice: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
        progress=gr.Progress(track_tqdm=False),
    ) -> tuple:
        """重建当前文档，并返回分页后的文档管理界面输出。"""

        outputs = rebuild_selected_document(choice, knowledge_base_choice, login_session, progress)
        return (outputs[0], *build_document_page_ui_outputs(outputs[1:]))

    def inspect_selected_document_quality(
        choice: str,
        knowledge_base_choice: str | None = None,
    ) -> tuple[str, str, list[list[str]], list[list[str]], str, list[list[str]], list[dict], str]:
        """执行当前文档的入库质检，并返回总览、抽样与检索验证默认视图。"""

        state = get_document_management_state(choice, knowledge_base_choice)
        return build_document_quality_outputs(state["selected_detail"])

    def inspect_selected_document_quality_ui(
        choice: str,
        knowledge_base_choice: str | None = None,
    ) -> tuple[str, str, list[list[object]], int, str, list[list[object]], int, str, str, list[list[object]], int, str, list[dict], str]:
        """执行当前文档入库质检，并返回分页后的相关表格。"""

        report_html, checks_html, section_rows, chunk_rows, search_summary, search_rows, search_state, search_detail = inspect_selected_document_quality(
            choice,
            knowledge_base_choice,
        )
        section_page_rows, section_page, section_page_info = build_document_table_page_outputs(
            section_rows,
            prepend_sequence=True,
        )
        chunk_page_rows, chunk_page, chunk_page_info = build_document_table_page_outputs(
            chunk_rows,
            prepend_sequence=True,
        )
        search_page_rows, search_page, search_page_info = build_document_table_page_outputs(
            search_rows,
            prepend_sequence=False,
        )
        return (
            report_html,
            checks_html,
            section_page_rows,
            section_page,
            section_page_info,
            chunk_page_rows,
            chunk_page,
            chunk_page_info,
            search_summary,
            search_page_rows,
            search_page,
            search_page_info,
            search_state,
            search_detail,
        )

    def run_document_quality_search(
        choice: str,
        query_text: str,
        knowledge_base_choice: str | None = None,
    ) -> tuple[str, list[list[str]], list[dict], str, str]:
        """在当前文档范围内执行检索验证。"""

        state = get_document_management_state(choice, knowledge_base_choice)
        outputs = build_document_quality_outputs(state["selected_detail"], query_text=query_text)
        normalized_query = normalize_search_query(query_text)
        return outputs[4], outputs[5], outputs[6], normalized_query, outputs[7]

    def run_document_quality_search_ui(
        choice: str,
        query_text: str,
        knowledge_base_choice: str | None = None,
    ) -> tuple[str, list[list[object]], int, str, list[dict], str, str]:
        """在当前文档范围内执行检索验证，并返回分页后的表格输出。"""

        summary_html, search_rows, search_state, normalized_query, detail_html = run_document_quality_search(
            choice,
            query_text,
            knowledge_base_choice,
        )
        page_rows, page_value, page_info = build_document_table_page_outputs(
            search_rows,
            prepend_sequence=False,
        )
        return summary_html, page_rows, page_value, page_info, search_state, normalized_query, detail_html

    def run_batch_document_quality(
        knowledge_base_choice: str | None = None,
    ) -> tuple[str, list[list[str]]]:
        """执行全部文档的批量入库质检。"""

        return build_document_quality_batch_outputs(knowledge_base_choice)

    def run_batch_document_quality_ui(
        knowledge_base_choice: str | None = None,
    ) -> tuple[str, list[list[object]], int, str]:
        """执行全部文档质检，并返回分页后的批量结果。"""

        summary_html, batch_rows = run_batch_document_quality(knowledge_base_choice)
        page_rows, page_value, page_info = build_document_table_page_outputs(
            batch_rows,
            prepend_sequence=True,
        )
        return summary_html, page_rows, page_value, page_info

    def change_database_summary_page(
        choice: str,
        knowledge_base_choice: str | None,
        current_page: int | float,
        action: str,
    ) -> tuple[list[list[object]], int, str]:
        """切换数据库统计表分页。"""

        rows = build_database_summary_rows(get_document_management_state(choice, knowledge_base_choice)["database_summary"])
        return change_document_table_page(rows, current_page, action, prepend_sequence=True)

    def change_document_list_page(
        choice: str,
        knowledge_base_choice: str | None,
        current_page: int | float,
        action: str,
    ) -> tuple[list[list[object]], int, str]:
        """切换文档列表分页。"""

        rows = get_document_management_state(choice, knowledge_base_choice)["table_rows"]
        return change_document_table_page(rows, current_page, action, prepend_sequence=True)

    def change_document_quality_sections_page(
        choice: str,
        knowledge_base_choice: str | None,
        current_page: int | float,
        action: str,
    ) -> tuple[list[list[object]], int, str]:
        """切换章节抽样分页。"""

        rows = build_document_quality_outputs(get_document_management_state(choice, knowledge_base_choice)["selected_detail"])[2]
        return change_document_table_page(rows, current_page, action, prepend_sequence=True)

    def change_document_quality_chunks_page(
        choice: str,
        knowledge_base_choice: str | None,
        current_page: int | float,
        action: str,
    ) -> tuple[list[list[object]], int, str]:
        """切换分块抽样分页。"""

        rows = build_document_quality_outputs(get_document_management_state(choice, knowledge_base_choice)["selected_detail"])[3]
        return change_document_table_page(rows, current_page, action, prepend_sequence=True)

    def change_document_quality_batch_page(
        knowledge_base_choice: str | None,
        current_page: int | float,
        action: str,
    ) -> tuple[list[list[object]], int, str]:
        """切换批量质检结果分页。"""

        rows = build_document_quality_batch_outputs(knowledge_base_choice)[1]
        return change_document_table_page(rows, current_page, action, prepend_sequence=True)

    def export_document_quality_csv(knowledge_base_choice: str | None = None) -> str:
        """导出全部文档的入库质检结果。"""

        try:
            export_result = ingest_service.export_document_quality_reports_csv(
                knowledge_base_id=resolve_knowledge_base_choice(knowledge_base_choice),
            )
            return format_operation_result_html(
                {
                    "success": True,
                    "message": f'已导出 {export_result["row_count"]} 条质检结果。',
                    "linked_check_id": export_result["file_path"],
                },
                title="导出结果",
            )
        except AppError as exc:
            return format_operation_result_html(
                {"success": False, "message": exc.message, "error_code": exc.error_code},
                title="导出结果",
            )

    def save_document_quality_config(
        sample_limit: int | float,
        long_document_char_threshold: int | float,
        min_sections_for_long_doc: int | float,
        max_avg_chunks_per_section: int | float,
        max_chunk_chars: int | float,
        short_chunk_chars: int | float,
        short_chunk_warn_min_chunk_count: int | float,
    ) -> tuple[str, int, int, int, int, int, int, int, str]:
        """保存入库质检阈值配置。"""

        payload = {
            "sample_limit": sample_limit,
            "long_document_char_threshold": long_document_char_threshold,
            "min_sections_for_long_doc": min_sections_for_long_doc,
            "max_avg_chunks_per_section": max_avg_chunks_per_section,
            "max_chunk_chars": max_chunk_chars,
            "short_chunk_chars": short_chunk_chars,
            "short_chunk_warn_min_chunk_count": short_chunk_warn_min_chunk_count,
        }
        try:
            ingest_service.save_document_quality_config(payload)
        except AppError as exc:
            return build_document_quality_config_outputs(
                {"success": False, "message": exc.message, "error_code": exc.error_code},
            )
        return build_document_quality_config_outputs(
            {"success": True, "message": "入库质检阈值已保存。"},
        )

    def export_markdown_result(module_name: str, result_name: str, markdown_text: str, *, linked_id: str | None = None) -> str:
        """将 Markdown 结果导出为 TXT 文件，并返回包含下载链接的结果提示。"""

        try:
            export_result = save_markdown_export(
                settings_runtime_payload.get("sqlite_db_path") or ".",
                module_name=module_name,
                result_name=result_name,
                linked_id=linked_id,
                markdown_text=markdown_text,
            )
            return format_operation_result_html(
                {
                    "success": True,
                    "message": f'已生成下载文件：{export_result["file_name"]}',
                    "download_url": build_download_url(
                        file_path=export_result["file_path"],
                    ),
                    "download_file_name": export_result["file_name"],
                    "preview_url": build_download_url(
                        file_path=export_result["preview_file_path"],
                    ),
                    "preview_file_name": export_result["preview_file_name"],
                },
                title="下载结果",
            )
        except AppError as exc:
            return format_operation_result_html(
                {"success": False, "message": exc.message, "error_code": exc.error_code},
                title="下载结果",
            )

    # 检索页处理器由独立模块实现；此处仅注入当前应用实例依赖并保留回调函数名。
    build_search_detail_payload = update_wrapper(
        partial(search_build_search_detail_payload, retrieval_service=retrieval_service),
        search_build_search_detail_payload,
    )
    build_search_detail = update_wrapper(
        partial(search_build_search_detail, retrieval_service=retrieval_service),
        search_build_search_detail,
    )
    export_search_results = update_wrapper(
        partial(search_export_search_results, export_markdown_result=export_markdown_result),
        search_export_search_results,
    )
    run_search_ui = update_wrapper(
        partial(
            search_run_search_ui,
            retrieval_service=retrieval_service,
            has_tab_access=_has_tab_access,
            resolve_authorized_knowledge_base=_resolve_authorized_knowledge_base_choice,
        ),
        search_run_search_ui,
    )
    select_search_result = update_wrapper(
        partial(search_select_search_result, retrieval_service=retrieval_service),
        search_select_search_result,
    )

    def build_document_table_page_outputs(
        rows: object,
        page: int | float | None = 1,
        *,
        prepend_sequence: bool,
    ) -> tuple[list[list[object]], int, str]:
        """构建文档管理页表格的分页输出。"""

        page_rows, resolved_page, _total_pages, page_info = paginate_table_rows(
            rows,
            page,
            prepend_sequence=prepend_sequence,
        )
        return page_rows, resolved_page, format_table_pagination_html(page_info)

    def change_document_table_page(
        rows: object,
        current_page: int | float,
        action: str,
        *,
        prepend_sequence: bool,
    ) -> tuple[list[list[object]], int, str]:
        """切换文档管理页表格分页。"""

        page_rows, new_page, page_info = change_table_page(
            rows,
            current_page,
            action=action,
            prepend_sequence=prepend_sequence,
        )
        return page_rows, new_page, format_table_pagination_html(page_info)

    def build_document_page_ui_outputs(base_outputs: tuple) -> tuple:
        """将文档管理基础输出扩展为带分页状态的界面输出。"""

        database_rows = base_outputs[2]
        document_rows = base_outputs[3]
        section_rows = base_outputs[10]
        chunk_rows = base_outputs[11]
        search_rows = base_outputs[13]
        batch_rows = base_outputs[17]
        database_page_rows, database_page, database_page_info = build_document_table_page_outputs(
            database_rows,
            prepend_sequence=True,
        )
        document_page_rows, document_page, document_page_info = build_document_table_page_outputs(
            document_rows,
            prepend_sequence=True,
        )
        section_page_rows, section_page, section_page_info = build_document_table_page_outputs(
            section_rows,
            prepend_sequence=True,
        )
        chunk_page_rows, chunk_page, chunk_page_info = build_document_table_page_outputs(
            chunk_rows,
            prepend_sequence=True,
        )
        search_page_rows, search_page, search_page_info = build_document_table_page_outputs(
            search_rows,
            prepend_sequence=False,
        )
        batch_page_rows, batch_page, batch_page_info = build_document_table_page_outputs(
            batch_rows,
            prepend_sequence=True,
        )
        return (
            base_outputs[0],
            base_outputs[1],
            database_page_rows,
            database_page,
            database_page_info,
            document_page_rows,
            document_page,
            document_page_info,
            base_outputs[4],
            base_outputs[5],
            base_outputs[6],
            base_outputs[7],
            base_outputs[8],
            base_outputs[9],
            section_page_rows,
            section_page,
            section_page_info,
            chunk_page_rows,
            chunk_page,
            chunk_page_info,
            base_outputs[12],
            search_page_rows,
            search_page,
            search_page_info,
            base_outputs[14],
            base_outputs[15],
            base_outputs[16],
            batch_page_rows,
            batch_page,
            batch_page_info,
            base_outputs[18],
            base_outputs[19],
            base_outputs[20],
            base_outputs[21],
            base_outputs[22],
            base_outputs[23],
            base_outputs[24],
            base_outputs[25],
            base_outputs[26],
            base_outputs[27],
        )

    def build_quality_claim_table_page_outputs(
        formatted_result: dict | None,
        page: int | float | None = 1,
    ) -> tuple[list[list[object]], int, str]:
        """构建 AI 质检 Claim 表格分页输出。"""

        full_rows = build_quality_claim_rows(formatted_result)
        page_rows, resolved_page, _total_pages, page_info = paginate_table_rows(
            full_rows,
            page,
            prepend_sequence=True,
        )
        return page_rows, resolved_page, format_table_pagination_html(page_info)

    def build_quality_claim_selector_page_outputs(
        formatted_result: dict | None,
        selected_claim: str | None = None,
        page: int | float | None = 1,
    ) -> tuple[list[str], str | None, int, str]:
        """构建 AI 质检 Claim 可选列表分页输出。"""

        full_rows = build_quality_claim_rows(formatted_result)
        page_rows, resolved_page, _total_pages, page_info = paginate_table_rows(
            full_rows,
            page,
            prepend_sequence=False,
        )
        start_index = (resolved_page - 1) * TABLE_PAGE_SIZE
        choice_map: dict[str, str] = {}
        for offset, row in enumerate(page_rows):
            claim_id = str(row[0]) if row else ""
            if not claim_id:
                continue
            claim_text = str(row[1]) if len(row) > 1 else ""
            verdict_text = str(row[2]) if len(row) > 2 else "-"
            risk_text = str(row[3]) if len(row) > 3 else "-"
            choice_map[claim_id] = (
                f"{claim_id} | 第 {start_index + offset + 1} 条 | {verdict_text} | {risk_text} | {claim_text[:48]}"
            )
        choices = list(choice_map.values())
        selected_claim_id = parse_claim_choice(selected_claim or "")
        if selected_claim_id not in choice_map and choice_map:
            selected_claim_id = next(iter(choice_map))
        selected_choice = choice_map.get(selected_claim_id)
        return choices, selected_choice, resolved_page, format_table_pagination_html(page_info)

    def build_quality_evidence_rows_from_items(evidence_items: list[dict] | None) -> list[list[str]]:
        """根据证据项直接构建证据表格行，避免分页后依赖详情对象。"""

        return build_claim_evidence_rows({"evidence_table": evidence_items or []})

    def build_quality_evidence_table_page_outputs(
        evidence_items: list[dict] | None,
        page: int | float | None = 1,
    ) -> tuple[list[list[object]], int, str]:
        """构建 AI 质检证据表格分页输出。"""

        full_rows = build_quality_evidence_rows_from_items(evidence_items)
        page_rows, resolved_page, _total_pages, page_info = paginate_table_rows(
            full_rows,
            page,
            prepend_sequence=True,
        )
        return page_rows, resolved_page, format_table_pagination_html(page_info)

    def build_recent_quality_table_page_outputs(
        recent_results: list[dict] | None,
        page: int | float | None = 1,
    ) -> tuple[list[list[object]], int, str]:
        """构建最近质检记录分页输出。"""

        recent_payload = format_recent_quality_checks(recent_results or [])
        full_rows = build_recent_quality_rows(recent_payload)
        page_rows, resolved_page, _total_pages, page_info = paginate_table_rows(
            full_rows,
            page,
            prepend_sequence=True,
        )
        return page_rows, resolved_page, format_table_pagination_html(page_info)

    def normalize_recent_quality_scope_value(scope_value: str | None) -> str:
        """规范历史质检记录筛选值。"""

        value = str(scope_value or "").strip()
        return value if value in recent_quality_scope_choices else recent_quality_scope_choices[0]

    def filter_recent_quality_results(
        recent_results: list[dict] | None,
        scope_value: str | None,
    ) -> list[dict]:
        """按待处理 Claim 情况过滤历史质检任务。"""

        normalized_scope = normalize_recent_quality_scope_value(scope_value)
        results = list(recent_results or [])
        if normalized_scope != "仅看含待处理 Claim":
            return results
        return [
            item
            for item in results
            if any(
                str(claim.get("review_status") or "pending").lower() == "pending"
                for claim in (item.get("claims") or [])
            )
        ]

    def build_quality_evaluation_table_page_outputs(
        evaluation_result: dict | None,
        page: int | float | None = 1,
    ) -> tuple[list[list[object]], int, str]:
        """构建效果评测明细分页输出。"""

        full_rows = build_quality_evaluation_rows(evaluation_result)
        page_rows, resolved_page, _total_pages, page_info = paginate_table_rows(
            full_rows,
            page,
            prepend_sequence=True,
        )
        return page_rows, resolved_page, format_table_pagination_html(page_info)

    def build_settings_template_table_page_outputs(
        template_items: list[dict] | None,
        page: int | float | None = 1,
    ) -> tuple[list[list[object]], int, str]:
        """构建功能设置模板表分页输出。"""

        full_rows = build_settings_template_rows(template_items or [])
        page_rows, resolved_page, _total_pages, page_info = paginate_table_rows(
            full_rows,
            page,
            prepend_sequence=True,
        )
        return page_rows, resolved_page, format_table_pagination_html(page_info)

    def build_settings_knowledge_base_table_page_outputs(
        knowledge_base_items: list[dict] | None,
        page: int | float | None = 1,
    ) -> tuple[list[list[object]], int, str]:
        """构建功能设置知识库表分页输出。"""

        full_rows = build_settings_knowledge_base_rows(knowledge_base_items or [])
        page_rows, resolved_page, _total_pages, page_info = paginate_table_rows(
            full_rows,
            page,
            prepend_sequence=True,
        )
        return page_rows, resolved_page, format_table_pagination_html(page_info)

    def build_settings_knowledge_base_selector_page_outputs(
        knowledge_base_items: list[dict] | None,
        selected_knowledge_base_id: str | None = None,
        page: int | float | None = 1,
    ) -> tuple[list[str], str | None, int, str]:
        """构建功能设置知识库可选列表分页输出。"""

        full_rows = build_settings_knowledge_base_rows(knowledge_base_items or [])
        page_rows, resolved_page, _total_pages, page_info = paginate_table_rows(
            full_rows,
            page,
            prepend_sequence=False,
        )
        start_index = (resolved_page - 1) * TABLE_PAGE_SIZE
        choice_map: dict[str, str] = {}
        for offset, row in enumerate(page_rows):
            knowledge_base_id = str(row[0]) if row else ""
            if not knowledge_base_id:
                continue
            knowledge_base_name = str(row[1]) if len(row) > 1 else ""
            description = str(row[2]) if len(row) > 2 else ""
            is_default = str(row[3]) if len(row) > 3 else "否"
            status = str(row[4]) if len(row) > 4 else "-"
            description_preview = description[:24] if description not in ("", "-") else ""
            choice_text = (
                f"{knowledge_base_id} | 第 {start_index + offset + 1} 条 | "
                f"{knowledge_base_name} | 默认:{is_default} | 状态:{status}"
            )
            if description_preview:
                choice_text = f"{choice_text} | {description_preview}"
            choice_map[knowledge_base_id] = choice_text
        choices = list(choice_map.values())
        normalized_knowledge_base_id = str(selected_knowledge_base_id or "")
        if normalized_knowledge_base_id not in choice_map and choice_map:
            normalized_knowledge_base_id = next(iter(choice_map))
        selected_choice = choice_map.get(normalized_knowledge_base_id)
        return choices, selected_choice, resolved_page, format_table_pagination_html(page_info)

    def build_quality_ui_outputs(
        base_outputs: tuple,
        *,
        claim_page: int | float | None = 1,
        evidence_page: int | float | None = 1,
        recent_page: int | float | None = 1,
    ) -> tuple:
        """将 AI 质检基础输出扩展为带分页状态的 UI 输出。"""

        (
            progress_html,
            result_html,
            formatted_result,
            claim_rows,
            selected_claim,
            claim_detail_map,
            claim_view,
            evidence_rows,
            review_view,
            evidence_items,
            evidence_detail_html,
            recent_results,
            recent_rows,
            evaluation_cases_text,
        ) = base_outputs
        claim_choices, resolved_selected_claim, claim_page_value, claim_page_info = build_quality_claim_selector_page_outputs(
            formatted_result,
            selected_claim,
            claim_page,
        )
        if resolved_selected_claim != selected_claim:
            claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(
                resolved_selected_claim or "",
                claim_detail_map,
            )
            evaluation_cases_text = build_quality_evaluation_example_text(
                formatted_result,
                resolved_selected_claim or "",
                claim_detail_map,
            )
        evidence_page_rows, evidence_page_value, evidence_page_info = build_quality_evidence_table_page_outputs(
            evidence_items,
            evidence_page,
        )
        recent_page_rows, recent_page_value, recent_page_info = build_recent_quality_table_page_outputs(
            recent_results,
            recent_page,
        )
        return (
            progress_html,
            result_html,
            format_active_quality_check_html(formatted_result),
            formatted_result,
            gr.update(choices=claim_choices, value=resolved_selected_claim),
            claim_page_value,
            claim_page_info,
            resolved_selected_claim or "",
            claim_detail_map,
            claim_view,
            evidence_page_rows,
            evidence_page_value,
            evidence_page_info,
            review_view,
            evidence_items,
            evidence_detail_html,
            recent_results,
            recent_page_rows,
            recent_page_value,
            recent_page_info,
            evaluation_cases_text,
        )

    def build_review_workspace_ui_outputs(
        base_outputs: tuple,
        *,
        pending_page: int | float | None = 1,
        processed_page: int | float | None = 1,
        evidence_page: int | float | None = 1,
        history_page: int | float | None = 1,
    ) -> tuple:
        """将人工审核基础输出扩展为带分页状态的 UI 输出。"""

        (
            pending_rows,
            processed_rows,
            candidate_items,
            selected_claim_id,
            claim_detail_map,
            claim_view,
            evidence_rows,
            evidence_items,
            evidence_detail_html,
            action_value,
            note_value,
            review_rows,
            review_items,
            selected_review_id,
            review_detail_html,
        ) = base_outputs
        pending_page_rows, pending_page_value, _pending_total_pages, pending_page_info = paginate_table_rows(
            pending_rows,
            pending_page,
            prepend_sequence=True,
        )
        processed_page_rows, processed_page_value, _processed_total_pages, processed_page_info = paginate_table_rows(
            processed_rows,
            processed_page,
            prepend_sequence=True,
        )
        evidence_page_rows, evidence_page_value, _evidence_total_pages, evidence_page_info = paginate_table_rows(
            evidence_rows,
            evidence_page,
            prepend_sequence=True,
        )
        review_page_rows, review_page_value, _review_total_pages, review_page_info = paginate_table_rows(
            review_rows,
            history_page,
            prepend_sequence=True,
        )
        return (
            pending_page_rows,
            pending_page_value,
            format_table_pagination_html(pending_page_info),
            processed_page_rows,
            processed_page_value,
            format_table_pagination_html(processed_page_info),
            candidate_items,
            selected_claim_id,
            claim_detail_map,
            claim_view,
            evidence_page_rows,
            evidence_page_value,
            format_table_pagination_html(evidence_page_info),
            evidence_items,
            evidence_detail_html,
            action_value,
            note_value,
            review_page_rows,
            review_page_value,
            format_table_pagination_html(review_page_info),
            review_items,
            selected_review_id,
            review_detail_html,
        )

    def build_settings_workspace_ui_outputs(
        base_outputs: tuple,
        *,
        page: int | float | None = 1,
    ) -> tuple:
        """将功能设置基础输出扩展为带分页状态的 UI 输出。"""

        page_rows, page_value, page_info = build_settings_template_table_page_outputs(
            base_outputs[1],
            page,
        )
        template_items = base_outputs[1] if isinstance(base_outputs[1], list) else []
        template_kind = str((template_items[0] or {}).get("settings_template_kind") or "AI质检") if template_items else "AI质检"
        is_pageindex = template_kind == "PageIndex"
        kind_hint = (
            "<div class='settings-kind-hint'>当前管理 PageIndex 回答模板，保存到 "
            "<code>templates/pageindex</code>，用于 PageIndex 深度检索最终回答。</div>"
            if is_pageindex
            else "<div class='settings-kind-hint'>当前管理 AI 质检模板，保存到 "
            "<code>templates/quality</code>，用于 Claim 质检与证据判断。</div>"
        )
        return (
            page_rows,
            page_value,
            page_info,
            kind_hint,
            base_outputs[1],
            base_outputs[2],
            base_outputs[3],
            base_outputs[4],
            base_outputs[5],
            base_outputs[6],
            gr.update(value=base_outputs[7], label="规则标签", visible=not is_pageindex),
            gr.update(value=base_outputs[8], label="树候选节点" if is_pageindex else "全文召回"),
            gr.update(value=base_outputs[9], label="选中节点" if is_pageindex else "向量召回"),
            gr.update(value=base_outputs[10], label="RAG/FTS 证据" if is_pageindex else "最终返回"),
            gr.update(value=base_outputs[11], visible=not is_pageindex),
            gr.update(value=base_outputs[12], label="邻居窗口", visible=not is_pageindex),
            gr.update(value=base_outputs[13], label="结构上下文" if is_pageindex else "章节上下文"),
            gr.update(value=base_outputs[14], label="章节最大字数", visible=not is_pageindex),
            base_outputs[15],
            base_outputs[16],
            base_outputs[17],
            base_outputs[18],
            base_outputs[19],
        )

    def build_settings_knowledge_base_workspace_ui_outputs(
        base_outputs: tuple,
        *,
        page: int | float | None = 1,
    ) -> tuple:
        """将知识库设置基础输出扩展为带分页状态的 UI 输出。"""

        selector_choices, selected_choice, page_value, page_info = build_settings_knowledge_base_selector_page_outputs(
            base_outputs[1],
            base_outputs[2],
            page,
        )
        resolved_knowledge_base_id = parse_knowledge_base_choice(selected_choice or "")
        if resolved_knowledge_base_id != str(base_outputs[2] or ""):
            base_outputs = build_settings_knowledge_base_workspace(resolved_knowledge_base_id)
        return (
            gr.update(choices=selector_choices, value=selected_choice),
            page_value,
            page_info,
            *base_outputs[1:],
        )

    def select_document_quality_search_result(
        results: list[dict],
        query_text: str,
        evt: gr.SelectData,
        current_page_rows: list[list[object]] | None = None,
    ) -> tuple[str, list[list[object]]]:
        """点击文档内检索结果后，展示对应原文详情。"""

        page_rows = normalize_table_rows(current_page_rows) if current_page_rows is not None else build_search_result_rows({"table": results or []})
        raw_rows = results or []
        if not page_rows or not raw_rows:
            return format_search_result_detail_html(None, query_text=query_text), page_rows
        matched_row = get_selected_search_item_from_page_rows(page_rows, raw_rows, evt)
        if not matched_row:
            return format_search_result_detail_html(None, query_text=query_text), page_rows
        return build_search_detail(matched_row, query_text), page_rows

    def render_claim_views(claim_choice: str, claim_detail_map: dict | None) -> tuple[str, list[list[str]], str, list[dict], str]:
        """统一渲染 Claim 摘要与证据表。"""

        detail = format_claim_detail_for_review(claim_choice, claim_detail_map)
        detail_html = format_claim_detail_html(detail)
        evidence_items = detail.get("evidence_table") or []
        evidence_detail_html = format_evidence_detail_html(evidence_items[0] if evidence_items else None)
        return detail_html, build_claim_evidence_rows(detail), detail_html, evidence_items, evidence_detail_html

    def select_quality_claim(
        claim_rows: list[list[object]],
        claim_detail_map: dict | None,
        formatted_result: dict | None,
        evt: gr.SelectData,
    ) -> tuple[str, list[list[str]], str, str, list[dict], str, str]:
        """点击 Claim 列表后联动详情与证据区域。"""

        normalized_rows = claim_rows.values.tolist() if hasattr(claim_rows, "values") else claim_rows
        if not normalized_rows:
            claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views("", claim_detail_map)
            return claim_view, evidence_rows, review_view, "", evidence_items, evidence_detail_html, build_quality_evaluation_example_text(formatted_result, "", claim_detail_map)
        index = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        try:
            row_index = int(index)
        except (TypeError, ValueError):
            claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views("", claim_detail_map)
            return claim_view, evidence_rows, review_view, "", evidence_items, evidence_detail_html, build_quality_evaluation_example_text(formatted_result, "", claim_detail_map)
        if row_index < 0 or row_index >= len(normalized_rows):
            claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views("", claim_detail_map)
            return claim_view, evidence_rows, review_view, "", evidence_items, evidence_detail_html, build_quality_evaluation_example_text(formatted_result, "", claim_detail_map)
        selected_row = normalized_rows[row_index] if normalized_rows[row_index] else []
        selected_claim_id = str(selected_row[1] if len(selected_row) > 8 else (selected_row[0] if selected_row else ""))
        claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(selected_claim_id, claim_detail_map)
        return (
            claim_view,
            evidence_rows,
            review_view,
            selected_claim_id,
            evidence_items,
            evidence_detail_html,
            build_quality_evaluation_example_text(formatted_result, selected_claim_id, claim_detail_map),
        )

    def select_quality_evidence(
        evidence_items: list[dict] | None,
        evt: gr.SelectData,
        current_page_rows: list[list[object]] | None = None,
    ) -> str:
        """点击证据列表后联动证据详情。"""

        page_rows = normalize_table_rows(current_page_rows) if current_page_rows is not None else build_quality_evidence_rows_from_items(evidence_items)
        items = evidence_items or []
        if not items or not page_rows:
            return format_evidence_detail_html(None)
        selected_row = get_row_from_paged_table(page_rows, evt, id_column_index=1)
        selected_chunk_id = str(selected_row[1] if len(selected_row) > 8 else (selected_row[0] if selected_row else ""))
        matched_item = next((item for item in items if str(item.get("chunk_id") or "") == selected_chunk_id), None)
        return format_evidence_detail_html(matched_item)

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

    def build_quality_evaluation_example_text(
        formatted_result: dict | None = None,
        selected_claim: str | None = None,
        claim_detail_map: dict | None = None,
    ) -> str:
        """构建 AI 质检效果评测样例 JSON，优先跟随当前选中的 Claim。"""

        claim_detail = format_claim_detail_for_review(selected_claim or "", claim_detail_map)
        claim_summary = claim_detail.get("summary") or {}
        if claim_summary.get("claim_id"):
            check = (formatted_result or {}).get("check") or {}
            return json.dumps(
                [
                    {
                        "case_id": str(claim_summary.get("claim_id")),
                        "input_text": str(claim_summary.get("claim_text") or ""),
                        "expected_overall_verdict": (
                            "passed" if str(claim_summary.get("verdict") or "") == "verified" else str(check.get("overall_verdict") or "needs_review")
                        ),
                        "expected_risk_level": str(claim_summary.get("risk_level") or check.get("risk_level") or "medium"),
                        "expected_claim_count": 1,
                    }
                ],
                ensure_ascii=False,
                indent=2,
            )

        return json.dumps(
            [
                {
                    "case_id": "demo_case_general_supported",
                    "input_text": "阿胶具有补血作用。",
                    "expected_overall_verdict": "passed",
                    "expected_risk_level": "low",
                    "expected_claim_count": 1,
                },
                {
                    "case_id": "demo_case_general_absolute",
                    "input_text": "阿胶只有东阿一家有。",
                    "expected_overall_verdict": "needs_review",
                    "expected_risk_level": "high",
                    "expected_claim_count": 1,
                },
            ],
            ensure_ascii=False,
            indent=2,
        )

    def run_quality_evaluation(
        cases_json: str,
        template_choice: str,
        knowledge_base_choice: str | None = None,
    ) -> tuple[str, list[list[str]], dict]:
        """执行 AI 质检效果评测，并返回摘要和明细。"""

        raw_text = str(cases_json or "").strip()
        if not raw_text:
            return (
                format_operation_result_html({"success": False, "message": "请输入评测样例 JSON。"}, title="效果评测"),
                [],
                {},
            )
        try:
            cases = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return (
                format_operation_result_html(
                    {"success": False, "message": f"样例 JSON 解析失败：{exc.msg}"},
                    title="效果评测",
                ),
                [],
                    {},
            )
        if not isinstance(cases, list):
            return (
                format_operation_result_html({"success": False, "message": "评测样例必须是 JSON 数组。"}, title="效果评测"),
                [],
                {},
            )

        try:
            evaluation_result = quality_service.run_evaluation_suite(
                cases,
                knowledge_base_id=resolve_knowledge_base_choice(knowledge_base_choice),
                template_id=parse_template_choice(template_choice),
            )
        except AppError as exc:
            return (
                format_operation_result_html(
                    {"success": False, "message": exc.message, "error_code": exc.error_code},
                    title="效果评测",
                ),
                [],
                {},
            )

        return (
            format_quality_evaluation_summary_html(evaluation_result),
            build_quality_evaluation_rows(evaluation_result),
            evaluation_result,
        )

    def run_quality_evaluation_ui(
        cases_json: str,
        template_choice: str,
        knowledge_base_choice: str | None = None,
    ) -> tuple[str, list[list[object]], dict, int, str]:
        """执行效果评测并返回分页后的表格输出。"""

        summary_html, _rows, evaluation_result = run_quality_evaluation(
            cases_json,
            template_choice,
            knowledge_base_choice,
        )
        page_rows, page_value, page_info = build_quality_evaluation_table_page_outputs(evaluation_result, page=1)
        return summary_html, page_rows, evaluation_result, page_value, page_info

    def change_quality_evaluation_page(
        evaluation_result: dict | None,
        current_page: int | float,
        action: str,
    ) -> tuple[list[list[object]], int, str]:
        """切换效果评测明细分页。"""

        full_rows = build_quality_evaluation_rows(evaluation_result)
        page_rows, new_page, page_info = change_table_page(
            full_rows,
            current_page,
            action=action,
            prepend_sequence=True,
        )
        return page_rows, new_page, format_table_pagination_html(page_info)

    def export_quality_results(
        formatted_result: dict | None,
        selected_claim: str,
        claim_detail_map: dict | None,
        evidence_items: list[dict] | None,
    ) -> tuple[str, str | None]:
        """导出当前 AI 质检结果。"""

        claim_detail = format_claim_detail_for_review(selected_claim, claim_detail_map)
        markdown_text = format_quality_export_markdown(
            formatted_result,
            claim_detail,
        )
        claim_summary = (claim_detail or {}).get("summary") or {}
        linked_id = str(claim_summary.get("claim_id") or (formatted_result or {}).get("check", {}).get("check_id") or "")
        try:
            export_result = save_markdown_export(
                settings_runtime_payload.get("sqlite_db_path") or ".",
                module_name="AI质检",
                result_name="质检结果",
                markdown_text=markdown_text,
                linked_id=linked_id or None,
                file_extension="md",
            )
            file_path = str(export_result["file_path"])
            result_html = format_operation_result_html(
                {
                    "success": True,
                    "message": f'已生成 AI 质检下载文件：{export_result["file_name"]}。请点击下方“下载文件”。',
                    "preview_url": build_download_url(file_path=export_result["preview_file_path"]),
                    "preview_file_name": export_result["preview_file_name"],
                },
                title="下载结果",
            )
            return result_html, file_path
        except Exception as exc:  # pragma: no cover - 防御性导出失败提示
            return (
                format_operation_result_html(
                    {"success": False, "message": f"导出失败：{exc}"},
                    title="下载结果",
                ),
                None,
            )

    def export_quality_evaluation_results(evaluation_result: dict | None) -> str:
        """导出当前 AI 质检效果评测结果。"""

        markdown_text = format_quality_evaluation_export_markdown(evaluation_result)
        first_row = ((evaluation_result or {}).get("rows") or [None])[0] or {}
        linked_id = str(first_row.get("case_id") or first_row.get("check_id") or "")
        return export_markdown_result("AI质检", "效果评测", markdown_text, linked_id=linked_id or None)

    def export_document_quality_result(
        choice: str,
        search_rows: list[dict],
        query_text: str,
        knowledge_base_choice: str | None = None,
    ) -> str:
        """导出当前文档的入库质检结果。"""

        state = get_document_management_state(choice, knowledge_base_choice)
        detail = state["selected_detail"]
        doc_uid = str(detail.get("doc_uid") or "")
        if not doc_uid:
            return format_operation_result_html(
                {"success": False, "message": "当前文档尚未入库，无法导出入库质检结果。"},
                title="下载结果",
            )
        report = ingest_service.inspect_document_quality(doc_uid)
        batch_result = ingest_service.list_document_quality_reports(doc_uids=[doc_uid], page_size=1)
        markdown_text = "\n".join(
            [
                format_document_detail_markdown(detail),
                "",
                format_document_quality_export_markdown(
                    report,
                    batch_result,
                    {"count": len(search_rows or []), "query_text": query_text, "table": search_rows or []},
                    build_search_detail_payload((search_rows or [None])[0]) if search_rows else None,
                    query_text=query_text,
                ),
                "",
                format_document_quality_config_markdown(ingest_service.get_document_quality_config()),
            ]
        )
        return export_markdown_result("文档管理", "入库质检", markdown_text, linked_id=doc_uid)

    def export_document_quality_search_result(
        choice: str,
        search_rows: list[dict],
        query_text: str,
        knowledge_base_choice: str | None = None,
    ) -> str:
        """导出当前文档内检索验证结果。"""

        detail = get_document_management_state(choice, knowledge_base_choice)["selected_detail"]
        doc_uid = str(detail.get("doc_uid") or "")
        selected_row = build_search_detail_payload((search_rows or [None])[0]) if search_rows else None
        markdown_text = format_search_export_markdown(
            {
                "count": len(search_rows or []),
                "query_text": query_text,
                "table": search_rows or [],
            },
            selected_row,
            query_text=query_text,
        )
        return export_markdown_result("文档管理", "文档检索验证", markdown_text, linked_id=doc_uid or None)

    def export_document_quality_batch_result(knowledge_base_choice: str | None = None) -> str:
        """导出批量入库质检结果。"""

        batch_result = ingest_service.list_document_quality_reports(
            knowledge_base_id=resolve_knowledge_base_choice(knowledge_base_choice),
        )
        markdown_text = format_document_quality_batch_export_markdown(batch_result)
        return export_markdown_result("文档管理", "批量入库质检", markdown_text)

    def export_document_quality_config_result(
        sample_limit: int | float,
        long_document_char_threshold: int | float,
        min_sections_for_long_doc: int | float,
        max_avg_chunks_per_section: int | float,
        max_chunk_chars: int | float,
        short_chunk_chars: int | float,
        short_chunk_warn_min_chunk_count: int | float,
    ) -> str:
        """导出当前入库质检阈值配置。"""

        config_payload = {
            **ingest_service.get_document_quality_config(),
            "sample_limit": int(sample_limit),
            "long_document_char_threshold": int(long_document_char_threshold),
            "min_sections_for_long_doc": int(min_sections_for_long_doc),
            "max_avg_chunks_per_section": int(max_avg_chunks_per_section),
            "max_chunk_chars": int(max_chunk_chars),
            "short_chunk_chars": int(short_chunk_chars),
            "short_chunk_warn_min_chunk_count": int(short_chunk_warn_min_chunk_count),
        }
        return export_markdown_result("文档管理", "质检阈值配置", format_document_quality_config_markdown(config_payload))

    def export_review_result(
        selected_claim_id: str,
        claim_detail_map: dict | None,
        evidence_items: list[dict] | None,
        selected_review_id: str,
        review_items: list[dict] | None,
    ) -> str:
        """导出人工审核当前查看结果。"""

        claim_detail = format_claim_detail_for_review(selected_claim_id, claim_detail_map)
        selected_record = next((item for item in (review_items or []) if str(item.get("review_id") or "") == str(selected_review_id or "")), None)
        markdown_text = format_review_export_markdown(claim_detail, evidence_items, selected_record)
        return export_markdown_result("人工审核", "审核结果", markdown_text, linked_id=selected_claim_id or None)

    def export_settings_result(selected_template_id: str) -> str:
        """导出当前功能设置详情。"""

        template = quality_service.get_template(selected_template_id) if selected_template_id else None
        markdown_text = "\n".join(
            [
                format_settings_template_detail_markdown(template),
                "",
                format_settings_runtime_markdown(build_settings_runtime_payload()),
            ]
        )
        return export_markdown_result("功能设置", "当前配置", markdown_text, linked_id=selected_template_id or None)

    def build_quality_outputs(
        *,
        progress_html: str,
        result_html: str,
        formatted_result: dict | None = None,
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
        evaluation_cases_text: str | None = None,
    ) -> tuple[str, str, dict, list[list[str]], str, dict, str, list[list[str]], str, list[dict], str, list[dict], list[list[str]], str]:
        """统一构建 AI 质检页输出。"""

        empty_claim_view, empty_evidence_rows, empty_review_view, empty_evidence_items, empty_evidence_detail_html = render_claim_views("", {})
        resolved_formatted_result = formatted_result or {}
        resolved_selected_claim = selected_claim or ""
        resolved_claim_detail_map = claim_detail_map or {}
        return (
            progress_html,
            result_html,
            resolved_formatted_result,
            claim_rows or [],
            resolved_selected_claim,
            resolved_claim_detail_map,
            claim_view or empty_claim_view,
            evidence_rows or empty_evidence_rows,
            review_view or empty_review_view,
            evidence_items or empty_evidence_items,
            evidence_detail_html or empty_evidence_detail_html,
            recent_results or [],
            recent_rows or [],
            evaluation_cases_text or build_quality_evaluation_example_text(
                resolved_formatted_result,
                resolved_selected_claim,
                resolved_claim_detail_map,
            ),
        )

    def build_quality_error_outputs(
        message: str,
        *,
        error_code: str = "QUALITY_CHECK_FAILED",
    ) -> tuple:
        """构建质检失败终态，避免 Gradio 保留最后一个 running 进度。"""

        return build_quality_outputs(
            progress_html=format_quality_progress_html(
                {
                    "status": "error",
                    "stage": "failed",
                    "message": message,
                    "model_status": "-",
                }
            ),
            result_html=format_operation_result_html(
                {"success": False, "message": message, "error_code": error_code},
                title="质检结果",
            ),
            formatted_result={},
            recent_results=[],
            recent_rows=[],
        )

    def build_recent_quality_view_outputs(
        recent_results: list[dict] | None,
        *,
        selected_index: int = 0,
        preferred_claim_id: str | None = None,
        history_scope_value: str | None = None,
        replay_result: bool = True,
    ) -> tuple[str, str, list[list[str]], str, dict, str, list[list[str]], str, list[dict], str, list[dict], list[list[str]], str]:
        """根据最近质检记录构建当前页面展示状态。"""

        results = filter_recent_quality_results(recent_results, history_scope_value)
        if not results:
            return build_quality_outputs(
                progress_html=format_quality_progress_html(None),
                result_html=format_quality_result_html(None),
                recent_results=[],
                recent_rows=[],
            )

        recent_payload = format_recent_quality_checks(results)
        recent_rows = build_recent_quality_rows(
            recent_payload,
        )
        if not replay_result:
            return build_quality_outputs(
                progress_html=format_quality_progress_html(None),
                result_html=format_quality_result_html(None),
                recent_results=results,
                recent_rows=recent_rows,
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
            formatted_result=selected_formatted,
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

    def list_recent_quality_results_ui(
        knowledge_base_choice: str | None = None,
        history_scope_value: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """加载最近质检记录，并输出分页后的界面状态。"""

        return build_quality_ui_outputs(
            list_recent_quality_results(
                knowledge_base_choice,
                history_scope_value,
                login_session,
            )
        )

    def load_recent_quality_runtime_results(
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> list[dict]:
        """按当前知识库读取最新历史质检结果，避免依赖服务启动快照。"""

        if not _has_tab_access(login_session, "AI 质检"):
            return []
        knowledge_base_id = _resolve_authorized_knowledge_base_choice(knowledge_base_choice, login_session)
        if not knowledge_base_id:
            return []
        try:
            return quality_service.list_recent_results(
                limit=RECENT_QUALITY_FETCH_LIMIT,
                knowledge_base_id=knowledge_base_id,
            )
        except AppError:
            return []

    def select_recent_quality_result_ui(
        current_page_rows: list[list[object]],
        recent_results: list[dict],
        current_recent_page: int | float,
        knowledge_base_choice: str | None,
        history_scope_value: str | None,
        evt: gr.SelectData,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """点击最近质检记录后，输出分页后的 AI 质检界面状态。"""

        results = load_recent_quality_runtime_results(knowledge_base_choice, login_session) or (recent_results or [])
        filtered_results = filter_recent_quality_results(results, history_scope_value)
        if not filtered_results:
            return build_quality_ui_outputs(build_recent_quality_view_outputs([], history_scope_value=history_scope_value))
        fresh_page_rows, resolved_recent_page, _recent_page_info = build_recent_quality_table_page_outputs(
            filtered_results,
            current_recent_page,
        )
        fallback_page_rows = normalize_table_rows(current_page_rows)
        selected_check_id = ""
        evt_value = getattr(evt, "value", None)
        if evt_value not in (None, ""):
            candidate_check_id = str(evt_value).strip()
            if any(str(item.get("check_id") or "") == candidate_check_id for item in filtered_results):
                selected_check_id = candidate_check_id
        if not selected_check_id:
            selected_row = get_row_from_paged_table(
                fresh_page_rows or fallback_page_rows,
                evt,
                id_column_index=1,
            )
            selected_check_id = str(selected_row[1] if len(selected_row) > 1 else "")
        selected_index = next(
            (index for index, item in enumerate(filtered_results) if str(item.get("check_id") or "") == selected_check_id),
            -1,
        )
        if selected_index < 0:
            raw_index = getattr(evt, "index", 0)
            row_index = raw_index[0] if isinstance(raw_index, (list, tuple)) else raw_index
            try:
                row_offset = int(row_index)
            except (TypeError, ValueError):
                row_offset = 0
            selected_index = max(0, min(len(filtered_results) - 1, (resolved_recent_page - 1) * TABLE_PAGE_SIZE + row_offset))
        outputs = list(
            build_quality_ui_outputs(
                build_recent_quality_view_outputs(results, selected_index=selected_index, history_scope_value=history_scope_value),
                recent_page=current_recent_page,
            )
        )
        active_check_id = str(((outputs[3] or {}).get("check") or {}).get("check_id") or selected_check_id or "")
        evidence_row_count = resolve_table_row_count(outputs[10])
        # 使用 update 而不是重建 Dataframe，避免 select 事件回写多个表格时触发前端局部重绘异常。
        outputs[0] = gr.update(value=outputs[0])
        outputs[1] = gr.update(value=outputs[1])
        outputs[2] = gr.update(value=outputs[2])
        outputs[6] = gr.update(value=outputs[6])
        outputs[9] = gr.update(value=outputs[9])
        outputs[10] = rebuild_readonly_dataframe(
            headers=["序号", "片段 ID", "文档", "定位", "证据关系", "检索来源", "检索路径", "重排分", "证据摘要"],
            rows=outputs[10],
            label="证据列表",
            elem_id="quality-evidence-table",
            row_count=evidence_row_count,
            component_key=f"quality-evidence-{active_check_id or 'empty'}",
        )
        outputs[12] = gr.update(value=outputs[12])
        outputs[13] = gr.update(value=outputs[13])
        outputs[15] = gr.update(value=outputs[15])
        outputs[17] = rebuild_readonly_dataframe(
            headers=["序号", "质检 ID", "模板", "总体结论", "Claim 数", "待处理 Claim", "时间", "输入摘要"],
            rows=outputs[17],
            label="最近质检记录",
            elem_id="quality-recent-table",
            row_count=TABLE_PAGE_SIZE,
            component_key=f"quality-recent-{active_check_id or 'empty'}",
        )
        outputs[19] = gr.update(value=outputs[19])
        outputs[20] = gr.update(value=outputs[20])
        return tuple(outputs)
    select_recent_quality_result_ui.__name__ = "select_recent_quality_result"

    def select_quality_claim_ui(
        selected_claim: str,
        claim_detail_map: dict | None,
        formatted_result: dict | None,
    ) -> tuple:
        """点击 Claim 列表后，返回分页后的证据表输出。"""

        claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(
            selected_claim,
            claim_detail_map,
        )
        evidence_page_rows, evidence_page_value, evidence_page_info = build_quality_evidence_table_page_outputs(
            evidence_items,
            page=1,
        )
        return (
            claim_view,
            evidence_page_rows,
            evidence_page_value,
            evidence_page_info,
            review_view,
            selected_claim,
            evidence_items,
            evidence_detail_html,
            build_quality_evaluation_example_text(formatted_result, selected_claim, claim_detail_map),
        )
    select_quality_claim_ui.__name__ = "select_quality_claim"

    def run_quality_check_ui(
        input_text: str,
        template_choice: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ):
        """执行 AI 质检，并将输出适配为带分页的界面结果。"""

        try:
            for base_outputs in run_quality_check(input_text, template_choice, knowledge_base_choice, login_session):
                yield build_quality_ui_outputs(base_outputs)
        except AppError as exc:
            yield build_quality_ui_outputs(build_quality_error_outputs(exc.message, error_code=exc.error_code))
        except Exception:  # noqa: BLE001
            # 结果格式化或分页渲染失败时，质检可能已经落库，也必须向前端发送终态。
            LOGGER.exception("AI 质检 UI 结果渲染失败")
            yield build_quality_ui_outputs(build_quality_error_outputs("质检结果渲染失败，请到历史记录中查看。"))

    def change_quality_claim_page(
        formatted_result: dict | None,
        claim_detail_map: dict | None,
        current_page: int | float,
        action: str,
        selected_claim: str,
    ) -> tuple[dict, int, str, str, str, list[list[object]], int, str, str, list[dict], str, str]:
        """切换 Claim 列表分页。"""

        claim_choices, current_choice, new_page, _current_page_info = build_quality_claim_selector_page_outputs(
            formatted_result,
            selected_claim,
            current_page,
        )
        target_page = new_page - 1 if action == "prev" else new_page + 1
        claim_choices, resolved_choice, final_page, final_page_info = build_quality_claim_selector_page_outputs(
            formatted_result,
            current_choice,
            target_page,
        )
        claim_view, _evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(
            resolved_choice or "",
            claim_detail_map,
        )
        evidence_page_rows, evidence_page_value, evidence_page_info = build_quality_evidence_table_page_outputs(
            evidence_items,
            page=1,
        )
        return (
            gr.update(choices=claim_choices, value=resolved_choice),
            final_page,
            final_page_info,
            resolved_choice or "",
            claim_view,
            evidence_page_rows,
            evidence_page_value,
            evidence_page_info,
            review_view,
            evidence_items,
            evidence_detail_html,
            build_quality_evaluation_example_text(formatted_result, resolved_choice or "", claim_detail_map),
        )

    def change_quality_evidence_page(
        evidence_items: list[dict] | None,
        current_page: int | float,
        action: str,
    ) -> tuple[list[list[object]], int, str]:
        """切换证据列表分页。"""

        full_rows = build_quality_evidence_rows_from_items(evidence_items)
        page_rows, new_page, page_info = change_table_page(
            full_rows,
            current_page,
            action=action,
            prepend_sequence=True,
        )
        return page_rows, new_page, format_table_pagination_html(page_info)

    def change_recent_quality_page(
        current_page: int | float,
        action: str,
        knowledge_base_choice: str | None = None,
        history_scope_value: str | None = None,
        recent_results: list[dict] | None = None,
    ) -> tuple[list[list[object]], int, str]:
        """切换最近质检记录分页。"""

        results = load_recent_quality_runtime_results(knowledge_base_choice) or (recent_results or [])
        recent_payload = format_recent_quality_checks(
            filter_recent_quality_results(results, history_scope_value)
        )
        full_rows = build_recent_quality_rows(recent_payload)
        page_rows, new_page, page_info = change_table_page(
            full_rows,
            current_page,
            action=action,
            prepend_sequence=True,
        )
        return page_rows, new_page, format_table_pagination_html(page_info)

    def change_settings_template_page(
        template_items: list[dict] | None,
        current_page: int | float,
        action: str,
    ) -> tuple[list[list[object]], int, str]:
        """切换模板列表分页。"""

        full_rows = build_settings_template_rows(template_items or [])
        page_rows, new_page, page_info = change_table_page(
            full_rows,
            current_page,
            action=action,
            prepend_sequence=True,
        )
        return page_rows, new_page, format_table_pagination_html(page_info)

    def refresh_settings_workspace_ui(template_kind: str | None, selected_template_id: str | None) -> tuple:
        """刷新功能设置页并返回分页后的模板列表。"""

        return build_settings_workspace_ui_outputs(refresh_settings_workspace(template_kind, selected_template_id))

    def refresh_settings_knowledge_base_workspace_ui(
        selected_knowledge_base_id: str | None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """刷新知识库设置页并返回分页后的知识库列表。"""

        return build_settings_knowledge_base_workspace_ui_outputs(
            refresh_settings_knowledge_base_workspace(selected_knowledge_base_id, login_session)
        )

    def save_settings_template_ui(*args) -> tuple:
        """保存模板并返回分页后的功能设置页输出。"""

        outputs = save_settings_template(*args)
        return (*build_settings_workspace_ui_outputs(outputs[:20]), *outputs[20:])

    def delete_settings_template_ui(*args) -> tuple:
        """删除模板并返回分页后的功能设置页输出。"""

        outputs = delete_settings_template(*args)
        return (*build_settings_workspace_ui_outputs(outputs[:20]), *outputs[20:])

    def save_settings_knowledge_base_ui(*args) -> tuple:
        """保存知识库并返回分页后的知识库设置页输出。"""

        outputs = save_settings_knowledge_base(*args)
        return (*build_settings_knowledge_base_workspace_ui_outputs(outputs[:10]), *outputs[10:])

    def delete_settings_knowledge_base_ui(*args) -> tuple:
        """删除知识库并返回分页后的知识库设置页输出。"""

        outputs = delete_settings_knowledge_base(*args)
        return (*build_settings_knowledge_base_workspace_ui_outputs(outputs[:10]), *outputs[10:])

    def change_settings_knowledge_base_page(
        knowledge_base_items: list[dict] | None,
        current_page: int | float,
        action: str,
        selected_knowledge_base_id: str,
    ) -> tuple[dict, int, str, str, str, str, str, str, bool, str]:
        """切换知识库列表分页。"""

        _choices, current_choice, new_page, _page_info = build_settings_knowledge_base_selector_page_outputs(
            knowledge_base_items,
            selected_knowledge_base_id,
            current_page,
        )
        target_page = new_page - 1 if action == "prev" else new_page + 1
        choices, resolved_choice, final_page, final_page_info = build_settings_knowledge_base_selector_page_outputs(
            knowledge_base_items,
            parse_knowledge_base_choice(current_choice or selected_knowledge_base_id),
            target_page,
        )
        outputs = build_settings_knowledge_base_workspace(parse_knowledge_base_choice(resolved_choice or ""))
        return (
            gr.update(choices=choices, value=resolved_choice),
            final_page,
            final_page_info,
            outputs[2],
            outputs[3],
            outputs[4],
            outputs[5],
            outputs[6],
            outputs[7],
            outputs[8],
            outputs[9],
        )

    def list_review_workspace_ui(
        scope_value: str,
        risk_value: str,
        selected_claim_id: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """加载人工审核页并返回分页后的界面输出。"""

        return build_review_workspace_ui_outputs(
            list_review_workspace(scope_value, risk_value, selected_claim_id, knowledge_base_choice, login_session),
        )

    def change_review_filters_ui(
        review_candidates: list[dict],
        review_items: list[dict],
        selected_claim_id: str,
        scope_value: str,
        risk_value: str,
    ) -> tuple:
        """切换人工审核筛选并返回分页后的界面输出。"""

        return build_review_workspace_ui_outputs(
            build_review_workspace_outputs(
                review_candidates,
                review_items,
                selected_claim_id=selected_claim_id,
                scope_value=scope_value,
                risk_value=risk_value,
            ),
        )
    change_review_filters_ui.__name__ = "change_review_filters"

    def select_review_candidate_ui(
        current_page_rows: list[list[object]],
        review_candidates: list[dict],
        review_items: list[dict],
        evt: gr.SelectData,
        scope_value: str,
        risk_value: str,
    ) -> tuple:
        """点击人工审核候选记录后，返回分页后的证据输出。"""

        (
            selected_claim_id,
            review_claim_detail_map,
            review_claim_detail_html,
            review_evidence_rows,
            review_evidence_items,
            review_evidence_detail_html,
            review_action_value,
            review_note_value,
            selected_review_id,
            review_record_detail_html,
        ) = select_review_candidate(current_page_rows, review_candidates, review_items, evt, scope_value, risk_value)
        evidence_page_rows, evidence_page_value, _evidence_total_pages, evidence_page_info = paginate_table_rows(
            review_evidence_rows,
            1,
            prepend_sequence=True,
        )
        return (
            selected_claim_id,
            review_claim_detail_map,
            review_claim_detail_html,
            evidence_page_rows,
            evidence_page_value,
            format_table_pagination_html(evidence_page_info),
            review_evidence_items,
            review_evidence_detail_html,
            review_action_value,
            review_note_value,
            selected_review_id,
            review_record_detail_html,
        )
    select_review_candidate_ui.__name__ = "select_review_candidate"

    def select_review_history_record_ui(
        review_items: list[dict],
        review_candidates: list[dict],
        scope_value: str,
        risk_value: str,
        current_page_rows: list[list[object]],
        evt: gr.SelectData,
    ) -> tuple:
        """点击审核历史后，返回分页后的证据输出。"""

        (
            selected_claim_id,
            review_claim_detail_map,
            review_claim_detail_html,
            review_evidence_rows,
            review_evidence_items,
            review_evidence_detail_html,
            review_action_value,
            review_note_value,
            selected_review_id,
            review_record_detail_html,
        ) = select_review_history_record(
            review_items,
            review_candidates,
            evt,
            scope_value,
            risk_value,
            current_page_rows,
        )
        evidence_page_rows, evidence_page_value, _evidence_total_pages, evidence_page_info = paginate_table_rows(
            review_evidence_rows,
            1,
            prepend_sequence=True,
        )
        return (
            selected_claim_id,
            review_claim_detail_map,
            review_claim_detail_html,
            evidence_page_rows,
            evidence_page_value,
            format_table_pagination_html(evidence_page_info),
            review_evidence_items,
            review_evidence_detail_html,
            review_action_value,
            review_note_value,
            selected_review_id,
            review_record_detail_html,
        )
    select_review_history_record_ui.__name__ = "select_review_history_record"

    def submit_review_action_ui(
        claim_choice: str,
        review_action: str,
        review_note: str,
        scope_value: str,
        risk_value: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """提交审核并返回分页后的人工审核界面输出。"""

        outputs = submit_review_action(
            claim_choice,
            review_action,
            review_note,
            scope_value,
            risk_value,
            knowledge_base_choice,
            login_session,
        )
        return (outputs[0], *build_review_workspace_ui_outputs(outputs[1:]))
    submit_review_action_ui.__name__ = "submit_review_action"

    def change_review_candidate_page(
        review_candidates: list[dict] | None,
        scope_value: str,
        risk_value: str,
        current_page: int | float,
        action: str,
        *,
        processed: bool,
    ) -> tuple[list[list[object]], int, str]:
        """切换人工审核候选列表分页。"""

        filtered_candidates = filter_review_candidates(
            review_candidates,
            scope_value=scope_value,
            risk_value=risk_value,
        )
        pending_items, processed_items = split_review_candidates(filtered_candidates)
        target_items = processed_items if processed else pending_items
        full_rows = build_review_candidate_rows(format_review_candidates(target_items))
        page_rows, new_page, page_info = change_table_page(
            full_rows,
            current_page,
            action=action,
            prepend_sequence=True,
        )
        return page_rows, new_page, format_table_pagination_html(page_info)

    def change_review_evidence_page(
        evidence_items: list[dict] | None,
        current_page: int | float,
        action: str,
    ) -> tuple[list[list[object]], int, str]:
        """切换人工审核证据列表分页。"""

        full_rows = build_quality_evidence_rows_from_items(evidence_items)
        page_rows, new_page, page_info = change_table_page(
            full_rows,
            current_page,
            action=action,
            prepend_sequence=True,
        )
        return page_rows, new_page, format_table_pagination_html(page_info)

    def change_review_history_page(
        review_items: list[dict] | None,
        current_page: int | float,
        action: str,
    ) -> tuple[list[list[object]], int, str]:
        """切换审核历史分页。"""

        full_rows = build_review_history_rows(format_review_history(review_items or []))
        page_rows, new_page, page_info = change_table_page(
            full_rows,
            current_page,
            action=action,
            prepend_sequence=True,
        )
        return page_rows, new_page, format_table_pagination_html(page_info)

    def run_quality_check(
        input_text: str,
        template_choice: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ):
        selected_template_id = parse_template_choice(template_choice)
        knowledge_base_id = _resolve_authorized_knowledge_base_choice(knowledge_base_choice, login_session)
        initial_result_html = format_quality_result_html(None)
        if not knowledge_base_id:
            yield build_quality_outputs(
                progress_html=format_quality_progress_html(None),
                result_html=format_operation_result_html(
                    {"success": False, "message": "当前账号没有可用知识库，请联系管理员开通知识库权限。"},
                    title="质检结果",
                ),
                formatted_result={},
                recent_results=[],
                recent_rows=[],
            )
            return
        try:
            completed = False
            for event in quality_service.run_check_stream(
                input_text,
                knowledge_base_id=knowledge_base_id,
                template_id=selected_template_id,
            ):
                if event.get("type") == "progress":
                    yield build_quality_outputs(
                        progress_html=format_quality_progress_html(event),
                        result_html=initial_result_html,
                        formatted_result={},
                    )
                    continue

                if event.get("type") != "result":
                    LOGGER.warning("AI 质检流返回未知事件类型：%s", event.get("type"))
                    continue

                result = event.get("result", {})
                formatted = format_quality_result(result)
                current_recent_result = {
                    "check_id": formatted["check"].get("check_id"),
                    "template_name": formatted["check"].get("template_name"),
                    "created_at": formatted["check"].get("created_at"),
                    "overall_verdict": formatted["check"].get("overall_verdict"),
                    "input_text": input_text,
                    "claims": formatted["claims"],
                }
                recent_results = quality_service.list_recent_results(
                    limit=RECENT_QUALITY_FETCH_LIMIT,
                    knowledge_base_id=knowledge_base_id,
                )
                current_check_id = str(current_recent_result.get("check_id") or "").strip()
                if not recent_results:
                    recent_results = [current_recent_result]
                elif current_check_id and not any(
                    str(item.get("check_id") or "").strip() == current_check_id for item in recent_results
                ):
                    recent_results = [current_recent_result, *recent_results][:RECENT_QUALITY_FETCH_LIMIT]
                navigation = build_recent_claim_navigation([current_recent_result])
                claim_view, evidence_rows, review_view, evidence_items, evidence_detail_html = render_claim_views(navigation["selected_choice"], navigation["claim_detail_map"])
                yield build_quality_outputs(
                    progress_html=format_quality_progress_html(event),
                    result_html=format_quality_result_html(formatted),
                    formatted_result=formatted,
                    claim_rows=build_quality_claim_rows(formatted),
                    selected_claim=navigation["selected_choice"],
                    claim_detail_map=navigation["claim_detail_map"],
                    claim_view=claim_view,
                    evidence_rows=evidence_rows,
                    review_view=review_view,
                    evidence_items=evidence_items,
                    evidence_detail_html=evidence_detail_html,
                    recent_results=recent_results,
                    recent_rows=build_recent_quality_rows(
                        recent_results,
                    ),
                )
                completed = True
                return
            if not completed:
                raise RuntimeError("质检流未返回最终结果")
        except AppError as exc:
            yield build_quality_error_outputs(exc.message, error_code=exc.error_code)
            return
        except Exception:  # noqa: BLE001
            # 普通异常不能直接交给 Gradio，否则前端会保留最后一个 running 进度。
            # 记录完整堆栈供日志排查，同时给页面发送明确终态。
            LOGGER.exception("AI 质检 UI 回调执行失败")
            yield build_quality_error_outputs("质检执行失败，未生成结果，请稍后重试。")
            return

    review_action_choices = ["通过", "不通过", "更新结论"]
    recent_quality_scope_choices = ["全部历史任务", "仅看含待处理 Claim"]
    review_scope_choices = ["全部记录", "仅待处理", "仅已处理"]
    review_risk_choices = ["全部风险", "仅高风险", "仅中风险", "仅低风险"]
    review_candidate_fetch_limit = 200
    settings_runtime_payload = runtime_config or {}

    def build_settings_runtime_payload() -> dict:
        """构建功能设置页的运行配置摘要。"""

        return {
            **settings_runtime_payload,
            "max_input_chars": settings_runtime_payload.get("max_input_chars", 2000),
            "review_candidate_limit": review_candidate_fetch_limit,
        }

    def parse_rule_tags_text(rule_tags_text: str) -> list[str]:
        """将模板规则标签输入框解析为标签列表。"""

        raw = str(rule_tags_text or "")
        for separator in ("，", "、", ";", "；", "\n", "\t"):
            raw = raw.replace(separator, ",")
        return [item.strip() for item in raw.split(",") if item.strip()]

    def to_int_setting(value: object, *, default: int) -> int:
        """将表单数值统一转换为整数。"""

        if value in (None, ""):
            return default
        return int(float(value))

    def build_settings_form_values(template: dict | None) -> tuple[str, str, str, str, int, int, int, bool, int, bool, int, str, str]:
        """根据模板生成设置页表单默认值。"""

        resolved = template or {}
        retrieval_policy = resolved.get("retrieval_policy", {}) if isinstance(resolved.get("retrieval_policy", {}), dict) else {}
        is_pageindex_template = any(
            key in retrieval_policy
            for key in ("max_tree_candidates", "max_selected_nodes", "max_rag_evidence")
        )
        return (
            str(resolved.get("template_id") or ""),
            str(resolved.get("template_name") or ""),
            str(resolved.get("description") or ""),
            "、".join(str(item) for item in resolved.get("rule_tags", []) if item),
            int(retrieval_policy.get("max_tree_candidates" if is_pageindex_template else "fulltext_top_k", 30 if is_pageindex_template else 3)),
            int(retrieval_policy.get("max_selected_nodes" if is_pageindex_template else "vector_top_k", 3)),
            int(retrieval_policy.get("max_rag_evidence" if is_pageindex_template else "final_top_k", 2 if is_pageindex_template else 3)),
            bool(retrieval_policy.get("use_rerank", False)),
            int(retrieval_policy.get("neighbor_window", 0)),
            bool(retrieval_policy.get("include_structure_context" if is_pageindex_template else "include_section_context", False)),
            int(retrieval_policy.get("section_max_chars", 400)),
            str(resolved.get("system_prompt") or ""),
            str(resolved.get("user_prompt_template") or ""),
        )

    def build_quality_template_refresh_outputs(selected_template_id: str | None = None) -> tuple[gr.update, str]:
        """构建 AI 质检页模板下拉与详情的刷新输出。"""

        template_items = quality_service.list_templates()
        template_choices = build_template_choices(template_items)
        normalized_template_id = str(selected_template_id or "")
        available_ids = {str(item.get("template_id") or "") for item in template_items}
        if normalized_template_id not in available_ids:
            normalized_template_id = "general_fact_check" if "general_fact_check" in available_ids else (str(template_items[0].get("template_id") or "") if template_items else "")
        selected_choice = next(
            (choice for choice in template_choices if parse_template_choice(choice) == normalized_template_id),
            template_choices[0] if template_choices else None,
        )
        detail_html = render_quality_template(selected_choice or "")
        return gr.update(choices=template_choices, value=selected_choice), detail_html

    def build_pageindex_template_refresh_output(selected_template_id: str | None = None) -> gr.update:
        """构建 PageIndex 页模板下拉的刷新输出。"""

        template_items = pageindex_service.template_service.list_templates()
        template_choices = build_template_choices(template_items)
        normalized_template_id = str(selected_template_id or "")
        available_ids = {str(item.get("template_id") or "") for item in template_items}
        if normalized_template_id not in available_ids:
            normalized_template_id = "strict_qa" if "strict_qa" in available_ids else (str(template_items[0].get("template_id") or "") if template_items else "")
        selected_choice = next(
            (choice for choice in template_choices if parse_template_choice(choice) == normalized_template_id),
            template_choices[0] if template_choices else None,
        )
        return gr.update(choices=template_choices, value=selected_choice)

    def build_knowledge_base_form_values(knowledge_base: dict | None) -> tuple[str, str, str, str, bool]:
        """根据知识库生成设置页表单默认值。"""

        resolved = knowledge_base or {}
        return (
            str(resolved.get("knowledge_base_id") or ""),
            str(resolved.get("knowledge_base_name") or ""),
            str(resolved.get("description") or ""),
            str(resolved.get("status") or "active"),
            bool(resolved.get("is_default", False)),
        )

    def build_settings_user_choices(users: list[dict] | None) -> list[str]:
        """构建设置页用户选择项。"""

        choices: list[str] = []
        for user in users or []:
            username = str(user.get("username") or "").strip()
            user_id = str(user.get("user_id") or "").strip()
            role_name = "管理员" if bool(user.get("is_admin")) else "普通用户"
            if username and user_id:
                choices.append(f"{username} | {role_name} | {user_id}")
        return choices

    def parse_settings_user_choice(choice: str | None) -> str:
        """从设置页用户选择项中解析用户 ID。"""

        normalized = str(choice or "").strip()
        if not normalized:
            return ""
        if " | " not in normalized:
            return normalized
        return normalized.rsplit(" | ", 1)[-1].strip()

    def format_settings_user_detail_html(user: dict | None) -> str:
        """格式化用户管理页详情面板。"""

        if not user:
            return (
                "<div class='settings-detail-card'>"
                "<h3>用户详情</h3>"
                "<p>当前暂无可管理用户，请先注册用户后再在这里维护。</p>"
                "</div>"
            )
        role_name = "管理员" if bool(user.get("is_admin")) else "普通用户"
        return (
            "<div class='settings-detail-card'>"
            "<h3>用户详情</h3>"
            f"<p><strong>用户名：</strong>{str(user.get('username') or '')}</p>"
            f"<p><strong>角色：</strong>{role_name}</p>"
            f"<p><strong>用户 ID：</strong>{str(user.get('user_id') or '')}</p>"
            f"<p><strong>创建时间：</strong>{str(user.get('created_at') or '')}</p>"
            "</div>"
        )

    def format_settings_permission_detail_html(user: dict | None, permissions) -> str:
        """格式化权限管理页详情面板。"""

        if not user:
            return (
                "<div class='settings-detail-card'>"
                "<h3>权限说明</h3>"
                "<p>当前暂无可配置用户。</p>"
                "</div>"
            )
        role_name = "管理员" if bool(user.get("is_admin")) else "普通用户"
        tab_names = "、".join(str(item) for item in (permissions.tab_names if permissions else []) if item) or "无"
        kb_ids = "、".join(str(item) for item in (permissions.kb_ids if permissions else []) if item) or "无"
        return (
            "<div class='settings-detail-card'>"
            "<h3>权限说明</h3>"
            f"<p><strong>用户名：</strong>{str(user.get('username') or '')}</p>"
            f"<p><strong>角色：</strong>{role_name}</p>"
            f"<p><strong>当前菜单权限：</strong>{tab_names}</p>"
            f"<p><strong>当前知识库权限：</strong>{kb_ids}</p>"
            "</div>"
        )

    def build_settings_user_permission_workspace(
        selected_user_id: str | None = None,
        *,
        user_result_payload: dict | None = None,
        permission_result_payload: dict | None = None,
    ) -> tuple[list[dict], str, list[str], str | None, str, str, list[str], list[str], list[str], str, str]:
        """构建用户管理与权限管理子页面所需的共享数据。"""

        users = auth_service.list_users() or []
        user_choices = build_settings_user_choices(users)
        normalized_selected_user_id = str(selected_user_id or "").strip()
        selected_user = next(
            (item for item in users if str(item.get("user_id") or "").strip() == normalized_selected_user_id),
            users[0] if users else None,
        )
        resolved_user_id = str(selected_user.get("user_id") or "").strip() if selected_user else ""
        selected_choice = next(
            (choice for choice in user_choices if parse_settings_user_choice(choice) == resolved_user_id),
            user_choices[0] if user_choices else None,
        )
        permissions = auth_service.get_user_permissions(resolved_user_id) if resolved_user_id else None
        knowledge_base_choices = build_knowledge_base_choices(ingest_service.list_knowledge_bases())
        selected_kb_choices = [
            choice
            for choice in knowledge_base_choices
            if parse_knowledge_base_choice(choice) in set(permissions.kb_ids if permissions else [])
        ]
        return (
            users,
            resolved_user_id,
            user_choices,
            selected_choice,
            format_settings_user_detail_html(selected_user),
            format_settings_permission_detail_html(selected_user, permissions),
            list(permissions.tab_names if permissions else []),
            knowledge_base_choices,
            selected_kb_choices,
            format_operation_result_html(user_result_payload, title="用户结果"),
            format_operation_result_html(permission_result_payload, title="权限结果"),
        )

    def build_settings_user_permission_ui_outputs(base_outputs: tuple) -> tuple:
        """将用户与权限工作区数据转换为设置页组件输出。"""

        return (
            gr.update(choices=base_outputs[2], value=base_outputs[3]),
            base_outputs[0],
            base_outputs[1],
            base_outputs[4],
            base_outputs[9],
            gr.update(choices=base_outputs[2], value=base_outputs[3]),
            base_outputs[5],
            gr.update(choices=AUTH_TAB_NAMES, value=base_outputs[6]),
            gr.update(choices=base_outputs[7], value=base_outputs[8]),
            base_outputs[10],
        )

    def refresh_settings_user_workspace_ui(selected_user_id: str | None) -> tuple:
        """刷新用户管理与权限管理子页面。"""

        return build_settings_user_permission_ui_outputs(
            build_settings_user_permission_workspace(selected_user_id),
        )

    def select_settings_user_ui(user_choice: str, _users: list[dict] | None = None) -> tuple:
        """切换用户管理或权限管理页的选中用户。"""

        return build_settings_user_permission_ui_outputs(
            build_settings_user_permission_workspace(parse_settings_user_choice(user_choice)),
        )

    def delete_settings_user_ui(
        selected_user_id: str | None,
        current_session: dict[str, object] | None = None,
    ) -> tuple:
        """删除普通用户并刷新用户与权限管理子页面。"""

        normalized_user_id = str(selected_user_id or "").strip()
        if not normalized_user_id:
            base_outputs = build_settings_user_permission_ui_outputs(
                build_settings_user_permission_workspace(
                    None,
                    user_result_payload={"success": False, "message": "请选择用户"},
                )
            )
            return (*base_outputs, *_build_current_session_permission_updates(current_session))
        success, message = auth_service.delete_user(normalized_user_id)
        next_selected_user_id = normalized_user_id if not success else None
        base_outputs = build_settings_user_permission_ui_outputs(
            build_settings_user_permission_workspace(
                next_selected_user_id,
                user_result_payload={"success": success, "message": message},
            )
        )
        return (
            *base_outputs,
            *_build_current_session_permission_updates(
                current_session,
                affected_user_id=normalized_user_id,
                deleted=success,
            ),
        )

    def save_settings_user_permissions_ui(
        selected_user_id: str | None,
        tab_names: list[str] | None,
        knowledge_base_choices_selected: list[str] | None,
        current_session: dict[str, object] | None = None,
    ) -> tuple:
        """保存用户菜单与知识库权限，并刷新权限管理子页面。"""

        normalized_user_id = str(selected_user_id or "").strip()
        if not normalized_user_id:
            base_outputs = build_settings_user_permission_ui_outputs(
                build_settings_user_permission_workspace(
                    None,
                    permission_result_payload={"success": False, "message": "请选择用户"},
                )
            )
            return (*base_outputs, *_build_current_session_permission_updates(current_session))
        knowledge_base_ids = [
            kb_id
            for kb_id in (
                parse_knowledge_base_choice(choice)
                for choice in (knowledge_base_choices_selected or [])
            )
            if kb_id
        ]
        success, message = auth_service.update_user_permissions(
            normalized_user_id,
            [normalize_auth_tab_name(item) for item in (tab_names or [])],
            knowledge_base_ids,
        )
        base_outputs = build_settings_user_permission_ui_outputs(
            build_settings_user_permission_workspace(
                normalized_user_id,
                permission_result_payload={"success": success, "message": message},
            )
        )
        return (
            *base_outputs,
            *_build_current_session_permission_updates(
                current_session,
                affected_user_id=normalized_user_id if success else None,
            ),
        )

    def build_knowledge_base_refresh_outputs(
        selected_knowledge_base_id: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[gr.update, gr.update, gr.update, gr.update]:
        """构建各页面知识库下拉刷新输出。"""

        _items, choices, resolved_choice = _build_visible_knowledge_base_bundle(
            login_session,
            selected_knowledge_base_id,
        )
        update = gr.update(choices=choices, value=resolved_choice)
        return update, update, update, update

    def sync_knowledge_base_selector_outputs(
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[gr.update, gr.update, gr.update, gr.update]:
        """按当前选中的知识库同步四个页面顶部下拉。"""

        return build_knowledge_base_refresh_outputs(
            parse_knowledge_base_choice(knowledge_base_choice or ""),
            login_session,
        )

    def change_document_knowledge_base_ui(
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """切换文档管理页知识库时，同步其它页面顶部下拉。"""

        _visible_items, _visible_choices, resolved_choice = _build_visible_knowledge_base_bundle(
            login_session,
            parse_knowledge_base_choice(knowledge_base_choice or ""),
        )
        return (
            *sync_knowledge_base_selector_outputs(resolved_choice, login_session),
            *load_document_management_state_ui(resolved_choice, login_session),
        )

    def change_search_knowledge_base_ui(
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """切换检索页知识库时，同步其它页面顶部下拉。"""

        _visible_items, _visible_choices, resolved_choice = _build_visible_knowledge_base_bundle(
            login_session,
            parse_knowledge_base_choice(knowledge_base_choice or ""),
        )
        return (
            *sync_knowledge_base_selector_outputs(resolved_choice, login_session),
            *reset_search_workspace_ui(resolved_choice),
        )

    def change_quality_knowledge_base_ui(
        knowledge_base_choice: str | None = None,
        recent_quality_scope_value: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """切换 AI 质检页知识库时，同步顶部下拉并清空旧历史结果。"""

        _visible_items, _visible_choices, resolved_choice = _build_visible_knowledge_base_bundle(
            login_session,
            parse_knowledge_base_choice(knowledge_base_choice or ""),
        )
        resolved_scope_value = normalize_recent_quality_scope_value(recent_quality_scope_value)
        recent_results = list_recent_quality_results_for_choice(
            resolved_choice,
            resolved_scope_value,
            login_session,
        )
        return (
            *sync_knowledge_base_selector_outputs(resolved_choice, login_session),
            *build_quality_ui_outputs(
                build_recent_quality_view_outputs(
                    recent_results,
                    history_scope_value=resolved_scope_value,
                    replay_result=False,
                ),
            ),
        )

    def change_review_knowledge_base_ui(
        scope_value: str,
        risk_value: str,
        selected_claim_id: str,
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """切换人工审核页知识库时，同步其它页面顶部下拉。"""

        _visible_items, _visible_choices, resolved_choice = _build_visible_knowledge_base_bundle(
            login_session,
            parse_knowledge_base_choice(knowledge_base_choice or ""),
        )
        return (
            *sync_knowledge_base_selector_outputs(resolved_choice, login_session),
            *list_review_workspace_ui(
                scope_value,
                risk_value,
                selected_claim_id,
                resolved_choice,
                login_session,
            ),
        )

    def build_settings_knowledge_base_workspace(
        selected_knowledge_base_id: str | None = None,
        *,
        result_payload: dict | None = None,
        form_override: dict | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[list[list[str]], list[dict], str, str, str, str, str, bool, str]:
        """构建设置页知识库工作区数据。"""

        if login_session is None:
            is_admin = True
            allowed_kb_ids = None
        else:
            is_admin, _allowed_tabs, allowed_kb_ids = extract_login_session_permissions(login_session)
        knowledge_bases, _choices, selected_choice = build_visible_knowledge_base_bundle(
            ingest_service.list_knowledge_bases(),
            allowed_kb_ids,
            is_admin=is_admin,
            selected_knowledge_base_id=str(selected_knowledge_base_id or ""),
        )
        normalized_knowledge_base_id = parse_knowledge_base_choice(selected_choice or "")
        selected_knowledge_base = (
            ingest_service.get_knowledge_base(normalized_knowledge_base_id) if normalized_knowledge_base_id else None
        )
        detail_html = format_settings_knowledge_base_detail_html(selected_knowledge_base)
        form_values = build_knowledge_base_form_values(selected_knowledge_base)
        if form_override:
            form_values = (
                str(form_override.get("knowledge_base_id", form_values[0])),
                str(form_override.get("knowledge_base_name", form_values[1])),
                str(form_override.get("description", form_values[2])),
                str(form_override.get("status", form_values[3])),
                bool(form_override.get("is_default", form_values[4])),
            )
        return (
            build_settings_knowledge_base_rows(knowledge_bases),
            knowledge_bases,
            normalized_knowledge_base_id,
            detail_html,
            *form_values,
            format_operation_result_html(result_payload, title="知识库结果"),
        )

    def refresh_settings_knowledge_base_workspace(
        selected_knowledge_base_id: str | None,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """刷新知识库工作区。"""

        return build_settings_knowledge_base_workspace(selected_knowledge_base_id, login_session=login_session)

    def select_settings_knowledge_base(
        knowledge_base_choice: str,
        knowledge_base_items: list[dict] | None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[str, str, str, str, str, str, bool, str]:
        """切换知识库选择器后加载对应详情与表单。"""

        items = knowledge_base_items or []
        if not items:
            outputs = build_settings_knowledge_base_workspace("", login_session=login_session)
            return outputs[2], outputs[3], outputs[4], outputs[5], outputs[6], outputs[7], outputs[8], outputs[9]
        knowledge_base_id = parse_knowledge_base_choice(knowledge_base_choice)
        outputs = build_settings_knowledge_base_workspace(knowledge_base_id, login_session=login_session)
        return outputs[2], outputs[3], outputs[4], outputs[5], outputs[6], outputs[7], outputs[8], outputs[9]

    def prepare_new_knowledge_base(login_session: dict[str, object] | None = None) -> tuple[str, str, str, str, str, str, bool, str]:
        """清空表单，准备创建新知识库。"""

        blank_form = {
            "knowledge_base_id": "",
            "knowledge_base_name": "",
            "description": "",
            "status": "active",
            "is_default": False,
        }
        outputs = build_settings_knowledge_base_workspace("", form_override=blank_form, login_session=login_session)
        return "", outputs[3], outputs[4], outputs[5], outputs[6], outputs[7], outputs[8], outputs[9]

    def save_settings_knowledge_base(
        selected_knowledge_base_id: str,
        knowledge_base_id: str,
        knowledge_base_name: str,
        description: str,
        status: str,
        is_default: bool,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """保存知识库并刷新设置页与各页面选择器。"""

        form_payload = {
            "knowledge_base_id": knowledge_base_id,
            "knowledge_base_name": knowledge_base_name,
            "description": description,
            "status": status,
            "is_default": is_default,
        }
        try:
            saved_item = ingest_service.save_knowledge_base(form_payload)
        except AppError as exc:
            outputs = build_settings_knowledge_base_workspace(
                selected_knowledge_base_id,
                result_payload={"success": False, "message": exc.message, "error_code": exc.error_code},
                form_override=form_payload,
                login_session=login_session,
            )
            selector_outputs = build_knowledge_base_refresh_outputs(selected_knowledge_base_id, login_session)
            return (*outputs, *selector_outputs)
        outputs = build_settings_knowledge_base_workspace(
            saved_item.get("knowledge_base_id"),
            result_payload={"success": True, "message": "知识库已保存。"},
            login_session=login_session,
        )
        selector_outputs = build_knowledge_base_refresh_outputs(saved_item.get("knowledge_base_id"), login_session)
        return (*outputs, *selector_outputs)

    def delete_settings_knowledge_base(
        selected_knowledge_base_id: str,
        knowledge_base_id_input: str,
        login_session: dict[str, object] | None = None,
    ) -> tuple:
        """删除知识库并刷新设置页与各页面选择器。"""

        knowledge_base_id = str(knowledge_base_id_input or selected_knowledge_base_id or "").strip()
        if not knowledge_base_id:
            outputs = build_settings_knowledge_base_workspace(
                selected_knowledge_base_id,
                result_payload={"success": False, "message": "请先选择或输入知识库 ID。"},
                login_session=login_session,
            )
            selector_outputs = build_knowledge_base_refresh_outputs(selected_knowledge_base_id, login_session)
            return (*outputs, *selector_outputs)
        try:
            deleted_item = ingest_service.delete_knowledge_base(knowledge_base_id)
        except AppError as exc:
            outputs = build_settings_knowledge_base_workspace(
                selected_knowledge_base_id,
                result_payload={"success": False, "message": exc.message, "error_code": exc.error_code},
                login_session=login_session,
            )
            selector_outputs = build_knowledge_base_refresh_outputs(selected_knowledge_base_id, login_session)
            return (*outputs, *selector_outputs)
        outputs = build_settings_knowledge_base_workspace(
            "",
            result_payload={"success": True, "message": f'知识库“{deleted_item.get("knowledge_base_name") or knowledge_base_id}”已删除。'},
            login_session=login_session,
        )
        selector_outputs = build_knowledge_base_refresh_outputs("", login_session)
        return (*outputs, *selector_outputs)

    def normalize_settings_template_kind(template_kind: str | None) -> str:
        """规范设置页模板类型。"""

        return "PageIndex" if str(template_kind or "").strip().lower() == "pageindex" else "AI质检"

    def list_settings_templates(template_kind: str | None) -> list[dict]:
        """按模板类型列出设置页模板。"""

        if normalize_settings_template_kind(template_kind) == "PageIndex":
            return pageindex_service.template_service.list_templates()
        return quality_service.list_templates()

    def get_settings_template(template_kind: str | None, template_id: str | None = None) -> dict:
        """按模板类型读取设置页模板。"""

        if normalize_settings_template_kind(template_kind) == "PageIndex":
            return pageindex_service.template_service.get_template(template_id)
        return quality_service.get_template(template_id)

    def build_default_settings_template_id(template_kind: str | None, templates: list[dict]) -> str:
        """按模板类型决定设置页默认选中的模板。"""

        template_ids = {str(item.get("template_id") or "") for item in templates}
        preferred_id = "strict_qa" if normalize_settings_template_kind(template_kind) == "PageIndex" else "general_fact_check"
        return preferred_id if preferred_id in template_ids else (str(templates[0].get("template_id") or "") if templates else "")

    def build_settings_workspace(
        template_kind: str | None = "AI质检",
        selected_template_id: str | None = None,
        *,
        result_payload: dict | None = None,
        form_override: dict | None = None,
    ) -> tuple[list[list[str]], list[dict], str, str, str, str, str, str, int, int, int, bool, int, bool, int, str, str, str, str, bool]:
        """构建功能设置页所需的模板列表、详情和表单值。"""

        normalized_template_kind = normalize_settings_template_kind(template_kind)
        templates = [
            {**item, "settings_template_kind": normalized_template_kind}
            for item in list_settings_templates(normalized_template_kind)
        ]
        template_ids = {str(item.get("template_id") or "") for item in templates}
        normalized_template_id = str(selected_template_id or "")
        if normalized_template_id not in template_ids:
            normalized_template_id = build_default_settings_template_id(normalized_template_kind, templates)
        selected_template = get_settings_template(normalized_template_kind, normalized_template_id) if normalized_template_id else None
        detail_html = format_settings_template_detail_html(selected_template)
        form_values = build_settings_form_values(selected_template)
        if form_override:
            form_values = (
                str(form_override.get("template_id", form_values[0])),
                str(form_override.get("template_name", form_values[1])),
                str(form_override.get("description", form_values[2])),
                str(form_override.get("rule_tags_text", form_values[3])),
                to_int_setting(form_override.get("fulltext_top_k"), default=form_values[4]),
                to_int_setting(form_override.get("vector_top_k"), default=form_values[5]),
                to_int_setting(form_override.get("final_top_k"), default=form_values[6]),
                bool(form_override.get("use_rerank", form_values[7])),
                to_int_setting(form_override.get("neighbor_window"), default=form_values[8]),
                bool(form_override.get("include_section_context", form_values[9])),
                to_int_setting(form_override.get("section_max_chars"), default=form_values[10]),
                str(form_override.get("system_prompt", form_values[11])),
                str(form_override.get("user_prompt_template", form_values[12])),
            )
        return (
            build_settings_template_rows(templates),
            templates,
            normalized_template_id,
            detail_html,
            *form_values,
            format_operation_result_html(result_payload, title="设置结果"),
            format_settings_runtime_html(build_settings_runtime_payload()),
            False,
        )

    def refresh_settings_workspace(
        template_kind: str | None,
        selected_template_id: str | None,
    ) -> tuple[list[list[str]], list[dict], str, str, str, str, str, str, int, int, int, bool, int, bool, int, str, str, str, str, bool]:
        """刷新功能设置页。"""

        return build_settings_workspace(template_kind, selected_template_id)

    def select_settings_template(
        template_kind: str | None,
        template_items: list[dict] | None,
        evt: gr.SelectData,
        current_page_rows: list[list[object]] | None = None,
    ) -> tuple[str, str, str, str, str, str, int, int, int, bool, int, bool, int, str, str, str, bool]:
        """点击模板列表后加载对应模板详情与表单。"""

        page_rows = normalize_table_rows(current_page_rows) if current_page_rows is not None else build_settings_template_rows(template_items or [])
        items = template_items or []
        if not items or not page_rows:
            outputs = build_settings_workspace(template_kind, "")
            return outputs[2], outputs[3], outputs[4], outputs[5], outputs[6], outputs[7], outputs[8], outputs[9], outputs[10], outputs[11], outputs[12], outputs[13], outputs[14], outputs[15], outputs[16], outputs[17], outputs[19]
        selected_row = get_row_from_paged_table(page_rows, evt, id_column_index=1)
        template_id = str(selected_row[1] if len(selected_row) > 6 else (selected_row[0] if selected_row else ""))
        outputs = build_settings_workspace(template_kind, template_id)
        return outputs[2], outputs[3], outputs[4], outputs[5], outputs[6], outputs[7], outputs[8], outputs[9], outputs[10], outputs[11], outputs[12], outputs[13], outputs[14], outputs[15], outputs[16], outputs[17], outputs[19]

    def prepare_new_template(template_kind: str | None = "AI质检") -> tuple[str, str, str, str, str, str, int, int, int, bool, int, bool, int, str, str, str, bool]:
        """清空表单，准备创建新模板。"""

        blank_form = {
            "template_id": "",
            "template_name": "",
            "description": "",
            "rule_tags_text": "",
            "fulltext_top_k": 3,
            "vector_top_k": 3,
            "final_top_k": 3,
            "use_rerank": False,
            "neighbor_window": 0,
            "include_section_context": False,
            "section_max_chars": 400,
            "system_prompt": "",
            "user_prompt_template": "",
        }
        outputs = build_settings_workspace(template_kind, "", form_override=blank_form)
        return "", outputs[3], outputs[4], outputs[5], outputs[6], outputs[7], outputs[8], outputs[9], outputs[10], outputs[11], outputs[12], outputs[13], outputs[14], outputs[15], outputs[16], outputs[17], outputs[19]

    def save_settings_template(
        template_kind: str,
        selected_template_id: str,
        template_id: str,
        template_name: str,
        description: str,
        rule_tags_text: str,
        fulltext_top_k: int | float,
        vector_top_k: int | float,
        final_top_k: int | float,
        use_rerank: bool,
        neighbor_window: int | float,
        include_section_context: bool,
        section_max_chars: int | float,
        system_prompt: str,
        user_prompt_template: str,
    ) -> tuple[list[list[str]], list[dict], str, str, str, str, str, str, int, int, int, bool, int, bool, int, str, str, str, str, bool, gr.update, str, gr.update]:
        """保存模板并刷新设置页。"""

        normalized_template_kind = normalize_settings_template_kind(template_kind)
        form_payload = {
            "template_id": template_id,
            "template_name": template_name,
            "description": description,
            "rule_tags_text": rule_tags_text,
            "fulltext_top_k": fulltext_top_k,
            "vector_top_k": vector_top_k,
            "final_top_k": final_top_k,
            "use_rerank": use_rerank,
            "neighbor_window": neighbor_window,
            "include_section_context": include_section_context,
            "section_max_chars": section_max_chars,
            "system_prompt": system_prompt,
            "user_prompt_template": user_prompt_template,
        }
        try:
            if normalized_template_kind == "PageIndex":
                saved_template = pageindex_service.template_service.save_template(
                    {
                        "template_id": template_id,
                        "template_name": template_name,
                        "description": description,
                        "answer_mode": "custom",
                        "system_prompt": system_prompt,
                        "user_prompt_template": user_prompt_template,
                        "retrieval_policy": {
                            "max_tree_candidates": to_int_setting(fulltext_top_k, default=30),
                            "max_selected_nodes": to_int_setting(vector_top_k, default=3),
                            "max_rag_evidence": to_int_setting(final_top_k, default=2),
                            "include_structure_context": bool(include_section_context),
                        },
                    }
                )
            else:
                saved_template = quality_service.save_template(
                    {
                        "template_id": template_id,
                        "template_name": template_name,
                        "description": description,
                        "rule_tags": parse_rule_tags_text(rule_tags_text),
                        "system_prompt": system_prompt,
                        "user_prompt_template": user_prompt_template,
                        "retrieval_policy": {
                            "fulltext_top_k": to_int_setting(fulltext_top_k, default=3),
                            "vector_top_k": to_int_setting(vector_top_k, default=3),
                            "final_top_k": to_int_setting(final_top_k, default=3),
                            "use_rerank": bool(use_rerank),
                            "neighbor_window": to_int_setting(neighbor_window, default=0),
                            "include_section_context": bool(include_section_context),
                            "section_max_chars": to_int_setting(section_max_chars, default=400),
                        },
                    }
                )
        except AppError as exc:
            outputs = build_settings_workspace(
                normalized_template_kind,
                selected_template_id,
                result_payload={"success": False, "message": exc.message, "error_code": exc.error_code},
                form_override=form_payload,
            )
            quality_outputs = build_quality_template_refresh_outputs(selected_template_id)
            pageindex_output = build_pageindex_template_refresh_output(selected_template_id)
            return (*outputs, *quality_outputs, pageindex_output)
        outputs = build_settings_workspace(
            normalized_template_kind,
            saved_template.get("template_id"),
            result_payload={"success": True, "message": "模板已保存。", "linked_claim_id": saved_template.get("template_id")},
        )
        quality_selected_id = saved_template.get("template_id") if normalized_template_kind == "AI质检" else None
        pageindex_selected_id = saved_template.get("template_id") if normalized_template_kind == "PageIndex" else None
        quality_outputs = build_quality_template_refresh_outputs(quality_selected_id)
        pageindex_output = build_pageindex_template_refresh_output(pageindex_selected_id)
        return (*outputs, *quality_outputs, pageindex_output)

    def delete_settings_template(
        template_kind: str,
        selected_template_id: str,
        template_id_input: str,
        delete_confirmed: bool,
    ) -> tuple[list[list[str]], list[dict], str, str, str, str, str, str, int, int, int, bool, int, bool, int, str, str, str, str, bool, gr.update, str, gr.update]:
        """删除当前模板并刷新设置页。"""

        normalized_template_kind = normalize_settings_template_kind(template_kind)
        template_id = str(template_id_input or selected_template_id or "").strip()
        if not template_id:
            outputs = build_settings_workspace(
                normalized_template_kind,
                selected_template_id,
                result_payload={"success": False, "message": "请先选择或输入模板 ID。"},
            )
            quality_outputs = build_quality_template_refresh_outputs(selected_template_id)
            pageindex_output = build_pageindex_template_refresh_output(selected_template_id)
            return (*outputs, *quality_outputs, pageindex_output)
        if not delete_confirmed:
            outputs = build_settings_workspace(
                normalized_template_kind,
                selected_template_id,
                result_payload={"success": False, "message": "请先勾选“我确认删除当前模板”。"},
            )
            quality_outputs = build_quality_template_refresh_outputs(selected_template_id)
            pageindex_output = build_pageindex_template_refresh_output(selected_template_id)
            return (*outputs, *quality_outputs, pageindex_output)
        try:
            if normalized_template_kind == "PageIndex":
                deleted_template = pageindex_service.template_service.delete_template(template_id)
            else:
                deleted_template = quality_service.delete_template(template_id)
        except AppError as exc:
            outputs = build_settings_workspace(
                normalized_template_kind,
                selected_template_id,
                result_payload={"success": False, "message": exc.message, "error_code": exc.error_code},
            )
            quality_outputs = build_quality_template_refresh_outputs(selected_template_id)
            pageindex_output = build_pageindex_template_refresh_output(selected_template_id)
            return (*outputs, *quality_outputs, pageindex_output)
        outputs = build_settings_workspace(
            normalized_template_kind,
            "",
            result_payload={"success": True, "message": f'模板“{deleted_template.get("template_name") or template_id}”已删除。'},
        )
        quality_outputs = build_quality_template_refresh_outputs("")
        pageindex_output = build_pageindex_template_refresh_output("")
        return (*outputs, *quality_outputs, pageindex_output)

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
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[list[list[str]], list[list[str]], list[dict], str, dict, str, list[list[str]], list[dict], str, str, str, list[list[str]], list[dict], str, str]:
        """读取人工审核页所需的待审核列表与审核历史。"""

        if not _has_tab_access(login_session, "人工审核"):
            return build_review_workspace_outputs([], [], scope_value=scope_value, risk_value=risk_value)
        knowledge_base_id = _resolve_authorized_knowledge_base_choice(knowledge_base_choice, login_session)
        if not knowledge_base_id:
            return build_review_workspace_outputs([], [], scope_value=scope_value, risk_value=risk_value)
        try:
            review_candidates = review_service.list_review_candidates(
                limit=review_candidate_fetch_limit,
                knowledge_base_id=knowledge_base_id,
            )
            review_items, _ = review_service.list_reviews(
                page=1,
                page_size=20,
                knowledge_base_id=knowledge_base_id,
            )
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
        candidate_rows: list[list[object]],
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
        selected_row = normalized_rows[row_index] if normalized_rows[row_index] else []
        selected_claim_id = str(selected_row[1] if len(selected_row) > 8 else (selected_row[0] if selected_row else ""))
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
        current_page_rows: list[list[object]] | None = None,
    ) -> tuple[str, dict, str, list[list[str]], list[dict], str, str, str, str, str]:
        """点击已审核记录后回放对应 Claim、证据与审核结论。"""

        page_rows = normalize_table_rows(current_page_rows) if current_page_rows is not None else build_review_history_rows(format_review_history(review_items or []))
        items = review_items or []
        if not items or not page_rows:
            empty_outputs = build_review_workspace_outputs(
                review_candidates,
                [],
                scope_value=scope_value,
                risk_value=risk_value,
            )
            return empty_outputs[3], empty_outputs[4], empty_outputs[5], empty_outputs[6], empty_outputs[7], empty_outputs[8], empty_outputs[9], empty_outputs[10], empty_outputs[13], empty_outputs[14]
        selected_row = get_row_from_paged_table(page_rows, evt, id_column_index=1)
        selected_review_id = str(selected_row[1] if len(selected_row) > 8 else (selected_row[0] if selected_row else ""))
        selected_record = next((item for item in items if str(item.get("review_id") or "") == selected_review_id), None)
        if not selected_record:
            selected_record = items[0]
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
        knowledge_base_choice: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[str, list[list[str]], list[list[str]], list[dict], str, dict, str, list[list[str]], list[dict], str, str, str, list[list[str]], list[dict], str, str]:
        if not _has_tab_access(login_session, "人工审核"):
            empty_outputs = build_review_workspace_outputs([], [], scope_value=scope_value, risk_value=risk_value)
            return (
                format_operation_result_html({"success": False, "message": "当前账号没有人工审核权限。"}, title="审核结果"),
                *empty_outputs,
            )
        knowledge_base_id = _resolve_authorized_knowledge_base_choice(knowledge_base_choice, login_session)
        if not knowledge_base_id:
            empty_outputs = build_review_workspace_outputs([], [], scope_value=scope_value, risk_value=risk_value)
            return (
                format_operation_result_html({"success": False, "message": "当前账号没有可用知识库，请联系管理员开通知识库权限。"}, title="审核结果"),
                *empty_outputs,
            )
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
                reviewer=str((login_session or {}).get("username") or "ui_user"),
            )
            review_candidates = review_service.list_review_candidates(
                limit=review_candidate_fetch_limit,
                knowledge_base_id=knowledge_base_id,
            )
            review_items, _ = review_service.list_reviews(
                page=1,
                page_size=20,
                knowledge_base_id=knowledge_base_id,
            )
        except AppError as exc:
            try:
                current_candidates = review_service.list_review_candidates(
                    limit=review_candidate_fetch_limit,
                    knowledge_base_id=knowledge_base_id,
                )
            except AppError:
                current_candidates = []
            try:
                current_review_items, _ = review_service.list_reviews(
                    page=1,
                    page_size=20,
                    knowledge_base_id=knowledge_base_id,
                )
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

    def list_recent_quality_results_for_choice(
        knowledge_base_choice: str | None = None,
        history_scope_value: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> list[dict]:
        """按知识库读取最近 AI 质检历史记录。"""

        if not _has_tab_access(login_session, "AI 质检"):
            return []
        knowledge_base_id = _resolve_authorized_knowledge_base_choice(knowledge_base_choice, login_session)
        if not knowledge_base_id:
            return []
        try:
            return quality_service.list_recent_results(
                limit=RECENT_QUALITY_FETCH_LIMIT,
                knowledge_base_id=knowledge_base_id,
            )
        except AppError:
            return []

    def list_recent_quality_results(
        knowledge_base_choice: str | None = None,
        history_scope_value: str | None = None,
        login_session: dict[str, object] | None = None,
    ) -> tuple[str, str, dict, list[list[str]], str, dict, str, list[list[str]], str, list[dict], str, list[dict], list[list[str]], str]:
        results = list_recent_quality_results_for_choice(knowledge_base_choice, history_scope_value, login_session)
        return build_recent_quality_view_outputs(
            results,
            selected_index=0,
            history_scope_value=history_scope_value,
        )

    def select_recent_quality_result(
        current_page_rows: list[list[object]],
        recent_results: list[dict],
        evt: gr.SelectData,
    ) -> tuple[str, str, dict, list[list[str]], str, dict, str, list[list[str]], str, list[dict], str, str]:
        """点击最近质检记录后回放对应结果。"""

        page_rows = normalize_table_rows(current_page_rows)
        results = recent_results or []
        if not results or not page_rows:
            empty_outputs = build_recent_quality_view_outputs([])
            return (*empty_outputs[:11], empty_outputs[13])
        selected_row = get_row_from_paged_table(page_rows, evt, id_column_index=1)
        selected_check_id = str(selected_row[2] if len(selected_row) > 7 else (selected_row[0] if selected_row else ""))
        selected_index = next(
            (index for index, item in enumerate(results) if str(item.get("check_id") or "") == selected_check_id),
            0,
        )
        selected_outputs = build_recent_quality_view_outputs(results, selected_index=selected_index)
        return (*selected_outputs[:11], selected_outputs[13])

    initial_document_state = get_document_management_state()
    initial_knowledge_base_choice = initial_document_state["knowledge_base_choice"]
    initial_knowledge_base_id = resolve_knowledge_base_choice(initial_knowledge_base_choice)
    initial_document_summary = format_document_summary_html(initial_document_state["scan_summary"])
    initial_database_summary = format_database_summary_html(initial_document_state["database_summary"])
    initial_database_rows = build_database_summary_rows(initial_document_state["database_summary"])
    initial_document_detail = format_document_detail_html(initial_document_state["selected_detail"])
    (
        initial_document_quality_report,
        initial_document_quality_checks,
        initial_document_quality_section_rows,
        initial_document_quality_chunk_rows,
        initial_document_quality_search_summary,
        initial_document_quality_search_rows,
        initial_document_quality_search_state,
        initial_document_quality_search_detail,
    ) = build_document_quality_outputs(initial_document_state["selected_detail"])
    initial_document_quality_batch_summary, initial_document_quality_batch_rows = build_document_quality_batch_outputs(initial_knowledge_base_choice)
    (
        initial_document_quality_config_html,
        initial_quality_sample_limit,
        initial_quality_long_document_char_threshold,
        initial_quality_min_sections_for_long_doc,
        initial_quality_max_avg_chunks_per_section,
        initial_quality_max_chunk_chars,
        initial_quality_short_chunk_chars,
        initial_quality_short_chunk_warn_min_chunk_count,
        initial_document_quality_config_result,
    ) = build_document_quality_config_outputs()
    initial_quality_evaluation_summary = format_quality_evaluation_summary_html(None)
    initial_recent_quality_scope_value = recent_quality_scope_choices[0]
    initial_quality_evaluation_rows: list[list[str]] = []
    initial_quality_evaluation_result: dict = {}
    (
        initial_progress_html,
        initial_result_html,
        initial_formatted_quality_result,
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
        initial_quality_evaluation_cases,
    ) = build_recent_quality_view_outputs(
        list_recent_quality_results_for_choice(
            initial_knowledge_base_choice,
            initial_recent_quality_scope_value,
            None,
        ),
        history_scope_value=initial_recent_quality_scope_value,
        replay_result=False,
    )
    initial_active_quality_check_html = format_active_quality_check_html(initial_formatted_quality_result)
    try:
        initial_review_candidates = review_service.list_review_candidates(
            limit=review_candidate_fetch_limit,
            knowledge_base_id=initial_knowledge_base_id,
        )
    except AppError:
        initial_review_candidates = []
    try:
        initial_review_items, _ = review_service.list_reviews(
            page=1,
            page_size=20,
            knowledge_base_id=initial_knowledge_base_id,
        )
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
    (
        initial_settings_template_rows,
        initial_settings_template_state,
        initial_settings_selected_template_id,
        initial_settings_template_detail_html,
        initial_settings_template_id_value,
        initial_settings_template_name_value,
        initial_settings_description_value,
        initial_settings_rule_tags_value,
        initial_settings_fulltext_top_k,
        initial_settings_vector_top_k,
        initial_settings_final_top_k,
        initial_settings_use_rerank,
        initial_settings_neighbor_window,
        initial_settings_include_section_context,
        initial_settings_section_max_chars,
        initial_settings_system_prompt,
        initial_settings_user_prompt_template,
        initial_settings_result_html,
        initial_settings_runtime_html,
        initial_settings_delete_confirm,
    ) = build_settings_workspace()
    (
        initial_settings_knowledge_base_rows,
        initial_settings_knowledge_base_state,
        initial_settings_selected_knowledge_base_id,
        initial_settings_knowledge_base_detail_html,
        initial_settings_knowledge_base_id_value,
        initial_settings_knowledge_base_name_value,
        initial_settings_knowledge_base_description_value,
        initial_settings_knowledge_base_status_value,
        initial_settings_knowledge_base_is_default,
        initial_settings_knowledge_base_result_html,
    ) = build_settings_knowledge_base_workspace()
    (
        initial_settings_user_state,
        initial_settings_selected_user_id,
        initial_settings_user_choices,
        initial_settings_user_selected_choice,
        initial_settings_user_detail_html,
        initial_settings_permission_detail_html,
        initial_settings_permission_tab_values,
        initial_settings_permission_kb_choices,
        initial_settings_permission_kb_values,
        initial_settings_user_result_html,
        initial_settings_permission_result_html,
    ) = build_settings_user_permission_workspace()
    initial_database_table_rows, initial_database_page, initial_database_page_info = reset_table_pagination(
        initial_database_rows,
        prepend_sequence=True,
    )
    initial_document_table_rows, initial_document_page, initial_document_page_info = reset_table_pagination(
        initial_document_state["table_rows"],
        prepend_sequence=True,
    )
    initial_document_quality_sections_table_rows, initial_document_quality_sections_page, initial_document_quality_sections_page_info = reset_table_pagination(
        initial_document_quality_section_rows,
        prepend_sequence=True,
    )
    initial_document_quality_chunks_table_rows, initial_document_quality_chunks_page, initial_document_quality_chunks_page_info = reset_table_pagination(
        initial_document_quality_chunk_rows,
        prepend_sequence=True,
    )
    initial_document_quality_search_table_rows, initial_document_quality_search_page, initial_document_quality_search_page_info = reset_table_pagination(
        initial_document_quality_search_rows,
        prepend_sequence=False,
    )
    initial_document_quality_batch_table_rows, initial_document_quality_batch_page, initial_document_quality_batch_page_info = reset_table_pagination(
        initial_document_quality_batch_rows,
        prepend_sequence=True,
    )
    initial_search_table_rows, initial_search_page, initial_search_page_info = reset_table_pagination([], prepend_sequence=False)
    initial_pageindex_document_choices, initial_pageindex_document_choice = _build_pageindex_document_choices(initial_knowledge_base_choice)
    initial_pageindex_template_items = pageindex_service.template_service.list_templates()
    initial_pageindex_template_choices = build_template_choices(initial_pageindex_template_items)
    initial_pageindex_template_choice = next(
        (choice for choice in initial_pageindex_template_choices if parse_template_choice(choice) == "strict_qa"),
        initial_pageindex_template_choices[0] if initial_pageindex_template_choices else None,
    )
    (
        initial_pageindex_status_html,
        initial_pageindex_tree_rows,
        initial_pageindex_answer_html,
        initial_pageindex_evidence_rows,
        initial_pageindex_debug_rows,
        initial_pageindex_history_rows,
        initial_pageindex_history_state,
        initial_pageindex_active_query_id,
        initial_pageindex_export_result_html,
        initial_pageindex_download_file,
    ) = _build_pageindex_selected_document_state(initial_knowledge_base_choice, initial_pageindex_document_choice)
    initial_quality_claim_table_rows, initial_quality_claim_page, initial_quality_claim_page_info = reset_table_pagination(
        initial_claim_rows,
        prepend_sequence=True,
    )
    initial_claim_evidence_table_rows, initial_claim_evidence_page, initial_claim_evidence_page_info = reset_table_pagination(
        initial_evidence_rows,
        prepend_sequence=True,
    )
    initial_recent_quality_table_rows, initial_recent_quality_page, initial_recent_quality_page_info = reset_table_pagination(
        initial_recent_rows,
        prepend_sequence=True,
    )
    initial_quality_evaluation_table_rows, initial_quality_evaluation_page, initial_quality_evaluation_page_info = reset_table_pagination(
        initial_quality_evaluation_rows,
        prepend_sequence=True,
    )
    quality_dummy_claim_choices = [
        "C1 | 高风险 | 阿胶可以直接替代所有补血药",
        "C2 | 中风险 | 《神农本草经》明确记载阿胶用于延年不老",
        "C3 | 低风险 | 阿胶在古籍中常与补血场景关联",
        "C4 | 待拆分 | 阿胶既能安胎又能治疗所有出血症",
    ]
    quality_dummy_evidence_rows = _build_quality_dummy_evidence_rows()
    quality_dummy_history_rows = _build_quality_dummy_history_rows()
    initial_review_pending_table_rows, initial_review_pending_page, initial_review_pending_page_info = reset_table_pagination(
        initial_review_pending_rows,
        prepend_sequence=True,
    )
    initial_review_processed_table_rows, initial_review_processed_page, initial_review_processed_page_info = reset_table_pagination(
        initial_review_processed_rows,
        prepend_sequence=True,
    )
    initial_review_evidence_table_rows, initial_review_evidence_page, initial_review_evidence_page_info = reset_table_pagination(
        initial_review_evidence_rows,
        prepend_sequence=True,
    )
    initial_review_history_table_rows, initial_review_history_page, initial_review_history_page_info = reset_table_pagination(
        initial_review_rows,
        prepend_sequence=True,
    )
    initial_settings_template_table_rows, initial_settings_template_page, initial_settings_template_page_info = reset_table_pagination(
        initial_settings_template_rows,
        prepend_sequence=True,
    )
    (
        initial_settings_knowledge_base_choices,
        initial_settings_knowledge_base_selected_choice,
        initial_settings_knowledge_base_page,
        initial_settings_knowledge_base_page_info,
    ) = build_settings_knowledge_base_selector_page_outputs(
        initial_settings_knowledge_base_state,
        initial_settings_selected_knowledge_base_id,
    )

    def _empty_login_session() -> dict[str, object]:
        """构造默认空登录态。"""
        return {"user_id": None, "username": None, "is_admin": False, "permissions": None}

    def _build_login_session(user_id: str) -> dict[str, object]:
        """按用户 ID 重建登录态，确保刷新后权限仍以数据库最新值为准。"""
        user = auth_service.get_user_by_id(user_id)
        if not user:
            return _empty_login_session()
        perms = auth_service.get_user_permissions(user.user_id)
        return {
            "user_id": user.user_id,
            "username": user.username,
            "is_admin": user.is_admin,
            "permissions": {"tab_names": perms.tab_names, "kb_ids": perms.kb_ids} if perms else {"tab_names": [], "kb_ids": []},
        }

    def _render_auth_user(username: str | None) -> str:
        """渲染头部用户名称，保持与菜单文字一致的轻样式。"""
        if not username:
            return ""
        return f"<span>{username}</span>"

    def _render_pending_access_html(session: dict[str, object] | None) -> str:
        """为零权限用户渲染统一的待开通提示页。"""

        username = ""
        if isinstance(session, dict):
            username = str(session.get("username") or "").strip()
        display_name = username or "当前账号"
        return (
            "<section class='settings-detail-card' id='pending-access-card'>"
            "<h3>功能待开通</h3>"
            f"<p><strong>当前用户：</strong>{display_name}</p>"
            "<p><strong>当前菜单权限：</strong>无</p>"
            "<p><strong>当前知识库权限：</strong>无</p>"
            "<p>当前账号已登录，但尚未开通任何业务功能，请联系管理员配置菜单权限和知识库权限。</p>"
            "</section>"
        )

    def _extract_session_permissions(session: dict[str, object] | None) -> tuple[bool, set[str] | None, set[str] | None]:
        """从登录态中解析管理员标记、页签权限和知识库权限。"""

        return extract_login_session_permissions(session)

    def _build_quality_permission_updates(
        session: dict[str, object] | None,
        history_scope_value: str | None = None,
    ) -> tuple:
        """按当前权限重置 AI 质检页状态，并自动加载历史列表。"""

        resolved_scope_value = normalize_recent_quality_scope_value(history_scope_value)
        resolved_choice = _build_visible_knowledge_base_bundle(session)[2]
        if not resolved_choice:
            return build_quality_ui_outputs(
                build_recent_quality_view_outputs([], history_scope_value=resolved_scope_value),
            )
        recent_results = list_recent_quality_results_for_choice(
            resolved_choice,
            resolved_scope_value,
            session,
        )
        return build_quality_ui_outputs(
            build_recent_quality_view_outputs(
                recent_results,
                history_scope_value=resolved_scope_value,
                replay_result=False,
            ),
        )

    def _build_main_tabs_update(session: dict[str, object] | None, *, select_default_tab: bool = False):
        """按登录入口需要选中默认主菜单。"""

        if select_default_tab and _has_tab_access(session, "AI 质检"):
            return gr.update(selected=MAIN_TAB_IDS["AI 质检"])
        return gr.update()

    def _build_permission_ui_updates(session: dict[str, object] | None, *, select_default_tab: bool = False) -> tuple:
        """根据登录态生成页签和知识库组件的可见性更新。"""

        is_admin, allowed_tabs, _allowed_kb_ids = _extract_session_permissions(session)
        logged_in = bool(isinstance(session, dict) and str(session.get("user_id") or "").strip())
        show_pending_access_tab = logged_in and not is_admin and allowed_tabs is not None and not allowed_tabs
        knowledge_base_session = session if logged_in else None
        visible_items, visible_choices, default_choice = _build_visible_knowledge_base_bundle(knowledge_base_session)
        selected_kb_id = parse_knowledge_base_choice(default_choice or "")
        (
            settings_choices,
            settings_selected_choice,
            settings_page_value,
            settings_page_info,
        ) = build_settings_knowledge_base_selector_page_outputs(
            visible_items,
            selected_kb_id,
        )
        tab_visibility_updates = tuple(
            gr.update(visible=(not show_pending_access_tab) and (is_admin or allowed_tabs is None or tab_name in allowed_tabs))
            for tab_name in MAIN_TAB_NAMES
        )
        knowledge_base_update = gr.update(choices=visible_choices, value=default_choice)
        settings_table_update = gr.update(choices=settings_choices, value=settings_selected_choice)
        return (
            gr.update(visible=show_pending_access_tab),
            *tab_visibility_updates,
            gr.update(value=_render_pending_access_html(session)),
            _build_main_tabs_update(session, select_default_tab=select_default_tab),
            knowledge_base_update,
            knowledge_base_update,
            knowledge_base_update,
            knowledge_base_update,
            knowledge_base_update,
            knowledge_base_update,
            visible_items,
            settings_table_update,
            settings_page_value,
            format_table_pagination_html(settings_page_info),
        )

    def _build_review_permission_updates(
        session: dict[str, object] | None,
        *,
        scope_value: str | None = None,
        risk_value: str | None = None,
    ) -> tuple:
        """按当前权限重置人工审核页知识库与历史状态，避免残留未授权数据。"""

        resolved_scope = normalize_review_scope_value(scope_value or review_scope_choices[0])
        resolved_risk = normalize_review_risk_value(risk_value or review_risk_choices[0])
        _visible_items, _visible_choices, default_choice = _build_visible_knowledge_base_bundle(session)
        return list_review_workspace_ui(
            resolved_scope,
            resolved_risk,
            "",
            default_choice,
            session,
        )

    def _build_document_permission_updates(session: dict[str, object] | None) -> tuple:
        """按当前权限刷新文档管理页，避免保留旧知识库文档状态。"""

        _visible_items, _visible_choices, default_choice = _build_visible_knowledge_base_bundle(session)
        return load_document_management_state_ui(default_choice, session)

    def _build_search_permission_updates(session: dict[str, object] | None) -> tuple:
        """按当前权限清空检索结果，避免保留旧知识库检索 state。"""

        _visible_items, _visible_choices, default_choice = _build_visible_knowledge_base_bundle(session)
        return reset_search_workspace_ui(default_choice)

    def _build_current_session_permission_updates(
        current_session: dict[str, object] | None,
        *,
        affected_user_id: str | None = None,
        deleted: bool = False,
    ) -> tuple:
        """当后台修改用户或权限后，按需即时刷新当前登录态与主界面权限。"""

        session = current_session or _empty_login_session()
        current_user_id = str(session.get("user_id") or "").strip()
        normalized_affected_user_id = str(affected_user_id or "").strip()
        if not current_user_id:
            return (
                session,
                session,
                _render_auth_user(str(session.get("username") or "")),
                gr.update(),
                gr.update(),
                *_build_permission_ui_updates(session),
                *_build_quality_permission_updates(session),
                *_build_review_permission_updates(session),
                *_build_document_permission_updates(session)[4:],
                *_build_search_permission_updates(session),
            )
        if deleted and normalized_affected_user_id == current_user_id:
            empty_session = _empty_login_session()
            return (
                empty_session,
                empty_session,
                "",
                gr.update(visible=True),
                gr.update(visible=False),
                *_build_permission_ui_updates(empty_session),
                *_build_quality_permission_updates(empty_session),
                *_build_review_permission_updates(empty_session),
                *_build_document_permission_updates(empty_session)[4:],
                *_build_search_permission_updates(empty_session),
            )
        if normalized_affected_user_id and normalized_affected_user_id == current_user_id:
            refreshed_session = _build_login_session(current_user_id)
            return (
                refreshed_session,
                refreshed_session,
                _render_auth_user(str(refreshed_session.get("username") or "")),
                gr.update(),
                gr.update(),
                *_build_permission_ui_updates(refreshed_session),
                *_build_quality_permission_updates(refreshed_session),
                *_build_review_permission_updates(refreshed_session),
                *_build_document_permission_updates(refreshed_session)[4:],
                *_build_search_permission_updates(refreshed_session),
            )
        return (
            session,
            session,
            _render_auth_user(str(session.get("username") or "")),
            gr.update(),
            gr.update(),
            *_build_permission_ui_updates(session),
            *_build_quality_permission_updates(session),
            *_build_review_permission_updates(session),
            *_build_document_permission_updates(session)[4:],
            *_build_search_permission_updates(session),
        )

    with gr.Blocks(title="基于文档的知识库AI查询系统") as demo:
        login_state = gr.State(_empty_login_session())
        login_restore_initialized = gr.State(False)
        persisted_login_state = gr.BrowserState(
            _empty_login_session(),
            storage_key=AUTH_SESSION_STORAGE_KEY,
            secret=AUTH_SESSION_SECRET,
        )
        # 登录页面
        with gr.Column(elem_id="auth-page", visible=False) as auth_page:
            with gr.Column(elem_id="auth-center-container"):
                gr.Markdown("# 基于文档的知识库AI查询系统")
                auth_login_form = gr.Column(elem_id="auth-login-form", visible=True)
                with auth_login_form:
                    gr.Markdown("### 登录")
                    auth_login_username = gr.Textbox(label="用户名", placeholder="请输入用户名", elem_id="auth-login-username")
                    auth_login_password = gr.Textbox(label="密码", type="password", placeholder="请输入密码", elem_id="auth-login-password")
                    auth_login_result = gr.HTML(elem_id="auth-login-result")
                    with gr.Row():
                        auth_login_submit = ui_button("登录", variant="primary")
                        auth_register_btn = ui_button("注册新用户")
                auth_register_form = gr.Column(elem_id="auth-register-form", visible=False)
                with auth_register_form:
                    gr.Markdown("### 注册新用户")
                    auth_register_username = gr.Textbox(label="用户名", placeholder="请输入用户名", elem_id="auth-register-username")
                    auth_register_password = gr.Textbox(label="密码", type="password", placeholder="请设置密码", elem_id="auth-register-password")
                    auth_register_password_confirm = gr.Textbox(label="重复密码", type="password", placeholder="再次输入密码", elem_id="auth-register-password-confirm")
                    auth_register_result = gr.HTML(elem_id="auth-register-result")
                    with gr.Row():
                        auth_register_submit = ui_button("注册", variant="primary")
                        auth_login_btn = ui_button("返回登录")
        # 主内容
        with gr.Column(elem_id="main-content", visible=False) as main_content:
            with gr.Row(elem_id="auth-header-actions"):
                auth_user_display = gr.HTML(value="", elem_id="auth-user-display")
                auth_logout_btn = gr.Button("退出登录", elem_id="auth-logout-btn", variant="secondary")
            with gr.Tabs(elem_id="main-tabs") as main_tabs:
                with gr.Tab("待开通", visible=False, id=MAIN_TAB_IDS["待开通"]) as pending_access_tab:
                    pending_access_view = gr.HTML(
                        value=_render_pending_access_html(_empty_login_session()),
                        elem_id="pending-access-view",
                    )
                with gr.Tab("AI 质检", visible=False, id=MAIN_TAB_IDS["AI 质检"]) as quality_tab:
                    initial_claim_choices, initial_selected_claim_choice, _initial_claim_choice_page, _initial_claim_choice_page_info = build_quality_claim_selector_page_outputs(
                        initial_formatted_quality_result,
                        initial_selected_claim,
                        initial_quality_claim_page,
                    )
                    quality_components = build_quality_tab(
                        knowledge_base_choices=knowledge_base_choices,
                        initial_knowledge_base_choice=initial_knowledge_base_choice,
                        template_choices=template_choices,
                        default_template_choice=default_template_choice,
                        default_template=default_template,
                        initial_formatted_quality_result=initial_formatted_quality_result,
                        initial_quality_claim_page=initial_quality_claim_page,
                        initial_quality_claim_choices=initial_claim_choices,
                        initial_selected_claim_choice=initial_selected_claim_choice,
                        initial_selected_claim=initial_selected_claim,
                        initial_quality_claim_page_info=initial_quality_claim_page_info,
                        initial_claim_view=initial_claim_view,
                        initial_claim_detail_map=initial_claim_detail_map,
                        initial_review_view=initial_review_view,
                        initial_evidence_items=initial_evidence_items,
                        initial_claim_evidence_page=initial_claim_evidence_page,
                        initial_claim_evidence_table_rows=initial_claim_evidence_table_rows,
                        initial_claim_evidence_page_info=initial_claim_evidence_page_info,
                        initial_evidence_detail_html=initial_evidence_detail_html,
                        recent_quality_scope_choices=recent_quality_scope_choices,
                        initial_recent_quality_scope_value=initial_recent_quality_scope_value,
                        initial_recent_results_state=_initial_recent_results_state,
                        initial_recent_quality_page=initial_recent_quality_page,
                        initial_recent_quality_table_rows=initial_recent_quality_table_rows,
                        initial_recent_quality_page_info=initial_recent_quality_page_info,
                        initial_progress_html=initial_progress_html,
                        initial_result_html=initial_result_html,
                        initial_active_quality_check_html=initial_active_quality_check_html,
                        initial_quality_evaluation_cases=initial_quality_evaluation_cases,
                        initial_quality_evaluation_summary=initial_quality_evaluation_summary,
                        initial_quality_evaluation_result=initial_quality_evaluation_result,
                        initial_quality_evaluation_page=initial_quality_evaluation_page,
                        initial_quality_evaluation_table_rows=initial_quality_evaluation_table_rows,
                        initial_quality_evaluation_page_info=initial_quality_evaluation_page_info,
                    )
                    quality_knowledge_base = quality_components["quality_knowledge_base"]
                    quality_template = quality_components["quality_template"]
                    quality_template_detail = quality_components["quality_template_detail"]
                    formatted_quality_result_state = quality_components["formatted_quality_result_state"]
                    quality_claim_page_state = quality_components["quality_claim_page_state"]
                    quality_evidence_page_state = quality_components["quality_evidence_page_state"]
                    recent_quality_page_state = quality_components["recent_quality_page_state"]
                    quality_progress = quality_components["quality_progress"]
                    quality_result = quality_components["quality_result"]
                    selected_claim_state = quality_components["selected_claim_state"]
                    claim_detail_state = quality_components["claim_detail_state"]
                    recent_quality_state = quality_components["recent_quality_state"]
                    evidence_items_state = quality_components["evidence_items_state"]
                    quality_active_check = quality_components["quality_active_check"]
                    quality_claims = quality_components["quality_claims"]
                    quality_claim_page_info = quality_components["quality_claim_page_info"]
                    claim_detail_view = quality_components["claim_detail_view"]
                    quality_review_claim_detail = quality_components["quality_review_claim_detail"]
                    claim_evidence_table = quality_components["claim_evidence_table"]
                    quality_evidence_page_info = quality_components["quality_evidence_page_info"]
                    claim_evidence_detail = quality_components["claim_evidence_detail"]
                    recent_quality_checks = quality_components["recent_quality_checks"]
                    recent_quality_page_info = quality_components["recent_quality_page_info"]
                    quality_evaluation_cases = quality_components["quality_evaluation_cases"]

                build_quality_dummy_tab(
                    claim_choices=quality_dummy_claim_choices,
                    evidence_rows=quality_dummy_evidence_rows,
                    history_rows=quality_dummy_history_rows,
                    build_top_help_html=_build_quality_dummy_top_help_html,
                    build_template_html=_build_quality_dummy_template_html,
                    build_progress_html=_build_quality_dummy_progress_html,
                    build_result_html=_build_quality_dummy_result_html,
                    build_active_check_html=_build_quality_dummy_active_check_html,
                    build_focus_html=_build_quality_dummy_focus_html,
                    build_evidence_detail_html=_build_quality_dummy_evidence_detail_html,
                    build_export_result_html=_build_quality_dummy_export_result_html,
                    build_actions_html=_build_quality_dummy_actions_html,
                    build_evaluation_help_html=_build_quality_dummy_evaluation_help_html,
                    build_evaluation_summary_html=_build_quality_dummy_evaluation_summary_html,
                    build_evaluation_rows=_build_quality_dummy_evaluation_rows,
                    build_help_html=_build_quality_dummy_help_html,
                )

                with gr.Tab("人工审核", visible=False, id=MAIN_TAB_IDS["人工审核"]) as review_tab:
                    review_candidate_state = gr.State(initial_review_candidate_items_state)
                    review_history_state = gr.State(initial_review_items_state)
                    review_selected_record_state = gr.State(initial_selected_review_id)
                    review_selected_claim_state = gr.State(initial_review_selected_claim_id)
                    review_claim_detail_state = gr.State(initial_review_claim_detail_map)
                    review_evidence_items_state = gr.State(initial_review_evidence_items)
                    review_pending_page_state = gr.State(initial_review_pending_page)
                    review_processed_page_state = gr.State(initial_review_processed_page)
                    review_evidence_page_state = gr.State(initial_review_evidence_page)
                    review_history_page_state = gr.State(initial_review_history_page)
                    review_components = build_review_tab(
                        knowledge_base_choices=knowledge_base_choices,
                        initial_knowledge_base_choice=initial_knowledge_base_choice,
                        review_scope_choices=review_scope_choices,
                        review_risk_choices=review_risk_choices,
                        review_action_choices=review_action_choices,
                        initial_review_pending_table_rows=initial_review_pending_table_rows,
                        initial_review_pending_page_info=initial_review_pending_page_info,
                        initial_review_processed_table_rows=initial_review_processed_table_rows,
                        initial_review_processed_page_info=initial_review_processed_page_info,
                        initial_review_claim_view=initial_review_claim_view,
                        initial_review_evidence_detail_html=initial_review_evidence_detail_html,
                        initial_review_evidence_table_rows=initial_review_evidence_table_rows,
                        initial_review_evidence_page_info=initial_review_evidence_page_info,
                        initial_review_action_value=initial_review_action_value,
                        initial_review_note_value=initial_review_note_value,
                        initial_review_history_table_rows=initial_review_history_table_rows,
                        initial_review_history_page_info=initial_review_history_page_info,
                        initial_review_record_detail_html=initial_review_record_detail_html,
                    )
                    review_knowledge_base = review_components["review_knowledge_base"]
                    review_pending_candidates = review_components["review_pending_candidates"]
                    review_pending_page_info = review_components["review_pending_page_info"]
                    review_processed_candidates = review_components["review_processed_candidates"]
                    review_processed_page_info = review_components["review_processed_page_info"]
                    review_claim_detail_panel = review_components["review_claim_detail_panel"]
                    review_evidence_detail = review_components["review_evidence_detail"]
                    review_evidence_table = review_components["review_evidence_table"]
                    review_evidence_page_info = review_components["review_evidence_page_info"]
                    review_action_input = review_components["review_action_input"]
                    review_note_input = review_components["review_note_input"]
                    review_history = review_components["review_history"]
                    review_history_page_info = review_components["review_history_page_info"]
                    review_record_detail = review_components["review_record_detail"]

                with gr.Tab("知识库管理", visible=False, id=MAIN_TAB_IDS["知识库管理"]) as document_tab:
                    database_page_state = gr.State(initial_database_page)
                    document_page_state = gr.State(initial_document_page)
                    document_quality_sections_page_state = gr.State(initial_document_quality_sections_page)
                    document_quality_chunks_page_state = gr.State(initial_document_quality_chunks_page)
                    document_quality_search_page_state = gr.State(initial_document_quality_search_page)
                    document_quality_batch_page_state = gr.State(initial_document_quality_batch_page)
                    document_quality_search_state = gr.State(initial_document_quality_search_state)
                    document_quality_search_query_state = gr.State("")
                    document_components = build_document_tab(
                        initial_values={
                            "knowledge_base_choices": knowledge_base_choices,
                            "initial_knowledge_base_choice": initial_knowledge_base_choice,
                            "document_summary": initial_document_summary,
                            "database_summary": initial_database_summary,
                            "document_choices": initial_document_state["document_choices"],
                            "active_choice": initial_document_state["active_choice"],
                            "document_detail": initial_document_detail,
                            "register_interactive": initial_document_state["register_interactive"],
                            "rebuild_interactive": initial_document_state["rebuild_interactive"],
                            "database_table_rows": initial_database_table_rows,
                            "database_page_info": initial_database_page_info,
                            "document_table_rows": initial_document_table_rows,
                            "document_page_info": initial_document_page_info,
                            "document_quality_report": initial_document_quality_report,
                            "document_quality_checks": initial_document_quality_checks,
                            "document_quality_sections_table_rows": initial_document_quality_sections_table_rows,
                            "document_quality_sections_page_info": initial_document_quality_sections_page_info,
                            "document_quality_chunks_table_rows": initial_document_quality_chunks_table_rows,
                            "document_quality_chunks_page_info": initial_document_quality_chunks_page_info,
                            "document_quality_search_summary": initial_document_quality_search_summary,
                            "document_quality_search_table_rows": initial_document_quality_search_table_rows,
                            "document_quality_search_page_info": initial_document_quality_search_page_info,
                            "document_quality_search_detail": initial_document_quality_search_detail,
                            "document_quality_batch_summary": initial_document_quality_batch_summary,
                            "document_quality_batch_table_rows": initial_document_quality_batch_table_rows,
                            "document_quality_batch_page_info": initial_document_quality_batch_page_info,
                            "document_quality_config_html": initial_document_quality_config_html,
                            "document_quality_config_result": initial_document_quality_config_result,
                            "quality_sample_limit": initial_quality_sample_limit,
                            "quality_long_document_char_threshold": initial_quality_long_document_char_threshold,
                            "quality_min_sections_for_long_doc": initial_quality_min_sections_for_long_doc,
                            "quality_max_avg_chunks_per_section": initial_quality_max_avg_chunks_per_section,
                            "quality_max_chunk_chars": initial_quality_max_chunk_chars,
                            "quality_short_chunk_chars": initial_quality_short_chunk_chars,
                            "quality_short_chunk_warn_min_chunk_count": initial_quality_short_chunk_warn_min_chunk_count,
                        }
                    )
                    document_knowledge_base = document_components["document_knowledge_base"]
                    document_target_knowledge_base = document_components["document_target_knowledge_base"]

                with gr.Tab("知识库检索", visible=False, id=MAIN_TAB_IDS["知识库检索"]) as search_tab:
                    search_components = build_search_tab(
                        knowledge_base_choices=knowledge_base_choices,
                        initial_knowledge_base_choice=initial_knowledge_base_choice,
                        initial_search_table_rows=initial_search_table_rows,
                        initial_search_page=initial_search_page,
                        initial_search_page_info=initial_search_page_info,
                    )
                    search_knowledge_base = search_components["search_knowledge_base"]

                with gr.Tab("PageIndex 深度检索", visible=False, id=MAIN_TAB_IDS["PageIndex 深度检索"]) as pageindex_tab:
                    pageindex_components = build_pageindex_tab(
                        knowledge_base_choices=knowledge_base_choices,
                        initial_knowledge_base_choice=initial_knowledge_base_choice,
                        document_choices=initial_pageindex_document_choices,
                        initial_document_choice=initial_pageindex_document_choice,
                        template_choices=initial_pageindex_template_choices,
                        initial_template_choice=initial_pageindex_template_choice,
                        initial_status_html=initial_pageindex_status_html,
                        initial_tree_rows=initial_pageindex_tree_rows,
                        initial_answer_html=initial_pageindex_answer_html,
                        initial_evidence_rows=initial_pageindex_evidence_rows,
                        initial_debug_rows=initial_pageindex_debug_rows,
                        initial_history_rows=initial_pageindex_history_rows,
                        initial_history_state=initial_pageindex_history_state,
                        initial_active_query_id=initial_pageindex_active_query_id,
                        initial_export_result_html=initial_pageindex_export_result_html,
                    )
                    pageindex_knowledge_base = pageindex_components["pageindex_knowledge_base"]
                    pageindex_template = pageindex_components["pageindex_template"]

                with gr.Tab("功能设置", visible=False, id=MAIN_TAB_IDS["功能设置"]) as settings_tab:
                    settings_template_state = gr.State(initial_settings_template_state)
                    settings_selected_template_state = gr.State(initial_settings_selected_template_id)
                    settings_template_page_state = gr.State(initial_settings_template_page)
                    settings_knowledge_base_state = gr.State(initial_settings_knowledge_base_state)
                    settings_selected_knowledge_base_state = gr.State(initial_settings_selected_knowledge_base_id)
                    settings_knowledge_base_page_state = gr.State(initial_settings_knowledge_base_page)
                    settings_user_state = gr.State(initial_settings_user_state)
                    settings_selected_user_state = gr.State(initial_settings_selected_user_id)
                    settings_components = build_settings_tab(
                        initial_values={
                            "runtime_html": initial_settings_runtime_html,
                            "template_table_rows": initial_settings_template_table_rows,
                            "template_page_info": initial_settings_template_page_info,
                            "template_kind": "AI质检",
                            "template_detail_html": initial_settings_template_detail_html,
                            "template_id": initial_settings_template_id_value,
                            "template_name": initial_settings_template_name_value,
                            "template_description": initial_settings_description_value,
                            "rule_tags": initial_settings_rule_tags_value,
                            "fulltext_top_k": initial_settings_fulltext_top_k,
                            "vector_top_k": initial_settings_vector_top_k,
                            "final_top_k": initial_settings_final_top_k,
                            "neighbor_window": initial_settings_neighbor_window,
                            "section_max_chars": initial_settings_section_max_chars,
                            "use_rerank": initial_settings_use_rerank,
                            "include_section_context": initial_settings_include_section_context,
                            "system_prompt": initial_settings_system_prompt,
                            "user_prompt_template": initial_settings_user_prompt_template,
                            "delete_confirm": initial_settings_delete_confirm,
                            "knowledge_base_choices": initial_settings_knowledge_base_choices,
                            "knowledge_base_selected_choice": initial_settings_knowledge_base_selected_choice,
                            "knowledge_base_page_info": initial_settings_knowledge_base_page_info,
                            "knowledge_base_detail_html": initial_settings_knowledge_base_detail_html,
                            "knowledge_base_id": initial_settings_knowledge_base_id_value,
                            "knowledge_base_name": initial_settings_knowledge_base_name_value,
                            "knowledge_base_description": initial_settings_knowledge_base_description_value,
                            "knowledge_base_status": initial_settings_knowledge_base_status_value,
                            "knowledge_base_is_default": initial_settings_knowledge_base_is_default,
                            "knowledge_base_result_html": initial_settings_knowledge_base_result_html,
                            "result_html": initial_settings_result_html,
                            "user_choices": initial_settings_user_choices,
                            "user_selected_choice": initial_settings_user_selected_choice,
                            "user_detail_html": initial_settings_user_detail_html,
                            "user_result_html": initial_settings_user_result_html,
                            "permission_user_choices": initial_settings_user_choices,
                            "permission_user_selected_choice": initial_settings_user_selected_choice,
                            "permission_detail_html": initial_settings_permission_detail_html,
                            "permission_tab_choices": AUTH_TAB_NAMES,
                            "permission_tab_values": initial_settings_permission_tab_values,
                            "permission_kb_choices": initial_settings_permission_kb_choices,
                            "permission_kb_values": initial_settings_permission_kb_values,
                            "permission_result_html": initial_settings_permission_result_html,
                        },
                    )
                    settings_knowledge_base_table = settings_components["settings_knowledge_base_table"]
                    settings_knowledge_base_page_info = settings_components["settings_knowledge_base_page_info"]

            bind_document_events(
                components=document_components,
                login_state=login_state,
                search_knowledge_base=search_knowledge_base,
                pageindex_knowledge_base=pageindex_knowledge_base,
                quality_knowledge_base=quality_knowledge_base,
                review_knowledge_base=review_knowledge_base,
                database_page_state=database_page_state,
                document_page_state=document_page_state,
                document_quality_sections_page_state=document_quality_sections_page_state,
                document_quality_chunks_page_state=document_quality_chunks_page_state,
                document_quality_search_page_state=document_quality_search_page_state,
                document_quality_batch_page_state=document_quality_batch_page_state,
                document_quality_search_state=document_quality_search_state,
                document_quality_search_query_state=document_quality_search_query_state,
                load_document_management_state_ui=load_document_management_state_ui,
                change_document_knowledge_base_ui=change_document_knowledge_base_ui,
                reassign_selected_document_ui=reassign_selected_document_ui,
                inspect_document_ui=inspect_document_ui,
                register_selected_document_ui=register_selected_document_ui,
                register_all_documents_ui=register_all_documents_ui,
                query_ingest_status_ui=query_ingest_status_ui,
                rebuild_selected_document_ui=rebuild_selected_document_ui,
                inspect_selected_document_quality_ui=inspect_selected_document_quality_ui,
                run_document_quality_search_ui=run_document_quality_search_ui,
                select_document_quality_search_result=select_document_quality_search_result,
                export_document_quality_result=export_document_quality_result,
                export_document_quality_search_result=export_document_quality_search_result,
                run_batch_document_quality_ui=run_batch_document_quality_ui,
                export_document_quality_batch_result=export_document_quality_batch_result,
                export_document_quality_csv=export_document_quality_csv,
                save_document_quality_config=save_document_quality_config,
                export_document_quality_config_result=export_document_quality_config_result,
                change_database_summary_page=change_database_summary_page,
                change_document_list_page=change_document_list_page,
                change_document_quality_sections_page=change_document_quality_sections_page,
                change_document_quality_chunks_page=change_document_quality_chunks_page,
                change_document_table_page=change_document_table_page,
                change_document_quality_batch_page=change_document_quality_batch_page,
            )
            bind_search_events(
                components=search_components,
                login_state=login_state,
                document_knowledge_base=document_knowledge_base,
                quality_knowledge_base=quality_knowledge_base,
                review_knowledge_base=review_knowledge_base,
                run_search_ui=run_search_ui,
                change_search_knowledge_base_ui=change_search_knowledge_base_ui,
                select_search_result=select_search_result,
                change_search_page=change_search_page,
                export_search_results=export_search_results,
            )
            bind_quality_events(
                components=quality_components,
                login_state=login_state,
                document_knowledge_base=document_knowledge_base,
                search_knowledge_base=search_knowledge_base,
                review_knowledge_base=review_knowledge_base,
                run_quality_check_ui=run_quality_check_ui,
                render_quality_template=render_quality_template,
                list_recent_quality_results_ui=list_recent_quality_results_ui,
                change_quality_knowledge_base_ui=change_quality_knowledge_base_ui,
                select_recent_quality_result_ui=select_recent_quality_result_ui,
                select_quality_claim_ui=select_quality_claim_ui,
                select_quality_evidence=select_quality_evidence,
                change_quality_claim_page=change_quality_claim_page,
                change_quality_evidence_page=change_quality_evidence_page,
                change_recent_quality_page=change_recent_quality_page,
                export_quality_results=export_quality_results,
                run_quality_evaluation_ui=run_quality_evaluation_ui,
                change_quality_evaluation_page=change_quality_evaluation_page,
                export_quality_evaluation_results=export_quality_evaluation_results,
            )
            bind_pageindex_events(
                components=pageindex_components,
                change_knowledge_base=change_pageindex_knowledge_base_ui,
                change_document=change_pageindex_document_ui,
                build_index=build_pageindex_index_ui,
                ask_question=ask_pageindex_question_ui,
                select_history=select_pageindex_history_ui,
                export_results=export_pageindex_results_ui,
            )
            document_components_for_settings = {
                **document_components,
                "database_page_state": database_page_state,
                "document_page_state": document_page_state,
                "document_quality_sections_page_state": document_quality_sections_page_state,
                "document_quality_chunks_page_state": document_quality_chunks_page_state,
                "document_quality_search_page_state": document_quality_search_page_state,
                "document_quality_batch_page_state": document_quality_batch_page_state,
                "document_quality_search_state": document_quality_search_state,
            }
            bind_settings_events(
                components=settings_components,
                settings_template_state=settings_template_state,
                settings_selected_template_state=settings_selected_template_state,
                settings_template_page_state=settings_template_page_state,
                settings_knowledge_base_state=settings_knowledge_base_state,
                settings_selected_knowledge_base_state=settings_selected_knowledge_base_state,
                settings_knowledge_base_page_state=settings_knowledge_base_page_state,
                settings_user_state=settings_user_state,
                settings_selected_user_state=settings_selected_user_state,
                document_components=document_components_for_settings,
                search_components=search_components,
                login_state=login_state,
                persisted_login_state=persisted_login_state,
                auth_user_display=auth_user_display,
                auth_page=auth_page,
                main_content=main_content,
                main_tabs=main_tabs,
                pending_access_tab=pending_access_tab,
                quality_tab=quality_tab,
                review_tab=review_tab,
                document_tab=document_tab,
                search_tab=search_tab,
                pageindex_tab=pageindex_tab,
                settings_tab=settings_tab,
                pending_access_view=pending_access_view,
                quality_template=quality_template,
                quality_template_detail=quality_template_detail,
                document_knowledge_base=document_knowledge_base,
                document_target_knowledge_base=document_target_knowledge_base,
                search_knowledge_base=search_knowledge_base,
                pageindex_knowledge_base=pageindex_knowledge_base,
                pageindex_template=pageindex_template,
                quality_knowledge_base=quality_knowledge_base,
                review_knowledge_base=review_knowledge_base,
                quality_progress=quality_progress,
                quality_result=quality_result,
                quality_active_check=quality_active_check,
                formatted_quality_result_state=formatted_quality_result_state,
                quality_claims=quality_claims,
                quality_claim_page_state=quality_claim_page_state,
                quality_claim_page_info=quality_claim_page_info,
                selected_claim_state=selected_claim_state,
                claim_detail_state=claim_detail_state,
                claim_detail_view=claim_detail_view,
                claim_evidence_table=claim_evidence_table,
                quality_evidence_page_state=quality_evidence_page_state,
                quality_evidence_page_info=quality_evidence_page_info,
                quality_review_claim_detail=quality_review_claim_detail,
                evidence_items_state=evidence_items_state,
                claim_evidence_detail=claim_evidence_detail,
                recent_quality_state=recent_quality_state,
                recent_quality_checks=recent_quality_checks,
                recent_quality_page_state=recent_quality_page_state,
                recent_quality_page_info=recent_quality_page_info,
                quality_evaluation_cases=quality_evaluation_cases,
                review_pending_candidates=review_pending_candidates,
                review_pending_page_state=review_pending_page_state,
                review_pending_page_info=review_pending_page_info,
                review_processed_candidates=review_processed_candidates,
                review_processed_page_state=review_processed_page_state,
                review_processed_page_info=review_processed_page_info,
                review_candidate_state=review_candidate_state,
                review_selected_claim_state=review_selected_claim_state,
                review_claim_detail_state=review_claim_detail_state,
                review_claim_detail_panel=review_claim_detail_panel,
                review_evidence_table=review_evidence_table,
                review_evidence_page_state=review_evidence_page_state,
                review_evidence_page_info=review_evidence_page_info,
                review_evidence_items_state=review_evidence_items_state,
                review_evidence_detail=review_evidence_detail,
                review_action_input=review_action_input,
                review_note_input=review_note_input,
                review_history=review_history,
                review_history_page_state=review_history_page_state,
                review_history_page_info=review_history_page_info,
                review_history_state=review_history_state,
                review_selected_record_state=review_selected_record_state,
                review_record_detail=review_record_detail,
                refresh_settings_workspace_ui=refresh_settings_workspace_ui,
                select_settings_template=select_settings_template,
                prepare_new_template=prepare_new_template,
                save_settings_template_ui=save_settings_template_ui,
                delete_settings_template_ui=delete_settings_template_ui,
                change_settings_template_page=change_settings_template_page,
                export_settings_result=export_settings_result,
                refresh_settings_knowledge_base_workspace_ui=refresh_settings_knowledge_base_workspace_ui,
                select_settings_knowledge_base=select_settings_knowledge_base,
                prepare_new_knowledge_base=prepare_new_knowledge_base,
                save_settings_knowledge_base_ui=save_settings_knowledge_base_ui,
                delete_settings_knowledge_base_ui=delete_settings_knowledge_base_ui,
                change_settings_knowledge_base_page=change_settings_knowledge_base_page,
                refresh_settings_user_workspace_ui=refresh_settings_user_workspace_ui,
                select_settings_user_ui=select_settings_user_ui,
                delete_settings_user_ui=delete_settings_user_ui,
                save_settings_user_permissions_ui=save_settings_user_permissions_ui,
            )
            bind_review_events(
                components=review_components,
                review_candidate_state=review_candidate_state,
                review_history_state=review_history_state,
                review_selected_record_state=review_selected_record_state,
                review_selected_claim_state=review_selected_claim_state,
                review_claim_detail_state=review_claim_detail_state,
                review_evidence_items_state=review_evidence_items_state,
                review_pending_page_state=review_pending_page_state,
                review_processed_page_state=review_processed_page_state,
                review_evidence_page_state=review_evidence_page_state,
                review_history_page_state=review_history_page_state,
                login_state=login_state,
                document_knowledge_base=document_knowledge_base,
                search_knowledge_base=search_knowledge_base,
                quality_knowledge_base=quality_knowledge_base,
                list_review_workspace_ui=list_review_workspace_ui,
                change_review_knowledge_base_ui=change_review_knowledge_base_ui,
                export_review_results=export_review_result,
                change_review_filters_ui=change_review_filters_ui,
                select_review_candidate_ui=select_review_candidate_ui,
                select_review_history_record_ui=select_review_history_record_ui,
                select_quality_evidence=select_quality_evidence,
                submit_review_action_ui=submit_review_action_ui,
                change_review_candidate_page=change_review_candidate_page,
                change_review_evidence_page=change_review_evidence_page,
                change_review_history_page=change_review_history_page,
            )

            # 认证状态变化后必须刷新知识库管理整页，不能继续使用服务启动时的初始快照。
            document_workspace_outputs = [
                document_components["document_summary"],
                document_components["database_summary"],
                document_components["database_summary_table"],
                database_page_state,
                document_components["database_page_info"],
                document_components["document_table"],
                document_page_state,
                document_components["document_page_info"],
                document_components["document_choices"],
                document_components["document_detail"],
                document_components["register_button"],
                document_components["rebuild_button"],
                document_components["document_quality_report"],
                document_components["document_quality_checks"],
                document_components["document_quality_sections"],
                document_quality_sections_page_state,
                document_components["document_quality_sections_page_info"],
                document_components["document_quality_chunks"],
                document_quality_chunks_page_state,
                document_components["document_quality_chunks_page_info"],
                document_components["document_quality_search_summary"],
                document_components["document_quality_search_results"],
                document_quality_search_page_state,
                document_components["document_quality_search_page_info"],
                document_quality_search_state,
                document_components["document_quality_search_detail"],
                document_components["document_quality_batch_summary"],
                document_components["document_quality_batch_table"],
                document_quality_batch_page_state,
                document_components["document_quality_batch_page_info"],
                document_components["document_quality_config_panel"],
                document_components["document_quality_sample_limit"],
                document_components["document_quality_long_document_char_threshold"],
                document_components["document_quality_min_sections_for_long_doc"],
                document_components["document_quality_max_avg_chunks_per_section"],
                document_components["document_quality_max_chunk_chars"],
                document_components["document_quality_short_chunk_chars"],
                document_components["document_quality_short_chunk_warn_min_chunk_count"],
                document_components["document_quality_config_result"],
                document_components["document_quality_csv_export_result"],
            ]

            def _do_login(username, password):
                try:
                    user = auth_service.authenticate(username, password)
                    if not user:
                        return (
                            _empty_login_session(),
                            _empty_login_session(),
                            "",
                            format_operation_result_html({"success": False, "message": "用户名或密码错误"}, title="登录失败"),
                            gr.update(visible=True),
                            gr.update(visible=False),
                            *_build_permission_ui_updates(_empty_login_session()),
                            *_build_quality_permission_updates(_empty_login_session()),
                            *_build_document_permission_updates(_empty_login_session()),
                            *_build_review_permission_updates(_empty_login_session()),
                        )
                    session = _build_login_session(user.user_id)
                    return (
                        session,
                        session,
                        _render_auth_user(user.username),
                        format_operation_result_html({"success": True, "message": "登录成功"}, title="登录成功"),
                        gr.update(visible=False),
                        gr.update(visible=True),
                        *_build_permission_ui_updates(session, select_default_tab=True),
                        *_build_quality_permission_updates(session),
                        *_build_document_permission_updates(session),
                        *_build_review_permission_updates(session),
                    )
                except Exception as e:
                    return (
                        _empty_login_session(),
                        _empty_login_session(),
                        "",
                        format_operation_result_html({"success": False, "message": str(e)}, title="错误"),
                        gr.update(visible=True),
                        gr.update(visible=False),
                        *_build_permission_ui_updates(_empty_login_session()),
                        *_build_quality_permission_updates(_empty_login_session()),
                        *_build_document_permission_updates(_empty_login_session()),
                        *_build_review_permission_updates(_empty_login_session()),
                    )

            def _switch_to_main():
                return gr.update(visible=False), gr.update(visible=True)

            def _do_register(username, password, password_confirm):
                # M10 修复：添加异常处理，防止注册失败时泄露内部堆栈信息
                try:
                    if password != password_confirm:
                        return format_operation_result_html({"success": False, "message": "两次密码不一致"}, title="注册失败")
                    success, msg = auth_service.register_user(username, password)
                    return format_operation_result_html({"success": success, "message": msg}, title="注册成功" if success else "注册失败")
                except Exception as e:
                    return format_operation_result_html({"success": False, "message": f"注册失败: {e}"}, title="注册失败")

            def _do_logout():
                return _empty_login_session()

            def _restore_login_session(stored_session, restore_initialized: bool = False):
                """从浏览器持久化状态恢复登录态，刷新页面后仍保持登录。"""
                try:
                    if not isinstance(stored_session, dict):
                        empty_session = _empty_login_session()
                        return (
                            empty_session,
                            "",
                            gr.update(visible=True),
                            gr.update(visible=False),
                            *_build_permission_ui_updates(empty_session),
                            *_build_quality_permission_updates(empty_session),
                            *_build_document_permission_updates(empty_session),
                            *_build_review_permission_updates(empty_session),
                            False,
                        )
                    user_id = str(stored_session.get("user_id") or "").strip()
                    if not user_id:
                        empty_session = _empty_login_session()
                        return (
                            empty_session,
                            "",
                            gr.update(visible=True),
                            gr.update(visible=False),
                            *_build_permission_ui_updates(empty_session),
                            *_build_quality_permission_updates(empty_session),
                            *_build_document_permission_updates(empty_session),
                            *_build_review_permission_updates(empty_session),
                            False,
                        )
                    restored_session = _build_login_session(user_id)
                    if not restored_session.get("user_id"):
                        empty_session = _empty_login_session()
                        return (
                            empty_session,
                            "",
                            gr.update(visible=True),
                            gr.update(visible=False),
                            *_build_permission_ui_updates(empty_session),
                            *_build_quality_permission_updates(empty_session),
                            *_build_document_permission_updates(empty_session),
                            *_build_review_permission_updates(empty_session),
                            False,
                        )
                    return (
                        restored_session,
                        _render_auth_user(str(restored_session.get("username") or "")),
                        gr.update(visible=False),
                        gr.update(visible=True),
                        # 浏览器会话恢复只更新权限和数据，不改变用户当前主标签页。
                        *_build_permission_ui_updates(restored_session, select_default_tab=False),
                        *_build_quality_permission_updates(restored_session),
                        *_build_document_permission_updates(restored_session),
                        *_build_review_permission_updates(restored_session),
                        True,
                    )
                except Exception:
                    empty_session = _empty_login_session()
                    return (
                        empty_session,
                        "",
                        gr.update(visible=True),
                        gr.update(visible=False),
                        *_build_permission_ui_updates(empty_session),
                        *_build_quality_permission_updates(empty_session),
                        *_build_document_permission_updates(empty_session),
                        *_build_review_permission_updates(empty_session),
                        False,
                    )

            def _reset_auth_forms():
                return (
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(value=""),
                )

            def _reset_logged_out_workspace():
                """退出登录后，清空主界面权限与业务状态，避免残留上一个账号的数据。"""

                empty_session = _empty_login_session()
                return (
                    *_build_permission_ui_updates(empty_session),
                    *_build_quality_permission_updates(empty_session),
                    *_build_document_permission_updates(empty_session),
                    *_build_review_permission_updates(empty_session),
                )

            auth_register_btn.click(
                fn=lambda: (gr.update(visible=False), gr.update(visible=True)),
                outputs=[auth_login_form, auth_register_form],
                queue=False,
                show_progress="hidden",
            )
            auth_login_btn.click(
                fn=lambda: (gr.update(visible=True), gr.update(visible=False)),
                outputs=[auth_login_form, auth_register_form],
                queue=False,
                show_progress="hidden",
            )
            auth_login_submit.click(fn=_do_login, inputs=[auth_login_username, auth_login_password],
                                    outputs=[login_state, persisted_login_state, auth_user_display, auth_login_result, auth_page, main_content,
                                             pending_access_tab, quality_tab, review_tab, document_tab, search_tab, pageindex_tab, settings_tab,
                                             pending_access_view, main_tabs,
                                             document_knowledge_base, document_target_knowledge_base, quality_knowledge_base,
                                             review_knowledge_base, search_knowledge_base, pageindex_knowledge_base, settings_knowledge_base_state,
                                             settings_knowledge_base_table, settings_knowledge_base_page_state, settings_knowledge_base_page_info,
                                             quality_progress, quality_result, quality_active_check, formatted_quality_result_state,
                                             quality_claims, quality_claim_page_state, quality_claim_page_info, selected_claim_state,
                                             claim_detail_state, claim_detail_view, claim_evidence_table, quality_evidence_page_state,
                                             quality_evidence_page_info, quality_review_claim_detail, evidence_items_state,
                                             claim_evidence_detail, recent_quality_state, recent_quality_checks, recent_quality_page_state,
                                             recent_quality_page_info, quality_evaluation_cases,
                                             *document_workspace_outputs,
                                             review_pending_candidates, review_pending_page_state, review_pending_page_info,
                                             review_processed_candidates, review_processed_page_state, review_processed_page_info,
                                             review_candidate_state, review_selected_claim_state, review_claim_detail_state,
                                             review_claim_detail_panel, review_evidence_table, review_evidence_page_state,
                                             review_evidence_page_info, review_evidence_items_state, review_evidence_detail,
                                             review_action_input, review_note_input, review_history, review_history_page_state,
                                             review_history_page_info, review_history_state, review_selected_record_state,
                                             review_record_detail],
                                    queue=False,
                                    show_progress="hidden")
            auth_login_password.submit(fn=_do_login, inputs=[auth_login_username, auth_login_password],
                                       outputs=[login_state, persisted_login_state, auth_user_display, auth_login_result, auth_page, main_content,
                                                pending_access_tab, quality_tab, review_tab, document_tab, search_tab, pageindex_tab, settings_tab,
                                                pending_access_view, main_tabs,
                                                document_knowledge_base, document_target_knowledge_base, quality_knowledge_base,
                                                review_knowledge_base, search_knowledge_base, pageindex_knowledge_base, settings_knowledge_base_state,
                                                settings_knowledge_base_table, settings_knowledge_base_page_state, settings_knowledge_base_page_info,
                                                quality_progress, quality_result, quality_active_check, formatted_quality_result_state,
                                                quality_claims, quality_claim_page_state, quality_claim_page_info, selected_claim_state,
                                                claim_detail_state, claim_detail_view, claim_evidence_table, quality_evidence_page_state,
                                                quality_evidence_page_info, quality_review_claim_detail, evidence_items_state,
                                                claim_evidence_detail, recent_quality_state, recent_quality_checks, recent_quality_page_state,
                                                recent_quality_page_info, quality_evaluation_cases,
                                                *document_workspace_outputs,
                                                review_pending_candidates, review_pending_page_state, review_pending_page_info,
                                                review_processed_candidates, review_processed_page_state, review_processed_page_info,
                                                review_candidate_state, review_selected_claim_state, review_claim_detail_state,
                                                review_claim_detail_panel, review_evidence_table, review_evidence_page_state,
                                                review_evidence_page_info, review_evidence_items_state, review_evidence_detail,
                                                review_action_input, review_note_input, review_history, review_history_page_state,
                                                review_history_page_info, review_history_state, review_selected_record_state,
                                                review_record_detail],
                                       queue=False,
                                       show_progress="hidden")
            auth_register_submit.click(fn=_do_register,
                                       inputs=[auth_register_username, auth_register_password, auth_register_password_confirm],
                                       outputs=[auth_register_result],
                                       queue=False,
                                       show_progress="hidden")
            auth_logout_btn.click(
                fn=lambda: (_do_logout(), _do_logout(), ""),
                outputs=[login_state, persisted_login_state, auth_user_display],
                queue=False,
                show_progress="hidden",
            )
            auth_logout_btn.click(
                fn=_reset_auth_forms,
                outputs=[
                    auth_page,
                    main_content,
                    auth_login_form,
                    auth_register_form,
                    auth_login_username,
                    auth_login_password,
                    auth_login_result,
                    auth_register_username,
                    auth_register_password,
                    auth_register_password_confirm,
                    auth_register_result,
                ],
                queue=False,
                show_progress="hidden",
            )
            auth_logout_btn.click(
                fn=_reset_logged_out_workspace,
                outputs=[
                    pending_access_tab,
                    quality_tab,
                    review_tab,
                    document_tab,
                    search_tab,
                    pageindex_tab,
                    settings_tab,
                    pending_access_view,
                    main_tabs,
                    document_knowledge_base,
                    document_target_knowledge_base,
                    quality_knowledge_base,
                    review_knowledge_base,
                    search_knowledge_base,
                    pageindex_knowledge_base,
                    settings_knowledge_base_state,
                    settings_knowledge_base_table,
                    settings_knowledge_base_page_state,
                    settings_knowledge_base_page_info,
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
                    *document_workspace_outputs,
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
                show_progress="hidden",
            )
            persisted_login_state.change(
                fn=_restore_login_session,
                inputs=[persisted_login_state, login_restore_initialized],
                outputs=[login_state, auth_user_display, auth_page, main_content,
                         pending_access_tab, quality_tab, review_tab, document_tab, search_tab, pageindex_tab, settings_tab,
                         pending_access_view, main_tabs,
                         document_knowledge_base, document_target_knowledge_base, quality_knowledge_base,
                         review_knowledge_base, search_knowledge_base, pageindex_knowledge_base, settings_knowledge_base_state,
                         settings_knowledge_base_table, settings_knowledge_base_page_state, settings_knowledge_base_page_info,
                         quality_progress, quality_result, quality_active_check, formatted_quality_result_state,
                         quality_claims, quality_claim_page_state, quality_claim_page_info, selected_claim_state,
                         claim_detail_state, claim_detail_view, claim_evidence_table, quality_evidence_page_state,
                         quality_evidence_page_info, quality_review_claim_detail, evidence_items_state,
                         claim_evidence_detail, recent_quality_state, recent_quality_checks, recent_quality_page_state,
                         recent_quality_page_info, quality_evaluation_cases,
                         *document_workspace_outputs,
                         review_pending_candidates, review_pending_page_state, review_pending_page_info,
                         review_processed_candidates, review_processed_page_state, review_processed_page_info,
                         review_candidate_state, review_selected_claim_state, review_claim_detail_state,
                         review_claim_detail_panel, review_evidence_table, review_evidence_page_state,
                         review_evidence_page_info, review_evidence_items_state, review_evidence_detail,
                         review_action_input, review_note_input, review_history, review_history_page_state,
                         review_history_page_info, review_history_state, review_selected_record_state,
                         review_record_detail, login_restore_initialized],
                queue=False,
                show_progress="hidden",
            )

    return demo
