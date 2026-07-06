"""بوت‌استرپ اجرای بات درون فرآیند وب‌آپ PythonAnywhere (پلن رایگان، بدون Always-on task).

ایده: پلن رایگان PythonAnywhere هیچ سرویس background/always-on-task نداره، ولی
میزبانی وب‌آپ رایگانه و همیشه (تا وقتی هر ماه تمدید بشه) روشن می‌مونه. با اجرای
polling بات تلگرام در یک ترد پس‌زمینه‌ی این پروسه‌ی وب، از همون زیرساخت رایگان
برای زنده نگه‌داشتن بات استفاده می‌کنیم.
"""

import asyncio
import logging
import os
import sys
import threading

PROJECT_HOME = "/home/ebrahimjafari/konkur-coach"

if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

os.chdir(PROJECT_HOME)

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_HOME, ".env"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wsgi_bootstrap")

_bot_started = False
_bot_lock = threading.Lock()


def _run_bot() -> None:
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
        import main as bot_main

        bot_main.main()
    except Exception:
        logger.exception("بات در ترد پس‌زمینه کرش کرد")


def start_bot_once() -> None:
    global _bot_started
    with _bot_lock:
        if _bot_started:
            return
        _bot_started = True
    threading.Thread(target=_run_bot, daemon=True).start()


start_bot_once()


def application(environ, start_response):
    status = "200 OK"
    content = b"Konkur Coach bot is running."
    response_headers = [("Content-Type", "text/plain"), ("Content-Length", str(len(content)))]
    start_response(status, response_headers)
    return [content]
