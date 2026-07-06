"""دستور فعال‌سازی حالت امتحان (`/exam_mode <YYYY-MM-DD>`)."""

from datetime import datetime

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from database.db import get_or_create_user, set_exam_date


async def exam_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تاریخ امتحان بعدی دانش‌آموز را ثبت می‌کند تا فرکانس و لحن پیام‌ها فشرده‌تر بشه."""
    if update.message is None or update.effective_user is None:
        return

    if not context.args:
        await update.message.reply_text("فرمت درست: /exam_mode YYYY-MM-DD (مثلاً /exam_mode 2026-08-15)")
        return

    date_text = context.args[0]
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("فرمت تاریخ درست نیست. لطفاً به‌صورت YYYY-MM-DD بفرست (مثلاً 2026-08-15).")
        return

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    set_exam_date(user.id, date_text)

    await update.message.reply_text(
        f"ثبت شد! تا {date_text} کنارتم و پیام‌هام رو متمرکزتر می‌کنم 💪\n"
        "هر وقت خواستی لغوش کنی، کافیه /exam_mode off رو بفرستی."
    )


async def exam_mode_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """حالت امتحان را غیرفعال می‌کند (فرمت: /exam_mode off)."""
    if update.message is None or update.effective_user is None:
        return

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    set_exam_date(user.id, None)
    await update.message.reply_text("حالت امتحان خاموش شد.")


async def route_exam_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بر اساس آرگومان اول، بین فعال/غیرفعال کردن حالت امتحان تصمیم می‌گیرد."""
    if context.args and context.args[0].lower() == "off":
        await exam_mode_off(update, context)
        return
    await exam_mode(update, context)


def build_exam_mode_handlers() -> list:
    """هندلر دستور حالت امتحان را می‌سازد."""
    return [CommandHandler("exam_mode", route_exam_mode)]
