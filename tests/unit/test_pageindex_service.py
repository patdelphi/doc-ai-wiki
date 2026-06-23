"""程序说明：验证 PageIndex 本地集成服务的知识库隔离与 LLM 配置保护。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.config import AppSettings
from src.common.errors import ValidationAppError
from src.common.utils import utc_now_iso
from src.db.connection import initialize_database
from src.db.transaction import transaction
from src.ingest.service import IngestService
from src.knowledge_base.service import KnowledgeBaseService
from src.pageindex.service import PageIndexService


def build_pageindex_test_settings(tmp_path: Path, *, llm_provider: str = "disabled") -> AppSettings:
    """构造 PageIndex 测试专用配置。"""

    rules_dir = tmp_path / "rules"
    templates_dir = tmp_path / "templates"
    rules_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)
    return AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=rules_dir,
        TEMPLATES_DIR=templates_dir,
        LLM_PROVIDER=llm_provider,
        EMBEDDING_PROVIDER="local",
        RERANK_ENABLED=False,
    )


def seed_markdown_document(settings: AppSettings, *, knowledge_base_id: str, file_name: str) -> dict:
    """在指定知识库中写入并注册 Markdown 文档。"""

    KnowledgeBaseService(settings.sqlite_db_path, settings.input_root).save_knowledge_base(
        {
            "knowledge_base_id": knowledge_base_id,
            "knowledge_base_name": f"{knowledge_base_id} 知识库",
            "description": "PageIndex 测试知识库",
            "status": "active",
            "is_default": False,
        }
    )
    document_path = settings.input_root / knowledge_base_id / file_name
    document_path.parent.mkdir(parents=True, exist_ok=True)
    document_title = Path(file_name).stem
    document_path.write_text(f"# {document_title}\n\n这是 PageIndex 测试文档。\n\n## 风险\n\n仅属于当前知识库。", encoding="utf-8")
    return IngestService(settings).register_document(
        {"file_path": str(document_path), "knowledge_base_id": knowledge_base_id},
        knowledge_base_id=knowledge_base_id,
    )


def seed_chunk(settings: AppSettings, *, doc_uid: str, chunk_id: str, content: str, source_span: str = "line 1") -> None:
    """为指定文档写入一条 RAG/FTS chunk，用于验证 PageIndex 混合检索。"""

    with transaction(settings.sqlite_db_path) as connection:
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, doc_uid, section_id, chunk_index, content, source_span,
                token_count, created_at, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, '2026-06-18T00:00:00+00:00', '2026-06-18T00:00:00+00:00')
            """,
            (chunk_id, doc_uid, 0, content, source_span, len(content)),
        )
        connection.execute(
            "INSERT INTO chunk_fts (chunk_id, doc_uid, content) VALUES (?, ?, ?)",
            (chunk_id, doc_uid, content),
        )


def test_pageindex_service_should_list_documents_inside_selected_knowledge_base(tmp_path: Path) -> None:
    """PageIndex 文档列表必须按 knowledge_base_id 隔离，不能混入其它知识库文档。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    first = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    second = seed_markdown_document(settings, knowledge_base_id="kb_beta", file_name="beta.md")

    service = PageIndexService(settings)
    alpha_documents = service.list_available_documents("kb_alpha")

    assert [item["doc_uid"] for item in alpha_documents] == [first["doc_uid"]]
    assert alpha_documents[0]["source_path"] == "kb_alpha/alpha.md"
    assert second["doc_uid"] not in {item["doc_uid"] for item in alpha_documents}


def test_pageindex_service_should_reject_build_when_llm_disabled(tmp_path: Path) -> None:
    """LLM 未启用时，PageIndex 不应静默建树或误走外部默认配置。"""

    settings = build_pageindex_test_settings(tmp_path, llm_provider="disabled")
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")

    service = PageIndexService(settings)

    with pytest.raises(ValidationAppError, match="PageIndex 需要启用 LLM"):
        service.build_index("kb_alpha", document["doc_uid"])


def test_pageindex_service_should_report_llm_retrieval_status(tmp_path: Path) -> None:
    """PageIndex 服务应暴露 LLM 语义检索是否可用，供前端明确展示。"""

    disabled_settings = build_pageindex_test_settings(tmp_path / "disabled", llm_provider="disabled")
    enabled_settings = build_pageindex_test_settings(tmp_path / "enabled", llm_provider="openai")
    enabled_settings.llm_api_key = "test-key"
    enabled_settings.llm_model = "gpt-test"
    initialize_database(disabled_settings.sqlite_db_path)
    initialize_database(enabled_settings.sqlite_db_path)

    disabled_status = PageIndexService(disabled_settings).get_retrieval_status()
    enabled_status = PageIndexService(enabled_settings).get_retrieval_status()

    assert disabled_status["llm_available"] is False
    assert disabled_status["retrieval_mode"] == "本地关键词降级"
    assert enabled_status["llm_available"] is True
    assert enabled_status["retrieval_mode"] == "LLM 语义树推理"
    assert enabled_status["model"] == "gpt-test"


def test_pageindex_service_should_repair_legacy_source_path_before_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """历史数据库路径指向旧项目时，应自动修复为当前 Input 知识库路径再构建。"""

    settings = build_pageindex_test_settings(tmp_path, llm_provider="openai")
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    legacy_path = tmp_path / "old_project" / "Input" / "kb_alpha" / "alpha.md"
    captured_paths: list[str] = []

    class FakePageIndexClient:
        """测试用 PageIndex 客户端，记录实际构建路径。"""

        def __init__(self, **_kwargs) -> None:
            pass

        def index(self, file_path: str, mode: str = "auto") -> str:
            captured_paths.append(file_path)
            return "pi_doc_repaired"

    with settings.sqlite_db_path.open("rb"):
        pass
    from src.db.connection import create_connection

    with create_connection(settings.sqlite_db_path) as connection:
        connection.execute(
            "UPDATE documents SET source_path = ? WHERE doc_uid = ?",
            (str(legacy_path), document["doc_uid"]),
        )
        connection.commit()

    monkeypatch.setattr("src.pageindex.service.PageIndexClient", FakePageIndexClient)
    service = PageIndexService(settings)

    result = service.build_index("kb_alpha", document["doc_uid"])

    assert result["pageindex_doc_id"] == "pi_doc_repaired"
    assert captured_paths
    captured_path = Path(captured_paths[0])
    assert captured_path.name == "source.cleaned.md"
    assert captured_path.read_text(encoding="utf-8").startswith("# alpha")
    with create_connection(settings.sqlite_db_path) as connection:
        repaired_row = connection.execute(
            "SELECT source_path FROM documents WHERE doc_uid = ?",
            (document["doc_uid"],),
        ).fetchone()
    assert repaired_row["source_path"] == "kb_alpha/alpha.md"


def test_pageindex_build_should_use_cleaned_markdown_copy_without_changing_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """构建 PageIndex 时应使用清洗后的 Markdown 副本，且不修改用户原始文档。"""

    settings = build_pageindex_test_settings(tmp_path, llm_provider="openai")
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    source_path = settings.input_root / "kb_alpha" / "alpha.md"
    original_text = "\n".join(
        [
            "# alpha",
            "",
            "目 录",
            "",
            "![](images/noise.jpg)",
            "",
            "## 正文",
            "",
            "阿胶正文内容。",
        ]
    )
    source_path.write_text(original_text, encoding="utf-8")
    captured_paths: list[Path] = []

    class FakePageIndexClient:
        """测试用 PageIndex 客户端，记录传给 PageIndex 的构建文件。"""

        def __init__(self, **_kwargs) -> None:
            pass

        def index(self, file_path: str, mode: str = "auto") -> str:
            captured_paths.append(Path(file_path))
            return "pi_doc_cleaned"

    monkeypatch.setattr("src.pageindex.service.PageIndexClient", FakePageIndexClient)

    result = PageIndexService(settings).build_index("kb_alpha", document["doc_uid"])

    assert result["pageindex_doc_id"] == "pi_doc_cleaned"
    assert captured_paths
    cleaned_path = captured_paths[0]
    assert cleaned_path != source_path
    cleaned_text = cleaned_path.read_text(encoding="utf-8")
    assert "![](images/noise.jpg)" not in cleaned_text
    assert "目 录" not in cleaned_text
    assert "阿胶正文内容。" in cleaned_text
    assert source_path.read_text(encoding="utf-8") == original_text


def seed_pageindex_workspace(settings: AppSettings, *, knowledge_base_id: str, doc_uid: str, file_name: str) -> str:
    """写入最小 PageIndex workspace，模拟 PageIndex 已完成建树。"""

    pageindex_doc_id = f"pi_{knowledge_base_id}_{doc_uid}".replace("-", "_")
    workspace = settings.sqlite_db_path.parent / "pageindex_workspace" / knowledge_base_id / doc_uid
    workspace.mkdir(parents=True, exist_ok=True)
    structure = [
        {
            "title": "总论",
            "line_num": 1,
            "level": 1,
            "summary": "介绍本地 PageIndex 文档。",
            "text": "# 总论\n\n这是本地 PageIndex 测试文档。",
            "nodes": [
                {
                    "title": "风险",
                    "line_num": 5,
                    "level": 2,
                    "summary": "风险只属于当前知识库。",
                    "text": "## 风险\n\n仅属于当前知识库，不能串到其它知识库。",
                    "nodes": [],
                }
            ],
        }
    ]
    source_path = settings.input_root / knowledge_base_id / file_name
    (workspace / "_meta.json").write_text(
        json.dumps(
            {
                pageindex_doc_id: {
                    "type": "md",
                    "doc_name": Path(file_name).stem,
                    "doc_description": "PageIndex 测试文档",
                    "path": str(source_path),
                    "line_count": 7,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (workspace / f"{pageindex_doc_id}.json").write_text(
        json.dumps(
            {
                "id": pageindex_doc_id,
                "type": "md",
                "path": str(source_path),
                "doc_name": Path(file_name).stem,
                "doc_description": "PageIndex 测试文档",
                "line_count": 7,
                "structure": structure,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return pageindex_doc_id


def seed_custom_pageindex_workspace(
    settings: AppSettings,
    *,
    knowledge_base_id: str,
    doc_uid: str,
    file_name: str,
    structure: list[dict],
) -> str:
    """写入自定义 PageIndex workspace，用于验证语义检索路径。"""

    pageindex_doc_id = f"pi_{knowledge_base_id}_{doc_uid}_custom".replace("-", "_")
    workspace = settings.sqlite_db_path.parent / "pageindex_workspace" / knowledge_base_id / doc_uid
    workspace.mkdir(parents=True, exist_ok=True)
    source_path = settings.input_root / knowledge_base_id / file_name
    (workspace / "_meta.json").write_text(
        json.dumps(
            {
                pageindex_doc_id: {
                    "type": "md",
                    "doc_name": Path(file_name).stem,
                    "doc_description": "PageIndex 语义检索测试文档",
                    "path": str(source_path),
                    "line_count": 12,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (workspace / f"{pageindex_doc_id}.json").write_text(
        json.dumps(
            {
                "id": pageindex_doc_id,
                "type": "md",
                "path": str(source_path),
                "doc_name": Path(file_name).stem,
                "doc_description": "PageIndex 语义检索测试文档",
                "line_count": 12,
                "structure": structure,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return pageindex_doc_id


def test_pageindex_service_should_return_tree_rows_from_local_workspace(tmp_path: Path) -> None:
    """已构建索引后，应能从 PageIndex workspace 读取文档结构表。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    rows = service.get_tree_rows("kb_alpha", document["doc_uid"])

    assert rows == [
        [1, "总论", "line 1", "介绍本地 PageIndex 文档。"],
        [2, "风险", "line 5", "风险只属于当前知识库。"],
    ]


def test_pageindex_service_should_answer_with_local_pageindex_evidence_and_save_history(tmp_path: Path) -> None:
    """PageIndex 提问应基于本地结构证据回答，并将历史限定在当前知识库和文档。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    other_document = seed_markdown_document(settings, knowledge_base_id="kb_beta", file_name="beta.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    other_pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_beta",
        doc_uid=other_document["doc_uid"],
        file_name="beta.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    service.upsert_index_record("kb_beta", other_document["doc_uid"], other_pageindex_doc_id, source_hash="hash_beta")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "风险 属于哪个知识库")
    history = service.list_query_history("kb_alpha", document["doc_uid"])
    other_history = service.list_query_history("kb_beta", other_document["doc_uid"])

    assert "风险" in answer["answer"]
    assert answer["evidence"][0]["title"] == "风险"
    assert len(history) == 1
    assert history[0]["question"] == "风险 属于哪个知识库"
    assert other_history == []


def test_pageindex_service_should_answer_across_all_indexed_documents_in_knowledge_base(tmp_path: Path) -> None:
    """知识库级 PageIndex 提问应检索当前知识库下所有已构建文档。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    first_document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    second_document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="beta.md")
    other_document = seed_markdown_document(settings, knowledge_base_id="kb_beta", file_name="gamma.md")
    service = PageIndexService(settings)
    first_pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=first_document["doc_uid"],
        file_name="alpha.md",
    )
    second_pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=second_document["doc_uid"],
        file_name="beta.md",
    )
    other_pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_beta",
        doc_uid=other_document["doc_uid"],
        file_name="gamma.md",
    )
    service.upsert_index_record("kb_alpha", first_document["doc_uid"], first_pageindex_doc_id, source_hash="hash_alpha")
    service.upsert_index_record("kb_alpha", second_document["doc_uid"], second_pageindex_doc_id, source_hash="hash_beta")
    service.upsert_index_record("kb_beta", other_document["doc_uid"], other_pageindex_doc_id, source_hash="hash_gamma")

    answer = service.ask_knowledge_base_question("kb_alpha", "风险 属于哪个知识库")
    history = service.list_knowledge_base_query_history("kb_alpha")
    first_doc_history = service.list_query_history("kb_alpha", first_document["doc_uid"])
    second_doc_history = service.list_query_history("kb_alpha", second_document["doc_uid"])
    other_history = service.list_knowledge_base_query_history("kb_beta")

    assert "风险" in answer["answer"]
    assert {item["doc_uid"] for item in answer["evidence"]} == {first_document["doc_uid"], second_document["doc_uid"]}
    assert len(history) == 1
    assert history[0]["question"] == "风险 属于哪个知识库"
    assert first_doc_history or second_doc_history
    assert other_history == []


def test_pageindex_service_should_use_llm_tree_reasoning_before_keyword_fallback(tmp_path: Path) -> None:
    """PageIndex 提问应优先让 LLM 基于树结构语义选择证据节点，而不是只匹配关键词。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {
            "title": "目录",
            "line_num": 1,
            "level": 1,
            "summary": "文档的组织说明。",
            "text": "# 目录\n\n这是组织说明。",
            "nodes": [],
        },
        {
            "title": "功效",
            "line_num": 8,
            "level": 1,
            "summary": "讨论滋养、润泽与皮肤状态改善。",
            "text": "# 功效\n\n材料提到滋养阴血、润燥，并说明与皮肤状态改善有关。",
            "nodes": [],
        },
    ]

    class StubReasoningClient:
        """测试用语义推理客户端，模拟 LLM 选择非关键词命中的正确节点。"""

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            self.prompts.append(user_prompt)
            if "问题分析" in system_prompt:
                return {
                    "intent": "询问功效",
                    "entities": ["皮肤"],
                    "keywords": ["皮肤", "滋养", "润燥"],
                    "expanded_terms": ["皮肤状态改善", "滋养阴血"],
                }
            if "Question Planner" in system_prompt:
                return {
                    "question_type": "information_extraction",
                    "answer_strategy": "说明哪些证据能回答皮肤状态改善问题。",
                    "target": "皮肤状态改善相关内容",
                    "claim": "",
                    "required_output": ["结论", "依据", "来源"],
                    "needs_evidence_relation": False,
                }
            if "迭代式树结构检索" in system_prompt:
                assert "candidate_id" in user_prompt
                assert "皮肤有帮助" in user_prompt
                assert "滋养阴血" in user_prompt
                assert "information_extraction" in user_prompt
                return {
                    "selected_nodes": [{"candidate_id": "node_2", "reason": "语义上对应皮肤状态改善"}],
                    "sufficiency": "sufficient",
                    "missing_information": "",
                    "next_search_focus": "",
                    "answer": "相关内容位于“功效”，证据提到滋养、润泽与皮肤状态改善。",
                }
            if "Question Plan JSON" in user_prompt:
                assert "information_extraction" in user_prompt
                return {"answer": "相关内容位于“功效”，证据提到滋养、润泽与皮肤状态改善。"}
            return {}

    llm_client = StubReasoningClient()
    service = PageIndexService(settings, llm_client=llm_client)
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "哪些内容说明它对皮肤有帮助")

    assert answer["answer"] == "相关内容位于“功效”，证据提到滋养、润泽与皮肤状态改善。"
    assert answer["retrieval_mode"] == "LLM 语义树推理"
    assert answer["evidence"][0]["title"] == "功效"
    assert answer["evidence"][0]["reason"] == "语义上对应皮肤状态改善"
    assert answer["debug"]["question_analysis"]["intent"] == "询问功效"
    assert answer["debug"]["question_analysis"]["expanded_terms"] == ["皮肤状态改善", "滋养阴血"]
    assert answer["debug"]["candidate_nodes"][0]["candidate_id"] == "node_2"
    assert answer["debug"]["selected_nodes"][0]["reason"] == "语义上对应皮肤状态改善"
    assert len(llm_client.prompts) == 5


def test_pageindex_iterative_prompt_should_require_sufficiency_fields() -> None:
    """迭代式检索 prompt 应要求 LLM 返回充分性判断和下一轮检索焦点。"""

    system_prompt, user_prompt = PageIndexService._build_iterative_tree_reasoning_prompts(
        "阿胶有哪些质量检测方法",
        {"keywords": ["质量检测", "方法"]},
        {
            "question_type": "information_extraction",
            "answer_strategy": "列举阿胶质量检测方法。",
            "target": "阿胶质量检测方法",
            "claim": "",
            "required_output": ["结论", "方法清单", "来源"],
            "needs_evidence_relation": False,
            "insufficient_evidence_policy": "证据不足时说明只覆盖当前知识库。",
        },
        [
            {
                "candidate_id": "node_1",
                "title": "质量检测",
                "level": 2,
                "position": "line 10",
                "summary": "检测方法概述",
                "content_excerpt": "包括性状、鉴别、含量测定。",
                "score": 10,
            }
        ],
        [],
        1,
    )

    assert "sufficiency" in user_prompt
    assert "missing_information" in user_prompt
    assert "next_search_focus" in user_prompt
    assert "selected_nodes" in user_prompt
    assert "Question Plan JSON" in user_prompt
    assert "information_extraction" in user_prompt
    assert "方法清单" in user_prompt
    assert "只返回 JSON" in system_prompt


def test_pageindex_should_continue_iterative_retrieval_until_sufficient(tmp_path: Path) -> None:
    """PageIndex LLM 检索应在证据不足时继续下一轮，证据充分后停止。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {
            "title": "质量检测概述",
            "line_num": 8,
            "level": 1,
            "summary": "阿胶质量检测包括多类方法，需要继续查具体项目。",
            "text": "# 质量检测概述\n\n阿胶质量检测包括多类方法，需要继续查具体项目。",
            "nodes": [],
        },
        {
            "title": "质量检测方法",
            "line_num": 18,
            "level": 1,
            "summary": "包括真伪鉴别、重金属检测和微生物检测。",
            "text": "# 质量检测方法\n\n包括真伪鉴别、重金属检测和微生物检测。",
            "nodes": [],
        },
    ]

    class IterativeReasoningClient:
        """测试用 LLM，第一轮认为证据不足，第二轮认为证据充分。"""

        def __init__(self) -> None:
            self.iterative_calls = 0

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            if "问题分析" in system_prompt:
                return {
                    "intent": "询问方法",
                    "entities": ["阿胶", "质量检测"],
                    "keywords": ["质量检测", "方法"],
                    "expanded_terms": ["真伪鉴别", "重金属检测", "微生物检测"],
                }
            if "迭代式树结构检索" in system_prompt:
                self.iterative_calls += 1
                if self.iterative_calls == 1:
                    return {
                        "selected_nodes": [{"candidate_id": "node_1", "reason": "先读取质量检测概述"}],
                        "sufficiency": "partial",
                        "missing_information": "缺少具体检测方法清单",
                        "next_search_focus": "质量检测方法",
                        "answer": "",
                    }
                return {
                    "selected_nodes": [{"candidate_id": "node_2", "reason": "补充具体检测项目"}],
                    "sufficiency": "sufficient",
                    "missing_information": "",
                    "next_search_focus": "",
                    "answer": "",
                }
            if "Question Planner" in system_prompt:
                return {
                    "question_type": "information_extraction",
                    "answer_strategy": "列举质量检测方法。",
                    "target": "阿胶质量检测方法",
                    "claim": "",
                    "required_output": ["结论", "方法清单", "来源"],
                    "needs_evidence_relation": False,
                }
            return {"answer": "结论：阿胶质量检测方法包括真伪鉴别、重金属检测和微生物检测。"}

    llm_client = IterativeReasoningClient()
    service = PageIndexService(settings, llm_client=llm_client)
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "阿胶有哪些质量检测方法")

    assert llm_client.iterative_calls == 2
    assert [item["title"] for item in answer["evidence"][:2]] == ["质量检测概述", "质量检测方法"]
    assert answer["debug"]["retrieval_rounds"][0]["sufficiency"] == "partial"
    assert answer["debug"]["retrieval_rounds"][0]["missing_information"] == "缺少具体检测方法清单"
    assert answer["debug"]["retrieval_rounds"][1]["sufficiency"] == "sufficient"
    assert answer["debug"]["retrieval_rounds"][1]["selected_nodes"][0]["title"] == "质量检测方法"


def test_pageindex_template_retrieval_policy_should_limit_selected_nodes(tmp_path: Path) -> None:
    """PageIndex 模板检索策略应真正限制每轮选中节点数量。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {
            "title": "质量检测概述",
            "line_num": 8,
            "level": 1,
            "summary": "阿胶质量检测概述。",
            "text": "# 质量检测概述\n\n阿胶质量检测概述。",
            "nodes": [],
        },
        {
            "title": "质量检测方法",
            "line_num": 18,
            "level": 1,
            "summary": "阿胶质量检测方法清单。",
            "text": "# 质量检测方法\n\n阿胶质量检测方法清单。",
            "nodes": [],
        },
    ]

    class PolicyClient:
        """测试用 LLM，返回多节点选择以验证模板策略裁剪。"""

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            if "问题分析" in system_prompt:
                return {
                    "intent": "询问方法",
                    "entities": ["阿胶", "质量检测"],
                    "keywords": ["质量检测", "方法"],
                    "expanded_terms": [],
                }
            if "Question Planner" in system_prompt:
                return {
                    "question_type": "information_extraction",
                    "answer_strategy": "列举质量检测方法。",
                    "target": "阿胶质量检测方法",
                    "claim": "",
                    "required_output": ["结论", "来源"],
                    "needs_evidence_relation": False,
                }
            if "迭代式树结构检索" in system_prompt:
                return {
                    "selected_nodes": [
                        {"candidate_id": "node_1", "reason": "概述相关"},
                        {"candidate_id": "node_2", "reason": "方法相关"},
                    ],
                    "sufficiency": "sufficient",
                    "missing_information": "",
                    "next_search_focus": "",
                    "answer": "",
                }
            return {"answer": "结论：按模板策略只读取一个节点。"}

    service = PageIndexService(settings, llm_client=PolicyClient())
    service.template_service.save_template(
        {
            "template_id": "limited_retrieval",
            "template_name": "限制检索",
            "description": "限制选中节点数量",
            "answer_mode": "strict_qa",
            "system_prompt": "只返回 JSON。",
            "user_prompt_template": "Question Plan JSON：{question_plan}\n证据：{evidence_json}",
            "retrieval_policy": {
                "max_tree_candidates": 30,
                "max_selected_nodes": 1,
                "max_rag_evidence": 0,
                "include_structure_context": True,
            },
        }
    )
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "阿胶有哪些质量检测方法", template_id="limited_retrieval")

    assert [item["title"] for item in answer["evidence"]] == ["质量检测概述"]
    assert [item["title"] for item in answer["debug"]["retrieval_rounds"][0]["selected_nodes"]] == ["质量检测概述"]


def test_pageindex_should_extract_cross_reference_targets() -> None:
    """PageIndex 应识别明确的文档内交叉引用目标。"""

    targets = PageIndexService._extract_cross_reference_targets(
        "主文提到详见附录 G；另参见表 5.3，见第六章，并详见“质量标准”。"
    )

    assert targets == ["附录 G", "表 5.3", "第六章", "质量标准"]


def test_pageindex_should_find_cross_reference_candidates() -> None:
    """PageIndex 应把交叉引用目标匹配到树节点标题或摘要。"""

    structure = [
        {"title": "正文", "summary": "主章节", "line_num": 1, "level": 1, "nodes": []},
        {"title": "附录 G", "summary": "统计表格", "line_num": 50, "level": 1, "nodes": []},
        {"title": "质量标准", "summary": "检测依据", "line_num": 80, "level": 1, "nodes": []},
    ]

    candidates = PageIndexService._find_cross_reference_candidates(structure, ["附录 G", "质量标准"])

    assert [item["title"] for item in candidates] == ["附录 G", "质量标准"]
    assert candidates[0]["candidate_id"] == "xref_1"
    assert candidates[0]["reason"] == "交叉引用候选"


def test_pageindex_iterative_retrieval_should_follow_cross_reference_candidate(tmp_path: Path) -> None:
    """迭代检索读取到明确交叉引用后，应把目标节点加入下一轮候选。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {
            "title": "递延资产说明",
            "line_num": 8,
            "level": 1,
            "summary": "递延资产主文说明。",
            "text": "# 递延资产说明\n\n主章节只说明资产增值额，递延资产总值详见附录 G。",
            "nodes": [],
        },
        {
            "title": "附录 G",
            "line_num": 40,
            "level": 1,
            "summary": "统计表格。",
            "text": "# 附录 G\n\n递延资产总值为 123。",
            "nodes": [],
        },
    ]

    class CrossReferenceClient:
        """测试用 LLM，第二轮检查交叉引用候选是否进入 prompt。"""

        def __init__(self) -> None:
            self.iterative_calls = 0

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            if "问题分析" in system_prompt:
                return {
                    "intent": "查询数值",
                    "entities": ["递延资产"],
                    "keywords": ["递延资产", "总值"],
                    "expanded_terms": [],
                }
            if "迭代式树结构检索" in system_prompt:
                self.iterative_calls += 1
                if self.iterative_calls == 1:
                    return {
                        "selected_nodes": [{"candidate_id": "node_1", "reason": "主文提到递延资产"}],
                        "sufficiency": "partial",
                        "missing_information": "需要附录 G 中的总值",
                        "next_search_focus": "附录 G",
                        "answer": "",
                    }
                assert "附录 G" in user_prompt
                assert "交叉引用候选" in user_prompt
                return {
                    "selected_nodes": [{"candidate_id": "xref_1", "reason": "跟随主文引用到附录 G"}],
                    "sufficiency": "sufficient",
                    "missing_information": "",
                    "next_search_focus": "",
                    "answer": "",
                }
            if "Question Planner" in system_prompt:
                return {
                    "question_type": "information_extraction",
                    "answer_strategy": "读取引用附录中的数值。",
                    "target": "递延资产总值",
                    "claim": "",
                    "required_output": ["结论", "来源"],
                    "needs_evidence_relation": False,
                }
            return {"answer": "结论：递延资产总值为 123。"}

    llm_client = CrossReferenceClient()
    service = PageIndexService(settings, llm_client=llm_client)
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "递延资产总值是多少")

    assert llm_client.iterative_calls == 2
    assert answer["evidence"][1]["title"] == "附录 G"
    assert answer["debug"]["retrieval_rounds"][1]["selected_nodes"][0]["reason"] == "跟随主文引用到附录 G"


def test_pageindex_service_should_report_keyword_fallback_when_llm_reasoning_fails(tmp_path: Path) -> None:
    """LLM 树推理失败时，应回退本地关键词并把本次模式返回给前端。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")

    class FailingReasoningClient:
        """测试用失败客户端，模拟 LLM 调用异常。"""

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            raise RuntimeError("llm down")

    service = PageIndexService(settings, llm_client=FailingReasoningClient())
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "风险 属于哪个知识库")

    assert answer["retrieval_mode"] == "本地关键词降级"
    assert answer["llm_error"] == "llm down"
    assert answer["evidence"][0]["title"] == "风险"
    assert answer["debug"]["question_analysis"]["mode"] == "本地关键词"
    assert answer["debug"]["candidate_nodes"][0]["title"] == "风险"


def test_pageindex_service_should_not_use_keyword_or_rag_fallback_when_llm_selects_no_node(tmp_path: Path) -> None:
    """LLM 已判断候选节点不相关时，不应再用泛化关键词或 RAG 片段补出伪证据。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {
            "title": "育肾活血方联合促性腺激素释放激素类似物治疗不孕症",
            "line_num": 8,
            "level": 1,
            "summary": "不涉及阿胶治疗不孕不育。",
            "nodes": [],
        }
    ]
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_generic_treatment",
        content="观察组加用阿胶口服，治疗16周，用于补充铁剂相关研究。",
        source_span="section-1:chunk-1",
    )

    class EmptySelectionClient:
        """测试用语义推理客户端，模拟 LLM 明确认为候选证据不足。"""

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            if "问题分析" in system_prompt:
                return {
                    "intent": "医疗咨询",
                    "entities": ["阿胶", "不孕不育"],
                    "keywords": ["阿胶", "治疗", "不孕不育"],
                    "expanded_terms": ["不孕症", "疗效"],
                }
            return {"selected_nodes": [], "answer": "未找到直接证据。"}

    service = PageIndexService(settings, llm_client=EmptySelectionClient())
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "阿胶能不能治疗不孕不育")

    assert answer["retrieval_mode"] == "LLM 语义树推理"
    assert answer["evidence"] == []
    assert answer["answer"].startswith("结论：证据不足")
    assert "依据：" in answer["answer"]
    assert answer["debug"]["selected_nodes"] == []


def test_pageindex_rag_query_terms_should_ignore_generic_treatment_when_specific_term_exists() -> None:
    """RAG/FTS 补证据不能用“治疗”这类泛词驱动，否则容易返回相似治疗流程噪音。"""

    terms = ["阿胶", "治疗", "不孕不育"]

    query_terms = PageIndexService._build_rag_query_terms(terms, "阿胶能不能治疗不孕不育")

    assert query_terms == ["不孕不育"]


def test_pageindex_rag_query_terms_should_expand_condition_question() -> None:
    """疾病疗效类问题应抽出核心对象词，并补充常见同义表达用于召回。"""

    terms = PageIndexService._extract_question_terms("阿胶对胃病有疗效")
    query_terms = PageIndexService._build_rag_query_terms(terms, "阿胶对胃病有疗效")

    assert "胃病" in terms
    assert "胃病有疗效" not in terms
    assert "脾胃" in query_terms
    assert "消化不良" in query_terms


def test_pageindex_rag_query_terms_should_reuse_entity_dictionary_aliases() -> None:
    """PageIndex 召回词应复用通用实体词表扩展，避免在服务内写死同义词。"""

    query_terms = PageIndexService._build_rag_query_terms(["女性"], "女性")

    assert "女性" in query_terms
    assert "妇女" in query_terms


def test_pageindex_should_use_rag_when_tree_has_no_candidates(tmp_path: Path) -> None:
    """PageIndex 树摘要无命中时，应允许同文档 RAG/FTS 召回细粒度证据。"""

    settings = build_pageindex_test_settings(tmp_path, llm_provider="openai")
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {"title": "应用注意点", "line_num": 1, "level": 1, "summary": "介绍服用注意事项。", "nodes": []},
    ]
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_stomach",
        content="现代阿胶加工后比较滋腻，容易影响脾胃；对于胃部胀满、消化不良、纳差，属中医脾胃虚弱者应慎用阿胶。",
        source_span="section-1:chunk-1",
    )

    class FakeLLMClient:
        """测试用 LLM 客户端，仅用于最终回答生成。"""

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            if "Question Plan" in user_prompt or "证据" in user_prompt:
                return {"answer": "结论：证据显示胃部胀满、消化不良、脾胃虚弱者应慎用阿胶。"}
            return {}

    service = PageIndexService(settings, llm_client=FakeLLMClient())
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "阿胶对胃病有疗效")

    assert answer["evidence"]
    assert answer["evidence"][0]["source_type"] == "RAG/FTS 原文"
    assert "脾胃" in answer["evidence"][0]["content"]
    assert answer["debug"]["candidate_nodes"] == []
    assert answer["debug"]["rag_evidence"]


def test_pageindex_service_should_return_debug_candidates_for_diagnosis(tmp_path: Path) -> None:
    """PageIndex 提问结果应返回候选节点诊断信息，便于判断召回和重排质量。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "风险 属于哪个知识库")

    debug = answer["debug"]
    assert debug["retrieval_mode"] == "本地关键词降级"
    assert debug["question_analysis"]["keywords"] == ["风险", "属于哪个知识库"]
    assert debug["candidate_nodes"][0]["title"] == "风险"
    assert debug["candidate_nodes"][0]["score"] > 0
    assert "line 5" == debug["candidate_nodes"][0]["position"]


def test_pageindex_candidate_ranking_should_penalize_generic_front_matter(tmp_path: Path) -> None:
    """本地候选召回应降低文档标题、课题组、CIP 等泛化前置节点的排序。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {"title": "阿胶历史文化通典", "line_num": 1, "level": 1, "summary": "阿胶历史文化来源", "nodes": []},
        {"title": "《阿胶历史文化通典》课题组", "line_num": 57, "level": 1, "summary": "阿胶历史文化来源", "nodes": []},
        {"title": "绪论 阿胶历史文化综述", "line_num": 116, "level": 1, "summary": "介绍阿胶历史文化来源", "nodes": []},
    ]
    service = PageIndexService(settings)
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    record = service._get_index_record("kb_alpha", document["doc_uid"])
    candidates = service._build_tree_candidates(
        record,
        structure,
        question_analysis={"keywords": ["阿胶", "历史", "文化", "来源"], "entities": [], "expanded_terms": []},
        limit=3,
        include_content=False,
    )

    assert candidates[0]["title"] == "绪论 阿胶历史文化综述"


def test_pageindex_question_terms_should_keep_meaningful_chinese_phrases() -> None:
    """本地问题词提取应保留核心短语，避免跨字碎片污染检索。"""

    cold_terms = PageIndexService._extract_question_terms("阿胶对感冒有没有作用")
    quality_terms = PageIndexService._extract_question_terms("阿胶质量检测方法有哪些")

    assert "感冒" in cold_terms
    assert "不孕不育" in PageIndexService._extract_question_terms("阿胶能不能治疗不孕不育")
    assert "胶对" not in cold_terms
    assert "对感" not in cold_terms
    assert "作用" not in cold_terms
    assert "质量检测" in quality_terms
    assert "检测方法" in quality_terms
    assert "有哪些" not in quality_terms


def test_pageindex_local_rank_should_return_empty_when_only_generic_terms_match(tmp_path: Path) -> None:
    """本地降级没有核心问题词命中时应返回证据不足，而不是用泛词硬凑节点。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {"title": "基于斑马鱼模型的新阿胶对化疗诱导免疫损伤的保护作用", "line_num": 1, "level": 1, "summary": "免疫损伤保护", "nodes": []},
        {"title": "不同工艺阿胶对血虚证小鼠外周血象的影响", "line_num": 8, "level": 1, "summary": "血虚证小鼠", "nodes": []},
    ]
    service = PageIndexService(settings)
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    record = service._get_index_record("kb_alpha", document["doc_uid"])

    evidence, debug_nodes = service._rank_evidence(record, structure, "阿胶对感冒有没有作用")

    assert evidence == []
    assert debug_nodes == []


def test_pageindex_local_rank_should_keep_direct_quality_detection_match(tmp_path: Path) -> None:
    """本地降级仍应保留问题核心词直接命中的 PageIndex 节点。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {"title": "阿胶在《伤寒杂病论》中的应用", "line_num": 1, "level": 1, "summary": "经典方剂", "nodes": []},
        {"title": "阿胶及其制品质量检测方法研究进展", "line_num": 12, "level": 1, "summary": "真伪鉴别、重金属检测和微生物检测", "nodes": []},
    ]
    service = PageIndexService(settings)
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    record = service._get_index_record("kb_alpha", document["doc_uid"])

    evidence, debug_nodes = service._rank_evidence(record, structure, "阿胶质量检测方法有哪些")

    assert evidence
    assert evidence[0]["title"] == "阿胶及其制品质量检测方法研究进展"
    assert debug_nodes[0]["title"] == "阿胶及其制品质量检测方法研究进展"


def test_pageindex_local_rank_should_penalize_toc_like_nodes(tmp_path: Path) -> None:
    """目录式 PageIndex 节点内容较薄，应排在真实正文节点之后。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {"title": "古法 /112", "line_num": 10, "level": 1, "summary": "文献 /112 流程 /117", "nodes": []},
        {"title": "器 用", "line_num": 80, "level": 1, "summary": "阿胶制作过程中使用刮皮、熬胶、切胶工具", "nodes": []},
    ]
    service = PageIndexService(settings)
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    record = service._get_index_record("kb_alpha", document["doc_uid"])

    evidence, debug_nodes = service._rank_evidence(record, structure, "阿胶制作工艺有什么特点")

    assert evidence[0]["title"] == "器 用"
    assert debug_nodes[0]["title"] == "器 用"


def test_pageindex_tree_candidates_should_fallback_to_question_terms_when_llm_terms_are_generic(tmp_path: Path) -> None:
    """LLM 问题分析词过泛时，树候选仍应使用用户问题中的核心短语。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    structure = [
        {"title": "阿胶治疗贫血研究", "line_num": 1, "level": 1, "summary": "贫血治疗", "nodes": []},
        {"title": "育肾活血方联合促性腺激素释放激素类似物治疗子宫内膜异位症不孕症", "line_num": 20, "level": 1, "summary": "不孕不育相关研究", "nodes": []},
    ]
    service = PageIndexService(settings)
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=structure,
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    record = service._get_index_record("kb_alpha", document["doc_uid"])

    candidates = service._build_tree_candidates(
        record,
        structure,
        question="阿胶能不能治疗不孕不育",
        question_analysis={"entities": ["阿胶"], "keywords": ["阿胶", "治疗"], "expanded_terms": []},
        limit=3,
        include_content=False,
    )

    assert candidates
    assert candidates[0]["title"] == "育肾活血方联合促性腺激素释放激素类似物治疗子宫内膜异位症不孕症"


def test_pageindex_service_should_add_rag_fts_evidence_inside_current_document_only(tmp_path: Path) -> None:
    """PageIndex 应在当前文档范围内补充 RAG/FTS 原文证据，不能混入其它文档。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    other_document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="beta.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_alpha_skin",
        content="阿胶相关资料指出，滋养阴血与润燥可用于解释皮肤状态改善。",
        source_span="line 8",
    )
    seed_chunk(
        settings,
        doc_uid=other_document["doc_uid"],
        chunk_id="chunk_beta_skin",
        content="其它文档中的皮肤状态改善内容不应混入当前 PageIndex 问答。",
        source_span="line 9",
    )

    answer = service.ask_question("kb_alpha", document["doc_uid"], "哪些内容说明它对皮肤有帮助")

    rag_items = [item for item in answer["evidence"] if item.get("source_type") == "RAG/FTS 原文"]
    assert rag_items
    assert rag_items[0]["chunk_id"] == "chunk_alpha_skin"
    assert "滋养阴血" in rag_items[0]["content"]
    assert "滋养阴血" in answer["answer"]
    assert all(item.get("doc_uid") == document["doc_uid"] for item in rag_items)
    assert "chunk_beta_skin" not in {item.get("chunk_id") for item in rag_items}
    assert answer["debug"]["rag_evidence"][0]["chunk_id"] == "chunk_alpha_skin"


def test_pageindex_rag_evidence_should_ignore_generic_entity_terms(tmp_path: Path) -> None:
    """RAG/FTS 补充证据不能被“阿胶”等泛词牵引到固定片段，应优先使用具体问题词。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_generic_ejiao",
        content="阿胶是传统滋补材料，常见资料会介绍其补血、止血、滋阴等笼统功效。",
        source_span="line 1",
    )
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_cold_evidence",
        content="感冒期间是否适合服用阿胶，需要结合发热、咳嗽和外感病程判断，不能只看滋补功效。",
        source_span="line 20",
    )
    record = service._get_index_record("kb_alpha", document["doc_uid"])

    rag_items = service._search_rag_fts_evidence(
        record,
        "阿胶对感冒的疗效",
        {"entities": ["阿胶"], "keywords": ["阿胶", "感冒", "疗效"], "expanded_terms": []},
    )

    assert [item["chunk_id"] for item in rag_items] == ["chunk_cold_evidence"]
    assert "感冒期间" in rag_items[0]["content"]


def test_pageindex_rag_evidence_should_skip_when_only_generic_terms(tmp_path: Path) -> None:
    """只有泛词时不追加 RAG/FTS 证据，避免不同问题反复引用同一批高频片段。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_generic_ejiao",
        content="阿胶功效与作用介绍，包含补血、止血、滋阴等常见泛化描述。",
        source_span="line 1",
    )
    record = service._get_index_record("kb_alpha", document["doc_uid"])

    rag_items = service._search_rag_fts_evidence(
        record,
        "阿胶有什么功效",
        {"entities": ["阿胶"], "keywords": ["阿胶", "功效", "作用"], "expanded_terms": []},
    )

    assert rag_items == []


def test_pageindex_rag_evidence_should_skip_incidental_trial_dropout_context(tmp_path: Path) -> None:
    """具体词只在试验脱落等偶发语境出现时，不应作为 PageIndex 补充证据。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_dropout_cold",
        content="阿胶贫血研究中有1例患者因流行性感冒停止治疗，其数据被排除在分析之外。",
        source_span="line 30",
    )
    record = service._get_index_record("kb_alpha", document["doc_uid"])

    rag_items = service._search_rag_fts_evidence(
        record,
        "阿胶对感冒的疗效",
        {"entities": ["阿胶"], "keywords": ["阿胶", "感冒", "疗效"], "expanded_terms": []},
    )

    assert rag_items == []


def test_pageindex_rag_evidence_should_not_use_expanded_generic_medical_terms(tmp_path: Path) -> None:
    """RAG/FTS 不应因 LLM 扩展出的泛化药理词命中弱相关原文片段。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_quality_control",
        content="阿胶质量控制研究使用特征肽鉴别方法，比较不同动物胶原蛋白来源。",
        source_span="line 100",
    )
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_hormone",
        content="阿胶珠联合孕激素用于妇科研究，观察子宫内膜与出血改善情况。",
        source_span="line 120",
    )
    record = service._get_index_record("kb_alpha", document["doc_uid"])

    rag_items = service._search_rag_fts_evidence(
        record,
        "阿胶对感冒有没有作用",
        {"entities": ["阿胶"], "keywords": ["阿胶", "感冒", "免疫", "抗炎", "疗效"], "expanded_terms": ["质量控制", "孕激素"]},
    )

    assert rag_items == []


def test_pageindex_rag_evidence_should_keep_question_specific_term_over_broad_context(tmp_path: Path) -> None:
    """RAG/FTS 应优先保留问题里的具体词，过滤只含泛化上下文的片段。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_anemia",
        content="阿胶用于贫血研究，主要观察血红蛋白水平和胃肠道不适反应。",
        source_span="line 200",
    )
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_fertility",
        content="不孕不育患者辨证使用阿胶相关方剂时，需结合月经、卵巢储备和助孕方案综合判断。",
        source_span="line 240",
    )
    record = service._get_index_record("kb_alpha", document["doc_uid"])

    rag_items = service._search_rag_fts_evidence(
        record,
        "阿胶能不能治疗不孕不育",
        {"entities": ["阿胶"], "keywords": ["阿胶", "不孕不育", "补血", "临床"], "expanded_terms": ["卵巢储备功能低下"]},
    )

    assert [item["chunk_id"] for item in rag_items] == ["chunk_fertility"]


def test_pageindex_rag_evidence_should_expand_heart_disease_to_heart_related_chunks(tmp_path: Path) -> None:
    """心脏病问法应能补召回“心脏相关病证”原文片段，并带出可追溯引用字段。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    with transaction(settings.sqlite_db_path) as connection:
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, doc_uid, section_id, chunk_index, content, source_span,
                heading_path, source_start_line, source_end_line, source_anchor, chunk_type,
                token_count, created_at, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-06-18T00:00:00+00:00', '2026-06-18T00:00:00+00:00')
            """,
            (
                "chunk_heart",
                document["doc_uid"],
                0,
                "阿胶养血滋阴。如心脏相关病证用炙甘草汤，需由医师辨证使用。",
                "section-2:chunk-0",
                "临床应用 > 心脏相关病证",
                20,
                22,
                "L20-L22",
                "paragraph",
                32,
            ),
        )
        connection.execute(
            "INSERT INTO chunk_fts (chunk_id, doc_uid, content) VALUES (?, ?, ?)",
            ("chunk_heart", document["doc_uid"], "阿胶养血滋阴。如心脏相关病证用炙甘草汤，需由医师辨证使用。"),
        )

    record = service._get_index_record("kb_alpha", document["doc_uid"])

    rag_items = service._search_rag_fts_evidence(
        record,
        "心脏病吃阿胶有好处",
        {"entities": ["阿胶"], "keywords": ["阿胶", "心脏病", "好处"], "expanded_terms": []},
    )

    assert [item["chunk_id"] for item in rag_items] == ["chunk_heart"]
    assert rag_items[0]["heading_path"] == "临床应用 > 心脏相关病证"
    assert rag_items[0]["source_anchor"] == "L20-L22"
    assert rag_items[0]["chunk_type"] == "paragraph"


def test_pageindex_local_answer_should_return_conclusion_not_hit_description() -> None:
    """本地降级答案应先给结论，不能只说明命中了哪个节点。"""

    answer = PageIndexService._build_local_answer(
        "心脏病吃阿胶有好处",
        [
            {
                "title": "阿胶应用的注意点（禁忌）",
                "position": "line 5946",
                "content": "阿胶有较高药用价值，但必须在医师指导下正确服用，否则会有不良反应。",
                "source_type": "PageIndex 节点",
            },
            {
                "title": "RAG/FTS 原文片段",
                "position": "section-445:chunk-1822",
                "content": "阿胶养血滋阴。如心脏相关病证用炙甘草汤，需由医师辨证使用。",
                "source_type": "RAG/FTS 原文",
            },
        ],
    )

    assert answer.startswith("结论：")
    assert "不能证明“心脏病吃阿胶有好处”" in answer
    assert "依据：" in answer
    assert "来源：" in answer
    assert "不确定点：" in answer
    assert "根据PageIndex 节点定位" not in answer


def test_pageindex_evidence_should_be_classified_before_answering() -> None:
    """PageIndex 证据应标注直接支持、间接相关或风险提醒，供结论判断使用。"""

    classified = PageIndexService._classify_evidence_items(
        "心脏病吃阿胶有好处",
        [
            {
                "title": "阿胶应用的注意点（禁忌）",
                "position": "line 5946",
                "content": "阿胶有较高药用价值，但必须在医师指导下正确服用，否则会有不良反应。",
                "source_type": "PageIndex 节点",
            },
            {
                "title": "RAG/FTS 原文片段",
                "position": "section-445:chunk-1822",
                "content": "阿胶养血滋阴。如心脏相关病证用炙甘草汤，需由医师辨证使用。",
                "source_type": "RAG/FTS 原文",
            },
        ],
    )

    assert [item["evidence_type"] for item in classified] == ["risk_or_condition", "method_or_formula_context"]
    assert [item["evidence_label"] for item in classified] == ["条件或限制", "方法/组合语境"]


def test_pageindex_formula_context_should_not_be_direct_support_for_benefit_claim() -> None:
    """方剂语境中的“心脏相关病证”不能当作“吃阿胶有好处”的直接支持。"""

    classified = PageIndexService._classify_evidence_items(
        "心脏病吃阿胶有好处",
        [
            {
                "title": "RAG/FTS 原文片段",
                "position": "section-445:chunk-1822",
                "content": "阿胶有良好的组织器官修复作用。阿胶养血滋阴。如心脏相关病证用炙甘草汤，月经病、皮肤黏膜疾病的治疗中亦常用阿胶。",
                "source_type": "RAG/FTS 原文",
            }
        ],
    )

    assert classified[0]["evidence_type"] == "partial_support"
    assert classified[0]["evidence_label"] == "部分支持"


def test_pageindex_local_answer_should_explain_evidence_judgement() -> None:
    """PageIndex 本地答案应展示证据判断，说明为什么不能直接下肯定结论。"""

    classified = PageIndexService._classify_evidence_items(
        "心脏病吃阿胶有好处",
        [
            {
                "title": "阿胶应用的注意点（禁忌）",
                "position": "line 5946",
                "content": "阿胶有较高药用价值，但必须在医师指导下正确服用，否则会有不良反应。",
                "source_type": "PageIndex 节点",
            },
            {
                "title": "RAG/FTS 原文片段",
                "position": "section-445:chunk-1822",
                "content": "阿胶养血滋阴。如心脏相关病证用炙甘草汤，需由医师辨证使用。",
                "source_type": "RAG/FTS 原文",
            },
        ],
    )

    answer = PageIndexService._build_local_answer("心脏病吃阿胶有好处", classified)

    assert "证据判断：" in answer
    assert "条件或限制" in answer
    assert "方法/组合语境" in answer
    assert "直接支持" not in answer


def test_pageindex_local_answer_should_give_clear_formula_context_conclusion_for_dysmenorrhea() -> None:
    """方剂语境证据不能让用户自己判断，应明确说明不能证明单独吃阿胶可缓解痛经。"""

    classified = PageIndexService._classify_evidence_items(
        "吃阿胶能缓解痛经",
        [
            {
                "title": "RAG/FTS 原文片段",
                "position": "section-12:chunk-55",
                "content": "温经汤临床中不仅应用于月经不调、痛经、崩漏等病证，方中阿胶既可止血，又兼止痛、补虚。",
                "source_type": "RAG/FTS 原文",
            },
            {
                "title": "RAG/FTS 原文片段",
                "position": "section-7:chunk-29",
                "content": "《伤寒杂病论》中含有阿胶的方剂有温经汤等 11 首，每方中阿胶功效并不完全相同。",
                "source_type": "RAG/FTS 原文",
            },
        ],
    )

    answer = PageIndexService._build_local_answer("吃阿胶能缓解痛经", classified)

    assert [item["evidence_type"] for item in classified] == ["partial_support", "method_or_formula_context"]
    assert "不能证明“吃阿胶能缓解痛经”" in answer
    assert "只支持" in answer
    assert "具体判断需结合下列依据" not in answer


def test_pageindex_llm_answer_should_pass_question_plan_to_final_template(tmp_path: Path) -> None:
    """列举/方法类问题应由 LLM Question Plan 决定回答策略，并传入最终模板。"""

    settings = build_pageindex_test_settings(tmp_path)

    class QuestionPlanClient:
        """测试用 LLM 客户端，验证最终回答能看到信息抽取计划。"""

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            if "Question Planner" in system_prompt:
                assert "阿胶有哪些质量检测方法" in user_prompt
                return {
                    "question_type": "information_extraction",
                    "answer_strategy": "列举证据中出现的质量检测方法。",
                    "target": "阿胶质量检测方法",
                    "claim": "",
                    "required_output": ["结论", "方法清单", "依据", "来源"],
                    "needs_evidence_relation": False,
                }
            assert "Question Plan JSON" in user_prompt
            assert "information_extraction" in user_prompt
            assert "方法清单" in user_prompt
            return {"answer": "结论：证据列出了真伪鉴别、重金属检测和微生物检测。\n\n来源：质量检测方法（line 580）。"}

    service = PageIndexService(settings, llm_client=QuestionPlanClient())
    answer = service._generate_llm_answer(
        QuestionPlanClient(),
        "阿胶有哪些质量检测方法",
        [
            {
                "title": "阿胶及其制品质量检测方法研究进展",
                "position": "line 580",
                "content": "包括真伪鉴别、重金属检测和微生物检测。",
                "source_type": "PageIndex 节点",
            }
        ],
    )

    assert "真伪鉴别" in answer
    assert "微生物检测" in answer


def test_pageindex_merge_evidence_should_keep_primary_and_rag_supplemental_items() -> None:
    """PageIndex 主证据存在时，也应保留 RAG/FTS 补充证据，避免引用不完整。"""

    merged = PageIndexService._merge_evidence(
        [
            {
                "title": "阿胶应用的注意点（禁忌）",
                "position": "line 5946",
                "source_type": "PageIndex 节点",
            }
        ],
        [
            {
                "title": "RAG/FTS 原文片段",
                "position": "section-2:chunk-0",
                "chunk_id": "chunk_heart",
                "source_type": "RAG/FTS 原文",
            }
        ],
    )

    assert [item["source_type"] for item in merged] == ["PageIndex 节点", "RAG/FTS 原文"]
    assert merged[1]["chunk_id"] == "chunk_heart"


def test_pageindex_merge_evidence_should_deduplicate_only_same_source_identity() -> None:
    """证据合并只去重同一来源身份，不能让 PageIndex 节点和 RAG 片段互相覆盖。"""

    merged = PageIndexService._merge_evidence(
        [
            {
                "title": "同一位置的 PageIndex 节点",
                "position": "section-2:chunk-0",
                "doc_uid": "doc_alpha",
                "source_type": "PageIndex 节点",
            },
            {
                "title": "重复 PageIndex 节点",
                "position": "section-2:chunk-0",
                "doc_uid": "doc_alpha",
                "source_type": "PageIndex 节点",
            },
            {
                "title": "另一文档同位置节点",
                "position": "section-2:chunk-0",
                "doc_uid": "doc_beta",
                "source_type": "PageIndex 节点",
            },
        ],
        [
            {
                "title": "RAG/FTS 原文片段",
                "position": "section-2:chunk-0",
                "chunk_id": "chunk_alpha",
                "doc_uid": "doc_alpha",
                "source_type": "RAG/FTS 原文",
            },
            {
                "title": "重复 RAG/FTS 原文片段",
                "position": "section-2:chunk-0",
                "chunk_id": "chunk_alpha",
                "doc_uid": "doc_alpha",
                "source_type": "RAG/FTS 原文",
            },
        ],
    )

    assert [(item["source_type"], item["doc_uid"], item["title"]) for item in merged] == [
        ("PageIndex 节点", "doc_alpha", "同一位置的 PageIndex 节点"),
        ("PageIndex 节点", "doc_beta", "另一文档同位置节点"),
        ("RAG/FTS 原文", "doc_alpha", "RAG/FTS 原文片段"),
    ]


def test_pageindex_rag_evidence_should_use_source_span_as_anchor_fallback(tmp_path: Path) -> None:
    """历史 chunk 缺少 source_anchor 时，应用 source_span 作为引用位置兜底。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    seed_chunk(
        settings,
        doc_uid=document["doc_uid"],
        chunk_id="chunk_legacy_heart",
        content="阿胶养血滋阴。如心脏相关病证用炙甘草汤。",
        source_span="section-9:chunk-3",
    )

    record = service._get_index_record("kb_alpha", document["doc_uid"])

    rag_items = service._search_rag_fts_evidence(
        record,
        "心脏病吃阿胶有好处",
        {"entities": ["阿胶"], "keywords": ["阿胶", "心脏病"], "expanded_terms": []},
    )

    assert rag_items[0]["source_anchor"] == "section-9:chunk-3"
    assert rag_items[0]["position"] == "section-9:chunk-3"


def test_pageindex_llm_answer_prompt_should_require_evidence_bound_format(tmp_path: Path) -> None:
    """LLM 回答提示词应要求按证据回答，并输出结论、依据、来源和不确定点。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")

    class PromptCheckingClient:
        """测试用 LLM 客户端，检查最终回答提示词是否足够约束。"""

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            if "问题分析" in system_prompt:
                return {
                    "intent": "询问证据",
                    "entities": ["风险"],
                    "keywords": ["风险"],
                    "expanded_terms": [],
                }
            if "树结构检索" in system_prompt:
                return {"selected_nodes": [{"candidate_id": "node_2", "reason": "风险节点相关"}], "answer": ""}
            if "Question Planner" in system_prompt:
                return {
                    "question_type": "claim_judgement",
                    "answer_strategy": "判断证据是否支持问题。",
                    "target": "风险 属于哪个知识库",
                    "claim": "风险属于某个知识库",
                    "required_output": ["结论", "证据判断", "依据", "来源", "不确定点"],
                    "needs_evidence_relation": True,
                }
            assert "只能基于给定证据回答" in system_prompt
            assert "证据不足" in system_prompt
            assert "claim_judgement" in user_prompt
            assert "结论" in user_prompt
            assert "依据" in user_prompt
            assert "来源" in user_prompt
            assert "不确定点" in user_prompt
            return {"answer": "结论：有相关证据。\n\n依据：风险节点说明仅属于当前知识库。\n\n来源：风险（line 5）。\n\n不确定点：未发现更多外部证据。"}

    service = PageIndexService(settings, llm_client=PromptCheckingClient())
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "风险 属于哪个知识库")

    assert "结论：" in answer["answer"]
    assert "来源：" in answer["answer"]


def test_pageindex_service_should_use_selected_answer_template_for_llm_answer(tmp_path: Path) -> None:
    """PageIndex LLM 回答应使用选中的 PageIndex 模板渲染最终回答提示词。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    settings.templates_dir.joinpath("pageindex").mkdir(parents=True, exist_ok=True)
    settings.templates_dir.joinpath("pageindex", "custom_pageindex_qa.yaml").write_text(
        """
template_id: custom_pageindex_qa
template_name: 自定义 PageIndex 问答
description: 自定义模板
answer_mode: custom
system_prompt: 自定义 PageIndex 系统提示。
user_prompt_template: |
  自定义变量检查：
  问题={question}
  证据={evidence_json}
  结构={structure_context}
  判断={evidence_judgement}
  引用={citation_rules}
""".strip(),
        encoding="utf-8",
    )

    class TemplateCheckingClient:
        """测试用 LLM 客户端，确认最终回答使用自定义 PageIndex 模板。"""

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            if "问题分析" in system_prompt:
                return {
                    "intent": "询问证据",
                    "entities": ["风险"],
                    "keywords": ["风险"],
                    "expanded_terms": [],
                }
            if "树结构检索" in system_prompt:
                return {"selected_nodes": [{"candidate_id": "node_2", "reason": "风险节点相关"}], "answer": ""}
            if "Question Planner" in system_prompt:
                return {
                    "question_type": "claim_judgement",
                    "answer_strategy": "判断证据是否支持问题。",
                    "target": "风险 属于哪个知识库",
                    "claim": "风险属于某个知识库",
                    "required_output": ["结论", "证据判断", "依据", "来源", "不确定点"],
                    "needs_evidence_relation": True,
                }
            assert system_prompt == "自定义 PageIndex 系统提示。"
            assert "自定义变量检查" in user_prompt
            assert "问题=风险 属于哪个知识库" in user_prompt
            assert "判断=" in user_prompt
            assert "引用=必须列出证据标题、位置、文档或 chunk 来源。" in user_prompt
            return {"answer": "结论：使用了自定义 PageIndex 模板。\n\n证据判断：直接支持。\n\n依据：风险节点。\n\n来源：风险。\n\n不确定点：无。"}

    service = PageIndexService(settings, llm_client=TemplateCheckingClient())
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    answer = service.ask_question("kb_alpha", document["doc_uid"], "风险 属于哪个知识库", template_id="custom_pageindex_qa")

    assert "使用了自定义 PageIndex 模板" in answer["answer"]


def test_pageindex_service_should_export_current_document_history_as_markdown(tmp_path: Path) -> None:
    """导出内容应只包含当前知识库和文档的 PageIndex 问答历史。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    service.ask_question("kb_alpha", document["doc_uid"], "风险")

    markdown_text = service.export_history_markdown("kb_alpha", document["doc_uid"])

    assert "# PageIndex 深度检索导出" in markdown_text
    assert "知识库：kb_alpha" in markdown_text
    assert "问题：风险" in markdown_text
    assert "## 风险" in markdown_text


def test_pageindex_export_should_format_dict_answer_as_markdown_sections(tmp_path: Path) -> None:
    """导出 Markdown 时应把 dict 字符串答案格式化为可读章节。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    query_id = "piq_dict_answer"
    answer_payload = {
        "结论": "该命题不准确。感冒期间应停服阿胶。",
        "证据判断": ["partial_support", "method_or_formula_context"],
        "依据": "1. 现代用药建议明确感冒期间停服阿胶。\n2. 古代复方背景不能证明单独缓解感冒。",
        "来源": [
            "标题: RAG/FTS 原文片段, 位置: section-102:chunk-160, 来源: 阿胶历史文化通典_default",
            "标题: RAG/FTS 原文片段, 位置: section-10:chunk-42, 来源: 阿胶学术论文全集_default",
        ],
        "不确定点": "存在特定体质和复方应用边界。",
    }
    with transaction(settings.sqlite_db_path) as connection:
        connection.execute(
            """
            INSERT INTO pageindex_query_history (
                query_id, knowledge_base_id, doc_uid, question, answer, evidence_json, debug_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query_id,
                "kb_alpha",
                document["doc_uid"],
                "阿胶对感冒有缓解作用吗",
                str(answer_payload),
                "[]",
                "{}",
                utc_now_iso(),
            ),
        )

    markdown_text = service.export_query_markdown("kb_alpha", document["doc_uid"], query_id)

    assert "{'结论':" not in markdown_text
    assert "#### 结论" in markdown_text
    assert "该命题不准确。感冒期间应停服阿胶。" in markdown_text
    assert "#### 证据判断" in markdown_text
    assert "- partial_support" in markdown_text
    assert "#### 来源" in markdown_text
    assert "- 标题: RAG/FTS 原文片段, 位置: section-102:chunk-160" in markdown_text


def test_pageindex_export_should_format_generic_llm_dict_without_fixed_schema(tmp_path: Path) -> None:
    """导出 Markdown 不应依赖固定中文字段，需兼容不同 LLM 的任意结构化 key。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")
    service = PageIndexService(settings)
    pageindex_doc_id = seed_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")
    query_id = "piq_generic_llm_answer"
    answer_payload = {
        "final_answer": "Current evidence does not support using Ejiao for common cold relief.",
        "reasoning": ["Modern guidance says stop Ejiao during cold symptoms.", "Formula context is not direct support."],
        "citations": [{"title": "RAG chunk", "position": "section-102:chunk-160"}],
        "confidence": "medium",
    }
    with transaction(settings.sqlite_db_path) as connection:
        connection.execute(
            """
            INSERT INTO pageindex_query_history (
                query_id, knowledge_base_id, doc_uid, question, answer, evidence_json, debug_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query_id,
                "kb_alpha",
                document["doc_uid"],
                "Does Ejiao relieve common cold?",
                json.dumps(answer_payload, ensure_ascii=False),
                "[]",
                "{}",
                utc_now_iso(),
            ),
        )

    markdown_text = service.export_query_markdown("kb_alpha", document["doc_uid"], query_id)

    assert '{"final_answer":' not in markdown_text
    assert "#### final_answer" in markdown_text
    assert "Current evidence does not support" in markdown_text
    assert "#### reasoning" in markdown_text
    assert "- Modern guidance says stop Ejiao during cold symptoms." in markdown_text
    assert "#### citations" in markdown_text
    assert "**title**：RAG chunk" in markdown_text
    assert "#### confidence" in markdown_text


def test_pageindex_history_should_persist_question_plan_debug(tmp_path: Path) -> None:
    """PageIndex 历史应保存 Question Plan，方便刷新页面后复盘回答策略。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")

    class PlanDebugClient:
        """测试用 LLM 客户端，生成可追踪的信息抽取计划。"""

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            if "问题分析" in system_prompt:
                return {
                    "intent": "询问方法",
                    "entities": ["阿胶", "质量检测"],
                    "keywords": ["阿胶", "质量检测"],
                    "expanded_terms": ["检测方法"],
                }
            if "树结构检索" in system_prompt:
                return {"selected_nodes": [{"candidate_id": "node_1", "reason": "质量检测相关"}], "answer": ""}
            if "Question Planner" in system_prompt:
                return {
                    "question_type": "information_extraction",
                    "answer_strategy": "列举质量检测方法。",
                    "target": "阿胶质量检测方法",
                    "claim": "",
                    "required_output": ["结论", "方法清单", "来源"],
                    "needs_evidence_relation": False,
                }
            return {"answer": "结论：包括真伪鉴别等方法。\n\n来源：质量检测方法。"}

    service = PageIndexService(settings, llm_client=PlanDebugClient())
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=[
            {
                "title": "阿胶及其制品质量检测方法研究进展",
                "line_num": 8,
                "level": 1,
                "summary": "真伪鉴别、重金属检测和微生物检测。",
                "text": "# 阿胶及其制品质量检测方法研究进展\n\n包括真伪鉴别、重金属检测和微生物检测。",
                "nodes": [],
            }
        ],
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    result = service.ask_question("kb_alpha", document["doc_uid"], "阿胶有哪些质量检测方法")
    history = service.list_query_history("kb_alpha", document["doc_uid"], limit=1)
    exported = service.export_query_markdown("kb_alpha", document["doc_uid"], result["query_id"])

    assert result["debug"]["question_plan"]["question_type"] == "information_extraction"
    assert history[0]["debug"]["question_plan"]["target"] == "阿胶质量检测方法"
    assert "问题类型：information_extraction" in exported


def test_pageindex_knowledge_base_question_should_use_aggregate_question_plan_answer(tmp_path: Path) -> None:
    """知识库级提问聚合多文档证据后，仍应使用 Question Plan 生成最终答案。"""

    settings = build_pageindex_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    document = seed_markdown_document(settings, knowledge_base_id="kb_alpha", file_name="alpha.md")

    class AggregatePlanClient:
        """测试用 LLM 客户端，验证知识库级最终回答不退回本地命题判断。"""

        def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
            if "问题分析" in system_prompt:
                return {
                    "intent": "询问方法",
                    "entities": ["阿胶", "质量检测"],
                    "keywords": ["阿胶", "质量检测"],
                    "expanded_terms": ["检测方法"],
                }
            if "树结构检索" in system_prompt:
                return {"selected_nodes": [{"candidate_id": "node_1", "reason": "质量检测相关"}], "answer": ""}
            if "Question Planner" in system_prompt:
                return {
                    "question_type": "information_extraction",
                    "answer_strategy": "列举质量检测方法。",
                    "target": "阿胶质量检测方法",
                    "claim": "",
                    "required_output": ["结论", "方法清单", "来源"],
                    "needs_evidence_relation": False,
                }
            assert "information_extraction" in user_prompt
            return {"answer": "结论：阿胶质量检测方法包括真伪鉴别、重金属检测和微生物检测。\n\n来源：质量检测方法。"}

    service = PageIndexService(settings, llm_client=AggregatePlanClient())
    pageindex_doc_id = seed_custom_pageindex_workspace(
        settings,
        knowledge_base_id="kb_alpha",
        doc_uid=document["doc_uid"],
        file_name="alpha.md",
        structure=[
            {
                "title": "阿胶及其制品质量检测方法研究进展",
                "line_num": 8,
                "level": 1,
                "summary": "真伪鉴别、重金属检测和微生物检测。",
                "text": "# 阿胶及其制品质量检测方法研究进展\n\n包括真伪鉴别、重金属检测和微生物检测。",
                "nodes": [],
            }
        ],
    )
    service.upsert_index_record("kb_alpha", document["doc_uid"], pageindex_doc_id, source_hash="hash_alpha")

    result = service.ask_knowledge_base_question("kb_alpha", "阿胶有哪些质量检测方法")

    assert result["debug"]["question_plan"]["question_type"] == "information_extraction"
    assert result["debug"]["document_retrieval_rounds"][0]["doc_uid"] == document["doc_uid"]
    assert result["debug"]["document_retrieval_rounds"][0]["rounds"][0]["sufficiency"] == "insufficient"
    assert "真伪鉴别" in result["answer"]
    assert "不能证明" not in result["answer"]
