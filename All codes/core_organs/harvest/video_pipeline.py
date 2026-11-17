"""
harvest.video_pipeline -- from a tutorial video (or just its transcript) to the pieces a grounded training pair and a RAG entry are made of.

    scene_changes / extract_keyframes   OpenCV: sampled frames, |frame - previous| on a small grey copy; an event is a change big enough (a menu opens, a dialog appears) after a quiet gap. Each event
                                        keeps a pre frame, a settled post frame, and the bounding box of what changed (the delta box: only that region needs scanning).
    action_moments                      the transcript windows where the speaker DOES something (rule-based verbs/chords from rag.procedures), so only those seconds are ever downloaded
    download_section                    yt-dlp section download of one such moment (720p cap) -- explicit, never automatic
    transcribe_audio                    faster-whisper on the CPU (int8): the fallback for videos without captions (VRAM stays free for the vision model)
    som_of_frame                        Set-of-Marks of a STILL: professor.sweeper.scan(image=...), mode quick (classical CV + Tesseract, no model call, no GPU, no live window) -> numbered elements

Nothing here captures the screen or touches a running application.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


# ---- scene changes ------------------------------------------------------------------------------------------------------------------------------------
def changed_region(before: np.ndarray, after: np.ndarray, thresh: int = 25, min_area_frac: float = 0.0005) -> Optional[Tuple[int, int, int, int]]:
    """Bounding box (x, y, w, h) in the pictures' own pixels of what changed between two frames, or None. The delta box: scan only inside it."""
    import cv2
    a = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY) if before.ndim == 3 else before
    b = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY) if after.ndim == 3 else after
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    diff = cv2.absdiff(a, b)
    mask = (diff > thresh).astype(np.uint8)
    if mask.sum() < min_area_frac * mask.size:
        return None
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
    pts = cv2.findNonZero(mask)
    if pts is None:
        return None
    x, y, w, h = cv2.boundingRect(pts)
    return int(x), int(y), int(w), int(h)


def scene_changes(video_path: str, sample_fps: float = 2.0, min_change: float = 0.015, min_gap_s: float = 1.0, settle_s: float = 0.6, max_events: int = 300, thumb: Tuple[int, int] = (192, 108), diff_thresh: int = 25) -> List[Dict[str, Any]]:
    """[{t, frame, change, bbox, settle_frame}] -- `change` is the fraction of the (small, grey) picture that differs from the previous sample; bbox is in full-frame pixels.
    `diff_thresh` (grey levels, default 25 = the old behaviour): a dark theme's panels differ from its background by ~15, so harvest.consolidate asks for less."""
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or thumb[0])
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or thumb[1])
    step = max(1, int(round(fps / sample_fps)))
    sx, sy = w / thumb[0], h / thumb[1]
    events: List[Dict[str, Any]] = []
    prev = None
    last_t = -1e9
    idx = 0
    while len(events) < max_events:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), thumb, interpolation=cv2.INTER_AREA)
            if prev is not None:
                diff = cv2.absdiff(prev, small)
                frac = float((diff > diff_thresh).mean())
                t = idx / fps
                if frac >= min_change and t - last_t >= min_gap_s:
                    bb = changed_region(prev, small, thresh=diff_thresh)
                    events.append({"t": round(t, 3), "frame": idx, "change": round(frac, 4),
                                   "bbox": [int(bb[0] * sx), int(bb[1] * sy), int(bb[2] * sx), int(bb[3] * sy)] if bb else None,
                                   "settle_frame": int(idx + settle_s * fps)})
                    last_t = t
            prev = small
        idx += 1
    cap.release()
    return events


def extract_keyframes(video_path: str, out_dir: str, video_id: str = "", **kw) -> List[Dict[str, Any]]:
    """Save a pre frame (the sample before the change) and a settled post frame for every scene change. Returns the events with relative paths."""
    import cv2
    os.makedirs(out_dir, exist_ok=True)
    events = scene_changes(video_path, **kw)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps / kw.get("sample_fps", 2.0))))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    out = []
    for i, ev in enumerate(events):
        pre_i, post_i = max(0, ev["frame"] - step), min(max(0, total - 1), ev["settle_frame"]) if total else ev["settle_frame"]
        paths = {}
        for tag, fi in (("pre", pre_i), ("post", post_i)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
            ok, frame = cap.read()
            if not ok:
                break
            p = os.path.join(out_dir, f"{video_id or 'v'}_{i:04d}_{tag}.jpg")
            cv2.imwrite(p, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            paths[tag] = p
        if len(paths) == 2:
            out.append(dict(ev, pre=paths["pre"], post=paths["post"], index=i))
    cap.release()
    return out


# ---- the transcript side ---------------------------------------------------------------------------------------------------------------------------
# Verbs that name a deliberate act on the interface. 'use', 'add', 'set', 'run', 'start', 'create'... are ordinary speech ("use this, but it can come in handy", "use a mac"): they do not make a moment.
_UI_VERBS = {"click", "double-click", "double click", "right-click", "right click", "press", "hit", "select", "choose", "drag", "drop", "type", "enter", "hold", "tap", "scroll", "open",
             "go to", "navigate to", "switch to", "toggle", "check", "uncheck", "expand", "collapse", "pick"}
_PRONOUN_TARGETS = {"this", "that", "it", "these", "those", "them", "here", "there", "one", "something", "anything", "up", "down", "back", "on", "off"}


def is_ui_action(step: Dict[str, Any]) -> bool:
    """A step the speaker performs ON THE INTERFACE: a key chord, or a UI verb with a real object (not 'this' / 'it')."""
    if step.get("chord"):
        return True
    tgt = (step.get("target") or "").strip().lower()
    return step.get("verb") in _UI_VERBS and len(tgt) >= 3 and tgt.split()[0] not in _PRONOUN_TARGETS


def action_moments(segments: Sequence[Dict[str, Any]], pad_s: float = 2.0, merge_gap_s: float = 4.0) -> List[Dict[str, Any]]:
    """Time spans [t0, t1] where the speaker performs an action (imperative step or key chord), padded and merged: the only seconds worth downloading."""
    from core_organs.rag.procedures import extract_steps
    spans: List[List[float]] = []
    for seg in segments:
        text = str(seg.get("text", ""))
        if any(is_ui_action(st) for st in extract_steps(text, [text])):
            t0 = max(0.0, float(seg["start"]) - pad_s)
            t1 = float(seg["start"]) + float(seg.get("duration", 0.0)) + pad_s
            if spans and t0 - spans[-1][1] <= merge_gap_s:
                spans[-1][1] = max(spans[-1][1], t1)
                spans[-1][2].append(text)
            else:
                spans.append([t0, t1, [text]])
    return [{"t0": round(a, 2), "t1": round(b, 2), "text": " ".join(t)} for a, b, t in spans]


class VideoUnavailable(Exception):
    """The video itself is gone / private / region-locked: a permanent property of THAT video, not a sign that the address is blocked."""


_UNAVAILABLE = ("not available", "unavailable", "private video", "has been removed", "sign in to confirm", "members-only", "copyright", "terminated")


def download_section(video_id: str, t0: float, t1: float, out_dir: str, max_height: int = 720) -> str:
    """Download ONLY [t0, t1] of a video (yt-dlp sections; needs ffmpeg). Returns the file path. Explicit use only: this is a network download.
    H.264 is preferred: YouTube's default 720p here is AV1, and ffmpeg's software AV1 decode crashed intermittently (Windows memory-pattern exit code) while OCR ran at the same time.
    A failed cut is retried once WITHOUT forced re-encoding (cuts at the nearest keyframe: a little longer, but a stream copy); a video that is gone raises VideoUnavailable."""
    import yt_dlp
    from yt_dlp.utils import download_range_func
    os.makedirs(out_dir, exist_ok=True)
    tmpl = os.path.join(out_dir, f"{video_id}_{int(t0)}-{int(t1)}.%(ext)s")
    fmt = (f"bestvideo[height<={max_height}][vcodec^=avc1][ext=mp4]/best[height<={max_height}][vcodec^=avc1][ext=mp4]/"
           f"bestvideo[height<={max_height}][ext=mp4]/best[height<={max_height}][ext=mp4]/best[height<={max_height}]")
    last: Optional[Exception] = None
    for force in (True, False):
        opts = {"quiet": True, "no_warnings": True, "format": fmt, "outtmpl": tmpl, "download_ranges": download_range_func(None, [(t0, t1)]), "force_keyframes_at_cuts": force,
                "noplaylist": True, "socket_timeout": 30}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                return ydl.prepare_filename(info)
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in _UNAVAILABLE):
                raise VideoUnavailable(str(exc)[:160])
            last = exc
    raise last


def transcribe_audio(path: str, model_size: str = "base.en") -> List[Dict[str, Any]]:
    """CPU int8 faster-whisper: [{text, start, duration}]. The fallback for videos without captions; keeps the GPU for the vision model."""
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(path, vad_filter=True)
    return [{"text": s.text.strip(), "start": float(s.start), "duration": float(s.end - s.start)} for s in segs if s.text.strip()]


# ---- Set-of-Marks of a still ---------------------------------------------------------------------------------------------------------------------------
def som_of_frame(image, budget_s: float = 40.0, region: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, Any]:
    """The numbered control map of one picture (the format the live model reads): {size, elements:[{id,label,role,box:[x,y,w,h],conf,sources}], tiers_used, tiers_skipped, seconds}.
    `region` (x, y, w, h): analyse only the delta box and shift the boxes back to full-frame pixels."""
    from PIL import Image
    from core_organs.professor import sweeper
    img = Image.open(image).convert("RGB") if isinstance(image, (str, os.PathLike)) else image.convert("RGB")
    ox = oy = 0
    if region:
        x, y, w, h = region
        img = img.crop((x, y, x + w, y + h))
        ox, oy = x, y
    opt = sweeper.ScanOptions.for_mode("quick")
    opt.use_vlm, opt.learn, opt.use_uia, opt.save, opt.include_popups, opt.knowledge = False, False, False, False, False, False
    opt.budget_s = budget_s
    t0 = time.time()
    sm, _ = sweeper.scan(image=img, mode="quick", options=opt)
    els = []
    for e in sm.elements:
        b = e.bbox
        els.append({"id": e.id, "label": e.label, "role": e.role, "box": [int(b.x1 + ox), int(b.y1 + oy), int(b.x2 - b.x1), int(b.y2 - b.y1)], "conf": round(float(e.conf), 3), "sources": list(e.sources)})
    return {"size": list(sm.size) if sm.size else list(img.size), "elements": els, "tiers_used": list(sm.tiers_used), "tiers_skipped": list(sm.tiers_skipped), "seconds": round(time.time() - t0, 2)}


def som_text(som: Dict[str, Any], max_items: int = 60) -> str:
    """The inventory a model is shown: one line per element, '#id role "label" [x,y,w,h]'."""
    lines = [f'#{e["id"]} {e["role"]} {json.dumps(e["label"], ensure_ascii=False) if e["label"] else "(unnamed icon)"} {e["box"]}' for e in som["elements"][:max_items]]
    return "\n".join(lines)


# ==== EDITING ===========================================================================================================================================
# A request ("a 30-second reel of the best moments with captions", "cut the silences", "join these clips with a title") -> an edit decision list planned by the model from
# what the footage holds (speech with times, silences, scene changes), checked by code against the sources, rendered by FFmpeg (trim / concat / burned-in captions / title /
# music ducked under the speech / loudness), written as a Shotcut (MLT) project the person can keep editing, and PROVEN by reading the render back. Nothing is uploaded.
FONT = os.environ.get("HOJAIGA_VIDEO_FONT", os.path.join(os.environ.get("WINDIR", "C:" + os.sep + "Windows"), "Fonts", "arial.ttf"))   # FFmpeg here has no fontconfig file: fonts are named
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")
WHISPER_DIR = os.environ.get("HOJAIGA_WHISPER", r"D:\new_automation\data\inbox\5_5_faster_whisper_turbo")


def ffbin(name: str = "ffmpeg") -> str:
    import shutil
    d = os.environ.get("HOJAIGA_FFMPEG_DIR", "")
    cand = os.path.join(d, name + ".exe") if d else ""
    return cand if cand and os.path.isfile(cand) else (shutil.which(name) or name)


def _run(args: Sequence[str], timeout: float = 1800) -> Tuple[int, str, str]:
    import subprocess
    p = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace", creationflags=0x08000000 if os.name == "nt" else 0)
    return p.returncode, p.stdout, p.stderr


def probe(path: str) -> Dict[str, Any]:
    """{'duration', 'width', 'height', 'fps', 'has_audio', 'has_video'} from ffprobe."""
    rc, out, _err = _run([ffbin("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", path], 120)
    if rc:
        return {"ok": False}
    d = json.loads(out or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), {})
    num, _, den = str(v.get("r_frame_rate", "30/1")).partition("/")
    return {"ok": True, "duration": float((d.get("format") or {}).get("duration") or v.get("duration") or 0), "width": int(v.get("width") or 0), "height": int(v.get("height") or 0),
            "fps": round(float(num) / float(den or 1), 3) if num else 30.0, "has_audio": bool(a), "has_video": bool(v)}


def silences(path: str, noise_db: float = -35.0, min_s: float = 0.6) -> List[Tuple[float, float]]:
    """[(start, end)] of quiet stretches (FFmpeg silencedetect)."""
    _rc, _out, err = _run([ffbin(), "-hide_banner", "-nostats", "-i", path, "-af", f"silencedetect=noise={noise_db}dB:d={min_s}", "-f", "null", "-"], 1800)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    dur = probe(path).get("duration", 0.0)
    return [(max(0.0, s), ends[i] if i < len(ends) else dur) for i, s in enumerate(starts)]


def spoken_spans(duration: float, quiet: Sequence[Tuple[float, float]], pad: float = 0.15, min_len: float = 0.4) -> List[Tuple[float, float]]:
    """The complement of the silences, padded so words are not clipped."""
    out, t = [], 0.0
    for s, e in sorted(quiet):
        if s - t >= min_len:
            out.append((max(0.0, t - pad), min(duration, s + pad)))
        t = max(t, e)
    if duration - t >= min_len:
        out.append((max(0.0, t - pad), duration))
    return out


def audio_array(path: str, rate: int = 16000) -> np.ndarray:
    """The sound track as 16 kHz mono float32, decoded by FFmpeg (faster-whisper's own loader breaks on this machine's PyAV: 'metadata_errors', Oct-28)."""
    import subprocess
    raw = subprocess.run([ffbin(), "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"], capture_output=True, timeout=1800,
                         creationflags=0x08000000 if os.name == "nt" else 0).stdout
    return np.frombuffer(raw, np.float32).copy()


def transcribe(path: str, hint: str = "") -> List[Dict[str, Any]]:
    """Speech with times: the downloaded large-v3-turbo (CPU int8) when it is there, else the small default. `hint`: words the speech is likely to contain
    (the request's names), given to whisper as its prompt so a name is spelled as the person spells it ('Hojaiga' came out 'Hojigah' without it)."""
    from faster_whisper import WhisperModel
    model = WhisperModel(WHISPER_DIR if os.path.isfile(os.path.join(WHISPER_DIR, "model.bin")) else "base.en", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio_array(path), vad_filter=True, initial_prompt=hint or None)
    return [{"text": s.text.strip(), "start": float(s.start), "duration": float(s.end - s.start)} for s in segs if s.text.strip()]


EDIT_SYSTEM = ("You are a video editor. You get the numbered lines of what is said in the footage (with their source and length) and a request. Name the lines the edit DROPS: "
               "filler (um, uh, false starts, 'let me find...'), repeats, and - only when the request asks for something short, a highlight or best-of - the weaker lines until it fits. "
               "Every line you do not name stays, in its order. Reply JSON only: {\"drop\": [line numbers], \"captions\": true or false, "
               "\"title\": \"the title text the request gives, else empty\", \"target_seconds\": n or 0}.")


def speech_lines(sources: Sequence[Dict[str, Any]], pad: float = 0.15) -> List[Dict[str, Any]]:
    """Every transcript line of every source, tightened to its SPOKEN part with the measured silences (a whisper line also covers the pause after it: measured
    5.9-13.7 s for speech at 6.0-8.9 s, Oct-28), with a small pad so no word is clipped."""
    out = []
    for i, s in enumerate(sources):
        spans = spoken_spans(s["duration"], s.get("quiet", []), pad=0.0, min_len=0.2) or [(0.0, s["duration"])]
        for x in s.get("speech", []):
            a, b = x["start"], x["start"] + x["duration"]
            hit = [(max(a, p), min(b, q)) for p, q in spans if min(b, q) - max(a, p) > 0.1]
            if hit:
                a, b = hit[0][0], hit[-1][1]
            out.append({"source": i, "start": round(max(0.0, a - pad), 3), "end": round(min(s["duration"], b + pad), 3), "text": x["text"]})
    return out


def _title_in(request: str) -> str:
    m = re.search(r"\btitled?\s+[\"“']?(.+?)[\"”']?(?=\s*(?:,|;|\.|$|\s+and\s|\s+with\s|\s+then\s))", request, re.I)
    return m.group(1).strip() if m else ""


def plan_edit(request: str, sources: Sequence[Dict[str, Any]], ask: Optional[Any] = None) -> Dict[str, Any]:
    """The edit decision list. The model chooses LINES (which to keep, in what order) - live Oct-28 the 7B planner, given raw times, kept the 'Um, uh' line and dropped two
    sentences; choosing lines is a judgment it makes well - and the code turns them into clips at the measured speech edges. Footage with no speech: its scenes are the lines."""
    if ask is None:
        from core_organs.mind import app_qa as QA
        ask = lambda system, prompt: QA.ask_llm(prompt, system, timeout=180, max_tokens=600, json_mode=True)
    lines = speech_lines(sources)
    if not lines:                                                                              # no speech: the scenes (or the whole clips) are what can be kept
        for i, s in enumerate(sources):
            cuts = [0.0] + [t for t in s.get("scenes", []) if 0 < t < s["duration"]] + [s["duration"]]
            lines += [{"source": i, "start": a, "end": b, "text": f"(shot {k + 1} of {os.path.basename(s['path'])}, {b - a:.1f} s, no speech)"}
                      for k, (a, b) in enumerate(zip(cuts, cuts[1:])) if b - a >= 0.5]
    desc = [f"{n}. (source {x['source']}, {x['end'] - x['start']:.1f} s) {x['text']}" for n, x in enumerate(lines, 1)]
    note = ""
    for _ in range(2):
        raw = ask(EDIT_SYSTEM, "Lines:\n" + "\n".join(desc[:400]) + f"\n\nRequest: {request}\n" + (f"Your previous answer was not usable: {note}\n" if note else "") + "JSON:") or ""
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
        except ValueError:
            d, note = {}, "it was not one JSON object"
            continue
        # the model names what goes; everything else stays in order (asked for what to KEEP, the 7B planner kept one merged line of a five-line talk for 'cut the fillers', Oct-28)
        drop = set()
        for k in d.get("drop") or []:
            with contextlib.suppress(TypeError, ValueError):
                drop.add(int(k))
        if "drop" not in d and isinstance(d.get("keep"), list):
            drop = set(range(1, len(lines) + 1)) - {int(k) for k in d["keep"] if str(k).isdigit()}
        keep = [n for n in range(1, len(lines) + 1) if n not in drop]
        if not keep:
            note = "every line was dropped"
            continue
        target = float(d.get("target_seconds") or 0) or float((re.search(r"(\d+(?:\.\d+)?)\s*(?:-\s*)?(?:s|sec|secs|second|seconds)\b", request, re.I) or [0, 0])[1])
        length = lambda ks: sum(lines[k - 1]["end"] - lines[k - 1]["start"] for k in ks)
        if target and length(keep) > 1.2 * target and len(keep) > 1:                                 # too long for what was asked: the model ranks, the code fits
            r2 = ask("Rank the lines by how well each carries the message of the footage for this request, best first. Reply JSON only: {\"ranked\": [line numbers]}.",
                     "Lines:\n" + "\n".join(desc[k - 1] for k in keep) + f"\n\nRequest: {request}\nJSON:") or ""
            m2 = re.search(r"\{.*\}", r2, re.S)
            with contextlib.suppress(ValueError, TypeError, AttributeError):
                ranked = [int(k) for k in json.loads(m2.group(0)).get("ranked", []) if int(k) in keep]
                ranked += [k for k in keep if k not in ranked]
                fit: List[int] = []
                for k in ranked:
                    if not fit or length(fit + [k]) <= 1.2 * target:
                        fit.append(k)
                keep = sorted(fit)
        d["target_seconds"] = target
        clips: List[Dict[str, Any]] = []
        for k in keep:
            x = lines[k - 1]
            if clips and clips[-1]["source"] == x["source"] and 0 <= x["start"] - clips[-1]["end"] < 0.35:
                clips[-1]["end"] = x["end"]                                                        # touching lines of one source play as one clip
                clips[-1]["lines"].append(k)
            else:
                clips.append({"source": x["source"], "start": x["start"], "end": x["end"], "lines": [k]})
        title = _title_in(request) or (str(d.get("title") or "") if str(d.get("title") or "").lower() in request.lower() else "")
        return {"clips": clips, "captions": bool(d.get("captions")) or bool(re.search(r"\b(caption|subtitle)", request, re.I)), "title": title[:80],
                "target_seconds": float(d.get("target_seconds") or 0), "lines": lines, "keep": keep}
    return {"clips": [], "captions": False, "title": "", "target_seconds": 0, "error": note or "the planner gave nothing"}


def edl_speech(edl: Dict[str, Any], sources: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The speech lines that fall in the chosen clips, moved to the edited timeline (captions of the edit, not of the sources)."""
    out, t = [], 0.0
    for c in edl["clips"]:
        for x in sources[c["source"]].get("speech", []):
            a, b = max(x["start"], c["start"]), min(x["start"] + x["duration"], c["end"])
            if b - a > 0.2:
                out.append({"text": x["text"], "start": t + a - c["start"], "end": t + b - c["start"]})
        t += c["end"] - c["start"]
    return out


def write_srt(lines: Sequence[Dict[str, Any]], path: str) -> str:
    def ts(v: float) -> str:
        ms = int(round(v * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    with open(path, "w", encoding="utf-8") as f:
        for i, x in enumerate(lines, 1):
            f.write(f"{i}\n{ts(x['start'])} --> {ts(x['end'])}\n{x['text']}\n\n")
    return path


def _ff_path(p: str) -> str:
    """A path inside an FFmpeg filter argument (Windows drive colon and backslashes escaped)."""
    return p.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render(edl: Dict[str, Any], sources: Sequence[Dict[str, Any]], out_path: str, srt: str = "", music: str = "", size: Tuple[int, int] = (1280, 720), fps: int = 30) -> Dict[str, Any]:
    """Trim every clip, scale to one size, join, then title (first 3 s), burned-in captions, music ducked under the speech, loudness to -16 LUFS. H.264 + AAC."""
    W, H = size
    args = [ffbin(), "-y", "-hide_banner", "-loglevel", "error"]
    for s in sources:
        args += ["-i", s["path"]]
    if music:
        args += ["-stream_loop", "-1", "-i", music]
    parts, labels = [], []
    for k, c in enumerate(edl["clips"]):
        i = c["source"]
        parts.append(f"[{i}:v]trim={c['start']}:{c['end']},setpts=PTS-STARTPTS,scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{k}]")
        if sources[i].get("has_audio", True):
            parts.append(f"[{i}:a]atrim={c['start']}:{c['end']},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[a{k}]")
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{c['end'] - c['start']}[a{k}]")
        labels.append(f"[v{k}][a{k}]")
    parts.append("".join(labels) + f"concat=n={len(edl['clips'])}:v=1:a=1[vc][ac]")
    v = "[vc]"
    if edl.get("title"):
        t = edl["title"].replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")
        parts.append(f"{v}drawtext=fontfile='{_ff_path(FONT)}':text='{t}':fontcolor=white:fontsize=56:box=1:boxcolor=black@0.5:boxborderw=18:x=(w-text_w)/2:y=h*0.12:enable='lt(t,3)'[vt]")
        v = "[vt]"
    if srt:
        parts.append(f"{v}subtitles='{_ff_path(srt)}':fontsdir='{_ff_path(os.path.dirname(FONT))}':force_style='FontName=Arial,FontSize=22,Outline=2,MarginV=40'[vs]")
        v = "[vs]"
    a = "[ac]"
    if music:
        parts.append(f"[{len(sources)}:a]volume=0.35,aformat=sample_rates=48000:channel_layouts=stereo[mu]")
        parts.append("[ac]asplit=2[sp][key]")
        parts.append("[mu][key]sidechaincompress=threshold=0.03:ratio=12:attack=20:release=400[duck]")
        parts.append("[sp][duck]amix=inputs=2:duration=first:dropout_transition=0[am]")
        a = "[am]"
    parts.append(f"{a}loudnorm=I=-16:TP=-1.5:LRA=11[ao]")
    args += ["-filter_complex", ";".join(parts), "-map", v, "-map", "[ao]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_path]
    rc, _out, err = _run(args, 3600)
    return {"ok": rc == 0 and os.path.isfile(out_path), "error": err.strip()[-400:] if rc else "", "path": out_path}


def write_mlt(edl: Dict[str, Any], sources: Sequence[Dict[str, Any]], path: str, fps: int = 30) -> str:
    """The same edit as a Shotcut / MLT project (one producer per source, a playlist of in/out points), so the person can open it and keep editing."""
    from xml.sax.saxutils import quoteattr
    fr = lambda s: int(round(s * fps))
    x = [f'<?xml version="1.0" encoding="utf-8"?>\n<mlt LC_NUMERIC="C" version="7.0.0" producer="main_bin">',
         f'  <profile description="HD {fps} fps" width="1280" height="720" progressive="1" sample_aspect_num="1" sample_aspect_den="1" display_aspect_num="16" display_aspect_den="9" frame_rate_num="{fps}" frame_rate_den="1" colorspace="709"/>']
    for i, s in enumerate(sources):
        x.append(f'  <producer id="producer{i}" in="0" out="{fr(s["duration"]) - 1}"><property name="resource">{quoteattr(s["path"])[1:-1]}</property><property name="mlt_service">avformat</property></producer>')
    x.append('  <playlist id="playlist0"><property name="shotcut:video">1</property><property name="shotcut:name">V1</property>')
    x += [f'    <entry producer="producer{c["source"]}" in="{fr(c["start"])}" out="{max(fr(c["start"]), fr(c["end"]) - 1)}"/>' for c in edl["clips"]]
    x.append('  </playlist>')
    total = sum(fr(c["end"]) - fr(c["start"]) for c in edl["clips"])
    x.append(f'  <tractor id="tractor0" in="0" out="{max(0, total - 1)}"><property name="shotcut">1</property><track producer="playlist0"/></tractor>\n</mlt>')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(x))
    return path


def check_render(out_path: str, edl: Dict[str, Any], srt: str = "", tol: float = 0.08) -> Dict[str, Any]:
    """The render read back: it plays (video + audio streams), its length is the edit's (within tol), the captions exist when asked."""
    p = probe(out_path) if os.path.isfile(out_path) else {"ok": False}
    want = sum(c["end"] - c["start"] for c in edl["clips"])
    probs = []
    if not p.get("ok"):
        probs.append("the render does not open")
    else:
        if not (p["has_video"] and p["has_audio"]):
            probs.append("a video or audio stream is missing")
        if want and abs(p["duration"] - want) > max(0.5, tol * want):
            probs.append(f"length {p['duration']:.1f} s, the edit is {want:.1f} s")
        if edl.get("target_seconds") and abs(p["duration"] - edl["target_seconds"]) > max(2.0, 0.25 * edl["target_seconds"]):
            probs.append(f"asked for about {edl['target_seconds']:.0f} s, made {p['duration']:.1f} s")
    if edl.get("captions") and not (srt and os.path.isfile(srt) and os.path.getsize(srt) > 0):
        probs.append("captions were asked for but none were made")
    return {"ok": not probs, "problems": probs, "duration": p.get("duration"), "edit_seconds": round(want, 2)}


def edit_video(request: str, paths: Sequence[str], out_dir: str, ask: Optional[Any] = None, music: str = "", transcribe_fn: Optional[Any] = None) -> Dict[str, Any]:
    """The whole edit: understand every source, plan, render, project file, proof. Returns the report (paths, the plan, the check)."""
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    sources = []
    for pth in paths:
        info = probe(pth)
        if not info.get("ok"):
            return {"status": "FAILED", "evidence": f"{pth} cannot be read as a video"}
        quiet = silences(pth) if info["has_audio"] else []
        names = " ".join(dict.fromkeys(re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", request)))
        speech = ((transcribe_fn or transcribe)(pth, names) if names else (transcribe_fn or transcribe)(pth)) if info["has_audio"] else []
        scenes = [round(e.get("t", e.get("time", 0.0)), 2) for e in (scene_changes(pth, max_events=60) if info["has_video"] else []) if isinstance(e, dict)]
        sources.append({"path": pth, **info, "quiet": quiet, "speech": speech, "scenes": scenes})
    edl = plan_edit(request, sources, ask)
    if not edl["clips"]:
        return {"status": "FAILED", "evidence": f"no edit could be planned: {edl.get('error')}", "sources": [{k: s[k] for k in ("path", "duration")} for s in sources]}
    stem = re.sub(r"[^\w-]+", "_", request.lower())[:40].strip("_") or "edit"
    srt = write_srt(edl_speech(edl, sources), os.path.join(out_dir, stem + ".srt")) if edl["captions"] else ""
    if srt and os.path.getsize(srt) == 0:
        srt = ""
    out = os.path.join(out_dir, stem + ".mp4")
    r = render(edl, sources, out, srt, music)
    mlt = write_mlt(edl, sources, os.path.join(out_dir, stem + ".mlt"))
    chk = check_render(out, edl, srt) if r["ok"] else {"ok": False, "problems": [r["error"]]}
    return {"status": "DONE" if chk["ok"] else ("FAILED_CHECK" if r["ok"] else "FAILED"), "video": out if r["ok"] else "", "project": mlt, "captions": srt, "plan": edl,
            "check": chk, "seconds": round(time.time() - t0, 1),
            "evidence": f"{len(edl['clips'])} clip(s), {chk.get('duration') or 0:.1f} s rendered" + ("; " + "; ".join(chk.get("problems", [])) if chk.get("problems") else "; length and streams check")}


# ---- taste: several edits to choose from, and the person's choices remembered ------------------------------------------------------------------------
TASTE_FILE = os.environ.get("HOJAIGA_VIDEO_TASTE", os.path.join("D:" + os.sep, "new_automation", "data", "video_taste.json"))
BRIEFS_SYSTEM = ("You are a video editor offering a person DIFFERENT edits of the same footage to choose from. From the request and what this person chose before, "
                 "write N short edit requests that differ in a way the person would notice (pace, length, what is kept, captions, title) and all still do what the "
                 "request asks. Use the person's past choices to lean toward what they liked; still make one option that tries something new. "
                 "Reply JSON only: {\"options\": [{\"name\": \"2-4 words\", \"request\": \"the edit request\", \"why\": \"what makes it different\"}]}.")


def taste(person: str = "me", path: str = "") -> List[Dict[str, Any]]:
    """What this person chose before (newest last): the request, the option they picked, the ones they passed over and why."""
    with contextlib.suppress(Exception):
        return (json.load(open(path or TASTE_FILE, encoding="utf-8")).get(person) or [])[-20:]
    return []


def record_choice(person: str, request: str, chosen: Dict[str, Any], others: Sequence[Dict[str, Any]], why: str = "", path: str = "") -> None:
    """The person picked one edit: kept per person, and fed into the next edit's options."""
    path = path or TASTE_FILE
    d: Dict[str, Any] = {}
    with contextlib.suppress(Exception):
        d = json.load(open(path, encoding="utf-8"))
    d.setdefault(person, []).append({"t": time.strftime("%Y-%m-%d %H:%M"), "request": request, "chose": {k: chosen.get(k) for k in ("name", "request", "why")},
                                     "passed_over": [o.get("name") for o in others if o is not chosen], "said": why})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(d, open(path, "w", encoding="utf-8"), indent=1)


def edit_options(request: str, paths: Sequence[str], out_dir: str, n: int = 3, person: str = "me", ask: Optional[Any] = None,
                 transcribe_fn: Optional[Any] = None, music: str = "", taste_path: str = "") -> Dict[str, Any]:
    """N different finished edits of the same footage, each rendered and checked, for the person to choose from (status NEEDS_CHOICE). The options are written
    by the model from the request and this person's past choices (taste); the footage is heard once and shared by every option."""
    if ask is None:
        from core_organs.mind import app_qa as QA
        ask = lambda system, prompt: QA.ask_llm(prompt, system, timeout=180, max_tokens=700, json_mode=True)
    past = taste(person, taste_path)
    heard: Dict[Tuple[str, str], Any] = {}
    base = transcribe_fn or transcribe
    def once(pth: str, hint: str = "") -> Any:                                                         # every option reads the same footage: transcribe it once
        if (pth, hint) not in heard:
            heard[(pth, hint)] = base(pth, hint) if hint else base(pth)
        return heard[(pth, hint)]
    facts = []                                                                                        # the options are written knowing the footage (Oct-28: 30 s / 1 min / 2 min
    for pth in paths:                                                                                 # were asked of 31 s with 9 s of speech, and all three failed their checks)
        info = probe(pth)
        names = " ".join(dict.fromkeys(re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", request)))
        sp = (once(pth, names) if names else once(pth)) if info.get("has_audio") else []
        talk = sum(max(0.0, float(x.get("end", 0)) - float(x.get("start", 0))) for x in sp if isinstance(x, dict))
        facts.append(f"- {os.path.basename(pth)}: {info.get('duration', 0):.0f} s long, {len(sp)} spoken line(s) covering {talk:.0f} s"
                     + (": " + " / ".join(str(x.get("text", ""))[:60] for x in sp[:8] if isinstance(x, dict)) if sp else ", no speech"))
    prompt = f"N = {n}\nThe footage (no option may ask for more than it holds):\n" + "\n".join(facts) + f"\nRequest: \"{request}\"\nThis person chose before:\n" + ("\n".join(f"- for '{p['request']}' they chose '{(p.get('chose') or {}).get('name')}' "
             f"({(p.get('chose') or {}).get('why')}) over {p.get('passed_over')}" + (f"; they said: {p['said']}" if p.get("said") else "") for p in past) or "- nothing yet") + "\nJSON:"
    opts: List[Dict[str, Any]] = []
    with contextlib.suppress(Exception):
        m = re.search(r"\{.*\}", ask(BRIEFS_SYSTEM, prompt) or "", re.S)
        opts = [o for o in (json.loads(m.group(0)).get("options") or []) if isinstance(o, dict) and str(o.get("request") or "").strip()][:n] if m else []
    if not opts:
        opts = [{"name": "as asked", "request": request, "why": "the request itself (no options could be written)"}]
    out = []
    for i, o in enumerate(opts, 1):
        r = edit_video(str(o["request"]), paths, os.path.join(out_dir, f"option_{i}"), ask=None if ask is None else ask, music=music, transcribe_fn=once)
        out.append({"option": i, "name": o.get("name"), "request": o["request"], "why": o.get("why"), "status": r.get("status"), "video": r.get("video"),
                    "seconds_long": (r.get("check") or {}).get("duration"), "evidence": r.get("evidence")})
    good = [o for o in out if o["status"] == "DONE"]
    return {"status": "NEEDS_CHOICE" if good else "FAILED", "options": out, "taste_used": len(past),
            "question": "Which edit is closer to what you want? (your choice is remembered for next time)" if good else "",
            "evidence": f"{len(good)} of {len(out)} options rendered and checked; taste from {len(past)} earlier choice(s)"}
