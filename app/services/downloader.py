"""
Thin, well-defined wrapper around yt-dlp.

Two responsibilities live here and nowhere else in the codebase:
  1. `extract_info`      - fetch metadata for the "video info" preview panel.
  2. `run_download`       - actually perform a download for one queue item,
                            reporting progress through a callback.

Everything queue/concurrency related lives in `queue_manager.py`; this
module knows nothing about threads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

from app.config import Config
from app.models.schemas import DownloadRequest, PlaylistMode
from app.services.diagnostics import ffmpeg_available, js_runtimes
from app.utils.logger import get_logger

log = get_logger(__name__)

# Default SponsorBlock categories to strip when the user opts in. "sponsor"
# alone is the least aggressive, highest-confidence category.
_SPONSORBLOCK_CATEGORIES = {"sponsor"}

_AUDIO_ONLY_CONTAINERS = {"mp3", "m4a", "wav", "flac"}


class DownloadCanceled(Exception):
    """Raised internally when a user cancels an in-progress download."""


@dataclass
class ProgressEvent:
    status: str
    percent: float = 0.0
    speed: Optional[str] = None
    eta: Optional[str] = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    filename: Optional[str] = None


def _common_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": False,
        "logger": log,
        "js_runtimes": js_runtimes(),
        "noprogress": True,
        # Sensible resilience defaults - a personal downloader shouldn't
        # hammer a site or hang forever on a bad connection.
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
    }
    if Config.HTTP_USER_AGENT:
        opts["http_headers"] = {"User-Agent": Config.HTTP_USER_AGENT}
    if Config.FFMPEG_LOCATION:
        opts["ffmpeg_location"] = Config.FFMPEG_LOCATION
    if Config.COOKIES_FROM_BROWSER:
        opts["cookiesfrombrowser"] = (Config.COOKIES_FROM_BROWSER,)
    if Config.COOKIES_FILE:
        opts["cookiefile"] = Config.COOKIES_FILE
    return opts


def extract_info(url: str, playlist_mode: str = PlaylistMode.SINGLE.value) -> dict[str, Any]:
    """Return a JSON-friendly metadata dict for the info/preview panel.

    Raises `yt_dlp.utils.DownloadError` on invalid/unsupported URLs - the
    caller (the API route) is responsible for turning that into a 4xx.
    """
    opts = _common_opts()
    opts.update(
        {
            "skip_download": True,
            "extract_flat": (
                "in_playlist" if playlist_mode != PlaylistMode.SINGLE.value else False
            ),
            "noplaylist": playlist_mode == PlaylistMode.SINGLE.value,
        }
    )

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise DownloadError("Could not read any information from that URL.")

    is_playlist = info.get("_type") == "playlist" or "entries" in info

    if is_playlist:
        entries = [e for e in (info.get("entries") or []) if e]
        return {
            "is_playlist": True,
            "playlist_title": info.get("title"),
            "playlist_count": len(entries),
            "entries": [
                {
                    "index": i + 1,
                    "id": e.get("id"),
                    "title": e.get("title"),
                    "duration": e.get("duration"),
                    "thumbnail": e.get("thumbnail") or (e.get("thumbnails") or [{}])[-1].get("url"),
                }
                for i, e in enumerate(entries)
            ],
        }

    formats = info.get("formats") or []
    resolutions = sorted(
        {f.get("height") for f in formats if f.get("vcodec") != "none" and f.get("height")},
        reverse=True,
    )
    audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]
    best_audio_bitrate = max((f.get("abr") or 0 for f in audio_formats), default=None)
    filesize = info.get("filesize") or info.get("filesize_approx")

    return {
        "is_playlist": False,
        "id": info.get("id"),
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "uploader": info.get("uploader"),
        "filesize_approx": filesize,
        "resolutions": resolutions,
        "fps": info.get("fps"),
        "vcodec": info.get("vcodec"),
        "acodec": info.get("acodec"),
        "audio_bitrate": best_audio_bitrate,
        "extractor": info.get("extractor_key"),
    }


def _format_selector(req: DownloadRequest) -> str:
    if req.audio_only or req.container in _AUDIO_ONLY_CONTAINERS:
        return "bestaudio/best"
    cap = "" if req.video_quality == "best" else f"[height<={int(req.video_quality.rstrip('p'))}]"
    if req.container == "mp4":
        return f"bestvideo{cap}[ext=mp4]+bestaudio[ext=m4a]/best{cap}[ext=mp4]/bestvideo{cap}+bestaudio/best{cap}"
    if req.container == "webm":
        return f"bestvideo{cap}[ext=webm]+bestaudio[ext=webm]/best{cap}[ext=webm]/bestvideo{cap}+bestaudio/best{cap}"
    return f"bestvideo{cap}+bestaudio/best{cap}"


def _build_postprocessors(req: DownloadRequest) -> list[dict[str, Any]]:
    pps: list[dict[str, Any]] = []
    is_audio_only = req.audio_only or req.container in _AUDIO_ONLY_CONTAINERS

    if is_audio_only:
        codec = req.container if req.container in _AUDIO_ONLY_CONTAINERS else "mp3"
        quality = "0" if req.audio_quality == "best" else req.audio_quality
        pps.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": quality,
            }
        )
    elif req.container in {"mp4", "webm"}:
        pps.append({"key": "FFmpegVideoConvertor", "preferedformat": req.container})

    if req.sponsorblock:
        pps.append(
            {
                "key": "SponsorBlock",
                "categories": _SPONSORBLOCK_CATEGORIES,
                "api": "https://sponsor.ajay.app",
                "when": "after_filter",
            }
        )
        pps.append(
            {
                "key": "ModifyChapters",
                "remove_sponsor_segments": _SPONSORBLOCK_CATEGORIES,
                "sponsorblock_chapter_title": "[SponsorBlock]: %(category_names)l",
            }
        )

    if req.embed_thumbnail and req.container in {"mp3", "m4a", "flac", "mp4"}:
        pps.append({"key": "EmbedThumbnail"})

    if req.embed_metadata:
        pps.append({"key": "FFmpegMetadata", "add_chapters": True})

    return pps


def build_ydl_opts(
    req: DownloadRequest,
    save_dir: str,
    progress_hook: Callable[[dict], None],
) -> dict[str, Any]:
    opts = _common_opts()

    noplaylist = req.playlist_mode == PlaylistMode.SINGLE.value
    opts.update(
        {
            "format": _format_selector(req),
            "outtmpl": f"{save_dir.rstrip('/')}/%(title).200B [%(id)s].%(ext)s",
            "restrictfilenames": False,
            "windowsfilenames": True,  # keep filenames valid on Windows too
            "noplaylist": noplaylist,
            "writethumbnail": req.embed_thumbnail
            and req.container in {"mp3", "m4a", "flac", "mp4"},
            "writesubtitles": req.download_subtitles,
            "writeautomaticsub": False,
            "subtitleslangs": ["en", "en-orig"] if req.download_subtitles else [],
            "postprocessors": _build_postprocessors(req),
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [progress_hook],
            "merge_output_format": (req.container if req.container in {"mp4", "webm"} else None),
        }
    )

    if not noplaylist and req.playlist_mode == PlaylistMode.SELECTED.value and req.playlist_items:
        opts["playlist_items"] = req.playlist_items

    return opts


def run_download(
    req: DownloadRequest,
    save_dir: str,
    on_progress: Callable[[ProgressEvent], None],
    should_cancel: Callable[[], bool],
) -> dict[str, Any]:
    """Run one download to completion. Returns yt-dlp's info dict.

    `on_progress` is called for every progress/postprocessor tick.
    `should_cancel` is polled on every tick; returning True aborts the
    download by raising DownloadCancelled from inside the hook, which is
    yt-dlp's documented mechanism for stopping a download in progress.
    """

    def hook(d: dict[str, Any]) -> None:
        if should_cancel():
            raise DownloadCancelled("Canceled by user")

        status = d.get("status", "downloading")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            percent = (downloaded / total * 100) if total else 0.0
            on_progress(
                ProgressEvent(
                    status="downloading",
                    percent=round(percent, 1),
                    speed=_human_rate(d.get("speed")),
                    eta=_human_eta(d.get("eta")),
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                    filename=d.get("filename"),
                )
            )
        elif status == "finished":
            on_progress(
                ProgressEvent(status="processing", percent=100.0, filename=d.get("filename"))
            )
        elif status == "error":
            on_progress(ProgressEvent(status="error"))

    if should_cancel():
        raise DownloadCanceled("Canceled by user")
    if not ffmpeg_available():
        raise DownloadError(
            "FFmpeg and ffprobe are required. Install FFmpeg, add its bin folder to PATH and restart the app."
        )
    output_files = []

    def after_move(filename):
        # yt-dlp invokes post_hooks with the FINAL path after conversions/moves.
        if should_cancel():
            raise DownloadCancelled("Canceled by user")
        output_files.append(str(Path(filename).resolve()))

    ydl_opts = build_ydl_opts(req, save_dir, hook)
    ydl_opts["post_hooks"] = [after_move]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
    except DownloadCancelled as exc:
        raise DownloadCanceled(str(exc)) from exc

    if should_cancel():
        raise DownloadCanceled("Canceled by user")
    if not info or not output_files:
        raise DownloadError("The download produced no media files.")
    info["_output_files"] = list(dict.fromkeys(output_files))
    return info


def resolve_final_filepath(info: dict[str, Any], req: DownloadRequest, save_dir: str) -> str:
    """Only return paths reported for THIS download, never the newest unrelated file."""
    base = Path(save_dir).resolve()
    for filename in info.get("_output_files", []):
        candidate = Path(filename).resolve()
        if candidate.is_file() and candidate.is_relative_to(base):
            return str(candidate)
    raise DownloadError("The output file could not be located. Check the download folder.")


def friendly_error(exc):
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(exc))
    if "403" in text:
        text += (
            " Try Settings → Update yt-dlp, then restart the server. Check the dependency status. "
            "Some links also require your own authorized browser session; an update alone cannot guarantee access."
        )
    return text


def _human_rate(bytes_per_sec: Optional[float]) -> Optional[str]:
    if not bytes_per_sec:
        return None
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.1f} {unit}"
        bytes_per_sec /= 1024
    return f"{bytes_per_sec:.1f} TB/s"


def _human_eta(seconds: Optional[float]) -> Optional[str]:
    if seconds is None:
        return None
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"
