"""程序说明：提供测试期的全局初始化配置，并按目录自动补齐 pytest marker。"""

from __future__ import annotations

import os
from pathlib import Path

# 在 pytest 导入 UI 相关模块前关闭 Gradio 分析线程，保证测试纯本地执行。
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")


def pytest_collection_modifyitems(items) -> None:
    """按目录自动标记 unit/integration，避免每个测试文件重复声明。"""

    for item in items:
        test_path = Path(str(item.fspath))
        path_parts = set(test_path.parts)
        if "unit" in path_parts:
            item.add_marker("unit")
        if "integration" in path_parts:
            item.add_marker("integration")
