"""程序说明：从 Markdown 文本中抽取最小可用元数据。"""

from __future__ import annotations

from pathlib import Path


def extract_basic_metadata(file_path: Path, content: str) -> dict:
    """提取标题与逻辑文档标识。"""

    title = file_path.stem
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip() or title
            break

    return {
        "doc_title": title,
        "doc_id": title.lower().replace(" ", "_"),
        "edition": None,
    }
