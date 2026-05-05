"""程序说明：校验启动脚本中的监听地址、端口和入口命令是否符合约定。"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_script(script_name: str) -> str:
    """读取启动脚本内容。"""

    return (PROJECT_ROOT / script_name).read_text(encoding="utf-8")


def test_local_powershell_startup_script_should_bind_to_127001_on_port_7860() -> None:
    """本地 PowerShell 脚本应固定监听 127.0.0.1:7860。"""

    content = read_script("start_gradio_local_7860.ps1")

    assert '$env:APP_HOST = "127.0.0.1"' in content
    assert '$env:GRADIO_PORT = "7860"' in content
    assert "python -m src.ui.app" in content


def test_server_powershell_startup_script_should_bind_to_0000_on_port_80() -> None:
    """服务器 PowerShell 脚本应固定监听 0.0.0.0:80。"""

    content = read_script("start_gradio_server_80.ps1")

    assert '$env:APP_HOST = "0.0.0.0"' in content
    assert '$env:GRADIO_PORT = "80"' in content
    assert "python -m src.ui.app" in content


def test_local_shell_startup_script_should_bind_to_127001_on_port_7860() -> None:
    """本地 Shell 脚本应固定监听 127.0.0.1:7860。"""

    content = read_script("start_gradio_local_7860.sh")

    assert 'export APP_HOST="127.0.0.1"' in content
    assert 'export GRADIO_PORT="7860"' in content
    assert "python -m src.ui.app" in content


def test_server_shell_startup_script_should_bind_to_0000_on_port_80() -> None:
    """服务器 Shell 脚本应固定监听 0.0.0.0:80。"""

    content = read_script("start_gradio_server_80.sh")

    assert 'export APP_HOST="0.0.0.0"' in content
    assert 'export GRADIO_PORT="80"' in content
    assert "python -m src.ui.app" in content


def test_legacy_powershell_startup_script_should_delegate_to_local_7860_script() -> None:
    """旧 PowerShell 入口应转发到本地 7860 脚本。"""

    content = read_script("start_gradio.ps1")

    assert "start_gradio_local_7860.ps1" in content
    assert "python -m src.ui.app" not in content


def test_legacy_shell_startup_script_should_delegate_to_local_7860_script() -> None:
    """旧 Shell 入口应转发到本地 7860 脚本。"""

    content = read_script("start_gradio.sh")

    assert 'start_gradio_local_7860.sh' in content
    assert "python -m src.ui.app" not in content
