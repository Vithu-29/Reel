"""Public format metadata and literal selection of a source video stream."""

from math import isfinite

from yt_dlp.utils import DownloadError

_VIDEO_EXTENSIONS = {"mp4", "webm", "mkv", "mov", "flv", "avi", "3gp", "ts", "m4v"}


def _number(value):
    return (
        value
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and value > 0
        else None
    )


def _is_video(fmt):
    codec = fmt.get("vcodec")
    return (
        not fmt.get("has_drm")
        and bool(fmt.get("url"))
        and (
            codec not in (None, "none", "images")
            or (codec is None and fmt.get("ext") in _VIDEO_EXTENSIONS)
        )
    )


def video_options(info):
    """Expose no media URLs, headers or cookies. Sizes refer to the source stream."""
    options = []
    seen = set()
    for fmt in info.get("formats") or []:
        identity = str(fmt.get("format_id", ""))
        if not identity or identity in seen or not _is_video(fmt):
            continue
        seen.add(identity)
        size = _number(fmt.get("filesize"))
        estimated = False
        if size is None:
            size = _number(fmt.get("filesize_approx"))
            estimated = size is not None
        if size is None and not info.get("is_live"):
            bitrate = _number(fmt.get("tbr"))
            duration = _number(info.get("duration"))
            if bitrate and duration:
                size, estimated = bitrate * 1000 * duration / 8, True
        options.append(
            {
                "format_id": identity,
                "height": _number(fmt.get("height")),
                "width": _number(fmt.get("width")),
                "fps": _number(fmt.get("fps")),
                "ext": fmt.get("ext"),
                "vcodec": fmt.get("vcodec"),
                "dynamic_range": fmt.get("dynamic_range"),
                "source_bytes": round(size) if size is not None else None,
                "size_estimated": estimated,
                "has_audio": fmt.get("acodec") not in (None, "none"),
            }
        )
    return sorted(
        options,
        key=lambda f: (f["height"] or 0, f["fps"] or 0, f["source_bytes"] or 0),
        reverse=True,
    )


def select_video_format(format_id):
    """Treat an ID as literal data, never as a yt-dlp selector expression."""

    def select(context):
        formats = context.get("formats") or []  # yt-dlp orders worst to best
        chosen = next(
            (f for f in formats if str(f.get("format_id")) == format_id and _is_video(f)), None
        )
        if chosen is None:
            raise DownloadError(
                "That video quality is no longer available. Paste the link again to refresh its qualities."
            )
        # Already contains audio, or the source does not report codec details.
        if chosen.get("acodec") != "none":
            yield chosen
            return
        audio = [
            f
            for f in reversed(formats)
            if f.get("vcodec") == "none"
            and f.get("acodec") not in (None, "none")
            and not f.get("has_drm")
            and f.get("url")
        ]
        if not audio:
            yield chosen  # genuinely silent source
            return
        preferred = {"mp4": "m4a", "webm": "webm"}.get(chosen.get("ext"))
        track = next((f for f in audio if preferred and f.get("ext") == preferred), audio[0])
        ext = chosen["ext"] if preferred and track.get("ext") == preferred else "mkv"
        yield {
            "format_id": f"{chosen['format_id']}+{track['format_id']}",
            "ext": ext,
            "requested_formats": [chosen, track],
            "protocol": f"{chosen['protocol']}+{track['protocol']}",
            "height": chosen.get("height"),
            "width": chosen.get("width"),
            "fps": chosen.get("fps"),
            "vcodec": chosen.get("vcodec"),
            "acodec": track.get("acodec"),
        }

    return select
