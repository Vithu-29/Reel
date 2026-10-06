"""Persisted user settings (download folder, concurrency, feature defaults).

Deliberately a flat JSON file rather than a database table - this is a
handful of scalar preferences, not relational data.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.config import Config
from app.utils.logger import get_logger

log = get_logger(__name__)

_DEFAULTS: dict[str, Any] = {
    "download_folder": Config.DEFAULT_DOWNLOAD_FOLDER,
    "concurrency": Config.MAX_CONCURRENT_DOWNLOADS,
    "sponsorblock_default": Config.SPONSORBLOCK_DEFAULT,
    "embed_metadata_default": True,
    "theme": "dark",
}


class SettingsStore:
    def __init__(self, path: str | None = None):
        self.path = Path(path or Config.SETTINGS_PATH)
        self._lock = threading.Lock()
        self._data = dict(_DEFAULTS)
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    on_disk = json.load(f)
                self._data.update({k: v for k, v in on_disk.items() if k in _DEFAULTS})
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Could not read settings file, using defaults: %s", exc)
        else:
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get_all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key, value in patch.items():
                if key in _DEFAULTS:
                    self._data[key] = value
            self._save()
            return dict(self._data)
