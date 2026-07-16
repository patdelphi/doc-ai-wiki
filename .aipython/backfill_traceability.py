"""程序说明：预检、备份并回填历史 Markdown 文档的证据追溯字段。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.config import AppSettings
from src.db.connection import create_connection
from src.metadata.traceability import backfill_traceability


def build_parser() -> argparse.ArgumentParser:
    """创建追溯字段回填参数。"""

    parser = argparse.ArgumentParser(description="事务化回填历史证据追溯字段")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--doc-uid", action="append", dest="doc_uids")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-root", type=Path)
    return parser


def _backup_database(database_path: Path, backup_root: Path) -> Path:
    """使用 SQLite 在线备份 API 创建包含 WAL 最新状态的一致快照。"""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = backup_root / timestamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_path = backup_dir / database_path.name
    with create_connection(database_path) as source, sqlite3.connect(backup_path) as destination:
        source.backup(destination)
        destination.execute("PRAGMA journal_mode = WAL;")
        destination.execute("PRAGMA synchronous = NORMAL;")
    return backup_path


def main() -> None:
    """先预检全部映射；仅在 apply 模式下备份并执行写入。"""

    args = build_parser().parse_args()
    settings = AppSettings()
    database_path = (args.database or settings.sqlite_db_path).resolve()
    input_root = (args.input_root or settings.input_root).resolve()
    preview = backfill_traceability(
        database_path,
        input_root,
        doc_uids=args.doc_uids,
        apply=False,
    )
    if not preview["success"]:
        print(json.dumps({"success": False, "preview": preview}, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    backup_path: Path | None = None
    result = preview
    if args.apply:
        backup_root = args.backup_root or database_path.parent / "backups" / "traceability"
        backup_path = _backup_database(database_path, backup_root)
        result = backfill_traceability(
            database_path,
            input_root,
            doc_uids=args.doc_uids,
            apply=True,
        )
    payload = {
        "success": result["success"],
        "mode": "apply" if args.apply else "dry_run",
        "backup_path": str(backup_path) if backup_path else "",
        "result": result,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not result["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
