"""
professor.ml.nn -- a small neural network in plain numpy: sparse hashed features -> ReLU hidden layer -> several output heads, trained ONLINE with (lazy) Adam.

No framework, no GPU, no downloads: it has to learn WHILE the automation runs, on a laptop that is also running a vision model, so it is tiny on purpose (about 100k parameters) and every
update touches only the rows of the weight matrix whose features were present. Heads are independent: a softmax head (k classes) or a sigmoid head (k = 1); a head whose target is
missing for an example is simply skipped for that example.
"""

from __future__ import annotations

import io
import math
import zlib
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

Features = Tuple[np.ndarray, np.ndarray]                      # (indices, values)


def hash_features(tokens: Iterable[Tuple[str, float]], n: int) -> Features:
    """Signed feature hashing (crc32: stable across runs, unlike Python's hash()). Identical indices are summed."""
    acc: Dict[int, float] = {}
    for tok, val in tokens:
        h = zlib.crc32(tok.encode("utf-8", "replace"))
        idx = h % n
        sign = 1.0 if (h >> 31) & 1 else -1.0
        acc[idx] = acc.get(idx, 0.0) + sign * float(val)
    if not acc:
        return np.zeros(0, np.int64), np.zeros(0, np.float64)
    idx = np.fromiter(acc.keys(), np.int64, len(acc))
    val = np.fromiter(acc.values(), np.float64, len(acc))
    return idx, val


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


class SparseMLP:
    def __init__(self, n_in: int, n_hidden: int, heads: Dict[str, int], lr: float = 0.02, seed: int = 7, l2: float = 1e-5):
        rng = np.random.default_rng(seed)
        self.n_in, self.H, self.heads, self.lr, self.l2 = n_in, n_hidden, dict(heads), lr, l2
        self.W1 = rng.normal(0.0, 0.1, (n_in, n_hidden))
        self.b1 = np.zeros(n_hidden)
        self.Wh = {h: rng.normal(0.0, 0.3, (n_hidden, k)) for h, k in heads.items()}
        self.bh = {h: np.zeros(k) for h, k in heads.items()}
        self.m: Dict[str, np.ndarray] = {}
        self.v: Dict[str, np.ndarray] = {}
        self.t = 0
        self._init_moments()

    # ---------------------------------------------------------------------------------------------------- parameters
    def _params(self) -> Dict[str, np.ndarray]:
        p = {"W1": self.W1, "b1": self.b1}
        for h in self.heads:
            p[f"Wh_{h}"], p[f"bh_{h}"] = self.Wh[h], self.bh[h]
        return p

    def _init_moments(self) -> None:
        for k, a in self._params().items():
            self.m[k], self.v[k] = np.zeros_like(a), np.zeros_like(a)

    def n_params(self) -> int:
        return int(sum(a.size for a in self._params().values()))

    # ------------------------------------------------------------------------------------------------------ forward
    def hidden(self, f: Features) -> Tuple[np.ndarray, np.ndarray]:
        idx, val = f
        pre = (self.W1[idx] * val[:, None]).sum(axis=0) + self.b1 if len(idx) else self.b1.copy()
        return pre, np.maximum(pre, 0.0)

    def predict(self, f: Features) -> Dict[str, np.ndarray]:
        _pre, h = self.hidden(f)
        out = {}
        for name, k in self.heads.items():
            z = h @ self.Wh[name] + self.bh[name]
            out[name] = _softmax(z) if k > 1 else np.array([_sigmoid(float(z[0]))])
        return out

    # ----------------------------------------------------------------------------------------------------- training
    def train_batch(self, batch: Sequence[Tuple[Features, Dict[str, Any]]], lr: Optional[float] = None) -> float:
        """One Adam step on the mean gradient of a mini-batch. `targets[head]` is a class index (softmax head) or 0/1 (sigmoid head); a missing head is skipped. Returns the mean loss."""
        if not batch:
            return 0.0
        lr = self.lr if lr is None else lr
        gW1: Dict[int, np.ndarray] = {}
        gb1 = np.zeros(self.H)
        gWh = {h: np.zeros_like(a) for h, a in self.Wh.items()}
        gbh = {h: np.zeros_like(a) for h, a in self.bh.items()}
        loss, n_terms = 0.0, 0
        for f, targets in batch:
            idx, val = f
            pre, h = self.hidden(f)
            dh = np.zeros(self.H)
            for name, k in self.heads.items():
                if name not in targets or targets[name] is None:
                    continue
                z = h @ self.Wh[name] + self.bh[name]
                if k > 1:
                    p = _softmax(z)
                    y = int(targets[name])
                    loss += -math.log(max(1e-9, float(p[y])))
                    d = p.copy()
                    d[y] -= 1.0
                else:
                    p1 = _sigmoid(float(z[0]))
                    y = float(targets[name])
                    loss += -(y * math.log(max(1e-9, p1)) + (1 - y) * math.log(max(1e-9, 1 - p1)))
                    d = np.array([p1 - y])
                gWh[name] += np.outer(h, d)
                gbh[name] += d
                dh += self.Wh[name] @ d
                n_terms += 1
            dh = dh * (pre > 0)
            gb1 += dh
            for i, v in zip(idx.tolist(), val.tolist()):
                g = gW1.get(i)
                if g is None:
                    gW1[i] = v * dh
                else:
                    g += v * dh
        B = float(len(batch))
        self.t += 1
        b1c, b2c, eps = 0.9, 0.999, 1e-8
        corr = lr * math.sqrt(1 - b2c ** self.t) / (1 - b1c ** self.t)

        def adam(name: str, grad: np.ndarray, rows: Optional[List[int]] = None, w: Optional[np.ndarray] = None) -> None:
            m, v, p = self.m[name], self.v[name], (w if w is not None else self._params()[name])
            if rows is None:
                grad = grad + self.l2 * p
                m *= b1c
                m += (1 - b1c) * grad
                v *= b2c
                v += (1 - b2c) * grad * grad
                p -= corr * m / (np.sqrt(v) + eps)
            else:
                r = np.asarray(rows)
                grad = grad + self.l2 * p[r]
                m[r] = b1c * m[r] + (1 - b1c) * grad
                v[r] = b2c * v[r] + (1 - b2c) * grad * grad
                p[r] -= corr * m[r] / (np.sqrt(v[r]) + eps)

        if gW1:
            rows = list(gW1.keys())
            adam("W1", np.vstack([gW1[r] for r in rows]) / B, rows, self.W1)
        adam("b1", gb1 / B)
        for name in self.heads:
            adam(f"Wh_{name}", gWh[name] / B)
            adam(f"bh_{name}", gbh[name] / B)
        return loss / max(1, n_terms)

    # ---------------------------------------------------------------------------------------------------- persistence
    def state(self) -> Dict[str, np.ndarray]:
        s = {k: a.copy() for k, a in self._params().items()}
        s["_t"] = np.array([self.t])
        s["_meta"] = np.array([self.n_in, self.H])
        return s

    def load_state(self, s: Dict[str, np.ndarray]) -> bool:
        try:
            if tuple(int(x) for x in s["_meta"]) != (self.n_in, self.H):
                return False
            self.W1[:] = s["W1"]
            self.b1[:] = s["b1"]
            for h in self.heads:
                self.Wh[h][:] = s[f"Wh_{h}"]
                self.bh[h][:] = s[f"bh_{h}"]
            self.t = int(s["_t"][0])
            return True
        except Exception:
            return False

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        np.savez_compressed(buf, **self.state())
        return buf.getvalue()

    def save(self, path: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(self.to_bytes())
        import os
        os.replace(tmp, path)

    def load(self, path: str) -> bool:
        try:
            with np.load(path) as z:
                return self.load_state({k: z[k] for k in z.files})
        except Exception:
            return False
