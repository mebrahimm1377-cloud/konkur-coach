"""منوی دکمه‌ای برای دسترسی راحت به قابلیت‌ها، مخصوص هر نقش (دانش‌آموز/کوچ/والد)."""

import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import config
from database.db import get_or_create_user
from handlers.challenge_handler import show_challenge
from handlers.coach_handler import list_students, report_menu
from handlers.notes_handler import list_notes
from handlers.parent_handler import invite_parent, my_student_report
from handlers.progress_handler import (
    show_comparison,
    show_history,
    show_leaderboard,
    show_mistakes,
    show_prediction,
    show_progress,
    show_stats,
)

logger = logging.getLogger(__name__)

# --- برچسب دسته‌ها (دکمه‌های ثابت پایین صفحه) ---
CAT_PROGRESS = "📊 پیشرفت من"
CAT_STUDY_TOOLS = "🛠 ابزار مطالعه"
CAT_QUIZ_FLASHCARD = "🧠 کوییز و فلش‌کارت"
CAT_NOTES_CHALLENGE = "📝 یادداشت و چالش"
CAT_SETTINGS = "⚙️ تنظیمات"

CAT_COACH_STUDENTS = "👥 دانش‌آموزها"
CAT_COACH_COMMS = "📣 ارتباط"
CAT_COACH_EXPORT = "📄 خروجی و چالش"

CAT_PARENT_REPORT = "📋 گزارش فرزندم"

_STUDENT_CATEGORIES = [CAT_PROGRESS, CAT_STUDY_TOOLS, CAT_QUIZ_FLASHCARD, CAT_NOTES_CHALLENGE, CAT_SETTINGS]
_COACH_CATEGORIES = [CAT_COACH_STUDENTS, CAT_COACH_COMMS, CAT_COACH_EXPORT]
_PARENT_CATEGORIES = [CAT_PARENT_REPORT]


def build_role_keyboard(role: str) -> ReplyKeyboardMarkup:
    """کیبورد ثابت پایین صفحه را متناسب با نقش کاربر می‌سازد."""
    if role == "coach":
        rows = [[KeyboardButton(CAT_COACH_STUDENTS), KeyboardButton(CAT_COACH_COMMS)], [KeyboardButton(CAT_COACH_EXPORT)]]
    elif role == "parent":
        rows = [[KeyboardButton(CAT_PARENT_REPORT)]]
    else:
        rows = [
            [KeyboardButton(CAT_PROGRESS), KeyboardButton(CAT_STUDY_TOOLS)],
            [KeyboardButton(CAT_QUIZ_FLASHCARD), KeyboardButton(CAT_NOTES_CHALLENGE)],
            [KeyboardButton(CAT_SETTINGS)],
        ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


# --- متن‌های راهنما برای قابلیت‌هایی که هنوز جایگزین دکمه‌ای ندارن ---
_INFO_TEXTS = {
    "flashcards_info": "برای ساخت فلش‌کارت بنویس:\n/flashcards <مبحث>\nمثال: /flashcards فرمول‌های مثلثات",
    "note_info": "برای ثبت یادداشت بنویس:\n/note <متن>\nمثال: /note مرور فرمول انتگرال جزءبه‌جزء",
    "exam_mode_info": "برای فعال‌سازی حالت امتحان بنویس:\n/exam_mode YYYY-MM-DD\nمثال: /exam_mode 2026-08-15\nبرای خاموش کردن: /exam_mode off",
    "pause_info": "برای استراحت موقت از نوبت‌های خودکار بنویس:\n/pause <تعداد روز>\nمثال: /pause 3",
    "pages_info": "برای دیدن عکس واقعی صفحات کتاب (شامل جدول‌ها و نمودارها) بنویس:\n/pages <موضوع>\nمثال: /pages میتوز",
}

# --- قابلیت‌های بدون‌آرگومان که مستقیم از منو اجرا می‌شن ---
_DIRECT_ACTIONS = {
    "progress": show_progress,
    "history": show_history,
    "stats": show_stats,
    "predict": show_prediction,
    "compare": show_comparison,
    "leaderboard": show_leaderboard,
    "mistakes": show_mistakes,
    "notes": list_notes,
    "challenge": show_challenge,
    "invite_parent": invite_parent,
    "students": list_students,
    "report": report_menu,
    "mystudent": my_student_report,
}


def _category_keyboard(items: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """کیبورد اینلاین یک دسته را از لیست (برچسب, callback_data) می‌سازد."""
    return InlineKeyboardMarkup([[InlineKeyboardButton(text=label, callback_data=data)] for label, data in items])


_CATEGORY_ITEMS: dict[str, list[tuple[str, str]]] = {
    CAT_PROGRESS: [
        ("📈 تحلیل روند هفته", "menu_action:progress"),
        ("🗂 آرشیو گزارش‌ها", "menu_action:history"),
        ("🏆 آمار من (استریک/امتیاز)", "menu_action:stats"),
        ("🔮 یه برداشت کلی", "menu_action:predict"),
        ("⚖️ مقایسه با هفته‌ی قبل", "menu_action:compare"),
        ("🥇 لیدربورد", "menu_action:leaderboard"),
        ("📚 بانک اشتباهاتم", "menu_action:mistakes"),
    ],
    CAT_STUDY_TOOLS: [
        ("✂️ خلاصه‌سازی", "menu_start:summarize"),
        ("🧭 حل قدم‌به‌قدم", "menu_start:solve"),
        ("✍️ بررسی دست‌خط (عکس)", "menu_start:handwriting"),
        ("🖼 ساخت تصویر آموزشی", "menu_start:image"),
        ("📖 عکس صفحه‌ی کتاب", "menu_action:pages_info"),
    ],
    CAT_QUIZ_FLASHCARD: [
        ("❓ کوییز جدید", "menu_start:quiz"),
        ("🗂 فلش‌کارت جدید", "menu_action:flashcards_info"),
    ],
    CAT_NOTES_CHALLENGE: [
        ("📝 یادداشت جدید", "menu_action:note_info"),
        ("📋 یادداشت‌های من", "menu_action:notes"),
        ("🎯 چالش این هفته", "menu_action:challenge"),
    ],
    CAT_SETTINGS: [
        ("⏳ حالت امتحان", "menu_action:exam_mode_info"),
        ("🌿 استراحت موقت", "menu_action:pause_info"),
        ("👪 دعوت والدین", "menu_action:invite_parent"),
    ],
    CAT_COACH_STUDENTS: [
        ("👥 لیست دانش‌آموزها", "menu_action:students"),
        ("📋 گزارش یه دانش‌آموز", "menu_action:report"),
        ("🥇 لیدربورد", "menu_action:leaderboard"),
    ],
    CAT_COACH_COMMS: [
        ("📩 پیام به دانش‌آموز", "menu_start:notify"),
        ("🔒 یادداشت خصوصی", "menu_start:coachnote"),
        ("📢 پیام همگانی", "menu_start:broadcast"),
    ],
    CAT_COACH_EXPORT: [
        ("📄 خروجی PDF گزارش", "menu_start:export"),
        ("🎯 تعریف چالش هفتگی", "menu_start:set_challenge"),
    ],
}


async def show_category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """با تشخیص متن دکمه‌ی دسته، کیبورد اینلاین همان دسته را نشان می‌دهد."""
    if update.message is None or update.message.text is None:
        return

    if update.message.text == CAT_PARENT_REPORT:
        await my_student_report(update, context)
        return

    items = _CATEGORY_ITEMS.get(update.message.text)
    if items is None:
        return

    await update.message.reply_text("یکی رو انتخاب کن:", reply_markup=_category_keyboard(items))


async def handle_menu_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دکمه‌ی اینلاین انتخاب‌شده را اجرا می‌کند (یا راهنمای فرمت را نشان می‌دهد)."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    action_id = query.data.split(":", 1)[1]

    if action_id in _INFO_TEXTS:
        await query.answer()
        await context.bot.send_message(chat_id=query.message.chat.id, text=_INFO_TEXTS[action_id])
        return

    handler_fn = _DIRECT_ACTIONS.get(action_id)
    if handler_fn is None:
        await query.answer()
        return

    await query.answer()
    await handler_fn(update, context)


async def show_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور /menu؛ کیبورد ثابت متناسب با نقش کاربر را دوباره نشان می‌دهد."""
    if update.message is None or update.effective_user is None:
        return

    role = "student"
    if update.effective_user.id == config.coach_telegram_id:
        role = "coach"

    user = get_or_create_user(update.effective_user.id, update.effective_user.first_name)
    if role != "coach" and user.role == "parent":
        role = "parent"

    await update.message.reply_text("منو:", reply_markup=build_role_keyboard(role))


def build_menu_handlers() -> list:
    """هندلرهای منو (دکمه‌های ثابت + کیبورد اینلاین هر دسته) را می‌سازد."""
    all_category_texts = _STUDENT_CATEGORIES + _COACH_CATEGORIES + _PARENT_CATEGORIES
    category_pattern = f"^({'|'.join(re.escape(t) for t in all_category_texts)})$"

    return [
        CommandHandler("menu", show_menu_command),
        MessageHandler(filters.Regex(category_pattern), show_category_menu),
        CallbackQueryHandler(handle_menu_action, pattern="^menu_action:"),
    ]
