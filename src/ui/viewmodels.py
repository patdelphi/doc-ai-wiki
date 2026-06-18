"""程序说明：为 Gradio 页面准备可直接展示的视图数据。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

CN_TIMEZONE = timezone(timedelta(hours=8))


def scan_input_documents(input_root: Path, knowledge_base_id: str | None = None) -> list[dict]:
    """扫描知识库输入目录，返回可注册的文档列表。"""

    if not input_root.exists():
        return []

    resolved_root = input_root.resolve()
    normalized_knowledge_base_id = str(knowledge_base_id or "").strip()
    items: list[dict] = []
    seen_paths: set[str] = set()

    def append_file(file_path: Path, *, storage_label: str) -> None:
        if not file_path.is_file():
            return
        if file_path.suffix.lower() not in {".md", ".json"}:
            return
        resolved_path = str(file_path.resolve())
        if resolved_path in seen_paths:
            return
        seen_paths.add(resolved_path)
        items.append(
            {
                "knowledge_base_id": normalized_knowledge_base_id or "default",
                "file_name": file_path.name,
                "file_path": resolved_path,
                "file_type": file_path.suffix.lower().lstrip("."),
                "size_bytes": file_path.stat().st_size,
                "size_display": format_file_size(file_path.stat().st_size),
                "storage_label": storage_label,
            }
        )

    if not normalized_knowledge_base_id:
        for directory in sorted(path for path in resolved_root.iterdir() if path.is_dir()):
            for file_path in sorted(directory.rglob("*")):
                append_file(file_path, storage_label=f"{directory.name} 目录")
        return items

    scan_root = resolved_root / normalized_knowledge_base_id
    if scan_root.exists():
        for file_path in sorted(scan_root.rglob("*")):
            append_file(file_path, storage_label=f'{normalized_knowledge_base_id} 目录')
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


def build_knowledge_base_choices(knowledge_bases: list[dict]) -> list[str]:
    """构建知识库下拉选项。"""

    return [build_knowledge_base_choice(item) for item in knowledge_bases if item.get("knowledge_base_id")]


def build_knowledge_base_choice(knowledge_base: dict) -> str:
    """构建单个知识库选项。"""

    return (
        f'{knowledge_base.get("knowledge_base_id", "")} | '
        f'{knowledge_base.get("knowledge_base_name", "")}'
    )


def parse_knowledge_base_choice(choice: str) -> str:
    """从知识库选项中解析知识库标识。"""

    if not choice:
        return ""
    return choice.split(" | ", maxsplit=1)[0].strip()


def build_settings_template_rows(templates: list[dict]) -> list[list[str]]:
    """将模板列表转换为设置页表格行。"""

    return [
        [
            _display_text(item.get("template_id")),
            _display_text(item.get("template_name")),
            _display_text(item.get("source_label") or item.get("source_type")),
            _display_text(item.get("rule_tags")),
            _display_text(item.get("retrieval_policy", {}).get("final_top_k") if isinstance(item.get("retrieval_policy", {}), dict) else None),
            "是" if item.get("deletable", True) else "否",
        ]
        for item in templates
    ]


def build_settings_knowledge_base_rows(knowledge_bases: list[dict]) -> list[list[str]]:
    """将知识库列表转换为设置页表格行。"""

    return [
        [
            _display_text(item.get("knowledge_base_id")),
            _display_text(item.get("knowledge_base_name")),
            _display_text(item.get("description")),
            "是" if item.get("is_default") else "否",
            _display_text(item.get("status")),
        ]
        for item in knowledge_bases
    ]


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
        description="知识库检索用于在当前知识库中查找相关内容，结果来自全文召回、向量召回和重排的综合排序。",
        cards=[
            ("支持输入", "支持关键词、短语、整句和多组关键词"),
            ("匹配方式", "混合召回，偏模糊，不是严格逐字匹配"),
            ("多组关键词", "支持，建议空格或逗号分隔"),
            ("正则表达式", "不支持正则表达式"),
        ],
        notes=[
            "可以输入一个关键词，也可以输入一句完整问题。",
            "如果输入多组关键词，系统会把它们合并成一次查询并综合排序。",
            "点击结果列表后，右侧会展示原文详情、定位和关键词高亮内容。",
        ],
        tone="neutral",
        min_height_px=260,
    )


def format_document_management_help_html() -> str:
    """构建文档管理功能说明面板。"""

    return _build_panel_html(
        title="功能说明",
        description="知识库管理用于查看输入文档、执行入库与重建，并检查数据库和索引状态。",
        cards=[
            ("先看哪里", "先看文档概览、数据库状态和现有文档列表"),
            ("常用操作", "刷新列表、注册当前文档、注册全部待处理、重建索引"),
            ("入库质检", "可检查章节、分块、索引和文档内检索效果"),
            ("适合场景", "日常入库、异常排查、批量质检和结果导出"),
        ],
        notes=[
            "建议先刷新文档列表，再选择目标文档执行注册或重建。",
            "入库质检区域位于文档管理页底部，默认折叠隐藏，需要时展开即可继续执行单文档检查、批量质检和阈值配置。",
            "如果页面提示建议重建，通常说明索引未完成、部分失败或源内容已变化。",
        ],
        tone="neutral",
        min_height_px=260,
    )


def format_quality_help_html() -> str:
    """构建 AI 质检功能说明面板。"""

    return _build_panel_html(
        title="功能说明",
        description="AI 质检会把输入内容拆成多条 Claim，结合规则、知识库证据和模型判定给出初步结论。",
        cards=[
            ("适合输入", "待核验陈述、成段描述、需要复核的业务内容"),
            ("处理流程", "拆分 Claim -> 匹配规则 -> 检索证据 -> 模型或启发式判定"),
            ("结果重点", "总体结论、风险等级、Claim 列表、证据链和历史记录"),
            ("效果评测", "支持批量样例评测，验证结论、风险和 Claim 数是否符合预期"),
        ],
        notes=[
            "建议一行或一句表达一个明确结论，便于系统逐条拆分和定位问题。",
            "医学、古文、绝对化表述建议优先选择更严格的模板。",
            "如果当前未配置模型，系统会回退到规则与启发式判定，因此结果应更保守地看待。",
        ],
        tone="neutral",
        min_height_px=260,
    )


def format_quality_evaluation_help_html() -> str:
    """构建 AI 质检效果评测说明面板。"""

    return _build_panel_html(
        title="效果评测说明",
        description="效果评测用于验证 AI 质检结果是否符合你的预期，不是再次做知识检索，而是用样例集批量比较“预期结果”和“实际质检结果”。建议先看核心命中，再看宽松命中，最后再看完全命中。",
        cards=[
            ("它在做什么", "逐条执行质检，再把实际结论与预期结论做比对"),
            ("适合怎么用", "回归测试、模板调优、误判复现、版本前后效果对比"),
            ("核心命中", "只看结论是否一致，适合先判断整体方向是否跑偏"),
            ("宽松命中", "结论、风险、Claim 数三项里命中至少两项，适合日常验收"),
            ("完全命中", "三项都一致才算通过，是最严格指标"),
            ("为什么会出现 0 条完全命中", "常见原因是 Claim 拆分数量或风险等级与预期略有偏差，不一定代表整体不可用"),
        ],
        notes=[
            "样例 JSON：每条至少提供 input_text；也可补预期结论、预期风险和预期 Claim 数。",
            "看哪里：先看评测摘要里的核心命中、宽松命中和主要失败原因，再看评测明细里具体是哪一项没有命中。",
            "样例 ID：当前评测样例的唯一标识，便于定位问题；如果来自当前 Claim，通常会直接使用 Claim ID。",
            "预期结论 / 预期风险 / 预期 Claim 数：你认为这条输入理应得到的质检结果，用来做对照基准。",
            "实际结论 / 实际风险 / 实际 Claim 数：系统本次真实跑出的结果，用于和预期逐项比较。",
            "结论命中：实际结论是否和预期结论一致。",
            "风险命中：实际风险等级是否和预期风险一致。",
            "Claim 数命中：系统拆出的 Claim 数量是否和预期一致。",
            "宽松命中：同一条样例中，结论、风险、Claim 数三项里至少两项一致。",
            "完全命中：同一条样例的结论、风险、Claim 数三项都一致时记为完全命中。",
            "差异说明：告诉你当前样例具体差在哪一项。",
            "建议排查方向：帮助判断更像是模板判定问题、风险分级问题，还是 Claim 拆分问题。",
            "输入摘要：该样例原始输入的简短预览，便于快速定位是哪条文本。",
        ],
        tone="neutral",
        min_height_px=380,
        badge_text="评测解释",
    )


def format_review_help_html() -> str:
    """构建人工审核功能说明面板。"""

    return _build_panel_html(
        title="功能说明",
        description="人工审核用于处理 AI 质检产生的待审核 Claim，并沉淀最终人工结论。",
        cards=[
            ("先做什么", "先在待处理记录或已处理 Claim 中选择一条记录"),
            ("看什么", "查看 Claim 详情、证据列表、证据详情和历史审核记录"),
            ("怎么提交", "填写审核动作和备注后提交，页面会自动刷新"),
            ("历史用途", "已审核记录用于回看、定位和复现之前的人工处理结果"),
        ],
        notes=[
            "可审核列表优先显示待处理记录，并支持按范围和风险等级筛选。",
            "审核动作、审核状态和页面展示结果都统一使用中文。",
            "如果某条 Claim 已处理但需要再次确认，可从已处理 Claim 或审核历史中重新定位。",
        ],
        tone="neutral",
        min_height_px=260,
    )


def format_settings_help_html() -> str:
    """构建功能设置说明面板。"""

    return _build_panel_html(
        title="功能说明",
        description="功能设置用于维护质检模板，并查看当前系统实际生效的关键运行配置。",
        cards=[
            ("模板管理", "支持新增、编辑、删除模板"),
            ("可改内容", "模板名称、规则标签、检索策略、系统提示词、用户提示模板"),
            ("配置查看", "展示输入目录、模板目录、模型与检索关键配置"),
            ("生效方式", "模板保存后可立即在 AI 质检页选择"),
        ],
        notes=[
            "建议先从现有模板复制或修改，避免直接大幅改动默认策略。",
            "删除模板前请确认该模板是否仍被日常流程使用。",
            "运行配置当前以只读展示为主，用于确认系统实际生效参数。",
        ],
        tone="neutral",
        min_height_px=260,
    )


def format_settings_runtime_html(runtime_config: dict | None) -> str:
    """构建运行配置概览面板。"""

    resolved = runtime_config or {}
    return _build_panel_html(
        title="运行配置",
        description="当前为只读展示，用于确认实际生效的核心配置。",
        cards=[
            ("输入目录", _display_text(resolved.get("input_root"))),
            ("模板目录", _display_text(resolved.get("templates_dir"))),
            ("LLM Provider", _display_text(resolved.get("llm_provider"))),
            ("Embedding", _display_text(resolved.get("embedding_provider"))),
        ],
        notes=[
            f'重排：{_display_text(resolved.get("rerank_provider"))} / 启用={_display_text(resolved.get("rerank_enabled"))}',
            f'最大输入长度：{_display_text(resolved.get("max_input_chars"))}',
            f'审核候选抓取上限：{_display_text(resolved.get("review_candidate_limit"))}',
        ],
        tone="neutral",
        min_height_px=260,
    )


def format_settings_runtime_markdown(runtime_config: dict | None) -> str:
    """将运行配置概览转换为 Markdown。"""

    resolved = runtime_config or {}
    return "\n".join(
        [
            "### 运行配置",
            f'- 输入目录：{_display_text(resolved.get("input_root"))}',
            f'- 模板目录：{_display_text(resolved.get("templates_dir"))}',
            f'- LLM Provider：{_display_text(resolved.get("llm_provider"))}',
            f'- Embedding：{_display_text(resolved.get("embedding_provider"))}',
            f'- 重排：{_display_text(resolved.get("rerank_provider"))} / 启用={_display_text(resolved.get("rerank_enabled"))}',
            f'- 最大输入长度：{_display_text(resolved.get("max_input_chars"))}',
            f'- 审核候选抓取上限：{_display_text(resolved.get("review_candidate_limit"))}',
        ]
    )


def format_settings_knowledge_base_detail_html(knowledge_base: dict | None) -> str:
    """构建设置页知识库详情面板。"""

    resolved = knowledge_base or {}
    if not resolved.get("knowledge_base_id"):
        return _build_panel_html(
            title="知识库详情",
            description="请选择知识库或新建知识库。",
            cards=[("当前状态", "未选择知识库")],
            notes=["知识库会决定 Input 二级目录、文档归属、检索范围和 AI 质检范围。"],
            tone="neutral",
        )

    return _build_panel_html(
        title="知识库详情",
        description=_display_text(resolved.get("description")),
        cards=[
            ("知识库 ID", _display_text(resolved.get("knowledge_base_id"))),
            ("知识库名称", _display_text(resolved.get("knowledge_base_name"))),
            ("默认知识库", "是" if resolved.get("is_default") else "否"),
            ("状态", _display_text(resolved.get("status"))),
        ],
        notes=[
            "Input 目录会按该知识库 ID 建立二级目录。",
            "删除知识库前，必须先确保没有归属文档。",
        ],
        tone="neutral",
    )


def format_settings_knowledge_base_detail_markdown(knowledge_base: dict | None) -> str:
    """将知识库详情转换为 Markdown。"""

    resolved = knowledge_base or {}
    if not resolved.get("knowledge_base_id"):
        return "### 知识库详情\n- 当前状态：未选择知识库"
    return "\n".join(
        [
            "### 知识库详情",
            f'- 知识库 ID：{_display_text(resolved.get("knowledge_base_id"))}',
            f'- 知识库名称：{_display_text(resolved.get("knowledge_base_name"))}',
            f'- 默认知识库：{"是" if resolved.get("is_default") else "否"}',
            f'- 状态：{_display_text(resolved.get("status"))}',
            f'- 说明：{_display_text(resolved.get("description"))}',
        ]
    )


def format_settings_template_detail_html(template: dict | None) -> str:
    """构建设置页模板详情面板。"""

    resolved = template or {}
    if not resolved.get("template_id"):
        return _build_panel_html(
            title="模板详情",
            description="请选择模板或点击新建模板。",
            cards=[("当前状态", "未选择模板")],
            notes=["选择模板后，这里会显示来源、规则标签和检索策略摘要。"],
            tone="neutral",
        )

    retrieval_policy = resolved.get("retrieval_policy", {}) if isinstance(resolved.get("retrieval_policy", {}), dict) else {}
    return _build_panel_html(
        title="模板详情",
        description=_display_text(resolved.get("description")),
        cards=[
            ("模板 ID", _display_text(resolved.get("template_id"))),
            ("模板名称", _display_text(resolved.get("template_name"))),
            ("模板来源", _display_text(resolved.get("source_label") or resolved.get("source_type"))),
            ("规则标签", _display_text(resolved.get("rule_tags"))),
        ],
        notes=[
            f'全文召回：{_display_text(retrieval_policy.get("fulltext_top_k"))}',
            f'向量召回：{_display_text(retrieval_policy.get("vector_top_k"))}',
            f'最终返回：{_display_text(retrieval_policy.get("final_top_k"))}',
            f'上下文扩展：{_format_context_strategy_summary(retrieval_policy)}',
        ],
        tone="neutral",
    )


def format_settings_template_detail_markdown(template: dict | None) -> str:
    """将模板详情转换为 Markdown。"""

    resolved = template or {}
    if not resolved.get("template_id"):
        return "### 模板详情\n- 当前状态：未选择模板"
    retrieval_policy = resolved.get("retrieval_policy", {}) if isinstance(resolved.get("retrieval_policy", {}), dict) else {}
    return "\n".join(
        [
            "### 模板详情",
            f'- 模板 ID：{_display_text(resolved.get("template_id"))}',
            f'- 模板名称：{_display_text(resolved.get("template_name"))}',
            f'- 模板来源：{_display_text(resolved.get("source_label") or resolved.get("source_type"))}',
            f'- 规则标签：{_display_text(resolved.get("rule_tags"))}',
            f'- 模板说明：{_display_text(resolved.get("description"))}',
            f'- 全文召回：{_display_text(retrieval_policy.get("fulltext_top_k"))}',
            f'- 向量召回：{_display_text(retrieval_policy.get("vector_top_k"))}',
            f'- 最终返回：{_display_text(retrieval_policy.get("final_top_k"))}',
            f'- 上下文扩展：{_format_context_strategy_summary(retrieval_policy)}',
        ]
    )


def format_quality_template_html(template: dict | None) -> str:
    """构建质检模板内容展示面板。"""

    resolved = template or {}
    if not resolved:
        return _build_panel_html(
            title="模板内容",
            description="请选择质检模板后查看适用场景、检索策略和提示词内容。",
            cards=[("当前状态", "未选择模板")],
            notes=["选择模板后，这里会同步显示模板说明和关键配置。"],
            tone="neutral",
        )

    retrieval_policy = resolved.get("retrieval_policy", {}) if isinstance(resolved.get("retrieval_policy", {}), dict) else {}
    system_prompt = _display_text(resolved.get("system_prompt"))
    user_prompt_template = _display_text(resolved.get("user_prompt_template"))
    summary_html = _build_panel_html(
        title="模板内容",
        description=_display_text(resolved.get("description")),
        cards=[
            ("模板名称", _display_text(resolved.get("template_name"))),
            ("模板 ID", _display_text(resolved.get("template_id"))),
            ("规则标签", "、".join(str(item) for item in resolved.get("rule_tags", []) if item) or "-"),
            ("检索策略", _format_retrieval_policy_summary(retrieval_policy)),
        ],
        notes=[
            f'全文召回：{_display_text(retrieval_policy.get("fulltext_top_k"))}',
            f'向量召回：{_display_text(retrieval_policy.get("vector_top_k"))}',
            f'最终返回：{_display_text(retrieval_policy.get("final_top_k"))}',
            f'上下文扩展：{_format_context_strategy_summary(retrieval_policy)}',
        ],
        tone="neutral",
    )
    return f"""
    <div style="display:grid;grid-template-columns:minmax(260px,1fr) minmax(320px,1.2fr) minmax(320px,1.2fr);gap:12px;align-items:stretch;width:100%;box-sizing:border-box;">
        <div style="min-width:0;display:flex;box-sizing:border-box;">{summary_html}</div>
        <div style="border:1px solid var(--border-color-primary);background:var(--body-background-fill);border-radius:16px;padding:16px 18px;box-sizing:border-box;min-width:0;">
            <div style="font-size:14px;font-weight:700;color:var(--body-text-color);margin:0 0 8px 0;">系统提示词</div>
            <pre style="margin:0;padding:12px 14px;border-radius:12px;background:var(--block-background-fill);border:1px solid var(--border-color-primary);font-size:13px;line-height:1.7;color:var(--body-text-color);white-space:pre-wrap;word-break:break-word;min-height:260px;max-height:420px;overflow:auto;">{escape(system_prompt)}</pre>
        </div>
        <div style="border:1px solid var(--border-color-primary);background:var(--body-background-fill);border-radius:16px;padding:16px 18px;box-sizing:border-box;min-width:0;">
            <div style="font-size:14px;font-weight:700;color:var(--body-text-color);margin:0 0 8px 0;">用户提示模板</div>
            <pre style="margin:0;padding:12px 14px;border-radius:12px;background:var(--block-background-fill);border:1px solid var(--border-color-primary);font-size:13px;line-height:1.7;color:var(--body-text-color);white-space:pre-wrap;word-break:break-word;min-height:260px;max-height:420px;overflow:auto;">{escape(user_prompt_template)}</pre>
        </div>
    </div>
    """


def format_quality_progress_html(progress: dict | None) -> str:
    """构建质检执行进度面板。"""

    resolved = progress or {}
    if not resolved:
        return _build_panel_html(
            title="执行进度",
            description="开始质检后，这里会显示当前阶段、Claim 进度和模型调用状态。",
            cards=[
                ("执行状态", "未开始"),
                ("当前阶段", "等待执行"),
                ("处理进度", "-"),
                ("模型状态", "-"),
            ],
            notes=["开始质检后，可在这里看到是否正在检索证据、整理上下文、调用模型和写入结果。"],
            tone="neutral",
        )

    status = _display_text(resolved.get("status")) or "running"
    tone = "success" if status == "success" else "warning" if status == "running" else "neutral"
    claim_index = int(resolved.get("claim_index") or 0)
    claim_total = int(resolved.get("claim_total") or 0)
    if claim_total > 0:
        progress_text = f"{claim_index}/{claim_total}"
    else:
        progress_text = "-"
    notes = []
    if resolved.get("claim_text"):
        notes.append(f'当前 Claim：{_display_text(resolved.get("claim_text"))}')
    if resolved.get("template_name"):
        notes.append(f'当前模板：{_display_text(resolved.get("template_name"))}')
    notes.append(f'阶段说明：{_display_text(resolved.get("message"))}')
    return _build_panel_html(
        title="执行进度",
        description=_display_text(resolved.get("message") or "质检处理中"),
        cards=[
            ("执行状态", _format_quality_progress_status(status)),
            ("当前阶段", _format_quality_progress_stage(resolved.get("stage"))),
            ("处理进度", progress_text),
            ("模型状态", _display_text(resolved.get("model_status")) or "-"),
        ],
        notes=notes,
        tone=tone,
    )


def format_quality_evaluation_summary_html(result: dict | None) -> str:
    """构建 AI 质检效果评测摘要。"""

    metrics = _build_quality_evaluation_metrics(result)
    case_count = metrics["case_count"]
    exact_match_count = metrics["exact_match_count"]
    description = "用于批量验证 AI 质检的结论、风险等级和 Claim 拆分是否符合预期。建议先看核心命中，再看宽松命中。"
    if case_count > 0:
        description = (
            f'本次共评测 {case_count} 条样例，核心命中 {metrics["core_match_count"]} 条，'
            f'宽松命中 {metrics["loose_match_count"]} 条，完全命中 {exact_match_count} 条。'
        )
    return _build_panel_html(
        title="效果评测",
        description=description,
        cards=[
            ("样例总数", _format_number(case_count)),
            ("核心命中", f'{metrics["core_match_count"]} / {case_count} ({metrics["core_match_rate"]})' if case_count > 0 else "0"),
            ("宽松命中", f'{metrics["loose_match_count"]} / {case_count} ({metrics["loose_match_rate"]})' if case_count > 0 else "0"),
            ("完全命中", f'{exact_match_count} / {case_count} ({metrics["exact_match_rate"]})' if case_count > 0 else "0"),
            ("结论命中率", metrics["overall_verdict_match_rate"]),
            ("风险命中率", metrics["risk_level_match_rate"]),
            ("Claim 数命中率", metrics["claim_count_match_rate"]),
            ("主要失败原因", metrics["primary_failure_reason"]),
        ],
        notes=[
            "核心命中：只看结论是否一致，适合先判断系统有没有明显跑偏。",
            "宽松命中：三项里至少两项一致，适合日常验收和模板迭代。",
            "完全命中：三项都一致才算命中，口径最严格。",
            "建议优先关注差异说明和排查方向，不要只看完全命中是否为 0。",
        ],
        tone="success" if case_count > 0 and metrics["core_match_count"] == case_count else "warning" if case_count > 0 else "neutral",
    )


def build_quality_evaluation_rows(result: dict | None) -> list[list[str]]:
    """将 AI 质检效果评测结果转换为表格行。"""

    rows = (result or {}).get("rows") or []
    return [
        [
            _display_text(item.get("case_id")),
            _format_verdict_label(item.get("expected_overall_verdict")),
            _format_verdict_label(item.get("actual_overall_verdict")),
            _format_match_label(_get_quality_evaluation_match_state(item, "overall_verdict")),
            _format_risk_level_label(item.get("expected_risk_level")),
            _format_risk_level_label(item.get("actual_risk_level")),
            _format_match_label(_get_quality_evaluation_match_state(item, "risk_level")),
            _display_text(item.get("expected_claim_count")),
            _display_text(item.get("actual_claim_count")),
            _format_match_label(_get_quality_evaluation_match_state(item, "claim_count")),
            _format_match_label(_is_quality_evaluation_loose_match(item)),
            "是" if item.get("all_matched") else "否",
            _describe_quality_evaluation_diff(item),
            _suggest_quality_evaluation_troubleshooting(item),
            _truncate_text(item.get("input_text"), limit=80),
        ]
        for item in rows
    ]


def format_quality_evaluation_result_markdown(result: dict | None) -> str:
    """将效果评测摘要转换为 Markdown 文本。"""

    metrics = _build_quality_evaluation_metrics(result)
    return "\n".join(
        [
            "### 效果评测",
            f'- 样例总数：{_format_number(metrics["case_count"])}',
            f'- 核心命中：{_format_number(metrics["core_match_count"])} / {metrics["case_count"]}（{metrics["core_match_rate"]}）' if metrics["case_count"] else "- 核心命中：0",
            f'- 宽松命中：{_format_number(metrics["loose_match_count"])} / {metrics["case_count"]}（{metrics["loose_match_rate"]}）' if metrics["case_count"] else "- 宽松命中：0",
            f'- 完全命中：{_format_number(metrics["exact_match_count"])} / {metrics["case_count"]}（{metrics["exact_match_rate"]}）' if metrics["case_count"] else "- 完全命中：0",
            f'- 结论命中率：{metrics["overall_verdict_match_rate"]}',
            f'- 风险命中率：{metrics["risk_level_match_rate"]}',
            f'- Claim 数命中率：{metrics["claim_count_match_rate"]}',
            f'- 主要失败原因：{metrics["primary_failure_reason"]}',
        ]
    )


def format_quality_evaluation_summary_markdown(result: dict | None) -> str:
    """兼容旧调用，输出细化后的效果评测摘要 Markdown。"""

    return format_quality_evaluation_result_markdown(result)


def format_quality_evaluation_export_markdown(result: dict | None) -> str:
    """汇总效果评测摘要与明细，用于导出。"""

    sections = [format_quality_evaluation_result_markdown(result), "", "#### 评测明细"]
    rows = build_quality_evaluation_rows(result)
    if rows:
        sections.append(
            _build_markdown_table(
                [
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
                rows,
            )
        )
    else:
        sections.append("- 暂无评测结果")
    return "\n".join(sections)


def _build_quality_evaluation_metrics(result: dict | None) -> dict[str, object]:
    """基于评测结果构建更适合展示的统计指标。"""

    resolved = result or {}
    summary = resolved.get("summary") or {}
    rows = resolved.get("rows") or []
    case_count = int(summary.get("case_count") or len(rows) or 0)
    overall_count = int(summary.get("overall_verdict_match_count") or 0)
    risk_count = int(summary.get("risk_level_match_count") or 0)
    claim_count = int(summary.get("claim_count_match_count") or 0)
    exact_count = int(summary.get("exact_match_count") or 0)
    loose_count = sum(1 for item in rows if _is_quality_evaluation_loose_match(item))
    if not rows:
        loose_count = exact_count
    failure_reason = _summarize_quality_evaluation_failure_reason(rows)
    return {
        "case_count": case_count,
        "core_match_count": overall_count,
        "loose_match_count": loose_count,
        "exact_match_count": exact_count,
        "overall_verdict_match_rate": _format_ratio(overall_count, case_count),
        "risk_level_match_rate": _format_ratio(risk_count, case_count),
        "claim_count_match_rate": _format_ratio(claim_count, case_count),
        "core_match_rate": _format_ratio(overall_count, case_count),
        "loose_match_rate": _format_ratio(loose_count, case_count),
        "exact_match_rate": _format_ratio(exact_count, case_count),
        "primary_failure_reason": failure_reason,
    }


def _get_quality_evaluation_match_state(item: dict, field_name: str) -> bool:
    """读取或回推效果评测某一项的命中状态。"""

    explicit_key = f"{field_name}_matched"
    if explicit_key in item:
        return bool(item.get(explicit_key))
    expected = item.get(f"expected_{field_name}")
    actual = item.get(f"actual_{field_name}")
    if expected in (None, ""):
        return True
    return str(expected) == str(actual)


def _is_quality_evaluation_loose_match(item: dict) -> bool:
    """判断一条效果评测样例是否达到宽松命中。"""

    matched_count = sum(
        1
        for field_name in ("overall_verdict", "risk_level", "claim_count")
        if _get_quality_evaluation_match_state(item, field_name)
    )
    return matched_count >= 2


def _describe_quality_evaluation_diff(item: dict) -> str:
    """生成当前样例的差异说明。"""

    diff_parts: list[str] = []
    if not _get_quality_evaluation_match_state(item, "overall_verdict"):
        diff_parts.append("结论不一致")
    if not _get_quality_evaluation_match_state(item, "risk_level"):
        diff_parts.append("风险等级不一致")
    if not _get_quality_evaluation_match_state(item, "claim_count"):
        diff_parts.append("Claim 拆分不一致")
    if not diff_parts:
        return "三项均命中"
    return "；".join(diff_parts)


def _suggest_quality_evaluation_troubleshooting(item: dict) -> str:
    """根据差异类型给出优先排查方向。"""

    overall_miss = not _get_quality_evaluation_match_state(item, "overall_verdict")
    risk_miss = not _get_quality_evaluation_match_state(item, "risk_level")
    claim_miss = not _get_quality_evaluation_match_state(item, "claim_count")
    if not any((overall_miss, risk_miss, claim_miss)):
        return "无需排查"
    if overall_miss and claim_miss:
        return "优先排查模板判定、证据召回和 Claim 拆分"
    if overall_miss and risk_miss:
        return "优先排查模板判定与风险分级策略"
    if claim_miss and risk_miss:
        return "优先排查 Claim 拆分与风险分级策略"
    if overall_miss:
        return "优先排查模板判定、证据召回和提示词"
    if claim_miss:
        return "优先排查输入切分、句式拆分和 Claim 生成"
    return "优先排查风险分级阈值与保守策略"


def _summarize_quality_evaluation_failure_reason(rows: list[dict]) -> str:
    """汇总评测中最主要的失败原因。"""

    if not rows:
        return "-"
    reason_counts = {
        "结论不一致": 0,
        "风险等级不一致": 0,
        "Claim 拆分不一致": 0,
    }
    for item in rows:
        if not _get_quality_evaluation_match_state(item, "overall_verdict"):
            reason_counts["结论不一致"] += 1
        if not _get_quality_evaluation_match_state(item, "risk_level"):
            reason_counts["风险等级不一致"] += 1
        if not _get_quality_evaluation_match_state(item, "claim_count"):
            reason_counts["Claim 拆分不一致"] += 1
    max_count = max(reason_counts.values())
    if max_count <= 0:
        return "无明显失败项"
    top_reasons = [name for name, count in reason_counts.items() if count == max_count]
    return " / ".join(top_reasons) + f"（{max_count} 条）"


def _format_match_label(value: bool) -> str:
    """格式化命中状态。"""

    return "是" if value else "否"


def _format_ratio(numerator: int, denominator: int) -> str:
    """将命中数格式化为百分比文本。"""

    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


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
        <div style="border:1px solid var(--border-color-primary);background:var(--body-background-fill);border-radius:16px;padding:16px 18px;margin:0 0 12px 0;max-width:100%;overflow:hidden;">
            <div style="font-size:16px;font-weight:700;color:var(--body-text-color);margin:0 0 8px 0;">原文内容</div>
            <div style="font-size:14px;line-height:1.8;color:var(--body-text-color);white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;max-width:100%;overflow:hidden;">{content_html}</div>
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
            ("归属知识库", _display_text(resolved.get("knowledge_base_id"))),
            ("文件大小", _display_text(resolved.get("size_display"))),
            ("是否已注册", _display_text(resolved.get("registered_label"))),
            ("索引状态", _display_text(resolved.get("index_status"))),
            ("是否需重建", _display_text(resolved.get("needs_rebuild_label"))),
        ],
        notes=[
            f'存放位置：{_display_text(resolved.get("storage_label"))}',
            f'文件路径：{_display_text(resolved.get("source_path"))}',
        ],
        tone=tone,
    )


def format_document_quality_report_html(report: dict | None) -> str:
    """将单文档入库质检结果转换为总览卡片。"""

    resolved = report or {}
    document = resolved.get("document") or {}
    metrics = resolved.get("metrics") or {}
    summary = resolved.get("summary") or {}
    if not document:
        return _build_panel_html(
            title="入库质检",
            description="请选择已入库文档后执行质检。",
            cards=[("当前状态", "未执行")],
            notes=["这里会展示章节、分块、全文/向量索引是否完备。"],
            tone="neutral",
        )

    return _build_panel_html(
        title="入库质检",
        description=_display_text(summary.get("message")),
        cards=[
            ("文档名称", _display_text(document.get("doc_title"))),
            ("章节数", _format_number(metrics.get("section_count"))),
            ("分块数", _format_number(metrics.get("chunk_count"))),
            ("全文索引数", _format_number(metrics.get("fts_chunk_count"))),
            ("向量数", _format_number(metrics.get("vector_chunk_count"))),
            ("平均分块长度", f'{_display_text(metrics.get("avg_chunk_chars"))} 字'),
        ],
        notes=[
            f'首章标题：{_display_text(resolved.get("first_section_title"))}',
            f'末章标题：{_display_text(resolved.get("last_section_title"))}',
            f'平均每章分块数：{_display_text(metrics.get("avg_chunks_per_section"))}',
        ],
        tone=_map_quality_tone(summary.get("level")),
    )


def format_document_quality_report_markdown(report: dict | None) -> str:
    """将单文档入库质检总览转换为 Markdown。"""

    resolved = report or {}
    document = resolved.get("document") or {}
    metrics = resolved.get("metrics") or {}
    summary = resolved.get("summary") or {}
    if not document:
        return "### 入库质检\n- 当前状态：未执行"
    return "\n".join(
        [
            "### 入库质检",
            f'- 文档名称：{_display_text(document.get("doc_title"))}',
            f'- 文档 UID：{_display_text(document.get("doc_uid"))}',
            f'- 质检结论：{_display_text(summary.get("message"))}',
            f'- 章节数：{_format_number(metrics.get("section_count"))}',
            f'- 分块数：{_format_number(metrics.get("chunk_count"))}',
            f'- 全文索引数：{_format_number(metrics.get("fts_chunk_count"))}',
            f'- 向量数：{_format_number(metrics.get("vector_chunk_count"))}',
            f'- 平均分块长度：{_display_text(metrics.get("avg_chunk_chars"))} 字',
            f'- 首章标题：{_display_text(resolved.get("first_section_title"))}',
            f'- 末章标题：{_display_text(resolved.get("last_section_title"))}',
            f'- 平均每章分块数：{_display_text(metrics.get("avg_chunks_per_section"))}',
        ]
    )


def format_document_quality_checks_html(report: dict | None) -> str:
    """将单文档入库质检检查项与风险提示转换为卡片。"""

    resolved = report or {}
    checks = resolved.get("checks") or []
    issues = resolved.get("issues") or []
    if not checks:
        return _build_panel_html(
            title="质检结论",
            description="执行入库质检后，这里会汇总检查项结论。",
            cards=[("检查项", "0"), ("风险提示", "0")],
            notes=["建议先执行一次质检，再查看章节和分块抽样。"],
            tone="neutral",
        )

    passed_count = sum(1 for item in checks if item.get("passed"))
    warning_count = sum(1 for item in checks if item.get("level") == "warning")
    failed_count = sum(1 for item in checks if item.get("level") == "danger")
    check_notes = [
        f'{_display_text(item.get("name"))}：{_display_text(item.get("message"))}'
        for item in checks[:6]
    ]
    issue_notes = [f'风险提示：{_display_text(item.get("message"))}' for item in issues[:4]]
    return _build_panel_html(
        title="质检结论",
        description="用于快速判断当前文档的结构、全文索引与向量索引是否完备。",
        cards=[
            ("检查项总数", str(len(checks))),
            ("已通过", str(passed_count)),
            ("警告", str(warning_count)),
            ("失败", str(failed_count)),
        ],
        notes=check_notes + issue_notes,
        tone="danger" if failed_count > 0 else "warning" if warning_count > 0 or issues else "success",
    )


def format_document_quality_checks_markdown(report: dict | None) -> str:
    """将单文档质检结论转换为 Markdown。"""

    resolved = report or {}
    checks = resolved.get("checks") or []
    issues = resolved.get("issues") or []
    lines = [
        "### 质检结论",
        f"- 检查项总数：{len(checks)}",
        f"- 风险提示数：{len(issues)}",
        "",
        "#### 检查项",
    ]
    if checks:
        lines.extend(
            f'- {_display_text(item.get("name"))}：{_display_text(item.get("message"))}'
            for item in checks
        )
    else:
        lines.append("- 暂无检查项")
    lines.extend(["", "#### 风险提示"])
    if issues:
        lines.extend(f'- {_display_text(item.get("message"))}' for item in issues)
    else:
        lines.append("- 暂无风险提示")
    return "\n".join(lines)


def build_document_quality_section_rows(report: dict | None) -> list[list[str]]:
    """将章节抽样结果转换为表格行。"""

    items = (report or {}).get("section_samples") or []
    return [
        [
            _display_text(item.get("source_span")),
            _display_text(item.get("section_title")),
            _format_number(item.get("section_level")),
            _format_number(item.get("content_length")),
            _truncate_text(item.get("content_preview"), limit=90),
        ]
        for item in items
    ]


def build_document_quality_chunk_rows(report: dict | None) -> list[list[str]]:
    """将分块抽样结果转换为表格行。"""

    items = (report or {}).get("chunk_samples") or []
    return [
        [
            _display_text(item.get("chunk_id")),
            _format_number(item.get("chunk_index")),
            _display_text(item.get("section_title")),
            _display_text(item.get("source_span")),
            _format_number(item.get("token_count")),
            _truncate_text(item.get("content_preview"), limit=90),
        ]
        for item in items
    ]


def format_document_quality_search_summary_html(formatted: dict | None, *, doc_title: str = "") -> str:
    """构建单文档检索验证摘要。"""

    resolved = formatted or {}
    count = int(resolved.get("count") or 0)
    return _build_panel_html(
        title="文档内检索验证",
        description="用于验证当前文档的分块和索引是否能召回正确内容。",
        cards=[
            ("当前文档", _display_text(doc_title)),
            ("命中条数", str(count)),
            ("当前查询", _display_text(resolved.get("query_text"))),
        ],
        notes=[
            "建议输入该文档中确定存在的专有词、标题或关键句做验证。",
            "命中 0 条时，需要结合章节/分块抽样一起判断是切分问题还是索引问题。",
        ],
        tone="success" if count > 0 else "neutral",
    )


def format_document_quality_search_summary_markdown(formatted: dict | None, *, doc_title: str = "") -> str:
    """将单文档检索验证摘要转换为 Markdown。"""

    resolved = formatted or {}
    return "\n".join(
        [
            "### 文档内检索验证",
            f"- 当前文档：{_display_text(doc_title)}",
            f'- 命中条数：{_format_number(resolved.get("count"))}',
            f'- 当前查询：{_display_text(resolved.get("query_text"))}',
        ]
    )


def format_document_quality_export_markdown(
    report: dict | None,
    batch_result: dict | None,
    search_formatted: dict | None,
    selected_search_item: dict | None,
    *,
    query_text: str = "",
) -> str:
    """将单文档入库质检导出为更适合预览阅读的 Markdown。"""

    doc_title = _display_text((report or {}).get("document", {}).get("doc_title"))
    return "\n".join(
        [
            format_document_quality_report_markdown(report),
            "",
            format_document_quality_checks_markdown(report),
            "",
            format_document_quality_batch_summary_markdown(batch_result),
            "",
            format_document_quality_search_summary_markdown(search_formatted, doc_title=doc_title),
            "",
            format_search_export_markdown(search_formatted, selected_search_item, query_text=query_text),
            "",
            format_document_quality_config_markdown(None),
        ]
    )


def format_document_quality_batch_export_markdown(batch_result: dict | None) -> str:
    """将批量入库质检结果导出为摘要加分块明细。"""

    sections = [format_document_quality_batch_summary_markdown(batch_result), "", "#### 文档明细"]
    rows = build_document_quality_batch_rows(batch_result)
    if rows:
        sections.append(
            _build_markdown_named_blocks(
                item_name="文档",
                columns=["文档名称", "文档 UID", "索引状态", "章节数", "分块数", "全文索引", "向量数", "质检等级", "风险摘要"],
                rows=rows,
            )
        )
    else:
        sections.append("- 暂无批量质检结果")
    return "\n".join(sections)


def format_document_quality_batch_summary_html(batch_result: dict | None) -> str:
    """构建批量入库质检摘要。"""

    resolved = batch_result or {}
    summary = resolved.get("summary") or {}
    return _build_panel_html(
        title="批量入库质检",
        description="用于快速查看所有已入库文档的章节、分块与索引异常分布。",
        cards=[
            ("文档总数", _format_number(summary.get("document_count"))),
            ("正常", _format_number(summary.get("success_count"))),
            ("警告", _format_number(summary.get("warning_count"))),
            ("失败", _format_number(summary.get("danger_count"))),
        ],
        notes=[
            "建议优先处理警告和失败文档，再做定向重建或人工抽样复核。",
            "导出 CSV 后可进一步人工筛查和留档。",
        ],
        tone="danger" if int(summary.get("danger_count") or 0) > 0 else "warning" if int(summary.get("warning_count") or 0) > 0 else "neutral",
    )


def format_document_quality_batch_summary_markdown(batch_result: dict | None) -> str:
    """将批量入库质检摘要转换为 Markdown。"""

    summary = (batch_result or {}).get("summary") or {}
    return "\n".join(
        [
            "### 批量入库质检",
            f'- 文档总数：{_format_number(summary.get("document_count"))}',
            f'- 正常：{_format_number(summary.get("success_count"))}',
            f'- 警告：{_format_number(summary.get("warning_count"))}',
            f'- 失败：{_format_number(summary.get("danger_count"))}',
        ]
    )


def build_document_quality_batch_rows(batch_result: dict | None) -> list[list[str]]:
    """将批量入库质检结果转换为表格行。"""

    reports = (batch_result or {}).get("reports") or []
    return [
        [
            _display_text(report.get("document", {}).get("doc_title")),
            _display_text(report.get("document", {}).get("doc_uid")),
            _display_text(report.get("document", {}).get("index_status")),
            _format_number(report.get("metrics", {}).get("section_count")),
            _format_number(report.get("metrics", {}).get("chunk_count")),
            _format_number(report.get("metrics", {}).get("fts_chunk_count")),
            _format_number(report.get("metrics", {}).get("vector_chunk_count")),
            _display_text(report.get("summary", {}).get("level")),
            _truncate_text("；".join(str(item.get("message") or "") for item in report.get("issues", [])) or report.get("summary", {}).get("message"), limit=80),
        ]
        for report in reports
    ]


def format_document_quality_config_html(config: dict | None) -> str:
    """构建入库质检阈值摘要。"""

    resolved = config or {}
    return _build_panel_html(
        title="质检阈值",
        description="这些阈值会直接影响章节过少、分块过碎、超长/过短分块等判定。",
        cards=[
            ("抽样数量", _format_number(resolved.get("sample_limit"))),
            ("长文阈值", f'{_format_number(resolved.get("long_document_char_threshold"))} 字'),
            ("长文最少章节", _format_number(resolved.get("min_sections_for_long_doc"))),
            ("每章分块上限", _format_number(resolved.get("max_avg_chunks_per_section"))),
        ],
        notes=[
            f'超长分块阈值：{_format_number(resolved.get("max_chunk_chars"))} 字',
            f'过短分块阈值：{_format_number(resolved.get("short_chunk_chars"))} 字',
            f'过短分块告警起点：{_format_number(resolved.get("short_chunk_warn_min_chunk_count"))} 个分块',
            f'配置文件：{_display_text(resolved.get("config_path"))}',
        ],
        tone="neutral",
    )


def format_document_quality_config_markdown(config: dict | None) -> str:
    """将入库质检阈值配置转换为 Markdown。"""

    resolved = config or {}
    return "\n".join(
        [
            "### 质检阈值",
            f'- 抽样数量：{_format_number(resolved.get("sample_limit"))}',
            f'- 长文阈值：{_format_number(resolved.get("long_document_char_threshold"))} 字',
            f'- 长文最少章节：{_format_number(resolved.get("min_sections_for_long_doc"))}',
            f'- 每章分块上限：{_format_number(resolved.get("max_avg_chunks_per_section"))}',
            f'- 超长分块阈值：{_format_number(resolved.get("max_chunk_chars"))} 字',
            f'- 过短分块阈值：{_format_number(resolved.get("short_chunk_chars"))} 字',
            f'- 过短分块告警起点：{_format_number(resolved.get("short_chunk_warn_min_chunk_count"))}',
            f'- 配置文件：{_display_text(resolved.get("config_path"))}',
        ]
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
    has_success = "success" in resolved
    success = bool(resolved.get("success"))
    progress_summary = resolved.get("progress_summary") or {}
    jobs = resolved.get("jobs") or []
    accepted = resolved.get("accepted") or []
    description = _display_text(resolved.get("message")) if resolved.get("message") else (
        "操作已完成" if success else ("操作未成功" if has_success else "等待操作")
    )
    notes: list[str] = []
    if resolved.get("error_code"):
        notes.append(f'错误代码：{_display_text(resolved.get("error_code"))}')
    if resolved.get("linked_claim_id"):
        notes.append(f'关联 Claim：{_display_text(resolved.get("linked_claim_id"))}')
    if resolved.get("linked_check_id"):
        notes.append(f'关联质检：{_display_text(resolved.get("linked_check_id"))}')
    footer_html = None
    if resolved.get("download_url"):
        file_name = _display_text(resolved.get("download_file_name") or "点击下载")
        download_url = str(resolved.get("download_url") or "")
        link_items = [
            (
                '<div style="margin:0 0 12px 0;padding:12px 14px;'
                'border:1px solid var(--border-color-primary);border-radius:12px;'
                'background:var(--body-background-fill);">'
                '<div style="font-size:13px;font-weight:700;margin:0 0 6px 0;">下载文件</div>'
                f'<div style="margin:0 0 6px 0;"><a href="{escape(download_url)}" '
                'target="_blank" rel="noopener noreferrer" '
                'style="display:inline-block;max-width:100%;white-space:normal;word-break:break-word;overflow-wrap:anywhere;">'
                f"{escape(file_name)}</a></div>"
                '<div style="font-size:12px;color:var(--body-text-color-subdued);margin:0 0 4px 0;">下载地址</div>'
                '<div style="font-size:12px;line-height:1.7;color:var(--body-text-color);'
                'white-space:normal;word-break:break-word;overflow-wrap:anywhere;">'
                f"{escape(download_url)}</div>"
                "</div>"
            )
        ]
        if resolved.get("preview_url"):
            preview_name = _display_text(resolved.get("preview_file_name") or "查看渲染效果")
            preview_url = str(resolved.get("preview_url") or "")
            link_items.append(
                '<div style="margin:0;padding:12px 14px;'
                'border:1px solid var(--border-color-primary);border-radius:12px;'
                'background:var(--body-background-fill);">'
                '<div style="font-size:13px;font-weight:700;margin:0 0 6px 0;">查看渲染效果</div>'
                f'<div style="margin:0 0 6px 0;"><a href="{escape(preview_url)}" '
                'target="_blank" rel="noopener noreferrer" '
                'style="display:inline-block;max-width:100%;white-space:normal;word-break:break-word;overflow-wrap:anywhere;">'
                f"{escape(preview_name)}</a></div>"
                '<div style="font-size:12px;color:var(--body-text-color-subdued);margin:0 0 4px 0;">预览地址</div>'
                '<div style="font-size:12px;line-height:1.7;color:var(--body-text-color);'
                'white-space:normal;word-break:break-word;overflow-wrap:anywhere;">'
                f"{escape(preview_url)}</div>"
                "</div>"
            )
        footer_html = "".join(link_items)

    status_label = _display_text(resolved.get("status_label")) if resolved.get("status_label") else "当前状态"
    status_value = _display_text(resolved.get("status_value")) if resolved.get("status_value") else "等待操作"
    cards = [("执行状态", "成功" if success else "失败")] if has_success else [(status_label, status_value)]
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
        footer_html=footer_html,
        tone=("success" if success else "danger") if has_success else "neutral",
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
            _wrap_search_row_cell(_display_text(item.get("retrieval_source")), is_selected=index == selected_row_index),
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


def format_search_result_detail_markdown(item: dict | None, *, query_text: str = "") -> str:
    """将检索结果详情转换为 Markdown 文本。"""

    resolved = item or {}
    if not resolved:
        return "#### 原文详情\n- 当前状态：未选择结果"

    return "\n".join(
        [
            "#### 原文详情",
            f'- 当前查询：{_display_text(query_text)}',
            f'- 文档名称：{_display_text(resolved.get("doc_title") or resolved.get("source_name"))}',
            f'- 片段 ID：{_display_text(resolved.get("chunk_id"))}',
            f'- 片段序号：{_display_text(resolved.get("chunk_index"))}',
            f'- 定位：{_display_text(resolved.get("source_span"))}',
            f'- 检索来源：{_display_text(resolved.get("retrieval_source"))}',
            f'- 匹配来源：{_display_text(resolved.get("matched_sources"))}',
            f'- 相关度：{_format_score(resolved.get("score"))}',
            f'- 重排分：{_format_score(resolved.get("rerank_score"))}',
            f'- 章节：{_display_text(resolved.get("section_title"))}',
            f'- 作者：{_display_text(resolved.get("author"))}',
            "",
            "#### 原文内容",
            _display_text(resolved.get("content") or resolved.get("expanded_content")),
        ]
    )


def format_search_export_markdown(formatted: dict | None, selected_item: dict | None, *, query_text: str = "") -> str:
    """汇总检索结果摘要、列表和详情，用于导出。"""

    rows = (formatted or {}).get("table") or []
    sections = [format_search_summary_markdown(formatted), "", "#### 结果列表"]
    if rows:
        sections.append(
            _build_markdown_named_blocks(
                item_name="结果",
                columns=["序号", "文档名称", "定位", "片段 ID", "检索来源", "相关度", "重排分", "匹配来源", "内容摘要"],
                rows=[
                    [
                        index + 1,
                        item.get("doc_title") or item.get("source_name"),
                        item.get("source_span"),
                        item.get("chunk_id"),
                        item.get("retrieval_source"),
                        _format_score(item.get("score")),
                        _format_score(item.get("rerank_score")),
                        _display_text(item.get("matched_sources")),
                        item.get("content_preview_highlighted") or item.get("content_preview"),
                    ]
                    for index, item in enumerate(rows)
                ],
            )
        )
    else:
        sections.append("- 暂无检索结果")
    sections.extend(["", format_search_result_detail_markdown(selected_item, query_text=query_text)])
    return "\n".join(sections)


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
            item["knowledge_base_id"],
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
        "table_headers": ["文件名", "文档名称", "归属知识库", "大小", "入库时间", "已注册", "索引状态", "需重建", "推荐动作", "错误信息"],
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
        "knowledge_base_id": (input_document or {}).get("knowledge_base_id") or (status_item or {}).get("knowledge_base_id") or "default",
        "storage_label": (input_document or {}).get("storage_label") or ("数据库记录" if status_item else "-"),
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
        "ingested_at": _format_display_datetime((status_item or {}).get("created_at")),
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


def _build_markdown_table(headers: list[object], rows: list[list[object]]) -> str:
    """将表头和行数据转换为 Markdown 表格。"""

    header_row = "| " + " | ".join(_escape_markdown_table_cell(item) for item in headers) + " |"
    separator_row = "| " + " | ".join("---" for _ in headers) + " |"
    body_rows = [
        "| " + " | ".join(_escape_markdown_table_cell(cell) for cell in row) + " |"
        for row in rows
    ]
    return "\n".join([header_row, separator_row, *body_rows])


def _build_markdown_named_blocks(item_name: str, columns: list[object], rows: list[list[object]]) -> str:
    """将宽表导出为命名块，降低预览页横向滚动风险。"""

    sections: list[str] = []
    for index, row in enumerate(rows, start=1):
        sections.append(f"##### {item_name} {index}")
        for column_name, cell in zip(columns, row):
            sections.append(f"- {_display_text(column_name)}：{_display_text(cell)}")
        sections.append("")
    return "\n".join(sections).rstrip()


def _escape_markdown_table_cell(value: object) -> str:
    """转义 Markdown 表格单元格中的特殊字符。"""

    return str(value if value not in (None, "") else "-").replace("\r", " ").replace("\n", "<br>").replace("|", "\\|")


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
            "evidence_judgement": item.get("evidence_judgement", "insufficient"),
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
            f'- 总体结论：{_format_verdict_label(check.get("overall_verdict") or resolved.get("summary"))}',
            f'- 模板名称：{_display_text(check.get("template_name"))}',
            f"- Claim 数量：{len(claims)}",
            f'- 摘要说明：{_display_text(resolved.get("summary"))}',
        ]
    )


def format_quality_export_markdown(
    formatted: dict | None,
    claim_detail: dict | None,
) -> str:
    """按 Claim 顺序导出完整 AI 质检结果。"""

    resolved = formatted or {}
    sections = [format_quality_result_markdown(resolved)]
    claims = resolved.get("claims") or []
    claim_detail_map = resolved.get("claim_detail_map") or build_claim_detail_map(claims)
    if not claims:
        sections.extend(["", "- 暂无 Claim"])
        return "\n".join(sections)

    for index, claim_item in enumerate(claims, start=1):
        claim_id = _display_text(claim_item.get("claim_id"))
        claim_detail_by_id = (
            format_claim_detail_for_review(claim_id, claim_detail_map)
            if claim_item.get("claim_id")
            else {}
        )
        current_claim_detail = claim_detail_by_id
        selected_summary = (claim_detail or {}).get("summary") or {}
        if selected_summary.get("claim_id") == claim_item.get("claim_id"):
            current_claim_detail = claim_detail or claim_detail_by_id
        evidence_items = current_claim_detail.get("evidence_table") or []
        sections.extend(
            [
                "",
                f"## Claim {index}",
                format_claim_detail_markdown(current_claim_detail),
            ]
        )
        if evidence_items:
            sections.extend(["", "#### 完整证据详情"])
            for evidence_index, evidence_item in enumerate(evidence_items, start=1):
                sections.extend(
                    [
                        "",
                        f"##### 证据 {evidence_index}",
                        format_evidence_detail_markdown(evidence_item),
                    ]
                )
        else:
            sections.extend(["", "- 当前 Claim 暂无证据条目"])
    return "\n".join(sections)


def format_quality_result_html(formatted: dict | None) -> str:
    """将质检结果转换为卡片式 HTML。"""

    resolved = formatted or {}
    check = resolved.get("check") or {}
    claims = resolved.get("claims") or []
    raw_overall_verdict = _display_text(check.get("overall_verdict") or resolved.get("summary"))
    overall_verdict = _format_verdict_label(raw_overall_verdict)
    tone = "warning" if "review" in raw_overall_verdict.lower() else "success"
    return _build_panel_html(
        title="质检结果",
        description=_display_text(resolved.get("summary")),
        cards=[
            ("总体结论", overall_verdict),
            ("模板名称", _display_text(check.get("template_name"))),
            ("Claim 数量", str(len(claims))),
            ("质检 ID", _display_text(check.get("check_id"))),
        ],
        notes=[
            "下方展示 Claim 列表、最近质检记录与证据详情",
            "本次结果已完成写库校验，刷新后仍可在历史记录中查看" if check.get("persist_verified") else "历史记录与人工审核列表均以数据库已落库结果为准",
        ],
        tone=tone,
    )


def format_active_quality_check_html(formatted: dict | None) -> str:
    """构建当前激活质检记录的高亮提示。"""

    resolved = formatted or {}
    check = resolved.get("check") or {}
    check_id = _display_text(check.get("check_id"))
    if check_id == "-":
        return _build_panel_html(
            title="当前激活质检",
            description="尚未加载质检结果",
            cards=[("质检 ID", "-"), ("模板", "-"), ("Claim 数", "0")],
            notes=["点击最近质检记录或执行新质检后，这里会同步显示当前激活任务。"],
            tone="neutral",
        )
    claims = resolved.get("claims") or []
    return _build_panel_html(
        title="当前激活质检",
        description="当前 Claim 列表与证据详情均跟随这条质检记录联动。",
        cards=[
            ("质检 ID", check_id),
            ("模板", _display_text(check.get("template_name"))),
            ("Claim 数", str(len(claims))),
        ],
        notes=[
            f'总体结论：{_format_verdict_label(check.get("overall_verdict"))}',
            f'时间：{_format_display_datetime(check.get("created_at"))}',
        ],
        tone="success" if len(claims) > 1 else "neutral",
    )


def build_quality_claim_rows(formatted: dict | None) -> list[list[str]]:
    """将质检结果中的 Claim 转换为表格行。"""

    rows = (formatted or {}).get("claims_table") or []
    return [
        [
            _display_text(item.get("claim_id")),
            _display_text(item.get("claim_text")),
            _format_verdict_label(item.get("verdict")),
            _format_risk_level_label(item.get("risk_level")),
            _format_score(item.get("confidence")),
            _format_evidence_relation_label(item.get("evidence_judgement")),
            _display_text(item.get("source_doc")),
            _display_text(item.get("source_span")),
        ]
        for item in rows
    ]


def parse_claim_choice(choice: str) -> str:
    """从审核下拉项中解析 claim_id。"""

    if not choice:
        return ""
    if " | " not in choice:
        return choice.strip()
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
            "evidence_judgement": item.get("evidence_judgement", "insufficient"),
            "review_status": item.get("review_status", "pending"),
            "source_doc": item.get("source_doc"),
            "source_span": item.get("source_span"),
            "check_id": item.get("check_id"),
            "template_name": item.get("template_name"),
            "check_created_at": item.get("check_created_at"),
            "evidence": item.get("evidence", ""),
            "evidence_reason": item.get("evidence_reason", ""),
            "evidence_details": item.get("evidence_details", [])
            or (
                [
                    {
                        "chunk_id": item.get("source_span") or item["claim_id"],
                        "doc_uid": item.get("source_doc", ""),
                        "doc_title": item.get("source_doc", ""),
                        "source_span": item.get("source_span", ""),
                        "retrieval_source": item.get("retrieval_source", "history"),
                        "matched_sources": item.get("matched_sources", ["history"]),
                        "matched_queries": item.get("matched_queries", ["history"]),
                        "rerank_score": item.get("rerank_score"),
                        "context_mode": item.get("context_mode", "history_record"),
                        "evidence_relation": item.get("evidence_judgement", "insufficient"),
                        "relation_reason": item.get("evidence_reason", ""),
                        "section_title": item.get("section_title", ""),
                        "content_preview": item.get("evidence", "") or item.get("claim_text", ""),
                    }
                ]
                if item.get("source_doc") or item.get("source_span") or item.get("evidence")
                else []
            ),
        }
        for item in claims
        if item.get("claim_id")
    }


def get_claim_detail(claim_choice: str, claim_detail_map: dict | None) -> dict:
    """根据 claim_id 或下拉选项读取 claim 详情。"""

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
            "matched_sources": _format_string_list(item.get("matched_sources", [])),
            "matched_queries": _format_string_list(item.get("matched_queries", [])),
            "rerank_score": item.get("rerank_score"),
            "context_mode": item.get("context_mode", ""),
            "evidence_relation": item.get("evidence_relation", "insufficient"),
            "relation_reason": item.get("relation_reason", ""),
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
            "evidence_judgement": detail.get("evidence_judgement", "insufficient"),
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
            f'- 当前判定：{_format_verdict_label(summary.get("verdict"))}',
            f'- 风险等级：{_format_risk_level_label(summary.get("risk_level"))}',
            f'- 置信度：{_format_score(summary.get("confidence"))}',
            f'- 证据关系：{_format_evidence_relation_label(summary.get("evidence_judgement"))}',
            f'- 审核状态：{_format_review_status_label(summary.get("review_status"))}',
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
    raw_verdict = _display_text(summary.get("verdict"))
    verdict = _format_verdict_label(raw_verdict)
    review_status = _format_review_status_label(summary.get("review_status"))
    evidence_relation = _format_evidence_relation_label(summary.get("evidence_judgement"))
    relation_tone = _get_evidence_relation_tone(summary.get("evidence_judgement"))
    tone = relation_tone if relation_tone != "neutral" else ("warning" if "review" in raw_verdict.lower() or review_status == "pending" else "success")
    return _build_panel_html(
        title="Claim 详情",
        description=_display_text(summary.get("claim_text")),
        cards=[
            ("Claim ID", _display_text(summary.get("claim_id"))),
            ("当前判定", verdict),
            ("证据关系", evidence_relation),
            ("风险等级", _format_risk_level_label(summary.get("risk_level"))),
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
        footer_html=(
            f'<div><strong>关系解读：</strong>{escape(_display_text(summary.get("evidence_reason")))}</div>'
            if summary.get("evidence_reason")
            else None
        ),
        tone=tone,
        badge_text=evidence_relation,
    )


def format_review_record_detail_html(record: dict | None) -> str:
    """将审核记录详情转换为卡片式 HTML。"""

    resolved = record or {}
    if not resolved.get("review_id"):
        return _build_panel_html(
            title="审核记录详情",
            description="请选择审核记录后查看详情",
            cards=[("当前状态", "未选择审核记录")],
            tone="neutral",
        )
    return _build_panel_html(
        title="审核记录详情",
        description=_display_text(resolved.get("claim_text")),
        cards=[
            ("审核 ID", _display_text(resolved.get("review_id"))),
            ("审核动作", _format_review_action_label(resolved.get("review_action"))),
            ("审核状态", _format_review_status_label(resolved.get("review_status"))),
            ("审核人", _display_text(resolved.get("reviewer"))),
            ("审核时间", _format_display_datetime(resolved.get("created_at"))),
            ("关联模板", _display_text(resolved.get("template_name"))),
        ],
        notes=[
            f'关联 Claim：{_display_text(resolved.get("claim_id"))}',
            f'关联质检：{_display_text(resolved.get("check_id"))}',
            f'审核备注：{_display_text(resolved.get("review_note"))}',
        ],
        tone="neutral",
    )


def format_review_record_detail_markdown(record: dict | None) -> str:
    """将审核记录详情转换为 Markdown。"""

    resolved = record or {}
    if not resolved.get("review_id"):
        return "### 审核记录详情\n- 当前状态：未选择审核记录"
    return "\n".join(
        [
            "### 审核记录详情",
            f'- 审核 ID：{_display_text(resolved.get("review_id"))}',
            f'- 关联 Claim：{_display_text(resolved.get("claim_id"))}',
            f'- 关联质检：{_display_text(resolved.get("check_id"))}',
            f'- 审核动作：{_format_review_action_label(resolved.get("review_action"))}',
            f'- 审核状态：{_format_review_status_label(resolved.get("review_status"))}',
            f'- 审核人：{_display_text(resolved.get("reviewer"))}',
            f'- 审核时间：{_format_display_datetime(resolved.get("created_at"))}',
            f'- 关联模板：{_display_text(resolved.get("template_name"))}',
            f'- Claim 摘要：{_display_text(resolved.get("claim_text"))}',
            f'- 审核备注：{_display_text(resolved.get("review_note"))}',
        ]
    )


def format_review_export_markdown(
    claim_detail: dict | None,
    evidence_items: list[dict] | None,
    review_record: dict | None,
) -> str:
    """将人工审核当前查看内容转换为导出 Markdown。"""

    sections = [format_claim_detail_markdown(claim_detail)]
    resolved_evidence_items = list(evidence_items or (claim_detail or {}).get("evidence_table") or [])
    if resolved_evidence_items:
        sections.extend(["", "#### 完整证据详情"])
        for index, evidence_item in enumerate(resolved_evidence_items, start=1):
            sections.extend(
                [
                    "",
                    f"##### 证据 {index}",
                    format_evidence_detail_markdown(evidence_item),
                ]
            )
    else:
        sections.extend(["", "- 当前 Claim 暂无证据条目"])
    sections.extend(["", format_review_record_detail_markdown(review_record)])
    return "\n".join(sections)


def build_claim_evidence_rows(detail: dict | None) -> list[list[str]]:
    """将 Claim 证据转换为表格行。"""

    evidence_rows = (detail or {}).get("evidence_table") or []
    return [
        [
            _display_text(item.get("chunk_id")),
            _display_text(item.get("doc_title") or item.get("doc_uid")),
            _display_text(item.get("source_span")),
            _format_evidence_relation_label(item.get("evidence_relation")),
            _display_text(item.get("retrieval_source")),
            _format_string_list(item.get("matched_queries") or item.get("matched_sources")),
            _format_score(item.get("rerank_score")),
            _display_text(item.get("content_preview")),
        ]
        for item in evidence_rows
    ]


def format_evidence_detail_html(evidence: dict | None) -> str:
    """将单条证据详情转换为卡片式 HTML。"""

    resolved = evidence or {}
    if not resolved:
        return _build_panel_html(
            title="证据详情",
            description="请选择证据列表中的条目后查看详情",
            cards=[("当前状态", "未选择证据")],
            tone="neutral",
        )
    relation_label = _format_evidence_relation_label(resolved.get("evidence_relation"))
    metadata_html = _build_panel_html(
        title="证据详情",
        description="当前已定位到所选证据条目。",
        cards=[
            ("片段 ID", _display_text(resolved.get("chunk_id"))),
            ("文档", _display_text(resolved.get("doc_title") or resolved.get("doc_uid"))),
            ("定位", _display_text(resolved.get("source_span"))),
            ("证据关系", relation_label),
            ("检索来源", _display_text(resolved.get("retrieval_source"))),
            ("检索路径", _format_string_list(resolved.get("matched_queries") or resolved.get("matched_sources"))),
            ("重排分", _format_score(resolved.get("rerank_score"))),
        ],
        notes=[
            f'章节：{_display_text(resolved.get("section_title"))}',
            f'上下文模式：{_display_text(resolved.get("context_mode"))}',
            f'关系说明：{_display_text(resolved.get("relation_reason"))}',
        ],
        tone=_get_evidence_relation_tone(resolved.get("evidence_relation")),
        badge_text=relation_label,
    )
    content_text = _display_text(resolved.get("content_preview"))
    return (
        f"{metadata_html}"
        f"""
        <div style="border:1px solid var(--border-color-primary);background:var(--body-background-fill);border-radius:16px;padding:16px 18px;margin:0 0 12px 0;max-width:100%;overflow:hidden;">
            <div style="font-size:16px;font-weight:700;color:var(--body-text-color);margin:0 0 8px 0;">原文内容</div>
            <div style="font-size:14px;line-height:1.8;color:var(--body-text-color);white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;max-width:100%;overflow:hidden;">{escape(content_text)}</div>
        </div>
        """
    )


def format_evidence_detail_markdown(evidence: dict | None) -> str:
    """将单条证据详情转换为 Markdown 文本。"""

    resolved = evidence or {}
    if not resolved:
        return "#### 当前证据详情\n- 当前状态：未选择证据"
    return "\n".join(
        [
            "#### 当前证据详情",
            f'- 片段 ID：{_display_text(resolved.get("chunk_id"))}',
            f'- 文档：{_display_text(resolved.get("doc_title") or resolved.get("doc_uid"))}',
            f'- 定位：{_display_text(resolved.get("source_span"))}',
            f'- 证据关系：{_format_evidence_relation_label(resolved.get("evidence_relation"))}',
            f'- 检索来源：{_display_text(resolved.get("retrieval_source"))}',
            f'- 检索路径：{_format_string_list(resolved.get("matched_queries") or resolved.get("matched_sources"))}',
            f'- 重排分：{_format_score(resolved.get("rerank_score"))}',
            f'- 章节：{_display_text(resolved.get("section_title"))}',
            f'- 上下文模式：{_display_text(resolved.get("context_mode"))}',
            f'- 关系说明：{_display_text(resolved.get("relation_reason"))}',
            "",
            "#### 原文内容",
            _display_text(resolved.get("content_preview")),
        ]
    )


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
        pending_claim_count = sum(
            1
            for claim in claims
            if str(claim.get("review_status") or "pending").lower() == "pending"
        )
        formatted.append(
            {
                "check_id": item.get("check_id"),
                "overall_verdict": item.get("overall_verdict"),
                "template_name": item.get("template_name"),
                "input_text": item.get("input_text"),
                "created_at": item.get("created_at"),
                "pending_claim_count": pending_claim_count,
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
            _format_verdict_label(item.get("overall_verdict")),
            str(len(item.get("claims") or [])),
            str(item.get("pending_claim_count", 0)),
            _format_display_datetime(item.get("created_at")),
            _truncate_text(item.get("input_text")),
        ]
        for item in rows
    ]


def build_claim_choice(claim: dict) -> str:
    """构建 claim 下拉选项。"""

    return (
        f'{claim["claim_id"]} | {_format_verdict_label(claim.get("verdict", ""))} | '
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


def format_review_candidates(candidate_items: list[dict]) -> dict:
    """将可审核 Claim 列表转换为更适合人工审核页展示的结构。"""

    items = [
        {
            "claim_id": item.get("claim_id"),
            "check_id": item.get("check_id"),
            "claim_text": item.get("claim_text", ""),
            "verdict": item.get("verdict"),
            "risk_level": item.get("risk_level"),
            "confidence": item.get("confidence"),
            "evidence_judgement": item.get("evidence_judgement", "insufficient"),
            "review_status": item.get("review_status", "pending"),
            "source_doc": item.get("source_doc"),
            "source_span": item.get("source_span"),
            "evidence": item.get("evidence", ""),
            "template_name": item.get("template_name", ""),
            "check_created_at": item.get("check_created_at") or item.get("created_at"),
        }
        for item in candidate_items
        if item.get("claim_id")
    ]
    claim_detail_map = build_claim_detail_map(candidate_items)
    return {
        "count": len(items),
        "items": items,
        "claim_detail_map": claim_detail_map,
    }


def build_review_candidate_rows(formatted: dict | None) -> list[list[str]]:
    """将可审核 Claim 转换为表格行。"""

    items = (formatted or {}).get("items") or []
    return [
        [
            _display_text(item.get("claim_id")),
            _truncate_text(item.get("claim_text")),
            _format_verdict_label(item.get("verdict")),
            _format_risk_level_label(item.get("risk_level")),
            _format_review_status_label(item.get("review_status")),
            _display_text(item.get("source_doc")),
            _display_text(item.get("template_name")),
            _format_display_datetime(item.get("check_created_at")),
        ]
        for item in items
    ]


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
            _format_review_action_label(item.get("review_action")),
            _format_review_status_label(item.get("review_status")),
            _display_text(item.get("reviewer")),
            _format_display_datetime(item.get("created_at")),
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


def get_review_record_detail(review_choice: str, review_map: dict | None) -> dict:
    """从审核记录中提取详情。"""

    review_id = parse_review_choice(review_choice)
    if not review_id or not review_map:
        return {}
    return review_map.get(review_id, {})


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


def _format_display_datetime(value: object) -> str:
    """将时间统一格式化为东八区友好展示文本。"""

    if value in (None, ""):
        return "-"
    text = str(value).strip()
    if not text:
        return "-"
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    localized = parsed.astimezone(CN_TIMEZONE)
    return localized.strftime("%y-%m-%d %H:%M")


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


def _format_retrieval_policy_summary(policy: dict) -> str:
    """将模板检索策略压缩为简短摘要。"""

    if not policy:
        return "-"
    rerank_text = "启用重排" if policy.get("use_rerank") else "不重排"
    return (
        f'全文 {policy.get("fulltext_top_k", "-")} / '
        f'向量 {policy.get("vector_top_k", "-")} / '
        f'最终 {policy.get("final_top_k", "-")} / {rerank_text}'
    )


def _format_context_strategy_summary(policy: dict) -> str:
    """将上下文扩展策略转换为可读文本。"""

    if not policy:
        return "-"
    return (
        f'邻居窗口 {policy.get("neighbor_window", 0)}，'
        f'{"含章节上下文" if policy.get("include_section_context") else "仅当前片段"}，'
        f'最长 {policy.get("section_max_chars", "-")} 字'
    )


def _format_quality_progress_stage(stage: object) -> str:
    """将执行阶段转换为用户可读文本。"""

    mapping = {
        "prepare": "准备输入",
        "template": "加载模板",
        "rules": "规则匹配",
        "retrieval": "检索证据",
        "context": "整理上下文",
        "model": "调用模型",
        "persist": "写入结果",
    }
    return mapping.get(str(stage or ""), _display_text(stage))


def _format_quality_progress_status(status: object) -> str:
    """将执行状态转换为用户可读文本。"""

    mapping = {
        "running": "执行中",
        "success": "已完成",
        "error": "执行失败",
    }
    return mapping.get(str(status or ""), _display_text(status) or "未开始")


def _format_risk_level_label(level: object) -> str:
    """将风险等级转换为中文展示。"""

    mapping = {
        "low": "低级",
        "medium": "中级",
        "high": "高级",
        "critical": "严重",
    }
    return mapping.get(str(level or "").lower(), _display_text(level))


def _format_verdict_label(verdict: object) -> str:
    """将判定结果转换为中文展示。"""

    mapping = {
        "verified": "通过",
        "passed": "通过",
        "approved": "通过",
        "rejected": "不通过",
        "needs_review": "需复核",
        "pending": "待处理",
        "updated": "已更新",
    }
    return mapping.get(str(verdict or "").lower(), _display_text(verdict))


def _format_review_action_label(action: object) -> str:
    """将审核动作转换为中文展示。"""

    mapping = {
        "approved": "通过",
        "rejected": "不通过",
        "updated": "更新结论",
    }
    return mapping.get(str(action or "").lower(), _display_text(action))


def _format_review_status_label(status: object) -> str:
    """将审核状态转换为中文展示。"""

    mapping = {
        "pending": "待处理",
        "approved": "已通过",
        "rejected": "已驳回",
        "updated": "已更新",
    }
    return mapping.get(str(status or "").lower(), _display_text(status))


def _map_quality_tone(level: object) -> str:
    """将质检等级映射为面板语义色。"""

    mapping = {
        "success": "success",
        "warning": "warning",
        "danger": "danger",
        "error": "danger",
    }
    return mapping.get(str(level or "").lower(), "neutral")


def _build_panel_html(
    *,
    title: str,
    description: str,
    cards: list[tuple[str, str]],
    notes: list[str] | None = None,
    footer_html: str | None = None,
    tone: str = "neutral",
    min_height_px: int = 0,
    badge_text: str = "状态模块",
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
    footer_section_html = ""
    if footer_html:
        footer_section_html = f"""
        <div style="margin-top:14px;font-size:13px;line-height:1.7;color:{palette['text']};">
            {footer_html}
        </div>
        """
    return f"""
    <div style="border:1px solid {palette['border']};background:{palette['panel_bg']};border-radius:16px;padding:16px 18px;margin:0 0 12px 0;box-shadow:none;{min_height_style}">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;">
            <div>
                <div style="font-size:16px;font-weight:700;color:{palette['title']};margin:0 0 6px 0;">{escape(title)}</div>
                <div style="font-size:13px;line-height:1.7;color:{palette['text']};">{escape(description)}</div>
            </div>
            <div style="padding:4px 10px;border-radius:999px;background:{palette['badge_bg']};color:{palette['badge_text']};font-size:12px;font-weight:600;">
                {escape(badge_text)}
            </div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-top:14px;">
            {card_html}
        </div>
        {notes_html}
        {footer_section_html}
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


def _format_evidence_relation_label(value: object) -> str:
    """格式化证据关系标签。"""

    mapping = {
        "support": "支持",
        "contradict": "矛盾",
        "insufficient": "证据不足",
    }
    return mapping.get(str(value or "").lower(), _display_text(value))


def _get_evidence_relation_tone(value: object) -> str:
    """根据证据关系返回展示色。"""

    mapping = {
        "support": "success",
        "contradict": "danger",
        "insufficient": "warning",
    }
    return mapping.get(str(value or "").lower(), "neutral")


def _format_string_list(value: object) -> str:
    """将字符串列表格式化为更适合 UI 展示的文本。"""

    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "、".join(items) if items else "-"
    return _display_text(value)
