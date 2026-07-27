"""程序说明：使用真实模型和活动数据库对比 PageIndex 与 AI 质检质量，并逐条回读落库记录。"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.embedding import build_embedding_client
from src.ai.llm import DisabledLLMClient, build_llm_client
from src.ai.rerank import build_reranker
from src.common.config import AppSettings
from src.common.errors import AppError
from src.pageindex.service import PageIndexService
from src.quality.service import QualityService
from src.retrieval.service import RetrievalService
from src.retrieval.vector_store import VectorStore


QUALITY_CASES = (
    {
        "case_id": "quality_safe_boundary",
        "text": "阿胶可用于部分补血相关研究，但不能替代贫血病因诊断和规范治疗。",
        "allowed": {"passed", "needs_review"},
        "forbidden_claim_verdict": "rejected",
    },
    {
        "case_id": "quality_evidence_gap",
        "text": "截至目前，当前知识库没有证据证明阿胶与华法林存在明确相互作用。",
        "allowed": {"needs_review"},
    },
    {
        "case_id": "quality_origin_boundary",
        "text": "东阿是历史道地产区之一，但不是唯一产地。",
        "allowed": {"passed", "needs_review"},
        "forbidden_claim_verdict": "rejected",
    },
    {
        "case_id": "quality_universal_dose",
        "text": "任何人每天服用500克阿胶都绝对安全，不会产生任何不良反应。",
        "allowed": {"rejected"},
        "required_risk": "high",
    },
    {
        "case_id": "quality_unlimited_product",
        "text": "阿胶糕通常含糖和坚果，糖尿病患者及坚果过敏人群可以长期不限量食用。",
        "allowed": {"rejected"},
        "required_risk": "high",
    },
    {
        "case_id": "quality_superiority_replacement",
        "text": "阿胶治疗贫血的效果一定优于铁剂，而且可以完全替代铁剂。",
        "allowed": {"rejected"},
        "required_risk": "high",
    },
)


PAGEINDEX_CASES = (
    {
        "case_id": "pageindex_evidence_layers",
        "template_id": "evidence_audit_qa",
        "question": "请比较阿胶的传统功效、动物或机制研究和人体临床研究：分别说明证据能支持到什么程度，哪些不能直接作为临床治疗承诺？",
        "required_sections": (
            "审查结论",
            "证据能证明什么",
            "证据不能证明什么",
            "不能外推的原因",
            "来源",
            "不确定点",
        ),
    },
    {
        "case_id": "pageindex_origin_scope",
        "template_id": "strict_qa",
        "question": "东阿与阿胶的历史道地性有什么关系？现有材料能否证明东阿是唯一产地或只有一家企业能生产？",
        "required_sections": ("结论", "证据判断", "依据", "来源", "不确定点"),
    },
    {
        "case_id": "pageindex_product_risk",
        "template_id": "medical_safety_qa",
        "question": "阿胶糕常见配料有哪些？糖尿病患者、坚果过敏人群是否适合长期不限量食用？请区分配料事实与安全结论。",
        "required_sections": (
            "结论",
            "证据能说明什么",
            "证据不能证明什么",
            "风险或人群边界",
            "依据",
            "来源",
            "不确定点",
            "非医疗建议",
        ),
    },
    {
        "case_id": "pageindex_usage_boundary",
        "template_id": "medical_safety_qa",
        "question": "阿胶常见的烊化或配伍用法能说明什么？这些传统用法能否证明任何人都可以长期大剂量服用？",
        "required_sections": (
            "结论",
            "证据能说明什么",
            "证据不能证明什么",
            "风险或人群边界",
            "依据",
            "来源",
            "不确定点",
            "非医疗建议",
        ),
    },
)


def _build_services(settings: AppSettings) -> tuple[PageIndexService, QualityService]:
    """使用活动索引和完整模型配置构造两条真实链路。"""

    llm_client = build_llm_client(settings)
    if isinstance(llm_client, DisabledLLMClient):
        raise RuntimeError("LLM 未启用，不能执行真实质量验收")
    embedding_client = build_embedding_client(settings)
    reranker = build_reranker(settings)
    vector_store = VectorStore(
        settings.chroma_persist_dir,
        embedding_client=embedding_client,
        sqlite_db_path=settings.sqlite_db_path,
        auto_repair_dimension_mismatch=False,
        embedding_model=settings.embedding_model,
        index_version="retrieval-v2",
    )
    retrieval_service = RetrievalService(settings.sqlite_db_path)
    retrieval_service.set_vector_store(vector_store)
    retrieval_service.set_reranker(reranker)
    return (
        PageIndexService(
            settings,
            llm_client=llm_client,
            retrieval_service=retrieval_service,
        ),
        QualityService(
            settings.sqlite_db_path,
            rules_dir=settings.rules_dir,
            templates_dir=settings.templates_dir,
            vector_store=vector_store,
            reranker=reranker,
            llm_client=llm_client,
        ),
    )


def _read_pageindex_record(database_path: Path, query_id: str) -> dict | None:
    """直接回读 PageIndex 历史，确认答案和 debug 已真实落库。"""

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT query_id, question, answer, evidence_json, debug_json
            FROM pageindex_query_history
            WHERE query_id = ?
            """,
            (query_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def _read_quality_record(database_path: Path, check_id: str) -> dict | None:
    """直接回读质检主记录和 Claim 数量，确认事务写入完成。"""

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT q.check_id, q.overall_verdict, q.risk_level, COUNT(c.claim_id) AS claim_count
            FROM quality_checks q
            LEFT JOIN quality_claims c ON c.check_id = q.check_id
            WHERE q.check_id = ?
            GROUP BY q.check_id, q.overall_verdict, q.risk_level
            """,
            (check_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def _run_quality_case(service: QualityService, settings: AppSettings, case: dict) -> dict:
    """执行并验证一条真实 AI 质检案例。"""

    result = service.run_check(
        str(case["text"]),
        knowledge_base_id="default",
        template_id="medical_safety_review",
    )
    check = result.get("check") or {}
    claims = result.get("claims") or []
    check_id = str(check.get("check_id") or "")
    persisted = _read_quality_record(settings.sqlite_db_path, check_id)
    overall_verdict = str(check.get("overall_verdict") or "")
    risk_level = str(check.get("risk_level") or "")
    forbidden_claim_verdict = str(case.get("forbidden_claim_verdict") or "")
    accepted = (
        overall_verdict in set(case["allowed"])
        and persisted is not None
        and int(persisted["claim_count"]) == len(claims)
        and (
            not case.get("required_risk")
            or risk_level == str(case["required_risk"])
        )
        and (
            not forbidden_claim_verdict
            or all(str(item.get("verdict") or "") != forbidden_claim_verdict for item in claims)
        )
    )
    return {
        "case_id": case["case_id"],
        "check_id": check_id,
        "accepted": accepted,
        "overall_verdict": overall_verdict,
        "risk_level": risk_level,
        "claim_count": len(claims),
        "persisted": persisted is not None,
        "claims": [
            {
                "text": item.get("claim_text"),
                "verdict": item.get("verdict"),
                "risk_level": item.get("risk_level"),
                "evidence_judgement": item.get("evidence_judgement"),
                "reason": item.get("evidence_reason"),
            }
            for item in claims
        ],
    }


def _run_pageindex_case(service: PageIndexService, settings: AppSettings, case: dict) -> dict:
    """执行并验证一条真实 PageIndex 问答案例。"""

    result = service.ask_knowledge_base_question(
        "default",
        str(case["question"]),
        template_id=str(case["template_id"]),
    )
    query_id = str(result.get("query_id") or "")
    answer = str(result.get("answer") or "")
    evidence = result.get("evidence") or []
    persisted = _read_pageindex_record(settings.sqlite_db_path, query_id)
    persisted_debug = (
        json.loads(str(persisted.get("debug_json") or "{}"))
        if persisted is not None
        else {}
    )
    answer_contract = persisted_debug.get("answer_contract") or {}
    degraded_reason = str(answer_contract.get("degraded_reason") or "")
    safe_contract_degradation = degraded_reason == "unsupported_external_knowledge"
    missing_sections = [
        section
        for section in case["required_sections"]
        if re.search(
            rf"(?:^|\n)\s*(?:#{{1,6}}\s*)?{re.escape(section)}\s*(?:[：:]|$)",
            answer,
            flags=re.MULTILINE,
        )
        is None
    ]
    traceable_count = sum(
        1
        for item in evidence
        if item.get("doc_uid")
        and (
            item.get("chunk_id")
            or item.get("node_id")
            or item.get("source_anchor")
            or item.get("position")
        )
    )
    accepted = (
        persisted is not None
        and bool(evidence)
        and traceable_count == len(evidence)
        and not missing_sections
        and (not str(result.get("llm_error") or "") or safe_contract_degradation)
        and not answer.lstrip().startswith("{")
        and "{'" not in answer
    )
    return {
        "case_id": case["case_id"],
        "query_id": query_id,
        "accepted": accepted,
        "template_id": case["template_id"],
        "retrieval_mode": result.get("retrieval_mode"),
        "llm_error": result.get("llm_error"),
        "degraded_reason": degraded_reason,
        "evidence_count": len(evidence),
        "traceable_count": traceable_count,
        "missing_sections": missing_sections,
        "persisted": persisted is not None,
        "answer_preview": answer[:1200],
    }


def main() -> int:
    """运行全部真实案例，并以 JSON 输出可审计结果。"""

    try:
        settings = AppSettings()
        pageindex_service, quality_service = _build_services(settings)
        quality_rows = [
            _run_quality_case(quality_service, settings, case)
            for case in QUALITY_CASES
        ]
        pageindex_rows = [
            _run_pageindex_case(pageindex_service, settings, case)
            for case in PAGEINDEX_CASES
        ]
        report = {
            "model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "rerank_model": settings.rerank_model,
            "quality_passed": sum(1 for row in quality_rows if row["accepted"]),
            "quality_total": len(quality_rows),
            "pageindex_passed": sum(1 for row in pageindex_rows if row["accepted"]),
            "pageindex_total": len(pageindex_rows),
            "passed": all(row["accepted"] for row in [*quality_rows, *pageindex_rows]),
            "quality_rows": quality_rows,
            "pageindex_rows": pageindex_rows,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    except AppError as exc:
        print(
            json.dumps(
                {"passed": False, "error": exc.message, "details": exc.details},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"passed": False, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
