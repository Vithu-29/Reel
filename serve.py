"""One-process server suitable for personal use, including Windows."""

from waitress import serve

from app.config import Config
from app.factory import create_app

if __name__ == "__main__":
    serve(create_app(), host=Config.HOST, port=Config.PORT, threads=8)
