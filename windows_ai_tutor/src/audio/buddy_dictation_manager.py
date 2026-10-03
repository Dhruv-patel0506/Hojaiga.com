"""
Buddy Dictation Manager - Push-to-Talk Voice Pipeline (Clicky-style)

Shared push-to-talk dictation manager for voice input.
Captures microphone audio, routes to transcription provider.
Converted from BuddyDictationManager.swift to Windows Python.
"""

from enum import Enum
from typing import Optional, Callable
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
import pyaudio
import array

from .audio_capture import AudioCaptureManager
from .transcription_manager import TranscriptionManager
from ..utils.logger import setup_logger


class BuddyPushToTalkShortcut(Enum):
    """Push-to-talk shortcut options."""
    CONTROL_OPTION = "control_option"
    SHIFT_CONTROL = "shift_control"
    CONTROL_OPTION_SPACE = "control_option_space"
    SHIFT_CONTROL_SPACE = "shift_control_space"

    def display_text(self) -> str:
        """Get display text for the shortcut."""
        if self == BuddyPushToTalkShortcut.CONTROL_OPTION:
            return "ctrl + alt"
        elif self == BuddyPushToTalkShortcut.SHIFT_CONTROL:
            return "shift + ctrl"
        elif self == BuddyPushToTalkShortcut.CONTROL_OPTION_SPACE:
            return "ctrl + alt + space"
        elif self == BuddyPushToTalkShortcut.SHIFT_CONTROL_SPACE:
            return "shift + ctrl + space"
        return "ctrl + alt"


class ShortcutTransition(Enum):
    """Shortcut transition states."""
    NONE = "none"
    PRESSED = "pressed"
    RELEASED = "released"


class BuddyVoiceState(Enum):
    """Voice state for dictation."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"


class BuddyDictationManager(QObject):
    """
    Push-to-talk dictation manager.
    Handles microphone capture, transcription, and shortcut management.
    """

    # Signals
    is_recording_from_keyboard_shortcut = pyqtSignal(bool)
    is_finalizing_transcript = pyqtSignal(bool)
    is_preparing_to_record = pyqtSignal(bool)
    shortcut_transition = pyqtSignal(ShortcutTransition)
    current_audio_power_level = pyqtSignal(float)
    transcript_finalized = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    dictation_started = pyqtSignal()
    dictation_ended = pyqtSignal()
    voice_state_changed = pyqtSignal(str)

    def __init__(self):
        """Initialize the buddy dictation manager."""
        super().__init__()

        self.logger = setup_logger("BuddyDictationManager")

        # Shortcut configuration
        self.current_shortcut = BuddyPushToTalkShortcut.CONTROL_OPTION
        self._shortcut_pressed = False

        # Audio capture
        self.audio_capture = AudioCaptureManager()

        # Transcription
        self.transcription = TranscriptionManager()

        # Recording state
        self._is_recording = False
        self._is_finalizing = False
        self._is_preparing = False

        # Audio buffer
        self._audio_buffer = []
        self._buffer_lock = None

        # Transcription task
        self._transcription_task = None

        # Voice state
        self.voice_state = BuddyVoiceState.IDLE

        self.logger.info("Buddy dictation manager initialized")

    def start(self):
        """Start the dictation manager."""
        self.logger.info("Starting buddy dictation manager...")
        self._is_recording = False
        self._is_finalizing = False
        self._is_preparing = False
        self._audio_buffer = []
        self.logger.info("Buddy dictation manager started")

    def stop(self):
        """Stop the dictation manager."""
        self.logger.info("Stopping buddy dictation manager...")
        if self._is_recording:
            self.cancel_current_dictation()
        self.logger.info("Buddy dictation manager stopped")

    def start_dictation_session(self):
        """Start a dictation session from keyboard shortcut."""
        self.logger.info("Starting dictation session...")
        self._is_recording = True
        self._is_finalizing = False
        self._is_preparing = False
        self._audio_buffer = []
        self.voice_state = BuddyVoiceState.LISTENING
        self.voice_state_changed.emit(self.voice_state.value)

        self.is_recording_from_keyboard_shortcut.emit(True)
        self.shortcut_transition.emit(ShortcutTransition.PRESSED)
        self.dictation_started.emit()

        # Start audio capture
        self.audio_capture.start_recording()

        # Connect audio data signal
        self.audio_capture.audio_data_available.connect(self._on_audio_data)

    def end_dictation_session(self):
        """End the dictation session and process audio."""
        self.logger.info("Ending dictation session...")
        self._is_recording = False
        self._is_finalizing = True
        self.voice_state = BuddyVoiceState.PROCESSING
        self.voice_state_changed.emit(self.voice_state.value)

        self.is_recording_from_keyboard_shortcut.emit(False)
        self.shortcut_transition.emit(ShortcutTransition.RELEASED)
        self.dictation_ended.emit()

        # Stop audio capture
        self.audio_capture.stop_recording()

        # Disconnect audio data signal
        try:
            self.audio_capture.audio_data_available.disconnect(self._on_audio_data)
        except:
            pass

        # Process captured audio
        if self._audio_buffer:
            self._process_audio_for_transcription()

        self.voice_state = BuddyVoiceState.IDLE
        self.voice_state_changed.emit(self.voice_state.value)

    def cancel_current_dictation(self):
        """Cancel the current dictation session."""
        self.logger.info("Canceling current dictation...")
        self._is_recording = False
        self._is_finalizing = False
        self._audio_buffer = []

        self.audio_capture.stop_recording()

        try:
            self.audio_capture.audio_data_available.disconnect(self._on_audio_data)
        except:
            pass

        self.is_recording_from_keyboard_shortcut.emit(False)

    def _on_audio_data(self, audio_data: bytes):
        """Handle incoming audio data."""
        if self._is_recording:
            self._audio_buffer.append(audio_data)

    def _process_audio_for_transcription(self):
        """Process captured audio for transcription."""
        self.logger.info(f"Processing {len(self._audio_buffer)} audio chunks for transcription...")

        # Combine audio chunks
        combined_audio = b''.join(self._audio_buffer)

        # Transcribe
        try:
            transcript = self.transcription.transcribe(combined_audio)
            if transcript:
                self.transcript_finalized.emit(transcript)
                self.logger.info(f"Transcript finalized: {transcript}")
            else:
                self.logger.warning("Transcription returned empty result")
        except Exception as e:
            self.logger.error(f"Transcription error: {e}")
            self.error_occurred.emit(f"Transcription error: {str(e)}")

        # Reset state
        self._is_finalizing = False
        self._audio_buffer = []

    def set_shortcut(self, shortcut: BuddyPushToTalkShortcut):
        """Set the push-to-talk shortcut."""
        self.logger.info(f"Setting shortcut to: {shortcut.value}")
        self.current_shortcut = shortcut

    def stop(self):
        """Stop the dictation manager."""
        self.logger.info("Stopping buddy dictation manager...")
        self.cancel_current_dictation()
        self.audio_capture.stop()
