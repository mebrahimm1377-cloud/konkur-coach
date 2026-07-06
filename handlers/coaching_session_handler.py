"""فلوی نوبت‌های کوچینگ صبحگاهی (لیزر کوچینگ) و شبانه (گزارش‌گیری کامل)."""

import json
import logging
import re
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from ai.client import ai_client
from ai.coaching_questions import EVENING_REPORT_QUESTIONS, MORNING_LASER_QUESTIONS, WEEKLY_PLANNING_QUESTIONS
from ai.schedule_image import build_weekly_schedule_image
from config import config
from database.db import (
    award_points,
    get_linked_parents,
    get_or_create_user,
    get_pulse_checks_for_date,
    get_recent_coach_notes,
    get_recent_sessions,
    record_evening_completion,
    save_coaching_session,
    set_needs_gentle_tone,
)
from database.models import User
from utils.telegram_text import send_long_message, split_for_telegram

_PULSE_LABELS = {"studying": "در حال مطالعه", "tired": "خسته ولی ادامه‌دهنده", "not_started": "هنوز شروع‌نکرده"}

logger = logging.getLogger(__name__)

AWAITING_ANSWER = 0

_QUESTION_BANKS: dict[str, list[str]] = {
    "morning_laser": MORNING_LASER_QUESTIONS,
    "evening_report": EVENING_REPORT_QUESTIONS,
    "weekly_planning": WEEKLY_PLANNING_QUESTIONS,
}

_POINTS_FOR_SLOT = {"morning_laser": 5, "weekly_planning": 8}
_STREAK_MILESTONES = {7, 14, 30, 60, 100}
_MOOD_QUESTION_INDEX = 7  # "حال روحی‌ت امروز از ۱ تا ۵ چند بود؟"

_SLOT_KEY = "coaching_slot_type"
_QIDX_KEY = "coaching_question_index"
_ANSWERS_KEY = "coaching_answers"

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def _extract_int(text: str) -> int | None:
    """اولین عدد داخل یک متن فارسی/انگلیسی را استخراج می‌کند."""
    match = re.search(r"\d+", text.translate(_PERSIAN_DIGITS))
    return int(match.group()) if match else None


def _questions_for(slot_type: str) -> list[str]:
    """لیست سوالات مربوط به یک نوع نوبت را برمی‌گرداند."""
    return _QUESTION_BANKS[slot_type]


async def start_coaching_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نوبت کوچینگ را با اولین سوال شروع می‌کند."""
    query = update.callback_query
    if query is None or query.data is None:
        return ConversationHandler.END

    await query.answer()
    slot_type = query.data.split(":", 1)[1]
    questions = _questions_for(slot_type)

    context.user_data[_SLOT_KEY] = slot_type
    context.user_data[_QIDX_KEY] = 0
    context.user_data[_ANSWERS_KEY] = []

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(chat_id=query.message.chat.id, text=questions[0])
    return AWAITING_ANSWER


async def receive_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پاسخ فعلی را ذخیره و سوال بعدی را می‌پرسد یا نوبت را جمع‌بندی می‌کند."""
    if update.message is None or update.message.text is None:
        return AWAITING_ANSWER

    slot_type = context.user_data.get(_SLOT_KEY)
    qidx = context.user_data.get(_QIDX_KEY, 0)
    questions = _questions_for(slot_type)

    answers: list[dict[str, str]] = context.user_data.setdefault(_ANSWERS_KEY, [])
    answers.append({"question": questions[qidx], "answer": update.message.text})

    next_idx = qidx + 1
    if next_idx < len(questions):
        context.user_data[_QIDX_KEY] = next_idx
        await update.message.reply_text(questions[next_idx])
        return AWAITING_ANSWER

    return await _finish_session(update, context, slot_type, answers)


async def _finish_session(
    update: Update, context: ContextTypes.DEFAULT_TYPE, slot_type: str, answers: list[dict[str, str]]
) -> int:
    """نوبت کوچینگ را ذخیره می‌کند و در صورت نیاز ارزیابی هوش مصنوعی را می‌سازد و پخش می‌کند."""
    telegram_user = update.effective_user
    session_date = datetime.now().strftime("%Y-%m-%d")

    student_user = None
    try:
        student_user = get_or_create_user(telegram_user.id, telegram_user.first_name)
        save_coaching_session(
            user_id=student_user.id,
            slot_type=slot_type,
            session_date=session_date,
            answers_json=json.dumps(answers, ensure_ascii=False),
        )
    except Exception:
        logger.exception("خطا در ذخیره‌ی نوبت کوچینگ")

    if slot_type in ("morning_laser", "weekly_planning"):
        if student_user is not None:
            try:
                award_points(student_user.id, _POINTS_FOR_SLOT.get(slot_type, 0))
            except Exception:
                logger.exception("خطا در ثبت امتیاز")

        if slot_type == "morning_laser":
            await update.message.reply_text("عالی بود! امروز رو با همین انرژی شروع کن 🚀 موفق باشی.")
        else:
            await update.message.reply_text("برنامه‌ی هفته‌ت ثبت شد 📅 موفق باشی، هفته‌ی خوبی داشته باشی!")
            try:
                image_bytes = build_weekly_schedule_image(answers)
                await update.message.chat.send_photo(photo=image_bytes)
            except Exception:
                logger.exception("خطا در ساخت تصویر برنامه‌ی هفتگی")

        _clear_session_state(context)
        return ConversationHandler.END

    # evening_report: ارزیابی کامل (سه نسخه‌ی متفاوت) بساز و برای دانش‌آموز، کوچ و والدین ارسال کن
    await update.message.chat.send_action(action="typing")
    qa_pairs = [(item["question"], item["answer"]) for item in answers]
    extra_context = _build_extra_context(student_user.id, session_date) if student_user is not None else None

    student_eval = await ai_client.generate_evaluation(qa_pairs, audience="student", extra_context=extra_context)
    coach_eval = await ai_client.generate_evaluation(qa_pairs, audience="coach", extra_context=extra_context)
    parent_eval = await ai_client.generate_evaluation(qa_pairs, audience="parent", extra_context=extra_context)

    new_streak = 0
    try:
        if student_user is not None:
            save_coaching_session(
                user_id=student_user.id,
                slot_type=slot_type,
                session_date=session_date,
                answers_json=json.dumps(answers, ensure_ascii=False),
                ai_evaluation=student_eval,
                ai_evaluation_coach=coach_eval,
                ai_evaluation_parent=parent_eval,
            )
            new_streak = record_evening_completion(student_user.id, session_date, points_awarded=10)
    except Exception:
        logger.exception("خطا در ذخیره‌ی ارزیابی نوبت شبانه")

    closing_message = f"ممنون بابت گزارش امروزت 🙏\n\n📋 ارزیابی امروز:\n{student_eval}"
    if new_streak in _STREAK_MILESTONES:
        closing_message += f"\n\n🎉 تبریک! به استریک {new_streak} روزه رسیدی، فوق‌العاده‌ای!"
    closing_chunks = split_for_telegram(closing_message)
    await update.message.reply_text(closing_chunks[0])
    for chunk in closing_chunks[1:]:
        await update.message.chat.send_message(chunk)

    if student_user is not None:
        await _broadcast_evening_digest(context, student_user, coach_eval, parent_eval)
        _update_gentle_tone_flag(student_user.id)
        await _check_and_alert_risk(context, student_user, answers)

    _clear_session_state(context)
    return ConversationHandler.END


def _update_gentle_tone_flag(student_user_id: int) -> None:
    """اگه روند ۳ گزارش اخیر افت واضح حال‌روحی نشون بده، لحن ملایم‌تر رو فعال می‌کنه."""
    try:
        recent = get_recent_sessions(student_user_id, slot_type="evening_report", limit=3)
        moods = []
        for session in recent:
            answers = json.loads(session.answers)
            if len(answers) > _MOOD_QUESTION_INDEX:
                mood = _extract_int(answers[_MOOD_QUESTION_INDEX]["answer"])
                if mood is not None:
                    moods.append(mood)

        needs_gentle = len(moods) >= 2 and sum(moods) / len(moods) <= 2
        set_needs_gentle_tone(student_user_id, needs_gentle)
    except Exception:
        logger.exception("خطا در به‌روزرسانی فلگ لحن ملایم")


async def _check_and_alert_risk(context: ContextTypes.DEFAULT_TYPE, student_user: User, answers: list[dict[str, str]]) -> None:
    """در صورت وجود نشونه‌ی ریسک جدی (حال‌روحی خیلی پایین یا چند pulse منفی)، بلافاصله به کوچ هشدار می‌دهد."""
    try:
        mood = _extract_int(answers[_MOOD_QUESTION_INDEX]["answer"]) if len(answers) > _MOOD_QUESTION_INDEX else None
        if mood is not None and mood <= 1:
            await context.bot.send_message(
                chat_id=config.coach_telegram_id,
                text=(
                    f"🚨 هشدار: {student_user.first_name or 'یک دانش‌آموز'} امروز حال روحی خیلی پایینی "
                    "(۱ از ۵) گزارش کرد. شاید بهتره زودتر باهاش صحبت کنی."
                ),
            )
    except Exception:
        logger.exception("خطا در بررسی ریسک زودهنگام")


def _build_extra_context(student_user_id: int, session_date: str) -> str | None:
    """رویدادهای دیگر امروز (pulse checkها و یادداشت‌های کوچ) را برای غنی‌سازی ارزیابی جمع می‌کند."""
    lines: list[str] = []

    try:
        for pulse in get_pulse_checks_for_date(student_user_id, session_date):
            label = _PULSE_LABELS.get(pulse.response, pulse.response)
            lines.append(f"- وضعیت سریع ({pulse.slot_type}): {label}")
    except Exception:
        logger.exception("خطا در خواندن pulse checkهای امروز")

    try:
        for note in get_recent_coach_notes(student_user_id, session_date):
            lines.append(f"- پیام کوچ به دانش‌آموز: {note.message}")
    except Exception:
        logger.exception("خطا در خواندن یادداشت‌های کوچ")

    return "\n".join(lines) if lines else None


async def _broadcast_evening_digest(
    context: ContextTypes.DEFAULT_TYPE, student_user: User, coach_eval: str, parent_eval: str
) -> None:
    """خلاصه‌ی متناسب با هر مخاطب را برای کوچ و والدین متصل ارسال می‌کند."""
    student_name = student_user.first_name or "دانش‌آموز"

    try:
        await send_long_message(context.bot, config.coach_telegram_id, f"📋 گزارش شبانه‌ی {student_name}:\n\n{coach_eval}")
    except Exception:
        logger.exception("ارسال دیجست شبانه به کوچ ناموفق بود")

    try:
        for parent in get_linked_parents(student_user.id):
            await send_long_message(context.bot, parent.telegram_id, f"📋 گزارش شبانه‌ی {student_name}:\n\n{parent_eval}")
    except Exception:
        logger.exception("ارسال دیجست شبانه به والدین ناموفق بود")


def _clear_session_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """داده‌های موقت نوبت جاری را از user_data پاک می‌کند."""
    context.user_data.pop(_SLOT_KEY, None)
    context.user_data.pop(_QIDX_KEY, None)
    context.user_data.pop(_ANSWERS_KEY, None)


async def cancel_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نوبت جاری را در صورت درخواست کاربر لغو می‌کند."""
    _clear_session_state(context)
    if update.message is not None:
        await update.message.reply_text("نوبت لغو شد. هر وقت خواستی می‌تونی دوباره شروع کنی.")
    return ConversationHandler.END


def build_coaching_session_conversation_handler() -> ConversationHandler:
    """ConversationHandler نوبت‌های کوچینگ صبح و شب را می‌سازد."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_coaching_session, pattern="^start_session:(morning_laser|evening_report|weekly_planning)$"
            )
        ],
        states={
            AWAITING_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_answer)],
        },
        fallbacks=[CommandHandler("cancel", cancel_session)],
        name="coaching_session",
        persistent=False,
    )


_SESSION_LABELS = {
    "morning_laser": "☀️ شروع لیزر کوچینگ صبحگاهی",
    "evening_report": "🌙 شروع گزارش‌گیری شبانه",
    "weekly_planning": "📅 شروع برنامه‌ریزی هفتگی",
}


def build_session_prompt_keyboard(slot_type: str) -> InlineKeyboardMarkup:
    """دکمه‌ی «شروع نوبت» برای پیام‌های زمان‌بندی‌شده را می‌سازد."""
    label = _SESSION_LABELS.get(slot_type, "شروع")
    return InlineKeyboardMarkup([[InlineKeyboardButton(text=label, callback_data=f"start_session:{slot_type}")]])
