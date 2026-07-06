"""کلاینت ارتباط با سرویس هوش مصنوعی (Groq یا هر provider سازگار با OpenAI)."""

import base64
import json
import logging
import re

from openai import APIError, AsyncOpenAI

from ai.system_prompt import COACH_REPORT_SYSTEM_PROMPT, COACH_SYSTEM_PROMPT, PARENT_REPORT_SYSTEM_PROMPT
from ai.textbook_rag import textbook_rag
from config import config

_AUDIENCE_PROMPTS = {
    "student": COACH_SYSTEM_PROMPT,
    "coach": COACH_REPORT_SYSTEM_PROMPT,
    "parent": PARENT_REPORT_SYSTEM_PROMPT,
}

logger = logging.getLogger(__name__)

_GENERIC_ERROR_REPLY = "یه خطای غیرمنتظره پیش اومد. لطفاً دوباره تلاش کن."
_API_ERROR_REPLY = "الان مشکلی توی ارتباط با سرویس هوش مصنوعی پیش اومد. لطفاً چند لحظه دیگه دوباره امتحان کن."


def _parse_json_array(content: str, required_keys: tuple[str, ...]) -> list[dict] | None:
    """یک آرایه‌ی JSON را از متن پاسخ AI استخراج و اعتبارسنجی می‌کند."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        items = json.loads(cleaned)
        if not isinstance(items, list):
            return None
        for item in items:
            if not all(key in item for key in required_keys):
                return None
        return items
    except (json.JSONDecodeError, TypeError):
        logger.exception("خطا در پارس JSON")
        return None


class AIClient:
    """کلاینت جنریک برای ارتباط با هر سرویس AI سازگار با فرمت OpenAI.

    با تغییر AI_BASE_URL و AI_MODEL در .env می‌توان بدون تغییر کد از Groq به
    هر provider دیگر سوییچ کرد.
    """

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=config.ai_api_key,
            base_url=config.ai_base_url,
        )
        self._model = config.ai_model
        self._vision_model = config.ai_vision_model
        self._audio_model = config.ai_audio_model

    async def get_reply(
        self, history: list[dict[str, str]], user_message: str, extra_context: str | None = None
    ) -> str:
        """پاسخ کوچ را برای پیام متنی کاربر با در نظر گرفتن تاریخچه مکالمه برمی‌گرداند.

        extra_context در صورت وجود (مثلاً شمارش‌معکوس امتحان) به system prompt اضافه می‌شود.
        اگه درخواست به‌خاطر حجم زیاد تاریخچه رد بشه (خطای ۴۱۳)، یک‌بار با تاریخچه‌ی کوتاه‌شده دوباره امتحان می‌شود.
        """
        system_content = COACH_SYSTEM_PROMPT
        if extra_context:
            system_content += f"\n\nزمینه‌ی اضافه درباره‌ی این دانش‌آموز:\n{extra_context}"

        textbook_context = textbook_rag.format_context(user_message)
        if textbook_context:
            system_content += (
                "\n\nبخش‌های زیر عیناً از متن کتاب‌های درسی رسمی (چاپ ۱۴۰۴-۱۴۰۵) استخراج شده‌اند. اگه سوال "
                "دانش‌آموز به یکی از این مباحث مربوطه، پاسخت رو بر اساس همین متن واقعی کتاب بده (نه فقط دانش "
                "عمومی خودت) و اگه لازم بود دقیقاً به شماره صفحه‌ی کتاب اشاره کن:\n\n" + textbook_context
            )

        async def _call(trimmed_history: list[dict[str, str]]) -> str:
            messages = [{"role": "system", "content": system_content}]
            messages.extend(trimmed_history)
            messages.append({"role": "user", "content": user_message})
            response = await self._client.chat.completions.create(model=self._model, messages=messages)
            content = response.choices[0].message.content
            return content.strip() if content else "متاسفانه نتونستم جواب بدم، لطفاً دوباره امتحان کن."

        try:
            return await _call(history)
        except APIError as error:
            if getattr(error, "status_code", None) == 413 and history:
                logger.warning("درخواست چت خیلی بزرگ بود؛ با تاریخچه‌ی کوتاه‌شده دوباره امتحان می‌شود")
                try:
                    return await _call(history[-2:])
                except Exception:
                    logger.exception("خطا در تلاش دوم با تاریخچه‌ی کوتاه‌شده")
                    return _API_ERROR_REPLY
            logger.exception("خطا در ارتباط با سرویس AI")
            return _API_ERROR_REPLY
        except Exception:
            logger.exception("خطای غیرمنتظره در دریافت پاسخ از AI")
            return _GENERIC_ERROR_REPLY

    async def get_vision_reply(self, image_bytes: bytes, caption: str | None) -> str:
        """تصویر ارسالی کاربر (مثلاً عکس دفترچه یا برگه تمرین) را تحلیل می‌کند."""
        image_b64 = base64.b64encode(image_bytes).decode()
        user_text = caption or "این تصویر رو تحلیل کن و به دانش‌آموز کمک کن."

        messages = [
            {"role": "system", "content": COACH_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            },
        ]

        try:
            response = await self._client.chat.completions.create(
                model=self._vision_model,
                messages=messages,
            )
            content = response.choices[0].message.content
            return content.strip() if content else "متاسفانه نتونستم تصویر رو تحلیل کنم، لطفاً دوباره امتحان کن."
        except APIError:
            logger.exception("خطا در تحلیل تصویر")
            return _API_ERROR_REPLY
        except Exception:
            logger.exception("خطای غیرمنتظره در تحلیل تصویر")
            return _GENERIC_ERROR_REPLY

    async def transcribe_audio(self, audio_bytes: bytes, filename: str) -> str | None:
        """پیام صوتی کاربر را به متن فارسی تبدیل می‌کند؛ در صورت خطا None برمی‌گرداند."""
        try:
            transcript = await self._client.audio.transcriptions.create(
                model=self._audio_model,
                file=(filename, audio_bytes),
                language="fa",
            )
            return transcript.text.strip() if transcript.text else None
        except APIError:
            logger.exception("خطا در تبدیل صدا به متن")
            return None
        except Exception:
            logger.exception("خطای غیرمنتظره در تبدیل صدا به متن")
            return None

    async def generate_evaluation(
        self,
        qa_pairs: list[tuple[str, str]],
        audience: str = "student",
        extra_context: str | None = None,
    ) -> str:
        """از روی پاسخ‌های گزارش شبانه (و در صورت وجود، رویدادهای روز)، ارزیابی متناسب با مخاطب می‌سازد.

        audience: یکی از 'student'، 'coach' یا 'parent' — لحن و سطح جزئیات خروجی را تعیین می‌کند.
        """
        qa_text = "\n".join(f"سوال: {q}\nپاسخ: {a}" for q, a in qa_pairs)
        context_block = f"\n\nرویدادهای دیگر امروز (وضعیت‌های میان‌روز، یادداشت‌های کوچ و ...):\n{extra_context}" if extra_context else ""
        instruction = (
            "این پاسخ‌های گزارش شبانه‌ی یک دانش‌آموز کنکوری‌ست. بر اساس این پاسخ‌ها (و رویدادهای اضافه‌ی "
            "احتمالی زیر) یک ارزیابی کوتاه (حداکثر ۸ خط) با این سه بخش بنویس:\n"
            "۱. نقاط قوت امروز\n۲. نگرانی‌ها یا موانع\n۳. پیشنهاد برای فردا\n\n"
            f"پاسخ‌های امروز:\n{qa_text}{context_block}"
        )
        messages = [
            {"role": "system", "content": _AUDIENCE_PROMPTS.get(audience, COACH_SYSTEM_PROMPT)},
            {"role": "user", "content": instruction},
        ]

        try:
            response = await self._client.chat.completions.create(model=self._model, messages=messages)
            content = response.choices[0].message.content
            return content.strip() if content else "نتونستم ارزیابی امروز رو بسازم."
        except APIError:
            logger.exception("خطا در ساخت ارزیابی شبانه")
            return _API_ERROR_REPLY
        except Exception:
            logger.exception("خطای غیرمنتظره در ساخت ارزیابی شبانه")
            return _GENERIC_ERROR_REPLY

    async def generate_progress_summary(self, sessions_data: str, audience: str = "student") -> str:
        """از روی چند نوبت اخیر گزارش شبانه، یک تحلیل روند (هفتگی) متناسب با مخاطب می‌سازد."""
        instruction = (
            "زیر خام‌داده‌ی چند گزارش شبانه‌ی اخیر یک دانش‌آموز کنکوریه (هر کدوم شامل سوال و جواب‌های همون روزه). "
            "بر اساس این داده‌ها یک تحلیل روند کوتاه (حداکثر ۱۰ خط) بنویس: روند ساعت مطالعه، روند حال روحی، "
            "موانع یا الگوهای تکرارشونده، و یک پیشنهاد کلی برای ادامه‌ی مسیر.\n\n"
            f"داده‌ی نوبت‌ها:\n{sessions_data}"
        )
        messages = [
            {"role": "system", "content": _AUDIENCE_PROMPTS.get(audience, COACH_SYSTEM_PROMPT)},
            {"role": "user", "content": instruction},
        ]

        try:
            response = await self._client.chat.completions.create(model=self._model, messages=messages)
            content = response.choices[0].message.content
            return content.strip() if content else "نتونستم تحلیل روند رو بسازم."
        except APIError:
            logger.exception("خطا در ساخت تحلیل روند")
            return _API_ERROR_REPLY
        except Exception:
            logger.exception("خطای غیرمنتظره در ساخت تحلیل روند")
            return _GENERIC_ERROR_REPLY

    async def generate_quiz(self, topic: str, num_questions: int = 5) -> list[dict] | None:
        """یک کوییز چهارگزینه‌ای کنکوری درباره‌ی یک مبحث می‌سازد؛ در صورت خطا None برمی‌گرداند.

        خروجی: لیستی از دیکشنری با کلیدهای question, options (لیست ۴تایی), correct_index (0-3), explanation.
        """
        textbook_context = textbook_rag.format_context(topic, top_k=4)
        grounding = (
            f"\n\nبرای دقت بیشتر، این بخش‌ها عیناً از متن کتاب درسی رسمی درباره‌ی این مبحث استخراج شده؛ "
            f"سوال‌ها رو تا حد امکان بر اساس همین محتوای واقعی کتاب بساز:\n\n{textbook_context}"
            if textbook_context
            else ""
        )
        instruction = (
            f"دقیقاً {num_questions} سوال چهارگزینه‌ای در سطح کنکور سراسری ایران درباره‌ی مبحث "
            f"«{topic}» بساز. خروجی را فقط و فقط به‌صورت یک آرایه‌ی JSON معتبر بده (بدون هیچ متن اضافه، "
            "بدون Markdown)، با این ساختار دقیق برای هر سوال:\n"
            '{"question": "متن سوال", "options": ["گزینه۱", "گزینه۲", "گزینه۳", "گزینه۴"], '
            f'"correct_index": 0, "explanation": "توضیح کوتاه پاسخ درست"}}{grounding}'
        )
        messages = [
            {"role": "system", "content": COACH_SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]

        try:
            response = await self._client.chat.completions.create(model=self._model, messages=messages)
            content = response.choices[0].message.content
            if not content:
                return None
            questions = _parse_json_array(content, ("question", "options", "correct_index", "explanation"))
            if not questions:
                return None
            valid_questions = [
                q
                for q in questions
                if isinstance(q["options"], list)
                and len(q["options"]) == 4
                and isinstance(q["correct_index"], int)
                and 0 <= q["correct_index"] < 4
            ]
            return valid_questions or None
        except Exception:
            logger.exception("خطا در ساخت کوییز")
            return None

    async def generate_flashcards(self, topic: str, num_cards: int = 6) -> list[dict] | None:
        """چند فلش‌کارت مرور (سوال/جواب کوتاه) درباره‌ی یک مبحث می‌سازد؛ در صورت خطا None برمی‌گرداند."""
        textbook_context = textbook_rag.format_context(topic, top_k=4)
        grounding = (
            f"\n\nاین بخش‌ها عیناً از متن کتاب درسی رسمی درباره‌ی این مبحث استخراج شده؛ فلش‌کارت‌ها رو تا حد "
            f"امکان بر اساس همین محتوای واقعی کتاب بساز:\n\n{textbook_context}"
            if textbook_context
            else ""
        )
        instruction = (
            f"دقیقاً {num_cards} فلش‌کارت مروری کوتاه (سوال و جواب) در سطح کنکور سراسری ایران درباره‌ی مبحث "
            f"«{topic}» بساز. خروجی را فقط و فقط به‌صورت یک آرایه‌ی JSON معتبر بده (بدون هیچ متن اضافه، "
            f'بدون Markdown)، با ساختار: {{"question": "متن سوال کوتاه", "answer": "جواب کوتاه"}}{grounding}'
        )
        messages = [
            {"role": "system", "content": COACH_SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]

        try:
            response = await self._client.chat.completions.create(model=self._model, messages=messages)
            content = response.choices[0].message.content
            if not content:
                return None
            return _parse_json_array(content, ("question", "answer"))
        except Exception:
            logger.exception("خطا در ساخت فلش‌کارت‌ها")
            return None

    async def generate_prediction(self, sessions_data: str) -> str:
        """یک تخمین کاملاً غیررسمی و کلی از وضعیت کلی دانش‌آموز (بدون اعداد رتبه/تراز دقیق) می‌سازد."""
        instruction = (
            "زیر خام‌داده‌ی چند گزارش شبانه‌ی اخیر یک دانش‌آموز کنکوریه. یک تخمین کاملاً کلی و غیررسمی "
            "(حداکثر ۶ خط) از وضعیت پیشرفتش بده؛ تاکید کن این فقط یه برداشت کلیه، نه پیش‌بینی دقیق رتبه یا تراز، "
            "و روی روند تلاش و ثبات تمرکز کن نه عدد.\n\n"
            f"داده‌ی نوبت‌ها:\n{sessions_data}"
        )
        messages = [
            {"role": "system", "content": COACH_SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]

        try:
            response = await self._client.chat.completions.create(model=self._model, messages=messages)
            content = response.choices[0].message.content
            return content.strip() if content else "نتونستم تخمینی بسازم."
        except Exception:
            logger.exception("خطا در ساخت تخمین روند")
            return _GENERIC_ERROR_REPLY

    async def generate_comparison(self, recent_data: str, previous_data: str) -> str:
        """روند ۷ روز اخیر را با ۷ روز قبل‌تر مقایسه می‌کند."""
        instruction = (
            "دو مجموعه داده‌ی گزارش شبانه از یک دانش‌آموز کنکوری داری: هفته‌ی اخیر و هفته‌ی قبل از اون. "
            "یک مقایسه‌ی کوتاه (حداکثر ۸ خط) بنویس: چی بهتر شده، چی بدتر شده، و یک جمع‌بندی کلی.\n\n"
            f"هفته‌ی اخیر:\n{recent_data}\n\nهفته‌ی قبل:\n{previous_data}"
        )
        messages = [
            {"role": "system", "content": COACH_SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]

        try:
            response = await self._client.chat.completions.create(model=self._model, messages=messages)
            content = response.choices[0].message.content
            return content.strip() if content else "نتونستم مقایسه‌ای بسازم."
        except Exception:
            logger.exception("خطا در ساخت مقایسه‌ی روند")
            return _GENERIC_ERROR_REPLY

    async def generate_image_brief(self, topic: str) -> dict | None:
        """از روی یک موضوع فارسی، یک prompt انگلیسی برای مدل تصویرساز و یک عنوان کوتاه فارسی می‌سازد.

        مدل‌های تصویرساز روی prompt انگلیسی بسیار بهتر عمل می‌کنن و نوشته‌ی فارسی داخل
        تصویر رو هم درست رندر نمی‌کنن؛ برای همین عنوان فارسی جدا تولید می‌شه تا بعداً
        خودمون (نه مدل تصویرساز) با فونت روی تصویر بکشیمش.

        خروجی: {"image_prompt": "...", "caption_fa": "..."} یا None در صورت خطا.
        """
        instruction = (
            f"موضوع آموزشی زیر (به فارسی) رو در نظر بگیر: «{topic}»\n\n"
            "دو چیز برام بساز:\n"
            "۱. یک prompt انگلیسی دقیق و تصویری (نه فارسی) برای یک مدل هوش مصنوعی تصویرساز، که یک "
            "تصویر آموزشی، تمیز و جذاب (illustration/infographic style, no text, no letters) درباره‌ی "
            "این موضوع بسازه. حتماً در prompt بگو که تصویر نباید هیچ متن یا حرفی داخلش داشته باشه.\n"
            "۲. یک عنوان کوتاه فارسی (حداکثر ۶ کلمه) که بشه زیر تصویر نوشت.\n\n"
            'خروجی رو فقط و فقط به‌صورت یک JSON با این ساختار دقیق بده: '
            '{"image_prompt": "...", "caption_fa": "..."}'
        )
        messages = [
            {"role": "system", "content": COACH_SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]

        try:
            response = await self._client.chat.completions.create(model=self._model, messages=messages)
            content = response.choices[0].message.content
            if not content:
                return None
            cleaned = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
            data = json.loads(cleaned)
            if isinstance(data, dict) and "image_prompt" in data and "caption_fa" in data:
                return data
            return None
        except Exception:
            logger.exception("خطا در ساخت prompt تصویر")
            return None

    async def generate_motivational_message(self, hint: str | None = None) -> str:
        """یک پیام کوتاه انگیزشی برای نوبت‌های میان‌روز می‌سازد."""
        instruction = "یک پیام کوتاه (۱ تا ۲ جمله)، انگیزشی و صمیمی برای یک دانش‌آموز کنکوری در وسط روز مطالعه بنویس."
        if hint:
            instruction += f" زمینه‌ی اضافه برای شخصی‌سازی: {hint}"

        messages = [
            {"role": "system", "content": COACH_SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]

        try:
            response = await self._client.chat.completions.create(model=self._model, messages=messages)
            content = response.choices[0].message.content
            return content.strip() if content else "بهت افتخار می‌کنم، به مسیرت ادامه بده! 💪"
        except Exception:
            logger.exception("خطا در ساخت پیام انگیزشی")
            return "بهت افتخار می‌کنم، به مسیرت ادامه بده! 💪"


ai_client = AIClient()
