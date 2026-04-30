"""程序说明：加载和管理质检 Prompt 模板，支持内置默认模板与本地可扩展模板文件。"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.common.errors import NotFoundAppError, ValidationAppError


BUILTIN_TEMPLATES = {
    "general_fact_check": {
        "template_id": "general_fact_check",
        "template_name": "通用事实核验",
        "description": "适合大多数知识库文本质检，平衡证据核验、规则命中与人工复核。",
        "system_prompt": """你是中文知识库质检助手。
请基于给定 claim、证据片段与规则命中结果，输出 JSON：
{
  "verdict": "verified|needs_review|rejected",
  "confidence": 0.0,
  "risk_level": "low|medium|high",
  "reason": "简短中文原因"
}
要求：
1. 没有足够证据时不要输出 verified。
2. 命中高风险规则时，风险等级不能低于规则等级。
3. 只输出 JSON，不要输出额外说明。""",
        "user_prompt_template": """任务：请核验以下 claim 是否能被知识库证据支持。

Claim:
{claim_text}

证据：
{evidence_block}

规则命中：
{rule_block}

请严格返回 JSON，不要输出解释性段落。""",
        "rule_tags": ["general"],
        "retrieval_policy": {
            "fulltext_top_k": 3,
            "vector_top_k": 3,
            "final_top_k": 3,
            "use_rerank": False,
            "neighbor_window": 0,
            "include_section_context": False,
            "section_max_chars": 400,
        },
    },
    "strict_evidence_check": {
        "template_id": "strict_evidence_check",
        "template_name": "严格证据核验",
        "description": "更强调证据充分性，证据不足时优先给出 needs_review，不轻易放行。",
        "system_prompt": """你是严格型中文知识库质检助手。
你只能依据证据片段和规则命中做判断，禁止脑补常识。
输出 JSON：
{
  "verdict": "verified|needs_review|rejected",
  "confidence": 0.0,
  "risk_level": "low|medium|high",
  "reason": "简短中文原因"
}
规则：
1. 证据不能直接支持 claim 时，必须输出 needs_review 或 rejected。
2. 若 claim 比证据更绝对、更宽泛，不能判定为 verified。
3. 只输出 JSON。""",
        "user_prompt_template": """你现在执行严格证据核验。

待核验 Claim：
{claim_text}

可用证据：
{evidence_block}

规则命中：
{rule_block}

请优先关注证据是否直接、完整、可追溯。""",
        "rule_tags": ["general", "strict"],
        "retrieval_policy": {
            "fulltext_top_k": 5,
            "vector_top_k": 5,
            "final_top_k": 5,
            "use_rerank": True,
            "neighbor_window": 1,
            "include_section_context": False,
            "section_max_chars": 500,
        },
    },
    "ancient_text_review": {
        "template_id": "ancient_text_review",
        "template_name": "古文审慎解读",
        "description": "面向古文、古籍摘录或含歧义的旧文体，强调不确定性与语义保守解释。",
        "system_prompt": """你是古文知识库质检助手。
处理古文、古籍摘录或文言文时，必须谨慎解释，避免把含混表述直接现代化定论。
输出 JSON：
{
  "verdict": "verified|needs_review|rejected",
  "confidence": 0.0,
  "risk_level": "low|medium|high",
  "reason": "简短中文原因"
}
要求：
1. 证据存在歧义、异文、断句差异时，优先输出 needs_review。
2. 不允许把推测性训释当作确定事实。
3. 只输出 JSON。""",
        "user_prompt_template": """请按古文审慎解读模式核验下述内容。

Claim：
{claim_text}

证据摘录：
{evidence_block}

规则命中：
{rule_block}

请重点说明是否存在词义歧义、断句歧义或现代转述过度。""",
        "rule_tags": ["ancient", "strict"],
        "retrieval_policy": {
            "fulltext_top_k": 5,
            "vector_top_k": 4,
            "final_top_k": 4,
            "use_rerank": True,
            "neighbor_window": 1,
            "include_section_context": True,
            "section_max_chars": 500,
        },
    },
    "medical_safety_review": {
        "template_id": "medical_safety_review",
        "template_name": "医学内容审慎质检",
        "description": "面向医学、方药、疗效、安全性描述，强调风险、禁忌与证据等级。",
        "system_prompt": """你是医学内容质检助手。
对疗效、适应症、安全性、禁忌、剂量等内容必须审慎判断。
输出 JSON：
{
  "verdict": "verified|needs_review|rejected",
  "confidence": 0.0,
  "risk_level": "low|medium|high",
  "reason": "简短中文原因"
}
要求：
1. 对绝对疗效、明确治愈、无副作用等说法从严处理。
2. 若证据仅为经验表述、缺少边界条件或禁忌说明，优先输出 needs_review。
3. 涉及明显高风险误导时可输出 rejected。
4. 只输出 JSON。""",
        "user_prompt_template": """请按医学内容审慎质检模板核验以下 claim。

Claim：
{claim_text}

检索证据：
{evidence_block}

规则命中：
{rule_block}

请重点关注疗效绝对化、安全性遗漏、适用范围夸大、禁忌缺失等问题。""",
        "rule_tags": ["medical", "strict"],
        "retrieval_policy": {
            "fulltext_top_k": 6,
            "vector_top_k": 6,
            "final_top_k": 5,
            "use_rerank": True,
            "neighbor_window": 1,
            "include_section_context": True,
            "section_max_chars": 600,
        },
    },
}


class QualityTemplateService:
    """质检模板管理服务。"""

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        self.templates_dir = Path(templates_dir) if templates_dir is not None else Path("templates")

    def list_templates(self) -> list[dict]:
        """列出所有可用模板，优先返回内置模板，再合并本地文件模板。"""

        templates = {template_id: item.copy() for template_id, item in BUILTIN_TEMPLATES.items()}
        for file_path in self._iter_template_files():
            template = self._load_template_file(file_path)
            templates[template["template_id"]] = {**templates.get(template["template_id"], {}), **template}

        return [
            {
                "template_id": item["template_id"],
                "template_name": item["template_name"],
                "description": item["description"],
                "rule_tags": item.get("rule_tags", []),
                "retrieval_policy": item.get("retrieval_policy", {}),
            }
            for item in sorted(templates.values(), key=lambda value: value["template_id"])
        ]

    def get_template(self, template_id: str | None = None) -> dict:
        """读取指定模板；为空时返回默认模板。"""

        if not template_id:
            return BUILTIN_TEMPLATES["general_fact_check"].copy()

        builtin_template = BUILTIN_TEMPLATES.get(template_id)
        if builtin_template and not self._iter_template_files():
            return builtin_template.copy()

        for file_path in self._iter_template_files():
            template = self._load_template_file(file_path)
            if template["template_id"] == template_id:
                return {**(builtin_template or {}), **template}

        if builtin_template:
            return builtin_template.copy()

        raise NotFoundAppError("质检模板不存在", details={"template_id": template_id})

    def _iter_template_files(self) -> list[Path]:
        """遍历模板目录下的质检模板文件。"""

        quality_dir = self.templates_dir / "quality"
        if not quality_dir.exists():
            return []
        return sorted(
            [
                file_path
                for file_path in quality_dir.rglob("*")
                if file_path.is_file() and file_path.suffix.lower() in {".yaml", ".yml"}
            ]
        )

    @staticmethod
    def _load_template_file(file_path: Path) -> dict:
        """读取并校验单个模板文件。"""

        try:
            payload = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValidationAppError(
                "质检模板格式错误",
                details={"file_path": str(file_path)},
            ) from exc

        if not isinstance(payload, dict):
            raise ValidationAppError("质检模板内容必须是对象", details={"file_path": str(file_path)})

        template = {
            "template_id": str(payload.get("template_id", file_path.stem)).strip(),
            "template_name": str(payload.get("template_name", file_path.stem)).strip(),
            "description": str(payload.get("description", "")).strip(),
            "system_prompt": str(payload.get("system_prompt", "")).strip(),
            "user_prompt_template": str(payload.get("user_prompt_template", "")).strip(),
            "rule_tags": [str(item).strip() for item in payload.get("rule_tags", []) if str(item).strip()]
            if isinstance(payload.get("rule_tags", []), list)
            else [],
            "retrieval_policy": payload.get("retrieval_policy", {})
            if isinstance(payload.get("retrieval_policy", {}), dict)
            else {},
        }
        missing_fields = [
            field_name
            for field_name in ("template_id", "template_name", "system_prompt", "user_prompt_template")
            if not template[field_name]
        ]
        if missing_fields:
            raise ValidationAppError(
                "质检模板缺少必要字段",
                details={"file_path": str(file_path), "missing_fields": missing_fields},
            )
        return template
