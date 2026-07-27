"""程序说明：编排 PageIndex Question Plan、证据分类和最终回答生成。"""

from __future__ import annotations

import ast
import json
from typing import Any, cast

from src.pageindex.evidence_judge import classify_evidence_relation, infer_conclusion
from src.pageindex.question_plan import build_question_plan_prompts, normalize_question_plan
from src.pageindex.routing import PageIndexBudget, RetrievalBudgetExceededError
from src.pageindex.templates import PageIndexTemplateService


class PageIndexAnswerOrchestrator:
    """把已检索证据转换为可追踪的最终回答。"""

    def __init__(self, template_service: PageIndexTemplateService) -> None:
        """复用现有 PageIndex 模板事实源。"""

        self.template_service = template_service

    @staticmethod
    def normalize_answer(value: object) -> str:
        """统一模型答案格式，避免结构化 dict 被 ``str()`` 成 Python repr。"""

        payload = _coerce_structured_answer(value)
        if payload is not None:
            return _render_structured_answer(payload)
        return str(value or "").strip()

    def build_question_plan(
        self,
        llm_client: object,
        question: str,
        evidence: list[dict],
        *,
        budget: PageIndexBudget | None = None,
    ) -> dict:
        """调用 LLM 生成 Question Plan，失败时返回结构化保守计划。"""

        system_prompt, user_prompt = build_question_plan_prompts(question, evidence)
        try:
            if budget is not None:
                budget.consume_llm("question_plan")
            payload = cast(Any, llm_client).complete_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except RetrievalBudgetExceededError:
            raise
        except Exception:  # noqa: BLE001
            payload = {}
        return normalize_question_plan(payload, question)

    @staticmethod
    def classify_evidence_items(question: str, evidence: list[dict]) -> list[dict]:
        """为证据标注支持、反驳、背景、条件或不足等关系。"""

        return [classify_evidence_relation(question, dict(item)) for item in evidence]

    def build_local_answer(
        self,
        question: str,
        evidence: list[dict],
        *,
        question_plan: dict | None = None,
    ) -> str:
        """基于当前证据生成带判断边界的本地回答。"""

        if not evidence:
            return "\n\n".join(
                [
                    f"结论：证据不足，不能回答“{question}”。",
                    "依据：未在当前知识库的 PageIndex 结构或原文片段中找到直接相关证据。",
                    "来源：无。",
                    "不确定点：需要补充相关文档或重新构建索引后再判断。",
                ]
            )
        if any(not item.get("evidence_type") for item in evidence):
            evidence = self.classify_evidence_items(question, evidence)
        plan = question_plan if isinstance(question_plan, dict) else {}
        question_type = str(plan.get("question_type") or "").strip()
        if question_type in {"information_extraction", "summary", "comparison"} or plan.get("needs_evidence_relation") is False:
            target = str(plan.get("target") or question).strip()
            return "\n\n".join(
                [
                    f"结论：当前证据可提取“{target}”相关内容。",
                    f"要点：{_build_local_evidence_points(evidence)}",
                    f"来源：{_build_local_source_points(evidence)}",
                    f"不确定点：{_infer_local_uncertainty(evidence)}",
                ]
            ).strip()
        return "\n\n".join(
            [
                f"结论：{infer_conclusion(question, evidence)}",
                f"证据判断：{_build_local_evidence_judgement(evidence)}",
                f"依据：{_build_local_evidence_points(evidence)}",
                f"来源：{_build_local_source_points(evidence)}",
                f"不确定点：{_infer_local_uncertainty(evidence)}",
            ]
        ).strip()

    def generate_llm_answer_payload(
        self,
        llm_client: object,
        question: str,
        evidence: list[dict],
        *,
        template_id: str | None = None,
        question_plan: dict | None = None,
        budget: PageIndexBudget | None = None,
    ) -> dict:
        """按既有模板和预算生成最终回答及 Question Plan。"""

        template = self.template_service.get_template(template_id)
        resolved_question_plan = question_plan or self.build_question_plan(
            llm_client,
            question,
            evidence,
            budget=budget,
        )
        system_prompt, user_prompt = self.template_service.render_answer_prompts(
            template,
            question=question,
            # 树节点正文可能是整段长文；最终回答只需有限上下文和可引用字段，
            # 过长请求会触发在线模型上下文/超时失败并退化为不完整答案。
            evidence=_compact_evidence_for_prompt(evidence),
            question_plan=resolved_question_plan,
            structure_context=_build_answer_structure_context(evidence),
            evidence_judgement=_build_local_evidence_judgement(evidence),
            citation_rules="必须列出证据标题、位置、文档或 chunk 来源。",
        )
        if budget is not None:
            budget.consume_llm("final_answer")
        result = cast(Any, llm_client).complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        answer_value = result.get("answer") if isinstance(result, dict) else ""
        return {
            "answer": self.normalize_answer(answer_value),
            "question_plan": resolved_question_plan,
        }


def _coerce_structured_answer(value: object) -> dict | None:
    """兼容 JSON dict、Python dict 字符串和外层 answer 包装。"""

    payload: object = value
    if isinstance(payload, str):
        text = payload.strip()
        if not (text.startswith("{") and text.endswith("}")):
            return None
        payload = None
        for parser in (json.loads, ast.literal_eval):
            try:
                candidate = parser(text)
            except (ValueError, SyntaxError, TypeError):
                continue
            if isinstance(candidate, dict):
                payload = candidate
                break
        if payload is None:
            return None
    if not isinstance(payload, dict):
        return None
    if set(payload) == {"answer"}:
        nested = _coerce_structured_answer(payload.get("answer"))
        if nested is not None:
            return nested
    return payload


def _render_structured_answer(payload: dict) -> str:
    """将结构化答案渲染成稳定、可读的 Markdown。"""

    if not payload:
        return ""
    ordered_keys = (
        "结论",
        "审查结论",
        "证据判断",
        "证据能说明什么",
        "证据能证明什么",
        "证据不能证明什么",
        "不能外推的原因",
        "风险或人群边界",
        "依据",
        "来源",
        "要点",
        "不确定点",
        "非医疗建议",
    )
    keys = [key for key in ordered_keys if key in payload]
    keys.extend(key for key in payload if key not in keys)
    lines: list[str] = []
    for key in keys:
        label = str(key).strip()
        if not label:
            continue
        lines.extend([f"#### {label}", ""])
        lines.extend(_render_answer_value(payload.get(key)))
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()


def _render_answer_value(value: object) -> list[str]:
    """渲染列表、嵌套对象和普通文本，保留证据审查的层级。"""

    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"- **{key}**：")
                lines.extend(f"  {line}" for line in _render_answer_value(item))
            else:
                lines.append(f"- **{key}**：{_stringify_answer_scalar(item)}")
        return lines or ["- 无"]
    if isinstance(value, (list, tuple)):
        lines = []
        for item in value:
            if isinstance(item, dict):
                nested = _render_answer_value(item)
                if nested:
                    lines.append(nested[0].removeprefix("- "))
                    lines.extend(f"  {line}" for line in nested[1:])
            elif isinstance(item, (list, tuple)):
                lines.extend(f"- {line}" for line in _render_answer_value(item))
            else:
                text = _stringify_answer_scalar(item)
                if text:
                    lines.append(f"- {text}")
        return lines or ["- 无"]
    text = str(value or "").strip()
    return text.splitlines() if text else ["无"]


def _stringify_answer_scalar(value: object) -> str:
    """将标量转成不带 Python repr 的展示文本。"""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value).strip()


def _build_answer_structure_context(evidence: list[dict]) -> str:
    """基于证据生成简短结构上下文。"""

    contexts: list[str] = []
    for item in evidence[:5]:
        title = str(item.get("title") or item.get("source_type") or "").strip()
        position = str(item.get("source_anchor") or item.get("position") or "").strip()
        doc_uid = str(item.get("doc_uid") or "").strip()
        if not title and not position:
            continue
        contexts.append(" > ".join(part for part in (doc_uid, title, position) if part))
    return "\n".join(contexts)


def _compact_evidence_for_prompt(evidence: list[dict], *, max_items: int = 8, max_text: int = 1200) -> list[dict]:
    """限制最终回答 Prompt 的证据体积，保留来源和定位字段。"""

    compact: list[dict] = []
    for raw_item in evidence[:max_items]:
        item = dict(raw_item)
        for field in ("content", "summary", "content_preview", "reason"):
            if field in item and item[field] is not None:
                text = str(item[field])
                item[field] = text[:max_text].rstrip() + ("..." if len(text) > max_text else "")
        compact.append(item)
    return compact


def _build_local_evidence_judgement(evidence: list[dict]) -> str:
    """汇总证据类型，帮助用户理解结论为何保守。"""

    labels = [
        f"{str(item.get('evidence_label') or '未分类')}：{str(item.get('title') or item.get('source_type') or '证据')}"
        for item in evidence[:4]
    ]
    return "；".join(labels) if labels else "未找到可判断证据。"


def _build_local_evidence_points(evidence: list[dict]) -> str:
    """提炼本地证据要点，避免把命中位置当作回答。"""

    points: list[str] = []
    for item in evidence[:4]:
        content = str(item.get("content") or item.get("summary") or "").strip()
        if not content:
            continue
        points.append(content[:180].rstrip() + "..." if len(content) > 180 else content)
    return "；".join(points) if points else "当前证据只有命中位置，缺少可判断的正文内容。"


def _build_local_source_points(evidence: list[dict]) -> str:
    """格式化本地证据来源。"""

    sources: list[str] = []
    for item in evidence[:4]:
        title = str(item.get("title") or item.get("source_type") or "证据").strip()
        position = str(item.get("source_anchor") or item.get("position") or "").strip()
        doc_uid = str(item.get("doc_uid") or "").strip()
        label = f"{title}（{position}）" if position else title
        sources.append(f"{label}，文档：{doc_uid}" if doc_uid else label)
    return "；".join(sources) if sources else "无。"


def _infer_local_uncertainty(evidence: list[dict]) -> str:
    """说明本地降级答案的判断边界。"""

    joined_evidence = "\n".join(
        str(item.get("content") or item.get("summary") or "") for item in evidence
    )
    if any(marker in joined_evidence for marker in ("医师指导", "辨证", "不良反应", "禁忌", "注意")):
        return "现有证据没有提供针对具体疾病人群的明确疗效结论，且涉及用药指导或禁忌，不能替代医生判断。"
    return "本地降级回答只基于当前命中的文档证据，未做外部医学事实补充。"
