import pytest

from app import extensions
from app.config import Config
from app.factory import create_app
from app.services import settings_store


@pytest.fixture
def app(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    for key, value in {
        "DATA_DIR": data,
        "AUTH_DATABASE": str(data / "auth.db"),
        "DATABASE_PATH": str(data / "app.db"),
        "SETTINGS_PATH": str(data / "settings.json"),
        "DEFAULT_DOWNLOAD_FOLDER": str(downloads),
        "LOG_DIR": tmp_path / "logs",
        "LOG_FILE": str(tmp_path / "logs/app.log"),
        "SECRET_KEY": "test-secret-only",
    }.items():
        monkeypatch.setattr(Config, key, value)
    monkeypatch.setitem(settings_store._DEFAULTS, "download_folder", str(downloads))
    for name in ("history", "queue_manager", "settings_store"):
        monkeypatch.setattr(extensions, name, None)
    app = create_app()
    app.config["TESTING"] = True
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client):
    with client.session_transaction() as session:
        return session.get("csrf", "")


def sign_in(app, client):
    app.extensions["accounts"].set_user("owner", "correct-password-123")
    client.get("/login")
    response = client.post(
        "/login",
        data={"username": "owner", "password": "correct-password-123", "csrf_token": csrf(client)},
    )
    assert response.status_code == 302
    client.get("/")
    return {"X-CSRF-Token": csrf(client)}
