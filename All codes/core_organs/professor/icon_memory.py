"""
professor.icon_memory -- the Professor never has to ask twice what a picture of a floppy disk means.

Every icon crop is reduced to a 256-bit perceptual fingerprint that ignores colour theme (it hashes |pixel - background|, so a white-on-dark Save and a
dark-on-white Save collide on purpose) and scale. Names arrive from three sources, in descending trust:
    uia  (an accessibility tree named the control that sits on these pixels -- free supervised data)
    ocr  (a caption printed on/next to it)
    vlm  (the vision model named it from a contact sheet)
and are stored as votes. A later scan of ANY application (even one with no accessibility tree) first looks the icon up here; only unknown icons go to the model.
Storage: one sqlite file; lookup is a vectorised XOR + popcount over all fingerprints.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from . import config as CFG
from .schema import fold

_TRUST = {"uia": 3, "ocr": 2, "knowledge": 2, "vlm": 1}
_POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def fingerprint(crop: Image.Image, side: int = 16) -> bytes:
    """256-bit hash of an icon crop. Steps chosen by measurement (fp_experiment: same icon across light/dark/125%/150% vs 14 different icons):
    grey -> |pixel - border-median| (theme invariant) -> crop to the ink -> centre on a square (aspect kept, size dropped) -> Gaussian blur (stroke-thickness
    invariant) -> 16x16 -> threshold at 30% of the peak. Same icon: mean distance ~12 bits (p90 30); different icons: never below 39."""
    from PIL import ImageFilter
    g = np.asarray(crop.convert("L"), dtype=np.float32)
    if g.size == 0 or min(g.shape) < 3:
        return bytes(side * side // 8)
    border = np.concatenate([g[0, :], g[-1, :], g[:, 0], g[:, -1]])
    ink = np.abs(g - float(np.median(border)))
    if ink.max() < 6:
        return bytes(side * side // 8)
    ys, xs = np.nonzero(ink > max(8.0, 0.25 * float(ink.max())))
    if len(ys):
        ink = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = ink.shape
    s = max(h, w)
    sq = np.zeros((s, s), dtype=np.float32)
    sq[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = ink
    im = Image.fromarray(np.clip(sq, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(0.6, 2.5 * s / 24.0)))
    a = np.asarray(im.resize((side, side), Image.BOX), dtype=np.float32)
    bits = (a > 0.3 * float(a.max())).astype(np.uint8).flatten()
    return np.packbits(bits).tobytes()


def hamming(a: bytes, b: bytes) -> int:
    return int(_POP[np.bitwise_xor(np.frombuffer(a, np.uint8), np.frombuffer(b, np.uint8))].sum())


class IconMemory:
    def __init__(self, path: Optional[str] = None):
        self.path = path or CFG.ICON_DB
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS icons(fp BLOB PRIMARY KEY, seen INTEGER DEFAULT 1, updated REAL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS votes(fp BLOB, label TEXT, source TEXT, n INTEGER DEFAULT 1, app TEXT DEFAULT '', "
                         "PRIMARY KEY(fp,label,source))")
        self._db.commit()
        self._fps: np.ndarray = np.zeros((0, 32), np.uint8)
        self._keys: List[bytes] = []
        self._load()

    def _load(self) -> None:
        with self._lock:
            rows = [r[0] for r in self._db.execute("SELECT fp FROM icons")]
            self._keys = rows
            self._fps = np.frombuffer(b"".join(rows), np.uint8).reshape(-1, 32) if rows else np.zeros((0, 32), np.uint8)

    def __len__(self) -> int:
        return len(self._keys)

    def nearest(self, fp: bytes, tol: int = 30) -> List[Tuple[bytes, int]]:
        if not len(self._keys):
            return []
        d = _POP[np.bitwise_xor(self._fps, np.frombuffer(fp, np.uint8))].sum(axis=1)
        idx = np.nonzero(d <= tol)[0]
        return sorted(((self._keys[i], int(d[i])) for i in idx), key=lambda t: t[1])

    def lookup(self, fp: bytes, tol: int = 30) -> Optional[Dict[str, object]]:
        """Best-supported name for pixels like these, or None. conf rises with trust of the source, number of votes and closeness of the match."""
        with self._lock:
            near = self.nearest(fp, tol)
            if not near:
                return None
            tally: Dict[str, float] = {}
            best_src: Dict[str, str] = {}
            for key, dist in near[:12]:
                for label, source, n in self._db.execute("SELECT label,source,n FROM votes WHERE fp=?", (key,)):
                    w = _TRUST.get(source, 1) * (1.0 + min(n, 5) * 0.4) * (1.0 - dist / (tol * 2.5))
                    tally[label] = tally.get(label, 0.0) + w
                    if _TRUST.get(source, 1) >= _TRUST.get(best_src.get(label, "vlm"), 1):
                        best_src[label] = source
            if not tally:
                return None
            label = max(tally, key=lambda k: tally[k])
            total = sum(tally.values())
            share = tally[label] / total
            top = tally[label]
            conf = min(0.97, 0.35 + 0.1 * top) * (0.55 + 0.45 * share)
            return {"label": label, "conf": round(conf, 3), "source": best_src.get(label, "vlm"), "distance": near[0][1], "support": round(top, 2)}

    def learn(self, fp: bytes, label: str, source: str, app: str = "") -> None:
        label = (label or "").strip()
        if not label or label == "?" or source not in _TRUST or len(label) > 40:
            return
        with self._lock:
            exact = self._db.execute("SELECT 1 FROM icons WHERE fp=?", (fp,)).fetchone()
            if not exact:
                self._db.execute("INSERT INTO icons(fp,seen,updated) VALUES(?,1,?)", (fp, time.time()))
                self._keys.append(fp)
                self._fps = np.vstack([self._fps, np.frombuffer(fp, np.uint8)[None, :]]) if len(self._fps) else np.frombuffer(fp, np.uint8)[None, :].copy()
            else:
                self._db.execute("UPDATE icons SET seen=seen+1, updated=? WHERE fp=?", (time.time(), fp))
            self._db.execute("INSERT INTO votes(fp,label,source,n,app) VALUES(?,?,?,1,?) ON CONFLICT(fp,label,source) DO UPDATE SET n=n+1", (fp, label, source, app))
            self._db.commit()

    def stats(self) -> Dict[str, object]:
        with self._lock:
            by = {s: n for s, n in self._db.execute("SELECT source, COUNT(*) FROM votes GROUP BY source")}
            return {"icons": len(self._keys), "votes_by_source": by, "path": self.path}

    def close(self) -> None:
        with self._lock:
            try:
                self._db.commit()
                self._db.close()
            except Exception:
                pass


_MEM: Optional[IconMemory] = None


def memory() -> IconMemory:
    global _MEM
    if _MEM is None:
        _MEM = IconMemory()
    return _MEM
