"""程序说明：从 Markdown 文本中抽取最小可用元数据。"""

from __future__ import annotations

from pathlib import Path

from src.common.utils import load_json_object, normalize_tags


def extract_basic_metadata(file_path: Path, content: str) -> dict:
    """提取标题与逻辑文档标识。"""

    if file_path.suffix.lower() == ".json":
        payload = load_json_object(file_path)
        title = str(payload.get("title", file_path.stem))
        edition = payload.get("edition")
        author = payload.get("author")
        source_name = payload.get("source") or payload.get("source_name")
        tags = normalize_tags(payload.get("tags"))
        return {
            "doc_title": title,
            "doc_id": title.lower().replace(" ", "_"),
            "edition": edition,
            "author": str(author) if author is not None else None,
            "source_name": str(source_name) if source_name is not None else None,
            "tags": tags,
        }

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
        "author": None,
        "source_name": None,
        "tags": [],
    }
