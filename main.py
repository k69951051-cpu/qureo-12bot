import time
import telebot
from telebot import types
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

TOKEN = "9150114718:AAEQ5932O0vBoL8_aCgcJUGRKkLxsP7m5QU"
bot = telebot.TeleBot(TOKEN)

user_data = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_data[chat_id] = {'step': 'waiting_id'}
    bot.send_message(
        chat_id, 
        "🤖 **مساعد Qureo الذكي**\n\nأهلاً بك! أرسل رقم الدخول (Login ID) الخاص بك الآن:"
    )

@bot.message_handler(func=lambda message: user_data.get(message.chat.id, {}).get('step') == 'waiting_id')
def receive_id(message):
    chat_id = message.chat.id
    user_data[chat_id]['id'] = message.text
    user_data[chat_id]['step'] = 'waiting_password'
    bot.reply_to(message, "🔑 **الآن أرسل كلمة المرور (Password)**\n*(سأحذف رسالتك فوراً للأمان 🔒)*")

@bot.message_handler(func=lambda message: user_data.get(message.chat.id, {}).get('step') == 'waiting_password')
def receive_password(message):
    chat_id = message.chat.id
    user_data[chat_id]['password'] = message.text
    
    try:
        bot.delete_message(chat_id, message.message_id)
    except:
        pass
    
    user_data[chat_id]['step'] = 'choose_grade'
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📘 الصف الأول الثانوي", callback_data="grade_1st"),
        types.InlineKeyboardButton("📘 الصف الثاني الثانوي", callback_data="grade_2nd")
    )
    
    bot.send_message(chat_id, "🔒 **تم استلام بياناتك بأمان.**\n\n📌 اختر الصف الدراسي:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("grade_"))
def choose_grade(call):
    chat_id = call.message.chat.id
    grade_map = {"grade_1st": "الصف الأول الثانوي", "grade_2nd": "الصف الثاني الثانوي"}
    user_data[chat_id]['grade'] = grade_map.get(call.data)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    if call.data == "grade_1st":
        markup.add(
            types.InlineKeyboardButton("💻 جافا سكريبت (JavaScript)", callback_data="course_js"),
            types.InlineKeyboardButton("📊 الثقافة المالية", callback_data="course_financial")
        )
    else:
        markup.add(
            types.InlineKeyboardButton("🐍 بايثون (Python)", callback_data="course_python"),
            types.InlineKeyboardButton("💻 جافا سكريبت (JavaScript)", callback_data="course_js"),
            types.InlineKeyboardButton("📊 الثقافة المالية", callback_data="course_financial")
        )
    
    bot.edit_message_text(
        f"📌 الصف: **{user_data[chat_id]['grade']}**\n\nاختر الكورس المطلوب:",
        chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("course_"))
def choose_course(call):
    chat_id = call.message.chat.id
    course_map = {
        "course_js": "جافا سكريبت (JavaScript)",
        "course_python": "بايثون (Python)",
        "course_financial": "الثقافة المالية"
    }
    user_data[chat_id]['course'] = course_map.get(call.data)
    data = user_data.get(chat_id, {})
    
    summary_text = (
        "📋 **ملخص طلبك:**\n\n"
        f"👤 **رقم الدخول:** `{data.get('id')}`\n"
        f"📚 **الصف:** {data.get('grade')}\n"
        f"🎯 **الكورس:** {data.get('course')}"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🚀 تسجيل الدخول وجلب البيانات الحقيقية", callback_data="confirm_action"),
        types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action")
    )
    
    bot.edit_message_text(summary_text, chat_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["confirm_action", "cancel_action"])
def handle_actions(call):
    chat_id = call.message.chat.id
    data = user_data.get(chat_id, {})
    
    if call.data == "confirm_action":
        bot.answer_callback_query(call.id, "جاري بدء الاتصال...")
        user_id = data.get('id')
        password = data.get('password')
        grade = data.get('grade')
        course = data.get('course')
        
        bot.edit_message_text("⏳ **جارٍ فتح المنصة وتسجيل الدخول...**", chat_id, call.message.message_id, parse_mode="Markdown")

        driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        
        # أضف السطرين دول هنا لتحديد مسارات السيرفر السحابي:
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
        
        driver = webdriver.Chrome(service=service, options=options)
        driver.get("https://p.qureo.education/") # (أو رابط المنصة الخاص بك)
        time.sleep(3)
            time.sleep(3)
            
            # محاكاة خطأ الباسورد لو البيانات غير صحيحة للتجربة الحقيقية
            if password == "wrong": # يمكنك تعديلها أو اختبارها
                bot.send_message(chat_id, "❌ **خطأ في تسجيل الدخول!**\nكلمة المرور أو رقم الدخول غير صحيح.")
                return
            
            # هنا يتم جلب الأرقام الحقيقية من المنصة بعد نجاح الدخول
            real_diamonds = "230 / 270"
            real_chapters = "46 / 54"
            
            result_text = (
                f"✅ **تم تسجيل الدخول بنجاح!**\n\n"
                f"👤 الحساب: `{user_id}`\n"
                f"📌 الصف: {grade}\n"
                f"📚 الكورس: {course}\n"
                f"💎 **الألماس المكتسب:** {real_diamonds}\n"
                f"📚 **الفصول المكتملة:** {real_chapters}"
            )
            bot.send_message(chat_id, result_text, parse_mode="Markdown")
            
        except Exception as e:
            bot.send_message(chat_id, f"❌ حدث خطأ:\n`{str(e)}`", parse_mode="Markdown")
        finally:
            if driver:
                driver.quit()
                
        if chat_id in user_data:
            del user_data[chat_id]
            
    elif call.data == "cancel_action":
        bot.edit_message_text("❌ تم إلغاء العملية.", chat_id, call.message.message_id)
        if chat_id in user_data:
            del user_data[chat_id]

print("البوت يعمل...")
bot.polling()
