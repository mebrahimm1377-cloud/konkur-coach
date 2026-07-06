"""ساخت تصویر آموزشی با AI به همراه عنوان فارسی (`/image`)."""

import io
import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from ai.client import ai_client
from ai.image_compose import add_persian_caption
from ai.image_gen import generate_illustration

logger = logging.getLogger(__name__)

AWAITING_TOPIC = 0

_PROMPT_TEXT = "چه موضوعی رو می‌خوای به تصویر آموزشی تبدیل کنم؟ (مثلاً «چرخه‌ی کربس» یا «قانون اول نیوتن»)"
_FAILURE_TEXT = "متاسفانه الان نتونستم تصویر رو بسازم. لطفاً چند لحظه دیگه دوباره امتحان کن."


async def start_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """entry point دستور /image."""
    if update.message is None:
        return ConversationHandler.END
    await update.message.reply_text(_PROMPT_TEXT)
    return AWAITING_TOPIC


async def start_image_from_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """entry point دکمه‌ی منو برای ساخت تصویر آموزشی."""
    query = update.callback_query
    if query is None:
        return ConversationHandler.END
    await query.answer()
    await query.message.reply_text(_PROMPT_TEXT)
    return AWAITING_TOPIC


async def receive_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """موضوع را دریافت، تصویر می‌سازد و همراه عنوان فارسی ارسال می‌کند."""
    if update.message is None or update.message.text is None:
        return ConversationHandler.END

    topic = update.message.text
    await update.message.chat.send_action(action="upload_photo")

    brief = await ai_client.generate_image_brief(topic)
    if brief is None:
        await update.message.reply_text(_FAILURE_TEXT)
        return ConversationHandler.END

    image_bytes = await generate_illustration(brief["image_prompt"])
    if image_bytes is None:
        await update.message.reply_text(_FAILURE_TEXT)
        return ConversationHandler.END

    try:
        final_image = add_persian_caption(image_bytes, brief["caption_fa"])
        await update.message.reply_photo(photo=io.BytesIO(final_image))
    except Exception:
        logger.exception("خطا در افزودن نوشته‌ی فارسی روی تصویر")
        await update.message.reply_text(_FAILURE_TEXT)

    return ConversationHandler.END


async def cancel_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """ساخت تصویر جاری را لغو می‌کند."""
    if update.message is not None:
        await update.message.reply_text("لغو شد.")
    return ConversationHandler.END


def build_image_conversation_handler() -> ConversationHandler:
    """ConversationHandler ساخت تصویر آموزشی را می‌سازد."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("image", start_image),
            CallbackQueryHandler(start_image_from_menu, pattern="^menu_start:image$"),
        ],
        states={
            AWAITING_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_topic)],
        },
        fallbacks=[CommandHandler("cancel", cancel_image)],
        name="image_generation",
        persistent=False,
    )
