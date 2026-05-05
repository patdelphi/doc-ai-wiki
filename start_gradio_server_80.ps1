# 程序说明：以服务器模式启动 Gradio UI，固定监听 0.0.0.0:80。

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

# 固化服务器启动参数，便于外部访问；80 端口通常需要管理员权限。
$env:APP_HOST = "0.0.0.0"
$env:GRADIO_PORT = "80"

$venvPython = Join-Path $scriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython -m src.ui.app
    exit $LASTEXITCODE
}

python -m src.ui.app
exit $LASTEXITCODE
