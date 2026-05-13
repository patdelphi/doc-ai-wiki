"""程序说明：提供知识库配置与目录管理能力。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from src.common.errors import NotFoundAppError, ValidationAppError
from src.db.repositories import KnowledgeBaseRepository


class KnowledgeBaseService:
    """知识库管理服务。"""

    def __init__(self, database_path: Path, input_root: Path) -> None:
        self.repository = KnowledgeBaseRepository(database_path)
        self.input_root = input_root
        self.input_root.mkdir(parents=True, exist_ok=True)
        self.get_input_directory("default").mkdir(parents=True, exist_ok=True)

    def list_knowledge_bases(self) -> list[dict]:
        """列出所有知识库。"""

        return self.repository.list_knowledge_bases()

    def get_knowledge_base(self, knowledge_base_id: str | None) -> dict:
        """读取指定知识库；未传时优先返回默认知识库。"""

        normalized_id = str(knowledge_base_id or "").strip()
        if normalized_id:
            item = self.repository.get_by_id(normalized_id)
            if not item:
                raise NotFoundAppError("知识库不存在", details={"knowledge_base_id": normalized_id})
            return item

        items = self.repository.list_knowledge_bases()
        if not items:
            raise NotFoundAppError("知识库不存在")
        return next((item for item in items if item.get("is_default")), items[0])

    def save_knowledge_base(self, payload: dict) -> dict:
        """新增或更新知识库，并确保目录存在。"""

        knowledge_base_id = self._normalize_knowledge_base_id(
            payload.get("knowledge_base_id") or payload.get("knowledge_base_name")
        )
        knowledge_base_name = str(payload.get("knowledge_base_name") or "").strip()
        if not knowledge_base_name:
            raise ValidationAppError("知识库名称不能为空")

        existing = self.repository.get_by_id(knowledge_base_id)
        saved = self.repository.save_knowledge_base(
            {
                "knowledge_base_id": knowledge_base_id,
                "knowledge_base_name": knowledge_base_name,
                "description": str(payload.get("description") or "").strip(),
                "status": str(payload.get("status") or "active").strip() or "active",
                "is_default": bool(payload.get("is_default")),
                "created_at": existing.get("created_at") if existing else None,
            }
        )
        self.get_input_directory(knowledge_base_id).mkdir(parents=True, exist_ok=True)
        return saved

    def delete_knowledge_base(self, knowledge_base_id: str) -> dict:
        """删除知识库；若已有归属文档则拒绝。"""

        item = self.get_knowledge_base(knowledge_base_id)
        if item.get("is_default"):
            raise ValidationAppError("默认知识库不能删除")
        related_counts = self.repository.get_related_record_counts(knowledge_base_id)
        if related_counts["document_count"] > 0:
            raise ValidationAppError(
                "当前知识库下仍有归属文档，不能删除",
                details={"knowledge_base_id": knowledge_base_id, **related_counts},
            )
        if related_counts["quality_check_count"] > 0 or related_counts["claim_count"] > 0 or related_counts["review_count"] > 0:
            raise ValidationAppError(
                "当前知识库下仍有关联质检或审核记录，不能删除",
                details={"knowledge_base_id": knowledge_base_id, **related_counts},
            )
        self.repository.delete_knowledge_base(knowledge_base_id)
        input_dir = self.get_input_directory(knowledge_base_id)
        if input_dir.exists() and not any(input_dir.iterdir()):
            input_dir.rmdir()
        return item

    def get_input_directory(self, knowledge_base_id: str) -> Path:
        """返回知识库对应的输入目录。"""

        normalized_id = self._normalize_knowledge_base_id(knowledge_base_id)
        return self.input_root / normalized_id

    def relocate_document_file(self, source_path: Path | str, target_knowledge_base_id: str) -> Path:
        """将输入文档移动到目标知识库目录，并返回最终路径。"""

        source = Path(source_path)
        normalized_target_id = self._normalize_knowledge_base_id(target_knowledge_base_id)
        target_directory = self.get_input_directory(normalized_target_id)
        target_directory.mkdir(parents=True, exist_ok=True)

        if not source.exists():
            return source

        resolved_source = source.resolve()
        resolved_input_root = self.input_root.resolve()
        try:
            resolved_source.relative_to(resolved_input_root)
        except ValueError:
            return resolved_source

        if resolved_source.parent == target_directory.resolve():
            return resolved_source

        target_path = self._build_available_target_path(resolved_source, target_directory)
        shutil.move(str(resolved_source), str(target_path))
        return target_path.resolve()

    @staticmethod
    def _build_available_target_path(source_path: Path, target_directory: Path) -> Path:
        """为迁移文档生成不冲突的目标路径。"""

        candidate = target_directory / source_path.name
        if not candidate.exists():
            return candidate

        if candidate.resolve() == source_path.resolve():
            return candidate

        stem = source_path.stem
        suffix = source_path.suffix
        index = 2
        while True:
            candidate = target_directory / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    @staticmethod
    def _normalize_knowledge_base_id(raw_value: object) -> str:
        """规范化知识库标识，便于作为目录名使用。"""

        normalized = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(raw_value or "").strip())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        if not normalized:
            raise ValidationAppError("知识库标识不能为空")
        return normalized
