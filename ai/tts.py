"""تبدیل متن فارسی به گفتار با edge-tts (رایگان، بدون نیاز به کلید API)."""

import io
import logging

import edge_tts

logger = logging.getLogger(__name__)

_VOICE = "fa-IR-FaridNeural"


async def synthesize_speech(text: str) -> bytes | None:
    """متن فارسی را به صدا (mp3 bytes) تبدیل می‌کند؛ در صورت خطا None برمی‌گرداند."""
    try:
        communicator = edge_tts.Communicate(text, _VOICE)
        buffer = io.BytesIO()
        async for chunk in communicator.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        return buffer.getvalue() or None
    except Exception:
        logger.exception("خطا در تبدیل متن به صدا")
        return None
