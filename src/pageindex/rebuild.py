"""程序说明：提供 PageIndex 工作区的备份、影子重建、质量门禁、发布与恢复。"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from src.common.errors import AppError, DatabaseAppError, ValidationAppError
from src.common.utils import utc_now_iso
from src.db.connection import create_connection
from src.db.transaction import transaction


DocumentBuilder = Callable[[dict, Path], dict]
QualityGate = Callable[[dict], bool]


class PageIndexRebuilder:
    """在独立目录构建 PageIndex，只有通过门禁才切换活动工作区。"""

    def __init__(
        self,
        *,
        database_path: Path,
        workspace_root: Path,
        backup_root: Path | None = None,
        document_builder: DocumentBuilder,
    ) -> None:
        self.database_path = Path(database_path)
        self.workspace_root = Path(workspace_root)
        self.backup_root = Path(
            backup_root or self.database_path.parent / "backups" / "pageindex"
        )
        self.document_builder = document_builder
        self._backup_path: Path | None = None
        self._staging_root: Path | None = None
        self._staging_results: list[dict] = []
        self._validation_report: dict | None = None

    @staticmethod
    def _timestamp() -> str:
        """生成 UTC 目录时间戳。"""

        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def inspect(self) -> dict:
        """只读返回当前 PageIndex 记录和工作区状态。"""

        return {
            "workspace_root": str(self.workspace_root),
            "workspace_exists": self.workspace_root.exists(),
            "document_count": len(self._load_records()),
            "records": self._load_records(),
        }

    def _load_records(self) -> list[dict]:
        """读取 PageIndex 记录及其当前文档来源哈希。"""

        try:
            connection = create_connection(self.database_path)
            try:
                rows = connection.execute(
                    """
                    SELECT
                        p.knowledge_base_id,
                        p.doc_uid,
                        p.pageindex_doc_id,
                        p.workspace_path,
                        p.source_hash,
                        p.status,
                        d.source_hash AS current_source_hash,
                        d.doc_title,
                        d.source_path
                    FROM pageindex_indexes p
                    JOIN documents d ON d.doc_uid = p.doc_uid
                    ORDER BY p.knowledge_base_id, p.doc_uid
                    """
                ).fetchall()
            finally:
                connection.close()
        except Exception as exc:  # noqa: BLE001
            raise DatabaseAppError(
                "读取 PageIndex 重建记录失败",
                details={"reason": str(exc)},
            ) from exc
        return [dict(row) for row in rows]

    def backup(self) -> Path:
        """备份活动 workspace、数据库 PageIndex 元数据导出和 manifest。"""

        backup_path = self.backup_root / self._timestamp()
        if backup_path.exists():
            raise ValidationAppError(
                "同一时间戳的 PageIndex 备份已存在",
                details={"backup_path": str(backup_path)},
            )
        try:
            backup_path.mkdir(parents=True, exist_ok=False)
            if self.workspace_root.exists():
                shutil.copytree(self.workspace_root, backup_path / "workspace")
            records = self._load_records()
            self._write_json(backup_path / "pageindex_records.json", records)
            self._write_json(
                backup_path / "manifest.json",
                {
                    "created_at": utc_now_iso(),
                    "workspace_root": str(self.workspace_root),
                    "document_count": len(records),
                },
            )
        except (AppError, OSError) as exc:
            if isinstance(exc, AppError):
                raise
            raise DatabaseAppError(
                "备份 PageIndex 失败",
                details={"backup_path": str(backup_path), "reason": str(exc)},
            ) from exc
        self._backup_path = backup_path
        return backup_path

    def rebuild_staging(self) -> dict:
        """逐文档在独立工作区构建候选 PageIndex。"""

        staging_root = self.workspace_root.with_name(
            f"{self.workspace_root.name}.staging.{self._timestamp()}"
        )
        if staging_root.exists():
            raise ValidationAppError(
                "PageIndex 影子工作区已存在",
                details={"staging_root": str(staging_root)},
            )
        records = self._load_records()
        results: list[dict] = []
        try:
            staging_root.mkdir(parents=True, exist_ok=False)
            for record in records:
                document_workspace = (
                    staging_root
                    / str(record["knowledge_base_id"])
                    / str(record["doc_uid"])
                )
                result = self.document_builder(record, document_workspace)
                results.append(
                    {
                        "knowledge_base_id": str(record["knowledge_base_id"]),
                        "doc_uid": str(record["doc_uid"]),
                        "pageindex_doc_id": str(result.get("pageindex_doc_id") or ""),
                        "source_hash": str(
                            result.get("source_hash") or record["current_source_hash"]
                        ),
                        "quality": result.get("quality") or {},
                        "workspace_path": str(document_workspace),
                    }
                )
            self._write_json(
                staging_root / "manifest.json",
                {
                    "created_at": utc_now_iso(),
                    "document_count": len(results),
                    "documents": results,
                },
            )
        except Exception as exc:  # noqa: BLE001
            raise DatabaseAppError(
                "构建 PageIndex 影子工作区失败",
                details={"staging_root": str(staging_root), "reason": str(exc)},
            ) from exc
        self._staging_root = staging_root
        self._staging_results = results
        return {
            "staging_root": str(staging_root),
            "document_count": len(results),
            "documents": results,
        }

    def validate(self) -> dict:
        """验证每篇文档的规范化结构文件和质量报告。"""

        if self._staging_root is None:
            raise ValidationAppError("尚未构建 PageIndex 影子工作区")
        errors: list[dict] = []
        for item in self._staging_results:
            normalized_path = Path(item["workspace_path"]) / "structure.normalized.json"
            raw_quality = item.get("quality")
            quality: dict = {}
            if isinstance(raw_quality, dict):
                quality = raw_quality
            item_errors: list[str] = []
            if not normalized_path.exists():
                item_errors.append("normalized_structure_missing")
            if not quality.get("passed"):
                item_errors.append("tree_quality_failed")
            if not item.get("pageindex_doc_id"):
                item_errors.append("pageindex_doc_id_missing")
            if item_errors:
                errors.append({"doc_uid": item["doc_uid"], "errors": item_errors})
        report = {
            "passed": not errors,
            "document_count": len(self._staging_results),
            "errors": errors,
        }
        self._validation_report = report
        return report

    def publish(self) -> dict:
        """原子切换工作区，并在事务内批量更新 PageIndex 记录。"""

        if not self._validation_report or not self._validation_report.get("passed"):
            raise ValidationAppError("PageIndex 影子工作区未通过质量门禁")
        if self._staging_root is None or not self._staging_root.exists():
            raise ValidationAppError("PageIndex 影子工作区不存在")

        timestamp = self._timestamp()
        previous_root = self.workspace_root.with_name(
            f"{self.workspace_root.name}.previous.{timestamp}"
        )
        try:
            if self.workspace_root.exists():
                self.workspace_root.replace(previous_root)
            self._staging_root.replace(self.workspace_root)
            try:
                with transaction(self.database_path) as connection:
                    for item in self._staging_results:
                        active_document_workspace = (
                            self.workspace_root
                            / item["knowledge_base_id"]
                            / item["doc_uid"]
                        )
                        connection.execute(
                            """
                            UPDATE pageindex_indexes
                            SET pageindex_doc_id = ?, workspace_path = ?, source_hash = ?,
                                status = 'ready', error_message = NULL, updated_at = ?
                            WHERE knowledge_base_id = ? AND doc_uid = ?
                            """,
                            (
                                item["pageindex_doc_id"],
                                str(active_document_workspace),
                                item["source_hash"],
                                utc_now_iso(),
                                item["knowledge_base_id"],
                                item["doc_uid"],
                            ),
                        )
            except Exception:
                failed_root = self.workspace_root.with_name(
                    f"{self.workspace_root.name}.failed.{timestamp}"
                )
                if self.workspace_root.exists():
                    self.workspace_root.replace(failed_root)
                if previous_root.exists():
                    previous_root.replace(self.workspace_root)
                raise
        except (AppError, OSError) as exc:
            if isinstance(exc, AppError):
                raise
            raise DatabaseAppError(
                "发布 PageIndex 工作区失败",
                details={"reason": str(exc)},
            ) from exc
        return {
            "published": True,
            "workspace_root": str(self.workspace_root),
            "previous_root": str(previous_root) if previous_root.exists() else None,
        }

    def rebuild(
        self,
        *,
        apply: bool = False,
        quality_gate: QualityGate | None = None,
    ) -> dict:
        """执行完整重建；默认只输出计划，不创建影子目录。"""

        if not apply:
            return {"status": "dry_run", "published": False, "plan": self.inspect()}
        backup_path = self.backup()
        staging = self.rebuild_staging()
        report = self.validate()
        gate_passed = bool(report.get("passed"))
        if quality_gate is not None:
            gate_passed = gate_passed and bool(quality_gate(report))
        if not gate_passed:
            self._retire_failed_staging()
            return {
                "status": "validation_failed",
                "published": False,
                "backup_path": str(backup_path),
                "staging": staging,
                "report": report,
            }
        published = self.publish()
        return {
            "status": "published",
            "backup_path": str(backup_path),
            "staging": staging,
            "report": report,
            **published,
        }

    def _retire_failed_staging(self) -> None:
        """保留失败候选目录供排障，不触碰活动工作区。"""

        if self._staging_root and self._staging_root.exists():
            failed_root = self._staging_root.with_name(
                self._staging_root.name.replace(".staging.", ".failed.")
            )
            self._staging_root.replace(failed_root)

    def restore_latest(self, *, apply: bool = False) -> dict:
        """恢复最近备份中的工作区和 PageIndex 数据库记录。"""

        backups = sorted(path for path in self.backup_root.glob("*") if path.is_dir())
        if not backups:
            raise ValidationAppError("没有可恢复的 PageIndex 备份")
        backup_path = backups[-1]
        backup_workspace = backup_path / "workspace"
        records_path = backup_path / "pageindex_records.json"
        if not backup_workspace.exists() or not records_path.exists():
            raise ValidationAppError(
                "最近 PageIndex 备份不完整",
                details={"backup_path": str(backup_path)},
            )
        if not apply:
            return {
                "status": "dry_run",
                "restored": False,
                "backup_path": str(backup_path),
            }

        safety_root = self.workspace_root.with_name(
            f"{self.workspace_root.name}.restore_safety.{self._timestamp()}"
        )
        restore_staging = self.workspace_root.with_name(
            f"{self.workspace_root.name}.restore_staging.{self._timestamp()}"
        )
        try:
            shutil.copytree(backup_workspace, restore_staging)
            if self.workspace_root.exists():
                self.workspace_root.replace(safety_root)
            restore_staging.replace(self.workspace_root)
            records = json.loads(records_path.read_text(encoding="utf-8-sig"))
            with transaction(self.database_path) as connection:
                for record in records:
                    active_document_workspace = (
                        self.workspace_root
                        / str(record["knowledge_base_id"])
                        / str(record["doc_uid"])
                    )
                    connection.execute(
                        """
                        UPDATE pageindex_indexes
                        SET pageindex_doc_id = ?, workspace_path = ?, source_hash = ?,
                            status = ?, error_message = NULL, updated_at = ?
                        WHERE knowledge_base_id = ? AND doc_uid = ?
                        """,
                        (
                            record["pageindex_doc_id"],
                            str(active_document_workspace),
                            record["source_hash"],
                            record["status"],
                            utc_now_iso(),
                            record["knowledge_base_id"],
                            record["doc_uid"],
                        ),
                    )
        except Exception as exc:  # noqa: BLE001
            raise DatabaseAppError(
                "恢复 PageIndex 失败，恢复前目录已保留",
                details={
                    "backup_path": str(backup_path),
                    "safety_root": str(safety_root),
                    "reason": str(exc),
                },
            ) from exc
        return {
            "status": "restored",
            "restored": True,
            "backup_path": str(backup_path),
            "safety_root": str(safety_root),
        }

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        """以 UTF-8 BOM、CRLF 原子写入 JSON。"""

        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
            newline="\r\n",
        )
        temporary_path.replace(path)
