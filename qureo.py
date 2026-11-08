import requests
import logging

logger = logging.getLogger(__name__)

def fetch_progress(username, password):
    """
    دالة تشخيصية متقدمة لتسجيل الدخول ومعرفة الرد الفعلي من سيرفرات المنصة.
    """
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })

    login_urls = [
        "https://egy.app.spx-learning-square.com/login",
        "https://egy.app.spx-learning-square.com/api/login",
        "https://me-portal.qureo.education/oauth2/password-login",
        "https://me-portal.qureo.education/api/login"
    ]

    payload_variants = [
        {"student_id": username, "password": password},
        {"username": username, "password": password},
        {"login_id": username, "password": password},
        {"code": username, "password": password}
    ]

    last_status = None
    last_text = ""

    for url in login_urls:
        for payload in payload_variants:
            try:
                base_origin = url.rsplit("/", 1)[0]
                session.headers.update({"Origin": base_origin, "Referer": url})
                
                response = session.post(url, json=payload, timeout=10, allow_redirects=True)
                last_status = response.status_code
                last_text = response.text[:150] # أول 150 حرف من رد السيرفر
                
                logger.info(f"URL: {url} | Status: {last_status} | Response: {last_text}")

                if response.status_code == 200:
                    try:
                        res_json = response.json()
                        if res_json:
                            return {
                                "chapter": res_json.get("current_chapter", res_json.get("chapter_name", res_json.get("chapter", "الفصل الأول"))),
                                "diamonds": res_json.get("diamonds", res_json.get("gems", res_json.get("balance", 0)))
                            }
                    except:
                        if session.cookies:
                            return {"chapter": "الفصل الأول", "diamonds": 0}
            except Exception as e:
                logger.debug(f"Attempt failed for {url}: {e}")
                continue

    # إرجاع تفاصيل الخطأ الحقيقية لتعرفها فوراً
    raise Exception(f"رفض الدخول (كود: {last_status}). الرد: {last_text}")
