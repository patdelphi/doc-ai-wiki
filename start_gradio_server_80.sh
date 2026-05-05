#!/usr/bin/env sh

# 程序说明：以服务器模式启动 Gradio UI，固定监听 0.0.0.0:80。

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 固化服务器启动参数，便于外部访问；80 端口通常需要 root 或等效权限。
export APP_HOST="0.0.0.0"
export GRADIO_PORT="80"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ -x "$VENV_PYTHON" ]; then
  exec "$VENV_PYTHON" -m src.ui.app
fi

exec python -m src.ui.app
