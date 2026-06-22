"""程序说明：生成和校验 PageIndex 问题计划，让回答策略由 LLM 结构化决定。"""

from __future__ import annotations

import json
from typing import Any


QUESTION_TYPES = {
    "information_extraction",
    "claim_judgement",
    "source_location",
    "comparison",
    "summary",
    "unknown",
}

DEFAULT_QUESTION_PLAN = {
    "question_type": "unknown",
    "answer_strategy": "先理解用户问题，再严格基于证据回答；证据不足时明确说明不足。",
    "target": "",
    "claim": "",
    "required_output": ["结论", "依据", "来源", "不确定点"],
    "needs_evidence_relation": True,
    "insufficient_evidence_policy": "证据不足时不能编造结论，必须说明当前知识库未提供足够依据。",
}


def normalize_question_plan(payload: dict[str, Any] | None, question: str) -> dict[str, Any]:
    """校验 LLM 生成的问题计划，字段缺失或非法时使用保守默认值。"""

    raw_payload = payload if isinstance(payload, dict) else {}
    plan = dict(DEFAULT_QUESTION_PLAN)
    question_type = str(raw_payload.get("question_type") or "").strip()
    if question_type in QUESTION_TYPES:
        plan["question_type"] = question_type
    for field in ("answer_strategy", "target", "claim", "insufficient_evidence_policy"):
        value = str(raw_payload.get(field) or "").strip()
        if value:
            plan[field] = value
    required_output = raw_payload.get("required_output")
    if isinstance(required_output, list):
        normalized_output = [str(item).strip() for item in required_output if str(item).strip()]
        if normalized_output:
            plan["required_output"] = normalized_output[:8]
    if isinstance(raw_payload.get("needs_evidence_relation"), bool):
        plan["needs_evidence_relation"] = bool(raw_payload["needs_evidence_relation"])
    if not str(plan.get("target") or "").strip():
        plan["target"] = str(question or "").strip()
    return plan


def build_question_plan_prompts(question: str, evidence: list[dict]) -> tuple[str, str]:
    """构建 Question Plan 提示词，只要求 LLM 返回结构化计划，不生成最终答案。"""

    evidence_preview = [
        {
            "title": str(item.get("title") or item.get("source_type") or "")[:120],
            "position": str(item.get("position") or item.get("source_anchor") or "")[:80],
            "evidence_type": str(item.get("evidence_type") or "")[:60],
            "content_excerpt": str(item.get("content") or item.get("summary") or "")[:500],
        }
        for item in evidence[:6]
    ]
    system_prompt = (
        "你是 PageIndex Question Planner。你的任务是判断用户真正需要的回答策略，"
        "只能返回 JSON，不要输出最终答案。"
    )
    user_prompt = "\n".join(
        [
            "用户问题：",
            str(question or ""),
            "",
            "证据预览 JSON：",
            json.dumps(evidence_preview, ensure_ascii=False),
            "",
            "请返回 JSON，字段必须包含：",
            json.dumps(
                {
                    "question_type": "information_extraction | claim_judgement | source_location | comparison | summary | unknown",
                    "answer_strategy": "如何基于证据回答",
                    "target": "用户要了解的对象",
                    "claim": "如果是命题判断，写出待判断命题；否则为空",
                    "required_output": ["结论", "依据", "来源", "不确定点"],
                    "needs_evidence_relation": True,
                    "insufficient_evidence_policy": "证据不足时如何处理",
                },
                ensure_ascii=False,
            ),
            "",
            "判断规则：",
            "1. 问“有哪些、是什么、方法、步骤、特点、流程”通常是 information_extraction，但仍要结合语义判断。",
            "2. 问“是否、有无好处、能不能、能否治疗、是否支持”通常是 claim_judgement。",
            "3. 问“在哪、出处、引用、原文位置”通常是 source_location。",
            "4. 不确定时返回 unknown，不要猜最终答案。",
        ]
    )
    return system_prompt, user_prompt
