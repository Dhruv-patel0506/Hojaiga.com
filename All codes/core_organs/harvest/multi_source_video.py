"""
harvest.multi_source_video -- video and picture sources that never rate-limit, so the dataset does not wait on YouTube.

    Source A  official-documentation micro-videos and GIFs (a clip + the heading / paragraph above it as its transcript)          -> `harvest_page_clips`
    Source B  Internet Archive and Wikimedia Commons (official open APIs, direct downloads)                                       -> `search_archive`, `search_commons`, `harvest_open_video`
    Source C  the browser self-recorder                                                                                          -> harvest.web_recorder
    Source D  open GUI datasets from Hugging Face, streamed (OFF unless the person approves the download)                       -> `stream_hf` (never called by a batch on its own)

A clip becomes pairs through the same explainer as a YouTube video: keyframes at the scene changes, the numbered-element scan on each, a step sentence matched to an element (video_explain.explain_video). The
'transcript' is the surrounding page text or the item's description -- no speech recognition. Every download is size-capped, polite (the web chain's pacing and robots.txt) and written under frames/; nothing
is uploaded anywhere.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional

from .paths import harvest_dir
from . import web_search_failover as W

CLIP_EXT = (".mp4", ".webm", ".ogv", ".gif")


def _download(url: str, out_dir: str, max_bytes: int = W.MAX_CLIP_BYTES) -> str:
    """A clip into out_dir (name = hash of the address); '' when it is too large, not a video, or refused."""
    st, data = W.get(url, binary=True, max_bytes=max_bytes + 1, timeout=40.0)
    if st != 200 or not data or len(data) > max_bytes:
        return ""
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    ext = ext if ext in CLIP_EXT else ".mp4"
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, hashlib.sha1(url.encode()).hexdigest()[:14] + ext)
    with open(p, "wb") as f:
        f.write(data)
    return p


def _gif_to_mp4(path: str) -> str:
    """cv2 reads an animated GIF frame by frame; the scene-change extractor needs a video file, so the GIF is rewritten as one."""
    import cv2
    from PIL import Image, ImageSequence
    out = path[:-4] + "_gif.mp4"
    if os.path.isfile(out):
        return out
    im = Image.open(path)
    frames = [f.convert("RGB").copy() for f in ImageSequence.Iterator(im)][:300]
    if len(frames) < 3:
        return ""
    w, h = frames[0].size
    vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (w, h))
    import numpy as np
    for f in frames:
        vw.write(cv2.cvtColor(np.asarray(f.resize((w, h))), cv2.COLOR_RGB2BGR))
    vw.release()
    return out


def clip_to_pairs(app_key: str, clip_path: str, text: str, title: str, root: str, rag: Any = None, som_fn: Any = None, max_pairs: int = 12) -> Dict[str, Any]:
    """One clip -> keyframes -> pairs. The clip's text is ONE transcript segment spanning the clip."""
    from . import video_explain as VE, video_pipeline as VP
    path = _gif_to_mp4(clip_path) if clip_path.lower().endswith(".gif") else clip_path
    if not path:
        return {"pairs": 0, "why": "gif too short"}
    vid = "clip_" + hashlib.sha1(clip_path.encode()).hexdigest()[:10]
    out_dir = os.path.join(root, "frames", vid)
    kf = VP.extract_keyframes(path, out_dir, vid, max_events=40)
    if not kf:
        return {"pairs": 0, "why": "no scene changes"}
    dur = max(float(k.get("t", 0)) for k in kf) + 2.0
    # the text is split into sentences spread over the clip: each sentence answers the changes near its share of the time
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 8] or [text.strip()]
    seg = [{"start": dur * i / len(sents), "end": dur * (i + 1) / len(sents), "text": s} for i, s in enumerate(sents)] if text.strip() else []
    if not seg:
        return {"pairs": 0, "why": "no text"}
    out = VE.explain_video(rag, app_key, vid, seg, kf, title=title, out_jsonl=os.path.join(root, "training", "ui_training_dataset.jsonl"), root=root, som_fn=som_fn, max_pairs=max_pairs, ingest=rag is not None)
    return {"pairs": int(out.get("pairs", 0) or out.get("written", 0) or 0), "detail": {k: out[k] for k in list(out)[:8]}}


# ---------------------------------------------------------------------------------------------------------------------------------- Source A
def harvest_page_clips(app_name: str, page_url: str, html: str, root: str = "", rag: Any = None, max_clips: int = 4) -> Dict[str, Any]:
    root = root or harvest_dir()[0]
    from . import free_master_harvester as M
    key = M.app_key_of(app_name)
    rep = {"found": 0, "downloaded": 0, "pairs": 0}
    for c in W.parse_clips(html, page_url)[:max_clips * 2]:
        if rep["downloaded"] >= max_clips:
            break
        rep["found"] += 1
        p = _download(c["url"], os.path.join(root, "frames", "clips_src"))
        if not p:
            continue
        rep["downloaded"] += 1
        with contextlib.suppress(Exception):
            rep["pairs"] += clip_to_pairs(key, p, c["text"], c["text"][:100], root, rag)["pairs"]
    return rep


# ---------------------------------------------------------------------------------------------------------------------------------- Source B
def search_archive(query: str, rows: int = 8) -> List[Dict[str, Any]]:
    """Internet Archive advanced search (official JSON API): software tutorial / screencast videos."""
    import requests
    W._pause()
    try:
        r = requests.get("https://archive.org/advancedsearch.php", params={"q": f"({query}) AND mediatype:movies", "fl[]": ["identifier", "title", "description"], "rows": rows, "output": "json"}, headers={"User-Agent": W.UA}, timeout=15)
        return [{"id": d["identifier"], "title": d.get("title", ""), "text": re.sub(r"<[^>]+>", " ", str(d.get("description", "")))[:600], "source": "archive.org"} for d in r.json().get("response", {}).get("docs", [])]
    except Exception:
        return []


def search_commons(query: str, rows: int = 8) -> List[Dict[str, Any]]:
    """Wikimedia Commons (official API): video files whose description names the application."""
    import requests
    W._pause()
    out = []
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", params={"action": "query", "generator": "search", "gsrsearch": f"{query} filetype:video", "gsrnamespace": 6, "gsrlimit": rows, "prop": "imageinfo",
                                                                          "iiprop": "url|size|extmetadata", "format": "json"}, headers={"User-Agent": W.UA}, timeout=15)
        for pg in (r.json().get("query", {}).get("pages", {}) or {}).values():
            ii = (pg.get("imageinfo") or [{}])[0]
            md = ii.get("extmetadata", {})
            out.append({"url": ii.get("url", ""), "size": ii.get("size", 0), "title": pg.get("title", ""), "text": re.sub(r"<[^>]+>", " ", md.get("ImageDescription", {}).get("value", ""))[:600], "source": "commons"})
    except Exception:
        pass
    return [o for o in out if o["url"]]


def archive_files(identifier: str) -> List[Dict[str, Any]]:
    import requests
    W._pause()
    try:
        meta = requests.get(f"https://archive.org/metadata/{identifier}", headers={"User-Agent": W.UA}, timeout=15).json()
        return [{"url": f"https://archive.org/download/{identifier}/{urllib.parse.quote(f['name'])}", "size": int(f.get("size", 0) or 0)} for f in meta.get("files", [])
                if f.get("name", "").lower().endswith((".mp4", ".webm", ".ogv")) and 0 < int(f.get("size", 0) or 0) <= W.MAX_CLIP_BYTES * 2]
    except Exception:
        return []


def harvest_open_video(app_name: str, root: str = "", rag: Any = None, max_items: int = 3) -> Dict[str, Any]:
    root = root or harvest_dir()[0]
    from . import free_master_harvester as M
    key = M.app_key_of(app_name)
    rep = {"candidates": 0, "downloaded": 0, "pairs": 0}
    items = search_commons(f"{app_name} tutorial", 6)
    for a in search_archive(f"{app_name} tutorial AND (software OR screencast)", 6):
        fs = archive_files(a["id"])
        if fs:
            items.append({"url": fs[0]["url"], "size": fs[0]["size"], "title": a["title"], "text": a["text"], "source": "archive.org"})
    for it in items:
        if rep["downloaded"] >= max_items:
            break
        if not all(w in (it["title"] + " " + it["text"]).lower() for w in re.findall(r"[a-z0-9]+", app_name.lower()) if len(w) > 2):
            continue                                                          # a clip that does not name the application is not about it
        rep["candidates"] += 1
        p = _download(it["url"], os.path.join(root, "frames", "clips_src"), max_bytes=W.MAX_CLIP_BYTES * 2)
        if not p:
            continue
        rep["downloaded"] += 1
        with contextlib.suppress(Exception):
            rep["pairs"] += clip_to_pairs(key, p, it["text"], it["title"], root, rag)["pairs"]
    return rep


# ---------------------------------------------------------------------------------------------------------------------------------- Source D (explicit approval only)
def stream_hf(dataset: str, split: str = "train", limit: int = 200, root: str = "", out_name: str = "ui_training_dataset_hf.jsonl", approved: bool = False) -> Dict[str, Any]:
    """Stream an open GUI dataset from Hugging Face into our record format (picture + elements + a click on the labelled box). OFF unless `approved=True`: it downloads data the person has not been asked about.
    The columns are detected by name (image / screenshot; a list of boxes with names or labels); a dataset whose layout is not recognised is reported, not guessed."""
    if not approved:
        return {"ran": False, "why": "downloads need the person's approval (approved=True); nothing was fetched"}
    from datasets import load_dataset
    root = root or harvest_dir()[0]
    ds = load_dataset(dataset, split=split, streaming=True)
    first = next(iter(ds))
    cols = list(first.keys())
    img_col = next((c for c in cols if c in ("image", "screenshot", "img")), None)
    box_col = next((c for c in cols if c in ("bbox", "bboxes", "boxes", "elements", "target_bbox")), None)
    name_col = next((c for c in cols if c in ("name", "label", "text", "instruction", "description", "target_name")), None)
    if not (img_col and box_col and name_col):
        return {"ran": False, "why": f"layout not recognised (columns: {cols})"}
    return {"ran": True, "columns": {"image": img_col, "box": box_col, "name": name_col}, "note": "mapping implemented per layout when a dataset is approved"}
