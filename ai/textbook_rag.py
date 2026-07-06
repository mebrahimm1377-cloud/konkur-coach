"""جست‌وجوی محتوای واقعی کتاب‌های درسی (RAG) برای پایه‌گذاری پاسخ‌های AI روی متن اصلی کتاب.

از BM25 (جست‌وجوی کلیدواژه‌ای کلاسیک، بدون نیاز به کلید API یا مدل embedding) استفاده
می‌شود چون رایگانه، سریعه و برای همین حجم داده کاملاً کافیه.
"""

import json
import logging
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

_INDEX_PATH = Path(__file__).parent.parent / "textbooks" / "index.json"
_TOKEN_RE = re.compile(r"[؀-ۿ]+|[A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """متن را برای BM25 به توکن‌های ساده می‌شکند."""
    return _TOKEN_RE.findall(text.lower())


class TextbookRAG:
    """ایندکس جست‌وجوی کتاب‌های درسی را در حافظه نگه می‌دارد و امکان جست‌وجو می‌دهد."""

    def __init__(self) -> None:
        self._chunks: list[dict] = []
        self._bm25: BM25Okapi | None = None
        self._load()

    def _load(self) -> None:
        if not _INDEX_PATH.exists():
            logger.warning("ایندکس کتاب‌های درسی پیدا نشد (%s)؛ RAG غیرفعال می‌ماند.", _INDEX_PATH)
            return

        try:
            self._chunks = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
            tokenized = [_tokenize(chunk["text"]) for chunk in self._chunks]
            self._bm25 = BM25Okapi(tokenized)
            logger.info("ایندکس کتاب‌های درسی بارگذاری شد: %d چانک", len(self._chunks))
        except Exception:
            logger.exception("خطا در بارگذاری ایندکس کتاب‌های درسی")
            self._chunks = []
            self._bm25 = None

    @property
    def is_ready(self) -> bool:
        return self._bm25 is not None and bool(self._chunks)

    def search(self, query: str, top_k: int = 3, subject: str | None = None, grade: int | None = None) -> list[dict]:
        """چانک‌های کتاب درسی مرتبط با query را برمی‌گرداند (خالی اگه ایندکس آماده نباشه)."""
        if not self.is_ready:
            return []

        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(self._chunks)), key=lambda i: scores[i], reverse=True)

        results = []
        for i in ranked:
            if scores[i] <= 0:
                break
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

        scores = self._bm25.get_scores(_tokenize(query))
        best_i = max(range(len(self._chunks)), key=lambda i: scores[i])
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
