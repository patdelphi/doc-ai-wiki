"""程序说明：验证应用最小接口闭环。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.app import create_app
from src.common.config import AppSettings


def build_test_settings(tmp_path: Path) -> AppSettings:
    """构造测试专用配置。"""

    return AppSettings(
        APP_ENV="test",
        DOCS_ROOT=tmp_path / "docs",
        SQLITE_DB_PATH=tmp_path / "app.db",
        CHROMA_PERSIST_DIR=tmp_path / "chroma",
        RULES_DIR=tmp_path / "rules",
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

    docs_root = tmp_path / "docs"
    docs_root.mkdir(parents=True, exist_ok=True)
    sample_file = docs_root / "sample_doc.MD"
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


def test_quality_and_review_flow_should_persist_result(tmp_path: Path) -> None:
    """质检和审核主链路应可完成最小持久化。"""

    docs_root = tmp_path / "docs"
    docs_root.mkdir(parents=True, exist_ok=True)
    sample_file = docs_root / "sample_doc.MD"
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
            json={"input_text": "中文知识库系统支持全文检索和 AI 质检。"},
        )

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

    assert review_response.status_code == 200
    assert review_response.json()["success"] is True

    assert review_list_response.status_code == 200
    assert review_list_response.json()["data"]["items"]

    assert quality_result_response.status_code == 200
    persisted_claims = quality_result_response.json()["data"]["claims"]
    assert persisted_claims[0]["review_status"] == "approved"
