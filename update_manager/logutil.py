"""File-only logging (no UI)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def log_dir() -> Path:
    local = Path.home() / "AppData" / "Local" / "CloneUp" / "logs"
    # Prefer LOCALAPPDATA when set (Windows).
    import os

    base = os.environ.get("LOCALAPPDATA")
    if base:
        local = Path(base) / "CloneUp" / "logs"
    local.mkdir(parents=True, exist_ok=True)
    return local


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("cloneup_update_manager")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    path = log_dir() / "update_manager.log"
    handler = RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    # Also mirror to stderr when running under a console (dev).
    stream = logging.StreamHandler()
    stream.setLevel(logging.WARNING)
    stream.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(stream)
    logger.info("log file: %s", path)
    return logger
