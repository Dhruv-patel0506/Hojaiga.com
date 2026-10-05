"""
Buddy Transcription Provider - Transcription Protocol (Clicky-style)

Shared protocol surface for voice transcription backends.
Converted from BuddyTranscriptionProvider.swift to Windows Python.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal


class BuddyStreamingTranscriptionSession(ABC):
    """Protocol for streaming transcription sessions."""

    @property
    @abstractmethod
    def final_transcript_fallback_delay_seconds(self) -> float:
        """Delay before requesting final transcript."""
        pass

    @abstractmethod
    def append_audio_buffer(self, audio_data: bytes):
        """Append audio buffer to the session."""
        pass

    @abstractmethod
    def request_final_transcript(self):
        """Request the final transcript."""
        pass

    @abstractmethod
    def cancel(self):
        """Cancel the session."""
        pass


class BuddyTranscriptionProvider(ABC):
    """Protocol for transcription providers."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Display name of the provider."""
        pass

    @property
    @abstractmethod
    def requires_speech_recognition_permission(self) -> bool:
        """Whether this provider requires speech recognition permission."""
        pass

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider is properly configured."""
        pass

    @property
    @abstractmethod
    def unavailable_explanation(self) -> Optional[str]:
        """Explanation if provider is unavailable."""
        pass

    @abstractmethod
    async def start_streaming_session(
        self,
        keyterms: list[str],
        on_transcript_update: Callable[[str], None],
        on_final_transcript_ready: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ) -> BuddyStreamingTranscriptionSession:
        """Start a streaming transcription session."""
        pass


class BuddyTranscriptionProviderFactory:
    """Factory for creating transcription providers."""

    @staticmethod
    def make_default_provider(config_manager=None) -> BuddyTranscriptionProvider:
        """Create the default transcription provider (prioritize FREE options)."""
        from .vosk_transcription_provider import VoskTranscriptionProvider
        from .windows_speech_transcription_provider import WindowsSpeechTranscriptionProvider
        from ..utils.logger import setup_logger

        logger = setup_logger("BuddyTranscriptionProviderFactory")

        # Try Vosk first (FREE, offline, works on Python 3.13)
        model_path = "models/vosk-model-small-en-us-0.15"
        if config_manager:
            model_path = config_manager.get("vosk_model_path", model_path)

        vosk_provider = VoskTranscriptionProvider(model_path=model_path)
        if vosk_provider.is_configured:
            logger.info(f"Transcription: using {vosk_provider.display_name}")
            return vosk_provider

        # Fall back to Windows Speech (FREE, built-in)
        windows_provider = WindowsSpeechTranscriptionProvider()
        logger.info(f"Transcription: using {windows_provider.display_name}")
        return windows_provider
