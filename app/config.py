"""
Central configuration for the application.

All values can be overridden with environment variables (see .env.example).
Nothing here should contain secrets committed to source control -- the
defaults are safe for local personal use only.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # Flask
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
    DEBUG: bool = _bool(os.environ.get("FLASK_DEBUG"), default=False)
    HOST: str = os.environ.get("HOST", "127.0.0.1")
    PORT: int = int(os.environ.get("PORT", "5000"))

    # Storage locations
    DEFAULT_DOWNLOAD_FOLDER: str = os.environ.get("DOWNLOAD_FOLDER", str(BASE_DIR / "downloads"))
    DATA_DIR: Path = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
    DATABASE_PATH: str = os.environ.get("DATABASE_PATH", str(DATA_DIR / "app.db"))
    SETTINGS_PATH: str = os.environ.get("SETTINGS_PATH", str(DATA_DIR / "settings.json"))

    # Logging
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    LOG_DIR: Path = Path(os.environ.get("LOG_DIR", str(BASE_DIR / "logs")))
    LOG_FILE: str = str(LOG_DIR / "app.log")

    # Download queue
    MAX_CONCURRENT_DOWNLOADS: int = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", "3"))
    MAX_HISTORY_ITEMS: int = int(os.environ.get("MAX_HISTORY_ITEMS", "500"))

    # yt-dlp behaviour
    COOKIES_FROM_BROWSER: str = os.environ.get("COOKIES_FROM_BROWSER", "")  # e.g. "chrome"
    COOKIES_FILE: str = os.environ.get("COOKIES_FILE", "")  # path to a cookies.txt
    SPONSORBLOCK_DEFAULT: bool = _bool(os.environ.get("SPONSORBLOCK_DEFAULT"), default=False)
    HTTP_USER_AGENT: str = os.environ.get("HTTP_USER_AGENT", "")

    FFMPEG_LOCATION: str = os.environ.get("FFMPEG_LOCATION", "")
    JS_RUNTIME: str = os.environ.get("JS_RUNTIME", "auto")
    JS_RUNTIME_PATH: str = os.environ.get("JS_RUNTIME_PATH", "")
    YTDLP_CHANNEL: str = os.environ.get("YTDLP_CHANNEL", "stable")

    # Single local account; credentials are created using manage.py set-user.
    AUTH_DATABASE: str = str(DATA_DIR / "auth.db")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"))
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    SESSION_REFRESH_EACH_REQUEST = False

    # Security
    ALLOWED_ORIGINS: str = os.environ.get(
        "ALLOWED_ORIGINS", ""
    )  # comma separated, blank = same-origin only
    MAX_CONTENT_LENGTH: int = 1 * 1024 * 1024  # 1MB - this app only accepts small JSON payloads

    @classmethod
    def ensure_dirs(cls) -> None:
        Path(cls.DEFAULT_DOWNLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
