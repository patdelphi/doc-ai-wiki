"""程序说明：验证 PageIndex 通用命题-证据关系判断，不绑定单一领域。"""

from __future__ import annotations

from src.pageindex.evidence_judge import classify_evidence_relation, infer_conclusion, load_evidence_judge_rules


def test_evidence_judge_should_detect_direct_support_for_regulation_claim() -> None:
    """法规证据直接说明允许时，应判断为直接支持。"""

    relation = classify_evidence_relation(
        "该制度允许项目负责人审批预算调整",
        {
            "title": "预算调整制度",
            "content": "项目负责人可以审批预算调整，审批后应在系统中留痕。",
        },
    )

    assert relation["relation_type"] == "direct_support"
    assert relation["relation_label"] == "直接支持"


def test_evidence_judge_should_not_treat_background_as_regulation_permission() -> None:
    """只有背景条款时，不能推出法规允许用户问的行为。"""

    relation = classify_evidence_relation(
        "该制度允许项目负责人审批预算调整",
        {
            "title": "预算管理背景",
            "content": "预算调整应加强过程管理，财务部门负责归档相关材料。",
        },
    )
    conclusion = infer_conclusion("该制度允许项目负责人审批预算调整", [relation])

    assert relation["relation_type"] == "context_only"
    assert "证据不足" in conclusion
    assert "不能得出" in conclusion


def test_evidence_judge_should_detect_method_context_for_single_item_claim() -> None:
    """组合方案或方法语境不能证明单项命题成立。"""

    relation = classify_evidence_relation(
        "A 模块能提高系统吞吐量",
        {
            "title": "性能优化方案",
            "content": "系统采用 A 模块、缓存层和异步队列组成的优化方案，整体吞吐量提升 20%。",
        },
    )
    conclusion = infer_conclusion("A 模块能提高系统吞吐量", [relation])

    assert relation["relation_type"] == "method_or_formula_context"
    assert "不能证明" in conclusion
    assert "组合方案" in conclusion


def test_evidence_judge_should_not_generalize_from_example_only() -> None:
    """单个案例只能作为样例，不能泛化为命题成立。"""

    relation = classify_evidence_relation(
        "这个工艺能稳定提高产量",
        {
            "title": "试生产案例",
            "content": "某次试生产案例中，该工艺产量提高 8%，但样本量较小。",
        },
    )
    conclusion = infer_conclusion("这个工艺能稳定提高产量", [relation])

    assert relation["relation_type"] == "example_only"
    assert "不能泛化" in conclusion


def test_evidence_judge_should_detect_direct_refute() -> None:
    """证据明确否定命题时，应给出直接反驳关系。"""

    relation = classify_evidence_relation(
        "张三提出了零库存理论",
        {
            "title": "学术观点来源",
            "content": "现有文献未见张三提出零库存理论，该理论通常归属于其他研究者。",
        },
    )
    conclusion = infer_conclusion("张三提出了零库存理论", [relation])

    assert relation["relation_type"] == "direct_refute"
    assert "不支持" in conclusion


def test_evidence_judge_should_prioritize_risk_or_condition_without_direct_support() -> None:
    """只有条件限制时，结论应提示不能直接推出命题。"""

    relation = classify_evidence_relation(
        "该接口可以对外开放",
        {
            "title": "接口开放条件",
            "content": "接口开放必须完成安全评审，并仅限白名单系统调用。",
        },
    )
    conclusion = infer_conclusion("该接口可以对外开放", [relation])

    assert relation["relation_type"] == "risk_or_condition"
    assert "存在条件或限制" in conclusion


def test_evidence_judge_should_not_treat_classic_symptom_phrase_as_refute() -> None:
    """“不得眠”等原文症状词不是对用户命题的直接反驳。"""

    relation = classify_evidence_relation(
        "吃阿胶能缓解痛经",
        {
            "title": "猪苓汤方语境",
            "content": "猪苓汤方即阿胶、滑石相协，以治少阴病下利六七日，咳而呕渴，心烦不得眠者。本方中阿胶既有止血作用，又有缓解窘迫症状之功。",
        },
    )

    assert relation["relation_type"] != "direct_refute"


def test_evidence_judge_should_treat_formula_role_as_partial_support_not_refute() -> None:
    """证据明确说方中阿胶兼止痛时，应视为部分支持而不是纯背景或反驳。"""

    relation = classify_evidence_relation(
        "吃阿胶能缓解痛经",
        {
            "title": "温经汤方义",
            "content": "温经汤临床中应用于月经不调、痛经等病证，方中阿胶既可止血，又兼止痛、补虚。",
        },
    )
    conclusion = infer_conclusion("吃阿胶能缓解痛经", [relation])

    assert relation["relation_type"] == "partial_support"
    assert "只支持" in conclusion
    assert "不能推出完整命题" in conclusion


def test_evidence_judge_should_load_external_yaml_rules(tmp_path) -> None:
    """Evidence Judge 规则应可通过 templates/pageindex/evidence_judge.yaml 外置调整。"""

    rule_dir = tmp_path / "templates" / "pageindex"
    rule_dir.mkdir(parents=True)
    (rule_dir / "evidence_judge.yaml").write_text(
        """
markers:
  support:
    - 形成依据
""".strip(),
        encoding="utf-8",
    )

    default_relation = classify_evidence_relation(
        "该资料形成依据",
        {"title": "资料说明", "content": "该资料形成依据，供后续审查使用。"},
    )
    external_relation = classify_evidence_relation(
        "该资料形成依据",
        {"title": "资料说明", "content": "该资料形成依据，供后续审查使用。"},
        rules=load_evidence_judge_rules(tmp_path / "templates"),
    )

    assert default_relation["relation_type"] != "direct_support"
    assert external_relation["relation_type"] == "direct_support"
