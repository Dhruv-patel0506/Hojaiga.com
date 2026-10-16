"""
rag.icons -- Sub-RAG 1: the Visual & Icon Vault (DESIGN.md section 5.1).

A thin federation layer over professor.icon_memory.IconMemory (the measured, theme-invariant 256-bit fingerprint; same icon ~12 bits apart, different icons >= 39), relocated to
<root>/rag/icons.db, with the two things the design adds:

    dHash64 O(1) prefilter    an in-RAM dict from a 64-bit difference hash to the fingerprints that carry it. A hit is accepted only when the 256-bit distance is <= ICON_DHASH_MAX_BITS,
                              so a dHash collision can never name an icon wrongly; a miss falls through to the vectorised 256-bit Hamming scan (app-scoped votes first).
    join to commands          a label is resolved through the Lexicon to a command_id, and the label itself is recorded there as an 'icon_label' alias.

Trust is the IconMemory trust order uia(3) > ocr = knowledge(2) > vlm(1). A UIA name that disagrees with an existing VLM name on the same pixels wins, and the disagreement is logged
(`disagreements`) for symbol_eval. A miss is never an answer: it is returned as a gap ('icon_unknown:<fp>') for the caller to batch into one contact sheet.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from . import config as C
from .lexicon import Lexicon
from .types import Evidence

try:
    import safety_guard as _SG                      # type: ignore
except Exception:                                   # pragma: no cover
    try:
        from core_organs import safety_guard as _SG
    except Exception:
        _SG = None


def dhash64(crop) -> int:
    """64-bit difference hash of |pixel - border median| (the same theme invariance as the 256-bit fingerprint), 9x8 grid."""
    from PIL import Image
    g = np.asarray(crop.convert("L"), dtype=np.float32)
    if g.size == 0 or min(g.shape) < 3:
        return 0
    border = np.concatenate([g[0, :], g[-1, :], g[:, 0], g[:, -1]])
    ink = np.abs(g - float(np.median(border)))
    top = float(ink.max()) or 1.0
    small = np.asarray(Image.fromarray((ink / top * 255).astype(np.uint8)).resize((9, 8), Image.BILINEAR), dtype=np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def _s64(v: int) -> int:
    v &= (1 << 64) - 1
    return v - (1 << 64) if v >= (1 << 63) else v


def _u64(v: int) -> int:
    return int(v) & ((1 << 64) - 1)


class Icons:
    name = "icon"

    def __init__(self, st, lexicon: Lexicon, memory=None):
        self.st, self.lex = st, lexicon
        if memory is None:
            from core_organs.professor.icon_memory import IconMemory
            memory = IconMemory(st.path("icons.db"))
        self.mem = memory
        self._db = memory._db
        self._db.execute("CREATE TABLE IF NOT EXISTS dh(fp BLOB PRIMARY KEY, dhash INTEGER)")
        self._db.execute("CREATE INDEX IF NOT EXISTS ix_dh ON dh(dhash)")
        self._db.execute("CREATE TABLE IF NOT EXISTS disagreements(fp BLOB, old_label TEXT, old_source TEXT, new_label TEXT, new_source TEXT, ts REAL)")
        self._db.commit()
        self._by_dh: Dict[int, List[bytes]] = {}
        for fp, dh in self._db.execute("SELECT fp, dhash FROM dh"):
            self._by_dh.setdefault(_u64(dh), []).append(bytes(fp))

    # ---- hashing ------------------------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def fingerprint(crop) -> Tuple[bytes, int]:
        from core_organs.professor.icon_memory import fingerprint
        return fingerprint(crop), dhash64(crop)

    # ---- reads --------------------------------------------------------------------------------------------------------------------------------------
    def _tally(self, keys: Sequence[Tuple[bytes, int]], app_key: str, tol: int) -> Optional[Dict[str, Any]]:
        from core_organs.professor.icon_memory import _TRUST
        votes = []
        for key, dist in keys[:12]:
            for label, source, n, app in self.mem._db.execute("SELECT label, source, n, app FROM votes WHERE fp=?", (key,)):
                votes.append((label, source, n, app, dist))
        if not votes:
            return None
        scoped = [v for v in votes if v[3] == app_key] if app_key else []
        use = scoped or votes                                         # this app's own votes when there are any, else everyone's
        tally: Dict[str, float] = {}
        best_src: Dict[str, str] = {}
        for label, source, n, app, dist in use:
            w = _TRUST.get(source, 1) * (1.0 + min(n, 5) * 0.4) * (1.0 - dist / (tol * 2.5))
            tally[label] = tally.get(label, 0.0) + w
            if _TRUST.get(source, 1) >= _TRUST.get(best_src.get(label, "vlm"), 1):
                best_src[label] = source
        label = max(tally, key=lambda k: tally[k])
        share = tally[label] / (sum(tally.values()) or 1.0)
        conf = min(0.97, 0.35 + 0.1 * tally[label]) * (0.55 + 0.45 * share)
        return {"label": label, "conf": round(conf, 3), "source": best_src.get(label, "vlm"), "distance": min(d for _, d in keys[:12]), "scoped": bool(scoped)}

    def lookup_fp(self, fp: bytes, dh: int = 0, app_key: str = "") -> Tuple[Optional[Dict[str, Any]], str]:
        """(hit, path) where path is 'dhash' (O(1)) or 'hamming'. hit = {label, conf, source, distance} or None."""
        from core_organs.professor.icon_memory import hamming
        if dh and dh in self._by_dh:
            keys = [(k, hamming(fp, k)) for k in self._by_dh[dh]]
            keys = sorted([kd for kd in keys if kd[1] <= C.ICON_DHASH_MAX_BITS], key=lambda t: t[1])
            if keys:
                hit = self._tally(keys, app_key, C.ICON_HAMMING_TOL)
                if hit:
                    return hit, "dhash"
        near = self.mem.nearest(fp, C.ICON_HAMMING_TOL)
        if near:
            hit = self._tally(near, app_key, C.ICON_HAMMING_TOL)
            if hit:
                return hit, "hamming"
        return None, "miss"

    def lookup(self, crop=None, fp: Optional[bytes] = None, dh: int = 0, app_key: str = "") -> Tuple[Optional[Evidence], List[str]]:
        if fp is None:
            if crop is None:
                return None, ["icon_no_input"]
            fp, dh = self.fingerprint(crop)
        hit, path = self.lookup_fp(fp, dh, app_key)
        if not hit:
            return None, [f"icon_unknown:{fp.hex()[:16]}"]
        cmds = [m.command_id for m in self.lex.resolve(app_key, hit["label"], limit=1)] if app_key else []
        safety = "allow" if _SG is None else (lambda d: "allow" if d.allowed else d.category)(_SG.check(hit["label"]))
        trust = {"uia": "learned", "ocr": "catalog", "knowledge": "catalog", "vlm": "llm"}.get(hit["source"], "seed")
        return Evidence("icon", app_key, "icon_label", hit["label"], cmds, {"label": hit["label"], "source": hit["source"], "distance": hit["distance"], "path": path,
                                                                           "fp": fp.hex()}, trust, float(hit["conf"]), 0.1, safety, f"icon:{fp.hex()[:12]}", "", float(hit["conf"])), []

    def lookup_many(self, crops: Sequence[Any], app_key: str = "") -> Tuple[Dict[int, Evidence], List[int]]:
        """({index: evidence}, [indexes that missed]) -- the misses are what one contact-sheet vision call should name."""
        hits, misses = {}, []
        for i, c in enumerate(crops):
            ev, _ = self.lookup(c, app_key=app_key)
            if ev:
                hits[i] = ev
            else:
                misses.append(i)
        return hits, misses

    # ---- writes -------------------------------------------------------------------------------------------------------------------------------------
    def learn(self, label: str, source: str, crop=None, fp: Optional[bytes] = None, dh: int = 0, app_key: str = "") -> bool:
        if fp is None:
            if crop is None:
                return False
            fp, dh = self.fingerprint(crop)
        label = (label or "").strip()
        if not label or label == "?":
            return False
        before, _ = self.lookup_fp(fp, dh, app_key)
        if source == "uia" and before and before["source"] == "vlm" and before["label"].lower() != label.lower():
            self._db.execute("INSERT INTO disagreements(fp,old_label,old_source,new_label,new_source,ts) VALUES(?,?,?,?,?,?)", (fp, before["label"], "vlm", label, "uia", time.time()))
        self.mem.learn(fp, label, source, app_key)
        if dh:
            self._db.execute("INSERT OR REPLACE INTO dh(fp,dhash) VALUES(?,?)", (fp, _s64(dh)))
            if fp not in self._by_dh.setdefault(_u64(dh), []):
                self._by_dh[_u64(dh)].append(fp)
        self._db.commit()
        if app_key:
            hit = self.lex.best(app_key, label)
            if hit:
                self.lex.add_alias(app_key, label, hit.command_id, "icon_label", "icon:" + source, {"uia": "learned", "ocr": "catalog", "knowledge": "catalog", "vlm": "llm"}.get(source, "seed"))
        self.st.bump(f"icon:{app_key}")
        return True

    def disagreements(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self._db.execute("SELECT hex(fp), old_label, new_label, ts FROM disagreements ORDER BY ts DESC LIMIT ?", (limit,))
        return [{"fp": a, "vlm_said": b, "uia_said": c, "ts": d} for a, b, c, d in cur]

    def stats(self, app_key: str = "") -> Dict[str, Any]:
        s = self.mem.stats()
        s["dhash_buckets"] = len(self._by_dh)
        return s

    def forget_app(self, app_key: str) -> int:
        cur = self._db.execute("DELETE FROM votes WHERE app=?", (app_key,))
        self._db.commit()
        return int(cur.rowcount)

    def close(self) -> None:
        self.mem.close()
