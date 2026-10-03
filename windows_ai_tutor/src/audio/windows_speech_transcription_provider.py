"""
Windows Speech Transcription Provider - Local Windows Speech (Clicky-style)

Local Windows Speech recognition provider (fallback when cloud APIs unavailable).
This replaces AppleSpeechTranscriptionProvider for Windows.
"""

import asyncio
from typing import Optional, Callable

from .buddy_transcription_provider import BuddyTranscriptionProvider, BuddyStreamingTranscriptionSession
from ..utils.logger import setup_logger


class WindowsSpeechTranscriptionProvider(BuddyTranscriptionProvider):
    """Windows Speech recognition provider (local fallback)."""

    def __init__(self):
        """Initialize the Windows Speech provider."""
        self.logger = setup_logger("WindowsSpeechTranscriptionProvider")

    @property
    def display_name(self) -> str:
        """Display name of the provider."""
        return "Windows Speech"

    @property
    def requires_speech_recognition_permission(self) -> bool:
        """Whether this provider requires speech recognition permission."""
        return False

    @property
    def is_configured(self) -> bool:
        """Whether this provider is properly configured."""
        # Windows Speech is always available on Windows
        return True

    @property
    def unavailable_explanation(self) -> Optional[str]:
        """Explanation if provider is unavailable."""
        return None

    async def start_streaming_session(
        self,
        keyterms: list[str],
        on_transcript_update: Callable[[str], None],
        on_final_transcript_ready: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ) -> BuddyStreamingTranscriptionSession:
        """Start a streaming transcription session."""
        return WindowsSpeechTranscriptionSession(
            keyterms=keyterms,
            on_transcript_update=on_transcript_update,
            on_final_transcript_ready=on_final_transcript_ready,
            on_error=on_error
        )


class WindowsSpeechTranscriptionSession(BuddyStreamingTranscriptionSession):
    """Windows Speech transcription session."""

    @property
    def final_transcript_fallback_delay_seconds(self) -> float:
        """Delay before requesting final transcript."""
        return 5.0

    def __init__(
        self,
        keyterms: list[str],
        on_transcript_update: Callable[[str], None],
        on_final_transcript_ready: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ):
        """Initialize the transcription session."""
        self.keyterms = keyterms
        self.on_transcript_update = on_transcript_update
        self.on_final_transcript_ready = on_final_transcript_ready
        self.on_error = on_error

        self.logger = setup_logger("WindowsSpeechTranscriptionSession")

        # State
        self.buffered_audio_data = bytearray()
        self.has_requested_final_transcript = False
        self.has_delivered_final_transcript = False
        self.is_cancelled = False

    def append_audio_buffer(self, audio_data: bytes):
        """Append audio buffer to the session."""
        if self.is_cancelled or self.has_requested_final_transcript:
            return
        self.buffered_audio_data.extend(audio_data)

    def request_final_transcript(self):
        """Request the final transcript."""
        if self.has_requested_final_transcript or self.is_cancelled:
            return

        self.has_requested_final_transcript = True

        # For now, return empty since Windows Speech requires more setup
        # This is a placeholder - would need SpeechRecognition library
        self._deliver_final_transcript("")

    def cancel(self):
        """Cancel the session."""
        self.is_cancelled = True
        self.buffered_audio_data.clear()

    def _deliver_final_transcript(self, transcript_text: str):
        """Deliver the final transcript."""
        if self.has_delivered_final_transcript:
            return

        self.has_delivered_final_transcript = True
        self.on_final_transcript_ready(transcript_text)
