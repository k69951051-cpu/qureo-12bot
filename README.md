# Qureo Telegram Learning Bot

نسخة تشغيل أولية:
- بوت Telegram يستقبل الأسئلة النصية والصور.
- يستخدم OpenAI لحل السؤال وشرحه.
- يحتوي وضع Demo ببيانات وهمية.
- يفتح رابط Qureo الرسمي.
- لا يجمع كلمات مرور الطلاب ولا يرسل إجابات للمنصة.

## التشغيل محليًا

1. أنشئ بوتًا جديدًا من BotFather.
2. انسخ `.env.example` إلى `.env` (لا ترفع الملف إلى Git).
3. ضع `BOT_TOKEN` و`OPENAI_API_KEY` كمتغيرات بيئة.
4. ثبّت الحزم: `pip install -r requirements.txt`
5. شغّل: `python bot.py`

على Windows PowerShell:
```powershell
$env:BOT_TOKEN="YOUR_NEW_BOT_TOKEN"
$env:OPENAI_API_KEY="YOUR_OPENAI_KEY"
python bot.py
```

على Linux/macOS:
```bash
export BOT_TOKEN="YOUR_NEW_BOT_TOKEN"
export OPENAI_API_KEY="YOUR_OPENAI_KEY"
python bot.py
```

## ما يلزم لتفعيل Qureo الحقيقي

الصور المرسلة توضح بعض مسارات HTTP وطلب إجابة لنشاط Python، لكنها لا تكفي لبناء تكامل آمن أو ثابت:
- نحتاج وثائق API رسمية أو موافقة تقنية من Qureo تحدد طريقة المصادقة والصلاحيات.
- لا تستخدم Cookies أو Authorization مأخوذة من جلسة المتصفح داخل بوت متعدد المستخدمين.
- لا تعتمد على endpoints غير موثقة أو تتجاوز CAPTCHA/2FA أو ضوابط المنصة.
- عند توفير API رسمي، تُستكمل الدوال في `qureo_adapter.py`.

## أمان

إذا سبق نشر توكن البوت في محادثة أو صورة، ألغِه من BotFather وأنشئ توكنًا جديدًا. لا ترسل المفاتيح أو كلمات المرور في المحادثة.
