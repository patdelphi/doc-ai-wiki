"""程序说明：校验运行时默认配置与 ".env.example" 模板保持一致。"""

from __future__ import annotations

from pathlib import Path

from src.common.config import AppSettings


def read_env_example_values() -> dict[str, str]:
    """读取 ".env.example" 中的键值，避免模板默认值与代码默认值漂移。"""

    env_values: dict[str, str] = {}
    env_example_path = Path(__file__).resolve().parents[2] / ".env.example"
    for raw_line in env_example_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_values[key.strip()] = value.strip()
    return env_values


def test_env_example_defaults_should_match_app_settings_defaults() -> None:
    """模板中的关键默认值应与 AppSettings 默认值一致。"""

    env_values = read_env_example_values()

    assert env_values["EMBEDDING_PROVIDER"] == AppSettings.model_fields["embedding_provider"].default
    assert env_values["EMBEDDING_MODEL"] == AppSettings.model_fields["embedding_model"].default
    assert env_values["LLM_PROVIDER"] == AppSettings.model_fields["llm_provider"].default
    assert env_values["LLM_MODEL"] == AppSettings.model_fields["llm_model"].default
