"""
Input validation helpers.

These exist to stop three concrete problems:
  1. Someone pasting a non-http(s) URL (file://, javascript:, etc).
  2. A crafted filename escaping the downloads folder (path traversal).
  3. A "server save path" that points somewhere it shouldn't.

They are deliberately simple and dependency-free.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}

# Loopback / link-local / private ranges we refuse to treat as a "public" URL
# target for the *server-side* browse feature is unrelated to this - this only
# guards the URL the user wants us to fetch media from.
_BLOCKED_HOSTS = {"localhost", "0.0.0.0"}


class ValidationError(ValueError):
    """Raised when user-supplied input fails validation."""


def validate_media_url(url: str) -> str:
    """Validate that `url` looks like a fetchable public http(s) URL.

    Returns the trimmed URL on success, raises ValidationError otherwise.
    Note: this is a shape check, not a guarantee the URL is safe or that
    yt-dlp actually supports it - yt-dlp itself will reject unsupported
    sites when extraction is attempted.
    """
    if not url or not isinstance(url, str):
        raise ValidationError("A video URL is required.")

    url = url.strip()
    if len(url) > 2048:
        raise ValidationError("URL is too long.")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValidationError("Only http:// and https:// URLs are supported.")
    if not parsed.netloc:
        raise ValidationError("That doesn't look like a valid URL.")
    if parsed.hostname and parsed.hostname.lower() in _BLOCKED_HOSTS:
        raise ValidationError("That URL is not allowed.")

    return url


_FILENAME_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, fallback: str = "download") -> str:
    """Strip anything that could act as a path separator or control char."""
    if not name:
        return fallback
    name = os.path.basename(name)  # drop any directory component outright
    name = _FILENAME_UNSAFE.sub("_", name).strip(" .")
    return name[:255] if name else fallback


def resolve_within(base_dir: str | Path, filename: str) -> Path:
    """Resolve `filename` under `base_dir`, raising if it would escape it.

    This is the path-traversal guard used before serving any file back to
    the browser - it defends against filenames like `../../etc/passwd`.
    """
    base = Path(base_dir).resolve()
    candidate = (base / sanitize_filename(filename)).resolve()
    if base not in candidate.parents and candidate != base:
        raise ValidationError("Invalid file path.")
    if not str(candidate).startswith(str(base)):
        raise ValidationError("Invalid file path.")
    return candidate


def validate_save_directory(path: str) -> str:
    """Validate a user-supplied *server-side* save directory.

    Must be an existing, writable directory. We intentionally do not try to
    silently create arbitrary directories on the host from a web request.
    """
    if not path:
        raise ValidationError("Path is empty.")
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValidationError("Please provide an absolute path.")
    if not candidate.exists():
        raise ValidationError("That folder does not exist.")
    if not candidate.is_dir():
        raise ValidationError("That path is not a folder.")
    if not os.access(candidate, os.W_OK):
        raise ValidationError("That folder is not writable.")
    return str(candidate)
