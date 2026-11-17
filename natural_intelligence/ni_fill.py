"""Dataset filler: streams REAL labelled data from Hugging Face (datasets-server REST API,
no `datasets` install, no full-dataset download) into bounded, resumable local shards.

Shard k of a task = 10 pages x 100 rows taken from a fixed permutation of pages, so any
prefix of shards is a class-mixed sample of the whole dataset (never an ordered slice).
Audio/video/graph store extracted features (raw stays re-streamable by gid); images keep
raw 32x32 uint8; text keeps the raw string.
"""
import os, io, sys, json, time, zlib, urllib.request, urllib.parse, tempfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from ni_common import DATA, log
import ni_features as F

B = "https://datasets-server.huggingface.co/"
UA = {"User-Agent": "ni-fill/1.0"}
PAGE = 100
SHARD_PAGES = 10

SOURCES = {
    "text/ag_news":      dict(ds="fancyzhx/ag_news",       cfg="default",   split="train", kind="text"),
    "image/cifar10":     dict(ds="uoft-cs/cifar10",        cfg="plain_text", split="train", kind="image"),
    "audio/urbansound8k": dict(ds="danavery/urbansound8K", cfg="default",   split="train", kind="audio"),
    "video/hmdb51":      dict(ds="divm/hmdb51",            cfg=None,        split="train", kind="video"),
}
GRAPHS = {"graph/proteins": "graphs-datasets/PROTEINS", "graph/mutag": "graphs-datasets/MUTAG"}


def _get(url, binary=False, tries=7):
    err = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                b = r.read()
            return b if binary else json.loads(b)
        except urllib.error.HTTPError as e:
            err = e
            if e.code in (401, 403, 404):
                raise
            time.sleep(min(60, 2 ** k * 1.5))
        except Exception as e:
            err = e
            time.sleep(min(60, 2 ** k))
    raise RuntimeError(f"GET failed {url[:120]}: {err}")


def _config_split(ds, cfg, split):
    if cfg:
        return cfg, split
    d = _get(B + "splits?dataset=" + urllib.parse.quote(ds))["splits"]
    for s in d:
        if s["split"] == split:
            return s["config"], split
    return d[0]["config"], d[0]["split"]


def _rows(ds, cfg, split, offset, n=PAGE):
    u = B + "rows?dataset=%s&config=%s&split=%s&offset=%d&length=%d" % (
        urllib.parse.quote(ds), urllib.parse.quote(cfg), urllib.parse.quote(split), offset, n)
    r = _get(u)
    return r.get("rows", []), r.get("num_rows_total", 0)


_meta_cache = {}


def _meta(key):
    if key not in _meta_cache:
        s = SOURCES[key]
        cfg, split = _config_split(s["ds"], s["cfg"], s["split"])
        _, total = _rows(s["ds"], cfg, split, 0, 1)
        _meta_cache[key] = (cfg, split, total)
    return _meta_cache[key]


def n_shards_available(key):
    cfg, split, total = _meta(key)
    return (total // PAGE + (1 if total % PAGE else 0) + SHARD_PAGES - 1) // SHARD_PAGES


def _page_perm(key, n_pages):
    return np.random.RandomState(7 + len(key)).permutation(n_pages)


def shard_path(key, k):
    return os.path.join(DATA, key.replace("/", os.sep), f"shard_{k:04d}.npz")


def existing_shards(key):
    d = os.path.join(DATA, key.replace("/", os.sep))
    return sorted(f for f in os.listdir(d) if f.startswith("shard_") and f.endswith(".npz")) if os.path.isdir(d) else []


def _save(path, **kw):
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        np.savez_compressed(f, **kw)
    os.replace(tmp, path)


def _movie(r):
    """Source film/clip name: video frames from one source are near-duplicates, so split by this group."""
    fn = str(r.get("original_filename", ""))
    lab = str(r.get("label", ""))
    return fn.split("_" + lab + "_")[0] if ("_" + lab + "_") in fn else fn.rsplit("_", 6)[0]


def _video_src(v):
    if isinstance(v, dict):
        return v.get("src") or v.get("path")
    if isinstance(v, list) and v:
        return v[0].get("src")
    return v


def _fill_shard(key, k):
    s = SOURCES[key]
    cfg, split, total = _meta(key)
    n_pages = total // PAGE + (1 if total % PAGE else 0)
    perm = _page_perm(key, n_pages)
    pages = perm[k * SHARD_PAGES:(k + 1) * SHARD_PAGES]
    if len(pages) == 0:
        return False
    rows, gids = [], []
    for pg in pages:
        rs, _ = _rows(s["ds"], cfg, split, int(pg) * PAGE)
        for i, r in enumerate(rs):
            rows.append(r["row"]); gids.append(int(pg) * PAGE + i)
        time.sleep(0.15)
    kind = s["kind"]
    out_path = shard_path(key, k)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    gids = np.asarray(gids, np.int64)
    if kind == "text":
        _save(out_path, docs=np.array([r["text"] for r in rows]),
                            y=np.array([r["label"] for r in rows], np.int64), gid=gids)
    elif kind == "image":
        from PIL import Image
        def dl(r):
            im = Image.open(io.BytesIO(_get(r["img"]["src"], binary=True))).convert("RGB").resize((32, 32))
            return np.asarray(im, np.uint8)
        with ThreadPoolExecutor(8) as ex:
            ims = list(ex.map(dl, rows))
        _save(out_path, x=np.stack(ims), y=np.array([r["label"] for r in rows], np.int64), gid=gids)
    elif kind == "audio":
        import soundfile as sf
        def dl(r):
            try:
                b = _get(r["audio"][0]["src"], binary=True)
                w, sr = sf.read(io.BytesIO(b), dtype="float32")
                return F.audio_feats(w, sr)
            except Exception as e:
                return None
        with ThreadPoolExecutor(6) as ex:
            fs = list(ex.map(dl, rows))
        ok = [i for i, f in enumerate(fs) if f is not None]
        _save(out_path, f=np.stack([fs[i] for i in ok]),
                            y=np.array([rows[i]["classID"] for i in ok], np.int64),
                            cls=np.array([rows[i]["class"] for i in ok]), gid=gids[ok],
                            grp=np.array([int(rows[i]["fsID"]) for i in ok], np.int64))
    elif kind == "video":
        def dl(r):
            try:
                b = _get(_video_src(r["video"]), binary=True)
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as t:
                    t.write(b); p = t.name
                try:
                    return F.video_feats(p)
                finally:
                    os.unlink(p)
            except Exception as e:
                return None
        with ThreadPoolExecutor(4) as ex:
            fs = list(ex.map(dl, rows))
        ok = [i for i, f in enumerate(fs) if f is not None]
        if not ok:
            return False
        _save(out_path, f=np.stack([fs[i] for i in ok]),
                            cls=np.array([str(rows[i]["label"]) for i in ok]), gid=gids[ok],
                            grp=np.array([zlib.crc32(_movie(rows[i]).encode()) for i in ok], np.int64))
    return True


def fill_graphs():
    for key, ds in GRAPHS.items():
        p = os.path.join(DATA, key.replace("/", os.sep), "shard_0000.npz")
        if os.path.exists(p):
            continue
        cfg, split = _config_split(ds, None, "train")
        feats, ys, gids = [], [], []
        off = 0
        while True:
            rs, total = _rows(ds, cfg, split, off)
            if not rs:
                break
            for i, r in enumerate(rs):
                row = r["row"]
                feats.append(F.graph_feats(row["edge_index"], row["node_feat"], row["num_nodes"]))
                ys.append(int(row["y"][0])); gids.append(off + i)
            off += len(rs)
            if off >= total:
                break
            time.sleep(0.15)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        d = max(f.shape[0] for f in feats)
        _save(p, f=np.stack([np.pad(f, (0, d - len(f))) for f in feats]), y=np.array(ys, np.int64),
                            gid=np.array(gids, np.int64))
        log(f"[fill] {key}: {len(feats)} graphs")


def fill(caps, budget_s=1800, graphs=True):
    """caps: {task_key: max_shards}. Resumable; stops when time budget is spent."""
    t0 = time.time()
    try:
        if graphs:
            fill_graphs()
    except Exception as e:
        log("[fill] graph fill failed:", repr(e)[:200])
    for key in ("text/ag_news", "audio/urbansound8k", "video/hmdb51", "image/cifar10"):
        try:
            avail = n_shards_available(key)
        except Exception as e:
            log(f"[fill] {key}: metadata failed {repr(e)[:150]}"); continue
        want = min(caps.get(key, 0), avail)
        have = {int(f[6:10]) for f in existing_shards(key)}
        for k in range(want):
            if k in have:
                continue
            if time.time() - t0 > budget_s:
                log(f"[fill] budget spent at {key} shard {k}"); return
            t1 = time.time()
            try:
                ok = _fill_shard(key, k)
                log(f"[fill] {key} shard {k}/{want} {'ok' if ok else 'empty'} {time.time()-t1:.0f}s")
            except Exception as e:
                log(f"[fill] {key} shard {k} failed: {repr(e)[:200]}")
                break


if __name__ == "__main__":
    fill({"text/ag_news": 2, "image/cifar10": 1, "audio/urbansound8k": 1, "video/hmdb51": 1}, budget_s=900)
