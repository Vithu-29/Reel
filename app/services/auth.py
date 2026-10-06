"""Single-user authentication. No public registration or plaintext passwords."""

from __future__ import annotations

import hmac
import re
import secrets
import sqlite3
import threading
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from time import monotonic

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


class AccountStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), "
                "username TEXT NOT NULL, password_hash TEXT NOT NULL, version TEXT NOT NULL)"
            )
        self._dummy_hash = generate_password_hash(secrets.token_urlsafe(32))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM account WHERE id=1").fetchone()
            return dict(row) if row else None

    def set_user(self, username, password):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username):
            raise ValueError(
                "Use 3–64 letters, numbers, dots, underscores or hyphens for the username."
            )
        if not 10 <= len(password) <= 256:
            raise ValueError("Use a password between 10 and 256 characters.")
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO account VALUES (1, ?, ?, ?)",
                (username, generate_password_hash(password), secrets.token_urlsafe(32)),
            )

    def verify(self, username, password):
        row = self.get()
        valid = check_password_hash(row["password_hash"] if row else self._dummy_hash, password)
        return (
            row
            if row and valid and hmac.compare_digest(row["username"].encode(), username.encode())
            else None
        )


class LoginLimiter:
    """Per-process throttle, appropriate for the required single-server process."""

    def __init__(self):
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def allow(self, key):
        now = monotonic()
        with self.lock:
            attempts = [t for t in self.entries.pop(key, []) if now - t < 300]
            allowed = len(attempts) < 5
            if allowed:
                attempts.append(now)
            self.entries[key] = attempts
            while len(self.entries) > 1024:
                self.entries.popitem(last=False)
            return allowed

    def reset(self, key):
        with self.lock:
            self.entries.pop(key, None)


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def init_auth(app):
    secret = app.config.get("SECRET_KEY")
    if not secret or secret in {"dev-only-change-me", "change-me-to-something-random"}:
        path = Path(app.config["DATA_DIR"]) / "session.key"
        try:
            with path.open("x", encoding="utf-8") as f:
                f.write(secrets.token_hex(32))
            path.chmod(0o600)
        except FileExistsError:
            pass
        app.secret_key = path.read_text().strip()
    app.extensions["accounts"] = AccountStore(app.config["AUTH_DATABASE"])
    app.extensions["login_limiter"] = LoginLimiter()
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect():
        # Let Flask return normal 404/405 responses for unmatched requests
        # (including the browser's automatic /favicon.ico request).
        if request.endpoint is None or request.endpoint == "static":
            return None
        public = request.endpoint == "auth.login"
        if not public:
            account = app.extensions["accounts"].get()
            if not account or session.get("account_version") != account["version"]:
                # Keep the anonymous login form's CSRF token intact. An old
                # tab polling the API must not overwrite the session cookie.
                # Invalid account versions still fail this check every time;
                # successful login and explicit logout clear the session.
                if request.path.startswith("/api/"):
                    return jsonify(error="Please sign in to continue."), 401
                return redirect(url_for("auth.login"))
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            provided = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            expected = session.get("csrf", "")
            if not expected or not hmac.compare_digest(expected.encode(), provided.encode()):
                if request.path.startswith("/api/"):
                    return jsonify(error="Session expired. Reload the page and try again."), 400
                return "Session expired. Reload the sign-in page and try again.", 400
