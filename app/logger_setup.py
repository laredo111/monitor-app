from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(base_dir: Path) -> logging.Logger:
    """
    Creates a production-friendly logger:
    - logs to logs/monitor.log
    - rotates at ~10MB, keeps 10 backups
    - UTF-8 encoding so Hebrew is OK
    """
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("monitor")
    logger.setLevel(logging.INFO)

    # חשוב: למנוע כפילות handlers אם setup_logger נקרא שוב
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        logs_dir / "monitor.log",
        maxBytes=10 * 1024 * 1024,   # 10MB
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
