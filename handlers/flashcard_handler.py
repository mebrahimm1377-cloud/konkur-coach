"""فلش‌کارت‌های مروری با زمان‌بندی spaced-repetition ساده (`/flashcards <مبحث>`)."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from ai.client import ai_client
from database.db import create_flashcards, get_flashcard_by_id, get_or_create_user, reschedule_flashcard
from database.models import Flashcard

logger = logging.getLogger(__name__)


async def make_flashcards(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """فلش‌کارت‌های جدید درباره‌ی یک مبحث می‌سازد. فرمت: /flashcards <مبحث>"""
    if update.message is None or update.effective_user is None:
        return

    if not context.args:
        await update.message.reply_text("فرمت درست: /flashcards <مبحث> (مثلاً /flashcards فرمول‌های مثلثات)")
        return

    topic = " ".join(context.args)
    await update.message.chat.send_action(action="typing")

    cards = await ai_client.generate_flashcards(topic)
    if not cards:
        await update.message.reply_text("نتونستم برای این مبحث فلش‌کارت بسازم. یه مبحث دیگه امتحان کن.")
        return

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    create_flashcards(user.id, topic, cards)

    await update.message.reply_text(
        f"{len(cards)} فلش‌کارت درباره‌ی «{topic}» ساخته شد 🗂 هر روز برای مرورشون بهت پیام می‌دم."
    )


async def send_flashcard_prompt(bot, chat_id: int, card: Flashcard) -> None:
    """یک فلش‌کارت را با دکمه‌ی «دیدن جواب» ارسال می‌کند."""
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(text="🔍 دیدن جواب", callback_data=f"flashcard_reveal:{card.id}")]]
    )
    await bot.send_message(
        chat_id=chat_id, text=f"🗂 فلش‌کارت ({card.topic}):\n\n{card.question}", reply_markup=keyboard
    )


async def reveal_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """جواب فلش‌کارت را نشان داده و دکمه‌های خودارزیابی را می‌فرستد."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()
    flashcard_id = int(query.data.split(":", 1)[1])

    card = get_flashcard_by_id(flashcard_id)
    answer_text = card.answer if card is not None else "(جواب پیدا نشد)"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(text="✅ بلد بودم", callback_data=f"flashcard_grade:{flashcard_id}:1"),
                InlineKeyboardButton(text="❌ بلد نبودم", callback_data=f"flashcard_grade:{flashcard_id}:0"),
            ]
        ]
    )
    await query.edit_message_text(f"{query.message.text}\n\n💡 جواب: {answer_text}", reply_markup=None)
    await query.message.reply_text("خودت رو بسنج:", reply_markup=keyboard)


async def grade_flashcard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """خودارزیابی کاربر را ذخیره و بازه‌ی مرور بعدی را تنظیم می‌کند."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()
    _, flashcard_id_str, remembered_str = query.data.split(":", 2)
    remembered = remembered_str == "1"

    try:
        reschedule_flashcard(int(flashcard_id_str), remembered)
    except Exception:
        logger.exception("خطا در زمان‌بندی مجدد فلش‌کارت")

    feedback = "عالی، مرور بعدیش دیرتر میاد 👍" if remembered else "اشکالی نداره، فردا دوباره مرورش می‌کنیم 💪"
    await query.edit_message_text(feedback, reply_markup=None)


def build_flashcard_handlers() -> list:
    """هندلرهای دستور و دکمه‌های فلش‌کارت را می‌سازد."""
    return [
        CommandHandler("flashcards", make_flashcards),
        CallbackQueryHandler(reveal_answer, pattern="^flashcard_reveal:"),
        CallbackQueryHandler(grade_flashcard, pattern="^flashcard_grade:"),
    ]
