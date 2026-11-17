"""
professor.voice_in -- hearing the learner: push-to-talk, microphone capture, local speech-to-text.

  PushToTalk   hold Ctrl+Alt (Clicky's ctrl+option) -> recording; release -> transcribe. Detected by POLLING GetAsyncKeyState: no keyboard hook, no
               admin rights, nothing injected, nothing that can steal focus. A tap shorter than 250 ms is ignored (accidental chord).
  Recorder     microphone -> 16 kHz mono PCM16. `sounddevice` when installed, else the Windows multimedia API (winmm waveIn) through ctypes: no dependency.
  Transcriber  backends in order of quality, first available wins (reported in `.backend`):
                 faster-whisper  (optional pip package + one-time free model download)   best accuracy
                 vosk            (optional pip package + a downloaded small model)         light
                 windows         System.Speech dictation through PowerShell                installed with Windows, offline, ~1-3 s per phrase
Nothing is sent anywhere: audio stays in memory and is dropped after transcription unless `keep_wav` is set.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import io
import os
import subprocess
import tempfile
import threading
import time
import wave
from typing import Any, Callable, Dict, List, Optional

from .capture import IS_WINDOWS, key_down

SAMPLE_RATE = 16000


# ======================================================================================================== recording
class Recorder:
    """Start/stop microphone capture. `stop()` returns raw PCM16 mono 16 kHz bytes."""

    def __init__(self) -> None:
        self.backend = "none"
        self._frames: List[bytes] = []
        self._run = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.error = ""
        try:
            import sounddevice  # noqa: F401
            self.backend = "sounddevice"
        except Exception:
            self.backend = "winmm" if IS_WINDOWS else "none"

    def start(self) -> bool:
        if self.backend == "none":
            return False
        self._frames = []
        self._run.set()
        self._thread = threading.Thread(target=self._loop, name="professor-mic", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> bytes:
        self._run.clear()
        if self._thread:
            self._thread.join(2.0)
        return b"".join(self._frames)

    def _loop(self) -> None:
        try:
            if self.backend == "sounddevice":
                self._loop_sd()
            else:
                self._loop_winmm()
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"

    def _loop_sd(self) -> None:
        import sounddevice as sd
        with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=1600) as st:
            while self._run.is_set():
                data, _ov = st.read(1600)
                self._frames.append(bytes(data))

    def _loop_winmm(self) -> None:
        mm = ctypes.WinDLL("winmm")

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [("wFormatTag", wt.WORD), ("nChannels", wt.WORD), ("nSamplesPerSec", wt.DWORD), ("nAvgBytesPerSec", wt.DWORD),
                        ("nBlockAlign", wt.WORD), ("wBitsPerSample", wt.WORD), ("cbSize", wt.WORD)]

        class WAVEHDR(ctypes.Structure):
            _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wt.DWORD), ("dwBytesRecorded", wt.DWORD), ("dwUser", ctypes.c_size_t),
                        ("dwFlags", wt.DWORD), ("dwLoops", wt.DWORD), ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]

        fmt = WAVEFORMATEX(1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16, 0)
        h = ctypes.c_void_p()
        mm.waveInOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), wt.UINT, ctypes.POINTER(WAVEFORMATEX), ctypes.c_size_t, ctypes.c_size_t, wt.DWORD]
        mm.waveInPrepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wt.UINT]
        mm.waveInUnprepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wt.UINT]
        mm.waveInAddBuffer.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wt.UINT]
        mm.waveInStart.argtypes = [ctypes.c_void_p]
        mm.waveInStop.argtypes = [ctypes.c_void_p]
        mm.waveInReset.argtypes = [ctypes.c_void_p]
        mm.waveInClose.argtypes = [ctypes.c_void_p]
        if mm.waveInOpen(ctypes.byref(h), 0xFFFFFFFF, ctypes.byref(fmt), 0, 0, 0) != 0:                  # WAVE_MAPPER, CALLBACK_NULL
            self.error = "no microphone could be opened"
            return
        n_buf, size = 4, 3200                                                                           # 4 x 100 ms
        bufs = [(ctypes.create_string_buffer(size), WAVEHDR()) for _ in range(n_buf)]
        for raw, hdr in bufs:
            hdr.lpData = ctypes.cast(raw, ctypes.c_void_p)
            hdr.dwBufferLength = size
            mm.waveInPrepareHeader(h, ctypes.byref(hdr), ctypes.sizeof(hdr))
            mm.waveInAddBuffer(h, ctypes.byref(hdr), ctypes.sizeof(hdr))
        mm.waveInStart(h)
        try:
            while self._run.is_set():
                for raw, hdr in bufs:
                    if hdr.dwFlags & 1:                                                                 # WHDR_DONE
                        self._frames.append(raw.raw[:hdr.dwBytesRecorded])
                        hdr.dwFlags &= ~1
                        hdr.dwBytesRecorded = 0
                        mm.waveInAddBuffer(h, ctypes.byref(hdr), ctypes.sizeof(hdr))
                time.sleep(0.02)
        finally:
            mm.waveInStop(h)
            mm.waveInReset(h)
            for raw, hdr in bufs:
                if hdr.dwFlags & 1 and hdr.dwBytesRecorded:
                    self._frames.append(raw.raw[:hdr.dwBytesRecorded])
                mm.waveInUnprepareHeader(h, ctypes.byref(hdr), ctypes.sizeof(hdr))
            mm.waveInClose(h)


def pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def rms_level(pcm: bytes) -> float:
    if len(pcm) < 4:
        return 0.0
    import array
    a = array.array("h", pcm[: len(pcm) // 2 * 2])
    return (sum(x * x for x in a) / len(a)) ** 0.5 / 32768.0


# ===================================================================================================== transcription
class Transcriber:
    def __init__(self, prefer: str = "auto", whisper_model: str = "base.en"):
        self.backend = "none"
        self.error = ""
        self._whisper = None
        self._vosk = None
        order = ["faster-whisper", "vosk", "windows"] if prefer == "auto" else [prefer]
        for name in order:
            try:
                if name == "faster-whisper":
                    from faster_whisper import WhisperModel
                    self._whisper = WhisperModel(whisper_model, device="cpu", compute_type="int8")
                elif name == "vosk":
                    import vosk
                    mp = os.environ.get("HOJAIGA_VOSK_MODEL", "")
                    if not mp or not os.path.isdir(mp):
                        raise FileNotFoundError("set HOJAIGA_VOSK_MODEL to a downloaded vosk model folder")
                    self._vosk = vosk.Model(mp)
                elif name == "windows":
                    if not IS_WINDOWS:
                        raise OSError("windows only")
                self.backend = name
                break
            except Exception as exc:
                self.error += f"{name}: {type(exc).__name__}: {str(exc)[:70]}; "

    def transcribe(self, pcm: bytes) -> Dict[str, Any]:
        t0 = time.time()
        if len(pcm) < SAMPLE_RATE * 2 * 0.3:
            return {"ok": False, "text": "", "error": "too short", "backend": self.backend}
        try:
            if self.backend == "faster-whisper":
                import numpy as np
                audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
                segs, _info = self._whisper.transcribe(audio, language="en", beam_size=1, vad_filter=True)
                text = " ".join(s.text.strip() for s in segs).strip()
            elif self.backend == "vosk":
                import json
                import vosk
                rec = vosk.KaldiRecognizer(self._vosk, SAMPLE_RATE)
                rec.AcceptWaveform(pcm)
                text = json.loads(rec.FinalResult()).get("text", "")
            elif self.backend == "windows":
                text = self._windows(pcm)
            else:
                return {"ok": False, "text": "", "error": "no speech-to-text backend: " + self.error, "backend": "none"}
        except Exception as exc:
            return {"ok": False, "text": "", "error": f"{type(exc).__name__}: {str(exc)[:120]}", "backend": self.backend}
        return {"ok": bool(text), "text": text.strip(), "seconds": round(time.time() - t0, 2), "backend": self.backend}

    def _windows(self, pcm: bytes) -> str:
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="prof_")
        os.close(fd)
        try:
            with open(path, "wb") as fh:
                fh.write(pcm_to_wav(pcm))
            script = ("Add-Type -AssemblyName System.Speech; $r = New-Object System.Speech.Recognition.SpeechRecognitionEngine; "
                      "$r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar)); "
                      f"$r.SetInputToWaveFile('{path}'); $res = $r.Recognize(); if ($res) {{ $res.Text }}")
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=40,
                                 creationflags=0x08000000)
            return (out.stdout or "").strip()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


# ===================================================================================================== push to talk
VK_CONTROL, VK_MENU, VK_ESCAPE = 0x11, 0x12, 0x1B


class PushToTalk:
    """Poll the keyboard state. on_start() when Ctrl+Alt has been held >= min_hold; on_end(duration) when released. Escape cancels via on_cancel()."""

    def __init__(self, on_start: Callable[[], None], on_end: Callable[[float], None], on_cancel: Optional[Callable[[], None]] = None, min_hold: float = 0.25):
        self.on_start, self.on_end, self.on_cancel, self.min_hold = on_start, on_end, on_cancel, min_hold
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="professor-ptt", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        held_since: Optional[float] = None
        active = False
        while not self._stop.is_set():
            chord = key_down(VK_CONTROL) and key_down(VK_MENU)
            now = time.time()
            if chord:
                if held_since is None:
                    held_since = now
                if not active and now - held_since >= self.min_hold:
                    active = True
                    try:
                        self.on_start()
                    except Exception:
                        pass
                if active and key_down(VK_ESCAPE):
                    active = False
                    held_since = None
                    if self.on_cancel:
                        self.on_cancel()
                    while key_down(VK_CONTROL) and key_down(VK_MENU) and not self._stop.is_set():
                        time.sleep(0.05)
            else:
                if active:
                    active = False
                    dur = now - (held_since or now)
                    try:
                        self.on_end(dur)
                    except Exception:
                        pass
                held_since = None
            time.sleep(0.03)
