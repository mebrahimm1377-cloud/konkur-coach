"""نقطه ورود اصلی؛ فقط راه‌اندازی و اجرای بات."""

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import config
from database.db import get_or_create_user, init_db
from handlers.challenge_handler import build_challenge_handlers
from handlers.chat_handler import handle_free_chat, handle_photo_message, handle_voice_message
from handlers.coach_actions_handler import build_coach_actions_conversation_handler
from handlers.coach_handler import build_coach_handlers
from handlers.coaching_session_handler import build_coaching_session_conversation_handler
from handlers.exam_mode_handler import build_exam_mode_handlers
from handlers.flashcard_handler import build_flashcard_handlers
from handlers.image_handler import build_image_conversation_handler
from handlers.menu_handler import build_menu_handlers, build_role_keyboard
from handlers.notes_handler import build_notes_handlers
from handlers.parent_handler import build_parent_handlers, handle_parent_token
from handlers.progress_handler import build_progress_handlers
from handlers.pulse_check_handler import build_pulse_check_handler
from handlers.quiz_handler import build_quiz_conversation_handler
from handlers.study_tools_handler import build_study_tools_handlers
from handlers.textbook_pages_handler import build_textbook_pages_handlers
from scheduler.agent_jobs import register_agent_jobs

logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور /start؛ کاربر را ثبت، دیپ‌لینک دعوت والدین را پردازش، و خوش‌آمدگویی می‌کند."""
    telegram_user = update.effective_user
    if telegram_user is None or update.message is None:
        return

    if context.args:
        handled_as_parent_invite = await handle_parent_token(update, context, context.args[0])
        if handled_as_parent_invite:
            return

    try:
        user = get_or_create_user(telegram_user.id, telegram_user.first_name)
    except Exception:
        logger.exception("خطا در ثبت کاربر هنگام /start")
        user = None

    if telegram_user.id == config.coach_telegram_id:
        await update.message.reply_text(
            "سلام کوچ عزیز 👋 از دکمه‌های پایین صفحه به قابلیت‌ها دسترسی داری، یا مستقیم دستور بنویس.",
            reply_markup=build_role_keyboard("coach"),
        )
        return

    if user is not None and user.role == "parent":
        await update.message.reply_text(
            "سلام! از دکمه‌ی پایین صفحه گزارش فرزندتون رو ببینید.",
            reply_markup=build_role_keyboard("parent"),
        )
        return

    await update.message.reply_text(
        "سلام! من کوچ تحصیلی هوشمندتم 🎯\n"
        "هر سوالی درباره درس و برنامه‌ریزی کنکور داشتی بپرس — می‌تونی متن بنویسی، "
        "پیام صوتی بفرستی، یا عکس یه برگه/دفترچه رو برام بفرستی تا تحلیلش کنم.\n\n"
        f"هر روز ۵ بار باهات چک این می‌کنم: {config.morning_laser_hour:02d}:{config.morning_laser_minute:02d} "
        "لیزر کوچینگ صبحگاهی، سه نوبت میان‌روز با پیام انگیزشی، و "
        f"{config.evening_report_hour:02d}:{config.evening_report_minute:02d} گزارش‌گیری کامل شبانه.\n\n"
        "از دکمه‌های پایین صفحه به همه‌ی قابلیت‌ها دسترسی داری 👇",
        reply_markup=build_role_keyboard("student"),
    )


def main() -> None:
    """بات را می‌سازد، هندلرها و جاب‌های زمان‌بندی را ثبت و اجرا می‌کند."""
    init_db()

    application = Application.builder().token(config.telegram_bot_token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(build_coaching_session_conversation_handler())
    application.add_handler(build_quiz_conversation_handler())
    application.add_handler(build_coach_actions_conversation_handler())
    application.add_handler(build_pulse_check_handler())
    application.add_handler(build_image_conversation_handler())
    for handler in build_study_tools_handlers():
        application.add_handler(handler)
    for handler in build_coach_handlers():
        application.add_handler(handler)
    for handler in build_parent_handlers():
        application.add_handler(handler)
    for handler in build_progress_handlers():
        application.add_handler(handler)
    for handler in build_notes_handlers():
        application.add_handler(handler)
    for handler in build_exam_mode_handlers():
        application.add_handler(handler)
    for handler in build_flashcard_handlers():
        application.add_handler(handler)
    for handler in build_challenge_handlers():
        application.add_handler(handler)
    for handler in build_textbook_pages_handlers():
        application.add_handler(handler)
    for handler in build_menu_handlers():
        application.add_handler(handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_chat))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))

    register_agent_jobs(application)

    logger.info("بات در حال اجراست...")
    # stop_signals=None چون این تابع ممکنه داخل یه ترد پس‌زمینه (نه ترد اصلی) اجرا
    # بشه (مثلاً روی PythonAnywhere که از یه ترد جدا برای اجرای بات استفاده می‌کنیم)،
    # و signal handler فقط توی ترد اصلی قابل ثبته.
    application.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=None)


if __name__ == "__main__":
    main()
