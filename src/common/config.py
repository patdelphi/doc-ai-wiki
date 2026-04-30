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

    embedding_provider: str = Field(default="dashscope", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="text-embedding-v3", alias="EMBEDDING_MODEL")
    rerank_enabled: bool = Field(default=True, alias="RERANK_ENABLED")
    rerank_provider: str = Field(default="dashscope", alias="RERANK_PROVIDER")
    rerank_model: str = Field(default="default", alias="RERANK_MODEL")
    llm_provider: str = Field(default="qwen", alias="LLM_PROVIDER")
    llm_model: str = Field(default="qwen-max", alias="LLM_MODEL")
    llm_timeout_seconds: int = Field(default=60, alias="LLM_TIMEOUT_SECONDS")

    dashscope_api_key: str | None = Field(default=None, alias="DASHSCOPE_API_KEY")

    def ensure_runtime_directories(self) -> None:
        """确保运行期依赖目录存在。"""

        self.input_root.mkdir(parents=True, exist_ok=True)
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
