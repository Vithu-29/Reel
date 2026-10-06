"""
Process-wide service singletons.

Flask's application factory pattern usually favours per-app extension
objects; for a single-process personal tool like this, simple module-level
singletons created once in `create_app()` are enough and keep the services
easy to unit test in isolation (they take no Flask objects as input).
"""

from __future__ import annotations

from typing import Optional

from app.services.history import HistoryService
from app.services.queue_manager import QueueManager
from app.services.settings_store import SettingsStore

history: Optional[HistoryService] = None
queue_manager: Optional[QueueManager] = None
settings_store: Optional[SettingsStore] = None


def init_extensions() -> None:
    global history, queue_manager, settings_store
    if history is None:
        history = HistoryService()
    if settings_store is None:
        settings_store = SettingsStore()
    if queue_manager is None:
        queue_manager = QueueManager(
            history=history,
            settings=settings_store,
            max_workers=settings_store.get_all()["concurrency"],
        )
