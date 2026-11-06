"""
مخزن الكتب المشترك بين البوت العام وبوت الإدارة.
كل شيء محفوظ داخل مجلد DATA_DIR:
  - library.json : بيانات المواد والكتب
  - files/       : ملفات الـ PDF المرفوعة
على Railway اربط Volume على المسار /data واضبط DATA_DIR=/data حتى لا تضيع الملفات عند إعادة النشر.
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

# الصفوف (يمكنك إضافة صف جديد هنا)
GRADES = {
    "g1": "🎓 أولى ثانوي",
    "bac2": "🎓 تانية بكالوريا",
}

_DEFAULT = {
    "subjects": {
        "g1": [],
        "bac2": ["التاريخ الوطني", "اللغة العربية"],
    },
    "books": [],
    "next_id": 1,
}

_lock = threading.RLock()


def _load():
    os.makedirs(FILES_DIR, exist_ok=True)
    if not os.path.exists(DB_PATH):
        return copy.deepcopy(_DEFAULT)
    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)
    for key in GRADES:
        db.setdefault("subjects", {}).setdefault(key, [])
    return db


def _save(db):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_PATH)


# ---------- المواد ----------

def subjects(grade):
    with _lock:
        return list(_load()["subjects"].get(grade, []))


def add_subject(grade, name):
    name = name.strip()
    with _lock:
        db = _load()
        if name and name not in db["subjects"][grade]:
            db["subjects"][grade].append(name)
            _save(db)
    return name


# ---------- الكتب ----------

def add_book(grade, subject, title, file_name=None, url=None, channel_id=None, message_id=None):
    with _lock:
        db = _load()
        book = {
            "id": db["next_id"],
            "grade": grade,
            "subject": subject,
            "title": title,
            "file": file_name,
            "url": url,
            # وضع قناة التخزين: الملف محفوظ كرسالة في قناة خاصة ويُنسخ للطالب بدون حد للحجم
            "channel_id": channel_id,
            "message_id": message_id,
            "public_file_id": None,  # يُحفظ بعد أول إرسال من البوت العام لتسريع الإرسال
        }
        db["next_id"] += 1
        db["books"].append(book)
        _save(db)
        return book


def books_for(grade, subject):
    with _lock:
        return [b for b in _load()["books"] if b["grade"] == grade and b["subject"] == subject]


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


# ---------- الملفات ----------

def save_file(data: bytes, original_name: str) -> str:
    """يحفظ الملف باسم آمن وفريد ويرجع اسمه المخزن."""
    os.makedirs(FILES_DIR, exist_ok=True)
    base = os.path.basename(original_name or "book.pdf")
    base = re.sub(r"[^\w.\-]", "_", base)
    stored = f"{uuid.uuid4().hex[:8]}_{base}"
    with open(os.path.join(FILES_DIR, stored), "wb") as f:
        f.write(data)
    return stored


def file_path(stored_name: str) -> str:
    return os.path.join(FILES_DIR, os.path.basename(stored_name))
