"""程序说明：提供知识库配置与目录管理能力。"""

from __future__ import annotations

import re
from pathlib import Path

from src.common.errors import NotFoundAppError, ValidationAppError
from src.db.repositories import KnowledgeBaseRepository


class KnowledgeBaseService:
    """知识库管理服务。"""

    def __init__(self, database_path: Path, input_root: Path) -> None:
        self.repository = KnowledgeBaseRepository(database_path)
        self.input_root = input_root

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
        document_count = self.repository.count_documents(knowledge_base_id)
        if document_count > 0:
            raise ValidationAppError(
                "当前知识库下仍有归属文档，不能删除",
                details={"knowledge_base_id": knowledge_base_id, "document_count": document_count},
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

    @staticmethod
    def _normalize_knowledge_base_id(raw_value: object) -> str:
        """规范化知识库标识，便于作为目录名使用。"""

        normalized = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(raw_value or "").strip())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        if not normalized:
            raise ValidationAppError("知识库标识不能为空")
        return normalized
