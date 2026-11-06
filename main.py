"""
نقطة التشغيل: تشغل البوت العام وبوت الإدارة في نفس الخدمة (نفس الـ Service على Railway).
"""
import logging
import os
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")


def run_polling(tb, name):
    logger.info("Starting %s", name)
    tb.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    import bot as public_bot

    if os.getenv("ADMIN_BOT_TOKEN"):
        import admin_bot

        threading.Thread(
            target=run_polling, args=(admin_bot.bot, "admin bot"), daemon=True
        ).start()
    else:
        logger.warning("ADMIN_BOT_TOKEN not set: admin bot is disabled")

    run_polling(public_bot.bot, "public bot")
