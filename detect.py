"""
التعرف التلقائي على الصف والترم والمادة من اسم الملف أو وصفه (caption).
يعتمد على كلمات مفتاحية عربية وإنجليزية، وأي شيء لا يتعرف عليه يرجع None
ليسأل بوت الإدارة عنه بالأزرار.
"""
import re

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_DIACRITICS = re.compile("[ً-ٰٟـ]")
_LETTERS = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه",
    "ئ": "", "ؤ": "", "ء": "",
})

_ORDINALS = {
    "اول": 1, "اولي": 1, "1": 1,
    "تاني": 2, "ثاني": 2, "ثانيه": 2, "تانيه": 2, "2": 2,
    "ثالث": 3, "تالت": 3, "ثالثه": 3, "تالته": 3, "3": 3,
    "رابع": 4, "رابعه": 4, "4": 4,
    "خامس": 5, "خامسه": 5, "5": 5,
    "سادس": 6, "سادسه": 6, "6": 6,
}
_MAX_GRADE = {"pri": 6, "prep": 3, "sec": 3}
_PREFIX = {"pri": "p", "prep": "m", "sec": "s"}


def normalize(text):
    t = (text or "").lower().translate(_AR_DIGITS)
    t = _DIACRITICS.sub("", t)
    t = t.translate(_LETTERS)
    t = re.sub(r"[_\-.()\[\]{}،,:;/\\|]+", " ", t)
    return t


def tokenize(text):
    out = []
    for w in re.findall(r"\w+", normalize(text), re.UNICODE):
        if w.startswith("ال") and len(w) > 4:
            w = w[2:]
        out.append(w)
    return out


# ---------- الصف ----------

def _stage(tok):
    if tok.startswith("ابتدا"):
        return "pri"
    if tok.startswith("اعداد"):
        return "prep"
    if tok.startswith("ثانو"):
        return "sec"
    if tok.startswith("بكالوريا"):
        return "bac"
    return None


def _detect_grade(toks):
    ords = [(i, _ORDINALS[t]) for i, t in enumerate(toks) if t in _ORDINALS]
    for pos, tok in enumerate(toks):
        stage = _stage(tok)
        if not stage:
            continue
        near = sorted((abs(i - pos), i, n) for i, n in ords if abs(i - pos) <= 3)
        n = near[0][2] if near else None
        if stage == "bac":
            return "bac2" if n in (None, 2) else None
        if n and n <= _MAX_GRADE[stage]:
            return f"{_PREFIX[stage]}{n}"
        return None
    return None


# ---------- الترم ----------

_TERM_RE = re.compile(
    r"(?:\bترم|فصل دراسي|\bterm|\bsemester)\s*(اول|اولي|1|تاني|ثاني|2|one|two|first|second)\b"
)
_TERM_RE2 = re.compile(r"\b(1st|2nd|first|second)\s*(?:term|semester)\b")
_ANNUAL_RE = re.compile(r"\bترمين\b|\bسنوي\b|\bسنويه\b|\bannual\b|\bfull year\b")


def _detect_term(toks):
    joined = " ".join(toks)
    m = _TERM_RE.search(joined) or _TERM_RE2.search(joined)
    if m:
        return 1 if m.group(1) in ("اول", "اولي", "1", "one", "first", "1st") else 2
    if _ANNUAL_RE.search(joined):
        return 0
    return None


# ---------- المادة ----------

# (اسم المادة، الكلمات المفتاحية) بترتيب الأولوية عند تساوي الموضع
_SUBJECT_RULES = [
    ("التاريخ الوطني", []),  # يُعالج بشكل خاص (تاريخ + وطني)
    ("اللغة العربية", ["عربي", "عربيه", "نحو", "بلاغه", "arabic"]),
    ("اللغة الإنجليزية", ["انجليزي", "انجليزيه", "انجلش", "english"]),
    ("اللغة الفرنسية", ["فرنسي", "فرنسيه", "فرنساوي", "french"]),
    ("اللغة الألمانية", ["الماني", "المانيه", "german"]),
    ("الرياضيات", ["رياضيات", "math", "maths", "جبر", "هندسه", "تفاضل", "تكامل",
                   "احصاء", "ميكانيكا", "استاتيكا", "ديناميكا"]),
    ("الفيزياء", ["فيزياء", "فيزيا", "physics"]),
    ("الكيمياء", ["كيمياء", "كيميا", "chemistry"]),
    ("الأحياء", ["احياء", "بيولوجي", "biology"]),
    ("الجيولوجيا", ["جيولوجيا", "جيولوجي", "geology"]),
    ("العلوم", ["علوم", "science"]),
    ("الدراسات الاجتماعية", ["دراسات"]),
    ("التاريخ", ["تاريخ", "history"]),
    ("الجغرافيا", ["جغرافيا", "جغرافيه", "geography"]),
    ("الفلسفة والمنطق", ["فلسفه", "منطق"]),
    ("علم النفس والاجتماع", ["نفس", "اجتماع", "واجتماع"]),
    ("التربية الدينية", ["دين", "ديني", "دينيه", "اسلاميه", "اسلامي", "مسيحيه", "مسيحي"]),
    ("الحاسب الآلي", ["حاسب", "كمبيوتر", "computer"]),
]


# نطبّق نفس التطبيع على الكلمات المفتاحية (مثلاً حذف الهمزة) حتى تتطابق مع النص بعد تطبيعه
_SUBJECT_RULES = [(name, [normalize(s) for s in stems]) for name, stems in _SUBJECT_RULES]


def _match(tok, stem):
    return tok == stem or (len(stem) >= 5 and tok.startswith(stem))


def _detect_subject(toks):
    best = None  # (موضع، ترتيب القاعدة، الاسم)
    for i, tok in enumerate(toks):
        if tok == "تاريخ" and "وطني" in toks[i + 1:i + 3]:
            cand = (i, 0, "التاريخ الوطني")
            best = min(best, cand) if best else cand
            continue
        for rank, (name, stems) in enumerate(_SUBJECT_RULES):
            if any(_match(tok, s) for s in stems):
                cand = (i, rank, name)
                best = min(best, cand) if best else cand
                break
    return best[2] if best else None


def detect(text):
    """يرجع {"grade": مفتاح الصف أو None, "term": 0/1/2 أو None, "subject": اسم المادة أو None}"""
    toks = tokenize(text)
    return {
        "grade": _detect_grade(toks),
        "term": _detect_term(toks),
        "subject": _detect_subject(toks),
    }
