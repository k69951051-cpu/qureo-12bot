import requests
import logging

logger = logging.getLogger(__name__)

def fetch_progress(username, password):
    """
    دالة ذكية للاتصال بمنصة Qureo / Sprix Learning Square مع تجربة عدة روابط وحقول مختلفة لضمان تسجيل الدخول بنجاح.
    """
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })

    # الروابط المحتملة لتسجيل الدخول في المنصة التعليمية
    login_urls = [
        "https://egy.app.spx-learning-square.com/login",
        "https://egy.app.spx-learning-square.com/api/login",
        "https://me-portal.qureo.education/oauth2/password-login",
        "https://me-portal.qureo.education/api/login"
    ]

    # الأشكال المحتملة لأسماء حقول بيانات الدخول
    payload_variants = [
        {"student_id": username, "password": password},
        {"username": username, "password": password},
        {"login_id": username, "password": password},
        {"code": username, "password": password}
    ]

    success = False
    data = {}

    for url in login_urls:
        for payload in payload_variants:
            try:
                base_origin = url.rsplit("/", 1)[0]
                session.headers.update({"Origin": base_origin, "Referer": url})
                
                response = session.post(url, json=payload, timeout=10, allow_redirects=True)
                
                if response.status_code == 200:
                    try:
                        res_json = response.json()
                        if res_json:
                            data = res_json
                            success = True
                            break
                    except:
                        if session.cookies:
                            success = True
                            break
                elif response.status_code in (400, 401, 403):
                    continue
            except Exception as e:
                logger.debug(f"Attempt failed for {url}: {e}")
                continue
        if success:
            break

    if not success:
        raise Exception("بيانات الدخول غير صحيحة أو أن المنصة تواجه ضغطاً حالياً. تأكد من كود الطالب وكلمة المرور.")

    # استخراج التقدم ورصيد الدايموند بمرونة عالية
    progress_data = {
        "chapter": data.get("current_chapter", data.get("chapter_name", data.get("chapter", "الفصل الأول"))),
        "diamonds": data.get("diamonds", data.get("gems", data.get("balance", 0)))
    }

    return progress_data
