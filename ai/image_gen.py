"""ساخت تصویر با یک مدل هوش مصنوعی تصویرساز رایگان و بدون کلید (Pollinations.ai، مبتنی بر Flux)."""

import logging
import urllib.parse

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://image.pollinations.ai/prompt"
_TIMEOUT = 60.0


async def generate_illustration(prompt: str, width: int = 1024, height: int = 1024) -> bytes | None:
    """یک تصویر بر اساس prompt انگلیسی می‌سازد؛ در صورت خطا None برمی‌گرداند.

    از Pollinations.ai استفاده می‌شود چون رایگانه و نیاز به کلید API نداره؛ مدل زیرینش
    (Flux) مثل بقیه‌ی مدل‌های تصویرساز در رندر متن فارسی داخل تصویر ضعیفه، برای همین
    نوشته‌ی فارسی را جداگانه (با ai/image_compose.py) روی تصویر اضافه می‌کنیم.
    """
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"{_BASE_URL}/{encoded_prompt}"
    params = {"width": width, "height": height, "nologo": "true"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.content
    except Exception:
        logger.exception("خطا در ساخت تصویر با مدل هوش مصنوعی")
        return None
