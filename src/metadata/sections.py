"""程序说明：解析 Markdown 标题层级，生成章节结构。"""

from __future__ import annotations


def parse_markdown_sections(content: str, fallback_title: str) -> list[dict]:
    """按 Markdown 标题切分章节，保留标题层级、标题路径和行号范围。"""

    lines = content.splitlines()
    sections: list[dict] = []
    current_title = fallback_title
    current_level = 1
    current_lines: list[str] = []
    current_start_line = 1
    heading_stack: list[tuple[int, str]] = [(1, fallback_title)]
    section_index = 0

    def build_heading_path() -> str:
        """根据当前标题栈生成稳定标题路径。"""

        return " > ".join(title for _, title in heading_stack if title)

    def flush_section(end_line: int) -> None:
        nonlocal section_index, current_lines
        normalized = "\n".join(current_lines).strip()
        if not normalized and sections:
            current_lines = []
            return

        section_index += 1
        safe_end_line = max(current_start_line, end_line)
        sections.append(
            {
                "section_title": current_title,
                "section_level": current_level,
                "content": normalized or current_title,
                "source_span": f"section-{section_index}",
                "heading_path": build_heading_path(),
                "source_start_line": current_start_line,
                "source_end_line": safe_end_line,
                "source_anchor": f"L{current_start_line}-L{safe_end_line}",
            }
        )
        current_lines = []

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip()
            heading_level = len(stripped) - len(stripped.lstrip("#"))
            if current_lines or sections:
                flush_section(line_number - 1)
            heading_stack = [(level, title) for level, title in heading_stack if level < heading_level]
            heading_stack.append((heading_level, heading_text or fallback_title))
            current_title = heading_text or fallback_title
            current_level = heading_level
            current_start_line = line_number
            continue

        current_lines.append(line)

    if current_lines or not sections:
        flush_section(len(lines) or 1)

    return sections
