import os
import requests

TIMEOUT = 25


class LoginFailed(Exception):
    pass


class NotConfigured(Exception):
    pass


class QureoUnavailable(Exception):
    pass


MODE = os.getenv("QUREO_MODE", "demo").strip().lower()


def _demo(username):
    n = sum(username.encode("utf-8"))
    return {"chapter": f"الفصل {n % 9 + 1}", "diamonds": (n * 7) % 400, "demo": True}


def fetch_progress(username, password):
    if not username or not password:
        raise LoginFailed()
    if MODE == "real":
        return solve_chapters_real(username, password, action="fetch")
    return _demo(username)


def solve_chapters_real(username, password, chapter_id="all", action="solve"):
    login_url = os.getenv("QUREO_LOGIN_URL", "").strip()
    solve_url = os.getenv("QUREO_SOLVE_URL", "").strip()
    progress_url = os.getenv("QUREO_PROGRESS_URL", "").strip()

    if not login_url:
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
                token = r.json().get(tok_key)
                if token:
                    s.headers["Authorization"] = f"Bearer {token}"

            if action == "solve":
                if not solve_url:
                    raise NotConfigured()
                s_res = s.post(solve_url, json={"chapter": chapter_id}, timeout=TIMEOUT)
                s_res.raise_for_status()
                return s_res.json()
            else:
                if not progress_url:
                    raise NotConfigured()
                p = s.get(progress_url, timeout=TIMEOUT)
                p.raise_for_status()
                data = p.json()
                return {"chapter": str(data.get(ch_key, "غير معروف")), "diamonds": int(data.get(dm_key, 0)), "demo": False}

    except LoginFailed:
        raise
    except NotConfigured:
        raise
    except (requests.RequestException, KeyError, ValueError, TypeError) as e:
        raise QureoUnavailable(type(e).__name__) from None
