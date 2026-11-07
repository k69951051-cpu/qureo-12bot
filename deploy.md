# أول نشر (أو عند تغيير كل المتغيرات):
gcloud run deploy qureo-bot --source . --region europe-west1 \
  --allow-unauthenticated --no-cpu-throttling \
  --min-instances 1 --max-instances 1 \
  --set-env-vars BOT_TOKEN=xxx,QUREO_MODE=real,REQUIRED_CHANNEL=off,GEMINI_API_KEY=xxx,ADMIN_BOT_TOKEN=xxx,ADMIN_IDS=123456,STORAGE_CHANNEL_ID=-100...

# بعد كده، لتغيير متغير واحد بدون مسح الباقي استخدم --update-env-vars (مش --set-env-vars):
gcloud run deploy qureo-bot --source . --region europe-west1 \
  --update-env-vars GEMINI_API_KEY=xxx

# ADMIN_BOT_TOKEN لازم يكون توكن بوت مختلف عن BOT_TOKEN (من @BotFather)
# ADMIN_IDS = رقم حسابك على تليجرام (ابعت /start للبوت وهو يرجّعلك رقمك)
