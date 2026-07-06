"""دستورات مخصوص کوچ (فقط برای COACH_TELEGRAM_ID قابل استفاده‌اند)."""

import io
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from ai.pdf_export import build_report_pdf
from config import config
from database.db import create_coach_note, get_recent_sessions, get_latest_session, get_students, get_user_by_telegram_id
from utils.telegram_text import split_for_telegram

logger = logging.getLogger(__name__)


def _is_coach(update: Update) -> bool:
    """بررسی می‌کند که آیا فرستنده‌ی پیام همان کوچ تنظیم‌شده در .env است."""
    return update.effective_user is not None and update.effective_user.id == config.coach_telegram_id


async def list_students(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """لیست دانش‌آموزها را همراه آخرین وضعیت گزارش شبانه نشان می‌دهد."""
    if update.effective_chat is None or not _is_coach(update):
        return

    students = get_students()
    if not students:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="هنوز هیچ دانش‌آموزی ثبت نشده.")
        return

    lines = ["👥 لیست دانش‌آموزها:\n"]
    for student in students:
        last_session = get_latest_session(student.id, slot_type="evening_report")
        status = f"آخرین گزارش: {last_session.session_date}" if last_session else "هنوز گزارشی نداده"
        lines.append(
            f"• {student.first_name or 'بدون‌نام'} (id: {student.telegram_id})\n"
            f"  {status} | 🔥 استریک: {student.current_streak} | ⭐ امتیاز: {student.points}"
        )

    await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))


async def report_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """منوی انتخاب دانش‌آموز برای دیدن آخرین ارزیابی شبانه را نشان می‌دهد."""
    if update.effective_chat is None or not _is_coach(update):
        return

    students = get_students()
    if not students:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="هنوز هیچ دانش‌آموزی ثبت نشده.")
        return

    buttons = [
        [InlineKeyboardButton(text=student.first_name or str(student.telegram_id), callback_data=f"coach_report:{student.id}")]
        for student in students
    ]
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="یه دانش‌آموز رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def show_student_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """آخرین ارزیابی شبانه‌ی دانش‌آموز انتخاب‌شده را نشان می‌دهد."""
    query = update.callback_query
    if query is None or query.data is None or not _is_coach(update):
        return

    await query.answer()
    student_id = int(query.data.split(":", 1)[1])
    session = get_latest_session(student_id, slot_type="evening_report")

    if session is None or not session.ai_evaluation_coach:
        await query.edit_message_text("هنوز گزارش شبانه‌ای برای این دانش‌آموز ثبت نشده.")
        return

    chunks = split_for_telegram(f"📋 آخرین گزارش ({session.session_date}):\n\n{session.ai_evaluation_coach}")
    await query.edit_message_text(chunks[0])
    for chunk in chunks[1:]:
        await query.message.chat.send_message(chunk)


async def notify_student(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پیام مستقیم کوچ را برای یک دانش‌آموز خاص ارسال می‌کند. فرمت: /notify <telegram_id> <متن>"""
    if update.message is None or not _is_coach(update):
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("فرمت درست: /notify <telegram_id> <متن پیام>")
        return

    try:
        target_telegram_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("آیدی تلگرام باید عدد باشه.")
        return

    text = " ".join(context.args[1:])

    try:
        await context.bot.send_message(chat_id=target_telegram_id, text=f"📩 پیام از کوچت:\n\n{text}")
        delivered = True
    except Exception:
        logger.exception("ارسال پیام کوچ به دانش‌آموز ناموفق بود")
        delivered = False

    await update.message.reply_text("پیام ارسال شد ✅" if delivered else "ارسال پیام ناموفق بود.")
    if not delivered:
        return

    target_user = get_user_by_telegram_id(target_telegram_id)
    if target_user is not None:
        try:
            create_coach_note(target_user.id, text)
        except Exception:
            logger.exception("ثبت یادداشت کوچ ناموفق بود")


async def add_private_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """یادداشت خصوصی کوچ روی یک دانش‌آموز را ذخیره می‌کند (بدون ارسال پیام به دانش‌آموز)."""
    if update.message is None or not _is_coach(update):
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("فرمت درست: /coachnote <telegram_id> <متن یادداشت خصوصی>")
        return

    try:
        target_telegram_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("آیدی تلگرام باید عدد باشه.")
        return

    target_user = get_user_by_telegram_id(target_telegram_id)
    if target_user is None:
        await update.message.reply_text("این دانش‌آموز پیدا نشد.")
        return

    text = " ".join(context.args[1:])
    try:
        create_coach_note(target_user.id, text)
        note_saved = True
    except Exception:
        logger.exception("ثبت یادداشت خصوصی کوچ ناموفق بود")
        note_saved = False

    await update.message.reply_text(
        "یادداشت خصوصی ثبت شد ✅ (به دانش‌آموز ارسال نمی‌شه)" if note_saved else "مشکلی پیش اومد."
    )


async def broadcast_to_students(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """یک پیام واحد را برای همه‌ی دانش‌آموزها ارسال می‌کند. فرمت: /broadcast <متن>"""
    if update.message is None or not _is_coach(update):
        return

    if not context.args:
        await update.message.reply_text("فرمت درست: /broadcast <متن پیام>")
        return

    text = " ".join(context.args)
    sent_count = 0
    for student in get_students():
        try:
            await context.bot.send_message(chat_id=student.telegram_id, text=f"📢 پیام از کوچ:\n\n{text}")
            sent_count += 1
        except Exception:
            logger.exception("ارسال broadcast به کاربر %s ناموفق بود", student.telegram_id)

    await update.message.reply_text(f"پیام برای {sent_count} دانش‌آموز ارسال شد ✅")


async def export_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """گزارش PDF یک دانش‌آموز را می‌سازد و ارسال می‌کند. فرمت: /export <telegram_id>"""
    if update.message is None or not _is_coach(update):
        return

    if not context.args:
        await update.message.reply_text("فرمت درست: /export <telegram_id>")
        return

    try:
        target_telegram_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("آیدی تلگرام باید عدد باشه.")
        return

    target_user = get_user_by_telegram_id(target_telegram_id)
    if target_user is None:
        await update.message.reply_text("این دانش‌آموز پیدا نشد.")
        return

    sessions = get_recent_sessions(target_user.id, slot_type="evening_report", limit=14)
    if not sessions:
        await update.message.reply_text("این دانش‌آموز هنوز گزارش شبانه‌ای نداده.")
        return

    try:
        pdf_bytes = build_report_pdf(
            target_user.first_name or "دانش‌آموز",
            [(s.session_date, s.ai_evaluation_coach or "") for s in sessions],
        )
        await update.message.reply_document(
            document=io.BytesIO(pdf_bytes), filename=f"report_{target_telegram_id}.pdf"
        )
    except Exception:
        logger.exception("ساخت/ارسال PDF گزارش ناموفق بود")
        await update.message.reply_text("مشکلی توی ساخت PDF پیش اومد.")


def build_coach_handlers() -> list:
    """تمام هندلرهای مخصوص کوچ را می‌سازد."""
    return [
        CommandHandler("students", list_students),
        CommandHandler("report", report_menu),
        CommandHandler("notify", notify_student),
        CommandHandler("coachnote", add_private_note),
        CommandHandler("broadcast", broadcast_to_students),
        CommandHandler("export", export_report),
        CallbackQueryHandler(show_student_report, pattern="^coach_report:"),
    ]
