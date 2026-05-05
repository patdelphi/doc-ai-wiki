# 程序说明：兼容旧入口，转发到本地 7860 启动脚本，最终仍启动 `src.ui.app`。

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

& (Join-Path $scriptRoot "start_gradio_local_7860.ps1")
exit $LASTEXITCODE
