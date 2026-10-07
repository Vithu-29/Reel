from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time

from flask import Blueprint, Response, jsonify, request, send_file

from app import extensions
from app.config import Config
from app.models.schemas import DownloadRequest
from app.services import diagnostics, downloader
from app.services import search as search_service
from app.utils.logger import get_logger
from app.utils.validators import ValidationError, validate_media_url, validate_save_directory

log = get_logger(__name__)
api_bp = Blueprint("api", __name__)
_update_lock = threading.Lock()

# Static option lists the frontend renders into <select> elements. Kept in
# one place so the UI can never drift from what the backend actually
# understands.
SUPPORTED_CONTAINERS = ["mp4", "webm", "mp3", "m4a", "wav", "flac"]
SUPPORTED_VIDEO_QUALITIES = ["best", "2160p", "1440p", "1080p", "720p", "480p", "360p"]
SUPPORTED_AUDIO_QUALITIES = ["best", "320", "256", "192", "128"]


def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


@api_bp.get("/formats")
def formats():
    return jsonify(
        {
            "containers": SUPPORTED_CONTAINERS,
            "video_qualities": SUPPORTED_VIDEO_QUALITIES,
            "audio_qualities": SUPPORTED_AUDIO_QUALITIES,
        }
    )


@api_bp.get("/info")
def info():
    url = request.args.get("url", "")
    playlist_mode = request.args.get("playlist_mode", "single")
    if playlist_mode not in {"single", "entire", "selected"}:
        return _error("Invalid playlist mode.")
    try:
        url = validate_media_url(url)
        data = downloader.extract_info(url, playlist_mode=playlist_mode)
    except ValidationError as exc:
        return _error(str(exc), 400)
    except downloader.DownloadError as exc:
        return _error(f"Could not read that URL: {downloader.friendly_error(exc)}", 422)
    except Exception as exc:  # noqa: BLE001
        log.exception("info() failed")
        return _error(f"Unexpected error reading video info: {exc}", 500)
    return jsonify(data)


@api_bp.post("/download")
def start_download():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error("A JSON object is required.")
    for name in (
        "url",
        "container",
        "video_quality",
        "video_format_id",
        "audio_quality",
        "playlist_mode",
        "playlist_items",
        "save_path",
    ):
        if name in body and not isinstance(body[name], str):
            return _error(f"{name} must be text.")
    for name in (
        "audio_only",
        "download_subtitles",
        "embed_thumbnail",
        "embed_metadata",
        "sponsorblock",
    ):
        if name in body and not isinstance(body[name], bool):
            return _error(f"{name} must be true or false.")
    try:
        url = validate_media_url(body.get("url", ""))
        req = DownloadRequest(
            url=url,
            container=body.get("container", "mp4"),
            video_quality=body.get("video_quality", "best"),
            video_format_id=body.get("video_format_id", ""),
            audio_only=bool(body.get("audio_only", False)),
            audio_quality=body.get("audio_quality", "best"),
            playlist_mode=body.get("playlist_mode", "single"),
            playlist_items=body.get("playlist_items", ""),
            download_subtitles=bool(body.get("download_subtitles", False)),
            embed_thumbnail=bool(body.get("embed_thumbnail", False)),
            embed_metadata=bool(body.get("embed_metadata", True)),
            sponsorblock=bool(body.get("sponsorblock", False)),
            save_path=body.get("save_path", "").strip(),
        )
    except ValidationError as exc:
        return _error(str(exc), 400)

    if req.container not in SUPPORTED_CONTAINERS:
        return _error("Unsupported container/format.", 400)
    if req.video_quality not in SUPPORTED_VIDEO_QUALITIES:
        return _error("Unsupported video quality.", 400)

    if len(req.video_format_id) > 200 or any(ord(c) < 32 for c in req.video_format_id):
        return _error("Invalid source format ID.")
    if req.video_format_id and (
        req.playlist_mode != "single" or req.audio_only or req.container not in {"mp4", "webm"}
    ):
        return _error("Source video formats can only be selected for a single video download.")
    if req.audio_quality not in SUPPORTED_AUDIO_QUALITIES:
        return _error("Unsupported audio quality.")
    if req.playlist_mode not in {"single", "entire", "selected"}:
        return _error("Invalid playlist mode.")
    if req.playlist_mode == "selected" and not re.fullmatch(
        r"[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*", req.playlist_items
    ):
        return _error("Enter playlist items like 1,3,5-8.")
    if req.save_path:
        try:
            validate_save_directory(req.save_path)
        except ValidationError as exc:
            return _error(str(exc))
    if not diagnostics.ffmpeg_available():
        return _error(
            "FFmpeg/ffprobe missing. See Settings → Download engine, then restart the app.", 422
        )
    task_id = extensions.queue_manager.add(req)
    return jsonify({"task_id": task_id}), 201


@api_bp.get("/progress/<task_id>")
def progress(task_id: str):
    def generate():
        last = None
        while True:
            item = extensions.queue_manager.get(task_id)
            if item is None:
                yield f"data: {json.dumps({'status': 'error', 'error': 'Unknown task'})}\n\n"
                break
            if item != last:
                yield f"data: {json.dumps(item)}\n\n"
                last = item
            if item["status"] in ("finished", "error", "canceled"):
                break
            time.sleep(0.4)

    return Response(generate(), mimetype="text/event-stream")


@api_bp.get("/queue")
def get_queue():
    return jsonify(
        {
            "items": extensions.queue_manager.get_all(),
            "stats": extensions.queue_manager.stats(),
        }
    )


@api_bp.get("/stats")
def get_stats():
    return jsonify(extensions.queue_manager.stats())


@api_bp.post("/queue/<task_id>/pause")
def pause_task(task_id: str):
    ok = extensions.queue_manager.pause(task_id)
    return (jsonify({"ok": True}), 200) if ok else _error("Task cannot be paused right now.", 409)


@api_bp.post("/queue/<task_id>/resume")
def resume_task(task_id: str):
    ok = extensions.queue_manager.resume(task_id)
    return (jsonify({"ok": True}), 200) if ok else _error("Task cannot be resumed right now.", 409)


@api_bp.post("/queue/<task_id>/cancel")
def cancel_task(task_id: str):
    ok = extensions.queue_manager.cancel(task_id)
    return (jsonify({"ok": True}), 200) if ok else _error("Task cannot be canceled.", 409)


@api_bp.post("/queue/<task_id>/retry")
def retry_task(task_id: str):
    new_id = extensions.queue_manager.retry(task_id)
    if not new_id:
        return _error("Only failed or canceled tasks can be retried.", 409)
    return jsonify({"task_id": new_id})


@api_bp.post("/queue/clear-completed")
def clear_completed():
    n = extensions.queue_manager.remove_completed()
    return jsonify({"removed": n})


@api_bp.post("/queue/clear")
def clear_queue():
    n = extensions.queue_manager.clear_all()
    return jsonify({"removed": n})


@api_bp.get("/download-file/<task_id>")
def download_file(task_id: str):
    item = extensions.queue_manager.get(task_id)
    if not item or item["status"] != "finished" or not item.get("filepath"):
        return _error("File is not ready.", 404)
    try:
        index = int(request.args.get("index", "0"))
        files = item.get("files") or [item["filepath"]]
        if index < 0 or index >= len(files):
            return _error("Unknown output file.", 404)
        return send_file(files[index], as_attachment=True)
    except (FileNotFoundError, OSError, ValueError):
        return _error("That file is no longer on disk.", 404)


@api_bp.get("/history")
def get_history():
    return jsonify({"items": extensions.history.get_all()})


@api_bp.delete("/history/<int:entry_id>")
def delete_history(entry_id: int):
    ok = extensions.history.delete(entry_id)
    return (jsonify({"ok": True}), 200) if ok else _error("Not found.", 404)


@api_bp.delete("/history")
def clear_history():
    extensions.history.clear()
    return jsonify({"ok": True})


@api_bp.post("/history/<int:entry_id>/redownload")
def redownload(entry_id: int):
    entry = extensions.history.get(entry_id)
    if not entry:
        return _error("Not found.", 404)
    try:
        req = DownloadRequest(
            url=validate_media_url(entry["url"]),
            container=entry.get("container") or "mp4",
            video_quality=entry.get("resolution") or "best",
        )
    except ValidationError as exc:
        return _error(str(exc), 400)
    if len(req.video_format_id) > 200 or any(ord(c) < 32 for c in req.video_format_id):
        return _error("Invalid source format ID.")
    if req.video_format_id and (
        req.playlist_mode != "single" or req.audio_only or req.container not in {"mp4", "webm"}
    ):
        return _error("Source video formats can only be selected for a single video download.")
    if req.audio_quality not in SUPPORTED_AUDIO_QUALITIES:
        return _error("Unsupported audio quality.")
    if req.playlist_mode not in {"single", "entire", "selected"}:
        return _error("Invalid playlist mode.")
    if req.playlist_mode == "selected" and not re.fullmatch(
        r"[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*", req.playlist_items
    ):
        return _error("Enter playlist items like 1,3,5-8.")
    if req.save_path:
        try:
            validate_save_directory(req.save_path)
        except ValidationError as exc:
            return _error(str(exc))
    if not diagnostics.ffmpeg_available():
        return _error(
            "FFmpeg/ffprobe missing. See Settings → Download engine, then restart the app.", 422
        )
    task_id = extensions.queue_manager.add(req)
    return jsonify({"task_id": task_id}), 201


@api_bp.get("/search")
def search():
    q = request.args.get("q", "")
    if not q.strip():
        return _error("Query is required.", 400)
    try:
        results = search_service.search_youtube(q, max_results=int(request.args.get("limit", 12)))
    except Exception as exc:  # noqa: BLE001
        log.exception("search() failed")
        return _error(f"Search failed: {exc}", 500)
    return jsonify({"results": results})


@api_bp.post("/browse-directory")
def browse_directory():
    """Open a native folder picker on the machine running the server.

    Only meaningful when the server runs on your own desktop - a headless
    server has no display, and this will return a clear error instead of
    hanging.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory()
        root.destroy()
        return jsonify({"path": path})
    except Exception as exc:  # noqa: BLE001
        return _error(
            "Could not open a folder picker on this machine (no display available?). "
            f"Type the path manually. Details: {exc}",
            500,
        )


@api_bp.get("/settings")
def get_settings():
    return jsonify(extensions.settings_store.get_all())


@api_bp.post("/settings")
def update_settings():
    patch = request.get_json(silent=True)
    if not isinstance(patch, dict):
        return _error("A JSON object is required.")
    if "concurrency" in patch and (
        type(patch["concurrency"]) is not int or not 1 <= patch["concurrency"] <= 10
    ):
        return _error("Concurrency must be an integer from 1 to 10.")
    if "download_folder" in patch and not isinstance(patch["download_folder"], str):
        return _error("Download folder must be text.")
    for key in ("sponsorblock_default", "embed_metadata_default"):
        if key in patch and not isinstance(patch[key], bool):
            return _error(f"{key} must be true or false.")
    if "theme" in patch and patch["theme"] not in ("dark", "light"):
        return _error("Theme must be dark or light.")

    if "download_folder" in patch and patch["download_folder"]:
        try:
            patch["download_folder"] = validate_save_directory(patch["download_folder"])
        except ValidationError as exc:
            return _error(f"Default download folder: {exc}", 400)

    updated = extensions.settings_store.update(patch)
    if "concurrency" in patch:
        try:
            extensions.queue_manager.set_concurrency(int(patch["concurrency"]))
        except (TypeError, ValueError):
            pass
    return jsonify(updated)


@api_bp.get("/system-status")
def system_status():
    return jsonify(diagnostics.report())


@api_bp.post("/update-ytdlp")
def update_ytdlp():
    """Update installed files; the running Python interpreter must be restarted."""
    if not _update_lock.acquire(blocking=False):
        return _error("An update is already running.", 409)
    try:
        stats = extensions.queue_manager.stats()
        if stats["active"] or stats["queued"]:
            return _error("Finish or clear the queue before updating.", 409)
        args = [sys.executable, "-m", "pip", "install", "--upgrade"]
        if Config.YTDLP_CHANNEL == "nightly":
            args.append("--pre")
        args.append("yt-dlp[default]")
        result = subprocess.run(args, capture_output=True, text=True, timeout=180)
        if result.returncode:
            log.error("yt-dlp update failed: %s", (result.stdout + result.stderr)[-4000:])
            return _error(
                "Update failed. See logs/app.log or run the upgrade command in your terminal.", 500
            )
        return jsonify(
            ok=True,
            restart_required=True,
            message="Update installed. Stop the server with Ctrl+C and run python run.py again to activate it.",
        )
    except Exception as exc:
        log.exception("yt-dlp update failed")
        return _error(f"Update failed: {exc}", 500)
    finally:
        _update_lock.release()
