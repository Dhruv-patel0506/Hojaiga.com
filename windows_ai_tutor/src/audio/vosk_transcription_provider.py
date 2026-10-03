"""
Vosk Transcription Provider - FREE Offline Speech Recognition (Clicky-style)

Vosk offline speech recognition provider - completely free, no API keys needed.
Works on Python 3.13 without PyTorch DLL issues.
"""

import asyncio
from typing import Optional, Callable, List
import queue
import threading

from .buddy_transcription_provider import BuddyTranscriptionProvider, BuddyStreamingTranscriptionSession
from ..utils.logger import setup_logger


class VoskTranscriptionProvider(BuddyTranscriptionProvider):
    """Vosk offline speech recognition provider - FREE and local."""

    def __init__(self, model_path: str = "vosk-model-small-en-us-0.15"):
        """
        Initialize the Vosk transcription provider.

        Args:
            model_path: Path to Vosk model directory
        """
        self.model_path = model_path
        self.logger = setup_logger("VoskTranscriptionProvider")

        self._model = None
        self._recognizer = None

    @property
    def display_name(self) -> str:
        """Display name of the provider."""
        return "Vosk (FREE)"

    @property
    def requires_speech_recognition_permission(self) -> bool:
        """Whether this provider requires speech recognition permission."""
        return False

    @property
    def is_configured(self) -> bool:
        """Whether this provider is properly configured."""
        try:
            import vosk
            return True
        except ImportError:
            self.logger.warning("Vosk not installed. Install with: pip install vosk")
            return False

    @property
    def unavailable_explanation(self) -> Optional[str]:
        """Explanation if provider is unavailable."""
        if not self.is_configured:
            return "Vosk not installed. Install with: pip install vosk"
        return None

    async def start_streaming_session(
        self,
        keyterms: List[str],
        on_transcript_update: Callable[[str], None],
        on_final_transcript_ready: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ) -> BuddyStreamingTranscriptionSession:
        """Start a streaming transcription session."""
        return VoskTranscriptionSession(
            model_path=self.model_path,
            keyterms=keyterms,
            on_transcript_update=on_transcript_update,
            on_final_transcript_ready=on_final_transcript_ready,
            on_error=on_error
        )


class VoskTranscriptionSession(BuddyStreamingTranscriptionSession):
    """Vosk transcription session."""

    @property
    def final_transcript_fallback_delay_seconds(self) -> float:
        """Delay before requesting final transcript."""
        return 2.0

    def __init__(
        self,
        model_path: str,
        keyterms: List[str],
        on_transcript_update: Callable[[str], None],
        on_final_transcript_ready: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ):
        """Initialize the transcription session."""
        self.model_path = model_path
        self.keyterms = keyterms
        self.on_transcript_update = on_transcript_update
        self.on_final_transcript_ready = on_final_transcript_ready
        self.on_error = on_error

        self.logger = setup_logger("VoskTranscriptionSession")

        # State
        self.audio_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.recognizer_thread = None
        self.is_running = False
        self.has_delivered_final_transcript = False
        self.partial_transcript = ""
        self.final_transcript = ""

    def append_audio_buffer(self, audio_data: bytes):
        """Append audio buffer to the session."""
        if self.is_running:
            self.audio_queue.put(audio_data)

    def request_final_transcript(self):
        """Request the final transcript."""
        if not self.has_delivered_final_transcript:
            self.is_running = False
            if self.recognizer_thread:
                self.recognizer_thread.join(timeout=2.0)
            self._deliver_final_transcript()

    def cancel(self):
        """Cancel the session."""
        self.is_running = False
        if self.recognizer_thread:
            self.recognizer_thread.join(timeout=1.0)

    def _deliver_final_transcript(self):
        """Deliver the final transcript."""
        if not self.has_delivered_final_transcript:
            self.has_delivered_final_transcript = True
            transcript = self.final_transcript or self.partial_transcript
            self.on_final_transcript_ready(transcript.strip())

    async def open(self):
        """Open the transcription session."""
        try:
            import vosk
            import json

            self.logger.info(f"Loading Vosk model from: {self.model_path}")

            # Load model
            model = vosk.Model(self.model_path)

            # Create recognizer
            recognizer = vosk.KaldiRecognizer(model, 16000)

            # Start recognition thread
            self.is_running = True
            self.recognizer_thread = threading.Thread(
                target=self._recognition_loop,
                args=(recognizer,),
                daemon=True
            )
            self.recognizer_thread.start()

            self.logger.info("Vosk transcription session started")

        except Exception as e:
            self.logger.error(f"Failed to start Vosk session: {e}")
            self.on_error(e)

    def _recognition_loop(self, recognizer):
        """Recognition loop running in background thread."""
        import json

        while self.is_running:
            try:
                # Get audio data from queue
                audio_data = self.audio_queue.get(timeout=0.1)

                # Feed to recognizer
                if recognizer.AcceptWaveform(audio_data):
                    # Final result
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").strip()
                    if text:
                        self.final_transcript = text
                        self.on_transcript_update(text)
                else:
                    # Partial result
                    result = json.loads(recognizer.PartialResult())
                    text = result.get("partial", "").strip()
                    if text:
                        self.partial_transcript = text
                        self.on_transcript_update(text)

            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Recognition error: {e}")
                break
