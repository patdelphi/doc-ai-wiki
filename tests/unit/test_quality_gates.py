"""程序说明：验证静态检查配置不会重新跳过已治理的检索模块。"""

from __future__ import annotations

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
