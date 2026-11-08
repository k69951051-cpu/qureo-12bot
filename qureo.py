import requests
import logging

logger = logging.getLogger(__name__)

LOGIN_URL = "https://me-portal.qureo.education/oauth2/password-login"

def fetch_progress(username, password):
    """
    الدالة المسؤولة عن تسجيل الدخول عبر الـ API وجلب بيانات التقدم ورصيد الدايموند للطالب.
    """
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://me-portal.qureo.education",
        "Referer": "https://me-portal.qureo.education/login",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })
    
    try:
        # إرسال طلب تسجيل الدخول باليوزر والباسورد
        payload = {
            "student_id": username,
            "password": password
        }
        
        response = session.post(LOGIN_URL, json=payload, timeout=15)
        
        if response.status_code in (400, 401, 403):
            raise Exception("بيانات الدخول غير صحيحة.")
        
        if response.status_code != 200:
            raise Exception(f"خطأ في الاتصال بالمنصة (كود: {response.status_code})")
            
        data = response.json()
        
        # استخراج البيانات المطلوبة مع قيم افتراضية آمنة
        progress_data = {
            "chapter": data.get("current_chapter", data.get("chapter_name", "الفصل الأول")),
            "diamonds": data.get("diamonds", data.get("gems", 0))
        }
        
        return progress_data
        
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Network error in qureo.py: {req_err}")
        raise Exception("تعذر الاتصال بخوادم المنصة.")
    except Exception as e:
        logger.error(f"Error in qureo.fetch_progress: {e}")
        raise e
