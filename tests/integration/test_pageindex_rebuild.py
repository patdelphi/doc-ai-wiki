"""程序说明：验证 PageIndex 影子重建的失败门禁、发布与元数据恢复。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.common.config import AppSettings
from src.common.utils import sha256_of_text
from src.db.connection import initialize_database
from src.ingest.service import IngestService
from src.knowledge_base.service import KnowledgeBaseService
from src.pageindex.rebuild import PageIndexRebuilder
from src.pageindex.service import PageIndexService


def _hash_directory(path: Path) -> str:
    """计算目录内容的稳定哈希。"""

    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update(child.read_bytes())
    return digest.hexdigest()


@pytest.fixture
def pageindex_rebuilder(tmp_path: Path) -> PageIndexRebuilder:
    """创建单文档 PageIndex 活动目录和离线影子构建器。"""

    settings = AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "index" / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "index" / "chroma",
        RULES_DIR=tmp_path / "rules",
        TEMPLATES_DIR=tmp_path / "templates",
        LLM_PROVIDER="disabled",
        LLM_MODEL="disabled",
        EMBEDDING_PROVIDER="local",
        RERANK_ENABLED=False,
    )
    initialize_database(settings.sqlite_db_path)
    KnowledgeBaseService(settings.sqlite_db_path, settings.input_root).save_knowledge_base(
        {
            "knowledge_base_id": "kb_alpha",
            "knowledge_base_name": "测试库",
            "description": "",
            "status": "active",
            "is_default": False,
        }
    )
    source_path = settings.input_root / "kb_alpha" / "alpha.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("# alpha\n\n## 风险\n\n正文", encoding="utf-8")
    document = IngestService(settings).register_document(
        {"file_path": str(source_path), "knowledge_base_id": "kb_alpha"},
        knowledge_base_id="kb_alpha",
    )
    service = PageIndexService(settings)
    service.upsert_index_record(
        "kb_alpha",
        document["doc_uid"],
        "old_pageindex_id",
        source_hash=sha256_of_text(source_path.read_text(encoding="utf-8")),
    )
    active_workspace = settings.sqlite_db_path.parent / "pageindex_workspace"
    doc_workspace = active_workspace / "kb_alpha" / document["doc_uid"]
    doc_workspace.mkdir(parents=True, exist_ok=True)
    (doc_workspace / "active.txt").write_text("old", encoding="utf-8")

    def build_document(record: dict, workspace: Path) -> dict:
        workspace.mkdir(parents=True, exist_ok=False)
        structure = [
            {
                "node_id": "root",
                "parent_id": None,
                "title": "alpha",
                "source_start_line": 1,
                "source_end_line": 5,
                "source_anchor": "alpha-L1",
                "nodes": [
                    {
                        "node_id": "risk",
                        "parent_id": "root",
                        "title": "风险",
                        "source_start_line": 3,
                        "source_end_line": 5,
                        "source_anchor": "风险-L3",
                        "nodes": [],
                    }
                ],
            }
        ]
        payload = {
            "status": "ready",
            "source_hash": record["current_source_hash"],
            "quality": {"passed": True, "errors": []},
            "structure": structure,
        }
        (workspace / "structure.normalized.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8-sig"
        )
        return {
            "pageindex_doc_id": "new_pageindex_id",
            "source_hash": record["current_source_hash"],
            "quality": payload["quality"],
        }

    return PageIndexRebuilder(
        database_path=settings.sqlite_db_path,
        workspace_root=active_workspace,
        backup_root=settings.sqlite_db_path.parent / "backups" / "pageindex",
        document_builder=build_document,
    )


def test_pageindex_rebuild_should_publish_only_after_quality_gate(
    pageindex_rebuilder: PageIndexRebuilder,
) -> None:
    """额外质量门禁失败时活动 workspace 和数据库记录均不得改变。"""

    original_hash = _hash_directory(pageindex_rebuilder.workspace_root)
    result = pageindex_rebuilder.rebuild(
        apply=True,
        quality_gate=lambda _report: False,
    )

    assert result["published"] is False
    assert result["status"] == "validation_failed"
    assert _hash_directory(pageindex_rebuilder.workspace_root) == original_hash
    assert pageindex_rebuilder.inspect()["records"][0]["pageindex_doc_id"] == "old_pageindex_id"


def test_pageindex_rebuild_publish_and_restore_should_recover_workspace_and_records(
    pageindex_rebuilder: PageIndexRebuilder,
) -> None:
    """通过门禁后可发布，并从最近备份恢复目录和 PageIndex 元数据。"""

    original_hash = _hash_directory(pageindex_rebuilder.workspace_root)
    rebuilt = pageindex_rebuilder.rebuild(apply=True)

    assert rebuilt["published"] is True
    assert pageindex_rebuilder.inspect()["records"][0]["pageindex_doc_id"] == "new_pageindex_id"

    restored = pageindex_rebuilder.restore_latest(apply=True)

    assert restored["restored"] is True
    assert _hash_directory(pageindex_rebuilder.workspace_root) == original_hash
    assert pageindex_rebuilder.inspect()["records"][0]["pageindex_doc_id"] == "old_pageindex_id"
