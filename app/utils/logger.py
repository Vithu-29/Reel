"""Centralised logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config import Config

_CONFIGURED = False


def configure_logging() -> None:
    """Idempotently configure root logging with a console + rotating file handler."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    Config.ensure_dirs()

    root = logging.getLogger()
    root.setLevel(Config.LOG_LEVEL)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        Config.LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # yt-dlp and urllib3 are noisy at INFO/DEBUG; keep them at WARNING unless
    # the whole app is explicitly set to DEBUG.
    if Config.LOG_LEVEL.upper() != "DEBUG":
        logging.getLogger("urllib3").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
