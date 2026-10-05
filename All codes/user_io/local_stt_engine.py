"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: Core File
Name: local_stt_engine.py

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [local_stt_engine.py]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: wave, typing, io, __future__, faster_whisper...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: local_stt_engine.py]) --> output([Output Node])
```
"""
from __future__ import annotations

"""
local_stt_engine.py
────────────────────────────────────────────────────────────────────────────
Offline, unlimited-use replacement for the Groq whisper-large-v3 API call
used in HojaigaVoiceInterface.transcribe_audio_groq().

WHY THIS EXISTS
----------------
Groq's hosted whisper-large-v3 endpoint enforces a hard rate limit of
20 requests/minute on the on-demand tier. Every push-to-talk utterance
consumes one request, so the ceiling is reached in under a minute of
normal use — this is what produced the HTTP 429 in your logs. It is
not a microphone, audio-capture, or transcription-quality problem.

This module removes the network dependency and the rate limit entirely
by running Whisper locally via faster-whisper (CTranslate2 runtime),
which is CPU-efficient and does not touch the GPU — consistent with
the Hojaiga hardware policy of reserving the RTX 3050 for the local
LLM Brain (Qwen3 8B / llama.cpp).

INTEGRATION
-----------
Only one method needs to be swapped inside HojaigaVoiceInterface:

    self.stt_engine = LocalSTTEngine()
    ...
    text = self.stt_engine.transcribe(audio)   # replaces transcribe_audio_groq(audio)

No other part of the voice interface, submit_callback, or CNS handoff
changes. The Brain's LLM still owns all reasoning/answering; this
module only converts speech -> text and text -> speech.

DEPENDENCIES
------------
pip install faster-whisper --break-system-packages
(faster-whisper pulls in ctranslate2, which ships prebuilt CPU wheels —
no CUDA toolkit required for CPU inference.)
"""


import io
import logging
import os
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("haos.local_stt")

try:
    from faster_whisper import WhisperModel
    _FASTER_WHISPER_AVAILABLE = True
except ImportError:
    _FASTER_WHISPER_AVAILABLE = False


@dataclass
class TranscriptionResult:
    text: str
    language: str
    confidence: float
    latency_seconds: float


class LocalSTTEngine:
    """
    Thread-safe, lazily-loaded local speech-to-text engine.

    model_size options (accuracy vs. speed/RAM tradeoff on a CPU-first
    i7 / 32GB target): "tiny", "base", "small", "medium".
    "small" is the recommended default — good multilingual accuracy,
    ~1-2s latency per utterance on a modern i7, ~1GB RAM.
    """

    _instance_lock = threading.Lock()

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = None,
        vad_filter: bool = True,
    ):
        if not _FASTER_WHISPER_AVAILABLE:
            raise RuntimeError(
                "faster-whisper is not installed. Run: "
                "pip install faster-whisper --break-system-packages"
            )

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.vad_filter = vad_filter

        self._model: Optional[WhisperModel] = None
        self._load_lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            logger.info(
                "Loading local Whisper model '%s' (device=%s, compute_type=%s)...",
                self.model_size, self.device, self.compute_type,
            )
            start = time.time()
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info("Local Whisper model loaded in %.2fs", time.time() - start)

    def transcribe_wav_bytes(self, wav_bytes: bytes, prompt: str = "") -> TranscriptionResult:
        """Transcribe raw WAV byte content (what SpeechRecognition's AudioData.get_wav_data() returns)."""
        self._ensure_loaded()
        start = time.time()

        model = self._model
        if model is None:
            # Fallback re-check/load
            self._ensure_loaded()
            model = self._model
            if model is None:
                raise RuntimeError("Whisper model is not loaded.")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name

        try:
            segments, info = model.transcribe(
                tmp_path,
                language=self.language,
                vad_filter=self.vad_filter,
                initial_prompt=prompt or None,
                beam_size=1,
            )
            text_parts = [seg.text for seg in segments]
            text = " ".join(part.strip() for part in text_parts).strip()
            latency = time.time() - start
            result = TranscriptionResult(
                text=text.lower(),
                language=info.language,
                confidence=float(getattr(info, "language_probability", 0.0) or 0.0),
                latency_seconds=latency,
            )
            logger.info(
                "Transcribed in %.2fs (lang=%s, conf=%.2f): %s",
                latency, result.language, result.confidence, result.text,
            )
            return result
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def transcribe(self, audio_data, prompt: str = "") -> str:
        """
        Drop-in replacement signature for transcribe_audio_groq(audio_data).
        `audio_data` is a speech_recognition.AudioData instance.
        Returns lowercase, stripped transcript text (empty string on failure).
        """
        try:
            wav_bytes = audio_data.get_wav_data()
            result = self.transcribe_wav_bytes(wav_bytes, prompt=prompt)
            return result.text
        except Exception as exc:
            logger.error("Local STT failed: %s", exc)
            return ""

    def warm_up(self) -> None:
        """Force model load + run a silent buffer through it, so the first
        real utterance isn't slowed down by lazy loading."""
        self._ensure_loaded()
        silence = _generate_silence_wav(seconds=0.5)
        self.transcribe_wav_bytes(silence)

    def unload(self) -> None:
        """Release the model from memory (mirrors the Brain's
        'shut down when not needed' policy for local runtimes)."""
        with self._load_lock:
            self._model = None
            logger.info("Local Whisper model unloaded, memory released.")


def _generate_silence_wav(seconds: float = 0.5, sample_rate: int = 16000) -> bytes:
    n_frames = int(seconds * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


class LocalTTSEngine:
    """
    Thin wrapper around pyttsx3 (already offline in your existing code) so
    STT and TTS share one consistent local module and one place to swap
    voices/rate/volume later without touching HojaigaVoiceInterface.
    """

    def __init__(self, rate: int = 170, volume: float = 1.0, voice_id: Optional[str] = None):
        self.rate = rate
        self.volume = volume
        self.voice_id = voice_id

    def speak(self, text: str) -> None:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        engine.setProperty("volume", self.volume)
        if self.voice_id:
            engine.setProperty("voice", self.voice_id)
        engine.say(text)
        engine.runAndWait()
        engine.stop()

    def list_voices(self):
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        engine.stop()
        return [(v.id, v.name) for v in voices]
