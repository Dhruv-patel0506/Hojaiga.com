"""
harvest_video_guides -- turns a (hour-long) YouTube software tutorial into machine-readable
training data, entirely on this machine and entirely free:

    URL -> transcript -> keyframes -> narration/screen alignment -> structured GUI steps
                                                                      -> dataset

Nothing is paid for and nothing leaves the box:
  * yt-dlp            video / audio / caption download from YouTube            (MIT, free)
  * YouTube captions  preferred transcript source when they exist              (free, instant)
  * faster-whisper    local speech-to-text when captions are missing or poor   (MIT, free, CPU)
  * ffmpeg            scene-change + stride frame extraction                   (free)
  * tesseract OCR     reads the labels that are on screen in each keyframe     (free)
  * Qwen3-VL :8081    narration + keyframe -> JSON steps (local, no key)
  * Ollama   :11434   text-only fallback (narration + OCR text)
  * regex rules       last-resort extractor: works with no model at all

Honesty rules (Hojaiga product laws):
  * Every step carries the engine that produced it ("vlm" | "ollama" | "rules") and a
    confidence. Nothing is presented as verified: this stage PRODUCES candidate guides,
    the live executor + UIA oracle is what proves them.
  * Sources are reported per video: captions vs whisper, frame count kept vs sampled,
    chunks processed vs chunks available. Truncation is never silent.
  * A model that is down is reported as down and the run continues on the weaker engine
    instead of failing or faking output.

Everything is checkpointed per stage, so an hour-long video can be stopped at minute 55
and resumed with the same command (--resume is the default behaviour).

Usage
-----
  python harvest_video_guides.py --check                     # report the environment and exit
  python harvest_video_guides.py <youtube-url> --app "Blender" --pilot 3
  python harvest_video_guides.py <youtube-url> --app "Blender" --full
  python harvest_video_guides.py <youtube-url> --full --engine vlm --max-height 1080
  python harvest_video_guides.py <youtube-url> --start-chunk 150 --pilot 6   # probe mid-video
  python harvest_video_guides.py --links links.txt           # one URL (or App::URL) per line
  python harvest_video_guides.py --xlsx master.xlsx --col-app "App Name" --col-url "YouTube Tutorial Link"
  python harvest_video_guides.py <url> --reassemble          # rebuild guides, no model calls

Rerunning the same command resumes: captions, transcript, keyframes, alignment and extracted
chunks are each cached under video_dataset/<id>/, so an interrupted hour-long job picks up where
it stopped. --redo discards the caches and rebuilds everything.

Output layout
-------------
  video_dataset/<video_id>/
      meta.json         probe result (title, duration, channel, caption availability)
      transcript.json   timed cues [{start,end,text,src}]
      frames/           kept keyframes (jpg) + frames.json [{t,path,dhash,ocr_text,ocr_words}]
      chunks.json       narration aligned to screen states
      steps.jsonl       one line per chunk: the steps that were extracted (resumable)
      guide.md          human-readable walkthrough
      model_io.log      every prompt + raw model answer (vision-interaction audit trail)
  video_dataset/dataset.jsonl       one line per harvested video (the ledger of the corpus)
  video_dataset/corpus/<id>.jsonl   one line per step (image ref + narration + step) for RAG/ML
  video_dataset/split.json          app-level 70/30 TRAIN-EVAL assignment (same seed as the text corpus)
  video_dataset/index.csv           per-video status ledger for a batch run
  trajectories/<TRAIN|EVAL>/<app_key>/<app_key>__<hash>.json   executor-ready guides
  brain/train_samples.jsonl         appended through phase1_training_dataset.sample_from_step
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

# The Windows console is cp1252; transcripts and titles carry smart quotes, arrows and
# emoji. Reconfigure both streams so one stray glyph can never kill a multi-hour run.
for _s in (sys.stdout, sys.stderr):
    try:
        _rc = getattr(_s, "reconfigure", None)
        if callable(_rc):
            _rc(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
ORGANS = ROOT / "All codes"                    # the Hojaiga organ package
if str(ORGANS) not in sys.path:
    sys.path.insert(0, str(ORGANS))

VIDEO_DIR = Path(os.environ.get("HOJAIGA_VIDEO_DIR", "video_dataset"))
TRAJ_DIR = Path(os.environ.get("HOJAIGA_TRAJ_DIR", "trajectories"))
BRAIN_DIR = Path(os.environ.get("HOJAIGA_BRAIN_DIR", "brain"))
TRAIN_SAMPLES = BRAIN_DIR / "train_samples.jsonl"

VISION_URL = os.environ.get("HOJAIGA_QWEN_VL_URL",
                            os.environ.get("HOJAIGA_PROF_VISION_URL", "http://127.0.0.1:8081")).rstrip("/")
OLLAMA_URL = os.environ.get("HOJAIGA_PROF_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("HOJAIGA_VG_MODEL", "qwen2.5:7b")
OLLAMA_PICK = {"model": OLLAMA_MODEL}          # resolved to whatever is actually installed at run start

SPLIT_SEED = int(os.environ.get("HOJAIGA_SPLIT_SEED", "7"))     # same convention as decompose_guides
TRAIN_RATIO = 0.70

WHISPER_MODEL = os.environ.get("HOJAIGA_WHISPER_MODEL", "base.en")
WHISPER_THREADS = int(os.environ.get("HOJAIGA_WHISPER_THREADS", "8"))
SEGMENT_SECONDS = int(os.environ.get("HOJAIGA_WHISPER_SEGMENT", "600"))   # checkpoint granularity

MAX_HEIGHT = 720            # keyframe resolution: below this, dense desktop UI text stops being OCR-able
STRIDE = 4.0                # safety-net frame sampling every N seconds (scene cuts add the rest)
SCENE_THRESHOLD = 0.10      # ffmpeg scene score; 0.10 catches a menu open, ignores a blinking caret
DHASH_KEEP = 6              # hamming bits a frame must differ from the last kept one to count as a new state
OCR_WORDS = 140             # on-screen words handed to the model per chunk
NARRATION_CAP = 900         # characters of narration per chunk (longer stretches are split, never dropped)
CHUNK_TOKENS = 700
CHAT_TIMEOUT = 150.0
MIN_FREE_GB = 6.0

VALID_ACTIONS = {"CLICK", "RIGHT_CLICK", "DOUBLE_CLICK", "HOVER", "DRAG_AND_DROP",
                 "CONTINUOUS_DRAG", "TYPE_TEXT", "KEY_COMBINATION"}
ACTION_MAP = {
    "click": ("CLICK", True), "left_click": ("CLICK", True), "press": ("CLICK", True),
    "tap": ("CLICK", True), "click_button": ("CLICK", True), "invoke": ("CLICK", True),
    "right_click": ("RIGHT_CLICK", True), "rightclick": ("RIGHT_CLICK", True),
    "double_click": ("DOUBLE_CLICK", True), "doubleclick": ("DOUBLE_CLICK", True),
    "hover": ("HOVER", True), "mouse_over": ("HOVER", True),
    "drag": ("DRAG_AND_DROP", True), "drag_drop": ("DRAG_AND_DROP", True),
    "drag_and_drop": ("DRAG_AND_DROP", True),
    "type": ("TYPE_TEXT", True), "fill": ("TYPE_TEXT", True), "enter": ("TYPE_TEXT", True),
    "write": ("TYPE_TEXT", True), "input": ("TYPE_TEXT", True), "paste": ("TYPE_TEXT", True),
    "key": ("KEY_COMBINATION", True), "shortcut": ("KEY_COMBINATION", True),
    "hotkey": ("KEY_COMBINATION", True), "press_key": ("KEY_COMBINATION", True),
    "scroll": ("SCROLL", False), "wait": ("WAIT", False), "observe": ("OBSERVE", False),
    "read": ("OBSERVE", False), "none": ("NONE", False),
}
ELEMENT_HINTS = ("button", "menu item", "menu", "tab", "text field", "input", "checkbox",
                 "radio", "dropdown", "combo box", "list item", "icon", "link", "slider",
                 "toolbar", "ribbon", "dialog", "sidebar", "pane", "canvas")

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(f"[harvest] {msg}", flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hhmmss(sec: float) -> str:
    sec = int(max(0, sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def rel_frame(path: str) -> str:
    """Frame reference relative to the repo root. Empty string when the run had no keyframes
    (transcript-only), which is a supported mode, not an error."""
    if not path:
        return ""
    try:
        return os.path.relpath(str(path), str(ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=3), encoding="utf-8")


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def append_jsonl(path: Path, row) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list:
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return rows


def slugify(text: str, maxlen: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
    return (s[:maxlen].rstrip("_")) or "app"


def run(cmd: list, timeout: float = 3600.0, cwd=None) -> tuple:
    """Hidden subprocess (no window, no focus stolen). Returns (rc, stdout, stderr)."""
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, cwd=cwd,
                           creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as exc:
        return -2, "", f"{type(exc).__name__}: {exc}"


def find_ffmpeg(name: str = "ffmpeg") -> str:
    """env override, PATH, then the ffmpeg build that already lives in this repo."""
    env = os.environ.get("HOJAIGA_FFMPEG" if name == "ffmpeg" else "HOJAIGA_FFPROBE", "")
    for cand in (env, shutil.which(name) or ""):
        if cand and os.path.isfile(cand):
            return cand
    for cand in sorted(ROOT.glob(f"ffmeg/**/{name}.exe")):
        return str(cand)
    return shutil.which(name) or ""


FFMPEG = find_ffmpeg("ffmpeg")
FFPROBE = find_ffmpeg("ffprobe")


def media_tool() -> str:
    if not FFMPEG:
        raise RuntimeError("ffmpeg not found (set HOJAIGA_FFMPEG or add it to PATH)")
    return FFMPEG


def free_gb(path=ROOT) -> float:
    try:
        return shutil.disk_usage(str(path)).free / 2 ** 30
    except Exception:
        return 999.0


# ---------------------------------------------------------------------------
# Environment pre-flight (--check): report what is actually usable, honestly
# ---------------------------------------------------------------------------

def vision_health() -> dict:
    try:
        import requests
        r = requests.get(VISION_URL + "/health", timeout=2)
        up = r.status_code == 200
        model = ""
        if up:
            try:
                m = requests.get(VISION_URL + "/v1/models", timeout=2).json()
                model = (m.get("data") or [{}])[0].get("id", "")
            except Exception:
                pass
        return {"up": up, "url": VISION_URL, "model": model}
    except Exception as exc:
        return {"up": False, "url": VISION_URL, "error": type(exc).__name__}


def vision_autostart(wait_s: float = 120.0) -> dict:
    """Bring the local vision server up through the Professor's own lifecycle manager."""
    try:
        from core_organs.professor import vision_server as VS
        r = VS.ensure(wait_s=wait_s)
        if r.get("ok"):
            log(f"vision server up ({r.get('model_loaded') or r.get('profile')} at {r.get('url')})")
        else:
            log(f"vision server NOT up: {str(r.get('error'))[:120]}")
        return r
    except Exception as exc:
        log(f"vision autostart unavailable ({type(exc).__name__}); will fall back if a text model is up")
        return {"ok": False, "error": str(exc)[:120]}


def ollama_health() -> dict:
    try:
        import requests
        j = requests.get(OLLAMA_URL + "/api/tags", timeout=2).json()
        names = [m.get("name", "") for m in j.get("models", [])]
        want = OLLAMA_MODEL.split(":")[0]
        pick = next((n for n in names if n.split(":")[0] == want), "") or (names[0] if names else "")
        return {"up": bool(names), "models": names[:8], "model": pick}
    except Exception as exc:
        return {"up": False, "error": type(exc).__name__}


def whisper_cached(model: str) -> bool:
    cache = Path(os.path.expanduser("~")) / ".cache" / "huggingface" / "hub"
    try:
        return any(f"faster-whisper-{model}" in d.name for d in cache.iterdir()) if cache.is_dir() else False
    except Exception:
        return False


def check_env(args) -> int:
    import platform
    rows = []
    try:
        import yt_dlp
        rows.append(("yt-dlp", "ok", yt_dlp.version.__version__))
    except Exception as exc:
        rows.append(("yt-dlp", "MISSING", f"{type(exc).__name__} -- pip install yt-dlp"))
    try:
        import faster_whisper
        rows.append(("faster-whisper", "ok", f"{faster_whisper.__version__} / model {args.whisper_model} "
                     f"{'cached' if whisper_cached(args.whisper_model) else 'will download once (free)'}"))
    except Exception:
        rows.append(("faster-whisper", "MISSING", "pip install faster-whisper (captions still work without it)"))
    rows.append(("ffmpeg", "ok" if FFMPEG else "MISSING", FFMPEG or "set HOJAIGA_FFMPEG"))
    try:
        import pytesseract
        exe = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract") or \
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        ver = ""
        if os.path.isfile(exe):
            pytesseract.pytesseract.tesseract_cmd = exe
            ver = (pytesseract.get_tesseract_version() and str(pytesseract.get_tesseract_version())) or ""
        rows.append(("tesseract OCR", "ok" if os.path.isfile(exe) else "MISSING", str(ver or exe)))
    except Exception as exc:
        rows.append(("tesseract OCR", "MISSING", type(exc).__name__ + " (pipeline runs without OCR)"))
    try:
        import cv2
        rows.append(("opencv", "ok", cv2.__version__))
    except Exception:
        rows.append(("opencv", "MISSING", "pip install opencv-python"))
    v = vision_health()
    rows.append(("vision :8081", "up" if v.get("up") else "down", v.get("model") or v.get("error", "")))
    o = ollama_health()
    rows.append(("ollama :11434", "up" if o.get("up") else "down", o.get("model") or o.get("error", "")))
    rows.append(("python", "ok", f"{platform.system()} {platform.python_version()}"))
    rows.append(("free disk", ("ok" if free_gb() > MIN_FREE_GB else "LOW"), f"{free_gb():.1f} GB"))
    width = max(len(r[0]) for r in rows)
    print("\n--- harvest_video_guides environment ---")
    for name, state, detail in rows:
        flag = "PASS" if state in ("ok", "up") else "WARN"
        print(f"  [{flag}] {name.ljust(width)}  {state}  {detail}")
    print(f"  engine plan: {engine_plan(v, o, args)}\n")
    return 0


def engine_plan(v: dict, o: dict, args) -> str:
    want = args.engine
    if want == "rules":
        return "rules only (no model calls)"
    if want == "vlm":
        return "vlm :8081" if v.get("up") else "vlm requested but :8081 is down"
    if want == "ollama":
        return f"ollama {o.get('model', '')}" if o.get("up") else "ollama requested but :11434 is down"
    if v.get("up"):
        return f"vlm :8081 ({v.get('model') or 'qwen3-vl'})"
    if o.get("up"):
        return f"ollama text-only {o.get('model')}"
    return "regex rules (weakest, always available)"


# ---------------------------------------------------------------------------
# Stage 1: probe the link
# ---------------------------------------------------------------------------

def ydl(extra: dict, client: str = ""):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "noprogress": True,
            "noplaylist": not extra.get("_playlist", False),
            "concurrent_fragment_downloads": 4, "restrictfilenames": True,
            "socket_timeout": 30}
    if FFMPEG:
        opts["ffmpeg_location"] = str(Path(FFMPEG).parent)
    if client:
        # YouTube answers some requests with 403 on one player client and fine on another
        opts["extractor_args"] = {"youtube": {"player_client": [client, "web"]}}
    opts.update({k: v for k, v in extra.items() if not k.startswith("_")})
    return yt_dlp.YoutubeDL(opts)


CLIENTS = ["", "android", "ios", "web_embedded", "mweb"]


def ydl_download(url: str, extra: dict) -> bool:
    """Download with a player-client fallback: YouTube throws 403 on one client and serves
    fine on the next, and an hour-long download lost to that should not lose the video."""
    for cl in CLIENTS:
        try:
            ydl(extra, cl).download([url])
            return True
        except Exception as exc:
            log(f"  download via client '{cl or 'default'}' failed "
                f"({type(exc).__name__}: {str(exc)[:90]})"
                + ("; trying the next one" if cl != CLIENTS[-1] else ""))
            time.sleep(2.0)
    return False


def probe(url: str, args) -> dict:
    info = ydl({"skip_download": True, "_playlist": args.playlist}).extract_info(url, download=False)
    if info.get("_type") == "playlist":
        return {"playlist": True, "title": info.get("title", ""),
                "entries": [e for e in (info.get("entries") or []) if e]}
    return normalise_meta(info, None, url)


def normalise_meta(info: dict, work, url: str) -> dict:
    vid = str(info.get("id") or hashlib.sha1(url.encode()).hexdigest()[:11])
    subs = sorted((info.get("subtitles") or {}).keys())
    autos = sorted((info.get("automatic_captions") or {}).keys())
    meta = {
        "video_id": vid, "url": url, "title": info.get("title", ""),
        "duration": float(info.get("duration") or 0), "channel": info.get("uploader") or info.get("channel", ""),
        "lang": info.get("language", ""), "uploaded": str(info.get("upload_date") or ""),
        "manual_subs": subs, "auto_subs": autos,
        "has_english_sub": any(k.startswith("en") for k in subs) or any(k.startswith("en") for k in autos),
        "probed": now_iso(),
    }
    if work is not None:
        write_json(Path(work) / "meta.json", meta)
    return meta


# ---------------------------------------------------------------------------
# Stage 2a: captions (free + instant, the preferred transcript source)
# ---------------------------------------------------------------------------

_TS_RE = re.compile(r"(\d+:)?\d+:\d{2}:\d{2}\.?\d{0,3}\s*-->\s*(\d+:)?\d+:\d{2}:\d{2}\.?\d{0,3}")
_TAG_RE = re.compile(r"<[^>]+>")


def _to_sec(stamp: str) -> float:
    stamp = stamp.strip().replace(",", ".")
    parts = stamp.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h, m, s = "0", parts[0], parts[1]
        else:
            return 0.0
        return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        return 0.0


def parse_captions(path: Path) -> list:
    """WebVTT or SRT -> [{start,end,text}]. Inline timing/colour tags are stripped."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    cues = []
    block = []
    for line in raw.replace("\ufeff", "").splitlines():
        block.append(line)
        if line.strip() == "":
            cue = _cue_from_block(block)
            if cue:
                cues.append(cue)
            block = []
    cue = _cue_from_block(block)
    if cue:
        cues.append(cue)
    return dedupe_rolling(cues)


def _cue_from_block(lines) -> dict:
    head = ""
    for ln in lines:
        if _TS_RE.search(ln):
            head = ln
            break
    if not head:
        return {}
    m = _TS_RE.search(head)
    a, b = head[:m.end()].split("-->")
    body = " ".join(_TAG_RE.sub("", ln).strip() for ln in lines[lines.index(head) + 1:] if ln.strip())
    body = re.sub(r"\s+", " ", body).strip()
    if not body:
        return {}
    return {"start": _to_sec(a.strip()), "end": _to_sec(b.strip()), "text": body}


def dedupe_rolling(cues: list) -> list:
    """YouTube auto-captions are 'rolling': every cue repeats part of what came before it, so a
    naive join prints each phrase two or three times. Rebuild the stream instead: append to the
    running text only the part of the new cue that does not already end the previous text."""
    out, tail = [], []
    for c in cues:
        toks = str(c["text"]).split()
        low = [t.lower().strip(".,!?;:\"'()") for t in toks]
        prev = [t.lower().strip(".,!?;:\"'()") for t in tail]
        overlap = 0
        for L in range(min(len(prev), len(low)), 1, -1):     # require >=2 words to count as overlap
            if prev[-L:] == low[:L]:
                overlap = L
                break
        new = toks[overlap:]
        if not new:
            continue                                          # cue carried nothing new
        out.append({"start": c["start"], "end": c["end"], "text": " ".join(new),
                    "src": c.get("src", "captions")})
        tail = (tail + new)[-40:]
    return out


def caption_stage(url: str, work: Path, allow_playlist: bool = False) -> list:
    dl = work / "captions"
    dl.mkdir(parents=True, exist_ok=True)
    opts = {"skip_download": True, "writesubtitles": True, "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US", "en-GB", "en.*", "en-[0-9].*"],
            "subtitlesformat": "vtt/srt/best", "outtmpl": str(dl / "%(id)s.%(ext)s"),
            "_playlist": allow_playlist}
    try:
        ydl_download(url, opts)
    except Exception as exc:
        log(f"caption fetch failed: {type(exc).__name__}: {str(exc)[:120]}")
        return []
    files = sorted(dl.glob("*.vtt")) + sorted(dl.glob("*.srt"))
    manual = [f for f in files if not f.stem.split(".")[-1].startswith("en-orig") and "auto" not in f.name]
    for cand in manual + [f for f in files if f not in manual]:
        cues = parse_captions(cand)
        if words_of(cues) > 40:
            log(f"captions from {cand.name}: {len(cues)} cues, {words_of(cues)} words")
            return cues
    return []


def words_of(cues: list) -> int:
    return sum(len(str(c.get("text", "")).split()) for c in cues)


def speech_rate_ok(cues: list, duration: float) -> bool:
    """A real walkthrough says roughly 100-200 words a minute. Anything far below is music,
    a silent screen recording, or a broken caption track -- Whisper should get a chance."""
    if not cues:
        return False
    w = words_of(cues)
    if duration <= 0:
        return w > 200
    return (w / (duration / 60.0)) >= 45.0


# ---------------------------------------------------------------------------
# Stage 2b: local Whisper (free, CPU, checkpointed per audio segment)
# ---------------------------------------------------------------------------

def download_audio(url: str, work: Path, allow_playlist: bool = False) -> str:
    dl = work / "audio"
    dl.mkdir(parents=True, exist_ok=True)
    out = dl / "src.%(ext)s"
    opts = {"format": "bestaudio[ext=m4a]/bestaudio/best", "outtmpl": str(out),
            "_playlist": allow_playlist}
    ydl_download(url, opts)
    cands = [p for p in dl.iterdir() if p.is_file() and p.stat().st_size > 100_000
             and not p.name.endswith((".part", ".ytdl")) and p.suffix.lower() != ".json"]
    if not cands:
        log("audio download produced no usable file (YouTube refused or the video has no audio)")
        return ""
    src = max(cands, key=lambda p: p.stat().st_size)
    wav = dl / "speech_16k.wav"
    rc, _, err = run([media_tool(), "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
                      "-c:a", "pcm_s16le", wav], timeout=1800)
    if rc != 0 or not wav.is_file():
        log(f"audio decode failed: {err[-200:]}")
        return ""
    try:
        src.unlink()                     # the raw m4a is not needed once decoded
    except OSError:
        pass
    log(f"audio ready: {wav.name} {wav.stat().st_size / 2 ** 20:.1f} MB (16 kHz mono)")
    return str(wav)


def wav_duration(path: str) -> float:
    rc, out, _ = run([FFPROBE or media_tool(), "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", path], timeout=120)
    try:
        return float(out.strip().splitlines()[0])
    except Exception:
        return 0.0


def silence_split_points(wav: str, total: float, seg_s: int) -> list:
    """Cut a long recording at the quietest moment near each segment boundary, so no word is
    sliced in half and each Whisper call stays small enough to checkpoint."""
    cuts = []
    try:
        import numpy as np
        import wave
        with wave.open(wav, "rb") as w:
            n = w.getnframes()
            sr = w.getframerate() or 16000
            raw = w.readframes(n)
        a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        win = max(1, int(sr * 0.25))
        hop = win
        count = max(1, len(a) // hop)
        rms = np.sqrt(np.mean(a[:count * hop].reshape(count, hop) ** 2, axis=1))
        t = seg_s
        while t < total - 5:
            lo = max(0, int((t - 10) / (hop / sr)))
            hi = min(len(rms), int((t + 10) / (hop / sr)))
            if hi > lo:
                best = lo + int(np.argmin(rms[lo:hi]))
                cuts.append(round(best * hop / sr, 3))
            else:
                cuts.append(float(t))
            t += seg_s
    except Exception as exc:
        log(f"silence-aware splitting unavailable ({type(exc).__name__}); using fixed cuts")
    return sorted(set(cuts))


def extract_segment(wav: str, start: float, dur: float, out: Path) -> bool:
    rc, _, err = run([media_tool(), "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.1f}", "-i", wav,
                      "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", out], timeout=900)
    return rc == 0 and out.is_file() and out.stat().st_size > 4000


def whisper_stage(url: str, work: Path, args, meta: dict) -> list:
    """Transcribe the whole recording with faster-whisper, one segment at a time, so a crash
    or a stop costs at most one segment. Cached on disk -> resumable."""
    segdir = work / "asr"
    segdir.mkdir(parents=True, exist_ok=True)
    audio = work / "audio" / "speech_16k.wav"
    if not audio.is_file():
        got = download_audio(url, work, args.playlist)
        if not got:
            return []
    total = wav_duration(str(audio)) or meta.get("duration", 0)
    log(f"whisper {args.whisper_model} on {hhmmss(total)} of audio ({WHISPER_THREADS} CPU threads)")
    cuts = silence_split_points(str(audio), total, args.whisper_segment) or []
    bounds = sorted({0.0} | {round(c, 3) for c in cuts if 5.0 <= c <= total - 5.0} | {total})
    cues = []
    done = 0
    t0 = time.time()
    model = None
    for i in range(len(bounds) - 1):
        start, end = bounds[i], bounds[i + 1]
        dur = end - start
        if dur < 1.0:
            continue
        ck = segdir / f"seg{i:03d}.json"
        if ck.is_file() and not args.redo:
            cues.extend(read_json(ck, []) or [])
            done += 1
            continue
        sf = segdir / f"seg{i:03d}.wav"
        if not (sf.is_file() or extract_segment(str(audio), start, dur, sf)):
            log(f"segment {i} could not be cut; skipping (reported in meta)")
            continue
        if model is None:
            model = load_whisper(args.whisper_model)
            if model is None:
                return cues
        got = transcribe_range(model, str(sf), start)
        if got is None:
            log(f"segment {i} failed to transcribe; the rest continue")
            continue
        write_json(ck, got)
        cues.extend(got)
        done += 1
        el = time.time() - t0
        eta = el / max(1, done) * (len(bounds) - 1 - done)
        log(f"  asr segment {done}/{len(bounds) - 1} -> {hhmmss(end)} "
            f"({words_of(got)} words, {el:.0f}s elapsed, eta {hhmmss(eta)})")
    for f in segdir.glob("seg*.wav"):
        try:
            f.unlink()
        except OSError:
            pass
    cues.sort(key=lambda c: c["start"])
    log(f"whisper done: {len(cues)} cues, {words_of(cues)} words")
    return cues


_whisper_lock = threading.Lock()
_whisper_model = None


def load_whisper(name: str):
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model
        try:
            from faster_whisper import WhisperModel
            log(f"loading faster-whisper '{name}' (cpu/int8, first use downloads it once -- free)")
            _whisper_model = WhisperModel(name, device="cpu", compute_type="int8",
                                          cpu_threads=WHISPER_THREADS)
            return _whisper_model
        except Exception as exc:
            log(f"faster-whisper unavailable: {type(exc).__name__}: {str(exc)[:160]}")
            return None


def transcribe_range(model, path: str, offset: float) -> list:
    """One Whisper call. condition_on_previous_text=False keeps an hour-long file from
    looping on its own output; vad_filter drops the silences between demos."""
    try:
        segs, _info = model.transcribe(path, language="en", beam_size=1, vad_filter=True,
                                       word_timestamps=True, condition_on_previous_text=False,
                                       initial_prompt="A screen-recording software tutorial with UI names and menu commands.")
        out = []
        for s in segs:
            txt = (s.text or "").strip()
            if txt:
                out.append({"start": round(float(s.start) + offset, 3), "end": round(float(s.end) + offset, 3),
                            "text": txt, "src": "whisper",
                            "words": [[round(float(w.start) + offset, 3), round(float(w.end) + offset, 3), w.word.strip()]
                                      for w in (s.words or [])]})
        return out
    except Exception as exc:
        log(f"  transcribe error: {type(exc).__name__}: {str(exc)[:140]}")
        return None


def transcript_stage(url: str, work: Path, args, meta: dict) -> list:
    out = work / "transcript.json"
    if out.is_file() and not args.redo:
        cues = read_json(out, []) or []
        if cues:
            meta["transcript_source"] = cues[0].get("src", "captions")
            log(f"transcript reused from checkpoint: {len(cues)} cues ({cues[0].get('src', '?')})")
            return cues
    if args.transcribe == "off":
        return []
    cues = [] if args.transcribe == "force" else caption_stage(url, work, args.playlist)
    if cues and not args.require_whisper and speech_rate_ok(cues, meta.get("duration", 0)):
        meta["transcript_source"] = "captions"
    else:
        if cues:
            log(f"caption track looks thin ({words_of(cues)} words over {hhmmss(meta.get('duration', 0))}); "
                f"transcribing locally instead")
        w = whisper_stage(url, work, args, meta)
        if w:
            cues, meta["transcript_source"] = w, "whisper"
        elif cues:
            meta["transcript_source"] = "captions-thin"
        else:
            meta["transcript_source"] = "none"
    if args.drop_words:
        for c in cues:
            c.pop("words", None)
    write_json(out, cues)
    return cues


# ---------------------------------------------------------------------------
# Stage 3: keyframes -- one decode pass for the stride grid, seeks for the scene cuts
# ---------------------------------------------------------------------------

def scale_vf(max_height: int) -> str:
    """Fit a frame to at most max_height pixels (never upscale). The comma inside min() is
    escaped because ffmpeg's filter graph parser would otherwise read it as a new filter."""
    return f"scale=-2:min({max_height}\\,ih)"


def find_video(work: Path) -> str:
    """The downloaded stream, whatever suffix yt-dlp gave this format."""
    dl = work / "video"
    if not dl.is_dir():
        return ""
    cands = [p for p in dl.iterdir()
             if p.is_file() and p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".ts")
             and not p.name.endswith((".part", ".ytdl"))]
    return str(max(cands, key=lambda p: p.stat().st_size)) if cands else ""


def download_video(url: str, work: Path, args) -> str:
    """Video-only stream capped at args.max_height: enough pixels to read UI labels,
    small enough that an hour is a few hundred MB, and no audio track to merge."""
    dl = work / "video"
    dl.mkdir(parents=True, exist_ok=True)
    existing = find_video(work)
    if existing and not args.redo and not args.reframes:
        log(f"reusing downloaded stream {Path(existing).name}")
        return existing
    h = int(args.max_height)
    opts = {"format": f"bv*[height<={h}][ext=mp4]/bv*[height<={h}]/bv",
            "outtmpl": str(dl / "%(id)s.%(ext)s"), "_playlist": args.playlist}
    if args.max_filesize_mb:
        opts["max_filesize"] = int(args.max_filesize_mb) * 2 ** 20
    log(f"downloading video stream (<= {h}p, video only) -- {free_gb():.0f} GB free")
    ydl_download(url, opts)
    got = find_video(work)
    if not got:
        log("video download produced no file (every player client refused, or the video is "
            "age-gated): continuing transcript-only, which still yields a guide")
        return ""
    log(f"video ready: {Path(got).name} {Path(got).stat().st_size / 2 ** 20:.0f} MB")
    return got


def scene_times(video: str, args) -> list:
    """Find the moments the screen visibly changed. The probe decode runs at low fps and
    low width (an hour costs about a minute of CPU) -- we only need the timestamps, and
    the full-quality frame is grabbed later with a fast seek."""
    vf = (f"fps={args.scene_probe_fps},scale={args.scene_probe_width}:-2,"
          f"select='gt(scene,{args.scene_threshold})',showinfo")
    rc, out, err = run([media_tool(), "-hide_banner", "-i", video, "-vf", vf, "-an", "-f", "null", "-"],
                       timeout=5400)
    times = [float(m) for m in re.findall(r"pts_time:([0-9]+\.?[0-9]*)", err or out)]
    log(f"scene detection: {len(times)} cuts at threshold {args.scene_threshold}")
    return sorted(set(round(t, 2) for t in times))


def stride_frames(video: str, out_dir: Path, stride: float, max_height: int, limit: int = 0) -> list:
    """Single ffmpeg pass: (t, path) for every stride'th second, as JPEG (a PNG grid over an
    hour is gigabytes; JPEG at quality 4 is still perfectly OCR-able)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [media_tool(), "-hide_banner", "-y", "-i", video,
           "-vf", f"fps=1/{stride},{scale_vf(max_height)}", "-q:v", "4"]
    if limit:
        cmd += ["-frames:v", str(limit)]
    cmd += [str(out_dir / "s%05d.jpg")]
    t0 = time.time()
    rc, _, err = run(cmd, timeout=5400)
    got = sorted(out_dir.glob("s*.jpg"))
    if rc != 0 and not got:
        log(f"stride sampling failed: {err[-200:]}")
        return []
    log(f"stride grid: {len(got)} frames every {stride:g}s in {time.time() - t0:.0f}s")
    return [(round(i * stride, 2), p) for i, p in enumerate(got)]


def grab_frame(video: str, t: float, out: Path, max_height: int) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    rc, _, _ = run([media_tool(), "-hide_banner", "-y", "-ss", f"{t:.2f}", "-i", video,
                    "-frames:v", "1", "-vf", scale_vf(max_height), "-q:v", "3", out], timeout=180)
    return rc == 0 and out.is_file() and out.stat().st_size > 2000


def dhash(path: Path, size: int = 8) -> int:
    """Perceptual difference hash: a screen that merely scrolled a few pixels scores 0-2 bits;
    a real state change (dialog opened, tab switched) scores far more."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            g = im.convert("L").resize((size + 1, size), Image.BOX)
            px = list(g.getdata())
        bits = 0
        for row in range(size):
            for col in range(size):
                a = px[row * (size + 1) + col]
                b = px[row * (size + 1) + col + 1]
                bits = (bits << 1) | (1 if a > b else 0)
        return bits
    except Exception:
        return -1


def hamming(a: int, b: int) -> int:
    if a < 0 or b < 0:
        return 99
    return bin(a ^ b).count("1")


def ocr_frame(path: Path) -> dict:
    """Read the words that are on screen. The label a narrator calls 'the Export button' is
    usually visible in the frame, and OCR is what lets a text-only engine name it correctly."""
    try:
        import pytesseract
        from PIL import Image
        if os.environ.get("TESSERACT_CMD"):
            pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
        elif not shutil.which("tesseract") and os.path.isfile(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        with Image.open(path) as im:
            txt = pytesseract.image_to_string(im, config="--psm 6")
        return clean_ocr(txt)
    except Exception:
        return {"text": "", "words": []}


def clean_ocr(txt: str) -> dict:
    raw = re.sub(r"[ \t]+", " ", txt or "")
    words, seen = [], set()
    for w in raw.split("\n"):
        for tok in w.strip().split():
            tok = tok.strip(".,:;!\"'`~^*()[]{}<>|/\\_?")
            if len(tok) < 2 or tok.isdigit() or tok.lower() in seen:
                continue
            # keep plausible UI labels; tesseract turns antialiased chrome into glyph soup
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 &.'/+()-]*", tok):
                continue
            if sum(1 for c in tok if not c.isalnum()) > len(tok) // 3:
                continue
            if not re.search(r"[A-Za-z]", tok):
                continue
            seen.add(tok.lower())
            words.append(tok)
    return {"text": re.sub(r"\s+", " ", raw).strip()[:1200], "words": words[:OCR_WORDS]}


def frames_stage(url: str, work: Path, args, meta: dict) -> list:
    """Sample, cut, dedupe and OCR -> the distinct screen states of the whole video."""
    fjson = work / "frames.json"
    if fjson.is_file() and not args.redo and not args.reframes:
        frames = read_json(fjson, []) or []
        if frames:
            log(f"frames reused from checkpoint: {len(frames)} distinct screen states")
            return ocr_pass(frames, work, args)
    frames = []
    if args.no_video:
        log("--no-video: skipping keyframes; the guide will be narration-only")
        write_json(fjson, frames)
        return frames
    if free_gb() < MIN_FREE_GB:
        log(f"only {free_gb():.1f} GB free -- skipping frame extraction (transcript still works)")
        meta["frames_skipped"] = f"low disk ({free_gb():.1f} GB)"
        write_json(fjson, frames)
        return frames
    video = find_video(work) if not args.redo else ""
    if not video:
        video = download_video(url, work, args)
    if not video:
        write_json(fjson, frames)
        return frames
    raw_dir = work / "frames_raw"
    times = []
    stride_hits = stride_frames(video, raw_dir, args.stride, args.max_height, args.max_stride)
    times = [(t, p, "stride") for t, p in stride_hits]
    if args.scene_threshold > 0:
        cuts = scene_times(video, args)
        near = [t for t, _, _ in times]
        extra = []
        for t in cuts:
            if near and min(abs(t - n) for n in near) <= args.stride * 1.3:
                continue
            if len(extra) >= args.max_scene_frames:
                log(f"scene cuts capped at {args.max_scene_frames} (--max-scene-frames to raise)")
                break
            out = raw_dir / f"c{t:08.2f}.jpg"
            if out.is_file() or grab_frame(video, t, out, args.max_height):
                extra.append((round(t, 2), out, "scene"))
        times += extra
    times.sort(key=lambda x: x[0])
    log(f"captured {len(times)} candidate frames ({sum(1 for x in times if x[2] == 'scene')} scene cuts)")
    frames = dedupe_frames(times, args)
    log(f"after perceptual dedupe: {len(frames)} distinct screen states kept")
    frames = ocr_pass(frames, work, args)
    write_json(fjson, frames)
    if not args.keep_video:
        for junk in (work / "video", work / "audio", work / "captions", work / "asr"):
            shutil.rmtree(junk, ignore_errors=True)
        log("source media deleted (keep with --keep-video); keyframes retained")
    return frames


def dedupe_frames(times: list, args) -> list:
    """Keep only the frames that show a genuinely different screen. A tutorial often sits on one
    window for minutes: those repetitions would otherwise each cost a model call."""
    kept, last, last_t = [], -1, -1e9
    for t, path, kind in times:
        h = dhash(path)
        if kept:
            dist = hamming(h, last)
            same_screen = dist < args.dhash_keep
            near_dup = (t - last_t) < args.min_state_seconds and dist < args.dhash_keep * 3
            if same_screen or near_dup:
                try:
                    path.unlink()           # this is the same screen we already keep
                except OSError:
                    pass
                continue
        kept.append({"t": round(t, 2), "path": str(path), "dhash": h, "kind": kind})
        last, last_t = h, t
    for i, f in enumerate(kept):
        f["idx"] = i
    return kept


def ocr_pass(frames: list, work: Path, args) -> list:
    if not frames or args.no_ocr:
        return frames
    todo = [f for f in frames if "ocr_words" not in f]
    if not todo:
        return frames
    t0 = time.time()
    workers = max(1, min(4, (os.cpu_count() or 4) - 1))
    log(f"OCR on {len(todo)} keyframes with {workers} workers")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for f, res in zip(todo, pool.map(lambda x: ocr_frame(Path(x["path"])), todo)):
            f["ocr_text"] = res["text"]
            f["ocr_words"] = res["words"]
    log(f"OCR done in {time.time() - t0:.0f}s")
    write_json(work / "frames.json", frames)
    return frames


# ---------------------------------------------------------------------------
# Stage 4: align narration to screen states -> chunks (the unit the model reads)
# ---------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def chunk_stage(work: Path, args, cues: list, frames: list, meta: dict) -> list:
    cpath = work / "chunks.json"
    if cpath.is_file() and not args.redo and not args.rechunk:
        chunks = read_json(cpath, []) or []
        if chunks:
            log(f"alignment reused: {len(chunks)} chunks")
            return chunks
    chunks = []
    if frames:
        for i, fr in enumerate(frames):
            t0 = fr["t"]
            t1 = frames[i + 1]["t"] if i + 1 < len(frames) else (t0 + args.stride)
            nar = [c["text"] for c in cues if t0 <= ((c["start"] + c["end"]) / 2.0) < t1]
            chunks.extend(make_chunks(work, fr, t0, t1, " ".join(nar).strip(), args))
    else:
        # no keyframes at all: fall back to narration windows so the run still yields a guide
        step = max(10.0, args.stride * 5)
        t = 0.0
        total = meta.get("duration", 0) or (cues[-1]["end"] if cues else 0)
        while t < total:
            nar = [c["text"] for c in cues if t <= ((c["start"] + c["end"]) / 2.0) < t + step]
            if " ".join(nar).strip():
                chunks.extend(make_chunks(work, {"idx": len(chunks), "t": t, "path": ""}, t, t + step,
                                          " ".join(nar).strip(), args))
            t += step
    for n, ch in enumerate(chunks):
        ch["i"] = n
    write_json(cpath, chunks)
    spoken = sum(1 for c in chunks if c["narration"])
    log(f"aligned {len(chunks)} chunks ({spoken} with narration, {len(chunks) - spoken} silent state changes)")
    return chunks


def make_chunks(work: Path, fr: dict, t0: float, t1: float, narration: str, args) -> list:
    """A screen state can carry minutes of talk. Split it by sentences so the model is never
    asked to compress detail it would then drop -- no narration is ever truncated away."""
    if not narration and (fr.get("kind") != "scene") and not args.keep_silent:
        return []
    pieces, cur, curlen = [], [], 0
    for sent in (s.strip() for s in _SENT_SPLIT.split(narration) if s.strip()):
        if curlen + len(sent) > NARRATION_CAP and cur:
            pieces.append(" ".join(cur))
            cur, curlen = [], 0
        cur.append(sent)
        curlen += len(sent) + 1
    if cur:
        pieces.append(" ".join(cur))
    if not pieces:
        pieces = [""]
    span = (t1 - t0) / len(pieces)
    out = []
    for k, piece in enumerate(pieces):
        out.append({"t0": round(t0 + k * span, 2), "t1": round(t0 + (k + 1) * span, 2),
                    "frame": fr.get("path", ""), "frame_idx": fr.get("idx", -1),
                    "kind": fr.get("kind", "stride"), "narration": piece,
                    "ocr": (fr.get("ocr_words") or [])[:OCR_WORDS],
                    "ocr_text": (fr.get("ocr_text") or "")[:600]})
    return out


# ---------------------------------------------------------------------------
# Stage 5: extraction -- keyframe + narration  ->  candidate GUI steps
# ---------------------------------------------------------------------------

SCHEMA_HINT = ('{"segment":"continue|new_task","task":"short name of the task being shown now",'
               '"steps":[{"action":"click|right_click|double_click|hover|drag_and_drop|type|key|scroll|wait|observe",'
               '"target_text":"the exact visible label of the widget, or empty",'
               '"element_type":"Button|MenuItem|Tab|Edit|CheckBox|RadioButton|Dropdown|ListItem|Icon|Canvas|Unknown",'
               '"value":"text to type or the key combo, else empty",'
               '"where":"region/menu/panel it happens in, else empty",'
               '"expected_state":"what is visibly different on screen after it",'
               '"confidence":0.0}]}')

SYSTEM_PROMPT = ("You watch one screen of a screen-recorded software tutorial and report the GUI actions "
                 "the narrator performs on that screen. You reply with JSON only, no prose, no markdown. "
                 "Only list actions that actually happen in this moment. Never invent a widget that is "
                 "neither visible in the picture nor named by the narrator. Use an empty steps list when "
                 "nothing is done (intro, talking, loading).")


def extract_json(text: str):
    """Models wrap JSON in prose or emit it twice-encoded. Pull out the first balanced object."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t).strip("` \n")
    for _ in range(3):
        if isinstance(t, str):
            start = t.find("{")
            if start < 0:
                return None
            depth, in_str, esc = 0, False, False
            for i in range(start, len(t)):
                ch = t[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                elif ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(t[start:i + 1])
                        except Exception:
                            return None
            return None
        elif isinstance(t, dict):
            return t
        else:
            return None
    return None


def _b64_image(path: str, budget: int = 1600) -> str:
    """Encode the keyframe for the vision endpoint within an image-token budget
    (Qwen costs about (w/32)*(h/32) tokens per picture)."""
    try:
        import base64
        import io
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGB")
            w, h = im.size
            tok = (w / 32.0) * (h / 32.0)
            if tok > budget:
                s = (budget / tok) ** 0.5
                im = im.resize((max(32, int(w * s)), max(32, int(h * s))), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


def build_prompt(chunk: dict, app: str, prev: str, ocr_cap: int = OCR_WORDS) -> str:
    """`ocr_cap` decides how much of the on-screen text to quote: a text-only engine needs the
    whole reading (it is blind), an engine holding the picture gets a short hint, because
    tesseract mangles antialiased UI text and the model should trust its own eyes over it."""
    ocr = ", ".join((chunk.get("ocr") or [])[:max(0, ocr_cap)])
    screen_line = (f"TEXT VISIBLE ON SCREEN (raw OCR, may contain misreadings): {ocr[:1400] or '(none read)'}\n"
                   if ocr_cap > 0 else "")
    return (
        f"APP: {app}\n"
        f"TIME ON SCREEN: {hhmmss(chunk['t0'])} to {hhmmss(chunk['t1'])}\n"
        f"NARRATOR (this screen): \"{chunk['narration'][:NARRATION_CAP] or '(silent)'}\"\n"
        + screen_line
        + f"PREVIOUS ACTION: {prev or '(none yet)'}\n\n"
        "Convert what happens here into GUI automation steps, oldest first. Rules:\n"
        " * one step per physical action (a click, a typed value, a key combo, a scroll);\n"
        " * target_text must be the literal label to look for on screen, exactly as spelled;\n"
        " * for typing, put the literal text in value and the field's label in target_text;\n"
        " * for shortcuts put the combo in value, e.g. Ctrl+S, and leave target_text empty;\n"
        " * expected_state must be something a checker could see change;\n"
        " * set segment to new_task when the narrator starts a genuinely different task;\n"
        f" * output JSON exactly like: {SCHEMA_HINT}\n"
    )


def call_vlm(prompt: str, image_b64: str, session) -> tuple:
    content = [{"type": "text", "text": prompt}]
    if image_b64:
        content.append({"type": "image_url", "image_url": {"url": image_b64}})
    body = {"messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": content}],
            "temperature": 0, "max_tokens": CHUNK_TOKENS, "stream": False}
    if image_b64:
        body["response_format"] = {"type": "json_object"}
    try:
        r = session.post(VISION_URL + "/v1/chat/completions", json=body, timeout=CHAT_TIMEOUT)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {r.text[:160]}"
        msg = (r.json().get("choices") or [{}])[0].get("message", {})
        txt = msg.get("content") or (msg.get("reasoning_content") or "")
        return txt, ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:160]}"


def call_ollama(prompt: str, session) -> tuple:
    body = {"model": OLLAMA_PICK["model"], "prompt": SYSTEM_PROMPT + "\n\n" + prompt, "format": "json",
            "stream": False, "options": {"temperature": 0, "num_predict": CHUNK_TOKENS}}
    try:
        r = session.post(OLLAMA_URL + "/api/generate", json=body, timeout=CHAT_TIMEOUT)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {r.text[:160]}"
        resp = r.json().get("response", "")
        try:                                    # Ollama can hand back an encoded-inside-encoded string
            inner = json.loads(resp)
            if isinstance(inner, str):
                resp = inner
        except Exception:
            pass
        return resp if isinstance(resp, str) else json.dumps(resp), ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:160]}"


# ---- no-model fallback: read the verbs out of the narration directly ----

OBJ_STOP = re.compile(r"\b(?:in|into|on|at|to|that|which|and|then|for|from|with|so|now|here|this|"
                      r"it|a|an|the|our|your|my)\b", re.I)
TYPE_RE = re.compile(r"\b(?:type|types|typed|enter|enters|input|inputs|write|writes|paste|pastes)\b"
                     r"\s+(?:in|into|on|to)?\s*[\"']?([^\"'\n]{1,60})[\"']?\s+"
                     r"(?:in|into|on|to|inside|within)\s+(?:the\s+)?([A-Za-z0-9 +>\-_/&']{2,60})", re.I)
FIELD_TYPE_RE = re.compile(r"\b(?:type|enter|write|input|paste)\b[^.]{0,40}?[\"']([^\"']{1,60})[\"']", re.I)
KEY_MOD = r"(?:ctrl|alt|shift|win|windows|cmd|option|super)"
KEY_TOKEN = rf"(?:{KEY_MOD}|f\d{{1,2}}|[a-z][a-z0-9_]*|[0-9])"
KEY_RE = re.compile(rf"\b(?:press(?:es|ed|ing)?|hit(?:s|ting)?|use(?:s|d)?|shortcut)?\s*"
                    rf"((?:{KEY_TOKEN})(?:\s*[+]\s*{KEY_TOKEN})+)", re.I)
SINGLE_KEY_RE = re.compile(r"\b(?:press|hit)\s+(?:the\s+)?[\"']?"
                           r"(enter|return|tab|esc|escape|delete|backspace|space|page\s*up|page\s*down|"
                           r"arrow\s*up|arrow\s*down|f\d{1,2}|ctrl|alt|shift|win)[\"']?", re.I)
CLICK_RE = re.compile(r"\b(?:click(?:s|ed|ing)?|tap(?:s|ped|ping)?|select(?:s|ed|ing)?|choose(?:s|d)?|"
                      r"pick(?:s|ed)?|press(?:es|ed)?|hit(?:s|ting)?|open(?:s|ed|ing)?)\b"
                      r"\s*(?:on)?\s*(?:the\s+|a\s+|an\s+|your\s+|our\s+)?"
                      r"[\"']?([^\"'\n.]{2,70})[\"']?", re.I)
PATH_RE = re.compile(r"([A-Za-z][A-Za-z0-9 &_\-']{1,30})\s*(?:>|→|->|>>)\s*([A-Za-z][A-Za-z0-9 &_\-']{1,30})")
GO_RE = re.compile(r"\b(?:go|navigat(?:e|ing)|head|switch|move|jump)\b[^.]{0,30}?"
                   r"(?:to|into)\s+(?:the\s+)?[\"']?([A-Za-z][^\"'\n.]{1,60})", re.I)
SCROLL_RE = re.compile(r"\bscroll(?:s|ed|ing)?\b(?:\s+(?:down|up|to|into|in)\s+([^.]{2,60}))?", re.I)
WAIT_RE = re.compile(r"\b(?:wait|loading|give it|let it|it takes|hold on|hang on)\b", re.I)
OBSERVE_RE = re.compile(r"\b(?:you(?:'| a)?ll see|notice|you can see|now you have|this shows|observe)\b", re.I)


LEAD_NOISE = re.compile(r"^(?:then|now|next|first|simply|just|please|you(?:'| a)?|can|will|it|we|i|"
                        r"the|a|an|this|that|our|your|my|on|in|to|click|select|press)\b[ ,]*", re.I)
ADJ_NOISE = re.compile(r"^(?:blue|green|red|grey|gray|white|black|big|small|little|new|same|"
                       r"following|above|below|main|other|entire|whole|exact)\b[ ,]*", re.I)
TRAIL_NOISE = re.compile(r"\s+\b(?:that|which|to|for|and|or|in|on|the|a|an|of|with|is|are)\b.*$", re.I)
TAIL_DANGLE = re.compile(r"[ ,]+\b(?:and|the|to|of|in|on|for|with|a|an)\b[ ,]*$", re.I)


def obj_clean(raw: str) -> str:
    """'click the blue Export button and wait' -> 'Export button'. The name a narrator says is
    what the executor later has to fuzzy-match in the UIA tree, so keep the widget noun and drop
    the clause around it."""
    s = re.sub(r"\s+", " ", str(raw or "")).strip(" .,;:!\"'`*()[]{}<>|/\\")
    if len(s.split()) > 4:
        s = OBJ_STOP.split(s)[0]                      # cut at the first connective in a long phrase
    if len(s.split()) > 3:                            # short names keep their wording ("Text to Speech")
        s = TRAIL_NOISE.sub("", s)
    for _ in range(4):                                # peel leading filler until nothing more comes off
        t = LEAD_NOISE.sub("", s).strip()
        t = ADJ_NOISE.sub("", t).strip()
        t = re.sub(r"^(?:\w+ly)\s+", "", t).strip()
        if t == s or not t:
            break
        s = t
    s = TAIL_DANGLE.sub("", s)
    return s.strip(" .,:;!\"'`*()[]{}<>|/\\")[:60]


def _mk(action, target="", value="", etype="Unknown", where="", expected="", conf=0.35):
    return {"action": action, "target_text": obj_clean(target), "element_type": etype,
            "value": (value or "").strip(), "where": where, "expected_state": expected, "confidence": conf}


def guess_type(phrase: str) -> str:
    p = (phrase or "").lower()
    if "tab" in p:
        return "Tab"
    if "menu" in p or "ribbon" in p:
        return "MenuItem"
    if "checkbox" in p or "check box" in p:
        return "CheckBox"
    if "radio" in p:
        return "RadioButton"
    if "dropdown" in p or "drop-down" in p or "combo" in p:
        return "Dropdown"
    if "field" in p or "search" in p or "textbox" in p or "input" in p or "box" in p:
        return "Edit"
    if "button" in p or "btn" in p or "cta" in p:
        return "Button"
    if "list" in p:
        return "ListItem"
    return "Unknown"


def rules_extract(narration: str) -> dict:
    """Deterministic narration reader. Weaker than a model, but it needs nothing and it
    never fabricates a widget the narrator did not name."""
    steps = []
    for sent in (s.strip() for s in _SENT_SPLIT.split(narration or "") if s.strip()):
        low = sent.lower()
        m = TYPE_RE.search(sent)
        if m:
            steps.append(_mk("type", m.group(2), m.group(1), guess_type(m.group(2)),
                             expected=f"field shows {m.group(1)[:40]}"))
        elif (m := FIELD_TYPE_RE.search(sent)):
            tail = sent[sent.find(m.group(1)) + len(m.group(1)):]
            where = re.search(r"\b(?:in|into|on|to)\s+(?:the\s+)?([^.\n]{2,50})", tail)
            steps.append(_mk("type", where.group(1) if where else "", m.group(1),
                             guess_type(where.group(1) if where else ""),
                             expected=f"field shows {m.group(1)[:40]}"))
        if (m := KEY_RE.search(sent)) or (m := SINGLE_KEY_RE.search(sent)):
            combo = re.sub(r"\s+", "", m.group(1)).replace("windows", "win").replace("cmd", "win")
            steps.append(_mk("key", value=combo, expected=f"{combo} performed"))
        elif (m := PATH_RE.search(sent)):
            for part in (m.group(1), m.group(2)):
                steps.append(_mk("click", part, "", guess_type(part), expected=f"{part} opened"))
        elif (m := CLICK_RE.search(sent)) and "scroll" not in low:
            tgt = m.group(1)
            if len(tgt.split()) > 8:
                tgt = " ".join(tgt.split()[:8])
            etype = guess_type(tgt)
            steps.append(_mk("click", tgt, "", etype, expected=f"{obj_clean(tgt)} responded"))
        elif (m := GO_RE.search(sent)):
            tgt = m.group(1)
            steps.append(_mk("click", tgt, "", guess_type(tgt), expected=f"{obj_clean(tgt)} is now shown"))
        elif (m := SCROLL_RE.search(sent)):
            steps.append(_mk("scroll", m.group(1) or "", "", "Canvas", expected="view moved"))
        elif WAIT_RE.search(low):
            steps.append(_mk("wait", expected="screen settled", conf=0.3))
        elif OBSERVE_RE.search(low):
            steps.append(_mk("observe", expected=sent[:90], conf=0.3))
    return {"segment": "continue", "task": "", "steps": steps}


class Extractor:
    """One engine per run, chosen by what is actually up. Every answer is logged so a step can
    be traced back to the exact prompt and raw model text that produced it."""

    def __init__(self, args, app: str, work: Path):
        self.args = args
        self.app = app
        self.work = work
        self.log_path = work / "model_io.log"
        self.session = None
        self.image_capable = False
        self.engine = "rules"
        self.stats = {"vlm": 0, "ollama": 0, "rules": 0, "vlm_fail": 0, "empty": 0}
        try:
            import requests
            self.session = requests.Session()
        except Exception:
            self.session = None

    def choose(self) -> str:
        want = self.args.engine
        v, o = vision_health(), (self.session and ollama_health()) or {"up": False}
        if want in ("auto", "vlm") and not v.get("up") and self.args.autostart_vision:
            v = vision_autostart(self.args.vision_wait)
        if want in ("auto", "vlm") and v.get("up") and self.session is not None:
            self.engine, self.image_capable = "vlm", True
            return f"vlm ({v.get('model') or 'qwen3-vl'} @ {VISION_URL})"
        if want in ("auto", "ollama") and o.get("up") and self.session is not None:
            self.engine = "ollama"
            OLLAMA_PICK["model"] = o.get("model") or OLLAMA_MODEL
            return f"ollama {OLLAMA_PICK['model']} (text + OCR only, no eyes)"
        if want in ("auto", "vlm", "ollama"):
            log("no local model reachable -- falling back to regex extraction "
                "(fewer steps, no screen reading)")
        self.engine = "rules"
        return "regex rules"

    def audit(self, chunk, prompt, raw, decision):
        line = (f"\n=== chunk {chunk['i']} @ {hhmmss(chunk['t0'])}-{hhmmss(chunk['t1'])} "
                f"engine={self.engine} frame={os.path.basename(chunk.get('frame') or '')} ===\n"
                f"-- prompt --\n{prompt}\n-- raw --\n{raw}\n-- decision --\n{decision}\n")
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    def run(self, chunk: dict, prev: str) -> dict:
        img = _b64_image(chunk["frame"]) if (self.engine == "vlm" and chunk.get("frame")) else ""
        prompt = build_prompt(chunk, self.app, prev, ocr_cap=(60 if img else OCR_WORDS))
        raw, err = "", ""
        if self.engine == "vlm":
            raw, err = call_vlm(prompt, img, self.session)
            if err:
                self.stats["vlm_fail"] += 1
                log(f"  chunk {chunk['i']}: vlm error {err[:90]}; using regex for this chunk")
        elif self.engine == "ollama":
            raw, err = call_ollama(prompt, self.session)
            if err:
                log(f"  chunk {chunk['i']}: ollama error {err[:90]}")
        obj = extract_json(raw) if raw else None
        if obj is None:
            if self.engine != "rules":
                fallback = rules_extract(chunk["narration"])
                self.stats["rules"] += 1
                self.audit(chunk, prompt, raw or err, json.dumps(fallback, ensure_ascii=False)[:800])
                fallback["_engine"] = "rules"
                fallback["_why"] = "model down or returned no JSON"
                return fallback
            self.stats["rules"] += 1
            res = rules_extract(chunk["narration"])
            self.audit(chunk, "(regex)", "", json.dumps(res)[:800])
            res["_engine"] = "rules"
            return res
        self.stats[self.engine] += 1
        self.audit(chunk, prompt, raw, json.dumps(obj, ensure_ascii=False)[:1200])
        obj["_engine"] = self.engine
        return obj


# ---------------------------------------------------------------------------
# Normalisation: model vocabulary -> the executor's trajectory schema
# ---------------------------------------------------------------------------

def normalise_steps(raw: dict, chunk: dict, app: str, seq0: int) -> list:
    engine = str(raw.get("_engine") or raw.get("engine") or "vlm")
    out = []
    steps = raw.get("steps")
    if isinstance(steps, dict):
        steps = [steps]
    for st in (steps or []):
        if not isinstance(st, dict):
            continue
        act = str(st.get("action") or st.get("verb") or "").strip().lower().replace(" ", "_")
        atype, executable = ACTION_MAP.get(act, ("NONE", False))
        if atype == "NONE" and act:
            atype, executable = ACTION_MAP.get(act.split("_")[0], ("NONE", False))
        target = obj_clean(st.get("target_text") or st.get("target") or st.get("label") or st.get("element_name"))
        value = str(st.get("value") or st.get("text") or "").strip()
        expected = str(st.get("expected_state") or st.get("expected") or st.get("state_change") or "").strip()
        if atype == "TYPE_TEXT" and not value and target and looks_like_payload(target):
            value, target = target, ""
        if atype == "KEY_COMBINATION" and not value:
            value, target = target, ""
        if atype in ("CLICK", "RIGHT_CLICK", "DOUBLE_CLICK", "HOVER", "DRAG_AND_DROP") and not target:
            continue                                     # a click on nothing is noise, drop it honestly
        etype = str(st.get("element_type") or guess_type(target)).strip()[:24] or "Unknown"
        if atype in ("DRAG_AND_DROP", "CONTINUOUS_DRAG"):
            executable = False     # a video cannot tell us the waypoints the actuator needs
        seq = seq0 + len(out)
        instruction = chunk["narration"][:220] or f"{atype.lower()} {target}".strip()
        step = {
            "step_id": seq,
            "ui_target": {"element_name": target, "element_type": etype, "automation_id": "",
                          "hierarchical_path": st.get("where") or "", "bounding_box": [0, 0, 0, 0],
                          "visual_description": (st.get("where") or "")[:120]},
            "virtual_mouse_action": {"action_type": atype},
            "low_level_instruction": instruction,
            "expected_state_change": expected or f"{target or atype.lower()} state changed",
            "provenance": {"engine": engine, "confidence": clamp_conf(st.get("confidence")),
                           "t0": chunk["t0"], "t1": chunk["t1"], "kind": chunk.get("kind", ""),
                           "frame": rel_frame(chunk.get("frame", "")),
                           "narration": chunk["narration"][:300], "executable": executable},
        }
        if atype == "TYPE_TEXT":
            step["virtual_mouse_action"]["text_payload"] = value
        elif atype == "KEY_COMBINATION":
            # live_trajectory_executor builds the chord from modifiers + "key" (not text_payload)
            mods, key = split_combo(value or target)
            step["virtual_mouse_action"]["modifiers"] = mods
            step["virtual_mouse_action"]["key"] = key
            if not key:
                continue
        out.append(step)
    return out


def looks_like_payload(text: str) -> bool:
    return bool(text) and (len(text.split()) > 3 or any(c in text for c in " @/\\.-_"))


def clamp_conf(val) -> float:
    try:
        return round(max(0.0, min(1.0, float(val))), 2)
    except Exception:
        return 0.5


def split_combo(value: str) -> tuple:
    norm = {"control": "ctrl", "windows": "win", "cmd": "win", "super": "win", "option": "alt"}
    parts = [norm.get(p, p) for p in re.split(r"[+\-_\s]+", str(value or "").lower()) if p.strip()]
    mods, seen = [], set()
    for p in parts[:-1]:
        if p in ("ctrl", "alt", "shift", "win") and p not in seen:
            seen.add(p)
            mods.append(p)
    key = parts[-1] if parts else ""
    return mods, key


# ---------------------------------------------------------------------------
# Stage 6: extract over all chunks (resumable) -> steps.jsonl
# ---------------------------------------------------------------------------

def extract_stage(args, work: Path, chunks: list, app: str) -> list:
    spath = work / "steps.jsonl"
    if args.no_extract:
        log(("--reassemble: reusing the extracted chunks on disk" if args.reassemble
             else "--no-extract: stopped after alignment; nothing was asked of the model"))
        return [r for r in read_jsonl(spath)]
    done = {r.get("chunk") for r in read_jsonl(spath) if r.get("chunk") is not None}
    todo = [c for c in chunks if c["i"] not in done]
    if args.start_chunk:
        todo = [c for c in todo if c["i"] >= args.start_chunk]
        log(f"probing from chunk {args.start_chunk} onward (chunk numbers follow the alignment)")
    if args.pilot and not args.full:
        todo = todo[:args.pilot]
        if len(todo) < len([c for c in chunks if c["i"] >= args.start_chunk]):
            log(f"PILOT MODE: only {len(todo)} of {len(chunks)} chunks will be extracted "
                f"(--full for the whole video)")
    if not chunks:
        log("nothing to extract: this video produced no aligned chunks "
            "(no transcript and no keyframes)")
        return []
    if not todo:
        log(f"extraction already complete ({len(done)} of {len(chunks)} chunks on disk)")
        return read_jsonl(spath)
    ex = Extractor(args, app, work)
    log(f"extraction engine: {ex.choose()}")
    t0 = time.time()
    prev = ""
    for n, ch in enumerate(todo, 1):
        raw = ex.run(ch, prev)
        steps = normalise_steps(raw, ch, app, 0)
        row = {"chunk": ch["i"], "t0": ch["t0"], "t1": ch["t1"], "frame": ch.get("frame", ""),
               "narration": ch["narration"], "ocr": (ch.get("ocr") or [])[:40],
               "engine": raw.get("_engine", ex.engine),
               "segment": str(raw.get("segment") or "continue"), "task": str(raw.get("task") or ""),
               "steps": steps, "why": raw.get("_why", "")}
        append_jsonl(spath, row)
        prev = steps[-1]["low_level_instruction"][:90] if steps else prev
        if steps:
            label = " / ".join(f"{s['virtual_mouse_action']['action_type']} "
                               f"{s['ui_target']['element_name'] or s['virtual_mouse_action'].get('text_payload', '')}".strip()
                               for s in steps[:3])
        else:
            label = "(nothing)"
        el = time.time() - t0
        eta = el / n * (len(todo) - n)
        log(f"  [{n}/{len(todo)}] {hhmmss(ch['t0'])} {raw.get('_engine', ex.engine):6s} "
            f"steps={len(steps):2d} eta {hhmmss(eta)} :: {label[:110]}")
    log(f"extraction finished in {hhmmss(time.time() - t0)}")
    return read_jsonl(spath)


# ---------------------------------------------------------------------------
# Stage 7: assemble guides + dataset rows
# ---------------------------------------------------------------------------

def same_action(a: dict, b: dict) -> bool:
    """Two chunks often describe the same click at their boundary; a repeated identical action
    in a row is one action seen twice, not two actions."""
    va, vb = a["virtual_mouse_action"], b["virtual_mouse_action"]
    return (str(va.get("action_type")) == str(vb.get("action_type"))
            and str(a["ui_target"].get("element_name", "")).strip().lower()
            == str(b["ui_target"].get("element_name", "")).strip().lower()
            and str(va.get("text_payload", "")) == str(vb.get("text_payload", "")))


def split_for_tasks(rows: list, max_steps: int, keep_nonexec: bool = False,
                    min_steps: int = 3) -> tuple:
    """An hour-long tutorial is a dozen tasks, not one. Cut where the model says a new task
    starts, where the task name changes, or once a task gets long enough to be a real session.
    A cut is only taken once the current task has `min_steps` steps, otherwise the model's
    habit of announcing "new task" every few seconds shatters the guide into stubs.
    Steps the executor cannot actuate (scroll/wait/observe) are kept in the corpus but left out
    of the guide unless --keep-nonexecutable is given."""
    tasks, cur, cur_name, dropped, deduped = [], [], "", 0, 0

    def flush():
        nonlocal cur, cur_name
        if cur:
            tasks.append((cur_name, cur))
            cur, cur_name = [], ""

    for row in rows:
        rsteps = []
        for st in row.get("steps", []):
            if keep_nonexec or st["provenance"].get("executable", True):
                rsteps.append(st)
            else:
                dropped += 1
        if not rsteps:
            continue
        name = str(row.get("task") or "").strip()
        says_new = str(row.get("segment", "")).lower() in ("new_task", "new", "true")
        renamed = bool(name and cur_name and name.lower() != cur_name.lower())
        if (says_new or renamed) and len(cur) >= min_steps:
            flush()
        cur_name = name or cur_name
        for st in rsteps:
            if cur and same_action(cur[-1][0], st):
                deduped += 1            # the same click seen by two neighbouring chunks
                continue
            cur.append((st, row))
            if len(cur) >= max_steps:
                flush()
    flush()
    return tasks, dropped, deduped


def assign_split(keys: list) -> dict:
    mpath = VIDEO_DIR / "split.json"
    m = read_json(mpath, {}) or {}
    apps = m.get("apps", {})
    for k in keys:
        apps.setdefault(k, {"app_key": k, "split": None})
    ordered = sorted(apps)
    random.Random(SPLIT_SEED).shuffle(ordered)
    n_train = int(round(len(ordered) * TRAIN_RATIO))
    for i, k in enumerate(ordered):
        apps[k]["split"] = "TRAIN" if i < n_train else "EVAL"
    out = {"seed": SPLIT_SEED, "train_ratio": TRAIN_RATIO, "created": now_iso(),
           "counts": {"TRAIN": n_train, "EVAL": len(ordered) - n_train}, "apps": apps}
    write_json(mpath, out)
    return out


def schema_warnings(doc: dict) -> list:
    """Grade the guide with the SAME validator the text corpus uses (decompose_guides.validate),
    so a video-derived guide carries the same honest quality signal as every other file in
    trajectories/. A keypress naming no widget is expected and reported, not hidden."""
    try:
        import decompose_guides as DG
        return list(DG.validate(doc) or [])
    except Exception:
        return []


def task_document(app_key: str, app_name: str, task_name: str, steps: list, meta: dict,
                  url: str, engine: str, split: str, idx: int) -> dict:
    sid = hashlib.sha1(f"{app_key}|{meta['video_id']}|{idx}|{task_name}".encode()).hexdigest()[:12]
    traj = []
    for n, (st, _row) in enumerate(steps, 1):
        s = dict(st)
        s["step_id"] = n
        traj.append(s)
    doc = {
        "app_metadata": {"app_name": app_name, "dataset_split": split, "scan_prerequisites_met": False},
        "target_kind": "gui",
        "high_level_task": task_name or f"{app_name}: {meta.get('title', '')[:80]}",
        "prerequisite_state": "App is open at the state the tutorial video starts from",
        "total_steps": len(traj),
        "trajectory": traj,
        "_meta": {
            "source": "video_harvest", "generator": engine, "produced": now_iso(),
            "source_app": app_name, "app_key": app_key, "dataset_split": split,
            "video_id": meta["video_id"], "video_url": url, "video_title": meta.get("title", ""),
            "video_duration": meta.get("duration", 0), "channel": meta.get("channel", ""),
            "transcript_source": meta.get("transcript_source", ""),
            "time_range": [steps[0][1]["t0"], steps[-1][1]["t1"]] if steps else [0, 0],
            "task_index": idx, "guide_id": sid, "verified": False,
            "note": "candidate guide from a tutorial video; prove each step with the live "
                    "executor + UIA oracle before trusting it",
            "schema_warnings": [],
        },
    }
    doc["_meta"]["schema_warnings"] = schema_warnings(doc)
    return doc


def assemble_stage(args, work: Path, meta: dict, cues: list, frames: list, chunks: list,
                   rows: list, app_name: str) -> dict:
    app_key = slugify(app_name)
    sp = assign_split([app_key])
    split = sp["apps"].get(app_key, {}).get("split", "TRAIN")
    steps_all = [(st, row) for row in rows for st in row.get("steps", [])]
    engines = sorted({r.get("engine", "?") for r in rows}) or ["none"]
    marker = work / "assembled.json"
    fingerprint = hashlib.sha1(json.dumps([r.get("chunk") for r in rows],
                                          sort_keys=True).encode()
                               + json.dumps([[s["virtual_mouse_action"]["action_type"],
                                              s["ui_target"]["element_name"],
                                              s["virtual_mouse_action"].get("text_payload", "")]
                                             for r in rows for s in r.get("steps", [])]).encode()
                               ).hexdigest()[:16]
    prev = read_json(marker, {}) or {}
    if prev.get("fingerprint") == fingerprint and not args.redo and not args.reassemble:
        log(f"dataset already assembled for this video ({prev.get('steps', 0)} steps); "
            f"nothing rewritten (use --redo to force)")
        return prev.get("record", {})
    if prev.get("guides"):
        purge_previous(prev, app_key, meta["video_id"])
    tasks, dropped, deduped = split_for_tasks(rows, args.max_steps_per_task, args.keep_nonexecutable,
                                              args.min_steps_per_task)
    in_guides = sum(len(t[1]) for t in tasks)
    written, md = [], []
    md.append(f"# {app_name} -- tutorial walkthrough\n")
    md.append(f"Source: {meta.get('url')}\nTitle: {meta.get('title')}  "
              f"Duration: {hhmmss(meta.get('duration', 0))}  "
              f"Transcript: {meta.get('transcript_source') or 'none'}\n")
    md.append(f"Keyframes kept: {len(frames)} / chunks aligned: {len(chunks)} / "
              f"chunks extracted: {len(rows)} / steps: {len(steps_all)} / engines: {', '.join(engines)}\n")
    if dropped:
        md.append(f"\n> {dropped} step(s) were held out of the executor guides because the current "
                  f"actuator has no such action (scroll / wait / observe). They stay in the corpus.\n")
    if deduped:
        md.append(f"> {deduped} repeated action(s) at chunk boundaries were merged into one.\n")
    if args.no_video or not frames:
        md.append("\n> No keyframes were available for this run: steps come from narration alone.\n")
    for i, (tname, tsteps) in enumerate(tasks):
        if not tsteps:
            continue
        doc = task_document(app_key, app_name, tname, tsteps, meta, meta.get("url", ""),
                            "+".join(engines), split, i)
        out = TRAJ_DIR / split / app_key / f"{app_key}__{doc['_meta']['guide_id']}.json"
        write_json(out, doc)
        written.append({"path": str(out), "task": doc["high_level_task"], "steps": doc["total_steps"]})
        md.append(f"\n## Task {i + 1}. {doc['high_level_task']}  ({doc['total_steps']} steps, "
                  f"{hhmmss(doc['_meta']['time_range'][0])} into the video)\n")
        for n, (st, row) in enumerate(tsteps, 1):
            va = st["virtual_mouse_action"]
            tgt = st["ui_target"]["element_name"]
            pay = va.get("text_payload", "")
            verb = va["action_type"].lower().replace("_", " ")
            body = f"{verb} {('\"' + tgt + '\"') if tgt else ''}{(' with ' + repr(pay)) if pay else ''}"
            mods = "+".join(va.get("modifiers") or [])
            if va["action_type"] == "KEY_COMBINATION" and mods:
                body = f"press {mods}+{pay}"
            md.append(f"  {n}. {body.strip()} -- {st['expected_state_change']} "
                      f"[{st['provenance']['engine']} {st['provenance']['confidence']:.2f} "
                      f"@ {hhmmss(st['provenance']['t0'])}]")
        feed_train(doc, out)
    write_md(work / "guide.md", md)
    corpus = VIDEO_DIR / "corpus" / f"{meta['video_id']}.jsonl"
    corpus.parent.mkdir(parents=True, exist_ok=True)
    with open(corpus, "w", encoding="utf-8") as fh:      # per video, so a re-run never duplicates rows
        for row in rows:
            for st in row.get("steps", []):
                fh.write(json.dumps({
                    "video_id": meta["video_id"], "app_key": app_key, "chunk": row["chunk"],
                    "t": st["provenance"]["t0"], "frame": st["provenance"]["frame"],
                    "narration": row.get("narration", "")[:300], "engine": row.get("engine"),
                    "action": st["virtual_mouse_action"]["action_type"],
                    "target": st["ui_target"]["element_name"],
                    "value": st["virtual_mouse_action"].get("text_payload", ""),
                    "expected_state": st["expected_state_change"],
                    "confidence": st["provenance"]["confidence"],
                    "ocr_words": (row.get("ocr") or [])[:40],
                    "executable": st["provenance"]["executable"]}, ensure_ascii=False) + "\n")
    rec = {"video_id": meta["video_id"], "url": meta.get("url", ""), "app": app_name, "app_key": app_key,
           "title": meta.get("title", ""), "duration": meta.get("duration", 0),
           "transcript_source": meta.get("transcript_source", ""), "transcript_words": words_of(cues),
           "frames_kept": len(frames), "chunks_aligned": len(chunks), "chunks_extracted": len(rows),
           "steps": in_guides, "steps_total": len(steps_all), "non_executable": dropped,
           "merged_duplicates": deduped,
           "tasks": len(written), "engines": engines, "split": split,
           "guides": [w["path"] for w in written], "corpus": str(corpus), "produced": now_iso(),
           "status": "ok" if steps_all else ("no_steps" if rows else "no_chunks")}
    merge_jsonl_row(VIDEO_DIR / "dataset.jsonl", "video_id", rec)
    update_index(rec, args)
    write_json(marker, {"fingerprint": fingerprint, "steps": in_guides,
                        "guides": [w["path"] for w in written], "video_id": meta["video_id"],
                        "record": rec, "at": now_iso()})
    log(f"assembled {in_guides} executor-ready step(s) of {len(steps_all)} extracted into "
        f"{len(written)} task guide(s) -> {TRAJ_DIR / split / app_key}"
        + (f" ({dropped} non-actuable step(s) kept in the corpus only)" if dropped else ""))
    return rec


def purge_previous(prev: dict, app_key: str, video_id: str) -> None:
    """A re-run replaces its own guides and its own training rows -- it never leaves the old
    version of the same video mixed into the corpus."""
    for p in prev.get("guides", []):
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        (VIDEO_DIR / "corpus" / f"{video_id}.jsonl").unlink(missing_ok=True)
    except OSError:
        pass
    if not TRAIN_SAMPLES.is_file():
        return
    tmp = TRAIN_SAMPLES.with_suffix(".tmp")
    kept = dropped = 0
    try:
        with open(TRAIN_SAMPLES, "r", encoding="utf-8") as src, open(tmp, "w", encoding="utf-8") as dst:
            for line in src:
                if not line.strip():
                    continue
                mark = prev.get("video_id") or video_id
                if '"source": "video_harvest"' in line and f'"{mark}"' in line:
                    dropped += 1
                    continue
                dst.write(line)
                kept += 1
        tmp.replace(TRAIN_SAMPLES)
        if dropped:
            log(f"removed {dropped} stale training sample(s) from this video before re-adding "
                f"({kept} kept)")
    except OSError as exc:
        log(f"could not refresh {TRAIN_SAMPLES.name}: {type(exc).__name__} (samples left untouched)")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def write_md(path: Path, lines: list) -> None:
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        log(f"could not write {path.name}: {type(exc).__name__}")


def merge_jsonl_row(path: Path, key: str, row: dict) -> None:
    rows = {r.get(key): r for r in read_jsonl(path) if isinstance(r, dict)}
    rows[row[key]] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows.values():
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def feed_train(doc: dict, guide_path: Path) -> None:
    """Hand the guide to the SAME sampler the text corpus uses, so video-derived steps join
    brain/train_samples.jsonl in the identical shape (and inherit its grounded-only filter)."""
    try:
        import phase1_training_dataset as P1
    except Exception:
        return
    try:
        with open(guide_path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
    except Exception:
        loaded = doc
    n = 0
    for st in loaded.get("trajectory", []):
        try:
            s = P1.sample_from_step(loaded["_meta"]["app_key"], loaded, st, require_grounding=True)
        except Exception:
            s = None
        if s:
            s["source"] = "video_harvest"
            s["video_id"] = loaded.get("_meta", {}).get("video_id", "")
            s["split"] = loaded.get("_meta", {}).get("dataset_split", "TRAIN")
            append_jsonl(TRAIN_SAMPLES, s)
            n += 1
    if n:
        log(f"  {n} training sample(s) appended to {TRAIN_SAMPLES}")


def update_index(rec: dict, args) -> None:
    path = VIDEO_DIR / "index.csv"
    cols = ["video_id", "app", "title", "duration", "transcript_source", "frames_kept",
            "chunks_aligned", "chunks_extracted", "steps", "steps_total", "non_executable",
            "merged_duplicates", "tasks", "engines", "split", "status", "produced"]
    rows = {}
    if path.is_file():
        with open(path, "r", encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                rows[r.get("video_id", "")] = r
    flat = {k: (", ".join(rec[k]) if isinstance(rec.get(k), list) else rec.get(k, "")) for k in cols}
    rows[rec["video_id"]] = flat
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows.values():
            w.writerow({k: r.get(k, "") for k in cols})


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def harvest_one(url: str, app_name: str, args) -> dict:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    meta = probe(url, args)
    if meta.get("playlist"):
        entries = meta.get("entries") or []
        if not args.playlist:
            log("that URL is a playlist; using only the first video (pass --playlist for all of them)")
            entries = entries[:1]
        results = []
        for e in entries:
            u = e.get("webpage_url") or f"https://www.youtube.com/watch?v={e.get('id')}"
            results.append(harvest_one(u, app_name, args))
        return {"video_id": "playlist", "steps": sum(r.get("steps", 0) for r in results),
                "videos": len(results)}
    work = VIDEO_DIR / meta["video_id"]
    work.mkdir(parents=True, exist_ok=True)
    write_json(work / "meta.json", meta)
    app = app_name or guess_app(meta.get("title", ""))
    log(f"--- {meta['video_id']} :: {app} :: \"{meta.get('title', '')[:80]}\" "
        f"[{hhmmss(meta.get('duration', 0))}] ---")
    if meta.get("duration", 0) > 3000:
        log("this is a long video: each stage takes minutes; progress is checkpointed, so let it run")
    free_space_gate(args, meta)
    cues = transcript_stage(url, work, args, meta)
    frames = frames_stage(url, work, args, meta)
    chunks = chunk_stage(work, args, cues, frames, meta)
    rows = extract_stage(args, work, chunks, app)
    write_json(work / "meta.json", meta)
    return assemble_stage(args, work, meta, cues, frames, chunks, rows, app)


def free_space_gate(args, meta: dict) -> None:
    est = max(1.0, (meta.get("duration", 0) or 0) / 3600.0)
    need = est * (0.6 if args.max_height <= 480 else 1.1)
    if not args.no_video and free_gb() < need + 2:
        log(f"low disk: ~{need:.1f} GB expected for this video, {free_gb():.1f} GB free. "
            f"Frames will be skipped if space runs out (or use --no-video / --max-height 480).")


LEAD_APP = re.compile(r"^(?:how\s+to(?:\s+(?:use|using|make|create|learn|edit|draw|animate))?|"
                      r"how(?:'s)?|what\s+is|learn(?:ing)?|using|use|intro(?:\s+to)?|"
                      r"introduction(?:\s+to)?|complete|getting\s+started(?:\s+with)?|"
                      r"start(?:ing)?\s+with|beginner(?:'?s)?(?:\s+guide|\s+tutorial)?\s+to|"
                      r"guide\s+to|tutorial(?:s)?|course|crash\s+course|full)\b[\s:,\-–]*", re.I)
CUT_WORDS = (r"tutorial(?:s)?|how\s+to.*|full\s+(?:course|tutorial|guide|training|series)|"
             r"complete\s+(?:course|guide|tutorial|training)|course|guide\b.*|"
             r"for\s+beginners|beginners?\b|crash\s+course|walkthrough|"
             r"lessons?|part\s+\d+|in\s+\d{4}|in\s+(?:just\s+)?\d+\s*(?:min|mins|minutes|"
             r"sec|secs|seconds|hour|hours)|\d+\s*(?:min|mins|minutes|hours)\b.*|\d+\s*steps?.*")


def guess_app(title: str) -> str:
    """Derive an app name from a tutorial title when the caller gave no --app. Titles in this
    niche are formulaic ("X Tutorial for Beginners - Complete Course in 2026"), so peel the
    formula off the front and the back and what remains is normally the product name."""
    t = re.sub(r"[^\w +.&\-–:]", " ", str(title or ""))
    t = re.sub(r"\s+", " ", t).strip()
    for _ in range(3):
        peeled = LEAD_APP.sub("", t).strip()
        if not peeled or peeled.lower() == t.lower():
            break
        t = peeled
    t = re.sub(r"\s+(?:" + CUT_WORDS + r").*$", "", t, flags=re.I)
    t = re.sub(r"\s*[:,\-–|(].*$", "", t)                          # cut at the first subtitle dash
    t = re.sub(r"\s+(?:" + CUT_WORDS + r").*$", "", t, flags=re.I)
    t = re.sub(r"\s+\d{4}\s*$", "", t)                             # trailing year
    t = t.strip(" :,-.–|()")
    words = [w for w in t.split() if (len(w) > 1 and not w.isdigit()) or w.isdigit()][:4]
    return " ".join(words).strip() or "app"


def parse_sources(args) -> list:
    src = []
    if args.url:
        src.append((args.url, args.app or ""))
    if args.links:
        p = Path(args.links)
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if p.is_file() else []:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if "::" in ln:
                a, u = ln.split("::", 1)
                src.append((u.strip(), a.strip()))
            elif "\t" in ln:
                a, u = ln.split("\t", 1)
                src.append((u.strip(), a.strip()))
            elif "," in ln and not ln.lower().startswith("http"):
                a, u = ln.split(",", 1)
                src.append((u.strip(), a.strip()))
            else:
                src.append((ln, ""))
        if not p.is_file():
            log(f"links file not found: {p}")
    if args.xlsx:
        src.extend(read_sheet(args))
    out, seen = [], set()
    for u, a in src:
        if u and u not in seen:
            seen.add(u)
            out.append((u, a))
    return out


def read_sheet(args) -> list:
    path = Path(args.xlsx)
    if not path.is_file():
        log(f"sheet not found: {path}")
        return []
    try:
        from openpyxl import load_workbook
    except Exception:
        log("openpyxl is required for --xlsx (pip install openpyxl)")
        return []
    wb = load_workbook(str(path), read_only=True, data_only=True)
    ws = wb[args.sheet] if args.sheet in wb.sheetnames else wb.active
    rows = ws.iter_rows(values_only=True)
    header = [str(c or "").strip() for c in (next(rows) or [])]

    def col(want, guess_words):
        low = [h.lower() for h in header]
        if want and want.strip().lower() in low:
            return low.index(want.strip().lower())
        for w in guess_words:
            for i, h in enumerate(low):
                if w in h:
                    return i
        return -1
    ia = col(args.col_app.lower(), ["app name", "app", "software", "name"])
    iu = col(args.col_url.lower(), ["youtube", "tutorial link", "video", "link", "url"])
    if iu < 0:
        log(f"no YouTube link column in {path.name} (headers: {header[:8]})")
        wb.close()
        return []
    out = [(str(r[iu]).strip(), str(r[ia]).strip() if ia >= 0 and len(r) > ia else "")
           for r in rows if r and len(r) > iu and str(r[iu] or "").strip().lower().startswith("http")]
    wb.close()
    log(f"{path.name}: {len(out)} links")
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="harvest_video_guides.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="YouTube tutorial -> transcript + keyframes + structured GUI step dataset (all local, all free)",
        epilog=("examples:\n"
                "  python harvest_video_guides.py --check\n"
                "  python harvest_video_guides.py https://youtu.be/XXXX --app Blender --pilot 4\n"
                "  python harvest_video_guides.py https://youtu.be/XXXX --app Blender --full --max-height 1080\n"
                "  python harvest_video_guides.py --links links.txt            (App::URL per line)\n"
                "  python harvest_video_guides.py --xlsx master.xlsx --col-url \"YouTube Tutorial Link\"\n"
                "  rerun the same command to resume where a stopped run left off\n"))
    ap.add_argument("url", nargs="?", help="single YouTube URL")
    ap.add_argument("--links", help="text file: one URL per line, optional 'App Name::URL'")
    ap.add_argument("--xlsx", help="workbook with the master sheet")
    ap.add_argument("--sheet", default="", help="sheet name (default: active)")
    ap.add_argument("--col-app", default="App Name")
    ap.add_argument("--col-url", default="YouTube Tutorial Link")
    ap.add_argument("--app", default="", help="app name for a single URL")
    ap.add_argument("--check", action="store_true", help="report the environment and exit")
    ap.add_argument("--full", action="store_true", help="extract every chunk (default is a pilot)")
    ap.add_argument("--pilot", type=int, default=4, help="chunks to extract when not --full (default 4)")
    ap.add_argument("--start-chunk", type=int, default=0,
                    help="skip the first N aligned chunks (quality probe deep inside a long video)")
    ap.add_argument("--engine", default="auto", choices=["auto", "vlm", "ollama", "rules"])
    ap.add_argument("--no-autostart", dest="autostart_vision", action="store_false",
                    help="do not try to launch the :8081 vision server")
    ap.add_argument("--vision-wait", type=float, default=120.0)
    ap.add_argument("--transcribe", default="auto", choices=["auto", "force", "off"],
                    help="whisper policy (auto = only when captions are missing or thin)")
    ap.add_argument("--require-whisper", dest="require_whisper", action="store_true",
                    help="ignore captions, always transcribe locally")
    ap.add_argument("--whisper-model", default=WHISPER_MODEL)
    ap.add_argument("--whisper-segment", type=int, default=SEGMENT_SECONDS,
                    help="checkpoint length in seconds (default 600)")
    ap.add_argument("--max-height", type=int, default=MAX_HEIGHT, help="keyframe height (720 = legible UI text)")
    ap.add_argument("--stride", type=float, default=STRIDE, help="seconds between safety-net frames")
    ap.add_argument("--scene-threshold", type=float, default=SCENE_THRESHOLD, help="0 disables scene cuts")
    ap.add_argument("--scene-probe-fps", type=float, default=2.0)
    ap.add_argument("--scene-probe-width", type=int, default=320)
    ap.add_argument("--max-scene-frames", type=int, default=400)
    ap.add_argument("--max-stride", type=int, default=0, help="cap stride frames (0 = all)")
    ap.add_argument("--dhash-keep", type=int, default=DHASH_KEEP, help="bits of difference to call a new state")
    ap.add_argument("--min-state-seconds", type=float, default=2.0)
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--no-video", action="store_true", help="transcript only, no keyframes")
    ap.add_argument("--no-extract", action="store_true", help="stop after alignment")
    ap.add_argument("--keep-silent", action="store_true", default=True,
                    help="keep scene-change chunks that have no narration (default on)")
    ap.add_argument("--drop-words", action="store_true", help="do not store whisper word timings")
    ap.add_argument("--max-filesize-mb", type=int, default=0)
    ap.add_argument("--max-steps-per-task", type=int, default=35)
    ap.add_argument("--min-steps-per-task", type=int, default=3,
                    help="do not start a new task guide until the current one has this many steps")
    ap.add_argument("--reassemble", action="store_true",
                    help="rebuild guides/dataset from the chunks already on disk (no model calls)")
    ap.add_argument("--keep-nonexecutable", action="store_true",
                    help="also put scroll/wait/observe steps into the executor guides (default: corpus only)")
    ap.add_argument("--keep-video", action="store_true", help="keep the downloaded media (uses GBs)")
    ap.add_argument("--redo", action="store_true", help="ignore checkpoints and redo every stage")
    ap.add_argument("--reframes", action="store_true", help="redo the frame stage only")
    ap.add_argument("--rechunk", action="store_true", help="redo alignment only")
    ap.add_argument("--playlist", action="store_true", help="expand a playlist URL into its videos")
    ap.add_argument("--between", type=float, default=8.0,
                    help="seconds to pause between videos in a batch (rate-limit safety, 0 = none)")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    args.url = args.url or ""
    if args.check:
        return check_env(args)
    if args.full:
        args.pilot = 0
    elif args.pilot is None or args.pilot < 1:
        args.pilot = 4
    if args.reassemble:
        args.no_extract = True          # rebuild guides from what is already on disk, no model calls
    sources = parse_sources(args)
    if not sources:
        print("nothing to do. Give a URL, --links FILE or --xlsx FILE (or --check).")
        return 2
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    log(f"{len(sources)} video(s) queued :: ffmpeg={'yes' if FFMPEG else 'NO'} :: "
        f"engine={args.engine} :: out={VIDEO_DIR}")
    total_steps, ok, bad = 0, 0, 0
    t0 = time.time()
    for n, (url, app_name) in enumerate(sources, 1):
        log(f"[{n}/{len(sources)}] {url[:90]}")
        try:
            rec = harvest_one(url, app_name, args)
            total_steps += rec.get("steps", 0) or 0
            ok += 1
        except KeyboardInterrupt:
            log("interrupted -- progress is checkpointed, re-run the same command to continue")
            return 130
        except Exception as exc:
            bad += 1
            import traceback
            log(f"FAILED {url[:70]}: {type(exc).__name__}: {str(exc)[:200]}")
            traceback.print_exc()
            append_jsonl(VIDEO_DIR / "failures.jsonl",
                         {"url": url, "error": f"{type(exc).__name__}: {str(exc)[:300]}", "at": now_iso()})
        if n < len(sources) and args.between:
            time.sleep(args.between)      # a long batch back-to-back invites YouTube rate limits
    log(f"done: {ok} video(s) ok, {bad} failed, {total_steps} candidate steps harvested "
        f"in {hhmmss(time.time() - t0)}")
    log(f"dataset: {VIDEO_DIR / 'dataset.jsonl'} :: ledger: {VIDEO_DIR / 'index.csv'} :: "
        f"guides: {TRAJ_DIR}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
