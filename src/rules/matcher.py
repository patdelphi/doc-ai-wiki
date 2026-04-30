"""程序说明：执行基于关键词的最小规则匹配。"""

from __future__ import annotations


def match_rules(claim_text: str, rules: list[dict]) -> list[dict]:
    """对单条 claim 执行关键词命中。"""

    hits: list[dict] = []
    for rule in rules:
        keywords = rule.get("keywords", [])
        if not isinstance(keywords, list):
            continue

        matched_keyword = next((keyword for keyword in keywords if keyword and keyword in claim_text), None)
        if not matched_keyword:
            continue

        hits.append(
            {
                "rule_code": rule.get("code", ""),
                "rule_name": rule.get("name", ""),
                "hit_level": rule.get("hit_level", "warn"),
                "hit_message": rule.get("message", f"命中规则关键词：{matched_keyword}"),
                "matched_keyword": matched_keyword,
            }
        )
    return hits
