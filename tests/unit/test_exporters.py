"""程序说明：验证结果导出工具能生成服务端文件与下载链接。"""

from pathlib import Path

import pytest

from src.common.errors import ValidationAppError
from src.ui.exporters import build_download_url, save_markdown_export


def test_save_markdown_export_should_write_txt_to_docs(tmp_path: Path) -> None:
    """导出结果应写入 Docs 目录，并保存为 TXT 文件。"""

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
    assert exported_file.exists()
    assert exported_file.suffix == ".txt"
    assert exported_file.parent == tmp_path / "Docs"
    assert exported_file.read_text(encoding="utf-8") == "### 检索结果\n- 命中条数：2"
    assert export_result["file_name"].endswith(".txt")
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

    download_url = build_download_url(
        file_path=file_path,
        request_host="127.0.0.1",
        request_port=7860,
    )

    assert download_url.startswith("http://127.0.0.1:7860/gradio_api/file=")
    assert "result.txt" in download_url
