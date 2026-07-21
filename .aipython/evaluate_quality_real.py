"""程序说明：使用真实索引与模型评估 AI 质检效果，并将质检历史写入临时数据库。"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.llm import DisabledLLMClient, build_llm_client
from src.ai.rerank import build_reranker
from src.common.config import AppSettings
from src.common.errors import AppError
from src.quality.service import QualityService


REAL_CASES = (
    {"claim": "阿胶具有补血作用。", "allowed": {"verified", "needs_review"}},
    {"claim": "阿胶可以治疗感冒。", "allowed": {"needs_review", "rejected"}},
    {"claim": "阿胶只有东阿一家有。", "allowed": {"needs_review", "rejected"}},
    {"claim": "阿胶能治疗癌症。", "allowed": {"needs_review", "rejected"}},
)


def _backup_database(source_path: Path, target_path: Path) -> None:
    """通过 SQLite 在线备份生成临时评测库，避免污染真实质检历史。"""

    with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
        source.backup(target)


def _build_service(settings: AppSettings, database_path: Path) -> QualityService:
    """使用真实模型、SQLite 全文索引和 Rerank 构建质检服务。"""

    llm_client = build_llm_client(settings)
    if isinstance(llm_client, DisabledLLMClient):
        raise RuntimeError("LLM 未启用，不能执行真实质检评测")
    return QualityService(
        database_path,
        rules_dir=settings.rules_dir,
        templates_dir=settings.templates_dir,
        reranker=build_reranker(settings),
        llm_client=llm_client,
    )


def _summarize_case(service: QualityService, case: dict[str, object]) -> dict[str, object]:
    """执行一个真实问题并提取可人工复核的结论与证据。"""

    claim = str(case["claim"])
    result = service.run_check(claim, knowledge_base_id="default", template_id="general_fact_check")
    claim_result = (result.get("claims") or [{}])[0]
    evidence = claim_result.get("evidence_details") or []
    verdict = str(claim_result.get("verdict") or "")
    return {
        "claim": claim,
        "verdict": verdict,
        "accepted": verdict in set(case["allowed"]),
        "risk_level": claim_result.get("risk_level"),
        "confidence": claim_result.get("confidence"),
        "reason": claim_result.get("evidence_reason"),
        "evidence_count": len(evidence),
        "evidence": [
            {
                "doc_uid": item.get("doc_uid"),
                "source_span": item.get("source_span"),
                "relation": item.get("evidence_relation"),
                "matched_queries": item.get("matched_queries"),
                "content": str(item.get("content_preview") or "")[:300],
            }
            for item in evidence[:4]
        ],
    }


def main() -> int:
    """运行真实问题集并返回是否全部达到基础验收标准。"""

    try:
        settings = AppSettings()
        # Windows 上 SQLite 连接释放可能稍有延迟，评测临时目录清理失败不应遮蔽结果。
        with TemporaryDirectory(prefix="doc-ai-quality-", ignore_cleanup_errors=True) as temporary_directory:
            temporary_db = Path(temporary_directory) / "app.db"
            _backup_database(settings.sqlite_db_path, temporary_db)
            service = _build_service(settings, temporary_db)
            rows = [_summarize_case(service, case) for case in REAL_CASES]
        report = {
            "model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "rerank_model": settings.rerank_model,
            "retrieval_mode": "sqlite_fulltext_multi_query+rerank",
            "passed": all(bool(row["accepted"]) for row in rows),
            "cases": rows,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    except AppError as exc:
        print(json.dumps({"passed": False, "error": exc.message, "details": exc.details}, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
