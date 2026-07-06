"""چالش هفتگی که کوچ برای همه‌ی دانش‌آموزها تعریف می‌کند."""

import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from config import config
from database.db import get_active_challenge, get_or_create_user, get_students, set_active_challenge

logger = logging.getLogger(__name__)


async def set_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """چالش هفتگی جدید را تعریف و به همه‌ی دانش‌آموزها اعلام می‌کند. فقط برای کوچ."""
    if update.message is None or update.effective_user is None:
        return
    if update.effective_user.id != config.coach_telegram_id:
        return

    if not context.args:
        await update.message.reply_text("فرمت درست: /set_challenge <متن چالش>")
        return

    text = " ".join(context.args)
    coach_user = get_or_create_user(update.effective_user.id, update.effective_user.first_name, role="coach")
    set_active_challenge(coach_user.id, text)

    for student in get_students():
        try:
            await context.bot.send_message(chat_id=student.telegram_id, text=f"🎯 چالش این هفته:\n\n{text}")
        except Exception:
            logger.exception("ارسال چالش به کاربر %s ناموفق بود", student.telegram_id)

    await update.message.reply_text("چالش ثبت و برای همه‌ی دانش‌آموزها ارسال شد ✅")


async def show_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """چالش فعال فعلی را نشان می‌دهد."""
    if update.effective_chat is None:
        return

    challenge = get_active_challenge()
    if challenge is None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="فعلاً هیچ چالش فعالی وجود نداره.")
        return

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎯 چالش این هفته:\n\n{challenge.text}")


def build_challenge_handlers() -> list:
    """هندلرهای چالش هفتگی را می‌سازد."""
    return [
        CommandHandler("set_challenge", set_challenge),
        CommandHandler("challenge", show_challenge),
    ]
