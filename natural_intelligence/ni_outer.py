"""OUTER BRAIN: four genuinely different predictors + a weighted vote.

  Predictor_Logic        Gaussian naive Bayes (closed form, rule-like, over-confident in high-D)
  Predictor_Pattern      MLP trained with micro-batches + gradient accumulation (GPU)
  Predictor_Verifier     cosine k-NN against the training window (local-evidence check, gives an OOD signal)
  Predictor_Exploratory  bagged linear heads on random Fourier features (stochastic, diverse errors)

The outer brain is re-fitted from scratch on each round's 70% window; it is scored on the
held-out 30% window. Those held-out OUTCOMES are the training dataset of the inner brain.
"""
import os, time, math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as Fn

NAMES = ["Predictor_Logic", "Predictor_Pattern", "Predictor_Verifier", "Predictor_Exploratory"]
P = len(NAMES)
# NI_ALGO=v2 switches on the changes made after the Nov-07 paired runs (each one traced to a measured weakness):
#   * Logic: shared full-covariance LDA with shrinkage + fitted temperature (diagonal naive Bayes was the weakest predictor on dense
#     embeddings, where dimensions are strongly correlated); falls back to the diagonal model for D > 1536 (hashed text).
#   * Pattern/Exploratory: sqrt-inverse-frequency class weights when the task is imbalanced (>5:1) - ogbg-molhiv sat on the majority baseline.
#   * Pattern: wider hidden layer (512) with input dropout.
# v1 stays the default so runs already in progress and their reports remain comparable.
ALGO = os.environ.get("NI_ALGO", "v1")


class Logic:
    def __init__(self, X, y, C):
        D = X.shape[1]
        self.mu = torch.stack([X[y == c].mean(0) if (y == c).any() else X.mean(0) for c in range(C)])
        v = torch.stack([X[y == c].var(0, unbiased=False) if (y == c).sum() > 1 else X.var(0) for c in range(C)])
        self.var = v + 0.05 * X.var(0, keepdim=True) + 1e-4
        cnt = torch.bincount(y, minlength=C).float().clamp_min(1)
        self.logprior = torch.log(cnt / cnt.sum())
        self.T = math.sqrt(D)

    @torch.no_grad()
    def proba(self, X):
        out = []
        for i in range(0, len(X), 2048):
            x = X[i:i + 2048, None, :]
            ll = -0.5 * (((x - self.mu[None]) ** 2 / self.var[None]) + torch.log(self.var[None])).sum(2) + self.logprior
            out.append(torch.softmax(ll / self.T, 1))
        return torch.cat(out)


def _lda_fit(X, y, C):
    n, D = X.shape
    cnt = torch.bincount(y, minlength=C).float().clamp_min(1)
    mu = torch.zeros(C, D, device=X.device).index_add_(0, y, X) / cnt[:, None]
    Xc = X - mu[y]
    S = Xc.T @ Xc / max(n - C, 1)
    alpha = float(min(0.5, max(0.02, 2.0 * D / n)))                     # more shrinkage when n is small relative to D
    eye = torch.eye(D, device=X.device)
    S = (1 - alpha) * S + alpha * (torch.trace(S) / D) * eye + 1e-4 * eye
    Wt = torch.linalg.solve(S, mu.T)                                     # [D,C]  = Sigma^-1 mu_c
    b = -0.5 * (mu.T * Wt).sum(0) + torch.log(cnt / cnt.sum())
    return Wt, b


class LogicLDA:
    """Gaussian generative rule with one shared, shrinkage-regularised full covariance (linear discriminant analysis)."""
    def __init__(self, X, y, C):
        n = len(X)
        g = torch.Generator(device="cpu").manual_seed(n)
        perm = torch.randperm(n, generator=g).to(X.device); k = max(int(0.1 * n), 1)
        Wt, b = _lda_fit(X[perm[k:]], y[perm[k:]], C)
        z = X[perm[:k]] @ Wt + b
        best, self.T = 1e9, 1.0
        for T in (1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0):                 # temperature picked on a held-out 10% of the TRAIN window
            nll = Fn.cross_entropy(z / T, y[perm[:k]]).item()
            if nll < best:
                best, self.T = nll, T
        self.Wt, self.b = _lda_fit(X, y, C)

    @torch.no_grad()
    def proba(self, X):
        return torch.cat([torch.softmax((X[i:i + 4096] @ self.Wt + self.b) / self.T, 1) for i in range(0, len(X), 4096)])


class Pattern:
    def __init__(self, X, y, C, seed, micro=128, accum=4, cw=None):
        torch.manual_seed(seed)
        D = X.shape[1]
        self.cw = cw
        if ALGO == "v2":
            self.net = nn.Sequential(nn.Dropout(0.05), nn.Linear(D, 512), nn.GELU(), nn.Dropout(0.25), nn.Linear(512, 128), nn.GELU(),
                                     nn.Linear(128, C)).to(X.device)
        else:
            self.net = nn.Sequential(nn.Linear(D, 256), nn.GELU(), nn.Dropout(0.2), nn.Linear(256, 128), nn.GELU(),
                                     nn.Linear(128, C)).to(X.device)
        opt = torch.optim.AdamW(self.net.parameters(), lr=2e-3, weight_decay=1e-3)
        n = len(X)
        updates = int(np.clip(12 * n / (micro * accum) + 100, 150, 1000))
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=updates)
        self.net.train()
        for u in range(updates):
            opt.zero_grad(set_to_none=True)
            for _ in range(accum):  # micro-batching with gradient accumulation
                idx = torch.randint(0, n, (micro,), device=X.device)
                loss = Fn.cross_entropy(self.net(X[idx]), y[idx], weight=self.cw, label_smoothing=0.05) / accum
                loss.backward()
            opt.step(); sched.step()
        self.net.eval()

    @torch.no_grad()
    def proba(self, X):
        return torch.cat([torch.softmax(self.net(X[i:i + 4096]), 1) for i in range(0, len(X), 4096)])


class Verifier:
    def __init__(self, X, y, C, k=15):
        self.Xn = Fn.normalize(X, dim=1)
        self.y = y; self.C = C; self.k = min(k, len(X)); self.tau = 0.05
        self.last_maxsim = None

    @torch.no_grad()
    def tune(self, Xs, ys, ks=(5, 15, 40), taus=(0.02, 0.05, 0.1)):
        """v3: pick the neighbourhood size and similarity temperature that give the lowest log-loss on a held-out slice of the
        training window (the task decides, not a constant)."""
        if len(Xs) > 2000:
            Xs, ys = Xs[:2000], ys[:2000]
        kmax = min(max(ks), len(self.Xn))
        v, ix = (Fn.normalize(Xs, dim=1) @ self.Xn.T).topk(kmax, 1)
        best = (1e9, self.k, self.tau)
        for k in ks:
            k = min(k, kmax)
            for tau in taus:
                w = torch.softmax(v[:, :k] / tau, 1)
                pr = torch.zeros(len(v), self.C, device=v.device).scatter_add_(1, self.y[ix[:, :k]], w)
                pr = (pr + 1e-3) / (1 + 1e-3 * self.C)
                nll = -pr[torch.arange(len(ys)), ys].log().mean().item()
                if nll < best[0]:
                    best = (nll, k, tau)
        self.k, self.tau = best[1], best[2]

    @torch.no_grad()
    def proba(self, X, want_sim=False):
        outs, sims = [], []
        for i in range(0, len(X), 1024):
            s = Fn.normalize(X[i:i + 1024], dim=1) @ self.Xn.T
            v, ix = s.topk(self.k, 1)
            w = torch.softmax(v / self.tau, 1)
            pr = torch.zeros(len(v), self.C, device=X.device)
            pr.scatter_add_(1, self.y[ix], w)
            outs.append(pr); sims.append(v[:, 0])
        self.last_maxsim = torch.cat(sims)
        return torch.cat(outs)


class Exploratory:
    def __init__(self, X, y, C, seed, R=1024, bags=5, steps=150, cw=None):
        g = torch.Generator(device="cpu").manual_seed(seed)
        D = X.shape[1]
        self.W = (torch.randn(D, R, generator=g) / math.sqrt(D) * 1.5).to(X.device)
        self.b = (torch.rand(R, generator=g) * 2 * math.pi).to(X.device)
        self.R = R
        Z = self.phi(X)
        n = len(X)
        self.heads = []
        for bgi in range(bags):
            gg = torch.Generator(device="cpu").manual_seed(seed + 17 * (bgi + 1))
            idx = torch.randint(0, n, (n,), generator=gg).to(X.device)
            head = nn.Linear(R, C).to(X.device)
            opt = torch.optim.Adam(head.parameters(), lr=1e-2, weight_decay=1e-4)
            for _ in range(steps):
                b = idx[torch.randint(0, n, (min(n, 2048),), device=X.device)]
                opt.zero_grad(); Fn.cross_entropy(head(Z[b]), y[b], weight=cw).backward(); opt.step()
            self.heads.append(head.eval())

    def phi(self, X):
        return torch.cos(X @ self.W + self.b) * math.sqrt(2.0 / self.R)

    @torch.no_grad()
    def proba(self, X):
        out = []
        for i in range(0, len(X), 4096):
            Z = self.phi(X[i:i + 4096])
            out.append(torch.stack([torch.softmax(h(Z), 1) for h in self.heads]).mean(0))
        return torch.cat(out)


class PatternEns:
    """v3 Pattern: the same MLP, averaged over m seeds, m chosen from how little data there is (small n overfits - seeds are cheap
    there; with a lot of data one net is already stable)."""
    def __init__(self, X, y, C, seed, cw=None):
        n = len(X)
        self.m = 3 if n < 4000 else (2 if n < 20000 else 1)
        self.nets = [Pattern(X, y, C, seed + 1009 * i, cw=cw) for i in range(self.m)]

    @torch.no_grad()
    def proba(self, X):
        return torch.stack([p.proba(X) for p in self.nets]).mean(0)


class ExploratoryMS:
    """v3 Exploratory: random-Fourier-feature bags, each at its OWN kernel width around the median pairwise distance of the data
    (multi-scale = genuinely different errors per bag). v1/v2 used one width fixed by a constant."""
    def __init__(self, X, y, C, seed, R=1024, bags=5, steps=150, cw=None):
        g = torch.Generator(device="cpu").manual_seed(seed)
        n, D = X.shape
        sub = X[torch.randperm(n, generator=g)[:512].to(X.device)]
        d_med = float(torch.cdist(sub, sub).flatten().median()) + 1e-6
        self.bags = []
        for bgi in range(bags):
            gg = torch.Generator(device="cpu").manual_seed(seed + 17 * (bgi + 1))
            sigma = d_med * math.exp(float(torch.empty(1).uniform_(-1.1, 0.4, generator=gg)))
            W = (torch.randn(D, R, generator=gg) / sigma).to(X.device)
            b = (torch.rand(R, generator=gg) * 2 * math.pi).to(X.device)
            Z = torch.cos(X @ W + b) * math.sqrt(2.0 / R)
            idx = torch.randint(0, n, (n,), generator=gg).to(X.device)
            head = nn.Linear(R, C).to(X.device)
            opt = torch.optim.Adam(head.parameters(), lr=1e-2, weight_decay=1e-4)
            for _ in range(steps):
                bb = idx[torch.randint(0, n, (min(n, 2048),), device=X.device)]
                opt.zero_grad(); Fn.cross_entropy(head(Z[bb]), y[bb], weight=cw).backward(); opt.step()
            del Z
            self.bags.append((W, b, head.eval(), R))

    @torch.no_grad()
    def proba(self, X):
        out = []
        for i in range(0, len(X), 4096):
            xb = X[i:i + 4096]
            out.append(torch.stack([torch.softmax(h(torch.cos(xb @ W + b) * math.sqrt(2.0 / R)), 1) for W, b, h, R in self.bags]).mean(0))
        return torch.cat(out)


# ---- v4: a tree learner for the Exploratory slot -------------------------------------------------------------------------------
# Measured (PROBE_gbdt.md, 6 graph sets, identical splits): gradient-boosted trees beat the four NI predictors on every one
# (+1.2 .. +6.8 points). The reason is the data, not the predictors: WL histograms + counts + spectra are heterogeneous, axis-aligned
# features, which trees split on and RFF/MLP/LDA/kNN smooth over. On dense pretrained embeddings trees usually lose, so the choice is
# made PER DATASET on the calibration slice (mix 0 = RFF only, 1 = trees only) and only attempted when the compute budget allows.
TREE_BUDGET = 2.5e7          # n_rows * D * max(C,2) above this: skip the tree member (cost grows linearly in all three)
TREE_MIXES = (0.0, 0.5, 1.0)
TREE_REFIT_MAX_S = 25.0      # a first tree fit slower than this is not repeated on the refit


class TreeBag:
    def __init__(self, X, y, C, seed, cw=None, iters=200):
        from sklearn.ensemble import HistGradientBoostingClassifier
        from threadpoolctl import threadpool_limits
        Xn = X.detach().cpu().numpy(); yn = y.detach().cpu().numpy(); self.C = C
        sw = None if cw is None else cw.detach().cpu().numpy()[yn]
        with threadpool_limits(4):
            self.m = HistGradientBoostingClassifier(max_iter=iters, learning_rate=0.1, early_stopping=True, validation_fraction=0.1,
                                                    n_iter_no_change=15, random_state=seed)
            self.m.fit(Xn, yn, sample_weight=sw)

    def proba(self, X):
        from threadpoolctl import threadpool_limits
        with threadpool_limits(4):
            p = self.m.predict_proba(X.detach().cpu().numpy())
        out = np.full((len(p), self.C), 1e-6, np.float32); out[:, self.m.classes_] = p
        return torch.as_tensor(out / out.sum(1, keepdims=True), device=X.device)


class ExploratoryBlend:
    """Exploratory slot of v4: (1-mix) * multi-scale RFF + mix * boosted trees."""
    def __init__(self, rff, tree, mix):
        self.rff, self.tree, self.mix = rff, tree, mix

    def proba(self, X):
        if self.mix <= 0 or self.tree is None:
            return self.rff.proba(X)
        if self.mix >= 1:
            return self.tree.proba(X)
        return (1 - self.mix) * self.rff.proba(X) + self.mix * self.tree.proba(X)


def _tree_ok(n, D, C):
    return n * D * max(C, 2) <= TREE_BUDGET


# ---- v3 calibration / stacking: all of it is fitted on a slice of the TRAIN window, never on the held-out 30% -------------------
REFIT_BELOW = 20000          # below this many training rows the predictors are refitted on the whole window after calibration
T_GRID = (0.25, 0.35, 0.5, 0.7, 1.0, 1.4, 2.0, 2.8, 4.0, 8.0)


def _temper(p, T):
    return torch.softmax(p.clamp_min(1e-5).log() / T, -1)


def _unshift(v, cal):
    if cal is None or cal.get("bias") is None:
        return v
    v = v * torch.exp(-cal["bias"])[None]
    return v / v.sum(1, keepdim=True)


def _nll(p, y):
    return -(p[torch.arange(len(y)), y].clamp_min(1e-9)).log().mean().item()


def fit_calibration(Ps, ys, C, prior_cnt):
    """Ps [P,n,C] raw predictor probabilities on the slice. Returns per-predictor temperature, stack weights (mean 1) and a
    class log-bias. Everything is derived from the slice: nothing here is a per-dataset constant."""
    P_ = Ps.shape[0]
    T = []
    for p in range(P_):
        T.append(min(T_GRID, key=lambda t: _nll(_temper(Ps[p], t), ys)))
    Pc = torch.stack([_temper(Ps[p], T[p]) for p in range(P_)])
    theta = torch.zeros(P_, device=Ps.device, requires_grad=True)
    opt = torch.optim.Adam([theta], lr=0.1)
    with torch.enable_grad():
        for _ in range(150):                                        # stack weights = log-loss-optimal mixture weights
            s = torch.softmax(theta, 0)
            mix = (Pc * s[:, None, None]).sum(0)
            loss = -(mix[torch.arange(len(ys)), ys].clamp_min(1e-9)).log().mean() + 0.01 * (theta ** 2).sum()
            opt.zero_grad(); loss.backward(); opt.step()
    s = (torch.softmax(theta.detach(), 0) * P_)
    mix = (Pc * s[:, None, None]).sum(0) / P_
    # class prior correction for imbalanced tasks: bias = -alpha*log(prior), alpha picked on the slice by balanced accuracy.
    # Only when the task is imbalanced (the plain vote then just predicts the majority class and accuracy hides it).
    pri = (prior_cnt / prior_cnt.sum()).clamp_min(1e-6)
    alpha = 0.0
    if float(prior_cnt.max() / prior_cnt[prior_cnt > 0].min()) > 5:
        def score(a):                       # half plain accuracy, half balanced accuracy: do not buy minority recall with a collapse in accuracy
            pr = (mix * torch.exp(-a * pri.log())[None]).argmax(1)
            bal = float(np.mean([(pr[ys == c] == c).float().mean().item() for c in torch.unique(ys).tolist()]))
            return 0.5 * bal + 0.5 * float((pr == ys).float().mean())
        alpha = max((0.0, 0.25, 0.5, 0.75, 1.0), key=score)
        if int((ys == torch.argmin(torch.where(prior_cnt > 0, prior_cnt, prior_cnt.max() + 1))).sum()) < 10:
            alpha = min(alpha, 0.5)                                 # too few minority cases on the slice to trust a large shift
    return dict(T=T, s=s, bias=(-alpha * pri.log()) if alpha > 0 else None, alpha=alpha)


def _auc(score, label):
    l = np.asarray(label) > 0.5; s = np.asarray(score, np.float64)
    npos, nneg = int(l.sum()), int((~l).sum())
    if npos == 0 or nneg == 0:
        return None
    u, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    ranks = (np.cumsum(cnt) - (cnt - 1) / 2.0)[inv]
    return (ranks[l].sum() - npos * (npos + 1) / 2) / (npos * nneg)


def entropy(p):
    C = p.shape[-1]
    return -(p.clamp_min(1e-9) * p.clamp_min(1e-9).log()).sum(-1) / math.log(max(C, 2))


def fit_v3(Xtr, ytr, C, fit_seed, dev, use_lda=None):
    """Diagnose the data, then treat it: a calibration slice is held out of the TRAIN window, the four predictors are fitted on the
    rest (each tuned from what the data shows), and temperatures / stack weights / class prior shift are fitted on the slice.
    Returns (predictors, cal, diag). Used by the rounds here and by the manager gate (ni_serve)."""
    n_tr, D = Xtr.shape
    if use_lda is None:
        use_lda = D <= 2304
    ks = int(min(max(0.12 * n_tr, 24), 20000, n_tr // 3))
    pg = torch.Generator(device="cpu").manual_seed(fit_seed + 91)
    perm = torch.randperm(n_tr, generator=pg).to(dev)
    sl, fi = perm[:ks], perm[ks:]
    Xf, yf, Xs_, ys_ = Xtr[fi], ytr[fi], Xtr[sl], ytr[sl]
    cntf = torch.bincount(yf, minlength=C).float()
    cwf = ((len(yf) / (C * cntf.clamp_min(1))) ** 0.5).to(dev) if cntf.max() / cntf[cntf > 0].min() > 5 else None
    ver = Verifier(Xf, yf, C); ver.tune(Xs_, ys_)
    preds = [(LogicLDA if use_lda else Logic)(Xf, yf, C), PatternEns(Xf, yf, C, fit_seed, cw=cwf), ver,
             ExploratoryMS(Xf, yf, C, fit_seed, cw=cwf)]
    mix, tree_note, tb = 0.0, "off", None
    if ALGO == "v4":
        if _tree_ok(len(yf), D, C):
            try:
                t_tb = time.time(); tb = TreeBag(Xf, yf, C, fit_seed, cw=cwf); tb.fit_s = time.time() - t_tb
                pr, pt = preds[3].proba(Xs_), tb.proba(Xs_)
                nll = {m_: float(_nll(((1 - m_) * pr + m_ * pt), ys_)) for m_ in TREE_MIXES}
                best_other = min(float(_nll(p_.proba(Xs_) / p_.proba(Xs_).sum(1, keepdim=True).clamp_min(1e-9), ys_)) for p_ in preds)
                tree_note = {**{str(k): round(v, 4) for k, v in nll.items()}, "best_other": round(best_other, 4)}
                # the tree joins only when it is BETTER than every existing predictor on the held-out slice (measured: on dense
                # pretrained embeddings it is not, and blending it in cost accuracy and 5x the time); otherwise v4 == v3
                if nll[1.0] < best_other:
                    mix = min(nll, key=nll.get)
                    if mix > 0:
                        preds[3] = ExploratoryBlend(preds[3], tb, mix)
                    else:
                        tb = None
                else:
                    tb = None
            except Exception as e:
                tree_note = "error:" + repr(e)[:60]
        else:
            tree_note = "skipped(budget)"
    Ps = torch.stack([p.proba(Xs_) for p in preds]); Ps = Ps / Ps.sum(2, keepdim=True).clamp_min(1e-9)
    cal = fit_calibration(Ps, ys_, C, cntf)
    refit = n_tr < REFIT_BELOW
    if refit:    # little data: the slice cost real training rows, so refit on everything and keep the calibration learned on the slice
        cnta = torch.bincount(ytr, minlength=C).float()
        cwa = ((n_tr / (C * cnta.clamp_min(1))) ** 0.5).to(dev) if cnta.max() / cnta[cnta > 0].min() > 5 else None
        ver2 = Verifier(Xtr, ytr, C); ver2.k, ver2.tau = ver.k, ver.tau
        preds = [(LogicLDA if use_lda else Logic)(Xtr, ytr, C), PatternEns(Xtr, ytr, C, fit_seed, cw=cwa), ver2,
                 ExploratoryMS(Xtr, ytr, C, fit_seed, cw=cwa)]
        if mix > 0:
            # refitting the trees on every row costs another full fit; when the first fit was already slow, keep it (trained on 88% of the rows)
            tb2 = tb if getattr(tb, "fit_s", 0.0) > TREE_REFIT_MAX_S else TreeBag(Xtr, ytr, C, fit_seed, cw=cwa)
            preds[3] = ExploratoryBlend(preds[3], tb2, mix)
    diag = dict(refit_on_all=refit, n_fit=len(yf), n_cal=ks, D=D, imbalance=round(float(cntf.max() / cntf[cntf > 0].min()), 2),
                pattern_seeds=preds[1].m, verifier_k=ver.k, verifier_tau=ver.tau, T=[round(float(t), 2) for t in cal["T"]],
                stack=[round(float(x), 3) for x in cal["s"]], prior_shift=cal["alpha"], tree_mix=mix, tree_nll=tree_note)
    return preds, cal, diag


class RoundContext:
    """Everything the inner brain's JEV sandbox needs to re-run the outer brain on perturbed inputs."""
    def __init__(self, predictors, mu, sd, Xva, yva, C, weights, cal=None):
        self.predictors, self.mu, self.sd, self.Xva, self.yva, self.C = predictors, mu, sd, Xva, yva, C
        self.weights = weights; self.cal = cal       # cal: v3 temperatures / stack weights / class bias (None = v1/v2 behaviour)

    def probs(self, Xs):
        Pr = torch.stack([self.predictors[0].proba(Xs), self.predictors[1].proba(Xs),
                          self.predictors[2].proba(Xs), self.predictors[3].proba(Xs)])  # [P,n,C]
        if self.cal is not None:
            Pr = torch.stack([_temper(Pr[p] / Pr[p].sum(1, keepdim=True).clamp_min(1e-9), self.cal["T"][p]) for p in range(Pr.shape[0])])
        return Pr

    def vote(self, Pr, w=None):
        w = self.weights if w is None else w
        wt = torch.as_tensor(w, dtype=torch.float32, device=Pr.device)[:, None, None]
        if self.cal is not None:
            wt = wt * self.cal["s"][:, None, None]
        v = (Pr * wt).sum(0) / wt.sum()
        if self.cal is not None and self.cal["bias"] is not None:
            v = v * torch.exp(self.cal["bias"])[None]; v = v / v.sum(1, keepdim=True)
        return v


class OuterBrain:
    def __init__(self, device):
        self.dev = device
        self.weights = {}      # task -> np.array[4] (meta weights, updated by the inner brain)
        self.last_acc = {}     # task -> previous round's vote accuracy (for the adaptability probe)

    def run_round(self, task, data, split_seed, fit_seed):
        from ni_common import split_train_mask
        t0 = time.time()
        dev = self.dev
        C = data["n_classes"]
        m = split_train_mask(data["gid"], split_seed)
        tr, va = np.where(m)[0], np.where(~m)[0]
        if len(tr) < 30 or len(va) < 15:
            return None
        Xtr = torch.as_tensor(data["X"][tr], device=dev); ytr = torch.as_tensor(data["y"][tr], device=dev)
        Xva = torch.as_tensor(data["X"][va], device=dev); yva = torch.as_tensor(data["y"][va], device=dev)
        mu, sd = Xtr.mean(0, keepdim=True), Xtr.std(0, keepdim=True) + 1e-4
        Xtr, Xva = (Xtr - mu) / sd, (Xva - mu) / sd
        cw = None
        if ALGO == "v2":
            cnt = torch.bincount(ytr, minlength=C).float()
            if cnt.max() / cnt[cnt > 0].min() > 5:        # imbalanced task: sqrt-inverse-frequency class weights
                cw = ((len(ytr) / (C * cnt.clamp_min(1))) ** 0.5).to(dev)
        use_lda = (ALGO == "v2" and Xtr.shape[1] <= 1536) or (ALGO in ("v3", "v4") and Xtr.shape[1] <= 2304)
        cal, diag = None, None
        if ALGO in ("v3", "v4"):
            preds, cal, diag = fit_v3(Xtr, ytr, C, fit_seed, dev, use_lda)
        else:
            preds = [(LogicLDA if use_lda else Logic)(Xtr, ytr, C), Pattern(Xtr, ytr, C, fit_seed, cw=cw), Verifier(Xtr, ytr, C),
                     Exploratory(Xtr, ytr, C, fit_seed, cw=cw)]
        fit_s = time.time() - t0
        t1 = time.time()
        w = self.weights.get(task, np.ones(P, np.float32))
        ctx = RoundContext(preds, mu, sd, Xva, yva, C, w, cal)
        Pr = ctx.probs(Xva)
        if cal is None:
            Pr = Pr / Pr.sum(2, keepdim=True).clamp_min(1e-9)
        maxsim = preds[2].last_maxsim
        infer_s = time.time() - t1
        wt = torch.as_tensor(w, dtype=torch.float32, device=dev)[:, None, None]
        vote = ctx.vote(Pr, w) if cal is not None else (Pr * wt).sum(0) / wt.sum()
        uni = Pr.mean(0)
        pred = vote.argmax(1)
        top2 = vote.topk(min(2, C), 1).values
        margin = top2[:, 0] - (top2[:, 1] if C > 1 else 0)
        pcls = Pr.argmax(2)                                   # [P,n]
        agree = (pcls == pred[None]).float()                  # [P,n]
        winner = ((Pr[:, torch.arange(len(va)), pred]) * wt[:, :, 0]).argmax(0)
        acc_p = (pcls == yva[None]).float().mean(1).cpu().numpy()
        acc_vote = (pred == yva).float().mean().item()
        acc_uni = (uni.argmax(1) == yva).float().mean().item()
        yv_np, pv_np = yva.cpu().numpy(), pred.cpu().numpy()
        recalls = [float((pv_np[yv_np == c] == c).mean()) for c in np.unique(yv_np)]
        acc_bal = float(np.mean(recalls))                                   # balanced accuracy: mean per-class recall
        auroc = _auc(vote[:, 1].cpu().numpy(), yv_np == 1) if C == 2 else None   # accuracy hides a majority-class predictor
        rec = dict(
            gid=data["gid"][va], y=yva.cpu().numpy(), pred=pred.cpu().numpy(),
            correct=(pred == yva).float().cpu().numpy(),
            p_conf=Pr.max(2).values.T.cpu().numpy(),          # [n,P]
            p_ent=entropy(Pr).T.cpu().numpy(),                # [n,P]
            p_agree=agree.T.cpu().numpy(),                    # [n,P]
            p_correct=(pcls == yva[None]).float().T.cpu().numpy(),
            vote_conf=vote.max(1).values.cpu().numpy(), vote_margin=margin.cpu().numpy(),
            vote_ent=entropy(vote).cpu().numpy(), maxsim=maxsim.cpu().numpy(),
            winner=winner.cpu().numpy(), w=np.tile(w / w.mean(), (len(va), 1)).astype(np.float32),
            logC=np.full(len(va), math.log(C) / math.log(51), np.float32),
        )
        info = dict(task=task, n_train=len(tr), n_val=len(va), C=C, acc_vote=acc_vote, acc_uniform=acc_uni, acc_bal=round(acc_bal, 4),
                    auroc=None if auroc is None else round(float(auroc), 4), algo=ALGO, diag=diag,
                    nll=round(_nll(_unshift(vote, cal), yva), 4),   # log-loss of the calibrated probabilities (prior shift is a decision rule, not a probability)
                    acc_pred=dict(zip(NAMES, [round(float(a), 4) for a in acc_p])),
                    chance=float(np.bincount(data["y"]).max() / len(data["y"])),
                    fit_s=round(fit_s, 2), infer_s=round(infer_s, 3), weights=[round(float(x), 3) for x in w],
                    vram_peak_gb=round(torch.cuda.max_memory_allocated() / 2**30, 3) if dev.type == "cuda" else 0.0)
        return rec, info, ctx
