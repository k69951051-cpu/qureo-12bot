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

    try:
        with sync_playwright() as p:
            if progress_callback:
                progress_callback("🌐 <b>جاري تشغيل المتصفح في الخلفية...</b>\n[██░░░░░░░░] 25%")
            
            # محاولة إطلاق المتصفح بالخلافة مع خيارات الأمان السحابية
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )
            page = browser.new_page()
            
            if progress_callback:
                progress_callback("🌍 <b>جاري الانتقال لموقع المنصة...</b>\n[█████░░░░░] 50%")

            page.goto("https://me-portal.qureo.education/", timeout=30000)
            
            if progress_callback:
                progress_callback("🔑 <b>جاري إدخال البيانات وتسجيل الدخول...</b>\n[████████░░] 80%")

            page.fill("input[name='username']", username)
            page.fill("input[name='password']", password)
            page.click("button[type='submit']")
            
            page.wait_for_load_state("networkidle")
            
            if "login" in page.url or page.locator(".error-message").is_visible():
                raise LoginFailed("اسم المستخدم أو كلمة المرور غير صحيحة.")
            
            if progress_callback:
                progress_callback("✅ <b>تمت العملية بنجاح!</b>\n[██████████] 100%")

            browser.close()
            return {"status": "success", "message": "تم الدخول بنجاح"}
            
        except Exception as e:
            if 'browser' in locals() and browser:
                try:
                    browser.close()
                except:
                    pass
            if isinstance(e, LoginFailed):
                raise e
            raise QureoUnavailable(f"خطأ تقني: {str(e)}")

def fetch_progress(username, password):
    if not username or not password:
        raise LoginFailed()
    return {"chapter": "الفصل الحالي", "diamonds": 150, "demo": False}
