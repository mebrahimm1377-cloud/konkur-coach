"""استخراج متن کتاب‌های درسی (PDF) و ساخت ایندکس جستجوی BM25 برای RAG.

اجرا: python scripts/build_textbook_index.py
خروجی: textbooks/index.json (شامل چانک‌های متن + متادیتا)

کتاب‌ها به‌صورت خودکار از زیرپوشه‌های textbooks/ کشف می‌شن؛ اسم هر زیرپوشه باید در
_SUBJECT_NAMES تعریف شده باشه، و اسم هر فایل PDF باید با یک عدد پایه (۱۰/۱۱/۱۲) تموم بشه
(مثلاً zist-11.pdf یا tarikh-11.pdf).

نکته درباره‌ی ترتیب کلمات: PyMuPDF متن فارسی رو به ترتیب دیداری (visual order) استخراج
می‌کنه نه ترتیب منطقی خواندن؛ برای همین کلمات هر خط رو معکوس می‌کنیم تا جمله‌ها درست
و قابل‌خواندن بشن (تست شده و برای متن خالص فارسی درست کار می‌کنه).

عکس صفحات کتاب اینجا از قبل رندر نمی‌شه (برای صرفه‌جویی در فضای دیسک روی هاست رایگان)؛
هر چانک مسیر نسبی فایل PDF اصلی رو نگه می‌داره تا در صورت نیاز، صفحه‌ی مربوطه به‌صورت
لحظه‌ای (on-demand) با ai/textbook_pages.py رندر بشه.
"""

import json
import re
from pathlib import Path

import fitz

_TEXTBOOKS_DIR = Path(__file__).parent.parent / "textbooks"
_INDEX_PATH = _TEXTBOOKS_DIR / "index.json"
_PAGES_PER_CHUNK = 2

_SUBJECT_NAMES = {
    "biology": "زیست‌شناسی",
    "chemistry": "شیمی",
    "physics": "فیزیک",
    "math": "ریاضی",
    "arabic": "عربی",
    "english": "انگلیسی",
    "lab": "آزمایشگاه علوم تجربی",
}

# فایل‌های داخل persian/ و social/ هرکدوم درس متفاوتی‌ان؛ به‌جای یک اسم کلی برای کل
# پوشه، از پیشوند اسم فایل تشخیص می‌دیم تا رفرنس صفحه‌ها دقیق بمونه.
_FILENAME_PREFIX_SUBJECTS = {
    "farsi": "فارسی",
    "negaresh": "نگارش",
    "dinozendegi": "دین و زندگی",
    "tarikh": "تاریخ معاصر ایران",
    "ensanvamohit": "انسان و محیط‌زیست",
    "jografia": "جغرافیای ایران",
    "zaminshenasi": "زمین‌شناسی",
    "salamat": "سلامت و بهداشت",
    "defa": "آمادگی دفاعی",
    "resane": "تفکر و سواد رسانه‌ای",
    "hoviyat": "هویت اجتماعی",
}

_GRADE_RE = re.compile(r"(1[0-2])(?!.*\d)")


def _subject_for(folder_name: str, file_stem: str) -> str | None:
    """اسم درس را برای یک فایل مشخص برمی‌گرداند (بر اساس پوشه یا پیشوند اسم فایل)."""
    if folder_name in _SUBJECT_NAMES:
        return _SUBJECT_NAMES[folder_name]
    prefix = file_stem.split("-")[0]
    return _FILENAME_PREFIX_SUBJECTS.get(prefix)


def _fix_line_order(line: str) -> str:
    """ترتیب دیداری کلمات یک خط فارسی را به ترتیب منطقی خواندن برمی‌گرداند."""
    words = line.strip().split()
    return " ".join(reversed(words))


def _extract_page_text(page) -> str:
    """متن یک صفحه را استخراج و ترتیب خطوطش را اصلاح می‌کند."""
    raw = page.get_text()
    lines = [_fix_line_order(line) for line in raw.splitlines() if line.strip()]
    return "\n".join(lines)


def _discover_books() -> list[dict]:
    """کتاب‌ها را از روی زیرپوشه‌ها و اسم فایل‌های PDF داخل textbooks/ کشف می‌کند."""
    books = []
    for folder in sorted(_TEXTBOOKS_DIR.iterdir()):
        if not folder.is_dir():
            continue

        for pdf_path in sorted(folder.glob("*.pdf")):
            subject = _subject_for(folder.name, pdf_path.stem)
            if subject is None:
                print(f"درس ناشناخته (رد شد): {pdf_path}")
                continue
            match = _GRADE_RE.search(pdf_path.stem)
            grade = int(match.group(1)) if match else 0
            books.append({"path": pdf_path, "subject": subject, "grade": grade})
    return books


def build_index() -> None:
    """تمام کتاب‌های کشف‌شده در textbooks/ را استخراج و در textbooks/index.json ذخیره می‌کند."""
    chunks: list[dict] = []

    for book in _discover_books():
        doc = fitz.open(book["path"])
        print(f"در حال پردازش {book['subject']} پایه {book['grade']} ({len(doc)} صفحه)...")

        book_rel_path = str(book["path"].relative_to(_TEXTBOOKS_DIR)).replace("\\", "/")
        for start in range(0, len(doc), _PAGES_PER_CHUNK):
            pages = doc[start : start + _PAGES_PER_CHUNK]
            text = "\n".join(_extract_page_text(p) for p in pages).strip()
            if len(text) < 30:
                continue
            chunks.append(
                {
                    "subject": book["subject"],
                    "grade": book["grade"],
                    "book_path": book_rel_path,
                    "page_start": start + 1,
                    "page_end": start + len(pages),
                    "text": text,
                }
            )
        doc.close()

    _INDEX_PATH.write_text(json.dumps(chunks, ensure_ascii=False, indent=None), encoding="utf-8")
    print(f"ایندکس ساخته شد: {len(chunks)} چانک در {_INDEX_PATH}")


if __name__ == "__main__":
    build_index()
