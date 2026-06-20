"""程序说明：校验启动脚本中的监听地址、端口和入口命令是否符合约定。"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_script(script_name: str) -> str:
    """读取启动脚本内容。"""

    return (PROJECT_ROOT / script_name).read_text(encoding="utf-8")


def test_local_powershell_startup_script_should_start_from_127001_and_7860() -> None:
    """本地 PowerShell 脚本应从 127.0.0.1 与 7860 起自动寻找可用端口。"""

    content = read_script("start_gradio_local_7860.ps1")

    assert '$hostValue = "127.0.0.1"' in content
    assert "$frontendPort = Get-FreePort -StartPort 7860 -HostValue $hostValue" in content
    assert '$env:GRADIO_PORT = [string]$frontendPort' in content
    assert '$frontendArgs = @("-m", "src.ui.app")' in content


def test_server_powershell_startup_script_should_start_from_0000_and_80() -> None:
    """服务器 PowerShell 脚本应从 0.0.0.0 与 80 起自动寻找可用端口。"""

    content = read_script("start_gradio_server_80.ps1")

    assert '$hostValue = "0.0.0.0"' in content
    assert "$frontendPort = Get-FreePort -StartPort 80 -HostValue $hostValue" in content
    assert '$env:GRADIO_PORT = [string]$frontendPort' in content
    assert '$frontendArgs = @("-m", "src.ui.app")' in content


def test_local_shell_startup_script_should_start_from_127001_and_7860() -> None:
    """本地 Shell 脚本应从 127.0.0.1 与 7860 起自动寻找可用端口。"""

    content = read_script("start_gradio_local_7860.sh")

    assert 'APP_HOST_VALUE="127.0.0.1"' in content
    assert 'GRADIO_PORT_VALUE="$(find_free_port 7860)"' in content
    assert 'export GRADIO_PORT="$GRADIO_PORT_VALUE"' in content
    assert '"$PYTHON_BIN" -m src.ui.app' in content


def test_server_shell_startup_script_should_start_from_0000_and_80() -> None:
    """服务器 Shell 脚本应从 0.0.0.0 与 80 起自动寻找可用端口。"""

    content = read_script("start_gradio_server_80.sh")

    assert 'APP_HOST_VALUE="0.0.0.0"' in content
    assert 'GRADIO_PORT_VALUE="$(find_free_port 80)"' in content
    assert 'export GRADIO_PORT="$GRADIO_PORT_VALUE"' in content
    assert '"$PYTHON_BIN" -m src.ui.app' in content


def test_legacy_powershell_startup_script_should_not_exist_anymore() -> None:
    """旧 PowerShell 入口已废弃，不应继续保留。"""

    assert (PROJECT_ROOT / "start_gradio.ps1").exists() is False


def test_legacy_shell_startup_script_should_not_exist_anymore() -> None:
    """旧 Shell 入口已废弃，不应继续保留。"""

    assert (PROJECT_ROOT / "start_gradio.sh").exists() is False
