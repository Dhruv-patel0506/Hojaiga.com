"""
professor.voice_out -- the Professor's voice. Local only, interruptible, and able to run a pointer animation alongside each sentence.

Backends, best first (the first one that works is used; `Speaker.backend` says which):
  piper    neural voice, runs ~16x faster than real time on this CPU (measured RTF 0.06 after a 4 s warm-up): the default for live teaching
  kokoro   neural voice from kokoro_models/ -- nicest, but measured RTF 3.3-4 on this CPU (8 s to say 2.5 s), so only used when asked for (HOJAIGA_TTS=kokoro)
  sapi     Windows SAPI5 voices through COM (pywin32): installed on every Windows PC, no network, async + purge
  none     silent (text is still returned/printed) -- reported, never faked
A worker thread owns the voice (COM objects are apartment-bound). `speak_sequence` takes (text, on_start) pairs so the lesson can fly the pointer to a control
at the moment the sentence about it starts.
"""

from __future__ import annotations

import io
import os
import queue
import re
import struct
import threading
import time
import wave
from typing import Callable, List, Optional, Sequence, Tuple

from . import config as CFG

try:
    import numpy as np
except Exception:                                                                       # pragma: no cover
    np = None


def split_sentences(text: str, max_len: int = 220) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    out: List[str] = []
    for p in parts:
        p = p.strip()
        while len(p) > max_len:
            cut = p.rfind(",", 0, max_len)
            cut = cut if cut > 40 else max_len
            out.append(p[:cut].strip(" ,"))
            p = p[cut:].strip(" ,")
        if p:
            out.append(p)
    return out


class Speaker:
    def __init__(self, backend: str = "auto", rate: int = 0, voice_hint: str = ""):
        self.rate = rate
        self.voice_hint = voice_hint.lower()
        self.backend = "none"
        self.error = ""
        self._q: "queue.Queue[Optional[Tuple[str, Optional[Callable[[], None]]]]]" = queue.Queue()
        self._stop_flag = threading.Event()
        self._speaking = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._thread = threading.Thread(target=self._run, args=(backend,), name="professor-voice", daemon=True)
        self._ready = threading.Event()
        self._thread.start()
        self._ready.wait(8.0)

    # ------------------------------------------------------------------------------------------------ worker
    def _init_piper(self):
        from piper import PiperVoice                                       # pip install piper-tts ; voice: python -m piper.download_voices en_US-lessac-medium
        path = os.path.join(CFG.PIPER_DIR, CFG.PIPER_VOICE + ".onnx")
        if not os.path.isfile(path):
            raise FileNotFoundError("piper voice missing: " + path)
        voice = PiperVoice.load(path)
        for _ch in voice.synthesize("ready"):                              # warm-up: the first call pays ~4 s of one-time initialisation
            pass
        return voice

    def _init_kokoro(self):
        model = os.path.join(CFG.KOKORO_DIR, "kokoro-v1.0.int8.onnx")
        voices = os.path.join(CFG.KOKORO_DIR, "voices-v1.0.bin")
        if not (os.path.isfile(model) and os.path.isfile(voices)):
            raise FileNotFoundError("kokoro model files missing")
        from kokoro_onnx import Kokoro                                # optional package
        return Kokoro(model, voices)

    def _init_sapi(self):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        v = win32com.client.Dispatch("SAPI.SpVoice")
        try:
            voices = v.GetVoices()
            pick = None
            for i in range(voices.Count):
                d = voices.Item(i).GetDescription().lower()
                if self.voice_hint and self.voice_hint in d:
                    pick = voices.Item(i)
                    break
                if pick is None and any(k in d for k in ("zira", "aria", "jenny", "david", "mark", "guy")):
                    pick = voices.Item(i)
            if pick is not None:
                v.Voice = pick
        except Exception:
            pass
        v.Rate = max(-10, min(10, self.rate))
        return v

    def _run(self, want: str) -> None:
        engine = None
        order = (["piper", "sapi"] if os.environ.get("HOJAIGA_TTS", "") != "kokoro" else ["kokoro", "piper", "sapi"]) if want == "auto" else [want]
        for name in order:
            try:
                if name == "piper":
                    engine = ("piper", self._init_piper())
                elif name == "kokoro":
                    engine = ("kokoro", self._init_kokoro())
                elif name == "sapi":
                    engine = ("sapi", self._init_sapi())
                if engine:
                    break
            except Exception as exc:
                self.error += f"{name}: {type(exc).__name__}: {str(exc)[:80]}; "
        self.backend = engine[0] if engine else "none"
        self._ready.set()
        while True:
            item = self._q.get()
            if item is None:
                return
            text, on_start = item
            self._idle.clear()
            self._speaking.set()
            try:
                if on_start:
                    try:
                        on_start()
                    except Exception:
                        pass
                if engine and not self._stop_flag.is_set():
                    if engine[0] == "sapi":
                        engine[1].Speak(text, 1)                                       # async
                        while not engine[1].WaitUntilDone(40):
                            if self._stop_flag.is_set():
                                engine[1].Speak("", 3)                                  # purge + async
                                break
                    elif engine[0] == "piper":
                        self._play_piper(engine[1], text)
                    else:
                        self._play_kokoro(engine[1], text)
            except Exception as exc:
                self.error += f"speak: {type(exc).__name__}: {str(exc)[:80]}; "
            finally:
                self._speaking.clear()
                if self._q.empty():
                    self._idle.set()
                    self._stop_flag.clear()

    def _play_pcm16(self, pcm: bytes, sr: int) -> None:
        """Play mono 16-bit PCM from memory (interruptible): winsound, so no audio-device setup can fail."""
        import winsound
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm)
        winsound.PlaySound(buf.getvalue(), winsound.SND_MEMORY | winsound.SND_ASYNC)
        dur = len(pcm) / 2.0 / float(sr)
        t0 = time.time()
        while time.time() - t0 < dur + 0.1:
            if self._stop_flag.is_set():
                winsound.PlaySound(None, winsound.SND_PURGE)
                return
            time.sleep(0.03)

    def _play_piper(self, voice, text: str) -> None:
        pcm, sr = b"", 22050
        for ch in voice.synthesize(text):
            pcm += ch.audio_int16_bytes
            sr = ch.sample_rate
            if self._stop_flag.is_set():
                return
        self._play_pcm16(pcm, sr)

    def _play_kokoro(self, k, text: str) -> None:
        samples, sr = k.create(text, voice="af_heart", speed=1.0, lang="en-us")
        self._play_pcm16((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes(), sr)

    # ------------------------------------------------------------------------------------------------- API
    def speak(self, text: str, on_start: Optional[Callable[[], None]] = None) -> None:
        from core_organs.speech_sanitize import clean_for_speech
        text = clean_for_speech(text) if text and text.strip() else text                  # never read the prompt machinery aloud
        if text and text.strip():
            self._stop_flag.clear()
            self._idle.clear()
            self._q.put((text.strip(), on_start))

    def speak_sequence(self, items: Sequence[Tuple[str, Optional[Callable[[], None]]]]) -> None:
        from core_organs.speech_sanitize import clean_for_speech
        for text, cb in items:
            for i, s in enumerate(split_sentences(clean_for_speech(text)) or [""]):
                if s or cb:
                    self.speak(s or " ", cb if i == 0 else None)

    def stop(self) -> None:
        self._stop_flag.set()
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        self._idle.set() if not self._speaking.is_set() else None

    def is_speaking(self) -> bool:
        return self._speaking.is_set() or not self._q.empty()

    def wait(self, timeout: float = 60.0) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if not self.is_speaking():
                return True
            time.sleep(0.05)
        return False

    def close(self) -> None:
        self.stop()
        self._q.put(None)


class SilentSpeaker:
    """Used by tests and --mute: records what would have been said."""
    backend = "silent"
    error = ""

    def __init__(self) -> None:
        self.said: List[str] = []

    def speak(self, text: str, on_start: Optional[Callable[[], None]] = None) -> None:
        from core_organs.speech_sanitize import clean_for_speech
        text = clean_for_speech(text) if text and text.strip() else text
        if text and text.strip():
            self.said.append(text.strip())
        if on_start:
            on_start()

    def speak_sequence(self, items: Sequence[Tuple[str, Optional[Callable[[], None]]]]) -> None:
        for text, cb in items:
            self.speak(text, cb)

    def stop(self) -> None:
        pass

    def is_speaking(self) -> bool:
        return False

    def wait(self, timeout: float = 0) -> bool:
        return True

    def close(self) -> None:
        pass
