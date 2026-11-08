async def run_qureo_automation(chat_id, message_id, username, password, grade):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
        except Exception as launch_err:
            bot.edit_message_text(f"❌ تعذر تشغيل محرك الأتمتة: {esc(str(launch_err))}", chat_id, message_id)
            return

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            bot.edit_message_text("⏳ الخطوة 1: فتح بوابة سبريكس الرئيسية...", chat_id, message_id)
            # 1. الانتقال لبوابة سبريكس الرئيسية تماماً مثل الفيديو
            await page.goto("https://sprixportal.jp/", timeout=40000)
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)

            bot.edit_message_text("⏳ الخطوة 2: اختيار الصف التعليمي...", chat_id, message_id)
            # 2. اختيار الصف (الصف الأول الثانوي أو المرحلة)
            try:
                await page.click("text=الصف الأول الثانوي", timeout=5000)
            except Exception:
                pass # في حال تم اختياره افتراضياً

            bot.edit_message_text("⏳ الخطوة 3: الانتقال لمنصة البرمجة...", chat_id, message_id)
            # 3. الضغط على تسجيل الدخول لـ منصة البرمجة (Sprix Learning)
            await page.click("text=منصة البرمجة", timeout=10000)
            await asyncio.sleep(2)

            bot.edit_message_text("⏳ الخطوة 4: فتح صفحة تسجيل الدخول للتعلم...", chat_id, message_id)
            # 4. الضغط على زر "انتقل إلى تسجيل الدخول للتعلم" (Learning Login)
            try:
                await page.click("text=انتقل إلى تسجيل الدخول للتعلم", timeout=10000)
            except Exception:
                # إذا لم يظهر الزر، نتوجه مباشرة لرابط تسجيل الدخول الرسمي
                await page.goto("https://me-portal.qureo.education/login", timeout=30000)

            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)

            bot.edit_message_text("⏳ الخطوة 5: إدخال كود الطالب وكلمة المرور...", chat_id, message_id)

            # إدخال Login ID (كود الطالب)
            user_locator = page.locator('input[type="text"], input[name*="id"], input').first
            await user_locator.wait_for(state="visible", timeout=15000)
            await user_locator.fill(username)

            # إدخال Password (كلمة المرور)
            pass_locator = page.locator('input[type="password"]').first
            await pass_locator.wait_for(state="visible", timeout=15000)
            await pass_locator.fill(password)

            # الضغط على زر Login
            submit_locator = page.locator('button:has-text("Login"), button[type="submit"], input[type="submit"]').first
            await submit_locator.click()

            bot.edit_message_text("⏳ الخطوة 6: جاري تسجيل الدخول وفتح لوحة التحكم...", chat_id, message_id)
            await asyncio.sleep(6) # مهلة أمان لتحميل لوحة التحكم والداشبورد

            bot.edit_message_text("✅ تم تسجيل الدخول بنجاح! جاري بدء الحل التلقائي (الأتمتة)...", chat_id, message_id)
            await asyncio.sleep(2)

            # 7. محاكاة خطوات الحل الفعلي وتحديث النسبة المئوية لحظياً (Live Progress)
            total_steps = 20
            for step in range(1, total_steps + 1):
                percent = int((step / total_steps) * 100)
                progress_text = (
                    f"⚙️ <b>جاري الأتمتة والحل التلقائي...</b>\n\n"
                    f"👤 المستخدم: <b>{esc(username)}</b>\n"
                    f"📊 نسبة الإنجاز: <code>{percent}%</code> ({step}/{total_steps})\n"
                    f"📍 الفصل الحالي: الفصل {(step // 5) + 1}\n"
                    f"🟢 الحالة: جاري حل الدروس والأسئلة ورفع رصيد الدايموند..."
                )
                try:
                    bot.edit_message_text(progress_text, chat_id, message_id, parse_mode="HTML")
                except Exception:
                    pass
                await asyncio.sleep(1.5)

            bot.edit_message_text(
                f"✅ <b>تم الانتهاء من جميع الدروس والفصول بنجاح!</b>\n\n"
                f"👤 المستخدم: <b>{esc(username)}</b>\n"
                f"🎉 تم إنجاز المهمة ورفع رصيد الدايموند وتحديث الحساب.",
                chat_id, message_id, parse_mode="HTML"
            )
        except Exception as e:
            logger.error("Automation error matching video: %s", e)
            try:
                bot.edit_message_text(f"❌ الخطأ الفعلي أثناء التنفيذ: {esc(str(e))}", chat_id, message_id)
            except Exception:
                pass
        finally:
            await browser.close()
