"""程序说明：为 Gradio 页面准备可直接展示的视图数据。"""

from __future__ import annotations

from html import escape
from pathlib import Path


def scan_input_documents(input_root: Path) -> list[dict]:
    """扫描知识库输入目录，返回可注册的文档列表。"""

    if not input_root.exists():
        return []

    resolved_root = input_root.resolve()
    items: list[dict] = []
    for file_path in sorted(resolved_root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".md", ".json"}:
            continue
        items.append(
            {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "file_type": file_path.suffix.lower().lstrip("."),
                "size_bytes": file_path.stat().st_size,
                "size_display": format_file_size(file_path.stat().st_size),
            }
        )
    return items


def format_file_size(size_bytes: int) -> str:
    """将文件字节数格式化为更易读的大小文本。"""

    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def build_document_choices(documents: list[dict]) -> list[str]:
    """构建下拉框可用的文档选项。"""

    return [build_document_choice(item) for item in documents]


def build_doc_uid_choices(documents: list[dict]) -> list[str]:
    """构建可用于重建索引的文档选项。"""

    return [f'{item["doc_uid"]} | {item.get("doc_title", "")}' for item in documents if item.get("doc_uid")]


def build_template_choices(templates: list[dict]) -> list[str]:
    """构建质检模板下拉选项。"""

    return [f'{item["template_id"]} | {item.get("template_name", "")}' for item in templates if item.get("template_id")]


def normalize_search_query(query: str) -> str:
    """将多组关键词输入规范化为单个查询字符串。"""

    raw = str(query or "").replace("\r", " ").replace("\n", " ")
    for separator in ("，", ",", "；", ";", "、", "|", "\t"):
        raw = raw.replace(separator, " ")
    return " ".join(part for part in raw.split(" ") if part.strip())


def format_search_results(items: list[dict], *, query_text: str = "") -> dict:
    """将检索结果转换为更适合 UI 展示的结构。"""

    normalized_query = normalize_search_query(query_text)
    query_terms = _extract_search_terms(normalized_query)
    rows = [
        {
            "chunk_id": item.get("chunk_id"),
            "doc_uid": item.get("doc_uid"),
            "doc_title": item.get("doc_title", ""),
            "author": item.get("author", ""),
            "source_name": item.get("source_name", ""),
            "tags": item.get("tags", []),
            "source_span": item.get("source_span"),
            "retrieval_source": item.get("retrieval_source", ""),
            "matched_sources": item.get("matched_sources", []),
            "score": item.get("score"),
            "rerank_score": item.get("rerank_score"),
            "section_title": item.get("section_title", ""),
            "content": str(item.get("content", "")),
            "content_preview": str(item.get("content", ""))[:200],
            "content_preview_highlighted": _highlight_query_terms(str(item.get("content", ""))[:200], query_terms),
        }
        for item in items
    ]
    return {
        "count": len(rows),
        "query_text": normalized_query,
        "query_terms": query_terms,
        "items": items,
        "table": rows,
    }


def format_search_help_html() -> str:
    """构建检索功能说明面板。"""

    return _build_panel_html(
        title="功能说明",
        description="当前为混合检索：会综合全文召回、向量召回和重排结果，适合日常知识查询。",
        cards=[
            ("支持输入", "支持关键词、短语、整句输入"),
            ("匹配方式", "混合召回，偏模糊"),
            ("多组关键词", "支持，建议空格或逗号分隔"),
            ("正则表达式", "不支持正则表达式"),
        ],
        notes=[
            "检索内容可以输入一个关键词，也可以输入一句完整问题。",
            "如果输入多组关键词，系统会把它们合并成一次查询并综合排序。",
            "更适合找相关内容，不保证逐字严格匹配。",
        ],
        tone="neutral",
        min_height_px=260,
    )


def format_search_result_detail_html(item: dict | None, *, query_text: str = "") -> str:
    """构建检索结果原文详情面板。"""

    resolved = item or {}
    if not resolved:
        return _build_panel_html(
            title="原文详情",
            description="点击下方检索结果后，这里会显示对应原文内容和定位信息。",
            cards=[("当前状态", "未选择结果")],
            notes=["可查看文档名称、片段 ID、定位、检索来源、命中来源和原文内容"],
            tone="neutral",
        )

    query_terms = _extract_search_terms(query_text)
    content_html = _highlight_query_terms(_display_text(resolved.get("content") or resolved.get("expanded_content")), query_terms)
    metadata_html = _build_panel_html(
        title="原文详情",
        description="当前已定位到所选检索结果的原文片段。",
        cards=[
            ("文档名称", _display_text(resolved.get("doc_title") or resolved.get("source_name"))),
            ("片段 ID", _display_text(resolved.get("chunk_id"))),
            ("片段序号", _display_text(resolved.get("chunk_index"))),
            ("定位", _display_text(resolved.get("source_span"))),
            ("检索来源", _display_text(resolved.get("retrieval_source"))),
            ("匹配来源", _display_text(resolved.get("matched_sources"))),
            ("相关度", _format_score(resolved.get("score"))),
            ("重排分", _format_score(resolved.get("rerank_score"))),
        ],
        notes=[
            f'章节：{_display_text(resolved.get("section_title"))}',
            f'作者：{_display_text(resolved.get("author"))}',
        ],
        tone="neutral",
    )
    return (
        f"{metadata_html}"
        f"""
        <div style="border:1px solid var(--border-color-primary);background:var(--body-background-fill);border-radius:16px;padding:16px 18px;margin:0 0 12px 0;">
            <div style="font-size:16px;font-weight:700;color:var(--body-text-color);margin:0 0 8px 0;">原文内容</div>
            <div style="font-size:14px;line-height:1.8;color:var(--body-text-color);white-space:pre-wrap;word-break:break-word;">{content_html}</div>
        </div>
        """
    )


def format_document_summary_markdown(summary: dict | None) -> str:
    """将文档概览转换为普通用户可读的摘要。"""

    resolved = summary or {}
    total_files = int(resolved.get("total_files") or 0)
    registered_files = int(resolved.get("registered_files") or 0)
    pending_register_files = int(resolved.get("pending_register_files") or 0)
    needs_rebuild_files = int(resolved.get("needs_rebuild_files") or 0)
    if total_files == 0:
        status_text = "当前目录下暂无可用文档"
    elif pending_register_files == 0 and needs_rebuild_files == 0:
        status_text = "全部文档已注册，且无需重建"
    elif pending_register_files > 0 and needs_rebuild_files == 0:
        status_text = f"当前有 {pending_register_files} 个文档待注册"
    elif pending_register_files == 0:
        status_text = f"当前有 {needs_rebuild_files} 个文档需要重建"
    else:
        status_text = f"当前有 {pending_register_files} 个待注册文档，{needs_rebuild_files} 个待重建文档"
    return "\n".join(
        [
            "### 文档概览",
            f"- 文档总数：{total_files}",
            f"- 已注册：{registered_files}",
            f"- 待注册：{pending_register_files}",
            f"- 需重建：{needs_rebuild_files}",
            f"- 当前状态：{status_text}",
        ]
    )


def format_document_summary_html(summary: dict | None) -> str:
    """将文档概览转换为卡片式 HTML。"""

    resolved = summary or {}
    total_files = int(resolved.get("total_files") or 0)
    registered_files = int(resolved.get("registered_files") or 0)
    pending_register_files = int(resolved.get("pending_register_files") or 0)
    needs_rebuild_files = int(resolved.get("needs_rebuild_files") or 0)
    if total_files == 0:
        status_text = "当前目录下暂无可用文档"
        tone = "neutral"
    elif pending_register_files == 0 and needs_rebuild_files == 0:
        status_text = "全部文档已注册，且无需重建"
        tone = "success"
    elif pending_register_files > 0 and needs_rebuild_files == 0:
        status_text = f"当前有 {pending_register_files} 个文档待注册"
        tone = "warning"
    elif pending_register_files == 0:
        status_text = f"当前有 {needs_rebuild_files} 个文档需要重建"
        tone = "warning"
    else:
        status_text = f"当前有 {pending_register_files} 个待注册文档，{needs_rebuild_files} 个待重建文档"
        tone = "warning"
    return _build_panel_html(
        title="文档概览",
        description=status_text,
        cards=[
            ("文档总数", str(total_files)),
            ("已注册", str(registered_files)),
            ("待注册", str(pending_register_files)),
            ("需重建", str(needs_rebuild_files)),
        ],
        notes=["用于反映 Input 目录与当前入库状态的总体差异"],
        tone=tone,
        min_height_px=260,
    )


def format_document_detail_markdown(detail: dict | None) -> str:
    """将文档详情转换为普通用户可读的摘要。"""

    resolved = detail or {}
    if "source_path" not in resolved:
        return "### 文档详情\n- 请选择文档"
    return "\n".join(
        [
            "### 文档详情",
            f'- 文件名：{_display_text(resolved.get("file_name"))}',
            f'- 文档名称：{_display_text(resolved.get("doc_title"))}',
            f'- 文件大小：{_display_text(resolved.get("size_display"))}',
            f'- 是否已注册：{_display_text(resolved.get("registered_label"))}',
            f'- 索引状态：{_display_text(resolved.get("index_status"))}',
            f'- 是否需重建：{_display_text(resolved.get("needs_rebuild_label"))}',
            f'- 当前状态：{_display_text(resolved.get("action_hint"))}',
            f'- 文件路径：{_display_text(resolved.get("source_path"))}',
        ]
    )


def format_document_detail_html(detail: dict | None) -> str:
    """将文档详情转换为卡片式 HTML。"""

    resolved = detail or {}
    if "source_path" not in resolved:
        return _build_panel_html(
            title="文档详情",
            description="请选择文档后查看详情",
            cards=[("当前状态", "未选择文档")],
            tone="neutral",
        )
    tone = "success" if resolved.get("action_hint") == "已就绪" else "warning"
    return _build_panel_html(
        title="文档详情",
        description=f'当前状态：{_display_text(resolved.get("action_hint"))}',
        cards=[
            ("文件名", _display_text(resolved.get("file_name"))),
            ("文档名称", _display_text(resolved.get("doc_title"))),
            ("文件大小", _display_text(resolved.get("size_display"))),
            ("是否已注册", _display_text(resolved.get("registered_label"))),
            ("索引状态", _display_text(resolved.get("index_status"))),
            ("是否需重建", _display_text(resolved.get("needs_rebuild_label"))),
        ],
        notes=[f'文件路径：{_display_text(resolved.get("source_path"))}'],
        tone=tone,
    )


def format_database_summary_markdown(summary: dict | None) -> str:
    """将数据库统计转换为文档管理页的自然语言摘要。"""

    resolved = summary or {}
    document_count = int(resolved.get("document_count") or 0)
    completed_document_count = int(resolved.get("completed_document_count") or 0)
    indexed_document_count = int(resolved.get("indexed_document_count") or 0)
    rebuild_pending_document_count = int(resolved.get("rebuild_pending_document_count") or 0)
    failed_document_count = int(resolved.get("failed_document_count") or 0)
    chunk_count = int(resolved.get("chunk_count") or 0)
    section_count = int(resolved.get("section_count") or 0)
    quality_check_count = int(resolved.get("quality_check_count") or 0)
    claim_count = int(resolved.get("claim_count") or 0)
    review_count = int(resolved.get("review_count") or 0)

    if document_count == 0:
        status_text = "当前数据库中还没有已入库文档"
    elif failed_document_count > 0:
        status_text = f"当前有 {failed_document_count} 篇文档存在索引异常，建议优先处理"
    elif rebuild_pending_document_count > 0:
        status_text = f"当前有 {rebuild_pending_document_count} 篇文档仍在等待索引或重建"
    else:
        status_text = "当前数据库中的文档和索引状态正常"

    return "\n".join(
        [
            "### 数据库状态",
            f"- 当前数据库已入库 {document_count} 篇文档，其中 {completed_document_count} 篇已完成入库流程，{indexed_document_count} 篇已建立索引",
            f"- 累计解析出 {section_count} 个章节，生成 {chunk_count} 条分块",
            f"- 质检累计产生 {quality_check_count} 次检查、{claim_count} 条 Claim、{review_count} 条审核记录",
            f"- 当前状态：{status_text}",
        ]
    )


def format_database_summary_html(summary: dict | None) -> str:
    """将数据库统计转换为卡片式 HTML。"""

    resolved = summary or {}
    document_count = int(resolved.get("document_count") or 0)
    completed_document_count = int(resolved.get("completed_document_count") or 0)
    indexed_document_count = int(resolved.get("indexed_document_count") or 0)
    rebuild_pending_document_count = int(resolved.get("rebuild_pending_document_count") or 0)
    failed_document_count = int(resolved.get("failed_document_count") or 0)
    chunk_count = int(resolved.get("chunk_count") or 0)
    section_count = int(resolved.get("section_count") or 0)
    quality_check_count = int(resolved.get("quality_check_count") or 0)
    claim_count = int(resolved.get("claim_count") or 0)
    review_count = int(resolved.get("review_count") or 0)

    if document_count == 0:
        status_text = "当前数据库中还没有已入库文档"
        tone = "neutral"
    elif failed_document_count > 0:
        status_text = f"当前有 {failed_document_count} 篇文档存在索引异常，建议优先处理"
        tone = "danger"
    elif rebuild_pending_document_count > 0:
        status_text = f"当前有 {rebuild_pending_document_count} 篇文档仍在等待索引或重建"
        tone = "warning"
    else:
        status_text = "当前数据库中的文档和索引状态正常"
        tone = "success"

    return _build_panel_html(
        title="数据库状态",
        description=status_text,
        cards=[
            ("已入库文档", str(document_count)),
            ("已完成入库", str(completed_document_count)),
            ("已建立索引", str(indexed_document_count)),
            ("分块总数", str(chunk_count)),
            ("章节总数", str(section_count)),
            ("Claim 总数", str(claim_count)),
        ],
        notes=[
            f"待重建/待索引：{rebuild_pending_document_count}",
            f"异常文档：{failed_document_count}",
            f"质检次数：{quality_check_count}，审核记录：{review_count}",
        ],
        tone=tone,
        min_height_px=260,
    )


def build_database_summary_rows(summary: dict | None) -> list[list[str]]:
    """将数据库统计转换为简洁表格。"""

    resolved = summary or {}
    return [
        ["已入库文档", _format_number(resolved.get("document_count"))],
        ["已完成入库", _format_number(resolved.get("completed_document_count"))],
        ["已建立索引", _format_number(resolved.get("indexed_document_count"))],
        ["待重建/待索引", _format_number(resolved.get("rebuild_pending_document_count"))],
        ["异常文档", _format_number(resolved.get("failed_document_count"))],
        ["章节总数", _format_number(resolved.get("section_count"))],
        ["分块总数", _format_number(resolved.get("chunk_count"))],
        ["质检次数", _format_number(resolved.get("quality_check_count"))],
        ["Claim 总数", _format_number(resolved.get("claim_count"))],
        ["审核记录", _format_number(resolved.get("review_count"))],
    ]


def format_operation_result_markdown(payload: dict | None, *, title: str) -> str:
    """将注册、重建、审核等操作结果转换为可读摘要。"""

    resolved = payload or {}
    success = bool(resolved.get("success"))
    progress_summary = resolved.get("progress_summary") or {}
    jobs = resolved.get("jobs") or []
    accepted = resolved.get("accepted") or []
    lines = [
        f"### {title}",
        f'- 执行状态：{"成功" if success else "失败"}',
    ]
    if resolved.get("message"):
        lines.append(f'- 结果说明：{_display_text(resolved.get("message"))}')
    if resolved.get("error_code"):
        lines.append(f'- 错误代码：{_display_text(resolved.get("error_code"))}')
    if resolved.get("linked_claim_id"):
        lines.append(f'- 关联 Claim：{_display_text(resolved.get("linked_claim_id"))}')
    if resolved.get("linked_check_id"):
        lines.append(f'- 关联质检：{_display_text(resolved.get("linked_check_id"))}')
    if jobs:
        lines.append(f"- 处理文档数：{len(jobs)}")
    if accepted:
        lines.append(f"- 已接受任务数：{len(accepted)}")
    if progress_summary:
        lines.append(f'- 进度步骤：{_display_text(progress_summary.get("step_count"))}')
        lines.append(f'- 最后阶段：{_display_text(progress_summary.get("last_stage"))}')
        lines.append(f'- 最后进度：{_format_number(progress_summary.get("last_percent"))}%')
    if len(lines) == 2 and success:
        lines.append("- 结果说明：操作已完成")
    return "\n".join(lines)


def format_operation_result_html(payload: dict | None, *, title: str) -> str:
    """将操作结果转换为卡片式 HTML。"""

    if payload is None:
        return _build_panel_html(
            title=title,
            description="暂无执行记录",
            cards=[("执行状态", "未开始")],
            notes=["执行相关操作后，这里会显示结果与进度摘要"],
            tone="neutral",
        )

    resolved = payload or {}
    success = bool(resolved.get("success"))
    progress_summary = resolved.get("progress_summary") or {}
    jobs = resolved.get("jobs") or []
    accepted = resolved.get("accepted") or []
    description = _display_text(resolved.get("message")) if resolved.get("message") else ("操作已完成" if success else "操作未成功")
    notes: list[str] = []
    if resolved.get("error_code"):
        notes.append(f'错误代码：{_display_text(resolved.get("error_code"))}')
    if resolved.get("linked_claim_id"):
        notes.append(f'关联 Claim：{_display_text(resolved.get("linked_claim_id"))}')
    if resolved.get("linked_check_id"):
        notes.append(f'关联质检：{_display_text(resolved.get("linked_check_id"))}')

    cards = [("执行状态", "成功" if success else "失败")]
    if jobs:
        cards.append(("处理文档数", str(len(jobs))))
    if accepted:
        cards.append(("接受任务数", str(len(accepted))))
    if progress_summary:
        cards.extend(
            [
                ("进度步骤", _display_text(progress_summary.get("step_count"))),
                ("最后阶段", _display_text(progress_summary.get("last_stage"))),
                ("最后进度", f'{_format_number(progress_summary.get("last_percent"))}%'),
            ]
        )
    return _build_panel_html(
        title=title,
        description=description,
        cards=cards,
        notes=notes,
        tone="success" if success else "danger",
    )


def _wrap_search_row_cell(content: str, *, is_selected: bool, is_first: bool = False) -> str:
    """为选中行单元格添加统一高亮样式。"""

    if not is_selected:
        return content
    classes = ["search-result-cell", "search-result-cell-selected"]
    if is_first:
        classes.append("search-result-cell-selected-first")
    return (
        f'<div class="{" ".join(classes)}">'
        f"{content}"
        "</div>"
    )


def build_search_result_rows(formatted: dict | None, *, selected_row_index: int | None = None) -> list[list[str]]:
    """将检索结果转换为表格行。"""

    rows = (formatted or {}).get("table") or []
    return [
        [
            _wrap_search_row_cell(str(index + 1), is_selected=index == selected_row_index, is_first=True),
            _wrap_search_row_cell(_display_text(item.get("doc_title") or item.get("source_name")), is_selected=index == selected_row_index),
            _wrap_search_row_cell(_display_text(item.get("source_span")), is_selected=index == selected_row_index),
            _wrap_search_row_cell(_display_text(item.get("chunk_id")), is_selected=index == selected_row_index),
            _wrap_search_row_cell(_display_text(item.get("retrieval_source")), is_selected=index == selected_row_index),
            _wrap_search_row_cell(_format_score(item.get("score")), is_selected=index == selected_row_index),
            _wrap_search_row_cell(_format_score(item.get("rerank_score")), is_selected=index == selected_row_index),
            _wrap_search_row_cell(_display_text(item.get("matched_sources")), is_selected=index == selected_row_index),
            _wrap_search_row_cell(
                _display_text(item.get("content_preview_highlighted") or item.get("content_preview")),
                is_selected=index == selected_row_index,
            ),
        ]
        for index, item in enumerate(rows)
    ]


def format_search_summary_markdown(formatted: dict | None) -> str:
    """将检索结果统计转换为摘要。"""

    count = int((formatted or {}).get("count") or 0)
    status_text = "未找到相关内容" if count == 0 else f"已找到 {count} 条相关内容"
    return "\n".join(
        [
            "### 检索结果",
            f"- 命中条数：{count}",
            f"- 当前状态：{status_text}",
        ]
    )


def format_search_summary_html(formatted: dict | None) -> str:
    """将检索结果摘要转换为卡片式 HTML。"""

    resolved = formatted or {}
    count = int(resolved.get("count") or 0)
    tone = "success" if count > 0 else "neutral"
    query_text = _display_text(resolved.get("query_text"))
    query_terms = resolved.get("query_terms") or []
    query_style = "关键词 / 多组词" if len(query_terms) > 1 else "短语 / 整句"
    return _build_panel_html(
        title="检索结果",
        description="已找到相关内容" if count > 0 else "未找到相关内容",
        cards=[
            ("命中条数", str(count)),
            ("查询类型", query_style if query_text != "-" else "未输入"),
            ("当前查询", query_text),
        ],
        notes=[
            "当前为混合检索，不是严格逐字匹配。",
            "结果明细已在下方表格中展示，点击某一行可查看原文详情。",
        ],
        tone=tone,
    )


def build_document_management_state(input_documents: list[dict], status_items: list[dict]) -> dict:
    """构建文档管理页所需的扫描、状态与重建选项数据。"""
    status_by_path = {
        _normalize_source_path(item.get("source_path")): item
        for item in status_items
        if item.get("source_path")
    }
    rows: list[dict] = []
    seen_paths: set[str] = set()

    for document in input_documents:
        source_path = _normalize_source_path(document["file_path"])
        seen_paths.add(source_path)
        status_item = status_by_path.get(source_path)
        rows.append(_build_document_row(document, status_item))

    for status_item in status_items:
        source_path = _normalize_source_path(status_item.get("source_path") or "")
        if not source_path or source_path in seen_paths:
            continue
        rows.append(_build_document_row(None, status_item))

    rows.sort(key=lambda item: (item["registered_sort"], item["file_name"].lower()))
    table_rows = [
        [
            item["file_name"],
            item["doc_title"],
            item["size_display"],
            item["ingested_at"],
            item["registered_label"],
            item["index_status"],
            item["needs_rebuild_label"],
            item["action_hint"],
            item["error_message"],
        ]
        for item in rows
    ]
    detail_map = {item["source_path"]: item for item in rows if item.get("source_path")}
    choices = [build_document_choice(item) for item in rows if item.get("source_path")]
    default_choice = choices[0] if choices else None
    return {
        "scan_summary": {
            "total_files": len(input_documents),
            "registered_files": sum(1 for item in rows if item["is_registered"]),
            "pending_register_files": sum(1 for item in rows if not item["is_registered"] and item["source_exists"]),
            "needs_rebuild_files": sum(1 for item in rows if item["needs_rebuild"]),
        },
        "table_headers": ["文件名", "文档名称", "大小", "入库时间", "已注册", "索引状态", "需重建", "推荐动作", "错误信息"],
        "table_rows": table_rows,
        "document_choices": choices,
        "default_choice": default_choice,
        "document_detail_map": detail_map,
        "selected_detail": get_document_detail(default_choice, detail_map),
        "status_items": status_items,
        "rebuild_choices": build_doc_uid_choices(status_items),
    }


def parse_document_choice(choice: str) -> str:
    """从下拉选项中解析出文件路径。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=2)[-1]


def build_document_choice(document: dict) -> str:
    """构建文档管理页的文档选择项。"""

    return (
        f'{document.get("file_name", "")} | {document.get("action_hint", "")} | '
        f'{document.get("source_path") or document.get("file_path", "")}'
    )


def get_document_detail(choice: str, document_detail_map: dict | None) -> dict:
    """根据文档选择项读取详情。"""

    source_path = parse_document_choice(choice)
    if not source_path or not document_detail_map:
        return {"message": "请选择文档"}
    return document_detail_map.get(source_path, {"message": "未找到对应文档"})


def build_document_action_updates(detail: dict | None) -> tuple[dict, dict]:
    """根据当前文档详情决定按钮是否可操作。"""

    resolved = detail or {}
    if "source_path" not in resolved:
        return {"interactive": False}, {"interactive": False}
    return (
        {"interactive": bool(resolved.get("can_register"))},
        {"interactive": bool(resolved.get("can_rebuild"))},
    )


def _build_document_row(input_document: dict | None, status_item: dict | None) -> dict:
    """合并 Input 扫描结果和数据库状态，构造成文档管理行。"""
    source_path = _normalize_source_path(
        (input_document or {}).get("file_path")
        or (status_item or {}).get("source_path")
        or ""
    )
    file_name = (input_document or {}).get("file_name") or Path(source_path).name
    size_bytes = int((input_document or {}).get("size_bytes") or 0)
    size_display = (input_document or {}).get("size_display") or ("-" if not size_bytes else format_file_size(size_bytes))
    is_registered = bool(status_item)
    source_exists = bool(input_document)
    index_status = (status_item or {}).get("index_status") or "not_registered"
    error_message = str((status_item or {}).get("error_message") or "")
    needs_rebuild = bool(status_item) and index_status != "indexed"
    action_hint = "可注册"
    if is_registered and needs_rebuild:
        action_hint = "建议重建"
    elif is_registered and not needs_rebuild:
        action_hint = "已就绪"
    elif not source_exists:
        action_hint = "源文件缺失"
    doc_title = (
        (status_item or {}).get("doc_title")
        or Path(file_name).stem
    )
    return {
        "source_path": source_path,
        "file_name": file_name,
        "doc_title": doc_title,
        "doc_uid": (status_item or {}).get("doc_uid", ""),
        "file_type": (input_document or {}).get("file_type") or Path(file_name).suffix.lstrip("."),
        "size_bytes": size_bytes,
        "size_display": size_display,
        "is_registered": is_registered,
        "registered_label": "是" if is_registered else "否",
        "registered_sort": 0 if is_registered else 1,
        "source_exists": source_exists,
        "ingested_at": str((status_item or {}).get("created_at") or "-"),
        "ingest_status": str((status_item or {}).get("ingest_status") or "not_registered"),
        "index_status": index_status,
        "needs_rebuild": needs_rebuild,
        "needs_rebuild_label": "是" if needs_rebuild else "否",
        "action_hint": action_hint,
        "error_message": error_message[:120],
        "can_register": source_exists and not is_registered,
        "can_rebuild": source_exists and is_registered,
    }


def _normalize_source_path(source_path: str | Path | None) -> str:
    """统一路径格式，避免相对路径和绝对路径重复显示为两条记录。"""

    if not source_path:
        return ""
    return str(Path(source_path).resolve())


def format_ingest_result(payload: dict, progress_events: list[dict]) -> dict:
    """整理文档管理操作结果与进度快照。"""

    return {
        **payload,
        "progress_summary": {
            "steps": progress_events,
            "step_count": len(progress_events),
            "last_stage": progress_events[-1]["stage"] if progress_events else None,
            "last_percent": progress_events[-1]["percent"] if progress_events else 0,
        },
    }


def format_quality_result(result: dict) -> dict:
    """将质检结果转换为更适合前端展示的结构。"""

    claims = result.get("claims", [])
    rule_hits = result.get("rule_hits", [])

    claim_choices = [build_claim_choice(item) for item in claims]
    claims_table = [
        {
            "claim_id": item["claim_id"],
            "claim_text": item["claim_text"],
            "verdict": item["verdict"],
            "risk_level": item.get("risk_level", ""),
            "confidence": item["confidence"],
            "source_doc": item.get("source_doc"),
            "source_span": item.get("source_span"),
            "evidence_details": item.get("evidence_details", []),
        }
        for item in claims
    ]

    return {
        "summary": result.get("check", {}).get("summary", ""),
        "check": result.get("check", {}),
        "claims": claims,
        "claims_table": claims_table,
        "rule_hits": rule_hits,
        "claim_choices": claim_choices,
        "claim_detail_map": build_claim_detail_map(claims),
    }


def format_quality_result_markdown(formatted: dict | None) -> str:
    """将质检结果转换为摘要。"""

    resolved = formatted or {}
    check = resolved.get("check") or {}
    claims = resolved.get("claims") or []
    return "\n".join(
        [
            "### 质检结果",
            f'- 总体结论：{_display_text(check.get("overall_verdict") or resolved.get("summary"))}',
            f'- 模板名称：{_display_text(check.get("template_name"))}',
            f"- Claim 数量：{len(claims)}",
            f'- 摘要说明：{_display_text(resolved.get("summary"))}',
        ]
    )


def format_quality_result_html(formatted: dict | None) -> str:
    """将质检结果转换为卡片式 HTML。"""

    resolved = formatted or {}
    check = resolved.get("check") or {}
    claims = resolved.get("claims") or []
    overall_verdict = _display_text(check.get("overall_verdict") or resolved.get("summary"))
    tone = "warning" if "review" in overall_verdict.lower() else "success"
    return _build_panel_html(
        title="质检结果",
        description=_display_text(resolved.get("summary")),
        cards=[
            ("总体结论", overall_verdict),
            ("模板名称", _display_text(check.get("template_name"))),
            ("Claim 数量", str(len(claims))),
            ("质检 ID", _display_text(check.get("check_id"))),
        ],
        notes=["下方展示 Claim 列表、最近质检记录与证据详情"],
        tone=tone,
    )


def build_quality_claim_rows(formatted: dict | None) -> list[list[str]]:
    """将质检结果中的 Claim 转换为表格行。"""

    rows = (formatted or {}).get("claims_table") or []
    return [
        [
            _display_text(item.get("claim_id")),
            _display_text(item.get("claim_text")),
            _display_text(item.get("verdict")),
            _display_text(item.get("risk_level")),
            _format_score(item.get("confidence")),
            _display_text(item.get("source_doc")),
            _display_text(item.get("source_span")),
        ]
        for item in rows
    ]


def parse_claim_choice(choice: str) -> str:
    """从审核下拉项中解析 claim_id。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=1)[0]


def build_claim_detail_map(claims: list[dict]) -> dict:
    """构建 claim_id 到 claim 详情的映射。"""

    return {
        item["claim_id"]: {
            "claim_id": item["claim_id"],
            "claim_text": item.get("claim_text", ""),
            "verdict": item.get("verdict", ""),
            "risk_level": item.get("risk_level", ""),
            "confidence": item.get("confidence"),
            "review_status": item.get("review_status", "pending"),
            "source_doc": item.get("source_doc"),
            "source_span": item.get("source_span"),
            "check_id": item.get("check_id"),
            "template_name": item.get("template_name"),
            "check_created_at": item.get("check_created_at"),
            "evidence": item.get("evidence", ""),
            "evidence_reason": item.get("evidence_reason", ""),
            "evidence_details": item.get("evidence_details", []),
        }
        for item in claims
        if item.get("claim_id")
    }


def get_claim_detail(claim_choice: str, claim_detail_map: dict | None) -> dict:
    """根据下拉选项读取 claim 详情。"""

    claim_id = parse_claim_choice(claim_choice)
    if not claim_id or not claim_detail_map:
        return {"message": "请选择 Claim"}
    return claim_detail_map.get(claim_id, {"message": "未找到对应 Claim 详情"})


def format_claim_detail_for_review(claim_choice: str, claim_detail_map: dict | None) -> dict:
    """将 claim 详情转换为更适合审核页展示的结构。"""

    detail = get_claim_detail(claim_choice, claim_detail_map)
    if "claim_id" not in detail:
        return detail

    evidence_details = detail.get("evidence_details", [])
    evidence_table = [
        {
            "chunk_id": item.get("chunk_id"),
            "doc_uid": item.get("doc_uid"),
            "doc_title": item.get("doc_title", ""),
            "source_span": item.get("source_span"),
            "retrieval_source": item.get("retrieval_source", ""),
            "matched_sources": item.get("matched_sources", []),
            "rerank_score": item.get("rerank_score"),
            "context_mode": item.get("context_mode", ""),
            "section_title": item.get("section_title", ""),
            "content_preview": item.get("content_preview", ""),
        }
        for item in evidence_details
    ]
    return {
        "summary": {
            "claim_id": detail.get("claim_id"),
            "claim_text": detail.get("claim_text", ""),
            "verdict": detail.get("verdict", ""),
            "risk_level": detail.get("risk_level", ""),
            "confidence": detail.get("confidence"),
            "review_status": detail.get("review_status", "pending"),
            "source_doc": detail.get("source_doc"),
            "source_span": detail.get("source_span"),
            "check_id": detail.get("check_id"),
            "template_name": detail.get("template_name"),
            "check_created_at": detail.get("check_created_at"),
            "evidence": detail.get("evidence", ""),
            "evidence_reason": detail.get("evidence_reason", ""),
        },
        "evidence_table": evidence_table,
        "evidence_count": len(evidence_table),
    }


def format_claim_detail_markdown(detail: dict | None) -> str:
    """将 Claim 详情转换为审核页可读摘要。"""

    resolved = detail or {}
    summary = resolved.get("summary") or {}
    if "claim_id" not in summary:
        return "### Claim 详情\n- 请选择 Claim"
    return "\n".join(
        [
            "### Claim 详情",
            f'- Claim ID：{_display_text(summary.get("claim_id"))}',
            f'- Claim 内容：{_display_text(summary.get("claim_text"))}',
            f'- 当前判定：{_display_text(summary.get("verdict"))}',
            f'- 风险等级：{_display_text(summary.get("risk_level"))}',
            f'- 置信度：{_format_score(summary.get("confidence"))}',
            f'- 审核状态：{_display_text(summary.get("review_status"))}',
            f'- 来源文档：{_display_text(summary.get("source_doc"))}',
            f'- 来源位置：{_display_text(summary.get("source_span"))}',
            f'- 证据摘要：{_display_text(summary.get("evidence"))}',
            f'- 证据说明：{_display_text(summary.get("evidence_reason"))}',
            f'- 证据条数：{_display_text(resolved.get("evidence_count"))}',
        ]
    )


def format_claim_detail_html(detail: dict | None) -> str:
    """将 Claim 详情转换为卡片式 HTML。"""

    resolved = detail or {}
    summary = resolved.get("summary") or {}
    if "claim_id" not in summary:
        return _build_panel_html(
            title="Claim 详情",
            description="请选择 Claim 后查看详情",
            cards=[("当前状态", "未选择 Claim")],
            tone="neutral",
        )
    verdict = _display_text(summary.get("verdict"))
    review_status = _display_text(summary.get("review_status"))
    tone = "warning" if "review" in verdict.lower() or review_status == "pending" else "success"
    return _build_panel_html(
        title="Claim 详情",
        description=_display_text(summary.get("claim_text")),
        cards=[
            ("Claim ID", _display_text(summary.get("claim_id"))),
            ("当前判定", verdict),
            ("风险等级", _display_text(summary.get("risk_level"))),
            ("置信度", _format_score(summary.get("confidence"))),
            ("审核状态", review_status),
            ("证据条数", _display_text(resolved.get("evidence_count"))),
        ],
        notes=[
            f'来源文档：{_display_text(summary.get("source_doc"))}',
            f'来源位置：{_display_text(summary.get("source_span"))}',
            f'证据摘要：{_display_text(summary.get("evidence"))}',
            f'证据说明：{_display_text(summary.get("evidence_reason"))}',
        ],
        tone=tone,
    )


def build_claim_evidence_rows(detail: dict | None) -> list[list[str]]:
    """将 Claim 证据转换为表格行。"""

    evidence_rows = (detail or {}).get("evidence_table") or []
    return [
        [
            _display_text(item.get("chunk_id")),
            _display_text(item.get("doc_title") or item.get("doc_uid")),
            _display_text(item.get("source_span")),
            _display_text(item.get("retrieval_source")),
            _display_text(item.get("matched_sources")),
            _format_score(item.get("rerank_score")),
            _display_text(item.get("content_preview")),
        ]
        for item in evidence_rows
    ]


def parse_doc_uid_choice(choice: str) -> str:
    """从下拉项中解析 doc_uid。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=1)[0]


def parse_template_choice(choice: str) -> str:
    """从模板下拉项中解析 template_id。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=1)[0]


def format_recent_quality_checks(quality_results: list[dict]) -> list[dict]:
    """将最近质检记录转换为 UI 可展示结构。"""

    formatted: list[dict] = []
    for item in quality_results:
        claims = item.get("claims", [])
        formatted.append(
            {
                "check_id": item.get("check_id"),
                "overall_verdict": item.get("overall_verdict"),
                "template_name": item.get("template_name"),
                "input_text": item.get("input_text"),
                "created_at": item.get("created_at"),
                "claim_choices": [
                    build_claim_choice(
                        {
                            **claim,
                            "check_id": item.get("check_id"),
                            "template_name": item.get("template_name"),
                            "check_created_at": item.get("created_at"),
                        }
                    )
                    for claim in claims
                ],
                "claim_detail_map": build_claim_detail_map(
                    [
                        {
                            **claim,
                            "check_id": item.get("check_id"),
                            "template_name": item.get("template_name"),
                            "check_created_at": item.get("created_at"),
                        }
                        for claim in claims
                    ]
                ),
                "claims": claims,
            }
        )
    return formatted


def build_recent_quality_rows(quality_results: list[dict] | None) -> list[list[str]]:
    """将最近质检记录转换为表格行。"""

    rows = quality_results or []
    return [
        [
            _display_text(item.get("check_id")),
            _display_text(item.get("template_name")),
            _display_text(item.get("overall_verdict")),
            str(len(item.get("claims") or [])),
            _display_text(item.get("created_at")),
            _truncate_text(item.get("input_text")),
        ]
        for item in rows
    ]


def build_claim_choice(claim: dict) -> str:
    """构建 claim 下拉选项。"""

    return (
        f'{claim["claim_id"]} | {claim.get("verdict", "")} | '
        f'{claim.get("review_status", "pending")} | {claim.get("claim_text", "")[:30]}'
    )


def build_recent_claim_navigation(quality_results: list[dict], preferred_claim_id: str | None = None) -> dict:
    """根据最近质检结果构建统一的 Claim 导航状态。"""

    merged_claims: list[dict] = []
    for item in quality_results:
        for claim in item.get("claims", []):
            merged_claims.append(
                {
                    **claim,
                    "check_id": item.get("check_id"),
                    "template_name": item.get("template_name"),
                    "check_created_at": item.get("created_at"),
                }
            )

    claim_choices = [build_claim_choice(item) for item in merged_claims]
    claim_detail_map = build_claim_detail_map(merged_claims)
    selected_claim_id = preferred_claim_id if preferred_claim_id in claim_detail_map else ""
    if not selected_claim_id and merged_claims:
        selected_claim_id = merged_claims[0]["claim_id"]
    selected_choice = next(
        (choice for choice in claim_choices if choice.startswith(f"{selected_claim_id} |")),
        None,
    )
    selected_detail = format_claim_detail_for_review(selected_choice, claim_detail_map)
    return {
        "claim_choices": claim_choices,
        "selected_choice": selected_choice,
        "claim_detail_map": claim_detail_map,
        "selected_detail": selected_detail,
    }


def format_review_history(review_items: list[dict]) -> dict:
    """将审核记录转换为更适合 UI 展示的结构。"""

    rows = [
        {
            "review_id": item.get("review_id"),
            "claim_id": item.get("claim_id"),
            "check_id": item.get("check_id"),
            "template_name": item.get("template_name", ""),
            "claim_text": item.get("claim_text", ""),
            "review_action": item.get("review_action"),
            "review_status": item.get("review_status"),
            "review_note": item.get("review_note"),
            "reviewer": item.get("reviewer"),
            "created_at": item.get("created_at"),
        }
        for item in review_items
    ]
    review_choices = [
        f'{item["review_id"]} | {item.get("review_action", "")} | {item.get("claim_text", "")[:30]}'
        for item in rows
        if item.get("review_id")
    ]
    review_map = {item["review_id"]: item for item in rows if item.get("review_id")}
    return {
        "count": len(rows),
        "items": rows,
        "review_choices": review_choices,
        "review_map": review_map,
    }


def build_review_history_rows(formatted: dict | None) -> list[list[str]]:
    """将审核记录转换为表格行。"""

    items = (formatted or {}).get("items") or []
    return [
        [
            _display_text(item.get("review_id")),
            _display_text(item.get("claim_id")),
            _display_text(item.get("review_action")),
            _display_text(item.get("review_status")),
            _display_text(item.get("reviewer")),
            _display_text(item.get("created_at")),
            _display_text(item.get("review_note")),
            _truncate_text(item.get("claim_text")),
        ]
        for item in items
    ]


def parse_review_choice(choice: str) -> str:
    """从审核记录下拉项中解析 review_id。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=1)[0]


def get_review_target_claim_id(review_choice: str, review_map: dict | None) -> str:
    """从审核记录中提取要定位的 claim_id。"""

    review_id = parse_review_choice(review_choice)
    if not review_id or not review_map:
        return ""
    return str(review_map.get(review_id, {}).get("claim_id", ""))


def _display_text(value: object) -> str:
    """统一处理空值与列表，避免直接把原始结构抛给用户。"""

    if value is None:
        return "-"
    if isinstance(value, list):
        if not value:
            return "-"
        return "、".join(_display_text(item) for item in value)
    text = str(value).strip()
    return text or "-"


def _format_score(value: object) -> str:
    """统一格式化分数类字段。"""

    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return _display_text(value)


def _format_number(value: object) -> str:
    """统一格式化数值，避免 None 直接显示。"""

    if value in (None, ""):
        return "0"
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return _display_text(value)


def _truncate_text(value: object, limit: int = 60) -> str:
    """截断过长文本，避免表格内容过宽。"""

    text = _display_text(value)
    if text == "-" or len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _extract_search_terms(query_text: str) -> list[str]:
    """提取用于高亮的检索词。"""

    seen: set[str] = set()
    terms: list[str] = []
    for part in normalize_search_query(query_text).split():
        term = part.strip()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return sorted(terms, key=len, reverse=True)


def _highlight_query_terms(text: str, query_terms: list[str]) -> str:
    """在文本中高亮命中的检索词。"""

    if not text:
        return "-"
    highlighted = escape(text)
    for term in query_terms:
        escaped_term = escape(term)
        highlighted = highlighted.replace(escaped_term, f"<mark>{escaped_term}</mark>")
    return highlighted


def _build_panel_html(
    *,
    title: str,
    description: str,
    cards: list[tuple[str, str]],
    notes: list[str] | None = None,
    tone: str = "neutral",
    min_height_px: int = 0,
) -> str:
    """生成统一风格的卡片面板 HTML。"""

    palette = _get_panel_palette(tone)
    min_height_style = f"min-height:{min_height_px}px;" if min_height_px > 0 else ""
    card_html = "".join(
        f"""
        <div style="background:{palette['card_bg']};border:1px solid {palette['card_border']};border-radius:12px;padding:12px 14px;min-height:76px;">
            <div style="font-size:12px;color:{palette['muted']};margin-bottom:6px;">{escape(label)}</div>
            <div style="font-size:16px;font-weight:700;color:{palette['value']};line-height:1.4;word-break:break-word;">{escape(value)}</div>
        </div>
        """
        for label, value in cards
    )
    notes_html = ""
    if notes:
        notes_html = "".join(
            f'<li style="margin:0 0 6px 0;">{escape(note)}</li>'
            for note in notes
            if note
        )
        if notes_html:
            notes_html = f"""
            <ul style="margin:14px 0 0 18px;padding:0;color:{palette['text']};font-size:13px;line-height:1.6;">
                {notes_html}
            </ul>
            """
    return f"""
    <div style="border:1px solid {palette['border']};background:{palette['panel_bg']};border-radius:16px;padding:16px 18px;margin:0 0 12px 0;box-shadow:none;{min_height_style}">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;">
            <div>
                <div style="font-size:16px;font-weight:700;color:{palette['title']};margin:0 0 6px 0;">{escape(title)}</div>
                <div style="font-size:13px;line-height:1.7;color:{palette['text']};">{escape(description)}</div>
            </div>
            <div style="padding:4px 10px;border-radius:999px;background:{palette['badge_bg']};color:{palette['badge_text']};font-size:12px;font-weight:600;">
                状态模块
            </div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-top:14px;">
            {card_html}
        </div>
        {notes_html}
    </div>
    """


def _get_panel_palette(tone: str) -> dict[str, str]:
    """根据语义色返回卡片面板配色。"""

    return {
        "panel_bg": "var(--block-background-fill)",
        "border": "var(--border-color-primary)",
        "card_bg": "var(--body-background-fill)",
        "card_border": "var(--border-color-primary)",
        "title": "var(--body-text-color)",
        "text": "var(--body-text-color)",
        "muted": "var(--body-text-color-subdued)",
        "value": "var(--body-text-color)",
        "badge_bg": "var(--body-background-fill)",
        "badge_text": "var(--body-text-color-subdued)",
    }
