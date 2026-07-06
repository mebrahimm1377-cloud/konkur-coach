"""مدیریت دکمه‌ی وضعیت سریع (pulse check) در نوبت‌های میان‌روز."""

import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from ai.coaching_questions import MIDDAY_PULSE_OPTIONS
from database.db import get_or_create_user, save_pulse_check

logger = logging.getLogger(__name__)

_RESPONSE_LABELS = dict(MIDDAY_PULSE_OPTIONS)


def build_pulse_keyboard(slot_type: str) -> InlineKeyboardMarkup:
    """کیبورد اینلاین گزینه‌های وضعیت سریع را برای یک نوبت میان‌روز می‌سازد."""
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"pulse:{slot_type}:{value}")
        for value, label in MIDDAY_PULSE_OPTIONS
    ]
    return InlineKeyboardMarkup([buttons])


async def handle_pulse_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پاسخ کاربر به دکمه‌ی وضعیت سریع را ذخیره می‌کند."""
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return

    await query.answer()
    _, slot_type, response = query.data.split(":", 2)

    try:
        user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
        save_pulse_check(
            user_id=user.id,
            slot_type=slot_type,
            session_date=datetime.now().strftime("%Y-%m-%d"),
            response=response,
        )
    except Exception:
        logger.exception("خطا در ذخیره‌ی pulse check")

    label = _RESPONSE_LABELS.get(response, response)
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"ثبت شد: {label} ✅ به کارت ادامه بده!")


def build_pulse_check_handler() -> CallbackQueryHandler:
    """CallbackQueryHandler مستقل برای دکمه‌های وضعیت سریع را می‌سازد."""
    return CallbackQueryHandler(handle_pulse_check, pattern=r"^pulse:midday_\d:")
