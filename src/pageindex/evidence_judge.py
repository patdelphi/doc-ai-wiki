"""程序说明：提供 PageIndex 通用命题-证据关系判断与结论策略。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


RELATION_LABELS = {
    "direct_support": "直接支持",
    "direct_refute": "直接反驳",
    "partial_support": "部分支持",
    "context_only": "仅背景相关",
    "example_only": "仅案例",
    "method_or_formula_context": "方法/组合语境",
    "risk_or_condition": "条件或限制",
    "insufficient": "证据不足",
}

DEFAULT_RULES = {
    "markers": {
        "support": [
            "可以",
            "允许",
            "支持",
            "证明",
            "表明",
            "显示",
            "提出",
            "记载",
            "有效",
            "改善",
            "提高",
            "降低",
            "缓解",
            "治疗",
            "导致",
            "提升",
        ],
        "refute": ["不支持", "禁止", "未见", "无证据", "无效", "并非", "不属于"],
        "refute_phrases": ["不能证明", "不能得出", "不能用于", "不能治疗", "不能改善", "不能缓解"],
        "condition": ["必须", "需要", "仅限", "条件", "限制", "例外", "风险", "禁忌", "注意", "前提", "白名单", "安全评审", "取决于"],
        "example": ["案例", "个案", "例如", "某次", "样例", "样本量较小", "试生产"],
        "method_context": [
            "组合方案",
            "优化方案",
            "方案",
            "方法",
            "流程",
            "模型",
            "配方",
            "方剂",
            "方中",
            "含有",
            "联合",
            "组成",
            "采用",
            "配伍",
            "温经汤",
            "炙甘草汤",
            "胶艾汤",
            "黄连阿胶汤",
            "猪苓汤",
        ],
        "single_item_subject": ["模块", "阿胶", "接口", "工艺", "制度", "项目负责人"],
        "partial_effect": ["止痛", "缓解", "改善", "提高", "提升", "治疗", "支持", "允许", "审批", "开放"],
        "claim_term": ["允许", "审批", "预算调整", "提高", "吞吐量", "产量", "提出", "理论", "开放", "缓解", "痛经", "阿胶"],
    },
    "stop_words": ["这个", "该", "是否", "可以", "能够", "能不能", "有没有", "是不是", "什么", "哪些", "如何", "一定"],
    "conclusion_templates": {
        "insufficient": "当前证据不足，不能得出“{claim}”的结论。",
        "direct_refute": "当前证据不支持“{claim}”，并存在直接反驳该命题的证据。",
        "direct_support": "当前证据支持“{claim}”。",
        "direct_support_with_limits": "当前证据支持“{claim}”，但存在条件、限制或只覆盖部分内容，结论需要按证据边界理解。",
        "partial_support": "当前证据只支持“{claim}”的一部分，不能证明“{claim}”完整成立，不能推出完整命题。",
        "method_or_formula_context": "当前证据不能证明“{claim}”；它只能说明组合方案、方法、配方、流程或系统语境相关，不能等同于用户命题本身成立。",
        "example_only": "当前证据只是案例或样例，不能泛化为“{claim}”成立。",
        "risk_or_condition": "当前证据仅说明“{claim}”存在条件或限制，不能直接推出该命题成立。",
    },
}


def load_evidence_judge_rules(templates_dir: Path | str | None = None) -> dict:
    """读取外置 Evidence Judge 规则；缺失时返回内置默认规则。"""

    rules = _merge_rules(DEFAULT_RULES, {})
    if templates_dir is None:
        templates_dir = Path("templates")
    rule_path = Path(templates_dir) / "pageindex" / "evidence_judge.yaml"
    if not rule_path.exists():
        return rules
    payload = yaml.safe_load(rule_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return rules
    return _merge_rules(rules, payload)


def classify_evidence_relation(claim: str, evidence: dict, *, rules: dict | None = None) -> dict:
    """判断单条证据与用户命题的关系。"""

    resolved_rules = rules or load_evidence_judge_rules()
    normalized_claim = _normalize_text(claim)
    content = str(evidence.get("content") or evidence.get("summary") or "")
    title = str(evidence.get("title") or "")
    combined = f"{title}\n{content}".strip()
    normalized_combined = _normalize_text(combined)
    claim_terms = _extract_claim_terms(normalized_claim, resolved_rules)
    matched_terms = [term for term in claim_terms if term and term in normalized_combined]
    relation_type = _classify_relation_type(
        normalized_claim=normalized_claim,
        normalized_content=normalized_combined,
        matched_terms=matched_terms,
        claim_terms=claim_terms,
        rules=resolved_rules,
    )
    return {
        **evidence,
        "claim": normalized_claim,
        "relation_type": relation_type,
        "relation_label": RELATION_LABELS[relation_type],
        "evidence_type": relation_type,
        "evidence_label": RELATION_LABELS[relation_type],
        "relation_reason": _build_relation_reason(relation_type, matched_terms),
    }


def infer_conclusion(claim: str, relations: list[dict], *, rules: dict | None = None) -> str:
    """根据证据关系生成明确结论，避免把相关证据当成答案。"""

    resolved_rules = rules or load_evidence_judge_rules()
    templates = resolved_rules.get("conclusion_templates", {})
    normalized_claim = _normalize_text(claim)
    relation_types = [str(item.get("relation_type") or item.get("evidence_type") or "") for item in relations]
    if not relations or not relation_types:
        return _render_conclusion_template(templates, "insufficient", normalized_claim)
    if "direct_refute" in relation_types:
        return _render_conclusion_template(templates, "direct_refute", normalized_claim)
    if "direct_support" in relation_types:
        if any(item in relation_types for item in ("risk_or_condition", "partial_support")):
            return _render_conclusion_template(templates, "direct_support_with_limits", normalized_claim)
        return _render_conclusion_template(templates, "direct_support", normalized_claim)
    if "partial_support" in relation_types:
        return _render_conclusion_template(templates, "partial_support", normalized_claim)
    if "method_or_formula_context" in relation_types:
        return _render_conclusion_template(templates, "method_or_formula_context", normalized_claim)
    if "example_only" in relation_types:
        return _render_conclusion_template(templates, "example_only", normalized_claim)
    if "risk_or_condition" in relation_types:
        return _render_conclusion_template(templates, "risk_or_condition", normalized_claim)
    return _render_conclusion_template(templates, "insufficient", normalized_claim)


def _classify_relation_type(
    *,
    normalized_claim: str,
    normalized_content: str,
    matched_terms: list[str],
    claim_terms: list[str],
    rules: dict,
) -> str:
    """按通用证据关系优先级分类。"""

    if not normalized_content:
        return "insufficient"
    if _has_refute_marker(normalized_content, rules):
        return "direct_refute" if _has_enough_overlap(matched_terms, claim_terms) else "context_only"
    if _is_example_only(normalized_content, rules):
        return "example_only"
    if _is_method_or_formula_context(normalized_claim, normalized_content, rules):
        if _is_subject_specific_partial_support(normalized_claim, normalized_content, rules):
            return "partial_support"
        return "method_or_formula_context"
    if _has_condition_marker(normalized_content, rules) and not _has_support_marker(normalized_content, rules):
        return "risk_or_condition"
    if _has_condition_marker(normalized_content, rules) and _has_enough_overlap(matched_terms, claim_terms):
        return "risk_or_condition"
    if _has_support_marker(normalized_content, rules) and _has_enough_overlap(matched_terms, claim_terms):
        return "direct_support"
    if matched_terms:
        return "context_only" if len(matched_terms) < max(2, len(claim_terms) // 2) else "partial_support"
    return "insufficient"


def _normalize_text(value: str) -> str:
    """去掉问题末尾语气符和多余空白，保留中文语义。"""

    text = re.sub(r"\s+", "", str(value or "").strip())
    return text.strip("。！？?；;，,")


def _extract_claim_terms(claim: str, rules: dict) -> list[str]:
    """从命题中抽取用于关系判断的核心词，避免只靠整句字面匹配。"""

    compact = _normalize_text(claim)
    stop_words = _get_rule_list(rules, "stop_words")
    cleaned = compact
    for word in stop_words:
        cleaned = cleaned.replace(word, " ")
    raw_terms = [term for term in re.split(r"[\s、，,。；;：:（）()《》“”\"']+", cleaned) if len(term) >= 2]
    terms: list[str] = []
    for term in raw_terms:
        terms.append(term)
        # 针对连续中文短句，补充常见实体和动作片段，提升跨领域召回。
        for marker in _get_marker_list(rules, "claim_term"):
            if marker in term and marker not in terms:
                terms.append(marker)
    return _deduplicate_terms(terms)


def _deduplicate_terms(terms: list[str]) -> list[str]:
    """保持顺序去重。"""

    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = str(term or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _has_enough_overlap(matched_terms: list[str], claim_terms: list[str]) -> bool:
    """判断证据是否覆盖命题核心，不要求完全字面一致。"""

    if not claim_terms:
        return False
    if len(matched_terms) >= 2:
        return True
    return bool(matched_terms and len(claim_terms) <= 2)


def _has_support_marker(content: str, rules: dict) -> bool:
    """识别支持命题成立的常见表达。"""

    return any(marker in content for marker in _get_marker_list(rules, "support"))


def _has_refute_marker(content: str, rules: dict) -> bool:
    """识别直接否定或反驳命题的表达。"""

    direct_markers = _get_marker_list(rules, "refute")
    if any(marker in content for marker in direct_markers):
        return True
    return any(marker in content for marker in _get_marker_list(rules, "refute_phrases"))


def _has_condition_marker(content: str, rules: dict) -> bool:
    """识别条件、限制、风险和例外。"""

    return any(marker in content for marker in _get_marker_list(rules, "condition"))


def _is_example_only(content: str, rules: dict) -> bool:
    """识别不能泛化的案例或样例证据。"""

    return any(marker in content for marker in _get_marker_list(rules, "example"))


def _is_method_or_formula_context(claim: str, content: str, rules: dict) -> bool:
    """识别组合方案、方法、配方、流程或系统语境。"""

    context_markers = _get_marker_list(rules, "method_context")
    if not any(marker in content for marker in context_markers):
        return False
    # 用户问的是单项能力，但证据说的是组合或方法整体能力时，不能直接支持单项命题。
    single_item_markers = _get_marker_list(rules, "single_item_subject")
    return any(marker in claim for marker in single_item_markers)


def _is_subject_specific_partial_support(claim: str, content: str, rules: dict) -> bool:
    """识别组合语境中明确归因到用户命题主体的部分支持。"""

    subjects = [marker for marker in _get_marker_list(rules, "single_item_subject") if marker in claim]
    if not subjects:
        return False
    effect_markers = _get_marker_list(rules, "partial_effect")
    for subject in subjects:
        for match in re.finditer(re.escape(subject), content):
            window = content[match.start() : match.start() + 36]
            if any(marker in window for marker in effect_markers):
                if "整体" in window or "组合" in window:
                    continue
                return True
    return False


def _get_marker_list(rules: dict, key: str) -> list[str]:
    """读取 markers 下的字符串列表。"""

    markers = rules.get("markers", {}) if isinstance(rules.get("markers", {}), dict) else {}
    value = markers.get(key, [])
    return [str(item) for item in value if str(item)]


def _get_rule_list(rules: dict, key: str) -> list[str]:
    """读取顶层字符串列表。"""

    value = rules.get(key, [])
    return [str(item) for item in value if str(item)]


def _merge_rules(base: dict, override: dict) -> dict:
    """合并默认规则与外置规则，列表按追加方式处理。"""

    merged = {
        "markers": {key: list(value) for key, value in base.get("markers", {}).items()},
        "stop_words": list(base.get("stop_words", [])),
        "conclusion_templates": dict(base.get("conclusion_templates", {})),
    }
    override_markers = override.get("markers", {}) if isinstance(override.get("markers", {}), dict) else {}
    for key, value in override_markers.items():
        if not isinstance(value, list):
            continue
        existing = merged["markers"].setdefault(key, [])
        for item in value:
            text = str(item)
            if text and text not in existing:
                existing.append(text)
    if isinstance(override.get("stop_words"), list):
        for item in override["stop_words"]:
            text = str(item)
            if text and text not in merged["stop_words"]:
                merged["stop_words"].append(text)
    if isinstance(override.get("conclusion_templates"), dict):
        for key, value in override["conclusion_templates"].items():
            merged["conclusion_templates"][str(key)] = str(value)
    return merged


def _render_conclusion_template(templates: dict, key: str, claim: str) -> str:
    """渲染外置结论模板。"""

    template = str(templates.get(key) or DEFAULT_RULES["conclusion_templates"][key])
    return template.format(claim=claim)


def _build_relation_reason(relation_type: str, matched_terms: list[str]) -> str:
    """生成可展示的关系判断理由。"""

    matched_text = "、".join(matched_terms[:4]) if matched_terms else "未覆盖核心词"
    return f"{RELATION_LABELS.get(relation_type, relation_type)}；命中核心词：{matched_text}"
