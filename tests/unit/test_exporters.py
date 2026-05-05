"""程序说明：验证结果导出工具能生成服务端文件、下载链接与 Markdown 预览页。"""

from pathlib import Path

import pytest

from src.common.errors import ValidationAppError
from src.ui.exporters import build_download_url, build_markdown_preview_html, save_markdown_export


def test_save_markdown_export_should_write_txt_to_docs(tmp_path: Path) -> None:
    """导出结果应写入 Docs 目录，并同时生成 TXT 与 HTML 预览文件。"""

    db_path = tmp_path / "app.db"
    db_path.write_text("", encoding="utf-8")

    export_result = save_markdown_export(
        db_path,
        module_name="文档检索",
        result_name="检索结果",
        linked_id="claim_demo_001",
        markdown_text="### 检索结果\n- 命中条数：2",
    )

    exported_file = Path(export_result["file_path"])
    preview_file = Path(export_result["preview_file_path"])
    assert exported_file.exists()
    assert preview_file.exists()
    assert exported_file.suffix == ".txt"
    assert preview_file.suffix == ".html"
    assert exported_file.parent == tmp_path / "Docs"
    assert exported_file.read_text(encoding="utf-8") == "### 检索结果\n- 命中条数：2"
    preview_html = preview_file.read_text(encoding="utf-8")
    assert "<h3>检索结果</h3>" in preview_html
    assert "<li>命中条数：2</li>" in preview_html
    assert export_result["file_name"].endswith(".txt")
    assert export_result["preview_file_name"].endswith(".preview.html")
    assert "claim_demo_001" in export_result["file_name"]


def test_save_markdown_export_should_reject_empty_markdown(tmp_path: Path) -> None:
    """空内容不应导出为结果文件。"""

    db_path = tmp_path / "app.db"
    db_path.write_text("", encoding="utf-8")

    with pytest.raises(ValidationAppError):
        save_markdown_export(
            db_path,
            module_name="AI质检",
            result_name="结果",
            markdown_text="   ",
        )


def test_build_download_url_should_return_gradio_file_url(tmp_path: Path) -> None:
    """下载链接应指向 Gradio 文件路由。"""

    file_path = tmp_path / "Docs" / "result.txt"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("ok", encoding="utf-8")

    download_url = build_download_url(file_path=file_path)

    assert download_url.startswith("/gradio_api/file=")
    assert "127.0.0.1" not in download_url
    assert "result.txt" in download_url


def test_build_markdown_preview_html_should_render_heading_list_and_table() -> None:
    """预览页应能渲染导出结果常见的标题、列表与表格结构。"""

    preview_html = build_markdown_preview_html(
        title="预览测试",
        markdown_text="\n".join(
            [
                "# 标题",
                "",
                "- 第一项",
                "- 第二项",
                "",
                "| 列1 | 列2 |",
                "| --- | --- |",
                "| A | B |",
            ]
        ),
    )

    assert "<h1>标题</h1>" in preview_html
    assert "<li>第一项</li>" in preview_html
    assert "<table>" in preview_html
    assert "<th>列1</th>" in preview_html
    assert "<td>A</td>" in preview_html
    assert "table-layout: fixed" in preview_html
    assert "overflow-wrap: anywhere" in preview_html
    assert "word-break: break-word" in preview_html
