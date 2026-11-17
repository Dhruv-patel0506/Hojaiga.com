"""Feature extractors per modality. Pure numpy/scipy/cv2 (no model downloads)."""
import re, zlib
import numpy as np

TEXT_DIM = 2048
_tok = re.compile(r"[a-z0-9']+")


def text_feats(docs, dim=TEXT_DIM):
    out = np.zeros((len(docs), dim), np.float32)
    for i, d in enumerate(docs):
        toks = _tok.findall(d.lower())
        grams = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
        for g in grams:
            h = zlib.crc32(g.encode())
            out[i, h % dim] += 1.0 if (h >> 20) & 1 else -1.0
    out = np.sign(out) * np.log1p(np.abs(out))
    n = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.maximum(n, 1e-6)


def image_feats(x):
    """x: uint8 [n,H,W,3] (any H,W >= 8). Returns [n, 384] float32."""
    x = x.astype(np.float32) / 255.0
    n, H, W, _ = x.shape
    H8, W8 = (H // 8) * 8, (W // 8) * 8
    x = x[:, :H8, :W8]
    small = x.reshape(n, 8, H8 // 8, 8, W8 // 8, 3).mean((2, 4)).reshape(n, -1)  # 192
    hist = np.stack([np.stack([np.histogram(x[i, :, :, c], bins=16, range=(0, 1))[0] for c in range(3)]).ravel()
                     for i in range(n)]).astype(np.float32)
    hist /= max(1, H8 * W8)  # 48
    g = x.mean(3)
    gx = np.zeros_like(g); gy = np.zeros_like(g)
    gx[:, :, 1:-1] = g[:, :, 2:] - g[:, :, :-2]
    gy[:, 1:-1, :] = g[:, 2:, :] - g[:, :-2, :]
    mag = np.sqrt(gx ** 2 + gy ** 2)
    ang = (np.arctan2(gy, gx) % np.pi) / np.pi * 9
    b = np.minimum(ang.astype(np.int32), 8)
    ch, cw = H8 // 4, W8 // 4
    hog = np.zeros((n, 4, 4, 9), np.float32)
    for by in range(4):
        for bx in range(4):
            m = mag[:, by * ch:(by + 1) * ch, bx * cw:(bx + 1) * cw].reshape(n, -1)
            bb = b[:, by * ch:(by + 1) * ch, bx * cw:(bx + 1) * cw].reshape(n, -1)
            for k in range(9):
                hog[:, by, bx, k] = (m * (bb == k)).sum(1)
    hog = hog.reshape(n, -1)
    hog /= np.maximum(np.linalg.norm(hog, axis=1, keepdims=True), 1e-6)
    return np.concatenate([small, hist, hog], 1).astype(np.float32)  # 192+48+144=384


def audio_feats(wave, sr, nb=32):
    """wave: float array (mono or [T,ch]). Returns 134-dim log-band stats."""
    from scipy.signal import stft
    w = np.asarray(wave, np.float32)
    if w.ndim > 1:
        w = w.mean(1)
    w = w[: int(sr * 4.0)]
    if len(w) < 2048:
        w = np.pad(w, (0, 2048 - len(w)))
    nper = 1024 if sr >= 22000 else 512
    f, t, Z = stft(w, fs=sr, nperseg=nper, noverlap=nper // 2)
    P = np.abs(Z) ** 2
    edges = np.geomspace(50, sr / 2 - 1, nb + 1)
    bands = np.zeros((nb, P.shape[1]), np.float32)
    for k in range(nb):
        m = (f >= edges[k]) & (f < edges[k + 1])
        if m.any():
            bands[k] = P[m].sum(0)
    L = np.log10(bands + 1e-10)
    d = np.abs(np.diff(L, axis=1)).mean(1) if L.shape[1] > 1 else np.zeros(nb)
    cen = (f[:, None] * P).sum(0) / (P.sum(0) + 1e-10)
    cs = np.cumsum(P, 0); roll = f[np.argmax(cs >= 0.85 * cs[-1:], axis=0)]
    frames = np.lib.stride_tricks.sliding_window_view(w, 512)[::256]
    rms = np.sqrt((frames ** 2).mean(1) + 1e-12)
    zcr = (np.diff(np.sign(frames), axis=1) != 0).mean(1)
    extra = [rms.mean(), rms.std(), zcr.mean(), cen.mean() / sr, cen.std() / sr, roll.mean() / sr]
    return np.concatenate([L.mean(1), L.std(1), L.max(1), d, extra]).astype(np.float32)  # 32*4+6=134


def graph_feats(edge_index, node_feat, n):
    """Structure + node-feature stats for one graph."""
    n = max(int(n), 1)
    A = np.zeros((n, n), np.float32)
    if len(edge_index) == 2 and len(edge_index[0]):
        s = np.asarray(edge_index[0], int); t = np.asarray(edge_index[1], int)
        ok = (s < n) & (t < n)
        A[s[ok], t[ok]] = 1.0; A[t[ok], s[ok]] = 1.0
    np.fill_diagonal(A, 0)
    deg = A.sum(1)
    E = A.sum() / 2
    tri = np.trace(A @ A @ A) / 6.0
    hist = np.bincount(np.minimum(deg.astype(int), 7), minlength=8)[:8] / n
    dinv = 1.0 / np.sqrt(np.maximum(deg, 1))
    Ln = (A * dinv[:, None]) * dinv[None, :]
    try:
        ev = np.sort(np.linalg.eigvalsh(Ln))[::-1][:4]
    except Exception:
        ev = np.zeros(4)
    ev = np.pad(ev, (0, 4 - len(ev)))
    trip = (deg * (deg - 1) / 2).sum()
    clus = 3 * tri / trip if trip > 0 else 0.0
    nf = np.asarray(node_feat, np.float32).reshape(n, -1) if node_feat is not None and len(node_feat) else np.zeros((n, 1), np.float32)
    base = [np.log1p(n), np.log1p(E), 2 * E / (n * (n - 1) + 1e-6), deg.mean(), deg.std(), deg.max(), clus, tri / n]
    return np.concatenate([base, hist, ev, nf.mean(0), nf.std(0)]).astype(np.float32)


def graph_wl_feats(edge_index, node_feat, n, iters=3, dim=512):
    """Weisfeiler-Lehman subtree histogram (hashed to `dim` buckets, log-scaled, L2-normalised) + the structure/spectral features.
    The WL colours of a molecule are the same idea as circular (ECFP) fingerprints: each atom's colour is refined by its neighbours'."""
    n = max(int(n), 1)
    nb = [set() for _ in range(n)]
    if len(edge_index) == 2:
        for s, t in zip(edge_index[0], edge_index[1]):
            if s < n and t < n and s != t:
                nb[s].add(t); nb[t].add(s)
    have = node_feat is not None and len(node_feat) > 0
    lab = []
    for i in range(n):
        if have and i < len(node_feat):
            lab.append(zlib.crc32(repr(tuple(round(float(v), 2) for v in np.atleast_1d(node_feat[i]))).encode()))
        else:
            lab.append(len(nb[i]))
    hist = np.zeros(dim, np.float32)
    for it in range(iters + 1):
        for l in lab:
            hist[(l * 2654435761 + it * 40503) % dim] += 1.0
        if it == iters:
            break
        lab = [zlib.crc32(f"{lab[i]}|{','.join(map(str, sorted(lab[j] for j in nb[i])))}".encode()) for i in range(n)]
    hist = np.log1p(hist); hist /= max(float(np.linalg.norm(hist)), 1e-6)
    return np.concatenate([graph_feats(edge_index, node_feat if have and len(node_feat) == n else None, n), hist]).astype(np.float32)


def video_feats(path, n_frames=8):
    import cv2
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frames = []
    if total > 0:
        for idx in np.linspace(0, max(total - 1, 0), n_frames).astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, fr = cap.read()
            if ok:
                frames.append(cv2.resize(fr, (32, 32), interpolation=cv2.INTER_AREA)[:, :, ::-1])
    else:
        while len(frames) < 64:
            ok, fr = cap.read()
            if not ok:
                break
            frames.append(cv2.resize(fr, (32, 32), interpolation=cv2.INTER_AREA)[:, :, ::-1])
        frames = [frames[i] for i in np.linspace(0, len(frames) - 1, n_frames).astype(int)] if frames else []
    cap.release()
    if len(frames) < 2:
        return None
    while len(frames) < n_frames:
        frames.append(frames[-1])
    F = np.stack(frames).astype(np.uint8)
    mid = image_feats(F[n_frames // 2: n_frames // 2 + 1])[0]  # 384
    g = F.astype(np.float32).mean(3) / 255.0
    motion = np.abs(np.diff(g, axis=0)).mean((1, 2))  # 7
    mean_hist = image_feats(F)[:, 192:240].mean(0)  # 48 colour hist averaged over time
    temporal = np.abs(np.diff(F.astype(np.float32).reshape(n_frames, -1, 3).mean(1), axis=0)).mean(0) / 255.0  # 3
    return np.concatenate([mid, motion, [motion.mean(), motion.std()], mean_hist, temporal]).astype(np.float32)


def graph_rich_feats(edge_index, node_feat, n, cap=400):
    """enc2 for graphs: everything the cheap WL fingerprint misses, as a fixed-length vector (no dataset-specific knowledge).
    WL subtree histograms (4 iterations, with node labels AND structure-only), full normalised-adjacency spectrum (histogram, extremes,
    heat-kernel traces, algebraic connectivity), random-walk return probabilities (closed-walk structure up to length 8), shortest-path
    length distribution (diameter / mean distance), degree and local-clustering distributions, node-feature min/max/mean/std."""
    from scipy.sparse.csgraph import shortest_path
    n = max(int(n), 1)
    have = node_feat is not None and len(node_feat) == n
    wl_lab = graph_wl_feats(edge_index, node_feat if have else None, n, iters=4, dim=1024)
    wl_deg = graph_wl_feats(edge_index, None, n, iters=3, dim=256)[-256:]
    A = np.zeros((n, n), np.float32)
    if len(edge_index) == 2 and len(edge_index[0]):
        s = np.asarray(edge_index[0], int); t = np.asarray(edge_index[1], int); ok = (s < n) & (t < n) & (s != t)
        A[s[ok], t[ok]] = 1.0; A[t[ok], s[ok]] = 1.0
    deg = A.sum(1)
    spec = np.zeros(24 + 8 + 5 + 2, np.float32); rw = np.zeros(8, np.float32); sp = np.zeros(12, np.float32)
    if n <= cap:
        dinv = 1.0 / np.sqrt(np.maximum(deg, 1))
        Ln = (A * dinv[:, None]) * dinv[None, :]
        try:
            ev = np.sort(np.linalg.eigvalsh(Ln))
            h = np.histogram(ev, bins=24, range=(-1.0, 1.0))[0] / n
            ext = np.pad(ev[::-1][:4], (0, max(0, 4 - len(ev)))).tolist() + np.pad(ev[:4], (0, max(0, 4 - len(ev)))).tolist()
            lap = 1.0 - ev
            heat = [float(np.exp(-t_ * lap).mean()) for t_ in (0.1, 0.3, 1.0, 3.0, 10.0)]
            lam2 = float(np.sort(lap)[1]) if len(lap) > 1 else 0.0
            spec = np.concatenate([h, ext[:8], heat, [lam2, float((lap < 1e-6).sum() / n)]]).astype(np.float32)
        except Exception:
            pass
        P = A * (1.0 / np.maximum(deg, 1))[:, None]; Pk = np.eye(n, dtype=np.float32)
        for k in range(8):
            Pk = Pk @ P; rw[k] = float(np.trace(Pk) / n)
        D = shortest_path(A, unweighted=True, directed=False); fin = np.isfinite(D) & (D > 0)
        if fin.any():
            d = D[fin]; sp = np.concatenate([np.bincount(np.minimum(d.astype(int), 9), minlength=10)[1:10][:9] / max(len(d), 1), [d.mean(), d.max() / n, float((~np.isfinite(D)).mean())]]).astype(np.float32)[:12]
            sp = np.pad(sp, (0, 12 - len(sp)))
    dh = np.bincount(np.minimum(deg.astype(int), 15), minlength=16)[:16] / n
    A2 = A @ A if n <= cap else None
    if A2 is not None:
        tri_i = np.diag(A2 @ A) / 2.0; trip_i = deg * (deg - 1) / 2.0
        cc = np.where(trip_i > 0, tri_i / np.maximum(trip_i, 1), 0.0); cq = np.quantile(cc, [0.25, 0.5, 0.75, 1.0])
        nd = np.where(deg > 0, (A @ deg) / np.maximum(deg, 1), 0.0); nbd = [nd.mean(), nd.std()]
    else:
        cq = np.zeros(4); nbd = [0.0, 0.0]
    nfm = np.asarray(node_feat, np.float32).reshape(n, -1) if have else np.zeros((n, 1), np.float32)
    nf = np.concatenate([nfm.mean(0), nfm.std(0), nfm.min(0), nfm.max(0)])
    return np.concatenate([wl_lab, wl_deg, spec, rw, sp, dh, cq, nbd, nf]).astype(np.float32)
