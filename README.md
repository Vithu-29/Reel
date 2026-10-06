# Reel — a personal media downloader

A self-hosted Flask app around [yt-dlp](https://github.com/yt-dlp/yt-dlp): paste
a link, pick a format, download. Runs entirely on your own machine.

Supports every site yt-dlp supports, including YouTube (videos, Shorts,
playlists), Instagram (Reels/videos/posts), Facebook (videos/Reels), TikTok,
Twitter/X, Reddit, Vimeo, Dailymotion, Twitch clips, Pinterest, and public
Google Drive/Dropbox links.

> **Use responsibly.** Only download media you own the rights to, or that's
> licensed for reuse, and respect each platform's terms of service. This tool
> doesn't bypass paywalls, DRM, or private-content restrictions — it's a
> convenience wrapper around yt-dlp's public-URL extraction, nothing more.

---

## Features

- Video info preview (thumbnail, title, duration, uploader, resolutions, fps,
  codecs, approximate file size) before you commit to a download
- Format picker: MP4 / WEBM / MP3 / M4A / WAV / FLAC, with per-format video
  or audio quality options
- Playlist support: just the linked video, the entire playlist, or a
  specific `1,3,5-8`-style selection
- A real download **queue** with configurable concurrency, pause (for
  queued items), cancel (for anything), and retry
- Local **history** (SQLite) with redownload and delete
- In-app **YouTube search** (no API key needed)
- Subtitles, embedded thumbnails, embedded metadata, and optional
  SponsorBlock sponsor-segment removal
- Dashboard stats (active / queued / completed / failed / total saved)
- Dark/light theme, drag-and-drop URL input, clipboard-paste detection,
  toast notifications, keyboard shortcuts
- A documented REST API (see below) so you can drive it from scripts too

## Requirements

- Python 3.11+ (3.13 recommended)
- [ffmpeg](https://ffmpeg.org/download.html) on your system `PATH` — required
  for merging separate video/audio streams, audio extraction, and embedding
  thumbnails/metadata. Without it, only pre-merged formats will work.

## Setup

```bash
git clone <this project>
cd media-downloader
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # optional - defaults work out of the box
python run.py
```

Then open **http://127.0.0.1:5000**.

### Windows notes

- Everything here works unmodified on Windows: paths are handled with
  `pathlib`, filenames are sanitized for Windows' reserved characters
  (`windowsfilenames: True` in the yt-dlp options), and the "browse for a
  folder" button uses `tkinter`, which ships with the standard Windows
  Python installer.
- Install ffmpeg and make sure `ffmpeg.exe` is on your `PATH` (e.g. via
  `winget install ffmpeg` or by downloading a build and adding its `bin`
  folder to `PATH`).

### Logging in to sites that require an account

Some sites only serve certain content to logged-in users. yt-dlp can reuse
cookies from a browser you're already logged into — set **one** of these in
`.env`:

```
COOKIES_FROM_BROWSER=chrome
# or
COOKIES_FILE=/path/to/cookies.txt
```

## Project structure

```
app/
    config.py            Env-driven configuration
    factory.py            Flask application factory
    extensions.py          Process-wide service singletons
    models/
        schemas.py          DownloadRequest / QueueItem dataclasses
    services/
        downloader.py        yt-dlp wrapper: info + download execution
        queue_manager.py       Thread-pool queue: pause/resume/cancel/retry
        history.py              SQLite download history
        search.py                 YouTube search via yt-dlp
        settings_store.py          Persisted user preferences (JSON)
    routes/
        pages.py               Serves the single-page UI
        api.py                    All /api/* REST endpoints
    utils/
        validators.py            URL / filename / path-traversal guards
        logger.py                  Rotating file + console logging
    templates/index.html        Single-page app shell
    static/
        css/style.css             Design system + components
        js/                         utils, downloads, history, search, settings, app
run.py                          Entry point
requirements.txt
.env.example
```

## REST API

All endpoints are under `/api`.

| Method | Path                        | Purpose                                 |
|--------|------------------------------|-------------------------------------------|
| GET    | `/info?url=&playlist_mode=` | Video/playlist metadata preview           |
| GET    | `/formats`                  | Supported containers/qualities            |
| POST   | `/download`                 | Add a download to the queue               |
| GET    | `/progress/<task_id>`       | Server-Sent Events progress stream        |
| GET    | `/queue`                    | All queue items + dashboard stats         |
| GET    | `/stats`                    | Dashboard stats only                      |
| POST   | `/queue/<task_id>/pause`    | Pause a **queued** item                   |
| POST   | `/queue/<task_id>/resume`   | Resume a paused item                      |
| POST   | `/queue/<task_id>/cancel`   | Cancel a queued **or active** item        |
| POST   | `/queue/<task_id>/retry`    | Re-queue a failed/canceled item           |
| POST   | `/queue/clear-completed`    | Remove finished/failed/canceled items     |
| POST   | `/queue/clear`              | Cancel + remove everything                |
| GET    | `/download-file/<task_id>`  | Download a finished browser-mode file     |
| GET    | `/history`                  | Download history                          |
| DELETE | `/history/<id>`             | Delete one history entry                  |
| DELETE | `/history`                  | Clear all history                         |
| POST   | `/history/<id>/redownload`  | Re-queue a past download                  |
| GET    | `/search?q=`                | Search YouTube                            |
| POST   | `/browse-directory`         | Native folder picker (desktop use only)   |
| GET/POST | `/settings`                | Read/update persisted preferences       |
| POST   | `/update-ytdlp`             | `pip install --upgrade yt-dlp`            |

`POST /download` body:

```json
{
  "url": "https://youtube.com/watch?v=...",
  "container": "mp4",
  "video_quality": "1080p",
  "audio_only": false,
  "audio_quality": "best",
  "playlist_mode": "single",
  "playlist_items": "",
  "download_subtitles": false,
  "embed_thumbnail": false,
  "embed_metadata": true,
  "sponsorblock": false,
  "save_path": ""
}
```

Leave `save_path` blank to have the file served back through your browser;
set it to an absolute, writable, existing folder to have the server save it
there directly instead.

## Known limitations (by design)

- **Pausing an active download isn't supported.** yt-dlp has no supported
  way to pause and resume a partially-downloaded stream. "Pause" only
  applies to items still sitting in the queue, before they've started —
  once a download is running, you can cancel it, not pause it.
- **Clipboard "monitoring"** checks the clipboard when the browser tab
  regains focus (with your permission), not continuously in the
  background — browsers don't allow background clipboard polling for
  privacy reasons.
- **Playlist progress** reflects the current item within the playlist, not
  overall playlist completion, since yt-dlp downloads a playlist as one
  continuous operation.
- **The folder-picker button** opens a native OS dialog *on the machine
  running the Flask process*. That's your own desktop for local use, but
  will fail gracefully (with a message asking you to type the path) on a
  headless server.
- **Concurrency limits are per-process.** Run with a single worker process
  (see below) — multiple worker processes would each keep their own,
  disconnected queue and history cache.

## Running in production

This is built for personal/local use, but if you expose it beyond
`127.0.0.1`:

```bash
gunicorn -w 1 -b 0.0.0.0:5000 "run:app"             # Linux/macOS
waitress-serve --host=0.0.0.0 --port=5000 run:app   # Windows
```

Use exactly **one** worker process — the queue, history, and settings
singletons live in that process's memory. Put it behind a reverse proxy
(nginx/Caddy) with HTTPS if it's reachable outside your own machine, and set
`SECRET_KEY` and `ALLOWED_ORIGINS` in `.env`.

## Code style

```bash
black .
ruff check .
```

## License

For personal use. yt-dlp is licensed separately under the Unlicense — see
their repository for details.
