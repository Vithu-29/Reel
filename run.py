"""
Entry point. Run with:

    python run.py

or in production with a proper WSGI server, e.g.:

    gunicorn -w 1 -b 0.0.0.0:5000 "run:app"

Note: -w 1 (a single worker process) matters here - the download queue and
history/settings singletons live in process memory, so multiple worker
processes would each get their own, independent queue.
"""

from app.config import Config
from app.factory import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG, threaded=True)
