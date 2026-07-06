"""ابزارهای مطالعه: خلاصه‌سازی (`/summarize`)، حل گام‌به‌گام (`/solve`) و تحلیل دست‌خط (`/handwriting`)."""

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from ai.client import ai_client
from utils.telegram_text import split_for_telegram

logger = logging.getLogger(__name__)

AWAITING_CONTENT = 0

_MODE_KEY = "study_tool_mode"

_INSTRUCTIONS = {
    "summarize": "این محتوا رو به‌صورت خلاصه و نکته‌به‌نکته (حداکثر ۸ خط) برای مرور سریع دانش‌آموز خلاصه کن.",
    "solve": (
        "این یک سوال درسی/تمرینه. **جواب مستقیم نده**. به‌جاش با سوال‌های راهنما (روش سقراطی) دانش‌آموز رو "
        "قدم‌به‌قدم به سمت حل خودش هدایت کن."
    ),
    "handwriting": (
        "این عکس یه صفحه از جزوه یا دست‌خط دانش‌آموزه. کیفیت خوانایی، سازمان‌دهی و کامل بودن یادداشت‌برداری رو "
        "ارزیابی کن و یه پیشنهاد کوتاه برای بهتر شدنش بده."
    ),
}

_PROMPT_TEXT = {
    "summarize": "چی رو می‌خوای خلاصه کنم؟ می‌تونی متن بفرستی یا عکس بگیری.",
    "solve": "سوالت رو بفرست (متن یا عکس) تا قدم‌به‌قدم راهنماییت کنم.",
    "handwriting": "یه عکس از جزوه یا دست‌خطت بفرست تا ارزیابیش کنم.",
}


def _make_start(mode: str):
    """entry point یک ابزار مطالعه را می‌سازد."""

    async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if update.message is None:
            return ConversationHandler.END
        context.user_data[_MODE_KEY] = mode
        await update.message.reply_text(_PROMPT_TEXT[mode])
        return AWAITING_CONTENT

    return _start


def _make_start_from_menu(mode: str):
    """entry point دکمه‌ی منو برای یک ابزار مطالعه را می‌سازد."""

    async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        if query is None:
            return ConversationHandler.END
        await query.answer()
        context.user_data[_MODE_KEY] = mode
        await query.message.reply_text(_PROMPT_TEXT[mode])
        return AWAITING_CONTENT

    return _start


async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """محتوای متنی یا تصویری کاربر را دریافت و با AI پردازش می‌کند."""
    if update.message is None:
        return ConversationHandler.END

    mode = context.user_data.get(_MODE_KEY, "summarize")
    instruction = _INSTRUCTIONS[mode]

    await update.message.chat.send_action(action="typing")

    if update.message.photo:
        largest_photo = update.message.photo[-1]
        photo_file = await largest_photo.get_file()
        image_bytes = bytes(await photo_file.download_as_bytearray())
        caption = f"{instruction}\n\nمتن اضافه‌ی کاربر: {update.message.caption}" if update.message.caption else instruction
        reply = await ai_client.get_vision_reply(image_bytes, caption)
    elif update.message.text:
        reply = await ai_client.get_reply([], update.message.text, extra_context=instruction)
    else:
        await update.message.reply_text("لطفاً متن یا عکس بفرست.")
        return AWAITING_CONTENT

    chunks = split_for_telegram(reply)
    await update.message.reply_text(chunks[0])
    for chunk in chunks[1:]:
        await update.message.chat.send_message(chunk)
    context.user_data.pop(_MODE_KEY, None)
    return ConversationHandler.END


async def cancel_study_tool(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """ابزار مطالعه‌ی جاری را لغو می‌کند."""
    context.user_data.pop(_MODE_KEY, None)
    if update.message is not None:
        await update.message.reply_text("لغو شد.")
    return ConversationHandler.END


def _build_handler(command: str, mode: str) -> ConversationHandler:
    """یک ConversationHandler برای یک ابزار مطالعه می‌سازد."""
    return ConversationHandler(
        entry_points=[
            CommandHandler(command, _make_start(mode)),
            CallbackQueryHandler(_make_start_from_menu(mode), pattern=f"^menu_start:{mode}$"),
        ],
        states={
            AWAITING_CONTENT: [MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, receive_content)],
        },
        fallbacks=[CommandHandler("cancel", cancel_study_tool)],
        name=f"study_tool_{mode}",
        persistent=False,
    )


def build_study_tools_handlers() -> list:
    """هندلرهای هر سه ابزار مطالعه را می‌سازد."""
    return [
        _build_handler("summarize", "summarize"),
        _build_handler("solve", "solve"),
        _build_handler("handwriting", "handwriting"),
    ]
