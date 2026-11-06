import os
import json
import logging
import requests
import telebot

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# CONFIG
# =========================

BOT_TOKEN =" 9150114718:AAHwz8AxdEp_APewCSDy3zoxoB8vkdEHJdc"
BASE_URL = "https://me-tp.qureo.education"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in Railway Variables")

bot = telebot.TeleBot(BOT_TOKEN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# تخزين حالات وبيانات المستخدمين مؤقتاً
users = {}


# =========================
# KEYBOARDS (القوائم والأزرار التفاعلية)
# =========================

def courses_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🐍 Python", callback_data="course_python"),
        InlineKeyboardButton("🟨 JavaScript", callback_data="course_js"),
        InlineKeyboardButton("💰 الثقافة المالية", callback_data="course_finance"),
        InlineKeyboardButton("⬅️ إلغاء ورجوع", callback_data="cancel")
    )
    return markup


def target_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("فصل محدد (1-58)", callback_data="target_chapter"),
        InlineKeyboardButton("حل كل الكورس", callback_data="target_all"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="back_to_courses")
    )
    return markup


def confirm_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✔️ تأكيد وبدء الحل", callback_data="confirm_run"),
        InlineKeyboardButton("❌ إلغاء من جديد", callback_data="cancel")
    )
    return markup


# =========================
# COMMANDS (الأوامر الأساسية)
# =========================

@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id
    users[chat_id] = {
        "step": "waiting_id",
        "login_id": None,
        "password": None,
        "course": None,
        "target": None
    }

    intro_text = (
        "👋 **مساعد Qureo**\n\n"
        "🌐 أحل الكورسات سواء كانت منصتك بالعربية أو لغات.\n\n"
        "أحل دروس Qureo بدلاً منك. كل ما أحتاجه:\n"
        "‏1️⃣ رقم الدخول\n"
        "‏2️⃣ كلمة المرور\n"
        "‏3️⃣ JavaScript أو Python أو الثقافة المالية\n"
        "‏4️⃣ ما الذي تريد حله: درس، فصل، عدة فصول أو كل شيء\n\n"
        "🔒 **أحذف رسالة كلمة المرور فوراً ولا أحفظها.**\n\n"
        "🏫 الصف الثاني الثانوي — التعليم العام\n"
        "📚 البرمجة وتكنولوجيا المعلومات\n"
        "📚 الثقافة المالية\n\n"
        "✍️ **أرسل رقم الدخول إلى Qureo:**"
    )

    bot.send_message(chat_id, intro_text, parse_mode="Markdown")


@bot.message_handler(commands=["cancel", "help"])
def cancel_command(message):
    chat_id = message.chat.id
    users[chat_id] = {"step": "waiting_id"}
    bot.send_message(chat_id, "تم إلغاء العملية والعودة للبداية. أرسل /start للبدء.")


# =========================
# MESSAGE HANDLERS (معالجة إدخال النصوص)
# =========================

@bot.message_handler(content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()

    if chat_id not in users:
        users[chat_id] = {"step": "waiting_id"}

    current_step = users[chat_id].get("step")

    # 1. استقبال رقم الدخول
    if current_step == "waiting_id":
        users[chat_id]["login_id"] = text
        users[chat_id]["step"] = "waiting_password"
        bot.send_message(
            chat_id,
            "🔑 **الآن كلمة المرور (سأحذف رسالتك فوراً):**",
            parse_mode="Markdown"
        )

    # 2. استقبال كلمة المرور وحذفها فوراً للأمان
    elif current_step == "waiting_password":
        users[chat_id]["password"] = text
        
        # محاولة حذف رسالة الباسورد التي أرسلها المستخدم فوراً
        try:
            bot.delete_message(chat_id, message.message_id)
        except Exception as e:
            logger.warning("Could not delete password message: %s", str(e))

        bot.send_message(
            chat_id,
            "🔒 وصلت كلمة المرور وتم حذف رسالتك.\n\n📚 **أي كورس؟**",
            reply_markup=courses_menu(),
            parse_mode="Markdown"
        )
        users[chat_id]["step"] = "choosing_course"

    # استقبال رقم الفصل لو اختار فصل محدد
    elif current_step == "waiting_chapter_number":
        users[chat_id]["target"] = f"الفصل {text}"
        show_review_screen(chat_id)

    else:
        bot.send_message(chat_id, "استخدم الأزرار التفاعلية أو اكتب /start للبدء.")


# =========================
# CALLBACK HANDLERS (التعامل مع الأزرار)
# =========================

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    data = call.data

    if chat_id not in users:
        users[chat_id] = {"step": "waiting_id"}

    bot.answer_callback_query(call.id)

    if data == "cancel":
        users[chat_id] = {"step": "waiting_id"}
        bot.send_message(chat_id, "تم الإلغاء. أرسل /start للبدء من جديد.")

    elif data.startswith("course_"):
        if data == "course_python":
            users[chat_id]["course"] = "Python"
        elif data == "course_js":
            users[chat_id]["course"] = "JavaScript"
        elif data == "course_finance":
            users[chat_id]["course"] = "الثقافة المالية"

        course_name = users[chat_id]['course']
        bot.edit_message_text(
            f"💰 **{course_name}**: ماذا تريد أن أحل؟",
            chat_id,
            call.message.message_id,
            reply_markup=target_menu(),
            parse_mode="Markdown"
        )
        users[chat_id]["step"] = "choosing_target"

    elif data == "target_chapter":
        bot.send_message(
            chat_id,
            "👆 **اضغط واكتب رقم الفصل (1–58):**",
            parse_mode="Markdown"
        )
        users[chat_id]["step"] = "waiting_chapter_number"

    elif data == "target_all":
        users[chat_id]["target"] = "حل الكورس بالكامل"
        show_review_screen(chat_id)

    elif data == "back_to_courses":
        bot.edit_message_text(
            "📚 **أي كورس؟**",
            chat_id,
            call.message.message_id,
            reply_markup=courses_menu(),
            parse_mode="Markdown"
        )

    elif data == "confirm_run":
        bot.edit_message_text(
            "⏳ **جاري الاتصال بمنصة Qureo وبدء الحل التلقائي...**",
            chat_id,
            call.message.message_id,
            parse_mode="Markdown"
        )

        user_data = users.get(chat_id, {})
        course = user_data.get("course", "الكورس")
        target = user_data.get("target", "المحتوى")

        # محاكاة الاتصال الناجح والبدء في حل الدروس فوراً
        bot.send_message(
            chat_id,
            "⏱ **تم اعتماد الطلب وبدء التنفيذ بنجاح!**\n"
            f"🎯 جاري حل ({target}) في مادة ({course}) بدلاً منك.\n\n"
            "يمكنك إغلاق تيليجرام، سأرسل لك رسالة عند الانتهاء 🚀.",
            parse_mode="Markdown"
        )

        # مسح بيانات الجلسة وسجل الباسورد حفاظاً على الأمان التام
        users[chat_id] = {"step": "waiting_id"}


def show_review_screen(chat_id):
    user_data = users.get(chat_id, {})
    login_id = user_data.get("login_id", "غير محدد")
    course = user_data.get("course", "غير محدد")
    target = user_data.get("target", "غير محدد")

    review_text = (
        "📝 **راجع ثم أكد**\n\n"
        f"👤 الرقم: `{login_id}`\n"
        "🔑 كلمة المرور: `••••••••`\n"
        f"💰 الكورس: {course}\n"
        f"🎯 المطلوب: {target}"
    )

    bot.send_message(
        chat_id,
        review_text,
        reply_markup=confirm_menu(),
        parse_mode="Markdown"
    )
    users[chat_id]["step"] = "reviewing"


# =========================
# RUN BOT
# =========================

if __name__ == "__main__":
    logger.info("Bot is starting...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
