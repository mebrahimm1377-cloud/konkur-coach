"""ساخت تصویر ساده‌ی خلاصه‌ی برنامه‌ریزی هفتگی از پاسخ‌های دانش‌آموز."""

import logging
from io import BytesIO

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_FONT_PATH = "C:/Windows/Fonts/tahoma.ttf"
_WIDTH = 900
_LINE_HEIGHT = 34
_PADDING = 20


def _rtl(text: str) -> str:
    """متن فارسی را برای رسم راست‌به‌چپ روی تصویر آماده می‌کند."""
    return get_display(arabic_reshaper.reshape(text))


def build_weekly_schedule_image(answers: list[dict[str, str]]) -> bytes:
    """از روی پاسخ‌های برنامه‌ریزی هفتگی، یک تصویر خلاصه می‌سازد و bytes آن (PNG) را برمی‌گرداند."""
    title_font = ImageFont.truetype(_FONT_PATH, 26)
    question_font = ImageFont.truetype(_FONT_PATH, 18)
    answer_font = ImageFont.truetype(_FONT_PATH, 20)

    lines_per_item = 2  # سوال + جواب
    height = _PADDING * 2 + _LINE_HEIGHT * 2 + len(answers) * _LINE_HEIGHT * lines_per_item + len(answers) * 10

    img = Image.new("RGB", (_WIDTH, height), color="white")
    draw = ImageDraw.Draw(img)

    y = _PADDING
    title = _rtl("📅 برنامه‌ی هفته‌ی جدید")
    w = draw.textlength(title, font=title_font)
    draw.text((_WIDTH - w - _PADDING, y), title, font=title_font, fill="black")
    y += _LINE_HEIGHT * 2

    for item in answers:
        question_text = _rtl(item["question"])
        w = draw.textlength(question_text, font=question_font)
        draw.text((_WIDTH - w - _PADDING, y), question_text, font=question_font, fill=(90, 90, 90))
        y += _LINE_HEIGHT

        answer_text = _rtl(item["answer"])
        w = draw.textlength(answer_text, font=answer_font)
        draw.text((_WIDTH - w - _PADDING, y), answer_text, font=answer_font, fill="black")
        y += _LINE_HEIGHT + 10

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
