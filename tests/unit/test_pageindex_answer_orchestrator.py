"""程序说明：验证 PageIndex 最终回答编排、Question Plan 与本地保守回答。"""

from __future__ import annotations

import pytest

from src.pageindex.answer_orchestrator import PageIndexAnswerOrchestrator
from src.pageindex.routing import PageIndexBudget, RetrievalBudgetExceededError
from src.pageindex.templates import PageIndexTemplateService


class RecordingTemplateService(PageIndexTemplateService):
    """记录最终回答模板收到的参数。"""

    def __init__(self) -> None:
        super().__init__()
        self.render_payload: dict = {}

    def get_template(self, template_id: str | None = None) -> dict:
        """返回最小测试模板。"""

        return {"template_id": template_id or "strict_qa"}

    def render_answer_prompts(
        self,
        template: dict,
        *,
        question: str,
        evidence: list[dict],
        structure_context: str,
        evidence_judgement: str,
        citation_rules: str,
        question_plan: dict | None = None,
    ) -> tuple[str, str]:
        """保存模板变量并返回稳定 Prompt。"""

        self.render_payload = {
            "template": template,
            "question": question,
            "evidence": evidence,
            "structure_context": structure_context,
            "evidence_judgement": evidence_judgement,
            "citation_rules": citation_rules,
            "question_plan": question_plan,
        }
        return "answer-system", "answer-user"


class ContractTemplateService(RecordingTemplateService):
    """返回带回答模式的模板，用于验证最终答案契约。"""

    def get_template(self, template_id: str | None = None) -> dict:
        """返回医学安全模板的最小契约字段。"""

        return {
            "template_id": template_id or "medical_safety_qa",
            "answer_mode": "medical_safety",
        }


class RecordingLLMClient:
    """按顺序返回 JSON，并记录模型调用。"""

    def __init__(self, responses: list[dict] | None = None, error: Exception | None = None) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        """返回下一项结果或抛出指定异常。"""

        self.calls.append((system_prompt, user_prompt))
        if self.error is not None:
            raise self.error
        return self.responses.pop(0) if self.responses else {}


def build_budget(*, max_llm_calls: int = 3) -> PageIndexBudget:
    """构造回答编排测试预算。"""

    return PageIndexBudget(
        max_llm_calls=max_llm_calls,
        max_rounds=1,
        max_documents=1,
        max_evidence=4,
    )


def build_evidence() -> list[dict]:
    """构造带来源和证据类型的最小证据。"""

    return [
        {
            "title": "预算制度",
            "position": "line 8",
            "source_anchor": "line 8",
            "doc_uid": "doc-1",
            "content": "制度允许项目负责人调整预算。",
            "evidence_type": "direct_support",
            "evidence_label": "直接支持",
            "relation_type": "direct_support",
        }
    ]


def test_build_question_plan_should_use_llm_and_consume_budget() -> None:
    """Question Plan 应使用模型结果并记录预算原因。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())
    llm_client = RecordingLLMClient(
        [
            {
                "question_type": "information_extraction",
                "answer_strategy": "列出预算规则。",
                "target": "预算规则",
                "required_output": ["结论", "规则"],
                "needs_evidence_relation": False,
            }
        ]
    )
    budget = build_budget()

    plan = orchestrator.build_question_plan(llm_client, "有哪些预算规则", [], budget=budget)

    assert plan["question_type"] == "information_extraction"
    assert plan["target"] == "预算规则"
    assert plan["required_output"] == ["结论", "规则"]
    assert budget.call_trace == ["question_plan"]
    assert len(llm_client.calls) == 1


def test_build_question_plan_should_fallback_when_llm_fails() -> None:
    """普通模型异常应生成保守 Question Plan。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())
    budget = build_budget()

    plan = orchestrator.build_question_plan(
        RecordingLLMClient(error=RuntimeError("planner unavailable")),
        "项目是否允许预算调整",
        [],
        budget=budget,
    )

    assert plan["question_type"] == "unknown"
    assert plan["target"] == "项目是否允许预算调整"
    assert budget.call_trace == ["question_plan"]


def test_build_question_plan_should_propagate_budget_exhaustion() -> None:
    """预算耗尽不得被普通模型降级捕获。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())
    llm_client = RecordingLLMClient()

    with pytest.raises(RetrievalBudgetExceededError):
        orchestrator.build_question_plan(
            llm_client,
            "项目是否允许预算调整",
            [],
            budget=build_budget(max_llm_calls=0),
        )

    assert llm_client.calls == []


def test_generate_answer_should_reuse_plan_and_render_existing_template_variables() -> None:
    """已有 Question Plan 应直接复用，并保持模板变量和预算名称。"""

    template_service = RecordingTemplateService()
    orchestrator = PageIndexAnswerOrchestrator(template_service)
    llm_client = RecordingLLMClient([{"answer": "结论：允许按制度调整预算。"}])
    budget = build_budget()
    question_plan = {"question_type": "claim_judgement", "target": "预算调整"}
    evidence = build_evidence()

    payload = orchestrator.generate_llm_answer_payload(
        llm_client,
        "项目是否允许预算调整",
        evidence,
        template_id="custom",
        question_plan=question_plan,
        budget=budget,
    )

    assert payload == {
        "answer": "结论：允许按制度调整预算。",
        "question_plan": question_plan,
    }
    assert llm_client.calls == [("answer-system", "answer-user")]
    assert budget.call_trace == ["final_answer"]
    assert template_service.render_payload["template"] == {"template_id": "custom"}
    assert template_service.render_payload["question_plan"] == question_plan
    assert template_service.render_payload["structure_context"] == "doc-1 > 预算制度 > line 8"
    assert template_service.render_payload["evidence_judgement"] == "直接支持：预算制度"
    assert template_service.render_payload["citation_rules"] == "必须列出证据标题、位置、文档或 chunk 来源。"


def test_generate_answer_should_build_plan_before_final_answer() -> None:
    """未提供 Question Plan 时应先规划，再生成最终回答。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())
    llm_client = RecordingLLMClient(
        [
            {"question_type": "claim_judgement", "target": "预算调整"},
            {"answer": "结论：证据支持预算调整。"},
        ]
    )
    budget = build_budget()

    payload = orchestrator.generate_llm_answer_payload(
        llm_client,
        "项目是否允许预算调整",
        build_evidence(),
        budget=budget,
    )

    assert payload["answer"] == "结论：证据支持预算调整。"
    assert payload["question_plan"]["question_type"] == "claim_judgement"
    assert budget.call_trace == ["question_plan", "final_answer"]
    assert len(llm_client.calls) == 2


def test_generate_answer_should_not_swallow_final_llm_error() -> None:
    """最终回答异常应交给现有服务调用者处理。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())

    with pytest.raises(RuntimeError, match="answer unavailable"):
        orchestrator.generate_llm_answer_payload(
            RecordingLLMClient(error=RuntimeError("answer unavailable")),
            "项目是否允许预算调整",
            build_evidence(),
            question_plan={"question_type": "claim_judgement"},
        )


def test_build_local_answer_should_return_evidence_bound_refusal_without_evidence() -> None:
    """无证据时应输出带来源和不确定点的明确拒答。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())

    answer = orchestrator.build_local_answer("项目是否允许预算调整", [])

    assert "结论：证据不足" in answer
    assert "依据：未在当前知识库" in answer
    assert "来源：无" in answer
    assert "不确定点：需要补充相关文档或重新构建索引" in answer


def test_classification_and_local_answer_should_keep_five_section_structure() -> None:
    """证据分类和本地回答应保留结论、判断、依据、来源和不确定点。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())
    classified = orchestrator.classify_evidence_items(
        "项目是否允许预算调整",
        [
            {
                "title": "预算制度",
                "position": "line 8",
                "doc_uid": "doc-1",
                "content": "制度允许项目负责人调整预算。",
            }
        ],
    )

    answer = orchestrator.build_local_answer("项目是否允许预算调整", classified)

    assert classified[0]["evidence_type"] == "direct_support"
    assert answer.startswith("结论：")
    assert "\n\n证据判断：" in answer
    assert "\n\n依据：" in answer
    assert "\n\n来源：预算制度（line 8），文档：doc-1" in answer
    assert "\n\n不确定点：" in answer


def test_information_extraction_local_answer_should_not_be_misclassified_as_claim_refusal() -> None:
    """信息抽取问题应输出可提取要点，不能套用命题真假结论。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())
    evidence = orchestrator.classify_evidence_items(
        "阿胶具有哪些补血相关作用？",
        [
            {
                "title": "调节血液系统",
                "position": "line 10",
                "doc_uid": "doc-1",
                "content": "研究表明，阿胶可以提高红细胞数量并改善造血功能。",
            }
        ],
    )

    answer = orchestrator.build_local_answer(
        "阿胶具有哪些补血相关作用？",
        evidence,
        question_plan={
            "question_type": "information_extraction",
            "target": "阿胶的补血相关作用",
            "needs_evidence_relation": False,
        },
    )

    assert "当前证据可提取" in answer
    assert "当前证据不支持" not in answer
    assert "提高红细胞数量" in answer


def test_normalize_answer_should_render_structured_dict_as_readable_markdown() -> None:
    """模型返回 dict 时，最终答案不能落成 Python repr。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())

    answer = orchestrator.normalize_answer(
        {
            "结论": "证据部分支持。",
            "证据能说明什么": ["支持辅助作用。", {"来源": "研究"}],
            "不确定点": "缺少大样本临床试验。",
        }
    )

    assert answer.startswith("#### 结论")
    assert "#### 证据能说明什么" in answer
    assert "- 支持辅助作用。" in answer
    assert "**来源**：研究" in answer
    assert "#### 不确定点" in answer
    assert not answer.startswith("{")


def test_normalize_answer_should_parse_python_dict_string() -> None:
    """兼容模型把结构化答案包成 Python 字典字符串的情况。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())

    answer = orchestrator.normalize_answer("{'结论': '证据不足。', '来源': ['文档 A']}")

    assert "#### 结论" in answer
    assert "证据不足。" in answer
    assert "- 文档 A" in answer


def test_normalize_answer_should_order_evidence_sections_before_limits() -> None:
    """证据审查回答应先说明能证明什么，再说明不能证明什么。"""

    orchestrator = PageIndexAnswerOrchestrator(RecordingTemplateService())

    answer = orchestrator.normalize_answer(
        {
            "审查结论": "部分支持",
            "证据不能证明什么": ["不能外推"],
            "证据能证明什么": ["支持传统功效"],
        }
    )

    assert answer.index("#### 证据能证明什么") < answer.index("#### 证据不能证明什么")


def test_generate_answer_should_repair_missing_medical_contract_sections() -> None:
    """医学模板回答缺少来源和边界时，应基于现有证据做保守补全。"""

    orchestrator = PageIndexAnswerOrchestrator(ContractTemplateService())
    evidence = [
        {
            **build_evidence()[0],
            "chunk_id": "chunk-1",
        }
    ]

    payload = orchestrator.generate_llm_answer_payload(
        RecordingLLMClient([{"answer": "现有材料提到相关作用。"}]),
        "该材料能否证明临床治疗效果？",
        evidence,
        template_id="medical_safety_qa",
        question_plan={"question_type": "claim_judgement"},
    )

    answer = payload["answer"]
    assert "#### 结论" in answer
    assert "#### 证据能说明什么" in answer
    assert "#### 证据不能证明什么" in answer
    assert "#### 风险或人群边界" in answer
    assert "#### 依据" in answer
    assert "#### 来源" in answer
    assert "doc-1" in answer
    assert "chunk-1" in answer
    assert "#### 不确定点" in answer
    assert "#### 非医疗建议" in answer
    assert payload["answer_contract"]["repaired"] is True
    assert "来源" in payload["answer_contract"]["missing_sections"]


def test_generate_answer_should_not_repair_complete_structured_contract() -> None:
    """模型已完整返回医学安全结构时，不应重复追加章节。"""

    orchestrator = PageIndexAnswerOrchestrator(ContractTemplateService())
    answer_payload = {
        "结论": "证据不足。",
        "证据能说明什么": "材料涉及相关机制。",
        "证据不能证明什么": "不能证明临床疗效。",
        "风险或人群边界": "缺少特定人群资料。",
        "依据": "当前仅有间接证据。",
        "来源": "预算制度（line 8），文档：doc-1",
        "不确定点": "缺少临床终点。",
        "非医疗建议": "不能替代医生判断。",
    }

    payload = orchestrator.generate_llm_answer_payload(
        RecordingLLMClient([{"answer": answer_payload}]),
        "该材料能否证明临床治疗效果？",
        build_evidence(),
        template_id="medical_safety_qa",
        question_plan={"question_type": "claim_judgement"},
    )

    assert payload["answer_contract"] == {
        "mode": "medical_safety",
        "required_sections": list(answer_payload),
        "missing_sections": [],
        "repaired": False,
    }
    assert payload["answer"].count("#### 来源") == 1


def test_generate_answer_should_degrade_when_model_uses_external_common_knowledge() -> None:
    """模型自行引用一般常识时，应回退到仅基于当前证据的保守答案。"""

    orchestrator = PageIndexAnswerOrchestrator(ContractTemplateService())
    evidence = [
        {
            "title": "产品配料表",
            "position": "line 10",
            "doc_uid": "doc-product",
            "chunk_id": "chunk-product",
            "evidence_type": "method_or_formula_context",
            "evidence_label": "方法/组合语境",
            "content": "配料表：黑芝麻、核桃仁、麦芽糖浆、冰糖、阿胶。",
        },
        {
            "title": "杨玉环",
            "position": "line 20",
            "doc_uid": "doc-history",
            "evidence_type": "context_only",
            "evidence_label": "仅背景相关",
            "content": "相传杨玉环长期食用阿胶羹。",
        },
        {
            "title": "生产工艺",
            "position": "line 25",
            "doc_uid": "doc-process",
            "evidence_type": "method_or_formula_context",
            "evidence_label": "方法/组合语境",
            "content": "阿胶工业生产过程包括配料、泡皮、化皮、浓缩和包装。",
        },
        {
            "title": "阿胶使用注意",
            "position": "line 30",
            "doc_uid": "doc-safety",
            "chunk_id": "chunk-safety",
            "evidence_type": "method_or_formula_context",
            "evidence_label": "方法/组合语境",
            "content": "阿胶必须在医师指导下正确服用，否则可能产生不良反应。",
        },
    ]

    payload = orchestrator.generate_llm_answer_payload(
        RecordingLLMClient(
            [
                {
                    "answer": {
                        "结论": "糖尿病患者绝对不能食用。",
                        "证据能说明什么": "配料含糖。",
                        "证据不能证明什么": "缺少临床数据。",
                        "风险或人群边界": "基于食品科学常识，高糖食品均不适合。",
                        "依据": "食品科学常识。",
                        "来源": "预算制度。",
                        "不确定点": "无。",
                        "非医疗建议": "咨询医生。",
                    }
                }
            ]
        ),
        "阿胶糕常见配料有哪些？糖尿病患者、坚果过敏人群是否适合长期不限量食用？",
        evidence,
        template_id="medical_safety_qa",
        question_plan={"question_type": "claim_judgement"},
    )

    assert "食品科学常识" not in payload["answer"]
    assert "特定人群、长期使用、剂量上限" in payload["answer"]
    assert "配料表：黑芝麻、核桃仁" in payload["answer"]
    assert "医师指导" in payload["answer"]
    assert "杨玉环" not in payload["answer"]
    assert "生产工艺" not in payload["answer"]
    assert "doc-product" in payload["answer"]
    assert "doc-safety" in payload["answer"]
    assert payload["answer_contract"]["repaired"] is False
    assert payload["answer_contract"]["degraded_reason"] == "unsupported_external_knowledge"
    assert "食品科学常识" in payload["answer_contract"]["external_knowledge_markers"]


def test_generate_answer_should_degrade_unsupported_strong_medical_claim() -> None:
    """证据原文没有的“严禁”等强医疗结论即使不提常识，也必须降级。"""

    orchestrator = PageIndexAnswerOrchestrator(ContractTemplateService())
    evidence = [
        {
            "title": "产品配料表",
            "position": "line 10",
            "doc_uid": "doc-product",
            "evidence_type": "method_or_formula_context",
            "evidence_label": "方法/组合语境",
            "content": "配料表包含核桃仁、麦芽糖浆和阿胶。",
        }
    ]

    payload = orchestrator.generate_llm_answer_payload(
        RecordingLLMClient(
            [
                {
                    "answer": {
                        "结论": "坚果过敏人群严禁食用。",
                        "证据能说明什么": "配料含核桃仁。",
                        "证据不能证明什么": "缺少人群研究。",
                        "风险或人群边界": "坚果过敏人群严禁食用。",
                        "依据": "配料表。",
                        "来源": "产品配料表。",
                        "不确定点": "无。",
                        "非医疗建议": "咨询医生。",
                    }
                }
            ]
        ),
        "坚果过敏人群是否适合食用？",
        evidence,
        template_id="medical_safety_qa",
        question_plan={"question_type": "claim_judgement"},
    )

    assert "严禁" not in payload["answer"]
    assert payload["answer_contract"]["degraded_reason"] == "unsupported_external_knowledge"
    assert "严禁" in payload["answer_contract"]["external_knowledge_markers"]
