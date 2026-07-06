"""تعریف جدول‌های دیتابیس با SQLAlchemy.

ساختار جدول‌ها طوری نوشته شده که با تغییر connection string در آینده
بتوان به‌راحتی به Postgres مهاجرت کرد.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """کلاس پایه برای تمام مدل‌های ORM."""


class User(Base):
    """کاربر بات: دانش‌آموز، والد یا کوچ."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="student")  # student | parent | coach
    field_of_study: Mapped[str] = mapped_column(String(100), nullable=True, default="تجربی")
    exam_date: Mapped[str] = mapped_column(String(10), nullable=True)  # فرمت YYYY-MM-DD
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_gentle_tone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paused_until: Mapped[str] = mapped_column(String(10), nullable=True)  # فرمت YYYY-MM-DD
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ParentLink(Base):
    """رابطه‌ی والد به دانش‌آموز."""

    __tablename__ = "parent_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    student_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ParentInviteToken(Base):
    """توکن یک‌بارمصرف برای دیپ‌لینک اتصال والدین به دانش‌آموز."""

    __tablename__ = "parent_invite_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    used_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class CoachingSession(Base):
    """رکورد یک نوبت کوچینگ (نوبت صبح شش‌سوالی یا گزارش شبانه ده‌سوالی)."""

    __tablename__ = "coaching_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    slot_type: Mapped[str] = mapped_column(String(30), nullable=False)  # morning_laser | evening_report
    session_date: Mapped[str] = mapped_column(String(10), nullable=False)  # فرمت YYYY-MM-DD
    answers: Mapped[str] = mapped_column(Text, nullable=False)  # JSON: [{"question": ..., "answer": ...}, ...]
    ai_evaluation: Mapped[str] = mapped_column(Text, nullable=True)  # نسخه‌ی خطاب به دانش‌آموز
    ai_evaluation_coach: Mapped[str] = mapped_column(Text, nullable=True)  # نسخه‌ی تحلیلی برای کوچ
    ai_evaluation_parent: Mapped[str] = mapped_column(Text, nullable=True)  # نسخه‌ی خلاصه برای والدین
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PulseCheck(Base):
    """پاسخ سریع دانش‌آموز به دکمه‌ی وضعیت در نوبت‌های میان‌روز."""

    __tablename__ = "pulse_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    slot_type: Mapped[str] = mapped_column(String(20), nullable=False)  # midday_1 | midday_2 | midday_3
    session_date: Mapped[str] = mapped_column(String(10), nullable=False)
    response: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CoachNote(Base):
    """یادداشت/پیامی که کوچ برای یک دانش‌آموز خاص ثبت یا ارسال کرده (برای تحلیل روند بعدی)."""

    __tablename__ = "coach_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QuizAttempt(Base):
    """رکورد یک کوییز تعاملی که دانش‌آموز شرکت کرده."""

    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Note(Base):
    """یادداشت سریع دانش‌آموز برای مرور بعدی."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Flashcard(Base):
    """فلش‌کارت مروری با زمان‌بندی spaced-repetition ساده."""

    __tablename__ = "flashcards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_review_date: Mapped[str] = mapped_column(String(10), nullable=False)  # فرمت YYYY-MM-DD
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Mistake(Base):
    """اشتباه ثبت‌شده از کوییزها، برای مرور بعدی نقاط ضعف."""

    __tablename__ = "mistakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Challenge(Base):
    """چالش هفتگی‌ای که کوچ برای همه‌ی دانش‌آموزها تعریف می‌کند."""

    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    coach_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
