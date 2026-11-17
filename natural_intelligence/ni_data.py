"""Task loaders: turn filled shards into (X, y, gid) arrays. Features are cached per shard."""
import os, numpy as np
from ni_common import DATA, log, task_hash
import ni_features as F
from ni_fill import existing_shards, shard_path

# curriculum: easiest -> toughest modality (phase = index+1 of the modality group)
PHASES = [
    (1, "text",  ["text/ag_news"]),
    (2, "graph", ["graph/proteins", "graph/mutag"]),
    (3, "image", ["image/cifar10"]),
    (4, "audio", ["audio/urbansound8k"]),
    (5, "video", ["video/hmdb51"]),
]
MODALITIES = [p[1] for p in PHASES]
VIDEO_TOP_CLASSES = 10


def _cached(path, fn):
    cp = path + ".feat.npy"
    if os.path.exists(cp) and os.path.getmtime(cp) >= os.path.getmtime(path):
        return np.load(cp)
    v = fn()
    np.save(cp, v)
    return v


ENC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_enc")
EXTERNAL_PREFIXES = ("enc/", "hand/", "enc2/", "cat/")   # enc2 = stronger frozen encoders (A/B set, opt-in)
#   # cached by ni_encode.py: enc = frozen pretrained embedding, hand = old hand-built features


def key_modality(key):
    """'text/ag_news' -> 'text';  'enc/audio/esc50' -> 'audio'."""
    parts = key.split("/")
    return parts[1] if key.startswith(EXTERNAL_PREFIXES) else parts[0]


def load_cat(key):
    """cat/<mod>/<name> = enc and enc2 features of the SAME items side by side (two different frozen views); needs both files with identical gid."""
    a, b = load_enc("enc/" + key.split("/", 1)[1]), load_enc("enc2/" + key.split("/", 1)[1])
    if a is None or b is None or len(a["y"]) != len(b["y"]) or not (a["gid"] == b["gid"]).all():
        return None
    return dict(a, X=np.concatenate([a["X"], b["X"]], 1))


def load_enc(key):
    if key.startswith("cat/"):
        return load_cat(key)
    p = os.path.join(ENC_DIR, key.replace("/", os.sep) + ".npz")
    if not os.path.exists(p):
        return None
    z = np.load(p)
    hk = "enc/" + key.split("/", 1)[1] if key.startswith("enc2/") else key        # enc and enc2 of one dataset share the same split
    X, y, G = z["X"].astype(np.float32), z["y"], z["gid"].astype(np.int64) + (task_hash(hk) % 1000) * 10_000_000
    ok = np.isfinite(X).all(1)
    X, y, G = X[ok], y[ok], G[ok]
    u, inv = np.unique(y, return_inverse=True)
    return dict(X=X, y=inv.astype(np.int64), gid=G, n_classes=len(u), names=None, n=len(y))


def load_task(key):
    """Returns dict(X,y,gid,n_classes,names) or None if nothing filled."""
    if key.startswith(EXTERNAL_PREFIXES):
        return load_enc(key)
    shards = existing_shards(key)
    if not shards:
        return None
    X, Y, G, N = [], [], [], []
    GR = []
    for s in shards:
        p = os.path.join(DATA, key.replace("/", os.sep), s)
        try:
            z = np.load(p, allow_pickle=False)
            if key.startswith("text"):
                f = _cached(p, lambda: F.text_feats(list(z["docs"])))
            elif key.startswith("image"):
                f = _cached(p, lambda: F.image_feats(z["x"]))
            else:
                f = z["f"]
            X.append(f); G.append(z["grp"] if "grp" in z.files else z["gid"])
            if key.startswith("video"):
                N.append(z["cls"])
            else:
                Y.append(z["y"])
        except Exception as e:
            log(f"[data] skipping bad shard {p}: {repr(e)[:100]}")
    if not X:
        return None
    X = np.concatenate(X).astype(np.float32); G = np.concatenate(G)
    names = None
    if key.startswith("video"):
        cls = np.concatenate(N)
        u, c = np.unique(cls, return_counts=True)
        keep = u[np.argsort(-c)[:VIDEO_TOP_CLASSES]]
        m = np.isin(cls, keep)
        names = sorted(keep.tolist())
        y = np.array([names.index(c) for c in cls[m]], np.int64)
        X, G = X[m], G[m]
    else:
        y = np.concatenate(Y)
    # globally unique ids so splits hash differently per task
    G = G + (task_hash(key) % 1000) * 10_000_000
    ok = np.isfinite(X).all(1)
    X, y, G = X[ok], y[ok], G[ok]
    # relabel to 0..C-1 (drop classes with < 2 samples)
    u, inv, c = np.unique(y, return_inverse=True, return_counts=True)
    return dict(X=X, y=inv.astype(np.int64), gid=G, n_classes=len(u), names=names, n=len(y))


if __name__ == "__main__":
    for _, m, keys in PHASES:
        for k in keys:
            d = load_task(k)
            print(k, None if d is None else (d["X"].shape, d["n_classes"], np.bincount(d["y"])[:12]))
