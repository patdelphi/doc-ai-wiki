"""程序说明：初始化 UI 包级配置，避免开发环境触发 Gradio 分析上报。"""

from __future__ import annotations

import os

# 本地开发与测试默认关闭分析上报，避免无意义外联和退出期日志噪音。
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
