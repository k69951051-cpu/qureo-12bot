gcloud run deploy qureo-bot --source . --region europe-west1 \
  --allow-unauthenticated --no-cpu-throttling \
  --min-instances 1 --max-instances 1 \
  --set-env-vars BOT_TOKEN=xxx,QUREO_MODE=real,REQUIRED_CHANNEL=off
# بوت الإدارة (اختياري): ADMIN_BOT_TOKEN=xxx,ADMIN_IDS=123456
# التخزين: STORAGE_CHANNEL_ID=-100... (لأن ملفات Cloud Run مؤقتة)
