"""
harvest.consolidate -- MANY tutorial videos of ONE application -> one consolidated graph of what can be done in it.

    python -m core_organs.harvest.consolidate fetch  --app "FL Studio" --n 3            download n tutorial videos (explicit command, polite, no proxies / no cookie tricks)
    python -m core_organs.harvest.consolidate ingest --app flstudio --videos a.mp4 b.mp4 [--label] [--transcripts a.json b.json]
    python -m core_organs.harvest.consolidate report --app flstudio                      videos, edges, shared vs unique, growth per video
    python -m core_organs.harvest.consolidate export-rag --app flstudio --name "FL Studio"
    python -m core_organs.harvest.consolidate export-training --app flstudio             prompt-v1 rows (picture + Set-of-Marks) into harvest/training, one row per VIDEO that shows the action

The idea (diagrams 1-3): every video is cut into ACTION EVENTS (a pre frame, a settled post frame, what changed). An event is described without any language or pixel-exact
coordinates: the layout signature of the screen before and after (edge density on a grid, so dark/light themes and resolutions agree), WHERE it changed (normalised box) and WHAT
changed (an edge fingerprint of the changed crop). Events from different videos that agree on all three are the SAME edge of the app's graph: their support grows (a shared, baseline
action). An event nobody else shows stays its own edge with support 1 and is kept, flagged `unique` (the hidden preference, the rare submenu): common output is merged, rare output is
never discarded. Adding a video can only add edges or support, so the graph keeps growing with more videos of the same app.

What this module does NOT do: it never touches a live screen, a running application or the existing scanner / RAG / adapters. Its outputs enter through the existing doors:
`rag_feed.write_workflow` (RAG), `video_explain.build_row` (training rows), and `video_graph_live` (a flag-gated hint). Labels come from the speaker's words (if a transcript is given)
or OCR of the changed region (if `--label`); an edge with no label is kept in the graph for the picture-only uses and is NOT written to the RAG as an anonymous step.

Everything is derived from the frames and the transcript: no application name, control name, resolution or language is written into this file.
"""
from __future__ import annotations

import argparse
from shutil import copy2 as shutil_copy
import contextlib
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
GRAPH_DIR = os.path.join(DATA, "video_graph")

GRID = (24, 14)                    # columns x rows of the layout signature
NORM = (384, 216)                  # every frame is looked at on this canvas (after its letterbox is cropped off)
LOC_NORM = tuple(int(x) for x in os.environ.get("HOJAIGA_VG_LOC", "384x216").split("x"))   # canvas the control crops are cut on / searched on live. 384x216 is the size validated on the synthetic app
#   (edge-map matching there: right control 0.84-0.88, next-best place 0.56-0.66). 768x432 was measured WORSE (lossy-video noise shows at that size). Real 1080p recordings are NOT validated yet.
SAME_OBJECT_SIM = 0.25             # a changed blob is a pressed / lit-up control only if its edge pattern survives the change this well
DELTA_THRESH = 25                  # grey levels
MIN_COMP_FRAC = 0.0004             # a changed blob smaller than this share of the frame is noise (cursor trail, compression)
MERGE_SIM = 0.55                   # events at least this similar are the same edge
MIN_BOX_IOU = 0.50                 # ... and changed in (about) the same place
MIN_DELTA_SIM = 0.40               # ... and the changed crop looks alike
STATE_SIM = 0.97                   # two screens at least this similar are the same state node
LIVE_MATCH_SIM = 0.90
MAX_CHANGED_FRAC = 0.30            # more than this share of the PIXELS changed = a page change / scene cut / zoom, not an action on a control (a big dialog changes ~14%: its box is large, its pixels are not)
INSET_GROW = 1.7                   # a detected webcam face is masked with this much margin around it (the bubble is bigger than the face)


# ------------------------------------------------------------------------------------------------------------------ pictures
def _to_gray(img: Any) -> np.ndarray:
    """path | PIL image | BGR/gray ndarray -> uint8 grey."""
    import cv2
    if isinstance(img, (str, os.PathLike)):
        a = cv2.imdecode(np.fromfile(str(img), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if a is None:
            raise FileNotFoundError(str(img))
        return a
    if hasattr(img, "convert"):
        return np.asarray(img.convert("L"))
    a = np.asarray(img)
    if a.ndim == 3:
        a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    return a.astype(np.uint8)


def crop_box(g: np.ndarray) -> Tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the picture without its letterbox / pillarbox (rows and columns that are one flat colour at the edge)."""
    h, w = g.shape
    row_flat = g.std(axis=1) < 3.0
    col_flat = g.std(axis=0) < 3.0
    y0 = 0
    while y0 < h - 1 and row_flat[y0]:
        y0 += 1
    y1 = h
    while y1 > y0 + 1 and row_flat[y1 - 1]:
        y1 -= 1
    x0 = 0
    while x0 < w - 1 and col_flat[x0]:
        x0 += 1
    x1 = w
    while x1 > x0 + 1 and col_flat[x1 - 1]:
        x1 -= 1
    if (x1 - x0) < 0.5 * w or (y1 - y0) < 0.5 * h:         # a mostly-flat screen is not a border: use all of it
        return 0, 0, w, h
    return x0, y0, x1, y1


def _canvas(g: np.ndarray, box: Optional[Tuple[int, int, int, int]] = None, size: Tuple[int, int] = NORM) -> np.ndarray:
    import cv2
    x0, y0, x1, y1 = box or crop_box(g)
    return cv2.resize(g[y0:y1, x0:x1], size, interpolation=cv2.INTER_AREA)


def layout_signature(canvas: np.ndarray) -> np.ndarray:
    """Edge density per grid cell, square-rooted and unit length: the same screen at another size, theme or compression gives (nearly) the same vector."""
    import cv2
    e = cv2.Canny(cv2.GaussianBlur(canvas, (3, 3), 0), 50, 150).astype(np.float32) / 255.0
    cells = cv2.resize(e, GRID, interpolation=cv2.INTER_AREA)
    v = np.sqrt(cells).ravel()
    n = float(np.linalg.norm(v))
    return (v / n) if n > 1e-6 else v


def _edges(canvas: np.ndarray) -> np.ndarray:
    import cv2
    return cv2.Canny(cv2.GaussianBlur(canvas, (3, 3), 0), 50, 150).astype(np.float32) / 255.0


def crop_signature(canvas: np.ndarray, box: Sequence[float], size: int = 16, normalize: bool = True) -> np.ndarray:
    """Edge-density fingerprint of a normalised box of the canvas (unit length). The edges are found on the whole canvas first, then the box is pooled to size x size:
    a big region keeps its structure (down-scaling the pixels before the edge detector would erase it)."""
    import cv2
    H, W = canvas.shape
    x0, y0 = int(box[0] * W), int(box[1] * H)
    x1, y1 = max(int(box[2] * W), x0 + 2), max(int(box[3] * H), y0 + 2)
    e = _edges(canvas)[y0:y1, x0:x1]
    if e.size == 0:
        return np.zeros(size * size, np.float32)
    v = np.sqrt(cv2.resize(e, (size, size), interpolation=cv2.INTER_AREA)).ravel()
    if not normalize:
        return v
    n = float(np.linalg.norm(v))
    return (v / n) if n > 1e-6 else v


def edge_density(canvas: np.ndarray, box: Sequence[float]) -> float:
    H, W = canvas.shape
    x0, y0, x1, y1 = int(box[0] * W), int(box[1] * H), max(int(box[2] * W), int(box[0] * W) + 2), max(int(box[3] * H), int(box[1] * H) + 2)
    e = _edges(canvas)[y0:y1, x0:x1]
    return float(e.mean()) if e.size else 0.0


def cos(a: Sequence[float], b: Sequence[float]) -> float:
    a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def box_iou(a: Sequence[float], b: Sequence[float]) -> float:
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 1e-9 else 0.0


def delta_components(pre: np.ndarray, post: np.ndarray) -> Dict[str, Any]:
    """What changed between two canvases: `union` (normalised box of everything) and `comps` (normalised boxes of each changed blob, largest first)."""
    import cv2
    d = cv2.absdiff(pre, post)
    m = ((d > DELTA_THRESH).astype(np.uint8)) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(m)
    H, W = m.shape
    comps = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area >= MIN_COMP_FRAC * W * H:
            comps.append({"box": [x / W, y / H, (x + w) / W, (y + h) / H], "area": float(area) / (W * H)})
    comps.sort(key=lambda c: -c["area"])
    if not comps:
        return {"union": None, "primary": None, "comps": []}
    u = [min(c["box"][0] for c in comps), min(c["box"][1] for c in comps), max(c["box"][2] for c in comps), max(c["box"][3] for c in comps)]
    # `primary` = the largest changed blob (what appeared / disappeared); the union also contains the pointer's jump and a webcam bubble, which say nothing about the action
    return {"union": u, "primary": comps[0]["box"], "comps": comps[:4], "changed": float((m > 0).mean())}


# ------------------------------------------------------------------------------------------------------------------ observations
def detect_inset(frames: Sequence[str], max_frames: int = 16, max_frac: float = 0.12) -> Optional[List[float]]:
    """Normalised box of a webcam bubble: a face that is small (< max_frac of the frame) and sits in the SAME place in several sampled frames. None when there is none.
    Found by faces, not by application: whatever the presenter's bubble covers is masked before any change is measured."""
    import cv2
    if not frames:
        return None
    casc = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    step = max(1, len(frames) // max_frames)
    boxes = []
    for f in list(frames)[::step][:max_frames]:
        g = _to_gray(f)
        H, W = g.shape
        sc = 640.0 / W if W > 640 else 1.0
        gg = cv2.resize(g, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA) if sc != 1.0 else g
        for (x, y, w, h) in casc.detectMultiScale(gg, scaleFactor=1.15, minNeighbors=5, minSize=(24, 24)):
            if (w * h) / float(gg.shape[0] * gg.shape[1]) <= max_frac:
                boxes.append([x / gg.shape[1], y / gg.shape[0], (x + w) / gg.shape[1], (y + h) / gg.shape[0]])
    if len(boxes) < 3:
        return None
    med = np.median(np.array(boxes), axis=0)
    close = [b for b in boxes if box_iou(b, med.tolist()) >= 0.3]
    if len(close) < 3:
        return None
    m = np.median(np.array(close), axis=0)
    cx, cy, w, h = (m[0] + m[2]) / 2, (m[1] + m[3]) / 2, (m[2] - m[0]) * INSET_GROW, (m[3] - m[1]) * INSET_GROW
    return [max(0.0, cx - w / 2), max(0.0, cy - h / 2), min(1.0, cx + w / 2), min(1.0, cy + h / 2)]


def _mask_inset(g: np.ndarray, mask: Optional[Sequence[float]]) -> np.ndarray:
    if not mask:
        return g
    H, W = g.shape
    out = g.copy()
    out[int(mask[1] * H):int(mask[3] * H) + 1, int(mask[0] * W):int(mask[2] * W) + 1] = 128
    return out


def observation_from_pair(pre_img: Any, post_img: Any, video_id: str, t: float, pre_path: str = "", post_path: str = "", crops_dir: str = "",
                          labels: Sequence[str] = (), kind: str = "click", step_text: str = "", mask: Optional[Sequence[float]] = None) -> Optional[Dict[str, Any]]:
    """One action event -> the language-free description the graph works with. None when nothing changed."""
    import cv2
    g_pre, g_post = _mask_inset(_to_gray(pre_img), mask), _mask_inset(_to_gray(post_img), mask)
    box = crop_box(g_pre)
    a, b = _canvas(g_pre, box), _canvas(g_post, box if g_post.shape == g_pre.shape else None)
    dc = delta_components(a, b)
    if not dc["union"]:
        return None
    prim = dc["primary"]
    page_change = dc.get("changed", 0.0) > MAX_CHANGED_FRAC
    d_pre, d_post = edge_density(a, prim), edge_density(b, prim)
    direction = 1 if d_post > d_pre * 1.15 else (-1 if d_pre > d_post * 1.15 else 0)          # +1 = something appeared there (a menu, a dialog), -1 = it went away
    # the SIGNED change inside the changed box (post minus pre edge density): A->B and B->A point in opposite directions, so they can never be mistaken for one action
    # plus how the changed region LOOKS afterwards; cos() of the two halves together is the mean of "looks alike" and "changed the same way"
    diff = crop_signature(b, prim, normalize=False) - crop_signature(a, prim, normalize=False)
    ds = np.concatenate([crop_signature(b, prim), diff / max(float(np.linalg.norm(diff)), 1e-6)])
    obs: Dict[str, Any] = {
        "video": video_id, "t": round(float(t), 2), "pre": pre_path, "post": post_path,
        "src_sig": [round(float(x), 4) for x in layout_signature(a)], "dst_sig": [round(float(x), 4) for x in layout_signature(b)],
        "union": [round(x, 4) for x in dc["union"]], "primary": [round(x, 4) for x in prim], "dir": direction, "comps": dc["comps"], "changed": round(dc.get("changed", 0.0), 4),
        "delta_sig": [round(float(x), 4) for x in ds],
        "labels": [l for l in labels if l], "kind": kind, "step_text": step_text[:200], "page_change": page_change,
        "frame_px": [int(g_pre.shape[1]), int(g_pre.shape[0])], "crop_px": list(box),
    }
    # opener candidates: the small blobs that are the SAME OBJECT before and after (a button that turned pressed, a menu title that lit up) - not content that moved or appeared, not the pointer.
    # Their crops come from the PRE frame at LOC_NORM resolution, so they show the control as it looked before the click and are big enough to find again.
    if crops_dir:
        os.makedirs(crops_dir, exist_ok=True)
        a_hi, b_hi = _canvas(g_pre, box, LOC_NORM), _canvas(g_post, box if g_post.shape == g_pre.shape else None, LOC_NORM)
        big = dc["comps"][0]["area"]
        cands = [c for c in dc["comps"] if c["area"] < 0.6 * big] or []
        saved = []
        for i, c in enumerate(cands[:4]):
            if len(saved) >= 2:
                break
            bx = c["box"]
            pad = 0.004
            x0, y0 = max(0.0, bx[0] - pad), max(0.0, bx[1] - pad)
            x1, y1 = min(1.0, bx[2] + pad), min(1.0, bx[3] + pad)
            H, W = a_hi.shape
            crop = a_hi[int(y0 * H):int(y1 * H) + 1, int(x0 * W):int(x1 * W) + 1]
            crop_after = b_hi[int(y0 * H):int(y1 * H) + 1, int(x0 * W):int(x1 * W) + 1]
            if crop.size == 0 or min(crop.shape) < 8:
                continue
            if cos(crop_signature(a_hi, [x0, y0, x1, y1]), crop_signature(b_hi, [x0, y0, x1, y1])) < SAME_OBJECT_SIM:
                continue
            key = hashlib.sha1(f"{video_id}|{t}|{i}".encode()).hexdigest()[:12]
            p = os.path.join(crops_dir, f"{key}.png")
            cv2.imencode(".png", crop)[1].tofile(p)
            saved.append({"path": p, "box": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]})
        obs["opener_crops"] = saved
    return obs


def obs_similarity(o: Dict[str, Any], e: Dict[str, Any]) -> float:
    """How alike an observation and an edge's representative are (0..1). 0 when the change is not in the same place, does not look alike, or goes the other way
    (opening a dialog and closing it change the same box, so the direction decides)."""
    if o.get("dir", 0) * e.get("dir", 0) < 0:
        return 0.0
    iou = box_iou(o["primary"], e["primary"])
    sd = cos(o["delta_sig"], e["delta_sig"])
    if iou < MIN_BOX_IOU or sd < MIN_DELTA_SIM:
        return 0.0
    return 0.15 * cos(o["src_sig"], e["src_sig"]) + 0.15 * cos(o["dst_sig"], e["dst_sig"]) + 0.2 * iou + 0.5 * sd


# ------------------------------------------------------------------------------------------------------------------ the graph
def _norm_label(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s&+.-]", " ", s or "")).strip().lower()


_GENERIC = {"the", "a", "an", "this", "that", "these", "those", "tool", "tools", "button", "buttons", "icon", "icons", "menu", "menus", "option", "options", "tab", "tabs", "panel",
            "bar", "from", "in", "on", "at", "to", "of", "and", "or", "your", "our", "my", "its", "it", "here", "there", "up", "top", "side", "left", "right", "then", "now", "also", "just"}
_CHORD_RX = re.compile(r"^(?:(?:ctrl|control|shift|alt|cmd|command|win|meta)\+)+[a-z0-9]+$|^f\d{1,2}$")


def label_key(s: str) -> str:
    """The identity of a spoken / written control name across authors: 'the Rectangle tool', 'rectangle' and 'Rectangle button' are one key; a key chord is its normalised chord. '' = nothing concrete."""
    t = (s or "").lower().strip()
    c = t.replace(" ", "")
    if _CHORD_RX.match(c):
        return c.replace("control", "ctrl").replace("command", "cmd")
    toks = [w for w in re.findall(r"[a-z0-9]+", t) if w not in _GENERIC and len(w) >= 2]
    return " ".join(toks)


class AppGraph:
    """Edges = distinct things that can be DONE in the app, each with the set of videos that show it."""

    def __init__(self, app_key: str, root: str = ""):
        self.app_key = app_key
        self.root = root or os.path.join(GRAPH_DIR, re.sub(r"[^\w.-]+", "_", app_key))
        self.videos: List[str] = []
        self.edges: List[Dict[str, Any]] = []
        self.nodes: List[Dict[str, Any]] = []                      # state nodes: {id, sig, videos}
        self.sequences: Dict[str, List[int]] = {}                  # video -> edge ids in the order shown
        self.growth: List[Dict[str, Any]] = []
        self.extra: Dict[str, Any] = {}                            # persisted side tables, e.g. 'ocr_votes' (shortcut facts voted for by events of different videos)

    # ---- persistence
    @property
    def path(self) -> str:
        return os.path.join(self.root, "graph.json")

    @property
    def crops_dir(self) -> str:
        return os.path.join(self.root, "crops")

    @classmethod
    def load(cls, app_key: str, root: str = "") -> "AppGraph":
        g = cls(app_key, root)
        if os.path.isfile(g.path):
            with contextlib.suppress(Exception):
                d = json.load(open(g.path, encoding="utf-8"))
                g.videos, g.edges, g.nodes = d["videos"], d["edges"], d["nodes"]
                g.sequences, g.growth = d.get("sequences", {}), d.get("growth", [])
                g.extra = d.get("extra", {})
        return g

    def save(self) -> str:
        os.makedirs(self.root, exist_ok=True)
        tmp = self.path + ".tmp"
        json.dump({"app_key": self.app_key, "videos": self.videos, "edges": self.edges, "nodes": self.nodes, "sequences": self.sequences, "growth": self.growth, "extra": self.extra,
                   "saved": time.strftime("%Y-%m-%d %H:%M:%S")}, open(tmp, "w", encoding="utf-8"))
        os.replace(tmp, self.path)
        return self.path

    # ---- building
    def _node_for(self, sig: Sequence[float], video: str) -> int:
        best, bs = -1, 0.0
        for n in self.nodes:
            s = cos(sig, n["sig"])
            if s > bs:
                best, bs = n["id"], s
        if best >= 0 and bs >= STATE_SIM:
            n = self.nodes[best]
            if video not in n["videos"]:
                n["videos"].append(video)
            return best
        self.nodes.append({"id": len(self.nodes), "sig": list(sig), "videos": [video]})
        return len(self.nodes) - 1

    def add_observation(self, o: Dict[str, Any]) -> Tuple[int, bool]:
        """(edge id, merged_into_existing)."""
        best, bs = None, 0.0
        for e in self.edges:
            s = obs_similarity(o, e["rep"])
            if s > bs:
                best, bs = e, s
        src, dst = self._node_for(o["src_sig"], o["video"]), self._node_for(o["dst_sig"], o["video"])
        if best is not None and bs >= MERGE_SIM:
            e = best
            n = len(e["obs"])
            for k in ("src_sig", "dst_sig", "delta_sig", "primary"):                       # the representative drifts to the mean of its members
                e["rep"][k] = [round((a * n + b) / (n + 1), 4) for a, b in zip(e["rep"][k], o[k])]
            if not e["rep"].get("dir"):
                e["rep"]["dir"] = o.get("dir", 0)
            merged = True
        else:
            e = {"id": len(self.edges), "rep": dict({k: list(o[k]) for k in ("src_sig", "dst_sig", "delta_sig", "primary")}, dir=o.get("dir", 0)), "obs": [], "labels": {}, "kinds": {}, "videos": [],
                 "src": src, "dst": dst, "opener_crops": [], "first_video": o["video"]}
            self.edges.append(e)
            merged = False
        keys = sorted({label_key(l) for l in o.get("labels", []) if label_key(l)})
        e["obs"].append(dict({k: o[k] for k in ("video", "t", "pre", "post", "union", "primary", "frame_px", "crop_px", "drag") if k in o}, label_keys=keys, kind=o.get("kind", "click"), step_text=o.get("step_text", "")))
        if o["video"] not in e["videos"]:
            e["videos"].append(o["video"])
        for nl in keys:
            e["labels"][nl] = e["labels"].get(nl, 0) + 1
        e["kinds"][o.get("kind", "click")] = e["kinds"].get(o.get("kind", "click"), 0) + 1
        for oc in o.get("opener_crops", []):
            if len(e["opener_crops"]) < 6:
                e["opener_crops"].append(dict(oc, video=o["video"]))
        return e["id"], merged

    def add_video(self, video_id: str, observations: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        if video_id in self.videos:
            return {"video": video_id, "skipped": "already ingested"}
        before = len(self.edges)
        seq, merged, new = [], 0, 0
        for o in sorted(observations, key=lambda x: x["t"]):
            eid, m = self.add_observation(o)
            seq.append(eid)
            merged += 1 if m else 0
            new += 0 if m else 1
        self.videos.append(video_id)
        self.sequences[video_id] = seq
        rep = {"video": video_id, "events": len(observations), "merged_into_existing": merged, "new_edges": len(self.edges) - before, "edges_total": len(self.edges),
               "videos_total": len(self.videos)}
        self.growth.append(rep)
        return rep

    # ---- views
    @staticmethod
    def support(e: Dict[str, Any]) -> int:
        return len(e["videos"])

    def best_label(self, e: Dict[str, Any]) -> str:
        return max(e["labels"].items(), key=lambda kv: kv[1])[0] if e["labels"] else ""

    def best_kind(self, e: Dict[str, Any]) -> str:
        return max(e["kinds"].items(), key=lambda kv: kv[1])[0] if e["kinds"] else "click"

    def baseline(self, min_support: int = 2) -> List[Dict[str, Any]]:
        return [e for e in self.edges if self.support(e) >= min_support]

    def unique(self) -> List[Dict[str, Any]]:
        return [e for e in self.edges if self.support(e) == 1]

    def order_of(self, e: Dict[str, Any]) -> float:
        """Mean relative position (0..1) of the edge in the videos that show it: how early in a typical session it happens."""
        pos = []
        for v, seq in self.sequences.items():
            if e["id"] in seq and len(seq) > 1:
                pos.append(seq.index(e["id"]) / (len(seq) - 1))
        return float(np.mean(pos)) if pos else 0.0

    def concepts(self) -> List[Dict[str, Any]]:
        """What the speakers NAMED, confirmed by a visible change at that moment: one concept per label key, with the videos that show it (support) and where in a session it usually comes.
        This is the cross-author merge: pictures of the same control differ between authors (size, layout, theme), the name they say does not."""
        pos: Dict[str, Dict[str, float]] = {}
        for v in self.videos:
            allobs = sorted((o for e in self.edges for o in e["obs"] if o["video"] == v), key=lambda o: o["t"])
            for i, o in enumerate(allobs):
                pos.setdefault(v, {})[(o["t"], o.get("pre", ""))] = i / max(len(allobs) - 1, 1)
        by: Dict[str, Dict[str, Any]] = {}
        for e in self.edges:
            for o in e["obs"]:
                for k in o.get("label_keys", []):
                    c = by.setdefault(k, {"key": k, "videos": [], "n_obs": 0, "kinds": Counter(), "edges": set(), "obs": [], "order": []})
                    if o["video"] not in c["videos"]:
                        c["videos"].append(o["video"])
                    c["n_obs"] += 1
                    c["kinds"][o.get("kind", "click")] += 1
                    c["edges"].add(e["id"])
                    c["obs"].append(o)
                    c["order"].append(pos.get(o["video"], {}).get((o["t"], o.get("pre", "")), 0.0))
        out = []
        for k, c in by.items():
            out.append({"key": k, "support": len(c["videos"]), "videos": c["videos"], "n_obs": c["n_obs"], "kind": c["kinds"].most_common(1)[0][0], "edges": sorted(c["edges"]),
                        "obs": c["obs"], "order": float(np.mean(c["order"])) if c["order"] else 0.0})
        out.sort(key=lambda c: (-c["support"], c["order"]))
        return out

    def summary(self) -> Dict[str, Any]:
        sup = Counter(self.support(e) for e in self.edges)
        cons = self.concepts()
        csup = Counter(c["support"] for c in cons)
        return {"app_key": self.app_key, "videos": len(self.videos), "edges": len(self.edges), "states": len(self.nodes),
                "baseline_edges(support>=2)": len(self.baseline()), "unique_edges(support==1)": len(self.unique()),
                "support_histogram": dict(sorted(sup.items())), "labelled_edges": sum(1 for e in self.edges if e["labels"]),
                "concepts": len(cons), "concepts_shared(support>=2)": sum(1 for c in cons if c["support"] >= 2), "concept_support_histogram": dict(sorted(csup.items())),
                "top_shared_concepts": [(c["key"], c["support"]) for c in cons if c["support"] >= 2][:15], "growth": self.growth}


# ------------------------------------------------------------------------------------------------------------------ video -> observations
_TYPE_RX = re.compile(r"\b(type|typing|write|enter the|input)\b", re.I)
_DRAG_RX = re.compile(r"\b(drag|drop|slide|move the)\b", re.I)


def _kind_of(step: Dict[str, Any]) -> str:
    txt = step.get("text", "")
    if step.get("chord"):
        return "hotkey"
    if _DRAG_RX.search(txt):
        return "drag"
    if _TYPE_RX.search(txt):
        return "type"
    return "click"


def observations_from_keyframes(keyframes: Sequence[Dict[str, Any]], video_id: str, crops_dir: str = "", segments: Optional[Sequence[Dict[str, Any]]] = None,
                                label_fn: Optional[Callable[[str, Sequence[int]], Sequence[str]]] = None, prefilter: bool = True, mask: Optional[Sequence[float]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """`keyframes` are video_pipeline.extract_keyframes() events ({t, pre, post, bbox}). Returns (observations, rejected-count report)."""
    rej = Counter()
    out: List[Dict[str, Any]] = []
    keep_fn = None
    if prefilter:
        with contextlib.suppress(Exception):
            from core_organs.harvest.frame_prefilter import looks_like_screencast as keep_fn
    used: set = set()                                                       # an instruction labels the first change it causes; later changes are consequences of later speech
    for ev in sorted(keyframes, key=lambda k: float(k["t"])):
        if keep_fn is not None:
            ok_pre, _ = keep_fn(ev["pre"])
            ok_post, _ = keep_fn(ev["post"])
            if not (ok_pre and ok_post):
                rej["not_a_screencast_frame"] += 1
                continue
        labels: List[str] = []
        kind, step_text = "click", ""
        if segments:
            with contextlib.suppress(Exception):
                from core_organs.harvest import video_explain as VE
                steps = [s for s in VE.steps_before(segments, float(ev["t"])) if VE.is_concrete(s) and (round(s["t"], 2), s.get("text", "")) not in used]
                earlier = [s for s in steps if s["t"] <= float(ev["t"])]
                if earlier or steps:
                    st = (earlier or steps)[-1]
                    used.add((round(st["t"], 2), st.get("text", "")))
                    step_text, kind = st.get("text", ""), _kind_of(st)
                    labels += [st.get("chord") or st.get("target", "")] + list(st.get("quoted") or [])
        if label_fn is not None and ev.get("bbox") and ev.get("post"):
            with contextlib.suppress(Exception):
                labels += list(label_fn(ev["post"], ev["bbox"]))
        o = observation_from_pair(ev["pre"], ev["post"], video_id, float(ev["t"]), ev["pre"], ev["post"], crops_dir, labels, kind, step_text, mask)
        if o is None:
            rej["no_visible_change"] += 1
            continue
        if o["page_change"]:
            rej["page_change_or_scene_cut"] += 1
            continue
        o["bbox_px"] = ev.get("bbox")
        out.append(o)
    return out, dict(rej)


def ingest_video(graph: AppGraph, video_path: str, video_id: str = "", segments: Optional[Sequence[Dict[str, Any]]] = None, label_fn: Optional[Callable] = None,
                 sample_fps: float = 2.0, keyframes_dir: str = "", diff_thresh: int = 12, trace_drags: bool = True, **scene_kw: Any) -> Dict[str, Any]:
    """Cut one video into events, describe them, merge them into the graph, save the graph. Re-ingesting the same video id is a no-op."""
    from core_organs.harvest import video_pipeline as VP
    video_id = video_id or os.path.splitext(os.path.basename(video_path))[0]
    if video_id in graph.videos:
        return {"video": video_id, "skipped": "already ingested"}
    t0 = time.time()
    kdir = keyframes_dir or os.path.join(graph.root, "frames", re.sub(r"[^\w.-]+", "_", video_id))
    kfs = VP.extract_keyframes(video_path, kdir, video_id=video_id, sample_fps=sample_fps, diff_thresh=diff_thresh, **scene_kw)
    inset = detect_inset([k["pre"] for k in kfs])
    obs, rej = observations_from_keyframes(kfs, video_id, graph.crops_dir, segments, label_fn, mask=inset)
    traced = 0
    if trace_drags:                                                      # an event that looks like something MOVED: re-read the video around it and keep the path as a vector
        from core_organs.harvest import drag_trace as DT
        for o in obs:
            if DT.looks_like_move(o):
                with contextlib.suppress(Exception):
                    d = DT.trace_window(video_path, max(0.0, o["t"] - 1.0), o["t"] + 1.5, o.get("crop_px"), inset)
                    if d:
                        o["drag"] = d
                        o["kind"] = "drag"
                        traced += 1
    rep = graph.add_video(video_id, obs)
    rep["drags_traced"] = traced
    if segments:
        with contextlib.suppress(Exception):
            rep.update(record_speech(graph, video_id, segments))
    rep.update({"events_cut": len(kfs), "rejected": rej, "webcam_inset_masked": inset, "seconds": round(time.time() - t0, 1)})
    graph.save()
    return rep


def rebuild(old: AppGraph, backup: bool = True) -> Dict[str, Any]:
    """Recompute `old` from the pre / post frames it already stored (no video decoding, no prefilter): use after the event rules changed. The old graph file is kept as graph.v1.json."""
    by_video: Dict[str, List[Dict[str, Any]]] = {}
    seen = set()
    for e in old.edges:
        for o in e["obs"]:
            key = (o["video"], o["t"], o.get("pre"))
            if key not in seen and o.get("pre") and o.get("post") and os.path.isfile(o["pre"]) and os.path.isfile(o["post"]):
                seen.add(key)
                by_video.setdefault(o["video"], []).append({"t": o["t"], "pre": o["pre"], "post": o["post"]})
    if backup and os.path.isfile(old.path):
        shutil_copy(old.path, os.path.join(old.root, "graph.v1.json"))
    new = AppGraph(old.app_key, old.root)
    reports = []
    for vid in old.videos:
        evs = sorted(by_video.get(vid, []), key=lambda x: x["t"])
        inset = detect_inset([x["pre"] for x in evs])
        obs, rej = observations_from_keyframes(evs, vid, new.crops_dir, None, None, prefilter=False, mask=inset)
        r = new.add_video(vid, obs)
        r.update({"events_cut": len(evs), "rejected": rej, "webcam_inset_masked": inset})
        reports.append(r)
    new.save()
    return {"rebuilt": reports, "summary": new.summary()}


# ------------------------------------------------------------------------------------------------------------------ exporters
def _step_text(kind: str, label: str, unique: bool) -> str:
    verb = {"click": "Click", "type": "Type into", "hotkey": "Press", "drag": "Drag"}.get(kind, "Click")
    t = f"{verb} {label}."
    return t if not unique else t[:-1] + " (alternate path seen in one tutorial)."


def export_rag(graph: AppGraph, rag: Any, app_name: str = "", include_unique: bool = False, min_labelled: int = 2, min_support: int = 2) -> Dict[str, Any]:
    """Concepts (spoken control names confirmed by a visible change), in the order they usually happen, become ONE workflow through the existing writer (rag_feed.write_workflow).
    By default only concepts at least `min_support` videos agree on; `include_unique` adds single-video ones, marked as an alternate path. A concept with no key is never written."""
    from core_organs.harvest import rag_feed as RF
    cons = [c for c in graph.concepts() if len(c["key"]) >= 3 and (c["support"] >= min_support or (include_unique and c["support"] == 1))]
    cons.sort(key=lambda c: (c["support"] == 1, c["order"]))                             # agreed steps first, in session order; single-video branches after
    steps = [{"text": _step_text(c["kind"], c["key"], c["support"] == 1), "names": [c["key"]] if c["kind"] != "hotkey" else [], "keys": [c["key"]] if c["kind"] == "hotkey" else [], "imgs": []} for c in cons]
    if len(steps) < min_labelled:
        return {"written": 0, "why": f"{len(steps)} concept(s) with support >= {min_support}: a workflow needs at least {min_labelled}; ingest more videos (with transcripts)"}
    res = RF.write_workflow(rag, graph.app_key, app_name or graph.app_key, f"consolidated from {len(graph.videos)} tutorial videos", steps, f"video-consolidation:{len(graph.videos)}-videos")
    return {"written": len(steps), "shared": sum(1 for c in cons if c["support"] >= 2), "unique": sum(1 for c in cons if c["support"] == 1), "rag": res, "concepts": [(c["key"], c["support"]) for c in cons]}


def export_training(graph: AppGraph, out_jsonl: str = "", root: str = "", som_fn: Optional[Callable[..., Dict[str, Any]]] = None, max_rows_per_concept: int = 6,
                    min_elements: int = 3, min_support: int = 1) -> Dict[str, Any]:
    """One training row per VIDEO that shows a concept (the same named action in different recordings = real variety), in the existing prompt-v1 shape (picture + Set-of-Marks list + goal).
    Rows are appended to harvest/training/ui_training_dataset.jsonl by default. A row needs the concept's name to match an element of the Set-of-Marks, otherwise its target would be a guess."""
    from core_organs.harvest import video_explain as VE, video_pipeline as VP
    from core_organs.harvest.paths import harvest_dir
    som_fn = som_fn or VP.som_of_frame
    root = root or harvest_dir()[0]
    out_jsonl = out_jsonl or os.path.join(root, "training", "ui_training_dataset.jsonl")
    os.makedirs(os.path.dirname(out_jsonl), exist_ok=True)
    seen = set()
    if os.path.isfile(out_jsonl):
        for l in open(out_jsonl, encoding="utf-8"):
            with contextlib.suppress(Exception):
                seen.add(json.loads(l).get("meta", {}).get("pair_id"))
    rep = Counter()
    rows = []
    for c in graph.concepts():
        if c["kind"] != "click" or c["support"] < min_support or len(c["key"]) < 3:
            rep["skipped_not_click_or_unsupported"] += 1
            continue
        per_video = {}
        for o in c["obs"]:
            per_video.setdefault(o["video"], o)
        for vid, o in list(per_video.items())[:max_rows_per_concept]:
            pid = hashlib.sha1(f"vc|{graph.app_key}|{c['key']}|{vid}|{o['t']}".encode()).hexdigest()[:16]
            if pid in seen:
                rep["duplicates"] += 1
                continue
            if not (o.get("pre") and os.path.isfile(o["pre"])):
                rep["missing_frame"] += 1
                continue
            som = som_fn(o["pre"])
            if len(som["elements"]) < min_elements:
                rep["sparse_frame"] += 1
                continue
            el = VE.match_element(som, c["key"])
            if el is None:
                rep["label_not_on_screen"] += 1
                continue
            action = {"step": 1, "action": "click", "target_id": el["id"], "hotkey": None, "text": None,
                      "verify_expectation": "the screen changes where the tutorials show it changing" if c["support"] > 1 else "the screen changes"}
            ev = {"pre": o["pre"], "post": o.get("post", ""), "t": o["t"], "bbox": None}
            rows.append(VE.build_row(root, graph.app_key, vid, ev, som, f"Click {c['key']}", [action], pid, True, None,
                                     {"source": "video-consolidation", "concept": c["key"], "support": c["support"], "unique": c["support"] == 1}))
            rep["rows"] += 1
    if rows:
        with open(out_jsonl, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return dict(rep, jsonl=out_jsonl)


# ------------------------------------------------------------------------------------------------------------------ on-screen text (language-free app knowledge)
_MODS = r"(?:cmd|command|ctrl|control|shift|alt|option|opt|win|meta)"
CHORD_RX = re.compile(rf"\b({_MODS}(?:\s*\+\s*{_MODS})*\s*\+\s*(?:[a-z0-9]|enter|return|esc|escape|tab|space|delete|backspace|up|down|left|right|f\d{{1,2}}|[,./\[\]\\-]))(?![a-z0-9])", re.I)
_TO_WINDOWS = {"cmd": "ctrl", "command": "ctrl", "option": "alt", "opt": "alt", "control": "ctrl", "meta": "win"}


def normalise_chord(raw: str) -> str:
    parts = [p.strip().lower() for p in re.split(r"\s*\+\s*", raw) if p.strip()]
    return "+".join("ctrl" if p == "control" else ("cmd" if p == "command" else ("alt" if p == "opt" else p)) for p in parts)


def windows_chord(chord: str) -> str:
    """A shortcut shown by a Mac author (cmd / option) in the form the Windows machine uses (ctrl / alt). The mapping is an inference and the fact keeps both forms."""
    return "+".join(_TO_WINDOWS.get(p, p) for p in chord.split("+"))


def facts_from_text(text: str) -> List[Dict[str, str]]:
    """[{chord, action}] from OCR text of a menu: each line with a key chord at its end gives the action named in front of it."""
    out = []
    for line in re.split(r"[\n|]+", text):
        m = CHORD_RX.search(line)
        if not m:
            continue
        action = re.sub(r"[^A-Za-z ]+", " ", line[:m.start()]).strip()
        if len(action) >= 3:
            out.append({"chord": normalise_chord(m.group(1)), "action": re.sub(r"\s+", " ", action)})
    return out


def ocr_crop(post_path: str, primary: Sequence[float], crop_px: Sequence[int], scale: int = 3) -> str:
    """Text inside the changed box of one event (the picture is read at its own resolution, enlarged, and light-on-dark text is inverted)."""
    import cv2
    import pytesseract
    im = cv2.imdecode(np.fromfile(post_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        return ""
    cx0, cy0, cx1, cy1 = crop_px
    x0, y0 = int(cx0 + primary[0] * (cx1 - cx0)), int(cy0 + primary[1] * (cy1 - cy0))
    x1, y1 = int(cx0 + primary[2] * (cx1 - cx0)), int(cy0 + primary[3] * (cy1 - cy0))
    c = im[max(0, y0 - 2):y1 + 2, max(0, x0 - 2):x1 + 2]
    if c.size == 0 or min(c.shape[:2]) < 8:
        return ""
    g = cv2.resize(cv2.cvtColor(c, cv2.COLOR_BGR2GRAY), None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if g.mean() < 110:
        g = 255 - g
    return pytesseract.image_to_string(g, config="--psm 6").strip()


def _line_key(line: str) -> str:
    return re.sub(r"[^a-z]", "", line.lower())


def ocr_edges(graph: AppGraph, min_support: int = 2, per_edge: int = 8, ocr: Optional[Callable[..., str]] = None) -> Dict[str, Any]:
    """Read the text of every edge at least `min_support` videos agree on, and keep only what several AUTHORS' screens show: lines (control names, menu entries) and shortcut facts
    (action + chord). One author's OCR error cannot become knowledge: a line or chord must appear for >= 2 different videos."""
    ocr = ocr or ocr_crop
    done = 0
    for e in graph.edges:
        if graph.support(e) < min_support:
            continue
        by_video: Dict[str, List[Dict[str, Any]]] = {}
        for o in e["obs"]:
            by_video.setdefault(o["video"], []).append(o)
        picked = [grp[0] for grp in by_video.values()]
        picked += [o for grp in by_video.values() for o in grp[1:]][:max(0, per_edge - len(picked))]
        line_videos: Dict[str, set] = {}
        line_raw: Dict[str, Counter] = {}
        chord_videos: Dict[str, set] = {}
        chord_action: Dict[str, Counter] = {}
        chord_raw: Dict[str, Counter] = {}
        for o in picked[:per_edge]:
            if not (o.get("post") and os.path.isfile(o["post"]) and o.get("primary") and o.get("crop_px")):
                continue
            txt = ocr(o["post"], o["primary"], o["crop_px"])
            done += 1
            for line in [l.strip() for l in re.split(r"[\n|]+", txt) if len(l.strip()) >= 4]:
                k = _line_key(line)
                if len(k) >= 4:
                    line_videos.setdefault(k, set()).add(o["video"])
                    line_raw.setdefault(k, Counter())[line] += 1
            for f in facts_from_text(txt):                                  # a Mac author's cmd+s and a Windows author's ctrl+s are the same fact
                w = windows_chord(f["chord"])
                chord_videos.setdefault(w, set()).add(o["video"])
                chord_action.setdefault(w, Counter())[f["action"]] += 1
                chord_raw.setdefault(w, Counter())[f["chord"]] += 1
        e["ocr"] = {"lines": [{"text": line_raw[k].most_common(1)[0][0], "videos": len(v)} for k, v in sorted(line_videos.items(), key=lambda kv: -len(kv[1])) if len(v) >= 2][:12],
                    "facts": [{"chord": chord_raw[w].most_common(1)[0][0], "windows": w, "action": chord_action[w].most_common(1)[0][0], "videos": len(v),
                               "mac_style": any(set(r.split("+")) & {"cmd", "command", "option", "opt"} for r in chord_raw[w])}
                              for w, v in sorted(chord_videos.items(), key=lambda kv: -len(kv[1])) if len(v) >= 2]}
    graph.save()
    facts = graph.facts()
    return {"ocr_calls": done, "edges_with_shared_text": sum(1 for e in graph.edges if (e.get("ocr") or {}).get("lines")), "shortcut_facts": len(facts), "facts": facts[:20]}


def record_speech(graph: AppGraph, video_id: str, segments: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """Spoken shortcuts and modifier gestures of one video become votes (once per video): graph.extra['spoken_votes'][windows chord] and ['gesture_votes'][modifier|gesture|effect]."""
    from core_organs.harvest import spoken_facts as SF, video_explain as VE
    cv = graph.extra.setdefault("spoken_votes", {})
    gv = graph.extra.setdefault("gesture_votes", {})
    nc = ng = 0
    for u in VE.utterances(segments):
        for c in SF.chords(u["text"]):
            w = windows_chord(c["chord"])
            v = cv.setdefault(w, {"videos": [], "actions": {}, "raw": {}})
            if video_id not in v["videos"]:
                v["videos"].append(video_id)
            v["actions"][c["action"]] = v["actions"].get(c["action"], 0) + 1
            v["raw"][c["chord"]] = v["raw"].get(c["chord"], 0) + 1
            nc += 1
        for g in SF.gestures(u["text"]):
            if not g["effect"]:
                continue
            key = f"{g['modifier']}|{g['gesture']}|{g['effect'][:60].lower()}"
            v = gv.setdefault(key, {"modifier": g["modifier"], "gesture": g["gesture"], "effect": g["effect"], "videos": []})
            if video_id not in v["videos"]:
                v["videos"].append(video_id)
            ng += 1
    return {"spoken_chords": nc, "spoken_gestures": ng}


def ocr_observations(graph: AppGraph, max_per_video: int = 80, ocr: Optional[Callable[..., str]] = None, min_area: float = 0.006, max_area: float = 0.5) -> Dict[str, Any]:
    """Read the text of EVERY event whose changed region could be a menu, dropdown, dialog or panel (a share of the screen between min_area and max_area), not only of the events other authors
    also showed: the same shortcut in two videos is agreement even when the two pictures never merged. Each reading votes `windows chord -> action`; a chord counts once per video.
    A fact is kept (see `facts()`) only when the votes of >= 2 different videos agree on the chord. Up to `max_per_video` events per video, the larger regions first."""
    ocr = ocr or ocr_crop
    votes: Dict[str, Dict[str, Any]] = graph.extra.setdefault("ocr_votes", {})
    done_keys = set(graph.extra.setdefault("ocr_done", []))
    calls = 0
    by_video: Dict[str, List[Dict[str, Any]]] = {}
    for e in graph.edges:
        for o in e["obs"]:
            prim = o.get("primary") or e["rep"].get("primary")
            if not (prim and o.get("post") and o.get("crop_px") and os.path.isfile(o["post"])):
                continue
            area = (prim[2] - prim[0]) * (prim[3] - prim[1])
            if min_area <= area <= max_area:
                by_video.setdefault(o["video"], []).append(dict(o, _area=area, primary=prim))
    for vid, obs in by_video.items():
        for o in sorted(obs, key=lambda x: -x["_area"])[:max_per_video]:
            k = f"{vid}|{o['t']}"
            if k in done_keys:
                continue
            done_keys.add(k)
            try:
                txt = ocr(o["post"], o["primary"], o["crop_px"])
            except Exception:
                continue
            calls += 1
            for f in facts_from_text(txt):
                w = windows_chord(f["chord"])
                v = votes.setdefault(w, {"videos": [], "actions": {}, "raw": {}})
                if vid not in v["videos"]:
                    v["videos"].append(vid)
                v["actions"][f["action"]] = v["actions"].get(f["action"], 0) + 1
                v["raw"][f["chord"]] = v["raw"].get(f["chord"], 0) + 1
    graph.extra["ocr_done"] = sorted(done_keys)
    graph.save()
    return {"ocr_calls": calls, "chords_voted": len(votes), "chords_with_2_videos": sum(1 for v in votes.values() if len(v["videos"]) >= 2)}


def _facts_of(graph: AppGraph, min_videos: int = 2) -> List[Dict[str, Any]]:
    by: Dict[str, Dict[str, Any]] = {}
    for e in graph.edges:
        for f in (e.get("ocr") or {}).get("facts", []):
            cur = by.get(f["windows"])
            if cur is None or f["videos"] > cur["videos"]:
                by[f["windows"]] = dict(f, edge=e["id"])
    for w, v in (graph.extra.get("ocr_votes") or {}).items():                       # fact-level agreement across videos (ocr_observations)
        n = len(v["videos"])
        if n < min_videos:
            continue
        cur = by.get(w)
        if cur is None or n > cur["videos"]:
            raw = max(v["raw"].items(), key=lambda kv: kv[1])[0]
            by[w] = {"chord": raw, "windows": w, "action": max(v["actions"].items(), key=lambda kv: kv[1])[0], "videos": n,
                     "mac_style": any(set(r.split("+")) & {"cmd", "command", "option", "opt"} for r in v["raw"]), "edge": None}
    for f in by.values():
        f.setdefault("source", "screen")
    for w, v in (graph.extra.get("spoken_votes") or {}).items():                  # what a presenter SAID: kept when no screen showed the chord, lower trust at export
        if w in by:
            by[w]["also_said_in"] = len(v["videos"])
            continue
        raw = max(v["raw"].items(), key=lambda kv: kv[1])[0]
        by[w] = {"chord": raw, "windows": w, "action": max(v["actions"].items(), key=lambda kv: kv[1])[0], "videos": len(v["videos"]),
                 "mac_style": any(set(r.split("+")) & {"cmd", "command", "option", "opt"} for r in v["raw"]), "edge": None, "source": "speech"}
    return sorted(by.values(), key=lambda f: (-f["videos"], f["windows"]))


def _drags_of(graph: AppGraph) -> List[Dict[str, Any]]:
    return [dict(o["drag"], video=o["video"], t=o["t"], edge=e["id"]) for e in graph.edges for o in e["obs"] if o.get("drag")]


def _gestures_of(graph: AppGraph) -> List[Dict[str, Any]]:
    return sorted(({"modifier": v["modifier"], "gesture": v["gesture"], "effect": v["effect"], "videos": len(v["videos"])} for v in (graph.extra.get("gesture_votes") or {}).values()),
                  key=lambda g: (-g["videos"], g["modifier"]))


AppGraph.drags = _drags_of                                        # type: ignore[attr-defined]
AppGraph.gestures = _gestures_of                                  # type: ignore[attr-defined]
AppGraph.facts = _facts_of                                    # type: ignore[attr-defined]


def export_facts_rag(graph: AppGraph, rag: Any, app_name: str = "", min_videos: int = 2, write_procedure: bool = True, only_new: bool = False, clean: bool = True,
                     accept_single: Optional[Callable[[Dict[str, Any]], int]] = None) -> Dict[str, Any]:
    """Shortcuts read off the screens of >= `min_videos` authors, filed under the graph's OWN app key (the bridge's app_key_of() would rewrite 'webapp:host' into another key).
    Three things per fact: the command name in the lexicon, a hotkey row in the fast-path store (trust 'web', verified=False: it is a lead, not a proven shortcut), and - once - one procedure
    listing them. Mac-style chords are written in the Windows form (cmd->ctrl, option->alt); the row's context says how many authors showed it. Nothing is deleted or overwritten.
    `only_new=True` (the unattended curriculum): a fact whose action already has a row for this app is NOT written - same payload = corroborated, different payload = a conflict, both only
    reported - so existing, possibly higher-trust knowledge is never duplicated or contradicted by a lead."""
    from core_organs.harvest import bridge as BR
    facts = [f for f in graph.facts(min_videos=1 if accept_single else min_videos) if f["videos"] >= min_videos or f.get("source") == "speech" or (accept_single and accept_single(f))]
    for f in facts:
        if f["videos"] < min_videos and f.get("source") != "speech":
            f["by_prior"] = accept_single(f)
    key, n = graph.app_key, len(graph.videos)
    cleaning: Dict[str, Any] = {}
    if clean and facts:                                              # run-together OCR names are split, junk dropped, one shortcut named three ways becomes one (fact_cleaner)
        from core_organs.harvest import fact_cleaner as FC
        facts, cleaning = FC.clean_facts(facts)
        kept = [f for f in facts if f.get("source") != "speech" or FC.speech_ok(f["action"])]            # what was only SAID must look like a command name
        cleaning["speech_dropped"] = [f["action"] for f in facts if f not in kept]
        facts = kept
    corroborated: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    if only_new and facts:
        fresh = []
        for f in facts:
            kind, payload = BR.norm_keys(f["windows"])
            same = rag.fast.find(key, f["action"], payload)
            others = [e for e in rag.fast.by_goal(key, f["action"], limit=6) if str(e.text).strip().lower() == f["action"].strip().lower() and (e.payload or {}).get("payload") != payload]
            if same:
                corroborated.append({"action": f["action"], "chord": f["windows"]})
            elif others:
                conflicts.append({"action": f["action"], "video_chord": f["windows"], "stored": [(e.payload or {}).get("payload") for e in others]})
            else:
                fresh.append(f)
        facts = fresh
    if len(facts) < 1 or (not only_new and len(facts) < 2):
        return {"written": 0, "why": f"{len(facts)} new shortcut(s) shown by >= {min_videos} videos", "corroborated": corroborated, "conflicts": conflicts, "cleaning": cleaning}
    recs, steps = [], []
    for f in facts:
        cid = rag.lex.add_command(key, f["action"], source="video_ocr", trust="web")
        kind, payload = BR.norm_keys(f["windows"])
        said = f.get("source") == "speech"
        recs.append({"app_key": key, "kind": kind, "command_id": cid, "task_pattern": f["action"], "payload": payload, "source": "transcript" if said else "web_table", "trust": "transcript" if said else "web",
                     "verified": False, "context": (f"video-speech: said in {f['videos']} of {n} videos" if said else f"video-ocr: shown by {f['videos']} of {n} authors") + (" (as a Mac chord)" if f["mac_style"] else "")
                                                                                                                         + (f"; matches {f['by_prior']} similar apps" if f.get("by_prior") else ""),
                     "params_schema_json": BR.infer_schema(payload)})
        steps.append({"text": f"Press {f['windows'].upper()} to {f['action'].lower()}." + (f" (shown as {f['chord'].upper()} in a Mac tutorial)" if f["mac_style"] else ""), "target": f["action"], "route_hint": "hotkey"})
    rep = rag.fast.upsert(recs)
    out: Dict[str, Any] = {"written": len(recs), "fast_paths": {"inserted": rep.inserted, "updated": rep.updated}, "app_key": key, "corroborated": corroborated, "conflicts": conflicts,
                           "rows": [(r["task_pattern"], r["payload"]) for r in recs], "cleaning": cleaning}
    gest = [g for g in graph.gestures() if g["videos"] >= 1] if hasattr(graph, "gestures") else []
    for g in gest[:12]:
        steps.append({"text": f"Hold {g['modifier'].upper()} while {g['gesture']} to {g['effect']}.", "target": g["gesture"], "route_hint": "drag"})
    if write_procedure and len(steps) >= 2:
        r = rag.proc.ingest_procedure(key, f"keyboard shortcuts shown on screen in {n} tutorial videos", steps, f"video-ocr:{n}-videos", trust="web")
        out["procedure"] = {"inserted": r.inserted, "updated": r.updated}
    return out


def _where(box: Sequence[float]) -> str:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    v = "top" if cy < 0.33 else ("bottom" if cy > 0.67 else "middle")
    h = "left" if cx < 0.33 else ("right" if cx > 0.67 else "centre")
    area = (box[2] - box[0]) * (box[3] - box[1])
    return f"{v}-{h}, {'small' if area < 0.03 else 'medium' if area < 0.15 else 'large'} region"


def understanding_report(graph: AppGraph, out_dir: str, top: int = 14, min_support: int = 2) -> Dict[str, Any]:
    """What the videos taught about the app, as a document with pictures: for each concept (most agreed first) its name, kind, how many authors show it, where in a session it comes,
    where on screen the change happened and whether something appeared or went away, plus a before / after strip for each author. The proof the numbers can be checked against."""
    import cv2
    os.makedirs(out_dir, exist_ok=True)
    safe = re.sub(r"[^\w.-]+", "_", graph.app_key)
    edge_by_id = {e["id"]: e for e in graph.edges}
    cons = [c for c in graph.concepts() if c["support"] >= min_support and len(c["key"]) >= 3][:top]
    TH = (256, 144)
    md = [f"# What the videos taught about `{graph.app_key}`", "", f"{len(graph.videos)} videos, {len(graph.edges)} visual edges, {len(graph.concepts())} named concepts "
          f"({sum(1 for c in graph.concepts() if c['support'] >= 2)} shown by 2+ authors).", ""]
    shared_text = [e for e in graph.edges if (e.get("ocr") or {}).get("lines")]
    if shared_text:
        md += ["## Text that several authors' screens show at the same place", ""]
        for e in sorted(shared_text, key=lambda e: -graph.support(e))[:12]:
            md.append(f"- edge {e['id']} (support {graph.support(e)}, {_where(e['rep']['primary'])}): " + "; ".join(l["text"][:50] for l in e["ocr"]["lines"][:6]))
        md.append("")
    if graph.facts():
        md += ["## Shortcuts read off the screens (>= 2 videos)", ""] + [f"- `{f['windows']}`  {f['action']}  ({f['videos']} videos" + (", shown as " + f["chord"] + " by a Mac author" if f["mac_style"] else "") + ")" for f in graph.facts()[:25]] + [""]
    md += ["## What authors said, confirmed by a visible change (named by >= %d authors)" % min_support, "",
           "Speech is the noisier source: spontaneous narration gives fragments, so only names several authors agree on are listed.", ""]
    for i, c in enumerate(cons):
        o0 = c["obs"][0]
        e0 = edge_by_id.get(c["edges"][0]) if c["edges"] else None
        prim = (e0 or {}).get("rep", {}).get("primary") or o0.get("primary") or [0, 0, 1, 1]
        dirn = {1: "something appeared", -1: "something went away", 0: "the region changed"}.get((e0 or {}).get("rep", {}).get("dir", 0), "the region changed")
        md.append(f"## {i + 1}. {c['kind']} `{c['key']}`  (support {c['support']}/{len(graph.videos)} videos, usually {int(c['order'] * 100)}% into a session)")
        md.append(f"- on screen: {dirn} in the {_where(prim)}")
        md.append(f"- authors: {', '.join(c['videos'])}")
        rows = []
        seen = set()
        for o in c["obs"]:
            if o["video"] in seen or not (o.get("pre") and os.path.isfile(o["pre"]) and o.get("post") and os.path.isfile(o["post"])):
                continue
            seen.add(o["video"])
            tiles = []
            for tag in ("pre", "post"):
                im = cv2.imdecode(np.fromfile(o[tag], dtype=np.uint8), cv2.IMREAD_COLOR)
                im = cv2.resize(im if im is not None else np.zeros((9, 16, 3), np.uint8), TH)
                if tag == "post":
                    b = o.get("primary") or prim
                    cv2.rectangle(im, (int(b[0] * TH[0]), int(b[1] * TH[1])), (int(b[2] * TH[0]), int(b[3] * TH[1])), (0, 0, 255), 2)
                cv2.rectangle(im, (0, 0), (TH[0], 14), (0, 0, 0), -1)
                cv2.putText(im, f"{o['video'][:11]} {tag} t={o['t']}", (3, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
                tiles.append(im)
            rows.append(np.hstack(tiles))
            if len(rows) >= 4:
                break
        if rows:
            img = os.path.join(out_dir, f"{safe}_concept_{i + 1:02d}.png")
            cv2.imencode(".png", np.vstack(rows))[1].tofile(img)
            md.append(f"![{c['key']}]({os.path.basename(img)})")
        md.append("")
    path = os.path.join(out_dir, f"{safe}_understanding.md")
    open(path, "w", encoding="utf-8").write("\n".join(md))
    return {"markdown": path, "concepts_shown": len(cons)}


# ------------------------------------------------------------------------------------------------------------------ fetching (explicit command only)
LAST_FETCH: Dict[str, Any] = {"rate_limited": False, "searched": 0, "picked": 0}


def fetch_videos(app_name: str, n: int = 3, out_dir: str = "", min_s: int = 240, max_s: int = 3600, max_height: int = 720, sleep_s: float = 8.0,
                 urls: Sequence[str] = (), log: Callable[[str], None] = print, dry_run: bool = False, exclude: Sequence[str] = (), require: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """Download up to `n` tutorial videos of one application (or the given urls) with yt-dlp. Polite: one at a time, a pause between, stops at the first rate-limit answer.
    No proxies, no IP rotation, no cookies. Only runs when this command is called. `dry_run`: search and list the candidates (id, title, minutes, rough size), download nothing."""
    import yt_dlp
    out_dir = out_dir or os.path.join(GRAPH_DIR, "_downloads", re.sub(r"[^\w.-]+", "_", app_name))
    os.makedirs(out_dir, exist_ok=True)
    LAST_FETCH.update({"rate_limited": False, "searched": 0, "picked": 0})
    picks: List[Dict[str, Any]] = []
    if urls:
        picks = [{"url": u, "id": "", "title": ""} for u in urls]
    else:
        seen_ids = set()
        for q in (f"{app_name} tutorial", f"{app_name} how to use", f"{app_name} beginner guide", f"{app_name} tips and tricks"):
            with contextlib.suppress(Exception):
                with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True, "skip_download": True}) as y:
                    res = y.extract_info(f"ytsearch12:{q}", download=False)
                for it in res.get("entries") or []:
                    d = it.get("duration") or 0
                    vid = it.get("id", "")
                    if min_s <= d <= max_s and vid and vid not in seen_ids:
                        seen_ids.add(vid)
                        picks.append({"url": it.get("url") or f"https://www.youtube.com/watch?v={vid}", "id": vid, "title": it.get("title", ""),
                                      "minutes": round(d / 60, 1), "approx_mb_at_720p": int(d / 60 * 6)})
            time.sleep(2.0)
        # a video already on disk is not fetched again and does not count towards n
        picks = [pk for pk in picks if not os.path.isfile(os.path.join(out_dir, pk["id"] + ".mp4")) and not any(x.lower() in pk["title"].lower() for x in exclude)
                 and (not require or any(x.lower() in pk["title"].lower() for x in require))]
    if dry_run:
        return picks[:max(n * 2, n)]
    done: List[Dict[str, Any]] = []
    opts = {"quiet": True, "no_warnings": True, "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"), "format": f"bestvideo[height<={max_height}][ext=mp4]/best[height<={max_height}][ext=mp4]/best[height<={max_height}]",
            "noplaylist": True, "retries": 1}
    for p in picks:
        if len(done) >= n:
            break
        try:
            with yt_dlp.YoutubeDL(opts) as y:
                info = y.extract_info(p["url"], download=True)
            fn = y.prepare_filename(info)
            done.append({"video_id": info.get("id", ""), "title": info.get("title", ""), "path": fn, "duration_s": info.get("duration"), "url": p["url"]})
            log(f"downloaded {info.get('id')} {info.get('title', '')[:60]}")
        except Exception as exc:
            msg = str(exc)
            log(f"skip {p['url']}: {msg[:120]}")
            if "429" in msg or "Too Many Requests" in msg:
                log("rate limited: stopping (no retries, no rotation)")
                LAST_FETCH["rate_limited"] = True
                break
        time.sleep(sleep_s)
    json.dump(done, open(os.path.join(out_dir, "fetched.json"), "w", encoding="utf-8"), indent=1)
    return done


_CAPTIONS_BLOCKED = {"yes": False}        # after the first HTTP 429 on the caption endpoint, this process stops asking (no hammering, no rotation)


def transcript_path(video_path: str) -> str:
    return os.path.splitext(video_path)[0] + ".transcript.json"


def _segments_from_json3(path: str) -> List[Dict[str, Any]]:
    d = json.load(open(path, encoding="utf-8"))
    out = []
    for ev in d.get("events", []):
        txt = "".join(sg.get("utf8", "") for sg in ev.get("segs", []) or []).replace("\n", " ").strip()
        if txt:
            out.append({"text": txt, "start": ev.get("tStartMs", 0) / 1000.0, "duration": ev.get("dDurationMs", 0) / 1000.0})
    return out


def fetch_transcript(video_path: str, video_id: str = "", whisper_model: str = "base.en", log: Callable[[str], None] = print) -> Dict[str, Any]:
    """Segments [{text, start, duration}] for one downloaded video, cached next to it as <name>.transcript.json.
    1) YouTube captions (a text file, no audio download); 2) the audio track downloaded on its own and transcribed locally on the CPU (faster-whisper, int8).
    Only runs when called; no cookies, no proxies. Returns {segments, source}."""
    cache = transcript_path(video_path)
    if os.path.isfile(cache):
        return json.load(open(cache, encoding="utf-8"))
    video_id = video_id or os.path.splitext(os.path.basename(video_path))[0]
    folder = os.path.dirname(video_path)
    url = f"https://www.youtube.com/watch?v={video_id}"
    import yt_dlp
    segs: List[Dict[str, Any]] = []
    source = ""
    try:
        if _CAPTIONS_BLOCKED["yes"]:
            raise RuntimeError("caption endpoint rate-limited earlier in this run")
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "writesubtitles": True, "writeautomaticsub": True, "subtitleslangs": ["en", "en-orig"], "subtitlesformat": "json3",
                "outtmpl": os.path.join(folder, "%(id)s")}
        with yt_dlp.YoutubeDL(opts) as y:
            y.extract_info(url, download=True)
        for cand in sorted(f for f in os.listdir(folder) if f.startswith(video_id) and f.endswith(".json3")):
            segs = _segments_from_json3(os.path.join(folder, cand))
            source = "youtube-captions:" + cand
            break
    except Exception as exc:
        if "429" in str(exc):
            _CAPTIONS_BLOCKED["yes"] = True
        log(f"captions unavailable for {video_id}: {str(exc)[:100]}")
    if len(segs) < 5:
        aud = os.path.join(folder, f"{video_id}.audio.m4a")
        if not os.path.isfile(aud):
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "format": "bestaudio[ext=m4a]/bestaudio", "outtmpl": os.path.join(folder, f"{video_id}.audio.%(ext)s")}) as y:
                y.extract_info(url, download=True)
            aud = next((os.path.join(folder, f) for f in os.listdir(folder) if f.startswith(video_id + ".audio.")), aud)
        from core_organs.harvest import video_pipeline as VP
        segs = VP.transcribe_audio(aud, whisper_model)
        source = f"faster-whisper:{whisper_model}"
    res = {"segments": segs, "source": source, "n": len(segs)}
    json.dump(res, open(cache, "w", encoding="utf-8"))
    return res


# ------------------------------------------------------------------------------------------------------------------ CLI
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="consolidate")
    ap.add_argument("cmd", choices=["fetch", "ingest", "report", "rebuild", "understand", "ocr", "export-rag", "export-facts", "export-training"])
    ap.add_argument("--app", required=True, help="app key (e.g. flstudio, webapp:figma.com) for the graph; for `fetch` the name to search for")
    ap.add_argument("--name", default="")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--videos", nargs="*", default=[])
    ap.add_argument("--transcripts", nargs="*", default=[], help="json files of segments [{start,end,text}] in the same order as --videos")
    ap.add_argument("--urls", nargs="*", default=[])
    ap.add_argument("--label", action="store_true", help="OCR the changed region of every event for a label (seconds per event)")
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--fresh", action="store_true", help="ingest: start the graph over (the old graph.json is kept as graph.before-fresh.json)")
    ap.add_argument("--transcribe", action="store_true", help="ingest: fetch captions (or transcribe the audio locally) for each video that has no <name>.transcript.json yet")
    ap.add_argument("--min-min", type=float, default=4.0, help="fetch: shortest video, minutes")
    ap.add_argument("--max-min", type=float, default=20.0, help="fetch: longest video, minutes")
    ap.add_argument("--exclude", nargs="*", default=[], help="fetch: skip videos whose title contains any of these words (other host apps, plugins)")
    ap.add_argument("--dry-run", action="store_true", help="fetch: list the candidates (title, minutes, rough size) and download nothing")
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        r = fetch_videos(a.app, a.n, urls=a.urls, min_s=int(a.min_min * 60), max_s=int(a.max_min * 60), dry_run=a.dry_run, exclude=a.exclude)
        print(json.dumps(r, indent=1))
        return 0 if r else 1
    g = AppGraph.load(a.app)
    if a.cmd == "ingest" and a.fresh and os.path.isfile(g.path):
        shutil_copy(g.path, os.path.join(g.root, "graph.before-fresh.json"))
        g = AppGraph(a.app, g.root)
    if a.cmd == "ingest":
        label_fn = None
        if a.label:
            from core_organs.harvest import video_pipeline as VP
            label_fn = lambda post, bbox: [e.get("name", "") for e in VP.som_of_frame(post, region=tuple(bbox))["elements"] if e.get("name")][:6]
        for i, v in enumerate(a.videos):
            segs = json.load(open(a.transcripts[i], encoding="utf-8")) if i < len(a.transcripts) else None
            if segs is None and (a.transcribe or os.path.isfile(transcript_path(v))):
                segs = fetch_transcript(v)["segments"]
            print(json.dumps(ingest_video(g, v, segments=segs, label_fn=label_fn, sample_fps=a.fps), indent=1))
        print(json.dumps(g.summary(), indent=1))
        return 0
    if a.cmd == "report":
        print(json.dumps(g.summary(), indent=1))
        return 0
    if a.cmd == "ocr":
        print(json.dumps(ocr_edges(g), indent=1))
        return 0
    if a.cmd == "understand":
        print(json.dumps(understanding_report(g, os.path.join(os.path.dirname(DATA), "reports", "video_understanding")), indent=1))
        return 0
    if a.cmd == "rebuild":
        print(json.dumps(rebuild(g), indent=1))
        return 0
    from core_organs import rag as R
    if a.cmd == "export-facts":
        print(json.dumps(export_facts_rag(g, R.get_rag(), a.name or a.app), indent=1, default=str))
    elif a.cmd == "export-rag":
        print(json.dumps(export_rag(g, R.get_rag(), a.name or a.app), indent=1, default=str))
    else:
        print(json.dumps(export_training(g), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
