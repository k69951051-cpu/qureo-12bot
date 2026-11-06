"""
ربط بوت الطلاب بمنصة Qureo و Sprix (التثقيف المالي والبرمجة):
يتحقق من رقم الدخول والباسورد ويرجع الفصول المتاحة، الرصيد، والكورسات.
"""
import os
import requests

MODE = os.getenv("QUREO_MODE", "demo").strip().lower()
TIMEOUT = 15
BASE = "https://me-portal.qureo.education"
SPRIX_FIN_BASE = os.getenv("SPRIX_FIN_BASE", "https://egy.app.spx-learning-square.com")
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

def _demo(username, course_type="programming"):
    n = sum(username.encode("utf-8"))
    if course_type == "financial":
        return {
            "chapter": f"الفصل {n % 58 + 1} (من 58)",
            "diamonds": (n * 7) % 400,
            "courses": ["الثقافة المالية (Sprix)"],
            "demo": True
        }
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
            r = s.post(login_url, json={user_f: username, pass_f: password},
                       timeout=TIMEOUT, allow_redirects=True)
            if r.status_code in (400, 401, 403):
                raise LoginFailed()
            p = s.get(progress_url, timeout=TIMEOUT)
            if p.status_code in (401, 403):
                raise LoginFailed()
            p.raise_for_status()
            data = p.json()
        chapter = _opt(data, ch_key, str)
        diamonds = _opt(data, dm_key, int)
        perms = data.get("permissions") if isinstance(data, dict) else None
        courses = sorted({p for p in (perms or []) if isinstance(p, str) and not p.endswith("_trial")})
        if course_type == "financial":
            courses.append("الثقافة المالية")
        return {"chapter": chapter, "diamonds": diamonds, "courses": courses, "demo": False}
    except LoginFailed:
        raise
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError) as e:
        raise QureoUnavailable(type(e).__name__) from None

def fetch_progress(username, password, course_type="programming"):
    if not username or not password:
        raise LoginFailed()
    if MODE == "real":
        return _real(username, password, course_type)
    return _demo(username, course_type)
