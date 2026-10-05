"""
OpenAI Audio Transcription Provider - AI Transcription (Clicky-style)

AI transcription provider backed by OpenAI's audio transcription API.
Converted from OpenAIAudioTranscriptionProvider.swift to Windows Python.
"""

import asyncio
import uuid
from typing import Optional, Callable
import requests
import io

from .buddy_transcription_provider import BuddyTranscriptionProvider, BuddyStreamingTranscriptionSession
from .buddy_audio_conversion_support import BuddyWAVFileBuilder, BuddyPCM16AudioConverter
from ..utils.logger import setup_logger


class OpenAIAudioTranscriptionProvider(BuddyTranscriptionProvider):
    """OpenAI audio transcription provider."""

    def __init__(self, api_key: str = "", model_name: str = "whisper-1"):
        """
        Initialize the OpenAI transcription provider.

        Args:
            api_key: OpenAI API key
            model_name: Model name (default: whisper-1)
        """
        self.api_key = api_key
        self.model_name = model_name
        self.logger = setup_logger("OpenAIAudioTranscriptionProvider")

    @property
    def display_name(self) -> str:
        """Display name of the provider."""
        return "OpenAI"

    @property
    def requires_speech_recognition_permission(self) -> bool:
        """Whether this provider requires speech recognition permission."""
        return False

    @property
    def is_configured(self) -> bool:
        """Whether this provider is properly configured."""
        return bool(self.api_key)

    @property
    def unavailable_explanation(self) -> Optional[str]:
        """Explanation if provider is unavailable."""
        if not self.is_configured:
            return "OpenAI transcription is not configured. Add OpenAI API key."
        return None

    async def start_streaming_session(
        self,
        keyterms: list[str],
        on_transcript_update: Callable[[str], None],
        on_final_transcript_ready: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ) -> BuddyStreamingTranscriptionSession:
        """Start a streaming transcription session."""
        if not self.is_configured:
            raise Exception(self.unavailable_explanation)

        return OpenAIAudioTranscriptionSession(
            api_key=self.api_key,
            model_name=self.model_name,
            keyterms=keyterms,
            on_transcript_update=on_transcript_update,
            on_final_transcript_ready=on_final_transcript_ready,
            on_error=on_error
        )


class OpenAIAudioTranscriptionSession(BuddyStreamingTranscriptionSession):
    """OpenAI audio transcription session."""

    TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions"
    TARGET_SAMPLE_RATE = 16000

    @property
    def final_transcript_fallback_delay_seconds(self) -> float:
        """Delay before requesting final transcript."""
        return 8.0

    def __init__(
        self,
        api_key: str,
        model_name: str,
        keyterms: list[str],
        on_transcript_update: Callable[[str], None],
        on_final_transcript_ready: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ):
        """Initialize the transcription session."""
        self.api_key = api_key
        self.model_name = model_name
        self.keyterms = keyterms
        self.on_transcript_update = on_transcript_update
        self.on_final_transcript_ready = on_final_transcript_ready
        self.on_error = on_error

        self.logger = setup_logger("OpenAIAudioTranscriptionSession")

        # Audio converter
        self.audio_pcm16_converter = BuddyPCM16AudioConverter(
            target_sample_rate=float(self.TARGET_SAMPLE_RATE)
        )

        # State
        self.buffered_pcm16_audio_data = bytearray()
        self.has_requested_final_transcript = False
        self.has_delivered_final_transcript = False
        self.is_cancelled = False
        self.transcription_task = None

    def append_audio_buffer(self, audio_data: bytes):
        """Append audio buffer to the session."""
        if self.is_cancelled or self.has_requested_final_transcript:
            return

        # Convert to PCM16 if needed
        pcm16_data = self.audio_pcm16_converter.convert_to_pcm16_data(
            audio_data,
            source_sample_rate=44100.0  # Assume 44.1kHz from PyAudio
        )

        if pcm16_data:
            self.buffered_pcm16_audio_data.extend(pcm16_data)

    def request_final_transcript(self):
        """Request the final transcript."""
        if self.has_requested_final_transcript or self.is_cancelled:
            return

        self.has_requested_final_transcript = True

        # Transcribe buffered audio
        buffered_data = bytes(self.buffered_pcm16_audio_data)
        self.transcription_task = asyncio.create_task(
            self._transcribe_buffered_audio(buffered_data)
        )

    def cancel(self):
        """Cancel the session."""
        self.is_cancelled = True
        self.buffered_pcm16_audio_data.clear()

        if self.transcription_task:
            self.transcription_task.cancel()

    async def _transcribe_buffered_audio(self, buffered_audio_data: bytes):
        """Transcribe the buffered audio."""
        if self.is_cancelled or not buffered_audio_data:
            self._deliver_final_transcript("")
            return

        # Build WAV file
        wav_audio_data = BuddyWAVFileBuilder.build_wav_data(
            pcm16_audio_data=buffered_audio_data,
            sample_rate=self.TARGET_SAMPLE_RATE
        )

        try:
            transcript_text = await self._request_transcription(wav_audio_data)

            if self.is_cancelled:
                return

            if transcript_text:
                self.on_transcript_update(transcript_text)

            self._deliver_final_transcript(transcript_text)

        except Exception as e:
            if not self.is_cancelled:
                self.logger.error(f"Transcription failed: {e}")
                self.on_error(e)

    async def _request_transcription(self, wav_audio_data: bytes) -> str:
        """Request transcription from OpenAI API."""
        # Prepare multipart form data
        files = {
            'file': ('voice-input.wav', io.BytesIO(wav_audio_data), 'audio/wav')
        }

        data = {
            'model': self.model_name,
            'language': 'en',
            'response_format': 'json'
        }

        # Add contextual prompt if keyterms are provided
        prompt_text = self._transcription_prompt_text()
        if prompt_text:
            data['prompt'] = prompt_text

        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }

        response = requests.post(
            self.TRANSCRIPTION_URL,
            files=files,
            data=data,
            headers=headers,
            timeout=45
        )

        if response.status_code not in range(200, 300):
            raise Exception(f"OpenAI transcription failed: {response.text}")

        result = response.json()
        transcript = result.get('text', '').strip()

        if not transcript:
            raise Exception("OpenAI transcription returned an empty transcript.")

        return transcript

    def _transcription_prompt_text(self) -> Optional[str]:
        """Generate contextual prompt from keyterms."""
        normalized_keyterms = [
            term.strip() for term in self.keyterms if term.strip()
        ]

        if not normalized_keyterms:
            return None

        return (
            "This is a short push-to-talk transcript for a coding and product app. "
            f"Expect product names, technical terms, and app-specific vocabulary such as: "
            f"{', '.join(normalized_keyterms)}."
        )

    def _deliver_final_transcript(self, transcript_text: str):
        """Deliver the final transcript."""
        if self.has_delivered_final_transcript:
            return

        self.has_delivered_final_transcript = True
        self.on_final_transcript_ready(transcript_text)
