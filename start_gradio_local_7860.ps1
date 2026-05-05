# 程序说明：以本地开发模式启动 Gradio UI，固定监听 127.0.0.1:7860。

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

# 固化本地开发启动参数，避免受外部环境变量污染。
$env:APP_HOST = "127.0.0.1"
$env:GRADIO_PORT = "7860"

$venvPython = Join-Path $scriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython -m src.ui.app
    exit $LASTEXITCODE
}

python -m src.ui.app
exit $LASTEXITCODE
