"""程序说明：提供检索索引的预检、备份、影子构建、门禁发布与恢复能力。"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from src.common.errors import DatabaseAppError, ValidationAppError
from src.db.transaction import transaction
from src.retrieval.index_state import build_retrieval_index_report, write_index_manifest
from src.retrieval.vector_store import VectorStore


class _VectorStoreProtocol(Protocol):
    """声明重建流程所需的最小向量索引接口。"""

    def rebuild_from_sqlite(self) -> tuple[int, int]: ...

    def inspect_index(self) -> dict: ...

    def close(self) -> None: ...


VectorStoreFactory = Callable[[Path, Path], _VectorStoreProtocol]
ValidationGate = Callable[[dict], bool]


class RetrievalIndexRebuilder:
    """以可恢复方式重建 SQLite FTS 与本地向量索引。"""

    def __init__(
        self,
        *,
        database_path: Path,
        chroma_path: Path,
        backup_root: Path | None = None,
        manifest_path: Path | None = None,
        vector_store_factory: VectorStoreFactory | None = None,
        embedding_provider: str = "local",
        embedding_model: str = "deterministic-v1",
        index_version: str = "retrieval-v2",
    ) -> None:
        self.database_path = Path(database_path)
        self.chroma_path = Path(chroma_path)
        self.backup_root = Path(backup_root or self.database_path.parent / "backups" / "retrieval")
        self.manifest_path = Path(manifest_path or self.database_path.parent / "index_manifest.json")
        self.vector_store_factory = vector_store_factory or self._default_vector_store_factory
        self.embedding_provider = str(embedding_provider)
        self.embedding_model = str(embedding_model)
        self.index_version = str(index_version)
        self._staging_chroma_path: Path | None = None
        self._candidate_report: dict | None = None
        self._backup_path: Path | None = None

    def _default_vector_store_factory(self, persist_directory: Path, database_path: Path) -> VectorStore:
        """构造默认的本地确定性向量索引，外部模型由 CLI 显式注入。"""

        return VectorStore(
            persist_directory,
            sqlite_db_path=database_path,
            auto_repair_dimension_mismatch=False,
            embedding_model=self.embedding_model,
            index_version=self.index_version,
        )

    @staticmethod
    def _timestamp() -> str:
        """生成用于备份和影子目录的 UTC 时间戳。"""

        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def inspect(self) -> dict:
        """只读汇总当前活动检索索引状态。"""

        try:
            vector_store = self.vector_store_factory(self.chroma_path, self.database_path)
            return build_retrieval_index_report(
                self.database_path,
                vector_store,  # type: ignore[arg-type]
                embedding_provider=self.embedding_provider,
                embedding_model=self.embedding_model,
                index_version=self.index_version,
            )
        except (ValidationAppError, DatabaseAppError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise DatabaseAppError(
                "读取检索索引状态失败",
                details={"reason": str(exc)},
            ) from exc
        finally:
            if vector_store is not None:
                vector_store.close()

    def backup(self) -> Path:
        """备份 SQLite、WAL/SHM、本地向量索引和索引清单。"""

        if not self.database_path.exists():
            raise ValidationAppError(
                "SQLite 数据库不存在，无法备份",
                details={"database_path": str(self.database_path)},
            )

        backup_path = self.backup_root / self._timestamp()
        if backup_path.exists():
            raise ValidationAppError(
                "同一时间戳的检索索引备份已存在",
                details={"backup_path": str(backup_path)},
            )

        try:
            backup_path.mkdir(parents=True, exist_ok=False)
            # PASSIVE checkpoint 不截断 WAL，避免备份遗漏已提交事务。
            connection = sqlite3.connect(self.database_path)
            try:
                connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            finally:
                connection.close()

            for source_path in self._database_files(self.database_path):
                if source_path.exists():
                    shutil.copy2(source_path, backup_path / source_path.name)
            if self.chroma_path.exists():
                shutil.copytree(self.chroma_path, backup_path / "chroma")
            if self.manifest_path.exists():
                shutil.copy2(self.manifest_path, backup_path / "index_manifest.json")
            (backup_path / "backup_info.json").write_text(
                json.dumps(
                    {
                        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "database_path": str(self.database_path),
                        "chroma_path": str(self.chroma_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8-sig",
                newline="\r\n",
            )
        except Exception as exc:  # noqa: BLE001
            raise DatabaseAppError(
                "备份检索索引失败",
                details={"backup_path": str(backup_path), "reason": str(exc)},
            ) from exc

        self._backup_path = backup_path
        return backup_path

    def build_staging(self) -> dict:
        """构建 FTS 临时表和独立向量索引影子目录。"""

        timestamp = self._timestamp()
        staging_chroma_path = self.chroma_path.with_name(f"{self.chroma_path.name}.staging.{timestamp}")
        if staging_chroma_path.exists():
            raise ValidationAppError(
                "检索索引影子目录已存在",
                details={"staging_path": str(staging_chroma_path)},
            )

        vector_store: _VectorStoreProtocol | None = None
        try:
            with transaction(self.database_path) as connection:
                connection.execute("DROP TABLE IF EXISTS chunk_fts__staging")
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE chunk_fts__staging USING fts5(
                        chunk_id UNINDEXED,
                        doc_uid UNINDEXED,
                        content,
                        tokenize='trigram'
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO chunk_fts__staging(chunk_id, doc_uid, content)
                    SELECT chunk_id, doc_uid, content FROM chunks
                    """
                )

            vector_store = self.vector_store_factory(staging_chroma_path, self.database_path)
            rebuilt_docs, rebuilt_chunks = vector_store.rebuild_from_sqlite()
        except (ValidationAppError, DatabaseAppError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise DatabaseAppError(
                "构建检索索引影子版本失败",
                details={"staging_path": str(staging_chroma_path), "reason": str(exc)},
            ) from exc
        finally:
            if vector_store is not None:
                vector_store.close()

        self._staging_chroma_path = staging_chroma_path
        return {
            "staging_chroma_path": str(staging_chroma_path),
            "rebuilt_documents": int(rebuilt_docs),
            "rebuilt_chunks": int(rebuilt_chunks),
        }

    def validate(self) -> dict:
        """校验影子 FTS、向量数量及模型元数据。"""

        if self._staging_chroma_path is None:
            raise ValidationAppError("尚未构建检索索引影子版本")

        vector_store: _VectorStoreProtocol | None = None
        try:
            connection = sqlite3.connect(self.database_path)
            try:
                sqlite_chunk_count = int(connection.execute("SELECT COUNT(1) FROM chunks").fetchone()[0])
                fts_chunk_count = int(
                    connection.execute("SELECT COUNT(1) FROM chunk_fts__staging").fetchone()[0]
                )
                fts_row = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='chunk_fts__staging'"
                ).fetchone()
            finally:
                connection.close()
            vector_store = self.vector_store_factory(
                self._staging_chroma_path,
                self.database_path,
            )
            vector_report = vector_store.inspect_index()
        except Exception as exc:  # noqa: BLE001
            raise DatabaseAppError(
                "校验检索索引影子版本失败",
                details={"reason": str(exc)},
            ) from exc
        finally:
            if vector_store is not None:
                vector_store.close()

        vector_count = int(vector_report.get("total_count") or 0)
        fts_sql = str(fts_row[0] or "") if fts_row else ""
        errors: list[str] = []
        if sqlite_chunk_count != fts_chunk_count:
            errors.append("fts_count_mismatch")
        if sqlite_chunk_count != vector_count:
            errors.append("vector_count_mismatch")
        if "trigram" not in fts_sql.lower():
            errors.append("fts_tokenizer_mismatch")
        if int(vector_report.get("missing_metadata_count") or 0):
            errors.append("missing_vector_metadata")
        if vector_count and vector_report.get("embedding_models") != [self.embedding_model]:
            errors.append("embedding_model_mismatch")
        if vector_count and vector_report.get("index_versions") != [self.index_version]:
            errors.append("index_version_mismatch")

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "index_version": self.index_version,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": vector_report.get("embedding_dimensions") or [],
            "sqlite_chunk_count": sqlite_chunk_count,
            "fts_chunk_count": fts_chunk_count,
            "fts_tokenizer": "trigram" if "trigram" in fts_sql.lower() else "unknown",
            "vector_count": vector_count,
            "vector_by_knowledge_base": vector_report.get("by_knowledge_base") or {},
            "vector_by_document": vector_report.get("by_document") or {},
            "missing_vector_metadata_count": int(vector_report.get("missing_metadata_count") or 0),
            "errors": errors,
            "consistent": not errors,
        }
        self._candidate_report = report
        return report

    def publish(self) -> dict:
        """通过门禁后切换向量目录，并在事务内替换活动 FTS。"""

        if not self._candidate_report or not self._candidate_report.get("consistent"):
            raise ValidationAppError("检索索引影子版本未通过一致性门禁")
        if self._staging_chroma_path is None or not self._staging_chroma_path.exists():
            raise ValidationAppError("检索索引影子目录不存在")

        timestamp = self._timestamp()
        previous_chroma_path = self.chroma_path.with_name(f"{self.chroma_path.name}.previous.{timestamp}")
        try:
            if self.chroma_path.exists():
                self.chroma_path.replace(previous_chroma_path)
            self._staging_chroma_path.replace(self.chroma_path)
            try:
                with transaction(self.database_path) as connection:
                    connection.execute("DROP TABLE chunk_fts")
                    connection.execute("ALTER TABLE chunk_fts__staging RENAME TO chunk_fts")
            except Exception:
                failed_chroma_path = self.chroma_path.with_name(f"{self.chroma_path.name}.failed.{timestamp}")
                if self.chroma_path.exists():
                    self.chroma_path.replace(failed_chroma_path)
                if previous_chroma_path.exists():
                    previous_chroma_path.replace(self.chroma_path)
                raise
            write_index_manifest(self.manifest_path, self._candidate_report)
        except (ValidationAppError, DatabaseAppError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise DatabaseAppError(
                "发布检索索引失败",
                details={"reason": str(exc)},
            ) from exc

        return {
            "published": True,
            "manifest_path": str(self.manifest_path),
            "previous_chroma_path": str(previous_chroma_path) if previous_chroma_path.exists() else None,
            "report": self._candidate_report,
        }

    def rebuild(
        self,
        *,
        apply: bool = False,
        validator: ValidationGate | None = None,
    ) -> dict:
        """执行完整流程；默认只预检，必须显式 apply 才创建或切换索引。"""

        if not apply:
            return {"status": "dry_run", "published": False, "report": self.inspect()}

        backup_path = self.backup()
        staging = self.build_staging()
        report = self.validate()
        gate_passed = bool(report.get("consistent"))
        if validator is not None:
            gate_passed = gate_passed and bool(validator(report))
        if not gate_passed:
            cleanup_error = self._retire_failed_staging()
            result = {
                "status": "validation_failed",
                "published": False,
                "backup_path": str(backup_path),
                "staging": staging,
                "report": report,
            }
            if cleanup_error:
                result["cleanup_error"] = cleanup_error
            return result

        published = self.publish()
        return {
            "status": "published",
            "backup_path": str(backup_path),
            "staging": staging,
            **published,
        }

    def _retire_failed_staging(self) -> str | None:
        """移除临时 FTS，并保留失败向量目录供排障。"""

        try:
            with transaction(self.database_path) as connection:
                connection.execute("DROP TABLE IF EXISTS chunk_fts__staging")
            if self._staging_chroma_path and self._staging_chroma_path.exists():
                failed_path = self._staging_chroma_path.with_name(
                    self._staging_chroma_path.name.replace(".staging.", ".failed.")
                )
                self._staging_chroma_path.replace(failed_path)
            return None
        except Exception as exc:  # noqa: BLE001
            # 清理属于次级动作，不得覆盖原始一致性门禁报告。
            return str(exc)

    def restore_latest(self, *, apply: bool = False) -> dict:
        """从最近一次完整备份恢复 SQLite、向量索引和索引清单。"""

        backups = sorted(path for path in self.backup_root.glob("*") if path.is_dir())
        if not backups:
            raise ValidationAppError(
                "没有可恢复的检索索引备份",
                details={"backup_root": str(self.backup_root)},
            )
        backup_path = backups[-1]
        if not apply:
            return {
                "status": "dry_run",
                "restored": False,
                "backup_path": str(backup_path),
            }

        backup_database_path = backup_path / self.database_path.name
        backup_chroma_path = backup_path / "chroma"
        if not backup_database_path.exists() or not backup_chroma_path.exists():
            raise ValidationAppError(
                "最近备份不完整，拒绝恢复",
                details={"backup_path": str(backup_path)},
            )

        safety_path = self.database_path.parent / "restore_safety" / self._timestamp()
        try:
            safety_path.mkdir(parents=True, exist_ok=False)
            for active_path in self._database_files(self.database_path):
                if active_path.exists():
                    shutil.copy2(active_path, safety_path / active_path.name)
            if self.chroma_path.exists():
                shutil.move(str(self.chroma_path), str(safety_path / "chroma"))

            # Windows 下活动 SQLite 文件可能被短暂持有，使用官方 backup API 恢复数据库页。
            source_connection = sqlite3.connect(backup_database_path)
            target_connection = sqlite3.connect(self.database_path)
            try:
                source_connection.backup(target_connection)
                target_connection.commit()
                target_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            finally:
                target_connection.close()
                source_connection.close()
            shutil.copytree(backup_chroma_path, self.chroma_path)
            backup_manifest_path = backup_path / "index_manifest.json"
            if backup_manifest_path.exists():
                shutil.copy2(backup_manifest_path, self.manifest_path)
        except Exception as exc:  # noqa: BLE001
            raise DatabaseAppError(
                "恢复检索索引失败，原活动文件已保留在安全目录",
                details={
                    "backup_path": str(backup_path),
                    "safety_path": str(safety_path),
                    "reason": str(exc),
                },
            ) from exc

        return {
            "status": "restored",
            "restored": True,
            "backup_path": str(backup_path),
            "safety_path": str(safety_path),
        }

    @staticmethod
    def _database_files(database_path: Path) -> tuple[Path, Path, Path]:
        """返回 SQLite 主文件及 WAL/SHM 伴随文件。"""

        return (
            database_path,
            Path(f"{database_path}-wal"),
            Path(f"{database_path}-shm"),
        )
