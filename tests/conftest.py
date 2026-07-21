"""程序说明：提供测试期的全局初始化配置，并按目录自动补齐 pytest marker。"""

from __future__ import annotations

import os
from pathlib import Path

# 在 pytest 导入业务模块前覆盖真实环境，保证测试纯本地、无外部调用。
os.environ["DOC_AI_WIKI_INITIAL_ADMIN_PASSWORD"] = ""
os.environ["LLM_PROVIDER"] = "disabled"
os.environ["LLM_MODEL"] = "disabled"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["EMBEDDING_API_KEY"] = ""
os.environ["RERANK_ENABLED"] = "false"
os.environ["RERANK_API_KEY"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
# 测试必须与真实运行期索引隔离，避免本地 Qwen 1024 维索引影响默认 app 导入。
os.environ["SQLITE_DB_PATH"] = "index/test_app.db"
os.environ["CHROMA_PERSIST_DIR"] = "index/test_chroma"


def pytest_collection_modifyitems(items) -> None:
    """按目录自动标记 unit/integration，避免每个测试文件重复声明。"""

    for item in items:
        test_path = Path(str(item.fspath))
        path_parts = set(test_path.parts)
        if "unit" in path_parts:
            item.add_marker("unit")
        if "integration" in path_parts:
            item.add_marker("integration")
