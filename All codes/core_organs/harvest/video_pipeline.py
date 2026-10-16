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


def scene_changes(video_path: str, sample_fps: float = 2.0, min_change: float = 0.015, min_gap_s: float = 1.0, settle_s: float = 0.6, max_events: int = 300, thumb: Tuple[int, int] = (192, 108)) -> List[Dict[str, Any]]:
    """[{t, frame, change, bbox, settle_frame}] -- `change` is the fraction of the (small, grey) picture that differs from the previous sample; bbox is in full-frame pixels."""
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
                frac = float((diff > 25).mean())
                t = idx / fps
                if frac >= min_change and t - last_t >= min_gap_s:
                    bb = changed_region(prev, small)
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
