"""程序说明：验证输入文档路径在数据库中只保存 Input 相对路径。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.common.errors import ValidationAppError
from src.common.paths import resolve_input_path, to_input_relative_path


def test_to_input_relative_path_should_store_relative_slash_path(tmp_path: Path) -> None:
    """Input 内文件应转换为稳定的相对路径。"""

    input_root = tmp_path / "Input"
    document_path = input_root / "default" / "a1.md"
    document_path.parent.mkdir(parents=True)
    document_path.write_text("# A1", encoding="utf-8")

    assert to_input_relative_path(document_path, input_root) == "default/a1.md"


def test_resolve_input_path_should_reject_path_escape(tmp_path: Path) -> None:
    """相对路径不能通过 .. 逃出 Input 目录。"""

    input_root = tmp_path / "Input"
    input_root.mkdir()

    with pytest.raises(ValidationAppError, match="文件路径不在允许的输入目录内"):
        resolve_input_path("../outside.md", input_root)
