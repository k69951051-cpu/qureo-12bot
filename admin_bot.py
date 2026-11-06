import html
import logging
import os
import queue
import threading
import time
import uuid
from collections import Counter

import telebot
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

import detect
import library

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}
MAX_DOWNLOAD = 20 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}

COPY_DELAY = float(os.getenv("COPY_DELAY", "1.2"))
IDLE_FLUSH = float(os.getenv("IDLE_FLUSH", "5"))
FLUSH_SIZE = int(os.getenv("FLUSH_SIZE", "200"))

import json

_SETTINGS_PATH = os.path.join(library.DATA_DIR, "admin_settings.json")


def _load_forced_term():
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as f:
            v = json.load(f).get("forced_term")
        return v if v in (1, 2) else None
    except (OSError, ValueError):
        return None


forced_term = _load_forced_term()


def set_forced_term(value):
    global forced_term
    forced_term = value if value in (1, 2) else None
    try:
        os.makedirs(library.DATA_DIR, exist_ok=True)
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump({"forced_term": forced_term}, f)
    except OSError as e:
        logger.error("Failed to save settings: %s", e)


def term_status_text():
    if forced_term:
        return f"📅 <b>الترم المحدد لكل الملفات:</b> {library.TERMS[forced_term]} 🔒"
    return "📅 <b>الترم:</b> تلقائي (من اسم الملف) — اختر ترماً من الأزرار لتثبيته لكل الملفات"


def term_lock_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    mark = lambda v, label: ("✅ " if forced_term == v else "") + label
    markup.add(
        InlineKeyboardButton(mark(1, "الترم الأول"), callback_data="ft:1"),
        InlineKeyboardButton(mark(2, "الترم الثاني"), callback_data="ft:2"),
    )
    markup.add(InlineKeyboardButton(mark(None, "🤖 تلقائي (من اسم الملف)"), callback_data="ft:auto"))
    return markup


def _parse_channel_id(raw):
    raw = (raw or "").strip().replace("\u2212", "-").replace("\u2013", "-").replace(" ", "")
    if raw.endswith("-"):
        raw = "-" + raw[:-1]
    try:
        return int(raw) if raw else 0
    except ValueError:
        logging.getLogger(__name__).error("STORAGE_CHANNEL_ID value is invalid: %r", raw)
        return 0


STORAGE_CHANNEL_ID = _parse_channel_id(os.getenv("STORAGE_CHANNEL_ID", ""))

if not ADMIN_BOT_TOKEN:
    raise RuntimeError("ADMIN_BOT_TOKEN is missing in environment variables")

bot = telebot.TeleBot(ADMIN_BOT_TOKEN, parse_mode="HTML")
logger = logging.getLogger(__name__)

pending = {}
batches = {}
_last_ack = {}


def esc(s):
    return html.escape(str(s))


def is_admin(user_id):
    return user_id in ADMIN_IDS


def _is_private(message):
    return message.chat.type == "private"


def _is_group(message):
    return message.chat.type in ("group", "supergroup")


def deny(message):
    bot.send_message(
        message.chat.id,
        "⛔ هذا البوت خاص بالإدارة.\n"
        f"رقم حسابك: <code>{message.from_user.id}</code>\n"
        "إذا كنت صاحب المشروع ضع هذا الرقم في متغير ADMIN_IDS على Railway.",
    )


def call_with_retry(fn, *args, **kwargs):
    for attempt in range(4):
        try:
            return fn(*args, **kwargs)
        except ApiTelegramException as e:
            if e.error_code == 429 and attempt < 3:
                wait = 5
                try:
                    wait = int(e.result_json["parameters"]["retry_after"]) + 1
                except Exception:
                    pass
                logger.warning("Rate limited, sleeping %ss", wait)
                time.sleep(wait)
                continue
            raise


def make_item(message):
    doc = message.document
    name = doc.file_name or ""
    ext = os.path.splitext(name)[1].lower()
    if ext:
        if ext not in ALLOWED_EXT:
            return None
    elif doc.mime_type != "application/pdf":
        return None
    return {
        "type": "file",
        "file_id": doc.file_id,
        "unique_id": doc.file_unique_id,
        "file_name": name or None,
        "size": doc.file_size or 0,
        "caption": (message.caption or "").strip(),
        "url": None,
        "src_chat": message.chat.id,
        "src_msg": message.message_id,
    }


def make_link_item(title, url):
    return {
        "type": "link", "file_id": None, "unique_id": "url:" + url, "file_name": None,
        "size": 0, "caption": title, "url": url, "src_chat": None, "src_msg": None,
    }


def build_title(item, found):
    for raw in (item["caption"] or "").splitlines()[:1] + [item["file_name"] or ""]:
        title = detect.clean_title(raw)
        if title:
            return title[:120]
    parts = [
        found.get("subject"),
        library.GRADES.get(found.get("grade")),
        library.TRACK_LABELS.get(found.get("track")),
        library.TERMS.get(found.get("term")) if found.get("term") is not None else None,
    ]
    return " - ".join(p for p in parts if p) or "كتاب بدون اسم"


def analyze(item, defaults=None):
    defaults = defaults or {}
    text = f"{item['caption']} {item['file_name'] or ''}"
    found = detect.detect(text, assume_grade=defaults.get("grade"))
    for key in ("grade", "term", "subject"):
        if found[key] is None:
            found[key] = defaults.get(key)
    if forced_term:
        found["term"] = forced_term
    if found["track"] is None and found["grade"] in library.GRADE_TRACKS:
        default_track = defaults.get("track")
        if default_track in library.tracks_for_grade(found["grade"]):
            found["track"] = default_track
    if found["grade"] not in library.GRADE_TRACKS:
        found["track"] = None
    info = dict(item)
    info.update(found)
    info["title"] = build_title(item, found)
    return info


def is_complete(info):
    return info.get("grade") is not None and info.get("term") is not None and bool(info.get("subject"))


def store_file(info):
    if info.get("type") == "link":
        return {"channel_id": None, "message_id": None, "file_name": None}
    if STORAGE_CHANNEL_ID:
        track = library.TRACK_LABELS.get(info.get("track"))
        caption = (
            f"{info['title']}\n"
            f"{library.GRADES[info['grade']]}"
            + (f" | {track}" if track else "")
            + f" | {library.TERMS[info['term']]} | {info['subject']}"
        )
        copied = call_with_retry(
            bot.copy_message, STORAGE_CHANNEL_ID, info["src_chat"], info["src_msg"],
            caption=caption, parse_mode=None,
        )
        time.sleep(COPY_DELAY)
        return {"channel_id": STORAGE_CHANNEL_ID, "message_id": copied.message_id, "file_name": None}
    if info.get("size", 0) > MAX_DOWNLOAD:
        raise ValueError("too_big")
    tg_file = call_with_retry(bot.get_file, info["file_id"])
    data = bot.download_file(tg_file.file_path)
    return {
        "channel_id": None, "message_id": None,
        "file_name": library.save_file(data, info.get("file_name") or "book.pdf"),
    }


def book_fields(info, stored):
    return {
        "grade": info["grade"], "term": info["term"], "subject": info["subject"],
        "title": info["title"], "track": info.get("track"),
        "file_name": stored["file_name"], "url": info.get("url"),
        "channel_id": stored["channel_id"], "message_id": stored["message_id"],
        "file_unique_id": info.get("unique_id"),
    }


def purge_channel(books):
    for b in books:
        if b.get("channel_id") and b.get("message_id"):
            try:
                call_with_retry(bot.delete_message, b["channel_id"], b["message_id"])
            except Exception as e:
                logger.warning("Could not delete channel message: %s", e)


def notify_admins(text, skip_chat=None):
    for aid in ADMIN_IDS:
        if aid == skip_chat:
            continue
        try:
            bot.send_message(aid, text)
        except Exception as e:
            logger.info("Could not notify admin %s: %s", aid, e)


jobs = queue.Queue()


class Report:
    def __init__(self):
        self.ok = []
        self.dup = 0
        self.review = 0
        self.fail = []


def _fail_reason(exc):
    if isinstance(exc, ValueError) and str(exc) == "too_big":
        return "أكبر من 20 ميجا (فعّل STORAGE_CHANNEL_ID)"
    return "خطأ أثناء الحفظ"


def process_job(job, reports, seen):
    rep = reports.setdefault(job["chat"], Report())
    item = job["item"]
    key = item["unique_id"]
    if key in seen or library.is_known(key):
        rep.dup += 1
        return
    info = analyze(item, job.get("defaults"))
    if not is_complete(info):
        library.review_add(info)
        seen.add(key)
        rep.review += 1
        return
    try:
        stored = store_file(info)
    except Exception as e:
        logger.error("Failed to store %r: %s", info.get("title"), e)
        rep.fail.append((info["title"], _fail_reason(e)))
        return
    seen.add(key)
    rep.ok.append(book_fields(info, stored))


def _place_label(grade, track, term):
    label = library.GRADES.get(grade, grade)
    if track:
        label += f" ({library.TRACK_LABELS.get(track, track)})"
    return f"{label} — {library.TERMS.get(term, '')}"


def report_text(rep, books):
    lines = []
    if books:
        lines.append(f"✅ تمت إضافة <b>{len(books)}</b> ملف إلى المكتبة")
        counts = Counter((b["grade"], b.get("track"), b["term"]) for b in books)
        for (g, tr, t), n in counts.most_common(8):
            lines.append(f"   • {_place_label(g, tr, t)}: {n}")
        if len(counts) > 8:
            lines.append(f"   • ... و{len(counts) - 8} تصنيفات أخرى")
    if rep.review:
        lines.append(f"⚠️ <b>{rep.review}</b> ملف لم أستطع تحديد كل بياناته، بانتظار مراجعتك (/review)")
    if rep.dup:
        lines.append(f"♻️ {rep.dup} ملف مكرر أو موجود مسبقاً، تم تجاهله")
    if rep.fail:
        lines.append(f"❌ فشل {len(rep.fail)} ملف:")
        for title, reason in rep.fail[:5]:
            lines.append(f"   • {esc(title[:40])} — {reason}")
        if len(rep.fail) > 5:
            lines.append(f"   • ... و{len(rep.fail) - 5} أخرى")
    return "\n".join(lines) or "لا يوجد شيء جديد."


def flush(reports):
    for chat_id, rep in reports.items():
        books = []
        if rep.ok:
            try:
                books = library.add_many(rep.ok)
            except Exception as e:
                logger.error("add_many failed: %s", e)
                rep.fail.extend((b["title"], "خطأ أثناء حفظ قاعدة البيانات") for b in rep.ok)
        markup = InlineKeyboardMarkup(row_width=1)
        if rep.review:
            markup.add(InlineKeyboardButton("🔍 مراجعة الآن", callback_data="rv"))
        if books:
            batch_id = uuid.uuid4().hex[:8]
            batches[batch_id] = [b["id"] for b in books]
            while len(batches) > 30:
                batches.pop(next(iter(batches)))
            markup.add(InlineKeyboardButton("↩️ تراجع عن هذه الإضافة", callback_data=f"undo:{batch_id}"))
        try:
            bot.send_message(chat_id, report_text(rep, books), reply_markup=markup)
        except Exception as e:
            logger.warning("Could not send report to %s: %s", chat_id, e)
        if rep.review:
            notify_admins(f"⚠️ {rep.review} ملف يحتاج مراجعة بياناته. أرسل /review", skip_chat=chat_id)


def worker():
    reports, seen = {}, set()
    while True:
        try:
            job = jobs.get(timeout=IDLE_FLUSH)
        except queue.Empty:
            if reports:
                flush(reports)
                reports, seen = {}, set()
            continue
        try:
            process_job(job, reports, seen)
        except Exception:
            logger.exception("Job failed")
        if sum(len(r.ok) for r in reports.values()) >= FLUSH_SIZE:
            flush(reports)
            reports, seen = {}, set()


threading.Thread(target=worker, daemon=True, name="batch-worker").start()


def enqueue(item, chat_id, defaults=None):
    jobs.put({"item": item, "chat": chat_id, "defaults": defaults})


def ack_receive(chat_id):
    now = time.time()
    if now - _last_ack.get(chat_id, 0) > 15:
        bot.send_message(
            chat_id,
            "📥 استلمت الملفات وجاري معالجتها، سأرسل لك ملخصاً واحداً عند الانتهاء."
            + (f"\n📅 الترم المحدد: {library.TERMS[forced_term]}" if forced_term else ""),
        )
    _last_ack[chat_id] = now


def bulk_defaults(uid):
    st = pending.get(uid)
    if st and st.get("mode") == "bulk":
        return {k: st.get(k) for k in ("grade", "term", "subject", "track")}
    return None


def _grade_text(st):
    return library.GRADES.get(st.get("grade")) or "❓ غير محدد"


def _term_text(st):
    return library.TERMS[st["term"]] if st.get("term") is not None else "❓ غير محدد"


def _track_line(st):
    if st.get("grade") not in library.GRADE_TRACKS:
        return ""
    label = library.TRACK_LABELS.get(st.get("track")) or "🔀 مشترك (كل المسارات)"
    return f"🧭 المسار: {label}\n"


def summary_text(st):
    subject = esc(st["subject"]) if st.get("subject") else "❓ غير محدد"
    if st.get("mode") == "bulk":
        return (
            "📦 <b>الإضافة الجماعية</b>\n\n"
            "أرسل الملفات بأي عدد (أو روابط، كل سطر: <code>اسم | رابط</code>). "
            "أحدد الاسم والصف والترم والمادة والمسار لكل ملف من اسمه.\n\n"
            "القيم الافتراضية (تُستخدم فقط للملفات التي لم أتعرف على بياناتها):\n"
            f"🎓 الصف: {_grade_text(st)}\n"
            f"{_track_line(st)}"
            f"📅 الترم: {_term_text(st)}\n"
            f"📘 المادة: {subject}"
        )
    return (
        f"📖 <b>{esc(st['title'])}</b>\n\n"
        f"🎓 الصف: {_grade_text(st)}\n"
        f"{_track_line(st)}"
        f"📅 الترم: {_term_text(st)}\n"
        f"📘 المادة: {subject}\n\n"
        f"راجع البيانات ثم اضغط حفظ. (المتبقي في المراجعة: {library.review_size()})"
    )


def summary_markup(st):
    bulk = st.get("mode") == "bulk"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🏁 إنهاء الوضع الجماعي" if bulk else "✅ حفظ ونشر", callback_data="sv"))
    buttons = [
        InlineKeyboardButton("🎓 الصف", callback_data="eg"),
        InlineKeyboardButton("📅 الترم", callback_data="et"),
        InlineKeyboardButton("📘 المادة", callback_data="es"),
    ]
    if st.get("grade") in library.GRADE_TRACKS:
        buttons.append(InlineKeyboardButton("🧭 المسار", callback_data="etk"))
    if not bulk:
        buttons.append(InlineKeyboardButton("✏️ الاسم", callback_data="en"))
    markup.add(*buttons)
    if not bulk:
        markup.add(InlineKeyboardButton("🗑 تجاهل هذا الملف", callback_data="ac"))
    return markup


def show_summary(chat_id, uid, message_id=None):
    st = pending.get(uid)
    if not st:
        return
    text, markup = summary_text(st), summary_markup(st)
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
            return
        except Exception as e:
            logger.info("edit failed: %s", e)
    bot.send_message(chat_id, text, reply_markup=markup)


def next_review(chat_id, uid):
    item = library.review_peek()
    if not item:
        pending.pop(uid, None)
        return bot.send_message(chat_id, "✅ لا توجد ملفات بانتظار المراجعة.")
    item["mode"] = "review"
    pending[uid] = item
    show_summary(chat_id, uid)


@bot.message_handler(commands=["start", "help"], func=_is_private)
def start(message):
    if not is_admin(message.from_user.id):
        return deny(message)
    bot.send_message(
        message.chat.id,
        "👋 <b>بوت إدارة المكتبة</b>\n\n"
        "📎 <b>أرسل أي عدد من الملفات</b> (PDF وغيره) وسأضيفها كلها دفعة واحدة، "
        "وأحدد اسم كل ملف والصف والترم والمادة والمسار تلقائياً من اسمه.\n"
        "🔗 الروابط: كل سطر <code>اسم الكتاب | https://...</code> (يمكن إرسال عدة أسطر معاً).\n\n"
        "👥 <b>من مجموعة:</b> أضفني للمجموعة (يفضل كمشرف) وأرسل فيها <code>/linkgroup</code>، "
        "وكل ملف يُرسل فيها يُضاف تلقائياً. لإلغاء الربط: <code>/unlinkgroup</code>\n\n"
        "💡 كلما كان اسم الملف أوضح كانت النتيجة أدق، مثل: "
        "<i>ثالثة ثانوي علمي علوم الترم الأول كيمياء</i> أو "
        "<i>تانية بكالوريا مسار الهندسة فيزياء ترم ثاني</i>.\n\n"
        "/bulk قيم افتراضية لدفعة ملفاتها بأسماء غير واضحة\n"
        "/review مراجعة الملفات التي لم أتعرف عليها\n"
        "/books عرض آخر الكتب وحذفها (/books all للكل)\n"
        "/term تحديد الترم لكل الملفات (أول / تاني / تلقائي)\n"
        "/cancel للإلغاء\n\n"
        + term_status_text(),
        reply_markup=term_lock_markup(),
    )


@bot.message_handler(commands=["term"], func=_is_private)
def term_cmd(message):
    if not is_admin(message.from_user.id):
        return deny(message)
    bot.send_message(
        message.chat.id,
        "اختر الترم الذي ستُحفظ به كل الملفات التي ترسلها:\n\n" + term_status_text(),
        reply_markup=term_lock_markup(),
    )


@bot.message_handler(commands=["cancel"], func=_is_private)
def cancel(message):
    if is_admin(message.from_user.id):
        pending.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "تم الإلغاء.")


@bot.message_handler(commands=["bulk"], func=_is_private)
def bulk(message):
    uid = message.from_user.id
    if not is_admin(uid):
        return deny(message)
    pending[uid] = {"mode": "bulk", "title": "", "grade": None, "term": None, "subject": None, "track": None}
    show_summary(message.chat.id, uid)


@bot.message_handler(commands=["review"], func=_is_private)
def review(message):
    uid = message.from_user.id
    if not is_admin(uid):
        return deny(message)
    next_review(message.chat.id, uid)


@bot.message_handler(commands=["books"], func=_is_private)
def list_books(message):
    if not is_admin(message.from_user.id):
        return deny(message)
    books = library.all_books()
    if not books:
        return bot.send_message(message.chat.id, "لا توجد كتب بعد.")
    show_all = "all" in message.text.lower().split()[1:]
    total = len(books)
    if not show_all:
        books = books[-20:]
    bot.send_message(
        message.chat.id,
        f"📚 إجمالي الكتب: {total}" + ("" if show_all or total <= 20 else "\nأعرض آخر 20 فقط، أرسل /books all لعرض الكل."),
    )
    for i in range(0, len(books), 10):
        chunk = books[i:i + 10]
        lines, markup = [], InlineKeyboardMarkup(row_width=1)
        for b in chunk:
            grade = library.GRADES.get(b["grade"], b["grade"])
            track = library.TRACK_LABELS.get(b.get("track"))
            term = library.TERMS.get(b.get("term", 0), "")
            where = " / ".join(x for x in (grade, track, term, esc(b["subject"])) if x)
            lines.append(f"#{b['id']} {esc(b['title'])}\n   {where}")
            markup.add(InlineKeyboardButton(f"🗑 حذف #{b['id']}", callback_data=f"del:{b['id']}"))
        bot.send_message(message.chat.id, "\n\n".join(lines), reply_markup=markup)


@bot.message_handler(commands=["linkgroup"], func=_is_group)
def link_group(message):
    if not message.from_user or not is_admin(message.from_user.id):
        return
    library.link_group(message.chat.id)
    bot.send_message(
        message.chat.id,
        "✅ تم ربط هذه المجموعة. كل ملف يُرسل هنا سيُضاف تلقائياً للمكتبة.\n"
        "💡 ليرى البوت كل الرسائل اجعله مشرفاً في المجموعة (أو عطّل Privacy Mode من BotFather).",
    )


@bot.message_handler(commands=["unlinkgroup"], func=_is_group)
def unlink_group(message):
    if not message.from_user or not is_admin(message.from_user.id):
        return
    ok = library.unlink_group(message.chat.id)
    bot.send_message(message.chat.id, "تم إلغاء الربط." if ok else "هذه المجموعة غير مربوطة.")


@bot.message_handler(content_types=["document"], func=_is_group)
def on_group_document(message):
    if not library.is_linked_group(message.chat.id):
        return
    item = make_item(message)
    if item:
        enqueue(item, message.chat.id)


@bot.message_handler(content_types=["document"], func=_is_private)
def on_document(message):
    uid = message.from_user.id
    if not is_admin(uid):
        return deny(message)
    item = make_item(message)
    if not item:
        return bot.send_message(
            message.chat.id,
            "⚠️ نوع الملف غير مدعوم. المدعوم: " + " ".join(sorted(ALLOWED_EXT)),
        )
    ack_receive(message.chat.id)
    enqueue(item, message.chat.id, bulk_defaults(uid))


def parse_links(text):
    out = []
    for line in text.splitlines():
        if "|" in line and "http" in line:
            title, _, url = line.partition("|")
            title, url = title.strip(), url.strip()
            if title and url.startswith("http"):
                out.append((title, url))
    return out


@bot.message_handler(content_types=["text"], func=_is_private)
def on_text(message):
    uid = message.from_user.id
    if not is_admin(uid):
        return deny(message)
    text = message.text.strip()
    state = pending.get(uid)

    fwd = getattr(message, "forward_from_chat", None)
    if fwd is None:
        fwd = getattr(getattr(message, "forward_origin", None), "chat", None)
    if fwd is not None:
        return bot.send_message(
            message.chat.id,
            f"🆔 رقم القناة: <code>{fwd.id}</code>\nضعه في متغير STORAGE_CHANNEL_ID على Railway.",
        )

    if state and state.get("await") == "subject":
        state["subject"] = text
        state.pop("await")
        return show_summary(message.chat.id, uid)
    if state and state.get("await") == "title":
        state["title"] = text
        state.pop("await")
        return show_summary(message.chat.id, uid)

    links = parse_links(text)
    if links:
        ack_receive(message.chat.id)
        defaults = bulk_defaults(uid)
        for title, url in links:
            enqueue(make_link_item(title, url), message.chat.id, defaults)
        return

    bot.send_message(
        message.chat.id,
        "أرسل ملفات PDF (أي عدد) أو روابط بالشكل: <code>اسم الكتاب | https://...</code>",
    )


def finish(chat_id, uid):
    state = pending.pop(uid, None)
    if not state or state.get("mode") != "review":
        return
    try:
        stored = store_file(state)
        book = library.add_book(**book_fields(state, stored))
        library.review_remove(state.get("unique_id"))
    except Exception as e:
        logger.error("Failed to save book: %s", e)
        pending[uid] = state
        bot.send_message(chat_id, f"⚠️ حدث خطأ أثناء حفظ الكتاب ({_fail_reason(e)}).")
        return show_summary(chat_id, uid)
    track = library.TRACK_LABELS.get(book.get("track"))
    bot.send_message(
        chat_id,
        f"✅ تمت إضافة <b>{esc(book['title'])}</b>\n"
        f"🎓 {library.GRADES[book['grade']]}\n"
        + (f"🧭 {track}\n" if track else "")
        + f"📅 {library.TERMS[book['term']]}\n"
        f"📘 {esc(book['subject'])}\n\n"
        "ظهر الآن في البوت العام.",
    )
    if library.review_size():
        next_review(chat_id, uid)


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
        book_id = int(data.split(":")[1])
        removed = library.delete_many([book_id])
        purge_channel(removed)
        return bot.send_message(chat_id, "🗑 تم الحذف." if removed else "الكتاب غير موجود.")

    if data.startswith("undo:"):
        bot.answer_callback_query(call.id)
        ids = batches.pop(data.split(":")[1], None)
        if not ids:
            return bot.send_message(chat_id, "لا يمكن التراجع عن هذه الدفعة (انتهت صلاحيتها أو تم التراجع عنها).")
        removed = library.delete_many(ids)
        purge_channel(removed)
        try:
            bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
        except Exception:
            pass
        return bot.send_message(chat_id, f"↩️ تم حذف {len(removed)} كتاب من هذه الدفعة.")

    if data.startswith("ft:"):
        val = data.split(":")[1]
        set_forced_term(int(val) if val in ("1", "2") else None)
        bot.answer_callback_query(call.id, "تم الحفظ ✅")
        try:
            bot.edit_message_text(
                "اختر الترم الذي ستُحفظ به كل الملفات التي ترسلها:\n\n" + term_status_text(),
                chat_id, msg_id, reply_markup=term_lock_markup(),
            )
        except Exception as e:
            logger.info("term edit skipped: %s", e)
        return

    if data == "rv":
        bot.answer_callback_query(call.id)
        try:
            return next_review(uid, uid)
        except Exception:
            return bot.send_message(chat_id, "افتح محادثة البوت الخاصة وأرسل /review")

    if data == "ac":
        bot.answer_callback_query(call.id)
        st = pending.pop(uid, None)
        reviewing = bool(st and st.get("mode") == "review")
        if reviewing:
            library.review_remove(st.get("unique_id"))
        try:
            bot.edit_message_text("🗑 تم تجاهل الملف." if reviewing else "تم الإلغاء.", chat_id, msg_id)
        except Exception:
            pass
        if reviewing and library.review_size():
            next_review(chat_id, uid)
        return

    if not state:
        return bot.answer_callback_query(call.id, "انتهت العملية، أرسل /review أو الملف من جديد.", show_alert=True)

    if data == "sv":
        if state.get("mode") == "bulk":
            bot.answer_callback_query(call.id)
            pending.pop(uid, None)
            return bot.edit_message_text("🏁 تم إنهاء الوضع الجماعي.", chat_id, msg_id)
        if state.get("grade") is None or state.get("term") is None or not state.get("subject"):
            return bot.answer_callback_query(call.id, "حدد الصف والترم والمادة أولاً.", show_alert=True)
        bot.answer_callback_query(call.id)
        bot.edit_message_text("⏳ جاري الحفظ...", chat_id, msg_id)
        return finish(chat_id, uid)

    bot.answer_callback_query(call.id)

    if data == "eg":
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
            if state.get("track") not in library.tracks_for_grade(key):
                state["track"] = None
        show_summary(chat_id, uid, msg_id)

    elif data == "etk":
        tracks = library.tracks_for_grade(state.get("grade"))
        if not tracks:
            return show_summary(chat_id, uid, msg_id)
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(*[
            InlineKeyboardButton(library.TRACK_LABELS[k], callback_data=f"xk:{k}")
            for k in tracks
        ])
        markup.add(InlineKeyboardButton("🔀 مشترك (كل المسارات)", callback_data="xk:-"))
        bot.edit_message_text("🧭 اختر المسار:", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("xk:"):
        key = data.split(":")[1]
        if key == "-":
            state["track"] = None
        elif key in library.tracks_for_grade(state.get("grade")):
            state["track"] = key
        show_summary(chat_id, uid, msg_id)

    elif data == "et":
        markup = InlineKeyboardMarkup(row_width=1)
        for key in (1, 2, 0):
            markup.add(InlineKeyboardButton(library.TERMS[key], callback_data=f"xt:{key}"))
        bot.edit_message_text("📅 اختر الترم:", chat_id, msg_id, reply_markup=markup)

    elif data.startswith("xt:"):
        key = int(data.split(":")[1])
        if key in library.TERMS:
            state["term"] = key
        show_summary(chat_id, uid, msg_id)

    elif data == "es":
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


if __name__ == "__main__":
    logger.info("Admin bot is starting up...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
