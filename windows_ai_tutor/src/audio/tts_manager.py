"""
TTS Manager - Text to Speech

This manages text-to-speech conversion and playback.
Equivalent to ElevenLabsTTSClient in Clicky.
"""

import asyncio
from typing import Optional
from PyQt5.QtCore import QObject, pyqtSignal
import pyttsx3

from ..utils.logger import setup_logger


class TTSManager(QObject):
    """
    Manages text-to-speech conversion and playback.
    Uses pyttsx3 for offline TTS.
    """

    # Signals
    playback_started = pyqtSignal()
    playback_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self):
        """Initialize the TTS manager."""
        super().__init__()

        self.logger = setup_logger("TTSManager")

        # TTS engine
        self.engine: Optional[pyttsx3.Engine] = None

        # Playback state
        self._is_playing = False
        self._playback_task: Optional[asyncio.Task] = None

        # Voice settings
        self.voice_rate = 150  # Words per minute
        self.voice_volume = 0.9  # 0.0 to 1.0

        self.logger.info("TTS manager initialized")

    def _initialize_engine(self):
        """Initialize the TTS engine."""
        if self.engine is None:
            try:
                self.engine = pyttsx3.init()

                # Set voice properties
                self.engine.setProperty('rate', self.voice_rate)
                self.engine.setProperty('volume', self.voice_volume)

                self.logger.info("TTS engine initialized")

            except Exception as e:
                self.logger.error(f"Failed to initialize TTS engine: {e}")
                self.error_occurred.emit(f"Failed to initialize TTS: {str(e)}")
                raise

    async def speak_text(self, text: str):
        """
        Convert text to speech and play it.

        Args:
            text: Text to speak
        """
        if not text.strip():
            self.logger.warning("Empty text provided to TTS")
            return

        if self._is_playing:
            self.logger.warning("TTS already playing")
            self.stop_playback()

        try:
            # Initialize engine if needed
            self._initialize_engine()

            self._is_playing = True
            self.playback_started.emit()

            self.logger.info(f"Speaking: {text[:50]}...")

            # Run TTS in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._speak_sync(text)
            )

            self._is_playing = False
            self.playback_finished.emit()

            self.logger.info("TTS playback finished")

        except Exception as e:
            self.logger.error(f"Error during TTS playback: {e}")
            self._is_playing = False
            self.error_occurred.emit(f"TTS error: {str(e)}")

    def _speak_sync(self, text: str):
        """
        Synchronous TTS playback (runs in thread).

        Args:
            text: Text to speak
        """
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            self.logger.error(f"Error in synchronous TTS: {e}")
            raise

    def stop_playback(self):
        """Stop current TTS playback."""
        if self._is_playing and self.engine:
            try:
                self.engine.stop()
                self._is_playing = False
                self.logger.info("TTS playback stopped")
            except Exception as e:
                self.logger.error(f"Error stopping TTS: {e}")

    @property
    def is_playing(self) -> bool:
        """Check if TTS is currently playing."""
        return self._is_playing

    def set_voice_rate(self, rate: int):
        """
        Set the voice rate (words per minute).

        Args:
            rate: Voice rate (default: 150)
        """
        self.voice_rate = rate
        if self.engine:
            self.engine.setProperty('rate', rate)
        self.logger.info(f"Voice rate set to: {rate}")

    def set_voice_volume(self, volume: float):
        """
        Set the voice volume.

        Args:
            volume: Volume level (0.0 to 1.0)
        """
        self.voice_volume = max(0.0, min(1.0, volume))
        if self.engine:
            self.engine.setProperty('volume', self.voice_volume)
        self.logger.info(f"Voice volume set to: {self.voice_volume}")

    def cleanup(self):
        """Clean up resources."""
        self.stop_playback()
        if self.engine:
            try:
                self.engine = None
            except Exception as e:
                self.logger.error(f"Error during TTS cleanup: {e}")

        self.logger.info("TTS manager cleaned up")