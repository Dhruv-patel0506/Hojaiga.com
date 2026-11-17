"""Frozen pretrained encoders -> cached embeddings (data_enc/), plus the OLD hand-built features on the SAME items.

kind "enc"  : embedding from a frozen Hugging Face model in models_hf/ (no fine-tuning).
kind "hand" : the original ni_features extractor (colour histograms, hashed n-grams, ...), for a paired comparison.
Output: data_enc/<kind>/<modality>/<name>.npz  with X (float32), y, gid (split group), n_classes, seconds.
Every task is resumable (skipped if the output exists unless --force) and logged to data_enc/encode_log.txt.
"""
import os, sys, io, csv, json, time, zlib, glob, argparse, tarfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
import torch.nn.functional as TF
from ni_common import ROOT, log, set_logfile
import ni_features as F

DU = os.path.join(ROOT, "data_user"); MD = os.path.join(ROOT, "models_hf")
OUT = os.path.join(ROOT, "data_enc"); SH = os.path.join(ROOT, "data")
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
HALF = torch.float16 if dev.type == "cuda" else torch.float32
MEAN = torch.tensor([0.485, 0.456, 0.406], device=dev).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225], device=dev).view(1, 3, 1, 1)
_M = {}


def _fix_videomae_bias(m, path):
    """The checkpoint stores q_bias/v_bias as separate tensors (key bias is zero by design); transformers 5 reports them
    UNEXPECTED and re-initialises query/value/key biases. Copy the real ones in so the encoder is the trained one."""
    from safetensors import safe_open
    n = 0
    with safe_open(os.path.join(path, "model.safetensors"), "pt") as f:
        keys = set(f.keys())
        for i, layer in enumerate(m.encoder.layer):
            att = layer.attention.attention
            for src, lin in (("q_bias", att.query), ("v_bias", att.value)):
                k = f"videomae.encoder.layer.{i}.attention.attention.{src}"
                if k in keys:
                    lin.bias.data.copy_(f.get_tensor(k).to(device=lin.bias.device, dtype=lin.bias.dtype)); n += 1
            att.key.bias.data.zero_()
    log(f"[enc] videomae: restored {n} q/v bias tensors from the checkpoint (expected {2 * len(m.encoder.layer)})")


def _model(name, cls="AutoModel"):
    if name not in _M:
        import transformers as T
        _M[name] = getattr(T, cls).from_pretrained(os.path.join(MD, name), dtype=HALF).to(dev).eval()
        if cls == "VideoMAEModel":
            _fix_videomae_bias(_M[name], os.path.join(MD, name))
        log(f"[enc] loaded {name} ({sum(p.numel() for p in _M[name].parameters()) / 1e6:.0f}M params) on {dev}")
    return _M[name]


# ----------------------------------------------------------------------------- encoders
def enc_text(docs, bs=256, maxlen=128):
    import transformers as T
    if "tok" not in _M:
        _M["tok"] = T.AutoTokenizer.from_pretrained(os.path.join(MD, "all-MiniLM-L6-v2"))
    tok, m = _M["tok"], _model("all-MiniLM-L6-v2")
    order = np.argsort([len(d) for d in docs]); out = np.zeros((len(docs), m.config.hidden_size), np.float32)
    for i in range(0, len(docs), bs):
        idx = order[i:i + bs]
        t = tok([docs[j] for j in idx], padding=True, truncation=True, max_length=maxlen, return_tensors="pt").to(dev)
        with torch.no_grad():
            h = m(**t).last_hidden_state
        mk = t["attention_mask"].unsqueeze(-1).to(h.dtype)
        e = TF.normalize(((h * mk).sum(1) / mk.sum(1)).float(), dim=1)
        out[idx] = e.cpu().numpy()
    return out


def enc2_text(docs, bs=128, maxlen=256):
    """enc2 = stronger frozen text encoder (BGE-base, CLS pooling, 768-d, 256 tokens). A/B partner of enc_text (MiniLM-L6, 384-d)."""
    import transformers as T
    nm = "bge-base-en-v1.5"
    if "tok2" not in _M:
        _M["tok2"] = T.AutoTokenizer.from_pretrained(os.path.join(MD, nm))
    tok, m = _M["tok2"], _model(nm)
    order = np.argsort([len(d) for d in docs]); out = np.zeros((len(docs), m.config.hidden_size), np.float32)
    for i in range(0, len(docs), bs):
        idx = order[i:i + bs]
        t = tok([docs[j] for j in idx], padding=True, truncation=True, max_length=maxlen, return_tensors="pt").to(dev)
        with torch.no_grad():
            h = m(**t).last_hidden_state[:, 0]
        out[idx] = TF.normalize(h.float(), dim=1).cpu().numpy()
    return out


def enc2_audio(items, bs=8):
    """enc2 for audio = AST (AudioSet-tuned, 768) + Whisper-base encoder (speech/prosody: mean of layer 4 and of the last layer, 2x512)
    + CLAP-HTSAT audio embedding (music/sound-language aligned, 512) = 2304-d. Three different frozen views of the same clip."""
    import transformers as T
    from scipy.signal import resample_poly
    from math import gcd
    ast = enc_audio(items, bs=16)
    if "wfe" not in _M:
        _M["wfe"] = T.WhisperFeatureExtractor.from_pretrained(os.path.join(MD, "whisper-base"))
        _M["cfe"] = T.ClapFeatureExtractor.from_pretrained(os.path.join(MD, "clap-htsat-unfused"))
    wm = _model("whisper-base", "WhisperModel").encoder
    cm = _model("clap-htsat-unfused", "ClapModel")
    out = []
    for i in range(0, len(items), bs):
        chunk = items[i:i + bs]
        w16 = [_resample16(w, sr) for w, sr in chunk]
        feats = _M["wfe"](w16, sampling_rate=16000, return_tensors="pt")["input_features"].to(dev, HALF)
        with torch.no_grad():
            hs = wm(feats, output_hidden_states=True).hidden_states
            vf = [min(1500, max(1, int(np.ceil(len(w) / 16000 * 50)))) for w in w16]
            mid = torch.stack([hs[4][b, :vf[b]].float().mean(0) for b in range(len(vf))])
            last = torch.stack([hs[-1][b, :vf[b]].float().mean(0) for b in range(len(vf))])
            w48 = []
            for w, sr in chunk:
                w = np.asarray(w, np.float32); w = w.mean(1) if w.ndim > 1 else w
                g = gcd(int(sr), 48000)
                w48.append(resample_poly(w, 48000 // g, int(sr) // g).astype(np.float32)[: 48000 * 10])
            ci = _M["cfe"](w48, sampling_rate=48000, return_tensors="pt")
            ci = {k: (v.to(dev, HALF) if v.is_floating_point() else v.to(dev)) for k, v in ci.items()}
            ce = cm.get_audio_features(**ci)
            ce = (ce if torch.is_tensor(ce) else ce.pooler_output).float()
        out.append(torch.cat([mid, last, ce], 1).cpu().numpy())
    return np.concatenate([ast, np.concatenate(out)], 1), np.ones(len(items), bool)


def _dino(x01, name="dinov2-small"):
    """x01: float [B,3,224,224] in 0..1 on device -> [B,2H] (CLS + mean patch)."""
    m = _model(name)
    with torch.no_grad():
        h = m(pixel_values=((x01 - MEAN) / STD).to(HALF)).last_hidden_state
    return torch.cat([h[:, 0], h[:, 1:].mean(1)], 1).float()


def enc_images(arr, bs=128):
    out = []
    for i in range(0, len(arr), bs):
        x = torch.from_numpy(arr[i:i + bs]).to(dev).permute(0, 3, 1, 2).float() / 255.0
        if x.shape[-1] != 224 or x.shape[-2] != 224:
            x = TF.interpolate(x, size=(224, 224), mode="bilinear", align_corners=False)
        out.append(_dino(x).cpu().numpy())
    return np.concatenate(out)


def enc2_images(arr, bs=64):
    """enc2 = DINOv2-base (86M) CLS + mean patch = 1536-d. A/B partner of enc_images (DINOv2-small, 768-d)."""
    out = []
    for i in range(0, len(arr), bs):
        x = torch.from_numpy(arr[i:i + bs]).to(dev).permute(0, 3, 1, 2).float() / 255.0
        if x.shape[-1] != 224 or x.shape[-2] != 224:
            x = TF.interpolate(x, size=(224, 224), mode="bilinear", align_corners=False)
        out.append(_dino(x, "dinov2-base").cpu().numpy())
    return np.concatenate(out)


def _resample16(w, sr):
    from scipy.signal import resample_poly
    w = np.asarray(w, np.float32)
    if w.ndim > 1:
        w = w.mean(1)
    if sr != 16000:
        from math import gcd
        g = gcd(int(sr), 16000)
        w = resample_poly(w, 16000 // g, int(sr) // g).astype(np.float32)
    return w[: 16000 * 10]


def enc_audio(items, bs=16):
    import transformers as T
    if "fe" not in _M:
        _M["fe"] = T.AutoFeatureExtractor.from_pretrained(os.path.join(MD, "ast-finetuned-audioset-10-10-0.4593"))
    fe, m = _M["fe"], _model("ast-finetuned-audioset-10-10-0.4593", "ASTModel")
    out = []
    for i in range(0, len(items), bs):
        ws = [_resample16(w, sr) for w, sr in items[i:i + bs]]
        iv = fe(ws, sampling_rate=16000, return_tensors="pt")["input_values"].to(dev, HALF)
        with torch.no_grad():
            out.append(m(input_values=iv).pooler_output.float().cpu().numpy())
    return np.concatenate(out)


def read_clip(path, n=16, size=224):
    import cv2
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total < 2:
        cap.release(); return None
    want = {int(v) for v in np.linspace(0, total - 1, n)}
    got = {}
    for i in range(total):
        if not cap.grab():
            break
        if i in want:
            ok, f = cap.retrieve()
            if ok:
                got[i] = cv2.resize(f, (size, size), interpolation=cv2.INTER_AREA)[:, :, ::-1]
    cap.release()
    if len(got) < 2:
        return None
    keys = sorted(got); fr = []
    for v in np.linspace(0, total - 1, n).astype(int):
        k = min(keys, key=lambda a: abs(a - v)); fr.append(got[k])
    return np.stack(fr)


def enc_video(paths, bs=4):
    """Per clip: VideoMAE mean token (768) + DINOv2 mean over 8 frames (768) = 1536. Returns (X, ok)."""
    vm = _model("videomae-base", "VideoMAEModel")
    with ThreadPoolExecutor(6) as ex:
        clips = list(ex.map(read_clip, paths))
    ok = np.array([c is not None for c in clips]); X = np.zeros((len(paths), 1536), np.float32)
    good = [i for i in range(len(paths)) if ok[i]]
    for s in range(0, len(good), bs):
        ids = good[s:s + bs]
        c = torch.from_numpy(np.stack([clips[i] for i in ids])).to(dev)          # [B,16,H,W,3] uint8
        x = c.permute(0, 1, 4, 2, 3).float() / 255.0                            # [B,16,3,H,W]
        B = x.shape[0]
        with torch.no_grad():
            xm = ((x.reshape(B * 16, 3, 224, 224) - MEAN) / STD).reshape(B, 16, 3, 224, 224).to(HALF)
            a = vm(pixel_values=xm).last_hidden_state.mean(1).float()
            d = _dino(x[:, ::2].reshape(B * 8, 3, 224, 224)).reshape(B, 8, -1).mean(1)
        X[ids] = torch.cat([a, d], 1).cpu().numpy()
    return X, ok


def enc2_video(paths, bs=4):
    """enc2 per clip: VideoMAE mean token (768) + DINOv2-BASE CLS/mean over 8 frames (1536) + X-CLIP video embedding (512) = 2816-d.
    Three different frozen views of the same clip (motion-pretrained, image-semantic, language-aligned)."""
    import transformers as T
    vm = _model("videomae-base", "VideoMAEModel")
    xc = _model("xclip-base-patch32", "XCLIPModel")
    cm = torch.tensor([0.48145466, 0.4578275, 0.40821073], device=dev).view(1, 3, 1, 1)
    cs = torch.tensor([0.26862954, 0.26130258, 0.27577711], device=dev).view(1, 3, 1, 1)
    with ThreadPoolExecutor(6) as ex:
        clips = list(ex.map(read_clip, paths))
    ok = np.array([c is not None for c in clips]); X = np.zeros((len(paths), 2816), np.float32)
    good = [i for i in range(len(paths)) if ok[i]]
    for s in range(0, len(good), bs):
        ids = good[s:s + bs]
        c = torch.from_numpy(np.stack([clips[i] for i in ids])).to(dev)
        x = c.permute(0, 1, 4, 2, 3).float() / 255.0
        B = x.shape[0]
        with torch.no_grad():
            xm = ((x.reshape(B * 16, 3, 224, 224) - MEAN) / STD).reshape(B, 16, 3, 224, 224).to(HALF)
            a = vm(pixel_values=xm).last_hidden_state.mean(1).float()
            d = _dino(x[:, ::2].reshape(B * 8, 3, 224, 224), "dinov2-base").reshape(B, 8, -1).mean(1)
            xx = ((x[:, ::2].reshape(B * 8, 3, 224, 224) - cm) / cs).reshape(B, 8, 3, 224, 224).to(HALF)
            xv = xc.get_video_features(pixel_values=xx)
            xv = (xv if torch.is_tensor(xv) else xv.pooler_output).float()      # newer transformers return an output object (pooler_output = 512-d projection)
        X[ids] = torch.cat([a, d, xv], 1).cpu().numpy()
    return X, ok


# ----------------------------------------------------------------------------- hand features (same items)
def hand_text(docs):
    return F.text_feats(docs), np.ones(len(docs), bool)


def hand_images(arr):
    return F.image_feats(arr), np.ones(len(arr), bool)


def hand_audio(items):
    fs, ok = [], []
    for w, sr in items:
        try:
            fs.append(F.audio_feats(w, sr)); ok.append(True)
        except Exception:
            fs.append(np.zeros(134, np.float32)); ok.append(False)
    return np.stack(fs), np.array(ok)


def hand_video(paths):
    with ThreadPoolExecutor(4) as ex:
        fs = list(ex.map(lambda p: F.video_feats(p), paths))
    ok = np.array([f is not None for f in fs]); d = next(len(f) for f in fs if f is not None)
    return np.stack([f if f is not None else np.zeros(d, np.float32) for f in fs]), ok


def hand_graphs(rows):
    def n_eff(r):   # some AIDS graphs list num_nodes one lower than their node-feature rows / edge indices: trust the larger
        nf = r.get("node_feat"); ei = r["edge_index"]
        m = max(int(r["num_nodes"]), len(nf) if nf is not None else 0, (max(max(ei[0], default=-1), max(ei[1], default=-1)) + 1) if len(ei) == 2 else 0)
        return m
    fs = [F.graph_feats(r["edge_index"], r.get("node_feat"), n_eff(r)) for r in rows]
    d = max(len(f) for f in fs)
    return np.stack([np.pad(f, (0, d - len(f))) for f in fs]), np.ones(len(rows), bool)


def enc_graphs(rows):
    """'enc' for graphs = Weisfeiler-Lehman subtree fingerprint + structure (there is no pretrained graph encoder to freeze)."""
    def n_eff(r):
        nf = r.get("node_feat"); ei = r["edge_index"]
        return max(int(r["num_nodes"]), len(nf) if nf is not None else 0, (max(max(ei[0], default=-1), max(ei[1], default=-1)) + 1) if len(ei) == 2 else 0)
    fs = [F.graph_wl_feats(r["edge_index"], r.get("node_feat"), n_eff(r)) for r in rows]
    d = max(len(f) for f in fs)
    return np.stack([np.pad(f, (0, d - len(f))) for f in fs]), np.ones(len(rows), bool)


def enc2_graphs(rows):
    """enc2 for graphs = ni_features.graph_rich_feats (WL x2, full spectrum, heat traces, random-walk returns, path lengths, distributions)."""
    def n_eff(r):
        nf = r.get("node_feat"); ei = r["edge_index"]
        return max(int(r["num_nodes"]), len(nf) if nf is not None else 0, (max(max(ei[0], default=-1), max(ei[1], default=-1)) + 1) if len(ei) == 2 else 0)
    fs = [F.graph_rich_feats(r["edge_index"], r.get("node_feat"), n_eff(r)) for r in rows]
    d = max(len(f) for f in fs)
    return np.stack([np.pad(f, (0, d - len(f))) for f in fs]), np.ones(len(rows), bool)


FEATS = {
    "text": dict(enc=lambda p: (enc_text(p), np.ones(len(p), bool)), hand=hand_text, enc2=lambda p: (enc2_text(p), np.ones(len(p), bool))),
    "image": dict(enc=lambda p: (enc_images(p), np.ones(len(p), bool)), hand=hand_images, enc2=lambda p: (enc2_images(p), np.ones(len(p), bool))),
    "audio": dict(enc=lambda p: (enc_audio(p), np.ones(len(p), bool)), hand=hand_audio, enc2=enc2_audio),
    "video": dict(enc=enc_video, hand=hand_video, enc2=enc2_video),
    "graph": dict(hand=hand_graphs, enc=enc_graphs, enc2=enc2_graphs),
}


# ----------------------------------------------------------------------------- sources (yield payload, y, gid in chunks)
def _pq(path, cols):
    import pyarrow.parquet as pq
    return pq.read_table(path, columns=cols).to_pydict()


def _glob(*parts):
    return sorted(p for p in glob.glob(os.path.join(DU, *parts), recursive=True) if ".cache" not in p)


def src_ag_news(chunk=20000):
    docs, ys = [], []
    for s in sorted(f for f in os.listdir(os.path.join(SH, "text", "ag_news")) if f.endswith(".npz") and f.startswith("shard_")):
        z = np.load(os.path.join(SH, "text", "ag_news", s)); docs += list(z["docs"]); ys += list(z["y"])
    ys = np.array(ys, np.int64); g = np.arange(len(docs), dtype=np.int64)
    for i in range(0, len(docs), chunk):
        yield [str(d) for d in docs[i:i + chunk]], ys[i:i + chunk], g[i:i + chunk]


def src_cifar10(chunk=10000):
    xs, ys = [], []
    for s in sorted(f for f in os.listdir(os.path.join(SH, "image", "cifar10")) if f.endswith(".npz") and f.startswith("shard_")):
        z = np.load(os.path.join(SH, "image", "cifar10", s)); xs.append(z["x"]); ys.append(z["y"])
    x, y = np.concatenate(xs), np.concatenate(ys); g = np.arange(len(y), dtype=np.int64)
    for i in range(0, len(y), chunk):
        yield x[i:i + chunk], y[i:i + chunk], g[i:i + chunk]


def src_text_parquet(files, tcols, lab, limit_total=None, chunk=20000, seed=0):
    docs, ys = [], []
    for f in files:
        d = _pq(f, tcols + [lab])
        docs += [". ".join(str(d[c][i]) for c in tcols) for i in range(len(d[lab]))]; ys += d[lab]
    ys = np.array(ys, np.int64)
    idx = np.arange(len(docs))
    if limit_total and len(docs) > limit_total:
        idx = np.sort(np.random.RandomState(seed).choice(len(docs), limit_total, replace=False))
    for i in range(0, len(idx), chunk):
        j = idx[i:i + chunk]
        yield [docs[k] for k in j], ys[j], j.astype(np.int64)


def src_20ng(chunk=20000):
    docs, ys = [], []
    for f in _glob("text", "20_newsgroups", "*.jsonl"):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line); docs.append(r["text"]); ys.append(int(r["label"]))
    ys = np.array(ys, np.int64); g = np.arange(len(docs), dtype=np.int64)
    for i in range(0, len(docs), chunk):
        yield docs[i:i + chunk], ys[i:i + chunk], g[i:i + chunk]


def src_images_parquet(files, icol, lcol, chunk=5000):
    from PIL import Image
    off = 0
    for f in files:
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(f)
        for rb in pf.iter_batches(batch_size=chunk, columns=[icol, lcol]):
            d = rb.to_pydict()
            with ThreadPoolExecutor(8) as ex:
                ims = list(ex.map(lambda r: np.asarray(Image.open(io.BytesIO(r["bytes"])).convert("RGB"), np.uint8), d[icol]))
            x = np.stack(ims); y = np.array(d[lcol], np.int64)
            yield x, y, np.arange(off, off + len(y), dtype=np.int64); off += len(y)


def src_esc50(chunk=200):
    import soundfile as sf
    classes = {}
    for f in _glob("audio", "esc50", "data", "*.parquet"):
        import pyarrow.parquet as pq
        for rb in pq.ParquetFile(f).iter_batches(batch_size=chunk, columns=["audio", "target", "src_file"]):
            d = rb.to_pydict(); items = []
            for a in d["audio"]:
                w, sr = sf.read(io.BytesIO(a["bytes"]), dtype="float32"); items.append((w, sr))
            yield items, np.array(d["target"], np.int64), np.array(d["src_file"], np.int64)


def src_gtzan(chunk=100):
    import soundfile as sf
    tarp = _glob("audio", "gtzan", "data", "*.tar.gz")[0]
    items, ys, names = [], [], []
    genres = {}
    with tarfile.open(tarp, "r:gz") as tf:
        for m in tf:
            if not (m.isfile() and m.name.endswith(".wav")):
                continue
            gname = m.name.replace("\\", "/").split("/")[-2]
            try:
                w, sr = sf.read(io.BytesIO(tf.extractfile(m).read()), dtype="float32")
            except Exception as e:
                log(f"[gtzan] skip {m.name}: {repr(e)[:60]}"); continue
            genres.setdefault(gname, len(genres)); items.append((w[: sr * 12], sr)); ys.append(genres[gname])
            names.append(zlib.crc32(m.name.encode()))
            if len(items) == chunk:
                yield items, np.array(ys, np.int64), np.array(names, np.int64); items, ys, names = [], [], []
    if items:
        yield items, np.array(ys, np.int64), np.array(names, np.int64)


def _movie(fn, lab):
    fn = str(fn)
    return fn.split("_" + lab + "_")[0] if ("_" + lab + "_") in fn else fn.rsplit("_", 6)[0]


def src_hmdb51(chunk=64):
    root = os.path.join(DU, "video", "hmdb51"); rows = []
    for sp in ("train", "test", "validation"):
        with open(os.path.join(root, sp, "metadata.csv"), encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows.append((os.path.join(root, sp, r["file_name"]), r["label"], zlib.crc32(_movie(r["original_filename"], r["label"]).encode())))
    labs = sorted({r[1] for r in rows}); li = {l: i for i, l in enumerate(labs)}
    log(f"[hmdb51] {len(rows)} clips, {len(labs)} classes, {len({r[2] for r in rows})} source films")
    for i in range(0, len(rows), chunk):
        b = rows[i:i + chunk]
        yield [r[0] for r in b], np.array([li[r[1]] for r in b], np.int64), np.array([r[2] for r in b], np.int64)


def src_video_dir(root, exts=(".mp4", ".avi", ".mkv", ".webm", ".mov"), chunk=64):
    """Generic video-folder source: label = parent folder name; group id = the person/source-group token when the file name has one
    (UCF101 'v_<Class>_gNN_cNN' -> gNN; YouTube-id names -> the id) so clips of one source never straddle train and test."""
    import re
    rows = []
    for r, _, fs in os.walk(root):
        for f in sorted(fs):
            if f.lower().endswith(exts) and ".cache" not in r:
                p = os.path.join(r, f); lab = os.path.basename(r)
                m = re.search(r"_(g\d+)_c\d+", f)
                key = (lab + "/" + m.group(1)) if m else re.sub(r"_\d{6}_\d{6}$", "", os.path.splitext(f)[0])
                rows.append((p, lab, zlib.crc32(key.encode())))
    labs = sorted({r[1] for r in rows}); li = {l: i for i, l in enumerate(labs)}
    log(f"[video:{os.path.basename(root)}] {len(rows)} clips, {len(labs)} classes, {len({r[2] for r in rows})} groups")
    for i in range(0, len(rows), chunk):
        b = rows[i:i + chunk]
        yield [r[0] for r in b], np.array([li[r[1]] for r in b], np.int64), np.array([r[2] for r in b], np.int64)


def src_graphs(files):
    def gen():
        rows, ys = [], []
        for f in files:
            if f.endswith(".jsonl"):
                with open(f, encoding="utf-8") as fh:
                    for line in fh:
                        r = json.loads(line); rows.append(r); ys.append(int(r["y"][0]))
            else:
                import pyarrow.parquet as pq
                have = pq.ParquetFile(f).schema_arrow.names
                d = _pq(f, [c for c in ("edge_index", "node_feat", "y", "num_nodes") if c in have])
                for i in range(len(d["y"])):
                    y0 = d["y"][i]; y0 = y0[0] if isinstance(y0, (list, tuple)) else y0
                    if y0 is None:
                        continue
                    r = {k: d[k][i] for k in d}
                    r.setdefault("num_nodes", (max(max(r["edge_index"][0], default=-1), max(r["edge_index"][1], default=-1)) + 1) if r.get("edge_index") else 1)
                    rows.append(r); ys.append(int(y0))
        ys = np.array(ys, np.int64); g = np.arange(len(rows), dtype=np.int64)
        for i in range(0, len(rows), 4000):
            yield rows[i:i + 4000], ys[i:i + 4000], g[i:i + 4000]
    return gen()


def src_generic(spec, chunk=None):
    """Any hub-registered text/image/audio/graph dataset: spec comes from ni_hub.autodetect (columns recorded, not assumed)."""
    mod = spec["modality"]; files = [os.path.join(DU, f) for f in spec["files"]]; lab = spec["label_col"]
    if mod == "graph":
        yield from src_graphs(files); return
    import pyarrow.parquet as pq
    from PIL import Image
    chunk = chunk or {"text": 20000, "image": 4000, "audio": 200}[mod]
    cols = (spec.get("text_cols") or []) if mod == "text" else [spec.get(mod + "_col")]
    cols = cols + [lab]
    def n_rows(f):
        if f.endswith(".parquet"):
            return pq.ParquetFile(f).metadata.num_rows
        with open(f, encoding="utf-8") as fh:
            return sum(1 for ln in fh if ln.strip())

    def batches(f):
        if f.endswith(".parquet"):
            for rb in pq.ParquetFile(f).iter_batches(batch_size=chunk, columns=cols):
                yield rb.to_pydict()
            return
        buf = {c: [] for c in cols}                      # jsonl: same dict-of-lists shape as a parquet batch
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                for c in cols:
                    buf[c].append(r.get(c))
                if len(buf[cols[0]]) >= chunk:
                    yield buf; buf = {c: [] for c in cols}
        if buf[cols[0]]:
            yield buf
    data_files = [f for f in files if f.endswith((".parquet", ".jsonl"))]
    total = sum(n_rows(f) for f in data_files) or 1
    keep_p = min(1.0, (spec.get("limit") or 10 ** 9) / total)
    rng = np.random.RandomState(0); lab_map = {}; off = 0

    def to_label(v):
        if v is None:
            return -1
        if isinstance(v, str):
            return lab_map.setdefault(v, len(lab_map))
        return int(v)
    for f in data_files:
        for d in batches(f):
            n = len(d[lab])
            ys = np.array([to_label(v) for v in d[lab]], np.int64)
            ok = (ys >= 0) & (rng.random_sample(n) < keep_p)
            idx = np.nonzero(ok)[0]
            if not len(idx):
                off += n; continue
            if mod == "text":
                payload = [". ".join(str(d[c][i]) for c in spec["text_cols"]) for i in idx]
            elif mod == "image":
                def dec(b):
                    try:
                        return np.asarray(Image.open(io.BytesIO(b["bytes"])).convert("RGB").resize((64, 64)), np.uint8)
                    except Exception:
                        return None
                with ThreadPoolExecutor(8) as ex:
                    ims = list(ex.map(dec, [d[cols[0]][i] for i in idx]))
                good = [j for j, a in enumerate(ims) if a is not None]
                idx = idx[good]; payload = np.stack([ims[j] for j in good]) if good else np.zeros((0, 64, 64, 3), np.uint8)
            else:
                import soundfile as sf
                payload, good = [], []
                for j, i in enumerate(idx):
                    try:
                        w, sr = sf.read(io.BytesIO(d[cols[0]][i]["bytes"]), dtype="float32"); payload.append((w[: sr * 12], sr)); good.append(j)
                    except Exception:
                        pass
                idx = idx[good]
            if len(idx):
                yield payload, ys[idx], (off + idx).astype(np.int64)
            off += n


def _registered():
    try:
        with open(os.path.join(DU, "hub_registry.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


TASKS = {  # name -> (modality, source factory, kinds)
    "text/ag_news": ("text", lambda: src_ag_news(), ("enc", "hand", "enc2")),
    "text/dbpedia_14": ("text", lambda: src_text_parquet(_glob("text", "dbpedia_14", "**", "train-*.parquet"), ["title", "content"], "label", limit_total=100000), ("enc", "hand", "enc2")),
    "text/banking77": ("text", lambda: src_text_parquet(_glob("text", "banking77", "**", "*.parquet"), ["text"], "label"), ("enc", "hand", "enc2")),
    "text/20_newsgroups": ("text", lambda: src_20ng(), ("enc", "hand", "enc2")),
    "image/cifar10": ("image", lambda: src_cifar10(), ("enc", "hand", "enc2")),
    "image/cifar100": ("image", lambda: src_images_parquet(_glob("image", "cifar100", "**", "*.parquet"), "img", "fine_label"), ("enc", "hand", "enc2")),
    "image/tiny_imagenet": ("image", lambda: src_images_parquet(_glob("image", "tiny-imagenet", "**", "train-*.parquet"), "image", "label"), ("enc", "hand", "enc2")),
    "audio/esc50": ("audio", lambda: src_esc50(), ("enc", "hand", "enc2")),
    "audio/gtzan": ("audio", lambda: src_gtzan(), ("enc", "hand", "enc2")),
    "video/hmdb51": ("video", lambda: src_hmdb51(), ("enc", "hand", "enc2")),
    "graph/ogbg_molhiv": ("graph", lambda: src_graphs(_glob("graph", "ogbg-molhiv", "*.jsonl")), ("hand", "enc", "enc2")),
    "graph/imdb_binary": ("graph", lambda: src_graphs(_glob("graph", "IMDB-BINARY", "*.jsonl")), ("hand", "enc", "enc2")),
    "graph/aids": ("graph", lambda: src_graphs(_glob("graph", "AIDS", "data", "*.parquet")), ("hand", "enc", "enc2")),
}


for _vn, _vdir in (("kinetics_mini", "kinetics_mini"), ("ucf101_subset", os.path.join("ucf101_subset", "x")), ("ucf101", os.path.join("ucf101", "x"))):
    _vroot = os.path.join(DU, "video", _vdir)       # video folders downloaded by video_fetch.py; a task exists only once its files are extracted
    if os.path.isdir(_vroot) and f"video/{_vn}" not in TASKS and os.path.exists(os.path.join(DU, "video", _vdir.split(os.sep)[0], ".ready")):
        TASKS[f"video/{_vn}"] = ("video", (lambda r=_vroot: src_video_dir(r)), ("enc", "enc2"))

for _name, _spec in _registered().items():     # datasets added through ni_hub.py become tasks automatically
    if _spec.get("ok") and _name not in TASKS:
        TASKS[_name] = (_spec["modality"], (lambda s=_spec: src_generic(s)), ("enc", "enc2") if _spec["modality"] in ("text", "image", "audio", "graph") else ("enc",))


def out_path(kind, name, suffix=""):
    return os.path.join(OUT, kind, name.replace("/", os.sep) + suffix + ".npz")


def run_task(name, kinds=None, limit=None, force=False):
    mod, factory, avail = TASKS[name]
    kinds = [k for k in (kinds or [a for a in avail if a != "enc2"]) if k in avail]      # enc2 only when asked for (A/B set)
    suffix = f"__smoke{limit}" if limit else ""
    todo = [k for k in kinds if force or not os.path.exists(out_path(k, name, suffix))]
    if not todo:
        log(f"[encode] {name}: already done ({','.join(kinds)})"); return
    acc = {k: [] for k in todo}; oks = {k: [] for k in todo}; Y, G = [], []
    secs = {k: 0.0 for k in todo}; n = 0; t0 = time.time()
    for payload, y, g in factory():
        if limit and n >= limit:
            break
        if limit and n + len(y) > limit:
            cut = limit - n; payload = payload[:cut]; y = y[:cut]; g = g[:cut]
        for k in todo:
            t1 = time.time()
            X, ok = FEATS[mod][k](payload)
            secs[k] += time.time() - t1; acc[k].append(np.asarray(X, np.float32)); oks[k].append(np.asarray(ok))
        Y.append(y); G.append(g); n += len(y)
        log(f"[encode] {name}: {n} items, {time.time() - t0:.0f}s  " + " ".join(f"{k}={secs[k]:.0f}s" for k in todo))
    y = np.concatenate(Y); g = np.concatenate(G)
    keep = np.ones(len(y), bool)
    for k in todo:
        keep &= np.concatenate(oks[k])
    log(f"[encode] {name}: kept {int(keep.sum())}/{len(y)} items")
    for k in todo:
        X = np.concatenate(acc[k])[keep]
        yy = y[keep]; u, inv = np.unique(yy, return_inverse=True)
        p = out_path(k, name, suffix); os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".part"
        with open(tmp, "wb") as f:
            np.savez(f, X=X, y=inv.astype(np.int64), gid=g[keep], n_classes=len(u), seconds=secs[k])
        os.replace(tmp, p)
        log(f"[encode] saved {k}/{name}: X{X.shape} classes={len(u)} encode_time={secs[k]:.0f}s -> {p}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="all")
    ap.add_argument("--kinds", default=None, help="enc,hand (default: all available)")
    ap.add_argument("--limit", type=int, default=None, help="smoke test: only the first N items, written with a __smoke suffix")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True); set_logfile(os.path.join(OUT, "encode_log.txt"))
    names = list(TASKS) if a.tasks == "all" else a.tasks.split(",")
    for nm in names:
        try:
            run_task(nm, a.kinds.split(",") if a.kinds else None, a.limit, a.force)
        except Exception as e:
            import traceback
            log(f"[encode] {nm} FAILED: {traceback.format_exc()[-700:]}")
        if dev.type == "cuda":
            torch.cuda.empty_cache()
    log("[encode] ALL DONE")
