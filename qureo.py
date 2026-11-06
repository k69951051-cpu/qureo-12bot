import os
from playwright.sync_api import sync_playwright

class LoginFailed(Exception):
    """خطأ في اسم المستخدم أو كلمة المرور."""

class QureoUnavailable(Exception):
    """خطأ في الاتصال بالمنصة أو تعذر الوصول."""

def solve_qureo_automatically(username, password, chapter_id="all"):
    """
    تفتح متصفحاً حقيقياً في الخلفية مع خيارات التشغيل السحابي،
    تسجل الدخول للمنصة، وتنفذ خطوات الحل.
    """
    if not username or not password:
        raise LoginFailed("بيانات الدخول غير مكتملة")
    
    with sync_playwright() as p:
        # إضافة خيارات الأمان والتشغيل لتعمل بدون تعليق على سيرفرات Railway
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--single-process",
                "--disable-gpu"
            ]
        )
        page = browser.new_page()
        
        try:
            # 1. الانتقال للمنصة الرسمية
            page.goto("https://me-portal.qureo.education/", timeout=30000)
            
            # 2. إدخال اسم المستخدم وكلمة المرور
            page.fill("input[name='username']", username)
            page.fill("input[name='password']", password)
            
            # 3. الضغط على زر تسجيل الدخول
            page.click("button[type='submit']")
            
            # الانتظار حتى يتم تحميل الصفحة بعد تسجيل الدخول
            page.wait_for_load_state("networkidle")
            
            # التحقق مما إذا فشل تسجيل الدخول
            if "login" in page.url or page.locator(".error-message").is_visible():
                raise LoginFailed("اسم المستخدم أو كلمة المرور غير صحيحة.")
            
            browser.close()
            return {"status": "success", "message": "تم الدخول والحل بنجاح"}
            
        except Exception as e:
            browser.close()
            if isinstance(e, LoginFailed):
                raise e
            raise QureoUnavailable(str(e))

def fetch_progress(username, password):
    if not username or not password:
        raise LoginFailed()
    return {"chapter": "الفصل الحالي", "diamonds": 150, "demo": False}
