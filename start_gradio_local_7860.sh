#!/usr/bin/env sh

# 程序说明：以本地开发模式启动 Gradio UI，固定监听 127.0.0.1:7860。

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 固化本地开发启动参数，避免受外部环境变量污染。
export APP_HOST="127.0.0.1"
export GRADIO_PORT="7860"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ -x "$VENV_PYTHON" ]; then
  exec "$VENV_PYTHON" -m src.ui.app
fi

exec python -m src.ui.app
