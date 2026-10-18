"""
tutor_voice -- the person's side of the conversation, all local: what the tutor SAYS (Windows SAPI), what it HEARS (faster-whisper on the CPU, from the microphone), what the person DOES (a click or a key,
read passively), and what they TYPE (a small always-on-top bar).

    Voice        speak(text, wait=True)   the voice and the screen stay in step: the call returns when the sentence has been said
    Listener     listen()                 records until the person stops talking (energy threshold learned from the room's own noise), transcribes, returns the words
    Watcher      wait(box, keys, ...)     a click inside a box, a key press, a typed line or a spoken command - whichever comes first. Clicks and keys are only READ (GetAsyncKeyState / GetCursorPos),
                                          never injected and never hooked: the person's input is theirs.
    ControlBar   a one-line text box + a mic switch; Enter sends the line. It is the only part that can take focus, and only when the person clicks it.
    command_of   'next', 'go on', 'back', 'repeat', 'skip', 'stop', 'do it for me' ... from what was said or typed (by words, not by position in a script)

Nothing here knows what is being taught.
"""
from __future__ import annotations

import contextlib
import ctypes
import queue
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

VK = {"lbutton": 0x01, "enter": 0x0D, "space": 0x20, "esc": 0x1B, "right": 0x27, "left": 0x25, "tab": 0x09}

COMMANDS: List[Tuple[str, re.Pattern]] = [
    ("delegate", re.compile(r"\b(do it for me|you do it|take over|automate|do (?:the rest|it yourself)|can you do (?:it|this))\b", re.I)),
    ("stop", re.compile(r"\b(stop|quit|exit|cancel|enough|that'?s all|close)\b", re.I)),
    ("back", re.compile(r"\b(back|previous|go back|last step)\b", re.I)),
    ("repeat", re.compile(r"\b(repeat|again|say that again|what was that|one more time)\b", re.I)),
    ("skip", re.compile(r"\b(skip|pass)\b", re.I)),
    ("next", re.compile(r"\b(next|go on|continue|done|okay|ok|got it|ready|yes|proceed|i did it)\b", re.I)),
]


def command_of(text: str) -> str:
    """The tutor command a spoken or typed line carries ('' when it is a question or something else)."""
    t = (text or "").strip()
    if not t:
        return ""
    for name, rx in COMMANDS:
        if rx.search(t) and (len(t.split()) <= 6 or name in ("delegate", "stop")):
            return name
    return ""


# ------------------------------------------------------------------------------------------------------------------------------------------------ speaking
class Voice:
    """Windows SAPI (pyttsx3) on its own thread. `enabled` False = silent (the words are on screen anyway)."""

    def __init__(self, enabled: bool = True, rate: int = 180) -> None:
        self.enabled = enabled
        self.rate = rate
        self._q: "queue.Queue[Tuple[str, threading.Event]]" = queue.Queue()
        self._t: Optional[threading.Thread] = None
        self.speaking = False
        self.said: List[str] = []

    def _loop(self) -> None:
        sapi, eng = None, None
        with contextlib.suppress(Exception):
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client
            sapi = win32com.client.Dispatch("SAPI.SpVoice")                      # Windows' own voice: no extra package needed
            sapi.Rate = max(-4, min(6, int((self.rate - 175) / 12)))
        if sapi is None:
            with contextlib.suppress(Exception):
                import pyttsx3
                eng = pyttsx3.init()
                eng.setProperty("rate", self.rate)
        while True:
            text, done = self._q.get()
            self.speaking = True
            try:
                if sapi is not None:
                    sapi.Speak(text)
                elif eng is not None:
                    eng.say(text)
                    eng.runAndWait()
            except Exception:
                pass
            self.speaking = False
            done.set()

    def speak(self, text: str, wait: bool = True, timeout: float = 25.0) -> bool:
        self.said.append(text)
        if not self.enabled or not text:
            return False
        if self._t is None or not self._t.is_alive():
            self._t = threading.Thread(target=self._loop, daemon=True, name="tutor-voice")
            self._t.start()
        done = threading.Event()
        self._q.put((text, done))
        if wait:
            done.wait(min(timeout, 3.0 + len(text.split()) / 2.0))
        return True

    def idle(self) -> bool:
        return self._q.empty() and not self.speaking

    def stop(self) -> None:
        with contextlib.suppress(Exception):
            while True:
                self._q.get_nowait()


# ------------------------------------------------------------------------------------------------------------------------------------------------ hearing
class Listener:
    """Microphone -> words, on the CPU. The model is loaded the first time it is needed."""

    def __init__(self, model: str = "base.en", device: Optional[int] = None) -> None:
        self.model_name, self.device = model, device
        self._model: Any = None
        self.rate = 16000

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            import sounddevice as sd
            return any(d["max_input_channels"] > 0 for d in sd.query_devices())
        except Exception:
            return False

    def record(self, max_s: float = 8.0, silence_s: float = 0.9, start_timeout: float = 6.0) -> Any:
        """Audio from the first word to a pause (or the limits): a float32 array at 16 kHz, or None when nobody spoke."""
        import numpy as np
        import sounddevice as sd
        chunk = int(self.rate * 0.1)
        frames: List[Any] = []
        noise: List[float] = []
        started, quiet, t0 = False, 0.0, time.time()
        with sd.InputStream(samplerate=self.rate, channels=1, dtype="float32", device=self.device, blocksize=chunk) as st:
            while time.time() - t0 < max_s + start_timeout:
                data, _ = st.read(chunk)
                x = data[:, 0].copy()
                rms = float(np.sqrt(np.mean(x * x)))
                if len(noise) < 4:
                    noise.append(rms)
                    continue
                thr = max(0.012, 3.0 * (sum(noise) / len(noise)))
                if not started:
                    if rms > thr:
                        started = True
                        frames.append(x)
                    elif time.time() - t0 > start_timeout:
                        return None
                    continue
                frames.append(x)
                quiet = quiet + 0.1 if rms < thr else 0.0
                if quiet >= silence_s or (time.time() - t0) > max_s + start_timeout:
                    break
        return np.concatenate(frames) if frames else None

    def transcribe(self, audio: Any) -> str:
        if audio is None or len(audio) < 4000:
            return ""
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        segs, _info = self._model.transcribe(audio, language="en", beam_size=1, vad_filter=False)
        return " ".join(s.text.strip() for s in segs).strip()

    def listen(self, **kw: Any) -> str:
        return self.transcribe(self.record(**kw))


# ------------------------------------------------------------------------------------------------------------------------------------------------ typing
class ControlBar:
    """A one-line always-on-top text box at the top of the screen. Enter sends the line; the window never takes focus by itself."""

    def __init__(self, on_line: Callable[[str], None], voice_toggle: Optional[Callable[[], bool]] = None, width: int = 420) -> None:
        self.on_line, self.voice_toggle, self.width = on_line, voice_toggle, width
        self._t: Optional[threading.Thread] = None
        self._root: Any = None
        self.ready = threading.Event()

    def start(self) -> bool:
        self._t = threading.Thread(target=self._run, daemon=True, name="tutor-bar")
        self._t.start()
        return self.ready.wait(3.0)

    def _run(self) -> None:
        try:
            import tkinter as tk
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.configure(bg="#111827")
            sw = root.winfo_screenwidth()
            root.geometry(f"{self.width}x34+{(sw - self.width) // 2}+40")
            ent = tk.Entry(root, bg="#1f2937", fg="#f9fafb", insertbackground="#f9fafb", relief="flat", font=("Segoe UI", 11))
            ent.pack(side="left", fill="x", expand=True, padx=(10, 4), pady=5)
            ent.insert(0, "Ask, or say 'next' / 'do it for me'")
            ent.bind("<FocusIn>", lambda e: ent.delete(0, "end") if ent.get().startswith("Ask, or say") else None)

            def send(_e: Any = None) -> None:
                t = ent.get().strip()
                if t and not t.startswith("Ask, or say"):
                    ent.delete(0, "end")
                    self.on_line(t)
            ent.bind("<Return>", send)
            mic = tk.Label(root, text="mic", bg="#111827", fg="#9ca3af", font=("Segoe UI", 9))
            mic.pack(side="left", padx=4)

            def toggle(_e: Any = None) -> None:
                on = self.voice_toggle() if self.voice_toggle else False
                mic.configure(fg="#4ade80" if on else "#9ca3af")
            mic.bind("<Button-1>", toggle)
            x = tk.Label(root, text="x", bg="#111827", fg="#9ca3af", font=("Segoe UI", 11, "bold"))
            x.pack(side="left", padx=(2, 10))
            x.bind("<Button-1>", lambda e: (self.on_line("stop"), root.after(50, root.destroy)))
            self._root = root
            self.ready.set()
            root.mainloop()
        except Exception:
            self.ready.set()

    def close(self) -> None:
        with contextlib.suppress(Exception):
            if self._root is not None:
                self._root.after(0, self._root.destroy)


# ------------------------------------------------------------------------------------------------------------------------------------------------ the person's actions
class Watcher:
    """Waits for the person's next move. Passive: the left button and the keys are polled, never hooked or injected."""

    def __init__(self, listener: Optional[Listener] = None) -> None:
        self.lines: "queue.Queue[str]" = queue.Queue()
        self.listener = listener
        self.voice_in = False
        self._vt: Optional[threading.Thread] = None
        self._speaking: Callable[[], bool] = lambda: False
        self._stop = threading.Event()
        self.heard: List[str] = []

    def push(self, text: str) -> None:
        self.lines.put(text)

    def toggle_voice(self) -> bool:
        self.voice_in = not self.voice_in
        if self.voice_in and self.listener is not None and (self._vt is None or not self._vt.is_alive()):
            self._stop.clear()
            self._vt = threading.Thread(target=self._hear, daemon=True, name="tutor-hear")
            self._vt.start()
        return self.voice_in

    def _hear(self) -> None:
        while self.voice_in and not self._stop.is_set():
            if self._speaking():
                time.sleep(0.2)                                                  # the microphone would hear the tutor itself
                continue
            with contextlib.suppress(Exception):
                txt = self.listener.listen(max_s=7.0, silence_s=0.8, start_timeout=4.0) if self.listener else ""
                if txt:
                    self.heard.append(txt)
                    self.lines.put(txt)

    @staticmethod
    def _down(vk: int) -> bool:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

    @staticmethod
    def _cursor() -> Tuple[int, int]:
        class P(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        p = P()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def wait(self, box: Optional[Tuple[float, float, float, float]] = None, keys: Sequence[str] = (), timeout: float = 120.0, poll: float = 0.03) -> Dict[str, Any]:
        """The first of: a left click inside `box` (x1, y1, x2, y2), one of `keys` going down, a typed / spoken line, the timeout. {'kind': click | key | line | timeout, ...}."""
        t0 = time.time()
        was_down = self._down(VK["lbutton"])
        key_was = {k: self._down(VK[k]) for k in keys if k in VK}
        while time.time() - t0 < timeout:
            try:
                line = self.lines.get_nowait()
                return {"kind": "line", "text": line, "command": command_of(line)}
            except queue.Empty:
                pass
            down = self._down(VK["lbutton"])
            if down and not was_down:
                x, y = self._cursor()
                if box is None or (box[0] - 4 <= x <= box[2] + 4 and box[1] - 4 <= y <= box[3] + 4):
                    return {"kind": "click", "at": (x, y)}
            was_down = down
            for k in keys:
                d = self._down(VK[k]) if k in VK else False
                if d and not key_was.get(k, False):
                    return {"kind": "key", "key": k}
                key_was[k] = d
            time.sleep(poll)
        return {"kind": "timeout"}
