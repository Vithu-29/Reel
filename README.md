# Reel — Personal Media Downloader

A local Python/Flask web app powered by yt-dlp and FFmpeg. Paste a media link, choose a format, and manage downloads in your browser. This update repairs the existing app and adds a single username/password account. It does not add new platform-specific integrations.

## Windows: update and run

1. Extract this ZIP into a new folder. Keep your old folder as a backup. The ZIP retains the supplied history database, settings, logs and downloaded file; no login account or session secret is included.
2. Install **Python 3.11 or newer**, **FFmpeg** (both `ffmpeg` and `ffprobe`) and either **Node.js 22+** or **Deno 2.3+**. Add the executables to PATH, then open a new terminal.
   - Python: https://www.python.org/downloads/
   - FFmpeg: https://ffmpeg.org/download.html
   - Node.js: https://nodejs.org/en/download
   - Deno: https://docs.deno.com/runtime/getting_started/installation/
3. Open PowerShell in the extracted `MyVideoDownloader` folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
.\.venv\Scripts\python.exe manage.py set-user
.\.venv\Scripts\python.exe run.py
```

The account command asks for a username, password and password confirmation. Password input is hidden while typing. Use at least 10 characters. There is **no default password**, email requirement or registration page.

4. Open http://127.0.0.1:5000 and sign in.
5. Open **Settings → Download engine**. Confirm FFmpeg, JavaScript runtime and EJS are available.

You do not need to activate the virtual environment when using the commands above. If PowerShell blocks activation scripts, these commands still work.

## Linux / macOS

Install Python 3.11+, FFmpeg and Node.js 22+ or Deno 2.3+ using your system package manager or the official links above.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --upgrade -r requirements.txt
.venv/bin/python manage.py set-user
.venv/bin/python run.py
```

## Authentication

- One local account, username/password only; password stored as a Werkzeug scrypt hash in `data/auth.db`.
- The dashboard and **all API routes**, file downloads, settings, history and updates require login.
- Session lifetime is 12 hours; cookies use HttpOnly and SameSite=Lax. State-changing requests require a CSRF token.
- Five login attempts per client IP per five minutes. The throttle is local to the single server process and resets on restart.
- Sign out is available above the dashboard, including on mobile.
- Reset or change the account by running `manage.py set-user` again. It replaces the single account and invalidates existing sessions; it keeps download history.
- The app generates a persistent random signing key in `data/session.key` unless a `SECRET_KEY` is explicitly configured.
- Keep `HOST=127.0.0.1` for your own computer. For access from another device, the server is still the machine that stores and processes downloads. Use HTTPS and `SESSION_COOKIE_SECURE=true` if exposing it beyond localhost. This is a personal single-user app, not a multi-tenant service.

## What changed

- Upgraded to the current verified stable yt-dlp baseline **2026.08.19** and its default extras, including **yt-dlp-ejs 0.8.0**. Tested with **Flask 3.1.3**.
- Added automatic detection of supported Deno/Node runtimes for modern YouTube extraction, optional explicit executable paths, and FFmpeg checks.
- `.env` now loads before configuration. A custom `DATA_DIR` also controls the default history/settings paths.
- Removed the forced old browser user-agent; yt-dlp can use its maintained defaults. Optional `HTTP_USER_AGENT` still works.
- Extractor warnings are now logged, with actionable guidance for HTTP 403 failures.
- Updates install `yt-dlp[default]`, refuse to run with queued/active downloads, and explicitly tell you to restart. Updating installed files does not replace modules already loaded by Python.
- Fixed queue duplication after pause/resume, worker races when clearing a running task, and changing concurrency without spawning duplicate worker indexes.
- Tracks final output filenames after conversion. It no longer guesses the newest file in the download folder, which could serve an unrelated file.
- Downloads go directly into the folder chosen in Settings, unless a per-download folder overrides it. Filenames include a unique suffix so simultaneous downloads and different qualities do not overwrite each other. Existing downloaded files remain unchanged.
- Existing playlist downloads expose a Save button for each reported media output. Downloaded subtitle sidecars remain on the server.
- Fixed stale link preview responses and improved input validation. Unsupported thumbnail embedding is omitted for WebM/WAV.
- Kept existing tabs, format choices, search, history, queue controls, theme and settings.

## Existing options

| Area | Options |
|---|---|
| Video | MP4/WebM output; detected source formats for individual videos, automatic selection, or per-item quality caps for playlists |
| Audio | MP3, M4A, WAV, FLAC; best or 128/192/256/320 kbps where applicable |
| Extras | English subtitles where available, supported thumbnail embedding, metadata, optional SponsorBlock |
| Playlists | Single linked video, entire playlist, selected indexes such as `1,3,5-8` |
| Queue | Concurrency 1–10, pause queued jobs, resume, cancel, retry, clear |
| Files | Settings download folder or per-download override on the server machine; optional browser copy |

Resolution is a maximum cap, not a guarantee that the source contains that quality. WAV/FLAC are lossless output formats; converting a compressed source does not recover lost detail. MP4 selection prefers available MP4 video and M4A audio before a fallback conversion. This does not guarantee H.264 hardware compatibility on every player.

Active downloads cannot be paused by this UI. Pause only applies to waiting jobs. Cancellation is cooperative and may wait until yt-dlp emits its next progress/postprocessing callback. A finished file can remain on disk after cancellation. Clearing queue/history does not delete downloaded files. The queue is in memory and resets when the app restarts; history and settings persist. Browser Save links are tied to the current queue; existing files remain accessible through your filesystem after restarting.

## Updates and 403 troubleshooting

The supplied logs contain repeated `HTTP Error 403: Forbidden` failures. Outdated extractors and missing current YouTube runtime dependencies are plausible contributors; the logs alone do not establish one universal cause.

1. Check **Settings → Download engine**.
2. Finish or clear the queue, click **Update yt-dlp**, stop the server with Ctrl+C and start it again.
3. To update manually on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade "yt-dlp[default]"
```

4. If stable still fails, upstream recommends trying the nightly build. Stop the app first:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade --pre "yt-dlp[default]"
```

Set `YTDLP_CHANNEL=nightly` in `.env` if you want the in-app button to request nightlies subsequently.

5. Some links require a login or are unavailable in your region/session. For content your account may access, configure **one** of `COOKIES_FROM_BROWSER` or `COOKIES_FILE`. Cookie extraction varies by browser/OS. Cookies are sensitive; do not include them in source control or share them.
6. Inspect `logs/app.log`. Updating cannot guarantee every link, bypass platform restrictions or resolve all network/IP/token requirements. Do not disable TLS certificate verification to work around a certificate error.

Upstream documentation:
- https://github.com/yt-dlp/yt-dlp/releases/latest
- https://github.com/yt-dlp/yt-dlp/wiki/EJS
- https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide

## Configuration and storage

**Download location:** Set an existing, writable absolute folder in Settings and click **Save settings**. Leave the optional server save folder on the Download tab blank to use it. New jobs save directly into that folder; completed jobs and History show their saved paths. If the folder becomes unavailable, the job fails with an explanation instead of silently switching folders. Files from earlier downloads are not moved.

**Save a copy** is optional: the file has already been saved by the app. This link downloads an additional copy through your browser, whose own download settings determine where that copy goes. When the app runs on another computer, the Settings folder belongs to that computer.

Copy `.env.example` to `.env` if you want custom paths/options. Restart after changes. Environment variables take precedence over `.env` values. Relative custom paths resolve from the server's working directory; absolute paths are recommended.

```text
app/
  config.py                 Environment configuration
  factory.py                Flask app and security setup
  routes/auth.py            Sign-in and sign-out
  routes/api.py             Download, queue, history, settings, diagnostics
  services/auth.py          Hashed account storage, sessions, CSRF, throttle
  services/downloader.py    yt-dlp options, progress and final file handling
  services/diagnostics.py   FFmpeg, runtime and package checks
  services/queue_manager.py Background download workers
  services/history.py      SQLite download history
  services/settings_store.py JSON preferences
  templates/               Dashboard and sign-in page
  static/                  CSS and JavaScript
manage.py                  Create/reset your single account
run.py                     Start the local app
serve.py                   Optional Waitress server (one process)
tests/                     Authentication and download regression tests
```

Data stays on the host running Python. Metadata/media requests go to the relevant platforms; thumbnails and the dashboard's Google Fonts are fetched by the browser. SponsorBlock sends requests to its service only when enabled.

## Optional Waitress server

```powershell
.\.venv\Scripts\python.exe serve.py
```

This reads HOST/PORT from the same configuration and uses a single process. Do not start multiple server processes against this app: each would have its own in-memory queue.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use synthetic one-second video/audio and a local HTTP server for actual yt-dlp/FFmpeg download/conversion. No third-party credentials or media are needed. See `VALIDATION.md` for the verification performed on this delivery.

Use this tool for media you have permission to download, within the relevant platform's rules.

## Available video qualities

After pasting a single-video link, the Video quality dropdown lists the source formats reported by yt-dlp: resolution, frame rate, source container, codec, HDR range when reported, and source-stream size when known. A `~` prefix means an estimate; missing sizes are explicitly labeled. DRM formats and audio-only streams are excluded from this video list.

Selecting a listed option requests that exact source format, with an appropriate audio-only track added when needed. The Format dropdown still controls the final output container; converting between containers/codecs may take additional time. Stream sizes exclude separately downloaded audio and may differ from final sizes after conversion. Format IDs are treated as literal identifiers, never executable selector expressions. If an ID is unavailable when the job starts, the app asks you to refresh the link instead of silently choosing another quality.

Automatic selection remains available. Playlists use the original per-video maximum caps because entries can have different source formats. Switching to MP3/M4A/WAV/FLAC uses the audio settings and clears the source-video selection from the request. Changing the pasted URL clears the old preview and its selected format. Retrying a queued job preserves its source choice; downloading again from history uses the saved output settings and resolves formats anew.

The included `updates/available-download-formats.patch` is an alternative to copying files: apply it to the prior login-fixed version using `git apply --check` followed by `git apply`. It includes the implementation, tests and documentation. If the check fails because your local files differ, review the differences rather than forcing the patch.
