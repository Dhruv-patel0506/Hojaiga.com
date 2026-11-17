"""
professor.setup_audio -- automated local setup of the modern audio stack (idempotent: safe to run on any machine, any number of times).

  speech-to-text   faster-whisper (CTranslate2) with the `base.en` model            -> sounddevice records, Whisper transcribes, all offline after the first download
  text-to-speech   piper-tts with an en_US voice (default en_US-lessac-medium)      -> ~16x faster than real time on CPU (kokoro-onnx is installed too but slower here)
  microphone       sounddevice (PortAudio) device check

`status()` only reports. `install(download=True)` pip-installs what is missing into the CURRENT interpreter (free open-source wheels; the dependency gate was
run first: all have Python 3.13 wheels, none touches numpy / torch / transformers) and downloads the two models once (~145 MB whisper, ~63 MB piper voice).
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from typing import Any, Dict, List

from . import config as CFG

PACKAGES = {"sounddevice": "sounddevice", "soundfile": "soundfile", "faster_whisper": "faster-whisper", "piper": "piper-tts", "kokoro_onnx": "kokoro-onnx"}


def _have(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def status() -> Dict[str, Any]:
    pk = {mod: _have(mod) for mod in PACKAGES}
    voice = os.path.join(CFG.PIPER_DIR, CFG.PIPER_VOICE + ".onnx")
    out: Dict[str, Any] = {"packages": pk, "piper_voice": os.path.isfile(voice), "piper_voice_path": voice,
                           "kokoro_model": os.path.isfile(os.path.join(CFG.KOKORO_DIR, "kokoro-v1.0.int8.onnx")), "whisper_model_cached": None, "microphone": None}
    if pk["faster_whisper"]:
        cache = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
        out["whisper_model_cached"] = os.path.isdir(cache) and any("faster-whisper-base.en" in d for d in os.listdir(cache))
    if pk["sounddevice"]:
        try:
            import sounddevice as sd
            sd.check_input_settings(samplerate=16000, channels=1, dtype="int16")
            out["microphone"] = [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0][:3]
        except Exception as exc:
            out["microphone"] = f"{type(exc).__name__}: {str(exc)[:80]}"
    out["ready"] = bool(pk["sounddevice"] and pk["faster_whisper"] and pk["piper"] and out["piper_voice"])
    return out


def install(download: bool = True) -> Dict[str, Any]:
    log: List[str] = []
    missing = [pip for mod, pip in PACKAGES.items() if not _have(mod)]
    if missing:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *missing], capture_output=True, text=True, timeout=900)
        log.append(f"pip install {' '.join(missing)} -> rc={r.returncode}" + ("" if r.returncode == 0 else " " + r.stderr[-300:]))
        importlib.invalidate_caches()
    if download:
        voice = os.path.join(CFG.PIPER_DIR, CFG.PIPER_VOICE + ".onnx")
        if not os.path.isfile(voice) and _have("piper"):
            os.makedirs(CFG.PIPER_DIR, exist_ok=True)
            r = subprocess.run([sys.executable, "-m", "piper.download_voices", CFG.PIPER_VOICE, "--download-dir", CFG.PIPER_DIR], capture_output=True, text=True, timeout=900)
            log.append(f"piper voice {CFG.PIPER_VOICE} -> rc={r.returncode}")
        if _have("faster_whisper"):
            try:
                from faster_whisper import WhisperModel
                WhisperModel("base.en", device="cpu", compute_type="int8")
                log.append("whisper base.en ready")
            except Exception as exc:
                log.append(f"whisper model: {type(exc).__name__}: {str(exc)[:100]}")
    st = status()
    st["log"] = log
    return st
