"""程序说明：将历史候选建议转换为真实 ID 的临时回归集，不覆盖人工金标。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.config import AppSettings
from src.db.connection import create_connection
from src.retrieval.evaluation import (
    build_provisional_aligned_cases,
    load_jsonl_cases,
    validate_case_references,
)


def build_parser() -> argparse.ArgumentParser:
    """创建候选对齐命令参数。"""

    parser = argparse.ArgumentParser(description="生成真实 chunk ID 的候选对齐回归集")
    parser.add_argument(
        "--cases",
        type=Path,
        default=PROJECT_ROOT / "tests" / "evaluation" / "retrieval_cases.jsonl",
    )
    parser.add_argument(
        "--suggestions",
        type=Path,
        default=PROJECT_ROOT / "Docs" / "retrieval_alignment_suggestions_20260621.md",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "tests" / "evaluation" / "retrieval_cases_real_20260716.jsonl",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "Docs" / "retrieval_case_alignment_20260716.md",
    )
    parser.add_argument("--database", type=Path)
    return parser


def main() -> None:
    """生成候选对齐集，真实引用校验失败时拒绝输出成功状态。"""

    args = build_parser().parse_args()
    database_path = args.database or AppSettings().sqlite_db_path
    source_cases = load_jsonl_cases(args.cases)
    suggestions = args.suggestions.read_text(encoding="utf-8-sig")
    with create_connection(database_path) as connection:
        knowledge_base_id_by_doc_uid = {
            str(row["doc_uid"]): str(row["knowledge_base_id"])
            for row in connection.execute(
                "SELECT doc_uid, knowledge_base_id FROM documents"
            ).fetchall()
        }
    aligned_cases = build_provisional_aligned_cases(
        source_cases,
        suggestions,
        knowledge_base_id_by_doc_uid=knowledge_base_id_by_doc_uid,
    )
    reference_report = validate_case_references(database_path, aligned_cases)
    aligned_count = sum(
        1 for case in aligned_cases if case.get("alignment_status") == "provisional_first_candidate"
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    jsonl = "\r\n".join(json.dumps(case, ensure_ascii=False) for case in aligned_cases) + "\r\n"
    args.output.write_text(jsonl, encoding="utf-8-sig", newline="")

    report = (
        "# 检索评测候选对齐记录\r\n\r\n"
        "## 结论\r\n\r\n"
        f"- 原始样例：`{len(source_cases)}` 条。\r\n"
        f"- 已对齐真实 chunk：`{aligned_count}` 条。\r\n"
        f"- 引用校验：`{'通过' if reference_report['valid'] else '失败'}`。\r\n"
        "- 相关性目标：仅使用 `expected_chunk_ids`，不使用文档级命中兜底。\r\n\r\n"
        "- 检索范围：每条样例继承候选文档的真实 `knowledge_base_id`。\r\n\r\n"
        "## 适用范围\r\n\r\n"
        "该数据集取历史候选建议中每条样例的首个候选，用于重建后的算法回归。"
        "候选由旧索引自动生成，未经逐条独立人工复核，因此不能作为正式金标或产品质量上限证明。\r\n\r\n"
        "## 引用校验\r\n\r\n```json\r\n"
        + json.dumps(reference_report, ensure_ascii=False, indent=2).replace("\n", "\r\n")
        + "\r\n```\r\n"
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8-sig", newline="")

    payload = {
        "success": reference_report["valid"] and aligned_count == len(source_cases),
        "case_count": len(source_cases),
        "aligned_count": aligned_count,
        "reference_report": reference_report,
        "output": str(args.output),
        "report": str(args.report),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
