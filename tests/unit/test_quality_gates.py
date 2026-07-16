"""程序说明：验证静态检查配置不会重新跳过已治理的检索模块。"""

from __future__ import annotations

import ast
from pathlib import Path
import tomllib


def test_mypy_should_check_governed_retrieval_modules() -> None:
    """已治理模块和检索/PageIndex目录不能被 Mypy 豁免。"""

    project_root = Path(__file__).resolve().parents[2]
    with (project_root / "pyproject.toml").open("rb") as file:
        config = tomllib.load(file)

    ignored_modules: set[str] = set()
    for override in config.get("tool", {}).get("mypy", {}).get("overrides", []):
        if not override.get("ignore_errors"):
            continue
        modules = override.get("module", [])
        ignored_modules.update([modules] if isinstance(modules, str) else modules)

    assert "src.retrieval.service" not in ignored_modules
    assert "src.retrieval.vector_store" not in ignored_modules
    assert "src.retrieval.*" not in ignored_modules
    assert "src.pageindex.*" not in ignored_modules


def test_ui_should_not_define_duplicate_tab_access_helpers() -> None:
    """UI 总装配函数只应保留一个主菜单权限判断实现。"""

    project_root = Path(__file__).resolve().parents[2]
    source = (project_root / "src" / "ui" / "pages.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    helper_definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_has_tab_access"
    ]

    assert len(helper_definitions) == 1


def test_ui_should_not_disable_unused_code_checks() -> None:
    """已清理文件必须持续接受 F401/F841 检查。"""

    project_root = Path(__file__).resolve().parents[2]
    with (project_root / "pyproject.toml").open("rb") as file:
        config = tomllib.load(file)

    per_file_ignores = config["tool"]["ruff"]["lint"]["per-file-ignores"]
    for file_path in ("src/ui/pages.py", "tests/unit/test_ui.py", "src/auth/service.py"):
        ignored_rules = per_file_ignores.get(file_path, [])
        assert "F401" not in ignored_rules
        assert "F841" not in ignored_rules

