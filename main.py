
import os
import logging
from typing import Optional, Dict, Any

import telebot
from telebot import types

# ==============================
# إعدادات البوت
# ==============================

BOT_TOKEN ="9150114718:AAHwz8AxdEp_APewCSDy3zoxoB8vkdEHJdc"

if not BOT_TOKEN:
   raise RuntimeError("Missing BOT_TOKEN environment variable")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

logger = logging.getLogger("qureo_bot")

bot = telebot.TeleBot(TOKEN if False else BOT_TOKEN, parse_mode="HTML")

sessions: Dict[int, Dict[str, Any]] = {}

# ==============================
# بيانات الصفوف
# ==============================

GRADE_LABELS = {
    "grade_1st": "الصف الأول الثانوي",
    "grade_2nd": "الصف الثاني الثانوي"
}

COURSES = {
    "javascript": {
        "label": "جافا سكريبت (JavaScript)",
        "provider": "QUREO",
        "diamonds": True,
        "chapters": True,
        "path": "/course/javascript_ar"
    },
    "python": {
        "label": "بايثون (Python)",
        "provider": "QUREO",
        "diamonds": True,
        "chapters": True,
        "path": "/course/python_short_ar"
    },
    "financial": {
        "label": "الثقافة المالية",
        "provider": "SPX Learning Square",
        "diamonds": False,
        "chapters": True,
        "path": "/dashboard"
    }
}


def reset_session(chat_id):
    sessions.pop(chat_id, None)


def get_course_keyboard(grade_code):
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    allowed = ["javascript", "financial"]

    if grade_code == "grade_2nd":
        allowed.insert(1, "python")

    for key in allowed:
        keyboard.add(
            types.InlineKeyboardButton(
                COURSES[key]["label"],
                callback_data=f"course_{key}"
            )
        )

    return keyboard


# ==============================
# مصدر بيانات QUREO و SPX
# ==============================

def fetch_progress(course_key, student_id):
    """
    مكان ربط API رسمي ومصرح به.

    الشكل المتوقع للبيانات:

    {
        "chapters": "12 / 20",
        "diamonds": "230 / 270"
    }

    الثقافة المالية لا تحتاج diamonds.
    """

    # لم يتم توفير API رسمي حتى الآن.
    return None


# ==============================
# بدء البوت
# ==============================

@bot.message_handler(commands=["start"])
def start(message):

    chat_id = message.chat.id

    sessions[chat_id] = {
        "step": "waiting_student_id"
    }

    bot.send_message(
        chat_id,
        "🤖 <b>مساعد QUREO الذكي</b>\n\n"
        "أهلاً بك!\n"
        "أرسل رقم الطالب أو المعرّف المسموح بمشاركته.\n\n"
        "⚠️ لا ترسل كلمة المرور أو رمز التحقق."
    )


# ==============================
# استقبال رقم الطالب
# ==============================

@bot.message_handler(
    func=lambda m:
    sessions.get(m.chat.id, {}).get("step") == "waiting_student_id"
)
def receive_student_id(message):

    chat_id = message.chat.id
    student_id = (message.text or "").strip()

    if not student_id or len(student_id) > 80:
        bot.reply_to(message, "❌ رقم الطالب غير صالح.")
        return

    sessions[chat_id]["student_id"] = student_id
    sessions[chat_id]["step"] = "choose_grade"

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        types.InlineKeyboardButton(
            "📘 الصف الأول الثانوي",
            callback_data="grade_1st"
        ),
        types.InlineKeyboardButton(
            "📘 الصف الثاني الثانوي",
            callback_data="grade_2nd"
        )
    )

    bot.send_message(
        chat_id,
        "📌 اختر الصف الدراسي:",
        reply_markup=keyboard
    )


# ==============================
# اختيار الصف
# ==============================

@bot.callback_query_handler(
    func=lambda c: c.data in GRADE_LABELS
)
def choose_grade(call):

    chat_id = call.message.chat.id
    data = sessions.get(chat_id)

    if not data or data.get("step") != "choose_grade":
        bot.answer_callback_query(call.id, "ابدأ من جديد باستخدام /start")
        return

    data["grade_code"] = call.data
    data["grade"] = GRADE_LABELS[call.data]
    data["step"] = "choose_course"

    bot.answer_callback_query(call.id)

    bot.edit_message_text(
        f"📌 الصف: <b>{data['grade']}</b>\n\n"
        "🎯 اختر الكورس:",
        chat_id,
        call.message.message_id,
        reply_markup=get_course_keyboard(call.data)
    )


# ==============================
# اختيار الكورس
# ==============================

@bot.callback_query_handler(
    func=lambda c: c.data.startswith("course_")
)
def choose_course(call):

    chat_id = call.message.chat.id
    data = sessions.get(chat_id)

    if not data or data.get("step") != "choose_course":
        bot.answer_callback_query(call.id, "انتهت الجلسة.")
        return

    course_key = call.data.replace("course_", "")

    if course_key not in COURSES:
        bot.answer_callback_query(call.id, "اختيار غير صحيح.")
        return

    if course_key == "python" and data["grade_code"] != "grade_2nd":
        bot.answer_callback_query(call.id, "الكورس غير متاح لهذا الصف.")
        return

    data["course_key"] = course_key
    data["step"] = "confirmation"

    course = COURSES[course_key]

    summary = (
        "📋 <b>ملخص الطلب</b>\n\n"
        f"📚 الصف: {data['grade']}\n"
        f"🎯 الكورس: {course['label']}\n"
        f"🌐 المنصة: {course['provider']}\n\n"
        "هل تريد المتابعة؟"
    )

    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.add(
        types.InlineKeyboardButton(
            "🚀 متابعة",
            callback_data="confirm"
        ),
        types.InlineKeyboardButton(
            "❌ إلغاء",
            callback_data="cancel"
        )
    )

    bot.answer_callback_query(call.id)

    bot.edit_message_text(
        summary,
        chat_id,
        call.message.message_id,
        reply_markup=keyboard
    )


# ==============================
# التأكيد والإلغاء
# ==============================

@bot.callback_query_handler(
    func=lambda c: c.data in ["confirm", "cancel"]
)
def handle_actions(call):

    chat_id = call.message.chat.id
    data = sessions.get(chat_id)

    if not data or data.get("step") != "confirmation":
        bot.answer_callback_query(call.id, "انتهت الجلسة.")
        return

    if call.data == "cancel":

        bot.answer_callback_query(call.id)

        bot.edit_message_text(
            "❌ تم إلغاء العملية.",
            chat_id,
            call.message.message_id
        )

        reset_session(chat_id)
        return

    bot.answer_callback_query(call.id, "جاري المعالجة...")

    bot.edit_message_text(
        "⏳ جاري طلب بيانات التقدم...",
        chat_id,
        call.message.message_id
    )

    try:

        course_key = data["course_key"]
        course = COURSES[course_key]

        progress = fetch_progress(
            course_key,
            data["student_id"]
        )

        if progress is None:

            bot.send_message(
                chat_id,
                "⚠️ لم يتم ربط مصدر البيانات الرسمي بعد.\n\n"
                "اختيارات الصف والكورس تعمل، لكن جلب "
                "الألماس والفصول يحتاج واجهة رسمية "
                "من QUREO أو SPX."
            )

            return

        chapters = progress.get("chapters")

        if not chapters:
            raise ValueError("Chapter data is missing")

        result = (
            "✅ <b>بيانات التقدم</b>\n\n"
            f"📚 الصف: {data['grade']}\n"
            f"🎯 الكورس: {course['label']}\n"
            f"📖 الفصول المكتملة: {chapters}"
        )

        if course["diamonds"]:
            diamonds = progress.get("diamonds")

            if diamonds:
                result += f"\n💎 الألماس: {diamonds}"

        bot.send_message(chat_id, result)

    except Exception:

        logger.exception("Progress lookup error")

        bot.send_message(
            chat_id,
            "❌ حدث خطأ أثناء معالجة الطلب. حاول لاحقاً."
        )

    finally:
        reset_session(chat_id)


# ==============================
# إلغاء العملية
# ==============================

@bot.message_handler(commands=["cancel"])
def cancel(message):

    reset_session(message.chat.id)

    bot.send_message(
        message.chat.id,
        "❌ تم إلغاء العملية.\n"
        "استخدم /start للبدء من جديد."
    )


# ==============================
# تشغيل البوت
# ==============================

if __name__ == "__main__":

    logger.info("QUREO Bot is starting...")

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
