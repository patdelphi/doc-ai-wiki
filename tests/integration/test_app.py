"""程序说明：验证应用最小接口闭环。"""

from __future__ import annotations

from base64 import b64encode
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from src.app import create_app
from src.auth.service import AuthService
from src.common.config import AppSettings
from src.db.connection import initialize_database
from src.db.repositories import DocumentRepository, QualityRepository
from src.ingest.service import IngestService

TEST_API_USERNAME = "api_tester"
TEST_API_PASSWORD = "ApiTester#123"


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


def build_api_auth_headers(database_path: Path) -> dict[str, str]:
    """构造受保护接口测试所需的 Basic Auth 请求头。"""

    initialize_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    auth_service = AuthService(connection)
    auth_service.register_user(TEST_API_USERNAME, TEST_API_PASSWORD)
    connection.execute(
        "UPDATE users SET is_admin = 1, is_active = 1 WHERE username = ?",
        (TEST_API_USERNAME,),
    )
    connection.commit()
    connection.close()
    credentials = b64encode(f"{TEST_API_USERNAME}:{TEST_API_PASSWORD}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {credentials}"}


def build_restricted_api_auth_headers(
    database_path: Path,
    username: str,
    password: str,
    *,
    tab_names: list[str],
    kb_ids: list[str],
) -> dict[str, str]:
    """构造受限用户认证头，并写入指定页签与知识库权限。"""

    initialize_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    auth_service = AuthService(connection)
    success, message = auth_service.register_user(username, password)
    assert success is True, message
    user_row = connection.execute(
        "SELECT user_id FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    assert user_row is not None
    success, message = auth_service.update_user_permissions(user_row[0], tab_names, kb_ids)
    assert success is True, message
    connection.close()
    credentials = b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {credentials}"}


def build_authenticated_test_client(app, database_path: Path) -> TestClient:
    """创建带默认认证头的测试客户端。"""

    return TestClient(app, headers=build_api_auth_headers(database_path))


def seed_quality_result_for_api_permission_test(
    database_path: Path,
    *,
    check_id: str,
    claim_id: str,
    knowledge_base_id: str,
) -> None:
    """写入最小质检结果，供 API 对象级权限测试复用。"""

    repository = QualityRepository(database_path)
    created_at = "2026-05-14T10:00:00+00:00"
    repository.create_quality_result(
        quality_check={
            "check_id": check_id,
            "knowledge_base_id": knowledge_base_id,
            "input_text": f"{knowledge_base_id} 质检输入",
            "template_id": "general_fact_check",
            "template_name": "通用事实核验",
            "overall_verdict": "needs_review",
            "risk_level": "medium",
            "summary": "用于 API 对象级权限测试",
            "created_at": created_at,
            "updated_at": created_at,
        },
        claims=[
            {
                "claim_id": claim_id,
                "check_id": check_id,
                "claim_text": f"{knowledge_base_id} Claim",
                "verdict": "needs_review",
                "risk_level": "medium",
                "confidence": 0.88,
                "evidence": f"{knowledge_base_id} 证据摘要",
                "evidence_details": [],
                "source_doc": "测试文档",
                "source_span": "section-1",
                "review_status": "pending",
                "created_at": created_at,
                "updated_at": created_at,
            }
        ],
        rule_hits=[],
    )


def seed_document_for_api_permission_test(
    database_path: Path,
    *,
    doc_uid: str,
    knowledge_base_id: str,
    source_path: str,
) -> None:
    """写入最小文档记录，供 doc_uid 对象级权限测试复用。"""

    repository = DocumentRepository(database_path)
    repository.upsert_document(
        {
            "doc_uid": doc_uid,
            "knowledge_base_id": knowledge_base_id,
            "doc_id": f"{doc_uid}_id",
            "doc_title": f"{knowledge_base_id} 文档",
            "source_path": source_path,
            "source_hash": f"hash_{doc_uid}",
            "ingest_status": "completed",
            "index_status": "indexed",
            "error_message": None,
        }
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


def test_app_metadata_should_expose_current_version(tmp_path: Path) -> None:
    """应用元数据应暴露当前项目版本。"""

    app = create_app(build_test_settings(tmp_path))

    assert app.title == "基于文档的知识库AI查询系统"
    assert app.version == "0.5"


def test_protected_endpoint_should_require_http_basic_auth(tmp_path: Path) -> None:
    """除健康检查外，其它接口默认应要求 HTTP Basic 认证。"""

    app = create_app(build_test_settings(tmp_path))
    with TestClient(app) as client:
        response = client.get("/knowledge-bases")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_restricted_user_should_not_access_management_endpoint(tmp_path: Path) -> None:
    """普通用户缺少知识库管理页签时，应被禁止访问管理接口。"""

    app = create_app(build_test_settings(tmp_path))
    headers = build_restricted_api_auth_headers(
        tmp_path / "app.db",
        "search_only_user",
        "SearchOnly#123",
        tab_names=["知识库检索"],
        kb_ids=["default"],
    )

    with TestClient(app, headers=headers) as client:
        response = client.get("/ingest/status")

    assert response.status_code == 403
    assert response.json()["detail"] == "无权限访问当前接口"


def test_restricted_user_should_only_list_authorized_knowledge_bases(tmp_path: Path) -> None:
    """知识库列表接口只应返回当前用户被授权的知识库。"""

    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    with build_authenticated_test_client(app, settings.sqlite_db_path) as admin_client:
        create_response = admin_client.post(
            "/knowledge-bases",
            json={
                "knowledge_base_id": "medical",
                "knowledge_base_name": "医学知识库",
                "description": "用于受限权限测试",
                "status": "active",
                "is_default": False,
            },
        )

    assert create_response.status_code == 200
    headers = build_restricted_api_auth_headers(
        settings.sqlite_db_path,
        "limited_kb_user",
        "LimitedKb#123",
        tab_names=["知识库检索"],
        kb_ids=["medical"],
    )
    with TestClient(app, headers=headers) as client:
        response = client.get("/knowledge-bases")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert [item["knowledge_base_id"] for item in payload["data"]["items"]] == ["medical"]


def test_restricted_user_should_not_access_unauthorized_knowledge_base(tmp_path: Path) -> None:
    """普通用户跨知识库检索时，应被知识库权限阻止。"""

    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    with build_authenticated_test_client(app, settings.sqlite_db_path) as admin_client:
        create_response = admin_client.post(
            "/knowledge-bases",
            json={
                "knowledge_base_id": "medical",
                "knowledge_base_name": "医学知识库",
                "description": "用于权限拦截测试",
                "status": "active",
                "is_default": False,
            },
        )

    assert create_response.status_code == 200
    headers = build_restricted_api_auth_headers(
        settings.sqlite_db_path,
        "default_only_user",
        "DefaultOnly#123",
        tab_names=["知识库检索"],
        kb_ids=["default"],
    )
    with TestClient(app, headers=headers) as client:
        response = client.get(
            "/search/fulltext",
            params={"query": "知识库", "knowledge_base_id": "medical"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "无权限访问当前知识库"


def test_restricted_user_should_not_access_unauthorized_quality_result_by_check_id(tmp_path: Path) -> None:
    """普通用户即使知道跨库 check_id，也不应读取未授权知识库的质检结果。"""

    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    with build_authenticated_test_client(app, settings.sqlite_db_path) as admin_client:
        create_response = admin_client.post(
            "/knowledge-bases",
            json={
                "knowledge_base_id": "medical",
                "knowledge_base_name": "医学知识库",
                "description": "用于对象级权限测试",
                "status": "active",
                "is_default": False,
            },
        )
    assert create_response.status_code == 200
    seed_quality_result_for_api_permission_test(
        settings.sqlite_db_path,
        check_id="chk_api_medical_only",
        claim_id="claim_api_medical_only",
        knowledge_base_id="medical",
    )
    headers = build_restricted_api_auth_headers(
        settings.sqlite_db_path,
        "quality_default_only_user",
        "QDefault#123",
        tab_names=["AI 质检"],
        kb_ids=["default"],
    )

    with TestClient(app, headers=headers) as client:
        response = client.get("/quality/result/chk_api_medical_only")

    assert response.status_code == 403
    assert response.json()["detail"] == "无权限访问当前知识库"


def test_restricted_user_should_not_submit_review_for_unauthorized_claim(tmp_path: Path) -> None:
    """普通用户即使知道跨库 claim_id，也不应提交未授权知识库的审核动作。"""

    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    with build_authenticated_test_client(app, settings.sqlite_db_path) as admin_client:
        create_response = admin_client.post(
            "/knowledge-bases",
            json={
                "knowledge_base_id": "medical",
                "knowledge_base_name": "医学知识库",
                "description": "用于对象级权限测试",
                "status": "active",
                "is_default": False,
            },
        )
    assert create_response.status_code == 200
    seed_quality_result_for_api_permission_test(
        settings.sqlite_db_path,
        check_id="chk_api_review_medical_only",
        claim_id="claim_api_review_medical_only",
        knowledge_base_id="medical",
    )
    headers = build_restricted_api_auth_headers(
        settings.sqlite_db_path,
        "review_default_only_user",
        "RDefault#123",
        tab_names=["人工审核"],
        kb_ids=["default"],
    )

    with TestClient(app, headers=headers) as client:
        response = client.post(
            "/review/submit",
            json={
                "claim_id": "claim_api_review_medical_only",
                "review_action": "approved",
                "reviewed_verdict": "needs_review",
                "review_note": "越权审核尝试",
                "reviewer": "tester",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "无权限访问当前知识库"


def test_restricted_user_should_not_query_ingest_status_by_unauthorized_doc_uid(tmp_path: Path) -> None:
    """普通用户即使不传知识库参数，也不应通过未授权 doc_uid 查看跨库文档状态。"""

    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    medical_dir = settings.input_root / "medical"
    medical_dir.mkdir(parents=True, exist_ok=True)
    medical_file = medical_dir / "medical_only.md"
    medical_file.write_text("# 医学文档\n\n用于 doc_uid 权限测试。", encoding="utf-8")
    with build_authenticated_test_client(app, settings.sqlite_db_path) as admin_client:
        create_response = admin_client.post(
            "/knowledge-bases",
            json={
                "knowledge_base_id": "medical",
                "knowledge_base_name": "医学知识库",
                "description": "用于对象级权限测试",
                "status": "active",
                "is_default": False,
            },
        )
    assert create_response.status_code == 200
    seed_document_for_api_permission_test(
        settings.sqlite_db_path,
        doc_uid="doc_api_medical_only",
        knowledge_base_id="medical",
        source_path=str(medical_file),
    )
    headers = build_restricted_api_auth_headers(
        settings.sqlite_db_path,
        "ingest_default_only_user",
        "Ingest#123",
        tab_names=["知识库管理"],
        kb_ids=["default"],
    )

    with TestClient(app, headers=headers) as client:
        response = client.get("/ingest/status", params={"doc_uid": "doc_api_medical_only"})

    assert response.status_code == 403
    assert response.json()["detail"] == "无权限访问当前知识库"


def test_restricted_user_should_not_rebuild_unauthorized_doc_uid(tmp_path: Path) -> None:
    """普通用户即使知道跨库 doc_uid，也不应发起未授权文档重建。"""

    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    medical_dir = settings.input_root / "medical"
    medical_dir.mkdir(parents=True, exist_ok=True)
    medical_file = medical_dir / "medical_rebuild.md"
    medical_file.write_text("# 医学文档\n\n用于重建权限测试。", encoding="utf-8")
    with build_authenticated_test_client(app, settings.sqlite_db_path) as admin_client:
        create_response = admin_client.post(
            "/knowledge-bases",
            json={
                "knowledge_base_id": "medical",
                "knowledge_base_name": "医学知识库",
                "description": "用于对象级权限测试",
                "status": "active",
                "is_default": False,
            },
        )
    assert create_response.status_code == 200
    seed_document_for_api_permission_test(
        settings.sqlite_db_path,
        doc_uid="doc_api_rebuild_medical_only",
        knowledge_base_id="medical",
        source_path=str(medical_file),
    )
    headers = build_restricted_api_auth_headers(
        settings.sqlite_db_path,
        "rebuild_default_only_user",
        "Rebuild#123",
        tab_names=["知识库管理"],
        kb_ids=["default"],
    )

    with TestClient(app, headers=headers) as client:
        response = client.post(
            "/ingest/rebuild",
            json={
                "doc_uids": ["doc_api_rebuild_medical_only"],
                "rebuild_fulltext": True,
                "rebuild_vector": False,
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "无权限访问当前知识库"


def test_save_knowledge_base_endpoint_should_create_input_directory(tmp_path: Path) -> None:
    """创建知识库接口应同时创建对应 Input 子目录。"""

    settings = build_test_settings(tmp_path)
    app = create_app(settings)

    with build_authenticated_test_client(app, settings.sqlite_db_path) as client:
        response = client.post(
            "/knowledge-bases",
            json={
                "knowledge_base_id": "api_created_kb",
                "knowledge_base_name": "接口创建知识库",
                "description": "验证创建接口与目录初始化",
                "status": "active",
                "is_default": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["item"]["knowledge_base_id"] == "api_created_kb"
    assert (settings.input_root / "api_created_kb").exists() is True


def test_ingest_status_endpoint_should_only_return_requested_knowledge_base_items(tmp_path: Path) -> None:
    """入库状态接口按知识库筛选时，应只返回当前知识库的数据。"""

    settings = build_test_settings(tmp_path)
    (settings.input_root / "default").mkdir(parents=True, exist_ok=True)
    app = create_app(settings)

    default_file = settings.input_root / "default" / "default_only.md"
    default_file.write_text("# 默认文档\n\n只属于默认知识库。", encoding="utf-8")

    with build_authenticated_test_client(app, settings.sqlite_db_path) as client:
        create_response = client.post(
            "/knowledge-bases",
            json={
                "knowledge_base_id": "medical",
                "knowledge_base_name": "医学知识库",
                "description": "用于状态隔离测试",
                "status": "active",
                "is_default": False,
            },
        )
        assert create_response.status_code == 200

        medical_file = settings.input_root / "medical" / "medical_only.md"
        medical_file.write_text("# 医学文档\n\n只属于 medical。", encoding="utf-8")

        register_response = client.post(
            "/ingest/register",
            json={
                "documents": [
                    {
                        "file_path": str(default_file),
                        "knowledge_base_id": "default",
                        "doc_title": "默认文档",
                    },
                    {
                        "file_path": str(medical_file),
                        "knowledge_base_id": "medical",
                        "doc_title": "医学文档",
                    },
                ],
                "rebuild_if_exists": False,
            },
        )
        default_status_response = client.get("/ingest/status", params={"knowledge_base_id": "default"})
        medical_status_response = client.get("/ingest/status", params={"knowledge_base_id": "medical"})

    assert register_response.status_code == 200
    assert register_response.json()["success"] is True

    assert default_status_response.status_code == 200
    default_items = default_status_response.json()["data"]["items"]
    assert len(default_items) == 1
    assert default_items[0]["knowledge_base_id"] == "default"
    assert default_items[0]["doc_title"] == "默认文档"

    assert medical_status_response.status_code == 200
    medical_items = medical_status_response.json()["data"]["items"]
    assert len(medical_items) == 1
    assert medical_items[0]["knowledge_base_id"] == "medical"
    assert medical_items[0]["doc_title"] == "医学文档"


def test_gradio_startup_scripts_should_only_launch_ui_entry() -> None:
    """Gradio 启动脚本应仅调用 UI 启动入口。"""

    script_paths = [
        Path("start_gradio_local_7860.ps1"),
        Path("start_gradio_server_80.ps1"),
        Path("start_gradio_local_7860.sh"),
        Path("start_gradio_server_80.sh"),
    ]

    for script_path in script_paths:
        assert script_path.exists() is True
        script_content = script_path.read_text(encoding="utf-8")
        assert "src.ui.app" in script_content
        assert "src.app" not in script_content


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
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
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
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
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
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
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
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
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


def test_search_endpoints_should_allow_default_10_and_max_100(tmp_path: Path) -> None:
    """检索接口默认返回数量应为 10，最大允许 100。"""

    app = create_app(build_test_settings(tmp_path))
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
        default_response = client.get("/search/hybrid", params={"query": "阿胶"})
        max_response = client.get("/search/hybrid", params={"query": "阿胶", "top_k": 100})
        overflow_response = client.get("/search/hybrid", params={"query": "阿胶", "top_k": 101})

    assert default_response.status_code == 200
    assert max_response.status_code == 200
    assert overflow_response.status_code == 422


def test_register_invalid_json_document_should_return_validation_error(tmp_path: Path) -> None:
    """非法 JSON 输入应返回可识别的校验错误。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    sample_file = input_root / "invalid.json"
    sample_file.write_text('{"title":"坏文档","content":', encoding="utf-8")

    app = create_app(build_test_settings(tmp_path))
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
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

    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    with build_authenticated_test_client(app, settings.sqlite_db_path) as client:
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
    assert quality_payload["data"]["claims"][0]["verdict"] in {"needs_review", "rejected"}
    assert quality_payload["data"]["check"]["risk_level"] in {"medium", "high"}
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
    assert persisted_claims[0]["risk_level"] in {"medium", "high"}
    assert quality_payload["data"]["claims"][0]["evidence_details"]


def test_ingest_service_should_return_database_summary(tmp_path: Path) -> None:
    """数据库状态统计应反映入库、分块、质检与审核数量。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    sample_file = input_root / "sample_doc.MD"
    sample_file.write_text(
        "# 测试文档\n\n中文知识库系统支持 Markdown 文档入库、全文检索和 AI 质检。",
        encoding="utf-8",
    )

    settings = build_test_settings(tmp_path)
    app = create_app(settings)
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
        register_response = client.post(
            "/ingest/register",
            json={
                "documents": [{"file_path": str(sample_file), "doc_title": "测试文档"}],
                "rebuild_if_exists": False,
            },
        )
        quality_response = client.post(
            "/quality/check",
            json={"input_text": "中文知识库系统一定支持全文检索和 AI 质检。"},
        )
        claim_id = quality_response.json()["data"]["claims"][0]["claim_id"]
        client.post(
            "/review/submit",
            json={
                "claim_id": claim_id,
                "review_action": "approved",
                "reviewed_verdict": "needs_review",
                "review_note": "测试通过",
                "reviewer": "tester",
            },
        )

    summary = IngestService(settings).get_database_summary()

    assert register_response.status_code == 200
    assert summary["document_count"] == 1
    assert summary["completed_document_count"] == 1
    assert summary["indexed_document_count"] == 1
    assert summary["chunk_count"] >= 1
    assert summary["section_count"] >= 1
    assert summary["quality_check_count"] == 1
    assert summary["claim_count"] >= 1
    assert summary["review_count"] == 1


def test_register_document_should_only_mark_indexed_after_vector_success(tmp_path: Path) -> None:
    """向量写入成功后才应标记 indexed。"""

    from src.ingest.service import IngestService

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    sample_file = input_root / "sample_doc.MD"
    sample_file.write_text("# 测试文档\n\n这是一篇用于索引状态测试的文档。", encoding="utf-8")

    settings = build_test_settings(tmp_path)
    initialize_database(settings.sqlite_db_path)
    service = IngestService(settings)
    service.vector_store.upsert_chunks = lambda items, **kwargs: None  # type: ignore[method-assign]

    result = service.register_document({"file_path": str(sample_file)})
    items, _ = service.list_status(doc_uid=None, status=None, page=1, page_size=10)

    assert result["status"] == "completed"
    assert result["progress_events"][-1]["percent"] == 100
    assert items[0]["index_status"] == "indexed"


def test_quality_check_should_limit_evidence_with_doc_uid(tmp_path: Path) -> None:
    """指定 doc_uid 时，质检检索应限制在目标文档范围内。"""

    input_root = tmp_path / "Input"
    input_root.mkdir(parents=True, exist_ok=True)
    doc_a = input_root / "doc_a.MD"
    doc_b = input_root / "doc_b.MD"
    doc_a.write_text("# 文档A\n\n这里只讨论甲主题。", encoding="utf-8")
    doc_b.write_text("# 文档B\n\n乙方结论只存在于这个文档。", encoding="utf-8")

    app = create_app(build_test_settings(tmp_path))
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
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
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
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
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
        response = client.post(
            "/quality/check",
            json={"input_text": "测试内容", "template_id": "not_exists"},
        )

    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "NOT_FOUND"


def test_initialize_database_should_add_missing_quality_claim_columns(tmp_path: Path) -> None:
    """旧版 quality_claims 表初始化后应自动补齐新增字段。"""

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
    assert "evidence_details_json" in columns


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
    with build_authenticated_test_client(app, tmp_path / "app.db") as client:
        register_response = client.post(
            "/ingest/register",
            json={"documents": [{"file_path": str(sample_file), "doc_title": "重建文档"}]},
        )
        doc_uid = register_response.json()["data"]["jobs"][0]["doc_uid"]
        connection = sqlite3.connect(tmp_path / "app.db")
        source_path_row = connection.execute(
            "SELECT source_path FROM documents WHERE doc_uid = ?",
            (doc_uid,),
        ).fetchone()
        connection.close()
        assert source_path_row is not None
        registered_source_path = Path(str(source_path_row[0]))

        registered_source_path.write_text(
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
