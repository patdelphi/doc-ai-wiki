"""程序说明：提供测试期的全局初始化配置。"""

from __future__ import annotations

import os

# 在 pytest 导入 UI 相关模块前关闭 Gradio 分析线程，保证测试纯本地执行。
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
