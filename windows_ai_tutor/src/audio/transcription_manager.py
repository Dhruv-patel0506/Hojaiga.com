"""
Transcription Manager - Speech to Text

This manages speech transcription using Vosk (FREE offline).
Simplified wrapper around VoskTranscriptionProvider.
"""

from typing import Optional
from PyQt5.QtCore import QObject, pyqtSignal

from .buddy_transcription_provider import BuddyTranscriptionProviderFactory
from ..utils.logger import setup_logger
from ..utils.config import ConfigManager


class TranscriptionManager(QObject):
    """
    Manages speech transcription using Vosk (FREE offline).
    Simplified wrapper for the Clicky architecture.
    """

    # Signals
    transcript_update = pyqtSignal(str)  # Partial transcript
    final_transcript = pyqtSignal(str)  # Final transcript
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self, model_size: str = "base", config_manager: Optional[ConfigManager] = None):
        """
        Initialize the transcription manager.

        Args:
            model_size: Model size (ignored, using Vosk)
            config_manager: Configuration manager instance
        """
        super().__init__()

        self.logger = setup_logger("TranscriptionManager")
        self.config_manager = config_manager

        # Get the transcription provider
        self.provider = BuddyTranscriptionProviderFactory.make_default_provider(config_manager)

        self.logger.info(f"Transcription manager initialized with: {self.provider.display_name}")

    @property
    def is_available(self) -> bool:
        """Check if transcription is available."""
        return self.provider.is_configured

    def transcribe(self, audio_data: bytes) -> str:
        """
        Transcribe audio data (synchronous wrapper).

        Args:
            audio_data: Raw audio data bytes

        Returns:
            Transcribed text
        """
        # For now, return empty - this is a placeholder
        # The actual transcription happens through BuddyDictationManager
        self.logger.warning("Direct transcribe() called - use BuddyDictationManager instead")
        return ""
