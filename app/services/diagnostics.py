"""Report locally installed download dependencies without making network calls."""

import re
import shutil
import subprocess
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from app.config import Config


def package_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return None


@lru_cache(maxsize=16)
def executable_version(executable):
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=5
        )
        return (result.stdout or result.stderr).splitlines()[0] if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def js_runtimes():
    names = ["deno", "node"] if Config.JS_RUNTIME == "auto" else [Config.JS_RUNTIME]
    found = {}
    for name in names:
        if name not in {"deno", "node"}:
            continue
        path = (Config.JS_RUNTIME_PATH if Config.JS_RUNTIME != "auto" else "") or shutil.which(name)
        raw = executable_version(path)
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", raw or "")
        minimum = (2, 3, 0) if name == "deno" else (22, 0, 0)
        if match and tuple(map(int, match.groups())) >= minimum:
            found[name] = {"path": path}
    return found


def ffmpeg_available():
    import yt_dlp
    from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor

    opts = {"quiet": True}
    if Config.FFMPEG_LOCATION:
        opts["ffmpeg_location"] = Config.FFMPEG_LOCATION
    with yt_dlp.YoutubeDL(opts) as ydl:
        pp = FFmpegPostProcessor(ydl)
        return pp.available and bool(pp.probe_available)


def report():
    from yt_dlp.version import __version__

    runtimes = js_runtimes()
    ffmpeg = ffmpeg_available()
    ejs = package_version("yt-dlp-ejs")
    warnings = []
    if not ffmpeg:
        warnings.append("FFmpeg/ffprobe missing. Install FFmpeg and add its bin folder to PATH.")
    if not runtimes:
        warnings.append(
            "YouTube needs Deno 2.3+ or Node.js 22+ on PATH. Restart the app after installing."
        )
    if not ejs:
        warnings.append('YouTube scripts missing. Run: python -m pip install -U "yt-dlp[default]"')
    if Config.COOKIES_FILE and not Path(Config.COOKIES_FILE).is_file():
        warnings.append("The configured cookies file does not exist.")
    return {
        "yt_dlp": __version__,
        "flask": package_version("flask"),
        "ejs": ejs,
        "ffmpeg": ffmpeg,
        "js_runtimes": list(runtimes),
        "warnings": warnings,
        "update_channel": Config.YTDLP_CHANNEL,
    }
