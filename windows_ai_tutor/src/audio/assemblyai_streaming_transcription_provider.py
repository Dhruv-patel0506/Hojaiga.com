"""
AssemblyAI Streaming Transcription Provider - Streaming AI Transcription (Clicky-style)

Streaming AI transcription provider backed by AssemblyAI's websocket API.
Converted from AssemblyAIStreamingTranscriptionProvider.swift to Windows Python.
"""

import asyncio
import json
import websockets
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass
import requests

from .buddy_transcription_provider import BuddyTranscriptionProvider, BuddyStreamingTranscriptionSession
from .buddy_audio_conversion_support import BuddyPCM16AudioConverter
from ..utils.logger import setup_logger


@dataclass
class TurnMessage:
    """Turn message from AssemblyAI."""
    type: str
    transcript: Optional[str] = None
    turn_order: Optional[int] = None
    end_of_turn: Optional[bool] = None
    turn_is_formatted: Optional[bool] = None


@dataclass
class ErrorMessage:
    """Error message from AssemblyAI."""
    type: str
    error: Optional[str] = None
    message: Optional[str] = None


@dataclass
class StoredTurnTranscript:
    """Stored turn transcript."""
    transcript_text: str
    is_formatted: bool


class AssemblyAIStreamingTranscriptionProvider(BuddyTranscriptionProvider):
    """AssemblyAI streaming transcription provider."""

    # URL for the Cloudflare Worker endpoint
    TOKEN_PROXY_URL = "https://your-worker-name.your-subdomain.workers.dev/transcribe-token"

    def __init__(self, api_key: str = ""):
        """
        Initialize the AssemblyAI transcription provider.

        Args:
            api_key: AssemblyAI API key (optional if using token proxy)
        """
        self.api_key = api_key
        self.logger = setup_logger("AssemblyAIStreamingTranscriptionProvider")

    @property
    def display_name(self) -> str:
        """Display name of the provider."""
        return "AssemblyAI"

    @property
    def requires_speech_recognition_permission(self) -> bool:
        """Whether this provider requires speech recognition permission."""
        return False

    @property
    def is_configured(self) -> bool:
        """Whether this provider is properly configured."""
        return True  # Can use token proxy

    @property
    def unavailable_explanation(self) -> Optional[str]:
        """Explanation if provider is unavailable."""
        return None

    async def start_streaming_session(
        self,
        keyterms: List[str],
        on_transcript_update: Callable[[str], None],
        on_final_transcript_ready: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ) -> BuddyStreamingTranscriptionSession:
        """Start a streaming transcription session."""
        # Fetch temporary token from proxy
        temporary_token = await self._fetch_temporary_token()
        self.logger.info(f"Fetched temporary token ({temporary_token[:20]}...)")

        session = AssemblyAIStreamingTranscriptionSession(
            api_key=self.api_key,
            temporary_token=temporary_token,
            keyterms=keyterms,
            on_transcript_update=on_transcript_update,
            on_final_transcript_ready=on_final_transcript_ready,
            on_error=on_error
        )

        await session.open()
        return session

    async def _fetch_temporary_token(self) -> str:
        """Fetch a temporary token from the proxy."""
        try:
            response = requests.post(self.TOKEN_PROXY_URL, timeout=10)

            if response.status_code not in range(200, 300):
                raise Exception(f"Failed to fetch AssemblyAI token (HTTP {response.status_code}): {response.text}")

            data = response.json()
            token = data.get("token")

            if not token:
                raise Exception("Invalid token response from proxy.")

            return token

        except Exception as e:
            self.logger.error(f"Failed to fetch temporary token: {e}")
            raise


class AssemblyAIStreamingTranscriptionSession(BuddyStreamingTranscriptionSession):
    """AssemblyAI streaming transcription session."""

    WEBSOCKET_BASE_URL = "wss://streaming.assemblyai.com/v3/ws"
    TARGET_SAMPLE_RATE = 16000.0
    EXPLICIT_FINAL_TRANSCRIPT_GRACE_PERIOD_SECONDS = 1.4

    @property
    def final_transcript_fallback_delay_seconds(self) -> float:
        """Delay before requesting final transcript."""
        return 2.8

    def __init__(
        self,
        api_key: str,
        temporary_token: str,
        keyterms: List[str],
        on_transcript_update: Callable[[str], None],
        on_final_transcript_ready: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ):
        """Initialize the transcription session."""
        self.api_key = api_key
        self.temporary_token = temporary_token
        self.keyterms = keyterms
        self.on_transcript_update = on_transcript_update
        self.on_final_transcript_ready = on_final_transcript_ready
        self.on_error = on_error

        self.logger = setup_logger("AssemblyAIStreamingTranscriptionSession")

        # Audio converter
        self.audio_pcm16_converter = BuddyPCM16AudioConverter(
            target_sample_rate=self.TARGET_SAMPLE_RATE
        )

        # State
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.has_delivered_final_transcript = False
        self.is_awaiting_explicit_final_transcript = False
        self.latest_transcript_text = ""
        self.active_turn_order: Optional[int] = None
        self.active_turn_transcript_text = ""
        self.stored_turn_transcripts_by_order: Dict[int, StoredTurnTranscript] = {}
        self.explicit_final_transcript_deadline_task: Optional[asyncio.Task] = None

        # Async queue for sending audio
        self.send_queue: asyncio.Queue = asyncio.Queue()

    async def open(self):
        """Open the websocket connection."""
        websocket_url = self._make_websocket_url(self.temporary_token, self.keyterms)

        headers = {}
        if self.api_key:
            headers["Authorization"] = self.api_key

        self.websocket = await websockets.connect(websocket_url, additional_headers=headers)

        # Start receive task
        asyncio.create_task(self._receive_messages())

        # Start send task
        asyncio.create_task(self._send_messages())

        self.logger.info("AssemblyAI websocket connected")

    async def _receive_messages(self):
        """Receive messages from websocket."""
        try:
            async for message in self.websocket:
                if isinstance(message, str):
                    self._handle_incoming_text_message(message)
                elif isinstance(message, bytes):
                    text = message.decode('utf-8')
                    self._handle_incoming_text_message(text)
        except Exception as e:
            self._fail_session(e)

    def _handle_incoming_text_message(self, text: str):
        """Handle incoming text message from websocket."""
        try:
            envelope = json.loads(text)
            message_type = envelope.get("type", "").lower()

            if message_type == "begin":
                self.logger.info("AssemblyAI session started")
            elif message_type == "turn":
                turn_message = TurnMessage(**envelope)
                self._handle_turn_message(turn_message)
            elif message_type == "termination":
                if self.is_awaiting_explicit_final_transcript and not self.has_delivered_final_transcript:
                    self._deliver_final_transcript_if_needed(self._best_available_transcript_text())
            elif message_type == "error":
                error_message = ErrorMessage(**envelope)
                message_text = error_message.error or error_message.message or "AssemblyAI returned an error."
                self._fail_session(Exception(message_text))
        except Exception as e:
            self._fail_session(e)

    def _handle_turn_message(self, turn_message: TurnMessage):
        """Handle turn message from AssemblyAI."""
        transcript_text = (turn_message.transcript or "").strip()

        turn_order = turn_message.turn_order or self.active_turn_order or (max(self.stored_turn_transcripts_by_order.keys(), default=-1) + 1)

        if turn_message.end_of_turn or turn_message.turn_is_formatted:
            self.active_turn_order = None
            self.active_turn_transcript_text = ""
            self._store_turn_transcript(
                transcript_text,
                turn_order,
                is_formatted=turn_message.turn_is_formatted
            )
        else:
            self.active_turn_order = turn_order
            self.active_turn_transcript_text = transcript_text

        full_transcript_text = self._compose_full_transcript()
        self.latest_transcript_text = full_transcript_text

        if full_transcript_text:
            self.on_transcript_update(full_transcript_text)

        if self.is_awaiting_explicit_final_transcript:
            if turn_message.end_of_turn or turn_message.turn_is_formatted:
                if self.explicit_final_transcript_deadline_task:
                    self.explicit_final_transcript_deadline_task.cancel()
                    self.explicit_final_transcript_deadline_task = None
                self._deliver_final_transcript_if_needed(self._best_available_transcript_text())

    def _store_turn_transcript(self, transcript_text: str, turn_order: int, is_formatted: bool):
        """Store turn transcript."""
        if not transcript_text:
            return

        existing_turn = self.stored_turn_transcripts_by_order.get(turn_order)
        if existing_turn and existing_turn.is_formatted and not is_formatted:
            return

        self.stored_turn_transcripts_by_order[turn_order] = StoredTurnTranscript(
            transcript_text=transcript_text,
            is_formatted=is_formatted
        )

    def _compose_full_transcript(self) -> str:
        """Compose full transcript from stored turns."""
        committed_segments = [
            turn.transcript_text
            for order, turn in sorted(self.stored_turn_transcripts_by_order.items())
            if turn.transcript_text
        ]

        transcript_segments = committed_segments.copy()

        trimmed_active = self.active_turn_transcript_text.strip()
        if trimmed_active:
            transcript_segments.append(trimmed_active)

        return " ".join(transcript_segments)

    def _best_available_transcript_text(self) -> str:
        """Get the best available transcript text."""
        composed = self._compose_full_transcript().strip()
        if composed:
            return composed
        return self.latest_transcript_text.strip()

    def _deliver_final_transcript_if_needed(self, transcript_text: str):
        """Deliver final transcript if not already delivered."""
        if self.has_delivered_final_transcript:
            return

        self.has_delivered_final_transcript = True
        if self.explicit_final_transcript_deadline_task:
            self.explicit_final_transcript_deadline_task.cancel()
            self.explicit_final_transcript_deadline_task = None

        self.on_final_transcript_ready(transcript_text)
        self._send_json_message({"type": "Terminate"})

    async def _send_messages(self):
        """Send messages from queue to websocket."""
        try:
            while self.websocket:
                message = await self.send_queue.get()
                await self.websocket.send(message)
        except Exception as e:
            self._fail_session(e)

    def _send_json_message(self, payload: dict):
        """Send JSON message to websocket."""
        json_string = json.dumps(payload)
        asyncio.create_task(self.send_queue.put(json_string))

    def _fail_session(self, error: Exception):
        """Fail the session with error."""
        latest_transcript = self._best_available_transcript_text()

        if self.is_awaiting_explicit_final_transcript and not self.has_delivered_final_transcript and latest_transcript:
            self.logger.warning(f"WebSocket error, delivering partial transcript: {error}")
            self._deliver_final_transcript_if_needed(latest_transcript)
        else:
            self.logger.error(f"Session failed: {error}")
            self.on_error(error)

    def append_audio_buffer(self, audio_data: bytes):
        """Append audio buffer to the session."""
        pcm16_data = self.audio_pcm16_converter.convert_to_pcm16_data(
            audio_data,
            source_sample_rate=44100.0
        )

        if pcm16_data:
            asyncio.create_task(self.send_queue.put(pcm16_data))

    def request_final_transcript(self):
        """Request the final transcript."""
        if self.has_delivered_final_transcript:
            return

        self.is_awaiting_explicit_final_transcript = True
        self._schedule_explicit_final_transcript_deadline()
        self._send_json_message({"type": "ForceEndpoint"})

    def _schedule_explicit_final_transcript_deadline(self):
        """Schedule explicit final transcript deadline."""
        if self.explicit_final_transcript_deadline_task:
            self.explicit_final_transcript_deadline_task.cancel()

        async def deadline():
            await asyncio.sleep(self.EXPLICIT_FINAL_TRANSCRIPT_GRACE_PERIOD_SECONDS)
            self._deliver_final_transcript_if_needed(self._best_available_transcript_text())

        self.explicit_final_transcript_deadline_task = asyncio.create_task(deadline())

    def cancel(self):
        """Cancel the session."""
        if self.explicit_final_transcript_deadline_task:
            self.explicit_final_transcript_deadline_task.cancel()
            self.explicit_final_transcript_deadline_task = None

        self._send_json_message({"type": "Terminate"})

        if self.websocket:
            asyncio.create_task(self.websocket.close())

    def _make_websocket_url(self, temporary_token: str, keyterms: List[str]) -> str:
        """Make websocket URL with parameters."""
        import urllib.parse

        params = {
            "sample_rate": "16000",
            "encoding": "pcm_s16le",
            "format_turns": "true",
            "speech_model": "u3-rt-pro"
        }

        normalized_keyterms = [term.strip() for term in keyterms if term.strip()]
        if normalized_keyterms:
            params["keyterms_prompt"] = json.dumps(normalized_keyterms)

        if temporary_token:
            params["token"] = temporary_token

        query_string = urllib.parse.urlencode(params)
        return f"{self.WEBSOCKET_BASE_URL}?{query_string}"
