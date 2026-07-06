"""توابع CRUD برای کار با دیتابیس."""

import logging
import secrets
from datetime import datetime, timedelta

from sqlalchemy import create_engine, desc
from sqlalchemy.orm import Session, sessionmaker

from config import config
from database.models import (
    Base,
    Challenge,
    CoachingSession,
    CoachNote,
    Flashcard,
    Mistake,
    Note,
    ParentInviteToken,
    ParentLink,
    PulseCheck,
    QuizAttempt,
    User,
)

logger = logging.getLogger(__name__)

engine = create_engine(f"sqlite:///{config.database_path}")
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """جدول‌های دیتابیس را در صورت نبود می‌سازد."""
    try:
        Base.metadata.create_all(engine)
        logger.info("دیتابیس با موفقیت مقداردهی اولیه شد.")
    except Exception:
        logger.exception("خطا در مقداردهی اولیه دیتابیس")
        raise


def get_or_create_user(telegram_id: int, first_name: str | None, role: str = "student") -> User:
    """کاربر را بر اساس telegram_id برمی‌گرداند، در صورت نبود می‌سازد."""
    session: Session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user is None:
            user = User(telegram_id=telegram_id, first_name=first_name, role=role)
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info("کاربر جدید ثبت شد: %s (role=%s)", telegram_id, role)
        return user
    except Exception:
        session.rollback()
        logger.exception("خطا در دریافت یا ساخت کاربر")
        raise
    finally:
        session.close()


def get_user_by_id(user_id: int) -> User | None:
    """کاربر را بر اساس شناسه‌ی داخلی (نه telegram_id) برمی‌گرداند؛ در صورت نبود None."""
    session: Session = SessionLocal()
    try:
        return session.query(User).filter_by(id=user_id).first()
    finally:
        session.close()


def get_user_by_telegram_id(telegram_id: int) -> User | None:
    """کاربر را بر اساس telegram_id برمی‌گرداند؛ در صورت نبود None."""
    session: Session = SessionLocal()
    try:
        return session.query(User).filter_by(telegram_id=telegram_id).first()
    finally:
        session.close()


def set_user_role(user_id: int, role: str) -> None:
    """نقش یک کاربر را تغییر می‌دهد."""
    session: Session = SessionLocal()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user is not None:
            user.role = role
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در تغییر نقش کاربر")
        raise
    finally:
        session.close()


def get_students(exclude_paused: bool = False) -> list[User]:
    """تمام کاربران با نقش دانش‌آموز را برمی‌گرداند (اختیاری: کاربران در حالت استراحت را حذف می‌کند)."""
    session: Session = SessionLocal()
    try:
        query = session.query(User).filter_by(role="student")
        students = query.all()
        if not exclude_paused:
            return students

        today = datetime.now().strftime("%Y-%m-%d")
        return [s for s in students if not s.paused_until or s.paused_until < today]
    finally:
        session.close()


def create_invite_token(student_user_id: int) -> str:
    """یک توکن یک‌بارمصرف برای دعوت والدین می‌سازد و برمی‌گرداند."""
    session: Session = SessionLocal()
    try:
        token = secrets.token_urlsafe(12)
        invite = ParentInviteToken(student_user_id=student_user_id, token=token)
        session.add(invite)
        session.commit()
        return token
    except Exception:
        session.rollback()
        logger.exception("خطا در ساخت توکن دعوت والدین")
        raise
    finally:
        session.close()


def resolve_invite_token(token: str) -> int | None:
    """در صورت معتبر بودن توکن، آن را مصرف‌شده علامت زده و شناسه‌ی دانش‌آموز را برمی‌گرداند."""
    session: Session = SessionLocal()
    try:
        invite = session.query(ParentInviteToken).filter_by(token=token, used_at=None).first()
        if invite is None:
            return None
        invite.used_at = datetime.utcnow()
        student_user_id = invite.student_user_id
        session.commit()
        return student_user_id
    except Exception:
        session.rollback()
        logger.exception("خطا در پردازش توکن دعوت والدین")
        raise
    finally:
        session.close()


def create_parent_link(parent_user_id: int, student_user_id: int) -> None:
    """رابطه‌ی والد به دانش‌آموز را ثبت می‌کند."""
    session: Session = SessionLocal()
    try:
        link = ParentLink(parent_user_id=parent_user_id, student_user_id=student_user_id)
        session.add(link)
        session.commit()
        logger.info("والد %s به دانش‌آموز %s لینک شد", parent_user_id, student_user_id)
    except Exception:
        session.rollback()
        logger.exception("خطا در ثبت رابطه‌ی والد-دانش‌آموز")
        raise
    finally:
        session.close()


def get_linked_students(parent_user_id: int) -> list[User]:
    """دانش‌آموزهای متصل به یک والد را برمی‌گرداند."""
    session: Session = SessionLocal()
    try:
        student_ids = [
            link.student_user_id
            for link in session.query(ParentLink).filter_by(parent_user_id=parent_user_id).all()
        ]
        if not student_ids:
            return []
        return session.query(User).filter(User.id.in_(student_ids)).all()
    finally:
        session.close()


def get_linked_parents(student_user_id: int) -> list[User]:
    """والدین متصل به یک دانش‌آموز را برمی‌گرداند."""
    session: Session = SessionLocal()
    try:
        parent_ids = [
            link.parent_user_id
            for link in session.query(ParentLink).filter_by(student_user_id=student_user_id).all()
        ]
        if not parent_ids:
            return []
        return session.query(User).filter(User.id.in_(parent_ids)).all()
    finally:
        session.close()


def save_coaching_session(
    user_id: int,
    slot_type: str,
    session_date: str,
    answers_json: str,
    ai_evaluation: str | None = None,
    ai_evaluation_coach: str | None = None,
    ai_evaluation_parent: str | None = None,
) -> CoachingSession:
    """یک نوبت کوچینگ کامل‌شده (صبح یا شب) را ذخیره می‌کند."""
    session: Session = SessionLocal()
    try:
        coaching_session = CoachingSession(
            user_id=user_id,
            slot_type=slot_type,
            session_date=session_date,
            answers=answers_json,
            ai_evaluation=ai_evaluation,
            ai_evaluation_coach=ai_evaluation_coach,
            ai_evaluation_parent=ai_evaluation_parent,
        )
        session.add(coaching_session)
        session.commit()
        session.refresh(coaching_session)
        logger.info("نوبت کوچینگ '%s' برای کاربر %s ذخیره شد", slot_type, user_id)
        return coaching_session
    except Exception:
        session.rollback()
        logger.exception("خطا در ذخیره‌ی نوبت کوچینگ")
        raise
    finally:
        session.close()


def get_latest_session(user_id: int, slot_type: str | None = None) -> CoachingSession | None:
    """آخرین نوبت کوچینگ یک کاربر را برمی‌گرداند (اختیاری: فیلتر بر اساس نوع نوبت)."""
    session: Session = SessionLocal()
    try:
        query = session.query(CoachingSession).filter_by(user_id=user_id)
        if slot_type is not None:
            query = query.filter_by(slot_type=slot_type)
        return query.order_by(desc(CoachingSession.created_at)).first()
    finally:
        session.close()


def save_pulse_check(user_id: int, slot_type: str, session_date: str, response: str) -> None:
    """پاسخ سریع دکمه‌ی وضعیت در نوبت میان‌روز را ذخیره می‌کند."""
    session: Session = SessionLocal()
    try:
        pulse = PulseCheck(user_id=user_id, slot_type=slot_type, session_date=session_date, response=response)
        session.add(pulse)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در ذخیره‌ی pulse check")
        raise
    finally:
        session.close()


def get_pulse_checks_for_date(user_id: int, session_date: str) -> list[PulseCheck]:
    """تمام pulse checkهای یک کاربر در یک روز مشخص را برمی‌گرداند."""
    session: Session = SessionLocal()
    try:
        return session.query(PulseCheck).filter_by(user_id=user_id, session_date=session_date).all()
    finally:
        session.close()


def create_coach_note(student_user_id: int, message: str) -> None:
    """پیام/یادداشتی که کوچ برای دانش‌آموز فرستاده را برای تحلیل روند بعدی ثبت می‌کند."""
    session: Session = SessionLocal()
    try:
        note = CoachNote(student_user_id=student_user_id, message=message)
        session.add(note)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در ثبت یادداشت کوچ")
        raise
    finally:
        session.close()


def get_recent_coach_notes(student_user_id: int, session_date: str) -> list[CoachNote]:
    """یادداشت‌های کوچ برای یک دانش‌آموز در یک روز مشخص را برمی‌گرداند."""
    session: Session = SessionLocal()
    try:
        return (
            session.query(CoachNote)
            .filter(CoachNote.student_user_id == student_user_id, CoachNote.created_at.isnot(None))
            .filter(CoachNote.created_at.like(f"{session_date}%"))
            .all()
        )
    finally:
        session.close()


def get_recent_sessions(user_id: int, slot_type: str, limit: int = 7) -> list[CoachingSession]:
    """چند نوبت اخیر کوچینگ یک کاربر از یک نوع مشخص را برمی‌گرداند (جدیدترین اول)."""
    session: Session = SessionLocal()
    try:
        return (
            session.query(CoachingSession)
            .filter_by(user_id=user_id, slot_type=slot_type)
            .order_by(desc(CoachingSession.created_at))
            .limit(limit)
            .all()
        )
    finally:
        session.close()


def record_evening_completion(user_id: int, session_date: str, points_awarded: int) -> int:
    """استریک و امتیاز کاربر را بعد از تکمیل موفق گزارش شبانه به‌روزرسانی و استریک جدید را برمی‌گرداند."""
    session: Session = SessionLocal()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user is None:
            return 0

        yesterday = (datetime.strptime(session_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        had_yesterday_session = (
            session.query(CoachingSession)
            .filter_by(user_id=user_id, slot_type="evening_report", session_date=yesterday)
            .first()
            is not None
        )

        user.current_streak = user.current_streak + 1 if had_yesterday_session else 1
        user.longest_streak = max(user.longest_streak, user.current_streak)
        user.points += points_awarded
        session.commit()
        return user.current_streak
    except Exception:
        session.rollback()
        logger.exception("خطا در به‌روزرسانی استریک و امتیاز")
        raise
    finally:
        session.close()


def award_points(user_id: int, points_awarded: int) -> None:
    """امتیاز به کاربر اضافه می‌کند (بدون تاثیر روی استریک)."""
    session: Session = SessionLocal()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user is not None:
            user.points += points_awarded
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در ثبت امتیاز")
        raise
    finally:
        session.close()


def create_note(user_id: int, text: str) -> None:
    """یک یادداشت سریع برای دانش‌آموز ذخیره می‌کند."""
    session: Session = SessionLocal()
    try:
        note = Note(user_id=user_id, text=text)
        session.add(note)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در ذخیره‌ی یادداشت")
        raise
    finally:
        session.close()


def get_notes(user_id: int, limit: int = 10) -> list[Note]:
    """یادداشت‌های اخیر یک کاربر را برمی‌گرداند (جدیدترین اول)."""
    session: Session = SessionLocal()
    try:
        return session.query(Note).filter_by(user_id=user_id).order_by(desc(Note.created_at)).limit(limit).all()
    finally:
        session.close()


def create_quiz_attempt(user_id: int, topic: str, score: int, total: int) -> None:
    """نتیجه‌ی یک کوییز تکمیل‌شده را ذخیره می‌کند."""
    session: Session = SessionLocal()
    try:
        attempt = QuizAttempt(user_id=user_id, topic=topic, score=score, total=total)
        session.add(attempt)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در ذخیره‌ی نتیجه‌ی کوییز")
        raise
    finally:
        session.close()


def set_exam_date(user_id: int, exam_date: str | None) -> None:
    """تاریخ امتحان دانش‌آموز را ثبت می‌کند."""
    session: Session = SessionLocal()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user is not None:
            user.exam_date = exam_date
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در ثبت تاریخ امتحان")
        raise
    finally:
        session.close()


def set_needs_gentle_tone(user_id: int, needs_gentle_tone: bool) -> None:
    """پرچم لحن ملایم‌تر را برای کاربر تنظیم می‌کند."""
    session: Session = SessionLocal()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user is not None:
            user.needs_gentle_tone = needs_gentle_tone
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در تنظیم لحن ملایم")
        raise
    finally:
        session.close()


def set_paused_until(user_id: int, paused_until: str | None) -> None:
    """تاریخ پایان حالت استراحت کاربر را تنظیم می‌کند."""
    session: Session = SessionLocal()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if user is not None:
            user.paused_until = paused_until
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در تنظیم حالت استراحت")
        raise
    finally:
        session.close()


def create_flashcards(user_id: int, topic: str, cards: list[dict]) -> None:
    """چند فلش‌کارت جدید را ذخیره می‌کند (همه با سررسید امروز)."""
    session: Session = SessionLocal()
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        for card in cards:
            session.add(
                Flashcard(
                    user_id=user_id,
                    topic=topic,
                    question=card["question"],
                    answer=card["answer"],
                    interval_days=1,
                    next_review_date=today,
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در ذخیره‌ی فلش‌کارت‌ها")
        raise
    finally:
        session.close()


def get_flashcard_by_id(flashcard_id: int) -> Flashcard | None:
    """یک فلش‌کارت را بر اساس شناسه برمی‌گرداند."""
    session: Session = SessionLocal()
    try:
        return session.query(Flashcard).filter_by(id=flashcard_id).first()
    finally:
        session.close()


def get_due_flashcards(user_id: int, today: str) -> list[Flashcard]:
    """فلش‌کارت‌های سررسیدشده‌ی یک کاربر تا امروز را برمی‌گرداند."""
    session: Session = SessionLocal()
    try:
        return (
            session.query(Flashcard)
            .filter(Flashcard.user_id == user_id, Flashcard.next_review_date <= today)
            .all()
        )
    finally:
        session.close()


def get_all_due_flashcards_by_user(today: str) -> dict[int, list[Flashcard]]:
    """فلش‌کارت‌های سررسیدشده‌ی همه‌ی کاربران را گروه‌بندی‌شده بر اساس user_id برمی‌گرداند."""
    session: Session = SessionLocal()
    try:
        due_cards = session.query(Flashcard).filter(Flashcard.next_review_date <= today).all()
        grouped: dict[int, list[Flashcard]] = {}
        for card in due_cards:
            grouped.setdefault(card.user_id, []).append(card)
        return grouped
    finally:
        session.close()


def reschedule_flashcard(flashcard_id: int, remembered: bool) -> None:
    """بازه‌ی مرور بعدی فلش‌کارت را بر اساس یادآوری موفق یا ناموفق تنظیم می‌کند."""
    session: Session = SessionLocal()
    try:
        card = session.query(Flashcard).filter_by(id=flashcard_id).first()
        if card is None:
            return

        card.interval_days = min(card.interval_days * 2, 60) if remembered else 1
        card.next_review_date = (datetime.now() + timedelta(days=card.interval_days)).strftime("%Y-%m-%d")
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در زمان‌بندی مجدد فلش‌کارت")
        raise
    finally:
        session.close()


def create_mistake(user_id: int, topic: str, question: str, correct_answer: str) -> None:
    """یک اشتباه از کوییز را برای بانک اشتباهات ذخیره می‌کند."""
    session: Session = SessionLocal()
    try:
        mistake = Mistake(user_id=user_id, topic=topic, question=question, correct_answer=correct_answer)
        session.add(mistake)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در ذخیره‌ی اشتباه")
        raise
    finally:
        session.close()


def get_mistakes(user_id: int, limit: int = 10) -> list[Mistake]:
    """اشتباهات اخیر یک کاربر را برمی‌گرداند (جدیدترین اول)."""
    session: Session = SessionLocal()
    try:
        return (
            session.query(Mistake).filter_by(user_id=user_id).order_by(desc(Mistake.created_at)).limit(limit).all()
        )
    finally:
        session.close()


def set_active_challenge(coach_user_id: int, text: str) -> None:
    """چالش‌های قبلی را غیرفعال کرده و یک چالش جدید فعال می‌سازد."""
    session: Session = SessionLocal()
    try:
        session.query(Challenge).filter_by(is_active=True).update({"is_active": False})
        session.add(Challenge(coach_user_id=coach_user_id, text=text, is_active=True))
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("خطا در ثبت چالش هفتگی")
        raise
    finally:
        session.close()


def get_active_challenge() -> Challenge | None:
    """چالش فعال فعلی را برمی‌گرداند؛ در صورت نبود None."""
    session: Session = SessionLocal()
    try:
        return session.query(Challenge).filter_by(is_active=True).order_by(desc(Challenge.created_at)).first()
    finally:
        session.close()
