"""程序说明：编排 PageIndex Question Plan、证据分类和最终回答生成。"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, cast

from src.pageindex.evidence_judge import classify_evidence_relation, infer_conclusion
from src.pageindex.question_plan import build_question_plan_prompts, normalize_question_plan
from src.pageindex.routing import PageIndexBudget, RetrievalBudgetExceededError
from src.pageindex.templates import PageIndexTemplateService


_ANSWER_CONTRACT_SECTIONS = {
    "general_summary": ("直接概览", "主要要点", "来源", "不确定点"),
    "balanced_qa": ("结论", "证据能说明什么", "依据", "来源", "不确定点"),
    "strict_qa": ("结论", "证据判断", "依据", "来源", "不确定点"),
    "evidence_audit": (
        "审查结论",
        "证据能证明什么",
        "证据不能证明什么",
        "不能外推的原因",
        "来源",
        "不确定点",
    ),
    "medical_safety": (
        "结论",
        "证据能说明什么",
        "证据不能证明什么",
        "风险或人群边界",
        "依据",
        "来源",
        "不确定点",
        "非医疗建议",
    ),
    "source_locator": ("定位结果", "来源"),
}
_EXTERNAL_KNOWLEDGE_MARKERS = (
    "一般医学常识",
    "一般营养学常识",
    "基于医学常识",
    "基于营养学常识",
    "根据医学常识",
    "根据营养学常识",
    "食品科学常识",
    "基于食品科学",
    "根据食品科学",
    "医学上任何",
    "常见的食物过敏原",
    "常识",
    "众所周知",
)
_STRONG_MEDICAL_CLAIM_MARKERS = (
    "严禁",
    "绝对禁忌",
    "高升糖",
    "导致血糖",
    "血糖波动",
    "严重的过敏风险",
    "常见坚果过敏原",
    "不适合长期",
    "对任何人群均不推荐",
    "高热量",
    "代谢负担",
)
_LOCAL_RELEVANCE_MARKERS = (
    "阿胶糕",
    "配料",
    "糖尿病",
    "坚果",
    "过敏",
    "长期",
    "不限量",
    "剂量",
    "大剂量",
    "不良反应",
    "禁忌",
    "治疗",
    "贫血",
    "临床",
    "传统",
    "用法",
    "烊化",
    "配伍",
    "产地",
    "唯一",
    "企业",
)
_MEDICAL_BOUNDARY_MARKERS = (
    "医师指导",
    "医生指导",
    "不良反应",
    "禁忌",
    "不宜",
    "慎用",
    "过敏",
    "副作用",
)


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
        answer = self.normalize_answer(answer_value)
        mode = str(template.get("answer_mode") or "").strip()
        external_knowledge_markers = _find_external_knowledge_markers(answer)
        if mode == "medical_safety":
            external_knowledge_markers.extend(
                _find_unsupported_medical_claim_markers(answer, evidence)
            )
        external_knowledge_markers = list(dict.fromkeys(external_knowledge_markers))
        if external_knowledge_markers:
            if mode == "medical_safety":
                answer = _build_medical_safety_local_answer(question, evidence)
            else:
                answer = self.build_local_answer(
                    question,
                    evidence,
                    question_plan=resolved_question_plan,
                )
            answer, answer_contract = _ensure_answer_contract(
                answer,
                raw_value=answer,
                template=template,
                evidence=evidence,
            )
            if answer_contract is not None:
                answer_contract["degraded_reason"] = "unsupported_external_knowledge"
                answer_contract["external_knowledge_markers"] = external_knowledge_markers
        else:
            answer, answer_contract = _ensure_answer_contract(
                answer,
                raw_value=answer_value,
                template=template,
                evidence=evidence,
            )
        payload = {
            "answer": answer,
            "question_plan": resolved_question_plan,
        }
        if answer_contract is not None:
            payload["answer_contract"] = answer_contract
        return payload


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


def _ensure_answer_contract(
    answer: str,
    *,
    raw_value: object,
    template: dict,
    evidence: list[dict],
) -> tuple[str, dict | None]:
    """按内置回答模式补齐必要章节，补全部分只使用当前证据。"""

    mode = str(template.get("answer_mode") or "").strip()
    required_sections = _ANSWER_CONTRACT_SECTIONS.get(mode)
    if not required_sections:
        return answer, None

    structured_payload = _coerce_structured_answer(raw_value)
    present_sections = (
        {str(key).strip() for key in structured_payload if str(key).strip()}
        if structured_payload is not None
        else set()
    )
    if structured_payload is None:
        present_sections = {
            section
            for section in required_sections
            if _answer_contains_section(answer, section)
        }
    missing_sections = [
        section for section in required_sections if section not in present_sections
    ]
    if not missing_sections:
        return answer, {
            "mode": mode,
            "required_sections": list(required_sections),
            "missing_sections": [],
            "repaired": False,
        }

    repaired_parts: list[str] = []
    remaining_missing = list(missing_sections)
    if not present_sections:
        first_section = required_sections[0]
        repaired_parts.extend(
            [
                f"#### {first_section}",
                "",
                answer or "当前证据不足，不能形成可靠结论。",
            ]
        )
        remaining_missing = [
            section for section in remaining_missing if section != first_section
        ]
    elif answer:
        repaired_parts.append(answer)

    for section in remaining_missing:
        repaired_parts.extend(
            [
                "",
                f"#### {section}",
                "",
                _build_contract_section(section, evidence),
            ]
        )
    return "\n".join(repaired_parts).strip(), {
        "mode": mode,
        "required_sections": list(required_sections),
        "missing_sections": missing_sections,
        "repaired": True,
    }


def _answer_contains_section(answer: str, section: str) -> bool:
    """识别 Markdown 标题或“章节：内容”形式的已有答案章节。"""

    pattern = rf"(?:^|\n)\s*(?:#{{1,6}}\s*)?{re.escape(section)}\s*(?:[：:]|$)"
    return re.search(pattern, str(answer or ""), flags=re.MULTILINE) is not None


def _find_external_knowledge_markers(answer: str) -> list[str]:
    """识别模型主动声明使用知识库外常识的情况。"""

    matches = [
        marker
        for marker in _EXTERNAL_KNOWLEDGE_MARKERS
        if marker in str(answer or "")
    ]
    return [
        marker
        for marker in matches
        if not any(marker != other and marker in other for other in matches)
    ]


def _find_unsupported_medical_claim_markers(answer: str, evidence: list[dict]) -> list[str]:
    """识别回答中未在证据原文出现的强医疗结论。"""

    evidence_text = "\n".join(
        str(item.get("content") or item.get("summary") or "")
        for item in evidence
    )
    return [
        marker
        for marker in _STRONG_MEDICAL_CLAIM_MARKERS
        if marker in answer and marker not in evidence_text
    ]


def _build_medical_safety_local_answer(question: str, evidence: list[dict]) -> str:
    """为医学安全模板生成简洁、仅基于库内证据的降级答案。"""

    classified = (
        [classify_evidence_relation(question, dict(item)) for item in evidence]
        if any(not item.get("evidence_type") for item in evidence)
        else [dict(item) for item in evidence]
    )
    selected = _select_local_evidence(question, classified, medical_safety=True)
    boundaries = _describe_question_boundaries(question)
    boundary_text = "、".join(boundaries)
    evidence_points = _build_local_evidence_point_list(question, selected)
    safety_point = _find_medical_boundary_point(selected)
    fact_scope = "部分配料事实" if "配料" in question else "部分相关事实"
    conclusion = f"当前知识库可确认{fact_scope}"
    if boundary_text:
        conclusion += f"，但未直接覆盖{boundary_text}"
    conclusion += "，不能据此认定问题中的完整安全性或适用性结论。"
    cannot_prove = (
        f"现有材料不能证明{boundary_text}条件下的安全性或适用性。"
        if boundary_text
        else "现有材料不能证明超出原文人群、剂量、疗程或用途范围的安全性。"
    )
    payload = {
        "结论": conclusion,
        "证据能说明什么": evidence_points or ["当前知识库仅提供了有限的相关事实。"],
        "证据不能证明什么": cannot_prove,
        "风险或人群边界": safety_point
        or "当前证据未充分覆盖具体疾病、人群、剂量、疗程及联合用药边界。",
        "依据": _build_local_evidence_judgement(selected),
        "来源": _build_local_source_points(selected),
        "不确定点": (
            f"仍缺少直接覆盖{boundary_text}的材料。"
            if boundary_text
            else _infer_local_uncertainty(selected)
        ),
        "非医疗建议": "以上仅为当前知识库证据整理，不能替代医生诊断或治疗建议。",
    }
    return _render_structured_answer(payload)


def _select_local_evidence(
    question: str,
    evidence: list[dict],
    *,
    medical_safety: bool = False,
    max_items: int = 3,
) -> list[dict]:
    """优先选择与问题直接相关且非纯背景的证据，并去除重复片段。"""

    question_markers = [marker for marker in _LOCAL_RELEVANCE_MARKERS if marker in question]
    requires_product_ingredient_evidence = "阿胶糕" in question and "配料" in question
    scored: list[tuple[int, int, dict]] = []
    seen_content: set[str] = set()
    for index, raw_item in enumerate(evidence):
        item = dict(raw_item)
        content = str(item.get("content") or item.get("summary") or "").strip()
        content_without_heading = re.sub(r"^\s*#+[^\n]*\n+", "", content)
        content_key = re.sub(r"\s+", "", content_without_heading)[:160]
        if content_key and content_key in seen_content:
            continue
        if content_key:
            seen_content.add(content_key)
        evidence_type = str(item.get("evidence_type") or "")
        searchable = "\n".join(
            (
                str(item.get("title") or ""),
                content,
            )
        )
        score = {
            "direct_support": 8,
            "partial_support": 4,
            "method_or_formula_context": 3,
            "counter_evidence": 5,
            "context_only": 0,
        }.get(evidence_type, 1)
        score += 3 * sum(1 for marker in question_markers if marker in searchable)
        has_medical_boundary = medical_safety and any(
            marker in searchable for marker in _MEDICAL_BOUNDARY_MARKERS
        )
        if has_medical_boundary:
            score += 5
        if requires_product_ingredient_evidence:
            has_product_ingredients = (
                "配料表" in content
                or (
                    "阿胶糕" in searchable
                    and any(marker in content for marker in ("黑芝麻", "核桃", "冰糖", "麦芽糖"))
                )
            )
            if not has_product_ingredients and not has_medical_boundary:
                continue
        if score >= 4:
            scored.append((score, -index, item))
    if not scored:
        return [dict(item) for item in evidence[:max_items]]
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [item for _, _, item in scored[:max_items]]


def _build_local_evidence_point_list(question: str, evidence: list[dict]) -> list[str]:
    """从每条已筛选证据中提取最相关句子，避免整段复制和问题复述。"""

    points: list[str] = []
    for item in evidence:
        point = _extract_best_evidence_excerpt(question, item)
        if point and point not in points:
            points.append(point)
    return points


def _extract_best_evidence_excerpt(question: str, evidence: dict) -> str:
    """按问题词和安全边界词选取单条证据中的最佳句子。"""

    content = str(evidence.get("content") or evidence.get("summary") or "").strip()
    if not content:
        return ""
    content = re.sub(r"(?m)^\s*#+[^\n]*$", "", content)
    markers = [marker for marker in _LOCAL_RELEVANCE_MARKERS if marker in question]
    ingredient_markers = (
        ("黑芝麻", "核桃", "冰糖", "麦芽糖", "黄酒", "蜜饯", "阿胶")
        if "配料" in question
        else ()
    )
    segments = [
        re.sub(r"\s+", " ", segment).strip(" #")
        for segment in re.split(r"[\n。；]+", content)
        if len(re.sub(r"\s+", "", segment)) >= 6
    ]
    if not segments:
        segments = [re.sub(r"\s+", " ", content).strip()]
    best = max(
        enumerate(segments),
        key=lambda row: (
            3 * sum(1 for marker in markers if marker in row[1])
            + 2 * sum(1 for marker in _MEDICAL_BOUNDARY_MARKERS if marker in row[1])
            + 8 * int("配料表" in row[1])
            + 2 * sum(1 for marker in ingredient_markers if marker in row[1]),
            -row[0],
        ),
    )[1]
    return best[:220].rstrip() + ("..." if len(best) > 220 else "")


def _find_medical_boundary_point(evidence: list[dict]) -> str:
    """从证据中抽取医师指导、禁忌或不良反应等直接边界。"""

    candidates: list[str] = []
    for item in evidence:
        content = str(item.get("content") or item.get("summary") or "")
        for segment in re.split(r"[\n。；]+", content):
            normalized = re.sub(r"\s+", " ", segment).strip(" #")
            if any(marker in normalized for marker in _MEDICAL_BOUNDARY_MARKERS):
                candidates.append(normalized)
    if not candidates:
        return ""
    best = max(candidates, key=lambda text: sum(marker in text for marker in _MEDICAL_BOUNDARY_MARKERS))
    return best[:220].rstrip() + ("..." if len(best) > 220 else "")


def _describe_question_boundaries(question: str) -> list[str]:
    """把问题中需要直接证据覆盖的人群、时间和剂量边界列出来。"""

    boundaries: list[str] = []
    if any(marker in question for marker in ("患者", "人群", "过敏", "儿童", "孕妇", "老人", "老年", "婴幼儿")):
        boundaries.append("特定人群")
    if any(marker in question for marker in ("长期", "持续", "常年")):
        boundaries.append("长期使用")
    if any(marker in question for marker in ("不限量", "大剂量", "剂量", "用量")):
        boundaries.append("剂量上限")
    return boundaries


def _build_contract_section(section: str, evidence: list[dict]) -> str:
    """为缺失章节生成不超出现有证据的确定性内容。"""

    if section in {"主要要点", "证据能说明什么", "证据能证明什么", "依据"}:
        return _build_local_evidence_points(evidence)
    if section == "证据判断":
        return _build_local_evidence_judgement(evidence)
    if section == "来源":
        return _build_local_source_points(evidence)
    if section == "不确定点":
        return _infer_local_uncertainty(evidence)
    if section == "证据不能证明什么":
        return "当前证据不能自动证明超出原文范围的普遍、因果或临床结论。"
    if section == "不能外推的原因":
        return "现有材料的人群、样本、时间、剂量或研究层级可能不完整，不能据此扩大结论范围。"
    if section == "风险或人群边界":
        return "现有证据未充分覆盖具体疾病、人群、剂量、疗程及联合用药边界。"
    if section == "非医疗建议":
        return "以上仅为当前知识库证据整理，不能替代医生诊断或治疗建议。"
    return "当前知识库未提供足够直接证据。"


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
        chunk_id = str(item.get("chunk_id") or "").strip()
        label = f"{title}（{position}）" if position else title
        source_parts = [label]
        if doc_uid:
            source_parts.append(f"文档：{doc_uid}")
        if chunk_id:
            source_parts.append(f"chunk：{chunk_id}")
        sources.append("，".join(source_parts))
    return "；".join(sources) if sources else "无。"


def _infer_local_uncertainty(evidence: list[dict]) -> str:
    """说明本地降级答案的判断边界。"""

    joined_evidence = "\n".join(
        str(item.get("content") or item.get("summary") or "") for item in evidence
    )
    if any(marker in joined_evidence for marker in ("医师指导", "辨证", "不良反应", "禁忌", "注意")):
        return "现有证据没有提供针对具体疾病人群的明确疗效结论，且涉及用药指导或禁忌，不能替代医生判断。"
    return "本地降级回答只基于当前命中的文档证据，未做外部医学事实补充。"
