r"""
youtube_video_memory.py -- a local "video memory": any video (a file, or a YouTube link) -> searchable moments of {what was SAID, what was ON SCREEN, which spoken thing is on screen where}.

    add-file   <video> --app A [--transcript t.json3|.srt] [--screen ocr|som|none]       a local video file; speech from faster-whisper (CPU) unless a transcript is given
    add-url    <link|id> --app A [--screen ...] [--max-minutes 20]                        YouTube: captions (paced, cookie-free) else Whisper; the video is downloaded at low resolution
    search     "where does he add a modifier" [--app A] [-k 5]                            hybrid: SQLite FTS5 (bm25) + embedding cosine, fused by reciprocal rank -> moments with a time link
    stats
    to-rag     --root <rag root> --confirm-ingest                                         ONLY on request: hands the transcripts to the federated RAG (rag.proc.ingest_transcript)

How it replaces "the VLM sees the video" for retrieval, without any API and without training:
  speech      faster-whisper (tiny / base / small are already in the local cache) or the video's own captions, cut into 15-35 s windows
  on screen   1-2 sampled frames per window; Tesseract (fast) or the harvester's Set-of-Marks (slow, more exact) -> labelled text elements with boxes
  alignment   (a) every spoken UI step ("click Add Modifier", "press shift A") is matched to an element on the sampled frames -> {phrase, label, box};
              (b) every content word of the speech that also appears as on-screen text is recorded with its position -> the "apple is said AND an apple is on screen, here" check.
              Both are plain string/geometry matches on text the scanner really read: nothing is detected that is not there, and a spoken thing that is not on screen is simply not aligned.
  retrieval   the moment's text (speech + screen labels + aligned labels) is embedded with a local embedder: `hash` (offline, lexical, always available) or `bge` (BAAI/bge-small-en-v1.5 from the local
              HF cache, CPU, real semantic similarity, ~25 s to load). The embedder id is stored in the database; a database is never queried with a different one.
Limits (honest): this finds WHERE a thing happens and what the screen said at that time; it cannot read a screen state it has no text for (icons, 3-D viewports, objects with no label). That seeing is the
Qwen-VL model's job. Everything here is CPU-only (CUDA hidden), offline after the download, and writes only to its own staging database until `to-rag` is asked for.
"""
from __future__ import annotations

import os

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "All codes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_STOP = set("""about above after again also always another because been before being between both could does doing done down during each either else even every from further have having here into just like
make more most much must need only other over really same should some such than that their them then there these they thing things this those through under until very want were what when where which while
will with would your you're going gonna kind okay right now let's let""".split())
_TOK = re.compile(r"[a-z0-9][a-z0-9+\-']*")


def tokens(s: str) -> List[str]:
    return _TOK.findall((s or "").lower())


# ----------------------------------------------------------------------------------------------------------------------------------- embedders
class BgeEmbedder:
    """BAAI/bge-small-en-v1.5 from the LOCAL Hugging Face cache (no download, CPU): CLS vector, L2-normalised, 384-d."""
    id = "bge-small-en-v1.5"
    dim = 384

    def __init__(self):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        import torch
        from transformers import AutoModel, AutoTokenizer
        self._torch = torch
        self.tok = AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5", local_files_only=True)
        self.model = AutoModel.from_pretrained("BAAI/bge-small-en-v1.5", local_files_only=True).eval()

    def embed(self, texts: Sequence[str], mode: str = "document") -> List[List[float]]:
        out: List[List[float]] = []
        for i in range(0, len(texts), 16):
            b = self.tok(list(texts[i:i + 16]), padding=True, truncation=True, max_length=256, return_tensors="pt")
            with self._torch.no_grad():
                v = self._torch.nn.functional.normalize(self.model(**b).last_hidden_state[:, 0], dim=1)
            out.extend(v.tolist())
        return out


def make_embedder(name: str = "hash"):
    if name == "bge":
        return BgeEmbedder()
    from core_organs.rag.embed import HashEmbedder
    return HashEmbedder()


def _pack(v: Sequence[float]) -> bytes:
    import numpy as np
    return np.asarray(v, np.float32).tobytes()


def _unpack(b: bytes):
    import numpy as np
    return np.frombuffer(b, np.float32)


# ----------------------------------------------------------------------------------------------------------------------------------- speech side
def transcribe_file(path: str, model_size: str = "base.en") -> List[Dict[str, Any]]:
    """faster-whisper on the CPU (int8) straight from the video file: [{text, start, duration}]. The model must already be in the local cache."""
    from faster_whisper import WhisperModel
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(path, vad_filter=True)
    return [{"text": s.text.strip(), "start": float(s.start), "duration": float(s.end - s.start)} for s in segs if s.text.strip()]


def read_transcript(path: str) -> List[Dict[str, Any]]:
    """A caption file -> segments. .json3 (YouTube) or .srt."""
    p = Path(path)
    if p.suffix.lower() == ".json3":
        from core_organs.harvest import captions as CAP
        return CAP.parse_json3(json.loads(p.read_text(encoding="utf-8")))
    segs: List[Dict[str, Any]] = []
    for block in re.split(r"\n\s*\n", p.read_text(encoding="utf-8-sig").strip()):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", block)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        a, b = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        text = " ".join(l.strip() for l in block.splitlines()[1:] if "-->" not in l and l.strip() and not l.strip().isdigit())
        if text:
            segs.append({"text": text, "start": a, "duration": max(b - a, 0.1)})
    return segs


WINDOW = (15.0, 35.0)                 # seconds per moment: min, max


def windows(segments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from core_organs.rag.procedures import window_transcript
    return window_transcript(list(segments), min_s=WINDOW[0], max_s=WINDOW[1])


# ----------------------------------------------------------------------------------------------------------------------------------- screen side
def sample_frames(video: str, t0: float, t1: float, out_dir: str, tag: str, n: int = 2) -> List[Tuple[float, str]]:
    """n frames inside [t0, t1] (at 1/3 and 5/6 for two): [(time, path)]."""
    import cv2
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    os.makedirs(out_dir, exist_ok=True)
    out: List[Tuple[float, str]] = []
    for f in ([0.5] if n == 1 else [1 / 3, 5 / 6][:n]):
        t = t0 + (t1 - t0) * f
        if total and t * fps >= total:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, fr = cap.read()
        if ok:
            p = os.path.join(out_dir, f"{tag}_{int(t)}.jpg")
            cv2.imwrite(p, fr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            out.append((round(t, 2), p))
    cap.release()
    return out


def screen_ocr(image: str, max_w: int = 1280, min_conf: float = 55.0) -> Dict[str, Any]:
    """Fast screen text: Tesseract words -> lines -> pieces split at wide gaps ('File  Edit  View' becomes three labels). Elements: {id, label, role, box[x,y,w,h], conf} in the picture's pixels."""
    import cv2
    import pytesseract
    if os.path.isfile(TESSERACT):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT
    img = cv2.imread(image)
    if img is None:
        return {"size": [0, 0], "elements": []}
    h0, w0 = img.shape[:2]
    sc = min(1.0, max_w / float(w0))
    if sc < 1.0:
        img = cv2.resize(img, (int(w0 * sc), int(h0 * sc)), interpolation=cv2.INTER_AREA)
    d = pytesseract.image_to_data(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), output_type=pytesseract.Output.DICT, config="--psm 11")
    lines: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
    for i, txt in enumerate(d["text"]):
        txt = (txt or "").strip()
        try:
            conf = float(d["conf"][i])
        except ValueError:
            conf = -1
        if len(txt) < 2 or conf < min_conf or not re.search(r"[A-Za-z0-9]", txt):
            continue
        lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(
            {"t": txt, "x": d["left"][i], "y": d["top"][i], "w": d["width"][i], "h": d["height"][i], "c": conf})
    els: List[Dict[str, Any]] = []
    for ws in lines.values():
        ws.sort(key=lambda w: w["x"])
        piece = [ws[0]]
        for w in ws[1:]:
            gap = w["x"] - (piece[-1]["x"] + piece[-1]["w"])
            if gap > 1.5 * max(w["h"], piece[-1]["h"]):
                els.append(_piece(piece, sc))
                piece = [w]
            else:
                piece.append(w)
        els.append(_piece(piece, sc))
    for i, e in enumerate(sorted(els, key=lambda e: (e["box"][1], e["box"][0])), 1):
        e["id"] = i
    return {"size": [w0, h0], "elements": sorted(els, key=lambda e: e["id"])}


def _piece(ws: List[Dict[str, Any]], sc: float) -> Dict[str, Any]:
    x0, y0 = min(w["x"] for w in ws), min(w["y"] for w in ws)
    x1, y1 = max(w["x"] + w["w"] for w in ws), max(w["y"] + w["h"] for w in ws)
    return {"label": " ".join(w["t"] for w in ws), "role": "text", "box": [int(x0 / sc), int(y0 / sc), int((x1 - x0) / sc), int((y1 - y0) / sc)], "conf": round(sum(w["c"] for w in ws) / len(ws) / 100, 3)}


def screen_som(image: str) -> Dict[str, Any]:
    """The harvester's Set-of-Marks (OCR + classical CV, CPU): slower (~10 s a frame), icons and controls included."""
    from core_organs.harvest import video_pipeline as VP
    return VP.som_of_frame(image, budget_s=25.0)


# ----------------------------------------------------------------------------------------------------------------------------------- alignment
def align_steps(speech: str, frames: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Spoken UI steps -> the element they name on one of the sampled frames. frames: [{t, path, elements}]."""
    import youtube_video_rag_harvester as H
    from core_organs.harvest import video_explain as VE
    from core_organs.rag.procedures import extract_steps
    out: List[Dict[str, Any]] = []
    for st in extract_steps(speech):
        st = dict(st, chord=H.step_chord(st))
        if st.get("verb") in H._UNSUPPORTED_VERBS or not VE.is_concrete(st) or H._SENSITIVE.search(f"{st.get('text', '')} {st.get('target', '')}"):
            continue
        if st["chord"]:
            out.append({"phrase": st.get("text", "")[:80], "action": "hotkey", "hotkey": st["chord"], "label": None, "box": None, "t": None})
            continue
        if st.get("verb") not in H._POINTING_VERBS:
            continue
        for fr in frames:
            el = VE.match_element({"elements": fr["elements"]}, st.get("target", "")) or (VE.match_element({"elements": fr["elements"]}, st["quoted"][0]) if st.get("quoted") else None)
            if el:
                out.append({"phrase": st.get("text", "")[:80], "action": "click", "hotkey": None, "label": el["label"], "box": el["box"], "t": fr["t"]})
                break
    return out


def cooccur(speech: str, frames: Sequence[Dict[str, Any]], cap: int = 12) -> List[Dict[str, Any]]:
    """Content words that are BOTH spoken and present as on-screen text (the 'apple is said and an apple is there' check), with where."""
    spoken = {w for w in tokens(speech) if len(w) >= 4 and w not in _STOP}
    found: Dict[str, Dict[str, Any]] = {}
    for fr in frames:
        for e in fr["elements"]:
            for w in set(tokens(e.get("label", ""))):
                if w in spoken and w not in found:
                    found[w] = {"word": w, "label": e["label"], "box": e["box"], "t": fr["t"]}
    return list(found.values())[:cap]


# ----------------------------------------------------------------------------------------------------------------------------------- the store
class VideoMemory:
    def __init__(self, db_path: str, embedder: str = "hash"):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.path = db_path
        self.c = sqlite3.connect(db_path, timeout=30)
        self.c.row_factory = sqlite3.Row
        self.c.executescript("""
            CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS videos(video_id TEXT PRIMARY KEY, app TEXT, title TEXT, source TEXT, duration REAL, segments_json TEXT, added REAL);
            CREATE TABLE IF NOT EXISTS moments(id INTEGER PRIMARY KEY, video_id TEXT, app TEXT, t0 REAL, t1 REAL, speech TEXT, screen_json TEXT, aligned_json TEXT, words_json TEXT,
                frame TEXT, embedding BLOB, UNIQUE(video_id, t0));
            CREATE VIRTUAL TABLE IF NOT EXISTS moments_fts USING fts5(speech, screen, aligned, title, tokenize='porter unicode61');
        """)
        self.emb = make_embedder(embedder)
        have = self.meta("embedder")
        if have and have != self.emb.id:
            raise ValueError(f"this memory was built with the '{have}' embedder; it cannot be searched with '{self.emb.id}' (open it with embedder='{'bge' if have.startswith('bge') else 'hash'}')")
        self.set_meta("embedder", self.emb.id)

    def close(self) -> None:
        self.c.close()

    def meta(self, k: str) -> str:
        r = self.c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else ""

    def set_meta(self, k: str, v: str) -> None:
        self.c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, v))
        self.c.commit()

    # --- write
    def add_video(self, video_id: str, app: str, title: str, source: str, duration: float, segments: Sequence[Dict[str, Any]], moments: Sequence[Dict[str, Any]]) -> Dict[str, int]:
        """moments: {t0, t1, speech, screen:[labels...], aligned:[...], words:[...], frame}. A moment already stored (same video, same t0) is skipped."""
        self.c.execute("INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?,?)", (video_id, app, title, source, duration, json.dumps(list(segments), ensure_ascii=False), time.time()))
        new = skipped = 0
        texts = [self._text(m) for m in moments]
        vecs = self.emb.embed(texts) if texts else []
        for m, txt, v in zip(moments, texts, vecs):
            if self.c.execute("SELECT 1 FROM moments WHERE video_id=? AND t0=?", (video_id, m["t0"])).fetchone():
                skipped += 1
                continue
            cur = self.c.execute("INSERT INTO moments(video_id, app, t0, t1, speech, screen_json, aligned_json, words_json, frame, embedding) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                 (video_id, app, m["t0"], m["t1"], m["speech"], json.dumps(m.get("screen", []), ensure_ascii=False), json.dumps(m.get("aligned", []), ensure_ascii=False),
                                  json.dumps(m.get("words", []), ensure_ascii=False), m.get("frame"), _pack(v)))
            self.c.execute("INSERT INTO moments_fts(rowid, speech, screen, aligned, title) VALUES (?,?,?,?,?)",
                           (cur.lastrowid, m["speech"], " ".join(m.get("screen", [])), " ".join(f"{a.get('phrase', '')} {a.get('label') or ''}" for a in m.get("aligned", [])), title))
            new += 1
        self.c.commit()
        return {"new": new, "skipped": skipped}

    @staticmethod
    def _text(m: Dict[str, Any]) -> str:
        al = "; ".join(f"{a.get('phrase', '')} -> {a.get('label') or a.get('hotkey')}" for a in m.get("aligned", []))
        return f"{m['speech']} | on screen: {', '.join(m.get('screen', [])[:25])} | aligned: {al}"

    # --- read
    def search(self, query: str, app: str = "", k: int = 5) -> List[Dict[str, Any]]:
        """Reciprocal-rank fusion of FTS5 bm25 (speech + screen text + aligned labels + title) and embedding cosine."""
        import numpy as np
        qt = [t for t in tokens(query) if t not in _STOP and len(t) > 1]
        fts: List[int] = []
        if qt:
            q = " OR ".join(f'"{t}"' for t in qt[:16])
            sql = "SELECT m.id FROM moments_fts f JOIN moments m ON m.id=f.rowid WHERE moments_fts MATCH ?" + (" AND m.app=?" if app else "") + " ORDER BY bm25(moments_fts) LIMIT 50"
            try:
                fts = [r[0] for r in self.c.execute(sql, (q, app) if app else (q,))]
            except sqlite3.OperationalError:
                fts = []
        rows = self.c.execute("SELECT id, embedding FROM moments" + (" WHERE app=?" if app else ""), (app,) if app else ()).fetchall()
        vec: List[int] = []
        if rows:
            qv = np.asarray(self.emb.embed([query], mode="query")[0], np.float32)
            sims = np.array([float(_unpack(r["embedding"]) @ qv) for r in rows])
            vec = [rows[i]["id"] for i in np.argsort(-sims)[:50]]
        score: Dict[int, float] = {}
        for ranking in (fts, vec):
            for rank, mid in enumerate(ranking):
                score[mid] = score.get(mid, 0.0) + 1.0 / (60 + rank)
        out = []
        for mid in sorted(score, key=score.get, reverse=True)[:k]:
            r = self.c.execute("SELECT m.*, v.title, v.source FROM moments m JOIN videos v ON v.video_id=m.video_id WHERE m.id=?", (mid,)).fetchone()
            out.append({"score": round(score[mid], 5), "video_id": r["video_id"], "app": r["app"], "title": r["title"], "t0": r["t0"], "t1": r["t1"], "speech": r["speech"],
                        "aligned": json.loads(r["aligned_json"]), "words_on_screen": json.loads(r["words_json"]), "frame": r["frame"], "link": self.link(r["source"], r["video_id"], r["t0"]),
                        "in_fts": mid in fts, "in_vector_top": mid in vec})
        return out

    @staticmethod
    def link(source: str, video_id: str, t: float) -> str:
        return f"https://www.youtube.com/watch?v={video_id}&t={int(t)}s" if source == "youtube" else f"{source}#t={int(t)}"

    def stats(self) -> Dict[str, Any]:
        q = lambda s: self.c.execute(s).fetchone()[0]
        return {"videos": q("SELECT count(*) FROM videos"), "moments": q("SELECT count(*) FROM moments"), "with_screen_text": q("SELECT count(*) FROM moments WHERE screen_json!='[]'"),
                "with_aligned_steps": q("SELECT count(*) FROM moments WHERE aligned_json!='[]'"), "with_words_on_screen": q("SELECT count(*) FROM moments WHERE words_json!='[]'"),
                "embedder": self.meta("embedder"), "path": self.path}

    # --- RAG hand-off (only on request)
    def to_rag(self, rag: Any, confirm: bool = False) -> Dict[str, Any]:
        """Hand each video's transcript to the federated RAG's transcript ingest (Sub-RAG 3). Refuses unless confirm=True."""
        if not confirm:
            return {"ingested": False, "why": "to_rag needs confirm=True (the person decides when the video memory goes into the RAG)"}
        n = 0
        for r in self.c.execute("SELECT video_id, app, title, segments_json FROM videos"):
            rep = rag.proc.ingest_transcript(r["app"], json.loads(r["segments_json"]), r["video_id"], r["title"])
            n += rep.inserted + rep.updated
        return {"ingested": True, "chunks": n}


# ----------------------------------------------------------------------------------------------------------------------------------- the pipeline
def build_moments(video: Optional[str], segments: Sequence[Dict[str, Any]], frames_dir: str, video_id: str, screen: str = "ocr", dots: bool = False,
                  screen_fn: Optional[Callable[[str], Dict[str, Any]]] = None, frames_per_moment: int = 2) -> List[Dict[str, Any]]:
    """Speech windows -> moments with screen text and alignment. screen = 'ocr' | 'som' | 'none' (or pass screen_fn)."""
    fn = screen_fn or (screen_ocr if screen == "ocr" else screen_som if screen == "som" else None)
    out: List[Dict[str, Any]] = []
    for w in windows(segments):
        m: Dict[str, Any] = {"t0": round(float(w["t0"]), 2), "t1": round(float(w["t1"]), 2), "speech": w["text"], "screen": [], "aligned": [], "words": [], "frame": None}
        if fn and video:
            frames = []
            for t, p in sample_frames(video, m["t0"], m["t1"], frames_dir, f"{video_id}_{int(m['t0'])}", frames_per_moment):
                els = fn(p)["elements"]
                frames.append({"t": t, "path": p, "elements": els})
            if frames:
                seen, labels = set(), []
                for fr in frames:
                    for e in fr["elements"]:
                        lab = (e.get("label") or "").strip()
                        if len(lab) >= 2 and lab.lower() not in seen:
                            seen.add(lab.lower())
                            labels.append(lab)
                m["screen"] = labels[:60]
                m["aligned"] = align_steps(m["speech"], frames)
                m["words"] = cooccur(m["speech"], frames)
                m["frame"] = frames[0]["path"]
                if dots:
                    m["frame"] = _dotted(frames, m["aligned"]) or m["frame"]
        else:
            from core_organs.rag.procedures import extract_steps
            import youtube_video_rag_harvester as H
            m["aligned"] = [{"phrase": s.get("text", "")[:80], "action": "hotkey", "hotkey": H.step_chord(dict(s)) or s.get("chord"), "label": None, "box": None, "t": None}
                            for s in extract_steps(m["speech"]) if H.step_chord(dict(s)) or s.get("chord")]
        out.append(m)
    return out


def _dotted(frames: Sequence[Dict[str, Any]], aligned: Sequence[Dict[str, Any]]) -> Optional[str]:
    """Save the frame that holds an aligned element with `● [id]` dots drawn on it."""
    import cv2
    import youtube_video_rag_harvester as H
    for a in aligned:
        for fr in frames:
            if a.get("t") == fr["t"] and a.get("label"):
                img = cv2.imread(fr["path"])
                target = next((e["id"] for e in fr["elements"] if e["label"] == a["label"] and e["box"] == a["box"]), None)
                if img is None or target is None:
                    continue
                dotted, _ = H.draw_dots(img, fr["elements"], must=[target])
                p = fr["path"][:-4] + "_dots.jpg"
                cv2.imwrite(p, dotted, [cv2.IMWRITE_JPEG_QUALITY, 88])
                return p
    return None


def ingest_file(mem: VideoMemory, video: str, app: str, title: str = "", transcript: str = "", screen: str = "ocr", dots: bool = False, whisper_model: str = "base.en",
                transcribe_fn: Callable[..., List[Dict[str, Any]]] = transcribe_file, screen_fn=None, frames_dir: str = "", video_id: str = "", source: str = "") -> Dict[str, Any]:
    import cv2
    vid = video_id or "file_" + hashlib.sha1(os.path.abspath(video).encode()).hexdigest()[:10]
    segs = read_transcript(transcript) if transcript else transcribe_fn(video, whisper_model)
    if not segs:
        return {"video_id": vid, "moments": 0, "why": "no speech found"}
    cap = cv2.VideoCapture(video)
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / (cap.get(cv2.CAP_PROP_FPS) or 25.0)
    cap.release()
    fdir = frames_dir or os.path.join(os.path.dirname(os.path.abspath(mem.path)), "video_memory_frames", vid)
    moments = build_moments(video, segs, fdir, vid, screen, dots, screen_fn)
    r = mem.add_video(vid, app, title or os.path.basename(video), source or os.path.abspath(video), dur, segs, moments)
    return {"video_id": vid, "moments": len(moments), **r}


def ingest_url(mem: VideoMemory, link: str, app: str, screen: str = "ocr", dots: bool = False, max_minutes: float = 20.0, height: int = 480, whisper_model: str = "base.en",
               captions_fn=None, download_fn=None, **kw) -> Dict[str, Any]:
    """YouTube: captions (the harvester's paced, cookie-free fetch) else Whisper on the downloaded video; the first `max_minutes` at `height` p are downloaded (explicit, network)."""
    import youtube_video_rag_harvester as H
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", link) or re.fullmatch(r"([A-Za-z0-9_-]{11})", link)
    if not m:
        raise ValueError(f"not a YouTube link or id: {link}")
    vid = m.group(1)
    cap = (captions_fn or H.fetch_captions)(vid)
    tmp = tempfile.mkdtemp(prefix="vmem_")
    try:
        path = (download_fn or _download_video)(vid, max_minutes, height, tmp)
        if not path:
            return {"video_id": vid, "moments": 0, "why": "download failed"}
        tf = (lambda p, size: cap["segments"]) if cap.get("segments") else transcribe_file
        r = ingest_file(mem, path, app, cap.get("title", ""), "", screen, dots, whisper_model, tf, video_id=vid, source="youtube", **kw)
        return dict(r, captions=cap.get("caption_kind", "none"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _download_video(video_id: str, max_minutes: float, height: int, out_dir: str) -> str:
    import glob
    import youtube_video_rag_harvester as H
    fmt = f"bv*[height<={height}][vcodec^=avc1][ext=mp4]/bv*[height<={height}][ext=mp4]/b[height<={height}][ext=mp4]/b[height<={height}]"
    rc, _o, err = H.run_ytdlp(["-f", fmt, "--download-sections", f"*0-{int(max_minutes * 60)}", "--no-playlist", "--no-warnings", "--sleep-requests", "1.5",
                               "-o", os.path.join(out_dir, f"{video_id}.%(ext)s"), f"https://www.youtube.com/watch?v={video_id}"], 900.0)
    H._check(rc, err)
    files = [f for f in glob.glob(os.path.join(out_dir, f"{video_id}.*")) if not f.endswith((".part", ".ytdl"))]
    return files[0] if files else ""


# ----------------------------------------------------------------------------------------------------------------------------------- CLI
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    default_db = str(ROOT / "data" / "ai_root" / "harvest" / "youtube_rag" / "video_memory_STAGING.db")
    ap.add_argument("--db", default=default_db, help="staging database (NOT the master RAG)")
    ap.add_argument("--embedder", choices=["hash", "bge"], default="hash")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("add-file", "add-url"):
        p = sub.add_parser(name)
        p.add_argument("source")
        p.add_argument("--app", required=True)
        p.add_argument("--screen", choices=["ocr", "som", "none"], default="ocr")
        p.add_argument("--dots", action="store_true")
        p.add_argument("--whisper-model", default="base.en")
        if name == "add-file":
            p.add_argument("--transcript", default="")
            p.add_argument("--title", default="")
        else:
            p.add_argument("--max-minutes", type=float, default=20.0)
            p.add_argument("--height", type=int, default=480)
    ps = sub.add_parser("search")
    ps.add_argument("query")
    ps.add_argument("--app", default="")
    ps.add_argument("-k", type=int, default=5)
    sub.add_parser("stats")
    pr = sub.add_parser("to-rag")
    pr.add_argument("--root", required=True, help="RAG storage root (a temp copy unless the person says otherwise)")
    pr.add_argument("--confirm-ingest", action="store_true")
    a = ap.parse_args(argv)
    mem = VideoMemory(a.db, a.embedder)
    try:
        if a.cmd == "add-file":
            print(json.dumps(ingest_file(mem, a.source, a.app, a.title, a.transcript, a.screen, a.dots, a.whisper_model)))
        elif a.cmd == "add-url":
            print(json.dumps(ingest_url(mem, a.source, a.app, a.screen, a.dots, a.max_minutes, a.height, a.whisper_model)))
        elif a.cmd == "search":
            for r in mem.search(a.query, a.app, a.k):
                print(f"{r['score']:.4f}  {r['title'][:50]}  {r['t0']:.0f}-{r['t1']:.0f}s  {r['link']}\n    {r['speech'][:140]}")
                for al in r["aligned"][:3]:
                    print(f"    -> {al['phrase'][:40]!r} => {al.get('label') or al.get('hotkey')} {al.get('box') or ''}")
        elif a.cmd == "stats":
            print(json.dumps(mem.stats(), indent=1))
        elif a.cmd == "to-rag":
            from core_organs.rag import storage as ST
            from core_organs.rag.router import Rag
            print(json.dumps(mem.to_rag(Rag(ST.Storage(a.root), icons=False), a.confirm_ingest)))
    finally:
        mem.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
