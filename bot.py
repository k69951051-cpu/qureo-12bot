import html
import os
import logging
import time

import telebot
import library
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# CONFIGURATION
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MAX_WRONG = 3  # بعد 3 محاولات خاطئة يظهر الحل مع الشرح
# بيانات التواصل مع مالك البوت (يمكن تغييرها من متغيرات البيئة)
OWNER_TELEGRAM = os.getenv("OWNER_TELEGRAM", "keroo_cr7").lstrip("@")
OWNER_WHATSAPP = os.getenv("OWNER_WHATSAPP", "01203423169")


def _parse_chat(raw):
    """يقبل @username أو رقم القناة (حتى لو انعكست علامة الناقص بسبب لوحة المفاتيح العربية)."""
    raw = (raw or "").strip().replace("\u2212", "-").replace("\u2013", "-").replace(" ", "")
    if raw.endswith("-") and raw[:-1].isdigit():
        raw = "-" + raw[:-1]
    if raw.lstrip("-").isdigit():
        return int(raw)
    if raw and not raw.startswith("@"):
        raw = "@" + raw
    return raw


# قناة الاشتراك الإجباري: لا يتصفح الطالب المكتبة إلا بعد الاشتراك فيها.
# REQUIRED_CHANNEL: @username أو رقم القناة/الجروب (-100...).
# الافتراضي: جروب الكتب. لتعطيل الشرط اضبط REQUIRED_CHANNEL=off في متغيرات البيئة.
# يجب أن يكون البوت مشرفاً (Admin) في القناة/الجروب ليتمكن من فحص الاشتراك.
_raw_channel = os.getenv("REQUIRED_CHANNEL", "@Highschool_textbooks_group")
REQUIRED_CHANNEL = "" if _raw_channel.strip().lower() in ("off", "none", "0") else _parse_chat(_raw_channel)
# رابط القناة للزر (مطلوب للقنوات الخاصة، وللعامة يُستنتج من الـ @username)
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "").strip()
# 0 = فحص جديد عند كل استخدام للبوت. ارفعه (مثلاً 60) لتقليل الطلبات لو زاد عدد الطلاب.
SUB_CACHE_SECONDS = int(os.getenv("SUB_CACHE_SECONDS", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in environment variables")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# حالة كل طالب (في الذاكرة فقط، ولا يتم تخزين أي بيانات حساسة)
users = {}

# =========================
# QUESTION BANK
# كل سؤال: نص، اختيارات، رقم الإجابة الصحيحة، تلميحات متدرجة، شرح
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
                    {
                        "q": "أي سطر ينشئ قائمة (list) في بايثون؟",
                        "options": ["a = (1, 2, 3)", "a = [1, 2, 3]", "a = {1, 2, 3}", "a = <1, 2, 3>"],
                        "answer": 1,
                        "hints": [
                            "القوائم تستخدم نوعاً معيناً من الأقواس.",
                            "الأقواس الدائرية للـ tuple والمعقوفة {} للـ set أو dict.",
                        ],
                        "explain": "القائمة تُكتب بين أقواس مربعة <code>[ ]</code>.",
                    },
                    {
                        "q": "ما ناتج <code>len('Python')</code>؟",
                        "options": ["5", "6", "7", "خطأ"],
                        "answer": 1,
                        "hints": [
                            "الدالة len تعد عدد الحروف.",
                            "عُد حروف كلمة Python حرفاً حرفاً.",
                        ],
                        "explain": "كلمة Python تتكون من 6 حروف: P-y-t-h-o-n.",
                    },
                ],
            },
            {
                "title": "الشروط والحلقات",
                "questions": [
                    {
                        "q": "كم مرة ستُطبع كلمة hi؟\n<code>for i in range(3):\n    print('hi')</code>",
                        "options": ["2", "3", "4", "لا شيء"],
                        "answer": 1,
                        "hints": [
                            "<code>range(3)</code> تنتج مجموعة أرقام تبدأ من الصفر.",
                            "اكتب الأرقام التي ينتجها range(3): 0 ثم ...",
                        ],
                        "explain": "<code>range(3)</code> تنتج 0 و1 و2، أي ثلاث قيم، فتتكرر الحلقة 3 مرات.",
                    },
                    {
                        "q": "ما ناتج الكود؟\n<code>n = 7\nif n % 2 == 0:\n    print('even')\nelse:\n    print('odd')</code>",
                        "options": ["even", "odd", "7", "خطأ"],
                        "answer": 1,
                        "hints": [
                            "العملية <code>%</code> تعطي باقي القسمة.",
                            "باقي قسمة 7 على 2 هو ...؟",
                        ],
                        "explain": "باقي قسمة 7 على 2 يساوي 1 وليس 0، فيُنفذ الفرع else ويطبع odd.",
                    },
                ],
            },
        ],
    },
    "js": {
        "name": "🟨 JavaScript",
        "chapters": [
            {
                "title": "المتغيرات والأنواع",
                "questions": [
                    {
                        "q": "أي كلمة تُستخدم لتعريف ثابت لا يمكن إعادة إسناده؟",
                        "options": ["var", "let", "const", "static"],
                        "answer": 2,
                        "hints": [
                            "الكلمة مأخوذة من constant.",
                            "<code>let</code> و<code>var</code> يسمحان بتغيير القيمة لاحقاً.",
                        ],
                        "explain": "<code>const</code> تعرّف متغيراً لا يمكن إعادة إسناد قيمة جديدة له.",
                    },
                    {
                        "q": "ما ناتج <code>typeof '10'</code>؟",
                        "options": ["number", "string", "boolean", "undefined"],
                        "answer": 1,
                        "hints": [
                            "انظر إلى علامتي الاقتباس حول الرقم.",
                            "ما يوضع بين علامات اقتباس يكون نصاً.",
                        ],
                        "explain": "القيمة <code>'10'</code> نص، فالناتج string.",
                    },
                    {
                        "q": "ما ناتج <code>'5' + 3</code> في JavaScript؟",
                        "options": ["8", "'53'", "NaN", "خطأ"],
                        "answer": 1,
                        "hints": [
                            "عند جمع نص مع رقم، ماذا تفعل JavaScript؟",
                            "العملية + مع نص تعني دمج النصوص (concatenation).",
                        ],
                        "explain": "يتم تحويل الرقم 3 إلى نص ودمجه، فالناتج النص <code>'53'</code>.",
                    },
                ],
            },
            {
                "title": "المصفوفات والدوال",
                "questions": [
                    {
                        "q": "ما ناتج <code>[1, 2, 3].length</code>؟",
                        "options": ["2", "3", "4", "undefined"],
                        "answer": 1,
                        "hints": [
                            "الخاصية length تعطي عدد العناصر.",
                            "عُد العناصر داخل المصفوفة.",
                        ],
                        "explain": "المصفوفة بها 3 عناصر، فالناتج 3.",
                    },
                    {
                        "q": "ما ناتج استدعاء الدالة؟\n<code>const f = (a, b) => a * b;\nconsole.log(f(3, 4));</code>",
                        "options": ["7", "12", "34", "undefined"],
                        "answer": 1,
                        "hints": [
                            "الدالة تستخدم عملية الضرب وليس الجمع.",
                            "ما حاصل ضرب 3 في 4؟",
                        ],
                        "explain": "الدالة السهمية تُرجع <code>a * b</code> أي 3 × 4 = 12.",
                    },
                ],
            },
        ],
    },
}

# =========================
# BOOKS LIBRARY
# كتب مجانية ومتاحة قانونياً من مواقع المؤلفين أنفسهم
# لإضافة كتاب جديد: أضف قاموساً جديداً بنفس الشكل
# =========================

BOOKS = [
    {
        "title": "Automate the Boring Stuff with Python",
        "author": "Al Sweigart",
        "level": "مبتدئ",
        "topic": "Python",
        "desc": "كتاب عملي يعلمك بايثون عبر أمثلة لأتمتة المهام اليومية مثل التعامل مع الملفات والجداول.",
        "url": "https://automatetheboringstuff.com/",
    },
    {
        "title": "Think Python (2nd Edition)",
        "author": "Allen B. Downey",
        "level": "مبتدئ",
        "topic": "Python",
        "desc": "يشرح أساسيات البرمجة والتفكير الحاسوبي بأسلوب مبسط، مناسب جداً للمبتدئين تماماً.",
        "url": "https://greenteapress.com/wp/think-python-2e/",
    },
    {
        "title": "Eloquent JavaScript",
        "author": "Marijn Haverbeke",
        "level": "متوسط",
        "topic": "JavaScript",
        "desc": "كتاب شامل يغطي اللغة من الأساس حتى المفاهيم المتقدمة، ويحتوي على تمارين تفاعلية.",
        "url": "https://eloquentjavascript.net/",
    },
    {
        "title": "The Modern JavaScript Tutorial",
        "author": "Ilya Kantor (javascript.info)",
        "level": "مبتدئ إلى متقدم",
        "topic": "JavaScript",
        "desc": "شرح مفصل ومحدّث لـ JavaScript الحديثة مع أمثلة ومهام للتطبيق بعد كل درس.",
        "url": "https://javascript.info/",
    },
]

# =========================
# SCHOOL LIBRARY: المرحلة ← الصف ← (المسار) ← الترم ← المادة ← الكتب
# الكتب تُضاف تلقائياً من بوت الإدارة (admin_bot.py) وتُقرأ من library.py
# =========================


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
    """المسار داخل callback_data ("-" يعني بدون مسار)."""
    return track or "-"


def place_title(grade, track=None):
    title = library.GRADES[grade]
    if track:
        title += f" — {library.TRACK_LABELS[track]}"
    return title


def _back_from_track(grade, track):
    """زر الرجوع من قائمة الترمين: للتخصص الفرعي ثم المسار ثم المرحلة."""
    if not track:
        return f"st:{library.stage_of(grade)}"
    parent = library.TRACK_PARENT.get(track)
    return f"tk:{grade}:{parent}" if parent else f"g:{grade}"


def track_menu(grade, parent=None):
    """مسارات الصف (طب/هندسة/... أو أدبي/علمي)، أو علوم/رياضة بعد اختيار علمي."""
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
# FORCED SUBSCRIPTION
# =========================

_sub_ok = {}  # user_id -> وقت آخر فحص ناجح


class SubscriptionCheckError(Exception):
    pass


def is_subscribed(user_id, fresh=False):
    """True إذا كان المستخدم مشتركاً (أو لا يوجد شرط اشتراك). fresh=True يتجاوز الذاكرة المؤقتة."""
    if not REQUIRED_CHANNEL:
        return True
    if not fresh and time.time() - _sub_ok.get(user_id, 0) < SUB_CACHE_SECONDS:
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
    except Exception as e:
        logger.error("Subscription check failed (is the bot an admin of the channel?): %s", e)
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
        return (
            "⚠️ تعذر التحقق من اشتراكك الآن.\n"
            "حاول مرة أخرى بعد قليل، وإذا استمرت المشكلة تواصل مع مالك البوت."
        )
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


def needs_subscription(data):
    """كل الأزرار تحتاج اشتراكاً، عدا زر التواصل مع المالك (ليتمكن من طلب المساعدة)."""
    return data != "contact"


def gate_message(message):
    """فحص الاشتراك للأوامر والرسائل النصية. يرجع True إذا مسموح له بالمتابعة."""
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
# CONTACT
# =========================


def contact_markup():
    digits = "".join(ch for ch in OWNER_WHATSAPP if ch.isdigit())
    if digits.startswith("0"):
        digits = "20" + digits[1:]  # رقم مصري بصيغة دولية لرابط واتساب
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
        "wrong": [],        # الاختيارات الخاطئة التي جربها الطالب في السؤال الحالي
        "hints_used": 0,
        "score": 0,
        "finished_q": False,
    }


def get_state(chat_id):
    if chat_id not in users:
        users[chat_id] = new_state()
    return users[chat_id]


def show(chat_id, message_id, text, markup=None):
    """تعديل الرسالة الحالية، وإذا تعذر ذلك يتم إرسال رسالة جديدة."""
    try:
        if message_id:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
            return
    except Exception as e:
        logger.info("edit failed, sending new message: %s", e)
    bot.send_message(chat_id, text, reply_markup=markup)


def current_question(st):
    chapter = COURSES[st["course"]]["chapters"][st["chapter"]]
    return chapter, chapter["questions"][st["q"]]


# =========================
# KEYBOARDS
# =========================


def courses_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    for key, course in COURSES.items():
        markup.add(InlineKeyboardButton(course["name"], callback_data=f"c:{key}"))
    markup.add(
        InlineKeyboardButton("📚 مكتبة الكتب", callback_data="lib"),
        InlineKeyboardButton("📞 تواصل مع المالك", callback_data="contact"),
    )
    return markup


def library_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    for i, book in enumerate(BOOKS):
        markup.add(InlineKeyboardButton(f"📖 {book['title']}", callback_data=f"b:{i}"))
    markup.add(InlineKeyboardButton("⬅️ رجوع", callback_data="lib"))
    return markup


def book_markup(index):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🔗 فتح الكتاب", url=BOOKS[index]["url"]),
        InlineKeyboardButton("⬅️ كل الكتب", callback_data="prog"),
    )
    return markup


def book_text(index):
    b = BOOKS[index]
    return (
        f"📖 <b>{b['title']}</b>\n"
        f"✍️ المؤلف: {b['author']}\n"
        f"🏷️ الموضوع: {b['topic']}\n"
        f"📶 المستوى: {b['level']}\n\n"
        f"{b['desc']}"
    )


def chapters_menu(course_key):
    markup = InlineKeyboardMarkup(row_width=1)
    for i, ch in enumerate(COURSES[course_key]["chapters"]):
        markup.add(InlineKeyboardButton(f"📘 {i + 1}. {ch['title']}", callback_data=f"ch:{course_key}:{i}"))
    markup.add(InlineKeyboardButton("⬅️ رجوع", callback_data="menu"))
    return markup


def question_markup(st):
    _, q = current_question(st)
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(opt, callback_data=f"a:{i}")
        for i, opt in enumerate(q["options"])
        if i not in st["wrong"]
    ]
    markup.add(*buttons)
    row = []
    if st["hints_used"] < len(q["hints"]):
        row.append(InlineKeyboardButton("💡 تلميح", callback_data="hint"))
    row.append(InlineKeyboardButton("🏠 القائمة", callback_data="menu"))
    markup.add(*row)
    return markup


def next_markup(last):
    markup = InlineKeyboardMarkup(row_width=1)
    if last:
        markup.add(InlineKeyboardButton("🏁 عرض نتيجتي", callback_data="next"))
    else:
        markup.add(InlineKeyboardButton("➡️ السؤال التالي", callback_data="next"))
    markup.add(InlineKeyboardButton("🏠 القائمة", callback_data="menu"))
    return markup


# =========================
# SCREENS
# =========================


def question_text(st, extra=""):
    chapter, q = current_question(st)
    total = len(chapter["questions"])
    text = (
        f"📘 <b>{chapter['title']}</b>\n"
        f"❓ السؤال {st['q'] + 1} من {total}\n\n"
        f"{q['q']}"
    )
    if extra:
        text += f"\n\n{extra}"
    return text


def show_question(chat_id, message_id, extra=""):
    st = get_state(chat_id)
    st["wrong"] = []
    st["hints_used"] = 0
    st["finished_q"] = False
    show(chat_id, message_id, question_text(st, extra), question_markup(st))


def show_result(chat_id, message_id):
    st = get_state(chat_id)
    chapter = COURSES[st["course"]]["chapters"][st["chapter"]]
    total = len(chapter["questions"])
    score = st["score"]
    if score == total:
        comment = "🌟 ممتاز! أجبت على كل الأسئلة بدون مساعدة."
    elif score >= total / 2:
        comment = "👍 أداء جيد، راجع الأسئلة التي احتجت فيها تلميحاً."
    else:
        comment = "💪 لا بأس، أعد الفصل وحاول مرة أخرى وستتحسن."
    text = (
        f"🏁 <b>انتهى فصل: {chapter['title']}</b>\n\n"
        f"النتيجة: {score} من {total}\n"
        f"{comment}"
    )
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🔁 إعادة الفصل", callback_data=f"ch:{st['course']}:{st['chapter']}"),
        InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu"),
    )
    show(chat_id, message_id, text, markup)


# =========================
# HANDLERS
# =========================


@bot.message_handler(commands=["start", "help", "cancel"])
def start(message):
    chat_id = message.chat.id
    users[chat_id] = new_state()
    if not gate_message(message):
        return
    bot.send_message(
        chat_id,
        "👋 <b>مرحباً بك في مساعد التعلم</b>\n\n"
        "هنا تتدرب على Python و JavaScript بنفسك: تجيب عن الأسئلة، "
        "وإذا تعثرت تحصل على تلميحات متدرجة وشرح للحل.\n\n"
        "📚 اختر الكورس:",
        reply_markup=courses_menu(),
    )


@bot.message_handler(commands=["contact"])
def contact(message):
    bot.send_message(message.chat.id, contact_text(), reply_markup=contact_markup())


@bot.message_handler(content_types=["text"])
def fallback(message):
    if not gate_message(message):
        return
    bot.send_message(message.chat.id, "استخدم الأزرار أو أرسل /start للبدء.")


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data
    st = get_state(chat_id)

    # الاشتراك الإجباري (فحص جديد دائماً عند فتح كتاب، حتى لا يستفيد من ترك القناة بعد الاشتراك)
    if data == "chk" or needs_subscription(data):
        try:
            subscribed = is_subscribed(call.from_user.id, fresh=data == "chk" or data.startswith("f:"))
        except SubscriptionCheckError:
            bot.answer_callback_query(call.id)
            return show(chat_id, msg_id, join_text(error=True), join_markup(error=True))
        if not subscribed:
            if data == "chk":
                return bot.answer_callback_query(call.id, "لم يتم العثور على اشتراكك بعد، اشترك أولاً ثم أعد المحاولة.", show_alert=True)
            bot.answer_callback_query(call.id)
            return show(chat_id, msg_id, join_text(), join_markup())
        if data == "chk":
            bot.answer_callback_query(call.id, "✅ تم التحقق، أهلاً بك!")
            return show(chat_id, msg_id, "📚 اختر الكورس:", courses_menu())

    bot.answer_callback_query(call.id)

    if data == "menu":
        users[chat_id] = new_state()
        show(chat_id, msg_id, "📚 اختر الكورس:", courses_menu())

    elif data == "contact":
        show(chat_id, msg_id, contact_text(), contact_markup())

    elif data == "lib":
        show(chat_id, msg_id, "📚 <b>مكتبة الكتب</b>\n\nاختر المرحلة أو القسم:", library_home())

    elif data == "prog":
        show(chat_id, msg_id, "💻 <b>كتب البرمجة</b>\n\nاختر كتاباً لعرض تفاصيله:", library_menu())

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
            if trk in library.TRACK_CHILDREN:  # علمي ← علوم أو رياضة
                show(chat_id, msg_id, f"{place_title(g, trk)}\n\nاختر التخصص:", track_menu(g, trk))
            else:
                show(chat_id, msg_id, f"{place_title(g, trk)}\n\nاختر الترم:", term_menu(g, trk))

    elif data.startswith("t:"):
        _, g, t, trk = data.split(":")
        trk = None if trk == "-" else trk
        if g in library.GRADES and int(t) in (1, 2) and (trk is None or trk in library.tracks_for_grade(g)):
            markup, has, has_elective = subjects_menu(g, int(t), trk)
            title = f"{place_title(g, trk)} — {library.TERMS[int(t)]}\n\n"
            if not has:
                body = "لا توجد كتب هنا بعد."
            elif has_elective:
                body = "اختر المادة:\n⭐ = مادة اختيارية في مسارك (اختر واحدة منها)"
            else:
                body = "اختر المادة:"
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
                    # الكتاب محفوظ في قناة التخزين، ننسخه للطالب بدون حد للحجم
                    bot.copy_message(chat_id, book["channel_id"], book["message_id"],
                                     caption=caption, parse_mode="HTML")
                elif book.get("public_file_id"):
                    bot.send_document(chat_id, book["public_file_id"], caption=caption, parse_mode="HTML")
                else:
                    with open(library.file_path(book["file"]), "rb") as f:
                        sent = bot.send_document(chat_id, f, caption=caption, parse_mode="HTML")
                    library.set_public_file_id(book["id"], sent.document.file_id)
            except Exception as e:
                logger.error("Failed to send book %s: %s", book["id"], e)
                bot.send_message(chat_id, "⚠️ تعذر إرسال الكتاب الآن، حاول لاحقاً.")

    elif data.startswith("b:"):
        idx = int(data.split(":")[1])
        if 0 <= idx < len(BOOKS):
            show(chat_id, msg_id, book_text(idx), book_markup(idx))

    elif data.startswith("c:"):
        course_key = data.split(":")[1]
        if course_key in COURSES:
            show(chat_id, msg_id, f"{COURSES[course_key]['name']}\n\nاختر الفصل:", chapters_menu(course_key))

    elif data.startswith("ch:"):
        _, course_key, idx = data.split(":")
        st.update(new_state())
        st["course"] = course_key
        st["chapter"] = int(idx)
        show_question(chat_id, msg_id)

    elif data.startswith("a:"):
        if st["course"] is None or st["finished_q"]:
            return
        choice = int(data.split(":")[1])
        _, q = current_question(st)

        if choice == q["answer"]:
            # نقطة كاملة فقط إذا أجاب بدون تلميح وبدون أخطاء
            if not st["wrong"] and st["hints_used"] == 0:
                st["score"] += 1
                verdict = "✅ <b>إجابة صحيحة!</b>"
            else:
                verdict = "✅ <b>صحيح!</b> (بعد مساعدة، لا تُحسب لها نقطة كاملة)"
            st["finished_q"] = True
            chapter, _ = current_question(st)
            last = st["q"] == len(chapter["questions"]) - 1
            show(
                chat_id, msg_id,
                question_text(st, f"{verdict}\n\n📖 <b>الشرح:</b> {q['explain']}"),
                next_markup(last),
            )
        else:
            st["wrong"].append(choice)
            if len(st["wrong"]) >= MAX_WRONG:
                correct = q["options"][q["answer"]]
                st["finished_q"] = True
                chapter, _ = current_question(st)
                last = st["q"] == len(chapter["questions"]) - 1
                show(
                    chat_id, msg_id,
                    question_text(
                        st,
                        f"❌ استنفدت المحاولات.\nالإجابة الصحيحة: <b>{correct}</b>\n\n"
                        f"📖 <b>الشرح:</b> {q['explain']}",
                    ),
                    next_markup(last),
                )
            else:
                show(
                    chat_id, msg_id,
                    question_text(st, "❌ إجابة غير صحيحة، جرّب مرة أخرى أو اطلب تلميحاً."),
                    question_markup(st),
                )

    elif data == "hint":
        if st["course"] is None or st["finished_q"]:
            return
        _, q = current_question(st)
        if st["hints_used"] < len(q["hints"]):
            st["hints_used"] += 1
        hints_text = "\n".join(f"💡 {i + 1}. {h}" for i, h in enumerate(q["hints"][: st["hints_used"]]))
        show(chat_id, msg_id, question_text(st, hints_text), question_markup(st))

    elif data == "next":
        if st["course"] is None:
            return
        chapter, _ = current_question(st)
        if st["q"] + 1 < len(chapter["questions"]):
            st["q"] += 1
            show_question(chat_id, msg_id)
        else:
            show_result(chat_id, msg_id)


# =========================
# RUN BOT
# =========================

if __name__ == "__main__":
    logger.info("Bot is starting up...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
