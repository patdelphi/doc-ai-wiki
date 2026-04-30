"""程序说明：读取当前 .env 配置，执行 LLM、Embedding 与 Rerank 的最小连通性自检并输出 JSON 结果。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai.smoke import print_model_smoke_test


if __name__ == "__main__":
    print_model_smoke_test()
