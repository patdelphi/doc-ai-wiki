"""程序说明：提供页面结果的 Markdown 文本导出、下载链接与预览页生成能力。"""

from __future__ import annotations

import re
from html import escape
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
    file_extension: str = "txt",
) -> dict:
    """将 Markdown 文本保存到 Docs 目录下的文本文件，并生成 HTML 预览页。"""

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
    safe_file_extension = _sanitize_file_extension(file_extension)
    file_name = "_".join(file_name_parts) + f".{safe_file_extension}"
    file_path = docs_dir / file_name
    file_path.write_text(resolved_text, encoding="utf-8")
    preview_file_name = "_".join(file_name_parts) + ".preview.html"
    preview_file_path = docs_dir / preview_file_name
    preview_file_path.write_text(
        build_markdown_preview_html(
            title=f"{module_name} - {result_name}",
            markdown_text=resolved_text,
        ),
        encoding="utf-8",
    )

    return {
        "file_name": file_name,
        "file_path": str(file_path),
        "preview_file_name": preview_file_name,
        "preview_file_path": str(preview_file_path),
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


def build_markdown_preview_html(*, title: str, markdown_text: str) -> str:
    """将 Markdown 文本转换为可在浏览器中直接查看的 HTML 页面。"""

    rendered_body = _render_markdown_blocks(markdown_text)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            f"  <title>{escape(title)}</title>",
            "  <style>",
            "    body { margin: 0; background: #f6f8fb; color: #1f2937; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }",
            "    .page { max-width: 960px; margin: 0 auto; padding: 32px 20px 48px; }",
            "    .card { background: #fff; border: 1px solid #d9e1ec; border-radius: 16px; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06); overflow: hidden; }",
            "    .header { padding: 20px 24px; border-bottom: 1px solid #e5e7eb; }",
            "    .header h1 { margin: 0; font-size: 24px; }",
            "    .content { padding: 24px; line-height: 1.75; font-size: 15px; overflow-wrap: anywhere; word-break: break-word; }",
            "    h1, h2, h3, h4, h5, h6 { margin: 1.2em 0 0.5em; line-height: 1.35; }",
            "    p { margin: 0 0 1em; }",
            "    ul, ol { margin: 0 0 1em 1.4em; padding: 0; }",
            "    li { margin: 0.25em 0; }",
            "    pre { margin: 0 0 1em; padding: 14px 16px; overflow: auto; background: #0f172a; color: #e2e8f0; border-radius: 12px; }",
            "    code { padding: 0.1em 0.35em; background: #eef2f7; border-radius: 6px; font-family: 'IBM Plex Mono', 'Consolas', monospace; font-size: 0.92em; }",
            "    pre code { padding: 0; background: transparent; }",
            "    table { width: 100%; border-collapse: collapse; margin: 0 0 1em; font-size: 14px; table-layout: fixed; }",
            "    th, td { padding: 10px 12px; border: 1px solid #d9e1ec; text-align: left; vertical-align: top; white-space: normal; word-break: break-word; overflow-wrap: anywhere; }",
            "    th { background: #f8fafc; }",
            "    blockquote { margin: 0 0 1em; padding: 10px 14px; border-left: 4px solid #94a3b8; background: #f8fafc; color: #475569; }",
            "  </style>",
            "</head>",
            "<body>",
            '  <main class="page">',
            '    <section class="card">',
            '      <header class="header">',
            f"        <h1>{escape(title)}</h1>",
            "      </header>",
            '      <article class="content">',
            rendered_body or "        <p>暂无内容</p>",
            "      </article>",
            "    </section>",
            "  </main>",
            "</body>",
            "</html>",
        ]
    )


def _sanitize_file_name_part(value: str) -> str:
    """清理文件名片段，避免非法字符导致写盘失败。"""

    normalized = re.sub(r"[<>:\"/\\|?*\r\n\t]+", "_", str(value or "").strip())
    normalized = re.sub(r"\s+", "_", normalized)
    return normalized.strip("._")


def _sanitize_file_extension(value: str) -> str:
    """清理导出文件后缀，异常输入统一回退到 txt。"""

    normalized = re.sub(r"[^A-Za-z0-9]+", "", str(value or "").strip().lstrip(".")).lower()
    return normalized or "txt"


def _render_markdown_blocks(markdown_text: str) -> str:
    """将常见导出 Markdown 转换为 HTML，覆盖标题、列表、表格与代码块。"""

    lines = str(markdown_text or "").splitlines()
    html_parts: list[str] = []
    paragraph_lines: list[str] = []
    list_items: list[str] = []
    list_tag: str | None = None
    code_lines: list[str] | None = None
    index = 0

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        content = " ".join(item.strip() for item in paragraph_lines if item.strip())
        if content:
            html_parts.append(f"<p>{_render_inline_markdown(content)}</p>")
        paragraph_lines.clear()

    def flush_list() -> None:
        nonlocal list_tag
        if not list_items or not list_tag:
            list_items.clear()
            list_tag = None
            return
        html_parts.append(f"<{list_tag}>")
        html_parts.extend(f"  <li>{item}</li>" for item in list_items)
        html_parts.append(f"</{list_tag}>")
        list_items.clear()
        list_tag = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if code_lines is not None:
            if stripped.startswith("```"):
                html_parts.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = None
            else:
                code_lines.append(line)
            index += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            code_lines = []
            index += 1
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            index += 1
            continue

        if _looks_like_markdown_table(lines, index):
            flush_paragraph()
            flush_list()
            table_html, index = _render_markdown_table(lines, index)
            html_parts.append(table_html)
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph()
            flush_list()
            level = len(heading_match.group(1))
            html_parts.append(f"<h{level}>{_render_inline_markdown(heading_match.group(2).strip())}</h{level}>")
            index += 1
            continue

        unordered_match = re.match(r"^[-*]\s+(.*)$", stripped)
        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if unordered_match or ordered_match:
            flush_paragraph()
            current_tag = "ul" if unordered_match else "ol"
            current_text = unordered_match.group(1) if unordered_match else ordered_match.group(1)
            if list_tag not in (None, current_tag):
                flush_list()
            list_tag = current_tag
            list_items.append(_render_inline_markdown(current_text.strip()))
            index += 1
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            flush_list()
            html_parts.append(f"<blockquote>{_render_inline_markdown(stripped[1:].strip())}</blockquote>")
            index += 1
            continue

        paragraph_lines.append(line)
        index += 1

    flush_paragraph()
    flush_list()
    if code_lines is not None:
        html_parts.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(f"        {item}" for item in html_parts)


def _looks_like_markdown_table(lines: list[str], index: int) -> bool:
    """判断当前位置是否是 Markdown 表格。"""

    if index + 1 >= len(lines):
        return False
    header = lines[index].strip()
    separator = lines[index + 1].strip()
    return header.startswith("|") and header.endswith("|") and bool(re.match(r"^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", separator))


def _render_markdown_table(lines: list[str], index: int) -> tuple[str, int]:
    """将连续的 Markdown 表格行转换为 HTML 表格。"""

    table_lines = [lines[index].strip()]
    index += 2
    while index < len(lines):
        current = lines[index].strip()
        if not current.startswith("|"):
            break
        table_lines.append(current)
        index += 1

    header_cells = _split_table_row(table_lines[0])
    body_rows = [_split_table_row(row) for row in table_lines[1:]]
    html_rows = ["<table>", "  <thead>", "    <tr>"]
    html_rows.extend(f"      <th>{_render_inline_markdown(cell)}</th>" for cell in header_cells)
    html_rows.extend(["    </tr>", "  </thead>", "  <tbody>"])
    for row in body_rows:
        html_rows.append("    <tr>")
        html_rows.extend(f"      <td>{_render_inline_markdown(cell)}</td>" for cell in row)
        html_rows.append("    </tr>")
    html_rows.extend(["  </tbody>", "</table>"])
    return "\n".join(html_rows), index


def _split_table_row(row: str) -> list[str]:
    """拆分单行 Markdown 表格内容。"""

    normalized = row.strip().strip("|")
    return [cell.strip().replace("<br>", "\n") for cell in normalized.split("|")]


def _render_inline_markdown(text: str) -> str:
    """渲染行内 Markdown。"""

    escaped = escape(str(text or ""))
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    return escaped.replace("\n", "<br>")
