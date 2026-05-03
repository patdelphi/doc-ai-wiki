"""程序说明：提供页面结果的 Markdown 文本导出与下载链接能力。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from src.common.errors import ValidationAppError
from src.common.utils import utc_now_iso


def save_markdown_export(
    base_path: str | Path,
    *,
    module_name: str,
    result_name: str,
    linked_id: str | None = None,
    markdown_text: str,
) -> dict:
    """将 Markdown 文本保存到 Docs 目录下的 TXT 文件。"""

    resolved_text = str(markdown_text or "").strip()
    if not resolved_text:
        raise ValidationAppError("导出内容为空，无法生成下载文件")

    docs_dir = resolve_export_docs_dir(base_path)

    safe_module_name = _sanitize_file_name_part(module_name) or "module"
    safe_result_name = _sanitize_file_name_part(result_name) or "result"
    safe_linked_id = _sanitize_file_name_part(linked_id or "")
    timestamp = utc_now_iso().replace(":", "").replace("-", "").replace("+", "_").replace("T", "_")
    file_name_parts = [safe_module_name, safe_result_name]
    if safe_linked_id:
        file_name_parts.append(safe_linked_id)
    file_name_parts.append(timestamp)
    file_name = "_".join(file_name_parts) + ".txt"
    file_path = docs_dir / file_name
    file_path.write_text(resolved_text, encoding="utf-8")

    return {
        "file_name": file_name,
        "file_path": str(file_path),
        "byte_count": file_path.stat().st_size,
    }


def resolve_export_docs_dir(base_path: str | Path) -> Path:
    """根据基准路径解析导出目录。"""

    root_path = Path(base_path).resolve()
    project_root = root_path if root_path.is_dir() else root_path.parent
    docs_dir = project_root / "Docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return docs_dir


def build_download_url(
    *,
    file_path: str | Path,
) -> str:
    """根据导出文件路径构造 Gradio 可访问的相对下载 URL。"""

    resolved_path = Path(file_path).resolve()
    encoded_path = quote(str(resolved_path).replace("\\", "/"), safe="/:")
    return f"/gradio_api/file={encoded_path}"


def _sanitize_file_name_part(value: str) -> str:
    """清理文件名片段，避免非法字符导致写盘失败。"""

    normalized = re.sub(r"[<>:\"/\\|?*\r\n\t]+", "_", str(value or "").strip())
    normalized = re.sub(r"\s+", "_", normalized)
    return normalized.strip("._")
