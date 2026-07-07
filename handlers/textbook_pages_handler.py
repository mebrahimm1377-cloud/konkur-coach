"""نمایش تصویر واقعی صفحات کتاب درسی (عکس‌ها، جدول‌ها، نمودارها) برای یک موضوع (`/pages`)."""

import io
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from ai.client import ai_client
from ai.textbook_pages import render_pages
from ai.textbook_rag import textbook_rag

logger = logging.getLogger(__name__)


async def show_textbook_pages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """موضوع را جست‌وجو کرده و تصویر صفحات مرتبط از کتاب درسی را می‌فرستد. فرمت: /pages <موضوع>"""
    if update.message is None:
        return

    if not context.args:
        await update.message.reply_text("فرمت درست: /pages <موضوع>\nمثال: /pages میتوز")
        return

    topic = " ".join(context.args)
    chunk = textbook_rag.top_hit(topic)

    not_found_reply = (
        "چیزی توی کتاب‌های درسی درباره‌ی این موضوع با اطمینان کافی پیدا نکردم. "
        "لطفاً موضوع رو دقیق‌تر و با کلمه‌ی کلیدی مشخص بنویس (مثلاً «میتوز» به‌جای «فصل ۲ زیست»)."
    )

    if chunk is None:
        await update.message.reply_text(not_found_reply)
        return

    if not await ai_client.is_topic_relevant(topic, chunk["text"]):
        await update.message.reply_text(not_found_reply)
        return

    await update.message.chat.send_action(action="upload_photo")

    images = render_pages(chunk["book_path"], chunk["page_start"], chunk["page_end"])
    caption = f"📖 {chunk['subject']} پایه {chunk['grade']} — صفحه {chunk['page_start']}"
    sent_any = False
    for i, image_bytes in enumerate(images):
        try:
            await update.message.reply_photo(photo=io.BytesIO(image_bytes), caption=caption if i == 0 else None)
            sent_any = True
        except Exception:
            logger.exception("خطا در ارسال تصویر صفحه‌ی کتاب")

    if not sent_any:
        await update.message.reply_text("متاسفانه نتونستم تصویر صفحه رو بسازم.")


def build_textbook_pages_handlers() -> list:
    """هندلر دستور /pages را می‌سازد."""
    return [CommandHandler("pages", show_textbook_pages)]
