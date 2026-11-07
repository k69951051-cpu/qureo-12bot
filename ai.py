"""مساعد ذكاء اصطناعي للبوت (Google Gemini عبر REST).

متغيرات البيئة:
  GEMINI_API_KEY   مفتاح Gemini من Google AI Studio (مطلوب؛ بدونه تبقى الميزة مغلقة)
  GEMINI_MODEL     اسم النموذج (افتراضي: gemini-2.5-flash) - غيّره لو جوجل أوقفته
  AI_MAX_TOKENS    أقصى طول للرد (افتراضي 2000؛ يشمل تفكير النموذج الداخلي)
  AI_RATE_LIMIT    عدد الأسئلة المسموح لكل طالب في الساعة (افتراضي 20)
"""
import logging
import os
import threading
import time

import requests

logger = logging.getLogger(__name__)

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "2000"))
RATE_LIMIT = int(os.getenv("AI_RATE_LIMIT", "20"))
HISTORY_MESSAGES = 8  # آخر 4 أسئلة وردودها

SYSTEM_PROMPT = (
    "أنت مساعد تعليمي داخل بوت تليجرام لطلاب المرحلة الثانوية في مصر. "
    "أجب بنفس لغة الطالب (غالباً العربية المبسطة أو العامية المصرية الخفيفة). "
    "اشرح بوضوح وبخطوات قصيرة مع مثال عند الحاجة، وفي البرمجة (Python وJavaScript) "
    "اكتب أمثلة كود صغيرة وصحيحة. عند الأسئلة الدراسية شجّع الطالب على الفهم: "
    "وضّح الفكرة وخطوات الحل بدل إعطاء الإجابة المجردة فقط. "
    "اجعل الرد مختصراً (مناسب لشاشة الموبايل) وتجنب الجداول وعلامات Markdown الثقيلة. "
    "إذا لم تكن متأكداً قل ذلك بصراحة. لا تطلب من الطالب أي كلمات مرور أو بيانات حساب."
)

LAST = "لم يُستخدم بعد"

_lock = threading.Lock()
_history = {}   # chat_id -> [{"role","content"}, ...]
_usage = {}     # chat_id -> [timestamps]


def enabled():
    return bool(API_KEY)


def reset(chat_id):
    with _lock:
        _history.pop(chat_id, None)


def _allowed(chat_id):
    now = time.time()
    with _lock:
        stamps = [t for t in _usage.get(chat_id, []) if now - t < 3600]
        if len(stamps) >= RATE_LIMIT:
            _usage[chat_id] = stamps
            return False
        stamps.append(now)
        _usage[chat_id] = stamps
        return True


def ask(chat_id, question):
    """يرجع نص الرد (دائماً نص صالح للعرض، حتى عند الخطأ)."""
    if not enabled():
        return "ميزة الذكاء الاصطناعي غير مفعّلة حالياً."
    question = (question or "").strip()[:2000]
    if not question:
        return "اكتب سؤالك وسأجيبك 🙂"
    if not _allowed(chat_id):
        return "وصلت للحد الأقصى من الأسئلة هذه الساعة ⏳ جرّب بعد قليل."

    with _lock:
        msgs = list(_history.get(chat_id, []))[-HISTORY_MESSAGES:]
        while msgs and msgs[0]["role"] != "user":
            msgs.pop(0)
    msgs.append({"role": "user", "content": question})
    contents = [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in msgs]

    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            headers={"x-goog-api-key": API_KEY, "Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": contents,
                "generationConfig": {"maxOutputTokens": MAX_TOKENS, "temperature": 0.6},
            },
            timeout=45,
        )
        if r.status_code != 200:
            global LAST
            try:
                detail = (r.json().get("error") or {}).get("message", "")[:200]
            except ValueError:
                detail = ""
            LAST = f"HTTP {r.status_code}: {detail}"
            logger.warning("AI API %s", LAST)
            return "تعذر الحصول على إجابة الآن، حاول مرة أخرى بعد قليل."
        data = r.json()
        cands = data.get("candidates") or []
        parts = (cands[0].get("content") or {}).get("parts", []) if cands else []
        answer = "".join(p.get("text", "") for p in parts).strip()
        LAST = "OK" if answer else "رد فارغ (ربما حجب أمان)"
        if not answer:
            return "لم أستطع الإجابة عن هذا السؤال، جرّب إعادة صياغته."
    except (requests.RequestException, ValueError) as e:
        LAST = f"خطأ اتصال: {type(e).__name__}"
        logger.warning("AI request failed: %s", type(e).__name__)
        return "تعذر الاتصال بالمساعد الآن، حاول مرة أخرى بعد قليل."

    msgs.append({"role": "model", "content": answer})
    with _lock:
        _history[chat_id] = msgs[-HISTORY_MESSAGES:]
    return answer
