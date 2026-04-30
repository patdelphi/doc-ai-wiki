"""程序说明：解析 Markdown 标题层级，生成章节结构。"""

from __future__ import annotations


def parse_markdown_sections(content: str, fallback_title: str) -> list[dict]:
    """按 Markdown 标题切分章节，保留标题层级和正文内容。"""

    lines = content.splitlines()
    sections: list[dict] = []
    current_title = fallback_title
    current_level = 1
    current_lines: list[str] = []
    section_index = 0

    def flush_section() -> None:
        nonlocal section_index, current_lines
        normalized = "\n".join(current_lines).strip()
        if not normalized and sections:
            current_lines = []
            return

        section_index += 1
        sections.append(
            {
                "section_title": current_title,
                "section_level": current_level,
                "content": normalized or current_title,
                "source_span": f"section-{section_index}",
            }
        )
        current_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip()
            heading_level = len(stripped) - len(stripped.lstrip("#"))
            if current_lines or sections:
                flush_section()
            current_title = heading_text or fallback_title
            current_level = heading_level
            continue

        current_lines.append(line)

    if current_lines or not sections:
        flush_section()

    return sections
