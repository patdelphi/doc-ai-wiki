"""程序说明：以显式 apply 门禁执行 PageIndex 预检、批量影子重建和最近备份恢复。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.config import AppSettings
from src.common.errors import AppError, ValidationAppError
from src.common.paths import resolve_input_path
from src.pageindex import service as pageindex_service_module
from src.pageindex.rebuild import PageIndexRebuilder
from src.pageindex.service import PageIndexService


def build_parser() -> argparse.ArgumentParser:
    """创建带显式写入确认的 PageIndex 运维参数。"""

    parser = argparse.ArgumentParser(description="PageIndex 安全重建与恢复")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect", help="只读检查当前 PageIndex")
    rebuild_parser = subparsers.add_parser("rebuild", help="备份、影子构建、校验并发布")
    rebuild_parser.add_argument("--apply", action="store_true", help="实际调用模型并切换工作区")
    restore_parser = subparsers.add_parser("restore", help="恢复最近一次完整备份")
    restore_parser.add_argument("--latest", action="store_true", help="选择最近备份")
    restore_parser.add_argument("--apply", action="store_true", help="实际执行恢复")
    return parser


def build_rebuilder(settings: AppSettings) -> PageIndexRebuilder:
    """构造不写活动数据库的 PageIndex 单文档影子构建函数。"""

    service = PageIndexService(settings)

    def build_document(record: dict, workspace: Path) -> dict:
        if pageindex_service_module.PageIndexClient is None:
            raise ValidationAppError("PageIndex 本地依赖不可用")
        if not settings.llm_api_key:
            raise ValidationAppError("PageIndex 重建缺少 LLM_API_KEY")
        source_path = resolve_input_path(str(record["source_path"]), settings.input_root)
        if not source_path.exists():
            raise ValidationAppError(
                "PageIndex 源文档不存在",
                details={"source_path": str(source_path)},
            )
        workspace.mkdir(parents=True, exist_ok=False)
        prepared_path = service._prepare_pageindex_source_path(source_path, workspace)
        mode = "md" if source_path.suffix.lower() in {".md", ".markdown"} else "pdf"
        if mode == "md":
            return service._build_local_markdown_workspace(
                workspace=workspace,
                source_path=prepared_path,
                doc_uid=str(record["doc_uid"]),
                doc_title=str(record.get("doc_title") or record["doc_uid"]),
                source_hash=str(record["current_source_hash"]),
            )
        service._configure_vendor_environment()
        client = pageindex_service_module.PageIndexClient(
            api_key=settings.llm_api_key,
            model=service._pageindex_model_name(),
            retrieve_model=service._pageindex_model_name(),
            workspace=str(workspace),
        )
        pageindex_doc_id = client.index(str(prepared_path), mode=mode)
        service._write_normalized_structure(
            client=client,
            workspace=workspace,
            pageindex_doc_id=pageindex_doc_id,
            doc_uid=str(record["doc_uid"]),
            source_path=prepared_path,
            mode=mode,
            source_hash=str(record["current_source_hash"]),
        )
        payload = json.loads(
            (workspace / "structure.normalized.json").read_text(encoding="utf-8-sig")
        )
        return {
            "pageindex_doc_id": pageindex_doc_id,
            "source_hash": str(record["current_source_hash"]),
            "quality": payload.get("quality") or {},
        }

    return PageIndexRebuilder(
        database_path=settings.sqlite_db_path,
        workspace_root=settings.sqlite_db_path.parent / "pageindex_workspace",
        document_builder=build_document,
    )


def run_command(args: argparse.Namespace) -> dict:
    """执行命令；无 apply 时只返回计划和预计调用上限。"""

    settings = AppSettings()
    rebuilder = build_rebuilder(settings)
    if args.command == "inspect":
        return rebuilder.inspect()
    if args.command == "rebuild":
        if not args.apply:
            plan = rebuilder.inspect()
            plan["model"] = settings.llm_model
            pdf_count = sum(
                1
                for record in plan["records"]
                if Path(str(record.get("source_path") or "")).suffix.lower() == ".pdf"
            )
            plan["local_markdown_count"] = int(plan["document_count"]) - pdf_count
            plan["estimated_max_llm_calls"] = pdf_count * 8
            return {"status": "dry_run", "published": False, "plan": plan}
        return rebuilder.rebuild(apply=True)
    if args.command == "restore":
        if not args.latest:
            raise ValidationAppError("restore 命令必须显式指定 --latest")
        return rebuilder.restore_latest(apply=bool(args.apply))
    raise ValidationAppError("不支持的 PageIndex 运维命令")


def main() -> None:
    """统一输出 JSON，并捕获应用和运行时异常。"""

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
