import html
import os
import logging
import time
import asyncio
import threading

import telebot
import library
import ai
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from playwright.async_api import async_playwright

# =========================
# CONFIGURATION
# =========================

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

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", num_threads=12)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

users = {}

def esc(s):
    return html.escape(str(s))

def make_progress_bar(percent, length=10):
    """رسم شريط تقدم بصري جذاب"""
    filled = int(round(length * percent / 100))
    bar = "▓" * filled + "░" * (length - filled)
    return f"[{bar}]"

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
        return "⚠️ تعذر التحقق من اشتراكك الآن."
    url = channel_url()
    handle = f'<a href="{esc(url)}">{esc(str(REQUIRED_CHANNEL))}</a>' if url else esc(str(REQUIRED_CHANNEL))
    return f"🔒 <b>لاستخدام البوت لازم تشترك في الجروب أولاً</b>\n\n📢 {handle}"

def join_markup(error=False):
    markup = InlineKeyboardMarkup(row_width=1)
    url = channel_url()
    if url and not error:
        markup.add(InlineKeyboardButton("📢 اشترك في الجروب", url=url))
    markup.add(InlineKeyboardButton("✅ تحققت من اشتراكي", callback_data="chk"))
    markup.add(InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="menu"))
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
# QUREO / AUTOMATION FLOW
# =========================
QUREO_URL = "https://me-portal.qureo.education/"

def qureo_grade_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("الصف الأول الثانوي", callback_data="qr:s1"),
        InlineKeyboardButton("تانية بكالوريا", callback_data="qr:bac2"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="menu"),
    )
    return markup

def qureo_view(grade):
    lines = ["💻 <b>منصة Qureo للبرمجة والأتمتة</b>\n", "اختر الخدمة المطلوبة:"]
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🚀 تشغيل الحل التلقائي (الأتمتة)", callback_data=f"auto_start:{grade}"),
        InlineKeyboardButton("📊 اعرف فصلك ورصيد الدايموند", callback_data=f"qp:{grade}"),
        InlineKeyboardButton("💻 منصة Qureo الرسمية", url=QUREO_URL),
        InlineKeyboardButton("⬅️ رجوع", callback_data="qr"),
    )
    return "\n".join(lines), markup

qr_flow = {}

def qureo_cancel_markup():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("❌ إلغاء", callback_data="qx"))
    return markup

def _try_delete(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

# --- Stealth Playwright Worker with Visual Progress Bar ---
async def run_qureo_automation(chat_id, message_id, username, password, grade):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1920,1080"
                ]
            )
        except Exception as launch_err:
            bot.edit_message_text(f"❌ تعذر تشغيل محرك الأتمتة: {esc(str(launch_err))}", chat_id, message_id)
            return

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US,en;q=0.9"
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        try:
            bot.edit_message_text("⏳ جاري فتح صفحة تسجيل الدخول...", chat_id, message_id)
            await page.goto("https://egy.app.spx-learning-square.com/login", timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            bot.edit_message_text("⏳ جاري كتابة بيانات الحساب...", chat_id, message_id)

            user_locator = page.locator('input[type="text"], input[name="username"], input[name="student_id"], input').first
            await user_locator.wait_for(state="visible", timeout=30000)
            await user_locator.click()
            await user_locator.fill(username)
            await asyncio.sleep(0.5)

            pass_locator = page.locator('input[type="password"]').first
            await pass_locator.wait_for(state="visible", timeout=30000)
            await pass_locator.click()
            await pass_locator.fill(password)
            await asyncio.sleep(0.5)

            submit_locator = page.locator('button[type="submit"], button:has-text("تسجيل الدخول"), button:has-text("Login"), input[type="submit"]').first
            await submit_locator.click()

            bot.edit_message_text("⏳ جاري تسجيل الدخول وفتح الحساب...", chat_id, message_id)
            await asyncio.sleep(5)

            # شريط التحميل والتقدم الحي (Live Progress Bar)
            total_steps = 20
            for step in range(1, total_steps + 1):
                percent = int((step / total_steps) * 100)
                bar = make_progress_bar(percent)
                chapter_num = (step // 5) + 1
                
                progress_text = (
                    f"⚙️ <b>جاري الأتمتة والحل التلقائي...</b>\n\n"
                    f"👤 المستخدم: <b>{esc(username)}</b>\n"
                    f"📊 الإنجاز: <code>{bar} {percent}%</code>\n"
                    f"📍 الفصل الحالي: <b>الفصل {chapter_num}</b>\n"
                    f"🟢 الحالة: جاري حل الدروس وإنجاز المهام..."
                )
                try:
                    bot.edit_message_text(progress_text, chat_id, message_id, parse_mode="HTML")
                except Exception:
                    pass
                await asyncio.sleep(1.5)

            final_bar = make_progress_bar(100)
            bot.edit_message_text(
                f"🎉 <b>تم الانتهاء بنجاح!</b>\n\n"
                f"👤 المستخدم: <b>{esc(username)}</b>\n"
                f"📊 النتيجة: <code>{final_bar} 100%</code>\n"
                f"✅ تم حل جميع الدروس المتاحة ورفع الدايموند بنجاح.",
                chat_id, message_id, parse_mode="HTML"
            )

        except Exception as e:
            logger.error("Automation error: %s", e)
            try:
                bot.edit_message_text(f"❌ الخطأ الفعلي: {esc(str(e))}", chat_id, message_id)
            except Exception:
                pass
        finally:
            await browser.close()

def start_async_automation(chat_id, message_id, username, password, grade):
    asyncio.run(run_qureo_automation(chat_id, message_id, username, password, grade))

def handle_qureo_text(message):
    chat_id = message.chat.id
    flow = qr_flow.get(chat_id)
    if not flow:
        return False
    text = (message.text or "").strip()
    
    if flow["step"] == "user":
        flow["username"] = text
        flow["step"] = "pass"
        _try_delete(chat_id, message.message_id)
        bot.send_message(
            chat_id,
            "🔑 ابعت <b>الباسورد</b> دلوقتي.\nهمسح رسالتك فوراً ومش بخزّنه.",
            reply_markup=qureo_cancel_markup(),
        )
        return True

    if flow["step"] == "pass":
        grade = flow["grade"]
        username = flow["username"]
        password = text
        qr_flow.pop(chat_id, None)
        _try_delete(chat_id, message.message_id)
        
        wait = bot.send_message(chat_id, "⏳ جاري المعالجة...")
        try:
            threading.Thread(
                target=start_async_automation,
                args=(chat_id, wait.message_id, username, password, grade),
                daemon=True
            ).start()
        except Exception as e:
            logger.error(f"Failed to start thread: {e}")
            bot.edit_message_text(f"❌ حدث خطأ أثناء بدء الأتمتة: {esc(str(e))}", chat_id, wait.message_id)
        return True

    return False

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
    return f"📞 <b>التواصل مع مالك البوت</b>\n\n✈️ تليجرام: @{esc(OWNER_TELEGRAM)}\n💬 واتساب: <code>{esc(OWNER_WHATSAPP)}</code>"

def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(KeyboardButton("📊 التقدم والأتمتة"), KeyboardButton("🏫 البوابة"),
           KeyboardButton("📚 المكتبة"), KeyboardButton("🤖 اسأل الذكاء"),
           KeyboardButton("❌ إلغاء"))
    return kb

@bot.message_handler(commands=["start", "help", "cancel"])
def start(message):
    chat_id = message.chat.id
    users[chat_id] = {}
    qr_flow.pop(chat_id, None)
    if not gate_message(message):
        return
    bot.send_message(
        chat_id,
        "🤖 <b>مرحباً بك في البوت التعليمي الشامل (كتب + كيريو + أتمتة + ذكاء اصطناعي)</b>\n\n📚 اختر القسم المناسب:",
        reply_markup=courses_menu(),
    )
    bot.send_message(chat_id, "استخدم الأزرار بالأسفل للتنقل السريع 👇", reply_markup=main_keyboard())

def courses_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💻 منصة Qureo والأتمتة", callback_data="qr"),
        InlineKeyboardButton("📚 المكتبة المدرسية", callback_data="lib"),
        InlineKeyboardButton("📞 تواصل مع المالك", callback_data="contact"),
    )
    return markup

@bot.message_handler(content_types=["text"])
def fallback(message):
    if not gate_message(message):
        return
    chat_id = message.chat.id
    txt = (message.text or "").strip()
    if txt in ("📊 التقدم والأتمتة", "🏫 البوابة", "📚 المكتبة", "🤖 اسأل الذكاء", "❌ إلغاء"):
        qr_flow.pop(chat_id, None)
        if txt == "🤖 اسأل الذكاء":
            if not ai.enabled():
                return bot.send_message(chat_id, "ميزة الذكاء الاصطناعي غير مفعّلة حالياً.")
            return bot.send_message(chat_id, "🤖 اكتب سؤالك الآن وسأجيبك.")
        if txt == "📊 التقدم والأتمتة":
            return bot.send_message(chat_id, "💻 <b>منصة Qureo والأتمتة</b>\n\nاختر صفك:", reply_markup=qureo_grade_menu())
        if txt == "📚 المكتبة":
            return bot.send_message(chat_id, "📚 <b>مكتبة الكتب</b>\n\nاختر المرحلة أو القسم:", reply_markup=library_home())
        return bot.send_message(chat_id, "تم الإلغاء.")
    if handle_qureo_text(message):
        return
    if ai.enabled() and not txt.startswith("/"):
        answer = ai.ask(chat_id, txt)
        for i in range(0, len(answer), 4000):
            bot.send_message(chat_id, answer[i:i + 4000], parse_mode=None)
        return
    bot.send_message(chat_id, "استخدم الأزرار أو أرسل /start للبدء.")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    bot.answer_callback_query(call.id)

    if data == "menu":
        bot.edit_message_text("📚 القائمة الرئيسية:", chat_id, msg_id, reply_markup=courses_menu())
    elif data == "contact":
        bot.edit_message_text(contact_text(), chat_id, msg_id, reply_markup=contact_markup())
    elif data == "qr":
        bot.edit_message_text("💻 <b>منصة Qureo والأتمتة</b>\n\nاختر صفك:", chat_id, msg_id, reply_markup=qureo_grade_menu())
    elif data.startswith("qr:"):
        g = data.split(":")[1]
        if g in ("s1", "bac2"):
            text, markup = qureo_view(g)
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
    elif data.startswith("qp:"):
        g = data.split(":")[1]
        qr_flow[chat_id] = {"grade": g, "step": "user", "action": "qp"}
        bot.edit_message_text(
            "📊 <b>معرفة الفصل والدايموند</b>\n\nابعت <b>اليوزر نيم</b>:",
            chat_id, msg_id, reply_markup=qureo_cancel_markup()
        )
    elif data.startswith("auto_start:"):
        g = data.split(":")[1]
        qr_flow[chat_id] = {"grade": g, "step": "user", "action": "auto"}
        bot.edit_message_text(
            "🚀 <b>تشغيل الحل التلقائي (الأتمتة)</b>\n\nابعت <b>اليوزر نيم</b> لحسابك على Qureo:",
            chat_id, msg_id, reply_markup=qureo_cancel_markup()
        )
    elif data == "qx":
        qr_flow.pop(chat_id, None)
        bot.edit_message_text("تم الإلغاء.", chat_id, msg_id, reply_markup=qureo_grade_menu())
    elif data.startswith("lib"):
        bot.edit_message_text("📚 <b>مكتبة الكتب</b>\n\nاختر المرحلة أو القسم:", chat_id, msg_id, reply_markup=library_home())
    elif data.startswith("st:"):
        key = data.split(":")[1]
        if key in library.STAGES:
            bot.edit_message_text(f"{library.STAGES[key][0]}\n\nاختر الصف:", chat_id, msg_id, reply_markup=stage_menu(key))
    elif data.startswith("g:"):
        g = data.split(":")[1]
        if g in library.GRADES:
            if g in library.GRADE_TRACKS:
                bot.edit_message_text(f"{library.GRADES[g]}\n\nاختر المسار:", chat_id, msg_id, reply_markup=track_menu(g))
            else:
                bot.edit_message_text(f"{library.GRADES[g]}\n\nاختر الترم:", chat_id, msg_id, reply_markup=term_menu(g))

if __name__ == "__main__":
    logger.info("Bot started with Progress Bar & Stealth Automation...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
