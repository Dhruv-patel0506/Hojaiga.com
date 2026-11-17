"""
professor.ml.candidates -- the VISION-CANDIDATE model: is this box the vision tier proposed a real control, or noise?

Free supervision: whenever a window that HAS an accessibility tree is scanned, the tree says exactly which pixel boxes are controls - so every such scan labels all of the vision tier's
candidates (matches a tree control = positive, matches nothing = negative) and trains this model, with no human labelling. What it learns is the SHAPE of controls (size, aspect, ink,
kind, neighbours, position in the picture, whether the detector also saw it), which generalises across applications and toolkits. It is then used where there is NO tree (Blender, canvas /
game / custom-drawn UIs): to rank candidates so the naming budget goes to the likely controls first and to drop the near-certain noise.

Honest scoring: `evaluate()` reports ROC-AUC, and precision / recall at the operating threshold, on scans the model did not train on (tests hold out whole applications / themes / scales).
"""

from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .nn import SparseMLP, hash_features

N_IN = 1024
MIN_DROP_P = 0.04


def _bucket(x: float, step: float, cap: int) -> int:
    return int(max(0, min(cap, x // step)))


def features_for(cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray] = None) -> List[Tuple[np.ndarray, np.ndarray]]:
    W, H = max(1, size[0]), max(1, size[1])
    centers = np.array([[c.box.cx, c.box.cy] for c in cands]) if cands else np.zeros((0, 2))
    out = []
    for i, c in enumerate(cands):
        b = c.box
        w, h = max(1.0, b.w), max(1.0, b.h)
        dens = 0.0
        if ink is not None and b.valid:
            bb = b.clip(ink.shape[1], ink.shape[0])
            if bb.valid:
                x1, y1, x2, y2 = bb.ituple()
                dens = float((ink[y1:y2, x1:x2] > 0).mean())
        near = int(((np.abs(centers[:, 0] - b.cx) < 56) & (np.abs(centers[:, 1] - b.cy) < 40)).sum()) - 1 if len(centers) else 0
        kind = c.kind
        yolo = "yolo" in (c.flags or [])
        aspect = int(round(math.log2(w / h) * 2)) if w > 0 and h > 0 else 0
        t: List[Tuple[str, float]] = [("bias", 1.0), (f"kind={kind}", 1.0), (f"wb={_bucket(w, 6, 24)}", 0.6), (f"hb={_bucket(h, 6, 16)}", 0.6), (f"kind|wb={kind}|{_bucket(w, 8, 16)}", 0.8),
                                      (f"kind|hb={kind}|{_bucket(h, 8, 12)}", 0.8), (f"asp={max(-6, min(6, aspect))}", 0.6), (f"kind|asp={kind}|{max(-6, min(6, aspect))}", 0.6),
                                      (f"ink={_bucket(dens * 20, 1, 20)}", 0.7), (f"kind|ink={kind}|{_bucket(dens * 10, 1, 10)}", 0.9), (f"near={min(10, near)}", 0.5), (f"kind|near={kind}|{min(10, near)}", 0.5),
                                      (f"x={_bucket(b.cx / W * 12, 1, 11)}", 0.3), (f"y={_bucket(b.cy / H * 16, 1, 15)}", 0.4), (f"kind|y={kind}|{_bucket(b.cy / H * 12, 1, 11)}", 0.5),
                                      (f"strip={int(c.in_strip >= 0)}", 0.7), (f"kind|strip={kind}|{int(c.in_strip >= 0)}", 0.6), (f"dd={int(bool(c.has_dropdown))}", 0.4),
                                      (f"yolo={int(yolo)}", 0.8), (f"yolo|kind={int(yolo)}|{kind}", 0.8), ("dens", dens), ("logw", math.log(w) / 5.0), ("logh", math.log(h) / 5.0)]
        if c.text:
            t += [("hastext", 0.5), (f"tlen={min(12, len(c.text) // 3)}", 0.4), (f"ocr={_bucket(c.ocr_conf, 15, 6)}", 0.4), (f"alpha={int(sum(ch.isalpha() for ch in c.text) / max(1, len(c.text)) * 4)}", 0.4)]
        out.append(hash_features(t, N_IN))
    return out


def match_labels(cands: Sequence[Any], truth: Sequence[Any]) -> List[int]:
    """1 when a candidate IS a control the accessibility tree knows (its box lies on / inside one, or overlaps it substantially), else 0."""
    y = []
    for c in cands:
        hit = 0
        for t in truth:
            if c.box.iou(t) >= 0.3 or (c.box.overlap_frac(t) >= 0.6 and t.area <= 4.0 * max(1.0, c.box.area)):
                hit = 1
                break
        y.append(hit)
    return y


def roc_auc(p: Sequence[float], y: Sequence[int]) -> float:
    p, y = np.asarray(p, float), np.asarray(y, int)
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = np.argsort(np.argsort(np.concatenate([pos, neg]))) + 1.0
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


class CandidateModel:
    def __init__(self, path: Optional[str] = None, hidden: int = 24, lr: float = 0.03, seed: int = 11):
        self.path = path
        self.net = SparseMLP(N_IN, hidden, {"is_control": 1}, lr=lr, seed=seed)
        self.seen = 0
        self.pos = 0
        self.recent: List[Tuple[Any, Dict[str, Any]]] = []
        self.updates = 0
        self.sources: set = set()                              # which applications / layouts it has learnt from (generalisation needs diversity)
        self.preq_p: List[float] = []
        self.preq_y: List[int] = []
        if path and os.path.isfile(path):
            self._load(path)

    def prob(self, cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray] = None) -> np.ndarray:
        return np.array([float(self.net.predict(f)["is_control"][0]) for f in features_for(cands, size, ink)]) if cands else np.zeros(0)

    def observe_scan(self, cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray], truth: Sequence[Any], train: bool = True, epochs: int = 2, source: str = "") -> Dict[str, Any]:
        """Learn from one scan of a window that has a tree. Candidates are predicted first (prequential AUC), then trained on, balanced so rare positives are not drowned."""
        if not cands or not truth:
            return {"examples": 0}
        valid_truth = [t for t in truth if getattr(t, "w", 0) > 4 and getattr(t, "h", 0) > 4 and (not hasattr(t, "cx") or (0 <= t.cx <= size[0] and 0 <= t.cy <= size[1]))]
        if len(valid_truth) < 6:
            return {"examples": 0, "skipped": "unlaid_or_offscreen"}
        feats = features_for(cands, size, ink)
        y = match_labels(cands, valid_truth)
        if sum(y) == 0:
            return {"examples": 0, "skipped": "no_positive_matches"}
        if source:
            self.sources.add(source)
        if self.seen >= 40:
            self.preq_p += [float(self.net.predict(f)["is_control"][0]) for f in feats]
            self.preq_y += y
            self.preq_p, self.preq_y = self.preq_p[-4000:], self.preq_y[-4000:]
        exs = [(f, {"is_control": float(t)}) for f, t in zip(feats, y)]
        self.seen += len(exs)
        self.pos += sum(y)
        for ex in exs:
            if len(self.recent) < 6000:
                self.recent.append(ex)
            else:
                self.recent[int(np.random.randint(0, len(self.recent)))] = ex
        loss = 0.0
        if train:
            order = np.random.permutation(len(exs))
            for _ in range(epochs):
                for k in range(0, len(order), 32):
                    loss = self.net.train_batch([exs[i] for i in order[k:k + 32]])
                    self.updates += 1
        return {"examples": len(exs), "positives": int(sum(y)), "loss": round(loss, 4)}

    def replay(self, n: int = 48) -> float:
        if len(self.recent) < 16:
            return 0.0
        idx = np.random.choice(len(self.recent), size=min(n, len(self.recent)), replace=False)
        self.updates += 1
        return self.net.train_batch([self.recent[i] for i in idx])

    def evaluate(self, cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray], truth: Sequence[Any], threshold: float = 0.5) -> Dict[str, Any]:
        """Score on a scan that the model has NOT trained on."""
        p = self.prob(cands, size, ink)
        y = np.array(match_labels(cands, truth))
        keep = p >= threshold
        tp = int((keep & (y == 1)).sum())
        return {"n": len(cands), "positives": int(y.sum()), "auc": round(roc_auc(p, y), 4), "base_precision": round(float(y.mean()), 4) if len(y) else None,
                "precision": round(tp / max(1, int(keep.sum())), 4), "recall": round(tp / max(1, int(y.sum())), 4), "kept": int(keep.sum())}

    def metrics(self) -> Dict[str, Any]:
        auc = roc_auc(self.preq_p, self.preq_y) if len(self.preq_y) > 50 else float("nan")
        return {"seen": self.seen, "positives": self.pos, "updates": self.updates, "prequential_auc": None if math.isnan(auc) else round(auc, 4), "parameters": self.net.n_params(),
                "sources": len(self.sources), "ready_to_filter": self.ready()}

    def ready(self) -> bool:
        """May the model act on a window that has NO tree? Only after it has learnt from enough different applications AND predicted new scans well BEFORE learning from them
        (measured: trained on one layout it is at chance on a very different one, so an under-travelled model must not drop anything)."""
        auc = roc_auc(self.preq_p, self.preq_y) if len(self.preq_y) > 100 else float("nan")
        return self.seen >= 400 and len(self.sources) >= 4 and not math.isnan(auc) and auc >= 0.85

    def filter(self, cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray], min_p: float = MIN_DROP_P) -> Tuple[List[Any], int]:
        """Drop only the near-certain noise (p < min_p); returns (kept candidates, dropped). Never used until the model has seen enough."""
        if not cands or not self.ready():
            return list(cands), 0
        p = self.prob(cands, size, ink)
        kept = [c for c, pi in zip(cands, p) if pi >= min_p]
        return kept, len(cands) - len(kept)

    def save(self, path: Optional[str] = None) -> None:
        path = path or self.path
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.net.save(path)
        with open(path + ".json", "w", encoding="utf-8") as fh:
            json.dump({"seen": self.seen, "pos": self.pos, "updates": self.updates, "sources": sorted(self.sources), "preq_p": self.preq_p[-2000:], "preq_y": self.preq_y[-2000:]}, fh)

    def _load(self, path: str) -> None:
        if self.net.load(path):
            try:
                with open(path + ".json", "r", encoding="utf-8") as fh:
                    m = json.load(fh)
                self.seen, self.pos, self.updates = int(m.get("seen", 0)), int(m.get("pos", 0)), int(m.get("updates", 0))
                self.sources = set(m.get("sources", []))
                self.preq_p, self.preq_y = list(m.get("preq_p", [])), list(m.get("preq_y", []))
            except Exception:
                pass
