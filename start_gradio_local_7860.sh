#!/usr/bin/env sh

# Program description: Start the FastAPI backend and Gradio frontend locally with automatic port fallback.

set -eu

DRY_RUN="0"
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN="1"
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ -x "$VENV_PYTHON" ]; then
  PYTHON_BIN="$VENV_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  printf 'Python was not found. Install Python or create .venv before starting the app.\n' >&2
  exit 1
fi

is_port_free() {
  "$PYTHON_BIN" - "$1" "$APP_HOST_VALUE" <<'PY'
import socket
import sys

port = int(sys.argv[1])
host = sys.argv[2]
bind_hosts = ["0.0.0.0"] if host == "0.0.0.0" else [host, "127.0.0.1"]
for bind_host in dict.fromkeys(bind_hosts):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((bind_host, port))
        except OSError:
            sys.exit(1)
sys.exit(0)
PY
}

find_free_port() {
  port="$1"
  while ! is_port_free "$port"; do
    port=$((port + 1))
  done
  printf '%s' "$port"
}

APP_HOST_VALUE="127.0.0.1"
APP_PORT_VALUE="$(find_free_port 8000)"
GRADIO_PORT_VALUE="$(find_free_port 7860)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
BACKEND_OUT_LOG="$LOG_DIR/backend_$APP_PORT_VALUE.out.log"
BACKEND_ERR_LOG="$LOG_DIR/backend_$APP_PORT_VALUE.err.log"
FRONTEND_OUT_LOG="$LOG_DIR/frontend_$GRADIO_PORT_VALUE.out.log"
FRONTEND_ERR_LOG="$LOG_DIR/frontend_$GRADIO_PORT_VALUE.err.log"

export APP_HOST="$APP_HOST_VALUE"
export APP_PORT="$APP_PORT_VALUE"
export GRADIO_PORT="$GRADIO_PORT_VALUE"

printf 'Backend URL: http://%s:%s\n' "$APP_HOST_VALUE" "$APP_PORT_VALUE"
printf 'Frontend URL: http://%s:%s\n' "$APP_HOST_VALUE" "$GRADIO_PORT_VALUE"

if [ "$DRY_RUN" = "1" ]; then
  printf 'Dry run enabled. No process was started.\n'
  printf 'Backend command: %s -m uvicorn src.app:app --host %s --port %s\n' "$PYTHON_BIN" "$APP_HOST_VALUE" "$APP_PORT_VALUE"
  printf 'Frontend command: %s -m src.ui.app\n' "$PYTHON_BIN"
  exit 0
fi

show_log_tail() {
  title="$1"
  path="$2"
  printf '\n----- %s -----\n' "$title"
  if [ -f "$path" ]; then
    tail -n 80 "$path"
  else
    printf 'Log file was not created: %s\n' "$path"
  fi
}

check_process_started() {
  pid="$1"
  name="$2"
  out_log="$3"
  err_log="$4"
  sleep 3
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    printf '%s failed to start.\n' "$name"
    show_log_tail "$name stderr" "$err_log"
    show_log_tail "$name stdout" "$out_log"
    return 1
  fi
  printf '%s is running. Process ID: %s\n' "$name" "$pid"
  return 0
}

"$PYTHON_BIN" -m uvicorn src.app:app --host "$APP_HOST_VALUE" --port "$APP_PORT_VALUE" > "$BACKEND_OUT_LOG" 2> "$BACKEND_ERR_LOG" &
BACKEND_PID="$!"

"$PYTHON_BIN" -m src.ui.app > "$FRONTEND_OUT_LOG" 2> "$FRONTEND_ERR_LOG" &
FRONTEND_PID="$!"

BACKEND_OK="1"
FRONTEND_OK="1"
check_process_started "$BACKEND_PID" "Backend" "$BACKEND_OUT_LOG" "$BACKEND_ERR_LOG" || BACKEND_OK="0"
check_process_started "$FRONTEND_PID" "Frontend" "$FRONTEND_OUT_LOG" "$FRONTEND_ERR_LOG" || FRONTEND_OK="0"
printf 'Logs directory: %s\n' "$LOG_DIR"
if [ "$BACKEND_OK" != "1" ] || [ "$FRONTEND_OK" != "1" ]; then
  exit 1
fi
