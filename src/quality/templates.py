"""程序说明：加载和管理质检 Prompt 模板，支持内置默认模板与本地可扩展模板文件。"""

from __future__ import annotations

import re
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

    DELETED_TEMPLATE_REGISTRY = "_deleted_templates.yaml"

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        self.templates_dir = Path(templates_dir) if templates_dir is not None else Path("templates")

    def list_templates(self) -> list[dict]:
        """列出所有可用模板，优先返回内置模板，再合并本地文件模板。"""

        deleted_template_ids = self._load_deleted_template_ids()
        templates = {
            template_id: self._annotate_template(item.copy(), source_type="builtin", file_path=None)
            for template_id, item in BUILTIN_TEMPLATES.items()
            if template_id not in deleted_template_ids
        }
        for file_path in self._iter_template_files():
            template = self._load_template_file(file_path)
            if template["template_id"] in deleted_template_ids:
                continue
            builtin_template = BUILTIN_TEMPLATES.get(template["template_id"])
            source_type = "builtin_override" if builtin_template else "custom"
            templates[template["template_id"]] = self._annotate_template(
                {**templates.get(template["template_id"], {}), **template},
                source_type=source_type,
                file_path=file_path,
            )

        return [
            {
                "template_id": item["template_id"],
                "template_name": item["template_name"],
                "description": item["description"],
                "rule_tags": item.get("rule_tags", []),
                "retrieval_policy": item.get("retrieval_policy", {}),
                "source_type": item.get("source_type", "builtin"),
                "source_label": item.get("source_label", "内置"),
                "editable": bool(item.get("editable", True)),
                "deletable": bool(item.get("deletable", True)),
                "file_path": item.get("file_path"),
            }
            for item in sorted(templates.values(), key=lambda value: value["template_id"])
        ]

    def get_template(self, template_id: str | None = None) -> dict:
        """读取指定模板；为空时返回默认模板。"""

        if not template_id:
            return self._annotate_template(BUILTIN_TEMPLATES["general_fact_check"].copy(), source_type="builtin", file_path=None)

        deleted_template_ids = self._load_deleted_template_ids()
        if template_id in deleted_template_ids:
            raise NotFoundAppError("质检模板不存在", details={"template_id": template_id})

        builtin_template = BUILTIN_TEMPLATES.get(template_id)
        if builtin_template and not self._iter_template_files():
            return self._annotate_template(builtin_template.copy(), source_type="builtin", file_path=None)

        for file_path in self._iter_template_files():
            template = self._load_template_file(file_path)
            if template["template_id"] == template_id:
                return self._annotate_template(
                    {**(builtin_template or {}), **template},
                    source_type="builtin_override" if builtin_template else "custom",
                    file_path=file_path,
                )

        if builtin_template:
            return self._annotate_template(builtin_template.copy(), source_type="builtin", file_path=None)

        raise NotFoundAppError("质检模板不存在", details={"template_id": template_id})

    def save_template(self, payload: dict) -> dict:
        """新增或更新模板，并持久化到本地 YAML 文件。"""

        template = self._normalize_template_payload(payload)
        file_path = self._get_template_file_path(template["template_id"])
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            yaml.safe_dump(template, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        deleted_template_ids = self._load_deleted_template_ids()
        if template["template_id"] in deleted_template_ids:
            deleted_template_ids.remove(template["template_id"])
            self._save_deleted_template_ids(deleted_template_ids)
        return self.get_template(template["template_id"])

    def delete_template(self, template_id: str) -> dict:
        """删除指定模板；内置模板通过删除标记隐藏，自定义模板删除文件。"""

        normalized_template_id = str(template_id or "").strip()
        if not normalized_template_id:
            raise ValidationAppError("模板 ID 不能为空")

        template = self.get_template(normalized_template_id)
        deleted_template_ids = self._load_deleted_template_ids()
        file_path = self._get_template_file_path(normalized_template_id)
        if file_path.exists():
            file_path.unlink()

        if normalized_template_id in BUILTIN_TEMPLATES:
            if normalized_template_id not in deleted_template_ids:
                deleted_template_ids.append(normalized_template_id)
                self._save_deleted_template_ids(deleted_template_ids)
        elif normalized_template_id in deleted_template_ids:
            deleted_template_ids.remove(normalized_template_id)
            self._save_deleted_template_ids(deleted_template_ids)

        return {"template_id": normalized_template_id, "template_name": template.get("template_name", "")}

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
                and file_path.name != self.DELETED_TEMPLATE_REGISTRY
            ]
        )

    def _get_template_file_path(self, template_id: str) -> Path:
        """根据模板 ID 生成用户模板文件路径。"""

        normalized_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", template_id.strip())
        return self.templates_dir / "quality" / f"{normalized_name}.yaml"

    def _load_deleted_template_ids(self) -> list[str]:
        """读取被显式删除的模板 ID 列表。"""

        registry_path = self.templates_dir / "quality" / self.DELETED_TEMPLATE_REGISTRY
        if not registry_path.exists():
            return []
        try:
            payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValidationAppError("模板删除清单格式错误", details={"file_path": str(registry_path)}) from exc
        if not isinstance(payload, dict):
            return []
        deleted_ids = payload.get("deleted_template_ids", [])
        if not isinstance(deleted_ids, list):
            return []
        return [str(item).strip() for item in deleted_ids if str(item).strip()]

    def _save_deleted_template_ids(self, template_ids: list[str]) -> None:
        """写回被删除的模板 ID 列表。"""

        registry_path = self.templates_dir / "quality" / self.DELETED_TEMPLATE_REGISTRY
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_ids = sorted({str(item).strip() for item in template_ids if str(item).strip()})
        if not normalized_ids:
            if registry_path.exists():
                registry_path.unlink()
            return
        registry_path.write_text(
            yaml.safe_dump({"deleted_template_ids": normalized_ids}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def _normalize_template_payload(self, payload: dict) -> dict:
        """校验并规范化待保存模板。"""

        template_id = str(payload.get("template_id", "")).strip()
        template_name = str(payload.get("template_name", "")).strip()
        system_prompt = str(payload.get("system_prompt", "")).strip()
        user_prompt_template = str(payload.get("user_prompt_template", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not template_id:
            raise ValidationAppError("模板 ID 不能为空")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", template_id):
            raise ValidationAppError("模板 ID 只允许字母、数字、下划线和中划线")
        if not template_name:
            raise ValidationAppError("模板名称不能为空")
        if not system_prompt:
            raise ValidationAppError("系统提示词不能为空")
        if not user_prompt_template:
            raise ValidationAppError("用户提示模板不能为空")

        retrieval_policy = payload.get("retrieval_policy", {}) if isinstance(payload.get("retrieval_policy", {}), dict) else {}
        normalized_policy = {
            "fulltext_top_k": int(retrieval_policy.get("fulltext_top_k", 3)),
            "vector_top_k": int(retrieval_policy.get("vector_top_k", 3)),
            "final_top_k": int(retrieval_policy.get("final_top_k", 3)),
            "use_rerank": bool(retrieval_policy.get("use_rerank", False)),
            "neighbor_window": int(retrieval_policy.get("neighbor_window", 0)),
            "include_section_context": bool(retrieval_policy.get("include_section_context", False)),
            "section_max_chars": int(retrieval_policy.get("section_max_chars", 400)),
        }
        for key in ("fulltext_top_k", "vector_top_k", "final_top_k", "neighbor_window", "section_max_chars"):
            if normalized_policy[key] < 0:
                raise ValidationAppError("检索策略数值不能小于 0", details={"field": key})

        return {
            "template_id": template_id,
            "template_name": template_name,
            "description": description,
            "system_prompt": system_prompt,
            "user_prompt_template": user_prompt_template,
            "rule_tags": [str(item).strip() for item in payload.get("rule_tags", []) if str(item).strip()]
            if isinstance(payload.get("rule_tags", []), list)
            else [],
            "retrieval_policy": normalized_policy,
        }

    @staticmethod
    def _annotate_template(template: dict, *, source_type: str, file_path: Path | None) -> dict:
        """补充模板来源与可编辑属性。"""

        source_mapping = {
            "builtin": "内置",
            "builtin_override": "覆盖内置",
            "custom": "自定义",
        }
        return {
            **template,
            "source_type": source_type,
            "source_label": source_mapping.get(source_type, source_type),
            "editable": True,
            "deletable": True,
            "file_path": str(file_path) if file_path else "",
        }

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
