"""INNER BRAIN: trained on the OUTER BRAIN's outcome stream.

Input dataset  = outcome records of the outer brain (per-predictor confidence/entropy/agreement,
                 vote margin, k-NN evidence, current meta-weights, modality, ...).
Learned target = "was the outer brain's final decision correct?"  (ground truth from the stream)
Self-questioning = measured probes (leave-one-predictor-out, input perturbation, per-class
                 weakness, round-to-round drift), each answered with numbers, not prose.
JEV sandbox    = executable verification run on low-trust decisions: the outer brain is re-run on
                 perturbed inputs and with each predictor removed; the decision is VERIFIED or REJECTED.
Feedback       = hardness-weighted multiplicative update of the outer meta-weights.
"""
import math, time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as Fn
from ni_common import split_train_mask, seed_for, VRAM_LIMIT_GB
from ni_outer import NAMES, P
from ni_data import MODALITIES

HOLDOUT_SEED = 777    # permanent 20% of samples the inner brain NEVER trains on (honest evaluation)
TAU_JEV = 0.75        # inner trust below this -> JEV sandbox is invoked
GRADE_W = dict(reliability=0.35, truthfulness=0.25, adaptability=0.20, scalability=0.20)  # Grill sec. 4


def build_features(rec, modality):
    n = len(rec["y"])
    mod = np.zeros((n, len(MODALITIES)), np.float32); mod[:, MODALITIES.index(modality)] = 1
    cols = [rec["p_conf"], rec["p_ent"], rec["p_agree"], rec["w"],
            rec["vote_conf"][:, None], rec["vote_margin"][:, None], rec["vote_ent"][:, None],
            rec["maxsim"][:, None], rec["logC"][:, None], mod,
            np.log(np.clip(rec["vote_conf"], 0.02, 0.98) / (1 - np.clip(rec["vote_conf"], 0.02, 0.98)))[:, None]]
    return np.concatenate(cols, 1).astype(np.float32)


def auc(score, label):
    s = np.asarray(score, np.float64); l = np.asarray(label) > 0.5
    npos, nneg = l.sum(), (~l).sum()
    if npos == 0 or nneg == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort"); ranks = np.empty(len(s)); ranks[order] = np.arange(1, len(s) + 1)
    # average ties
    u, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    if len(u) < len(s):
        cs = np.cumsum(cnt); avg = (cs - (cnt - 1) / 2.0); ranks = avg[inv]
    return float((ranks[l].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def ece(conf, correct, bins=15):
    conf = np.asarray(conf); correct = np.asarray(correct)
    e = 0.0
    for b in range(bins):
        m = (conf > b / bins) & (conf <= (b + 1) / bins)
        if m.any():
            e += m.mean() * abs(conf[m].mean() - correct[m].mean())
    return float(e)


def acc_at_coverage(score, correct, cov):
    k = max(1, int(len(score) * cov))
    top = np.argsort(-np.asarray(score), kind="mergesort")[:k]
    return float(np.asarray(correct)[top].mean())


class InnerNet(nn.Module):
    def __init__(self, d):
        super().__init__()
        self.f = nn.Sequential(nn.Linear(d, 64), nn.GELU(), nn.Dropout(0.1), nn.Linear(64, 64), nn.GELU(), nn.Linear(64, 1))
        nn.init.zeros_(self.f[-1].weight); nn.init.zeros_(self.f[-1].bias)   # deep path starts silent -> start = wide path
        self.wide = nn.Linear(d, 1)   # wide&deep: a linear path so it starts at least as good as the raw vote-confidence logit
        nn.init.zeros_(self.wide.weight); nn.init.zeros_(self.wide.bias)
        with torch.no_grad():
            self.wide.weight[0, -1] = 1.0   # last feature column = logit(vote_conf)

    def forward(self, x):
        return (self.f(x) + self.wide(x)).squeeze(-1)


class InnerBrain:
    def __init__(self, device, cap=3_000_000):
        self.dev = device; self.cap = cap
        self.X = np.zeros((0, 0), np.float32); self.t = np.zeros(0, np.float32)
        self.gid = np.zeros(0, np.int64); self.rnd = np.zeros(0, np.int32)
        self.net = None; self.mean = None; self.std = None
        self.history = []

    # ---------------------------------------------------------- ingest (Outer outcomes -> Inner dataset)
    def ingest(self, rec, modality, round_id):
        X = build_features(rec, modality)
        if self.X.shape[1] == 0:
            self.X = X; self.t = rec["correct"].astype(np.float32); self.gid = rec["gid"]
            self.rnd = np.full(len(X), round_id, np.int32)
        else:
            self.X = np.concatenate([self.X, X]); self.t = np.concatenate([self.t, rec["correct"].astype(np.float32)])
            self.gid = np.concatenate([self.gid, rec["gid"]]); self.rnd = np.concatenate([self.rnd, np.full(len(X), round_id, np.int32)])
        if len(self.X) > self.cap:
            self.X, self.t, self.gid, self.rnd = (a[-self.cap:] for a in (self.X, self.t, self.gid, self.rnd))
        return X

    # ---------------------------------------------------------- train on the outcome dataset
    def train(self, cycle, steps=500, bs=1024):
        if len(self.X) < 200:
            return None
        if self.net is None:
            self.mean = self.X.mean(0); self.std = np.maximum(self.X.std(0), 0.3)  # floor: columns constant at fit time (weights=1) must not explode later
            self.net = InnerNet(self.X.shape[1]).to(self.dev)
            self.opt = torch.optim.AdamW(self.net.parameters(), lr=2e-3, weight_decay=1e-2)
        seed = seed_for("inner", cycle)
        hold = ~split_train_mask(self.gid, HOLDOUT_SEED, 0.8)
        pool = np.where(~hold)[0]
        m = split_train_mask(self.gid[pool], seed)
        tr, va = pool[m], np.where(hold)[0]       # rotating 70% of the pool trains; evaluation = permanent holdout
        if len(tr) < 100 or len(va) < 50:
            return None
        Xt = torch.as_tensor(self._norm(self.X[tr]), device=self.dev); yt = torch.as_tensor(self.t[tr], device=self.dev)
        torch.manual_seed(seed)
        vm = split_train_mask(self.gid[pool], seed)   # rotating 30% of the pool = early-stopping window
        vi = pool[~vm]
        Xv = torch.as_tensor(self._norm(self.X[vi]), device=self.dev); yv = torch.as_tensor(self.t[vi], device=self.dev)
        def vloss():
            self.net.eval()
            with torch.no_grad():
                return Fn.binary_cross_entropy_with_logits(self.net(Xv), yv).item()
        best, best_state = vloss(), {k: v.clone() for k, v in self.net.state_dict().items()}
        for st in range(steps):
            self.net.train()
            idx = torch.randint(0, len(tr), (min(bs, len(tr)),), device=self.dev)
            self.opt.zero_grad(set_to_none=True)
            Fn.binary_cross_entropy_with_logits(self.net(Xt[idx]), yt[idx]).backward()
            self.opt.step()
            if (st + 1) % 50 == 0:
                l = vloss()
                if l < best:
                    best, best_state = l, {k: v.clone() for k, v in self.net.state_dict().items()}
        self.net.load_state_dict(best_state)
        self.net.eval()
        p = self.predict(self.X[va]); y = self.t[va]
        vc = self.X[va][:, 16]  # vote_conf column (see build_features ordering)
        res = dict(cycle=cycle, n_records=int(len(self.X)), n_val=int(len(va)), base_rate=float(y.mean()),
                   inner=dict(auc=auc(p, y), ece=ece(p, y), brier=float(((p - y) ** 2).mean()),
                              acc80=acc_at_coverage(p, y, 0.8)),
                   outer_conf=dict(auc=auc(vc, y), ece=ece(vc, y), brier=float(((vc - y) ** 2).mean()),
                                   acc80=acc_at_coverage(vc, y, 0.8)))
        self.history.append(res)
        return res

    def _norm(self, X):
        return np.clip(np.nan_to_num((X - self.mean) / self.std), -8, 8).astype(np.float32)

    @torch.no_grad()
    def predict(self, X):
        if self.net is None:
            return np.full(len(X), 0.5, np.float32)
        x = torch.as_tensor(self._norm(X), device=self.dev)
        return np.nan_to_num(torch.sigmoid(self.net(x)).cpu().numpy(), nan=0.5)

    # ---------------------------------------------------------- JEV execution sandbox
    @torch.no_grad()
    def jev(self, ctx, rec, p1, seed, tau=TAU_JEV, cap=6000, draws=4, sigma=0.5):
        """Re-run the outer brain on perturbed inputs / with each predictor removed for low-trust decisions."""
        trig = np.where(p1 < tau)[0]
        if len(trig) == 0:
            return dict(idx=trig, consistency=np.zeros(0), loo=np.zeros(0), verified=np.zeros(0, bool), n_trig=0)
        if len(trig) > cap:
            trig = np.sort(np.random.RandomState(seed).choice(trig, cap, replace=False))
        g = torch.Generator(device=self.dev).manual_seed(seed)
        ti = torch.as_tensor(trig, device=self.dev)
        Xs = ctx.Xva[ti]
        pred0 = torch.as_tensor(rec["pred"][trig], device=self.dev)
        cons = torch.zeros(len(trig), device=self.dev)
        for _ in range(draws):
            Xn = Xs + sigma * torch.randn(Xs.shape, generator=g, device=self.dev)
            cons += (ctx.vote(ctx.probs(Xn)).argmax(1) == pred0).float()
        cons /= draws
        Pr = ctx.probs(Xs)
        w = np.asarray(ctx.weights, np.float32)
        loo = torch.zeros(len(trig), device=self.dev)
        for p in range(P):
            w2 = w.copy(); w2[p] = 0.0
            loo += (ctx.vote(Pr, w2).argmax(1) == pred0).float()
        loo /= P
        cons, loo = cons.cpu().numpy(), loo.cpu().numpy()
        return dict(idx=trig, consistency=cons, loo=loo, verified=(cons >= 0.75) & (loo >= 0.75), n_trig=int(len(trig)))

    # ---------------------------------------------------------- feedback to the outer brain
    def feedback_weights(self, w, rec, p1, eta=1.5):
        hard = (1.0 - p1) + 0.1
        wrong = 1.0 - rec["p_correct"]                       # [n,P]
        L = (wrong * hard[:, None]).sum(0) / hard.sum()
        adv = L.mean() - L
        w2 = np.asarray(w, np.float64) * np.exp(eta * adv)
        w2 = np.clip(w2 / w2.mean(), 0.2, 5.0)
        return (w2 / w2.mean()).astype(np.float32), dict(zip(NAMES, [round(float(a), 4) for a in adv]))

    # ---------------------------------------------------------- assess one round (self-questioning + factors)
    def assess(self, task, modality, rec, info, ctx, prev_acc, cycle, round_id, throughput, vram_gb):
        X = build_features(rec, modality)
        p1 = self.predict(X)
        correct = rec["correct"]
        # honest evaluation: only samples the inner brain never trains on (permanent holdout)
        held = np.where(~split_train_mask(rec["gid"], HOLDOUT_SEED, 0.8))[0]
        jev = self.jev(ctx, rec, p1, seed_for(task, cycle, salt=9))
        trig = jev["idx"]
        # --- self-questioning answered with numbers
        n = len(correct)
        winner_ct = np.bincount(rec["winner"], minlength=P) / n
        pc = rec["p_correct"].mean(0)
        flips = None
        Pr_flip = []
        # Q1 'why did X win': how often would the decision change without predictor p?
        # (computed on a subsample for cost)
        sub = np.random.RandomState(seed_for(task, cycle, 3)).choice(n, min(n, 3000), replace=False)
        with torch.no_grad():
            Pr = ctx.probs(ctx.Xva[torch.as_tensor(sub, device=self.dev)])
            base = ctx.vote(Pr).argmax(1)
            w = np.asarray(ctx.weights, np.float32)
            flips = []
            for p in range(P):
                w2 = w.copy(); w2[p] = 0
                flips.append(float((ctx.vote(Pr, w2).argmax(1) != base).float().mean()))
        # Q3 weakest class
        yv, pv = rec["y"], rec["pred"]
        cls_acc = {int(c): float((pv[yv == c] == c).mean()) for c in np.unique(yv) if (yv == c).sum() >= 5}
        worst = min(cls_acc.items(), key=lambda kv: kv[1]) if cls_acc else (None, float("nan"))
        div = float(1.0 - rec["p_agree"].mean())
        # --- JEV outcome statistics
        jv = {}
        if len(trig):
            ok = jev["verified"]
            cc = correct[trig]
            jv = dict(n_triggered=int(len(trig)), frac_triggered=float(len(trig) / n),
                      acc_verified=float(cc[ok].mean()) if ok.any() else None,
                      acc_rejected=float(cc[~ok].mean()) if (~ok).any() else None,
                      n_verified=int(ok.sum()), n_rejected=int((~ok).sum()),
                      consistency_mean=float(jev["consistency"].mean()), loo_mean=float(jev["loo"].mean()))
        # --- selective prediction on the inner-held-out window
        sel = {}
        if len(held) > 100:
            hc = correct[held]
            cov = 0.8
            accepted = (p1 >= TAU_JEV)
            if len(trig):
                v = np.zeros(n, bool); v[trig[jev["verified"]]] = True; accepted = accepted | v
            ah = accepted[held]
            kk = max(1, int(ah.sum()))
            base_acc_same_cov = acc_at_coverage(rec["vote_conf"][held], hc, ah.mean() if ah.mean() > 0 else cov)
            sel = dict(n_held=int(len(held)), outer_acc_all=float(hc.mean()), cov_final=float(ah.mean()),
                       acc_final=float(hc[ah].mean()) if ah.any() else None,
                       acc_by_voteconf_same_cov=base_acc_same_cov,
                       acc_by_inner_same_cov=acc_at_coverage(p1[held], hc, ah.mean() if ah.mean() > 0 else cov),
                       inner_auc=auc(p1[held], hc), voteconf_auc=auc(rec["vote_conf"][held], hc),
                       inner_ece=ece(p1[held], hc), voteconf_ece=ece(rec["vote_conf"][held], hc))
        # --- 4 factor scores (all measured, formulas in the Grill file)
        rel = 1.0 - ece(rec["vote_conf"], correct)
        tru = float(correct.mean())
        cons_all = jv.get("consistency_mean", 1.0)
        stab = 1.0 if prev_acc is None else max(0.0, 1.0 - 5.0 * abs(tru - prev_acc))
        ada = 0.5 * cons_all + 0.5 * stab
        sca = 0.5 * max(0.0, 1.0 - vram_gb / VRAM_LIMIT_GB) + 0.5 * min(1.0, throughput / 200.0)
        grade = (GRADE_W["reliability"] * rel + GRADE_W["truthfulness"] * tru +
                 GRADE_W["adaptability"] * ada + GRADE_W["scalability"] * sca)
        # --- feedback
        w_new, adv = self.feedback_weights(ctx.weights, rec, p1)
        # --- transcripts: hardest samples with their numbers
        transcripts = []
        order = np.argsort(p1)[:3]
        cmap = {int(t): k for k, t in enumerate(trig)}
        for i in order:
            j = cmap.get(int(i))
            transcripts.append(dict(
                task=task, round=round_id, sample_gid=int(rec["gid"][i]), truth=int(rec["y"][i]), vote=int(rec["pred"][i]),
                correct=bool(correct[i]),
                Q1_why_did_winner_win=f"{NAMES[int(rec['winner'][i])]} held weight {float(rec['w'][i][int(rec['winner'][i])]):.2f} "
                                      f"and {int(rec['p_agree'][i].sum())}/{P} predictors agreed; leaving out each predictor flips the vote "
                                      f"{dict(zip(NAMES, [round(f, 3) for f in flips]))} of the time",
                Q2_robust_to_shift=None if j is None else f"under 4 noisy re-runs the same class won {jev['consistency'][j]:.2f} of the time; "
                                                          f"verdict {'VERIFIED' if jev['verified'][j] else 'REJECTED'}",
                Q3_edge_cases=f"vote_margin={float(rec['vote_margin'][i]):.3f}, knn_maxsim={float(rec['maxsim'][i]):.3f}, weakest class in this round={worst[0]} (acc {worst[1]:.2f})",
                Q4_adaptable_or_rigid=f"predictor disagreement {div:.3f}; accuracy changed {0.0 if prev_acc is None else tru - prev_acc:+.3f} vs the previous window",
                inner_trust=float(p1[i]), outer_vote_conf=float(rec["vote_conf"][i])))
        out = dict(task=task, modality=modality, round=round_id, cycle=cycle,
                   factors=dict(reliability=round(rel, 4), truthfulness=round(tru, 4), adaptability=round(ada, 4), scalability=round(sca, 4)),
                   composite_grade=round(grade, 4), jev=jv, selective=sel, loo_flip_rate=dict(zip(NAMES, [round(f, 4) for f in flips])),
                   winner_share=dict(zip(NAMES, [round(float(x), 3) for x in winner_ct])), predictor_acc=dict(zip(NAMES, [round(float(x), 4) for x in pc])),
                   worst_class=dict(cls=worst[0], acc=None if worst[0] is None else round(worst[1], 3)), disagreement=round(div, 4),
                   feedback_advantage=adv, weights_after=[round(float(x), 3) for x in w_new])
        return out, w_new, transcripts

    # ---------------------------------------------------------- persistence
    def state(self):
        return dict(net=None if self.net is None else self.net.state_dict(), mean=self.mean, std=self.std, history=self.history)

    def load_state(self, s, d):
        self.mean, self.std, self.history = s["mean"], s["std"], s["history"]
        if s["net"] is not None:
            self.net = InnerNet(d).to(self.dev); self.net.load_state_dict(s["net"]); self.net.eval()
            self.opt = torch.optim.AdamW(self.net.parameters(), lr=1e-3, weight_decay=1e-2)
