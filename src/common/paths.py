"""程序说明：统一处理 Input 目录内文档路径的解析与数据库存储格式。"""

from __future__ import annotations

from pathlib import Path

from src.common.errors import ValidationAppError


def resolve_input_path(source_path: str | Path, input_root: Path) -> Path:
    """将数据库或 UI 传入路径解析为 Input 内的真实文件路径。"""

    raw_path = Path(str(source_path or "").strip())
    if not str(raw_path):
        raise ValidationAppError("文件路径不能为空")

    base_root = input_root.resolve()
    candidate = raw_path if raw_path.is_absolute() else input_root / raw_path
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(base_root)
    except ValueError as exc:
        raise ValidationAppError(
            "文件路径不在允许的输入目录内",
            details={"file_path": str(source_path), "input_root": str(base_root)},
        ) from exc
    return resolved_candidate


def to_input_relative_path(source_path: str | Path, input_root: Path) -> str:
    """将 Input 内路径转换为数据库使用的相对路径。"""

    resolved_path = resolve_input_path(source_path, input_root)
    relative_path = resolved_path.relative_to(input_root.resolve())
    return relative_path.as_posix()
