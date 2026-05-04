"""程序说明：加载应用运行配置，并统一管理默认路径与环境变量。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """应用配置对象。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    gradio_port: int = Field(default=7860, alias="GRADIO_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # 兼容旧的 DOCS_ROOT，同时明确新语义为知识库输入目录。
    input_root: Path = Field(
        default=Path("Input"),
        alias="INPUT_ROOT",
        validation_alias=AliasChoices("INPUT_ROOT", "DOCS_ROOT"),
    )
    sqlite_db_path: Path = Field(default=Path("index/app.db"), alias="SQLITE_DB_PATH")
    chroma_persist_dir: Path = Field(default=Path("index/chroma"), alias="CHROMA_PERSIST_DIR")
    rules_dir: Path = Field(default=Path("rules"), alias="RULES_DIR")
    templates_dir: Path = Field(default=Path("templates"), alias="TEMPLATES_DIR")

    embedding_provider: str = Field(default="local", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="deterministic-v1", alias="EMBEDDING_MODEL")
    embedding_base_url: str | None = Field(default=None, alias="EMBEDDING_BASE_URL")
    embedding_api_key: str | None = Field(
        default=None,
        alias="EMBEDDING_API_KEY",
        validation_alias=AliasChoices("EMBEDDING_API_KEY", "OPENAI_API_KEY"),
    )
    embedding_timeout_seconds: int = Field(default=180, alias="EMBEDDING_TIMEOUT_SECONDS")
    rerank_enabled: bool = Field(default=True, alias="RERANK_ENABLED")
    rerank_provider: str = Field(default="dashscope", alias="RERANK_PROVIDER")
    rerank_model: str = Field(default="default", alias="RERANK_MODEL")
    rerank_base_url: str | None = Field(default=None, alias="RERANK_BASE_URL")
    rerank_api_key: str | None = Field(
        default=None,
        alias="RERANK_API_KEY",
        validation_alias=AliasChoices("RERANK_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY"),
    )
    rerank_timeout_seconds: int = Field(default=60, alias="RERANK_TIMEOUT_SECONDS")
    llm_provider: str = Field(default="disabled", alias="LLM_PROVIDER")
    llm_base_url: str | None = Field(default=None, alias="LLM_BASE_URL")
    llm_api_key: str | None = Field(
        default=None,
        alias="LLM_API_KEY",
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"),
    )
    llm_model: str = Field(default="disabled", alias="LLM_MODEL")
    llm_timeout_seconds: int = Field(default=60, alias="LLM_TIMEOUT_SECONDS")
    llm_max_tokens: int = Field(default=1024, alias="LLM_MAX_TOKENS")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    llm_top_p: float = Field(default=1.0, alias="LLM_TOP_P")
    llm_enable_thinking: bool = Field(default=False, alias="LLM_ENABLE_THINKING")
    anthropic_api_version: str = Field(default="2023-06-01", alias="ANTHROPIC_API_VERSION")

    dashscope_api_key: str | None = Field(default=None, alias="DASHSCOPE_API_KEY")

    def ensure_runtime_directories(self) -> None:
        """确保运行期依赖目录存在。"""

        self.input_root.mkdir(parents=True, exist_ok=True)
        (self.input_root / "default").mkdir(parents=True, exist_ok=True)
        self.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """返回单例配置，避免重复读取环境变量。"""

    settings = AppSettings()
    settings.ensure_runtime_directories()
    return settings
