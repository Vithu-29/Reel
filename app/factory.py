from __future__ import annotations

from flask import Flask

from app.config import Config
from app.utils.logger import configure_logging, get_logger

log = get_logger(__name__)


def create_app() -> Flask:
    Config.ensure_dirs()
    configure_logging()

    app = Flask(__name__)
    app.config.from_object(Config)
    from app.services.auth import init_auth

    init_auth(app)

    from app import extensions

    extensions.init_extensions()

    from app.routes.api import api_bp
    from app.routes.auth import auth_bp
    from app.routes.pages import pages_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    _apply_security_headers(app)

    log.info("Application ready (download folder: %s)", Config.DEFAULT_DOWNLOAD_FOLDER)
    return app


def _apply_security_headers(app: Flask) -> None:
    allowed = [o.strip() for o in Config.ALLOWED_ORIGINS.split(",") if o.strip()]

    @app.after_request
    def set_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        from flask import request

        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        if allowed:
            from flask import request

            origin = request.headers.get("Origin")
            if origin in allowed:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Vary"] = "Origin"
        return response
