import functools
import http.server
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
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
    assert path.parent == tmp_path
    assert path.stat().st_size > 0
    assert len(info["_output_files"]) == 1


def test_real_download_of_preview_selected_format(local_media, tmp_path):
    metadata = downloader.extract_info(local_media)
    assert metadata["video_formats"]
    source_id = metadata["video_formats"][0]["format_id"]
    req = DownloadRequest(url=local_media, container="mp4", video_format_id=source_id)
    info = downloader.run_download(req, str(tmp_path), lambda event: None, lambda: False)
    path = Path(downloader.resolve_final_filepath(info, req, str(tmp_path)))
    assert path.suffix == ".mp4"
    assert path.stat().st_size > 0


@pytest.mark.parametrize("use_override", [False, True])
def test_saved_folder_used_directly_for_concurrent_downloads(
    app, client, monkeypatch, tmp_path, local_media, use_override
):
    from conftest import sign_in

    from app import extensions
    from app.config import Config
    from app.services.settings_store import SettingsStore

    chosen = tmp_path / "My videos 100% café"
    chosen.mkdir()
    headers = sign_in(app, client)
    response = client.post(
        "/api/settings", json={"download_folder": str(chosen)}, headers=headers
    )
    assert response.status_code == 200
    manager = extensions.queue_manager
    # Reload from disk so this also checks that the saved setting survives restart.
    manager._settings = SettingsStore(Config.SETTINGS_PATH)
    monkeypatch.setattr(manager._pending, "put", lambda tid: None)
    destination = chosen
    if use_override:
        destination = tmp_path / "override"
        destination.mkdir()
    existing = destination / "sample [sample].mp4"
    existing.write_bytes(b"existing download")
    ids = [
        manager.add(DownloadRequest(
            url=local_media, save_path=str(destination) if use_override else ""
        ))
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(manager._run_task, ids))
    paths = []
    for tid in ids:
        item = manager.get(tid)
        assert item["status"] == "finished", item.get("error")
        path = Path(item["filepath"])
        assert path.parent == destination
        assert path.stat().st_size > 0
        paths.append(str(path))
        copy = client.get(f"/api/download-file/{tid}")
        assert copy.status_code == 200
        assert copy.data == path.read_bytes()
        copy.close()
    assert len(set(paths)) == 2
    assert existing.read_bytes() == b"existing download"
    assert all(path.is_file() for path in destination.iterdir())
    assert not list(Path(Config.DEFAULT_DOWNLOAD_FOLDER).iterdir())
    if use_override:
        assert not list(chosen.iterdir())
    history = extensions.history.get_all()
    assert {entry["filepath"] for entry in history} == set(paths)
    assert all(entry["status"] == "finished" for entry in history)


@pytest.mark.parametrize("unavailable", ["missing", "unwritable"])
def test_unavailable_settings_folder_never_falls_back(app, monkeypatch, tmp_path, unavailable):
    from app import extensions
    from app.config import Config
    from app.utils import validators

    chosen = tmp_path / "unavailable"
    if unavailable == "unwritable":
        chosen.mkdir()
        monkeypatch.setattr(validators.os, "access", lambda *args: False)
    extensions.settings_store.update({"download_folder": str(chosen)})
    manager = extensions.queue_manager
    monkeypatch.setattr(manager._pending, "put", lambda tid: None)

    def unexpected_download(*args):
        pytest.fail("Downloader must not run when the chosen folder is unavailable")

    monkeypatch.setattr(downloader, "run_download", unexpected_download)
    tid = manager.add(DownloadRequest(url="https://example.com/video"))
    manager._run_task(tid)
    item = manager.get(tid)
    assert item["status"] == "error"
    assert str(chosen) in item["error"]
    assert "Settings" in item["error"]
    assert not list(Path(Config.DEFAULT_DOWNLOAD_FOLDER).iterdir())
