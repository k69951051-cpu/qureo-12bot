import html
import os
import logging
import time
import threading

import telebot
import library
import qureo
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_TELEGRAM = os.getenv("OWNER_TELEGRAM", "keroo_cr7").lstrip("@")
OWNER_WHATSAPP = os.getenv("OWNER_WHATSAPP", "01203423169")

def _parse_chat(raw):
    raw = (raw or "").strip().replace("\u2212", "-").replace("\u2013", "-").replace(" ", "")
    if raw.endswith("-") and raw[:-1].isdigit():
        raw = "-" + raw[:-1]
    if raw.lstrip("-").isdigit():
        return int(raw)
    if raw and not raw.startswith("@"):
        raw = "@" + raw
    return raw

_raw_channel = os.getenv("REQUIRED_CHANNEL", "@Highschool_textbooks_group")
REQUIRED_CHANNEL = "" if _raw_channel.strip().lower() in ("off", "none", "0") else _parse_chat(_raw_channel)
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "").strip()
SUB_CACHE_SECONDS = int(os.getenv("SUB_CACHE_SECONDS", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in environment variables")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

users = {}
qr_flow = {}  # لتخزين خطوات إدخال بيانات المنصة مؤقتاً لكل طالب

def esc(s):
    return html.escape(str(s))

def courses_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📚 مكتبة الكتب", callback_data="lib"),
        InlineKeyboardButton("💻 منصة Qureo (مع الحل التلقائي)", callback_data="qr"),
        InlineKeyboardButton("📞 تواصل مع المالك", callback_data="contact"),
    )
    return markup

def qureo_grade_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🚀 تشغيل الحل التلقائي للفصول", callback_data="auto_solve_start"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="menu"),
    )
    return markup

# نظام التحقق من الاشتراك الإجباري
_sub_ok = {}

class SubscriptionCheckError(Exception):
    pass

def is_subscribed(user_id, fresh=False):
    if not REQUIRED_CHANNEL:
        return True
    if not fresh and time.time() - _sub_ok.get(user_id, 0) < SUB_CACHE_SECONDS:
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
    except Exception as e:
        logger.error("Subscription check failed: %s", e)
        raise SubscriptionCheckError() from e
    ok = member.status in ("creator", "administrator", "member") or (
        member.status == "restricted" and getattr(member, "is_member", False)
    )
    if ok:
        _sub_ok[user_id] = time.time()
    else:
        _sub_ok.pop(user_id, None)
    return ok

def channel_url():
    if CHANNEL_LINK:
        return CHANNEL_LINK
    if isinstance(REQUIRED_CHANNEL, str) and REQUIRED_CHANNEL.startswith("@"):
        return f"https://t.me/{REQUIRED_CHANNEL[1:]}"
    return None

def join_text(error=False):
    if error:
        return "⚠️ تعذر التحقق من اشتراكك الآن. حاول مرة أخرى لاحقاً."
    url = channel_url()
    handle = f'<a href="{esc(url)}">{esc(str(REQUIRED_CHANNEL))}</a>' if url else esc(str(REQUIRED_CHANNEL))
    return f"🔒 <b>لاستخدام البوت لازم تشترك في الجروب أولاً</b>\n\n📢 {handle}\n\nاضغط «تحققت من اشتراكي» بعد الانضمام."

def join_markup(error=False):
    markup = InlineKeyboardMarkup(row_width=1)
    url = channel_url()
    if url and not error:
        markup.add(InlineKeyboardButton("📢 اشترك في الجروب", url=url))
    markup.add(InlineKeyboardButton("✅ تحققت من اشتراكي", callback_data="chk"))
    return markup

def gate_message(message):
    user = message.from_user
    if not user:
        return True
    try:
        ok = is_subscribed(user.id)
    except SubscriptionCheckError:
        bot.send_message(message.chat.id, join_text(error=True), reply_markup=join_markup(error=True))
        return False
    if not ok:
        bot.send_message(message.chat.id, join_text(), reply_markup=join_markup())
        return False
    return True

@bot.message_handler(commands=["start", "help", "cancel"])
def start(message):
    chat_id = message.chat.id
    qr_flow.pop(chat_id, None)
    if not gate_message(message):
        return
    bot.send_message(
        chat_id,
        "👋 <b>مرحباً بك في بوت الخدمات التعليمية والحل التلقائي</b>\n\nاختر من القائمة أدناه:",
        reply_markup=courses_menu(),
    )

@bot.message_handler(content_types=["text"])
def fallback(message):
    chat_id = message.chat.id
    if not gate_message(message):
        return
    
    # معالجة خطوات إدخال اليوزر والباسورد للمنصة
    flow = qr_flow.get(chat_id)
    if flow:
        text = (message.text or "").strip()
        if flow["step"] == "username":
            flow["username"] = text
            flow["step"] = "password"
            try:
                bot.delete_message(chat_id, message.message_id)
            except Exception:
                pass
            bot.send_message(chat_id, "🔑 أرسل الآن <b>كلمة المرور (Password)</b> الخاصة بك:\n(سيتم مسحها فوراً للحفاظ على أمانك).")
            return
        elif flow["step"] == "password":
            username = flow["username"]
            password = text
            qr_flow.pop(chat_id, None)
            try:
                bot.delete_message(chat_id, message.message_id)
            except Exception:
                pass
            
            wait_msg = bot.send_message(chat_id, "🚀 جاري تشغيل المتصفح والدخول للمنصة في الخلفية...")
            
            def run_solver():
                try:
                    qureo.solve_qureo_automatically(username, password)
                    bot.edit_message_text("✅ <b>تمت العملية بنجاح!</b>\n\nتم الدخول على حسابك وحل الفصول المطلوبة.", chat_id, wait_msg.message_id)
                except qureo.LoginFailed:
                    bot.edit_message_text("❌ <b>فشل تسجيل الدخول:</b> التأكد من صحة اسم المستخدم أو كلمة المرور.", chat_id, wait_msg.message_id)
                except Exception as e:
                    bot.edit_message_text(f"⚠️ <b>حدث خطأ:</b> {str(e)}", chat_id, wait_msg.message_id)

            threading.Thread(target=run_solver, daemon=True).start()
            return

    bot.send_message(chat_id, "استخدم الأزرار التفاعلية أو أرسل /start للبدء.")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    if data == "chk":
        try:
            sub = is_subscribed(call.from_user.id, fresh=True)
        except SubscriptionCheckError:
            return bot.answer_callback_query(call.id, "تعذر التحقق حالياً.", show_alert=True)
        if not sub:
            return bot.answer_callback_query(call.id, "لم تقم بالاشتراك في الجروب بعد!", show_alert=True)
        bot.answer_callback_query(call.id, "✅ تم التحقق بنجاح!")
        return bot.edit_message_text("📚 القائمة الرئيسية:", chat_id, msg_id, reply_markup=courses_menu())

    bot.answer_callback_query(call.id)

    if data == "menu":
        bot.edit_message_text("📚 القائمة الرئيسية:", chat_id, msg_id, reply_markup=courses_menu())
    elif data == "qr":
        bot.edit_message_text("💻 <b>منصة Qureo للبرمجة والحل التلقائي</b>\n\nاضغط على الزر أدناه لبدء عملية الأتمتة:", chat_id, msg_id, reply_markup=qureo_grade_menu())
    elif data == "auto_solve_start":
        qr_flow[chat_id] = {"step": "username"}
        bot.edit_message_text("👤 <b>الخطوة 1 من 2:</b>\n\nأرسل الآن <b>اسم المستخدم (Username)</b> الخاص بك على المنصة عبر الرسائل:", chat_id, msg_id)
    elif data == "contact":
        bot.edit_message_text(f"📞 التواصل مع المالك:\nتليجرام: @{esc(OWNER_TELEGRAM)}\nواتساب: {esc(OWNER_WHATSAPP)}", chat_id, msg_id, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="menu")]]))

if __name__ == "__main__":
    logger.info("Bot is starting up with automation support...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
