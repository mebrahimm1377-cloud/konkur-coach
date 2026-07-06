"""خواندن متغیرهای محیطی و تنظیمات کلی پروژه."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    """تنظیمات سراسری پروژه، همه از فایل .env خوانده می‌شوند."""

    telegram_bot_token: str
    ai_api_key: str
    ai_base_url: str
    ai_model: str
    ai_vision_model: str
    ai_audio_model: str
    coach_telegram_id: int
    database_path: str
    morning_laser_hour: int
    morning_laser_minute: int
    midday_1_hour: int
    midday_1_minute: int
    midday_2_hour: int
    midday_2_minute: int
    midday_3_hour: int
    midday_3_minute: int
    evening_report_hour: int
    evening_report_minute: int
    engagement_check_hour: int
    engagement_check_minute: int
    weekly_planning_day: int
    weekly_planning_hour: int
    weekly_planning_minute: int
    weekly_digest_day: int
    weekly_digest_hour: int
    weekly_digest_minute: int
    exam_countdown_hour: int
    exam_countdown_minute: int
    flashcard_review_hour: int
    flashcard_review_minute: int
    konkur_exam_date: str | None
    timezone: str
    chat_history_limit: int
    log_level: str


def _get_required(name: str) -> str:
    """یک متغیر محیطی الزامی را می‌خواند و در صورت نبود، خطا می‌دهد."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"متغیر محیطی الزامی '{name}' در فایل .env تعریف نشده است.")
    return value


def load_config() -> Config:
    """تمام تنظیمات را از متغیرهای محیطی بارگذاری و برمی‌گرداند."""
    return Config(
        telegram_bot_token=_get_required("TELEGRAM_BOT_TOKEN"),
        ai_api_key=_get_required("AI_API_KEY"),
        ai_base_url=os.getenv("AI_BASE_URL", "https://api.deepseek.com"),
        ai_model=os.getenv("AI_MODEL", "deepseek-chat"),
        ai_vision_model=os.getenv("AI_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
        ai_audio_model=os.getenv("AI_AUDIO_MODEL", "whisper-large-v3-turbo"),
        coach_telegram_id=int(_get_required("COACH_TELEGRAM_ID")),
        database_path=os.getenv("DATABASE_PATH", "konkur_coach.db"),
        morning_laser_hour=int(os.getenv("MORNING_LASER_HOUR", "8")),
        morning_laser_minute=int(os.getenv("MORNING_LASER_MINUTE", "0")),
        midday_1_hour=int(os.getenv("MIDDAY_1_HOUR", "11")),
        midday_1_minute=int(os.getenv("MIDDAY_1_MINUTE", "0")),
        midday_2_hour=int(os.getenv("MIDDAY_2_HOUR", "14")),
        midday_2_minute=int(os.getenv("MIDDAY_2_MINUTE", "0")),
        midday_3_hour=int(os.getenv("MIDDAY_3_HOUR", "17")),
        midday_3_minute=int(os.getenv("MIDDAY_3_MINUTE", "0")),
        evening_report_hour=int(os.getenv("EVENING_REPORT_HOUR", "22")),
        evening_report_minute=int(os.getenv("EVENING_REPORT_MINUTE", "0")),
        engagement_check_hour=int(os.getenv("ENGAGEMENT_CHECK_HOUR", "12")),
        engagement_check_minute=int(os.getenv("ENGAGEMENT_CHECK_MINUTE", "0")),
        weekly_planning_day=int(os.getenv("WEEKLY_PLANNING_DAY", "4")),  # 0=یکشنبه ... 4=پنج‌شنبه
        weekly_planning_hour=int(os.getenv("WEEKLY_PLANNING_HOUR", "19")),
        weekly_planning_minute=int(os.getenv("WEEKLY_PLANNING_MINUTE", "0")),
        weekly_digest_day=int(os.getenv("WEEKLY_DIGEST_DAY", "5")),  # 5=جمعه
        weekly_digest_hour=int(os.getenv("WEEKLY_DIGEST_HOUR", "20")),
        weekly_digest_minute=int(os.getenv("WEEKLY_DIGEST_MINUTE", "0")),
        exam_countdown_hour=int(os.getenv("EXAM_COUNTDOWN_HOUR", "9")),
        exam_countdown_minute=int(os.getenv("EXAM_COUNTDOWN_MINUTE", "0")),
        flashcard_review_hour=int(os.getenv("FLASHCARD_REVIEW_HOUR", "16")),
        flashcard_review_minute=int(os.getenv("FLASHCARD_REVIEW_MINUTE", "0")),
        konkur_exam_date=os.getenv("KONKUR_EXAM_DATE") or None,
        timezone=os.getenv("TIMEZONE", "Asia/Tehran"),
        chat_history_limit=int(os.getenv("CHAT_HISTORY_LIMIT", "6")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


config = load_config()
