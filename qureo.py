"""
ربط بوت الطلاب بمنصة Qureo: يتحقق من اليوزر والباسورد ويرجع الفصل الحالي وعدد الدايموند.

الأوضاع (متغير البيئة QUREO_MODE):
  demo  (الافتراضي) : نتيجة تجريبية ثابتة لأي يوزر/باسورد غير فارغين، لتجربة الفلو وتدريب الطلاب.
  real              : دخول فعلي عبر HTTP. يحتاج ضبط المتغيرات التالية بعد معرفة طلبات المنصة
                      (من تبويب Network في المتصفح أو من وثائق SPRIX الرسمية):
        QUREO_LOGIN_URL      رابط طلب تسجيل الدخول (POST)
        QUREO_USER_FIELD     اسم حقل اليوزر في الطلب   (افتراضي: username)
        QUREO_PASS_FIELD     اسم حقل الباسورد          (افتراضي: password)
        QUREO_PROGRESS_URL   رابط جلب التقدم (GET) بعد الدخول
        QUREO_CHAPTER_KEY    مفتاح الفصل في رد JSON    (افتراضي: chapter)
        QUREO_DIAMONDS_KEY   مفتاح الدايموند في رد JSON (افتراضي: diamonds)
        QUREO_TOKEN_KEY      (اختياري) مفتاح التوكن في رد الدخول لو المنصة تستخدم Bearer

لا يتم تخزين الباسورد ولا تسجيله في اللوج: يُستخدم في الذاكرة لطلب واحد فقط.
"""
import os

import requests

MODE = os.getenv("QUREO_MODE", "demo").strip().lower()
TIMEOUT = 15


class LoginFailed(Exception):
    """اليوزر أو الباسورد غير صحيح."""


class NotConfigured(Exception):
    """الوضع الفعلي غير مضبوط بعد."""


class QureoUnavailable(Exception):
    """تعذر الوصول للمنصة أو شكل الرد غير متوقع."""


def _demo(username):
    n = sum(username.encode("utf-8"))
    return {"chapter": f"الفصل {n % 9 + 1}", "diamonds": (n * 7) % 400, "demo": True}


def _real(username, password):
    login_url = os.getenv("QUREO_LOGIN_URL", "").strip()
    progress_url = os.getenv("QUREO_PROGRESS_URL", "").strip()
    if not login_url or not progress_url:
        raise NotConfigured()
    user_f = os.getenv("QUREO_USER_FIELD", "username")
    pass_f = os.getenv("QUREO_PASS_FIELD", "password")
    ch_key = os.getenv("QUREO_CHAPTER_KEY", "chapter")
    dm_key = os.getenv("QUREO_DIAMONDS_KEY", "diamonds")
    tok_key = os.getenv("QUREO_TOKEN_KEY", "").strip()
    try:
        with requests.Session() as s:
            r = s.post(login_url, json={user_f: username, pass_f: password}, timeout=TIMEOUT)
            if r.status_code in (400, 401, 403):
                raise LoginFailed()
            r.raise_for_status()
            if tok_key:
                s.headers["Authorization"] = f"Bearer {r.json()[tok_key]}"
            p = s.get(progress_url, timeout=TIMEOUT)
            p.raise_for_status()
            data = p.json()
        return {"chapter": str(data[ch_key]), "diamonds": int(data[dm_key]), "demo": False}
    except LoginFailed:
        raise
    except (requests.RequestException, KeyError, ValueError, TypeError) as e:
        # نسجّل نوع الخطأ فقط (بدون أي بيانات دخول)
        raise QureoUnavailable(type(e).__name__) from None


def fetch_progress(username, password):
    """يرجع {"chapter", "diamonds", "demo"} أو يرفع LoginFailed / NotConfigured / QureoUnavailable."""
    if not username or not password:
        raise LoginFailed()
    if MODE == "real":
        return _real(username, password)
    return _demo(username)
