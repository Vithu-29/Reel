import functools
import http.server
import subprocess
import threading
from pathlib import Path

import pytest

from app.models.schemas import DownloadRequest
from app.services import downloader


def test_never_return_unrelated_file(tmp_path):
    (tmp_path / "unrelated.mp4").write_bytes(b"existing")
    with pytest.raises(downloader.DownloadError):
        downloader.resolve_final_filepath(
            {}, DownloadRequest(url="https://example.com"), str(tmp_path)
        )


def test_clear_running_queue_and_duplicate_resume(app, monkeypatch):
    from app import extensions

    manager = extensions.queue_manager
    monkeypatch.setattr(manager._pending, "put", lambda tid: None)
    tid = manager.add(DownloadRequest(url="https://example.com"))
    assert manager.pause(tid)
    assert manager.resume(tid)
    count = []

    def canceled(*args):
        count.append(1)
        manager.clear_all()
        raise downloader.DownloadCanceled("Canceled")

    monkeypatch.setattr(downloader, "run_download", canceled)
    manager._run_task(tid)
    manager._run_task(tid)
    assert len(count) == 1
    assert manager.get_all() == []


def test_duplicate_pending_id_downloads_once(app, monkeypatch, tmp_path):
    from app import extensions

    manager = extensions.queue_manager
    monkeypatch.setattr(manager._pending, "put", lambda tid: None)
    count = []

    def done(req, directory, *args):
        count.append(1)
        path = Path(directory) / "output.mp4"
        path.write_bytes(b"test")
        return {"title": "test", "_output_files": [str(path)]}

    monkeypatch.setattr(downloader, "run_download", done)
    tid = manager.add(DownloadRequest(url="https://example.com"))
    manager.pause(tid)
    manager.resume(tid)
    manager._run_task(tid)
    manager._run_task(tid)
    assert len(count) == 1
    assert manager.get(tid)["total_bytes"] == 4


@pytest.fixture(scope="module")
def local_media(tmp_path_factory):
    root = tmp_path_factory.mktemp("media")
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x120:r=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-y",
            str(root / "sample.mp4"),
        ],
        check=True,
    )

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(root))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/sample.mp4"
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("container", ["mp4", "mp3", "m4a", "wav", "flac", "webm"])
def test_real_download_and_conversion(local_media, container, tmp_path):
    req = DownloadRequest(url=local_media, container=container, audio_quality="192")
    info = downloader.run_download(req, str(tmp_path), lambda evt: None, lambda: False)
    path = Path(downloader.resolve_final_filepath(info, req, str(tmp_path)))
    assert path.suffix == "." + container
    assert path.stat().st_size > 0
    assert len(info["_output_files"]) == 1
