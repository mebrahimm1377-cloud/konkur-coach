"""مدیریت پیام‌های آزاد کاربر (متن، عکس، صدا) و ارسال آن‌ها به AI."""

import io
import logging
from datetime import datetime

from telegram import Message, Update
from telegram.ext import ContextTypes

from ai.client import ai_client
from ai.textbook_pages import render_pages
from ai.textbook_rag import textbook_rag
from ai.tts import synthesize_speech
from config import config
from database.db import get_or_create_user
from database.models import User
from utils.telegram_text import split_for_telegram

logger = logging.getLogger(__name__)

HISTORY_KEY = "chat_history"


async def _reply_long_text(message, text: str) -> None:
    """متن طولانی (که ممکنه از سقف ۴۰۹۶ کاراکتری تلگرام رد بشه) را در چند پیام پشت‌سرهم می‌فرستد."""
    chunks = split_for_telegram(text)
    await message.reply_text(chunks[0])
    for chunk in chunks[1:]:
        await message.chat.send_message(chunk)


def _remember_user(telegram_user) -> User | None:
    """کاربر تلگرامی را در دیتابیس ثبت می‌کند (در صورت نبود) و رکورد او را برمی‌گرداند."""
    try:
        return get_or_create_user(telegram_user.id, telegram_user.first_name)
    except Exception:
        logger.exception("خطا در ثبت کاربر")
        return None


def _build_extra_context(user: User | None) -> str | None:
    """شمارش‌معکوس امتحان (در صورت فعال بودن) و نیاز به لحن ملایم‌تر را برای تزریق به AI می‌سازد."""
    if user is None:
        return None

    lines: list[str] = []

    if user.exam_date:
        try:
            days_left = (datetime.strptime(user.exam_date, "%Y-%m-%d") - datetime.now()).days
            if days_left >= 0:
                lines.append(f"این دانش‌آموز {days_left} روز تا امتحانش مونده (حالت امتحان فعاله)؛ لحن رو متمرکزتر و فشرده‌تر کن.")
        except ValueError:
            pass

    if user.needs_gentle_tone:
        lines.append("این دانش‌آموز اخیراً حال روحی پایینی داشته؛ لحن رو ملایم‌تر و کمتر فشار‌آور کن.")

    return "\n".join(lines) if lines else None


def _push_history(context: ContextTypes.DEFAULT_TYPE, user_text: str, reply: str) -> None:
    """یک رد و بدل پیام را به تاریخچه مکالمه اضافه و تاریخچه را کوتاه می‌کند."""
    history: list[dict[str, str]] = context.user_data.setdefault(HISTORY_KEY, [])
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply})

    max_messages = config.chat_history_limit * 2
    if len(history) > max_messages:
        del history[:-max_messages]


async def _maybe_send_textbook_page(message: Message, query: str) -> None:
    """اگه سوال کاربر به‌وضوح به یک بخش خاص از کتاب درسی مربوط باشه، تصویر همون صفحه رو
    هم خودکار می‌فرسته (علاوه بر پاسخ متنی)، تا کاربر مجبور نباشه جداگانه /pages بزنه."""
    chunk = textbook_rag.top_hit(query)
    if chunk is None:
        return

    images = render_pages(chunk["book_path"], chunk["page_start"], chunk["page_end"])
    if not images:
        return

    await message.chat.send_action(action="upload_photo")
    caption = f"📖 {chunk['subject']} پایه {chunk['grade']} — صفحه {chunk['page_start']}"
    for i, image_bytes in enumerate(images):
        try:
            await message.reply_photo(photo=io.BytesIO(image_bytes), caption=caption if i == 0 else None)
        except Exception:
            logger.exception("خطا در ارسال خودکار تصویر صفحه‌ی کتاب")


async def _maybe_reply_voice(message: Message, text: str) -> None:
    """پاسخ متنی رو به صدا تبدیل و به‌عنوان پیام صوتی هم می‌فرسته (برای پاسخ به پیام صوتی کاربر)."""
    audio_bytes = await synthesize_speech(text)
    if not audio_bytes:
        return
    try:
        # edge-tts خروجی MP3 می‌دهد؛ send_voice فقط OGG/Opus را با مدت‌زمان درست نمایش می‌دهد،
        # پس از reply_audio (که MP3 را هم به‌درستی پخش می‌کند) استفاده می‌کنیم.
        await message.reply_audio(audio=io.BytesIO(audio_bytes), filename="pasokh.mp3")
    except Exception:
        logger.exception("خطا در ارسال پاسخ صوتی")


async def handle_free_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پیام متنی آزاد کاربر را دریافت، به AI ارسال و پاسخ را برمی‌گرداند."""
    if update.message is None or update.message.text is None or update.effective_user is None:
        return

    user_message = update.message.text
    user = _remember_user(update.effective_user)

    history: list[dict[str, str]] = context.user_data.setdefault(HISTORY_KEY, [])

    await update.message.chat.send_action(action="typing")
    reply = await ai_client.get_reply(history, user_message, extra_context=_build_extra_context(user))

    _push_history(context, user_message, reply)
    await _reply_long_text(update.message, reply)
    await _maybe_send_textbook_page(update.message, user_message)


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عکس ارسالی کاربر (مثلاً برگه تمرین یا یادداشت درسی) را تحلیل می‌کند."""
    if update.message is None or not update.message.photo or update.effective_user is None:
        return

    _remember_user(update.effective_user)

    await update.message.chat.send_action(action="upload_photo")

    largest_photo = update.message.photo[-1]
    photo_file = await largest_photo.get_file()
    image_bytes = bytes(await photo_file.download_as_bytearray())

    reply = await ai_client.get_vision_reply(image_bytes, update.message.caption)

    _push_history(context, update.message.caption or "[تصویر ارسال شد]", reply)
    await _reply_long_text(update.message, reply)


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پیام صوتی کاربر را به متن تبدیل کرده و مثل یک پیام متنی پاسخ می‌دهد."""
    if update.message is None or update.effective_user is None:
        return

    voice = update.message.voice or update.message.audio
    if voice is None:
        return

    user = _remember_user(update.effective_user)

    await update.message.chat.send_action(action="typing")

    voice_file = await voice.get_file()
    audio_bytes = bytes(await voice_file.download_as_bytearray())

    transcribed_text = await ai_client.transcribe_audio(audio_bytes, "voice.ogg")
    if not transcribed_text:
        await update.message.reply_text("متاسفانه نتونستم صداتو تشخیص بدم. می‌شه دوباره امتحان کنی یا به‌صورت متنی بنویسی؟")
        return

    history: list[dict[str, str]] = context.user_data.setdefault(HISTORY_KEY, [])
    reply = await ai_client.get_reply(history, transcribed_text, extra_context=_build_extra_context(user))

    _push_history(context, transcribed_text, reply)
    await _reply_long_text(update.message, f"🎙 متن پیامت: «{transcribed_text}»\n\n{reply}")
    await _maybe_reply_voice(update.message, reply)
    await _maybe_send_textbook_page(update.message, transcribed_text)
