"""程序说明：验证 PageIndex 本地集成服务的知识库隔离与 LLM 配置保护。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.config import AppSettings
from src.common.errors import ValidationAppError
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
            assert "candidate_id" in user_prompt
            assert "皮肤有帮助" in user_prompt
            assert "滋养阴血" in user_prompt
            return {
                "selected_nodes": [{"candidate_id": "node_2", "reason": "语义上对应皮肤状态改善"}],
                "answer": "相关内容位于“功效”，证据提到滋养、润泽与皮肤状态改善。",
            }

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
    assert len(llm_client.prompts) == 3


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
    assert "未在 PageIndex 文档结构中找到" in answer["answer"]
    assert answer["debug"]["selected_nodes"] == []


def test_pageindex_rag_query_terms_should_ignore_generic_treatment_when_specific_term_exists() -> None:
    """RAG/FTS 补证据不能用“治疗”这类泛词驱动，否则容易返回相似治疗流程噪音。"""

    terms = ["阿胶", "治疗", "不孕不育"]

    query_terms = PageIndexService._build_rag_query_terms(terms, "阿胶能不能治疗不孕不育")

    assert query_terms == ["不孕不育"]


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
            assert "只能基于给定证据回答" in system_prompt
            assert "证据不足" in system_prompt
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
