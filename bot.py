"""
ملف bot.py الشامل والمحدث للبوت
يحتوي على: التدفق التفاعلي لمنصات Qureo و Sprix، مكتبة الكتب، الأسئلة التفاعلية، والاشتراك الإجباري المستثنى منه خطوات المنصة.
"""
import html
import os
import logging
import time

import telebot
import library
import qureo
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# =========================
# CONFIGURATION
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MAX_WRONG = 3
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
qureo_wizard = {}  # تخزين حالة الطالب المؤقتة في الذاكرة للتدفق التفاعلي

# =========================
# QUESTION BANK
# =========================

COURSES = {
    "py": {
        "name": "🐍 Python",
        "chapters": [
            {
                "title": "المتغيرات وأنواع البيانات",
                "questions": [
                    {
                        "q": "ما ناتج الكود التالي؟\n<code>x = 5\ny = '5'\nprint(type(x) == type(y))</code>",
                        "options": ["True", "False", "خطأ في الكود", "None"],
                        "answer": 1,
                        "hints": [
                            "قارن بين نوع <code>x</code> ونوع <code>y</code>، وليس بين قيمتيهما.",
                            "القيمة الموضوعة بين علامتي اقتباس تُعتبر نصاً (str) حتى لو كانت رقماً.",
                        ],
                        "explain": "<code>x</code> من النوع int و<code>y</code> من النوع str، فالنوعان مختلفان والنتيجة False.",
                    },
                ],
            },
        ],
    },
}

BOOKS = [
    {
        "title": "Automate the Boring Stuff with Python",
        "author": "Al Sweigart",
        "level": "مبتدئ",
        "topic": "Python",
        "desc": "كتاب عملي يعلمك بايثون عبر أمثلة لأتمتة المهام اليومية.",
        "url": "https://automatetheboringstuff.com/",
    },
]

def esc(s):
    return html.escape(str(s))

def library_home():
    markup = InlineKeyboardMarkup(row_width=1)
    for key, (name, _) in library.STAGES.items():
        markup.add(InlineKeyboardButton(name, callback_data=f"st:{key}"))
    markup.add(
        InlineKeyboardButton("💻 كتب البرمجة", callback_data="prog"),
        InlineKeyboardButton("📞 تواصل مع المالك", callback_data="contact"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="menu"),
    )
    return markup

def stage_menu(stage_key):
    _, grades = library.STAGES[stage_key]
    markup = InlineKeyboardMarkup(row_width=1)
    for g in grades:
        n = library.count_books(g)
        label = library.GRADES[g] + (f" ({n})" if n else "")
        markup.add(InlineKeyboardButton(label, callback_data=f"g:{g}"))
    markup.add(InlineKeyboardButton("⬅️ رجوع", callback_data="lib"))
    return markup

def _tcode(track):
    return track or "-"

def place_title(grade, track=None):
    title = library.GRADES[grade]
    if track:
        title += f" — {library.TRACK_LABELS[track]}"
    return title

def _back_from_track(grade, track):
    if not track:
        return f"st:{library.stage_of(grade)}"
    parent = library.TRACK_PARENT.get(track)
    return f"tk:{grade}:{parent}" if parent else f"g:{grade}"

def track_menu(grade, parent=None):
    keys = library.TRACK_CHILDREN[parent] if parent else library.GRADE_TRACKS[grade]
    markup = InlineKeyboardMarkup(row_width=1)
    for k in keys:
        n = library.count_books(grade, track=k)
        label = library.TRACK_BUTTONS[k] + (f" ({n})" if n else "")
        markup.add(InlineKeyboardButton(label, callback_data=f"tk:{grade}:{k}"))
    back = f"g:{grade}" if parent else f"st:{library.stage_of(grade)}"
    markup.add(InlineKeyboardButton("⬅️ رجوع", callback_data=back))
    return markup

def term_menu(grade, track=None):
    markup = InlineKeyboardMarkup(row_width=1)
    for t in (1, 2):
        n = library.count_books(grade, t, track)
        label = library.TERMS[t] + (f" ({n})" if n else "")
        markup.add(InlineKeyboardButton(label, callback_data=f"t:{grade}:{t}:{_tcode(track)}"))
    markup.add(InlineKeyboardButton("⬅️ رجوع", callback_data=_back_from_track(grade, track)))
    return markup

def subjects_menu(grade, term, track=None):
    entries = library.subject_entries(grade, term, track)
    markup = InlineKeyboardMarkup(row_width=1)
    for i, e in enumerate(entries):
        n = len(library.books_for_subjects(grade, term, e["subjects"], track))
        icon = "⭐" if e["elective"] else "📘"
        markup.add(InlineKeyboardButton(
            f"{icon} {e['label']}" + (f" ({n})" if n else ""),
            callback_data=f"s:{grade}:{term}:{_tcode(track)}:{i}",
        ))
    back = f"tk:{grade}:{track}" if track else f"g:{grade}"
    markup.add(InlineKeyboardButton("⬅️ رجوع", callback_data=back))
    return markup, bool(entries), any(e["elective"] for e in entries)

def subject_books_view(grade, term, track, idx):
    entry = library.subject_entries(grade, term, track)[idx]
    books = library.books_for_subjects(grade, term, entry["subjects"], track)
    lines = [f"{place_title(grade, track)} — {library.TERMS[term]}\n📘 <b>{esc(entry['label'])}</b>\n"]
    markup = InlineKeyboardMarkup(row_width=1)
    for book in books:
        lines.append(f"📖 {esc(book['title'])}")
        if book.get("file") or book.get("message_id"):
            markup.add(InlineKeyboardButton(f"📥 فتح: {book['title'][:40]}", callback_data=f"f:{book['id']}"))
        elif book.get("url"):
            markup.add(InlineKeyboardButton(f"🔗 {book['title'][:40]}", url=book["url"]))
    if not books:
        lines.append("لا توجد كتب في هذه المادة بعد.")
    markup.add(InlineKeyboardButton("⬅️ رجوع", callback_data=f"t:{grade}:{term}:{_tcode(track)}"))
    return "\n".join(lines), markup

# =========================
# FORCED SUBSCRIPTION (المستثنى منها خطوات المنصة)
# =========================

_sub_ok = {}

class SubscriptionCheckError(Exception):
    pass

def needs_subscription(data):
    # استثناء جميع خطوات وأزرار منصة Qureo و Sprix والقوائم الرئيسية من فحص الاشتراك لتجنب التوقف
    if data in ("contact", "menu", "qr", "qx", "qr_start_action") or data.startswith(("qr", "qrs", "qred", "qrc")):
        return False
    return True

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
    return (
        "🔒 <b>لاستخدام البوت لازم تشترك في الجروب أولاً</b>\n\n"
        f"📢 {handle}\n\n"
        "1️⃣ اضغط «اشترك في الجروب»\n"
        "2️⃣ ثم ارجع واضغط «تحققت من اشتراكي»"
    )

def join_markup(error=False):
    markup = InlineKeyboardMarkup(row_width=1)
    url = channel_url()
    if url and not error:
        markup.add(InlineKeyboardButton("📢 اشترك في الجروب", url=url))
    markup.add(InlineKeyboardButton("✅ تحققت من اشتراكي", callback_data="chk"))
    markup.add(
        InlineKeyboardButton("📞 تواصل مع المالك", callback_data="contact"),
        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu"),
    )
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

# =========================
# QUREO / SPRIX WIZARD MENUS
# =========================

def qureo_grade_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("الصف الثاني الثانوي", callback_data="qrs:s2"),
        InlineKeyboardButton("الصف الأول الثانوي", callback_data="qrs:s1"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="menu"),
    )
    return markup

def qureo_education_type_menu(grade_key):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📚 التعليم العام", callback_data=f"qred:{grade_key}:general"),
        InlineKeyboardButton("🕌 الأزهر الشريف", callback_data=f"qred:{grade_key}:azhar"),
        InlineKeyboardButton("⚙️ التعليم الفني", callback_data=f"qred:{grade_key}:technical"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="qr"),
    )
    return markup

def qureo_course_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💻 البرمجة وتكنولوجيا المعلومات", callback_data="qrc:programming"),
        InlineKeyboardButton("💰 الثقافة المالية (Sprix)", callback_data="qrc:financial"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="qr"),
    )
    return markup

def qureo_scope_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📌 فصل واحد", callback_data="qrs_one"),
        InlineKeyboardButton("📚 كل الفصول", callback_data="qrs_all"),
        InlineKeyboardButton("📑 عدة فصول", callback_data="qrs_some"),
        InlineKeyboardButton("❌ إلغاء", callback_data="qx"),
    )
    return markup

def qureo_confirm_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ ابدأ", callback_data="qr_start_action"),
        InlineKeyboardButton("❌ إلغاء", callback_data="qx"),
    )
    return markup

def qureo_cancel_markup():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("❌ إلغاء", callback_data="qx"))
    return markup

def _try_delete(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

# =========================
# CONTACT
# =========================

def contact_markup():
    digits = "".join(ch for ch in OWNER_WHATSAPP if ch.isdigit())
    if digits.startswith("0"):
        digits = "20" + digits[1:]
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("✈️ تليجرام", url=f"https://t.me/{OWNER_TELEGRAM}"),
        InlineKeyboardButton("💬 واتساب", url=f"https://wa.me/{digits}"),
        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu"),
    )
    return markup

def contact_text():
    return (
        "📞 <b>التواصل مع مالك البوت</b>\n\n"
        "لأي اقتراح أو مشكلة أو طلب كتاب، تواصل معنا:\n"
        f"✈️ تليجرام: @{esc(OWNER_TELEGRAM)}\n"
        f"💬 واتساب: <code>{esc(OWNER_WHATSAPP)}</code>"
    )

# =========================
# HELPERS
# =========================

def new_state():
    return {
        "course": None,
        "chapter": None,
        "q": 0,
        "wrong": [],
        "hints_used": 0,
        "score": 0,
        "finished_q": False,
    }

def get_state(chat_id):
    if chat_id not in users:
        users[chat_id] = new_state()
    return users[chat_id]

def show(chat_id, message_id, text, markup=None):
    try:
        if message_id:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
            return
    except Exception as e:
        logger.info("edit failed, sending new message: %s", e)
    bot.send_message(chat_id, text, reply_markup=markup)

def courses_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💻 منصة Qureo / Sprix", callback_data="qr"),
        InlineKeyboardButton("📚 مكتبة الكتب", callback_data="lib"),
        InlineKeyboardButton("📞 تواصل مع المالك", callback_data="contact"),
    )
    return markup

# =========================
# HANDLERS & WIZARD TEXT HANDLER
# =========================

def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("📊 التقدم"), KeyboardButton("🏫 البوابة"),
           KeyboardButton("📚 المكتبة"), KeyboardButton("❌ إلغاء"))
    return kb

@bot.message_handler(commands=["start", "help", "cancel"])
def start(message):
    chat_id = message.chat.id
    users[chat_id] = new_state()
    qureo_wizard.pop(chat_id, None)
    if not gate_message(message):
        return
    bot.send_message(
        chat_id,
        "👋 <b>مرحباً بك في مساعد التعلم والمنصات</b>\n\n"
        "اختر القسم المطلوب من الأزرار بالأسفل 👇",
        reply_markup=courses_menu(),
    )
    bot.send_message(chat_id, "استخدم الأزرار للتنقل السريع 👇", reply_markup=main_keyboard())

@bot.message_handler(commands=["contact"])
def contact(message):
    bot.send_message(message.chat.id, contact_text(), reply_markup=contact_markup())

def handle_qureo_wizard_text(message):
    chat_id = message.chat.id
    st = qureo_wizard.get(chat_id)
    if not st or "step" not in st:
        return False
    
    text = (message.text or "").strip()
    
    if st["step"] == "username":
        st["username"] = text
        st["step"] = "password"
        _try_delete(chat_id, message.message_id)
        bot.send_message(
            chat_id,
            "🔑 الآن أرسل <b>كلمة المرور</b>\n(سيتم حذف رسالتك فوراً للأمان 🔒)",
            reply_markup=qureo_cancel_markup()
        )
        return True

    elif st["step"] == "password":
        st["password"] = text
        st["step"] = "confirm"
        _try_delete(chat_id, message.message_id)  # حذف رسالة الباسورد فوراً
        
        summary = (
            "📝 <b>راجع ثم أكد:</b>\n\n"
            f"👤 الرقم: <code>{st.get('username')}</code>\n"
            f"🔑 كلمة المرور: <code>••••••••</code>\n"
            f"📚 الكورس: <b>{'الثقافة المالية' if st.get('course_type') == 'financial' else 'البرمجة'}</b>\n"
            f"🎯 المطلوب: <b>{st.get('scope', 'كل الفصول')}</b>\n\n"
            "اضغط على (ابدأ) لتنفيذ المطلوب عبر المنصة."
        )
        bot.send_message(chat_id, summary, reply_markup=qureo_confirm_menu())
        return True

    return False

@bot.message_handler(content_types=["text"])
def fallback(message):
    if not gate_message(message):
        return
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    
    if txt in ("📊 التقدم", "🏫 البوابة", "📚 المكتبة", "❌ إلغاء"):
        qureo_wizard.pop(chat_id, None)
        if txt in ("📊 التقدم", "🏫 البوابة"):
            return bot.send_message(chat_id, "💻 <b>منصة Qureo / Sprix</b>\n\nاختر صفك:", reply_markup=qureo_grade_menu())
        if txt == "📚 المكتبة":
            return bot.send_message(chat_id, "📚 <b>مكتبة الكتب</b>\n\nاختر المرحلة أو القسم:", reply_markup=library_home())
        return bot.send_message(chat_id, "تم الإلغاء.")
    
    if handle_qureo_wizard_text(message):
        return
        
    bot.send_message(chat_id, "استخدم الأزرار أو أرسل /start للبدء.")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    if needs_subscription(data):
        try:
            subscribed = is_subscribed(call.from_user.id, fresh=data == "chk" or data.startswith("f:"))
        except SubscriptionCheckError:
            bot.answer_callback_query(call.id)
            return show(chat_id, msg_id, join_text(error=True), join_markup(error=True))
        if not subscribed:
            if data == "chk":
                return bot.answer_callback_query(call.id, "لم يتم العثور على اشتراكك بعد، اشترك أولاً.", show_alert=True)
            bot.answer_callback_query(call.id)
            return show(chat_id, msg_id, join_text(), join_markup())
        if data == "chk":
            bot.answer_callback_query(call.id, "✅ تم التحقق، أهلاً بك!")
            return show(chat_id, msg_id, "📚 القائمة الرئيسية:", courses_menu())

    bot.answer_callback_query(call.id)

    # معالجات أزرار الـ Wizard الخاصة بـ Qureo و Sprix
    if data.startswith("qrs:"):
        if chat_id not in qureo_wizard:
            qureo_wizard[chat_id] = {}
        qureo_wizard[chat_id]["grade"] = data.split(":")[1]
        show(chat_id, msg_id, "🏫 اختر نوع التعليم:", qureo_education_type_menu(qureo_wizard[chat_id]["grade"]))

    elif data.startswith("qred:"):
        parts = data.split(":")
        if chat_id not in qureo_wizard:
            qureo_wizard[chat_id] = {}
        qureo_wizard[chat_id]["grade"] = parts[1]
        qureo_wizard[chat_id]["education_type"] = parts[2]
        show(chat_id, msg_id, "🎯 اختر الكورس المطلوب:", qureo_course_menu())

    elif data.startswith("qrc:"):
        if chat_id not in qureo_wizard:
            qureo_wizard[chat_id] = {}
        qureo_wizard[chat_id]["course_type"] = data.split(":")[1]
        show(chat_id, msg_id, "📊 ماذا تريد أن أحل؟", qureo_scope_menu())

    elif data.startswith("qrs_"):
        if chat_id not in qureo_wizard:
            qureo_wizard[chat_id] = {}
        scope_map = {"qrs_one": "فصل واحد", "qrs_all": "كل الفصول", "qrs_some": "عدة فصول"}
        qureo_wizard[chat_id]["scope"] = scope_map.get(data, "كل الفصول")
        qureo_wizard[chat_id]["step"] = "username"
        show(chat_id, msg_id, "🔑 أرسل <b>رقم الدخول (Username)</b> إلى المنصة:", qureo_cancel_markup())

    elif data == "qr_start_action":
        wz = qureo_wizard.get(chat_id, {})
        username = wz.get("username")
        password = wz.get("password")
        course_type = wz.get("course_type", "programming")
        
        wait = bot.send_message(chat_id, "⏳ جاري الاتصال بالمنصة وتنفيذ المطلوب...")
        try:
            result = qureo.fetch_progress(username, password, course_type)
        except qureo.LoginFailed:
            body = "❌ رقم الدخول أو كلمة المرور غير صحيحة. جرّب مجدداً."
        except qureo.NotConfigured:
            body = "⚠️ النظام غير مفعّل بشكل كامل حالياً."
        except qureo.QureoUnavailable:
            body = "⚠️ تعذر الوصول للمنصة حالياً، حاول لاحقاً."
        else:
            body = (
                "✅ <b>تمت العملية بنجاح!</b>\n\n"
                f"👤 رقم الدخول: <b>{esc(username)}</b>\n"
                f"📚 الكورس: <b>{'الثقافة المالية (Sprix)' if course_type == 'financial' else 'البرمجة'}</b>\n"
                f"📍 الحالة: <b>{esc(result.get('chapter', 'جاهز'))}</b>\n"
                f"💎 رصيد الدايموند: <b>{result.get('diamonds', 0)}</b>"
            )
        qureo_wizard.pop(chat_id, None)
        bot.send_message(chat_id, body, reply_markup=courses_menu())

    elif data == "qx":
        qureo_wizard.pop(chat_id, None)
        show(chat_id, msg_id, "❌ تم الإلغاء.", courses_menu())

    elif data == "qr":
        qureo_wizard.pop(chat_id, None)
        show(chat_id, msg_id, "💻 <b>منصة Qureo / Sprix</b>\n\nاختر صفك:", qureo_grade_menu())

    elif data == "menu":
        users[chat_id] = new_state()
        qureo_wizard.pop(chat_id, None)
        show(chat_id, msg_id, "📚 القائمة الرئيسية:", courses_menu())

    elif data == "contact":
        show(chat_id, msg_id, contact_text(), contact_markup())

    elif data == "lib":
        show(chat_id, msg_id, "📚 <b>مكتبة الكتب</b>\n\nاختر المرحلة أو القسم:", library_home())

    elif data.startswith("st:"):
        key = data.split(":")[1]
        if key in library.STAGES:
            show(chat_id, msg_id, f"{library.STAGES[key][0]}\n\nاختر الصف:", stage_menu(key))

    elif data.startswith("g:"):
        g = data.split(":")[1]
        if g in library.GRADES:
            if g in library.GRADE_TRACKS:
                show(chat_id, msg_id, f"{library.GRADES[g]}\n\nاختر المسار:", track_menu(g))
            else:
                show(chat_id, msg_id, f"{library.GRADES[g]}\n\nاختر الترم:", term_menu(g))

    elif data.startswith("tk:"):
        _, g, trk = data.split(":")
        if g in library.GRADE_TRACKS and trk in library.tracks_for_grade(g):
            if trk in library.TRACK_CHILDREN:
                show(chat_id, msg_id, f"{place_title(g, trk)}\n\nاختر التخصص:", track_menu(g, trk))
            else:
                show(chat_id, msg_id, f"{place_title(g, trk)}\n\nاختر الترم:", term_menu(g, trk))

    elif data.startswith("t:"):
        _, g, t, trk = data.split(":")
        trk = None if trk == "-" else trk
        if g in library.GRADES and int(t) in (1, 2) and (trk is None or trk in library.tracks_for_grade(g)):
            markup, has, has_elective = subjects_menu(g, int(t), trk)
            title = f"{place_title(g, trk)} — {library.TERMS[int(t)]}\n\n"
            body = "اختر المادة:" if has else "لا توجد كتب هنا بعد."
            show(chat_id, msg_id, title + body, markup)

    elif data.startswith("s:"):
        _, g, t, trk, i = data.split(":")
        trk = None if trk == "-" else trk
        if (
            g in library.GRADES and int(t) in (1, 2)
            and (trk is None or trk in library.tracks_for_grade(g))
            and 0 <= int(i) < len(library.subject_entries(g, int(t), trk))
        ):
            text, markup = subject_books_view(g, int(t), trk, int(i))
            show(chat_id, msg_id, text, markup)

    elif data.startswith("f:"):
        book = library.get_book(int(data.split(":")[1]))
        if not book or not (book.get("file") or book.get("message_id")):
            bot.send_message(chat_id, "⚠️ هذا الكتاب لم يعد متاحاً.")
        else:
            caption = esc(book["title"])
            try:
                if book.get("message_id"):
                    bot.copy_message(chat_id, book["channel_id"], book["message_id"],
                                     caption=caption, parse_mode="HTML")
                elif book.get("public_file_id"):
                    bot.send_document(chat_id, book["public_file_id"], caption=caption, parse_mode="HTML")
                else:
                    with open(library.file_path(book["file"]), "rb") as f:
                        sent = bot.send_document(chat_id, f, caption=caption, parse_mode="HTML")
                    library.set_public_file_id(book["id"], sent.document.file_id)
            except Exception as e:
                logger.error("Failed to send book: %s", e)
                bot.send_message(chat_id, "⚠️ تعذر إرسال الكتاب الآن، حاول لاحقاً.")

# =========================
# RUN BOT
# =========================

if __name__ == "__main__":
    logger.info("Bot is starting up...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
