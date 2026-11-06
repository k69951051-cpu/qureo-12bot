import os
import base64
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
QUREO_URL = "https://me-tp.qureo.education/"

if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN as an environment variable.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_modes = {}

def menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🤖 حل سؤال", callback_data="solve"),
        InlineKeyboardButton("📘 Qureo", callback_data="qureo"),
        InlineKeyboardButton("🧪 تجربة توضيحية", callback_data="demo"),
        InlineKeyboardButton("ℹ️ المساعدة", callback_data="help"),
    )
    return kb

def ai_solve(prompt, image_bytes=None):
    if not OPENAI_API_KEY:
        return ("البوت متوصلش بمفتاح الذكاء الاصطناعي لسه. "
                "أضف OPENAI_API_KEY في إعدادات الاستضافة، ثم أعد التشغيل.")
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    system = (
        "أنت مساعد تعليمي لطالب مدرسة. حل السؤال بدقة وبالعربية المصرية المبسطة. "
        "لو السؤال برمجة، اكتب الكود الصحيح داخل code block واشرحه باختصار. "
        "لو الصورة غير واضحة أو البيانات ناقصة، اطلب صورة أوضح ولا تخمّن. "
        "اذكر الإجابة ثم سببها، ولا تدّعِ أنك أرسلت الإجابة إلى منصة خارجية."
    )
    content = [{"type": "text", "text": prompt or "اقرأ السؤال من الصورة وحله واشرحه."}]
    if image_bytes:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}
        })
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "temperature": 0.2,
    }
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers, json=payload, timeout=90
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "أهلاً بيك 👋\nأنا مساعدك التعليمي.\n"
        "ابعت سؤال كتابة أو صورة، وأنا أحله وأشرحلك. "
        "تقدر كمان تفتح Qureo من الزر الموجود تحت.",
        reply_markup=menu()
    )

@bot.message_handler(commands=["help"])
def help_cmd(message):
    help_text(message.chat.id)

def help_text(chat_id):
    bot.send_message(
        chat_id,
        "طريقة الاستخدام:\n"
        "• ابعت نص السؤال مباشرة.\n"
        "• أو ابعت صورة واضحة للسؤال.\n"
        "• استخدم /demo لتجربة شكل التكامل.\n\n"
        "مهم: النسخة الحالية تحل الأسئلة داخل تليجرام، "
        "ولا تطلب كلمة مرور Qureo ولا ترسل إجابات للمنصة. "
        "التكامل الفعلي يحتاج API رسمي وآلية مصادقة معتمدة."
    )

@bot.message_handler(commands=["demo"])
def demo_cmd(message):
    demo_text(message.chat.id)

def demo_text(chat_id):
    bot.send_message(
        chat_id,
        "🧪 <b>وضع التجربة – بيانات وهمية</b>\n\n"
        "الدرس: المتغيرات – Python\n"
        "المهمة: خزّن الرقم 5 في المتغير num ثم اطبع قيمته.\n\n"
        "الحل النموذجي:\n<pre>num = 5\nprint(num)</pre>\n"
        "الحالة: تم تجهيز مثال توضيحي فقط؛ لم يتم الاتصال بحساب Qureo."
    )

@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    if call.data == "solve":
        bot.answer_callback_query(call.id, "ابعت السؤال كتابة أو صورة.")
        bot.send_message(call.message.chat.id, "ابعت السؤال دلوقتي ✍️")
    elif call.data == "qureo":
        bot.answer_callback_query(call.id)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("فتح منصة Qureo", url=QUREO_URL))
        bot.send_message(call.message.chat.id,
                         "افتح حسابك بنفسك من الموقع الرسمي، ومتبعثش كلمة المرور للبوت.",
                         reply_markup=kb)
    elif call.data == "demo":
        bot.answer_callback_query(call.id)
        demo_text(call.message.chat.id)
    elif call.data == "help":
        bot.answer_callback_query(call.id)
        help_text(call.message.chat.id)

@bot.message_handler(content_types=["photo"])
def photo_handler(message):
    status = bot.reply_to(message, "⏳ بفحص الصورة وبحل السؤال...")
    try:
        photo = message.photo[-1]
        info = bot.get_file(photo.file_id)
        data = bot.download_file(info.file_path)
        answer = ai_solve(message.caption or "حل السؤال الموجود في الصورة واشرحه.", data)
        bot.edit_message_text(answer, message.chat.id, status.message_id)
    except Exception as e:
        bot.edit_message_text(
            "حصل خطأ أثناء تحليل الصورة. تأكد من إعداد OPENAI_API_KEY "
            "وجرب صورة أوضح.\n"
            f"<code>{str(e)[:500]}</code>",
            message.chat.id, status.message_id
        )

@bot.message_handler(content_types=["text"])
def text_handler(message):
    if message.text.startswith("/"):
        return
    status = bot.reply_to(message, "⏳ بفكر في السؤال...")
    try:
        answer = ai_solve(message.text)
        bot.edit_message_text(answer, message.chat.id, status.message_id)
    except Exception as e:
        bot.edit_message_text(
            "حصل خطأ أثناء الحل. راجع مفتاح OpenAI والاتصال.\n"
            f"<code>{str(e)[:500]}</code>",
            message.chat.id, status.message_id
        )

if __name__ == "__main__":
    print("Qureo learning bot is running...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
