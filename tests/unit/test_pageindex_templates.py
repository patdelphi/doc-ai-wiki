"""程序说明：验证 PageIndex 回答模板加载、保存、删除和提示词渲染能力。"""

from __future__ import annotations

from pathlib import Path


def test_pageindex_template_service_should_return_builtin_and_custom_templates(tmp_path: Path) -> None:
    """PageIndex 模板服务应返回内置模板，并合并本地自定义模板。"""

    from src.pageindex.templates import PageIndexTemplateService

    template_dir = tmp_path / "templates" / "pageindex"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "custom.yaml").write_text(
        """
template_id: custom_pageindex_qa
template_name: 自定义 PageIndex 问答
description: 自定义答案风格
answer_mode: custom
system_prompt: 你是自定义 PageIndex 问答助手。
user_prompt_template: |
  问题：
  {question}
  证据：
  {evidence_json}
  结构：
  {structure_context}
  证据判断：
  {evidence_judgement}
  引用规则：
  {citation_rules}
""".strip(),
        encoding="utf-8",
    )

    service = PageIndexTemplateService(tmp_path / "templates")
    items = service.list_templates()

    template_ids = {item["template_id"] for item in items}
    assert "strict_qa" in template_ids
    assert "medical_safety_qa" in template_ids
    assert "source_locator" in template_ids
    assert "custom_pageindex_qa" in template_ids


def test_pageindex_template_service_should_support_upsert_and_delete_custom_template(tmp_path: Path) -> None:
    """PageIndex 模板服务应支持新增、更新和删除自定义 YAML 模板。"""

    from src.common.errors import NotFoundAppError
    from src.pageindex.templates import PageIndexTemplateService

    service = PageIndexTemplateService(tmp_path / "templates")
    service.save_template(
        {
            "template_id": "custom_pageindex_qa",
            "template_name": "自定义 PageIndex 问答",
            "description": "第一次保存",
            "answer_mode": "custom",
            "system_prompt": "系统提示 A",
            "user_prompt_template": "问题：{question}\n证据：{evidence_json}\n结构：{structure_context}\n证据判断：{evidence_judgement}\n引用规则：{citation_rules}",
            "retrieval_policy": {
                "max_tree_candidates": 24,
                "max_selected_nodes": 4,
                "max_rag_evidence": 3,
                "include_structure_context": True,
            },
        }
    )

    created = service.get_template("custom_pageindex_qa")
    service.save_template({**created, "template_name": "自定义 PageIndex 问答-更新", "description": "第二次保存"})
    updated = service.get_template("custom_pageindex_qa")
    service.delete_template("custom_pageindex_qa")

    assert created["template_name"] == "自定义 PageIndex 问答"
    assert updated["template_name"] == "自定义 PageIndex 问答-更新"
    assert updated["retrieval_policy"]["max_selected_nodes"] == 4
    assert all(item["template_id"] != "custom_pageindex_qa" for item in service.list_templates())

    try:
        service.get_template("custom_pageindex_qa")
        assert False, "删除后不应还能读取 PageIndex 模板"
    except NotFoundAppError:
        assert True


def test_pageindex_template_service_should_render_prompt_with_pageindex_variables(tmp_path: Path) -> None:
    """PageIndex 模板应支持问题、证据、结构、证据判断和引用规则变量。"""

    from src.pageindex.templates import PageIndexTemplateService

    service = PageIndexTemplateService(tmp_path / "templates")
    template = service.get_template("strict_qa")

    system_prompt, user_prompt = service.render_answer_prompts(
        template,
        question="心脏病吃阿胶有好处",
        evidence=[
            {
                "title": "阿胶应用的注意点（禁忌）",
                "evidence_label": "风险提醒",
                "content": "必须在医师指导下正确服用，否则会有不良反应。",
            }
        ],
        structure_context="阿胶应用 > 禁忌",
        evidence_judgement="风险提醒：阿胶应用的注意点（禁忌）",
        citation_rules="必须列出标题和位置。",
        question_plan={"question_type": "claim_judgement", "target": "心脏病吃阿胶有好处"},
    )

    assert "严谨的 PageIndex" in system_prompt
    assert "心脏病吃阿胶有好处" in user_prompt
    assert "风险提醒" in user_prompt
    assert "claim_judgement" in user_prompt
    assert "阿胶应用 > 禁忌" in user_prompt
    assert "必须列出标题和位置" in user_prompt


def test_pageindex_builtin_templates_should_explain_generic_evidence_relations(tmp_path: Path) -> None:
    """内置模板应要求 LLM 按通用证据关系判断，而不是只输出相关证据摘要。"""

    from src.pageindex.templates import PageIndexTemplateService

    service = PageIndexTemplateService(tmp_path / "templates")
    template = service.get_template("strict_qa")

    joined_prompt = f'{template["system_prompt"]}\n{template["user_prompt_template"]}'

    assert "direct_support" in joined_prompt
    assert "direct_refute" in joined_prompt
    assert "method_or_formula_context" in joined_prompt
    assert "context_only" in joined_prompt
    assert "不能证明用户命题" in joined_prompt


def test_pageindex_template_service_should_ignore_evidence_judge_rule_file(tmp_path: Path) -> None:
    """PageIndex 模板目录中的 Evidence Judge 规则文件不应被当成回答模板加载。"""

    from src.pageindex.templates import PageIndexTemplateService

    rule_dir = tmp_path / "templates" / "pageindex"
    rule_dir.mkdir(parents=True)
    (rule_dir / "evidence_judge.yaml").write_text(
        """
markers:
  support:
    - 形成依据
""".strip(),
        encoding="utf-8",
    )

    service = PageIndexTemplateService(tmp_path / "templates")
    template_ids = {item["template_id"] for item in service.list_templates()}

    assert "strict_qa" in template_ids
    assert "evidence_judge" not in template_ids
