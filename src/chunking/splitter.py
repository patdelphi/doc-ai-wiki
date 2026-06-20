"""程序说明：按 Markdown 语义块优先、固定长度兜底的方式切分文本。"""

from __future__ import annotations


def split_text(content: str, chunk_size: int = 500, chunk_overlap: int = 100) -> list[str]:
    """优先按 Markdown 结构切分文本，超长普通段落再按字符长度兜底。"""

    if not content.strip():
        return []

    semantic_blocks = _split_markdown_blocks(content)
    if not semantic_blocks:
        return []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for block in semantic_blocks:
        if _should_split_block(block, chunk_size):
            if current_parts:
                chunks.append("\n\n".join(current_parts).strip())
                current_parts = []
                current_length = 0
            chunks.extend(_split_by_length(block, chunk_size, chunk_overlap))
            continue

        separator_length = 2 if current_parts else 0
        next_length = current_length + separator_length + len(block)
        if current_parts and next_length > chunk_size:
            chunks.append("\n\n".join(current_parts).strip())
            current_parts = [block]
            current_length = len(block)
        else:
            current_parts.append(block)
            current_length = next_length

    if current_parts:
        chunks.append("\n\n".join(current_parts).strip())

    return [chunk for chunk in chunks if chunk]


def _split_by_length(content: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """对超长普通文本执行固定长度兜底切分。"""

    if chunk_size <= 0:
        return [content.strip()] if content.strip() else []

    overlap = max(0, min(chunk_overlap, chunk_size - 1))
    chunks: list[str] = []
    start = 0
    content_length = len(content)

    while start < content_length:
        end = min(start + chunk_size, content_length)
        chunks.append(content[start:end].strip())
        if end >= content_length:
            break
        start = max(end - overlap, start + 1)

    return [chunk for chunk in chunks if chunk]


def _split_markdown_blocks(content: str) -> list[str]:
    """将 Markdown 文本切成段落、表格、引用块、代码块等语义块。"""

    blocks: list[str] = []
    current_lines: list[str] = []
    current_kind = ""
    in_fenced_code = False

    def flush_current() -> None:
        nonlocal current_lines, current_kind
        normalized = "\n".join(current_lines).strip()
        if normalized:
            blocks.append(normalized)
        current_lines = []
        current_kind = ""

    for line in content.splitlines():
        stripped = line.strip()
        line_kind = _detect_line_kind(stripped, in_fenced_code)

        if line_kind == "blank" and not in_fenced_code:
            flush_current()
            continue

        if current_lines and current_kind and line_kind != current_kind and not in_fenced_code:
            flush_current()

        current_lines.append(line)
        current_kind = line_kind

        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fenced_code = not in_fenced_code
            current_kind = "fenced_code"
            if not in_fenced_code:
                flush_current()

    flush_current()
    return blocks


def _detect_line_kind(stripped_line: str, in_fenced_code: bool) -> str:
    """识别当前行所属的 Markdown 块类型。"""

    if in_fenced_code:
        return "fenced_code"
    if not stripped_line:
        return "blank"
    if stripped_line.startswith("```") or stripped_line.startswith("~~~"):
        return "fenced_code"
    if stripped_line.startswith(">"):
        return "blockquote"
    if stripped_line.startswith("|") and stripped_line.endswith("|"):
        return "table"
    if stripped_line.startswith(("- ", "* ", "+ ")) or _is_ordered_list_line(stripped_line):
        return "list"
    return "paragraph"


def _is_ordered_list_line(stripped_line: str) -> bool:
    """判断是否为有序列表行。"""

    dot_index = stripped_line.find(". ")
    if dot_index <= 0:
        return False
    return stripped_line[:dot_index].isdigit()


def _should_split_block(block: str, chunk_size: int) -> bool:
    """只有普通超长段落才允许二次固定长度切分。"""

    if chunk_size <= 0 or len(block) <= chunk_size:
        return False
    first_line = block.lstrip().splitlines()[0].strip()
    structural_prefixes = (">", "|", "```", "~~~", "- ", "* ", "+ ")
    if first_line.startswith(structural_prefixes) or _is_ordered_list_line(first_line):
        return False
    return True
