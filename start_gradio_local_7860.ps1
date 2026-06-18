# Program description: Start the FastAPI backend and Gradio frontend locally with automatic port fallback.

param(
    [switch]$DryRun,
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

function Test-PortAvailable {
    param(
        [int]$Port,
        [string]$HostValue = "127.0.0.1"
    )
    try {
        $activeListeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        if ($activeListeners) {
            return $false
        }
    } catch {
        # Fall back to socket binding when Get-NetTCPConnection is unavailable.
    }
    $listener = $null
    try {
        $ipAddress = if ($HostValue -eq "0.0.0.0") { [System.Net.IPAddress]::Any } else { [System.Net.IPAddress]::Parse($HostValue) }
        $listener = [System.Net.Sockets.TcpListener]::new($ipAddress, $Port)
        $listener.Server.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::Socket, [System.Net.Sockets.SocketOptionName]::ExclusiveAddressUse, $true)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $listener) {
            $listener.Stop()
        }
    }
}

function Get-FreePort {
    param(
        [int]$StartPort,
        [string]$HostValue = "127.0.0.1"
    )
    $port = $StartPort
    while (-not (Test-PortAvailable -Port $port -HostValue $HostValue)) {
        $port += 1
    }
    return $port
}

$pythonExe = "python"
$venvPython = Join-Path $scriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
}

$hostValue = "127.0.0.1"
$backendPort = Get-FreePort -StartPort 8000 -HostValue $hostValue
$frontendPort = Get-FreePort -StartPort 7860 -HostValue $hostValue
$logDir = Join-Path $scriptRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$backendOutLog = Join-Path $logDir "backend_$backendPort.out.log"
$backendErrLog = Join-Path $logDir "backend_$backendPort.err.log"
$frontendOutLog = Join-Path $logDir "frontend_$frontendPort.out.log"
$frontendErrLog = Join-Path $logDir "frontend_$frontendPort.err.log"

$env:APP_HOST = $hostValue
$env:APP_PORT = [string]$backendPort
$env:GRADIO_PORT = [string]$frontendPort

$backendArgs = @("-m", "uvicorn", "src.app:app", "--host", $hostValue, "--port", [string]$backendPort)
$frontendArgs = @("-m", "src.ui.app")

function Show-LogTail {
    param(
        [string]$Title,
        [string]$Path
    )
    Write-Host ""
    Write-Host "----- $Title -----"
    if (Test-Path $Path) {
        Get-Content -Path $Path -Tail 80
    } else {
        Write-Host "Log file was not created: $Path"
    }
}

function Wait-ServiceStartup {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Name,
        [string]$OutLog,
        [string]$ErrLog
    )
    Start-Sleep -Seconds 3
    if ($Process.HasExited) {
        Write-Host "$Name failed to start. Exit code: $($Process.ExitCode)"
        Show-LogTail "$Name stderr" $ErrLog
        Show-LogTail "$Name stdout" $OutLog
        return $false
    }
    Write-Host "$Name is running. Process ID: $($Process.Id)"
    return $true
}

function Wait-BeforeExit {
    if (-not $NoPause) {
        Write-Host ""
        Read-Host "Press Enter to close this window"
    }
}

trap {
    Write-Host "Startup script failed."
    Write-Host $_
    Wait-BeforeExit
    exit 1
}

Write-Host "Backend URL: http://$hostValue`:$backendPort"
Write-Host "Frontend URL: http://$hostValue`:$frontendPort"

if ($DryRun) {
    Write-Host "Dry run enabled. No process was started."
    Write-Host "Backend command: $pythonExe $($backendArgs -join ' ')"
    Write-Host "Frontend command: $pythonExe $($frontendArgs -join ' ')"
    Wait-BeforeExit
    exit 0
}

$backendProcess = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList $backendArgs `
    -WorkingDirectory $scriptRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendOutLog `
    -RedirectStandardError $backendErrLog `
    -PassThru

$frontendProcess = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList $frontendArgs `
    -WorkingDirectory $scriptRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $frontendOutLog `
    -RedirectStandardError $frontendErrLog `
    -PassThru

$backendOk = Wait-ServiceStartup $backendProcess "Backend" $backendOutLog $backendErrLog
$frontendOk = Wait-ServiceStartup $frontendProcess "Frontend" $frontendOutLog $frontendErrLog
Write-Host "Logs directory: $logDir"
if (-not ($backendOk -and $frontendOk)) {
    Wait-BeforeExit
    exit 1
}
Wait-BeforeExit
