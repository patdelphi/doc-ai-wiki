"""程序说明：管理文档入库质检的本地阈值配置。"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.common.errors import ValidationAppError


DEFAULT_INGEST_QUALITY_CONFIG = {
    "sample_limit": 4,
    "long_document_char_threshold": 2000,
    "min_sections_for_long_doc": 2,
    "max_avg_chunks_per_section": 12,
    "max_chunk_chars": 700,
    "short_chunk_chars": 30,
    "short_chunk_warn_min_chunk_count": 3,
}


class IngestQualityConfigService:
    """入库质检阈值配置服务。"""

    CONFIG_FILE_NAME = "ingest_quality.yaml"

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        self.templates_dir = Path(templates_dir) if templates_dir is not None else Path("templates")

    def get_config(self) -> dict:
        """读取当前质检阈值配置。"""

        config_path = self._get_config_path()
        if not config_path.exists():
            return {**DEFAULT_INGEST_QUALITY_CONFIG, "config_path": str(config_path)}
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValidationAppError("入库质检配置文件格式错误", details={"file_path": str(config_path)}) from exc
        if not isinstance(payload, dict):
            raise ValidationAppError("入库质检配置内容必须为对象", details={"file_path": str(config_path)})
        return {
            **DEFAULT_INGEST_QUALITY_CONFIG,
            **self._normalize_payload(payload),
            "config_path": str(config_path),
        }

    def save_config(self, payload: dict) -> dict:
        """保存入库质检阈值配置。"""

        normalized = self._normalize_payload(payload)
        config_path = self._get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return {
            **DEFAULT_INGEST_QUALITY_CONFIG,
            **normalized,
            "config_path": str(config_path),
        }

    def _get_config_path(self) -> Path:
        """返回质检配置文件路径。"""

        return self.templates_dir / "settings" / self.CONFIG_FILE_NAME

    def _normalize_payload(self, payload: dict) -> dict:
        """校验并规范化配置内容。"""

        normalized = {
            "sample_limit": self._to_int(payload.get("sample_limit"), field_name="sample_limit", minimum=1),
            "long_document_char_threshold": self._to_int(
                payload.get("long_document_char_threshold"),
                field_name="long_document_char_threshold",
                minimum=100,
            ),
            "min_sections_for_long_doc": self._to_int(
                payload.get("min_sections_for_long_doc"),
                field_name="min_sections_for_long_doc",
                minimum=1,
            ),
            "max_avg_chunks_per_section": self._to_int(
                payload.get("max_avg_chunks_per_section"),
                field_name="max_avg_chunks_per_section",
                minimum=1,
            ),
            "max_chunk_chars": self._to_int(payload.get("max_chunk_chars"), field_name="max_chunk_chars", minimum=50),
            "short_chunk_chars": self._to_int(payload.get("short_chunk_chars"), field_name="short_chunk_chars", minimum=1),
            "short_chunk_warn_min_chunk_count": self._to_int(
                payload.get("short_chunk_warn_min_chunk_count"),
                field_name="short_chunk_warn_min_chunk_count",
                minimum=1,
            ),
        }
        if normalized["max_chunk_chars"] <= normalized["short_chunk_chars"]:
            raise ValidationAppError("超长分块阈值必须大于过短分块阈值")
        return normalized

    @staticmethod
    def _to_int(value: object, *, field_name: str, minimum: int) -> int:
        """将配置项转换为正整数。"""

        if value in (None, ""):
            return int(DEFAULT_INGEST_QUALITY_CONFIG[field_name])
        try:
            normalized = int(float(value))
        except (TypeError, ValueError) as exc:
            raise ValidationAppError(f"{field_name} 必须为整数") from exc
        if normalized < minimum:
            raise ValidationAppError(f"{field_name} 不能小于 {minimum}")
        return normalized
