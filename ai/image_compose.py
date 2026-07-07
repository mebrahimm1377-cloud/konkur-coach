"""افزودن نوشته‌ی فارسی روی تصویر تولیدشده توسط AI.

مدل‌های تصویرساز (مثل Flux/DALL-E/Stable Diffusion) معمولاً نوشته‌ی فارسی/عربی را
به‌درستی داخل تصویر رندر نمی‌کنن (بهم‌ریخته یا نامفهوم می‌شه) — این یک محدودیت شناخته‌شده‌ی
این مدل‌هاست. برای همین متن فارسی را به‌صورت جداگانه، با همون روش تست‌شده‌ی PDF/تصویر
برنامه‌ی هفتگی (arabic_reshaper + bidi + فونت Tahoma)، مستقیماً روی تصویر می‌کشیم تا
همیشه ۱۰۰٪ درست و خوانا باشه.
"""

import logging
import textwrap
from io import BytesIO
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_FONT_PATH = str(Path(__file__).parent.parent / "assets" / "fonts" / "Vazirmatn-Bold.ttf")
_FONT_SIZE = 40
_LINE_HEIGHT = 52
_BAR_PADDING = 24
_WRAP_WIDTH = 28


def _rtl(text: str) -> str:
    """متن فارسی را برای رسم راست‌به‌چپ روی تصویر آماده می‌کند."""
    return get_display(arabic_reshaper.reshape(text))


def add_persian_caption(image_bytes: bytes, caption: str) -> bytes:
    """یک نوار نیمه‌شفاف پایین تصویر اضافه کرده و نوشته‌ی فارسی را رویش می‌کشد."""
    image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    font = ImageFont.truetype(_FONT_PATH, _FONT_SIZE)

    lines = textwrap.wrap(caption, width=_WRAP_WIDTH) or [caption]
    bar_height = _BAR_PADDING * 2 + len(lines) * _LINE_HEIGHT

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle(
        [(0, image.height - bar_height), (image.width, image.height)],
        fill=(0, 0, 0, 160),
    )

    y = image.height - bar_height + _BAR_PADDING
    for line in lines:
        shaped = _rtl(line)
        w = draw.textlength(shaped, font=font)
        draw.text(((image.width - w) / 2, y), shaped, font=font, fill=(255, 255, 255, 255))
        y += _LINE_HEIGHT

    composed = Image.alpha_composite(image, overlay).convert("RGB")
    buffer = BytesIO()
    composed.save(buffer, format="PNG")
    return buffer.getvalue()
