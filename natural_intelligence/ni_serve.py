"""MANAGER GATE: the NI brain as a trust check in front of an agent's next step.

The manager (Hojaiga, or any agent such as an opencode/Claude-style coding agent) asks BEFORE acting:

    POST /trust    {"app": "calculator", "goal": "click Scientific notation", "action": "click:Scientific notation"}
      -> {"p_success": 0.31, "decision": "verify_first", "trust": 0.58, "signals": {...}, "why": [...], "model": {...}}
    POST /outcome  {"app": ..., "goal": ..., "action": ..., "verdict": "PASS"|"FAIL", "evidence": "..."}   (the gate learns from it)
    GET  /status   what the gate was trained on, how it did out-of-fold, when it last retrained

decision is one of
    proceed      calibrated p_success is high AND the four predictors agree AND the case is not far from anything seen
    verify_first the gate is unsure or the predictors disagree: run the manager's own verifier / ask for a confirmation first
    ask_human    p_success is low, or the case is out-of-distribution (never seen anything like it): do not act alone
The proceed threshold is NOT a constant: it is the smallest probability at which out-of-fold precision reached the target on this
gate's own data; if that never happens the gate never says "proceed" (it says what it can honestly say).

Data it learns from (real, from the manager's own runs):   hojaiga_outcome_ledger.json  (per app/goal PASS/FAIL, 143 goals at the
time of writing, 105 FAIL / 38 PASS)  +  everything POSTed to /outcome (data_user/manager/outcomes.jsonl).
Honest limit: 143 records is small. `python ni_serve.py --evaluate` prints the out-of-fold numbers against the base-rate baselines;
do not trust the gate's "proceed" beyond what that table shows.

    python ni_serve.py --evaluate            # cross-validated numbers, no server
    python ni_serve.py --serve [--port 8765] # loopback server, retrains in the background every --retrain-every new outcomes
"""
import os, sys, json, time, hashlib, threading, argparse, math
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")        # the gate is small; it never competes with training for the GPU
import numpy as np
import torch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ni_common import ROOT, log, set_logfile
import ni_outer

LEDGER = os.environ.get("HOJAIGA_OUTCOME_LEDGER", r"D:\new_automation\hojaiga_outcome_ledger.json")
STORE = os.path.join(ROOT, "data_user", "manager"); os.makedirs(STORE, exist_ok=True)
OUTCOMES = os.path.join(STORE, "outcomes.jsonl")
MODEL_F = os.path.join(STORE, "gate_status.json")
dev = torch.device("cpu")


# ------------------------------------------------------------------------------------------------ data
def fp(app, goal):
    return hashlib.md5(f"{app}|{goal}".lower().encode()).hexdigest()[:12]


def load_records():
    """-> list of dict(app, goal, action, y(1=PASS,0=FAIL), key, src). One record per (app, goal)."""
    recs = {}
    try:
        with open(LEDGER, encoding="utf-8") as f:
            d = json.load(f)
        for app, goals in d.items():
            if not isinstance(goals, dict):
                continue
            for gid, r in goals.items():
                if r.get("last_verdict") in ("PASS", "FAIL"):
                    recs[fp(app, r.get("goal", gid))] = dict(app=app, goal=r.get("goal", gid), action="", y=int(r["last_verdict"] == "PASS"),
                                                              key=fp(app, r.get("goal", gid)), src="ledger")
    except Exception as e:
        log("[gate] ledger unreadable:", repr(e)[:100])
    if os.path.exists(OUTCOMES):
        with open(OUTCOMES, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("verdict") in ("PASS", "FAIL"):
                    k = fp(r.get("app", ""), r.get("goal", ""))
                    recs[k] = dict(app=r.get("app", ""), goal=r.get("goal", ""), action=r.get("action", ""), y=int(r["verdict"] == "PASS"), key=k, src="posted")
    return list(recs.values())


_ENC = {}


def embed(texts):
    """Frozen MiniLM sentence embedding (same encoder the text datasets use), CPU, cached by text."""
    import transformers as T
    import torch.nn.functional as TF
    md = os.path.join(ROOT, "models_hf", "all-MiniLM-L6-v2")
    if "m" not in _ENC:
        _ENC["tok"] = T.AutoTokenizer.from_pretrained(md); _ENC["m"] = T.AutoModel.from_pretrained(md).eval()
    out = []
    todo = [t for t in texts if t not in _ENC.setdefault("cache", {})]
    for i in range(0, len(todo), 64):
        b = todo[i:i + 64]
        t = _ENC["tok"](b, padding=True, truncation=True, max_length=128, return_tensors="pt")
        with torch.no_grad():
            h = _ENC["m"](**t).last_hidden_state
        mk = t["attention_mask"].unsqueeze(-1).float()
        e = TF.normalize((h * mk).sum(1) / mk.sum(1), dim=1).numpy()
        for s, v in zip(b, e):
            _ENC["cache"][s] = v
    return np.stack([_ENC["cache"][t] for t in texts]).astype(np.float32)


def text_of(r):
    return f"{r['app']}: {r['goal']}" + (f" | {r['action']}" if r.get("action") else "")


def history_feats(recs, tr_idx, q_app, q_goal_emb, E, y, exclude=None):
    """Numeric history features for one query computed ONLY from training records (so a record never sees its own label):
    app pass rate (Laplace-smoothed), log app count, nearest-training-goal similarity and the pass rate of its 5 nearest goals."""
    idx = np.array([i for i in tr_idx if i != exclude])
    if len(idx) == 0:
        return np.array([0.5, 0.0, 0.0, 0.5], np.float32)
    same = [i for i in idx if recs[i]["app"] == q_app]
    rate = (sum(y[i] for i in same) + 1) / (len(same) + 2)
    sims = E[idx] @ q_goal_emb
    top = np.argsort(-sims)[:5]
    return np.array([rate, math.log1p(len(same)), float(sims[top[0]]), float(y[idx[top]].mean())], np.float32)


def featurize(recs, tr_idx, q_idx_list, E, y, loo=False):
    return np.stack([np.concatenate([E[i], history_feats(recs, tr_idx, recs[i]["app"], E[i], E, y, exclude=i if loo else None)]) for i in q_idx_list])


# ------------------------------------------------------------------------------------------------ model
class Gate:
    def __init__(self):
        self.ok = False
        self.status = {}

    def fit(self, recs, E, y, tr_idx, seed=0):
        Xtr = featurize(recs, tr_idx, tr_idx, E, y, loo=True)                     # training rows: leave-one-out history, no label leak
        self.mu, self.sd = Xtr.mean(0, keepdims=True), Xtr.std(0, keepdims=True) + 1e-4
        Xt = torch.as_tensor((Xtr - self.mu) / self.sd, dtype=torch.float32); yt = torch.as_tensor(y[tr_idx], dtype=torch.long)
        self.preds, self.cal, self.diag = ni_outer.fit_v3(Xt, yt, 2, 1000 + seed, dev, use_lda=True)
        self.recs, self.E, self.y, self.tr_idx = recs, E, y, tr_idx
        self.Xtr_n = Xt
        sims = torch.nn.functional.normalize(Xt, dim=1) @ torch.nn.functional.normalize(Xt, dim=1).T
        sims.fill_diagonal_(-1)
        self.ref_maxsim = sims.max(1).values.numpy()                              # how close a training case is to its nearest other case
        self.ok = True

    def predict_raw(self, X):
        Xn = torch.as_tensor((X - self.mu) / self.sd, dtype=torch.float32)
        ctx = ni_outer.RoundContext(self.preds, None, None, Xn, None, 2, np.ones(4, np.float32), self.cal)
        Pr = ctx.probs(Xn)
        v = ctx.vote(Pr)
        return v[:, 1].numpy(), Pr[:, :, 1].T.numpy(), self.preds[2].last_maxsim.numpy()


def auroc(s, l):
    return ni_outer._auc(s, l)


def evaluate(recs, E, y, folds=5, seed=0):
    """Out-of-fold predictions with folds GROUPED by goal fingerprint (a goal never sits on both sides)."""
    keys = np.array([r["key"] for r in recs]); uk = np.unique(keys)
    rng = np.random.RandomState(seed); rng.shuffle(uk)
    fold_of = {k: i % folds for i, k in enumerate(uk)}; f = np.array([fold_of[k] for k in keys])
    oof = np.full(len(recs), np.nan); agree = np.full(len(recs), np.nan); msim = np.full(len(recs), np.nan); base_app = np.full(len(recs), np.nan)
    for k in range(folds):
        tr = np.where(f != k)[0]; te = np.where(f == k)[0]
        g = Gate(); g.fit(recs, E, y, tr, seed=k)
        Xte = featurize(recs, tr, te, E, y)
        p, pp, ms = g.predict_raw(Xte)
        oof[te] = p; msim[te] = ms
        agree[te] = (pp > 0.5).mean(1)
        for i in te:
            same = [j for j in tr if recs[j]["app"] == recs[i]["app"]]
            base_app[i] = (sum(y[j] for j in same) + 1) / (len(same) + 2)
    return oof, agree, msim, base_app


def pick_threshold(oof, y, target=0.9, min_n=8):
    """Smallest probability at which out-of-fold precision of 'p >= t' reaches the target with at least min_n cases (None if never)."""
    for t in np.unique(np.round(oof, 3)):
        sel = oof >= t
        if sel.sum() >= min_n and y[sel].mean() >= target:
            return float(t)
    return None


def report(recs, E, y):
    oof, agree, msim, base_app = evaluate(recs, E, y)
    maj = max(y.mean(), 1 - y.mean())
    L = [f"records {len(y)}  PASS {int(y.sum())}  FAIL {int((1 - y).sum())}  (majority-class accuracy {maj:.3f})",
         f"gate  : accuracy {((oof > 0.5) == y).mean():.3f}   AUROC {auroc(oof, y):.3f}",
         f"base  : per-app pass-rate AUROC {auroc(base_app, y):.3f}   (the thing the gate must beat to justify itself)"]
    t = pick_threshold(oof, y)
    L.append(f"proceed threshold (precision >= 0.9, >= 8 cases): {t if t is not None else 'none reached -> the gate would never say proceed'}")
    if t is not None:
        sel = oof >= t
        L.append(f"  at that threshold: {int(sel.sum())} of {len(y)} cases would 'proceed', {y[sel].mean():.3f} of them really passed")
    return "\n".join(L), oof, agree, msim, t


# ------------------------------------------------------------------------------------------------ server
class State:
    def __init__(self, retrain_every):
        self.lock = threading.Lock(); self.gate = None; self.thr = None; self.n_since = 0; self.retrain_every = retrain_every
        self.summary = "not trained yet"; self.trained_at = None; self.n_records = 0
        self.retrain()

    def retrain(self):
        recs = load_records()
        if len(recs) < 30 or len({r["y"] for r in recs}) < 2:
            self.summary = f"only {len(recs)} outcome records (need >= 30 with both PASS and FAIL): the gate abstains (ask_human) on everything"
            self.gate = None; self.n_records = len(recs); return
        E = embed([text_of(r) for r in recs]); y = np.array([r["y"] for r in recs])
        txt, oof, agree, msim, thr = report(recs, E, y)
        g = Gate(); g.fit(recs, E, y, np.arange(len(recs)))
        with self.lock:
            self.gate, self.thr, self.summary, self.trained_at, self.n_records, self.n_since = g, thr, txt, time.strftime("%Y-%m-%d %H:%M:%S"), len(recs), 0
            self.oof_lo = float(np.quantile(oof, 0.2)); self.ms_floor = float(np.quantile(g.ref_maxsim, 0.05))
        with open(MODEL_F, "w", encoding="utf-8") as f:
            json.dump(dict(trained_at=self.trained_at, n_records=self.n_records, summary=self.summary, proceed_threshold=thr, diag=g.diag), f, indent=1)
        log("[gate] trained on", len(recs), "records\n" + txt)

    def trust(self, q):
        app, goal, action = q.get("app", ""), q.get("goal", ""), q.get("action", "")
        with self.lock:
            g = self.gate
        if g is None:
            return dict(p_success=None, decision="ask_human", trust=0.0, why=[self.summary], model=dict(records=self.n_records))
        r = dict(app=app, goal=goal, action=action)
        e = embed([text_of(r)])[0]
        recs, E, y = g.recs, g.E, g.y
        x = np.concatenate([e, history_feats(recs, g.tr_idx, app, e, E, y)])[None]
        p, pp, ms = g.predict_raw(x)
        p = float(p[0]); pp = pp[0]; ms = float(ms[0]); agree = float((pp > 0.5).mean()); agree = max(agree, 1 - agree)
        ood = ms < self.ms_floor
        known_app = any(rr["app"] == app for rr in recs)
        why = []
        if not known_app:
            why.append(f"app '{app}' never seen in the training outcomes")
        if ood:
            why.append(f"nearest known case similarity {ms:.2f} is below the 5th percentile of the training cases ({self.ms_floor:.2f}): out of distribution")
        if agree < 0.75:
            why.append(f"predictors disagree ({', '.join(f'{n.split('_')[1]} {v:.2f}' for n, v in zip(ni_outer.NAMES, pp))})")
        if ood or not known_app:
            dec = "ask_human"
        elif p <= self.oof_lo:
            dec = "ask_human"; why.append(f"p_success {p:.2f} is in the lowest fifth of out-of-fold predictions")
        elif self.thr is not None and p >= self.thr and agree >= 0.75:
            dec = "proceed"; why.append(f"p_success {p:.2f} >= {self.thr:.2f}, the level at which out-of-fold precision reached 0.9")
        else:
            dec = "verify_first"
            if self.thr is None:
                why.append("the gate never reached precision 0.9 out-of-fold, so it does not authorise unverified action")
        trust = float(max(0.0, min(1.0, agree * (1 - ood) * (0.5 + abs(p - 0.5)))))
        return dict(p_success=round(p, 3), decision=dec, trust=round(trust, 3), why=why,
                    signals=dict(agreement=round(agree, 2), nearest_similarity=round(ms, 3), known_app=known_app,
                                 per_predictor={n.split("_")[1]: round(float(v), 3) for n, v in zip(ni_outer.NAMES, pp)}),
                    model=dict(records=self.n_records, trained_at=self.trained_at))

    def outcome(self, q):
        if q.get("verdict") not in ("PASS", "FAIL") or not q.get("app") or not q.get("goal"):
            return dict(ok=False, error="need app, goal and verdict PASS|FAIL")
        with open(OUTCOMES, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ts=time.strftime("%Y-%m-%d %H:%M:%S"), **{k: q.get(k, "") for k in ("app", "goal", "action", "verdict", "evidence")}), ensure_ascii=False) + "\n")
        self.n_since += 1
        if self.n_since >= self.retrain_every:
            threading.Thread(target=self.retrain, daemon=True).start()
        return dict(ok=True, pending_before_retrain=max(0, self.retrain_every - self.n_since))


def make_handler(st):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self):
            if self.path in ("/status", "/health"):
                self._send(200, dict(ok=True, trained_at=st.trained_at, records=st.n_records, proceed_threshold=st.thr, summary=st.summary))
            else:
                self._send(404, dict(error="GET /status, POST /trust, POST /outcome"))

        def do_POST(self):
            try:
                q = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/trust":
                    self._send(200, st.trust(q))
                elif self.path == "/outcome":
                    self._send(200, st.outcome(q))
                else:
                    self._send(404, dict(error="unknown path"))
            except Exception as e:
                self._send(500, dict(error=repr(e)[:200]))

        def log_message(self, *a):
            pass
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluate", action="store_true"); ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8765); ap.add_argument("--retrain-every", type=int, default=20)
    a = ap.parse_args()
    set_logfile(os.path.join(STORE, "gate_log.txt"))
    torch.set_num_threads(2)
    if a.evaluate:
        recs = load_records(); E = embed([text_of(r) for r in recs]); y = np.array([r["y"] for r in recs])
        txt = report(recs, E, y)[0]
        print(txt)
        with open(os.path.join(ROOT, "GATE_EVAL.md"), "w", encoding="utf-8") as f:
            f.write("# Manager gate: out-of-fold evaluation\n\n```\n" + txt + "\n```\n")
        return
    if a.serve:
        st = State(a.retrain_every)
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(st))
        log(f"[gate] serving on 127.0.0.1:{a.port}"); srv.serve_forever()


if __name__ == "__main__":
    main()
