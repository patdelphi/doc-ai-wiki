"""程序说明：只读运行正式检索评测，并输出 JSON 摘要与 UTF-8 BOM Markdown 报告。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.embedding import build_embedding_client
from src.ai.rerank import build_reranker
from src.common.config import AppSettings
from src.retrieval.evaluation import (
    evaluate_retrieval_cases,
    format_evaluation_report_markdown,
    load_jsonl_cases,
    validate_case_references,
)
from src.retrieval.service import RetrievalService
from src.retrieval.vector_store import VectorStore


def build_parser() -> argparse.ArgumentParser:
    """创建只读评测参数。"""

    parser = argparse.ArgumentParser(description="AI 检索与 PageIndex 离线评测")
    parser.add_argument(
        "--cases",
        type=Path,
        default=PROJECT_ROOT / "tests" / "evaluation" / "retrieval_cases.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "Docs" / "retrieval_pageindex_evaluation_20260716.md",
    )
    parser.add_argument("--top-k", type=int, default=10)
    return parser


def main() -> None:
    """运行真实混合检索主链评测，未达正式门槛时返回退出码 1。"""

    args = build_parser().parse_args()
    settings = AppSettings()
    cases = load_jsonl_cases(args.cases)
    reference_report = validate_case_references(settings.sqlite_db_path, cases)
    vector_store = VectorStore(
        settings.chroma_persist_dir,
        embedding_client=build_embedding_client(settings),
        sqlite_db_path=settings.sqlite_db_path,
        auto_repair_dimension_mismatch=False,
        embedding_model=settings.embedding_model,
        index_version="retrieval-v2",
    )
    retrieval_service = RetrievalService(settings.sqlite_db_path)
    retrieval_service.set_vector_store(vector_store)
    retrieval_service.set_reranker(build_reranker(settings))
    try:
        retrieval_result = evaluate_retrieval_cases(
            retrieval_service,
            cases,
            top_k=max(int(args.top_k), 10),
        )
    finally:
        vector_store.close()
    summary = retrieval_result["summary"]
    thresholds = {
        "recall_at_5": 0.80,
        "mrr_at_10": 0.65,
        "ndcg_at_10": 0.70,
        "traceable_rate": 1.0,
    }
    passed = reference_report["valid"] and all(
        float(summary.get(metric) or 0.0) >= minimum
        for metric, minimum in thresholds.items()
    )
    report = format_evaluation_report_markdown(
        title="AI 检索与 PageIndex 评测报告",
        retrieval_result=retrieval_result,
    )
    report += "\r\n## 引用校验\r\n\r\n```json\r\n"
    report += json.dumps(reference_report, ensure_ascii=False, indent=2).replace("\n", "\r\n")
    report += "\r\n```\r\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8-sig", newline="\r\n")
    payload = {
        "success": passed,
        "summary": summary,
        "reference_report": reference_report,
        "thresholds": thresholds,
        "output": str(args.output),
        "mode": "local_read_only",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
