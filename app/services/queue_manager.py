"""
In-process download queue.

Design notes (read this before changing behaviour):

- A small pool of daemon worker threads pulls task ids off a `queue.Queue`.
  The number of workers *is* the concurrency limit - there is no separate
  semaphore to keep in sync.
- Pausing only ever applies to a task that hasn't started running yet.
  yt-dlp has no supported way to pause and resume a partially-downloaded
  file mid-stream, so we don't pretend to offer that: an active download
  can only be canceled, not paused. This is called out in the README.
- Canceling an active download raises `DownloadCancelled` from inside
  yt-dlp's progress hook (see services/downloader.py), which is yt-dlp's
  own documented mechanism for aborting a download in progress.
"""

from __future__ import annotations

import os
import queue
import threading
from typing import Any, Optional
from uuid import uuid4

from app.config import Config
from app.models.schemas import DownloadRequest, QueueItem, TaskStatus
from app.services import downloader
from app.services.history import HistoryService
from app.utils.logger import get_logger
from app.utils.validators import validate_save_directory

log = get_logger(__name__)


class QueueManager:
    def __init__(self, history: HistoryService, settings=None, max_workers: int | None = None):
        self._history = history
        self._settings = settings  # SettingsStore - optional so tests can omit it
        self._tasks: dict[str, QueueItem] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._paused_ids: set[str] = set()
        self._lock = threading.RLock()
        self._pending: "queue.Queue[str]" = queue.Queue()
        self._max_workers = max(1, min(10, int(max_workers or Config.MAX_CONCURRENT_DOWNLOADS)))
        self._worker_threads: list[threading.Thread] = []
        self._condition = threading.Condition(self._lock)
        self._active_workers = 0
        for i in range(10):
            self._spawn_worker(i)

    # -- worker plumbing -----------------------------------------------

    def _spawn_worker(self, index: int) -> None:
        t = threading.Thread(
            target=self._worker_loop,
            args=(index,),
            daemon=True,
            name=f"dl-worker-{index}",
        )
        self._worker_threads.append(t)
        t.start()

    def set_concurrency(self, n: int) -> None:
        n = max(1, min(n, 10))
        with self._condition:
            self._max_workers = n
            self._condition.notify_all()
        log.info("Queue concurrency set to %s", n)

    def _worker_loop(self, index: int) -> None:
        while True:
            task_id = self._pending.get()
            with self._condition:
                self._condition.wait_for(lambda: self._active_workers < self._max_workers)
                self._active_workers += 1
            try:
                self._run_task(task_id)
            except Exception:
                log.exception("Unexpected queue worker failure")
            finally:
                with self._condition:
                    self._active_workers -= 1
                    self._condition.notify_all()
                self._pending.task_done()

    # -- public API -------------------------------------------------------

    def add(self, req: DownloadRequest) -> str:
        task_id = uuid4().hex
        item = QueueItem(task_id=task_id, url=req.url, options=req, status=TaskStatus.QUEUED.value)
        with self._lock:
            self._tasks[task_id] = item
            self._cancel_events[task_id] = threading.Event()
        self._pending.put(task_id)
        return task_id

    def get(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            item = self._tasks.get(task_id)
            return item.public_dict() if item else None

    def get_all(self) -> list[dict[str, Any]]:
        with self._lock:
            items = sorted(self._tasks.values(), key=lambda i: i.created_at, reverse=True)
            return [i.public_dict() for i in items]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            items = list(self._tasks.values())
        active = sum(
            1
            for i in items
            if i.status
            in (
                TaskStatus.DOWNLOADING.value,
                TaskStatus.PROCESSING.value,
                TaskStatus.STARTING.value,
            )
        )
        completed = sum(1 for i in items if i.status == TaskStatus.FINISHED.value)
        failed = sum(
            1 for i in items if i.status in (TaskStatus.ERROR.value, TaskStatus.CANCELED.value)
        )
        queued = sum(
            1 for i in items if i.status in (TaskStatus.QUEUED.value, TaskStatus.PAUSED.value)
        )
        total_bytes = sum(i.total_bytes for i in items if i.status == TaskStatus.FINISHED.value)
        return {
            "active": active,
            "completed": completed,
            "failed": failed,
            "queued": queued,
            "total_downloaded_bytes": total_bytes,
            "concurrency": self._max_workers,
        }

    def pause(self, task_id: str) -> bool:
        with self._lock:
            item = self._tasks.get(task_id)
            if not item or item.status != TaskStatus.QUEUED.value:
                return False
            item.status = TaskStatus.PAUSED.value
            self._paused_ids.add(task_id)
            return True

    def resume(self, task_id: str) -> bool:
        with self._lock:
            item = self._tasks.get(task_id)
            if not item or item.status != TaskStatus.PAUSED.value:
                return False
            item.status = TaskStatus.QUEUED.value
            self._paused_ids.discard(task_id)
        self._pending.put(task_id)
        return True

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            item = self._tasks.get(task_id)
            if not item:
                return False
            if item.status in (TaskStatus.QUEUED.value, TaskStatus.PAUSED.value):
                item.status = TaskStatus.CANCELED.value
                self._paused_ids.discard(task_id)
                return True
            if item.status in (
                TaskStatus.STARTING.value,
                TaskStatus.DOWNLOADING.value,
                TaskStatus.PROCESSING.value,
            ):
                self._cancel_events[task_id].set()
                return True
            return False

    def retry(self, task_id: str) -> Optional[str]:
        with self._lock:
            item = self._tasks.get(task_id)
            if not item or item.status not in (
                TaskStatus.ERROR.value,
                TaskStatus.CANCELED.value,
            ):
                return None
        return self.add(item.options)

    def remove_completed(self) -> int:
        removed = 0
        with self._lock:
            done_states = {
                TaskStatus.FINISHED.value,
                TaskStatus.ERROR.value,
                TaskStatus.CANCELED.value,
            }
            for tid in [t for t, i in self._tasks.items() if i.status in done_states]:
                del self._tasks[tid]
                self._cancel_events.pop(tid, None)
                removed += 1
        return removed

    def clear_all(self) -> int:
        with self._lock:
            for tid, item in self._tasks.items():
                if item.status in (
                    TaskStatus.DOWNLOADING.value,
                    TaskStatus.PROCESSING.value,
                    TaskStatus.STARTING.value,
                ):
                    self._cancel_events[tid].set()
            count = len(self._tasks)
            self._tasks.clear()
            self._cancel_events.clear()
            self._paused_ids.clear()
        # Drain anything still sitting in the pending queue so it doesn't
        # get picked up and re-created a moment later.
        try:
            while True:
                self._pending.get_nowait()
                self._pending.task_done()
        except queue.Empty:
            pass
        return count

    # -- execution ---------------------------------------------------------

    def _run_task(self, task_id: str) -> None:
        with self._lock:
            item = self._tasks.get(task_id)
            if item is None:
                return
            if item.status != TaskStatus.QUEUED.value:
                return  # Ignore duplicate resume IDs and tasks already started/completed.
            if task_id in self._paused_ids:
                return  # pause() flips status but leaves it out of the run
            item.status = TaskStatus.STARTING.value
            cancel_event = self._cancel_events[task_id]
            req = item.options

        server_mode = bool(req.save_path)
        if server_mode:
            target_dir = req.save_path
        else:
            # No per-download override - fall back to the persisted default
            # from Settings, not the hardcoded project folder.
            target_dir = (
                self._settings.get_all().get("download_folder")
                if self._settings
                else Config.DEFAULT_DOWNLOAD_FOLDER
            )
            target_dir = target_dir or Config.DEFAULT_DOWNLOAD_FOLDER

        try:
            save_dir = validate_save_directory(target_dir)
        except Exception as exc:
            self._finish_with_error(
                task_id,
                f"Cannot save to {target_dir}: {downloader.friendly_error(exc)} "
                "Check the download folder in Settings or the per-download folder override.",
            )
            return

        def on_progress(evt: downloader.ProgressEvent) -> None:
            with self._lock:
                it = self._tasks.get(task_id)
                if not it:
                    return
                it.status = evt.status
                it.percent = evt.percent
                it.speed = evt.speed
                it.eta = evt.eta
                if evt.status == "downloading":
                    it.downloaded_bytes = evt.downloaded_bytes
                    it.total_bytes = evt.total_bytes
                if evt.filename:
                    it.filename = os.path.basename(evt.filename)

        def should_cancel() -> bool:
            return cancel_event.is_set()

        try:
            info = downloader.run_download(req, save_dir, on_progress, should_cancel)
            filepath = downloader.resolve_final_filepath(info, req, save_dir)
            with self._lock:
                it = self._tasks.get(task_id)
                if it is None:
                    return  # Clear queue was pressed while the download was finishing.
                if cancel_event.is_set():
                    it.status = TaskStatus.CANCELED.value
                    return
                it.files = info.get("_output_files", [filepath])
                it.total_bytes = sum(os.path.getsize(f) for f in it.files if os.path.isfile(f))
                it.downloaded_bytes = it.total_bytes
                it.status = TaskStatus.FINISHED.value
                it.percent = 100.0
                it.filepath = filepath
                it.filename = os.path.basename(filepath) if filepath else it.filename
                it.title = info.get("title", it.title)
                it.thumbnail = info.get("thumbnail")
            self._history.add_entry(
                filename=it.filename or "unknown",
                url=req.url,
                resolution=req.video_quality,
                container=req.container,
                status="finished",
                filepath=filepath,
            )
        except downloader.DownloadCanceled:
            with self._lock:
                it = self._tasks.get(task_id)
                if it is not None:
                    it.status = TaskStatus.CANCELED.value
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            log.exception("Download failed for task %s", task_id)
            self._finish_with_error(task_id, downloader.friendly_error(exc))

    def _finish_with_error(self, task_id: str, message: str) -> None:
        with self._lock:
            item = self._tasks.get(task_id)
            if not item:
                return
            item.status = TaskStatus.ERROR.value
            item.error = message
        self._history.add_entry(
            filename=item.filename or item.url,
            url=item.url,
            resolution=item.options.video_quality,
            container=item.options.container,
            status="error",
            error=message,
        )
