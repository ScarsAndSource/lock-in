"""
Voice check-in and screenshot screen time: from a recording or a picture to a PROPOSAL the person confirms.

Order of business (the order is the safety design):
  validate the upload -> (voice: transcribe) -> crisis screen on the words -> parse -> proposal.
Nothing is saved here. The app shows the proposal and the person confirms through the normal check-in endpoint, so a
mishearing costs one tap, not a wrong log. Audio and images are held in memory for the one call and never stored.
A crisis phrase gets the same fixed support payload as everywhere else and never reaches the parser.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from app.config import get_settings
from app.dates import Clock, utc_now
from app.exceptions import DailyLimitError, ServiceUnavailableError, ValidationError
from app.safety import is_crisis, support_payload
from app.services.audio_sniff import inspect_audio
from app.services.image_dims import exceeds as too_many_pixels
from app.services.checkin_parser import MAX_SPEECH_CHARS, ParsedCheckin, build_messages, parse_reply
from app.services.habits_service import HabitsService
from app.services.llm import LLMBudgetExceeded, LLMError, LLMRejectedInput, MediaLLM, seconds_until_reset
from app.services.profile_service import ProfileService
from app.services import schedule_image_parser as schedule_parser
from app.services.screenshot_parser import MAX_IMAGE_BYTES, PROMPT, ParsedScreenshot, parse_reply as parse_screen, sniff_image
from app.services.task_time import zone

logger = logging.getLogger("lockin.media")

MAX_AUDIO_BYTES = 4_000_000
_AUDIO_FILES = {
    "audio/webm": "checkin.webm", "audio/ogg": "checkin.ogg", "audio/wav": "checkin.wav", "audio/x-wav": "checkin.wav",
    "audio/mp4": "checkin.m4a", "audio/x-m4a": "checkin.m4a", "audio/m4a": "checkin.m4a", "audio/aac": "checkin.m4a",
    "audio/mpeg": "checkin.mp3", "audio/mp3": "checkin.mp3",
}


@dataclass(slots=True)
class CheckinProposal:
    transcript: str | None
    parsed: ParsedCheckin = field(default_factory=ParsedCheckin)
    support: dict | None = None


class MediaService:
    def __init__(self, llm: MediaLLM, habits: HabitsService, profiles: ProfileService, clock: Clock = utc_now):
        self._llm, self._habits, self._profiles, self._clock = llm, habits, profiles, clock

    async def _guard(self, call):
        """Model failures -> the app's own errors, so the router never leaks provider detail."""
        try:
            return await call()
        except LLMBudgetExceeded as exc:
            raise DailyLimitError(seconds_until_reset(self._clock())) from exc
        except LLMRejectedInput as exc:
            logger.info("media input rejected by the provider")
            raise ValidationError("That file couldn't be processed. Try a smaller or clearer one.") from exc
        except LLMError as exc:
            logger.warning("media model call failed: %s", type(exc).__name__)
            raise ServiceUnavailableError("The assistant is unavailable right now. Try again, or log it by hand.") from exc

    # ------------------------------------------------------------------ voice / typed check-in
    async def parse_text(self, user_id: UUID, text: str) -> CheckinProposal:
        speech = " ".join((text or "").split())[:MAX_SPEECH_CHARS]
        if not speech:
            raise ValidationError("Say or type something first.")
        if is_crisis(speech):                                           # fixed support copy; the parser never sees it
            tz = (await self._profiles.get(user_id)).timezone
            return CheckinProposal(transcript=None, support=support_payload(tz))
        habits = await self._habits.list_habits(user_id)
        raw = await self._guard(lambda: self._llm.complete(build_messages(habits, speech), max_tokens=400, temperature=0))
        parsed = parse_reply(raw, habits) or ParsedCheckin()
        return CheckinProposal(transcript=speech, parsed=parsed)

    async def parse_audio(self, user_id: UUID, audio: bytes, content_type: str) -> CheckinProposal:
        base = (content_type or "").split(";")[0].strip().lower()
        filename = _AUDIO_FILES.get(base)
        if filename is None:
            raise ValidationError("That doesn't look like an audio recording.")
        if not audio:
            raise ValidationError("The recording was empty.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise ValidationError("That recording is too long. Keep it under about a minute.")
        info = inspect_audio(audio)   # what the bytes ARE, not what the client said
        if info is None:
            raise ValidationError("That doesn't look like an audio recording.")
        if info.seconds is not None and info.seconds > get_settings().max_audio_seconds:
            raise ValidationError("That recording is too long. Keep it under about a minute.")
        text = await self._guard(lambda: self._llm.transcribe(audio, info.filename, info.content_type))
        if not text.strip():
            raise ValidationError("I couldn't hear anything. Try again a bit closer to the mic.")
        return await self.parse_text(user_id, text)

    # ------------------------------------------------------------------ screenshot screen time
    async def parse_screenshot(self, image: bytes) -> ParsedScreenshot:
        if not image:
            raise ValidationError("The image was empty.")
        if len(image) > MAX_IMAGE_BYTES:
            raise ValidationError("That image is too large. Use a normal screenshot.")
        media_type = sniff_image(image)
        if media_type is None:
            raise ValidationError("Use a PNG, JPEG or WebP screenshot.")
        if too_many_pixels(image, get_settings().max_image_pixels):
            raise ValidationError("That image is too large. Use a normal screenshot.")
        raw = await self._guard(lambda: self._llm.describe_image(image, media_type, PROMPT))
        parsed = parse_screen(raw)
        if parsed is None:
            raise ValidationError("I couldn't find a daily total in that screenshot. Open the DAY view and try again.")
        return parsed

    # ------------------------------------------------------------------ timetable / notice photo
    async def parse_schedule_image(self, user_id: UUID, image: bytes) -> schedule_parser.ParsedSchedule:
        """A picture of a timetable, date sheet or notice -> proposed events and tasks. Saves nothing."""
        if not image:
            raise ValidationError("The image was empty.")
        if len(image) > MAX_IMAGE_BYTES:
            raise ValidationError("That image is too large. Use a normal photo or screenshot.")
        media_type = sniff_image(image)
        if media_type is None:
            raise ValidationError("Use a PNG, JPEG or WebP image.")
        if too_many_pixels(image, get_settings().max_image_pixels):
            raise ValidationError("That image is too large. Use a normal photo or screenshot.")
        tz = zone((await self._profiles.get(user_id)).timezone)
        today = self._clock().astimezone(tz).date()
        prompt = schedule_parser.PROMPT.format(today=today.isoformat())
        raw = await self._guard(lambda: self._llm.describe_image(image, media_type, prompt, max_tokens=1400))
        parsed = schedule_parser.parse_reply(raw, today)
        if parsed is None:
            raise ValidationError("I couldn't read dates from that picture. Try a sharper, straighter photo.")
        return parsed
