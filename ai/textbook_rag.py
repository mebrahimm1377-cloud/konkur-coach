"""جست‌وجوی محتوای واقعی کتاب‌های درسی (RAG) برای پایه‌گذاری پاسخ‌های AI روی متن اصلی کتاب.

از BM25 (جست‌وجوی کلیدواژه‌ای کلاسیک، بدون نیاز به کلید API یا مدل embedding) استفاده
می‌شود چون رایگانه، سریعه و برای همین حجم داده کاملاً کافیه.
"""

import json
import logging
import math
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

_INDEX_PATH = Path(__file__).parent.parent / "textbooks" / "index.json"
_TOKEN_RE = re.compile(r"[؀-ۿ]+|[A-Za-z0-9]+")

# کلمات عمومی/دستوری فارسی که هیچ سیگنال موضوعی ندارن؛ باید از کوئری کاربر حذف بشن
# وگرنه یه پیام عمومی مثل «کامل بهم آموزش بده با مثال توضیح بده» (که موضوع واقعی‌اش
# توی پیام‌های قبلی مکالمه‌ست، نه همین پیام) می‌تونه به‌طور تصادفی امتیاز خیلی بالایی
# به یه فصل کاملاً بی‌ربط بده، چون این کلمات عمومی همه‌جا زیاد تکرار می‌شن.
_STOPWORDS = {
    "من", "تو", "او", "ما", "شما", "ایشان", "اینها", "آنها",
    "این", "آن", "اینکه", "که", "را", "به", "از", "در", "با", "برای", "تا", "هم",
    "هر", "یک", "یه", "چند", "چیز", "چیزی", "چیزها",
    "است", "هست", "هستم", "هستی", "هستیم", "هستید", "هستند", "بود", "بودم", "بودی",
    "بودیم", "بودید", "بودند", "باشد", "باشم", "باشی", "باشیم", "باشید", "باشند",
    "شد", "شدم", "شدی", "شدیم", "شدید", "شدند", "شود", "بشود", "بشه", "میشه", "می‌شه",
    "کن", "کنید", "کنم", "کنی", "کنیم", "کردن", "کرد", "کردم", "کردی", "کردیم",
    "بده", "بدید", "بدم", "بدی", "بدیم", "بگو", "بگید", "بگم",
    "چیه", "چیست", "چطور", "چگونه", "کجا", "کی", "کدام", "چرا",
    "خیلی", "کامل", "کاملا", "کاملاً", "لطفا", "لطفاً", "ممنون", "مرسی",
    "بهم", "برام", "بهت", "برات", "میتونی", "می‌تونی", "میشه", "می‌شه",
    "طوری", "طور", "جوری", "متوجه", "بشم", "بفهمم", "توضیح", "مثال", "مثل",
    "الان", "دیگه", "دیگر", "فقط", "واقعا", "واقعاً", "یعنی", "پس", "اگه", "اگر",
    "و", "یا", "ولی", "اما", "چون", "زیرا", "رو", "می",
    "فصل", "بخش", "درس", "قسمت", "پایه", "اولش", "دومش",
    "سلام", "چطوری", "چطور", "خوبی", "خداحافظ", "بای", "درود", "احوالت",
}

# وقتی کاربر صریحاً پایه یا نام درس رو تو سؤالش می‌گه (مثلاً «فصل دوم شیمی پایه
# یازدهم»)، این کلمات ناوبری («فصل»، «بخش») سیگنال موضوعی ندارن و BM25 به‌تنهایی
# نمی‌تونه پایه‌ی درست رو تشخیص بده (چون کلمه‌ی «یازدهم» لزوماً تو متن کتاب تکرار
# نمی‌شه). برای همین پایه/درس رو مستقیم از متن سؤال استخراج و به‌عنوان فیلتر قطعی
# اعمال می‌کنیم تا هیچ‌وقت پایه یا درس اشتباه برنگرده.
_GRADE_WORDS = {"دهم": 10, "یازدهم": 11, "دوازدهم": 12}

_SUBJECT_ALIASES = {
    "شیمی": "شیمی",
    "فیزیک": "فیزیک",
    "زیست": "زیست‌شناسی",
    "زیست‌شناسی": "زیست‌شناسی",
    "ریاضی": "ریاضی",
    "عربی": "عربی",
    "فارسی": "فارسی",
    "نگارش": "نگارش",
    "دین": "دین و زندگی",
    "دینی": "دین و زندگی",
    "انگلیسی": "انگلیسی",
    "زمین‌شناسی": "زمین‌شناسی",
    "زمینشناسی": "زمین‌شناسی",
    "تاریخ": "تاریخ معاصر ایران",
    "جغرافیا": "جغرافیای ایران",
    "جغرافی": "جغرافیای ایران",
    "آزمایشگاه": "آزمایشگاه علوم تجربی",
    "دفاعی": "آمادگی دفاعی",
    "رسانه": "تفکر و سواد رسانه‌ای",
    "سلامت": "سلامت و بهداشت",
    "بهداشت": "سلامت و بهداشت",
    "هویت": "هویت اجتماعی",
}


_GRADE_AND_SUBJECT_WORDS = set(_GRADE_WORDS) | set(_SUBJECT_ALIASES)


def _detect_filters(query: str) -> tuple[str | None, int | None]:
    """پایه و/یا نام درس را در صورت ذکر صریح در متن سؤال تشخیص می‌دهد."""
    tokens = _tokenize(query)
    grade = next((_GRADE_WORDS[t] for t in tokens if t in _GRADE_WORDS), None)
    subject = next((_SUBJECT_ALIASES[t] for t in tokens if t in _SUBJECT_ALIASES), None)
    return subject, grade

# نرمال‌سازی طول سند BM25 (پارامتر b) رو کمتر از پیش‌فرض (۰.۷۵) نگه می‌داریم؛ چون
# چانک‌های کتاب طول خیلی متفاوتی دارن، مقدار پیش‌فرض به چانک‌های کوتاه که به‌طور
# تصادفی یک کلمه‌ی کلیدی رو (بدون ربط موضوعی واقعی) دارن، امتیاز به‌طرز غیرمنصفانه
# بالایی می‌ده (مثلاً یک پاراگراف زندگی‌نامه در کتاب تاریخ که اسم رشته‌ی تحصیلی یک
# شخصیت رو ذکر کرده، برای سوال‌های علمی درباره‌ی همون رشته بالاتر از فصل واقعی می‌شینه).
_BM25_B = 0.3


def _tokenize(text: str) -> list[str]:
    """متن را برای BM25 به توکن‌های ساده می‌شکند."""
    return _TOKEN_RE.findall(text.lower())


def _query_tokens(text: str) -> set[str]:
    """کوئری کاربر را توکنایز و کلمات عمومی/بی‌سیگنال (stopwords) را از آن حذف می‌کند.

    اسم پایه/درس (مثلاً «یازدهم»، «شیمی») هم از رتبه‌بندی حذف می‌شن؛ چون این‌ها با
    _detect_filters به‌عنوان فیلتر قطعی اعمال می‌شن و اگه توی رتبه‌بندی BM25 هم
    بمونن، صفحات جلد/فهرست کتاب (که اسم کامل کتاب رو مدام تکرار می‌کنن) امتیاز
    مصنوعاً بالایی می‌گیرن و به‌جای فصل واقعی انتخاب می‌شن."""
    return {tok for tok in _tokenize(text) if tok not in _STOPWORDS and tok not in _GRADE_AND_SUBJECT_WORDS}


class TextbookRAG:
    """ایندکس جست‌وجوی کتاب‌های درسی را در حافظه نگه می‌دارد و امکان جست‌وجو می‌دهد."""

    def __init__(self) -> None:
        self._chunks: list[dict] = []
        self._tokenized: list[list[str]] = []
        self._bm25: BM25Okapi | None = None
        self._load()

    def _load(self) -> None:
        if not _INDEX_PATH.exists():
            logger.warning("ایندکس کتاب‌های درسی پیدا نشد (%s)؛ RAG غیرفعال می‌ماند.", _INDEX_PATH)
            return

        try:
            self._chunks = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
            self._tokenized = [_tokenize(chunk["text"]) for chunk in self._chunks]
            self._bm25 = BM25Okapi(self._tokenized, b=_BM25_B)
            logger.info("ایندکس کتاب‌های درسی بارگذاری شد: %d چانک", len(self._chunks))
        except Exception:
            logger.exception("خطا در بارگذاری ایندکس کتاب‌های درسی")
            self._chunks = []
            self._tokenized = []
            self._bm25 = None

    @property
    def is_ready(self) -> bool:
        return self._bm25 is not None and bool(self._chunks)

    def _ranked_indices(self, query: str) -> list[int]:
        """ایندکس چانک‌ها را بر اساس امتیاز BM25 مرتب می‌کند، با فیلتر «پوشش کلمات»:
        برای کوئری‌های چندکلمه‌ای، چانکی که فقط یکی از چند کلمه‌ی کوئری رو (به‌طور
        اتفاقی) داره کنار گذاشته می‌شه، تا مثلاً «قانون دوم نیوتن» به یک چانک ریاضی
        که فقط کلمه‌ی «نیوتن» رو داره (نه «قانون» یا «دوم») نره."""
        query_tokens = _query_tokens(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(list(query_tokens))
        min_coverage = math.ceil(len(query_tokens) / 2) if len(query_tokens) > 1 else 1

        ranked = sorted(range(len(self._chunks)), key=lambda i: scores[i], reverse=True)
        filtered = [
            i
            for i in ranked
            if scores[i] > 0 and len(query_tokens & set(self._tokenized[i])) >= min_coverage
        ]
        return filtered if filtered else [i for i in ranked if scores[i] > 0]

    def search(self, query: str, top_k: int = 3, subject: str | None = None, grade: int | None = None) -> list[dict]:
        """چانک‌های کتاب درسی مرتبط با query را برمی‌گرداند (خالی اگه ایندکس آماده نباشه).

        اگه subject/grade صریحاً پاس داده نشده باشن، از خود متن query (مثلاً «شیمی
        پایه یازدهم») تشخیص داده و به‌عنوان فیلتر قطعی اعمال می‌شن."""
        if not self.is_ready:
            return []

        detected_subject, detected_grade = _detect_filters(query)
        subject = subject or detected_subject
        grade = grade or detected_grade

        results = []
        for i in self._ranked_indices(query):
            chunk = self._chunks[i]
            if subject and chunk["subject"] != subject:
                continue
            if grade and chunk["grade"] != grade:
                continue
            results.append(chunk)
            if len(results) >= top_k:
                break
        return results

    def top_hit(self, query: str, min_score: float = 8.0) -> dict | None:
        """بهترین چانک مرتبط را برمی‌گرداند، فقط اگه امتیازش به‌قدر کافی بالا باشه (برای جلوگیری
        از فرستادن تصویر صفحه برای سوال‌های عمومی که ربط ضعیفی به یک بخش خاص کتاب دارن)."""
        if not self.is_ready:
            return None

        subject, grade = _detect_filters(query)
        ranked = self._ranked_indices(query)
        if subject or grade:
            ranked = [
                i
                for i in ranked
                if (not subject or self._chunks[i]["subject"] == subject)
                and (not grade or self._chunks[i]["grade"] == grade)
            ]
        if not ranked:
            return None

        best_i = ranked[0]
        scores = self._bm25.get_scores(list(_query_tokens(query)))
        if scores[best_i] < min_score:
            return None
        return self._chunks[best_i]

    def format_context(self, query: str, top_k: int = 3) -> str | None:
        """چانک‌های مرتبط را به‌صورت یک متن آماده برای تزریق به prompt برمی‌گرداند."""
        chunks = self.search(query, top_k=top_k)
        if not chunks:
            return None

        blocks = []
        for chunk in chunks:
            source = f"[کتاب {chunk['subject']} پایه {chunk['grade']}، صفحه {chunk['page_start']}]"
            blocks.append(f"{source}\n{chunk['text']}")
        return "\n\n".join(blocks)


textbook_rag = TextbookRAG()
