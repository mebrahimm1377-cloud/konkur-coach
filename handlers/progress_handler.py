"""دستورات مربوط به روند پیشرفت، آرشیو گزارش‌ها و آمار گیمیفیکیشن دانش‌آموز."""

import json
import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from datetime import datetime, timedelta

from ai.client import ai_client
from database.db import get_mistakes, get_or_create_user, get_recent_sessions, get_students, set_paused_until
from database.models import CoachingSession
from utils.telegram_text import send_long_message

logger = logging.getLogger(__name__)

_HISTORY_LIMIT = 7
_PROGRESS_LIMIT = 7
_COMPARE_WINDOW = 7


def _format_sessions_for_ai(sessions: list[CoachingSession]) -> str:
    """چند نوبت شبانه‌ی اخیر را برای ورودی AI به متن ساده تبدیل می‌کند."""
    blocks = []
    for session in sessions:
        answers = json.loads(session.answers)
        qa_text = "\n".join(f"  {item['question']} -> {item['answer']}" for item in answers)
        blocks.append(f"تاریخ {session.session_date}:\n{qa_text}")
    return "\n\n".join(blocks)


async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تحلیل روند هفته‌ی اخیر دانش‌آموز را با استفاده از AI نشان می‌دهد."""
    if update.effective_chat is None or update.effective_user is None:
        return

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    sessions = get_recent_sessions(user.id, slot_type="evening_report", limit=_PROGRESS_LIMIT)

    if not sessions:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="هنوز داده‌ای برای تحلیل روند نداری. بعد از چند گزارش شبانه دوباره امتحان کن.",
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    sessions_text = _format_sessions_for_ai(sessions)
    summary = await ai_client.generate_progress_summary(sessions_text, audience="student")

    await send_long_message(context.bot, update.effective_chat.id, f"📈 تحلیل روند {len(sessions)} روز اخیرت:\n\n{summary}")


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """آرشیو گزارش‌های شبانه‌ی اخیر دانش‌آموز را لیست می‌کند."""
    if update.effective_chat is None or update.effective_user is None:
        return

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    sessions = get_recent_sessions(user.id, slot_type="evening_report", limit=_HISTORY_LIMIT)

    if not sessions:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="هنوز هیچ گزارش شبانه‌ای ثبت نشده.")
        return

    lines = ["🗂 آرشیو گزارش‌های اخیر:\n"]
    for session in sessions:
        snippet = (session.ai_evaluation or "").strip().splitlines()
        first_line = snippet[0] if snippet else "بدون ارزیابی"
        lines.append(f"• {session.session_date}: {first_line}")

    await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """استریک و امتیاز دانش‌آموز را نشان می‌دهد."""
    if update.effective_chat is None or update.effective_user is None:
        return

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)

    badge = "🥉"
    if user.longest_streak >= 30:
        badge = "🥇"
    elif user.longest_streak >= 14:
        badge = "🥈"

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "🏆 آمار تو:\n\n"
            f"🔥 استریک فعلی: {user.current_streak} روز\n"
            f"{badge} بهترین استریک: {user.longest_streak} روز\n"
            f"⭐ امتیاز کل: {user.points}"
        ),
    )


async def show_prediction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """یک تخمین کاملاً غیررسمی از روند کلی دانش‌آموز نشان می‌دهد."""
    if update.effective_chat is None or update.effective_user is None:
        return

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    sessions = get_recent_sessions(user.id, slot_type="evening_report", limit=_PROGRESS_LIMIT)

    if not sessions:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="هنوز داده‌ای برای تخمین نداری. بعد از چند گزارش شبانه دوباره امتحان کن."
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prediction = await ai_client.generate_prediction(_format_sessions_for_ai(sessions))
    await send_long_message(context.bot, update.effective_chat.id, f"🔮 یه برداشت کلی (نه پیش‌بینی دقیق):\n\n{prediction}")


async def show_comparison(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """۷ روز اخیر را با ۷ روز قبل‌تر مقایسه می‌کند."""
    if update.effective_chat is None or update.effective_user is None:
        return

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    sessions = get_recent_sessions(user.id, slot_type="evening_report", limit=_COMPARE_WINDOW * 2)

    if len(sessions) < 2:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="برای مقایسه به داده‌ی بیشتری نیاز داری. چند روز دیگه دوباره امتحان کن."
        )
        return

    recent = sessions[:_COMPARE_WINDOW]
    previous = sessions[_COMPARE_WINDOW:]

    if not previous:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="هنوز داده‌ی هفته‌ی قبل رو نداری که باهاش مقایسه کنم."
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    comparison = await ai_client.generate_comparison(_format_sessions_for_ai(recent), _format_sessions_for_ai(previous))
    await send_long_message(context.bot, update.effective_chat.id, f"⚖️ مقایسه‌ی این هفته با هفته‌ی قبل:\n\n{comparison}")


async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """رتبه‌بندی دانش‌آموزها بر اساس امتیاز را نشان می‌دهد."""
    if update.effective_chat is None:
        return

    students = sorted(get_students(), key=lambda s: s.points, reverse=True)
    if not students:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="هنوز دانش‌آموزی ثبت نشده.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 لیدربورد:\n"]
    for i, student in enumerate(students[:10]):
        prefix = medals[i] if i < len(medals) else f"{i + 1}."
        lines.append(f"{prefix} {student.first_name or 'بدون‌نام'} — {student.points} امتیاز")

    await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))


async def show_mistakes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بانک اشتباهات اخیر دانش‌آموز از کوییزها را نشان می‌دهد."""
    if update.effective_chat is None or update.effective_user is None:
        return

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    mistakes = get_mistakes(user.id)

    if not mistakes:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="هنوز اشتباهی ثبت نشده — همینطوری با کوییزها ادامه بده!"
        )
        return

    lines = ["📚 بانک اشتباهات اخیرت:\n"]
    for mistake in mistakes:
        lines.append(f"• [{mistake.topic}] {mistake.question}\n  جواب درست: {mistake.correct_answer}")

    await context.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines))


async def pause_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نوبت‌های خودکار را برای چند روز موقتاً خاموش می‌کند. فرمت: /pause <روز>"""
    if update.message is None or update.effective_user is None:
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("فرمت درست: /pause <تعداد روز> (مثلاً /pause 3)")
        return

    days = int(context.args[0])
    paused_until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    set_paused_until(user.id, paused_until)

    await update.message.reply_text(f"باشه، تا {paused_until} پیام‌های خودکار رو برات خاموش می‌کنم. استراحت خوبی داشته باش 🌿")


def build_progress_handlers() -> list:
    """هندلرهای مربوط به روند پیشرفت، آرشیو و آمار را می‌سازد."""
    return [
        CommandHandler("progress", show_progress),
        CommandHandler("history", show_history),
        CommandHandler("stats", show_stats),
        CommandHandler("predict", show_prediction),
        CommandHandler("compare", show_comparison),
        CommandHandler("leaderboard", show_leaderboard),
        CommandHandler("mistakes", show_mistakes),
        CommandHandler("pause", pause_agent),
    ]
