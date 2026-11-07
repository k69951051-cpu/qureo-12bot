"""مساعد ذكاء اصطناعي للبوت (Google Gemini عبر REST) مع اختيار تلقائي لأحدث نموذج flash متاح.

متغيرات البيئة:
  GEMINI_API_KEY   مفتاح Gemini من Google AI Studio (مطلوب)
  GEMINI_MODEL     (اختياري) اسم نموذج محدد. بدونه يختار البوت تلقائياً.
  AI_MAX_TOKENS    أقصى طول للرد (افتراضي 2000)
  AI_RATE_LIMIT    عدد الأسئلة لكل طالب في الساعة (افتراضي 20)
"""
import logging
import os
import re
import threading
import time

import requests

logger = logging.getLogger(__name__)

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "").strip() or "gemini-flash-latest"
MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "2000"))
RATE_LIMIT = int(os.getenv("AI_RATE_LIMIT", "20"))
HISTORY_MESSAGES = 8
BASE = "https://generativelanguage.googleapis.com/v1beta"

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
_state = {"model": MODEL, "think": True}
_lock = threading.Lock()
_history = {}
_usage = {}


def _headers():
    return {"x-goog-api-key": API_KEY, "Content-Type": "application/json"}


def enabled():
    return bool(API_KEY)


def current_model():
    return _state["model"]


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


def _discover():
    """يختار أحدث نموذج flash مستقر يدعم generateContent من قائمة جوجل."""
    r = requests.get(f"{BASE}/models", params={"pageSize": 200}, headers=_headers(), timeout=20)
    if r.status_code != 200:
        return None
    best, best_v = None, -1.0
    for m in r.json().get("models", []):
        name = m.get("name", "").split("/")[-1]
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if "flash" not in name or any(x in name for x in ("lite", "image", "tts", "live", "audio", "preview", "exp", "thinking", "robotics", "computer")):
            continue
        v = re.search(r"gemini-(\d+(?:\.\d+)?)-flash", name)
        ver = float(v.group(1)) if v else 0.0
        if ver > best_v:
            best, best_v = name, ver
    return best


def _generate(model, contents):
    cfg = {"maxOutputTokens": max(MAX_TOKENS, 4000), "temperature": 0.6}
    if _state["think"]:
        # نقلل "التفكير" الداخلي حتى لا يستهلك حد الرد فيرجع فارغاً
        cfg["thinkingConfig"] = {"thinkingBudget": 0}
    return requests.post(
        f"{BASE}/models/{model}:generateContent",
        headers=_headers(),
        json={
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": cfg,
        },
        timeout=(5, 20),
    )


def _error_detail(r):
    try:
        return (r.json().get("error") or {}).get("message", "")[:200]
    except ValueError:
        return ""


TRANSIENT = (429, 500, 502, 503, 504, 599)
DEADLINE = 40  # أقصى ثواني إجمالية لمحاولة الإجابة
FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest"]


class _Fail:
    """استجابة وهمية عند انتهاء المهلة/انقطاع الاتصال (نعاملها كخطأ مؤقت)."""
    status_code = 599

    def __init__(self, name):
        self.name = name

    def json(self):
        return {"error": {"message": self.name}}


def _call(model, contents):
    """طلب واحد مع معالجة رفض إعداد التفكير وانتهاء المهلة."""
    try:
        r = _generate(model, contents)
        if r.status_code == 400 and _state["think"]:
            # أغلب أسباب 400 هنا أن النموذج لا يقبل إعداد التفكير: نعيد بدونه
            _state["think"] = False
            r = _generate(model, contents)
        return r
    except requests.RequestException as e:
        return _Fail(type(e).__name__)


def _generate_with_fallback(contents):
    """محاولة النموذج الأساسي، ثم إعادة واحدة، ثم نموذج أخف، بحد زمني إجمالي."""
    t0 = time.time()
    primary = _state["model"]
    r = _call(primary, contents)
    if r.status_code == 404:  # النموذج غير موجود: نختار بديلاً تلقائياً
        found = _discover() or "gemini-flash-lite-latest"
        if found != primary:
            _state["model"] = primary = found
            r = _call(primary, contents)
    if r.status_code in TRANSIENT and time.time() - t0 < DEADLINE - 25:
        time.sleep(1)
        r = _call(primary, contents)
    for alt in FALLBACK_MODELS:
        if r.status_code not in TRANSIENT or time.time() - t0 > DEADLINE - 20:
            break
        if alt != primary:
            r = _call(alt, contents)
    return r


def ask(chat_id, question):
    """يرجع نص الرد (دائماً نص صالح للعرض، حتى عند الخطأ)."""
    global LAST
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
        r = _generate_with_fallback(contents)
        if r.status_code != 200:
            detail = _error_detail(r)
            LAST = f"HTTP {r.status_code} (model={_state['model']}): {detail}"
            logger.warning("AI API %s", LAST)
            return "تعذر الحصول على إجابة الآن، حاول مرة أخرى بعد قليل."
        data = r.json()
        cands = data.get("candidates") or []
        parts = (cands[0].get("content") or {}).get("parts", []) if cands else []
        answer = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        reason = cands[0].get("finishReason") if cands else (data.get("promptFeedback") or {}).get("blockReason")
        LAST = "OK" if answer else f"رد فارغ (السبب: {reason})"
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
