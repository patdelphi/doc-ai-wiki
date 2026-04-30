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
    service.retrieval_service.hybrid_search = lambda query, top_k=3: [  # type: ignore[method-assign]
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
    service.retrieval_service.hybrid_search = lambda query, top_k=3: [  # type: ignore[method-assign]
        {"doc_uid": "doc_1", "source_span": "section-1:chunk-0", "content": "证据内容"}
    ]

    result = service.run_check("这段内容禁止发布。")

    assert result["claims"][0]["verdict"] == "rejected"
    assert result["check"]["risk_level"] == "high"
    assert result["rule_hits"][0]["hit_level"] == "block"
