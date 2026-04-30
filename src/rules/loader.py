"""程序说明：从规则目录加载 YAML 规则配置。"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_rule_files(rules_dir: Path) -> list[dict]:
    """读取规则目录下的 YAML 文件。"""

    if not rules_dir.exists():
        return []

    rules: list[dict] = []
    for file_path in sorted(rules_dir.glob("*.y*ml")):
        content = yaml.safe_load(file_path.read_text(encoding="utf-8")) or []
        if isinstance(content, list):
            rules.extend(item for item in content if isinstance(item, dict))
    return rules
