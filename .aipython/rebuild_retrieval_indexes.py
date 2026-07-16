"""程序说明：以显式 apply 门禁执行检索索引预检、重建和最近备份恢复。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.embedding import build_embedding_client
from src.common.config import AppSettings
from src.common.errors import AppError
from src.retrieval.rebuild import RetrievalIndexRebuilder
from src.retrieval.vector_store import VectorStore


def build_parser() -> argparse.ArgumentParser:
    """创建带显式写入开关的命令行参数。"""

    parser = argparse.ArgumentParser(description="检索索引安全重建与恢复")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect", help="只读检查当前索引")

    rebuild_parser = subparsers.add_parser("rebuild", help="备份、影子构建、校验并发布")
    rebuild_parser.add_argument("--apply", action="store_true", help="实际执行备份和索引切换")

    restore_parser = subparsers.add_parser("restore", help="恢复最近一次完整备份")
    restore_parser.add_argument("--latest", action="store_true", help="选择最近一次完整备份")
    restore_parser.add_argument("--apply", action="store_true", help="实际执行恢复")
    return parser


def build_rebuilder(settings: AppSettings) -> RetrievalIndexRebuilder:
    """按当前配置创建重建器，并延迟构造 Embedding 客户端。"""

    def vector_store_factory(persist_directory: Path, database_path: Path) -> VectorStore:
        return VectorStore(
            persist_directory,
            embedding_client=build_embedding_client(settings),
            sqlite_db_path=database_path,
            auto_repair_dimension_mismatch=False,
            embedding_model=settings.embedding_model,
            index_version="retrieval-v2",
        )

    return RetrievalIndexRebuilder(
        database_path=settings.sqlite_db_path,
        chroma_path=settings.chroma_persist_dir,
        vector_store_factory=vector_store_factory,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        index_version="retrieval-v2",
    )


def run_command(args: argparse.Namespace) -> dict:
    """执行命令；未指定 apply 时保持只读。"""

    settings = AppSettings()
    rebuilder = build_rebuilder(settings)
    if args.command == "inspect":
        return {"status": "inspected", "report": rebuilder.inspect()}
    if args.command == "rebuild":
        return rebuilder.rebuild(apply=bool(args.apply))
    if args.command == "restore":
        if not args.latest:
            raise AppError("restore 命令必须显式指定 --latest")
        return rebuilder.restore_latest(apply=bool(args.apply))
    raise AppError("不支持的检索索引命令", details={"command": args.command})


def main() -> None:
    """统一输出 JSON，并将应用异常转换为非零退出码。"""

    try:
        result = run_command(build_parser().parse_args())
    except AppError as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": {
                        "message": exc.message,
                        "error_code": exc.error_code,
                        "details": exc.details,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "success": False,
                    "error": {"message": str(exc), "error_code": "INTERNAL_ERROR", "details": {}},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1) from exc
    print(json.dumps({"success": True, "data": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
