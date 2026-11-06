
import os
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# CONFIG
# =========================

BOT_TOKEN = "9150114718:AAHwz8AxdEp_APewCSDy3zoxoB8vkdEHJdc"
QUREO_TOKEN = os.getenv("QUREO_BEARER_TOKEN", "")

BASE_URL = "https://me-tp.qureo.education"
SPX_LOGIN = "https://egy.app.spx-learning-square.com/login"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

bot = telebot.TeleBot(BOT_TOKEN)

# Temporary conversation state only
users = {}

# =========================
# KEYBOARDS
# =========================

def make_keyboard(rows):
    kb = InlineKeyboardMarkup()

    for row in rows:
        kb.row(*[
            InlineKeyboardButton(
                text=label,
                callback_data=value
            )
            for label, value in row
        ])

    return kb


def main_menu(chat_id):
    users.setdefault(chat_id, {})

    bot.send_message(
        chat_id,
        "🎓 أهلاً بك في SPX Student Bot\n\n"
        "اختر مرحلتك الدراسية:",
        reply_markup=make_keyboard([
            [
                ("أولى ثانوي", "first"),
                ("تانية بكالوريا", "second")
            ]
        ])
    )


# =========================
# API
# =========================

def get_qureo_data():
    headers = {
        "Accept": "application/json"
    }

    if QUREO_TOKEN:
        headers["Authorization"] = (
            f"Bearer {QUREO_TOKEN}"
        )

    chapters_response = requests.get(
        BASE_URL +
        "/api/study/students/sections/106/chapters",
        headers=headers,
        timeout=20
    )

    chapters_response.raise_for_status()
    chapters = chapters_response.json()

    diamond_response = requests.get(
        BASE_URL +
        "/api/study/students/courses/python_short_ar/diamond",
        headers=headers,
        timeout=20
    )

    diamond_response.raise_for_status()
    diamonds = diamond_response.json()

    return chapters, diamonds


def get_total_diamonds(chapters, diamonds):
    if isinstance(diamonds, (int, float)):
        return diamonds

    if isinstance(diamonds, dict):
        for key in ("diamond", "diamonds", "total"):
            value = diamonds.get(key)

            if isinstance(value, (int, float)):
                return value

    return sum(
        int(item.get("diamond", 0))
        for item in chapters
    )


def show_python(chat_id):
    bot.send_message(
        chat_id,
        "⏳ جاري تحميل بيانات Python..."
    )

    try:
        chapters, diamonds = get_qureo_data()

        total = get_total_diamonds(
            chapters,
            diamonds
        )

        text = (
            "🐍 <b>تقرير Python</b>\n\n"
            f"💎 إجمالي الماسات: {total}\n"
            f"📚 عدد الفصول: {len(chapters)}\n"
            "━━━━━━━━━━━━━━\n"
        )

        for index, chapter in enumerate(
            chapters, start=1
        ):
            text += (
                f"\n📖 الفصل {index}\n"
                f"🆔 ID: {chapter.get('chapter_id')}\n"
                f"💎 الماسات: {chapter.get('diamond', 0)}\n"
                f"✅ أفضل إجابات صحيحة: "
                f"{chapter.get('best_correct_count', 0)}\n"
                "━━━━━━━━━━━━━━\n"
            )

        bot.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            reply_markup=make_keyboard([
                [("🔄 تحديث", "python")],
                [("🏠 الرئيسية", "home")]
            ])
        )

    except requests.exceptions.HTTPError as error:
        code = error.response.status_code

        if code in (401, 403):
            message = (
                "الحساب يحتاج تسجيل دخول وصلاحية رسمية "
                "للوصول إلى Qureo."
            )
        else:
            message = f"خطأ HTTP: {code}"

        bot.send_message(
            chat_id,
            "⚠️ " + message
        )

    except requests.exceptions.RequestException:
        bot.send_message(
            chat_id,
            "⚠️ تعذر الاتصال بالسيرفر."
        )

    except (ValueError, TypeError):
        bot.send_message(
            chat_id,
            "⚠️ صيغة البيانات غير متوقعة."
        )


# =========================
# START
# =========================

@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id
    users[chat_id] = {}
    main_menu(chat_id)


# =========================
# CALLBACKS
# =========================

@bot.callback_query_handler(
    func=lambda call: True
)
def callback(call):
    chat_id = call.message.chat.id
    data = call.data

    bot.answer_callback_query(call.id)

    users.setdefault(chat_id, {})

    if data == "home":
        main_menu(chat_id)

    elif data in ("first", "second"):
        users[chat_id]["stage"] = data

        bot.send_message(
            chat_id,
            "اختر نوع التعليم:",
            reply_markup=make_keyboard([
                [
                    ("عام", "general"),
                    ("فني", "technical")
                ],
                [("أزهر", "azhar")],
                [("رجوع", "home")]
            ])
        )

    elif data in ("general", "technical", "azhar"):
        users[chat_id]["education"] = data

        options = [
            [("Qureo", "qureo")]
        ]

        if users[chat_id]["stage"] == "second":
            options.append(
                [("الثقافة المالية", "finance")]
            )

        options.append(
            [("رجوع", "home")]
        )

        bot.send_message(
            chat_id,
            "اختر المنصة:",
            reply_markup=make_keyboard(options)
        )

    elif data == "qureo":
        stage = users[chat_id]["stage"]

        options = []

        if stage == "second":
            options.append(
                [("Python", "python")]
            )

        options.append(
            [("JavaScript", "javascript")]
        )

        options.append(
            [("رجوع", "home")]
        )

        bot.send_message(
            chat_id,
            "اختر الكورس:",
            reply_markup=make_keyboard(options)
        )

    elif data == "python":
        users[chat_id]["course"] = "python"
        show_python(chat_id)

    elif data == "javascript":
        bot.send_message(
            chat_id,
            "💻 JavaScript\n"
            "نحتاج تحديد واجهة API الخاصة بالكورس."
        )

    elif data == "finance":
        bot.send_message(
            chat_id,
            "💰 الثقافة المالية\n"
            "نحتاج تحديد واجهة API الخاصة بها."
        )


# =========================
# RUN
# =========================

print("SPX Bot is running...")

bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30
)
