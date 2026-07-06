"""ساخت گزارش PDF فارسی (راست‌به‌چپ، با طراحی گرم و برندشده) از روند یک دانش‌آموز."""

import logging
import re
from datetime import datetime

import arabic_reshaper
from bidi.algorithm import get_display
from fpdf import FPDF

logger = logging.getLogger(__name__)

_FONT_PATH = "C:/Windows/Fonts/tahoma.ttf"
_FONT_BOLD_PATH = "C:/Windows/Fonts/tahomabd.ttf"

# پالت رنگی برند
_DARK_ORANGE = (249, 96, 13)  # #F9600D — تیترها، لوگو، عناصر برجسته
_LIGHT_ORANGE = (255, 138, 0)  # #FF8A00 — تاکید ثانویه، خط زیر تیتر
_AMBER_GOLD = (255, 179, 0)  # #FFB300 — هایلایت/بج
_LIGHT_GOLD = (255, 193, 7)  # #FFC107 — جزئیات ظریف
_SOFT_BLACK = (21, 21, 21)  # #151515 — متن اصلی
_OFF_WHITE = (250, 250, 248)  # #FAFAF8 — پس‌زمینه
_MUTED_COLOR = (140, 120, 100)
_CARD_BG = (255, 255, 255)

_PAGE_MARGIN = 15

_LRE = "‪"  # آغاز embedding چپ‌به‌راست
_PDF_MARK = "‬"  # پایان embedding
_BOLD_LINE_RE = re.compile(r"^\*\*(.+)\*\*$")


def _rtl(text: str) -> str:
    """متن فارسی را برای نمایش درست (چسبیدن حروف + جهت راست‌به‌چپ) آماده می‌کند."""
    return get_display(arabic_reshaper.reshape(text))


def _keep_ltr(value: str) -> str:
    """یک رشته‌ی لاتین/عددی (مثل تاریخ) را طوری علامت می‌زند که داخل متن فارسی جابه‌جا نشود."""
    return f"{_LRE}{value}{_PDF_MARK}"


class _ReportPDF(FPDF):
    """PDF با پس‌زمینه‌ی گرم، هدر برندشده و فوتر شماره‌صفحه‌دار در همه‌ی صفحات."""

    def header(self) -> None:
        self.set_fill_color(*_OFF_WHITE)
        self.rect(0, 0, self.w, self.h, style="F")

        if self.page_no() == 1:
            return  # هدر ویژه‌ی صفحه‌ی اول جداگانه در build_report_pdf رسم می‌شود

        self.set_font("Tahoma", size=9)
        self.set_text_color(*_MUTED_COLOR)
        self.set_xy(_PAGE_MARGIN, 8)
        self.cell(0, 6, _rtl("گزارش پیشرفت — کوچ تحصیلی هوشمند"), align="R")
        self.set_draw_color(*_LIGHT_GOLD)
        self.set_line_width(0.6)
        self.line(_PAGE_MARGIN, 15, self.w - _PAGE_MARGIN, 15)

    def footer(self) -> None:
        self.set_draw_color(*_LIGHT_GOLD)
        self.set_line_width(0.4)
        self.line(_PAGE_MARGIN, self.h - 18, self.w - _PAGE_MARGIN, self.h - 18)
        self.set_y(-15)
        self.set_font("Tahoma", size=8)
        self.set_text_color(*_MUTED_COLOR)
        self.cell(0, 10, _rtl(f"صفحه {self.page_no()}"), align="C")


def build_report_pdf(student_name: str, sessions: list[tuple[str, str]]) -> bytes:
    """PDF گزارش شامل تاریخ و ارزیابی هر نوبت شبانه را می‌سازد و bytes آن را برمی‌گرداند.

    sessions: لیستی از (تاریخ, متن ارزیابی)، جدیدترین اول.
    """
    pdf = _ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=24)
    pdf.set_margins(_PAGE_MARGIN, _PAGE_MARGIN, _PAGE_MARGIN)
    pdf.add_font("Tahoma", "", _FONT_PATH)
    pdf.add_font("Tahoma", "B", _FONT_BOLD_PATH)
    pdf.add_page()

    _render_cover_header(pdf, student_name)

    pdf.set_xy(_PAGE_MARGIN, 56)
    pdf.set_text_color(*_SOFT_BLACK)

    if not sessions:
        pdf.set_font("Tahoma", size=12)
        pdf.multi_cell(0, 8, _rtl("هنوز گزارش شبانه‌ای برای این دانش‌آموز ثبت نشده."), align="R")
        return bytes(pdf.output())

    for date, evaluation in sessions:
        _render_session_card(pdf, date, evaluation)

    return bytes(pdf.output())


def _render_cover_header(pdf: _ReportPDF, student_name: str) -> None:
    """هدر برندشده‌ی صفحه‌ی اول (نوار نارنجی تیره + خط تاکید طلایی) را رسم می‌کند."""
    pdf.set_fill_color(*_DARK_ORANGE)
    pdf.rect(0, 0, pdf.w, 40, style="F")
    pdf.set_fill_color(*_LIGHT_ORANGE)
    pdf.rect(0, 40, pdf.w, 2.5, style="F")

    # دایره‌های تزئینی ظریف با تُن طلایی، هم‌راستا با هویت بصری برند
    pdf.set_fill_color(*_AMBER_GOLD)
    pdf.ellipse(pdf.w - 26, -14, 40, 40, style="F")
    pdf.set_fill_color(*_LIGHT_GOLD)
    pdf.ellipse(pdf.w - 10, 20, 14, 14, style="F")

    pdf.set_xy(_PAGE_MARGIN, 10)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Tahoma", "B", 20)
    pdf.cell(pdf.w - 2 * _PAGE_MARGIN, 12, _rtl(f"گزارش پیشرفت {student_name}"), align="R")

    pdf.set_xy(_PAGE_MARGIN, 24)
    pdf.set_font("Tahoma", size=11)
    today = datetime.now().strftime("%Y-%m-%d")
    pdf.cell(
        pdf.w - 2 * _PAGE_MARGIN, 8, _rtl(f"تهیه‌شده در تاریخ {_keep_ltr(today)} — کوچ تحصیلی هوشمند"), align="R"
    )

    pdf.set_xy(_PAGE_MARGIN, 48)
    pdf.set_font("Tahoma", "B", 12)
    pdf.set_text_color(*_DARK_ORANGE)
    pdf.cell(pdf.w - 2 * _PAGE_MARGIN, 8, _rtl("گزارش‌های اخیر"), align="R")


def _render_session_card(pdf: _ReportPDF, date: str, evaluation: str) -> None:
    """یک کارت شامل بج تاریخ (طلایی) و متن ارزیابی یک نوبت شبانه رسم می‌کند."""
    lines = [line for line in evaluation.splitlines() if line.strip()] or ["—"]

    line_height = 6.5
    badge_height = 12
    estimated_height = badge_height + 8 + line_height * len(lines) + 8
    if pdf.get_y() + estimated_height > pdf.page_break_trigger:
        pdf.add_page()

    start_y = pdf.get_y()
    card_left = _PAGE_MARGIN
    card_width = pdf.w - 2 * _PAGE_MARGIN

    # کارت با پس‌زمینه‌ی سفید، حاشیه‌ی طلایی ظریف و نوار تاکید نارنجی سمت راست
    pdf.set_draw_color(*_LIGHT_GOLD)
    pdf.set_line_width(0.3)
    pdf.set_fill_color(*_CARD_BG)
    pdf.rect(card_left, start_y, card_width, estimated_height, style="FD")
    pdf.set_fill_color(*_DARK_ORANGE)
    pdf.rect(card_left + card_width - 3, start_y, 3, estimated_height, style="F")

    # بج تاریخ به رنگ کهربایی
    badge_text = _rtl(f"تاریخ: {_keep_ltr(date)}")
    pdf.set_font("Tahoma", "B", 11)
    badge_w = pdf.get_string_width(badge_text) + 8
    badge_x = card_left + card_width - 9 - badge_w
    pdf.set_fill_color(*_AMBER_GOLD)
    pdf.rect(badge_x, start_y + 4, badge_w, 8, style="F")
    pdf.set_xy(badge_x, start_y + 4)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(badge_w, 8, badge_text, align="C")

    pdf.set_xy(card_left + 6, start_y + badge_height + 8)
    pdf.set_text_color(*_SOFT_BLACK)
    for line in lines:
        pdf.set_x(card_left + 6)
        bold_match = _BOLD_LINE_RE.match(line.strip())
        if bold_match:
            pdf.set_font("Tahoma", "B", 11)
            pdf.set_text_color(*_DARK_ORANGE)
            pdf.multi_cell(card_width - 15, line_height, _rtl(bold_match.group(1)), align="R")
            pdf.set_text_color(*_SOFT_BLACK)
        else:
            pdf.set_font("Tahoma", size=10.5)
            pdf.multi_cell(card_width - 15, line_height, _rtl(line.replace("**", "")), align="R")

    pdf.set_y(start_y + estimated_height + 6)
