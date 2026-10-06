"""
Typed data structures shared by the services and API layer.

Plain dataclasses are used (rather than Pydantic) to avoid an extra
dependency for a project this size - swap in Pydantic `BaseModel`s here
if you later want request-body validation/coercion for free.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from time import time
from typing import Any, Optional


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PAUSED = "paused"
    STARTING = "starting"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    FINISHED = "finished"
    ERROR = "error"
    CANCELED = "canceled"


class PlaylistMode(str, Enum):
    SINGLE = "single"  # just the linked video, even if it's inside a playlist
    ENTIRE = "entire"  # every item in the playlist
    SELECTED = "selected"  # a specific comma/range list of playlist items


@dataclass
class DownloadRequest:
    url: str
    container: str = "mp4"  # mp4 | webm | mp3 | m4a | wav | flac
    video_quality: str = "best"  # best | 2160p | 1440p | 1080p | 720p | 480p | 360p
    audio_only: bool = False
    audio_quality: str = "best"  # best | 320 | 256 | 192 | 128 (kbps)
    playlist_mode: str = PlaylistMode.SINGLE.value
    playlist_items: str = ""  # e.g. "1,3,5-8" - only used when playlist_mode == selected
    download_subtitles: bool = False
    embed_thumbnail: bool = False
    embed_metadata: bool = True
    sponsorblock: bool = False
    save_path: str = ""  # blank -> server default folder, browser-delivered

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QueueItem:
    task_id: str
    url: str
    options: DownloadRequest
    status: str = TaskStatus.QUEUED.value
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    percent: float = 0.0
    speed: Optional[str] = None
    eta: Optional[str] = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    filename: Optional[str] = None
    filepath: Optional[str] = None
    files: list[str] = field(default_factory=list)
    error: Optional[str] = None
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)

    def public_dict(self) -> dict[str, Any]:
        """A JSON-serialisable snapshot safe to send to the browser."""
        d = asdict(self)
        d["options"] = self.options.to_dict()
        return d
