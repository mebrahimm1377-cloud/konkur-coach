"""زمان‌بند agent کوچینگ: ۵ نوبت روزانه + یادآوری هوشمند + برنامه‌ریزی/دایجست هفتگی +
شمارش‌معکوس امتحان + مرور فلش‌کارت + شمارش‌معکوس ملی کنکور."""

import io
import json
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from telegram.ext import Application, ContextTypes

from ai.client import ai_client
from ai.tts import synthesize_speech
from database.db import (
    get_all_due_flashcards_by_user,
    get_latest_session,
    get_linked_parents,
    get_recent_sessions,
    get_students,
)
from handlers.coaching_session_handler import build_session_prompt_keyboard
from handlers.flashcard_handler import send_flashcard_prompt
from handlers.pulse_check_handler import build_pulse_keyboard
from utils.telegram_text import send_long_message

logger = logging.getLogger(__name__)

_SESSION_PROMPT_TEXTS = {
    "morning_laser": "صبح بخیر! وقت لیزر کوچینگ امروزه ☀️",
    "evening_report": "وقت گزارش‌گیری شبانه‌ست 🌙",
    "weekly_planning": "وقت برنامه‌ریزی هفته‌ی جدیده 📅",
}

_ENGAGEMENT_GAP_DAYS = 2
_EXAM_COUNTDOWN_DAYS = 7
_NATIONAL_COUNTDOWN_DAYS = 30


async def send_session_prompt(application: Application, slot_type: str) -> None:
    """پیام «شروع نوبت» (صبح، شب یا برنامه‌ریزی هفتگی) را به همه‌ی دانش‌آموزها می‌فرستد."""
    keyboard = build_session_prompt_keyboard(slot_type)
    text = _SESSION_PROMPT_TEXTS.get(slot_type, "وقت یه نوبت جدیده")

    for student in get_students(exclude_paused=True):
        try:
            await application.bot.send_message(chat_id=student.telegram_id, text=text, reply_markup=keyboard)
        except Exception:
            logger.exception("ارسال پیام نوبت '%s' به کاربر %s ناموفق بود", slot_type, student.telegram_id)


async def send_midday_pulse(application: Application, slot_type: str) -> None:
    """پیام صوتی + متنی انگیزشی همراه دکمه‌ی وضعیت سریع را در نوبت‌های میان‌روز می‌فرستد."""
    message = await ai_client.generate_motivational_message()
    keyboard = build_pulse_keyboard(slot_type)

    for student in get_students(exclude_paused=True):
        try:
            audio_bytes = await synthesize_speech(message)
            if audio_bytes:
                # edge-tts خروجی MP3 می‌دهد؛ send_voice فقط OGG/Opus را با مدت‌زمان درست نمایش می‌دهد،
                # پس از send_audio (که MP3 را هم به‌درستی پخش می‌کند) استفاده می‌کنیم.
                await application.bot.send_audio(
                    chat_id=student.telegram_id, audio=io.BytesIO(audio_bytes), filename="motivation.mp3"
                )
        except Exception:
            logger.exception("ارسال پیام صوتی میان‌روز به کاربر %s ناموفق بود", student.telegram_id)

        try:
            await application.bot.send_message(chat_id=student.telegram_id, text=message, reply_markup=keyboard)
        except Exception:
            logger.exception("ارسال پیام میان‌روز '%s' به کاربر %s ناموفق بود", slot_type, student.telegram_id)


async def run_engagement_watchdog(application: Application) -> None:
    """اگر دانش‌آموزی چند روز گزارش شبانه نداده، یادآوری ویژه به او و هشدار به کوچ می‌فرستد."""
    from config import config

    today = datetime.now()

    for student in get_students(exclude_paused=True):
        last_session = get_latest_session(student.id, slot_type="evening_report")
        if last_session is not None:
            gap_days = (today - datetime.strptime(last_session.session_date, "%Y-%m-%d")).days
        else:
            gap_days = _ENGAGEMENT_GAP_DAYS  # هیچ گزارشی ثبت نشده، مثل یه گپ بزرگ رفتار کن

        if gap_days < _ENGAGEMENT_GAP_DAYS:
            continue

        try:
            await application.bot.send_message(
                chat_id=student.telegram_id,
                text=(
                    "چند روزه ازت خبری نیست 🙂 نگرانتم! هر اتفاقی افتاده مهم نیست، فقط بگو در چه حالی و "
                    "دوباره با هم شروع کنیم."
                ),
            )
        except Exception:
            logger.exception("ارسال یادآوری engagement به کاربر %s ناموفق بود", student.telegram_id)

        try:
            await application.bot.send_message(
                chat_id=config.coach_telegram_id,
                text=f"⚠️ {student.first_name or 'یک دانش‌آموز'} حدود {gap_days} روزه گزارش شبانه نداده.",
            )
        except Exception:
            logger.exception("ارسال هشدار engagement به کوچ ناموفق بود")


def _format_sessions_for_digest(sessions) -> str:
    """چند نوبت شبانه را برای ورودی خلاصه‌ی هفتگی AI به متن ساده تبدیل می‌کند."""
    blocks = []
    for session in sessions:
        answers = json.loads(session.answers)
        qa_text = "\n".join(f"  {item['question']} -> {item['answer']}" for item in answers)
        blocks.append(f"تاریخ {session.session_date}:\n{qa_text}")
    return "\n\n".join(blocks)


async def run_weekly_digest(application: Application) -> None:
    """خلاصه‌ی هفتگی روند هر دانش‌آموز را برای کوچ و والدین متصل می‌فرستد."""
    from config import config

    for student in get_students():
        sessions = get_recent_sessions(student.id, slot_type="evening_report", limit=7)
        if not sessions:
            continue

        sessions_text = _format_sessions_for_digest(sessions)
        student_name = student.first_name or "دانش‌آموز"

        coach_summary = await ai_client.generate_progress_summary(sessions_text, audience="coach")
        try:
            await send_long_message(
                application.bot, config.coach_telegram_id, f"📊 دایجست هفتگی {student_name}:\n\n{coach_summary}"
            )
        except Exception:
            logger.exception("ارسال دایجست هفتگی به کوچ ناموفق بود")

        parents = get_linked_parents(student.id)
        if parents:
            parent_summary = await ai_client.generate_progress_summary(sessions_text, audience="parent")
            for parent in parents:
                try:
                    await send_long_message(
                        application.bot, parent.telegram_id, f"📊 دایجست هفتگی {student_name}:\n\n{parent_summary}"
                    )
                except Exception:
                    logger.exception("ارسال دایجست هفتگی به والدین ناموفق بود")


async def run_exam_countdown(application: Application) -> None:
    """برای دانش‌آموزهایی که حالت امتحان فعاله و کمتر از ۷ روز مونده، پیام تمرکز می‌فرستد."""
    today = datetime.now()

    for student in get_students(exclude_paused=True):
        if not student.exam_date:
            continue

        try:
            days_left = (datetime.strptime(student.exam_date, "%Y-%m-%d") - today).days
        except ValueError:
            continue

        if not (0 <= days_left <= _EXAM_COUNTDOWN_DAYS):
            continue

        try:
            await application.bot.send_message(
                chat_id=student.telegram_id,
                text=f"⏳ {days_left} روز تا امتحانت مونده. امروز رو با تمرکز کامل شروع کن، از پسش برمیای 💪",
            )
        except Exception:
            logger.exception("ارسال شمارش‌معکوس امتحان به کاربر %s ناموفق بود", student.telegram_id)


async def run_national_countdown(application: Application) -> None:
    """اگه KONKUR_EXAM_DATE تنظیم شده و کمتر از ۳۰ روز مونده، به همه‌ی دانش‌آموزها پیام می‌فرسته."""
    from config import config

    if not config.konkur_exam_date:
        return

    try:
        days_left = (datetime.strptime(config.konkur_exam_date, "%Y-%m-%d") - datetime.now()).days
    except ValueError:
        logger.warning("فرمت KONKUR_EXAM_DATE نامعتبره")
        return

    if not (0 <= days_left <= _NATIONAL_COUNTDOWN_DAYS):
        return

    for student in get_students(exclude_paused=True):
        try:
            await application.bot.send_message(
                chat_id=student.telegram_id, text=f"🎓 {days_left} روز تا کنکور سراسری مونده. با تمام توان ادامه بده!"
            )
        except Exception:
            logger.exception("ارسال شمارش‌معکوس ملی به کاربر %s ناموفق بود", student.telegram_id)


async def run_flashcard_review(application: Application) -> None:
    """فلش‌کارت‌های سررسیدشده‌ی هر کاربر را برای مرور می‌فرستد (حداکثر ۵ کارت در روز برای هر کاربر)."""
    today = datetime.now().strftime("%Y-%m-%d")
    grouped = get_all_due_flashcards_by_user(today)

    for student in get_students(exclude_paused=True):
        cards = grouped.get(student.id)
        if not cards:
            continue

        for card in cards[:5]:
            try:
                await send_flashcard_prompt(application.bot, student.telegram_id, card)
            except Exception:
                logger.exception("ارسال فلش‌کارت به کاربر %s ناموفق بود", student.telegram_id)


def _make_session_callback(slot_type: str):
    """callback واسط JobQueue برای نوبت‌های صبح/شب/برنامه‌ریزی هفتگی می‌سازد."""

    async def _callback(context: ContextTypes.DEFAULT_TYPE) -> None:
        await send_session_prompt(context.application, slot_type)

    return _callback


def _make_pulse_callback(slot_type: str):
    """callback واسط JobQueue برای نوبت‌های میان‌روز می‌سازد."""

    async def _callback(context: ContextTypes.DEFAULT_TYPE) -> None:
        await send_midday_pulse(context.application, slot_type)

    return _callback


async def _engagement_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """callback واسط JobQueue برای یادآوری هوشمند."""
    await run_engagement_watchdog(context.application)


async def _weekly_digest_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """callback واسط JobQueue برای دایجست هفتگی."""
    await run_weekly_digest(context.application)


async def _exam_countdown_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """callback واسط JobQueue برای شمارش‌معکوس امتحان."""
    await run_exam_countdown(context.application)


async def _national_countdown_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """callback واسط JobQueue برای شمارش‌معکوس ملی کنکور."""
    await run_national_countdown(context.application)


async def _flashcard_review_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """callback واسط JobQueue برای مرور روزانه‌ی فلش‌کارت‌ها."""
    await run_flashcard_review(context.application)


def register_agent_jobs(application: Application) -> None:
    """تمام جاب‌های روزانه/هفتگی agent کوچینگ را در JobQueue ثبت می‌کند."""
    from config import config

    tz = ZoneInfo(config.timezone)
    # APScheduler به‌طور پیش‌فرض misfire_grace_time=1 ثانیه داره؛ یعنی اگه اجرای دقیق جاب
    # حتی چند ثانیه (مثلاً به‌خاطر یه فراخوانی شبکه‌ای هم‌زمان) عقب بیفته، بی‌سروصدا skip می‌شه
    # و تا نوبت بعدی (فردا/هفته‌ی بعد) اجرا نمی‌شه. برای جابی که قراره فقط یک‌بار در روز/هفته
    # بزنه، این ریسک غیرقابل‌قبوله؛ پس یه grace time بزرگ (۱۰ دقیقه) ست می‌کنیم.
    _JOB_KWARGS = {"misfire_grace_time": 600}

    daily_slots = [
        ("morning_laser", config.morning_laser_hour, config.morning_laser_minute, _make_session_callback),
        ("midday_1", config.midday_1_hour, config.midday_1_minute, _make_pulse_callback),
        ("midday_2", config.midday_2_hour, config.midday_2_minute, _make_pulse_callback),
        ("midday_3", config.midday_3_hour, config.midday_3_minute, _make_pulse_callback),
        ("evening_report", config.evening_report_hour, config.evening_report_minute, _make_session_callback),
    ]

    for slot_type, hour, minute, callback_factory in daily_slots:
        application.job_queue.run_daily(
            callback=callback_factory(slot_type),
            time=time(hour=hour, minute=minute, tzinfo=tz),
            name=f"agent_job_{slot_type}",
            job_kwargs=_JOB_KWARGS,
        )
        logger.info("جاب '%s' برای ساعت %02d:%02d (%s) ثبت شد", slot_type, hour, minute, config.timezone)

    application.job_queue.run_daily(
        callback=_engagement_callback,
        time=time(hour=config.engagement_check_hour, minute=config.engagement_check_minute, tzinfo=tz),
        name="agent_job_engagement_watchdog",
        job_kwargs=_JOB_KWARGS,
    )
    logger.info(
        "جاب 'engagement_watchdog' برای ساعت %02d:%02d ثبت شد",
        config.engagement_check_hour,
        config.engagement_check_minute,
    )

    application.job_queue.run_daily(
        callback=_exam_countdown_callback,
        time=time(hour=config.exam_countdown_hour, minute=config.exam_countdown_minute, tzinfo=tz),
        name="agent_job_exam_countdown",
        job_kwargs=_JOB_KWARGS,
    )
    logger.info(
        "جاب 'exam_countdown' برای ساعت %02d:%02d ثبت شد", config.exam_countdown_hour, config.exam_countdown_minute
    )

    application.job_queue.run_daily(
        callback=_national_countdown_callback,
        time=time(hour=config.exam_countdown_hour, minute=config.exam_countdown_minute, tzinfo=tz),
        name="agent_job_national_countdown",
        job_kwargs=_JOB_KWARGS,
    )
    logger.info("جاب 'national_countdown' ثبت شد")

    application.job_queue.run_daily(
        callback=_flashcard_review_callback,
        time=time(hour=config.flashcard_review_hour, minute=config.flashcard_review_minute, tzinfo=tz),
        name="agent_job_flashcard_review",
        job_kwargs=_JOB_KWARGS,
    )
    logger.info(
        "جاب 'flashcard_review' برای ساعت %02d:%02d ثبت شد",
        config.flashcard_review_hour,
        config.flashcard_review_minute,
    )

    application.job_queue.run_daily(
        callback=_make_session_callback("weekly_planning"),
        time=time(hour=config.weekly_planning_hour, minute=config.weekly_planning_minute, tzinfo=tz),
        days=(config.weekly_planning_day,),
        name="agent_job_weekly_planning",
        job_kwargs=_JOB_KWARGS,
    )
    logger.info(
        "جاب 'weekly_planning' برای روز %s ساعت %02d:%02d ثبت شد",
        config.weekly_planning_day,
        config.weekly_planning_hour,
        config.weekly_planning_minute,
    )

    application.job_queue.run_daily(
        callback=_weekly_digest_callback,
        time=time(hour=config.weekly_digest_hour, minute=config.weekly_digest_minute, tzinfo=tz),
        days=(config.weekly_digest_day,),
        name="agent_job_weekly_digest",
        job_kwargs=_JOB_KWARGS,
    )
    logger.info(
        "جاب 'weekly_digest' برای روز %s ساعت %02d:%02d ثبت شد",
        config.weekly_digest_day,
        config.weekly_digest_hour,
        config.weekly_digest_minute,
    )
