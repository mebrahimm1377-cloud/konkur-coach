"""نمایش تصویر واقعی صفحات کتاب درسی (عکس‌ها، جدول‌ها، نمودارها) برای یک موضوع (`/pages`)."""

import io
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from ai.textbook_pages import render_pages
from ai.textbook_rag import textbook_rag

logger = logging.getLogger(__name__)

_MAX_RESULTS = 2


async def show_textbook_pages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """موضوع را جست‌وجو کرده و تصویر صفحات مرتبط از کتاب درسی را می‌فرستد. فرمت: /pages <موضوع>"""
    if update.message is None:
        return

    if not context.args:
        await update.message.reply_text("فرمت درست: /pages <موضوع>\nمثال: /pages میتوز")
        return

    topic = " ".join(context.args)
    results = textbook_rag.search(topic, top_k=_MAX_RESULTS)

    if not results:
        await update.message.reply_text("چیزی توی کتاب‌های درسی درباره‌ی این موضوع پیدا نکردم.")
        return

    await update.message.chat.send_action(action="upload_photo")

    sent_any = False
    for chunk in results:
        images = render_pages(chunk["book_path"], chunk["page_start"], chunk["page_end"])
        caption = f"📖 {chunk['subject']} پایه {chunk['grade']} — صفحه {chunk['page_start']}"
        for i, image_bytes in enumerate(images):
            try:
                await update.message.reply_photo(
                    photo=io.BytesIO(image_bytes), caption=caption if i == 0 else None
                )
                sent_any = True
            except Exception:
                logger.exception("خطا در ارسال تصویر صفحه‌ی کتاب")

    if not sent_any:
        await update.message.reply_text("متاسفانه نتونستم تصویر صفحه رو بسازم.")


def build_textbook_pages_handlers() -> list:
    """هندلر دستور /pages را می‌سازد."""
    return [CommandHandler("pages", show_textbook_pages)]
