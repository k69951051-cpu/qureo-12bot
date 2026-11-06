"""
بوت الإدارة (خاص بك فقط).
ترسل له ملف PDF أو رابطاً، تختار الصف والمادة، فيظهر الكتاب تلقائياً في البوت العام.
"""
import logging
import os

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

import library

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")
# أرقام حسابات الأدمن على تليجرام، مفصولة بفاصلة. مثال: 123456789,987654321
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}
MAX_DOWNLOAD = 20 * 1024 * 1024  # حد تليجرام لتنزيل الملفات عبر البوت

if not ADMIN_BOT_TOKEN:
    raise RuntimeError("ADMIN_BOT_TOKEN is missing in environment variables")

bot = telebot.TeleBot(ADMIN_BOT_TOKEN, parse_mode="HTML")
logger = logging.getLogger(__name__)

# العملية الجارية لكل أدمن: {admin_id: {...}}
pending = {}


def is_admin(user_id):
    return user_id in ADMIN_IDS


def deny(message):
    bot.send_message(
        message.chat.id,
        "⛔ هذا البوت خاص بالإدارة.\n"
        f"رقم حسابك: <code>{message.from_user.id}</code>\n"
        "إذا كنت صاحب المشروع ضع هذا الرقم في متغير ADMIN_IDS على Railway.",
    )


def grades_markup():
    markup = InlineKeyboardMarkup(row_width=1)
    for key, name in library.GRADES.items():
        markup.add(InlineKeyboardButton(name, callback_data=f"ag:{key}"))
    markup.add(InlineKeyboardButton("❌ إلغاء", callback_data="ac"))
    return markup


def subjects_markup(grade):
    markup = InlineKeyboardMarkup(row_width=1)
    for i, name in enumerate(library.subjects(grade)):
        markup.add(InlineKeyboardButton(f"📘 {name}", callback_data=f"as:{i}"))
    markup.add(
        InlineKeyboardButton("➕ مادة جديدة", callback_data="an"),
        InlineKeyboardButton("❌ إلغاء", callback_data="ac"),
    )
    return markup


@bot.message_handler(commands=["start", "help"])
def start(message):
    if not is_admin(message.from_user.id):
        return deny(message)
    bot.send_message(
        message.chat.id,
        "👋 <b>بوت إدارة المكتبة</b>\n\n"
        "📎 أرسل ملف PDF (حتى 20 ميجا) ويمكنك كتابة اسم الكتاب في الوصف (caption).\n"
        "🔗 أو أرسل رابطاً بهذا الشكل:\n<code>اسم الكتاب | https://...</code>\n\n"
        "بعدها اختر الصف والمادة وسينزل الكتاب تلقائياً في البوت العام.\n\n"
        "/books لعرض الكتب وحذفها، /cancel للإلغاء.",
    )


@bot.message_handler(commands=["cancel"])
def cancel(message):
    if is_admin(message.from_user.id):
        pending.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "تم الإلغاء.")


@bot.message_handler(commands=["books"])
def list_books(message):
    if not is_admin(message.from_user.id):
        return deny(message)
    books = library.all_books()
    if not books:
        return bot.send_message(message.chat.id, "لا توجد كتب بعد.")
    markup = InlineKeyboardMarkup(row_width=1)
    lines = []
    for b in books:
        grade = library.GRADES.get(b["grade"], b["grade"])
        lines.append(f"#{b['id']} {b['title']} — {grade} / {b['subject']}")
        markup.add(InlineKeyboardButton(f"🗑 حذف #{b['id']}", callback_data=f"del:{b['id']}"))
    bot.send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.message_handler(content_types=["document"])
def on_document(message):
    uid = message.from_user.id
    if not is_admin(uid):
        return deny(message)
    doc = message.document
    if doc.file_size and doc.file_size > MAX_DOWNLOAD:
        return bot.send_message(
            message.chat.id,
            "⚠️ الملف أكبر من 20 ميجا ولا يمكن للبوت تنزيله.\n"
            "ارفعه على أي موقع/قناة وأرسل رابطه بالشكل: <code>اسم الكتاب | الرابط</code>",
        )
    title = (message.caption or "").strip() or os.path.splitext(doc.file_name or "كتاب")[0]
    pending[uid] = {"kind": "file", "file_id": doc.file_id, "file_name": doc.file_name, "title": title}
    bot.send_message(message.chat.id, f"📖 <b>{title}</b>\n\nاختر الصف:", reply_markup=grades_markup())


@bot.message_handler(content_types=["text"])
def on_text(message):
    uid = message.from_user.id
    if not is_admin(uid):
        return deny(message)
    text = message.text.strip()
    state = pending.get(uid)

    # انتظار اسم مادة جديدة
    if state and state.get("awaiting_subject"):
        grade = state["grade"]
        name = library.add_subject(grade, text)
        state["subject"] = name
        return finish(message.chat.id, uid)

    # رابط بالشكل: العنوان | الرابط
    if "|" in text and "http" in text:
        title, _, url = text.partition("|")
        title, url = title.strip(), url.strip()
        if title and url.startswith("http"):
            pending[uid] = {"kind": "link", "url": url, "title": title}
            return bot.send_message(message.chat.id, f"🔗 <b>{title}</b>\n\nاختر الصف:", reply_markup=grades_markup())

    bot.send_message(message.chat.id, "أرسل ملف PDF أو رابطاً بالشكل: <code>اسم الكتاب | https://...</code>")


def finish(chat_id, uid):
    state = pending.pop(uid, None)
    if not state:
        return
    file_name = None
    try:
        if state["kind"] == "file":
            info = bot.get_file(state["file_id"])
            data = bot.download_file(info.file_path)
            file_name = library.save_file(data, state.get("file_name") or "book.pdf")
        book = library.add_book(
            state["grade"], state["subject"], state["title"],
            file_name=file_name, url=state.get("url"),
        )
    except Exception as e:
        logger.error("Failed to save book: %s", e)
        return bot.send_message(chat_id, "⚠️ حدث خطأ أثناء حفظ الكتاب، حاول مرة أخرى.")
    bot.send_message(
        chat_id,
        f"✅ تمت إضافة <b>{book['title']}</b>\n"
        f"{library.GRADES[book['grade']]} / {book['subject']}\n\n"
        "ظهر الآن في البوت العام.",
    )


@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    uid = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    if not is_admin(uid):
        return bot.answer_callback_query(call.id, "غير مسموح")
    bot.answer_callback_query(call.id)
    data = call.data
    state = pending.get(uid)

    if data == "ac":
        pending.pop(uid, None)
        bot.edit_message_text("تم الإلغاء.", chat_id, msg_id)

    elif data.startswith("ag:") and state:
        grade = data.split(":")[1]
        if grade in library.GRADES:
            state["grade"] = grade
            bot.edit_message_text(
                f"{library.GRADES[grade]}\n\nاختر المادة:", chat_id, msg_id,
                reply_markup=subjects_markup(grade),
            )

    elif data.startswith("as:") and state and state.get("grade"):
        subjects = library.subjects(state["grade"])
        idx = int(data.split(":")[1])
        if 0 <= idx < len(subjects):
            state["subject"] = subjects[idx]
            bot.edit_message_text("⏳ جاري الحفظ...", chat_id, msg_id)
            finish(chat_id, uid)

    elif data == "an" and state and state.get("grade"):
        state["awaiting_subject"] = True
        bot.edit_message_text("✍️ اكتب اسم المادة الجديدة:", chat_id, msg_id)

    elif data.startswith("del:"):
        ok = library.delete_book(int(data.split(":")[1]))
        bot.send_message(chat_id, "🗑 تم الحذف." if ok else "الكتاب غير موجود.")
