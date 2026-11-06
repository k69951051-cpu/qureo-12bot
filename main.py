
import os
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# Configuration
# =========================

BOT_TOKEN = "9150114718:AAHwz8AxdEp_APewCSDy3zoxoB8vkdEHJdc"
QUREO_BASE = "https://me-tp.qureo.education"

# Optional official API bearer token, if required
QUREO_TOKEN = os.getenv("QUREO_BEARER_TOKEN", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing!")

bot = telebot.TeleBot(BOT_TOKEN)

GRADES = [
    "الصف الأول الثانوي",
    "الصف الثاني الثانوي",
    "الصف الثالث الثانوي"
]

def keyboard(rows):
    markup = InlineKeyboardMarkup()
    for row in rows:
        markup.row(*[
            InlineKeyboardButton(text, callback_data=data)
            for text, data in row
        ])
    return markup


def api_get(path):
    headers = {"Accept": "application/json"}

    if QUREO_TOKEN:
        headers["Authorization"] = f"Bearer {QUREO_TOKEN}"

    response = requests.get(
        QUREO_BASE + path,
        headers=headers,
        timeout=20
    )

    response.raise_for_status()
    return response.json()


def get_python_data():
    chapters = api_get(
        "/api/study/students/sections/106/chapters"
    )

    diamonds = api_get(
        "/api/study/students/courses/python_short_ar/diamond"
    )

    if not isinstance(chapters, list):
        raise ValueError("Unexpected chapters response")

    return chapters, diamonds


def format_diamonds(data, chapters):
    if isinstance(data, int):
        return data

    if isinstance(data, dict):
        for key in ("diamond", "diamonds", "total"):
            if isinstance(data.get(key), (int, float)):
                return data[key]

    return sum(
        int(chapter.get("diamond", 0))
        for chapter in chapters
    )


def show_python(chat_id):
    bot.send_message(chat_id, "⏳ جاري تحميل بيانات Python...")

    try:
        chapters, diamond_data = get_python_data()
        total = format_diamonds(diamond_data, chapters)

        message = (
            "🐍 <b>تقرير كورس Python</b>\n\n"
            f"💎 إجمالي الماسات: <b>{total}</b>\n"
            f"📚 عدد الفصول: <b>{len(chapters)}</b>\n\n"
            "━━━━━━━━━━━━━━\n"
        )

        for index, chapter in enumerate(chapters, 1):
            message += (
                f"\n📖 <b>الفصل {index}</b>\n"
                f"🆔 رقم الفصل: {chapter.get('chapter_id', '-')}\n"
                f"💎 الماسات: {chapter.get('diamond', 0)}\n"
                f"✅ أفضل إجابات صحيحة: "
                f"{chapter.get('best_correct_count', 0)}\n"
                "━━━━━━━━━━━━━━\n"
            )

        bot.send_message(
            chat_id,
            message,
            parse_mode="HTML",
            reply_markup=keyboard([
                [("🔄 تحديث البيانات", "python")],
                [("↩️ القائمة الرئيسية", "home")]
            ])
        )

    except requests.exceptions.HTTPError as error:
        status = error.response.status_code
        if status in (401, 403):
            msg = "الحساب يحتاج صلاحية دخول رسمية للـ API."
        else:
            msg = f"خطأ من السيرفر: {status}"

        bot.send_message(chat_id, "⚠️ " + msg)

    except requests.exceptions.RequestException:
        bot.send_message(
            chat_id,
            "⚠️ تعذر الاتصال بـ Qureo. حاول مرة أخرى."
        )

    except (ValueError, TypeError, KeyError):
        bot.send_message(
            chat_id,
            "⚠️ صيغة البيانات المستلمة غير متوقعة."
        )

    except Exception:
        bot.send_message(
            chat_id,
            "⚠️ حصل خطأ غير متوقع."
        )


def show_home(chat_id):
    bot.send_message(
        chat_id,
        "🎓 <b>أهلاً بك في بوت متابعة الكورسات</b>\n\n"
        "اختر الصف الدراسي:",
        parse_mode="HTML",
        reply_markup=keyboard([
            [(grade, f"grade_{i}")]
            for i, grade in enumerate(GRADES)
        ])
    )


@bot.message_handler(commands=["start"])
def start(message):
    show_home(message.chat.id)


@bot.message_handler(commands=["help"])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "استخدم /start لبدء البوت."
    )


@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    data = call.data
    chat_id = call.message.chat.id

    bot.answer_callback_query(call.id)

    if data == "home":
        show_home(chat_id)

    elif data.startswith("grade_"):
        grade_index = int(data.split("_")[1])

        if not 0 <= grade_index < len(GRADES):
            return

        bot.send_message(
            chat_id,
            f"📚 {GRADES[grade_index]}\n\nاختر المادة:",
            reply_markup=keyboard([
                [("🐍 Python", "python")],
                [("💻 JavaScript", "javascript")],
                [("💰 الثقافة المالية", "finance")],
                [("↩️ رجوع", "home")]
            ])
        )

    elif data == "python":
        show_python(chat_id)

    elif data == "javascript":
        bot.send_message(
            chat_id,
            "💻 كورس JavaScript موجود، لكن نحتاج "
            "رابط API الخاص بفصوله قبل تفعيل عرض بياناته."
        )

    elif data == "finance":
        bot.send_message(
            chat_id,
            "💰 الثقافة المالية موجودة على SPX، "
            "ونحتاج واجهة API الرسمية للفصول لتفعيلها."
        )


print("Telegram bot is running...")
bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30
)
