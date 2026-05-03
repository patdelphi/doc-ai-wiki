# 程序说明：启动本项目的 Gradio UI 服务，不启动独立 FastAPI 服务。

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

$venvPython = Join-Path $scriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython -m src.ui.app
    exit $LASTEXITCODE
}

python -m src.ui.app
exit $LASTEXITCODE
