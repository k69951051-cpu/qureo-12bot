import os
import json
import logging
import requests
import telebot

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# CONFIG
# =========================

BOT_TOKEN = "9150114718:AAHwz8AxdEp_APewCSDy3zoxoB8vkdEHJdc"
BASE_URL = "https://me-tp.qureo.education"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in Railway Variables")

bot = telebot.TeleBot(BOT_TOKEN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# تخزين بيانات وحالة كل مستخدم (الـ ID، الباسورد، التوكن، والخطوة الحالية)
users = {}


# =========================
# KEYBOARDS (القوائم والأزرار)
# =========================

def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💻 تسجيل الدخول لمنصة Qureo", callback_data="start_login"),
        InlineKeyboardButton("ℹ️ عن البوت", callback_data="about")
    )
    return markup


def dashboard_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🐍 جلب بيانات كورس Python", callback_data="python_data"),
        InlineKeyboardButton("🚪 تسجيل خروج / تغيير الحساب", callback_data="logout"),
        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")
    )
    return markup


def back_home_menu():
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")
    )
    return markup


# =========================
# API FUNCTIONS (الربط بالمنصة)
# =========================

def authenticate_user(login_id, password):
    """إرسال بيانات الدخول للمنصة للحصول على التوكن الخاص بالمستخدم"""
    login_url = f"{BASE_URL}/api/auth/login"  # (أو رابط الـ Login الفعلي للمنصة)
    payload = {
        "login_id": login_id,
        "password": password
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    
    try:
        response = requests.post(login_url, json=payload, headers=headers, timeout=20)
        if response.status_code == 200:
            data = response.json()
            # استخراج التوكن من الاستجابة (ح حسب شكل الـ JSON العائد من المنصة)
            token = data.get("token") or data.get("access_token")
            return token, None
        elif response.status_code in (401, 403):
            return None, "خطأ: معرف الدخول أو كلمة المرور غير صحيحة."
        else:
            return None, f"تعذر الاتصال بالمنصة (كود الخطأ: {response.status_code})."
    except Exception as e:
        logger.error("Login request failed: %s", str(e))
        return None, "حدث خطأ شبكي أثناء الاتصال بالمنصة."


def get_qureo_data(url, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code in (401, 403):
            return None, "انتهت صلاحية الجلسة، يرجى تسجيل الدخول مرة أخرى."
        response.raise_for_status()
        return response.json(), None
    except Exception as e:
        logger.error("API request failed: %s", str(e))
        return None, "فشل جلب البيانات من المنصة."


def format_data(data, max_length=3500):
    if data is None:
        return "لا توجد بيانات."
    result = json.dumps(data, ensure_ascii=False, indent=2)
    if len(result) > max_length:
        result = result[:max_length] + "\n... تم اختصار النتيجة"
    return result


# =========================
# COMMANDS (الأوامر)
# =========================

@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id
    # إعادة ضبط حالة المستخدم عند البداية لمنع التكرار
    users[chat_id] = {"step": "home", "login_id": None, "password": None, "token": None}

    bot.send_message(
        chat_id,
        "أهلاً بك يا بطل في بوت منصة Qureo التعليمي 🚀\n\n"
        "يرجى اختيار الإجراء المناسب:",
        reply_markup=main_menu()
    )


@bot.message_handler(commands=["cancel", "help"])
def cancel_or_help(message):
    chat_id = message.chat.id
    users[chat_id] = {"step": "home", "login_id": None, "password": None, "token": None}
    bot.send_message(
        chat_id,
        "تم العودة للقائمة الرئيسية.",
        reply_markup=main_menu()
    )


# =========================
# CALLBACK HANDLERS (الأزرار التفاعلية)
# =========================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    data = call.data

    if chat_id not in users:
        users[chat_id] = {"step": "home", "login_id": None, "password": None, "token": None}

    bot.answer_callback_query(call.id)

    if data == "home" or data == "logout":
        users[chat_id] = {"step": "home", "login_id": None, "password": None, "token": None}
        bot.send_message(
            chat_id,
            "🏠 القائمة الرئيسية:",
            reply_markup=main_menu()
        )

    elif data == "start_login":
        users[chat_id]["step"] = "waiting_id"
        bot.send_message(
            chat_id,
            "🆔 **الخطوة 1 من 2:**\nالرجاء إرسال **معرف الدخول (Login ID)** الخاص بك الآن:"
        )

    elif data == "python_data":
        token = users[chat_id].get("token")
        if not token:
            bot.send_message(chat_id, "⚠️ يجب تسجيل الدخول أولاً.", reply_markup=main_menu())
            return

        bot.send_message(chat_id, "⏳ جاري سحب بيانات كورس Python من المنصة...")
        
        chapters_url = f"{BASE_URL}/api/study/students/sections/106/chapters"
        chapters, err1 = get_qureo_data(chapters_url, token)
        if err1:
            bot.send_message(chat_id, "⚠️ " + err1)
            return

        diamond_url = f"{BASE_URL}/api/study/students/courses/python_short_ar/diamond"
        diamonds, err2 = get_qureo_data(diamond_url, token)
        if err2:
            bot.send_message(chat_id, "⚠️ " + err2)
            return

        text = (
            "🐍 **بيانات كورس Python الحقيقية:**\n\n"
            "📚 **الفصول:**\n" + format_data(chapters, 1500) +
            "\n\n💎 **Diamonds:**\n" + format_data(diamonds, 1500)
        )
        bot.send_message(chat_id, text, reply_markup=dashboard_menu())

    elif data == "about":
        bot.send_message(
            chat_id,
            "بوت تفاعلي متقدم لربط طلاب Qureo بالمنصة مباشرة وسحب بياناتهم وحل تدريباتهم بكل مرونة.",
            reply_markup=back_home_menu()
        )


# =========================
# MESSAGE HANDLERS (معالجة النصوص وإدخال البيانات)
# =========================

@bot.message_handler(content_types=["text"])
def handle_text_inputs(message):
    chat_id = message.chat.id
    text = message.text.strip()

    if chat_id not in users:
        users[chat_id] = {"step": "home", "login_id": None, "password": None, "token": None}

    current_step = users[chat_id].get("step")

    # الخطوة 1: استقبال معرف الدخول (Login ID)
    if current_step == "waiting_id":
        users[chat_id]["login_id"] = text
        users[chat_id]["step"] = "waiting_password"
        bot.send_message(
            chat_id,
            "🔑 **الخطوة 2 من 2:**\nتم حفظ المعرف بنجاح.\nالرجاء إرسال **كلمة المرور (Password)** الخاصة بك:"
        )

    # الخطوة 2: استقبال كلمة المرور وتنفيذ المصادقة مع المنصة
    elif current_step == "waiting_password":
        users[chat_id]["password"] = text
        login_id = users[chat_id]["login_id"]
        password = users[chat_id]["password"]

        bot.send_message(chat_id, "🔄 جاري التحقق وتسجيل الدخول إلى منصة Qureo...")

        token, error = authenticate_user(login_id, password)

        if error:
            users[chat_id]["step"] = "home"
            bot.send_message(
                chat_id,
                f"❌ {error}\n\nيرجى المحاولة مرة أخرى من القائمة الرئيسية.",
                reply_markup=main_menu()
            )
            return

        # حفظ التوكن بنجاح وتحديث الحالة
        users[chat_id]["token"] = token
        users[chat_id]["step"] = "logged_in"
        # مسح كلمة المرور من الذاكرة لأسباب أمنية
        users[chat_id]["password"] = None

        bot.send_message(
            chat_id,
            "✅ **تم تسجيل الدخول بنجاح وتأكيد الربط مع المنصة!** 🚀\n\n"
            "يمكنك الآن اختيار ما تحب استعراضه من لوحة التحكم:",
            reply_markup=dashboard_menu()
        )

    else:
        bot.send_message(
            chat_id,
            "استخدم الأزرار التفاعلية الموجودة في القائمة، أو اضغط /start للبدء من جديد."
        )


# =========================
# RUN BOT
# =========================

if __name__ == "__main__":
    logger.info("Bot is starting...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
