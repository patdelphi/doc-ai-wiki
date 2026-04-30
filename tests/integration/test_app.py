"""程序说明：验证应用最小接口闭环。"""

from __future__ import annotations

from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from src.app import create_app
from src.common.config import AppSettings


def build_test_settings(tmp_path: Path) -> AppSettings:
    """构造测试专用配置。"""

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "base_rules.yaml").write_text(
        """
- code: R001
  name: 绝对化表述
  keywords:
    - 绝对
    - 一定
  hit_level: warn
  message: 包含绝对化表述，建议人工复核
""".strip(),
        encoding="utf-8",
    )

    return AppSettings(
        APP_ENV="test",
        INPUT_ROOT=tmp_path / "Input",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=rules_dir,
        TEMPLATES_DIR=tmp_path / "templates",
    )


def test_health_endpoint_should_return_ok(tmp_path: Path) -> None:
    """健康检查接口应返回正常状态。"""

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "healthy"


def test_register_document_and_query_status_should_work(tmp_path: Path) -> None:
    """文档注册后应可查询状态。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    sample_file = input_root / "sample_doc.MD"
    sample_file.write_text(
        "# 测试文档\n\n中文知识库系统支持 Markdown 文档入库与检索。",
        encoding="utf-8",
    )

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        register_response = client.post(
            "/ingest/register",
            json={
                "documents": [
                    {
                        "file_path": str(sample_file),
                        "doc_title": "测试文档",
                        "edition": "v1",
                    }
                ],
                "rebuild_if_exists": False,
            },
        )
        status_response = client.get("/ingest/status")

    assert register_response.status_code == 200
    register_payload = register_response.json()
    assert register_payload["success"] is True
    assert register_payload["data"]["jobs"][0]["status"] == "completed"

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["success"] is True
    assert status_payload["data"]["items"]
    assert status_payload["data"]["items"][0]["doc_title"] == "测试文档"

    connection = sqlite3.connect(tmp_path / "app.db")
    section_rows = connection.execute("SELECT section_title FROM document_sections ORDER BY section_level, section_title").fetchall()
    chunk_rows = connection.execute("SELECT section_id FROM chunks").fetchall()
    connection.close()

    assert len(section_rows) >= 1
    assert all(row[0] for row in section_rows)
    assert all(row[0] is not None for row in chunk_rows)


def test_vector_and_hybrid_search_should_return_results_after_ingest(tmp_path: Path) -> None:
    """完成文档入库后，向量检索与混合检索应可返回结果。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    sample_file = input_root / "sample_doc.MD"
    sample_file.write_text(
        "# 检索测试文档\n\n中文知识库系统支持全文检索、向量检索和混合检索。",
        encoding="utf-8",
    )

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        client.post(
            "/ingest/register",
            json={
                "documents": [{"file_path": str(sample_file), "doc_title": "检索测试文档"}],
                "rebuild_if_exists": False,
            },
        )
        vector_response = client.get(
            "/search/vector",
            params={"query": "向量检索", "top_k": 3},
        )
        hybrid_response = client.get(
            "/search/hybrid",
            params={"query": "混合检索", "top_k": 3},
        )

    assert vector_response.status_code == 200
    vector_payload = vector_response.json()
    assert vector_payload["success"] is True
    assert vector_payload["data"]["items"]
    assert vector_payload["data"]["items"][0]["doc_title"] == "检索测试文档"
    assert vector_payload["data"]["items"][0]["retrieval_source"] == "vector"

    assert hybrid_response.status_code == 200
    hybrid_payload = hybrid_response.json()
    assert hybrid_payload["success"] is True
    assert hybrid_payload["data"]["items"]
    assert hybrid_payload["data"]["items"][0]["doc_title"] == "检索测试文档"
    assert hybrid_payload["data"]["items"][0]["retrieval_source"] in {"fulltext", "vector", "hybrid"}


def test_register_json_document_should_work(tmp_path: Path) -> None:
    """JSON 输入文件应能完成最小入库。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    sample_file = input_root / "sample_doc.json"
    sample_file.write_text(
        '{"title":"JSON测试文档","content":"这是一个 JSON 知识条目，支持检索。","edition":"v1"}',
        encoding="utf-8",
    )

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        register_response = client.post(
            "/ingest/register",
            json={
                "documents": [{"file_path": str(sample_file)}],
                "rebuild_if_exists": False,
            },
        )
        search_response = client.get("/search/fulltext", params={"query": "JSON", "top_k": 3})

    assert register_response.status_code == 200
    assert register_response.json()["data"]["jobs"][0]["status"] == "completed"
    assert search_response.status_code == 200
    assert search_response.json()["data"]["items"]
    assert search_response.json()["data"]["items"][0]["doc_title"] == "JSON测试文档"
    assert search_response.json()["data"]["items"][0]["retrieval_source"] == "fulltext"


def test_register_json_document_should_expose_extended_metadata_in_status_and_search(tmp_path: Path) -> None:
    """JSON 输入的扩展元数据应能在状态接口和检索结果中返回。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    sample_file = input_root / "rich_doc.json"
    sample_file.write_text(
        (
            '{"title":"扩展元数据文档","content":"支持更多 JSON 元数据。",'
            '"edition":"增补版","author":"张三","source":"古籍整理库","tags":["古文","医学"]}'
        ),
        encoding="utf-8",
    )

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        register_response = client.post(
            "/ingest/register",
            json={
                "documents": [{"file_path": str(sample_file)}],
                "rebuild_if_exists": False,
            },
        )
        status_response = client.get("/ingest/status")
        search_response = client.get("/search/hybrid", params={"query": "更多", "top_k": 3})

    assert register_response.status_code == 200
    assert status_response.status_code == 200
    item = status_response.json()["data"]["items"][0]
    assert item["doc_title"] == "扩展元数据文档"
    assert item["edition"] == "增补版"
    assert item["author"] == "张三"
    assert item["source_name"] == "古籍整理库"
    assert item["tags"] == ["古文", "医学"]
    assert search_response.status_code == 200
    search_item = search_response.json()["data"]["items"][0]
    assert search_item["doc_title"] == "扩展元数据文档"
    assert search_item["author"] == "张三"
    assert search_item["source_name"] == "古籍整理库"
    assert search_item["tags"] == ["古文", "医学"]


def test_register_invalid_json_document_should_return_validation_error(tmp_path: Path) -> None:
    """非法 JSON 输入应返回可识别的校验错误。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    sample_file = input_root / "invalid.json"
    sample_file.write_text('{"title":"坏文档","content":', encoding="utf-8")

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/ingest/register",
            json={
                "documents": [{"file_path": str(sample_file)}],
                "rebuild_if_exists": False,
            },
        )

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "VALIDATION_ERROR"


def test_initialize_database_should_add_missing_document_metadata_columns(tmp_path: Path) -> None:
    """旧版 documents 表初始化后应自动补齐新增元数据列。"""

    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE documents (
            doc_uid TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            doc_title TEXT NOT NULL,
            edition TEXT,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            ingest_status TEXT NOT NULL,
            index_status TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()

    app = create_app(
        AppSettings(
            APP_ENV="test",
            INPUT_ROOT=tmp_path / "Input",
            SQLITE_DB_PATH=database_path,
            CHROMA_PERSIST_DIR=tmp_path / "chroma",
            RULES_DIR=tmp_path / "rules",
            TEMPLATES_DIR=tmp_path / "templates",
        )
    )
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    connection = sqlite3.connect(database_path)
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(documents)").fetchall()
    }
    connection.close()
    assert {"author", "source_name", "tags_json"}.issubset(columns)


def test_quality_and_review_flow_should_persist_result(tmp_path: Path) -> None:
    """质检和审核主链路应可完成最小持久化。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    sample_file = input_root / "sample_doc.MD"
    sample_file.write_text(
        "# 测试文档\n\n中文知识库系统支持 Markdown 文档入库、全文检索和 AI 质检。",
        encoding="utf-8",
    )

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        client.post(
            "/ingest/register",
            json={
                "documents": [{"file_path": str(sample_file), "doc_title": "测试文档"}],
                "rebuild_if_exists": False,
            },
        )
        quality_response = client.post(
            "/quality/check",
            json={
                "input_text": "中文知识库系统一定支持全文检索和 AI 质检。",
                "template_id": "strict_evidence_check",
            },
        )
        templates_response = client.get("/quality/templates")

        quality_payload = quality_response.json()
        first_claim = quality_payload["data"]["claims"][0]

        review_response = client.post(
            "/review/submit",
            json={
                "claim_id": first_claim["claim_id"],
                "review_action": "approved",
                "reviewed_verdict": first_claim["verdict"],
                "review_note": "测试通过",
                "reviewer": "tester",
            },
        )
        review_list_response = client.get("/review/list")
        quality_result_response = client.get(f"/quality/result/{quality_payload['data']['check']['check_id']}")

    assert quality_response.status_code == 200
    assert quality_payload["success"] is True
    assert quality_payload["data"]["claims"]
    assert quality_payload["data"]["rule_hits"]
    assert quality_payload["data"]["check"]["template_id"] == "strict_evidence_check"
    assert quality_payload["data"]["check"]["template_name"] == "严格证据核验"
    assert quality_payload["data"]["claims"][0]["verdict"] == "needs_review"
    assert quality_payload["data"]["check"]["risk_level"] == "medium"
    assert templates_response.status_code == 200
    strict_template = next(
        item
        for item in templates_response.json()["data"]["items"]
        if item["template_id"] == "strict_evidence_check"
    )
    assert strict_template["rule_tags"] == ["general", "strict"]
    assert strict_template["retrieval_policy"]["neighbor_window"] == 1
    assert strict_template["retrieval_policy"]["use_rerank"] is True

    assert review_response.status_code == 200
    assert review_response.json()["success"] is True

    assert review_list_response.status_code == 200
    review_item = review_list_response.json()["data"]["items"][0]
    assert review_item["claim_text"]
    assert review_item["template_name"] == "严格证据核验"
    assert review_item["review_status"] == "approved"

    persisted_claims = quality_result_response.json()["data"]["claims"]
    assert persisted_claims[0]["review_status"] == "approved"
    assert persisted_claims[0]["risk_level"] == "medium"
    assert quality_payload["data"]["claims"][0]["evidence_details"]


def test_quality_check_should_limit_evidence_with_doc_uid(tmp_path: Path) -> None:
    """指定 doc_uid 时，质检检索应限制在目标文档范围内。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    doc_a = input_root / "doc_a.MD"
    doc_b = input_root / "doc_b.MD"
    doc_a.write_text("# 文档A\n\n这里只讨论甲主题。", encoding="utf-8")
    doc_b.write_text("# 文档B\n\n乙方结论只存在于这个文档。", encoding="utf-8")

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        register_response = client.post(
            "/ingest/register",
            json={
                "documents": [
                    {"file_path": str(doc_a), "doc_title": "文档A"},
                    {"file_path": str(doc_b), "doc_title": "文档B"},
                ],
                "rebuild_if_exists": False,
            },
        )
        doc_uid = register_response.json()["data"]["jobs"][0]["doc_uid"]
        quality_response = client.post(
            "/quality/check",
            json={"input_text": "乙方结论只存在于这个文档。", "doc_uid": doc_uid},
        )

    assert quality_response.status_code == 200
    claim = quality_response.json()["data"]["claims"][0]
    assert claim["source_doc"] == doc_uid
    assert claim["source_doc"] != register_response.json()["data"]["jobs"][1]["doc_uid"]


def test_quality_check_should_reject_input_longer_than_2000_characters(tmp_path: Path) -> None:
    """质检输入超过 2000 字时应返回校验错误。"""

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/quality/check",
            json={"input_text": "甲" * 2001},
        )

    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "VALIDATION_ERROR"


def test_quality_check_should_return_not_found_for_unknown_template(tmp_path: Path) -> None:
    """不存在的质检模板应返回明确错误。"""

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/quality/check",
            json={"input_text": "测试内容", "template_id": "not_exists"},
        )

    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "NOT_FOUND"


def test_initialize_database_should_add_missing_quality_claim_risk_level_column(tmp_path: Path) -> None:
    """旧版 quality_claims 表初始化后应自动补齐 risk_level 列。"""

    database_path = tmp_path / "legacy_quality.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE quality_claims (
            claim_id TEXT PRIMARY KEY,
            check_id TEXT NOT NULL,
            claim_text TEXT NOT NULL,
            verdict TEXT NOT NULL,
            confidence REAL NOT NULL,
            evidence TEXT NOT NULL,
            source_doc TEXT,
            source_span TEXT,
            review_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()

    app = create_app(
        AppSettings(
            APP_ENV="test",
            INPUT_ROOT=tmp_path / "Input",
            SQLITE_DB_PATH=database_path,
            CHROMA_PERSIST_DIR=tmp_path / "chroma",
            RULES_DIR=tmp_path / "rules",
            TEMPLATES_DIR=tmp_path / "templates",
        )
    )
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    connection = sqlite3.connect(database_path)
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(quality_claims)").fetchall()
    }
    connection.close()
    assert "risk_level" in columns


def test_initialize_database_should_add_missing_quality_check_template_columns(tmp_path: Path) -> None:
    """旧版 quality_checks 表初始化后应自动补齐模板列。"""

    database_path = tmp_path / "legacy_quality_check.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE quality_checks (
            check_id TEXT PRIMARY KEY,
            input_text TEXT NOT NULL,
            overall_verdict TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            summary TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()

    app = create_app(
        AppSettings(
            APP_ENV="test",
            INPUT_ROOT=tmp_path / "Input",
            SQLITE_DB_PATH=database_path,
            CHROMA_PERSIST_DIR=tmp_path / "chroma",
            RULES_DIR=tmp_path / "rules",
            TEMPLATES_DIR=tmp_path / "templates",
        )
    )
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    connection = sqlite3.connect(database_path)
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(quality_checks)").fetchall()
    }
    connection.close()
    assert {"template_id", "template_name"}.issubset(columns)


def test_rebuild_should_support_fulltext_and_vector_separately(tmp_path: Path) -> None:
    """重建应支持全文索引和向量索引分开执行。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    sample_file = input_root / "rebuild_doc.MD"
    sample_file.write_text(
        "# 重建文档\n\n原始关键词甲。",
        encoding="utf-8",
    )

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        register_response = client.post(
            "/ingest/register",
            json={"documents": [{"file_path": str(sample_file), "doc_title": "重建文档"}]},
        )
        doc_uid = register_response.json()["data"]["jobs"][0]["doc_uid"]

        sample_file.write_text(
            "# 重建文档\n\n更新后的关键词乙。",
            encoding="utf-8",
        )

        rebuild_fulltext_response = client.post(
            "/ingest/rebuild",
            json={
                "doc_uids": [doc_uid],
                "rebuild_fulltext": True,
                "rebuild_vector": False,
            },
        )
        fulltext_response = client.get("/search/fulltext", params={"query": "关键词乙", "top_k": 3})
        vector_response = client.get("/search/vector", params={"query": "关键词乙", "top_k": 3})
        rebuild_vector_response = client.post(
            "/ingest/rebuild",
            json={
                "doc_uids": [doc_uid],
                "rebuild_fulltext": False,
                "rebuild_vector": True,
            },
        )
        vector_response_after = client.get("/search/vector", params={"query": "关键词乙", "top_k": 3})

    assert rebuild_fulltext_response.status_code == 200
    assert rebuild_fulltext_response.json()["data"]["accepted"] == [doc_uid]
    assert fulltext_response.status_code == 200
    assert fulltext_response.json()["data"]["items"]
    assert vector_response.status_code == 200
    assert all("关键词乙" not in item["content"] for item in vector_response.json()["data"]["items"])
    assert rebuild_vector_response.status_code == 200
    assert rebuild_vector_response.json()["data"]["accepted"] == [doc_uid]
    assert vector_response_after.status_code == 200
    assert vector_response_after.json()["data"]["items"]
    assert any("关键词乙" in item["content"] for item in vector_response_after.json()["data"]["items"])
