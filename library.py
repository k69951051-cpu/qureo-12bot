"""
مخزن الكتب المشترك بين البوت العام وبوت الإدارة.
كل شيء محفوظ داخل مجلد DATA_DIR:
  - library.json : بيانات الكتب
  - files/       : ملفات الـ PDF (فقط في وضع بدون قناة تخزين)
في وضع قناة التخزين (STORAGE_CHANNEL_ID) تُحفظ الكتب كرسائل في القناة.
"""
import copy
import json
import os
import re
import threading
import uuid

DATA_DIR = os.getenv("DATA_DIR", "data")
FILES_DIR = os.path.join(DATA_DIR, "files")
DB_PATH = os.path.join(DATA_DIR, "library.json")

# =========================
# المراحل والصفوف
# =========================

_ORD = ["الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس"]

GRADES = {}
for _i in range(1, 7):
    GRADES[f"p{_i}"] = f"الصف {_ORD[_i - 1]} الابتدائي"
for _i in range(1, 4):
    GRADES[f"m{_i}"] = f"الصف {_ORD[_i - 1]} الإعدادي"
for _i in range(1, 4):
    GRADES[f"s{_i}"] = f"الصف {_ORD[_i - 1]} الثانوي"
GRADES["bac2"] = "تانية بكالوريا"

STAGES = {
    "pri": ("🏫 المرحلة الابتدائية", [f"p{i}" for i in range(1, 7)]),
    "prep": ("🏫 المرحلة الإعدادية", [f"m{i}" for i in range(1, 4)]),
    "sec": ("🏫 المرحلة الثانوية", [f"s{i}" for i in range(1, 4)]),
    "bac": ("🎓 البكالوريا", ["bac2"]),
}

TERMS = {1: "الترم الأول", 2: "الترم الثاني", 0: "سنوي (الترمين)"}

# المواد الشائعة (يمكن للأدمن كتابة مادة أخرى)
SUBJECTS = [
    "اللغة العربية", "اللغة الإنجليزية", "اللغة الفرنسية", "اللغة الألمانية",
    "الرياضيات", "العلوم", "الدراسات الاجتماعية", "التاريخ", "التاريخ الوطني",
    "الجغرافيا", "الفيزياء", "الكيمياء", "الأحياء", "الجيولوجيا",
    "الفلسفة والمنطق", "علم النفس والاجتماع", "التربية الدينية", "الحاسب الآلي",
]


def stage_of(grade):
    for key, (_, grades) in STAGES.items():
        if grade in grades:
            return key
    return None


# =========================
# التخزين
# =========================

_lock = threading.RLock()
_DEFAULT = {"books": [], "next_id": 1}


def _load():
    os.makedirs(FILES_DIR, exist_ok=True)
    if not os.path.exists(DB_PATH):
        return copy.deepcopy(_DEFAULT)
    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)
    db.setdefault("books", [])
    db.setdefault("next_id", 1)
    for b in db["books"]:
        if b.get("grade") == "g1":  # ترحيل من النسخة القديمة (أولى ثانوي)
            b["grade"] = "s1"
        b.setdefault("term", 0)
    return db


def _save(db):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_PATH)


def add_book(grade, term, subject, title, file_name=None, url=None, channel_id=None, message_id=None):
    with _lock:
        db = _load()
        book = {
            "id": db["next_id"],
            "grade": grade,
            "term": term,
            "subject": subject,
            "title": title,
            "file": file_name,
            "url": url,
            "channel_id": channel_id,
            "message_id": message_id,
            "public_file_id": None,
        }
        db["next_id"] += 1
        db["books"].append(book)
        _save(db)
        return book


def _term_match(book_term, term):
    # الكتاب السنوي (0) يظهر في الترمين
    return term is None or book_term in (term, 0)


def books_for(grade, term, subject):
    with _lock:
        return [
            b for b in _load()["books"]
            if b["grade"] == grade and b["subject"] == subject and _term_match(b["term"], term)
        ]


def subjects_in(grade, term):
    with _lock:
        names = {
            b["subject"] for b in _load()["books"]
            if b["grade"] == grade and _term_match(b["term"], term)
        }
    return sorted(names)


def count_books(grade, term=None):
    with _lock:
        return sum(
            1 for b in _load()["books"]
            if b["grade"] == grade and _term_match(b["term"], term)
        )


def all_books():
    with _lock:
        return list(_load()["books"])


def get_book(book_id):
    with _lock:
        for b in _load()["books"]:
            if b["id"] == book_id:
                return b
    return None


def set_public_file_id(book_id, file_id):
    with _lock:
        db = _load()
        for b in db["books"]:
            if b["id"] == book_id:
                b["public_file_id"] = file_id
        _save(db)


def delete_book(book_id):
    with _lock:
        db = _load()
        removed = [b for b in db["books"] if b["id"] == book_id]
        db["books"] = [b for b in db["books"] if b["id"] != book_id]
        _save(db)
    for b in removed:
        if b.get("file"):
            try:
                os.remove(os.path.join(FILES_DIR, b["file"]))
            except OSError:
                pass
    return bool(removed)


# =========================
# الملفات (وضع بدون قناة)
# =========================

def save_file(data: bytes, original_name: str) -> str:
    os.makedirs(FILES_DIR, exist_ok=True)
    base = os.path.basename(original_name or "book.pdf")
    base = re.sub(r"[^\w.\-]", "_", base)
    stored = f"{uuid.uuid4().hex[:8]}_{base}"
    with open(os.path.join(FILES_DIR, stored), "wb") as f:
        f.write(data)
    return stored


def file_path(stored_name: str) -> str:
    return os.path.join(FILES_DIR, os.path.basename(stored_name))
