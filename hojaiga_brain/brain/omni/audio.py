# brain/omni/audio.py
"""Audio from scratch: decode → mono 16 kHz → log-mel spectrogram (STFT + mel filterbank) → MFCC.
WAV is read with the standard library; every other format (mp3, m4a, flac, ogg, video soundtracks)
is decoded by ffmpeg when it is on PATH."""
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Optional

import numpy as np

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus"}
SAMPLE_RATE = 16000


def load_audio(path: str, sr: int = SAMPLE_RATE, max_seconds: float = 30.0) -> Optional[np.ndarray]:
    p = Path(path)
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as w:
                ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
                raw = w.readframes(min(n, int(rate * max_seconds)))
            dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
            x = np.frombuffer(raw, dtype=dtype).astype(np.float32)
            x = (x - 128.0) / 128.0 if width == 1 else x / float(np.iinfo(dtype).max)
            x = x.reshape(-1, ch).mean(1)
            if rate != sr:                                   # linear resampling
                t_new = np.linspace(0, len(x) / rate, int(len(x) * sr / rate), endpoint=False)
                x = np.interp(t_new, np.arange(len(x)) / rate, x).astype(np.float32)
            return x
        except Exception:
            pass                                             # fall through to ffmpeg (e.g. float WAV)
    if not shutil.which("ffmpeg"):
        return None
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(p), "-t", str(max_seconds), "-ac", "1",
                          "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    if out.returncode != 0 or not out.stdout:
        return None
    return np.frombuffer(out.stdout, dtype=np.float32).copy()


def _mel_filterbank(n_mels: int, n_fft: int, sr: int) -> np.ndarray:
    def hz_to_mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel_to_hz(m):
        return 700.0 * (10 ** (m / 2595.0) - 1.0)
    mels = np.linspace(hz_to_mel(0), hz_to_mel(sr / 2), n_mels + 2)
    bins = np.floor((n_fft + 1) * mel_to_hz(mels) / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mels + 1):
        a, b, c = bins[m - 1], bins[m], bins[m + 1]
        for k in range(a, b):
            fb[m - 1, k] = (k - a) / max(b - a, 1)
        for k in range(b, c):
            fb[m - 1, k] = (c - k) / max(c - b, 1)
    return fb


def log_mel(x: np.ndarray, sr: int = SAMPLE_RATE, n_mels: int = 64, n_fft: int = 400, hop: int = 160) -> np.ndarray:
    """[n_mels, frames] log-mel spectrogram (25 ms windows, 10 ms hop at 16 kHz)."""
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    frames = 1 + (len(x) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(x[idx] * np.hanning(n_fft).astype(np.float32), axis=1)) ** 2
    mel = _mel_filterbank(n_mels, n_fft, sr) @ spec.T
    return np.log(mel + 1e-6).astype(np.float32)


def mfcc_features(x: np.ndarray, sr: int = SAMPLE_RATE, n_mfcc: int = 20) -> np.ndarray:
    """Fixed-length vector for classical ML: mean and std of MFCCs + spectral centroid/energy stats."""
    lm = log_mel(x, sr)
    n = lm.shape[0]
    k = np.arange(n)
    dct = np.cos(np.pi / n * (k[None, :] + 0.5) * np.arange(n_mfcc)[:, None])
    mf = dct @ lm
    energy = np.log(np.mean(x.reshape(-1)[: len(x) // 160 * 160].reshape(-1, 160) ** 2, axis=1) + 1e-8) \
        if len(x) >= 160 else np.zeros(1)
    feats = np.concatenate([mf.mean(1), mf.std(1), [energy.mean(), energy.std(), lm.mean(), lm.std()]])
    return feats.astype(np.float32)


def write_wav(path: str, x: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
