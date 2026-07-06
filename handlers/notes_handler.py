"""دستورات یادداشت سریع دانش‌آموز (`/note`, `/notes`)."""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from database.db import create_note, get_notes, get_or_create_user


async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """یک یادداشت سریع جدید ذخیره می‌کند. فرمت: /note <متن>"""
    if update.message is None or update.effective_user is None:
        return

    if not context.args:
        await update.message.reply_text("فرمت درست: /note <متنی که می‌خوای یادت بمونه>")
        return

    text = " ".join(context.args)
    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    create_note(user.id, text)
    await update.message.reply_text("یادداشت شد ✅")


async def list_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """یادداشت‌های اخیر کاربر را لیست می‌کند."""
    if update.effective_chat is None or update.effective_user is None:
        return

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    notes = get_notes(user.id)

    if not notes:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="هنوز یادداشتی ثبت نکردی. با /note <متن> شروع کن."
        )
        return

    lines = ["📝 یادداشت‌های اخیرت:\n"]
    for note in notes:
        date_str = note.created_at.strftime("%Y-%m-%d")
        lines.append(f"• [{date_str}] {note.text}")

    await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))


def build_notes_handlers() -> list:
    """هندلرهای یادداشت سریع را می‌سازد."""
    return [
        CommandHandler("note", add_note),
        CommandHandler("notes", list_notes),
    ]
