"""ابزار مشترک برای ارسال متن‌های طولانی (مثلاً پاسخ AI) که ممکنه از سقف ۴۰۹۶
کاراکتری تلگرام رد بشن؛ بدون این کار، send_message با خطای BadRequest کرش می‌کنه
و کاربر اصلاً پاسخی دریافت نمی‌کنه."""

_TELEGRAM_MESSAGE_LIMIT = 4000


def split_for_telegram(text: str, limit: int = _TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """متن را به چند تکه‌ی کوچک‌تر از سقف مجاز تلگرام می‌شکند (ترجیحاً از سر خط)."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")

    return chunks


async def send_long_message(bot, chat_id: int, text: str) -> None:
    """متن طولانی را در چند پیام پشت‌سرهم (در صورت نیاز) به یک چت می‌فرستد."""
    for chunk in split_for_telegram(text):
        await bot.send_message(chat_id=chat_id, text=chunk)
