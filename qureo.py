"""
ربط بوت الطلاب بمنصة Qureo و Sprix:
يتحقق من رقم الدخول والباسورد مع ترويسات محاكية للمتصفح الحقيقي لتجاوز الحماية.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

MODE = os.getenv("QUREO_MODE", "demo").strip().lower()
TIMEOUT = 15
BASE = "https://me-portal.qureo.education"

# ترويسات مطابقة تماماً لمتصفح هاتف محمول حقيقي لتجاوز حماية المنصة
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/json",
    "Origin": BASE,
    "Referer": BASE + "/login",
    "Sec-Ch-Ua": '"Not-A.Brand";v="99", "Chromium";v="120"',
    "Sec-Ch-Ua-Mobile": "?1",
    "Sec-Ch-Ua-Platform": '"Android"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
}

class LoginFailed(Exception):
    """رقم الدخول أو الباسورد غير صحيح."""

class NotConfigured(Exception):
    """الوضع الفعلي غير مضبوط بعد."""

class QureoUnavailable(Exception):
    """تعذر الوصول للمنصة أو شكل الرد غير متوقع."""

def _demo(username, course_type="programming"):
    n = sum(username.encode("utf-8"))
    return {
        "chapter": f"الفصل {n % 9 + 1}",
        "diamonds": (n * 7) % 400,
        "courses": ["javascript", "python"],
        "demo": True
    }

def _dig(data, path):
    cur = data
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur

def _opt(data, path, cast):
    if not path:
        return None
    try:
        return cast(_dig(data, path))
    except (KeyError, IndexError, ValueError, TypeError):
        return None

def _real(username, password, course_type="programming"):
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
            
            # إرسال طلب تسجيل الدخول
            r = s.post(login_url, json={user_f: username, pass_f: password},
                       timeout=TIMEOUT, allow_redirects=True)
            
            # تسجيل الحالة في اللوج لمعرفة سبب الرفض إن وجدت
            logger.info("Qureo Login Status Code: %s", r.status_code)
            
            if r.status_code in (400, 401, 403):
                raise LoginFailed()
            r.raise_for_status()
            
            # جلب معلومات المستخدم
            p = s.get(progress_url, timeout=TIMEOUT)
            logger.info("Qureo Userinfo Status Code: %s", p.status_code)
            
            if p.status_code in (401, 403):
                raise LoginFailed()
            p.raise_for_status()
            data = p.json()
            
        chapter = _opt(data, ch_key, str) or "متاح عبر المنصة"
        diamonds = _opt(data, dm_key, int)
        
        perms = data.get("permissions") if isinstance(data, dict) else None
        courses = sorted({p for p in (perms or []) if isinstance(p, str) and not p.endswith("_trial")})
        if not courses and isinstance(perms, list):
            courses = perms

        return {
            "chapter": chapter, 
            "diamonds": diamonds, 
            "courses": courses if courses else ["javascript", "python"], 
            "name": data.get("name", username),
            "school_id": data.get("school_id"),
            "demo": False
        }
    except LoginFailed:
        raise
    except Exception as e:
        logger.error("Qureo API Error Details: %s", type(e).__name__ + ": " + str(e))
        raise QureoUnavailable(type(e).__name__) from None

def fetch_progress(username, password, course_type="programming"):
    if not username or not password:
        raise LoginFailed()
    if MODE == "real":
        return _real(username, password, course_type)
    return _demo(username, course_type)
