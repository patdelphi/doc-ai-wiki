# 程序说明：启动本项目的 Gradio UI 服务，不启动独立 FastAPI 服务。

#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ -x "$VENV_PYTHON" ]; then
  exec "$VENV_PYTHON" -m src.ui.app
fi

exec python -m src.ui.app
