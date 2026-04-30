"""程序说明：提供最小 Gradio 页面占位，便于后续接入。"""

from __future__ import annotations

import gradio as gr


def build_ui() -> gr.Blocks:
    """构建最小界面占位。"""

    with gr.Blocks(title="中文知识库系统") as demo:
        gr.Markdown("# 中文知识库系统 MVP")
        gr.Markdown("当前版本已完成基础服务骨架，后续将逐步接入检索、质检与审核页面。")
    return demo
