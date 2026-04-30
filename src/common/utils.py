"""程序说明：提供文本、时间与哈希等通用工具函数。"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


def utc_now_iso() -> str:
    """返回统一的 UTC 时间字符串。"""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_of_text(content: str) -> str:
    """计算文本内容哈希值，用于变更检测。"""

    return sha256(content.encode("utf-8")).hexdigest()


def read_text_file(file_path: Path) -> str:
    """读取 UTF-8 文本文件。"""

    return file_path.read_text(encoding="utf-8")
