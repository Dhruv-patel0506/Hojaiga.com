# brain/conveyor/ml_stations.py
"""Belt stations 3–6, NumPy first (PyTorch used when present):

3 vectorization      TF-IDF (learned vocabulary) + the brain's hashed n-gram embeddings + VLM image vectors
4 classical ML       label discovery · k-means++ topics · Multinomial Naive Bayes · softmax logistic
                     regression · stratified k-fold · anomaly detection
5 deep learning      MLP classifier (PyTorch or NumPy backprop) · Transformer-encoder text classifier
6 algorithms         keyphrase co-occurrence graph · PageRank · label-propagation communities
"""
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

_TOKEN = re.compile(r"\w+", re.UNICODE)


# ─────────────────────────────────────────────────────────────── 3. vectorization
class TfidfVectorizer:
    """Vocabulary and IDF are learned from the data; very common terms get IDF→0 on their own."""

    def __init__(self, max_features: int = 2048, min_df: int = 2, max_df_ratio: float = 0.9):
        self.max_features, self.min_df, self.max_df_ratio = max_features, min_df, max_df_ratio
        self.vocab: Dict[str, int] = {}
        self.idf: np.ndarray = np.zeros(0, dtype=np.float32)

    @staticmethod
    def tokens(text: str) -> List[str]:
        w = [t.lower() for t in _TOKEN.findall(text)]
        return w + [a + "_" + b for a, b in zip(w, w[1:])]

    def fit(self, texts: List[str]) -> "TfidfVectorizer":
        n = len(texts)
        df: Counter = Counter()
        for t in texts:
            df.update(set(self.tokens(t)))
        min_df = self.min_df if n >= 10 else 1
        keep = [(w, c) for w, c in df.items() if c >= min_df and c <= max(1, self.max_df_ratio * n)]
        keep.sort(key=lambda wc: (-wc[1], wc[0]))
        self.vocab = {w: i for i, (w, _) in enumerate(keep[: self.max_features])}
        self.idf = np.array([math.log((1 + n) / (1 + df[w])) + 1 for w in self.vocab], dtype=np.float32)
        return self

    def transform(self, texts: List[str]) -> np.ndarray:
        X = np.zeros((len(texts), len(self.vocab)), dtype=np.float32)
        for r, t in enumerate(texts):
            for w, c in Counter(self.tokens(t)).items():
                j = self.vocab.get(w)
                if j is not None:
                    X[r, j] = 1.0 + math.log(c)
        X *= self.idf
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        return X / np.maximum(norms, 1e-8)

    def state(self) -> Dict[str, Any]:
        return {"vocab": self.vocab, "idf": self.idf.tolist()}

    @classmethod
    def from_state(cls, st: Dict[str, Any]) -> "TfidfVectorizer":
        v = cls()
        v.vocab, v.idf = st["vocab"], np.asarray(st["idf"], dtype=np.float32)
        return v


def image_features(rgb: np.ndarray, size: int = 64, cells: int = 8, bins: int = 9) -> np.ndarray:
    """Classic computer-vision descriptor (no training needed): HOG-style histograms of gradient
    orientation per cell + per-channel colour histograms. Shapes and textures separate well."""
    from PIL import Image
    im = Image.fromarray(rgb.astype(np.uint8)).convert("RGB").resize((size, size))
    a = np.asarray(im, dtype=np.float32) / 255.0
    g = a.mean(-1)
    gx = np.zeros_like(g)
    gy = np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1] = g[2:] - g[:-2]
    mag = np.hypot(gx, gy)
    ang = (np.arctan2(gy, gx) % np.pi) / np.pi * bins
    step = size // cells
    hog = np.zeros((cells, cells, bins), dtype=np.float32)
    for i in range(cells):
        for j in range(cells):
            m = mag[i * step:(i + 1) * step, j * step:(j + 1) * step].ravel()
            b = np.minimum(ang[i * step:(i + 1) * step, j * step:(j + 1) * step].ravel().astype(int), bins - 1)
            hog[i, j] = np.bincount(b, weights=m, minlength=bins)
    hog = hog.ravel()
    hog /= max(np.linalg.norm(hog), 1e-8)
    col = np.concatenate([np.histogram(a[..., c], bins=8, range=(0, 1))[0] for c in range(3)]).astype(np.float32)
    col /= max(col.sum(), 1e-8)
    return np.concatenate([hog, col])


# ─────────────────────────────────────────────────────────────── 4. classical ML
def candidate_label_fields(records: List[Dict[str, Any]]) -> List[str]:
    """Categorical fields: 2..50 short distinct values covering most rows, each value repeated."""
    if len(records) < 6:
        return []
    out = []
    keys = set().union(*[r.keys() for r in records])
    for k in sorted(keys):
        vals = [r.get(k) for r in records if isinstance(r.get(k), (str, int, bool)) and str(r.get(k)).strip()]
        if len(vals) < 0.8 * len(records):
            continue
        counts = Counter(str(v).strip().lower() for v in vals)
        k_cls = len(counts)
        avg_len = sum(len(v) for v in counts) / max(k_cls, 1)
        if 2 <= k_cls <= min(50, len(vals) // 2) and avg_len <= 30 and min(counts.values()) >= 2:
            out.append(k)
    return out


def rank_label_fields(texts: List[str], records: List[Dict[str, Any]], X: np.ndarray) -> List[Dict[str, Any]]:
    """Which categorical field does the text actually predict? Lift of 3-fold Naive Bayes accuracy
    over the majority-class baseline. Random/unrelated columns get lift ≈ 0 and are not used."""
    ranked = []
    for k in candidate_label_fields(records):
        idx = [i for i, r in enumerate(records) if str(r.get(k, "")).strip()]
        y = np.array([str(records[i][k]).strip().lower() for i in idx])
        base = max(Counter(y.tolist()).values()) / len(y)
        acc = cross_validate(MultinomialNB, X[idx], y, k=3)["accuracy"]
        ranked.append({"field": k, "cv_accuracy": acc, "baseline": round(base, 3), "lift": round(acc - base, 3)})
    return sorted(ranked, key=lambda r: -r["lift"])


def discover_label_field(records: List[Dict[str, Any]]) -> Optional[str]:
    """Kept for callers without text vectors: the most label-like categorical field."""
    if len(records) < 6:
        return None
    best, best_score = None, 0.0
    keys = set().union(*[r.keys() for r in records])
    for k in keys:
        vals = [r.get(k) for r in records if isinstance(r.get(k), (str, int, bool)) and str(r.get(k)).strip()]
        if len(vals) < 0.8 * len(records):
            continue
        counts = Counter(str(v).strip().lower() for v in vals)
        k_cls = len(counts)
        avg_len = sum(len(v) for v in counts) / max(k_cls, 1)
        if not (2 <= k_cls <= min(50, len(vals) // 2)) or avg_len > 30 or min(counts.values()) < 2:
            continue
        score = 1.0 - k_cls / len(vals)                   # fewer, larger classes look more like labels
        if score > best_score:
            best, best_score = k, score
    return best


def kmeans(X: np.ndarray, k: int, iters: int = 50, seed: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    centers = [X[rng.integers(len(X))]]
    for _ in range(1, k):                                 # k-means++ seeding
        d = np.min([((X - c) ** 2).sum(1) for c in centers], axis=0)
        centers.append(X[rng.choice(len(X), p=d / d.sum())] if d.sum() > 0 else X[rng.integers(len(X))])
    C = np.stack(centers)
    labels = np.zeros(len(X), dtype=int)
    for _ in range(iters):
        dist = ((X[:, None, :] - C[None]) ** 2).sum(-1)
        new = dist.argmin(1)
        if np.array_equal(new, labels) and _ > 0:
            break
        labels = new
        for j in range(k):
            if (labels == j).any():
                C[j] = X[labels == j].mean(0)
    return labels, C


def silhouette(X: np.ndarray, labels: np.ndarray, sample: int = 400, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(X), size=min(sample, len(X)), replace=False)
    Xs, ls = X[idx], labels[idx]
    D = np.sqrt(((Xs[:, None] - Xs[None]) ** 2).sum(-1))
    scores = []
    for i in range(len(Xs)):
        same = ls == ls[i]
        if same.sum() <= 1:
            continue
        a = D[i, same].sum() / (same.sum() - 1)
        b = min(D[i, ls == c].mean() for c in set(ls.tolist()) if c != ls[i]) if len(set(ls.tolist())) > 1 else 0
        scores.append((b - a) / max(a, b, 1e-9))
    return float(np.mean(scores)) if scores else 0.0


def discover_topics(X: np.ndarray, tfidf: TfidfVectorizer, k_max: int = 8) -> Dict[str, Any]:
    """Pick k by silhouette, then name each cluster by its strongest TF-IDF terms."""
    if len(X) < 4:
        return {"k": 0, "clusters": []}
    best = None
    for k in range(2, min(k_max, len(X) - 1) + 1):
        lab, C = kmeans(X, k)
        s = silhouette(X, lab)
        if best is None or s > best[0]:
            best = (s, k, lab, C)
    s, k, lab, C = best
    inv = {i: w for w, i in tfidf.vocab.items()}
    clusters = []
    for j in range(k):
        if not (lab == j).any():
            continue
        words: List[str] = []
        for t in np.argsort(-C[j]):
            w = inv.get(int(t), "")
            if C[j, t] <= 0 or len(words) >= 4:
                break
            if "_" not in w and w not in words:
                words.append(w)
        clusters.append({"cluster": j, "size": int((lab == j).sum()), "name": "_".join(words)})
    dist = np.sqrt(((X - C[lab]) ** 2).sum(1))
    z = (dist - dist.mean()) / max(dist.std(), 1e-9)
    return {"k": k, "silhouette": round(s, 3), "clusters": clusters, "labels": lab,
            "anomalies": [int(i) for i in np.where(z > 3.0)[0]]}


class MultinomialNB:
    def fit(self, X: np.ndarray, y: np.ndarray, alpha: float = 0.5) -> "MultinomialNB":
        self.classes = np.unique(y)
        counts = np.stack([X[y == c].sum(0) for c in self.classes]) + alpha
        self.log_prob = np.log(counts / counts.sum(1, keepdims=True))
        self.log_prior = np.log(np.array([(y == c).mean() for c in self.classes]))
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        s = X @ self.log_prob.T + self.log_prior
        s -= s.max(1, keepdims=True)
        p = np.exp(s)
        return p / p.sum(1, keepdims=True)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.classes[self.predict_proba(X).argmax(1)]


class SoftmaxRegression:
    def fit(self, X: np.ndarray, y: np.ndarray, lr: float = 0.5, epochs: int = 300, l2: float = 1e-3):
        self.classes = np.unique(y)
        Y = (y[:, None] == self.classes[None]).astype(np.float32)
        self.W = np.zeros((X.shape[1], len(self.classes)), dtype=np.float32)
        self.b = np.zeros(len(self.classes), dtype=np.float32)
        for _ in range(epochs):
            P = self.predict_proba(X)
            G = (P - Y) / len(X)
            self.W -= lr * (X.T @ G + l2 * self.W)
            self.b -= lr * G.sum(0)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        s = X @ self.W + self.b
        s -= s.max(1, keepdims=True)
        p = np.exp(s)
        return p / p.sum(1, keepdims=True)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.classes[self.predict_proba(X).argmax(1)]


def stratified_folds(y: np.ndarray, k: int = 5, seed: int = 0) -> List[np.ndarray]:
    rng = np.random.default_rng(seed)
    folds: List[List[int]] = [[] for _ in range(k)]
    for c in np.unique(y):
        idx = np.where(y == c)[0]
        rng.shuffle(idx)
        for i, j in enumerate(idx):
            folds[i % k].append(int(j))
    return [np.array(f) for f in folds if f]


def macro_f1(y: np.ndarray, p: np.ndarray) -> float:
    f = []
    for c in np.unique(y):
        tp = ((p == c) & (y == c)).sum()
        prec = tp / max((p == c).sum(), 1)
        rec = tp / max((y == c).sum(), 1)
        f.append(0 if tp == 0 else 2 * prec * rec / (prec + rec))
    return float(np.mean(f))


def cross_validate(make_model, X: np.ndarray, y: np.ndarray, k: int = 5, return_preds: bool = False) -> Dict[str, Any]:
    k = max(2, min(k, int(min(Counter(y.tolist()).values()))))
    preds = np.empty_like(y)
    for test in stratified_folds(y, k):
        train = np.setdiff1d(np.arange(len(y)), test)
        preds[test] = make_model().fit(X[train], y[train]).predict(X[test])
    out = {"accuracy": round(float((preds == y).mean()), 3), "macro_f1": round(macro_f1(y, preds), 3), "folds": k}
    if return_preds:
        out["_preds"] = preds
    return out


try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.svm import LinearSVC
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


def model_zoo(n_samples: int) -> Dict[str, Any]:
    """Supervised models compared on every labelled task (scikit-learn ones when installed)."""
    zoo: Dict[str, Any] = {"naive_bayes": MultinomialNB, "logistic_regression": SoftmaxRegression}
    if HAS_SKLEARN:
        zoo["random_forest"] = lambda: RandomForestClassifier(n_estimators=200, random_state=0, n_jobs=-1)
        zoo["linear_svm"] = lambda: LinearSVC(C=1.0, random_state=0)
        if n_samples <= 5000:
            zoo["gradient_boosting"] = lambda: GradientBoostingClassifier(random_state=0)
    return zoo


def compare_models(X: np.ndarray, y: np.ndarray, nonneg: bool = True) -> Dict[str, Any]:
    """Stratified k-fold for every model in the zoo; the best by macro-F1 is selected."""
    results: Dict[str, Any] = {}
    preds: Dict[str, np.ndarray] = {}
    for name, make in model_zoo(len(y)).items():
        if name == "naive_bayes" and not nonneg:
            continue
        try:
            r = cross_validate(make, X, y, return_preds=True)
            preds[name] = r.pop("_preds")
            results[name] = r
        except Exception as exc:
            results[name] = {"error": str(exc)}
    ok = {k: v for k, v in results.items() if "macro_f1" in v}
    best = max(ok, key=lambda k: (ok[k]["macro_f1"], ok[k]["accuracy"])) if ok else None
    return {"models": results, "best_model": best, "_best_preds": preds.get(best)}


def confusion(y: np.ndarray, p: np.ndarray) -> Tuple[List[str], np.ndarray]:
    labels = sorted(set(y.tolist()) | set(p.tolist()))
    idx = {l: i for i, l in enumerate(labels)}
    m = np.zeros((len(labels), len(labels)), dtype=int)
    for a, b in zip(y, p):
        m[idx[a], idx[b]] += 1
    return labels, m


def render_charts(out_prefix: Path, comparisons: Dict[str, Dict[str, Any]], X_topics: Optional[np.ndarray],
                  topic_labels: Optional[np.ndarray], conf: Optional[Tuple[str, List[str], np.ndarray]]) -> List[str]:
    """Model comparison bars, a 2-D topic map (SVD projection) and the best model's confusion matrix."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    files = []
    if comparisons:
        fig, ax = plt.subplots(figsize=(8, 4))
        tasks = list(comparisons)
        names = sorted({m for c in comparisons.values() for m in c["models"] if "macro_f1" in c["models"][m]})
        w = 0.8 / max(len(names), 1)
        for j, n in enumerate(names):
            vals = [comparisons[t]["models"].get(n, {}).get("macro_f1", 0) for t in tasks]
            ax.bar(np.arange(len(tasks)) + j * w, vals, w, label=n)
        ax.set_xticks(np.arange(len(tasks)) + w * (len(names) - 1) / 2, tasks)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("macro-F1 (k-fold)")
        ax.set_title("Model comparison per task")
        ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1))
        fig.tight_layout()
        f = f"{out_prefix}_models.png"
        fig.savefig(f, dpi=110)
        plt.close(fig)
        files.append(f)
    if X_topics is not None and topic_labels is not None and len(X_topics) >= 3:
        Xc = X_topics - X_topics.mean(0)
        U, S, _ = np.linalg.svd(Xc, full_matrices=False)
        xy = U[:, :2] * S[:2]
        fig, ax = plt.subplots(figsize=(6, 5))
        sc = ax.scatter(xy[:, 0], xy[:, 1], c=topic_labels, cmap="tab10", s=18)
        ax.set_title("Discovered topics (2-D projection)")
        fig.colorbar(sc, ax=ax, label="cluster")
        fig.tight_layout()
        f = f"{out_prefix}_topics.png"
        fig.savefig(f, dpi=110)
        plt.close(fig)
        files.append(f)
    if conf is not None:
        title, labels, m = conf
        fig, ax = plt.subplots(figsize=(1.2 + 0.6 * len(labels), 1 + 0.6 * len(labels)))
        ax.imshow(m, cmap="Blues")
        ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
        ax.set_yticks(range(len(labels)), labels)
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(j, i, int(m[i, j]), ha="center", va="center", fontsize=8)
        ax.set_xlabel("predicted")
        ax.set_ylabel("true")
        ax.set_title(title)
        fig.tight_layout()
        f = f"{out_prefix}_confusion.png"
        fig.savefig(f, dpi=110)
        plt.close(fig)
        files.append(f)
    return files


# ─────────────────────────────────────────────────────────────── 5. deep learning
class MLPClassifier:
    """Two-layer MLP with dropout. PyTorch when available, otherwise NumPy backprop."""

    def __init__(self, hidden: int = 128, epochs: int = 200, lr: float = 3e-3, seed: int = 0):
        self.hidden, self.epochs, self.lr, self.seed = hidden, epochs, lr, seed

    def fit(self, X: np.ndarray, y: np.ndarray) -> "MLPClassifier":
        self.classes = np.unique(y)
        yi = np.searchsorted(self.classes, y)
        if HAS_TORCH:
            torch.manual_seed(self.seed)
            self.net = nn.Sequential(nn.Linear(X.shape[1], self.hidden), nn.ReLU(), nn.Dropout(0.2),
                                     nn.Linear(self.hidden, self.hidden // 2), nn.ReLU(),
                                     nn.Linear(self.hidden // 2, len(self.classes)))
            opt = torch.optim.AdamW(self.net.parameters(), lr=self.lr, weight_decay=1e-3)
            Xt, yt = torch.tensor(X, dtype=torch.float32), torch.tensor(yi)
            for _ in range(self.epochs):
                self.net.train()
                opt.zero_grad()
                F.cross_entropy(self.net(Xt), yt).backward()
                opt.step()
            self.net.eval()
            return self
        rng = np.random.default_rng(self.seed)
        self.W1 = rng.normal(0, np.sqrt(2 / X.shape[1]), (X.shape[1], self.hidden)).astype(np.float32)
        self.b1 = np.zeros(self.hidden, dtype=np.float32)
        self.W2 = rng.normal(0, np.sqrt(2 / self.hidden), (self.hidden, len(self.classes))).astype(np.float32)
        self.b2 = np.zeros(len(self.classes), dtype=np.float32)
        Y = np.eye(len(self.classes), dtype=np.float32)[yi]
        for _ in range(self.epochs * 2):
            H = np.maximum(X @ self.W1 + self.b1, 0)
            mask = (rng.random(H.shape) > 0.2) / 0.8
            Hd = H * mask
            P = self._softmax(Hd @ self.W2 + self.b2)
            G2 = (P - Y) / len(X)
            G1 = (G2 @ self.W2.T) * mask * (H > 0)
            self.W2 -= self.lr * 30 * (Hd.T @ G2)
            self.b2 -= self.lr * 30 * G2.sum(0)
            self.W1 -= self.lr * 30 * (X.T @ G1)
            self.b1 -= self.lr * 30 * G1.sum(0)
        return self

    @staticmethod
    def _softmax(s: np.ndarray) -> np.ndarray:
        s = s - s.max(1, keepdims=True)
        e = np.exp(s)
        return e / e.sum(1, keepdims=True)

    def predict(self, X: np.ndarray) -> np.ndarray:
        if HAS_TORCH:
            with torch.no_grad():
                return self.classes[self.net(torch.tensor(X, dtype=torch.float32)).argmax(1).numpy()]
        H = np.maximum(X @ self.W1 + self.b1, 0)
        return self.classes[(H @ self.W2 + self.b2).argmax(1)]


if HAS_TORCH:
    class _TinyTransformerClassifier(nn.Module):
        def __init__(self, vocab: int, n_cls: int, dim: int = 96, layers: int = 2, max_len: int = 128):
            super().__init__()
            self.emb = nn.Embedding(vocab, dim, padding_idx=0)
            self.pos = nn.Parameter(torch.zeros(1, max_len, dim))
            layer = nn.TransformerEncoderLayer(dim, 4, dim * 2, dropout=0.1, batch_first=True, norm_first=True)
            self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
            self.head = nn.Linear(dim, n_cls)

        def forward(self, ids):
            mask = ids == 0
            h = self.enc(self.emb(ids) + self.pos[:, : ids.shape[1]], src_key_padding_mask=mask)
            h = h.masked_fill(mask.unsqueeze(-1), 0).sum(1) / (~mask).sum(1, keepdim=True).clamp(min=1)
            return self.head(h)


def transformer_text_classifier(texts: List[str], y: np.ndarray, tokenizer, epochs: int = 30,
                                max_len: int = 128, seed: int = 0) -> Dict[str, Any]:
    """Transformer encoder trained from scratch on the brain's own tokenizer; 80/20 stratified split."""
    if not HAS_TORCH:
        return {"skipped": "PyTorch not installed"}
    torch.manual_seed(seed)
    classes = np.unique(y)
    yi = np.searchsorted(classes, y)
    ids = [tokenizer.encode(t, add_bos=False)[:max_len] for t in texts]
    remap: Dict[int, int] = {}
    for seq in ids:
        for t in seq:
            remap.setdefault(t, len(remap) + 1)
    X = torch.zeros(len(ids), max(len(s) for s in ids) or 1, dtype=torch.long)
    for i, s in enumerate(ids):
        X[i, : len(s)] = torch.tensor([remap[t] for t in s])
    folds = stratified_folds(yi, 5, seed)
    test = folds[0]
    train = np.setdiff1d(np.arange(len(yi)), test)
    model = _TinyTransformerClassifier(len(remap) + 1, len(classes), max_len=X.shape[1])
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-2)
    yt = torch.tensor(yi)
    for _ in range(epochs):
        model.train()
        perm = torch.tensor(np.random.default_rng(_).permutation(train))
        for b in range(0, len(perm), 16):
            bi = perm[b: b + 16]
            opt.zero_grad()
            F.cross_entropy(model(X[bi]), yt[bi]).backward()
            opt.step()
    model.eval()
    with torch.no_grad():
        pred = model(X[torch.tensor(test)]).argmax(1).numpy()
    return {"accuracy": round(float((pred == yi[test]).mean()), 3), "test_size": int(len(test)),
            "params": int(sum(p.numel() for p in model.parameters()))}


def holdout_accuracy(make_model, X: np.ndarray, y: np.ndarray, seed: int = 0) -> Dict[str, float]:
    test = stratified_folds(y, 5, seed)[0]
    train = np.setdiff1d(np.arange(len(y)), test)
    p = make_model().fit(X[train], y[train]).predict(X[test])
    return {"accuracy": round(float((p == y[test]).mean()), 3), "test_size": int(len(test))}


# ─────────────────────────────────────────────────────────────── 6. algorithms
def concept_graph(texts: List[str], l1, l3, top_terms: int = 6) -> Dict[str, Any]:
    """Keyphrases per item (L3) using salience = tf · IDF over this batch · log2(len+1), so words that
    appear everywhere ("the", "please") fall out on their own → co-occurrence graph → PageRank +
    label-propagation communities."""
    edges: Counter = Counter()
    toks_all = [[w.lower() for w in _TOKEN.findall(t)] for t in texts]
    df: Counter = Counter()
    for toks in toks_all:
        df.update(set(toks))
    n = len(texts)
    for t, toks in zip(texts, toks_all):
        tf = Counter(toks)
        sal = {w: (c / max(len(toks), 1)) * math.log((n + 1) / (df[w] + 0.5)) * math.log2(len(w) + 1)
               for w, c in tf.items()}
        phrases = [p for p in l3.extract_dynamic_keyphrases(t, sal) if len(p) > 2][:top_terms]
        for i, a in enumerate(phrases):
            for b in phrases[i + 1:]:
                if a != b:
                    edges[tuple(sorted((a, b)))] += 1
    nodes = sorted({n for e in edges for n in e})
    if not nodes:
        return {"nodes": 0, "edges": 0, "top_concepts": [], "communities": 0}
    idx = {n: i for i, n in enumerate(nodes)}
    A = np.zeros((len(nodes), len(nodes)), dtype=np.float32)
    for (a, b), w in edges.items():
        A[idx[a], idx[b]] = A[idx[b], idx[a]] = w
    deg = A.sum(1)
    P = np.where(deg[:, None] > 0, A / np.maximum(deg[:, None], 1e-9), 1.0 / len(nodes))
    r = np.full(len(nodes), 1.0 / len(nodes))
    for _ in range(50):                                   # PageRank
        r = 0.15 / len(nodes) + 0.85 * (P.T @ r)
    lab = np.arange(len(nodes))
    rng = np.random.default_rng(0)
    for _ in range(20):                                   # label propagation communities
        for i in rng.permutation(len(nodes)):
            nb = np.where(A[i] > 0)[0]
            if len(nb):
                votes = defaultdict(float)
                for j in nb:
                    votes[lab[j]] += A[i, j]
                lab[i] = max(votes, key=votes.get)
    top = np.argsort(-r)[:10]
    return {"nodes": len(nodes), "edges": len(edges), "communities": int(len(set(lab.tolist()))),
            "top_concepts": [[nodes[i], round(float(r[i]), 4)] for i in top],
            "triples": [(a, "co_occurs_with", b) for (a, b), _ in edges.most_common(200)]}


def save_classifier(path: Path, tfidf: TfidfVectorizer, model: SoftmaxRegression, field: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"field": field, "tfidf": tfidf.state(), "classes": model.classes.tolist(),
                                "W": model.W.tolist(), "b": model.b.tolist()}), encoding="utf-8")


def load_classifier(path: Path) -> Tuple[TfidfVectorizer, SoftmaxRegression, str]:
    st = json.loads(path.read_text(encoding="utf-8"))
    m = SoftmaxRegression()
    m.classes = np.asarray(st["classes"])
    m.W, m.b = np.asarray(st["W"], dtype=np.float32), np.asarray(st["b"], dtype=np.float32)
    return TfidfVectorizer.from_state(st["tfidf"]), m, st["field"]
