"""程序说明：验证质检模板加载、默认回退和本地模板扩展能力。"""

from __future__ import annotations

from pathlib import Path


def test_quality_template_service_should_return_builtin_and_custom_templates(tmp_path: Path) -> None:
    """模板服务应返回内置模板，并合并本地模板文件。"""

    from src.quality.templates import QualityTemplateService

    quality_dir = tmp_path / "templates" / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)
    (quality_dir / "custom.yaml").write_text(
        """
template_id: custom_review
template_name: 自定义复核
description: 自定义模板
system_prompt: 你是自定义模板。
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

    service = QualityTemplateService(tmp_path / "templates")
    items = service.list_templates()

    template_ids = {item["template_id"] for item in items}
    assert "general_fact_check" in template_ids
    assert "custom_review" in template_ids


def test_quality_template_service_should_load_selected_template(tmp_path: Path) -> None:
    """按 template_id 应能读取指定模板内容。"""

    from src.quality.templates import QualityTemplateService

    quality_dir = tmp_path / "templates" / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)
    (quality_dir / "ancient.yaml").write_text(
        """
template_id: ancient_review
template_name: 古文模板
description: 古文场景
system_prompt: 古文系统提示
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

    service = QualityTemplateService(tmp_path / "templates")
    template = service.get_template("ancient_review")

    assert template["template_name"] == "古文模板"
    assert "古文系统提示" in template["system_prompt"]


def test_quality_template_service_should_support_upsert_and_delete_custom_template(tmp_path: Path) -> None:
    """模板服务应支持新增、更新和删除自定义模板。"""

    from src.common.errors import NotFoundAppError
    from src.quality.templates import QualityTemplateService

    service = QualityTemplateService(tmp_path / "templates")
    service.save_template(
        {
            "template_id": "custom_review",
            "template_name": "自定义模板",
            "description": "第一次保存",
            "system_prompt": "系统提示 A",
            "user_prompt_template": "用户提示 A",
            "rule_tags": ["general", "strict"],
            "retrieval_policy": {
                "fulltext_top_k": 4,
                "vector_top_k": 5,
                "final_top_k": 3,
                "use_rerank": True,
                "neighbor_window": 1,
                "include_section_context": False,
                "section_max_chars": 500,
            },
        }
    )

    created_template = service.get_template("custom_review")
    service.save_template(
        {
            **created_template,
            "template_name": "自定义模板-更新",
            "description": "第二次保存",
        }
    )
    updated_template = service.get_template("custom_review")
    service.delete_template("custom_review")

    assert created_template["template_name"] == "自定义模板"
    assert updated_template["template_name"] == "自定义模板-更新"
    assert updated_template["description"] == "第二次保存"
    assert all(item["template_id"] != "custom_review" for item in service.list_templates())

    try:
        service.get_template("custom_review")
        assert False, "删除后不应还能读取模板"
    except NotFoundAppError:
        assert True


def test_quality_template_service_should_allow_deleting_builtin_template(tmp_path: Path) -> None:
    """按当前策略，内置模板也应支持删除并持久化删除状态。"""

    from src.common.errors import NotFoundAppError
    from src.quality.templates import QualityTemplateService

    service = QualityTemplateService(tmp_path / "templates")

    assert any(item["template_id"] == "general_fact_check" for item in service.list_templates())

    service.delete_template("general_fact_check")

    assert all(item["template_id"] != "general_fact_check" for item in service.list_templates())

    try:
        service.get_template("general_fact_check")
        assert False, "删除后的内置模板不应继续可读"
    except NotFoundAppError:
        assert True
