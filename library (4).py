"""
مخزن الكتب المشترك بين البوت العام وبوت الإدارة.
كل شيء محفوظ داخل مجلد DATA_DIR:
  - library.json : بيانات الكتب + المجموعات المربوطة + طابور المراجعة
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

# =========================
# المسارات (التخصصات)
# =========================

# المسارات المتاحة لكل صف (الصفوف الأخرى بدون مسارات)
GRADE_TRACKS = {
    "bac2": ["med", "eng", "art", "biz"],
    "s3": ["lit", "sci"],
}
# مسارات فرعية: علمي ← علوم / رياضة
TRACK_CHILDREN = {"sci": ["sci_bio", "sci_math"]}
TRACK_PARENT = {child: parent for parent, kids in TRACK_CHILDREN.items() for child in kids}

# الاسم الكامل (يظهر في الملخصات والعناوين)
TRACK_LABELS = {
    "med": "مسار الطب وعلوم الحياة",
    "eng": "مسار الهندسة",
    "art": "مسار الآداب والفنون",
    "biz": "مسار إدارة الأعمال",
    "lit": "أدبي",
    "sci": "علمي",
    "sci_bio": "علمي علوم",
    "sci_math": "علمي رياضة",
}
# نص الزر في البوت العام
TRACK_BUTTONS = {
    "med": "🩺 مسار الطب وعلوم الحياة",
    "eng": "⚙️ مسار الهندسة",
    "art": "🎨 مسار الآداب والفنون",
    "biz": "💼 مسار إدارة الأعمال",
    "lit": "📖 أدبي",
    "sci": "🔬 علمي",
    "sci_bio": "🧬 علوم",
    "sci_math": "📐 رياضة",
}

# المواد الشائعة (يمكن للأدمن كتابة مادة أخرى)
SUBJECTS = [
    "اللغة العربية", "اللغة الإنجليزية", "اللغة الفرنسية", "اللغة الألمانية",
    "الرياضيات", "العلوم", "الدراسات الاجتماعية", "التاريخ", "التاريخ الوطني",
    "الجغرافيا", "الفيزياء", "الكيمياء", "الأحياء", "الجيولوجيا",
    "الفلسفة والمنطق", "علم النفس والاجتماع", "التربية الدينية", "الحاسب الآلي",
    "المحاسبة", "الاقتصاد", "البرمجة", "إدارة الأعمال",
]


# مواد تانية بكالوريا: مواد مشتركة في كل المسارات + مادتان اختياريتان لكل مسار (يختار الطالب واحدة)
# كل عنصر: (الاسم الظاهر للطالب، أسماء المواد المخزنة تحته)
BAC_COMMON = [
    ("التاريخ الوطني", ["التاريخ الوطني"]),
    ("اللغة الإنجليزية", ["اللغة الإنجليزية"]),
    ("اللغة العربية", ["اللغة العربية"]),
]
BAC_ELECTIVES = {
    "med": [("الفيزياء", ["الفيزياء"]), ("الرياضيات", ["الرياضيات"])],
    "eng": [("الكيمياء", ["الكيمياء"]), ("البرمجة", ["البرمجة"])],
    "art": [
        ("علم النفس والاجتماع", ["علم النفس والاجتماع"]),
        ("لغة ثانية (فرنسي/ألماني)", ["اللغة الفرنسية", "اللغة الألمانية", "اللغة الثانية"]),
    ],
    "biz": [
        ("الحاسبات", ["الحاسب الآلي", "الحاسبات"]),
        ("إدارة الأعمال", ["إدارة الأعمال", "المحاسبة", "الاقتصاد"]),
    ],
}


def stage_of(grade):
    for key, (_, grades) in STAGES.items():
        if grade in grades:
            return key
    return None


def tracks_for_grade(grade):
    """كل المسارات التي يمكن اختيارها لهذا الصف (الرئيسية والفرعية)."""
    out = []
    for t in GRADE_TRACKS.get(grade, []):
        out.append(t)
        out.extend(TRACK_CHILDREN.get(t, []))
    return out


def track_visible(book_track, view_track):
    """
    هل يظهر كتاب مساره book_track لطالب يتصفح المسار view_track؟
    - view_track = None: بدون تصفية (يظهر كل شيء)
    - كتاب بدون مسار (None) = مشترك لكل المسارات
    - كتاب "علمي" يظهر في علمي علوم وعلمي رياضة، والعكس عند عرض "علمي"
    """
    if view_track is None or book_track is None:
        return True
    return (
        book_track == view_track
        or TRACK_PARENT.get(view_track) == book_track
        or TRACK_PARENT.get(book_track) == view_track
    )


# =========================
# التخزين
# =========================

_lock = threading.RLock()
_DEFAULT = {"books": [], "next_id": 1, "groups": [], "review": []}


def _load():
    os.makedirs(FILES_DIR, exist_ok=True)
    if not os.path.exists(DB_PATH):
        return copy.deepcopy(_DEFAULT)
    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)
    db.setdefault("books", [])
    db.setdefault("next_id", 1)
    db.setdefault("groups", [])
    db.setdefault("review", [])
    for b in db["books"]:
        if b.get("grade") == "g1":  # ترحيل من النسخة القديمة (أولى ثانوي)
            b["grade"] = "s1"
        b.setdefault("term", 0)
        b.setdefault("track", None)
        b.setdefault("file_unique_id", None)
    return db


def _save(db):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_PATH)


def _new_book(db, f):
    book = {
        "id": db["next_id"],
        "grade": f["grade"],
        "term": f["term"],
        "subject": f["subject"],
        "title": f["title"],
        "track": f.get("track"),
        "file": f.get("file_name"),
        "url": f.get("url"),
        "channel_id": f.get("channel_id"),
        "message_id": f.get("message_id"),
        "public_file_id": None,
        "file_unique_id": f.get("file_unique_id"),
    }
    db["next_id"] += 1
    db["books"].append(book)
    return book


def add_book(grade, term, subject, title, file_name=None, url=None, channel_id=None,
             message_id=None, track=None, file_unique_id=None):
    with _lock:
        db = _load()
        book = _new_book(db, {
            "grade": grade, "term": term, "subject": subject, "title": title,
            "track": track, "file_name": file_name, "url": url,
            "channel_id": channel_id, "message_id": message_id,
            "file_unique_id": file_unique_id,
        })
        _save(db)
        return book


def add_many(items):
    """
    إضافة عدد كبير من الكتب بعملية حفظ واحدة (أسرع بكثير من add_book في حلقة).
    كل عنصر قاموس بمفاتيح: grade, term, subject, title, track, file_name, url,
    channel_id, message_id, file_unique_id
    """
    with _lock:
        db = _load()
        books = [_new_book(db, it) for it in items]
        _save(db)
        return books


def is_known(unique_id):
    """هل هذا الملف/الرابط موجود في المكتبة أو في طابور المراجعة؟ (لمنع التكرار)"""
    if not unique_id:
        return False
    with _lock:
        db = _load()
        return (
            any(b.get("file_unique_id") == unique_id for b in db["books"])
            or any(r.get("unique_id") == unique_id for r in db["review"])
        )


def _term_match(book_term, term):
    # الكتاب السنوي (0) يظهر في الترمين
    return term is None or book_term in (term, 0)


def books_for(grade, term, subject, track=None):
    with _lock:
        return [
            b for b in _load()["books"]
            if b["grade"] == grade and b["subject"] == subject
            and _term_match(b["term"], term) and track_visible(b.get("track"), track)
        ]


def subjects_in(grade, term, track=None):
    with _lock:
        names = {
            b["subject"] for b in _load()["books"]
            if b["grade"] == grade and _term_match(b["term"], term)
            and track_visible(b.get("track"), track)
        }
    return sorted(names)


def subject_entries(grade, term, track=None):
    """
    المواد التي تظهر للطالب. في مسارات تانية بكالوريا تظهر القائمة الثابتة (المشتركة ثم الاختيارية)
    حتى لو لم تُرفع كتبها بعد، وأي مادة أخرى عليها كتب تظهر تحت "مواد أخرى".
    غير ذلك: المواد التي عليها كتب فقط.
    كل عنصر: {"label", "subjects", "elective"}
    """
    present = set(subjects_in(grade, term, track))
    if grade == "bac2" and track in BAC_ELECTIVES:
        entries = [{"label": l, "subjects": subs, "elective": False} for l, subs in BAC_COMMON]
        entries += [{"label": l, "subjects": subs, "elective": True} for l, subs in BAC_ELECTIVES[track]]
        covered = {x for e in entries for x in e["subjects"]}
        other = sorted(present - covered)
        if other:
            entries.append({"label": "مواد أخرى", "subjects": other, "elective": False})
        return entries
    return [{"label": n, "subjects": [n], "elective": False} for n in sorted(present)]


def books_for_subjects(grade, term, subjects, track=None):
    names = set(subjects)
    with _lock:
        return [
            b for b in _load()["books"]
            if b["grade"] == grade and b["subject"] in names
            and _term_match(b["term"], term) and track_visible(b.get("track"), track)
        ]


def count_books(grade, term=None, track=None):
    with _lock:
        return sum(
            1 for b in _load()["books"]
            if b["grade"] == grade and _term_match(b["term"], term)
            and track_visible(b.get("track"), track)
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


def _remove_files(removed):
    for b in removed:
        if b.get("file"):
            try:
                os.remove(os.path.join(FILES_DIR, b["file"]))
            except OSError:
                pass


def delete_many(ids):
    """يحذف عدة كتب بعملية واحدة ويرجع قائمة الكتب المحذوفة."""
    ids = set(ids)
    with _lock:
        db = _load()
        removed = [b for b in db["books"] if b["id"] in ids]
        db["books"] = [b for b in db["books"] if b["id"] not in ids]
        _save(db)
    _remove_files(removed)
    return removed


def delete_book(book_id):
    return bool(delete_many([book_id]))


# =========================
# المجموعات المربوطة (يضيف منها البوت الكتب تلقائياً)
# =========================

def link_group(chat_id):
    with _lock:
        db = _load()
        if chat_id not in db["groups"]:
            db["groups"].append(chat_id)
            _save(db)


def unlink_group(chat_id):
    with _lock:
        db = _load()
        if chat_id in db["groups"]:
            db["groups"].remove(chat_id)
            _save(db)
            return True
    return False


def is_linked_group(chat_id):
    with _lock:
        return chat_id in _load()["groups"]


# =========================
# طابور المراجعة (ملفات لم يتعرف البوت على بياناتها كاملة)
# =========================

def review_add(item):
    with _lock:
        db = _load()
        db["review"].append(item)
        _save(db)


def review_peek():
    with _lock:
        review = _load()["review"]
        return copy.deepcopy(review[0]) if review else None


def review_remove(unique_id):
    with _lock:
        db = _load()
        before = len(db["review"])
        db["review"] = [r for r in db["review"] if r.get("unique_id") != unique_id]
        if len(db["review"]) != before:
            _save(db)


def review_size():
    with _lock:
        return len(_load()["review"])


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
