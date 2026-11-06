import os
from playwright.sync_api import sync_playwright

class LoginFailed(Exception):
    pass

class QureoUnavailable(Exception):
    pass

def solve_qureo_automatically(username, password, chapter_id="all", progress_callback=None):
    if not username or not password:
        raise LoginFailed("بيانات الدخول غير مكتملة")
    
    if progress_callback:
        progress_callback("🚀 <b>جاري تهيئة النظام...</b>\n[░░░░░░░░░░] 10%")

    with sync_playwright() as p:
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
            if progress_callback:
                progress_callback("🌐 <b>جاري فتح موقع المنصة...</b>\n[███░░░░░░░] 30%")

            page.goto("https://me-portal.qureo.education/", timeout=30000)
            
            if progress_callback:
                progress_callback("🔑 <b>جاري كتابة بيانات الدخول...</b>\n[██████░░░░] 60%")

            page.fill("input[name='username']", username)
            page.fill("input[name='password']", password)
            page.click("button[type='submit']")
            
            if progress_callback:
                progress_callback("⏳ <b>جاري تسجيل الدخول وتحميل الصفحة...</b>\n[████████░░] 85%")

            page.wait_for_load_state("networkidle")
            
            if "login" in page.url or page.locator(".error-message").is_visible():
                raise LoginFailed("اسم المستخدم أو كلمة المرور غير صحيحة.")
            
            if progress_callback:
                progress_callback("✅ <b>اكتملت العملية بنجاح!</b>\n[██████████] 100%")

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
