"""程序说明：验证规则等级对质检结论的影响。"""

from pathlib import Path

import pytest

from src.common.errors import DatabaseAppError
from src.db.connection import initialize_database
from src.quality.service import QualityService


def test_quality_service_should_raise_risk_when_warn_rule_is_hit(tmp_path: Path) -> None:
    """命中 warn 规则时，应降级为人工复核。"""

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "warn_rules.yaml").write_text(
        """
- code: R001
  name: 绝对化表述
  keywords:
    - 一定
  hit_level: warn
  message: 包含绝对化表述
""".strip(),
        encoding="utf-8",
    )
    db_path = tmp_path / "app.db"
    initialize_database(db_path)

    service = QualityService(db_path, rules_dir=rules_dir)
    service.retrieval_service.hybrid_search = lambda query, top_k=3, doc_uid=None, **kwargs: [  # type: ignore[method-assign]
        {"doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "证据内容"}
    ]

    result = service.run_check("这个系统一定正确。")

    assert result["claims"][0]["verdict"] == "needs_review"
    assert result["check"]["risk_level"] == "medium"
    assert result["rule_hits"]


def test_quality_service_should_reject_when_block_rule_is_hit(tmp_path: Path) -> None:
    """命中 block 规则时，应标记为高风险拒绝。"""

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "block_rules.yaml").write_text(
        """
- code: R999
  name: 禁止词
  keywords:
    - 禁止发布
  hit_level: block
  message: 命中禁止发布规则
""".strip(),
        encoding="utf-8",
    )
    db_path = tmp_path / "app.db"
    initialize_database(db_path)

    service = QualityService(db_path, rules_dir=rules_dir)
    service.retrieval_service.hybrid_search = lambda query, top_k=3, doc_uid=None, **kwargs: [  # type: ignore[method-assign]
        {"doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "证据内容"}
    ]

    result = service.run_check("这段内容禁止发布。")

    assert result["claims"][0]["verdict"] == "rejected"
    assert result["check"]["risk_level"] == "high"
    assert result["rule_hits"][0]["hit_level"] == "block"


def test_quality_service_should_apply_template_rule_tags_and_retrieval_policy(tmp_path: Path) -> None:
    """模板应同时影响规则筛选和检索上下文策略。"""

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "tagged_rules.yaml").write_text(
        """
- code: G001
  name: 通用规则
  keywords:
    - 一定
  hit_level: warn
  message: 通用规则命中
  template_tags:
    - general

- code: M001
  name: 医学规则
  keywords:
    - 治愈
  hit_level: error
  message: 医学规则命中
  template_tags:
    - medical
""".strip(),
        encoding="utf-8",
    )

    db_path = tmp_path / "app.db"
    initialize_database(db_path)
    service = QualityService(db_path, rules_dir=rules_dir, templates_dir=tmp_path / "templates")

    captured_search_kwargs: dict = {}
    captured_expand_kwargs: dict = {}

    def fake_hybrid_search(query, top_k=5, doc_uid=None, **kwargs):  # noqa: ANN001
        captured_search_kwargs.update({"query": query, "top_k": top_k, "doc_uid": doc_uid, **kwargs})
        return [{"chunk_id": "chk_1", "doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "证据内容"}]

    def fake_expand_evidence_context(items, **kwargs):  # noqa: ANN001
        captured_expand_kwargs.update(kwargs)
        return [{**items[0], "expanded_content": "扩展证据", "context_mode": "section_context"}]

    service.retrieval_service.hybrid_search = fake_hybrid_search  # type: ignore[method-assign]
    service.retrieval_service.expand_evidence_context = fake_expand_evidence_context  # type: ignore[method-assign]

    result = service.run_check("该疗法一定可以治愈所有人。", template_id="medical_safety_review")

    assert result["check"]["template_id"] == "medical_safety_review"
    assert result["check"]["active_rule_tags"] == ["medical", "strict"]
    assert result["check"]["retrieval_policy"]["final_top_k"] == 5
    assert result["check"]["retrieval_policy"]["use_rerank"] is True
    assert captured_search_kwargs["fulltext_top_k"] >= 6
    assert captured_search_kwargs["vector_top_k"] >= 6
    assert captured_search_kwargs["use_rerank"] is True
    assert captured_expand_kwargs["neighbor_window"] == 1
    assert captured_expand_kwargs["include_section_context"] is True
    assert result["rule_hits"][0]["rule_code"] == "M001"
    assert result["claims"][0]["evidence_details"][0]["context_mode"] == "section_context"


def test_quality_service_should_allow_template_to_disable_rerank(tmp_path: Path) -> None:
    """模板策略指定不启用 rerank 时，应向检索层透传关闭标记。"""

    templates_dir = tmp_path / "templates" / "quality"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "general_fact_check.yaml").write_text(
        """
template_id: general_fact_check
template_name: 通用事实核检
description: 覆盖默认模板
rule_tags:
  - general
retrieval_policy:
  fulltext_top_k: 2
  vector_top_k: 2
  final_top_k: 2
  use_rerank: false
  neighbor_window: 0
  include_section_context: false
  section_max_chars: 300
system_prompt: 系统提示
user_prompt_template: |
  Claim:
  {claim_text}
  证据：
  {evidence_block}
  规则：
  {rule_block}
""".strip(),
        encoding="utf-8",
    )

    db_path = tmp_path / "app.db"
    initialize_database(db_path)
    service = QualityService(db_path, templates_dir=tmp_path / "templates")
    captured_search_kwargs: dict = {}

    def fake_hybrid_search(query, top_k=5, doc_uid=None, **kwargs):  # noqa: ANN001
        captured_search_kwargs.update(kwargs)
        return [{"chunk_id": "chk_1", "doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "证据内容"}]

    service.retrieval_service.hybrid_search = fake_hybrid_search  # type: ignore[method-assign]
    service.retrieval_service.expand_evidence_context = lambda items, **kwargs: items  # type: ignore[method-assign]

    result = service.run_check("普通结论。", template_id="general_fact_check")

    assert result["check"]["retrieval_policy"]["use_rerank"] is False
    assert captured_search_kwargs["use_rerank"] is False


def test_quality_service_stream_should_report_model_stage(tmp_path: Path) -> None:
    """流式质检应暴露检索、模型和完成阶段，便于前端展示进度。"""

    class StubLLMClient:
        """程序说明：用于验证模型阶段事件的测试桩。"""

        def evaluate_claim(
            self,
            *,
            claim_text: str,
            evidence_list: list[dict],
            matched_rules: list[dict],
            prompt_template: dict | None = None,
        ) -> dict:
            return {
                "verdict": "needs_review",
                "confidence": 0.61,
                "risk_level": "medium",
                "reason": f'llm:{prompt_template.get("template_id") if prompt_template else "none"}:{claim_text}:{len(evidence_list)}:{len(matched_rules)}',
            }

    db_path = tmp_path / "app.db"
    initialize_database(db_path)
    service = QualityService(db_path, llm_client=StubLLMClient())
    service.retrieval_service.hybrid_search = lambda query, top_k=3, doc_uid=None, **kwargs: [  # type: ignore[method-assign]
        {"chunk_id": "chk_1", "doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "证据内容"}
    ]
    service.retrieval_service.expand_evidence_context = lambda items, **kwargs: items  # type: ignore[method-assign]

    events = list(service.run_check_stream("需要模型参与判断。", template_id="general_fact_check"))

    progress_stages = [event.get("stage") for event in events if event.get("type") == "progress"]
    result_events = [event for event in events if event.get("type") == "result"]

    assert "retrieval" in progress_stages
    assert "model" in progress_stages
    assert result_events
    assert result_events[0]["result"]["claims"][0]["evidence_reason"].startswith("llm:general_fact_check:")
    assert result_events[0]["result"]["check"]["persist_verified"] is True


def test_quality_service_stream_should_verify_persisted_result_before_reporting_success(tmp_path: Path) -> None:
    """成功事件必须以数据库回读校验通过为前提。"""

    db_path = tmp_path / "app.db"
    initialize_database(db_path)
    service = QualityService(db_path)
    service.retrieval_service.hybrid_search = lambda query, top_k=3, doc_uid=None, **kwargs: [  # type: ignore[method-assign]
        {"chunk_id": "chk_1", "doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "证据内容"}
    ]
    service.retrieval_service.expand_evidence_context = lambda items, **kwargs: items  # type: ignore[method-assign]

    original_get_quality_result = service.repository.get_quality_result
    state = {"called": False}

    def fake_get_quality_result(check_id: str):  # noqa: ANN001
        if not state["called"]:
            state["called"] = True
            return None
        return original_get_quality_result(check_id)

    service.repository.get_quality_result = fake_get_quality_result  # type: ignore[method-assign]

    with pytest.raises(DatabaseAppError, match="写入后校验失败"):
        list(service.run_check_stream("需要验证写库。", template_id="general_fact_check"))


def test_quality_service_should_run_evaluation_suite_and_aggregate_metrics(tmp_path: Path) -> None:
    """效果评测应汇总预期与实际命中情况。"""

    db_path = tmp_path / "app.db"
    initialize_database(db_path)
    service = QualityService(db_path)
    service.retrieval_service.hybrid_search = lambda query, top_k=3, doc_uid=None, **kwargs: [  # type: ignore[method-assign]
        {"chunk_id": "chk_1", "doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "证据内容"}
    ]
    service.retrieval_service.expand_evidence_context = lambda items, **kwargs: items  # type: ignore[method-assign]

    result = service.run_evaluation_suite(
        [
            {
                "case_id": "case_pass",
                "input_text": "第一条结论。",
                "expected_overall_verdict": "passed",
                "expected_risk_level": "low",
                "expected_claim_count": 1,
            },
            {
                "case_id": "case_mismatch",
                "input_text": "第二条。第三条。",
                "expected_overall_verdict": "needs_review",
                "expected_risk_level": "medium",
                "expected_claim_count": 1,
            },
        ],
        template_id="general_fact_check",
    )

    assert result["summary"]["case_count"] == 2
    assert result["summary"]["overall_verdict_match_count"] == 1
    assert result["summary"]["risk_level_match_count"] == 1
    assert result["summary"]["claim_count_match_count"] == 1
    assert result["summary"]["exact_match_count"] == 1
    assert result["rows"][0]["all_matched"] is True
    assert result["rows"][1]["actual_claim_count"] == 2
    assert result["rows"][1]["claim_count_matched"] is False


def test_quality_service_should_not_upgrade_warn_claim_to_verified_even_if_llm_is_optimistic(tmp_path: Path) -> None:
    """命中绝对化或唯一化规则时，即使模型乐观也不能直接放行为 verified。"""

    class OptimisticLLMClient:
        """程序说明：故意返回过于乐观结论，用于验证保守合并策略。"""

        def evaluate_claim(
            self,
            *,
            claim_text: str,
            evidence_list: list[dict],
            matched_rules: list[dict],
            prompt_template: dict | None = None,
        ) -> dict:
            return {
                "verdict": "verified",
                "confidence": 0.96,
                "risk_level": "low",
                "reason": "llm optimistic",
            }

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "general_rules.yaml").write_text(
        """
- code: G002
  name: 唯一化表述
  keywords:
    - 只有
  hit_level: error
  message: 存在唯一化断言
  template_tags:
    - general
""".strip(),
        encoding="utf-8",
    )

    db_path = tmp_path / "app.db"
    initialize_database(db_path)
    service = QualityService(db_path, rules_dir=rules_dir, llm_client=OptimisticLLMClient())
    service.retrieval_service.hybrid_search = lambda query, top_k=3, doc_uid=None, **kwargs: [  # type: ignore[method-assign]
        {"chunk_id": "chk_1", "doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "东阿所产驴皮胶最负盛名。"}
    ]
    service.retrieval_service.expand_evidence_context = lambda items, **kwargs: items  # type: ignore[method-assign]

    result = service.run_check("阿胶只有东阿一家有。", template_id="general_fact_check")

    assert result["claims"][0]["verdict"] == "needs_review"
    assert result["claims"][0]["risk_level"] == "high"
    assert result["rule_hits"][0]["rule_code"] == "G002"


def test_quality_service_should_retrieve_counter_evidence_and_reject_exclusive_claim(tmp_path: Path) -> None:
    """唯一化 claim 应结合放宽后的检索查询补召回反证，并输出 rejected。"""

    db_path = tmp_path / "app.db"
    initialize_database(db_path)
    service = QualityService(db_path)

    captured_queries: list[str] = []

    def fake_hybrid_search(query, top_k=5, doc_uid=None, **kwargs):  # noqa: ANN001
        captured_queries.append(query)
        if "只有" in query:
            return [
                {
                    "chunk_id": "chk_primary",
                    "doc_uid": "doc_1",
                    "source_span": "section-1:chunk-0",
                    "content": "东阿所产驴皮胶最负盛名。",
                }
            ]
        return [
            {
                "chunk_id": "chk_counter",
                "doc_uid": "doc_1",
                "source_span": "section-2:chunk-1",
                "content": "所载的阿胶一般不具有地域之别，连番邦小国也有产阿胶的。",
            }
        ]

    service.retrieval_service.hybrid_search = fake_hybrid_search  # type: ignore[method-assign]
    service.retrieval_service.expand_evidence_context = lambda items, **kwargs: items  # type: ignore[method-assign]

    result = service.run_check("阿胶只有东阿一家有。", template_id="general_fact_check")

    assert len(captured_queries) >= 2
    assert captured_queries[0] == "阿胶只有东阿一家有"
    assert "只有" not in captured_queries[-1]
    assert result["claims"][0]["verdict"] == "rejected"
    assert result["check"]["overall_verdict"] == "rejected"
    assert len(result["claims"][0]["evidence_details"]) >= 2


def test_quality_service_should_build_complementary_queries_for_strict_claim() -> None:
    """强约束 Claim 应构造更多互补查询，兼顾主题、放宽检索与反证探测。"""

    query_specs = QualityService._build_retrieval_queries("阿胶只有东阿一家有")

    labels = [item["label"] for item in query_specs]
    queries = [item["query"] for item in query_specs]

    assert labels[0] == "claim_literal"
    assert "logic_relaxed" in labels
    assert "topic_focus" in labels
    assert "counter_probe" in labels
    assert len(query_specs) >= 4
    assert queries[0] == "阿胶只有东阿一家有"
    assert any("只有" not in query for query in queries[1:])
    assert any("也有" in query or "并非唯一" in query for query in queries)


def test_quality_service_should_build_keyword_queries_for_chinese_sentence_claim() -> None:
    """普通中文整句 Claim 应补充关键词查询，避免整句检索零召回。"""

    query_specs = QualityService._build_retrieval_queries("阿胶能治疗癌症")

    labels = [item["label"] for item in query_specs]
    queries = [item["query"] for item in query_specs]

    assert "keyword_focus" in labels
    assert "阿胶 癌症" in queries
    assert "癌症" in queries
    assert "阿胶 治疗" in queries


def test_quality_service_should_expand_entity_alias_queries_for_claim() -> None:
    """质检 Claim 使用别名时，应补充标准名查询，避免各模块硬编码补丁分裂。"""

    query_specs = QualityService._build_retrieval_queries("驴皮胶能改善贫血")

    queries = [item["query"] for item in query_specs]

    assert "阿胶能改善贫血" in queries
    assert "阿胶 贫血" in queries


def test_quality_service_should_keep_broader_candidate_pool_before_final_judgement(tmp_path: Path) -> None:
    """多查询召回时，不应在整理上下文前过早截断候选证据。"""

    db_path = tmp_path / "app.db"
    initialize_database(db_path)
    service = QualityService(db_path)

    service._build_retrieval_queries = lambda claim_text: [  # type: ignore[method-assign]
        {"label": "claim_literal", "query": "q1"},
        {"label": "logic_relaxed", "query": "q2"},
        {"label": "counter_probe", "query": "q3"},
    ]

    def fake_hybrid_search(query, top_k=5, doc_uid=None, **kwargs):  # noqa: ANN001
        if query == "q1":
            return [
                {"chunk_id": "chk_1", "doc_uid": "doc_1", "source_span": "s1", "content": "证据1", "rerank_score": 0.91},
                {"chunk_id": "chk_2", "doc_uid": "doc_1", "source_span": "s2", "content": "证据2", "rerank_score": 0.90},
                {"chunk_id": "chk_3", "doc_uid": "doc_1", "source_span": "s3", "content": "证据3", "rerank_score": 0.89},
            ]
        if query == "q2":
            return [
                {"chunk_id": "chk_1", "doc_uid": "doc_1", "source_span": "s1", "content": "证据1", "rerank_score": 0.91},
                {"chunk_id": "chk_4", "doc_uid": "doc_1", "source_span": "s4", "content": "证据4", "rerank_score": 0.88},
                {"chunk_id": "chk_5", "doc_uid": "doc_1", "source_span": "s5", "content": "证据5", "rerank_score": 0.87},
            ]
        return [
            {"chunk_id": "chk_6", "doc_uid": "doc_1", "source_span": "s6", "content": "证据6", "rerank_score": 0.95},
            {"chunk_id": "chk_7", "doc_uid": "doc_1", "source_span": "s7", "content": "证据7", "rerank_score": 0.86},
            {"chunk_id": "chk_8", "doc_uid": "doc_1", "source_span": "s8", "content": "证据8", "rerank_score": 0.85},
        ]

    service.retrieval_service.hybrid_search = fake_hybrid_search  # type: ignore[method-assign]

    results = service._retrieve_evidence_candidates(
        claim_text="阿胶只有东阿一家有",
        doc_uid=None,
            knowledge_base_id=None,
        retrieval_policy={
            "fulltext_top_k": 4,
            "vector_top_k": 4,
            "final_top_k": 4,
            "use_rerank": True,
        },
    )

    assert len(results) >= 8
    merged_item = next(item for item in results if item["chunk_id"] == "chk_1")
    assert set(merged_item["matched_queries"]) == {"claim_literal", "logic_relaxed"}


def test_quality_service_should_finalize_evidence_list_by_relation_priority() -> None:
    """最终证据列表应优先保留矛盾证据，并限制到 final_top_k。"""

    evidence_list = [
        {"chunk_id": "c1", "evidence_relation": "insufficient", "matched_queries": ["claim_literal"], "rerank_score": 0.95},
        {"chunk_id": "c2", "evidence_relation": "contradict", "matched_queries": ["counter_probe", "logic_relaxed"], "rerank_score": 0.70},
        {"chunk_id": "c3", "evidence_relation": "support", "matched_queries": ["claim_literal"], "rerank_score": 0.90},
        {"chunk_id": "c4", "evidence_relation": "contradict", "matched_queries": ["counter_probe"], "rerank_score": 0.88},
        {"chunk_id": "c5", "evidence_relation": "insufficient", "matched_queries": ["topic_focus"], "rerank_score": 0.92},
        {"chunk_id": "c6", "evidence_relation": "insufficient", "matched_queries": ["logic_relaxed"], "rerank_score": 0.85},
    ]

    final_list = QualityService._finalize_evidence_list(evidence_list, final_top_k=4)

    assert len(final_list) == 4
    assert [item["chunk_id"] for item in final_list[:2]] == ["c2", "c4"]
    assert any(item["chunk_id"] == "c3" for item in final_list)


def test_quality_service_should_keep_one_support_evidence_when_contradictions_dominate() -> None:
    """存在明显反证时，最终证据仍应尽量保留一条直接支持证据，便于人工对比。"""

    evidence_list = [
        {"chunk_id": "c1", "evidence_relation": "contradict", "matched_queries": ["counter_probe"], "rerank_score": 0.96},
        {"chunk_id": "c2", "evidence_relation": "contradict", "matched_queries": ["counter_probe", "logic_relaxed"], "rerank_score": 0.95},
        {"chunk_id": "c3", "evidence_relation": "contradict", "matched_queries": ["logic_relaxed"], "rerank_score": 0.94},
        {"chunk_id": "c4", "evidence_relation": "contradict", "matched_queries": ["topic_focus"], "rerank_score": 0.93},
        {"chunk_id": "c5", "evidence_relation": "support", "matched_queries": ["claim_literal"], "rerank_score": 0.80},
    ]

    final_list = QualityService._finalize_evidence_list(evidence_list, final_top_k=4)

    assert len(final_list) == 4
    assert [item["chunk_id"] for item in final_list[:2]] == ["c2", "c1"]
    assert any(item["chunk_id"] == "c5" for item in final_list)


def test_quality_service_should_mark_direct_strict_evidence_as_support() -> None:
    """强约束 Claim 若证据直接覆盖约束本身，应标记为 support 而不是 insufficient。"""

    claim_logic = QualityService._build_claim_logic_snapshot("阿胶只有东阿一家有")
    evidence_list = [
        {
            "chunk_id": "c1",
            "content": "阿胶只有东阿所产最为正宗，其他地区并不具备同等来源。",
            "matched_queries": ["claim_literal"],
        }
    ]

    annotated_items = QualityService._annotate_evidence_relations(
        claim_text="阿胶只有东阿一家有",
        evidence_list=evidence_list,
        claim_logic=claim_logic,
    )

    assert annotated_items[0]["evidence_relation"] == "support"
    assert "唯一性约束" in annotated_items[0]["relation_reason"]


def test_quality_service_should_prefer_more_informative_insufficient_evidence() -> None:
    """补充证据不足项时，应优先保留原句或反证探测相关项，减少纯主题噪声。"""

    evidence_list = [
        {"chunk_id": "c1", "evidence_relation": "contradict", "matched_queries": ["counter_probe"], "rerank_score": 0.99},
        {"chunk_id": "c2", "evidence_relation": "support", "matched_queries": ["claim_literal"], "rerank_score": 0.90},
        {"chunk_id": "c3", "evidence_relation": "insufficient", "matched_queries": ["topic_focus"], "rerank_score": 0.96},
        {"chunk_id": "c4", "evidence_relation": "insufficient", "matched_queries": ["claim_literal"], "rerank_score": 0.80},
        {"chunk_id": "c5", "evidence_relation": "insufficient", "matched_queries": ["counter_probe"], "rerank_score": 0.81},
    ]

    final_list = QualityService._finalize_evidence_list(evidence_list, final_top_k=4)

    assert len(final_list) == 4
    final_ids = [item["chunk_id"] for item in final_list]
    assert "c4" in final_ids
    assert "c5" in final_ids
    assert "c3" not in final_ids


def test_quality_service_should_limit_insufficient_noise_when_conflicts_are_strong() -> None:
    """当矛盾证据已经较强时，最终列表最多补 1 条证据不足，避免噪声过多。"""

    evidence_list = [
        {"chunk_id": "c1", "evidence_relation": "contradict", "matched_queries": ["counter_probe"], "rerank_score": 0.99},
        {"chunk_id": "c2", "evidence_relation": "contradict", "matched_queries": ["logic_relaxed"], "rerank_score": 0.96},
        {"chunk_id": "c3", "evidence_relation": "contradict", "matched_queries": ["claim_literal"], "rerank_score": 0.93},
        {"chunk_id": "c4", "evidence_relation": "insufficient", "matched_queries": ["claim_literal"], "rerank_score": 0.90},
        {"chunk_id": "c5", "evidence_relation": "insufficient", "matched_queries": ["counter_probe"], "rerank_score": 0.89},
        {"chunk_id": "c6", "evidence_relation": "insufficient", "matched_queries": ["topic_focus"], "rerank_score": 0.98},
    ]

    final_list = QualityService._finalize_evidence_list(evidence_list, final_top_k=5)

    assert [item["chunk_id"] for item in final_list[:3]] == ["c1", "c2", "c3"]
    assert len([item for item in final_list if item["evidence_relation"] == "insufficient"]) == 1
    assert len(final_list) == 4


def test_quality_service_should_return_specific_heuristic_reason_for_strict_claim(tmp_path: Path) -> None:
    """强约束 Claim 在无模型时也应返回具体原因，而不是占位词。"""

    db_path = tmp_path / "app.db"
    initialize_database(db_path)
    service = QualityService(db_path)
    service.retrieval_service.hybrid_search = lambda query, top_k=3, doc_uid=None, **kwargs: [  # type: ignore[method-assign]
        {"chunk_id": "chk_only", "doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "东阿所产阿胶最为著名。"}
    ]
    service.retrieval_service.expand_evidence_context = lambda items, **kwargs: items  # type: ignore[method-assign]

    result = service.run_check("阿胶只有东阿一家有", template_id="general_fact_check")

    reason = result["claims"][0]["evidence_reason"]
    assert "唯一性" in reason or "排他" in reason
    assert "heuristic" not in reason
