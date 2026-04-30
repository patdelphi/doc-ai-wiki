"""程序说明：验证第一版规则引擎最小命中逻辑。"""

from pathlib import Path

from src.rules.service import RuleService


def test_rule_service_should_match_keywords_from_yaml(tmp_path: Path) -> None:
    """规则目录中存在关键词规则时，应返回命中结果。"""

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "base_rules.yaml").write_text(
        """
- code: R001
  name: 绝对化表述
  keywords:
    - 绝对
    - 完全
  hit_level: warn
  message: 包含绝对化表述，建议人工复核
""".strip(),
        encoding="utf-8",
    )

    service = RuleService(rules_dir)
    hits = service.match_claim("这个说法绝对正确")

    assert len(hits) == 1
    assert hits[0]["rule_code"] == "R001"
    assert hits[0]["hit_level"] == "warn"


def test_rule_service_should_filter_rules_by_template_tags(tmp_path: Path) -> None:
    """按模板标签过滤时，只应命中当前模板启用的规则。"""

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

    service = RuleService(rules_dir)
    hits = service.match_claim("这个说法一定能治愈所有人", active_tags=["medical"])

    assert len(hits) == 1
    assert hits[0]["rule_code"] == "M001"
