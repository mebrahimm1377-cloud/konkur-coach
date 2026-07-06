"""رندر لحظه‌ای (on-demand) تصویر صفحات کتاب درسی، شامل عکس‌ها، جدول‌ها و نمودارها.

به‌جای رندر از پیش همه‌ی صفحات (که فضای دیسک زیادی می‌گیره)، فقط وقتی کاربر واقعاً
درخواست می‌کنه، صفحه‌ی مربوطه از PDF اصلی رندر و کش می‌شه.
"""

import logging
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)

_TEXTBOOKS_DIR = Path(__file__).parent.parent / "textbooks"
_CACHE_DIR = _TEXTBOOKS_DIR / "page_cache"
_PAGE_IMAGE_DPI = 130
_MAX_PAGES_PER_REQUEST = 4


def render_pages(book_path: str, page_start: int, page_end: int) -> list[bytes]:
    """صفحات page_start..page_end را از کتاب مشخص‌شده به‌صورت PNG رندر می‌کند (با کش روی دیسک)."""
    pdf_path = _TEXTBOOKS_DIR / book_path
    if not pdf_path.exists():
        logger.warning("فایل کتاب پیدا نشد: %s", pdf_path)
        return []

    page_end = min(page_end, page_start + _MAX_PAGES_PER_REQUEST - 1)
    cache_dir = _CACHE_DIR / pdf_path.stem
    cache_dir.mkdir(parents=True, exist_ok=True)

    images: list[bytes] = []
    doc = None
    try:
        for page_number in range(page_start, page_end + 1):
            cache_path = cache_dir / f"p{page_number:03d}.png"
            if cache_path.exists():
                images.append(cache_path.read_bytes())
                continue

            if doc is None:
                doc = fitz.open(pdf_path)
            if page_number - 1 >= len(doc):
                continue

            zoom = _PAGE_IMAGE_DPI / 72
            pixmap = doc[page_number - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            pixmap.save(cache_path)
            images.append(cache_path.read_bytes())
    except Exception:
        logger.exception("خطا در رندر صفحات کتاب %s", book_path)
    finally:
        if doc is not None:
            doc.close()

    return images
