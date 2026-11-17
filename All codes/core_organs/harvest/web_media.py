"""
harvest.web_media -- understand what a page's VIDEO is showing and saying, not only how the page around it works.

A streaming or video site (YouTube, Twitch, Vimeo, TED, a tutorial embedded in a product page) is mostly CONTENT: if an automation is to act there without inventing things, it has to know what is on
the screen right now. So whenever the explorer lands on a page with a player, `understand_media` reads it:

    what the page says it is   title, channel, description, JSON-LD VideoObject, Open Graph, chapters / captions tracks the player offers
    what is shown              the player is MUTED (your speakers are never used), started if paused, and sampled at a few moments: each sample is a picture of the player, read with OCR (titles, slides,
                               menus, code on screen), with a scene-change score between samples, so 'a static slide' and 'a moving scene' are told apart
    what is said               the first minutes of the audio are fetched (yt-dlp) and transcribed locally (faster-whisper): no key, no network service; key terms, and any keyboard shortcut the speaker names
    what it means for the app  the record is filed with the site, so a later question ('what does the Trello intro video show?') has an answer grounded in the video, not a guess

`describe_screen(page)` is the cheap version for use BEFORE an action: what text is visible, what media is playing and what is on its frame right now, which dialog is open, what has focus.

Nothing is typed or submitted; videos are muted; a player that needs a login or a DRM license simply yields metadata only (the record says so).
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

SYSTEM_PYTHON = os.environ.get("HOJAIGA_YTDLP_PYTHON", r"C:\Users\dhruv\AppData\Local\Programs\Python\Python313\python.exe")
EMBED_RX = re.compile(r"(youtube(?:-nocookie)?\.com/embed|youtu\.be|player\.vimeo\.com|player\.twitch\.tv|wistia\.(?:com|net)|loom\.com/embed|dailymotion\.com/embed|fast\.wistia|vidyard|brightcove)", re.I)
STOP = set("the and for you your with from that this are was have has not all can will get use our out now one any how what who why when where about into over just like then than also here there their they them "
           "going gonna really very okay yeah right thing things something know want need make made see look let lets actually basically so well um uh".split())

MEDIA_JS = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 120 && r.height > 70 && s.visibility !== 'hidden' && s.display !== 'none' && r.bottom > 0 && r.top < innerHeight * 2; };
  const out = [];
  const tag = (e) => { if (!e.dataset.hjMedia) e.dataset.hjMedia = String(window.__hjm = (window.__hjm || 0) + 1); return e.dataset.hjMedia; };
  for (const v of document.querySelectorAll('video, audio')) {
    if (v.tagName === 'AUDIO' || vis(v)) { const r = v.getBoundingClientRect();
      out.push({kind: v.tagName.toLowerCase(), id: tag(v), src: (v.currentSrc || v.src || '').slice(0, 200), duration: isFinite(v.duration) ? v.duration : -1, paused: v.paused, ended: v.ended, muted: v.muted, ready: v.readyState,
                w: Math.round(r.width), h: Math.round(r.height), poster: (v.poster || '').slice(0, 160), tracks: [...v.querySelectorAll('track')].map(t => ({kind: t.kind, label: t.label, lang: t.srclang})).slice(0, 6)}); }
  }
  for (const f of document.querySelectorAll('iframe')) {
    const src = f.src || f.getAttribute('data-src') || '';
    if (vis(f) && /youtube|youtu\.be|vimeo|twitch|wistia|loom|dailymotion|vidyard|brightcove/i.test(src)) { const r = f.getBoundingClientRect();
      out.push({kind: 'embed', id: tag(f), src: src.slice(0, 300), duration: -1, paused: null, ended: false, muted: null, ready: -1, w: Math.round(r.width), h: Math.round(r.height), poster: '', tracks: []}); }
  }
  return out;
}
"""
META_JS = r"""
() => {
  const m = (n) => { const e = document.querySelector('meta[property="' + n + '"], meta[name="' + n + '"]'); return e ? (e.content || '') : ''; };
  let ld = [];
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) { try { const j = JSON.parse(s.textContent); const arr = Array.isArray(j) ? j : (j['@graph'] || [j]); for (const x of arr) if (x && /VideoObject|Clip|BroadcastEvent/i.test(JSON.stringify(x['@type'] || ''))) ld.push({name: x.name, description: (x.description || '').slice(0, 400), duration: x.duration, uploadDate: x.uploadDate, author: (x.author && (x.author.name || x.author)) || ''}); } catch (e) {} }
  return {title: document.title, og_title: m('og:title'), og_description: m('og:description').slice(0, 500), og_video: m('og:video') || m('og:video:url'), og_type: m('og:type'), description: m('description').slice(0, 500),
          h1: [...document.querySelectorAll('h1')].map(e => (e.innerText || '').trim()).filter(Boolean).slice(0, 3), ld: ld.slice(0, 2), url: location.href};
}
"""
SCREEN_JS = r"""
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none' && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
  const texts = []; const seen = new Set();
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while ((n = w.nextNode()) && texts.length < 160) { const t = (n.nodeValue || '').replace(/\s+/g, ' ').trim(); if (t.length < 3 || seen.has(t)) continue; const p = n.parentElement; if (!p || p.closest('script,style,noscript,#__hj_hud')) continue; if (vis(p)) { seen.add(t); texts.push(t.slice(0, 120)); } }
  const dlg = [...document.querySelectorAll('[role=dialog], [aria-modal=true], dialog[open]')].filter(vis).map(e => (e.getAttribute('aria-label') || (e.innerText || '').replace(/\s+/g, ' ').slice(0, 80)));
  const a = document.activeElement; const focus = a && a !== document.body ? ((a.getAttribute('aria-label') || a.innerText || a.placeholder || a.tagName) + '').replace(/\s+/g, ' ').slice(0, 60) : '';
  return {title: document.title, url: location.href, visible_text: texts, dialogs: dlg, focus};
}
"""


def words(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in STOP and len(w) <= 22]


def key_terms(text: str, top: int = 12) -> List[str]:
    """Words a speaker keeps coming back to (frequent, not filler) plus capitalised names (products, features) that appear more than once."""
    c = Counter(words(text))
    names = Counter(re.findall(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-zA-Z0-9]{2,})\b", text or ""))
    out = [w for w, n in c.most_common(40) if n >= 2][:top]
    out += [n.lower() for n, k in names.most_common(8) if k >= 2 and n.lower() not in out][:5]
    return list(dict.fromkeys(out))[:top + 4]


def ocr_image(png: bytes, min_conf: int = 55) -> List[str]:
    """Text read off one picture of the player (enlarged and contrast-normalised first); only words the OCR is reasonably sure of."""
    import cv2
    import numpy as np
    import pytesseract
    im = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if im is None or min(im.shape[:2]) < 40:
        return []
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    if max(g.shape) < 1100:
        g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    if g.mean() < 110:
        g = 255 - g
    d = pytesseract.image_to_data(g, config="--psm 11", output_type=pytesseract.Output.DICT)
    lines: Dict[Tuple[int, int, int], List[str]] = {}
    for i, t in enumerate(d["text"]):
        t = (t or "").strip()
        try:
            conf = float(d["conf"][i])
        except Exception:
            conf = -1
        if t and conf >= min_conf and re.search(r"[A-Za-z0-9]", t):
            lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(t)
    out = [" ".join(v) for v in lines.values()]
    return [l for l in out if len(re.findall(r"[A-Za-z]", l)) >= 3][:40]


def change_between(a: bytes, b: bytes) -> float:
    """0..1: how much the picture changed between two samples (mean absolute difference of small grey versions)."""
    import cv2
    import numpy as np
    ia = cv2.imdecode(np.frombuffer(a, np.uint8), cv2.IMREAD_GRAYSCALE)
    ib = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_GRAYSCALE)
    if ia is None or ib is None:
        return 0.0
    ia, ib = cv2.resize(ia, (96, 54)), cv2.resize(ib, (96, 54))
    return float(np.mean(np.abs(ia.astype(float) - ib.astype(float))) / 255.0)


def fetch_audio(url: str, seconds: int, out_dir: str, timeout_s: float = 150.0) -> str:
    """The first `seconds` of a page's video as audio, with yt-dlp (it knows YouTube, Vimeo, TED, Twitch VODs, Wistia ...). Returns the file path or ''."""
    if not os.path.isfile(SYSTEM_PYTHON):
        return ""
    out = os.path.join(out_dir, "audio.%(ext)s")
    cmd = [SYSTEM_PYTHON, "-m", "yt_dlp", "-q", "--no-warnings", "--no-playlist", "-f", "bestaudio[ext=m4a]/bestaudio", "--download-sections", f"*0-{seconds}", "--force-keyframes-at-cuts", "-o", out, url]
    with contextlib.suppress(Exception):
        subprocess.run(cmd, capture_output=True, timeout=timeout_s)
    for f in os.listdir(out_dir):
        if f.startswith("audio.") and not f.endswith((".part", ".ytdl")):
            return os.path.join(out_dir, f)
    return ""


WHISPER_SCRIPT = (
    "import sys, json\n"
    "from faster_whisper import WhisperModel\n"
    "m = WhisperModel(sys.argv[2], device='cpu', compute_type='int8')\n"
    "segs, _ = m.transcribe(sys.argv[1], vad_filter=True)\n"
    "print(json.dumps([{'text': s.text.strip(), 'start': float(s.start), 'duration': float(s.end - s.start)} for s in segs if s.text.strip()]))\n")


def transcribe_file(path: str, model: str = "base.en", timeout_s: float = 300.0) -> List[Dict[str, Any]]:
    """Speech to text, locally (faster-whisper, CPU int8), in a separate interpreter: the project environment's audio decoder (PyAV) is a different version from the one faster-whisper expects, the
    system interpreter's pair works."""
    p = subprocess.run([SYSTEM_PYTHON, "-X", "utf8", "-c", WHISPER_SCRIPT, path, model], capture_output=True, text=True, timeout=timeout_s)
    out = (p.stdout or "").strip().splitlines()
    if p.returncode != 0 or not out:
        raise RuntimeError((p.stderr or "no output")[-160:])
    return json.loads(out[-1])


def transcribe(url: str, seconds: int = 150, model: str = "base.en") -> Dict[str, Any]:
    tmp = tempfile.mkdtemp(prefix="wm_")
    try:
        path = fetch_audio(url, seconds, tmp)
        if not path:
            return {"ok": False, "why": "audio could not be fetched (login, DRM, live stream or an unsupported player)"}
        segs = transcribe_file(path, model)
        text = " ".join(s["text"] for s in segs)
        return {"ok": True, "segments": segs, "text": text, "seconds": seconds, "key_terms": key_terms(text)}
    except Exception as e:
        return {"ok": False, "why": f"{type(e).__name__}: {str(e)[:120]}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def caption_frames(pngs: Sequence[bytes], limit: int = 2) -> Dict[str, Any]:
    """What the PICTURE shows, in a sentence, from the local vision-language model (Qwen3-VL through llama-server, no key, no cloud). OCR reads text; only a vision model says 'a person at a desk', 'a
    code editor', 'a slide with a chart'. If the model is not running the answer says so and nothing is invented."""
    try:
        from PIL import Image
        from core_organs.professor import vlm as V
        c = V.client()
        if not c.available():
            return {"vlm": "not running", "how": "start scratch\\_start_vision_8b.bat (Qwen3-VL-8B on :8081) to get one-sentence descriptions of what the picture shows", "captions": []}
        caps = []
        for png in list(pngs)[:limit]:
            r = c.describe(Image.open(io.BytesIO(png)).convert("RGB"), "In one factual sentence, say what this video frame shows (people, objects, screen, slide). Quote any visible text exactly. If you are unsure, say so. Do not guess names.", max_tokens=90, timeout=60)
            if getattr(r, "ok", False) and getattr(r, "text", ""):
                caps.append(r.text.strip())
        return {"vlm": c.health().get("model", "up"), "captions": caps}
    except Exception as e:
        return {"vlm": f"error: {type(e).__name__}: {str(e)[:80]}", "captions": []}


def find_media(page: Any) -> List[Dict[str, Any]]:
    with contextlib.suppress(Exception):
        return page.evaluate(MEDIA_JS)
    return []


def sample_frames(page: Any, m: Dict[str, Any], n: int = 4, gap_s: float = 2.5) -> List[Tuple[float, bytes]]:
    """Pictures of the player at n moments. The video is muted first and started if it is paused (autoplay-blocked players stay as they are)."""
    sel = f"[data-hj-media='{m['id']}']"
    loc = page.locator(sel).first
    if m["kind"] in ("video", "audio"):
        with contextlib.suppress(Exception):
            loc.evaluate("v => { v.muted = true; v.volume = 0; const p = v.play && v.play(); if (p && p.catch) p.catch(() => {}); }", timeout=2000)
    with contextlib.suppress(Exception):
        loc.scroll_into_view_if_needed(timeout=1500)
    out: List[Tuple[float, bytes]] = []
    t0 = time.monotonic()
    time.sleep(0.8)
    for i in range(n):
        with contextlib.suppress(Exception):
            out.append((round(time.monotonic() - t0, 1), loc.screenshot(timeout=4000)))
        if i < n - 1:
            time.sleep(gap_s)
    return out


def understand_media(page: Any, media: Optional[Dict[str, Any]] = None, frames: int = 4, gap_s: float = 2.5, transcript_seconds: int = 150, want_transcript: bool = True,
                     out_dir: str = "") -> Dict[str, Any]:
    """Everything that can be learned about ONE player on the current page. Never raises; a field that could not be read says why."""
    t0 = time.perf_counter()
    meta: Dict[str, Any] = {}
    with contextlib.suppress(Exception):
        meta = page.evaluate(META_JS)
    ms = [media] if media else find_media(page)
    if not ms:
        return {}
    m = sorted(ms, key=lambda x: -(x["w"] * x["h"]))[0]
    rec: Dict[str, Any] = {"url": meta.get("url") or page.url, "title": (meta.get("og_title") or (meta.get("h1") or [""])[0] or meta.get("title") or "")[:160], "player": {k: m[k] for k in ("kind", "duration", "paused", "w", "h", "src")},
                           "page_says": {"description": meta.get("og_description") or meta.get("description") or "", "type": meta.get("og_type", ""), "video_object": meta.get("ld", []), "tracks": m.get("tracks", [])}}
    shots = sample_frames(page, m, frames, gap_s)
    fr: List[Dict[str, Any]] = []
    prev: Optional[bytes] = None
    for t, png in shots:
        item: Dict[str, Any] = {"t": t, "ocr": []}
        with contextlib.suppress(Exception):
            item["ocr"] = ocr_image(png)
        if prev is not None:
            item["change"] = round(change_between(prev, png), 3)
        prev = png
        fr.append(item)
        if out_dir:
            with contextlib.suppress(Exception):
                os.makedirs(out_dir, exist_ok=True)
                with open(os.path.join(out_dir, f"media_{m['id']}_{int(t * 10)}.png"), "wb") as f:
                    f.write(png)
    rec["frames"] = fr
    rec["scene"] = caption_frames([png for _, png in shots][:: max(1, len(shots) // 2)] if shots else [])
    shown: List[str] = []
    for f in fr:
        for l in f["ocr"]:
            if l not in shown:
                shown.append(l)
    rec["on_screen_text"] = shown[:40]
    ch = [f["change"] for f in fr if "change" in f]
    rec["motion"] = "moving picture" if ch and max(ch) > 0.04 else "still picture (a slide, a paused frame or a blocked player)" if ch else "unknown"
    rec["playing"] = bool(shots) and m["kind"] != "embed"
    src_url = rec["url"]
    if m["kind"] == "embed" and EMBED_RX.search(m["src"]):
        src_url = m["src"]
    if want_transcript and transcript_seconds > 0:
        tr = transcribe(src_url, transcript_seconds)
        if tr.get("ok"):
            rec["transcript"] = {"seconds": tr["seconds"], "segments": len(tr["segments"]), "text": tr["text"][:6000], "key_terms": tr["key_terms"]}
            rec["_segments"] = tr["segments"]
            with contextlib.suppress(Exception):
                from core_organs.harvest import spoken_facts as SF
                rec["spoken_shortcuts"] = [{"keys": c["chord"], "action": c["action"]} for c in SF.chords(tr["text"])][:12]
        else:
            rec["transcript"] = {"ok": False, "why": tr.get("why")}
    body = " ".join([rec["title"], rec["page_says"]["description"], " ".join(shown), rec.get("transcript", {}).get("text", "")])
    terms = key_terms(body)
    if len(terms) < 4:                                                 # a short clip repeats nothing: fall back to its distinctive longer words, in the order they were said
        terms += [w for w in dict.fromkeys(w for w in words(body) if len(w) >= 5) if w not in terms][: 6 - len(terms)]
    rec["key_terms"] = terms
    said = (rec.get("transcript") or {}).get("text", "")
    cap = (rec.get("scene") or {}).get("captions") or []
    rec["summary"] = (f"'{rec['title']}': {rec['motion']}; " + (f"picture: {cap[0][:120]}; " if cap else "") + "on screen text: " + (", ".join(shown[:4]) if shown else "no readable text") + ("; says: " + said[:140] + ("..." if len(said) > 140 else "") if said else "; no transcript")
                      + ("; about: " + ", ".join(terms[:6]) if terms else ""))
    rec["seconds"] = round(time.perf_counter() - t0, 1)
    return rec


def describe_screen(page: Any, with_media: bool = True) -> Dict[str, Any]:
    """The grounding read for BEFORE an action: what is visible right now (text, dialog, focus) and, for each player, what its current frame shows. Cheap: no transcript, one picture per player."""
    out: Dict[str, Any] = {}
    with contextlib.suppress(Exception):
        out = page.evaluate(SCREEN_JS)
    if with_media:
        media = []
        for m in find_media(page)[:3]:
            item: Dict[str, Any] = {"kind": m["kind"], "playing": (not m["paused"]) if m["paused"] is not None else None, "size": [m["w"], m["h"]]}
            with contextlib.suppress(Exception):
                png = page.locator(f"[data-hj-media='{m['id']}']").first.screenshot(timeout=3000)
                item["on_screen_now"] = ocr_image(png)[:12]
            media.append(item)
        out["media"] = media
    return out


def media_document(rec: Dict[str, Any]) -> str:
    """The record as a retrievable document: what it is, what is shown, what is said, what it is about."""
    md = [f"# Video: {rec.get('title', '')}", "", f"Page: {rec.get('url', '')}", f"Picture: {rec.get('motion', '')}", ""]
    caps = (rec.get("scene") or {}).get("captions") or []
    if caps:
        md += ["## What the picture shows (vision model)", ""] + [f"- {c}" for c in caps] + [""]
    d = (rec.get("page_says") or {}).get("description")
    if d:
        md += ["## The page says", "", d, ""]
    if rec.get("on_screen_text"):
        md += ["## Shown on screen (read from the video)", ""] + [f"- {l}" for l in rec["on_screen_text"][:25]] + [""]
    tr = rec.get("transcript") or {}
    if tr.get("text"):
        md += [f"## Said in the first {tr['seconds']} seconds (transcribed locally)", "", tr["text"][:3500], ""]
    if rec.get("spoken_shortcuts"):
        md += ["## Shortcuts the speaker named", ""] + [f"- {s['keys']}: {s['action']}" for s in rec["spoken_shortcuts"]] + [""]
    if rec.get("key_terms"):
        md += ["## About", "", ", ".join(rec["key_terms"]), ""]
    return "\n".join(md)
