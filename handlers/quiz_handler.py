"""فلوی کوییز تعاملی کنکوری (`/quiz <مبحث>`)."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ai.client import ai_client
from database.db import award_points, create_mistake, create_quiz_attempt, get_or_create_user

logger = logging.getLogger(__name__)

ASK_TOPIC, ANSWERING = range(2)

_TOPIC_KEY = "quiz_topic"
_QUESTIONS_KEY = "quiz_questions"
_QIDX_KEY = "quiz_question_index"
_SCORE_KEY = "quiz_score"

_PERSIAN_DIGITS = ["۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"]
_POINTS_PER_CORRECT = 3


async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """کوییز را شروع می‌کند؛ اگر مبحث در دستور داده شده باشد مستقیم می‌سازد، وگرنه می‌پرسد."""
    if update.message is None:
        return ConversationHandler.END

    if context.args:
        topic = " ".join(context.args)
        return await _generate_and_start(update, context, topic)

    await update.message.reply_text("چه مبحثی رو می‌خوای ازش کوییز بگیرم؟ (مثلاً «زیست فصل ۵» یا «مشتق»)")
    return ASK_TOPIC


async def start_quiz_from_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """کوییز را از طریق دکمه‌ی منو شروع می‌کند (همیشه با پرسیدن مبحث)."""
    query = update.callback_query
    if query is None:
        return ConversationHandler.END

    await query.answer()
    await query.message.reply_text("چه مبحثی رو می‌خوای ازش کوییز بگیرم؟ (مثلاً «زیست فصل ۵» یا «مشتق»)")
    return ASK_TOPIC


async def receive_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """مبحث دریافت‌شده را می‌گیرد و کوییز را می‌سازد."""
    if update.message is None or update.message.text is None:
        return ASK_TOPIC

    return await _generate_and_start(update, context, update.message.text)


async def _generate_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str) -> int:
    """کوییز را از AI می‌گیرد و اولین سوال را ارسال می‌کند."""
    await update.message.chat.send_action(action="typing")
    questions = await ai_client.generate_quiz(topic)

    if not questions:
        await update.message.reply_text("نتونستم برای این مبحث کوییز بسازم. لطفاً یه مبحث دیگه امتحان کن.")
        return ConversationHandler.END

    context.user_data[_TOPIC_KEY] = topic
    context.user_data[_QUESTIONS_KEY] = questions
    context.user_data[_QIDX_KEY] = 0
    context.user_data[_SCORE_KEY] = 0

    await update.message.reply_text(f"کوییز «{topic}» آماده‌ست، {len(questions)} سوال داره. موفق باشی! 🎯")
    await _send_question(update.message.chat.id, context)
    return ANSWERING


async def _send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سوال جاری کوییز را با دکمه‌های گزینه‌ها ارسال می‌کند."""
    questions = context.user_data[_QUESTIONS_KEY]
    qidx = context.user_data[_QIDX_KEY]
    question = questions[qidx]

    buttons = [
        [InlineKeyboardButton(text=f"{_PERSIAN_DIGITS[i] if i < len(_PERSIAN_DIGITS) else i + 1}. {opt}", callback_data=f"quiz_answer:{i}")]
        for i, opt in enumerate(question["options"])
    ]
    text = f"سوال {qidx + 1} از {len(questions)}:\n\n{question['question']}"
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پاسخ انتخاب‌شده را می‌سنجد، بازخورد می‌دهد و سوال بعدی را می‌فرستد یا کوییز را جمع می‌کند."""
    query = update.callback_query
    if query is None or query.data is None:
        return ANSWERING

    await query.answer()
    selected_index = int(query.data.split(":", 1)[1])

    questions = context.user_data.get(_QUESTIONS_KEY)
    qidx = context.user_data.get(_QIDX_KEY, 0)
    question = questions[qidx]
    correct_index = question["correct_index"]
    is_correct = selected_index == correct_index

    if is_correct:
        context.user_data[_SCORE_KEY] = context.user_data.get(_SCORE_KEY, 0) + 1
        feedback = f"✅ درسته!\n{question.get('explanation', '')}"
    else:
        correct_option = question["options"][correct_index]
        feedback = f"❌ اشتباه بود. جواب درست: {correct_option}\n{question.get('explanation', '')}"

        telegram_user = update.effective_user
        if telegram_user is not None:
            try:
                user = get_or_create_user(telegram_user.id, telegram_user.first_name)
                topic = context.user_data.get(_TOPIC_KEY, "نامشخص")
                create_mistake(user.id, topic, question["question"], correct_option)
            except Exception:
                logger.exception("خطا در ثبت اشتباه کوییز")

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(feedback)

    next_idx = qidx + 1
    if next_idx < len(questions):
        context.user_data[_QIDX_KEY] = next_idx
        await _send_question(query.message.chat.id, context)
        return ANSWERING

    return await _finish_quiz(query.message.chat.id, update, context)


async def _finish_quiz(chat_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نتیجه‌ی نهایی کوییز را ذخیره و اعلام می‌کند."""
    telegram_user = update.effective_user
    topic = context.user_data.get(_TOPIC_KEY, "نامشخص")
    score = context.user_data.get(_SCORE_KEY, 0)
    total = len(context.user_data.get(_QUESTIONS_KEY, []))

    if telegram_user is not None:
        try:
            user = get_or_create_user(telegram_user.id, telegram_user.first_name)
            create_quiz_attempt(user.id, topic, score, total)
            award_points(user.id, score * _POINTS_PER_CORRECT)
        except Exception:
            logger.exception("خطا در ذخیره‌ی نتیجه‌ی کوییز")

    await context.bot.send_message(
        chat_id=chat_id, text=f"🏁 کوییز تموم شد! نمره‌ت: {score} از {total}\nآفرین بابت تلاشت 👏"
    )
    _clear_quiz_state(context)
    return ConversationHandler.END


def _clear_quiz_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """داده‌های موقت کوییز جاری را پاک می‌کند."""
    for key in (_TOPIC_KEY, _QUESTIONS_KEY, _QIDX_KEY, _SCORE_KEY):
        context.user_data.pop(key, None)


async def cancel_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """کوییز جاری را لغو می‌کند."""
    _clear_quiz_state(context)
    if update.message is not None:
        await update.message.reply_text("کوییز لغو شد.")
    return ConversationHandler.END


def build_quiz_conversation_handler() -> ConversationHandler:
    """ConversationHandler کوییز تعاملی را می‌سازد."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("quiz", start_quiz),
            CallbackQueryHandler(start_quiz_from_menu, pattern="^menu_start:quiz$"),
        ],
        states={
            ASK_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_topic)],
            ANSWERING: [CallbackQueryHandler(handle_answer, pattern="^quiz_answer:")],
        },
        fallbacks=[CommandHandler("cancel", cancel_quiz)],
        name="quiz_session",
        persistent=False,
    )
