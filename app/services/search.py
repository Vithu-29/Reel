"""In-app YouTube search, backed by yt-dlp's own ytsearch: pseudo-extractor
(no API key needed, no extra dependency).
"""

from __future__ import annotations

from typing import Any

import yt_dlp

from app.services.downloader import _common_opts
from app.utils.logger import get_logger

log = get_logger(__name__)


def search_youtube(query: str, max_results: int = 12) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        return []
    max_results = max(1, min(max_results, 30))

    opts = {
        **_common_opts(),
        "quiet": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)

    entries = (result or {}).get("entries") or []
    out = []
    for e in entries:
        if not e:
            continue
        out.append(
            {
                "id": e.get("id"),
                "title": e.get("title"),
                "url": e.get("url") or f"https://www.youtube.com/watch?v={e.get('id')}",
                "thumbnail": e.get("thumbnail") or (e.get("thumbnails") or [{}])[-1].get("url"),
                "duration": e.get("duration"),
                "uploader": e.get("uploader") or e.get("channel"),
            }
        )
    return out
