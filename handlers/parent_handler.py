"""دستورات مربوط به دعوت و دسترسی والدین."""

import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from database.db import (
    create_invite_token,
    create_parent_link,
    get_latest_session,
    get_linked_students,
    get_or_create_user,
    resolve_invite_token,
    set_user_role,
)
from utils.telegram_text import send_long_message

logger = logging.getLogger(__name__)

PARENT_TOKEN_PREFIX = "parent_"


async def invite_parent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """برای دانش‌آموز یه لینک دعوت والدین می‌سازد."""
    if update.effective_chat is None or update.effective_user is None:
        return

    try:
        student_user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
        token = create_invite_token(student_user.id)
    except Exception:
        logger.exception("خطا در ساخت توکن دعوت والدین")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="مشکلی پیش اومد، لطفاً دوباره امتحان کن.")
        return

    bot_username = context.bot.username
    invite_link = f"https://t.me/{bot_username}?start={PARENT_TOKEN_PREFIX}{token}"

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "این لینک رو برای والدینت بفرست تا به گزارش‌های تحصیلی‌ت دسترسی داشته باشن:\n\n"
            f"{invite_link}\n\n"
            "کافیه والدینت روی همین لینک بزنن و بات رو استارت کنن."
        ),
    )


async def handle_parent_token(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str) -> bool:
    """در صورتی که payload دستور /start توکن دعوت والدین باشد، اتصال را انجام می‌دهد.

    خروجی True یعنی درخواست به‌عنوان دعوت والدین پردازش شد.
    """
    if not payload.startswith(PARENT_TOKEN_PREFIX) or update.message is None or update.effective_user is None:
        return False

    token = payload[len(PARENT_TOKEN_PREFIX):]
    student_user_id = resolve_invite_token(token)

    if student_user_id is None:
        await update.message.reply_text("این لینک دعوت نامعتبر یا قبلاً استفاده‌شده است.")
        return True

    parent_user = get_or_create_user(update.effective_user.id, update.effective_user.first_name, role="parent")
    set_user_role(parent_user.id, "parent")
    create_parent_link(parent_user_id=parent_user.id, student_user_id=student_user_id)

    await update.message.reply_text(
        "خوش اومدی! از این به بعد گزارش‌های شبانه‌ی فرزندت رو اینجا دریافت می‌کنی.\n"
        "برای دیدن آخرین گزارش هر وقت خواستی، دستور /mystudent رو بزن."
    )
    return True


async def my_student_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """آخرین گزارش شبانه‌ی دانش‌آموز(های) لینک‌شده به این والد را نشان می‌دهد."""
    if update.effective_chat is None or update.effective_user is None:
        return

    parent_user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    students = get_linked_students(parent_user.id)

    if not students:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="هنوز هیچ دانش‌آموزی به حساب شما لینک نشده."
        )
        return

    for student in students:
        session = get_latest_session(student.id, slot_type="evening_report")
        if session is None or not session.ai_evaluation_parent:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"هنوز گزارش شبانه‌ای برای {student.first_name or 'فرزندتان'} ثبت نشده.",
            )
            continue
        await send_long_message(
            context.bot,
            update.effective_chat.id,
            f"📋 آخرین گزارش {student.first_name or 'فرزندتان'} ({session.session_date}):\n\n{session.ai_evaluation_parent}",
        )


def build_parent_handlers() -> list:
    """هندلرهای دستورات والدین را می‌سازد."""
    return [
        CommandHandler("invite_parent", invite_parent),
        CommandHandler("mystudent", my_student_report),
    ]
