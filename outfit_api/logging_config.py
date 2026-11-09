"""统一日志配置：控制台输出，可选按大小轮转的日志文件。"""

import logging.config
import os
from pathlib import Path

_CONFIGURED = False
_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging():
    """按 LOG_LEVEL / LOG_FILE 配置根日志，重复调用只生效一次。"""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    handlers = {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    }
    attached = ["console"]

    log_file = os.environ.get("LOG_FILE", "").strip()
    if log_file:
        path = Path(log_file).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "filename": str(path),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 3,
            "encoding": "utf-8",
        }
        attached.append("file")

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper().strip() or "INFO"
    level = logging.getLevelName(level_name)
    if not isinstance(level, int):
        level = logging.INFO

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"standard": {"format": _FORMAT, "datefmt": _DATE_FORMAT}},
            "handlers": handlers,
            "loggers": {
                # 第三方 HTTP 客户端在 INFO 级别会逐条打印请求，压到 WARNING 避免刷屏。
                "httpx": {"level": "WARNING"},
                "httpcore": {"level": "WARNING"},
            },
            "root": {"level": level, "handlers": attached},
        }
    )
