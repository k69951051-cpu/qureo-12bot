# استخدام صورة بايثون رسمية خفيفة
FROM python:3.10-slim

# تحديد مجلد العمل داخل السيرفر
WORKDIR /app

# نسخ ملف المتطلبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تثبيت متصفح Playwright مع مكتبات النظام الضرورية ليعمل بدون مشاكل
RUN playwright install --with-deps chromium

# نسخ باقي ملفات المشروع إلى السيرفر
COPY . .

# أمر تشغيل البوت (تأكد أنه يشغل ملف البداية لديك، غالباً main.py)
CMD ["python", "main.py"]
