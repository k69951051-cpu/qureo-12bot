# --- تدفق تفاعلي لمنصات Qureo / Sprix (مشابه للفيديو) ---

# هيكل تخزين حالة الطالب المؤقتة في الذاكرة
qureo_wizard = {}  # chat_id -> {grade, education_type, course_type, scope, username, step}

def qureo_grade_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("الصف الثاني الثانوي", callback_data="qrs:s2"),
        InlineKeyboardButton("الصف الأول الثانوي", callback_data="qrs:s1"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="menu"),
    )
    return markup

def qureo_education_type_menu(grade_key):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📚 التعليم العام", callback_data=f"qred:{grade_key}:general"),
        InlineKeyboardButton("🕌 الأزهر الشريف", callback_data=f"qred:{grade_key}:azhar"),
        InlineKeyboardButton("⚙️ التعليم الفني", callback_data=f"qred:{grade_key}:technical"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="qr"),
    )
    return markup

def qureo_course_menu(state_key):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💻 البرمجة وتكنولوجيا المعلومات", callback_data="qrc:programming"),
        InlineKeyboardButton("💰 الثقافة المالية (Sprix)", callback_data="qrc:financial"),
        InlineKeyboardButton("⬅️ رجوع", callback_data="qr"),
    )
    return markup

def qureo_scope_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📌 فصل واحد", callback_data="qrs_one"),
        InlineKeyboardButton("📚 كل الفصول", callback_data="qrs_all"),
        InlineKeyboardButton("📑 عدة فصول", callback_data="qrs_some"),
        InlineKeyboardButton("❌ إلغاء", callback_data="qx"),
    )
    return markup

def qureo_confirm_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ ابدأ", callback_data="qr_start_action"),
        InlineKeyboardButton("❌ إلغاء", callback_data="qx"),
    )
    return markup
