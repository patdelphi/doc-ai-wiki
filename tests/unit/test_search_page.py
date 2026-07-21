"""程序说明：直接验证知识库检索页处理器，不依赖完整 Gradio 应用装配。"""

from __future__ import annotations

import gradio as gr

from src.common.errors import ValidationAppError
from src.ui.search_page import (
    build_search_detail_payload,
    change_search_page,
    export_search_results,
    reset_search_workspace_ui,
    run_search,
    run_search_ui,
    select_search_result,
)


class StubRetrievalService:
    """提供可控检索结果和详情的服务桩。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    def hybrid_search(self, query: str, **kwargs) -> list[dict]:
        self.calls.append({"query": query, **kwargs})
        if self.fail:
            raise ValidationAppError("检索参数错误")
        return [
            {
                "chunk_id": "chunk_1",
                "doc_uid": "doc_1",
                "doc_title": "测试文档",
                "source_span": "第一章",
                "retrieval_source": "fulltext",
                "matched_sources": ["fulltext"],
                "content": "阿胶测试内容",
            }
        ]

    def get_chunk_detail(self, chunk_id: str) -> dict | None:
        if not chunk_id:
            return None
        return {"chunk_id": chunk_id, "chunk_index": 1, "content": "阿胶完整原文"}


def allow_search(_session: dict[str, object] | None, _tab_name: str) -> bool:
    """测试用菜单放行回调。"""

    return True


def resolve_default(_choice: str | None, _session: dict[str, object] | None) -> str:
    """测试用知识库解析回调。"""

    return "default"


def test_run_search_should_reject_empty_query() -> None:
    """空查询应在调用检索服务前返回稳定提示。"""

    service = StubRetrievalService()
    outputs = run_search(
        "",
        10,
        "default",
        {},
        retrieval_service=service,
        has_tab_access=allow_search,
        resolve_authorized_knowledge_base=resolve_default,
    )

    assert "请输入关键词" in outputs[0]
    assert outputs[2] == []
    assert service.calls == []


def test_run_search_should_reject_missing_permission() -> None:
    """无菜单权限时不得调用检索服务。"""

    service = StubRetrievalService()
    outputs = run_search(
        "阿胶",
        10,
        "default",
        {"is_admin": False},
        retrieval_service=service,
        has_tab_access=lambda _session, _tab: False,
        resolve_authorized_knowledge_base=resolve_default,
    )

    assert "没有知识库检索权限" in outputs[0]
    assert service.calls == []


def test_run_search_should_reject_missing_knowledge_base() -> None:
    """无授权知识库时不得调用检索服务。"""

    service = StubRetrievalService()
    outputs = run_search(
        "阿胶",
        10,
        None,
        {"is_admin": False},
        retrieval_service=service,
        has_tab_access=allow_search,
        resolve_authorized_knowledge_base=lambda _choice, _session: None,
    )

    assert "没有可用知识库" in outputs[0]
    assert service.calls == []


def test_run_search_should_return_first_result_detail() -> None:
    """正常检索应返回结果、规范化查询和首条完整详情。"""

    service = StubRetrievalService()
    outputs = run_search(
        " 阿胶，测试 ",
        5,
        "default",
        {"is_admin": True},
        retrieval_service=service,
        has_tab_access=allow_search,
        resolve_authorized_knowledge_base=resolve_default,
    )

    assert outputs[2][0]["chunk_id"] == "chunk_1"
    assert outputs[3] == "阿胶 测试"
    assert outputs[5]["chunk_index"] == 1
    assert service.calls == [
        {
            "query": "阿胶 测试",
            "top_k": 5,
            "knowledge_base_id": "default",
            "use_rerank": True,
        }
    ]


def test_run_search_should_render_app_error() -> None:
    """检索业务异常应转换为稳定页面错误。"""

    outputs = run_search(
        "阿胶",
        5,
        "default",
        {"is_admin": True},
        retrieval_service=StubRetrievalService(fail=True),
        has_tab_access=allow_search,
        resolve_authorized_knowledge_base=resolve_default,
    )

    assert "检索参数错误" in outputs[0]
    assert "VALIDATION_ERROR" in outputs[0]
    assert outputs[2] == []


def test_run_search_ui_should_reject_missing_session() -> None:
    """缺少登录态时应使用零权限会话并拒绝检索。"""

    outputs = run_search_ui(
        "阿胶",
        10,
        "default",
        None,
        retrieval_service=StubRetrievalService(),
        has_tab_access=lambda session, _tab: bool((session or {}).get("is_admin")),
        resolve_authorized_knowledge_base=resolve_default,
    )

    assert "没有知识库检索权限" in outputs[0]
    assert outputs[2] == []
    assert outputs[6] == 1


def test_reset_and_change_page_should_keep_stable_outputs() -> None:
    """重置和分页应保持现有输出结构。"""

    reset_outputs = reset_search_workspace_ui("default")
    assert reset_outputs[2] == []
    assert reset_outputs[6] == 1

    rows = [
        {
            "chunk_id": f"chunk_{index}",
            "doc_title": f"文档 {index}",
            "content_preview": f"内容 {index}",
        }
        for index in range(25)
    ]
    page_rows, page, page_info = change_search_page(rows, 1, "next")
    assert page == 2
    assert len(page_rows) == 10
    assert "第 2 / 3 页" in page_info


def test_select_search_result_should_load_detail() -> None:
    """点击表格行应定位原始结果并读取完整详情。"""

    service = StubRetrievalService()
    search_rows = [
        {
            "chunk_id": "chunk_1",
            "doc_title": "测试文档",
            "content_preview": "阿胶测试内容",
        }
    ]
    current_page_rows = [["1", "测试文档", "-", "fulltext", "fulltext", "阿胶测试内容"]]
    event = gr.SelectData(None, {"index": [0, 0], "value": "1"})

    detail_html, returned_rows, selected = select_search_result(
        current_page_rows,
        search_rows,
        "阿胶",
        event,
        retrieval_service=service,
    )

    assert "完整原文" in detail_html
    assert "<mark>阿胶</mark>" in detail_html
    assert returned_rows == current_page_rows
    assert selected["chunk_index"] == 1


def test_export_search_results_should_pass_markdown_to_export_callback() -> None:
    """导出处理器应传递稳定模块名、结果名和关联片段。"""

    calls: list[dict] = []

    def fake_export(module_name: str, result_name: str, markdown_text: str, *, linked_id: str | None = None) -> str:
        calls.append(
            {
                "module_name": module_name,
                "result_name": result_name,
                "markdown_text": markdown_text,
                "linked_id": linked_id,
            }
        )
        return "导出成功"

    rows = [{"chunk_id": "chunk_1", "doc_title": "测试文档", "content": "阿胶内容"}]
    result = export_search_results(rows, rows[0], "阿胶", export_markdown_result=fake_export)

    assert result == "导出成功"
    assert calls[0]["module_name"] == "文档检索"
    assert calls[0]["result_name"] == "检索结果"
    assert calls[0]["linked_id"] == "chunk_1"
    assert "阿胶" in calls[0]["markdown_text"]


def test_build_search_detail_payload_should_merge_sqlite_detail() -> None:
    """详情应以服务返回的完整追溯字段覆盖列表摘要。"""

    payload = build_search_detail_payload(
        {"chunk_id": "chunk_1", "content": "摘要"},
        retrieval_service=StubRetrievalService(),
    )

    assert payload is not None
    assert payload["content"] == "阿胶完整原文"
    assert payload["chunk_index"] == 1
