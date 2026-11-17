r"""
youtube_video_rag_harvester.py -- app-tutorial videos -> real-frame training pairs (Set-of-Marks dots) + procedural chains in the master RAG.

    index     app / web-app / website names (or raw queries) -> candidate tutorial videos, METADATA ONLY (yt-dlp flat search), into a resumable ledger
    process   ledger videos -> captions -> parts (chapters / action moments) -> only those seconds downloaded -> keyframes at scene changes
              -> numbered elements (Set-of-Marks) -> `● [id]` dots drawn on the frame -> JSONL pair + chain (Precondition frame -> Action -> Result delta) in causal_procedures_fts
    run       index + process for --query / --apps-file
    seed      clean app names out of the master RAG (or a text file) into a plain list for `index`
    stats     the ledger, counted

Alignment (what ties speech to picture): a spoken instruction (rag.procedures.extract_steps) in the seconds BEFORE a scene change labels the change; the delta box is where the screen changed;
"cursor_like" activity boxes are small moving blobs in the 2 s that end 0.5 s before the change (heuristic: a cursor, a caret and a tooltip all look alike) and are only used to ground a step when no element label matches,
and then the pair says so (`grounding: cursor`). A row without a numbered target or a hotkey is not written. Nothing is drawn or invented: every dot sits on an element the scanner found in the real frame.

Resource rules
  * CPU + disk only. CUDA is hidden before anything is imported (a test asserts torch is never loaded); the process runs at BELOW_NORMAL priority with --threads cv2/OMP threads, so Terminal 1 keeps its cores.
  * No window: every subprocess is CREATE_NO_WINDOW with stdin closed, nothing captures the screen, no application is touched -> nothing can take focus.
  * Polite to YouTube: paced requests, no browser cookies, no account / IP rotation. A refusal (HTTP 429, "confirm you're not a bot") is written to the ledger as a cool-down (30 min, doubling to 6 h) and the
    run STOPS; nothing retries into a block, and no later run starts before the cool-down is over.
  * Disk: clips are deleted after their keyframes are cut; --disk-cap-gb stops the run when frames/ gets too big.
  * The master RAG is written in short transactions with a busy timeout; if another process holds the write lock the chains go to pending_ingest.jsonl and are flushed on the next run.
  * Chains are stored as UNVERIFIED hypotheses (trap_guard says so): a tutorial is evidence, the live scanner decides what is executable. Credential / payment-looking steps are dropped; destructive verbs
    mark the chain HITL_REQUIRED.
"""
from __future__ import annotations

import os

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"                 # zero VRAM, decided before any library can look at the GPU
for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_k, "2")

import argparse
import glob
import hashlib
import importlib.util
import json
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "All codes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MASTER_DB = ROOT / "data" / "hojaiga_master_rag.db"
DOMAIN_OF = {"app": "desktop_app", "web_app": "web_app", "website": "website"}
QUERY_TEMPLATES = {"app": "{app} tutorial", "web_app": "{app} web app tutorial how to use", "website": "{app} website tutorial how to use"}
_QUERY_TAIL = re.compile(r"\b(tutorial|tutorials|walkthrough|beginner|beginners|guide|course|crash course|full|complete|basics|how to use|for beginners|20\d\d)\b", re.I)
_BLOCK_RX = re.compile(r"429|too many requests|confirm you.re not a bot|sign in to confirm|rate.?limit", re.I)
_GONE_RX = re.compile(r"video unavailable|private video|has been removed|not available|members.only|copyright|terminated|age.restricted", re.I)
_SENSITIVE = re.compile(r"password|passcode|\bcvv\b|card number|credit card|\bssn\b|social security|api[ _-]?key|secret|access token|2fa code|one.time (code|password)|seed phrase", re.I)
_DESTRUCTIVE = re.compile(r"\b(delete|erase|wipe|format|uninstall|remove all|reset|purchase|buy|pay|checkout|subscribe|publish|send|submit|deploy)\b", re.I)
SYSTEM_HINT = ("You operate software by reading the numbered dots drawn on the screenshot (● [id] = a control). Reply with a JSON list of actions: "
               '[{"step": 1, "action": "click|hotkey|type", "target_id": <dot id or null>, "hotkey": <keys or null>, "text": <text or null>, "verify_expectation": "<what the screen should show next>"}]')
COOLDOWN_S = (1800, 21600)


class Blocked(Exception):
    """YouTube refused (429 / bot check). The run stops; the ledger remembers the cool-down."""


class VideoGone(Exception):
    pass


_UNSUPPORTED_VERBS = {"scroll", "drag", "drop", "hold", "zoom", "rotate", "pan"}
_POINTING_VERBS = {"click", "double-click", "double click", "right-click", "right click", "select", "choose", "press", "tap", "pick", "open", "toggle", "check", "uncheck"}
_MODIFIERS = {"shift", "ctrl", "control", "alt", "cmd", "win"}
_NAMED_KEYS = {"enter", "return", "tab", "delete", "backspace", "esc", "escape", "space", "home", "end"}


def step_chord(step: Dict[str, Any]) -> str:
    """The key chord of a step: the extractor's own, or one spoken without a plus ('press shift A' -> 'shift+a'): 1-3 modifiers then exactly one key."""
    if step.get("chord"):
        return step["chord"]
    if step.get("verb") not in ("press", "hit", "tap"):
        return ""
    w = re.findall(r"[a-z0-9]+", (step.get("target") or "").lower())
    mods = 0
    while mods < len(w) and w[mods] in _MODIFIERS:
        mods += 1
    if 1 <= mods <= 3 and len(w) == mods + 1 and (len(w[-1]) == 1 or re.fullmatch(r"f\d{1,2}", w[-1]) or w[-1] in _NAMED_KEYS):
        return "+".join("ctrl" if x == "control" else x for x in w)
    return ""


# ----------------------------------------------------------------------------------------------------------------------------------- process hygiene
def polite_process(threads: int = 2) -> None:
    """Below-normal priority and a small thread budget so an overnight run in another terminal keeps its CPU."""
    try:
        import cv2
        cv2.setNumThreads(max(1, threads))
    except Exception:
        pass
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 10)
    except Exception:
        pass


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _ytdlp_cmd() -> List[str]:
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    exe = shutil.which("yt-dlp")
    if not exe:
        raise RuntimeError("yt-dlp is not installed (neither the module nor the executable)")
    return [exe]


def run_ytdlp(args: Sequence[str], timeout: float = 120.0) -> Tuple[int, str, str]:
    """(returncode, stdout, stderr). No window, no stdin, no cookies. A timeout is a failure, not a block."""
    try:
        p = subprocess.run(_ytdlp_cmd() + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL, creationflags=_flags())
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def _check(rc: int, err: str) -> None:
    if rc == 0:
        return
    if _BLOCK_RX.search(err):
        raise Blocked(err.strip().splitlines()[-1][:160] if err.strip() else "blocked")
    if _GONE_RX.search(err):
        raise VideoGone(err.strip().splitlines()[-1][:160])


# ----------------------------------------------------------------------------------------------------------------------------------- ledger
class Ledger:
    """Resumable state: which queries were searched, which videos are waiting / done / skipped, what each produced, and the cool-down after a refusal."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.c = sqlite3.connect(path, timeout=30)
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.executescript("""
            CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS queries(query TEXT PRIMARY KEY, app TEXT, kind TEXT, found INTEGER, ts REAL);
            CREATE TABLE IF NOT EXISTS videos(video_id TEXT PRIMARY KEY, app TEXT, kind TEXT, query TEXT, title TEXT, channel TEXT, duration REAL,
                status TEXT DEFAULT 'indexed', reason TEXT, parts INTEGER DEFAULT 0, pairs INTEGER DEFAULT 0, chains INTEGER DEFAULT 0, updated REAL);
            CREATE TABLE IF NOT EXISTS parts(video_id TEXT, idx INTEGER, t0 REAL, t1 REAL, chapter TEXT, text TEXT, PRIMARY KEY(video_id, idx));
            CREATE TABLE IF NOT EXISTS pairs(pair_id TEXT PRIMARY KEY, video_id TEXT);
        """)
        self.c.commit()

    def close(self) -> None:
        self.c.close()

    def meta(self, k: str, default: str = "") -> str:
        r = self.c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    def set_meta(self, k: str, v: Any) -> None:
        self.c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, str(v)))
        self.c.commit()

    def blocked_until(self) -> float:
        return float(self.meta("blocked_until", "0") or 0)

    def block(self, now: Optional[float] = None) -> float:
        n = int(self.meta("block_count", "0") or 0) + 1
        until = (now or time.time()) + min(COOLDOWN_S[1], COOLDOWN_S[0] * 2 ** (n - 1))
        self.set_meta("block_count", n)
        self.set_meta("blocked_until", until)
        return until

    def unblock_streak(self) -> None:
        if self.meta("block_count", "0") != "0":
            self.set_meta("block_count", 0)

    def query_done(self, q: str) -> bool:
        return self.c.execute("SELECT 1 FROM queries WHERE query=?", (q,)).fetchone() is not None

    def mark_query(self, q: str, app: str, kind: str, found: int) -> None:
        self.c.execute("INSERT OR REPLACE INTO queries VALUES (?,?,?,?,?)", (q, app, kind, found, time.time()))
        self.c.commit()

    def add_video(self, e: Dict[str, Any], app: str, kind: str, query: str) -> bool:
        cur = self.c.execute("INSERT OR IGNORE INTO videos(video_id, app, kind, query, title, channel, duration, updated) VALUES (?,?,?,?,?,?,?,?)",
                             (e["id"], app, kind, query, e.get("title", ""), e.get("channel", ""), float(e.get("duration") or 0), time.time()))
        self.c.commit()
        return cur.rowcount > 0

    def pending(self, limit: int, kind: str = "", frames: bool = False) -> List[Dict[str, Any]]:
        """Videos still to do: 'indexed' ones; a frames pass also takes the 'captioned' ones (captions-only tier already done), indexed first."""
        st = "status IN ('indexed','captioned')" if frames else "status='indexed'"
        q = f"SELECT video_id, app, kind, title, duration FROM videos WHERE {st}" + (" AND kind=?" if kind else "") + " ORDER BY status='captioned', rowid LIMIT ?"
        rows = self.c.execute(q, ((kind, limit) if kind else (limit,))).fetchall()
        return [dict(zip(("video_id", "app", "kind", "title", "duration"), r)) for r in rows]

    def finish(self, vid: str, status: str, reason: str = "", parts: int = 0, pairs: int = 0, chains: int = 0) -> None:
        self.c.execute("UPDATE videos SET status=?, reason=?, parts=?, pairs=?, chains=?, updated=? WHERE video_id=?", (status, reason, parts, pairs, chains, time.time(), vid))
        self.c.commit()

    def save_parts(self, vid: str, parts: Sequence[Dict[str, Any]]) -> None:
        self.c.execute("DELETE FROM parts WHERE video_id=?", (vid,))
        self.c.executemany("INSERT INTO parts VALUES (?,?,?,?,?,?)", [(vid, p["idx"], p["t0"], p["t1"], p.get("chapter", ""), p.get("text", "")[:2000]) for p in parts])
        self.c.commit()

    def pair_seen(self, pid: str) -> bool:
        return self.c.execute("SELECT 1 FROM pairs WHERE pair_id=?", (pid,)).fetchone() is not None

    def pair_add(self, pid: str, vid: str) -> None:
        self.c.execute("INSERT OR IGNORE INTO pairs VALUES (?,?)", (pid, vid))
        self.c.commit()

    def stats(self) -> Dict[str, Any]:
        by = lambda sql: {str(k): v for k, v in self.c.execute(sql).fetchall()}
        return {"queries": self.c.execute("SELECT count(*) FROM queries").fetchone()[0],
                "videos_by_kind": by("SELECT kind, count(*) FROM videos GROUP BY kind"),
                "videos_by_status": by("SELECT status, count(*) FROM videos GROUP BY status"),
                "parts": self.c.execute("SELECT count(*) FROM parts").fetchone()[0],
                "pairs": self.c.execute("SELECT count(*) FROM pairs").fetchone()[0],
                "chains": self.c.execute("SELECT coalesce(sum(chains),0) FROM videos").fetchone()[0],
                "blocked_until": self.blocked_until()}


# ----------------------------------------------------------------------------------------------------------------------------------- search (metadata only)
def app_of_query(q: str) -> str:
    """'Blender tutorial' -> 'Blender'; 'FL Studio beginner' -> 'FL Studio'."""
    s = re.sub(r"\s+", " ", _QUERY_TAIL.sub(" ", q)).strip(" -:,")
    return s or q.strip()


def search_youtube(query: str, n: int = 10, runner: Callable[..., Tuple[int, str, str]] = run_ytdlp) -> List[Dict[str, Any]]:
    """Flat search: id, title, channel, duration. One request, nothing downloaded."""
    rc, out, err = runner(["--flat-playlist", "-J", "--no-warnings", "--skip-download", f"ytsearch{int(n)}:{query}"], 90.0)
    _check(rc, err)
    try:
        data = json.loads(out or "{}")
    except ValueError:
        return []
    return [{"id": e.get("id"), "title": e.get("title") or "", "channel": e.get("channel") or e.get("uploader") or "", "duration": e.get("duration"),
             "live": e.get("live_status") in ("is_live", "is_upcoming")} for e in data.get("entries", []) if e and e.get("id") and len(str(e["id"])) == 11]


def relevant(e: Dict[str, Any], app: str, min_s: float = 120.0, max_s: float = 7200.0) -> bool:
    """A tutorial that names the application, long enough to teach something, not a live stream."""
    if e.get("live"):
        return False
    d = e.get("duration")
    if d is not None and not (min_s <= float(d) <= max_s):
        return False
    title = (e.get("title") or "").lower()
    toks = [t for t in re.findall(r"[a-z0-9]+", app.lower()) if len(t) > 2]
    return all(t in title for t in toks)


# ----------------------------------------------------------------------------------------------------------------------------------- transcript and parts
def fetch_captions(video_id: str, runner: Callable[..., Tuple[int, str, str]] = run_ytdlp) -> Dict[str, Any]:
    """Captions (+ chapters, title, duration) through yt-dlp, paced, cookie-free. {} segments when the video has none."""
    from core_organs.harvest import captions as CAP
    with tempfile.TemporaryDirectory(prefix="yt_caps_") as d:
        rc, _out, err = runner(["--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "en,en-orig", "--sub-format", "json3", "--write-info-json", "--no-playlist", "--no-warnings",
                                "--sleep-requests", "1.5", "--sleep-subtitles", "2", "-o", os.path.join(d, "%(id)s"), f"https://www.youtube.com/watch?v={video_id}"], 120.0)
        files = sorted(glob.glob(os.path.join(d, f"{video_id}*.json3")))
        if rc != 0 and not files:
            _check(rc, err)
        info: Dict[str, Any] = {}
        ip = os.path.join(d, f"{video_id}.info.json")
        if os.path.isfile(ip):
            try:
                info = json.load(open(ip, encoding="utf-8"))
            except ValueError:
                info = {}
        segs = CAP.parse_json3(json.load(open(files[0], encoding="utf-8"))) if files else []
    chapters = [{"t0": float(c["start_time"]), "t1": float(c["end_time"]), "title": c.get("title", "")} for c in info.get("chapters") or []]
    manual = bool(files) and "en" in (info.get("subtitles") or {})
    return {"segments": segs, "chapters": chapters, "duration": info.get("duration"), "title": info.get("title", ""), "caption_kind": "manual" if manual else "auto" if files else "none"}


def make_parts(segments: Sequence[Dict[str, Any]], chapters: Sequence[Dict[str, Any]] = (), max_parts: int = 6, max_len: float = 90.0) -> List[Dict[str, Any]]:
    """Segregate a video into the parts worth downloading: the spans where the speaker DOES something (action moments), named by the chapter they fall in, long ones cut to max_len, the densest
    max_parts kept in time order."""
    from core_organs.harvest import video_pipeline as VP
    from core_organs.rag.procedures import extract_steps
    parts: List[Dict[str, Any]] = []
    for m in VP.action_moments(segments):
        t0 = m["t0"]
        while t0 < m["t1"] - 3.0:
            t1 = min(m["t1"], t0 + max_len)
            words = [s for s in segments if t0 - 0.5 <= float(s["start"]) <= t1]
            text = " ".join(s["text"] for s in words)
            steps = sum(1 for st in extract_steps(text, [text]) if VP.is_ui_action(st))
            chap = next((c["title"] for c in chapters if c["t0"] <= t0 + 1.0 < c["t1"]), "")
            parts.append({"t0": round(t0, 2), "t1": round(t1, 2), "text": text, "chapter": chap, "density": steps / max(t1 - t0, 1.0)})
            t0 = t1
    best = sorted(parts, key=lambda p: -p["density"])[:max_parts]
    best.sort(key=lambda p: p["t0"])
    for i, p in enumerate(best):
        p["idx"] = i
    return best


def download_clip(video_id: str, t0: float, t1: float, out_dir: str, max_height: int = 720, runner: Callable[..., Tuple[int, str, str]] = run_ytdlp) -> str:
    """Only [t0, t1] of the picture track (no audio needed), H.264 preferred. Retried once as a stream copy. '' when nothing was written."""
    fmt = f"bv*[height<={max_height}][vcodec^=avc1][ext=mp4]/bv*[height<={max_height}][ext=mp4]/b[height<={max_height}][ext=mp4]/b[height<={max_height}]"
    for force in (True, False):
        args = ["-f", fmt, "--download-sections", f"*{t0:.2f}-{t1:.2f}", "--no-playlist", "--no-warnings", "--sleep-requests", "1.5", "-o", os.path.join(out_dir, f"{video_id}_clip.%(ext)s"),
                f"https://www.youtube.com/watch?v={video_id}"]
        if force:
            args.insert(4, "--force-keyframes-at-cuts")
        rc, _o, err = runner(args, 420.0)
        files = [f for f in glob.glob(os.path.join(out_dir, f"{video_id}_clip.*")) if not f.endswith((".part", ".ytdl"))]
        if rc == 0 and files:
            return files[0]
        _check(rc, err)
    return ""


# ----------------------------------------------------------------------------------------------------------------------------------- picture side
def activity_regions(clip_path: str, t_clip: float, window_s: float = 2.0, lead_s: float = 0.5, fps: float = 6.0, width: int = 480) -> List[Dict[str, Any]]:
    """Moving blobs in [t - window_s - lead_s, t - lead_s] before a change (the scene sampler only notices a change up to one sample late, so the last `lead_s` seconds may already show its
    consequences), in full-frame pixels. 'cursor_like': small (< 0.4% of the frame, < 12% of its width) -- a pointer, a caret or a tooltip, indistinguishable here; 'ui_change': anything bigger.
    `now` is True for a blob that is present in the LATER frame of its pair (a moved pointer leaves two blobs: where it was and where it is). Oldest first."""
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(clip_path)
    if not cap.isOpened():
        return []
    vfps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W, H = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or width, cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or width * 9 / 16
    sc = W / float(width)
    sh = int(H / sc)
    out: List[Dict[str, Any]] = []
    prev = None
    t = max(0.0, t_clip - lead_s - window_s)
    while t <= t_clip - lead_s:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * vfps))
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(fr, (width, sh), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY), (3, 3), 0)
        if prev is not None:
            m = (cv2.absdiff(prev, g) > 30).astype(np.uint8)
            m = cv2.dilate(m, None, iterations=1)
            n, _lab, stats, _c = cv2.connectedComponentsWithStats(m, connectivity=8)
            for i in range(1, n):
                x, y, w, h, a = (int(v) for v in stats[i])
                if a < 6:
                    continue
                kind = "cursor_like" if (w * h) < 0.004 * width * sh and w < 0.12 * width and h < 0.12 * width else "ui_change"
                out.append({"kind": kind, "box": [int(x * sc), int(y * sc), int(w * sc), int(h * sc)], "t": round(t, 2), "now": _present(prev, g, x, y, w, h)})
        prev = g
        t += 1.0 / fps
    cap.release()
    return out[:40]


def _present(prev, cur, x: int, y: int, w: int, h: int, ring: int = 6) -> bool:
    """Is the object at this box in `cur` (not only in `prev`)? Compare how much the box stands out from its surround in each frame."""
    import numpy as np
    H, W = cur.shape[:2]
    x0, y0, x1, y1 = max(0, x - ring), max(0, y - ring), min(W, x + w + ring), min(H, y + h + ring)

    def contrast(img):
        outer = img[y0:y1, x0:x1].astype(float)
        inner = img[y:y + h, x:x + w].astype(float)
        n_out = outer.size - inner.size
        if n_out <= 0 or inner.size == 0:
            return 0.0
        return abs(inner.mean() - (outer.sum() - inner.sum()) / n_out)
    return bool(contrast(cur) > contrast(prev))


def cursor_point(regions: Sequence[Dict[str, Any]]) -> Optional[Tuple[int, int]]:
    """Where the pointer last was before the change: the latest cursor_like blob's centre."""
    cs = [r for r in regions if r["kind"] == "cursor_like" and r.get("now", True)]
    if not cs:
        return None
    x, y, w, h = cs[-1]["box"]
    return x + w // 2, y + h // 2


def _inside(pt: Tuple[int, int], box: Sequence[int], slack: int = 4) -> bool:
    return box[0] - slack <= pt[0] <= box[0] + box[2] + slack and box[1] - slack <= pt[1] <= box[1] + box[3] + slack


def element_at(som: Dict[str, Any], pt: Tuple[int, int]) -> Optional[Dict[str, Any]]:
    """The smallest numbered element that contains the point."""
    hit = [e for e in som["elements"] if _inside(pt, e["box"])]
    return min(hit, key=lambda e: e["box"][2] * e["box"][3]) if hit else None


def draw_dots(img, elements: Sequence[Dict[str, Any]], must: Sequence[int] = (), regions: Sequence[Dict[str, Any]] = (), delta: Optional[Sequence[int]] = None,
              max_dots: int = 40, min_gap: int = 18) -> Tuple[Any, List[Dict[str, Any]]]:
    """Draw `● [id]` over the elements and return (image, the elements actually drawn). The target is always drawn; elements touching an active region or the delta box come next, then the labelled
    ones by confidence. A dot too close to another is skipped, and the caller lists exactly the drawn ones."""
    import cv2
    h, w = img.shape[:2]
    active = [r["box"] for r in regions] + ([list(delta)] if delta else [])

    def touches(b):
        return any(not (b[0] + b[2] < a[0] or a[0] + a[2] < b[0] or b[1] + b[3] < a[1] or a[1] + a[3] < b[1]) for a in active)

    ok = [e for e in elements if e["box"][2] >= 6 and e["box"][3] >= 6 and 0 <= e["box"][0] < w and 0 <= e["box"][1] < h]
    order = sorted(ok, key=lambda e: (e["id"] not in must, not touches(e["box"]), not (e.get("label") or "").strip(), -float(e.get("conf", 0))))
    out = img.copy()
    placed: List[Tuple[int, int]] = []
    drawn: List[Dict[str, Any]] = []
    palette = [(0, 0, 255), (0, 160, 0), (255, 80, 0), (200, 0, 200), (0, 140, 255), (160, 160, 0)]
    for e in order:
        if len(drawn) >= max_dots and e["id"] not in must:
            continue
        x, y, bw, bh = e["box"]
        c = (x + min(7, bw // 2), y + bh // 2)
        if e["id"] not in must and any((c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2 < min_gap ** 2 for p in placed):
            continue
        col = palette[e["id"] % len(palette)]
        cv2.rectangle(out, (x, y), (x + bw, y + bh), col, 1 if e["id"] not in must else 2)
        cv2.circle(out, c, 5, (255, 255, 255), -1)
        cv2.circle(out, c, 4, col, -1)
        tag = f"[{e['id']}]"
        pos = (min(c[0] + 8, w - 8 * len(tag)), max(10, c[1] + 4))
        cv2.putText(out, tag, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(out, tag, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
        placed.append(c)
        drawn.append(e)
    return out, drawn


# ----------------------------------------------------------------------------------------------------------------------------------- chains and the RAG
_FTS = "CREATE VIRTUAL TABLE IF NOT EXISTS causal_procedures_fts USING fts5(arch_id, domain, goal, steps_json, trap_guard, tokenize='porter unicode61')"
_SIDE = "CREATE TABLE IF NOT EXISTS video_harvest_ingested (chain_id TEXT PRIMARY KEY, fts_rowid INTEGER, video_id TEXT, ts REAL)"


def chain_record(app: str, kind: str, video_id: str, part: Dict[str, Any], steps: Sequence[Dict[str, Any]], evidence: str) -> Dict[str, Any]:
    """One procedure: goal + ordered steps, each Precondition (frame, visible controls) -> Action -> Result delta. evidence = 'video' (frames seen) or 'transcript'."""
    from core_organs.harvest import video_explain as VE
    first = steps[0]
    goal = (part.get("chapter") or first.get("goal") or "").strip() or first.get("goal", "")
    goal = f"{goal} in {app}"
    destructive = any(_DESTRUCTIVE.search(f"{s.get('target', '')} {s.get('goal', '')}") for s in steps)
    guard = ("VIDEO_OBSERVED_UNVERIFIED: derived from a tutorial; confirm the control on the live app before acting."
             + (" HITL_REQUIRED: includes a destructive / outward-facing verb; never auto-execute." if destructive else ""))
    cid = hashlib.sha1(f"{video_id}|{part['t0']}".encode()).hexdigest()[:16]          # one procedure per part, whatever evidence it came from (a frames pass replaces a transcript-only one)
    return {"chain_id": cid, "arch_id": f"VIDEO_{evidence.upper()}", "domain": DOMAIN_OF.get(kind, "desktop_app"), "goal": goal, "trap_guard": guard, "video_id": video_id,
            "steps": [{k: v for k, v in s.items() if k != "goal"} for s in steps]}


def ingest_chains(db_path: str, chains: Sequence[Dict[str, Any]], spool: str, busy_ms: int = 8000) -> Dict[str, int]:
    """Append new chains to causal_procedures_fts (one short transaction). A chain already ingested is skipped; if the database stays locked the chains are spooled, never lost, never blocking."""
    new = {"inserted": 0, "skipped": 0, "spooled": 0}
    if not chains:
        return new
    try:
        conn = sqlite3.connect(str(db_path), timeout=busy_ms / 1000.0)
        conn.execute(f"PRAGMA busy_timeout={busy_ms}")
        try:
            conn.execute(_FTS)
            conn.execute(_SIDE)
            conn.execute("BEGIN IMMEDIATE")
            for ch in chains:
                if conn.execute("SELECT 1 FROM video_harvest_ingested WHERE chain_id=?", (ch["chain_id"],)).fetchone():
                    new["skipped"] += 1
                    continue
                cur = conn.execute("INSERT INTO causal_procedures_fts (arch_id, domain, goal, steps_json, trap_guard) VALUES (?,?,?,?,?)",
                                   (ch["arch_id"], ch["domain"], ch["goal"], json.dumps(ch["steps"], ensure_ascii=False), ch["trap_guard"]))
                conn.execute("INSERT INTO video_harvest_ingested VALUES (?,?,?,?)", (ch["chain_id"], cur.lastrowid, ch["video_id"], time.time()))
                new["inserted"] += 1
            conn.commit()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        os.makedirs(os.path.dirname(spool), exist_ok=True)
        with open(spool, "a", encoding="utf-8") as f:
            for ch in chains:
                f.write(json.dumps(ch, ensure_ascii=False) + "\n")
        return {"inserted": 0, "skipped": 0, "spooled": len(chains)}
    return new


def flush_spool(db_path: str, spool: str) -> Dict[str, int]:
    if not os.path.isfile(spool):
        return {"inserted": 0, "skipped": 0, "spooled": 0}
    with open(spool, encoding="utf-8") as f:
        chains = [json.loads(l) for l in f if l.strip()]
    r = ingest_chains(db_path, chains, spool + ".retry")
    if r["spooled"] == 0:
        os.remove(spool)
        if os.path.isfile(spool + ".retry"):
            os.remove(spool + ".retry")
    else:
        os.replace(spool + ".retry", spool)
    return r


def seed_names(kind: str, db_path: str = str(MASTER_DB), limit: int = 0) -> List[str]:
    """Application / site names that appear in the RAG's own goals ('<task> in <name>'), cleaned of generator debris. Read-only. These are only as real as the rows that mention them."""
    dom = DOMAIN_OF[kind]
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    seen: Dict[str, str] = {}
    for (g,) in c.execute("SELECT goal FROM causal_procedures_fts WHERE domain=?", (dom,)):
        if " in " not in g:
            continue
        name = g.rsplit(" in ", 1)[1].split(" via ")[0].strip()
        if 3 <= len(name) <= 40 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .+&_-]*", name) and not re.search(r"\d{3,}|#|\bpane\b|\bmodal\b|\bpage\b|\bcommand palette\b", name, re.I):
            seen.setdefault(name.lower(), name)
    c.close()
    names = sorted(seen.values(), key=str.lower)
    return names[:limit] if limit else names


# ----------------------------------------------------------------------------------------------------------------------------------- the harvester
class Harvester:
    def __init__(self, root: str = "", db: str = str(MASTER_DB), ingest: bool = True, frames: bool = True, threads: int = 2, max_parts: int = 6, max_clip_s: float = 90.0,
                 max_events: int = 50, max_pairs_per_video: int = 40, som_budget: float = 25.0, disk_cap_gb: float = 20.0, whisper: bool = False, pace: Tuple[float, float] = (3.0, 6.0),
                 max_dots: int = 40, whisper_first: bool = False, whisper_model: str = "base.en", whisper_s: float = 240.0):
        self.whisper_first, self.whisper_model, self.whisper_s = whisper_first, whisper_model, whisper_s
        self.audio_fn: Optional[Callable[[str, float, str], str]] = None                        # (video_id, seconds, out_dir) -> audio path; replaceable for tests
        self.transcribe_fn: Optional[Callable[[str, str], List[Dict[str, Any]]]] = None         # (audio path, model) -> segments
        self.timing: Dict[str, float] = {}
        if not root:
            from core_organs.harvest.paths import harvest_dir
            root = harvest_dir()[0]
        self.root, self.db, self.ingest, self.frames, self.max_parts, self.max_clip_s = root, db, ingest, frames, max_parts, max_clip_s
        self.max_events, self.max_pairs, self.som_budget, self.disk_cap, self.whisper, self.pace, self.max_dots = max_events, max_pairs_per_video, som_budget, disk_cap_gb, whisper, pace, max_dots
        self.work = os.path.join(root, "youtube_rag")
        self.frames_root = os.path.join(self.work, "frames")
        self.out_jsonl = os.path.join(root, "training", "vlm_youtube_visual_dots_dataset.jsonl")
        self.chains_jsonl = os.path.join(self.work, "chains.jsonl")
        self.spool = os.path.join(self.work, "pending_ingest.jsonl")
        for d in (self.work, self.frames_root, os.path.dirname(self.out_jsonl), os.path.join(self.work, "clips")):
            os.makedirs(d, exist_ok=True)
        self.ledger = Ledger(os.path.join(self.work, "ledger.db"))
        self.deadline = float("inf")
        polite_process(threads)
        # replaceable for tests / other back-ends
        self.search_fn: Callable[..., List[Dict[str, Any]]] = search_youtube
        self.captions_fn: Callable[[str], Dict[str, Any]] = fetch_captions
        self.clip_fn: Callable[..., str] = download_clip
        self.som_fn: Optional[Callable[..., Dict[str, Any]]] = None
        self.prefilter_fn: Optional[Callable[[str], Tuple[bool, str]]] = None
        self.sleep_fn: Callable[[float], None] = time.sleep
        self.log: Callable[[str], None] = lambda m: print(m, flush=True)

    def close(self) -> None:
        self.ledger.close()

    # --- guards
    def _guard(self) -> None:
        if time.time() < self.ledger.blocked_until():
            raise Blocked(f"cool-down until {time.strftime('%H:%M', time.localtime(self.ledger.blocked_until()))} after a refusal from YouTube; nothing is requested before then")
        if time.time() > self.deadline:
            raise TimeoutError("time budget used")

    def _on_block(self, why: str) -> None:
        until = self.ledger.block()
        self.log(f"BLOCKED by YouTube ({why}). Stopping; cool-down until {time.strftime('%Y-%m-%d %H:%M', time.localtime(until))}. No cookies / rotation / retry is used.")

    def _pause(self) -> None:
        self.sleep_fn(random.uniform(*self.pace))

    def _disk_gb(self) -> float:
        tot = 0
        for dp, _dn, fn in os.walk(self.frames_root):
            tot += sum(os.path.getsize(os.path.join(dp, f)) for f in fn)
        return tot / 1e9

    # --- index
    def index(self, plans: Sequence[Tuple[str, str, str]], per_query: int = 5) -> Dict[str, int]:
        """plans: (app, kind, query). Metadata only. Resumable: a searched query is never searched again."""
        rep = {"queries": 0, "videos": 0, "skipped_done": 0, "irrelevant": 0}
        for app, kind, q in plans:
            if self.ledger.query_done(q):
                rep["skipped_done"] += 1
                continue
            self._guard()
            try:
                entries = self.search_fn(q, per_query * 3)
            except Blocked as exc:
                self._on_block(str(exc))
                raise
            self.ledger.unblock_streak()
            keep = [e for e in entries if relevant(e, app)]
            rep["irrelevant"] += len(entries) - len(keep)
            added = sum(self.ledger.add_video(e, app, kind, q) for e in keep[:per_query])
            self.ledger.mark_query(q, app, kind, added)
            rep["queries"] += 1
            rep["videos"] += added
            self._pause()
        return rep

    # --- process
    def _som(self, image: str, region=None) -> Dict[str, Any]:
        if self.som_fn is not None:
            return self.som_fn(image, region=region) if region else self.som_fn(image)
        from core_organs.harvest import video_pipeline as VP
        return VP.som_of_frame(image, budget_s=self.som_budget, region=region)

    def _screencast(self, path: str) -> bool:
        fn = self.prefilter_fn
        if fn is None:
            from core_organs.harvest.frame_prefilter import looks_like_screencast as fn
        return bool(fn(path)[0])

    def _row(self, app: str, video_id: str, ev: Dict[str, Any], dotted_rel: str, drawn: Sequence[Dict[str, Any]], goal: str, actions: List[Dict[str, Any]], meta: Dict[str, Any]) -> Dict[str, Any]:
        dots = "\n".join(f"  ● [{e['id']}] {e.get('role', 'control')} " + (json.dumps(e['label'], ensure_ascii=False) if e.get("label") else "(unnamed icon)") + f" at {e['box']}" for e in drawn)
        return {"messages": [{"role": "system", "content": [{"type": "text", "text": SYSTEM_HINT}]},
                             {"role": "user", "content": [{"type": "image", "image": dotted_rel},
                                                          {"type": "text", "text": f"Application: {app}\nGoal: {goal}\nDots on screen:\n{dots}"}]},
                             {"role": "assistant", "content": [{"type": "text", "text": json.dumps(actions, ensure_ascii=False)}]}], "meta": meta}

    def frames_for_part(self, app: str, video_id: str, part: Dict[str, Any], segments: Sequence[Dict[str, Any]], report: Dict[str, int]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """(training rows, chain steps) for one part: the clip is cut, keyframed, scanned, dotted and deleted."""
        import cv2
        from core_organs.harvest import video_explain as VE, video_pipeline as VP
        rel = lambda p: os.path.relpath(p, self.root).replace("\\", "/")
        tmp = tempfile.mkdtemp(prefix="yt_clip_", dir=os.path.join(self.work, "clips"))
        rows: List[Dict[str, Any]] = []
        steps_out: List[Dict[str, Any]] = []
        try:
            self._guard()
            clip = self.clip_fn(video_id, part["t0"], part["t1"], tmp)
            if not clip:
                report["no_clip"] += 1
                return rows, steps_out
            vid_p = f"{video_id}_p{part['idx']}"
            fdir = os.path.join(self.frames_root, video_id)
            kf = VP.extract_keyframes(clip, fdir, vid_p, sample_fps=2.0, max_events=self.max_events)
            used = set()
            for ev in kf:
                if len(rows) >= self.max_pairs:
                    break
                t_clip, t_abs = float(ev["t"]), round(part["t0"] + float(ev["t"]), 2)
                steps = [s for s in VE.steps_before(segments, t_abs, lookback_s=4.0, lookahead_s=1.0) if VE.is_concrete(s)]
                if not steps:
                    report["no_step"] += 1
                    continue
                step = dict(([s for s in steps if s["t"] <= t_abs] or steps)[-1])
                if step.get("verb") in _UNSUPPORTED_VERBS:
                    report["unsupported_verb"] += 1                        # scroll / drag / hold are not a click: the action schema cannot say them, so no pair
                    continue
                step["chord"] = step_chord(step)
                text_blob = f"{step.get('text', '')} {step.get('target', '')} {' '.join(step.get('quoted') or [])}"
                if _SENSITIVE.search(text_blob):
                    report["sensitive_dropped"] += 1
                    continue
                skey = (round(step["t"], 2), step["text"])
                if skey in used:
                    report["step_used"] += 1
                    continue
                pid = hashlib.sha1(f"{video_id}|{t_abs}|{step['text']}".encode()).hexdigest()[:16]
                if self.ledger.pair_seen(pid):
                    report["duplicate"] += 1
                    continue
                if not self._screencast(ev["pre"]):
                    report["not_screencast"] += 1
                    continue
                used.add(skey)
                som = self._som(ev["pre"])
                if not som["elements"]:
                    report["no_elements"] += 1
                    used.discard(skey)
                    continue
                regions = activity_regions(clip, t_clip)
                el = VE.match_element(som, step.get("target", "")) or (VE.match_element(som, step["quoted"][0]) if step.get("quoted") else None)
                grounding = "label" if el else ""
                if not el and not step.get("chord") and step.get("verb") in _POINTING_VERBS:         # the pointer only identifies a target the speaker CLICKED, not "add a plane"
                    pt = cursor_point(regions)
                    el = element_at(som, pt) if pt else None
                    grounding = "cursor" if el else ""
                if step.get("chord"):
                    grounding = grounding or "chord"
                if not grounding:
                    report["ungrounded"] += 1
                    used.discard(skey)
                    continue
                expectation = f"the screen changes in the region {ev['bbox']}" if ev.get("bbox") else "the screen changes"
                if ev.get("bbox") and ev.get("post"):
                    names = VE.clean_labels(self._som(ev["post"], region=tuple(ev["bbox"]))["elements"])
                    if names:
                        expectation = "new on screen: " + ", ".join(names)
                img = cv2.imread(ev["pre"])
                if img is None:
                    continue
                dotted, drawn = draw_dots(img, som["elements"], must=[el["id"]] if el else [], regions=regions, delta=ev.get("bbox"), max_dots=self.max_dots)
                dpath = ev["pre"][:-4] + "_dots.jpg"
                cv2.imwrite(dpath, dotted, [cv2.IMWRITE_JPEG_QUALITY, 88])
                actions = [VE._action(step, el["id"] if el else None, expectation)]
                goal = VE.goal_text(step)
                meta = {"pair_id": pid, "provenance": "youtube_real_frame", "app_key": app, "video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}&t={int(t_abs)}s",
                        "part": part["idx"], "t": t_abs, "pre": rel(ev["pre"]), "post": rel(ev.get("post", "")), "dotted": rel(dpath), "delta_bbox": ev.get("bbox"), "grounding": grounding,
                        "activity": regions[-6:], "spoken": step["text"], "dots": [e["id"] for e in drawn], "som_elements": len(som["elements"])}
                rows.append(self._row(app, video_id, ev, rel(dpath), drawn, goal, actions, meta))
                a = actions[0]
                steps_out.append({"step": len(steps_out) + 1, "action": a["action"], "target": (el or {}).get("label") or step.get("target", ""), "target_id": a.get("target_id"),
                                  "hotkey": a.get("hotkey"), "goal": goal,
                                  "precondition": {"frame": rel(ev["pre"]), "dotted": rel(dpath), "visible": VE.clean_labels(som["elements"], 10)},
                                  "expected_delta": expectation, "source_ref": f"{video_id}@{int(t_abs)}", "grounding": grounding})
                self.ledger.pair_add(pid, video_id)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return rows, steps_out

    def transcript_steps(self, part: Dict[str, Any], segments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Frame-less procedure for a part: its concrete spoken steps in order (precondition and result are NOT observed -- the chain says so)."""
        from core_organs.harvest import video_explain as VE
        from core_organs.rag.procedures import extract_steps
        seg = [s for s in segments if part["t0"] <= float(s["start"]) <= part["t1"]]
        out: List[Dict[str, Any]] = []
        for u in VE.utterances(seg):
            for st in extract_steps(u["text"]):
                st = dict(st, chord=step_chord(st))
                if st.get("verb") in _UNSUPPORTED_VERBS or not (st["chord"] or st.get("verb") in _POINTING_VERBS):
                    continue
                if VE.is_concrete(st) and not _SENSITIVE.search(f"{st.get('text', '')} {st.get('target', '')}"):
                    out.append({"step": len(out) + 1, "action": "hotkey" if st.get("chord") else "click", "target": st.get("target", ""), "target_id": None, "hotkey": st.get("chord") or None,
                                "goal": VE.goal_text(st), "precondition": {"frame": None, "note": "not observed (transcript only)"}, "expected_delta": "", "source_ref": f"@{int(u['start'])}"})
        return out

    def process_video(self, v: Dict[str, Any]) -> Dict[str, Any]:
        vid, app, kind = v["video_id"], v["app"], v["kind"]
        self._guard()
        self.timing = {}
        try:
            cap = {"segments": self._whisper(vid), "chapters": []} if self.whisper_first else self.captions_fn(vid)     # whisper-first never touches the caption endpoint
        except VideoGone as exc:
            self.ledger.finish(vid, "skipped", f"gone: {exc}")
            return {"video": vid, "status": "skipped"}
        except Blocked as exc:
            self._on_block(str(exc))
            raise
        self.ledger.unblock_streak()
        segs = cap.get("segments") or []
        if not segs and self.whisper and not self.whisper_first:
            segs = self._whisper(vid)
        if not segs:
            self.ledger.finish(vid, "skipped", "no_speech" if self.whisper_first else "no_captions")
            return {"video": vid, "status": "skipped", "why": "no speech" if self.whisper_first else "no captions", "timing": self.timing}
        parts = make_parts(segs, cap.get("chapters") or [], self.max_parts, self.max_clip_s)
        self.ledger.save_parts(vid, parts)
        if not parts:
            self.ledger.finish(vid, "skipped", "no_action_moments")
            return {"video": vid, "status": "skipped", "why": "no action moments"}
        rep = {k: 0 for k in ("no_clip", "no_step", "unsupported_verb", "sensitive_dropped", "step_used", "duplicate", "not_screencast", "no_elements", "ungrounded")}
        chains: List[Dict[str, Any]] = []
        n_rows = 0
        for part in parts:
            if time.time() > self.deadline or (self.frames and self._disk_gb() > self.disk_cap):
                break
            rows, steps = ([], [])
            if self.frames:
                try:
                    rows, steps = self.frames_for_part(app, vid, part, segs, rep)
                except Blocked as exc:
                    self._on_block(str(exc))
                    raise
                except VideoGone:
                    rep["no_clip"] += 1
                if rows:
                    with open(self.out_jsonl, "a", encoding="utf-8") as f:
                        for r in rows:
                            f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    n_rows += len(rows)
            evidence = "video"
            if not steps:
                steps, evidence = self.transcript_steps(part, segs), "transcript"
            if steps:
                chains.append(chain_record(app, kind, vid, part, steps, evidence))
            if self.frames:
                self._pause()                                                         # a clip download is a request; a part of a transcript is not
        if chains:
            with open(self.chains_jsonl, "a", encoding="utf-8") as f:
                for ch in chains:
                    f.write(json.dumps(ch, ensure_ascii=False) + "\n")
        res = ingest_chains(self.db, chains, self.spool) if (self.ingest and chains) else {"inserted": 0, "skipped": 0, "spooled": 0}
        self.ledger.finish(vid, "done" if self.frames else "captioned", json.dumps(rep), parts=len(parts), pairs=n_rows, chains=len(chains))
        return {"video": vid, "status": "done", "parts": len(parts), "pairs": n_rows, "chains": len(chains), "rag": res, "drops": {k: v for k, v in rep.items() if v}, "timing": self.timing}

    @staticmethod
    def local_transcribe(path: str, model_size: str = "base.en") -> List[Dict[str, Any]]:
        """faster-whisper on the CPU (int8) from a model already in the cache. The audio is decoded here with ffmpeg (16 kHz mono) and passed as samples: faster-whisper's own loader fails with the PyAV
        version installed in hojaiga_env (`open() got an unexpected keyword argument 'metadata_errors'`)."""
        import numpy as np
        p = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"], capture_output=True, stdin=subprocess.DEVNULL, creationflags=_flags())
        if p.returncode != 0 or not p.stdout:
            raise RuntimeError("ffmpeg could not decode the audio: " + p.stderr.decode("utf-8", "replace")[:160])
        audio = np.frombuffer(p.stdout, dtype=np.float32)
        from faster_whisper import WhisperModel
        model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=int(os.environ.get("OMP_NUM_THREADS", "2")))
        segs, _info = model.transcribe(audio, vad_filter=True)
        return [{"text": s.text.strip(), "start": float(s.start), "duration": float(s.end - s.start)} for s in segs if s.text.strip()]

    def _fetch_audio(self, vid: str, seconds: float, out_dir: str) -> str:
        rc, _o, err = run_ytdlp(["-f", "bestaudio[ext=m4a]/bestaudio", "--download-sections", f"*0-{int(seconds)}", "--no-playlist", "--no-warnings", "-o", os.path.join(out_dir, "%(id)s.%(ext)s"),
                                 f"https://www.youtube.com/watch?v={vid}"], 300.0)
        _check(rc, err)
        files = [f for f in glob.glob(os.path.join(out_dir, f"{vid}.*")) if not f.endswith((".part", ".ytdl"))]
        return files[0] if files else ""

    def _whisper(self, vid: str) -> List[Dict[str, Any]]:
        """Local speech recognition (CPU int8, a model already on disk) of the first `whisper_s` seconds. self.timing keeps audio_download_s / transcribe_s / audio_s for the report."""
        from core_organs.harvest import video_pipeline as VP
        with tempfile.TemporaryDirectory(prefix="yt_audio_") as d:
            t = time.perf_counter()
            path = (self.audio_fn or self._fetch_audio)(vid, self.whisper_s, d)
            self.timing["audio_download_s"] = round(time.perf_counter() - t, 1)
            if not path:
                return []
            t = time.perf_counter()
            segs = (self.transcribe_fn or self.local_transcribe)(path, self.whisper_model)
            self.timing["transcribe_s"] = round(time.perf_counter() - t, 1)
            self.timing["speech_s"] = round(max((float(s["start"]) + float(s.get("duration", 0)) for s in segs), default=0.0), 1)
            return segs

    def process(self, max_videos: int = 10, kind: str = "") -> Dict[str, Any]:
        sp = flush_spool(self.db, self.spool) if self.ingest else {}
        total = {"videos": 0, "done": 0, "skipped": 0, "pairs": 0, "chains": 0, "spool_flushed": sp.get("inserted", 0)}
        for v in self.ledger.pending(max_videos, kind, self.frames):
            if time.time() > self.deadline:
                break
            if self.frames and self._disk_gb() > self.disk_cap:
                self.log(f"frames/ is over {self.disk_cap} GB: stopping (raise --disk-cap-gb or move the data)")
                break
            try:
                r = self.process_video(v)
            except Blocked:
                total["blocked"] = True
                break
            except TimeoutError:
                break
            except Exception as exc:
                self.ledger.finish(v["video_id"], "error", f"{type(exc).__name__}: {exc}"[:200])
                self.log(f"{v['video_id']} error: {exc}")
                continue
            total["videos"] += 1
            total["done" if r["status"] == "done" else "skipped"] += 1
            total["pairs"] += r.get("pairs", 0)
            total["chains"] += r.get("chains", 0)
            self.log(json.dumps(r, ensure_ascii=False))
            self._pause()
        return total


# ----------------------------------------------------------------------------------------------------------------------------------- CLI
def _plans(args) -> List[Tuple[str, str, str]]:
    plans: List[Tuple[str, str, str]] = []
    for q in args.query or []:
        plans.append((app_of_query(q), args.kind, q))
    if args.apps_file:
        for line in Path(args.apps_file).read_text(encoding="utf-8").splitlines():
            name = line.strip()
            if name and not name.startswith("#"):
                plans.append((name, args.kind, QUERY_TEMPLATES[args.kind].format(app=name)))
    return plans


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--root", default="", help="harvest directory (default: the RAG's harvest dir)")
        p.add_argument("--db", default=str(MASTER_DB), help="database that receives the chains")
        p.add_argument("--no-ingest", action="store_true", help="write JSONL / chains.jsonl only; do not touch the database")
        p.add_argument("--no-frames", action="store_true", help="captions-only tier: transcript chains, no clip download, no pairs (cheap, no GPU/OCR)")
        p.add_argument("--threads", type=int, default=2)
        p.add_argument("--budget-minutes", type=float, default=0, help="stop after this many minutes (0 = no limit)")
        p.add_argument("--disk-cap-gb", type=float, default=20.0)
        p.add_argument("--whisper", action="store_true", help="local CPU speech recognition for videos without captions")
        p.add_argument("--whisper-first", action="store_true", help="transcribe the first --whisper-seconds of every video locally (CPU) and never call YouTube's caption endpoint")
        p.add_argument("--whisper-model", default="base.en", help="a faster-whisper model already in the Hugging Face cache (base.en, tiny.en, small)")
        p.add_argument("--whisper-seconds", type=float, default=240.0)
        p.add_argument("--max-parts", type=int, default=6)
        p.add_argument("--max-clip-s", type=float, default=90.0)
        p.add_argument("--pace", default="3,6", help="seconds to wait between requests, 'min,max' (random in between); raise it after a 429, e.g. 25,45")

    def selection(p):
        p.add_argument("--query", action="append", help='raw search, e.g. "Blender tutorial" (repeatable)')
        p.add_argument("--apps-file", help="one name per line")
        p.add_argument("--kind", choices=sorted(DOMAIN_OF), default="app")
        p.add_argument("--per-query", type=int, default=5)

    for name in ("index", "process", "run"):
        p = sub.add_parser(name)
        common(p)
        if name != "process":
            selection(p)
        if name != "index":
            p.add_argument("--max-videos", type=int, default=10)
            if name == "process":
                p.add_argument("--kind", choices=sorted(DOMAIN_OF), default="")
    ps = sub.add_parser("seed")
    ps.add_argument("--kind", choices=sorted(DOMAIN_OF), default="app")
    ps.add_argument("--db", default=str(MASTER_DB))
    ps.add_argument("--out", required=True)
    ps.add_argument("--limit", type=int, default=0)
    st = sub.add_parser("stats")
    st.add_argument("--root", default="")
    ic = sub.add_parser("ingest-chains", help="load chains.jsonl (written by --no-ingest runs) into the RAG; frame-observed chains win over transcript-only ones")
    ic.add_argument("--root", default="")
    ic.add_argument("--db", default=str(MASTER_DB))
    a = ap.parse_args(argv)

    if a.cmd == "ingest-chains":
        root = a.root or __import__("core_organs.harvest.paths", fromlist=["x"]).harvest_dir()[0]
        path = os.path.join(root, "youtube_rag", "chains.jsonl")
        with open(path, encoding="utf-8") as f:
            chains = [json.loads(l) for l in f if l.strip()]
        chains.sort(key=lambda c: c["arch_id"] != "VIDEO_VIDEO")                # stable: observed evidence is inserted first, so it keeps the chain_id
        tot = {"inserted": 0, "skipped": 0, "spooled": 0}
        for i in range(0, len(chains), 200):
            r = ingest_chains(a.db, chains[i:i + 200], os.path.join(root, "youtube_rag", "pending_ingest.jsonl"))
            for k in tot:
                tot[k] += r[k]
        print(json.dumps({"chains_read": len(chains), **tot}))
        return 0

    if a.cmd == "seed":
        names = seed_names(a.kind, a.db, a.limit)
        Path(a.out).write_text("\n".join(names) + "\n", encoding="utf-8")
        print(f"{len(names)} {a.kind} names -> {a.out}")
        return 0
    if a.cmd == "stats":
        root = a.root or __import__("core_organs.harvest.paths", fromlist=["x"]).harvest_dir()[0]
        print(json.dumps(Ledger(os.path.join(root, "youtube_rag", "ledger.db")).stats(), indent=1))
        return 0

    lo, hi = (float(x) for x in a.pace.split(","))
    h = Harvester(a.root, a.db, not a.no_ingest, not a.no_frames, a.threads, a.max_parts, a.max_clip_s, disk_cap_gb=a.disk_cap_gb, whisper=a.whisper, pace=(lo, hi),
                  whisper_first=a.whisper_first, whisper_model=a.whisper_model, whisper_s=a.whisper_seconds)
    if a.budget_minutes:
        h.deadline = time.time() + a.budget_minutes * 60
    try:
        if a.cmd in ("index", "run"):
            plans = _plans(a)
            if not plans:
                ap.error("give --query and/or --apps-file")
            h.log("index: " + json.dumps(h.index(plans, a.per_query)))
        if a.cmd in ("process", "run"):
            res = h.process(a.max_videos, getattr(a, "kind", "") if a.cmd == "process" else "")
            h.log("process: " + json.dumps(res))
            if res.get("blocked"):
                print(json.dumps(h.ledger.stats()))
                return 2                                                          # refused mid-run: same exit code as a refused index
    except Blocked as exc:
        print(f"stopped: {exc}")
        return 2                                                                  # exit code 2 = refused by YouTube: a driver must stop
    except TimeoutError as exc:
        print(f"budget used: {exc}")                                              # exit code 0: the time budget ending is normal
        print(json.dumps(h.ledger.stats()))
        return 0
    print(json.dumps(h.ledger.stats()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
