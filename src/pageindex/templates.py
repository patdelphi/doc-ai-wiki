"""程序说明：管理 PageIndex 回答模板，支持内置模板与本地 YAML 扩展。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from src.common.errors import NotFoundAppError, ValidationAppError


BUILTIN_PAGEINDEX_TEMPLATES = {
    "strict_qa": {
        "template_id": "strict_qa",
        "template_name": "严谨问答",
        "description": "默认 PageIndex 问答模板，强调结论、证据判断、依据、来源和不确定点。",
        "answer_mode": "strict_qa",
        "system_prompt": """你是严谨的 PageIndex 文档问答助手。
只能基于给定证据回答，必须先判断证据是否支持用户命题本身，不能把相关背景当作直接支持。
证据关系类型包括：direct_support、direct_refute、partial_support、context_only、example_only、method_or_formula_context、risk_or_condition、insufficient。
如果证据只是 context_only、example_only 或 method_or_formula_context，必须明确说明不能证明用户命题。
回答必须包含：结论、证据判断、依据、来源、不确定点。
只返回 JSON：{"answer":"..."}。""",
        "user_prompt_template": """用户问题：
{question}

证据 JSON：
{evidence_json}

Question Plan JSON：
{question_plan}

PageIndex 结构上下文：
{structure_context}

证据判断：
{evidence_judgement}

引用规则：
{citation_rules}

请直接回答用户问题。证据不足或不能证明用户命题时必须明确说明，不能让用户自行阅读证据后判断。""",
        "retrieval_policy": {
            "max_tree_candidates": 30,
            "max_selected_nodes": 3,
            "max_rag_evidence": 2,
            "include_structure_context": True,
        },
    },
    "medical_safety_qa": {
        "template_id": "medical_safety_qa",
        "template_name": "医学安全问答",
        "description": "面向疗效、安全性、禁忌、人群边界问题，默认从严判断。",
        "answer_mode": "medical_safety",
        "system_prompt": """你是医学安全导向的 PageIndex 问答助手。
涉及疾病、疗效、用药、禁忌、人群边界时必须保守回答。
先使用通用证据关系判断：direct_support、direct_refute、partial_support、context_only、example_only、method_or_formula_context、risk_or_condition、insufficient。
间接相关、方剂语境、经验表述不能当作明确疗效证据；method_or_formula_context 不能证明用户问的单项命题。
只返回 JSON：{"answer":"..."}。""",
        "user_prompt_template": """医学相关问题：
{question}

证据 JSON：
{evidence_json}

Question Plan JSON：
{question_plan}

结构上下文：
{structure_context}

证据判断：
{evidence_judgement}

引用规则：
{citation_rules}

请输出：结论、证据判断、依据、来源、不确定点。不得给出替代医生诊断的建议。""",
        "retrieval_policy": {
            "max_tree_candidates": 36,
            "max_selected_nodes": 4,
            "max_rag_evidence": 3,
            "include_structure_context": True,
        },
    },
    "source_locator": {
        "template_id": "source_locator",
        "template_name": "原文定位",
        "description": "只定位原文和结构位置，不生成超出证据的判断。",
        "answer_mode": "source_locator",
        "system_prompt": """你是 PageIndex 原文定位助手。
只说明命中的文档、章节、位置和原文摘要，不做额外结论。
如需描述关系，只能使用 direct_support、direct_refute、partial_support、context_only、example_only、method_or_formula_context、risk_or_condition、insufficient。
只返回 JSON：{"answer":"..."}。""",
        "user_prompt_template": """定位问题：
{question}

证据 JSON：
{evidence_json}

Question Plan JSON：
{question_plan}

结构上下文：
{structure_context}

证据判断：
{evidence_judgement}

引用规则：
{citation_rules}

请只输出定位结果和引用。""",
        "retrieval_policy": {
            "max_tree_candidates": 30,
            "max_selected_nodes": 5,
            "max_rag_evidence": 3,
            "include_structure_context": True,
        },
    },
}


class PageIndexTemplateService:
    """PageIndex 回答模板管理服务。"""

    DELETED_TEMPLATE_REGISTRY = "_deleted_templates.yaml"
    RULE_FILE_NAMES = {"evidence_judge.yaml", "evidence_judge.yml"}

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        self.templates_dir = Path(templates_dir) if templates_dir is not None else Path("templates")

    def list_templates(self) -> list[dict]:
        """列出 PageIndex 内置模板和本地自定义模板。"""

        deleted_template_ids = self._load_deleted_template_ids()
        templates = {
            template_id: self._annotate_template(item.copy(), source_type="builtin", file_path=None)
            for template_id, item in BUILTIN_PAGEINDEX_TEMPLATES.items()
            if template_id not in deleted_template_ids
        }
        for file_path in self._iter_template_files():
            template = self._load_template_file(file_path)
            if template["template_id"] in deleted_template_ids:
                continue
            builtin_template = BUILTIN_PAGEINDEX_TEMPLATES.get(template["template_id"])
            templates[template["template_id"]] = self._annotate_template(
                {**templates.get(template["template_id"], {}), **template},
                source_type="builtin_override" if builtin_template else "custom",
                file_path=file_path,
            )
        return [
            {
                "template_id": item["template_id"],
                "template_name": item["template_name"],
                "description": item["description"],
                "answer_mode": item.get("answer_mode", "strict_qa"),
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
        """读取指定 PageIndex 模板；为空时返回严谨问答模板。"""

        if not template_id:
            return self._annotate_template(BUILTIN_PAGEINDEX_TEMPLATES["strict_qa"].copy(), source_type="builtin", file_path=None)
        deleted_template_ids = self._load_deleted_template_ids()
        if template_id in deleted_template_ids:
            raise NotFoundAppError("PageIndex 模板不存在", details={"template_id": template_id})
        builtin_template = BUILTIN_PAGEINDEX_TEMPLATES.get(template_id)
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
        raise NotFoundAppError("PageIndex 模板不存在", details={"template_id": template_id})

    def save_template(self, payload: dict) -> dict:
        """新增或更新 PageIndex 模板，并保存到本地 YAML。"""

        template = self._normalize_template_payload(payload)
        file_path = self._get_template_file_path(template["template_id"])
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(yaml.safe_dump(template, allow_unicode=True, sort_keys=False), encoding="utf-8")
        deleted_template_ids = self._load_deleted_template_ids()
        if template["template_id"] in deleted_template_ids:
            deleted_template_ids.remove(template["template_id"])
            self._save_deleted_template_ids(deleted_template_ids)
        return self.get_template(template["template_id"])

    def delete_template(self, template_id: str) -> dict:
        """删除 PageIndex 模板；内置模板通过删除标记隐藏。"""

        normalized_template_id = str(template_id or "").strip()
        if not normalized_template_id:
            raise ValidationAppError("模板 ID 不能为空")
        template = self.get_template(normalized_template_id)
        file_path = self._get_template_file_path(normalized_template_id)
        if file_path.exists():
            file_path.unlink()
        deleted_template_ids = self._load_deleted_template_ids()
        if normalized_template_id in BUILTIN_PAGEINDEX_TEMPLATES:
            if normalized_template_id not in deleted_template_ids:
                deleted_template_ids.append(normalized_template_id)
                self._save_deleted_template_ids(deleted_template_ids)
        elif normalized_template_id in deleted_template_ids:
            deleted_template_ids.remove(normalized_template_id)
            self._save_deleted_template_ids(deleted_template_ids)
        return {"template_id": normalized_template_id, "template_name": template.get("template_name", "")}

    def render_answer_prompts(
        self,
        template: dict,
        *,
        question: str,
        evidence: list[dict],
        structure_context: str,
        evidence_judgement: str,
        citation_rules: str,
        question_plan: dict | None = None,
    ) -> tuple[str, str]:
        """把 PageIndex 问答变量渲染为 LLM system/user prompt。"""

        system_prompt = str(template.get("system_prompt") or BUILTIN_PAGEINDEX_TEMPLATES["strict_qa"]["system_prompt"])
        user_prompt_template = str(template.get("user_prompt_template") or BUILTIN_PAGEINDEX_TEMPLATES["strict_qa"]["user_prompt_template"])
        try:
            user_prompt = user_prompt_template.format(
                question=str(question or ""),
                evidence_json=json.dumps(evidence, ensure_ascii=False),
                question_plan=json.dumps(question_plan or {}, ensure_ascii=False),
                structure_context=str(structure_context or ""),
                evidence_judgement=str(evidence_judgement or ""),
                citation_rules=str(citation_rules or ""),
            )
        except KeyError as exc:
            raise ValidationAppError("PageIndex 模板变量不存在", details={"variable": str(exc)}) from exc
        return system_prompt, user_prompt

    def _iter_template_files(self) -> list[Path]:
        """遍历 PageIndex 模板目录。"""

        pageindex_dir = self.templates_dir / "pageindex"
        if not pageindex_dir.exists():
            return []
        return sorted(
            [
                file_path
                for file_path in pageindex_dir.rglob("*")
                if file_path.is_file() and file_path.suffix.lower() in {".yaml", ".yml"}
                and file_path.name != self.DELETED_TEMPLATE_REGISTRY
                and file_path.name not in self.RULE_FILE_NAMES
            ]
        )

    def _get_template_file_path(self, template_id: str) -> Path:
        """根据模板 ID 生成 PageIndex 模板文件路径。"""

        normalized_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", template_id.strip())
        return self.templates_dir / "pageindex" / f"{normalized_name}.yaml"

    def _load_deleted_template_ids(self) -> list[str]:
        """读取 PageIndex 模板删除清单。"""

        registry_path = self.templates_dir / "pageindex" / self.DELETED_TEMPLATE_REGISTRY
        if not registry_path.exists():
            return []
        try:
            payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValidationAppError("PageIndex 模板删除清单格式错误", details={"file_path": str(registry_path)}) from exc
        if not isinstance(payload, dict):
            return []
        deleted_ids = payload.get("deleted_template_ids", [])
        if not isinstance(deleted_ids, list):
            return []
        return [str(item).strip() for item in deleted_ids if str(item).strip()]

    def _save_deleted_template_ids(self, template_ids: list[str]) -> None:
        """保存 PageIndex 模板删除清单。"""

        registry_path = self.templates_dir / "pageindex" / self.DELETED_TEMPLATE_REGISTRY
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
        """校验并规范化 PageIndex 模板。"""

        template_id = str(payload.get("template_id", "")).strip()
        template_name = str(payload.get("template_name", "")).strip()
        description = str(payload.get("description", "")).strip()
        answer_mode = str(payload.get("answer_mode", "strict_qa")).strip() or "strict_qa"
        system_prompt = str(payload.get("system_prompt", "")).strip()
        user_prompt_template = str(payload.get("user_prompt_template", "")).strip()
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
            "max_tree_candidates": int(retrieval_policy.get("max_tree_candidates", 30)),
            "max_selected_nodes": int(retrieval_policy.get("max_selected_nodes", 3)),
            "max_rag_evidence": int(retrieval_policy.get("max_rag_evidence", 2)),
            "include_structure_context": bool(retrieval_policy.get("include_structure_context", True)),
        }
        for key in ("max_tree_candidates", "max_selected_nodes", "max_rag_evidence"):
            if normalized_policy[key] < 0:
                raise ValidationAppError("PageIndex 检索策略数值不能小于 0", details={"field": key})
        return {
            "template_id": template_id,
            "template_name": template_name,
            "description": description,
            "answer_mode": answer_mode,
            "system_prompt": system_prompt,
            "user_prompt_template": user_prompt_template,
            "retrieval_policy": normalized_policy,
        }

    @staticmethod
    def _annotate_template(template: dict, *, source_type: str, file_path: Path | None) -> dict:
        """补充模板来源与可编辑状态。"""

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

    def _load_template_file(self, file_path: Path) -> dict:
        """读取并校验单个 PageIndex 模板文件。"""

        try:
            payload = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValidationAppError("PageIndex 模板格式错误", details={"file_path": str(file_path)}) from exc
        if not isinstance(payload, dict):
            raise ValidationAppError("PageIndex 模板内容必须是对象", details={"file_path": str(file_path)})
        return self._normalize_template_payload(
            {
                "template_id": str(payload.get("template_id", file_path.stem)).strip(),
                "template_name": str(payload.get("template_name", file_path.stem)).strip(),
                "description": str(payload.get("description", "")).strip(),
                "answer_mode": str(payload.get("answer_mode", "strict_qa")).strip(),
                "system_prompt": str(payload.get("system_prompt", "")).strip(),
                "user_prompt_template": str(payload.get("user_prompt_template", "")).strip(),
                "retrieval_policy": payload.get("retrieval_policy", {}) if isinstance(payload.get("retrieval_policy", {}), dict) else {},
            }
        )
