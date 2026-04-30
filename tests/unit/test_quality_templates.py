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
