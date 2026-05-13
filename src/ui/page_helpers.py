"""程序说明：集中放置 UI 页面拆分过程中可复用的权限、分页与通用组件 helper。"""

from __future__ import annotations

import re

import gradio as gr

from src.ui.viewmodels import build_knowledge_base_choices, parse_knowledge_base_choice


TABLE_PAGE_SIZE = 10


def filter_visible_knowledge_base_items(
    knowledge_base_items: list[dict],
    allowed_kb_ids: set[str] | None,
    *,
    is_admin: bool,
) -> list[dict]:
    """按权限过滤知识库列表；管理员保持全量可见。"""

    if is_admin or allowed_kb_ids is None:
        return list(knowledge_base_items)
    normalized_kb_ids = {str(item_id or "").strip() for item_id in allowed_kb_ids if str(item_id or "").strip()}
    return [
        item
        for item in knowledge_base_items
        if str(item.get("knowledge_base_id") or "").strip() in normalized_kb_ids
    ]


def build_visible_knowledge_base_bundle(
    knowledge_base_items: list[dict],
    allowed_kb_ids: set[str] | None,
    *,
    is_admin: bool,
    selected_knowledge_base_id: str | None = None,
) -> tuple[list[dict], list[str], str | None]:
    """根据权限构建可见知识库列表、下拉选项与当前选中项。"""

    visible_items = filter_visible_knowledge_base_items(
        knowledge_base_items,
        allowed_kb_ids,
        is_admin=is_admin,
    )
    visible_choices = build_knowledge_base_choices(visible_items)
    default_choice = next(
        (
            choice
            for choice in visible_choices
            if any(
                item.get("is_default")
                and parse_knowledge_base_choice(choice) == item.get("knowledge_base_id")
                for item in visible_items
            )
        ),
        visible_choices[0] if visible_choices else None,
    )
    normalized_selected_id = str(selected_knowledge_base_id or "").strip()
    available_ids = {str(item.get("knowledge_base_id") or "").strip() for item in visible_items}
    if normalized_selected_id not in available_ids:
        normalized_selected_id = parse_knowledge_base_choice(default_choice or "")
    selected_choice = next(
        (choice for choice in visible_choices if parse_knowledge_base_choice(choice) == normalized_selected_id),
        default_choice,
    )
    return visible_items, visible_choices, selected_choice


def extract_login_session_permissions(
    session: dict[str, object] | None,
    *,
    normalize_tab_name,
) -> tuple[bool, set[str] | None, set[str] | None]:
    """从登录态中提取管理员标记、页签权限和知识库权限。"""

    if session is None:
        # 兼容直接调用内部回调函数的历史路径：未显式传入登录态时，保持全量可见。
        return True, None, None
    if not isinstance(session, dict):
        return False, set(), set()
    is_admin = bool(session.get("is_admin", False))
    permissions = session.get("permissions") if isinstance(session.get("permissions"), dict) else {}
    if is_admin:
        return True, None, None
    tab_names = {
        normalize_tab_name(str(tab_name or ""))
        for tab_name in (permissions.get("tab_names") or [])
        if str(tab_name or "").strip()
    }
    kb_ids = {
        str(knowledge_base_id or "").strip()
        for knowledge_base_id in (permissions.get("kb_ids") or [])
        if str(knowledge_base_id or "").strip()
    }
    return False, tab_names, kb_ids


def ui_button(
    value: str | None = None,
    *,
    tone: str | None = None,
    elem_classes: str | list[str] | tuple[str, ...] | None = None,
    **kwargs: object,
) -> gr.Button:
    """构建统一按钮，按语义映射样式，避免页面各自追加按钮补丁。"""

    classes = ["ui-button"]
    variant = str(kwargs.get("variant") or "").strip().lower()
    resolved_tone = tone
    if resolved_tone is None:
        normalized_value = (value or "").strip()
        if variant == "primary" or normalized_value.startswith(("保存", "开始模拟")):
            resolved_tone = "primary"
        elif variant == "stop" or normalized_value.startswith("删除"):
            resolved_tone = "danger"
        elif normalized_value in {"上一页", "下一页"}:
            resolved_tone = "pagination"
        else:
            resolved_tone = "secondary"
    classes.append(f"ui-button--{resolved_tone}")
    resolved_min_width = 164
    if resolved_tone == "pagination":
        resolved_min_width = 136
    elif resolved_tone in {"primary", "danger"}:
        resolved_min_width = 148
    elif (value or "").startswith("下载"):
        resolved_min_width = 188
    kwargs.setdefault("scale", 0)
    kwargs.setdefault("min_width", resolved_min_width)
    if isinstance(elem_classes, str):
        classes.append(elem_classes)
    elif elem_classes:
        classes.extend(elem_classes)
    return gr.Button(value, elem_classes=classes, **kwargs)


def build_markdown_table(headers: list[object], rows: list[list[object]]) -> str:
    """将表头和行数据转换为 Markdown 表格。"""

    normalized_headers = [str(item if item not in (None, "") else "-").replace("|", "\\|") for item in headers]
    header_row = "| " + " | ".join(normalized_headers) + " |"
    separator_row = "| " + " | ".join("---" for _ in normalized_headers) + " |"
    body_rows = [
        "| "
        + " | ".join(
            str(cell if cell not in (None, "") else "-").replace("\r", " ").replace("\n", "<br>").replace("|", "\\|")
            for cell in row
        )
        + " |"
        for row in rows
    ]
    return "\n".join([header_row, separator_row, *body_rows])


def normalize_table_rows(rows: object) -> list[list[object]]:
    """将 DataFrame 或任意二维列表规范化为列表行。"""

    if hasattr(rows, "values"):
        return rows.values.tolist()
    normalized_rows = rows or []
    return list(normalized_rows)


def paginate_table_rows(
    rows: object,
    page: int | float | None,
    *,
    prepend_sequence: bool,
) -> tuple[list[list[object]], int, int, str]:
    """按固定页大小裁剪表格行，并按需补自然序号。"""

    normalized_rows = normalize_table_rows(rows)
    total_rows = len(normalized_rows)
    total_pages = max(1, (total_rows + TABLE_PAGE_SIZE - 1) // TABLE_PAGE_SIZE)
    try:
        resolved_page = int(page or 1)
    except (TypeError, ValueError):
        resolved_page = 1
    resolved_page = max(1, min(resolved_page, total_pages))
    start_index = (resolved_page - 1) * TABLE_PAGE_SIZE
    end_index = start_index + TABLE_PAGE_SIZE
    page_rows = normalized_rows[start_index:end_index]
    if prepend_sequence:
        page_rows = [[str(start_index + offset + 1), *list(row)] for offset, row in enumerate(page_rows)]
    page_info = f"第 {resolved_page} / {total_pages} 页，共 {total_rows} 条，每页最多 {TABLE_PAGE_SIZE} 行"
    return page_rows, resolved_page, total_pages, page_info


def change_table_page(
    rows: object,
    current_page: int | float | None,
    *,
    action: str,
    prepend_sequence: bool,
) -> tuple[list[list[object]], int, str]:
    """根据上一页/下一页动作切换表格分页。"""

    normalized_rows = normalize_table_rows(rows)
    _current_rows, resolved_page, total_pages, _page_info = paginate_table_rows(
        normalized_rows,
        current_page,
        prepend_sequence=prepend_sequence,
    )
    target_page = resolved_page - 1 if action == "prev" else resolved_page + 1
    if action not in {"prev", "next"}:
        target_page = resolved_page
    target_page = max(1, min(target_page, total_pages))
    page_rows, final_page, _final_total_pages, page_info = paginate_table_rows(
        normalized_rows,
        target_page,
        prepend_sequence=prepend_sequence,
    )
    return page_rows, final_page, page_info


def reset_table_pagination(
    rows: object,
    *,
    prepend_sequence: bool,
) -> tuple[list[list[object]], int, str]:
    """将表格重置到第一页。"""

    page_rows, page, _total_pages, page_info = paginate_table_rows(
        rows,
        1,
        prepend_sequence=prepend_sequence,
    )
    return page_rows, page, page_info


def get_row_from_paged_table(
    rows: object,
    evt: gr.SelectData,
    *,
    id_column_index: int,
) -> list[object]:
    """从当前页表格中取出被点击的整行。"""

    normalized_rows = normalize_table_rows(rows)
    if not normalized_rows:
        return []
    index = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
    try:
        row_index = int(index)
    except (TypeError, ValueError):
        row_index = 0
    if row_index < 0 or row_index >= len(normalized_rows):
        row_index = 0
    selected_row = normalized_rows[row_index] if normalized_rows else []
    if not selected_row:
        return []
    if id_column_index >= len(selected_row):
        return []
    return list(selected_row)


def get_selected_search_item_from_page_rows(
    page_rows: object,
    raw_rows: list[dict] | None,
    evt: gr.SelectData,
) -> dict | None:
    """根据当前页表格的序号列，定位被点击的原始检索结果。"""

    normalized_page_rows = normalize_table_rows(page_rows)
    normalized_raw_rows = raw_rows or []
    if not normalized_page_rows or not normalized_raw_rows:
        return None
    selected_row = get_row_from_paged_table(normalized_page_rows, evt, id_column_index=0)
    if not selected_row:
        return None
    sequence_text = re.sub(r"<[^>]+>", "", str(selected_row[0] if selected_row else "")).strip()
    matched = re.search(r"\d+", sequence_text)
    if not matched:
        return None
    raw_index = int(matched.group()) - 1
    if raw_index < 0 or raw_index >= len(normalized_raw_rows):
        return None
    return normalized_raw_rows[raw_index]


def format_table_pagination_html(page_info: str) -> str:
    """格式化表格分页提示。"""

    return f"<div style='padding: 6px 2px 0 2px; color: #6b7280; font-size: 12px;'>{page_info}</div>"


def resolve_table_row_count(rows: list[list[object]] | None, *, default_rows: int = TABLE_PAGE_SIZE) -> int:
    """根据当前页实际数据量返回更稳定的表格可见行数。"""

    row_count = len(rows or [])
    if row_count <= 0:
        return 1
    return min(default_rows, row_count)


def rebuild_readonly_dataframe(
    *,
    headers: list[str],
    rows: list[list[object]] | None,
    label: str,
    elem_id: str,
    row_count: int,
    component_key: str,
    max_height: int = 420,
) -> dict:
    """返回只读表格更新参数，避免在 select 事件里重建 Dataframe。"""

    _ = (headers, label, elem_id, component_key)
    resolved_rows = rows or []
    return gr.update(
        value=resolved_rows,
        row_count=max(1, int(row_count)),
        max_height=max_height,
    )
