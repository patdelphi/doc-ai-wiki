"""程序说明：验证 PageIndex Question Plan 的结构化归一化与提示词生成。"""

from __future__ import annotations


def test_question_plan_should_normalize_information_extraction_payload() -> None:
    """信息抽取类计划应保留 LLM 策略，并允许关闭证据关系判断。"""

    from src.pageindex.question_plan import normalize_question_plan

    plan = normalize_question_plan(
        {
            "question_type": "information_extraction",
            "answer_strategy": "列举质量检测方法并按类别归纳。",
            "target": "阿胶质量检测方法",
            "claim": "",
            "required_output": ["结论", "方法清单", "依据", "来源"],
            "needs_evidence_relation": False,
        },
        "阿胶有哪些质量检测方法",
    )

    assert plan["question_type"] == "information_extraction"
    assert plan["target"] == "阿胶质量检测方法"
    assert plan["needs_evidence_relation"] is False
    assert "方法清单" in plan["required_output"]


def test_question_plan_should_fallback_to_unknown_for_invalid_payload() -> None:
    """非法计划不能影响回答链路，应保守降级为 unknown。"""

    from src.pageindex.question_plan import normalize_question_plan

    plan = normalize_question_plan({"question_type": "made_up"}, "心脏病吃阿胶有好处吗")

    assert plan["question_type"] == "unknown"
    assert plan["target"] == "心脏病吃阿胶有好处吗"
    assert plan["needs_evidence_relation"] is True


def test_question_plan_prompt_should_include_question_and_evidence_preview() -> None:
    """Question Plan 提示词应携带问题和证据预览，但不要求生成最终答案。"""

    from src.pageindex.question_plan import build_question_plan_prompts

    system_prompt, user_prompt = build_question_plan_prompts(
        "阿胶有哪些质量检测方法",
        [{"title": "质量检测方法", "position": "line 10", "content": "包括真伪鉴别、重金属检测。"}],
    )

    assert "Question Planner" in system_prompt
    assert "阿胶有哪些质量检测方法" in user_prompt
    assert "真伪鉴别" in user_prompt
    assert "不要猜最终答案" in user_prompt
