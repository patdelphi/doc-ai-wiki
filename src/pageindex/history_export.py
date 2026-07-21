"""程序说明：解析 PageIndex 历史数据库行并格式化 Markdown 导出内容。"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence


def parse_history_rows(rows: Sequence[Mapping[str, object]]) -> list[dict]:
    """将 PageIndex 历史查询行转换为规范化字典。"""

    items: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            evidence = json.loads(str(item.pop("evidence_json") or "[]"))
        except json.JSONDecodeError:
            evidence = []
        try:
            debug = json.loads(str(item.pop("debug_json", "{}") or "{}"))
        except json.JSONDecodeError:
            debug = {}
        item["evidence"] = evidence if isinstance(evidence, list) else []
        item["debug"] = debug if isinstance(debug, dict) else {}
        items.append(item)
    return items


def format_history_markdown(*, knowledge_base_id: str, doc_uid: str, history: list[dict]) -> str:
    """格式化 PageIndex 历史导出内容，供全量与单条导出复用。"""

    lines = [
        "# PageIndex 深度检索导出",
        "",
        f"- 知识库：{knowledge_base_id}",
        f"- 文档：{doc_uid}",
        "",
    ]
    for index, item in enumerate(history, start=1):
        lines.extend(
            [
                f"## 记录 {index}",
                "",
                f"- 时间：{item.get('created_at', '')}",
                f"- 问题：{item.get('question', '')}",
                "",
                "### 回答",
                "",
            ]
        )
        lines.extend(_format_history_answer_markdown(str(item.get("answer") or "")))
        lines.extend(
            [
                "",
                "### 调试信息",
                "",
                f"- 问题类型：{_history_question_type(item)}",
                "",
                "### 证据",
                "",
            ]
        )
        evidence_items = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        if not evidence_items:
            lines.extend(["- 暂无证据", ""])
            continue
        for evidence in evidence_items:
            lines.extend(
                [
                    f"#### {evidence.get('title', '')}",
                    "",
                    f"- 位置：{evidence.get('position', '')}",
                    "",
                    str(evidence.get("content") or evidence.get("summary") or ""),
                    "",
                ]
            )
    return "\n".join(lines).strip()


def _format_history_answer_markdown(answer: str) -> list[str]:
    """将历史答案格式化为 Markdown；兼容 LLM 返回的 dict 字符串。"""

    normalized_answer = str(answer or "").strip()
    structured_answer = _parse_structured_answer(normalized_answer)
    if not structured_answer:
        return [normalized_answer] if normalized_answer else ["暂无回答"]

    ordered_keys = ["结论", "证据判断", "依据", "来源", "不确定点"]
    lines: list[str] = []
    for key in ordered_keys:
        if key not in structured_answer:
            continue
        lines.extend([f"#### {key}", ""])
        lines.extend(_format_markdown_value(structured_answer.get(key)))
        lines.append("")
    for key in (key for key in structured_answer if key not in ordered_keys):
        lines.extend([f"#### {key}", ""])
        lines.extend(_format_markdown_value(structured_answer.get(key)))
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines or ["暂无回答"]


def _parse_structured_answer(answer: str) -> dict | None:
    """解析 JSON 或 Python dict 字符串答案；失败时返回 None 保持原文。"""

    text = str(answer or "").strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            payload = parser(text)
        except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _format_markdown_value(value: object) -> list[str]:
    """将结构化字段值转换成 Markdown 段落或列表。"""

    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            lines.extend(_format_markdown_list_item(item))
        return lines or ["- 无"]
    if isinstance(value, dict):
        return [f"- **{key}**：{_stringify_markdown_scalar(item)}" for key, item in value.items()] or ["- 无"]
    text = str(value or "").strip()
    return text.splitlines() if text else ["无"]


def _format_markdown_list_item(item: object) -> list[str]:
    """将列表项转换为 Markdown，支持列表中嵌套 dict。"""

    if isinstance(item, dict):
        return [
            f"{'- ' if index == 0 else '  '}**{key}**：{_stringify_markdown_scalar(value)}"
            for index, (key, value) in enumerate(item.items())
        ]
    if isinstance(item, list):
        return [f"- {_stringify_markdown_scalar(value)}" for value in item]
    text = str(item or "").strip()
    return [f"- {text}"] if text else []


def _stringify_markdown_scalar(value: object) -> str:
    """把嵌套标量转换为 Markdown 友好的字符串。"""

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "").strip()


def _history_question_type(item: dict) -> str:
    """从历史 debug 中读取 Question Plan 类型，供导出排查使用。"""

    raw_debug = item.get("debug")
    debug = raw_debug if isinstance(raw_debug, dict) else {}
    raw_question_plan = debug.get("question_plan")
    question_plan = raw_question_plan if isinstance(raw_question_plan, dict) else {}
    return str(question_plan.get("question_type") or "unknown")
