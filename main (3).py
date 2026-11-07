"""تشغيل البوت العام وبوت الإدارة معاً + خادم صحة بسيط لـ Cloud Run."""
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("main")

import bot as public_bot


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def _poll(name, b):
    """يشغّل الاستطلاع، ويعيد المحاولة دائماً حتى لو حدث خطأ (مع تسجيله في اللوج)."""
    while True:
        try:
            me = b.get_me()
            logger.info("%s bot started: @%s", name, me.username)
            b.remove_webhook()  # أي webhook قديم يمنع getUpdates (خطأ 409)
            b.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception:
            logger.exception("%s bot crashed, retrying in 10s", name)
        time.sleep(10)


if __name__ == "__main__":
    threading.Thread(target=_poll, args=("public", public_bot.bot), daemon=True).start()
    admin_token = os.getenv("ADMIN_BOT_TOKEN", "").strip()
    if admin_token:
        if admin_token == os.getenv("BOT_TOKEN", "").strip():
            logger.error("ADMIN_BOT_TOKEN is the same as BOT_TOKEN: use a separate bot for admin")
        else:
            try:
                import admin_bot
                threading.Thread(target=_poll, args=("admin", admin_bot.bot), daemon=True).start()
            except Exception:
                logger.exception("failed to start admin bot")
    else:
        logger.warning("ADMIN_BOT_TOKEN is not set: admin bot is NOT running")
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), Health).serve_forever()
