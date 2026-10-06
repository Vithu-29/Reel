import pytest
from conftest import csrf, sign_in

from app import extensions


@pytest.mark.parametrize(
    "path",
    [
        "/api/queue",
        "/api/history",
        "/api/settings",
        "/api/info",
        "/api/search",
        "/api/download-file/fake",
        "/api/system-status",
        "/api/progress/fake",
    ],
)
def test_private_reads_require_login(client, path):
    assert client.get(path).status_code == 401


def test_setup_is_local_only(client):
    assert client.get("/").status_code == 302
    assert b"python manage.py set-user" in client.get("/login").data
    assert client.post("/api/download", json={}).status_code == 401
    assert client.post("/api/update-ytdlp").status_code == 401


def test_login_csrf_logout_and_password_reset(app, client):
    headers = sign_in(app, client)
    assert client.get("/api/queue").status_code == 200
    assert b"correct-password-123" not in app.extensions["accounts"].get()["password_hash"].encode()
    assert client.post("/api/settings", json={"theme": "light"}).status_code == 400
    assert client.post("/api/settings", json={"theme": "light"}, headers=headers).status_code == 200
    with client.session_transaction() as s:
        old_session = dict(s)
    app.extensions["accounts"].set_user("owner", "a-new-password-123")
    assert client.get("/api/queue").status_code == 401
    sign_in(app, client)
    assert client.post("/logout", data={"csrf_token": csrf(client)}).status_code == 302
    assert client.get("/api/history").status_code == 401
    assert old_session["account_version"] != app.extensions["accounts"].get()["version"]


def test_wrong_password_and_throttle(app, client):
    app.extensions["accounts"].set_user("owner", "correct-password-123")
    client.get("/login")
    for _ in range(5):
        assert (
            client.post(
                "/login",
                data={"username": "owner", "password": "wrong", "csrf_token": csrf(client)},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/login", data={"username": "owner", "password": "wrong", "csrf_token": csrf(client)}
        ).status_code
        == 429
    )


def test_login_requires_csrf(app, client):
    app.extensions["accounts"].set_user("owner", "correct-password-123")
    assert (
        client.post(
            "/login", data={"username": "owner", "password": "correct-password-123"}
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"url": 123},
        {"url": "https://example.com/v", "audio_quality": "999"},
        {"url": "https://example.com/v", "playlist_mode": "selected", "playlist_items": "0"},
        {"url": "https://example.com/v", "audio_only": "false"},
    ],
)
def test_bad_download_input(app, client, payload):
    headers = sign_in(app, client)
    assert client.post("/api/download", json=payload, headers=headers).status_code == 400


def test_status_and_update_restart_notice(app, client, monkeypatch):
    from types import SimpleNamespace

    import app.routes.api as api

    headers = sign_in(app, client)
    assert client.get("/api/system-status").json["yt_dlp"]
    calls = []
    monkeypatch.setattr(
        api.subprocess,
        "run",
        lambda args, **kw: (
            calls.append(args) or SimpleNamespace(returncode=0, stdout="", stderr="")
        ),
    )
    response = client.post("/api/update-ytdlp", headers=headers)
    assert response.json["restart_required"] is True
    assert "yt-dlp[default]" in calls[0]
    assert (
        client.post("/api/settings", json={"concurrency": -1}, headers=headers).status_code == 400
    )


def test_queue_completion_and_file_access(app, client, monkeypatch, tmp_path):
    from app.models.schemas import DownloadRequest
    from app.services import downloader

    sign_in(app, client)
    target = tmp_path / "downloads" / "result.mp4"
    target.write_bytes(b"fixture-content")
    monkeypatch.setattr(
        downloader,
        "run_download",
        lambda *args: {"title": "Sample", "_output_files": [str(target)]},
    )
    manager = extensions.queue_manager
    monkeypatch.setattr(manager._pending, "put", lambda task: None)
    tid = manager.add(
        DownloadRequest(url="https://example.com/video", save_path=str(target.parent))
    )
    manager._run_task(tid)
    response = client.get("/api/download-file/" + tid)
    assert response.data == b"fixture-content"
    assert client.get("/api/download-file/" + tid + "?index=-1").status_code == 404
    client.post("/logout", data={"csrf_token": csrf(client)})
    assert client.get("/api/download-file/" + tid).status_code == 401


def test_template_has_csrf_and_mobile_logout(app, client):
    sign_in(app, client)
    page = client.get("/")
    assert b'name="csrf-token"' in page.data
    assert b'action="/logout"' in page.data
    assert b'id="systemStatus"' in page.data
    assert page.headers["Cache-Control"] == "no-store"


def test_dotenv_loaded_before_config(tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    (tmp_path / "app").mkdir()
    shutil.copy(root / "app/config.py", tmp_path / "app/config.py")
    (tmp_path / "app/__init__.py").write_text("")
    (tmp_path / ".env").write_text("PORT=5678\nDATA_DIR=custom-data\n")
    env = os.environ.copy()
    for key in ("PORT", "DATA_DIR", "DATABASE_PATH", "SETTINGS_PATH"):
        env.pop(key, None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.config import Config; print(Config.PORT); print(Config.DATABASE_PATH)",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "5678" in result.stdout
    assert "custom-data" in result.stdout


@pytest.mark.parametrize("background_path", ["/favicon.ico", "/missing-page", "/api/queue", "/"])
def test_background_request_does_not_expire_login(app, client, background_path):
    """Browsers request icons and old tabs poll while a login form is open."""
    app.extensions["accounts"].set_user("owner", "correct-password-123")
    client.get("/login")
    token_from_form = csrf(client)
    background = client.get(background_path)
    assert csrf(client) == token_from_form
    assert "Set-Cookie" not in background.headers
    response = client.post(
        "/login",
        data={
            "username": "owner",
            "password": "correct-password-123",
            "csrf_token": token_from_form,
        },
    )
    assert response.status_code == 302
    assert client.get("/api/queue").status_code == 200


def test_mismatched_login_token_still_rejected(app, client):
    app.extensions["accounts"].set_user("owner", "correct-password-123")
    client.get("/login")
    response = client.post(
        "/login",
        data={
            "username": "owner",
            "password": "correct-password-123",
            "csrf_token": "incorrect-token",
        },
    )
    assert response.status_code == 400
    assert client.get("/api/queue").status_code == 401


def test_password_reset_and_old_tab_do_not_invalidate_new_login_form(app, client):
    sign_in(app, client)
    app.extensions["accounts"].set_user("owner", "replacement-password-123")
    client.get("/login")
    token_from_form = csrf(client)
    assert client.get("/api/queue").status_code == 401
    assert csrf(client) == token_from_form
    response = client.post(
        "/login",
        data={
            "username": "owner",
            "password": "replacement-password-123",
            "csrf_token": token_from_form,
        },
    )
    assert response.status_code == 302
    assert client.get("/api/queue").status_code == 200
