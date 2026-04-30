"""程序说明：验证规则等级对质检结论的影响。"""

from pathlib import Path

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
    assert captured_search_kwargs["fulltext_top_k"] == 6
    assert captured_search_kwargs["vector_top_k"] == 6
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
template_name: 通用事实核验
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
