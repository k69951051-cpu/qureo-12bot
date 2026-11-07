"""تشغيل البوت العام وبوت الإدارة معاً + خادم صحة بسيط لـ Cloud Run."""
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import bot as public_bot


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def _poll(b):
    b.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    threading.Thread(target=_poll, args=(public_bot.bot,), daemon=True).start()
    if os.getenv("ADMIN_BOT_TOKEN"):
        import admin_bot
        threading.Thread(target=_poll, args=(admin_bot.bot,), daemon=True).start()
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), Health).serve_forever()
