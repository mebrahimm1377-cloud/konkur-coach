"""فلوی دکمه‌ای اقدامات کوچ (انتخاب دانش‌آموز با اسم، نه آیدی عددی)."""

import io
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from ai.pdf_export import build_report_pdf
from config import config
from database.db import (
    create_coach_note,
    get_or_create_user,
    get_recent_sessions,
    get_students,
    get_user_by_id,
    set_active_challenge,
)

logger = logging.getLogger(__name__)

AWAITING_STUDENT_PICK, AWAITING_TEXT = range(2)

_ACTION_KEY = "coach_action"
_TARGET_STUDENT_KEY = "coach_target_student_id"

_NEEDS_STUDENT_PICK = {"notify", "coachnote", "export"}
_PROMPT_AFTER_PICK = {
    "notify": "چه پیامی برای این دانش‌آموز بفرستم؟",
    "coachnote": "متن یادداشت خصوصی رو بنویس (به دانش‌آموز ارسال نمی‌شه):",
}
_DIRECT_PROMPTS = {
    "broadcast": "چه پیامی برای همه‌ی دانش‌آموزها بفرستم؟",
    "set_challenge": "متن چالش این هفته چیه؟",
}


def _is_coach(update: Update) -> bool:
    """بررسی می‌کند که آیا فرستنده همان کوچ تنظیم‌شده در .env است."""
    return update.effective_user is not None and update.effective_user.id == config.coach_telegram_id


async def start_coach_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """با توجه به دکمه‌ی منو، انتخاب دانش‌آموز یا پرسیدن متن را شروع می‌کند."""
    query = update.callback_query
    if query is None or query.data is None or not _is_coach(update):
        return ConversationHandler.END

    await query.answer()
    action = query.data.split(":", 1)[1]
    context.user_data[_ACTION_KEY] = action

    if action in _NEEDS_STUDENT_PICK:
        students = get_students()
        if not students:
            await query.message.reply_text("هنوز هیچ دانش‌آموزی ثبت نشده.")
            return ConversationHandler.END

        buttons = [
            [InlineKeyboardButton(text=student.first_name or f"کاربر {student.id}", callback_data=f"coach_pick:{student.id}")]
            for student in students
        ]
        await query.message.reply_text("یه دانش‌آموز رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))
        return AWAITING_STUDENT_PICK

    await query.message.reply_text(_DIRECT_PROMPTS[action])
    return AWAITING_TEXT


async def handle_student_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دانش‌آموز انتخاب‌شده را ذخیره و بر اساس نوع اقدام ادامه می‌دهد."""
    query = update.callback_query
    if query is None or query.data is None or not _is_coach(update):
        return ConversationHandler.END

    await query.answer()
    student_id = int(query.data.split(":", 1)[1])
    action = context.user_data.get(_ACTION_KEY)

    student = get_user_by_id(student_id)
    if student is None:
        await query.message.reply_text("این دانش‌آموز پیدا نشد.")
        return ConversationHandler.END

    if action == "export":
        await _send_export(query, context, student)
        return ConversationHandler.END

    context.user_data[_TARGET_STUDENT_KEY] = student_id
    await query.message.reply_text(f"{_PROMPT_AFTER_PICK[action]}\n(برای {student.first_name or 'این دانش‌آموز'})")
    return AWAITING_TEXT


async def _send_export(query, context: ContextTypes.DEFAULT_TYPE, student) -> None:
    """گزارش PDF یک دانش‌آموز را می‌سازد و ارسال می‌کند."""
    sessions = get_recent_sessions(student.id, slot_type="evening_report", limit=14)
    if not sessions:
        await query.message.reply_text("این دانش‌آموز هنوز گزارش شبانه‌ای نداده.")
        return

    try:
        pdf_bytes = build_report_pdf(
            student.first_name or "دانش‌آموز",
            [(s.session_date, s.ai_evaluation_coach or "") for s in sessions],
        )
        await context.bot.send_document(
            chat_id=query.message.chat.id,
            document=io.BytesIO(pdf_bytes),
            filename=f"report_{student.telegram_id}.pdf",
        )
    except Exception:
        logger.exception("ساخت/ارسال PDF گزارش ناموفق بود")
        await query.message.reply_text("مشکلی توی ساخت PDF پیش اومد.")


async def receive_action_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """متن نهایی (پیام/یادداشت/چالش) را دریافت و اجرا می‌کند."""
    if update.message is None or update.message.text is None or not _is_coach(update):
        return ConversationHandler.END

    action = context.user_data.get(_ACTION_KEY)
    text = update.message.text

    if action == "broadcast":
        sent_count = 0
        for student in get_students():
            try:
                await context.bot.send_message(chat_id=student.telegram_id, text=f"📢 پیام از کوچ:\n\n{text}")
                sent_count += 1
            except Exception:
                logger.exception("ارسال broadcast به کاربر %s ناموفق بود", student.telegram_id)
        await update.message.reply_text(f"پیام برای {sent_count} دانش‌آموز ارسال شد ✅")

    elif action == "set_challenge":
        telegram_user = update.effective_user
        coach_user = get_or_create_user(telegram_user.id, telegram_user.first_name, role="coach")
        set_active_challenge(coach_user.id, text)
        for student in get_students():
            try:
                await context.bot.send_message(chat_id=student.telegram_id, text=f"🎯 چالش این هفته:\n\n{text}")
            except Exception:
                logger.exception("ارسال چالش به کاربر %s ناموفق بود", student.telegram_id)
        await update.message.reply_text("چالش ثبت و برای همه‌ی دانش‌آموزها ارسال شد ✅")

    elif action in ("notify", "coachnote"):
        student_id = context.user_data.get(_TARGET_STUDENT_KEY)
        student = get_user_by_id(student_id) if student_id else None
        if student is None:
            await update.message.reply_text("این دانش‌آموز پیدا نشد.")
        elif action == "notify":
            # عملیات اصلی (ارسال پیام + ثبت یادداشت) جدا از پیام تاییدیه انجام می‌شه تا اگه فقط
            # ارسال پیام تاییدیه با خطای شبکه مواجه بشه، به‌اشتباه به کاربر «ناموفق» گزارش نشه.
            try:
                await context.bot.send_message(chat_id=student.telegram_id, text=f"📩 پیام از کوچت:\n\n{text}")
                create_coach_note(student.id, text)
                notify_succeeded = True
            except Exception:
                logger.exception("ارسال پیام کوچ به دانش‌آموز ناموفق بود")
                notify_succeeded = False

            await update.message.reply_text("پیام ارسال شد ✅" if notify_succeeded else "ارسال پیام ناموفق بود.")
        else:
            try:
                create_coach_note(student.id, text)
                note_saved = True
            except Exception:
                logger.exception("ثبت یادداشت خصوصی کوچ ناموفق بود")
                note_saved = False

            await update.message.reply_text(
                "یادداشت خصوصی ثبت شد ✅ (به دانش‌آموز ارسال نمی‌شه)" if note_saved else "مشکلی پیش اومد."
            )

    _clear_state(context)
    return ConversationHandler.END


def _clear_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """داده‌های موقت فلوی جاری را پاک می‌کند."""
    context.user_data.pop(_ACTION_KEY, None)
    context.user_data.pop(_TARGET_STUDENT_KEY, None)


async def cancel_coach_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """فلوی جاری کوچ را لغو می‌کند."""
    _clear_state(context)
    if update.message is not None:
        await update.message.reply_text("لغو شد.")
    return ConversationHandler.END


def build_coach_actions_conversation_handler() -> ConversationHandler:
    """ConversationHandler دکمه‌ای اقدامات کوچ را می‌سازد."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_coach_action, pattern="^menu_start:(notify|coachnote|export|broadcast|set_challenge)$"
            )
        ],
        states={
            AWAITING_STUDENT_PICK: [CallbackQueryHandler(handle_student_pick, pattern="^coach_pick:")],
            AWAITING_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_action_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel_coach_action)],
        name="coach_actions",
        persistent=False,
    )
