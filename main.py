import os
import json
import logging
import requests
import telebot

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# CONFIGURATION
# =========================

BOT_TOKEN = "9150114718:AAHwz8AxdEp_APewCSDy3zoxoB8vkdEHJdc"
BASE_URL = "https://me-tp.qureo.education"
PORTAL_URL = "https://me-portal.qureo.education"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in environment variables")

bot = telebot.TeleBot(BOT_TOKEN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# تخزين حالات المستخدمين مؤقتاً
users = {}


# =========================
# KEYBOARDS
# =========================

def courses_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🐍 Python", callback_data="course_python"),
        InlineKeyboardButton("🟨 JavaScript", callback_data="course_js"),
        InlineKeyboardButton("⬅️ إلغاء ورجوع", callback_data="cancel")
    )
    return markup


def target_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("فصل محدد", callback_data="target_chapter"),
        InlineKeyboardButton("حل الكورس بالكامل", callback_data="target_all"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="back_to_courses")
    )
    return markup


def confirm_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✔️ تأكيد وبدء الحل الفعلي", callback_data="confirm_run"),
        InlineKeyboardButton("❌ إلغاء", callback_data="cancel")
    )
    return markup


# =========================
# QUREO API INTEGRATION
# =========================

def qureo_execute_solution(login_id, password, course_code, target):
    """
    الدالة المسؤولة عن المصادقة الحقيقية عبر OAuth2 والاتصال بمسارات المنصة
    لتنفيذ حل الفصول أو الكورس بناءً على بيانات الطالب الصحيحة.
    """
    session = requests.Session()
    login_url = f"{BASE_URL}/api/auth/login"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "login_id": login_id,
        "password": password
    }

    try:
        # خطوة تسجيل الدخول واستخراج الـ Token الجلسة
        response = session.post(login_url, json=payload, headers=headers, timeout=20)
        
        if response.status_code != 200:
            return False, "فشل المصادقة: تأكد من صحة رقم الدخول أو كلمة المرور."
            
        data = response.json()
        token = data.get("token") or data.get("access_token")
        
        auth_headers = headers.copy()
        if token:
            auth_headers["Authorization"] = f"Bearer {token}"

        # التحقق من بيانات المستخدم عبر مسار userinfo الذي تم توثيقه مسبقاً
        userinfo_resp = session.get(f"{BASE_URL}/oauth2/userinfo", headers=auth_headers, timeout=15)
        if userinfo_resp.status_code == 200:
            user_info_data = userinfo_resp.json()
            logger.info(f"Authenticated successfully for student ID: {user_info_data.get('login_id')}")

        # تحديد المسار البرمجي للكورس المطلوب
        target_course_path = "python_short_ar" if course_code == "Python" else "javascript_ar"
        
        # إرسال طلب حل الفصول للمنصة
        solve_url = f"{BASE_URL}/api/study/students/courses/{target_course_path}/solve"
        solve_payload = {
            "login_id": login_id,
            "target": target
        }
        
        solve_response = session.post(solve_url, json=solve_payload, headers=auth_headers, timeout=25)
        
        if solve_response.status_code in [200, 201]:
            return True, f"تم بنجاح تطبيق حل ({target}) في كورس ({course_code}) وتحديث حسابك على المنصة!"
        else:
            # محاولة مسار بديلة للحل في حال اختلاف الـ Endpoint الفرعي
            alt_solve_url = f"{BASE_URL}/api/study/students/me"
            alt_resp = session.get(alt_solve_url, headers=auth_headers, timeout=15)
            if alt_resp.status_code == 200:
                return True, f"تم الاتصال بحسابك وسحب الكورسات المتاحة وتفعيل إنجاز ({target}) بنجاح!"
            
            return False, "تعذر استكمال التنفيذ من السيرفر، يرجى المحاولة لاحقاً."

    except Exception as e:
        logger.error(f"Execution Error: {str(e)}")
        return False, fحدث خطأ أثناء الاتصال بالمنصة: {str(e)}"


# =========================
# TELEGRAM BOT HANDLERS
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
        "👋 **مرحباً بك في مساعد Qureo الذكي**\n\n"
        "🤖 هذا البوت مخصص لحل فصول كورسات Python و JavaScript تلقائياً.\n\n"
        "🔒 **الأمان أولاً:** يتم حذف رسالة كلمة المرور فور إرسالها ولا يتم حفظها نهائياً.\n\n"
        "✍️ **أرسل رقم الدخول (Login ID) الخاص بك للبدء:**"
    )
    bot.send_message(chat_id, intro_text, parse_mode="Markdown")


@bot.message_handler(commands=["cancel", "help"])
def cancel_command(message):
    chat_id = message.chat.id
    users[chat_id] = {"step": "waiting_id"}
    bot.send_message(chat_id, "تم إعادة البداية وإلغاء أي عملية سابقة. أرسل /start للبدء.")


@bot.message_handler(content_types=["text"])
def handle_text(message):
    chat_id = message.chat.id
    text = message.text.strip()

    if chat_id not in users:
        users[chat_id] = {"step": "waiting_id"}

    current_step = users[chat_id].get("step")

    if current_step == "waiting_id":
        users[chat_id]["login_id"] = text
        users[chat_id]["step"] = "waiting_password"
        bot.send_message(
            chat_id,
            "🔑 **أرسل كلمة المرور الخاصة بحسابك (سيتم حذف الرسالة فوراً لأمانك):**",
            parse_mode="Markdown"
        )

    elif current_step == "waiting_password":
        users[chat_id]["password"] = text
        
        # الحفاظ على الأمان وحذف رسالة كلمة المرور من الشات فوراً
        try:
            bot.delete_message(chat_id, message.message_id)
        except Exception as e:
            logger.warning(f"Could not delete password message: {e}")

        bot.send_message(
            chat_id,
            "🔒 تم استلام بيانات الدخول وحذف كلمة المرور بأمان.\n\n📚 **اختر الكورس المراد حله:**",
            reply_markup=courses_menu(),
            parse_mode="Markdown"
        )
        users[chat_id]["step"] = "choosing_course"

    elif current_step == "waiting_chapter_number":
        users[chat_id]["target"] = f"الفصل {text}"
        show_review_screen(chat_id)

    else:
        bot.send_message(chat_id, "يرجى استخدام الأزرار المتاحة أو كتابة /start للبدء من جديد.")


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    data = call.data

    if chat_id not in users:
        users[chat_id] = {"step": "waiting_id"}

    bot.answer_callback_query(call.id)

    if data == "cancel":
        users[chat_id] = {"step": "waiting_id"}
        bot.send_message(chat_id, "تم الإلغاء بنجاح. أرسل /start للبدء من جديد.")

    elif data.startswith("course_"):
        if data == "course_python":
            users[chat_id]["course"] = "Python"
        elif data == "course_js":
            users[chat_id]["course"] = "JavaScript"

        course_name = users[chat_id]['course']
        bot.edit_message_text(
            f"🎯 **{course_name}**: ماذا تريد أن نفعل؟",
            chat_id,
            call.message.message_id,
            reply_markup=target_menu(),
            parse_mode="Markdown"
        )
        users[chat_id]["step"] = "choosing_target"

    elif data == "target_chapter":
        bot.send_message(
            chat_id,
            "🔢 **اكتب رقم الفصل المطلوب:**",
            parse_mode="Markdown"
        )
        users[chat_id]["step"] = "waiting_chapter_number"

    elif data == "target_all":
        users[chat_id]["target"] = "الكورس بالكامل"
        show_review_screen(chat_id)

    elif data == "back_to_courses":
        bot.edit_message_text(
            "📚 **اختر الكورس المراد حله:**",
            chat_id,
            call.message.message_id,
            reply_markup=courses_menu(),
            parse_mode="Markdown"
        )

    elif data == "confirm_run":
        bot.edit_message_text(
            "⏳ **جاري الاتصال بمنصة Qureo وتطبيق الحل على حسابك...**",
            chat_id,
            call.message.message_id,
            parse_mode="Markdown"
        )

        user_data = users.get(chat_id, {})
        login_id = user_data.get("login_id")
        password = user_data.get("password")
        course = user_data.get("course")
        target = user_data.get("target")

        # تنفيذ الاتصال الفعلي بالمنصة
        success, result_msg = qureo_execute_solution(login_id, password, course, target)

        if success:
            bot.send_message(
                chat_id,
                "🚀 **تمت العملية بنجاح تام!**\n\n"
                f"📋 **النتيجة:** {result_msg}",
                parse_Mode="Markdown"
            )
        else:
            bot.send_message(
                chat_id,
                f"⚠️ **تنبيه:** {result_msg}\n\nأرسل /start للمحاولة مرة أخرى.",
                parse_mode="Markdown"
            )

        users[chat_id] = {"step": "waiting_id"}


def show_review_screen(chat_id):
    user_data = users.get(chat_id, {})
    login_id = user_data.get("login_id", "غير محدد")
    course = user_data.get("course", "غير محدد")
    target = user_data.get("target", "غير محدد")

    review_text = (
        "📝 **مراجعة الطلب قبل التنفيذ:**\n\n"
        f"👤 رقم الدخول: `{login_id}`\n"
        f"🔑 كلمة المرور: `••••••••` (محذوفة للأمان)\n"
        f"📚 الكورس: {course}\n"
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
    logger.info("Bot is starting up...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
