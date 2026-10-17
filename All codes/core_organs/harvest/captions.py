"""
harvest.captions -- subtitles for a video WITHOUT bursts against YouTube's transcript endpoint, and a local-speech fallback when a video has none.

The first real run used `youtube-transcript-api`, which hits the (undocumented) timed-text endpoint once per video with no pacing; this address was refused after ~40 requests. Here the same captions are
fetched the way a person's player gets them, through yt-dlp, paced the way yt-dlp documents for polite use (--sleep-requests 1.5 --sleep-interval 2 --max-sleep-interval 5), English first, manual
captions before automatic ones, NO browser cookies (nothing of the person's sign-in is read). A refusal (HTTP 429, "confirm you're not a bot") is reported as Blocked and the caller STOPS: nothing here retries into a block.

A video with no captions at all falls back to local CPU speech recognition (faster-whisper, int8, a model already on disk) on the first minutes of its audio: `whisper_transcript`.
"""
from __future__ import annotations

import glob
import json
import os
import re
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

PACING = {"sleep_interval_requests": 1.5, "sleep_interval": 2, "max_sleep_interval": 5}      # yt-dlp: --sleep-requests 1.5 --sleep-interval 2 --max-sleep-interval 5

_BLOCK_RX = re.compile(r"429|too many requests|confirm you.re not a bot|sign in to confirm|rate.?limit|blocked", re.I)


class TranscriptUnavailable(Exception):
    pass


def parse_json3(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """YouTube's json3 caption format -> [{text, start, duration}]. Automatic captions repeat the previous words in a rolling window, so a line that only extends the previous one replaces it."""
    out: List[Dict[str, Any]] = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs or "tStartMs" not in ev:
            continue
        text = re.sub(r"\s+", " ", "".join(s.get("utf8", "") for s in segs)).strip()
        if not text or text in ("[Music]", "[Applause]"):
            continue
        start, dur = ev["tStartMs"] / 1000.0, ev.get("dDurationMs", 0) / 1000.0
        if out and text.startswith(out[-1]["text"]) and start - out[-1]["start"] < 6.0:
            out[-1].update(text=text, duration=round(start + dur - out[-1]["start"], 3))
            continue
        out.append({"text": text, "start": round(start, 3), "duration": round(dur, 3)})
    return out


def _download(video_id: str, languages: Sequence[str], workdir: str, pacing: Dict[str, Any]) -> str:
    """Run yt-dlp for the subtitles only; returns the path of the json3 file ('' if none was written). Raises PermissionError when YouTube refuses."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": list(languages), "subtitlesformat": "json3",
            "outtmpl": os.path.join(workdir, "%(id)s.%(ext)s"), "socket_timeout": 25, "retries": 1, "extractor_retries": 1, **pacing}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as exc:
        msg = str(exc)
        if _BLOCK_RX.search(msg):
            raise PermissionError("Blocked:" + msg[:60])
        if re.search(r"video unavailable|private video|removed|not available|members.only|age", msg, re.I):
            raise TranscriptUnavailable("Video_Unavailable")
        raise
    files = sorted(glob.glob(os.path.join(workdir, f"{video_id}*.json3")))
    # manual captions (no auto suffix in the language tag is not distinguishable by name) -- prefer the requested language order
    for lang in languages:
        for f in files:
            if f".{lang}." in os.path.basename(f):
                return f
    return files[0] if files else ""


def ytdlp_transcript(video_id: str, languages: Sequence[str], download: Optional[Callable[..., str]] = None, pacing: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Captions through yt-dlp, paced, cookie-free. `download` is injectable for tests."""
    with tempfile.TemporaryDirectory(prefix="hv_caps_") as d:
        path = (download or _download)(video_id, languages, d, pacing or PACING)
        if not path:
            raise TranscriptUnavailable("No_Subtitles")
        segs = parse_json3(json.load(open(path, encoding="utf-8")))
    if not segs:
        raise TranscriptUnavailable("No_Subtitles")
    return segs


def whisper_transcript(video_id: str, max_audio_s: float = 240.0, model_size: str = "base.en", fetch_audio: Optional[Callable[..., str]] = None,
                       transcribe: Optional[Callable[..., List[Dict[str, Any]]]] = None) -> List[Dict[str, Any]]:
    """Local speech recognition of the first `max_audio_s` seconds of a video with no captions (CPU int8, a model already cached on disk: no download of weights). Both steps are injectable for tests."""
    from . import video_pipeline as VP
    with tempfile.TemporaryDirectory(prefix="hv_audio_") as d:
        path = (fetch_audio or _fetch_audio)(video_id, max_audio_s, d)
        if not path:
            raise TranscriptUnavailable("No_Audio")
        return (transcribe or VP.transcribe_audio)(path, model_size)


def _fetch_audio(video_id: str, max_audio_s: float, workdir: str) -> str:
    import yt_dlp
    from yt_dlp.utils import download_range_func
    opts = {"quiet": True, "no_warnings": True, "format": "bestaudio[ext=m4a]/bestaudio", "outtmpl": os.path.join(workdir, "%(id)s.%(ext)s"), "socket_timeout": 25, "retries": 1,
            "download_ranges": download_range_func(None, [(0, max_audio_s)]), "force_keyframes_at_cuts": False, **PACING}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as exc:
        if _BLOCK_RX.search(str(exc)):
            raise PermissionError("Blocked:" + str(exc)[:60])
        raise TranscriptUnavailable("No_Audio")
    files = glob.glob(os.path.join(workdir, f"{video_id}.*"))
    return files[0] if files else ""
