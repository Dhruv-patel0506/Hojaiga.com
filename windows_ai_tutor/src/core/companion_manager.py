"""
Companion Manager - Central State Manager (Clicky-style)

This is the central state manager that coordinates all components.
Converted from CompanionManager.swift to Windows Python.
"""

from enum import Enum
from typing import Optional, Tuple
from PyQt5.QtCore import QObject, pyqtSignal, pyqtProperty, QTimer
from PyQt5.QtCore import QPoint, QRect
import asyncio

from ..audio.audio_capture import AudioCaptureManager
from ..audio.buddy_dictation_manager import BuddyDictationManager, ShortcutTransition
from ..audio.transcription_manager import TranscriptionManager
from ..audio.tts_manager import TTSManager
from ..vision.screen_capture import ScreenCaptureUtility
from ..vision.companion_screen_capture_utility import CompanionScreenCaptureUtility
from ..ai.llm_manager import LLMManager
from ..ai.claude_api import ClaudeAPI
from ..core.global_push_to_talk_shortcut_monitor import GlobalPushToTalkShortcutMonitor
from ..core.window_position_manager import WindowPositionManager
from ..core.clicky_analytics import ClickyAnalytics
from ..vision.element_location_detector import ElementLocationDetector
from ..ui.cursor_overlay_manager import CursorOverlayManager
from ..ui.companion_response_overlay import CompanionResponseOverlayManager
from ..utils.logger import setup_logger
from ..utils.config import ConfigManager


class CompanionVoiceState(Enum):
    """Voice interaction states."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"


class CompanionManager(QObject):
    """
    Central state manager for the Windows AI Tutor (Clicky-style).
    Coordinates voice pipeline, screen capture, AI processing, and cursor overlay.
    """

    # Signals
    voice_state_changed = pyqtSignal(str)  # Voice state changes
    transcript_received = pyqtSignal(str)  # New transcript
    response_received = pyqtSignal(str)  # AI response
    cursor_location_detected = pyqtSignal(tuple)  # (x, y, label, screen_number)
    screen_display_frame = pyqtSignal(QRect)  # Display frame for cursor
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the companion manager.

        Args:
            config_manager: Configuration manager instance
        """
        super().__init__()

        self.logger = setup_logger("CompanionManager")
        self.config = config_manager

        # Voice state
        self._voice_state = CompanionVoiceState.IDLE
        self._last_transcript: Optional[str] = None
        self._current_audio_power_level: float = 0.0

        # Permissions
        self._has_accessibility_permission = False
        self._has_screen_recording_permission = False
        self._has_microphone_permission = False

        # Cursor overlay state
        self._detected_element_screen_location: Optional[QPoint] = None
        self._detected_element_display_frame: Optional[QRect] = None
        self._detected_element_bubble_text: Optional[str] = None
        self._is_overlay_visible = False
        self._is_cursor_enabled = True

        # Conversation history
        self._conversation_history: list[Tuple[str, str]] = []

        # Components
        self.audio_capture = AudioCaptureManager()
        self.dictation_manager = BuddyDictationManager()
        self.transcription = TranscriptionManager(config_manager=config_manager)
        self.tts = TTSManager()
        self.screen_capture = ScreenCaptureUtility()
        self.llm = LLMManager(config_manager)
        self.claude_api = ClaudeAPI(
            proxy_url=config_manager.get("llamacpp_host", "http://localhost:8081/v1/chat"),
            model=config_manager.get("model", "Qwen2.5-VL-7B-Instruct")
        )
        self.cursor_overlay = CursorOverlayManager()
        self.response_overlay = CompanionResponseOverlayManager()
        self.element_detector = ElementLocationDetector()
        self.shortcut_monitor = GlobalPushToTalkShortcutMonitor()
        self.window_position_manager = WindowPositionManager()

        # Permission polling timer
        self._permission_check_timer = QTimer()
        self._permission_check_timer.timeout.connect(self._refresh_all_permissions)

        self.logger.info("Companion manager initialized")

    @pyqtProperty(str)
    def voice_state(self) -> str:
        """Current voice state."""
        return self._voice_state.value

    @voice_state.setter
    def voice_state(self, value):
        """Set voice state and emit signal."""
        # Handle both enum and string input
        if isinstance(value, CompanionVoiceState):
            state_value = value.value
            self._voice_state = value
        else:
            state_value = str(value)
            self._voice_state = CompanionVoiceState(state_value)

        self.voice_state_changed.emit(state_value)
        self.logger.info(f"Voice state changed to: {state_value}")

    @pyqtProperty(bool)
    def has_accessibility_permission(self) -> bool:
        """Accessibility permission status."""
        return self._has_accessibility_permission

    @pyqtProperty(bool)
    def has_screen_recording_permission(self) -> bool:
        """Screen recording permission status."""
        return self._has_screen_recording_permission

    @pyqtProperty(bool)
    def has_microphone_permission(self) -> bool:
        """Microphone permission status."""
        return self._has_microphone_permission

    @pyqtProperty(bool)
    def all_permissions_granted(self) -> bool:
        """All permissions granted status."""
        return (self._has_accessibility_permission and
                self._has_screen_recording_permission and
                self._has_microphone_permission)

    @pyqtProperty(bool)
    def is_overlay_visible(self) -> bool:
        """Overlay visibility status."""
        return self._is_overlay_visible

    @pyqtProperty(bool)
    def is_cursor_enabled(self) -> bool:
        """Cursor enabled status."""
        return self._is_cursor_enabled

    def set_cursor_enabled(self, enabled: bool):
        """Enable/disable cursor overlay."""
        self._is_cursor_enabled = enabled
        if enabled:
            self.cursor_overlay.show()
            self._is_overlay_visible = True
        else:
            self.cursor_overlay.hide()
            self._is_overlay_visible = False
        self.logger.info(f"Cursor enabled: {enabled}")

    def start(self):
        """Start the companion manager."""
        self.logger.info("Starting companion manager...")
        self._refresh_all_permissions()
        self._start_permission_polling()

        # Start components
        self.audio_capture.start()
        self.dictation_manager.start()
        self.screen_capture.start()
        self.cursor_overlay.start()
        self.shortcut_monitor.start()

        # Connect shortcut signals
        self.shortcut_monitor.shortcut_transition.connect(self._on_shortcut_transition)
        self.dictation_manager.transcript_finalized.connect(self._on_transcript_finalized)

        # If all permissions granted and cursor enabled, show overlay
        if self.all_permissions_granted and self._is_cursor_enabled:
            self.cursor_overlay.show()
            self._is_overlay_visible = True

        self.logger.info("Companion manager started")

    def stop(self):
        """Stop the companion manager."""
        self.logger.info("Stopping companion manager...")
        self._permission_check_timer.stop()

        # Stop components
        self.audio_capture.stop()
        self.transcription.stop()
        self.tts.stop()
        self.screen_capture.stop()
        self.cursor_overlay.stop()

        self.logger.info("Companion manager stopped")

    def _refresh_all_permissions(self):
        """Refresh all permission states."""
        # For Windows, we'll simulate permission checks
        # In a real implementation, these would check actual Windows permissions
        self._has_accessibility_permission = True
        self._has_screen_recording_permission = True
        self._has_microphone_permission = True

        self.logger.info(f"Permissions refreshed - accessibility: {self._has_accessibility_permission}, "
                        f"screen: {self._has_screen_recording_permission}, "
                        f"mic: {self._has_microphone_permission}")

    def _start_permission_polling(self):
        """Start periodic permission checks."""
        self._permission_check_timer.start(1500)  # Check every 1.5 seconds

    def on_hotkey_pressed(self):
        """Handle hotkey press (Ctrl activation)."""
        self.logger.info("Hotkey pressed - starting voice input")
        self.voice_state = CompanionVoiceState.LISTENING.value  # Use string value
        self._show_text_input_dialog()

    def _show_text_input_dialog(self):
        """Show a text input dialog as fallback when transcription is unavailable."""
        from PyQt5.QtWidgets import QInputDialog, QApplication

        self.logger.info("Showing text input dialog (transcription unavailable)")

        app = QApplication.instance()
        if app:
            dialog = QInputDialog()
            dialog.setWindowTitle("Windows AI Tutor")
            dialog.setLabelText("What would you like to ask?")
            dialog.setTextValue("")

            if dialog.exec_() == QInputDialog.Accepted:
                text = dialog.textValue()
                if text:
                    self.logger.info(f"Text input received: {text}")
                    self._last_transcript = text
                    self.transcript_received.emit(text)
                    self._process_ai_response(text)
                else:
                    self.voice_state = CompanionVoiceState.IDLE.value
            else:
                self.voice_state = CompanionVoiceState.IDLE.value

    def on_hotkey_released(self):
        """Handle hotkey release."""
        self.logger.info("Hotkey released - processing voice input")
        self.voice_state = CompanionVoiceState.PROCESSING.value  # Use string value



    def _parse_cursor_coordinates(self, response: str):
        """Parse cursor coordinates from AI response."""
        # Parse format: [POINT:x,y:label:screenN]
        import re
        pattern = r'\[POINT:(\d+),(\d+):([^:]+):screen(\d+)\]'
        matches = re.findall(pattern, response)

        if matches:
            self.logger.info(f"Found {len(matches)} coordinate(s) in response")
        else:
            self.logger.info("No coordinates found in response")

        for match in matches:
            x, y, label, screen_num = match
            self._detected_element_screen_location = QPoint(int(x), int(y))
            self._detected_element_bubble_text = label
            self.cursor_location_detected.emit((int(x), int(y), label, int(screen_num)))
            self.logger.info(f"Cursor location detected: {x}, {y} - {label}")

            # Animate cursor to location
            self.cursor_overlay.animate_to_position(int(x), int(y), label)

    def _on_shortcut_transition(self, transition: ShortcutTransition):
        """Handle shortcut transition (pressed/released)."""
        if transition == ShortcutTransition.PRESSED:
            self.on_hotkey_pressed()
        elif transition == ShortcutTransition.RELEASED:
            self.on_hotkey_released()

    def _on_transcript_finalized(self, transcript: str):
        """Handle finalized transcript from dictation manager."""
        self.logger.info(f"Transcript finalized: {transcript}")
        self._last_transcript = transcript
        self.transcript_received.emit(transcript)

        # Process with AI (simplified - no screenshot for now)
        self._process_ai_response(transcript)

    def _process_ai_response(self, transcript: str):
        """Process transcript with AI including screen capture."""
        try:
            # Temporarily disable screen capture to test text-only pipeline
            self.logger.info("Processing AI response (text-only for testing)")
            screenshot = None

            # Get response from LLM with screenshot
            response = self.llm.generate_simple_response(transcript, images=None)

            self.response_received.emit(response)
            self.voice_state = CompanionVoiceState.RESPONDING.value  # Use string value

            # Show response overlay
            self.response_overlay.show_overlay_and_begin_streaming()
            self.response_overlay.update_streaming_text(response)
            self.response_overlay.finish_streaming()

            # TTS disabled for now - engine initialization issue
            # self.tts._speak_sync(response)

            # Parse coordinates from response
            self._parse_cursor_coordinates(response)

            self.voice_state = CompanionVoiceState.IDLE.value  # Use string value

        except Exception as e:
            self.logger.error(f"Error processing AI response: {e}")
            self.error_occurred.emit(f"AI error: {str(e)}")
            self.voice_state = CompanionVoiceState.IDLE.value  # Use string value
