"""
State Manager - Central State Machine

This is the central state manager that coordinates all components.
Equivalent to CompanionManager.swift in Clicky.
"""

from enum import Enum
from typing import Optional, List, Tuple
from PyQt5.QtCore import QObject, pyqtSignal, QState, QStateMachine, QFinalState
from PyQt5.QtCore import Qt
import asyncio

from ..audio.audio_capture import AudioCaptureManager
from ..audio.transcription_manager import TranscriptionManager
from ..audio.tts_manager import TTSManager
from ..vision.screen_capture import ScreenCaptureUtility
from ..ai.llm_manager import LLMManager
from ..ui.cursor_overlay import CursorOverlayManager
from ..utils.logger import setup_logger


class VoiceState(Enum):
    """Voice interaction states."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    RESPONDING = "responding"


class StateManager(QObject):
    """
    Central state manager for the Windows AI Tutor.
    Coordinates voice pipeline, screen capture, AI processing, and cursor overlay.
    """

    # Signals
    state_changed = pyqtSignal(str)  # Voice state changes
    transcript_received = pyqtSignal(str)  # New transcript
    response_received = pyqtSignal(str)  # AI response
    cursor_location_detected = pyqtSignal(tuple)  # (x, y, label, screen_number)
    permission_changed = pyqtSignal(str, bool)  # Permission type, granted status
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self, config_manager):
        """
        Initialize the state manager.

        Args:
            config_manager: Configuration manager instance
        """
        super().__init__()

        self.logger = setup_logger("StateManager")
        self.config = config_manager

        # Current state
        self._voice_state = VoiceState.IDLE
        self._last_transcript: Optional[str] = None
        self._current_audio_level: float = 0.0

        # Permission states
        self._has_microphone_permission = False
        self._has_accessibility_permission = False
        self._has_screen_recording_permission = False

        # Cursor overlay state
        self._detected_element_location: Optional[Tuple[float, float]] = None
        self._detected_element_screen_frame: Optional[Tuple[float, float, float, float]] = None
        self._detected_element_label: Optional[str] = None
        self._is_overlay_visible = False

        # User preferences
        self._is_cursor_enabled = self.config.get("show_cursor", True)
        self._selected_model = self.config.get("model", "llama3")

        # Onboarding state
        self._has_completed_onboarding = self.config.get("has_completed_onboarding", False)

        # Conversation history
        self._conversation_history: List[Tuple[str, str]] = []  # (user, assistant)

        # Initialize component managers
        self.audio_capture = AudioCaptureManager()
        self.transcription_manager = TranscriptionManager()
        self.tts_manager = TTSManager()
        self.screen_capture = ScreenCaptureUtility()
        self.llm_manager = LLMManager(self.config)
        self.cursor_overlay = CursorOverlayManager()

        # Connect component signals
        self._connect_component_signals()

        # Current AI response task
        self._current_response_task: Optional[asyncio.Task] = None

        self.logger.info("State manager initialized")

    def _connect_component_signals(self):
        """Connect signals from component managers."""
        # Audio capture signals
        self.audio_capture.audio_level_changed.connect(self._on_audio_level_changed)
        self.audio_capture.error_occurred.connect(self._on_audio_error)

        # Transcription signals
        self.transcription_manager.transcript_update.connect(self._on_transcript_update)
        self.transcription_manager.final_transcript.connect(self._on_final_transcript)
        self.transcription_manager.error_occurred.connect(self._on_transcription_error)

        # TTS signals
        self.tts_manager.playback_started.connect(self._on_tts_started)
        self.tts_manager.playback_finished.connect(self._on_tts_finished)
        self.tts_manager.error_occurred.connect(self._on_tts_error)

        # LLM signals
        self.llm_manager.response_chunk.connect(self._on_llm_response_chunk)
        self.llm_manager.response_complete.connect(self._on_llm_response_complete)
        self.llm_manager.error_occurred.connect(self._on_llm_error)

        self.logger.info("Component signals connected")

    # State management
    @property
    def voice_state(self) -> VoiceState:
        """Get current voice state."""
        return self._voice_state

    def _set_voice_state(self, state: VoiceState):
        """Set voice state and emit signal."""
        if self._voice_state != state:
            self._voice_state = state
            self.state_changed.emit(state.value)
            self.logger.info(f"Voice state changed to: {state.value}")

    # Permission management
    @property
    def has_microphone_permission(self) -> bool:
        """Check microphone permission."""
        return self._has_microphone_permission

    @property
    def has_accessibility_permission(self) -> bool:
        """Check accessibility permission."""
        return self._has_accessibility_permission

    @property
    def has_screen_recording_permission(self) -> bool:
        """Check screen recording permission."""
        return self._has_screen_recording_permission

    @property
    def all_permissions_granted(self) -> bool:
        """Check if all permissions are granted."""
        return (self._has_microphone_permission and
                self._has_accessibility_permission and
                self._has_screen_recording_permission)

    @property
    def has_completed_onboarding(self) -> bool:
        """Check if user has completed onboarding."""
        return self._has_completed_onboarding

    def set_permission(self, permission_type: str, granted: bool):
        """Set permission status."""
        if permission_type == "microphone":
            self._has_microphone_permission = granted
        elif permission_type == "accessibility":
            self._has_accessibility_permission = granted
        elif permission_type == "screen_recording":
            self._has_screen_recording_permission = granted

        self.permission_changed.emit(permission_type, granted)
        self.logger.info(f"Permission {permission_type}: {granted}")

    # Cursor management
    @property
    def is_cursor_enabled(self) -> bool:
        """Check if cursor overlay is enabled."""
        return self._is_cursor_enabled

    def set_cursor_enabled(self, enabled: bool):
        """Enable or disable cursor overlay."""
        self._is_cursor_enabled = enabled
        self.config.set("show_cursor", enabled)

        if enabled:
            self.cursor_overlay.show_overlay()
            self._is_overlay_visible = True
        else:
            self.cursor_overlay.hide_overlay()
            self._is_overlay_visible = False

        self.logger.info(f"Cursor overlay: {enabled}")

    # Hotkey handlers
    def on_hotkey_pressed(self):
        """Handle hotkey press event."""
        if self._voice_state != VoiceState.IDLE:
            return

        self.logger.info("Hotkey pressed - starting voice interaction")

        # Cancel any ongoing response
        if self._current_response_task:
            self._current_response_task.cancel()
            self._current_response_task = None

        # Stop any ongoing TTS
        self.tts_manager.stop_playback()

        # Clear detected element location
        self._clear_detected_element()

        # Start listening
        self._set_voice_state(VoiceState.LISTENING)
        asyncio.create_task(self._start_listening())

    def on_hotkey_released(self):
        """Handle hotkey release event."""
        if self._voice_state != VoiceState.LISTENING:
            return

        self.logger.info("Hotkey released - stopping listening")

        # Stop listening and start processing
        self._set_voice_state(VoiceState.PROCESSING)
        asyncio.create_task(self._stop_listening_and_process())

    # Voice pipeline
    async def _start_listening(self):
        """Start audio capture and transcription."""
        try:
            # Start audio capture
            await self.audio_capture.start_capture()

            # Start transcription
            await self.transcription_manager.start_transcription(
                on_update=lambda text: self._on_transcript_update(text),
                on_final=lambda text: self._on_final_transcript(text)
            )

        except Exception as e:
            self.logger.error(f"Error starting listening: {e}")
            self.error_occurred.emit(f"Failed to start listening: {str(e)}")
            self._set_voice_state(VoiceState.IDLE)

    async def _stop_listening_and_process(self):
        """Stop audio capture and process the transcript."""
        try:
            # Stop audio capture
            await self.audio_capture.stop_capture()

            # Stop transcription and get final transcript
            final_transcript = await self.transcription_manager.stop_transcription()

            if final_transcript:
                self._last_transcript = final_transcript
                self.transcript_received.emit(final_transcript)

                # Process with AI
                await self._process_with_ai(final_transcript)
            else:
                self.logger.warning("No transcript received")
                self._set_voice_state(VoiceState.IDLE)

        except Exception as e:
            self.logger.error(f"Error processing transcript: {e}")
            self.error_occurred.emit(f"Failed to process: {str(e)}")
            self._set_voice_state(VoiceState.IDLE)

    async def _process_with_ai(self, transcript: str):
        """Process transcript with AI using screen context."""
        try:
            # Capture screen
            screen_captures = await self.screen_capture.capture_all_screens()

            # Build prompt with screen context
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(transcript, screen_captures)

            # Send to LLM
            self._current_response_task = asyncio.create_task(
                self.llm_manager.generate_response(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    images=screen_captures,
                    conversation_history=self._conversation_history,
                    on_chunk=lambda chunk: self._on_llm_response_chunk(chunk)
                )
            )

            response = await self._current_response_task
            self._current_response_task = None

            # Parse response for pointing coordinates
            self._parse_pointing_coordinates(response)

            # Add to conversation history
            self._conversation_history.append((transcript, response))

            # Keep only last 10 exchanges
            if len(self._conversation_history) > 10:
                self._conversation_history = self._conversation_history[-10:]

            # Play response via TTS
            if response.strip():
                await self.tts_manager.speak_text(response)

        except Exception as e:
            self.logger.error(f"Error processing with AI: {e}")
            self.error_occurred.emit(f"AI processing failed: {str(e)}")
            self._set_voice_state(VoiceState.IDLE)

    # Signal handlers
    def _on_audio_level_changed(self, level: float):
        """Handle audio level changes."""
        self._current_audio_level = level

    def _on_transcript_update(self, text: str):
        """Handle partial transcript updates."""
        self.logger.debug(f"Transcript update: {text}")

    def _on_final_transcript(self, text: str):
        """Handle final transcript."""
        self.logger.info(f"Final transcript: {text}")

    def _on_llm_response_chunk(self, chunk: str):
        """Handle streaming LLM response."""
        self.logger.debug(f"LLM chunk: {chunk}")

    def _on_llm_response_complete(self, response: str):
        """Handle complete LLM response."""
        self.logger.info(f"LLM response complete: {response[:100]}...")
        self.response_received.emit(response)

    def _on_tts_started(self):
        """Handle TTS playback start."""
        self._set_voice_state(VoiceState.RESPONDING)

    def _on_tts_finished(self):
        """Handle TTS playback finish."""
        self._set_voice_state(VoiceState.IDLE)

    # Error handlers
    def _on_audio_error(self, error: str):
        """Handle audio capture errors."""
        self.logger.error(f"Audio error: {error}")
        self.error_occurred.emit(error)

    def _on_transcription_error(self, error: str):
        """Handle transcription errors."""
        self.logger.error(f"Transcription error: {error}")
        self.error_occurred.emit(error)

    def _on_tts_error(self, error: str):
        """Handle TTS errors."""
        self.logger.error(f"TTS error: {error}")
        self.error_occurred.emit(error)

    def _on_llm_error(self, error: str):
        """Handle LLM errors."""
        self.logger.error(f"LLM error: {error}")
        self.error_occurred.emit(error)

    # Helper methods
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the AI."""
        return """You are a helpful AI teaching assistant that lives on the user's computer. You can see their screen and help them learn how to use applications, understand code, or complete tasks.

Rules:
- Be concise and direct - 1-2 sentences by default
- Use natural, conversational language
- Reference specific elements you see on screen when helpful
- If the user asks for detailed explanations, provide thorough answers
- Don't use markdown or formatting - speak naturally
- When pointing at screen elements would be helpful, use the [POINT:x,y:label] format
- The coordinates should be in the screenshot's pixel space (0,0 at top-left)
- If pointing wouldn't help, use [POINT:none]"""

    def _build_user_prompt(self, transcript: str, screen_captures) -> str:
        """Build the user prompt with screen context."""
        prompt = transcript

        # Add screen information
        if screen_captures:
            prompt += "\n\nScreen context: "
            for i, capture in enumerate(screen_captures):
                prompt += f"Screen {i+1}: {capture.width}x{capture.height} pixels"
                if capture.is_cursor_screen:
                    prompt += " (cursor is here)"
                prompt += ". "

        return prompt

    def _parse_pointing_coordinates(self, response: str):
        """Parse [POINT:x,y:label] tags from AI response."""
        import re

        # Match [POINT:x,y:label] or [POINT:none]
        pattern = r'\[POINT:(\d+),(\d+):([^\]]+)\]|\[POINT:none\]'
        matches = re.findall(pattern, response)

        if matches:
            for match in matches:
                if match[0]:  # Has coordinates
                    x, y, label = match
                    self._detected_element_location = (float(x), float(y))
                    self._detected_element_label = label
                    self.cursor_location_detected.emit((float(x), float(y), label, None))
                    self.logger.info(f"Pointing at: {label} at ({x}, {y})")
                else:
                    self._clear_detected_element()

    def _clear_detected_element(self):
        """Clear detected element location."""
        self._detected_element_location = None
        self._detected_element_label = None
        self._detected_element_screen_frame = None

    # Onboarding
    def complete_onboarding(self):
        """Mark onboarding as complete."""
        self._has_completed_onboarding = True
        self.config.set("has_completed_onboarding", True)
        self.logger.info("Onboarding completed")

    # Shutdown
    def shutdown(self):
        """Clean shutdown of all components."""
        self.logger.info("Shutting down state manager...")

        # Cancel any ongoing tasks
        if self._current_response_task:
            self._current_response_task.cancel()

        # Stop all components
        self.audio_capture.cleanup()
        self.transcription_manager.cleanup()
        self.tts_manager.cleanup()
        self.cursor_overlay.hide_overlay()

        self.logger.info("State manager shutdown complete")