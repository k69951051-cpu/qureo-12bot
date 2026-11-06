import os
import json
import logging
import requests
import telebot

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
QUREO_BEARER_TOKEN = os.getenv("QUREO_BEARER_TOKEN", "")

BASE_URL = "https://me-tp.qureo.education"

CHAPTERS_URL = (
    BASE_URL
    + "/api/study/students/sections/106/chapters"
)

PYTHON_DIAMOND_URL = (
    BASE_URL
    + "/api/study/students/courses/python_short_ar/diamond"
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in Railway Variables")

bot = telebot.TeleBot(BOT_TOKEN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# حالة المستخدم داخل البوت
users = {}


# =========================
# KEYBOARDS
# =========================

def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)

    markup.add(
        InlineKeyboardButton("📚 المرحلة الدراسية", callback_data="stages"),
        InlineKeyboardButton("💻 منصة Qureo", callback_data="qureo"),
        InlineKeyboardButton("ℹ️ عن البوت", callback_data="about")
    )

    return markup


def stages_menu():
    markup = InlineKeyboardMarkup(row_width=1)

    markup.add(
        InlineKeyboardButton("المرحلة الأولى", callback_data="stage_first"),
        InlineKeyboardButton("المرحلة الثانية", callback_data="stage_second"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="home")
    )

    return markup


def education_menu():
    markup = InlineKeyboardMarkup(row_width=1)

    markup.add(
        InlineKeyboardButton("تعليم عام", callback_data="edu_general"),
        InlineKeyboardButton("تعليم فني", callback_data="edu_technical"),
        InlineKeyboardButton("تعليم أزهري", callback_data="edu_azhar"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="stages")
    )

    return markup


def courses_menu():
    markup = InlineKeyboardMarkup(row_width=1)

    markup.add(
        InlineKeyboardButton("🐍 Python", callback_data="python"),
        InlineKeyboardButton("🟨 JavaScript", callback_data="javascript"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="qureo")
    )

    return markup


def back_home_menu():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")
    )
    return markup


# =========================
# API FUNCTIONS
# =========================

def qureo_headers():
    if not QUREO_BEARER_TOKEN:
        raise RuntimeError(
            "QUREO_BEARER_TOKEN is missing in Railway Variables"
        )

    return {
        "Authorization": f"Bearer {QUREO_BEARER_TOKEN}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }


def get_api_data(url):
    try:
        response = requests.get(
            url,
            headers=qureo_headers(),
            timeout=20
        )

        if response.status_code in (401, 403):
            logger.warning("Qureo API authorization failed: %s",
                           response.status_code)
            return None, "التوكن غير صالح أو غير مصرح له."

        response.raise_for_status()

        try:
            return response.json(), None
        except ValueError:
            return None, "الاستجابة من المنصة ليست JSON."

    except requests.Timeout:
        return None, "انتهت مهلة الاتصال بالمنصة."

    except requests.RequestException as exc:
        logger.error("Qureo request failed: %s", type(exc).__name__)
        return None, "حصلت مشكلة أثناء الاتصال بالمنصة."

    except RuntimeError as exc:
        return None, str(exc)


def format_data(data, max_length=3500):
    """
    عرض البيانات بصورة آمنة ومختصرة.
    """
    if data is None:
        return "لا توجد بيانات."

    result = json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )

    if len(result) > max_length:
        result = result[:max_length] + "\n... تم اختصار النتيجة"

    return result


# =========================
# COMMANDS
# =========================

@bot.message_handler(commands=["start"])
def start(message):
    users[message.chat.id] = {
        "stage": None,
        "education": None,
        "course": None
    }

    bot.send_message(
        message.chat.id,
        "أهلاً بيك 👋\n\n"
        "اختار من القائمة اللي تحب تدخل عليها:",
        reply_markup=main_menu()
    )


@bot.message_handler(commands=["cancel"])
def cancel(message):
    users.pop(message.chat.id, None)

    bot.send_message(
        message.chat.id,
        "تم الرجوع للقائمة الرئيسية.",
        reply_markup=main_menu()
    )


@bot.message_handler(commands=["help"])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "الأوامر المتاحة:\n"
        "/start - تشغيل البوت\n"
        "/cancel - الرجوع للقائمة الرئيسية\n"
        "/help - المساعدة"
    )


# =========================
# CALLBACKS
# =========================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    data = call.data

    if chat_id not in users:
        users[chat_id] = {
            "stage": None,
            "education": None,
            "course": None
        }

    bot.answer_callback_query(call.id)

    if data == "home":
        bot.send_message(
            chat_id,
            "القائمة الرئيسية:",
            reply_markup=main_menu()
        )

    elif data == "stages":
        bot.send_message(
            chat_id,
            "اختار المرحلة الدراسية:",
            reply_markup=stages_menu()
        )

    elif data == "stage_first":
        users[chat_id]["stage"] = "first"

        bot.send_message(
            chat_id,
            "اختار نوع التعليم:",
            reply_markup=education_menu()
        )

    elif data == "stage_second":
        users[chat_id]["stage"] = "second"

        bot.send_message(
            chat_id,
            "اختار نوع التعليم:",
            reply_markup=education_menu()
        )

    elif data in ("edu_general", "edu_technical", "edu_azhar"):
        users[chat_id]["education"] = data

        bot.send_message(
            chat_id,
            "تم اختيار نوع التعليم.\n"
            "تقدر تدخل على منصة Qureo من القائمة الرئيسية.",
            reply_markup=main_menu()
        )

    elif data == "qureo":
        bot.send_message(
            chat_id,
            "اختار المادة:",
            reply_markup=courses_menu()
        )

    elif data == "python":
        stage = users[chat_id].get("stage")

        if stage != "second":
            bot.send_message(
                chat_id,
                "قسم Python متاح حالياً للمرحلة الثانية فقط.",
                reply_markup=stages_menu()
            )
            return

        bot.send_message(
            chat_id,
            "⏳ جاري جلب بيانات Python..."
        )

        chapters, error = get_api_data(CHAPTERS_URL)

        if error:
            bot.send_message(chat_id, "⚠️ " + error)
            return

        diamonds, error = get_api_data(PYTHON_DIAMOND_URL)

        if error:
            bot.send_message(chat_id, "⚠️ " + error)
            return

        text = (
            "🐍 بيانات Python\n\n"
            "📚 الفصول:\n"
            + format_data(chapters, 1500)
            + "\n\n💎 Diamonds:\n"
            + format_data(diamonds, 1500)
        )

        bot.send_message(
            chat_id,
            text,
            reply_markup=back_home_menu()
        )

    elif data == "javascript":
        bot.send_message(
            chat_id,
            "قسم JavaScript لسه محتاج ربط API الخاص به."
        )

    elif data == "about":
        bot.send_message(
            chat_id,
            "بوت تعليمي تجريبي لعرض بيانات منصة Qureo.\n"
            "تسجيل دخول الطلاب بحساباتهم الشخصية تم توجيهه عبر التوكن."
        )

    else:
        bot.send_message(chat_id, "اختيار غير معروف.")


# =========================
# UNKNOWN MESSAGES
# =========================

@bot.message_handler(
    content_types=["text"],
    func=lambda message: True
)
def other_messages(message):
    bot.send_message(
        message.chat.id,
        "استخدم الأزرار الموجودة في القائمة أو اكتب /start."
    )


# =========================
# RUN
# =========================

if __name__ == "__main__":
    logger.info("Bot is starting...")
    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
        )
