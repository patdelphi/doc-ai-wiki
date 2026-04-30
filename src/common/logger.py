"""程序说明：封装日志初始化，避免各模块重复配置。"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

import yaml


def configure_logging(config_path: Path, default_level: str = "INFO") -> None:
    """按配置文件初始化日志；缺失时回退到基础配置。"""

    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file) or {}
        logging.config.dictConfig(config)
        return

    logging.basicConfig(level=getattr(logging, default_level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    """获取具名日志对象。"""

    return logging.getLogger(name)
