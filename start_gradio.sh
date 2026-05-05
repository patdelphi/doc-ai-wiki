#!/usr/bin/env sh

# 程序说明：兼容旧入口，转发到本地 7860 启动脚本。

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

exec sh "$SCRIPT_DIR/start_gradio_local_7860.sh"
