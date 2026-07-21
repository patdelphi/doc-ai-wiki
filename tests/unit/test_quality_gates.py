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


def test_search_page_handlers_should_not_be_nested_in_build_ui() -> None:
    """检索页处理器迁出后不得重新嵌套回 UI 总装配函数。"""

    project_root = Path(__file__).resolve().parents[2]
    source = (project_root / "src" / "ui" / "pages.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    build_ui = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "build_ui"
    )
    nested_names = {
        node.name
        for node in ast.walk(build_ui)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not build_ui
    }
    migrated_handlers = {
        "build_search_table_page_outputs",
        "build_search_detail_payload",
        "build_search_detail",
        "export_search_results",
        "run_search",
        "run_search_ui",
        "reset_search_workspace_ui",
        "change_search_page",
        "select_search_result",
    }

    assert nested_names.isdisjoint(migrated_handlers)


def test_source_comments_should_explain_invariants_instead_of_ticket_labels() -> None:
    """源码注释不应只保留无法追溯的历史缺陷编号。"""

    project_root = Path(__file__).resolve().parents[2]
    source_text = "\n".join(
        path.read_text(encoding="utf-8-sig")
        for path in (project_root / "src").rglob("*.py")
    )

    for ticket_label in ("H7 修复", "M3 修复", "C5 修复"):
        assert ticket_label not in source_text


def test_ci_should_lint_archived_migration_scripts() -> None:
    """CI 与 PR 清单必须覆盖仍保存在仓库中的历史迁移脚本。"""

    project_root = Path(__file__).resolve().parents[2]
    expected_command = "python -m ruff check src tests .aipython Docs/migrations"
    workflow = (project_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8-sig")
    pull_request_template = (project_root / ".github" / "pull_request_template.md").read_text(encoding="utf-8-sig")

    assert expected_command in workflow
    assert expected_command in pull_request_template


def test_pageindex_service_should_not_own_history_export_formatters() -> None:
    """PageIndex 巨型服务不得重新吸收已迁移的历史导出纯函数。"""

    project_root = Path(__file__).resolve().parents[2]
    source = (project_root / "src" / "pageindex" / "service.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    service_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PageIndexService"
    )
    method_names = {
        node.name
        for node in service_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    migrated_methods = {
        "_parse_history_rows",
        "_format_history_markdown",
        "_format_history_answer_markdown",
        "_parse_structured_answer",
        "_format_markdown_value",
        "_format_markdown_list_item",
        "_stringify_markdown_scalar",
        "_history_question_type",
    }

    assert method_names.isdisjoint(migrated_methods)


def test_pageindex_service_should_not_own_persistence_sql_or_private_read_wrappers() -> None:
    """PageIndex 持久化迁出后，服务不得重新包含自有表 SQL 或读取包装层。"""

    project_root = Path(__file__).resolve().parents[2]
    service_path = project_root / "src" / "pageindex" / "service.py"
    repository_path = project_root / "src" / "pageindex" / "index_repository.py"
    service_source = service_path.read_text(encoding="utf-8-sig")
    repository_source = repository_path.read_text(encoding="utf-8-sig")
    service_tree = ast.parse(service_source)
    service_class = next(
        node
        for node in service_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PageIndexService"
    )
    service_method_names = {
        node.name
        for node in service_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "pageindex_indexes" not in service_source
    assert "pageindex_query_history" not in service_source
    assert {"_get_index_record", "_list_index_records"}.isdisjoint(service_method_names)
    assert "src.pageindex.service" not in repository_source


def test_pageindex_service_should_not_own_deterministic_tree_retrieval_algorithms() -> None:
    """确定性树检索迁出后，服务不得保留包装方法或重复实现。"""

    project_root = Path(__file__).resolve().parents[2]
    service_path = project_root / "src" / "pageindex" / "service.py"
    retriever_path = project_root / "src" / "pageindex" / "tree_retriever.py"
    service_source = service_path.read_text(encoding="utf-8-sig")
    retriever_source = retriever_path.read_text(encoding="utf-8-sig")
    service_tree = ast.parse(service_source)
    retriever_tree = ast.parse(retriever_source)
    service_class = next(
        node
        for node in service_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PageIndexService"
    )
    service_method_names = {
        node.name
        for node in service_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    migrated_methods = {
        "_extract_cross_reference_targets",
        "_find_cross_reference_candidates",
        "_merge_tree_candidates",
        "_flatten_structure_static",
        "_score_node",
        "_penalize_generic_front_matter",
        "_candidate_to_debug",
        "_flatten_structure",
        "_format_node_position",
    }
    forbidden_dependencies = {
        "src.pageindex.service",
        "src.pageindex.client",
        "src.ai",
        "src.db",
        "src.common.config",
    }
    retriever_imports = {
        alias.name
        for node in ast.walk(retriever_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        str(node.module or "")
        for node in ast.walk(retriever_tree)
        if isinstance(node, ast.ImportFrom)
    }
    retriever_function_names = [
        node.name
        for node in retriever_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    assert service_method_names.isdisjoint(migrated_methods)
    assert service_method_names & {"_build_tree_candidates"} == {"_build_tree_candidates"}
    assert forbidden_dependencies.isdisjoint(retriever_imports)
    assert retriever_function_names.count("flatten_structure") == 1
    assert "PageIndexClient" not in retriever_source


def test_pageindex_service_should_delegate_final_answer_orchestration() -> None:
    """最终回答迁出后，服务不得保留包装方法、旧单轮路径或反向依赖。"""

    project_root = Path(__file__).resolve().parents[2]
    service_path = project_root / "src" / "pageindex" / "service.py"
    orchestrator_path = project_root / "src" / "pageindex" / "answer_orchestrator.py"
    service_source = service_path.read_text(encoding="utf-8-sig")
    orchestrator_source = orchestrator_path.read_text(encoding="utf-8-sig")
    service_tree = ast.parse(service_source)
    orchestrator_tree = ast.parse(orchestrator_source)
    service_class = next(
        node
        for node in service_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PageIndexService"
    )
    service_method_names = {
        node.name
        for node in service_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    migrated_methods = {
        "_generate_llm_answer",
        "_generate_llm_answer_payload",
        "_build_question_plan",
        "_build_answer_structure_context",
        "_build_local_answer",
        "_classify_evidence_items",
        "_classify_single_evidence",
        "_build_local_evidence_judgement",
        "_build_local_evidence_points",
        "_build_local_source_points",
        "_infer_local_conclusion",
        "_infer_local_uncertainty",
        "_is_benefit_or_treatment_question",
        "_is_formula_context_for_single_herb_question",
        "_answer_with_llm_tree_reasoning",
        "_build_tree_reasoning_prompts",
    }
    orchestrator_imports = {
        alias.name
        for node in ast.walk(orchestrator_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        str(node.module or "")
        for node in ast.walk(orchestrator_tree)
        if isinstance(node, ast.ImportFrom)
    }
    forbidden_dependencies = {
        "src.pageindex.service",
        "src.db",
        "src.retrieval",
        "src.common.config",
        "pageindex",
    }

    assert service_method_names.isdisjoint(migrated_methods)
    assert service_source.count("PageIndexAnswerOrchestrator(") == 1
    assert not any(
        imported == forbidden or imported.startswith(f"{forbidden}.")
        for imported in orchestrator_imports
        for forbidden in forbidden_dependencies
    )
    assert "PageIndexClient" not in orchestrator_source
