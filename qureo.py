"""
ربط بوت الطلاب بمنصة Qureo: يتحقق من رقم الدخول والباسورد ويرجع الفصل الحالي وعدد الدايموند.

الأوضاع (متغير البيئة QUREO_MODE):
  demo  (الافتراضي) : نتيجة تجريبية ثابتة لأي رقم/باسورد غير فارغين.
  real              : دخول فعلي عبر HTTP (OAuth2 بكوكيز):
        POST  QUREO_LOGIN_URL  بجسم JSON {student_id, password}  ثم نتبع التحويل ونحتفظ بالكوكيز
        GET   QUREO_PROGRESS_URL  بنفس الجلسة، ونقرأ الفصل والدايموند من رد JSON

متغيرات البيئة (كلها لها قيم افتراضية مناسبة للمنصة):
  QUREO_LOGIN_URL      (افتراضي: https://me-portal.qureo.education/oauth2/password-login)
  QUREO_USER_FIELD     (افتراضي: student_id)
  QUREO_PASS_FIELD     (افتراضي: password)
  QUREO_PROGRESS_URL   (افتراضي: https://me-portal.qureo.education/oauth2/userinfo)
  QUREO_CHAPTER_KEY    (اختياري) مسار الفصل في رد JSON، يدعم النقاط مثل  data.chapter
  QUREO_DIAMONDS_KEY   (اختياري) مسار الدايموند، مثل  data.diamonds
  (رد userinfo الحالي فيه الكورسات المتاحة فقط؛ الفصل والدايموند يظهران عند ضبط المسارين)

لا يتم تخزين الباسورد ولا تسجيله في اللوج: يُستخدم في الذاكرة لطلب واحد فقط.
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)
LAST = "لم يُستخدم بعد"

MODE = os.getenv("QUREO_MODE", "demo").strip().lower()
TIMEOUT = 15
BASE = "https://me-portal.qureo.education"
HEADERS = {
    "Accept": "application/json, */*",
    "Origin": BASE,
    "Referer": BASE + "/login",
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
}


class LoginFailed(Exception):
    """رقم الدخول أو الباسورد غير صحيح."""


class NotConfigured(Exception):
    """الوضع الفعلي غير مضبوط بعد."""


class QureoUnavailable(Exception):
    """تعذر الوصول للمنصة أو شكل الرد غير متوقع."""


def _demo(username):
    n = sum(username.encode("utf-8"))
    return {"chapter": f"الفصل {n % 9 + 1}", "diamonds": (n * 7) % 400, "courses": ["javascript", "python"], "demo": True}


def _dig(data, path):
    """يقرأ قيمة من JSON متداخل بمسار منقط مثل a.b.c (ويدعم أرقام القوائم)."""
    cur = data
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur


def _opt(data, path, cast):
    """قيمة اختيارية: ترجع None إذا لم يُضبط المسار أو لم توجد القيمة."""
    if not path:
        return None
    try:
        return cast(_dig(data, path))
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def _real(username, password):
    login_url = os.getenv("QUREO_LOGIN_URL", BASE + "/oauth2/password-login").strip()
    progress_url = os.getenv("QUREO_PROGRESS_URL", BASE + "/oauth2/userinfo").strip()
    if not login_url or not progress_url:
        raise NotConfigured()
    user_f = os.getenv("QUREO_USER_FIELD", "student_id")
    pass_f = os.getenv("QUREO_PASS_FIELD", "password")
    ch_key = os.getenv("QUREO_CHAPTER_KEY", "").strip()
    dm_key = os.getenv("QUREO_DIAMONDS_KEY", "").strip()
    try:
        with requests.Session() as s:
            s.headers.update(HEADERS)
            r = s.post(login_url, json={user_f: username, pass_f: password},
                       timeout=TIMEOUT, allow_redirects=True)
            global LAST
            LAST = f"login={r.status_code} redirects={len(r.history)} host={requests.utils.urlparse(r.url).netloc}"
            logger.info("qureo login: status=%s final_host=%s redirects=%s",
                        r.status_code, requests.utils.urlparse(r.url).netloc, len(r.history))
            if r.status_code in (400, 401, 403):
                raise LoginFailed()
            # الجلسة تقوم على الكوكيز: نتأكد من نجاح الدخول بطلب userinfo
            p = s.get(progress_url, timeout=TIMEOUT)
            LAST += f" | userinfo={p.status_code} type={p.headers.get('content-type')}"
            logger.info("qureo userinfo: status=%s type=%s", p.status_code, p.headers.get("content-type"))
            if p.status_code in (401, 403):
                raise LoginFailed()
            p.raise_for_status()
            data = p.json()
        chapter = _opt(data, ch_key, str)
        diamonds = _opt(data, dm_key, int)
        perms = data.get("permissions") if isinstance(data, dict) else None
        courses = sorted({p for p in (perms or []) if isinstance(p, str) and not p.endswith("_trial")})
        return {"chapter": chapter, "diamonds": diamonds, "courses": courses, "demo": False}
    except LoginFailed:
        raise
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError) as e:
        # نسجّل نوع الخطأ فقط (بدون أي بيانات دخول)
        LAST += f" | فشل: {type(e).__name__}"
        logger.warning("qureo failed: %s", type(e).__name__)
        raise QureoUnavailable(type(e).__name__) from None


def fetch_progress(username, password):
    """يرجع {"chapter", "diamonds", "demo"} أو يرفع LoginFailed / NotConfigured / QureoUnavailable."""
    if not username or not password:
        raise LoginFailed()
    if MODE == "real":
        return _real(username, password)
    return _demo(username)
