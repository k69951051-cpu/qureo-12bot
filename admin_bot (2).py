"""
بوت الإدارة (خاص بك فقط).
ترسل له ملف PDF أو رابطاً، فيتعرف تلقائياً على الصف والترم والمادة من الاسم/الوصف،
وتراجعها ثم تضغط حفظ، فينزل الكتاب في البوت العام.
"""
import html
import logging
import os

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

import detect
import library

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")
# أرقام حسابات الأدمن على تليجرام، مفصولة بفاصلة. مثال: 123456789,987654321
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}
MAX_DOWNLOAD = 20 * 1024 * 1024  # حد تليجرام لتنزيل الملفات عبر البوت (يُستخدم فقط بدون قناة تخزين)


def _parse_channel_id(raw):
    """يقبل الرقم حتى لو انعكست علامة الناقص إلى آخره بسبب لوحة المفاتيح العربية."""
    raw = (raw or "").strip().replace("−", "-").replace("–", "-").replace(" ", "")
    if raw.endswith("-"):
        raw = "-" + raw[:-1]
    try:
        return int(raw) if raw else 0
    except ValueError:
        logging.getLogger(__name__).error("STORAGE_CHANNEL_ID value is invalid: %r", raw)
        return 0


# قناة تخزين خاصة (رقمها يبدأ بـ -100). مع وجودها تُقبل الملفات بأي حجم (حتى 2 جيجا)
STORAGE_CHANNEL_ID = _parse_channel_id(os.getenv("STORAGE_CHANNEL_ID", ""))

if not ADMIN_BOT_TOKEN:
    raise RuntimeError("ADMIN_BOT_TOKEN is missing in environment variables")

bot = telebot.TeleBot(ADMIN_BOT_TOKEN, parse_mode="HTML")
logger = logging.getLogger(__name__)

# العملية الجارية لكل أدمن: {admin_id: {...}}
pending = {}


def esc(s):
    return html.escape(str(s))


def is_admin(user_id):
    return user_id in ADMIN_IDS


def deny(message):
    bot.send_message(
        message.chat.id,
        "⛔ هذا البوت خاص بالإدارة.\n"
        f"رقم حسابك: <code>{message.from_user.id}</code>\n"
        "إذا كنت صاحب المشروع ضع هذا الرقم في متغير ADMIN_IDS على Railway.",
    )


# =========================
# شاشة المراجعة
# =========================

def summary_text(st):
    grade = library.GRADES.get(st.get("grade")) or "❓ غير محدد"
    term = library.TERMS.get(st["term"]) if st.get("term") is not None else "❓ غير محدد"
    subject = esc(st["subject"]) if st.get("subject") else "❓ غير محدد"
    return (
        f"📖 <b>{esc(st['title'])}</b>\n\n"
        f"🎓 الصف: {grade}\n"
        f"📅 الترم: {term}\n"
        f"📘 المادة: {subject}\n\n"
        "راجع البيانات (تم التعرف عليها تلقائياً من الاسم) ثم اضغط حفظ."
    )


def summary_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("✅ حفظ ونشر", callback_data="sv"))
    markup.add(
        InlineKeyboardButton("🎓 الصف", callback_data="eg"),
        InlineKeyboardButton("📅 الترم", callback_data="et"),
        InlineKeyboardButton("📘 المادة", callback_data="es"),
        InlineKeyboardButton("✏️ الاسم", callback_data="en"),
    )
    markup.add(InlineKeyboardButton("❌ إلغاء", callback_data="ac"))
    return markup


def show_summary(chat_id, uid, message_id=None):
    st = pending.get(uid)
    if not st:
        return
    text, markup = summary_text(st), summary_markup()
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
            return
        except Exception as e:
            logger.info("edit failed: %s", e)
    bot.send_message(chat_id, text, reply_markup=markup)


def start_pending(message, state):
    """يبدأ عملية جديدة بعد التعرف التلقائي على الصف والترم والمادة."""
    found = detect.detect(f"{state['title']} {state.get('file_name') or ''}")
    state.update({"grade": found["grade"], "term": found["term"], "subject": found["subject"]})
    pending[message.from_user.id] = state
    show_summary(message.chat.id, message.from_user.id)


# =========================
# الأوامر
# =========================

@bot.message_handler(commands=["start", "help"])
def start(message):
    if not is_admin(message.from_user.id):
        return deny(message)
    bot.send_message(
        message.chat.id,
        "👋 <b>بوت إدارة المكتبة</b>\n\n"
        "📎 أرسل ملف PDF ويمكنك كتابة اسم الكتاب في الوصف (caption).\n"
        "🔗 أو أرسل رابطاً بهذا الشكل:\n<code>اسم الكتاب | https://...</code>\n\n"
        "سأتعرف تلقائياً على الصف والترم والمادة من الاسم، "
        "وتراجعها وتضغط حفظ فينزل الكتاب في البوت العام.\n\n"
        "💡 اكتب في اسم الملف مثل: <i>الصف الثالث الابتدائي الترم الثاني رياضيات</i> "
        "لتكون النتيجة أدق.\n\n"
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
    for i in range(0, len(books), 10):
        chunk = books[i:i + 10]
        lines, markup = [], InlineKeyboardMarkup(row_width=1)
        for b in chunk:
            grade = library.GRADES.get(b["grade"], b["grade"])
            term = library.TERMS.get(b.get("term", 0), "")
            lines.append(f"#{b['id']} {esc(b['title'])}\n   {grade} / {term} / {esc(b['subject'])}")
            markup.add(InlineKeyboardButton(f"🗑 حذف #{b['id']}", callback_data=f"del:{b['id']}"))
        bot.send_message(message.chat.id, "\n\n".join(lines), reply_markup=markup)


# =========================
# استقبال الملفات والنصوص
# =========================

@bot.message_handler(content_types=["document"])
def on_document(message):
    uid = message.from_user.id
    if not is_admin(uid):
        return deny(message)
    doc = message.document
    if not STORAGE_CHANNEL_ID and doc.file_size and doc.file_size > MAX_DOWNLOAD:
        return bot.send_message(
            message.chat.id,
            "⚠️ الملف أكبر من 20 ميجا ولا يمكن للبوت تنزيله.\n"
            "فعّل قناة التخزين (متغير STORAGE_CHANNEL_ID) لقبول الملفات الكبيرة، "
            "أو أرسل رابطه بالشكل: <code>اسم الكتاب | الرابط</code>",
        )
    title = (message.caption or "").strip() or os.path.splitext(doc.file_name or "كتاب")[0].replace("_", " ")
    start_pending(message, {
        "kind": "file", "file_id": doc.file_id, "file_name": doc.file_name, "title": title,
        "src_chat": message.chat.id, "src_msg": message.message_id,
    })


@bot.message_handler(content_types=["text"])
def on_text(message):
    uid = message.from_user.id
    if not is_admin(uid):
        return deny(message)
    text = message.text.strip()
    state = pending.get(uid)

    # لمعرفة رقم القناة: حوّل أي رسالة من القناة إلى هذا البوت
    fwd = getattr(message, "forward_from_chat", None)
    if fwd is None:
        fwd = getattr(getattr(message, "forward_origin", None), "chat", None)
    if fwd is not None:
        return bot.send_message(
            message.chat.id,
            f"🆔 رقم القناة: <code>{fwd.id}</code>\nضعه في متغير STORAGE_CHANNEL_ID على Railway.",
        )

    # انتظار نص: مادة جديدة أو اسم جديد
    if state and state.get("await") == "subject":
        state["subject"] = text
        state.pop("await")
        return show_summary(message.chat.id, uid)
    if state and state.get("await") == "title":
        state["title"] = text
        state.pop("await")
        return show_summary(message.chat.id, uid)

    # رابط بالشكل: العنوان | الرابط
    if "|" in text and "http" in text:
        title, _, url = text.partition("|")
        title, url = title.strip(), url.strip()
        if title and url.startswith("http"):
            return start_pending(message, {"kind": "link", "url": url, "title": title})

    bot.send_message(message.chat.id, "أرسل ملف PDF أو رابطاً بالشكل: <code>اسم الكتاب | https://...</code>")


# =========================
# الحفظ
# =========================

def finish(chat_id, uid):
    state = pending.pop(uid, None)
    if not state:
        return
    file_name = None
    channel_id = message_id = None
    try:
        if state["kind"] == "file":
            if STORAGE_CHANNEL_ID:
                info = (
                    f"{state['title']}\n"
                    f"{library.GRADES[state['grade']]} | {library.TERMS[state['term']]} | {state['subject']}"
                )
                # ننسخ الرسالة إلى قناة التخزين (بدون تنزيل، لذلك لا يوجد حد للحجم)
                copied = bot.copy_message(
                    STORAGE_CHANNEL_ID, state["src_chat"], state["src_msg"],
                    caption=info, parse_mode=None,
                )
                channel_id, message_id = STORAGE_CHANNEL_ID, copied.message_id
            else:
                tg_file = bot.get_file(state["file_id"])
                data = bot.download_file(tg_file.file_path)
                file_name = library.save_file(data, state.get("file_name") or "book.pdf")
        book = library.add_book(
            state["grade"], state["term"], state["subject"], state["title"],
            file_name=file_name, url=state.get("url"),
            channel_id=channel_id, message_id=message_id,
        )
    except Exception as e:
        logger.error("Failed to save book: %s", e)
        return bot.send_message(chat_id, "⚠️ حدث خطأ أثناء حفظ الكتاب، حاول مرة أخرى.")
    bot.send_message(
        chat_id,
        f"✅ تمت إضافة <b>{esc(book['title'])}</b>\n"
        f"🎓 {library.GRADES[book['grade']]}\n"
        f"📅 {library.TERMS[book['term']]}\n"
        f"📘 {esc(book['subject'])}\n\n"
        "ظهر الآن في البوت العام.",
    )


# =========================
# الأزرار
# =========================

@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    uid = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    if not is_admin(uid):
        return bot.answer_callback_query(call.id, "غير مسموح")
    data = call.data
    state = pending.get(uid)

    if data.startswith("del:"):
        bot.answer_callback_query(call.id)
        book = library.get_book(int(data.split(":")[1]))
        if book and book.get("channel_id"):
            try:
                bot.delete_message(book["channel_id"], book["message_id"])
            except Exception as e:
                logger.warning("Could not delete channel message: %s", e)
        ok = library.delete_book(int(data.split(":")[1]))
        return bot.send_message(chat_id, "🗑 تم الحذف." if ok else "الكتاب غير موجود.")

    if data == "ac":
        bot.answer_callback_query(call.id)
        pending.pop(uid, None)
        return bot.edit_message_text("تم الإلغاء.", chat_id, msg_id)

    if not state:
        return bot.answer_callback_query(call.id, "انتهت العملية، أرسل الملف من جديد.", show_alert=True)

    if data == "sv":
        if state.get("grade") is None or state.get("term") is None or not state.get("subject"):
            return bot.answer_callback_query(call.id, "حدد الصف والترم والمادة أولاً.", show_alert=True)
        bot.answer_callback_query(call.id)
        bot.edit_message_text("⏳ جاري الحفظ...", chat_id, msg_id)
        return finish(chat_id, uid)

    bot.answer_callback_query(call.id)

    if data == "eg":  # اختيار الصف
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(*[
            InlineKeyboardButton(name, callback_data=f"xg:{key}")
            for key, name in library.GRADES.items()
        ])
        bot.edit_message_text("🎓 اختر الصف:", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("xg:"):
        key = data.split(":")[1]
        if key in library.GRADES:
            state["grade"] = key
        show_summary(chat_id, uid, msg_id)

    elif data == "et":  # اختيار الترم
        markup = InlineKeyboardMarkup(row_width=1)
        for key in (1, 2, 0):
            markup.add(InlineKeyboardButton(library.TERMS[key], callback_data=f"xt:{key}"))
        bot.edit_message_text("📅 اختر الترم:", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("xt:"):
        key = int(data.split(":")[1])
        if key in library.TERMS:
            state["term"] = key
        show_summary(chat_id, uid, msg_id)

    elif data == "es":  # اختيار المادة
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(*[
            InlineKeyboardButton(name, callback_data=f"xs:{i}")
            for i, name in enumerate(library.SUBJECTS)
        ])
        markup.add(InlineKeyboardButton("✍️ مادة أخرى (اكتبها)", callback_data="xo"))
        bot.edit_message_text("📘 اختر المادة:", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("xs:"):
        idx = int(data.split(":")[1])
        if 0 <= idx < len(library.SUBJECTS):
            state["subject"] = library.SUBJECTS[idx]
        show_summary(chat_id, uid, msg_id)

    elif data == "xo":
        state["await"] = "subject"
        bot.edit_message_text("✍️ اكتب اسم المادة:", chat_id, msg_id)

    elif data == "en":
        state["await"] = "title"
        bot.edit_message_text("✏️ اكتب اسم الكتاب الجديد:", chat_id, msg_id)
