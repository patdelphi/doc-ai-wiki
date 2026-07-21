"""程序说明：封装 PageIndex 本地索引构建、文档查询与知识库隔离逻辑。"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

from src.ai.llm import DisabledLLMClient, build_llm_client
from src.common.config import AppSettings
from src.common.errors import AppError, DatabaseAppError, NotFoundAppError, ValidationAppError
from src.common.paths import resolve_input_path, to_input_relative_path
from src.common.utils import utc_now_iso
from src.db.connection import create_connection
from src.db.transaction import transaction
from src.pageindex.answer_orchestrator import PageIndexAnswerOrchestrator
from src.pageindex.history_export import format_history_markdown, parse_history_rows
from src.pageindex.index_repository import PageIndexRepository
from src.pageindex.routing import PageIndexBudget, RetrievalBudgetExceededError, route_documents
from src.pageindex.structure import build_heading_tree, enrich_vendor_structure, evaluate_tree_quality
from src.pageindex.templates import PageIndexTemplateService
from src.pageindex import tree_retriever
from src.retrieval.query_normalizer import expand_query_texts
from src.retrieval.service import RetrievalService


PAGEINDEX_VENDOR_ROOT = Path(__file__).resolve().parents[2] / "vendor" / "pageindex"
if str(PAGEINDEX_VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(PAGEINDEX_VENDOR_ROOT))

try:
    from pageindex import PageIndexClient
except Exception as exc:  # noqa: BLE001
    PageIndexClient = None
    PAGEINDEX_IMPORT_ERROR = exc
else:
    PAGEINDEX_IMPORT_ERROR = None


class PageIndexService:
    """PageIndex 本地服务，所有数据都绑定到指定知识库。"""

    def __init__(
        self,
        settings: AppSettings,
        *,
        llm_client: object | None = None,
        retrieval_service: RetrievalService | None = None,
    ) -> None:
        """初始化服务并确保 PageIndex 元数据表存在。"""

        self.settings = settings
        self.llm_client = llm_client
        self.retrieval_service = retrieval_service or RetrievalService(settings.sqlite_db_path)
        self.template_service = PageIndexTemplateService(settings.templates_dir)
        self.answer_orchestrator = PageIndexAnswerOrchestrator(self.template_service)
        self.workspace_root = settings.sqlite_db_path.parent / "pageindex_workspace"
        self.index_repository = PageIndexRepository(settings.sqlite_db_path)
        self.index_repository.initialize_schema()

    def list_available_documents(self, knowledge_base_id: str) -> list[dict]:
        """列出当前知识库中已入库、可用于 PageIndex 的文档。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        try:
            with create_connection(self.settings.sqlite_db_path) as connection:
                rows = connection.execute(
                    """
                    SELECT
                        doc_uid,
                        doc_id,
                        doc_title,
                        source_path,
                        source_hash,
                        ingest_status,
                        index_status,
                        updated_at
                    FROM documents
                    WHERE knowledge_base_id = ?
                      AND ingest_status = 'completed'
                    ORDER BY updated_at DESC, doc_title ASC
                    """,
                    (resolved_knowledge_base_id,),
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise DatabaseAppError("读取 PageIndex 可用文档失败", details={"reason": str(exc)}) from exc

        return [dict(row) for row in rows]

    def get_retrieval_status(self) -> dict:
        """返回 PageIndex 提问阶段的 LLM 语义检索可用性。"""

        provider = str(self.settings.llm_provider or "").strip()
        model = str(self.settings.llm_model or "").strip()
        has_llm = provider.lower() not in {"", "disabled", "none"} and model.lower() not in {"", "disabled", "none"}
        if self.llm_client is not None:
            return {
                "llm_available": True,
                "llm_status": "已配置",
                "retrieval_mode": "LLM 语义树推理",
                "provider": provider or "injected",
                "model": model or "injected",
            }
        if has_llm and self.settings.llm_api_key:
            return {
                "llm_available": True,
                "llm_status": "已配置",
                "retrieval_mode": "LLM 语义树推理",
                "provider": provider,
                "model": model,
            }
        reason = "未配置" if not has_llm else "缺少 API Key"
        return {
            "llm_available": False,
            "llm_status": reason,
            "retrieval_mode": "本地关键词降级",
            "provider": provider or "disabled",
            "model": model or "disabled",
        }

    def build_index(self, knowledge_base_id: str, doc_uid: str, *, rebuild: bool = False) -> dict:
        """为指定知识库下的单篇文档构建 PageIndex 本地索引。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_doc_uid = str(doc_uid or "").strip()
        if not resolved_doc_uid:
            raise ValidationAppError("请选择需要构建 PageIndex 的文档")

        document = self._get_document(resolved_knowledge_base_id, resolved_doc_uid)
        source_path = self._resolve_existing_source_path(document)
        if source_path.suffix.lower() not in {".md", ".markdown", ".pdf"}:
            raise ValidationAppError("PageIndex 当前仅支持 Markdown 与 PDF 文档", details={"source_path": str(source_path)})
        if not source_path.exists():
            raise NotFoundAppError("PageIndex 源文档不存在", details={"source_path": str(source_path)})

        workspace = self._document_workspace(resolved_knowledge_base_id, resolved_doc_uid)
        workspace.mkdir(parents=True, exist_ok=True)
        pageindex_source_path = self._prepare_pageindex_source_path(source_path, workspace)
        mode = "md" if source_path.suffix.lower() in {".md", ".markdown"} else "pdf"
        if mode == "md":
            local_result = self._build_local_markdown_workspace(
                workspace=workspace,
                source_path=pageindex_source_path,
                doc_uid=resolved_doc_uid,
                doc_title=str(document.get("doc_title") or resolved_doc_uid),
                source_hash=str(document["source_hash"]),
            )
            pageindex_doc_id = str(local_result["pageindex_doc_id"])
            structure_status = "normalized"
        else:
            self._ensure_llm_enabled()
            self._ensure_pageindex_available()
            self._configure_vendor_environment()
            client = PageIndexClient(
                api_key=self.settings.llm_api_key,
                model=self._pageindex_model_name(),
                retrieve_model=self._pageindex_model_name(),
                workspace=str(workspace),
            )
            pageindex_doc_id = client.index(str(pageindex_source_path), mode=mode)
            structure_status = self._write_normalized_structure(
                client=client,
                workspace=workspace,
                pageindex_doc_id=pageindex_doc_id,
                doc_uid=resolved_doc_uid,
                source_path=pageindex_source_path,
                mode=mode,
                source_hash=str(document["source_hash"]),
            )
        self.upsert_index_record(
            resolved_knowledge_base_id,
            resolved_doc_uid,
            pageindex_doc_id,
            source_hash=str(document["source_hash"]),
        )

        return {
            "knowledge_base_id": resolved_knowledge_base_id,
            "doc_uid": resolved_doc_uid,
            "pageindex_doc_id": pageindex_doc_id,
            "workspace_path": str(workspace),
            "status": "ready",
            "structure_status": structure_status,
            "rebuild": rebuild,
        }

    def upsert_index_record(
        self,
        knowledge_base_id: str,
        doc_uid: str,
        pageindex_doc_id: str,
        *,
        source_hash: str,
    ) -> None:
        """写入或更新 PageIndex 索引记录，测试和构建流程共用。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_doc_uid = self._require_doc_uid(doc_uid)
        resolved_pageindex_doc_id = str(pageindex_doc_id or "").strip()
        if not resolved_pageindex_doc_id:
            raise ValidationAppError("PageIndex 文档 ID 不能为空")

        now = utc_now_iso()
        workspace = self._document_workspace(resolved_knowledge_base_id, resolved_doc_uid)
        self.index_repository.upsert_index_record(
            knowledge_base_id=resolved_knowledge_base_id,
            doc_uid=resolved_doc_uid,
            pageindex_doc_id=resolved_pageindex_doc_id,
            workspace_path=str(workspace),
            source_hash=str(source_hash or ""),
            created_at=now,
            updated_at=now,
        )

    def get_tree_rows(self, knowledge_base_id: str, doc_uid: str) -> list[list[object]]:
        """读取 PageIndex 文档结构，并转换为页面表格行。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_doc_uid = self._require_doc_uid(doc_uid)
        record = self.index_repository.get_index_record(resolved_knowledge_base_id, resolved_doc_uid)
        if record is None:
            raise NotFoundAppError(
                "当前文档尚未构建 PageIndex",
                details={"knowledge_base_id": resolved_knowledge_base_id, "doc_uid": resolved_doc_uid},
            )
        structure = self._load_structure(record)
        rows: list[list[object]] = []
        for node in tree_retriever.flatten_structure(structure):
            rows.append(
                [
                    int(node.get("level") or 1),
                    str(node.get("title") or ""),
                    tree_retriever.format_node_position(node),
                    str(node.get("summary") or node.get("prefix_summary") or ""),
                ]
            )
        return rows

    def ask_question(self, knowledge_base_id: str, doc_uid: str, question: str, *, template_id: str | None = None) -> dict:
        """基于 PageIndex 本地结构定位证据，并保存问答历史。"""

        normalized_question = str(question or "").strip()
        if not normalized_question:
            raise ValidationAppError("问题不能为空")
        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_doc_uid = self._require_doc_uid(doc_uid)
        record = self.index_repository.get_index_record(resolved_knowledge_base_id, resolved_doc_uid)
        if record is None:
            raise NotFoundAppError(
                "当前文档尚未构建 PageIndex",
                details={"knowledge_base_id": resolved_knowledge_base_id, "doc_uid": resolved_doc_uid},
            )
        structure = self._load_structure(record)
        retrieval_result = self._answer_with_reasoning_or_fallback(
            record,
            structure,
            normalized_question,
            template_id=template_id,
            budget=PageIndexBudget(
                max_llm_calls=6,
                max_rounds=3,
                max_documents=1,
                max_evidence=8,
            ),
        )
        evidence = retrieval_result["evidence"]
        answer_text = retrieval_result["answer"]
        query_id = f"piq_{uuid4().hex[:12]}"
        created_at = utc_now_iso()

        self.index_repository.insert_query_history(
            query_id=query_id,
            knowledge_base_id=str(record["knowledge_base_id"]),
            doc_uid=str(record["doc_uid"]),
            question=normalized_question,
            answer=str(answer_text),
            evidence_json=json.dumps(evidence, ensure_ascii=False),
            debug_json=json.dumps(retrieval_result.get("debug", {}), ensure_ascii=False),
            created_at=created_at,
        )

        return {
            "query_id": query_id,
            "knowledge_base_id": record["knowledge_base_id"],
            "doc_uid": record["doc_uid"],
            "question": normalized_question,
            "answer": answer_text,
            "evidence": evidence,
            "retrieval_mode": retrieval_result["retrieval_mode"],
            "llm_error": retrieval_result.get("llm_error", ""),
            "debug": retrieval_result.get("debug", {}),
            "created_at": created_at,
        }

    def ask_knowledge_base_question(self, knowledge_base_id: str, question: str, *, template_id: str | None = None) -> dict:
        """在当前知识库所有已构建 PageIndex 文档中提问，并保存问答历史。"""

        normalized_question = str(question or "").strip()
        if not normalized_question:
            raise ValidationAppError("问题不能为空")
        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        records = self.index_repository.list_index_records(resolved_knowledge_base_id)
        if not records:
            raise NotFoundAppError("当前知识库尚未构建 PageIndex")
        retrieval_result = self._answer_knowledge_base_with_reasoning_or_fallback(records, normalized_question, template_id=template_id)
        evidence = retrieval_result["evidence"]
        answer_text = retrieval_result["answer"]
        history_doc_uid = self._resolve_history_doc_uid(records, evidence)
        query_id = f"piq_{uuid4().hex[:12]}"
        created_at = utc_now_iso()

        self.index_repository.insert_query_history(
            query_id=query_id,
            knowledge_base_id=str(records[0]["knowledge_base_id"]),
            doc_uid=history_doc_uid,
            question=normalized_question,
            answer=str(answer_text),
            evidence_json=json.dumps(evidence, ensure_ascii=False),
            debug_json=json.dumps(retrieval_result.get("debug", {}), ensure_ascii=False),
            created_at=created_at,
        )

        return {
            "query_id": query_id,
            "knowledge_base_id": records[0]["knowledge_base_id"],
            "doc_uid": history_doc_uid,
            "question": normalized_question,
            "answer": answer_text,
            "evidence": evidence,
            "retrieval_mode": retrieval_result["retrieval_mode"],
            "llm_error": retrieval_result.get("llm_error", ""),
            "debug": retrieval_result.get("debug", {}),
            "created_at": created_at,
        }

    def list_query_history(self, knowledge_base_id: str, doc_uid: str, *, limit: int = 50) -> list[dict]:
        """读取当前知识库与文档下的 PageIndex 问答历史。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_doc_uid = self._require_doc_uid(doc_uid)
        rows = self.index_repository.list_query_history(
            resolved_knowledge_base_id,
            resolved_doc_uid,
            max(1, int(limit)),
        )
        return parse_history_rows(rows)

    def list_knowledge_base_query_history(self, knowledge_base_id: str, *, limit: int = 50) -> list[dict]:
        """读取当前知识库下所有 PageIndex 问答历史。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        rows = self.index_repository.list_knowledge_base_query_history(
            resolved_knowledge_base_id,
            max(1, int(limit)),
        )
        return parse_history_rows(rows)

    def get_query_history_record(self, knowledge_base_id: str, doc_uid: str, query_id: str) -> dict:
        """按记录 ID 读取当前知识库与文档下的一条 PageIndex 问答历史。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_doc_uid = self._require_doc_uid(doc_uid)
        resolved_query_id = str(query_id or "").strip()
        if not resolved_query_id:
            raise ValidationAppError("请先从历史记录中选择要下载的结果")
        row = self.index_repository.get_query_history_record(
            resolved_knowledge_base_id,
            resolved_doc_uid,
            resolved_query_id,
        )
        if row is None:
            raise NotFoundAppError("未找到选中的 PageIndex 历史记录")
        return parse_history_rows([row])[0]

    def get_knowledge_base_query_history_record(self, knowledge_base_id: str, query_id: str) -> dict:
        """按记录 ID 读取当前知识库下的一条 PageIndex 问答历史。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_query_id = str(query_id or "").strip()
        if not resolved_query_id:
            raise ValidationAppError("请先从历史记录中选择要下载的结果")
        row = self.index_repository.get_knowledge_base_query_history_record(
            resolved_knowledge_base_id,
            resolved_query_id,
        )
        if row is None:
            raise NotFoundAppError("未找到选中的 PageIndex 历史记录")
        return parse_history_rows([row])[0]

    def export_query_markdown(self, knowledge_base_id: str, doc_uid: str, query_id: str) -> str:
        """将当前激活的 PageIndex 历史记录导出为 Markdown。"""

        record = self.get_query_history_record(knowledge_base_id, doc_uid, query_id)
        return format_history_markdown(
            knowledge_base_id=str(record.get("knowledge_base_id") or ""),
            doc_uid=str(record.get("doc_uid") or ""),
            history=[record],
        )

    def export_knowledge_base_query_markdown(self, knowledge_base_id: str, query_id: str) -> str:
        """将当前知识库下激活的 PageIndex 历史记录导出为 Markdown。"""

        record = self.get_knowledge_base_query_history_record(knowledge_base_id, query_id)
        return format_history_markdown(
            knowledge_base_id=str(record.get("knowledge_base_id") or ""),
            doc_uid=str(record.get("doc_uid") or ""),
            history=[record],
        )

    def export_history_markdown(self, knowledge_base_id: str, doc_uid: str) -> str:
        """将当前知识库与文档下的 PageIndex 历史导出为 Markdown。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_doc_uid = self._require_doc_uid(doc_uid)
        history = list(reversed(self.list_query_history(resolved_knowledge_base_id, resolved_doc_uid, limit=200)))
        if not history:
            raise ValidationAppError("暂无可导出的 PageIndex 问答历史")
        return format_history_markdown(
            knowledge_base_id=resolved_knowledge_base_id,
            doc_uid=resolved_doc_uid,
            history=history,
        )

    def _get_document(self, knowledge_base_id: str, doc_uid: str) -> dict:
        """读取并校验文档归属，防止跨知识库构建。"""

        try:
            with create_connection(self.settings.sqlite_db_path) as connection:
                row = connection.execute(
                    """
                    SELECT doc_uid, knowledge_base_id, doc_title, source_path, source_hash
                    FROM documents
                    WHERE knowledge_base_id = ? AND doc_uid = ?
                    """,
                    (knowledge_base_id, doc_uid),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise DatabaseAppError("读取 PageIndex 文档失败", details={"reason": str(exc)}) from exc
        if not row:
            raise NotFoundAppError("当前知识库下未找到指定文档", details={"knowledge_base_id": knowledge_base_id, "doc_uid": doc_uid})
        return dict(row)

    def _answer_knowledge_base_with_reasoning_or_fallback(self, records: list[dict], question: str, *, template_id: str | None = None) -> dict:
        """聚合当前知识库内多篇 PageIndex 文档的问答证据。"""

        # 知识库问答共享一份预算；轮次必须按文档数扩展，否则第一篇文档
        # 消耗完 3 轮后，第二篇文档和最终回答会被误判为预算耗尽。
        routed_document_limit = min(len(records), 3)
        budget = PageIndexBudget(
            max_llm_calls=max(6, 1 + routed_document_limit * 4 + 1),
            max_rounds=max(3, routed_document_limit * 3),
            max_documents=3,
            max_evidence=8,
        )
        try:
            question_analysis = self._analyze_question(question, budget=budget)
        except RetrievalBudgetExceededError:
            question_analysis = {
                "mode": "预算内本地关键词",
                "intent": "",
                "entities": [],
                "keywords": self._extract_question_terms(question),
                "expanded_terms": [],
            }
        routed_records = budget.limit_documents(
            route_documents(question, records, question_analysis, limit=budget.max_documents)
        )
        evidence: list[dict] = []
        candidate_nodes: list[dict] = []
        rag_evidence: list[dict] = []
        llm_errors: list[str] = []
        question_plans: list[dict] = []
        document_retrieval_rounds: list[dict] = []
        for record in routed_records:
            try:
                structure = self._load_structure(record)
                result = self._answer_with_reasoning_or_fallback(
                    record,
                    structure,
                    question,
                    template_id=template_id,
                    budget=budget,
                    question_analysis=question_analysis,
                    finalize_answer=False,
                )
            except AppError as exc:
                llm_errors.append(exc.message)
                continue
            evidence = self._merge_evidence(evidence, result.get("evidence") if isinstance(result.get("evidence"), list) else [])
            evidence = self.answer_orchestrator.classify_evidence_items(question, evidence)
            debug = result.get("debug") if isinstance(result.get("debug"), dict) else {}
            for item in debug.get("candidate_nodes") or []:
                if isinstance(item, dict):
                    candidate_nodes.append(item)
            for item in debug.get("rag_evidence") or []:
                if isinstance(item, dict):
                    rag_evidence.append(item)
            question_plan = debug.get("question_plan")
            if isinstance(question_plan, dict) and question_plan:
                question_plans.append(question_plan)
            retrieval_rounds = debug.get("retrieval_rounds")
            if isinstance(retrieval_rounds, list):
                document_retrieval_rounds.append(
                    {
                        "doc_uid": str(record.get("doc_uid") or ""),
                        "pageindex_doc_id": str(record.get("pageindex_doc_id") or ""),
                        "rounds": retrieval_rounds,
                    }
                )
            if result.get("llm_error"):
                llm_errors.append(str(result.get("llm_error") or ""))
            if budget.exhausted:
                break

        evidence = budget.limit_evidence(evidence)
        if not evidence and llm_errors:
            raise ValidationAppError("当前知识库 PageIndex 检索失败", details={"reason": "；".join(llm_errors)})
        aggregate_question_plan = question_plans[0] if question_plans else {}
        answer = self.answer_orchestrator.build_local_answer(
            question,
            evidence,
            question_plan=aggregate_question_plan,
        )
        if evidence and not budget.exhausted:
            try:
                llm_client = self._get_llm_client()
                answer_payload = self.answer_orchestrator.generate_llm_answer_payload(
                    llm_client,
                    question,
                    evidence,
                    template_id=template_id,
                    question_plan=aggregate_question_plan,
                    budget=budget,
                )
                answer = str(answer_payload.get("answer") or answer)
                aggregate_question_plan = answer_payload.get("question_plan") if isinstance(answer_payload.get("question_plan"), dict) else aggregate_question_plan
            except Exception as exc:  # noqa: BLE001
                llm_errors.append(str(exc))
        return {
            "evidence": evidence,
            "answer": answer,
            "retrieval_mode": "知识库多文档检索",
            "llm_error": "；".join(dict.fromkeys(item for item in llm_errors if item)),
            "debug": {
                "retrieval_mode": "知识库多文档检索",
                "candidate_nodes": candidate_nodes,
                "rag_evidence": rag_evidence,
                "selected_nodes": candidate_nodes[: len(evidence)],
                "question_plan": aggregate_question_plan,
                "document_question_plans": question_plans,
                "document_retrieval_rounds": document_retrieval_rounds,
                "routed_documents": [
                    {
                        "doc_uid": str(item.get("doc_uid") or ""),
                        "doc_title": str(item.get("doc_title") or ""),
                        "routing_score": int(item.get("routing_score") or 0),
                        "routing_reason": str(item.get("routing_reason") or ""),
                    }
                    for item in routed_records
                ],
                "budget": budget.snapshot(),
            },
        }

    @staticmethod
    def _resolve_history_doc_uid(records: list[dict], evidence: list[dict]) -> str:
        """历史表仍需 doc_uid，优先挂到首条证据所属文档。"""

        for item in evidence:
            doc_uid = str(item.get("doc_uid") or "").strip()
            if doc_uid:
                return doc_uid
        return str(records[0].get("doc_uid") or "")

    def _answer_with_reasoning_or_fallback(
        self,
        record: dict,
        structure: list[dict],
        question: str,
        *,
        template_id: str | None = None,
        budget: PageIndexBudget | None = None,
        question_analysis: dict | None = None,
        finalize_answer: bool = True,
    ) -> dict:
        """优先用 LLM 对 PageIndex 树做语义推理，失败时回退到本地关键词。"""

        active_budget = budget or PageIndexBudget(
            max_llm_calls=6,
            max_rounds=3,
            max_documents=1,
            max_evidence=8,
        )
        resolved_analysis = question_analysis or self._analyze_question(question, budget=active_budget)
        try:
            evidence, answer, debug = self._answer_with_iterative_tree_reasoning(
                record,
                structure,
                question,
                resolved_analysis,
                template_id=template_id,
                budget=active_budget,
                finalize_answer=finalize_answer,
            )
            evidence = self.answer_orchestrator.classify_evidence_items(question, evidence)
            if evidence:
                debug["retrieval_mode"] = "LLM 语义树推理"
                debug["question_analysis"] = resolved_analysis
                debug["budget"] = active_budget.snapshot()
                return {
                    "evidence": evidence,
                    "answer": answer or self.answer_orchestrator.build_local_answer(
                        question,
                        evidence,
                        question_plan=debug.get("question_plan") if isinstance(debug, dict) else None,
                    ),
                    "retrieval_mode": "LLM 语义树推理",
                    "llm_error": "",
                    "debug": debug,
                }
            debug["retrieval_mode"] = "LLM 语义树推理"
            debug["question_analysis"] = resolved_analysis
            debug["budget"] = active_budget.snapshot()
            return {
                "evidence": [],
                "answer": self.answer_orchestrator.build_local_answer(
                    question,
                    [],
                    question_plan=debug.get("question_plan") if isinstance(debug, dict) else None,
                ),
                "retrieval_mode": "LLM 语义树推理",
                "llm_error": "",
                "debug": debug,
            }
        except RetrievalBudgetExceededError as exc:
            llm_error = exc.message
        except Exception as exc:  # noqa: BLE001
            llm_error = str(exc)
        else:
            llm_error = ""

        evidence, candidate_nodes = self._rank_evidence(record, structure, question, resolved_analysis)
        rag_evidence = self._search_rag_fts_evidence(record, question, resolved_analysis)
        evidence = self._merge_evidence(evidence, rag_evidence)
        evidence = active_budget.limit_evidence(evidence)
        evidence = self.answer_orchestrator.classify_evidence_items(question, evidence)
        return {
            "evidence": evidence,
            "answer": self.answer_orchestrator.build_local_answer(
                question,
                evidence,
                question_plan=None,
            ),
            "retrieval_mode": "本地关键词降级",
            "llm_error": llm_error,
            "debug": {
                "retrieval_mode": "本地关键词降级",
                "question_analysis": resolved_analysis,
                "candidate_nodes": candidate_nodes,
                "rag_evidence": rag_evidence,
                "selected_nodes": candidate_nodes[: len(evidence)],
                "llm_error": llm_error,
                "budget": active_budget.snapshot(),
            },
        }

    def _answer_with_iterative_tree_reasoning(
        self,
        record: dict,
        structure: list[dict],
        question: str,
        question_analysis: dict,
        *,
        template_id: str | None = None,
        max_rounds: int = 3,
        budget: PageIndexBudget | None = None,
        finalize_answer: bool = True,
    ) -> tuple[list[dict], str, dict]:
        """让 LLM 多轮选择 PageIndex 节点，证据不足时继续检索。"""

        llm_client = self._get_llm_client()
        client = PageIndexClient(workspace=str(record["workspace_path"]))
        evidence: list[dict] = []
        selected_debug: list[dict] = []
        retrieval_rounds: list[dict] = []
        candidate_debug_by_id: dict[str, dict] = {}
        selected_candidate_ids: set[str] = set()
        cross_reference_candidates: list[dict] = []
        answer = ""
        debug_error = ""
        active_budget = budget or PageIndexBudget(
            max_llm_calls=6,
            max_rounds=max_rounds,
            max_documents=1,
            max_evidence=8,
        )
        retrieval_question_plan = self.answer_orchestrator.build_question_plan(
            llm_client,
            question,
            [],
            budget=active_budget,
        )
        retrieval_policy = self._resolve_pageindex_retrieval_policy(template_id)
        max_tree_candidates = int(retrieval_policy.get("max_tree_candidates", 30))
        max_selected_nodes = int(retrieval_policy.get("max_selected_nodes", 3))
        max_rag_evidence = int(retrieval_policy.get("max_rag_evidence", 2))
        search_focus = ""

        for round_index in range(1, max(1, int(max_rounds or 3)) + 1):
            active_budget.consume_round(f"node_selection_round_{round_index}")
            round_question = (
                f"{question}\n本轮补充检索重点：{search_focus}"
                if search_focus
                else question
            )
            round_analysis = dict(question_analysis)
            if search_focus:
                round_analysis["expanded_terms"] = [
                    *(question_analysis.get("expanded_terms") or []),
                    search_focus,
                ]
            candidates = self._build_tree_candidates(
                record,
                structure,
                question=round_question,
                question_analysis=round_analysis,
                limit=max_tree_candidates,
                include_content=True,
            )
            # 交叉引用候选保留 xref ID，避免被同标题的普通焦点候选覆盖。
            candidates = tree_retriever.merge_tree_candidates(cross_reference_candidates, candidates)
            candidates = [item for item in candidates if str(item.get("candidate_id") or "") not in selected_candidate_ids]
            for candidate in candidates:
                candidate_debug_by_id[str(candidate.get("candidate_id") or "")] = tree_retriever.candidate_to_debug(candidate)
            if not candidates:
                retrieval_rounds.append(
                    {
                        "round": round_index,
                        "search_focus": search_focus,
                        "candidate_node_ids": [],
                        "selected_nodes": [],
                        "sufficiency": "insufficient",
                        "missing_information": "PageIndex 树标题和摘要未召回候选节点",
                        "next_search_focus": "使用同文档 RAG/FTS 原文片段补充召回",
                    }
                )
                break

            system_prompt, user_prompt = self._build_iterative_tree_reasoning_prompts(
                round_question,
                round_analysis,
                retrieval_question_plan,
                candidates,
                evidence,
                round_index,
            )
            active_budget.consume_llm(f"node_selection_round_{round_index}")
            selection = llm_client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
            if not isinstance(selection, dict):
                debug_error = "LLM 迭代检索返回格式无效"
                retrieval_rounds.append(
                    {
                        "round": round_index,
                        "search_focus": search_focus,
                        "candidate_node_ids": [str(item.get("candidate_id") or "") for item in candidates],
                        "selected_nodes": [],
                        "sufficiency": "insufficient",
                        "missing_information": debug_error,
                        "next_search_focus": "",
                    }
                )
                break

            selected_items = selection.get("selected_nodes")
            if not isinstance(selected_items, list):
                selected_items = []
            sufficiency = self._normalize_retrieval_sufficiency(selection.get("sufficiency"))
            missing_information = str(selection.get("missing_information") or "").strip()
            next_search_focus = str(selection.get("next_search_focus") or "").strip()
            answer = str(selection.get("answer") or answer or "").strip()
            candidate_map = {str(item["candidate_id"]): item for item in candidates}
            round_selected_debug: list[dict] = []

            for selected in selected_items[:max(0, max_selected_nodes)]:
                if not isinstance(selected, dict):
                    continue
                candidate_id = str(selected.get("candidate_id") or "")
                candidate = candidate_map.get(candidate_id)
                if not candidate:
                    continue
                selected_candidate_ids.add(candidate_id)
                node = candidate["node"]
                line_num = int(node.get("line_num") or 0)
                evidence.append(
                    {
                        "title": str(node.get("title") or ""),
                        "position": tree_retriever.format_node_position(node),
                        "summary": str(node.get("summary") or node.get("prefix_summary") or ""),
                        "content": self._load_node_content(client, str(record["pageindex_doc_id"]), line_num),
                        "reason": str(selected.get("reason") or "LLM 迭代语义推理选中"),
                        "source_type": "PageIndex 节点",
                        "doc_uid": str(record.get("doc_uid") or ""),
                        "pageindex_doc_id": str(record.get("pageindex_doc_id") or ""),
                        "node_id": str(node.get("node_id") or candidate_id),
                        "heading_path": str(node.get("heading_path") or ""),
                        "source_start_line": node.get("source_start_line"),
                        "source_end_line": node.get("source_end_line"),
                        "source_anchor": str(node.get("source_anchor") or ""),
                        "retrieval_round": round_index,
                        "local_score": int(candidate.get("score") or 0),
                        "degraded_reason": "",
                    }
                )
                debug_item = {
                    **tree_retriever.candidate_to_debug(candidate),
                    "reason": str(selected.get("reason") or "LLM 迭代语义推理选中"),
                }
                round_selected_debug.append(debug_item)
                selected_debug.append(debug_item)

            new_targets: list[str] = []
            for item in evidence[-len(round_selected_debug) :] if round_selected_debug else []:
                new_targets.extend(tree_retriever.extract_cross_reference_targets(str(item.get("content") or "")))
            if new_targets:
                cross_reference_candidates = tree_retriever.merge_tree_candidates(
                    cross_reference_candidates,
                    tree_retriever.find_cross_reference_candidates(structure, new_targets),
                )

            retrieval_rounds.append(
                {
                    "round": round_index,
                    "search_focus": search_focus,
                    "candidate_node_ids": [str(item.get("candidate_id") or "") for item in candidates],
                    "selected_nodes": round_selected_debug,
                    "sufficiency": sufficiency,
                    "missing_information": missing_information,
                    "next_search_focus": next_search_focus,
                }
            )
            search_focus = next_search_focus
            if sufficiency == "sufficient" and evidence:
                break
            if not round_selected_debug:
                break

        # PageIndex 树摘要可能缺少用户问题中的细粒度疾病/指标词；只有树候选为 0 时才启用 RAG 兜底，避免覆盖 LLM 明确拒选的判断。
        rag_evidence = self._search_rag_fts_evidence(record, question, question_analysis, max_results=max_rag_evidence) if evidence or not candidate_debug_by_id else []
        evidence = self._merge_evidence(evidence, rag_evidence)
        evidence = active_budget.limit_evidence(evidence)
        evidence = self.answer_orchestrator.classify_evidence_items(question, evidence)
        question_plan: dict = {}
        if evidence and finalize_answer:
            try:
                answer_payload = self.answer_orchestrator.generate_llm_answer_payload(
                    llm_client,
                    question,
                    evidence,
                    template_id=template_id,
                    question_plan=retrieval_question_plan,
                    budget=active_budget,
                )
                answer = str(answer_payload.get("answer") or answer or "")
                question_plan = answer_payload.get("question_plan") if isinstance(answer_payload.get("question_plan"), dict) else {}
            except Exception:  # noqa: BLE001
                if not answer:
                    answer = self.answer_orchestrator.build_local_answer(
                        question,
                        evidence,
                        question_plan=retrieval_question_plan,
                    )
        return evidence, answer, {
            "candidate_nodes": list(candidate_debug_by_id.values()),
            "rag_evidence": rag_evidence,
            "selected_nodes": selected_debug,
            "retrieval_rounds": retrieval_rounds,
            "question_plan": question_plan or retrieval_question_plan,
            "retrieval_question_plan": retrieval_question_plan,
            "retrieval_policy": retrieval_policy,
            "llm_error": debug_error,
            "budget": active_budget.snapshot(),
        }

    @staticmethod
    def _normalize_retrieval_sufficiency(value: object) -> str:
        """规范化 LLM 返回的信息充分性标签。"""

        normalized = str(value or "").strip().lower()
        if normalized in {"sufficient", "partial", "insufficient"}:
            return normalized
        return "insufficient"

    def _get_llm_client(self) -> object:
        """获取 PageIndex 语义推理使用的 LLM 客户端。"""

        if self.llm_client is not None:
            return self.llm_client
        llm_client = build_llm_client(self.settings)
        if isinstance(llm_client, DisabledLLMClient):
            raise ValidationAppError("PageIndex 语义检索需要启用 LLM")
        self.llm_client = llm_client
        return llm_client

    def _analyze_question(
        self,
        question: str,
        *,
        budget: PageIndexBudget | None = None,
    ) -> dict:
        """分析问题意图与扩展关键词，LLM 不可用时使用本地关键词。"""

        local_terms = self._extract_question_terms(question)
        fallback = {
            "mode": "本地关键词",
            "intent": "",
            "entities": [],
            "keywords": local_terms,
            "expanded_terms": [],
        }
        try:
            llm_client = self._get_llm_client()
            if budget is not None:
                budget.consume_llm("question_analysis")
            result = llm_client.complete_json(
                system_prompt="你是中文文档问题分析助手。请抽取问题意图、实体、关键词和同义扩展词，只返回 JSON。",
                user_prompt="\n".join(
                    [
                        "用户问题：",
                        question,
                        "",
                        '请返回 JSON：{"intent":"问题意图","entities":["实体"],"keywords":["关键词"],"expanded_terms":["同义或相关表达"]}',
                    ]
                ),
            )
        except RetrievalBudgetExceededError:
            raise
        except Exception:  # noqa: BLE001
            return fallback

        keywords = self._normalize_term_list(result.get("keywords")) or local_terms
        return {
            "mode": "LLM 问题分析",
            "intent": str(result.get("intent") or ""),
            "entities": self._normalize_term_list(result.get("entities")),
            "keywords": keywords,
            "expanded_terms": self._normalize_term_list(result.get("expanded_terms")),
        }

    def _build_tree_candidates(
        self,
        record: dict,
        structure: list[dict],
        *,
        question: str = "",
        question_analysis: dict | None = None,
        limit: int = 80,
        include_content: bool = False,
    ) -> list[dict]:
        """准备问题词与可选原文读取器，并构建树候选。"""

        question_text = str(question or (question_analysis or {}).get("question") or "")
        raw_terms = self._normalize_term_list(
            [
                *self._analysis_terms(question_analysis or {}),
                *self._extract_question_terms(question_text),
            ]
        )
        terms = self._build_tree_scoring_terms(raw_terms, question_text)
        client = PageIndexClient(workspace=str(record["workspace_path"])) if include_content else None

        def load_content(node: dict) -> str:
            """通过现有 vendor client 读取节点原文。"""

            return self._load_node_content(
                client,
                str(record["pageindex_doc_id"]),
                int(node.get("line_num") or 0),
            )

        return tree_retriever.build_tree_candidates(
            structure,
            terms,
            limit=limit,
            content_loader=load_content if client is not None else None,
        )

    @staticmethod
    def _build_iterative_tree_reasoning_prompts(
        question: str,
        question_analysis: dict,
        question_plan: dict,
        candidates: list[dict],
        retrieved_evidence: list[dict],
        round_index: int,
    ) -> tuple[str, str]:
        """构建 PageIndex 迭代式树推理检索提示词。"""

        system_prompt = (
            "你是 PageIndex 迭代式树结构检索助手。请基于用户问题、已读证据和候选节点，"
            "选择下一批最值得读取的节点，并判断当前信息是否足够回答问题。只返回 JSON，不要输出额外文本。"
        )
        safe_candidates = [
            {
                "candidate_id": str(item.get("candidate_id") or ""),
                "title": str(item.get("title") or ""),
                "level": int(item.get("level") or 1),
                "position": str(item.get("position") or ""),
                "summary": str(item.get("summary") or ""),
                "content_excerpt": str(item.get("content_excerpt") or "")[:900],
                "score": int(item.get("score") or 0),
                "reason": str(item.get("reason") or ""),
            }
            for item in candidates
        ]
        evidence_preview = [
            {
                "title": str(item.get("title") or item.get("source_type") or ""),
                "position": str(item.get("position") or item.get("source_anchor") or ""),
                "content_excerpt": str(item.get("content") or item.get("summary") or "")[:700],
                "reason": str(item.get("reason") or ""),
            }
            for item in retrieved_evidence[:8]
        ]
        user_prompt = "\n".join(
            [
                f"检索轮次：{max(1, int(round_index or 1))}",
                "",
                "用户问题：",
                str(question or ""),
                "",
                "问题分析 JSON：",
                json.dumps(question_analysis or {}, ensure_ascii=False),
                "",
                "Question Plan JSON：",
                json.dumps(question_plan or {}, ensure_ascii=False),
                "",
                "已读证据 JSON：",
                json.dumps(evidence_preview, ensure_ascii=False),
                "",
                "候选 PageIndex 节点 JSON：",
                json.dumps(safe_candidates, ensure_ascii=False),
                "",
                "请返回 JSON：",
                json.dumps(
                    {
                        "selected_nodes": [{"candidate_id": "node_1", "reason": "选择理由"}],
                        "sufficiency": "sufficient | partial | insufficient",
                        "missing_information": "还缺什么信息",
                        "next_search_focus": "下一轮应该找什么",
                        "answer": "基于当前证据的临时答案",
                    },
                    ensure_ascii=False,
                ),
                "要求：每轮最多选择 3 个节点；如果当前证据已足够回答，sufficiency 返回 sufficient；"
                "如果仍缺关键信息，返回 partial 或 insufficient，并写清 missing_information 和 next_search_focus。",
                "候选选择必须服从 Question Plan：information_extraction 优先选择能列举对象、方法、步骤、类别或清单的节点；"
                "claim_judgement 优先选择能直接支持、反对或限定命题的节点；source_location 优先选择可定位出处和原文位置的节点；"
                "summary 优先选择覆盖面更完整的上层概述节点；comparison 优先选择同时覆盖比较对象或比较维度的节点。",
            ]
        )
        return system_prompt, user_prompt

    def _resolve_existing_source_path(self, document: dict) -> Path:
        """解析源文档路径；历史路径失效时修复到当前 Input 知识库目录。"""

        raw_source_path = Path(str(document["source_path"]))
        knowledge_base_id = str(document.get("knowledge_base_id") or "").strip()
        doc_uid = str(document.get("doc_uid") or "").strip()
        try:
            source_path = resolve_input_path(raw_source_path, self.settings.input_root)
        except ValidationAppError:
            source_path = raw_source_path
        else:
            if source_path.exists():
                stored_source_path = to_input_relative_path(source_path, self.settings.input_root)
                if str(document.get("source_path") or "") != stored_source_path:
                    self._update_document_source_path(knowledge_base_id, doc_uid, stored_source_path)
                return source_path

        candidates = self._build_source_path_repair_candidates(raw_source_path, knowledge_base_id)
        for candidate in candidates:
            if not candidate.exists():
                continue
            repaired_path = candidate.resolve()
            self._update_document_source_path(
                knowledge_base_id,
                doc_uid,
                to_input_relative_path(repaired_path, self.settings.input_root),
            )
            return repaired_path
        return source_path

    def _update_document_source_path(self, knowledge_base_id: str, doc_uid: str, source_path: str) -> None:
        """将修复后的文档路径写回数据库，数据库只保存 Input 相对路径。"""

        with transaction(self.settings.sqlite_db_path) as connection:
            connection.execute(
                """
                UPDATE documents
                SET source_path = ?, updated_at = ?
                WHERE knowledge_base_id = ? AND doc_uid = ?
                """,
                (source_path, utc_now_iso(), knowledge_base_id, doc_uid),
            )

    def _build_source_path_repair_candidates(self, source_path: Path, knowledge_base_id: str) -> list[Path]:
        """根据历史 source_path 生成当前项目下的候选修复路径。"""

        candidates: list[Path] = []
        parts = list(source_path.parts)
        normalized_parts = [part.lower() for part in parts]
        if "input" in normalized_parts:
            input_index = normalized_parts.index("input")
            relative_parts = parts[input_index + 1 :]
            if relative_parts:
                candidates.append((self.settings.input_root / Path(*relative_parts)).resolve())
        if knowledge_base_id:
            candidates.append((self.settings.input_root / knowledge_base_id / source_path.name).resolve())
        candidates.append((self.settings.input_root / source_path.name).resolve())

        unique_candidates: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(candidate)
        return unique_candidates

    def _prepare_pageindex_source_path(self, source_path: Path, workspace: Path) -> Path:
        """为 PageIndex 构建准备输入文件，Markdown 使用清洗副本且不改原文。"""

        if source_path.suffix.lower() not in {".md", ".markdown"}:
            return source_path
        raw_text = source_path.read_text(encoding="utf-8")
        cleaned_text = self._clean_markdown_for_pageindex(raw_text)
        prepared_path = workspace / "source.cleaned.md"
        prepared_path.write_text(cleaned_text, encoding="utf-8")
        return prepared_path

    @staticmethod
    def _clean_markdown_for_pageindex(markdown_text: str) -> str:
        """清理 PageIndex 建树噪音，保留标题和正文。"""

        cleaned_lines: list[str] = []
        blank_pending = False
        for raw_line in markdown_text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if re.fullmatch(r"!\[[^\]]*]\([^)]+\)", stripped):
                continue
            if stripped in {"目 录", "目录", "TABLE OF CONTENTS", "Table of Contents"}:
                continue
            if re.fullmatch(r"[-—_]{3,}", stripped):
                continue
            if not stripped:
                if cleaned_lines and not blank_pending:
                    cleaned_lines.append("")
                    blank_pending = True
                continue
            cleaned_lines.append(line)
            blank_pending = False
        return "\n".join(cleaned_lines).strip() + "\n"

    def _load_structure(self, record: dict) -> list[dict]:
        """优先读取通过质量门禁的规范化树，旧索引显式标记为 legacy。"""

        self._ensure_pageindex_available()
        workspace_path = Path(str(record["workspace_path"]))
        normalized_path = workspace_path / "structure.normalized.json"
        if normalized_path.exists():
            try:
                payload = json.loads(normalized_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValidationAppError(
                    "PageIndex 规范化结构 JSON 无效",
                    details={"reason": str(exc), "index_status": "stale_index"},
                ) from exc
            structure = payload.get("structure") if isinstance(payload, dict) else None
            expected_hash = str(record.get("source_hash") or "")
            current_hash = str(record.get("current_source_hash") or expected_hash)
            manifest_hash = str(payload.get("source_hash") or "") if isinstance(payload, dict) else ""
            if not expected_hash or current_hash != expected_hash or manifest_hash != expected_hash:
                raise ValidationAppError(
                    "stale_index：PageIndex 来源哈希已变化，请重建索引",
                    details={
                        "index_status": "stale_index",
                        "index_source_hash": expected_hash,
                        "current_source_hash": current_hash,
                        "manifest_source_hash": manifest_hash,
                    },
                )
            if payload.get("status") != "ready" or not isinstance(structure, list):
                raise ValidationAppError(
                    "PageIndex 规范化结构未通过质量门禁",
                    details={"index_status": "stale_index"},
                )
            return structure
        if not (workspace_path / "_meta.json").exists():
            raise ValidationAppError(
                "PageIndex 索引文件缺失",
                details={"workspace_path": str(workspace_path)},
            )
        client = PageIndexClient(workspace=str(workspace_path))
        raw_structure = client.get_document_structure(str(record["pageindex_doc_id"]))
        try:
            structure = json.loads(raw_structure)
        except json.JSONDecodeError as exc:
            raise ValidationAppError("PageIndex 结构 JSON 无效", details={"reason": str(exc)}) from exc
        if isinstance(structure, dict) and structure.get("error"):
            raise NotFoundAppError("PageIndex 结构不存在", details={"reason": str(structure.get("error"))})
        if not isinstance(structure, list):
            raise ValidationAppError("PageIndex 结构格式无效")
        for node in structure:
            if isinstance(node, dict):
                node.setdefault("_structure_status", "legacy")
        return structure

    def _write_normalized_structure(
        self,
        *,
        client: object,
        workspace: Path,
        pageindex_doc_id: str,
        doc_uid: str,
        source_path: Path,
        mode: str,
        source_hash: str,
    ) -> str:
        """增强 vendor 结构并在质量通过后原子写入规范化文件。"""

        get_structure = getattr(client, "get_document_structure", None)
        if not callable(get_structure):
            # 仅兼容测试替身或历史 vendor；真实客户端始终提供该接口。
            return "legacy"
        try:
            raw_structure = get_structure(pageindex_doc_id)
            vendor_structure = json.loads(raw_structure)
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            raise ValidationAppError(
                "PageIndex vendor 结构无法规范化",
                details={"reason": str(exc)},
            ) from exc
        if not isinstance(vendor_structure, list):
            raise ValidationAppError("PageIndex vendor 结构格式无效")

        source_text = ""
        if mode == "md":
            try:
                source_text = source_path.read_text(encoding="utf-8-sig")
            except OSError as exc:
                raise ValidationAppError(
                    "读取 PageIndex 规范化源文档失败",
                    details={"source_path": str(source_path), "reason": str(exc)},
                ) from exc
        heading_tree = build_heading_tree(source_text) if mode == "md" else []
        normalized_structure = enrich_vendor_structure(vendor_structure, heading_tree, doc_uid)
        source_line_count = len(source_text.splitlines()) if mode == "md" else 0
        quality_report = evaluate_tree_quality(normalized_structure, source_line_count)
        self._write_json_atomic(workspace / "structure.quality.json", quality_report)
        if not quality_report["passed"]:
            raise ValidationAppError(
                "PageIndex 结构未通过质量门禁",
                details={"quality": quality_report, "index_status": "stale_index"},
            )

        self._write_json_atomic(
            workspace / "structure.normalized.json",
            {
                "status": "ready",
                "pageindex_doc_id": pageindex_doc_id,
                "doc_uid": doc_uid,
                "source_hash": source_hash,
                "quality": quality_report,
                "structure": normalized_structure,
            },
        )
        return "normalized"

    def _build_local_markdown_workspace(
        self,
        *,
        workspace: Path,
        source_path: Path,
        doc_uid: str,
        doc_title: str,
        source_hash: str,
    ) -> dict:
        """用 Markdown 标题和原文范围本地建树，避免节点级 LLM 并发风暴。"""

        try:
            source_text = source_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ValidationAppError(
                "读取 PageIndex Markdown 源文档失败",
                details={"source_path": str(source_path), "reason": str(exc)},
            ) from exc
        heading_tree = build_heading_tree(source_text)
        normalized_structure = enrich_vendor_structure([], heading_tree, doc_uid)
        quality_report = evaluate_tree_quality(
            normalized_structure,
            len(source_text.splitlines()),
        )
        self._write_json_atomic(workspace / "structure.quality.json", quality_report)
        if not quality_report["passed"]:
            raise ValidationAppError(
                "Markdown 本地 PageIndex 结构未通过质量门禁",
                details={"quality": quality_report, "index_status": "stale_index"},
            )

        pageindex_doc_id = f"local-md-{str(source_hash)[:24]}"
        vendor_document = {
            "id": pageindex_doc_id,
            "type": "md",
            "path": source_path.name,
            "doc_name": doc_title,
            "doc_description": str(normalized_structure[0].get("summary") or ""),
            "line_count": len(source_text.splitlines()),
            "structure": normalized_structure,
        }
        vendor_meta = {
            pageindex_doc_id: {
                "type": "md",
                "doc_name": doc_title,
                "doc_description": vendor_document["doc_description"],
                "path": source_path.name,
                "line_count": vendor_document["line_count"],
            }
        }
        self._write_json_atomic(workspace / f"{pageindex_doc_id}.json", vendor_document)
        self._write_json_atomic(workspace / "_meta.json", vendor_meta)
        self._write_json_atomic(
            workspace / "structure.normalized.json",
            {
                "status": "ready",
                "pageindex_doc_id": pageindex_doc_id,
                "doc_uid": doc_uid,
                "source_hash": source_hash,
                "quality": quality_report,
                "structure": normalized_structure,
            },
        )
        return {
            "pageindex_doc_id": pageindex_doc_id,
            "source_hash": source_hash,
            "quality": quality_report,
        }

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict) -> None:
        """使用同目录临时文件原子写入 UTF-8 BOM JSON。"""

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
            newline="\r\n",
        )
        temporary_path.replace(path)

    def _rank_evidence(self, record: dict, structure: list[dict], question: str, question_analysis: dict | None = None) -> tuple[list[dict], list[dict]]:
        """按问题关键词对 PageIndex 节点进行本地打分。"""

        candidates = self._build_tree_candidates(record, structure, question=question, question_analysis=question_analysis, limit=30, include_content=True)
        client = PageIndexClient(workspace=str(record["workspace_path"]))
        evidence: list[dict] = []
        for candidate in candidates[:3]:
            node = candidate["node"]
            line_num = int(node.get("line_num") or 0)
            content = self._load_node_content(client, str(record["pageindex_doc_id"]), line_num)
            evidence.append(
                {
                    "title": str(node.get("title") or ""),
                    "position": tree_retriever.format_node_position(node),
                    "summary": str(node.get("summary") or node.get("prefix_summary") or ""),
                    "content": content,
                    "reason": "本地候选召回",
                    "source_type": "PageIndex 节点",
                    "doc_uid": str(record.get("doc_uid") or ""),
                    "pageindex_doc_id": str(record.get("pageindex_doc_id") or ""),
                }
            )
        return evidence, [tree_retriever.candidate_to_debug(item) for item in candidates]

    def _search_rag_fts_evidence(self, record: dict, question: str, question_analysis: dict | None = None, *, max_results: int = 2) -> list[dict]:
        """调用统一混合检索服务，为当前 PageIndex 文档补充细粒度证据。"""

        max_results = max(0, int(max_results or 0))
        if max_results <= 0:
            return []
        terms = self._analysis_terms(question_analysis or {})
        if not terms:
            terms = self._extract_question_terms(question)
        query_terms = self._build_rag_query_terms(terms, question)
        if not query_terms:
            return []
        required_subject_terms = self._required_rag_subject_terms(terms)
        rows: list[dict] = []
        seen_chunks: set[str] = set()
        for term in query_terms:
            if len(rows) >= max_results:
                break
            normalized_term = str(term or "").strip()
            if not normalized_term:
                continue
            result_rows = self.retrieval_service.hybrid_search(
                normalized_term,
                top_k=max(max_results * 3, 3),
                doc_uid=str(record.get("doc_uid") or ""),
                knowledge_base_id=str(record.get("knowledge_base_id") or "") or None,
                fulltext_top_k=max(max_results * 3, 3),
                vector_top_k=max(max_results * 3, 3),
                use_rerank=False,
            )
            for item in result_rows:
                chunk_id = str(item.get("chunk_id") or "")
                if not chunk_id or chunk_id in seen_chunks:
                    continue
                content = str(item.get("content") or "")
                if normalized_term not in content:
                    continue
                if required_subject_terms and not any(subject in content for subject in required_subject_terms):
                    continue
                if self._is_incidental_rag_context(normalized_term, content):
                    continue
                seen_chunks.add(chunk_id)
                rows.append(dict(item))
                if len(rows) >= max_results:
                    break

        evidence: list[dict] = []
        for row in rows:
            evidence.append(
                {
                    "title": "RAG/FTS 原文片段",
                    "position": str(row.get("source_span") or ""),
                    "summary": "",
                    "content": str(row.get("content") or ""),
                    "reason": "当前知识库 RAG/FTS 补充命中",
                    "source_type": "RAG/FTS 原文",
                    "chunk_id": str(row.get("chunk_id") or ""),
                    "doc_uid": str(row.get("doc_uid") or ""),
                    "heading_path": str(row.get("heading_path") or ""),
                    "source_start_line": row.get("source_start_line"),
                    "source_end_line": row.get("source_end_line"),
                    "source_anchor": str(row.get("source_anchor") or row.get("source_span") or ""),
                    "chunk_type": str(row.get("chunk_type") or ""),
                    "retrieval_round": 0,
                    "rrf_score": float(row.get("rrf_score") or row.get("query_rrf_score") or 0.0),
                    "local_score": row.get("lexical_rank"),
                    "matched_sources": list(row.get("matched_sources") or []),
                    "retrieval_trace": list(row.get("retrieval_trace") or []),
                    "degraded_reason": str(row.get("degraded_reason") or ""),
                }
            )
        return evidence

    def _resolve_pageindex_retrieval_policy(self, template_id: str | None = None) -> dict:
        """读取 PageIndex 模板检索策略，失败时回退到严谨问答默认策略。"""

        template = self.template_service.get_template(template_id)
        policy = template.get("retrieval_policy", {}) if isinstance(template.get("retrieval_policy", {}), dict) else {}
        return {
            "max_tree_candidates": max(0, int(policy.get("max_tree_candidates", 30))),
            "max_selected_nodes": max(0, int(policy.get("max_selected_nodes", 3))),
            "max_rag_evidence": max(0, int(policy.get("max_rag_evidence", 2))),
            "include_structure_context": bool(policy.get("include_structure_context", True)),
        }

    @staticmethod
    def _required_rag_subject_terms(terms: list[str]) -> list[str]:
        """提取必须出现在补充片段中的主题词，只做相关性门槛，不单独检索。"""

        required: list[str] = []
        for term in terms:
            normalized = str(term or "").strip()
            if normalized == "阿胶" and normalized not in required:
                required.append(normalized)
        return required

    @classmethod
    def _build_rag_query_terms(cls, terms: list[str], question: str) -> list[str]:
        """构造 RAG/FTS 补充检索词，过滤会导致重复污染的泛词。"""

        specific_terms: list[str] = []
        seen: set[str] = set()
        normalized_question = cls._normalize_rag_text(question)
        for term in terms or cls._extract_question_terms(question):
            normalized = str(term or "").strip()
            if not normalized or normalized in seen:
                continue
            term_in_question = cls._normalize_rag_text(normalized) in normalized_question
            expanded_terms = [normalized] if cls._is_generic_rag_term(normalized) else cls._expand_term_with_entity_dictionary(normalized)
            for expanded in cls._expand_meaningful_segment(normalized):
                if expanded not in expanded_terms:
                    expanded_terms.append(expanded)
            for expanded in expanded_terms:
                if expanded in seen:
                    continue
                if not term_in_question and cls._normalize_rag_text(expanded) not in normalized_question:
                    continue
                if cls._is_generic_rag_term(expanded):
                    continue
                seen.add(expanded)
                specific_terms.append(expanded)
        specific_terms.sort(key=len, reverse=True)
        return specific_terms[:8]

    @staticmethod
    def _expand_term_with_entity_dictionary(term: str) -> list[str]:
        """复用通用实体词表扩展单个 PageIndex 查询词。"""

        candidates: list[str] = []
        for expanded in expand_query_texts(str(term or ""), limit=8):
            if " " in expanded:
                candidates.extend(part for part in expanded.split() if part)
            else:
                candidates.append(expanded)
        return PageIndexService._normalize_term_list([str(term or ""), *candidates])

    @staticmethod
    def _normalize_rag_text(value: str) -> str:
        """规范化 RAG/FTS 匹配文本，避免标点和空白影响问题原词判断。"""

        return re.sub(r"[\s，。！？、,.?？：:；;（）()《》“”\"'`]+", "", str(value or ""))

    @staticmethod
    def _is_generic_rag_term(term: str) -> bool:
        """判断词是否过于泛化，不适合单独驱动 RAG/FTS 补充证据。"""

        normalized = PageIndexService._normalize_rag_text(str(term or ""))
        noisy_fragments = {"哪些", "内容", "说明", "它对", "有帮", "帮助", "对皮", "肤有"}
        if len(normalized) > 10 or "的" in normalized or normalized.startswith("对") or any(fragment in normalized for fragment in noisy_fragments):
            return True
        generic_terms = {
            "阿胶",
            "功效",
            "作用",
            "应用",
            "疗效",
            "治疗",
            "益处",
            "好处",
            "帮助",
            "内容",
            "哪些",
            "什么",
            "如何",
            "是否",
            "证据",
            "资料",
            "研究",
            "文献",
            "相关",
            "主要",
            "方面",
            "方向",
        }
        if normalized in generic_terms:
            return True
        without_subject = normalized.replace("阿胶", "")
        return not without_subject or without_subject in generic_terms

    @staticmethod
    def _is_incidental_rag_context(term: str, content: str) -> bool:
        """过滤试验脱落、排除病例等偶然提及问题词的无关上下文。"""

        normalized_term = str(term or "").strip()
        normalized_content = str(content or "")
        if not normalized_term or normalized_term not in normalized_content:
            return False
        incidental_markers = ("因", "停止", "排除", "未能", "脱落", "未完成", "剔除", "不良事件")
        start = max(normalized_content.find(normalized_term) - 18, 0)
        end = min(normalized_content.find(normalized_term) + len(normalized_term) + 24, len(normalized_content))
        window = normalized_content[start:end]
        return any(marker in window for marker in incidental_markers)

    @staticmethod
    def _merge_evidence(primary: list[dict], supplemental: list[dict]) -> list[dict]:
        """合并 PageIndex 节点证据和 RAG/FTS 证据，并按来源去重。"""

        merged: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        source_items = [*primary, *supplemental]
        for item in source_items:
            key = (
                str(item.get("source_type") or "PageIndex 节点"),
                str(item.get("doc_uid") or ""),
                str(item.get("chunk_id") or item.get("position") or item.get("title") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _load_node_content(self, client, pageindex_doc_id: str, line_num: int) -> str:
        """读取 PageIndex 节点原文，读取失败时返回空文本。"""

        if line_num <= 0:
            return ""
        raw_content = client.get_page_content(pageindex_doc_id, str(line_num))
        try:
            items = json.loads(raw_content)
        except json.JSONDecodeError:
            return ""
        if isinstance(items, dict) and items.get("error"):
            return ""
        if not isinstance(items, list) or not items:
            return ""
        return str(items[0].get("content") or "")

    @staticmethod
    def _extract_question_terms(question: str) -> list[str]:
        """提取本地打分用关键词，保留中文短语并过滤短虚词。"""

        raw_terms = [item.strip() for item in question.replace("，", " ").replace("？", " ").replace("?", " ").split()]
        terms = [term for term in raw_terms if len(term) >= 2]
        if len(terms) > 1:
            return terms
        compact_question = re.sub(r"[，。！？、,.?？\s]", "", question)
        if len(terms) == 1 and terms[0] == compact_question and PageIndexService._looks_like_compact_question(compact_question):
            terms = []
        if "阿胶" in compact_question:
            terms.append("阿胶")
        semantic_text = compact_question
        for pattern in (
            "阿胶",
            "哪些内容",
            "有没有",
            "能不能",
            "有哪些",
            "有什么",
            "有好处吗",
            "有作用吗",
            "有疗效吗",
            "有疗效",
            "有作用",
            "有好处",
            "有帮助",
            "如何",
            "是否",
            "治疗",
            "疗效",
            "说明",
            "帮助",
            "哪些",
            "内容",
            "它",
            "对",
            "吃",
            "吗",
        ):
            semantic_text = semantic_text.replace(pattern, " ")
        for segment in re.split(r"\s+", semantic_text):
            segment = segment.strip()
            if len(segment) < 2:
                continue
            for term in PageIndexService._expand_meaningful_segment(segment):
                if term not in terms:
                    terms.append(term)
        return terms[:24]

    @staticmethod
    def _looks_like_compact_question(question: str) -> bool:
        """识别无空格中文问句，避免把整句当成检索词。"""

        markers = (
            "阿胶",
            "有没有",
            "能不能",
            "有哪些",
            "有什么",
            "有疗效",
            "有作用",
            "有好处",
            "治疗",
            "如何",
            "是否",
            "对",
            "吗",
        )
        return any(marker in str(question or "") for marker in markers)

    @staticmethod
    def _expand_meaningful_segment(segment: str) -> list[str]:
        """从中文问题片段中抽取可用于结构检索的核心短语。"""

        terms = [segment]
        # 用户常在核心主题后附加“研究/资料”等泛化尾词，标题通常只保留主题本身。
        for suffix in ("研究", "资料", "信息", "情况"):
            if segment.endswith(suffix) and len(segment) - len(suffix) >= 2:
                terms.append(segment[: -len(suffix)])
        if len(segment) >= 4:
            if "质量检测" in segment:
                terms.append("质量检测")
            if "检测方法" in segment:
                terms.append("检测方法")
            if "制作工艺" in segment:
                terms.extend(["制作工艺", "工艺", "古法", "流程", "器用", "原料"])
            if "古代文献" in segment:
                terms.extend(["古代文献", "古籍", "本草", "文献"])
            if "状态改善" in segment:
                terms.append("状态改善")
            if "皮肤状态" in segment:
                terms.extend(["皮肤状态", "皮肤", "胶原", "抗氧化"])
            if "癌症患者" in segment:
                terms.extend(["癌症患者", "癌症"])
            if "不孕不育" in segment:
                terms.append("不孕不育")
        if "胃病" in segment:
            terms.extend(["胃病", "胃部", "胃脘", "脾胃", "消化不良"])
        if "心脏病" in segment:
            terms.extend(["心脏病", "心脏"])
        return [term for term in terms if not PageIndexService._is_generic_tree_term(term)]

    @staticmethod
    def _normalize_term_list(value: object) -> list[str]:
        """规范化 LLM 返回的词表，过滤空值与重复项。"""

        if not isinstance(value, list):
            return []
        terms: list[str] = []
        seen: set[str] = set()
        for item in value:
            term = str(item or "").strip()
            if not term or term in seen:
                continue
            seen.add(term)
            terms.append(term)
        return terms

    def _analysis_terms(self, question_analysis: dict) -> list[str]:
        """合并问题分析中的实体、关键词与扩展词。"""

        terms: list[str] = []
        for key in ("entities", "keywords", "expanded_terms"):
            terms.extend(self._normalize_term_list(question_analysis.get(key)))
        return self._normalize_term_list(terms)

    @classmethod
    def _build_tree_scoring_terms(cls, terms: list[str], question: str) -> list[str]:
        """构造 PageIndex 树节点打分词，排除主题词、问句词和跨字碎片。"""

        candidates = terms or cls._extract_question_terms(question)
        scoring_terms: list[str] = []
        seen: set[str] = set()
        for term in candidates:
            normalized = str(term or "").strip()
            if not normalized or normalized in seen:
                continue
            if cls._is_generic_tree_term(normalized):
                continue
            seen.add(normalized)
            scoring_terms.append(normalized)
        scoring_terms.sort(key=len, reverse=True)
        return scoring_terms[:16]

    @staticmethod
    def _is_generic_tree_term(term: str) -> bool:
        """判断词是否不适合参与 PageIndex 树节点打分。"""

        normalized = PageIndexService._normalize_rag_text(str(term or ""))
        if len(normalized) < 2:
            return True
        generic_terms = {
            "阿胶",
            "作用",
            "功效",
            "疗效",
            "治疗",
            "患者",
            "好处",
            "益处",
            "证据",
            "方法",
            "特点",
            "内容",
            "哪些",
            "什么",
            "如何",
            "是否",
            "有没有",
            "能不能",
            "有作用",
            "有好处",
            "应用",
            "研究",
            "相关",
            "主要",
        }
        if normalized in generic_terms:
            return True
        noisy_prefixes = ("对", "有", "能", "没", "吗", "么", "些")
        noisy_suffixes = ("对", "有", "能", "不", "没", "吗", "么", "些")
        if len(normalized) <= 4 and (normalized.startswith(noisy_prefixes) or normalized.endswith(noisy_suffixes)):
            return True
        return False

    def _document_workspace(self, knowledge_base_id: str, doc_uid: str) -> Path:
        """生成按知识库与文档隔离的 PageIndex workspace 路径。"""

        return self.workspace_root / knowledge_base_id / doc_uid

    def _ensure_llm_enabled(self) -> None:
        """PageIndex 构建依赖模型调用，未配置时必须显式阻断。"""

        provider = str(self.settings.llm_provider or "").strip().lower()
        model = str(self.settings.llm_model or "").strip().lower()
        if provider in {"", "disabled", "none"} or model in {"", "disabled", "none"}:
            raise ValidationAppError("PageIndex 需要启用 LLM 后才能构建索引")

    def _ensure_pageindex_available(self) -> None:
        """确认 vendor PageIndex 能被导入。"""

        if PageIndexClient is None:
            raise ValidationAppError("PageIndex 本地依赖不可用", details={"reason": str(PAGEINDEX_IMPORT_ERROR)})

    def _pageindex_model_name(self) -> str:
        """将项目 LLM 配置转换为 PageIndex/LiteLLM 可识别的模型名。"""

        provider = str(self.settings.llm_provider or "").strip()
        model = str(self.settings.llm_model or "").strip()
        if "/" in model or not provider:
            return model
        return f"{provider}/{model}"

    def _configure_vendor_environment(self) -> None:
        """把项目 LLM 地址桥接给 PageIndex vendor 使用的 LiteLLM。"""

        base_url = str(self.settings.llm_base_url or "").strip().rstrip("/")
        if base_url:
            os.environ["OPENAI_API_BASE"] = base_url

    @staticmethod
    def _require_knowledge_base_id(knowledge_base_id: str) -> str:
        """校验知识库 ID，避免空值落到全局范围。"""

        resolved = str(knowledge_base_id or "").strip()
        if not resolved:
            raise ValidationAppError("请选择知识库")
        return resolved

    @staticmethod
    def _require_doc_uid(doc_uid: str) -> str:
        """校验文档 ID，避免空值触发跨库查询。"""

        resolved = str(doc_uid or "").strip()
        if not resolved:
            raise ValidationAppError("请选择文档")
        return resolved
