"""程序说明：按固定长度对文本进行最小可用分块。"""

from __future__ import annotations


def split_text(content: str, chunk_size: int = 500, chunk_overlap: int = 100) -> list[str]:
    """按字符长度切分文本，保留少量重叠上下文。"""

    if not content.strip():
        return []

    chunks: list[str] = []
    start = 0
    content_length = len(content)

    while start < content_length:
        end = min(start + chunk_size, content_length)
        chunks.append(content[start:end].strip())
        if end >= content_length:
            break
        start = max(end - chunk_overlap, start + 1)

    return [chunk for chunk in chunks if chunk]
