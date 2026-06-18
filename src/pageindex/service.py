"""程序说明：封装 PageIndex 本地索引构建、文档查询与知识库隔离逻辑。"""

from __future__ import annotations

import sqlite3
import json
import re
import sys
from pathlib import Path
from uuid import uuid4

from src.ai.llm import DisabledLLMClient, build_llm_client
from src.common.config import AppSettings
from src.common.errors import DatabaseAppError, NotFoundAppError, ValidationAppError
from src.common.paths import resolve_input_path, to_input_relative_path
from src.common.utils import utc_now_iso
from src.db.connection import create_connection
from src.db.transaction import transaction


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

    def __init__(self, settings: AppSettings, *, llm_client: object | None = None) -> None:
        """初始化服务并确保 PageIndex 元数据表存在。"""

        self.settings = settings
        self.llm_client = llm_client
        self.workspace_root = settings.sqlite_db_path.parent / "pageindex_workspace"
        self._ensure_tables()

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

        self._ensure_llm_enabled()
        self._ensure_pageindex_available()
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
        client = PageIndexClient(
            api_key=self.settings.llm_api_key,
            model=self._pageindex_model_name(),
            retrieve_model=self._pageindex_model_name(),
            workspace=str(workspace),
        )
        mode = "md" if source_path.suffix.lower() in {".md", ".markdown"} else "pdf"
        pageindex_doc_id = client.index(str(pageindex_source_path), mode=mode)
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
        with transaction(self.settings.sqlite_db_path) as connection:
            connection.execute(
                """
                INSERT INTO pageindex_indexes (
                    knowledge_base_id,
                    doc_uid,
                    pageindex_doc_id,
                    workspace_path,
                    source_hash,
                    status,
                    error_message,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'ready', NULL, ?, ?)
                ON CONFLICT(knowledge_base_id, doc_uid) DO UPDATE SET
                    pageindex_doc_id = excluded.pageindex_doc_id,
                    workspace_path = excluded.workspace_path,
                    source_hash = excluded.source_hash,
                    status = excluded.status,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (
                    resolved_knowledge_base_id,
                    resolved_doc_uid,
                    resolved_pageindex_doc_id,
                    str(workspace),
                    str(source_hash or ""),
                    now,
                    now,
                ),
            )

    def get_tree_rows(self, knowledge_base_id: str, doc_uid: str) -> list[list[object]]:
        """读取 PageIndex 文档结构，并转换为页面表格行。"""

        record = self._get_index_record(knowledge_base_id, doc_uid)
        structure = self._load_structure(record)
        rows: list[list[object]] = []
        for node in self._flatten_structure(structure):
            rows.append(
                [
                    int(node.get("level") or 1),
                    str(node.get("title") or ""),
                    self._format_node_position(node),
                    str(node.get("summary") or node.get("prefix_summary") or ""),
                ]
            )
        return rows

    def ask_question(self, knowledge_base_id: str, doc_uid: str, question: str) -> dict:
        """基于 PageIndex 本地结构定位证据，并保存问答历史。"""

        normalized_question = str(question or "").strip()
        if not normalized_question:
            raise ValidationAppError("问题不能为空")
        record = self._get_index_record(knowledge_base_id, doc_uid)
        structure = self._load_structure(record)
        retrieval_result = self._answer_with_reasoning_or_fallback(record, structure, normalized_question)
        evidence = retrieval_result["evidence"]
        answer_text = retrieval_result["answer"]
        query_id = f"piq_{uuid4().hex[:12]}"
        created_at = utc_now_iso()

        with transaction(self.settings.sqlite_db_path) as connection:
            connection.execute(
                """
                INSERT INTO pageindex_query_history (
                    query_id,
                    knowledge_base_id,
                    doc_uid,
                    question,
                    answer,
                    evidence_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    query_id,
                    record["knowledge_base_id"],
                    record["doc_uid"],
                    normalized_question,
                    answer_text,
                    json.dumps(evidence, ensure_ascii=False),
                    created_at,
                ),
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

    def list_query_history(self, knowledge_base_id: str, doc_uid: str, *, limit: int = 50) -> list[dict]:
        """读取当前知识库与文档下的 PageIndex 问答历史。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_doc_uid = self._require_doc_uid(doc_uid)
        try:
            with create_connection(self.settings.sqlite_db_path) as connection:
                rows = connection.execute(
                    """
                    SELECT query_id, knowledge_base_id, doc_uid, question, answer, evidence_json, created_at
                    FROM pageindex_query_history
                    WHERE knowledge_base_id = ? AND doc_uid = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (resolved_knowledge_base_id, resolved_doc_uid, max(1, int(limit))),
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise DatabaseAppError("读取 PageIndex 历史失败", details={"reason": str(exc)}) from exc

        items: list[dict] = []
        for row in rows:
            item = dict(row)
            try:
                evidence = json.loads(str(item.pop("evidence_json") or "[]"))
            except json.JSONDecodeError:
                evidence = []
            item["evidence"] = evidence if isinstance(evidence, list) else []
            items.append(item)
        return items

    def export_history_markdown(self, knowledge_base_id: str, doc_uid: str) -> str:
        """将当前知识库与文档下的 PageIndex 历史导出为 Markdown。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_doc_uid = self._require_doc_uid(doc_uid)
        history = list(reversed(self.list_query_history(resolved_knowledge_base_id, resolved_doc_uid, limit=200)))
        if not history:
            raise ValidationAppError("暂无可导出的 PageIndex 问答历史")

        lines = [
            "# PageIndex 深度检索导出",
            "",
            f"- 知识库：{resolved_knowledge_base_id}",
            f"- 文档：{resolved_doc_uid}",
            "",
        ]
        for index, item in enumerate(history, start=1):
            lines.extend(
                [
                    f"## 记录 {index}",
                    "",
                    f"- 时间：{item.get('created_at', '')}",
                    f"- 问题：{item.get('question', '')}",
                    "",
                    "### 回答",
                    "",
                    str(item.get("answer") or ""),
                    "",
                    "### 证据",
                    "",
                ]
            )
            evidence_items = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            if not evidence_items:
                lines.append("- 暂无证据")
                lines.append("")
                continue
            for evidence in evidence_items:
                lines.extend(
                    [
                        f"#### {evidence.get('title', '')}",
                        "",
                        f"- 位置：{evidence.get('position', '')}",
                        "",
                        str(evidence.get("content") or evidence.get("summary") or ""),
                        "",
                    ]
                )
        return "\n".join(lines).strip()

    def _ensure_tables(self) -> None:
        """创建 PageIndex 本地元数据表，使用事务保证结构初始化一致。"""

        with transaction(self.settings.sqlite_db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pageindex_indexes (
                    knowledge_base_id TEXT NOT NULL,
                    doc_uid TEXT NOT NULL,
                    pageindex_doc_id TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (knowledge_base_id, doc_uid),
                    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases (knowledge_base_id),
                    FOREIGN KEY (doc_uid) REFERENCES documents (doc_uid) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_pageindex_indexes_kb
                    ON pageindex_indexes (knowledge_base_id);

                CREATE TABLE IF NOT EXISTS pageindex_query_history (
                    query_id TEXT PRIMARY KEY,
                    knowledge_base_id TEXT NOT NULL,
                    doc_uid TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (knowledge_base_id, doc_uid)
                        REFERENCES pageindex_indexes (knowledge_base_id, doc_uid)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_pageindex_query_history_scope
                    ON pageindex_query_history (knowledge_base_id, doc_uid, created_at);
                """
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

    def _answer_with_reasoning_or_fallback(self, record: dict, structure: list[dict], question: str) -> dict:
        """优先用 LLM 对 PageIndex 树做语义推理，失败时回退到本地关键词。"""

        question_analysis = self._analyze_question(question)
        try:
            evidence, answer, debug = self._answer_with_llm_tree_reasoning(record, structure, question, question_analysis)
            if evidence:
                debug["retrieval_mode"] = "LLM 语义树推理"
                debug["question_analysis"] = question_analysis
                return {
                    "evidence": evidence,
                    "answer": answer or self._build_local_answer(question, evidence),
                    "retrieval_mode": "LLM 语义树推理",
                    "llm_error": "",
                    "debug": debug,
                }
        except Exception as exc:  # noqa: BLE001
            llm_error = str(exc)
        else:
            llm_error = ""

        evidence, candidate_nodes = self._rank_evidence(record, structure, question, question_analysis)
        rag_evidence = self._search_rag_fts_evidence(record, question, question_analysis)
        evidence = self._merge_evidence(evidence, rag_evidence)
        return {
            "evidence": evidence,
            "answer": self._build_local_answer(question, evidence),
            "retrieval_mode": "本地关键词降级",
            "llm_error": llm_error,
            "debug": {
                "retrieval_mode": "本地关键词降级",
                "question_analysis": question_analysis,
                "candidate_nodes": candidate_nodes,
                "rag_evidence": rag_evidence,
                "selected_nodes": candidate_nodes[: len(evidence)],
                "llm_error": llm_error,
            },
        }

    def _answer_with_llm_tree_reasoning(
        self,
        record: dict,
        structure: list[dict],
        question: str,
        question_analysis: dict,
    ) -> tuple[list[dict], str, dict]:
        """让 LLM 根据 PageIndex 树结构选择相关节点，并基于证据生成回答。"""

        llm_client = self._get_llm_client()
        candidates = self._build_tree_candidates(record, structure, question_analysis=question_analysis, limit=30, include_content=True)
        if not candidates:
            return [], "", {"candidate_nodes": [], "selected_nodes": []}

        system_prompt, user_prompt = self._build_tree_reasoning_prompts(question, question_analysis, candidates)
        selection = llm_client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
        selected_items = selection.get("selected_nodes")
        if not isinstance(selected_items, list):
            selected_items = []

        candidate_map = {item["candidate_id"]: item for item in candidates}
        client = PageIndexClient(workspace=str(record["workspace_path"]))
        evidence: list[dict] = []
        for selected in selected_items[:3]:
            if not isinstance(selected, dict):
                continue
            candidate = candidate_map.get(str(selected.get("candidate_id") or ""))
            if not candidate:
                continue
            node = candidate["node"]
            line_num = int(node.get("line_num") or 0)
            evidence.append(
                {
                    "title": str(node.get("title") or ""),
                    "position": self._format_node_position(node),
                    "summary": str(node.get("summary") or node.get("prefix_summary") or ""),
                    "content": self._load_node_content(client, str(record["pageindex_doc_id"]), line_num),
                    "reason": str(selected.get("reason") or "LLM 语义推理选中"),
                    "source_type": "PageIndex 节点",
                }
            )

        rag_evidence = self._search_rag_fts_evidence(record, question, question_analysis)
        evidence = self._merge_evidence(evidence, rag_evidence)
        answer = str(selection.get("answer") or "").strip()
        if evidence:
            try:
                answer = self._generate_llm_answer(llm_client, question, evidence)
            except Exception:  # noqa: BLE001
                if not answer:
                    answer = self._build_local_answer(question, evidence)
        selected_debug = []
        for selected in selected_items[:3]:
            if not isinstance(selected, dict):
                continue
            candidate = candidate_map.get(str(selected.get("candidate_id") or ""))
            if not candidate:
                continue
            selected_debug.append(
                {
                    **self._candidate_to_debug(candidate),
                    "reason": str(selected.get("reason") or "LLM 语义推理选中"),
                }
            )
        return evidence, answer, {
            "candidate_nodes": [self._candidate_to_debug(item) for item in candidates],
            "rag_evidence": rag_evidence,
            "selected_nodes": selected_debug,
        }

    def _get_llm_client(self) -> object:
        """获取 PageIndex 语义推理使用的 LLM 客户端。"""

        if self.llm_client is not None:
            return self.llm_client
        llm_client = build_llm_client(self.settings)
        if isinstance(llm_client, DisabledLLMClient):
            raise ValidationAppError("PageIndex 语义检索需要启用 LLM")
        self.llm_client = llm_client
        return llm_client

    def _analyze_question(self, question: str) -> dict:
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
        question_analysis: dict | None = None,
        limit: int = 80,
        include_content: bool = False,
    ) -> list[dict]:
        """将 PageIndex 树节点转换为 LLM 可选择的候选列表。"""

        terms = self._analysis_terms(question_analysis or {})
        flattened = self._flatten_structure(structure)
        scored_items: list[tuple[int, int, dict]] = []
        for index, node in enumerate(flattened, start=1):
            score = self._score_node(node, terms)
            scored_items.append((score, index, node))
        scored_items.sort(key=lambda item: (-item[0], int(item[2].get("level") or 1), int(item[2].get("line_num") or 0)))
        if not any(score > 0 for score, _index, _node in scored_items):
            scored_items = [(score, index, node) for score, index, node in scored_items[:limit]]

        client = PageIndexClient(workspace=str(record["workspace_path"])) if include_content else None
        candidates: list[dict] = []
        for score, original_index, node in scored_items[:limit]:
            content_excerpt = ""
            if client is not None:
                content_excerpt = self._load_node_content(client, str(record["pageindex_doc_id"]), int(node.get("line_num") or 0))[:900]
            candidates.append(
                {
                    "candidate_id": f"node_{original_index}",
                    "title": str(node.get("title") or ""),
                    "level": int(node.get("level") or 1),
                    "position": self._format_node_position(node),
                    "summary": str(node.get("summary") or node.get("prefix_summary") or "")[:500],
                    "content_excerpt": content_excerpt,
                    "score": score,
                    "node": node,
                }
            )
        return candidates

    @staticmethod
    def _build_tree_reasoning_prompts(question: str, question_analysis: dict, candidates: list[dict]) -> tuple[str, str]:
        """构建 PageIndex 树推理检索提示词。"""

        system_prompt = (
            "你是 PageIndex 树结构检索助手。请理解用户问题，从候选节点中选择最相关的证据节点。"
            "只返回 JSON，不要输出额外文本。"
        )
        safe_candidates = [
            {
                "candidate_id": item["candidate_id"],
                "title": item["title"],
                "level": item["level"],
                "position": item["position"],
                "summary": item["summary"],
                "content_excerpt": item.get("content_excerpt", ""),
                "score": item.get("score", 0),
            }
            for item in candidates
        ]
        user_prompt = "\n".join(
            [
                "用户问题：",
                question,
                "",
                "问题分析 JSON：",
                json.dumps(question_analysis, ensure_ascii=False),
                "",
                "候选 PageIndex 节点 JSON：",
                json.dumps(safe_candidates, ensure_ascii=False),
                "",
                "请返回 JSON：",
                '{"selected_nodes":[{"candidate_id":"node_1","reason":"选择理由"}],"answer":"基于证据的简短中文回答"}',
                "要求：最多选择 3 个节点；如果没有足够相关节点，selected_nodes 返回空数组。",
            ]
        )
        return system_prompt, user_prompt

    @staticmethod
    def _generate_llm_answer(llm_client: object, question: str, evidence: list[dict]) -> str:
        """让 LLM 基于已取回证据生成简短回答。"""

        system_prompt = (
            "你是严谨的文档问答助手。只能基于给定证据回答，证据不足时要明确说明证据不足，"
            "不得编造未给出的事实。只返回 JSON。"
        )
        user_prompt = "\n".join(
            [
                "用户问题：",
                question,
                "",
                "证据 JSON：",
                json.dumps(evidence, ensure_ascii=False),
                "",
                "请按以下结构写中文回答：",
                "结论：直接回答问题。",
                "依据：列出支持结论的证据要点。",
                "来源：列出证据标题、位置或 chunk 来源。",
                "不确定点：说明证据不足或需要复核之处；如果没有，写“无”。",
                "",
                '请返回 JSON：{"answer":"结论：...\\n\\n依据：...\\n\\n来源：...\\n\\n不确定点：..."}',
            ]
        )
        result = llm_client.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
        return str(result.get("answer") or "").strip()

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

    def _get_index_record(self, knowledge_base_id: str, doc_uid: str) -> dict:
        """读取 PageIndex 索引记录，并校验知识库与文档范围。"""

        resolved_knowledge_base_id = self._require_knowledge_base_id(knowledge_base_id)
        resolved_doc_uid = self._require_doc_uid(doc_uid)
        try:
            with create_connection(self.settings.sqlite_db_path) as connection:
                row = connection.execute(
                    """
                    SELECT knowledge_base_id, doc_uid, pageindex_doc_id, workspace_path, source_hash, status
                    FROM pageindex_indexes
                    WHERE knowledge_base_id = ? AND doc_uid = ?
                    """,
                    (resolved_knowledge_base_id, resolved_doc_uid),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise DatabaseAppError("读取 PageIndex 索引记录失败", details={"reason": str(exc)}) from exc
        if not row:
            raise NotFoundAppError("当前文档尚未构建 PageIndex", details={"knowledge_base_id": resolved_knowledge_base_id, "doc_uid": resolved_doc_uid})
        return dict(row)

    def _load_structure(self, record: dict) -> list[dict]:
        """通过 vendor PageIndex 读取文档结构。"""

        self._ensure_pageindex_available()
        workspace_path = Path(str(record["workspace_path"]))
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
        return structure

    def _rank_evidence(self, record: dict, structure: list[dict], question: str, question_analysis: dict | None = None) -> tuple[list[dict], list[dict]]:
        """按问题关键词对 PageIndex 节点进行本地打分。"""

        candidates = self._build_tree_candidates(record, structure, question_analysis=question_analysis, limit=30, include_content=True)
        client = PageIndexClient(workspace=str(record["workspace_path"]))
        evidence: list[dict] = []
        for candidate in candidates[:3]:
            node = candidate["node"]
            line_num = int(node.get("line_num") or 0)
            content = self._load_node_content(client, str(record["pageindex_doc_id"]), line_num)
            evidence.append(
                {
                    "title": str(node.get("title") or ""),
                    "position": self._format_node_position(node),
                    "summary": str(node.get("summary") or node.get("prefix_summary") or ""),
                    "content": content,
                    "reason": "本地候选召回",
                    "source_type": "PageIndex 节点",
                }
            )
        return evidence, [self._candidate_to_debug(item) for item in candidates]

    def _search_rag_fts_evidence(self, record: dict, question: str, question_analysis: dict | None = None) -> list[dict]:
        """在当前文档的 RAG/FTS chunk 中补充细粒度原文证据。"""

        terms = self._analysis_terms(question_analysis or {})
        if not terms:
            terms = self._extract_question_terms(question)
        query_terms = terms[:24] or [question]
        rows: list[dict] = []
        seen_chunks: set[str] = set()
        with create_connection(self.settings.sqlite_db_path) as connection:
            for term in query_terms:
                if len(rows) >= 3:
                    break
                normalized_term = str(term or "").strip()
                if not normalized_term:
                    continue
                try:
                    result_rows = connection.execute(
                        """
                        SELECT c.chunk_id, c.doc_uid, c.source_span, c.content
                        FROM chunk_fts f
                        JOIN chunks c ON c.chunk_id = f.chunk_id
                        WHERE chunk_fts MATCH ?
                          AND c.doc_uid = ?
                        LIMIT 3
                        """,
                        (normalized_term, record["doc_uid"]),
                    ).fetchall()
                except sqlite3.OperationalError:
                    result_rows = []
                if not result_rows:
                    result_rows = connection.execute(
                        """
                        SELECT c.chunk_id, c.doc_uid, c.source_span, c.content
                        FROM chunks c
                        WHERE c.content LIKE ?
                          AND c.doc_uid = ?
                        ORDER BY c.chunk_index ASC
                        LIMIT 3
                        """,
                        (f"%{normalized_term}%", record["doc_uid"]),
                    ).fetchall()
                for row in result_rows:
                    item = dict(row)
                    chunk_id = str(item.get("chunk_id") or "")
                    if not chunk_id or chunk_id in seen_chunks:
                        continue
                    seen_chunks.add(chunk_id)
                    rows.append(item)
                    if len(rows) >= 3:
                        break

        evidence: list[dict] = []
        for row in rows:
            evidence.append(
                {
                    "title": "RAG/FTS 原文片段",
                    "position": str(row.get("source_span") or ""),
                    "summary": "",
                    "content": str(row.get("content") or ""),
                    "reason": "当前文档 RAG/FTS 补充命中",
                    "source_type": "RAG/FTS 原文",
                    "chunk_id": str(row.get("chunk_id") or ""),
                    "doc_uid": str(row.get("doc_uid") or ""),
                }
            )
        return evidence

    @staticmethod
    def _merge_evidence(primary: list[dict], supplemental: list[dict]) -> list[dict]:
        """合并 PageIndex 节点证据和 RAG/FTS 证据，并按来源去重。"""

        merged: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in [*primary, *supplemental]:
            key = (str(item.get("source_type") or "PageIndex 节点"), str(item.get("chunk_id") or item.get("position") or item.get("title") or ""))
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
    def _build_local_answer(question: str, evidence: list[dict]) -> str:
        """基于已定位证据生成本地摘要回答。"""

        if not evidence:
            return f"未在 PageIndex 文档结构中找到与“{question}”直接相关的证据。"
        top = evidence[0]
        content = str(top.get("content") or top.get("summary") or "").strip()
        if len(content) > 600:
            content = content[:600].rstrip() + "..."
        return "\n\n".join(
            [
                f"根据 PageIndex 定位，最相关位置是“{top.get('title', '')}”（{top.get('position', '')}）。",
                content,
            ]
        ).strip()

    @staticmethod
    def _extract_question_terms(question: str) -> list[str]:
        """提取本地打分用关键词，保留中文短语并过滤短虚词。"""

        raw_terms = [item.strip() for item in question.replace("，", " ").replace("？", " ").replace("?", " ").split()]
        terms = [term for term in raw_terms if len(term) >= 2]
        if len(terms) > 1:
            return terms
        compact_question = re.sub(r"[，。！？、,.?？\s]", "", question)
        stop_words = {"哪些", "内容", "说明", "它对", "有帮助", "属于", "哪个", "知识", "文档", "什么", "如何", "是否"}
        for match in re.findall(r"[\u4e00-\u9fff]{2,}", compact_question):
            for size in (2, 3, 4):
                for index in range(0, max(len(match) - size + 1, 0)):
                    term = match[index : index + size]
                    if term in stop_words or term in terms:
                        continue
                    terms.append(term)
        return terms[:24]

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

    def _score_node(self, node: dict, terms: list[str]) -> int:
        """按标题、摘要和节点原文对候选节点打分。"""

        haystack_parts = [
            str(node.get("title") or ""),
            str(node.get("summary") or ""),
            str(node.get("prefix_summary") or ""),
            str(node.get("text") or ""),
        ]
        haystack = " ".join(haystack_parts).lower()
        score = 0
        for term in terms:
            normalized = term.lower()
            if not normalized:
                continue
            if normalized in str(node.get("title") or "").lower():
                score += 4
            elif normalized in haystack:
                score += 2
        return score

    @staticmethod
    def _candidate_to_debug(candidate: dict) -> dict:
        """将候选节点转换为前端诊断行所需字段。"""

        return {
            "candidate_id": str(candidate.get("candidate_id") or ""),
            "title": str(candidate.get("title") or ""),
            "position": str(candidate.get("position") or ""),
            "summary": str(candidate.get("summary") or ""),
            "score": int(candidate.get("score") or 0),
            "reason": str(candidate.get("reason") or "本地候选召回"),
            "content_excerpt": str(candidate.get("content_excerpt") or ""),
        }

    def _flatten_structure(self, structure: list[dict]) -> list[dict]:
        """将 PageIndex 树结构展开为深度优先列表。"""

        items: list[dict] = []

        def walk(nodes: list[dict]) -> None:
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                items.append(node)
                children = node.get("nodes")
                if isinstance(children, list):
                    walk(children)

        walk(structure)
        return items

    @staticmethod
    def _format_node_position(node: dict) -> str:
        """格式化节点定位信息。"""

        if node.get("page"):
            return f'page {node.get("page")}'
        if node.get("line_num"):
            return f'line {node.get("line_num")}'
        return ""

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
