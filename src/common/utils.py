"""程序说明：提供文本、时间与哈希等通用工具函数。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


def utc_now_iso() -> str:
    """返回统一的 UTC 时间字符串。"""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_of_text(content: str) -> str:
    """计算文本内容哈希值，用于变更检测。"""

    return sha256(content.encode("utf-8")).hexdigest()


def load_json_object(file_path: Path) -> dict:
    """读取 JSON 对象，供知识条目最小兼容逻辑复用。"""

    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON 根节点必须为对象")
    return payload


def normalize_tags(raw_tags: object) -> list[str]:
    """将 tags 字段归一化为字符串列表。"""

    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        return [raw_tags] if raw_tags.strip() else []
    if isinstance(raw_tags, list):
        return [str(item).strip() for item in raw_tags if str(item).strip()]
    raise ValueError("JSON tags 必须为字符串或字符串数组")


def read_text_file(file_path: Path) -> str:
    """读取 UTF-8 文本文件，对 JSON 输入做最小内容展开。"""

    if file_path.suffix.lower() == ".json":
        payload = load_json_object(file_path)
        title = str(payload.get("title", file_path.stem))
        content = str(payload.get("content", ""))
        return f"# {title}\n\n{content}".strip()
    return file_path.read_text(encoding="utf-8")
