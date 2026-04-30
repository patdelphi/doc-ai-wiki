"""程序说明：规则服务入口，负责加载规则并执行匹配。"""

from __future__ import annotations

from pathlib import Path

from src.rules.loader import load_rule_files
from src.rules.matcher import match_rules


class RuleService:
    """规则服务。"""

    def __init__(self, rules_dir: Path) -> None:
        self.rules_dir = rules_dir

    def list_rules(self, active_tags: list[str] | None = None) -> list[dict]:
        """返回当前可用规则。"""

        rules = load_rule_files(self.rules_dir)
        if not active_tags:
            return rules
        return [
            rule
            for rule in rules
            if not isinstance(rule.get("template_tags"), list)
            or not rule.get("template_tags")
            or bool(set(active_tags) & {str(item).strip() for item in rule.get("template_tags", []) if str(item).strip()})
        ]

    def match_claim(self, claim_text: str, active_tags: list[str] | None = None) -> list[dict]:
        """对 claim 执行规则匹配。"""

        return match_rules(claim_text, self.list_rules(active_tags), active_tags=active_tags)
