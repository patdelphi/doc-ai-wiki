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

    assert hybrid_response.status_code == 200
    hybrid_payload = hybrid_response.json()
    assert hybrid_payload["success"] is True
    assert hybrid_payload["data"]["items"]


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
            json={"input_text": "中文知识库系统一定支持全文检索和 AI 质检。"},
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
    assert quality_payload["data"]["rule_hits"]

    assert review_response.status_code == 200
    assert review_response.json()["success"] is True

    assert review_list_response.status_code == 200
    assert review_list_response.json()["data"]["items"]

    assert quality_result_response.status_code == 200
    persisted_claims = quality_result_response.json()["data"]["claims"]
    assert persisted_claims[0]["review_status"] == "approved"


def test_rebuild_should_refresh_indexes_after_source_changed(tmp_path: Path) -> None:
    """修改源文档后，rebuild 应刷新全文与向量检索结果。"""

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

        rebuild_response = client.post(
            "/ingest/rebuild",
            json={
                "doc_uids": [doc_uid],
                "rebuild_fulltext": True,
                "rebuild_vector": True,
            },
        )
        fulltext_response = client.get("/search/fulltext", params={"query": "关键词乙", "top_k": 3})
        vector_response = client.get("/search/vector", params={"query": "关键词乙", "top_k": 3})

    assert rebuild_response.status_code == 200
    assert rebuild_response.json()["data"]["accepted"] == [doc_uid]
    assert fulltext_response.status_code == 200
    assert fulltext_response.json()["data"]["items"]
    assert vector_response.status_code == 200
    assert vector_response.json()["data"]["items"]
