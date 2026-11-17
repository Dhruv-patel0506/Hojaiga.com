"""Evaluate the manager trust gate on PUBLIC agent-run outcomes (nebius/SWE-agent-trajectories, pre-run information only),
and test honestly whether anything learned there transfers to the user's own manager ledger (different domain: expect little)."""
import os, sys, json, random, time, hashlib
import numpy as np, torch
torch.set_num_threads(6)
import ni_serve as S
from ni_common import ROOT
N_TASKS = int(sys.argv[1]) if len(sys.argv) > 1 else 2500
rows = [json.loads(l) for l in open(os.path.join(ROOT, "data_user", "agent", "swe_records.jsonl"), encoding="utf-8")]
by = {}
for r in rows: by.setdefault(r["goal"].split(":")[0], []).append(r)
ids = sorted(by); random.Random(1).shuffle(ids); keep = [r for i in ids[:N_TASKS] for r in by[i]]
recs = [dict(app=r["app"], goal=r["goal"], action=r["action"], y=int(r["verdict"] == "PASS"), key=S.fp(r["app"], r["goal"].split(":")[0]), src="swe") for r in keep]
y = np.array([r["y"] for r in recs])
t0 = time.time(); E = S.embed([S.text_of(r) for r in recs]); print(f"embedded {len(recs)} in {time.time()-t0:.0f}s", flush=True)
txt, oof, agree, msim, thr = S.report(recs, E, y)
# trivial baselines the gate must beat on this data: per-agent (model) pass rate and per-repo pass rate
def rate_auc(field):
    keys = np.array([r[field] for r in recs]); g = np.array([r["key"] for r in recs]); uk = np.unique(g); rng = np.random.RandomState(0); rng.shuffle(uk)
    fold = {k: i % 5 for i, k in enumerate(uk)}; f = np.array([fold[k] for k in g]); s = np.zeros(len(recs))
    for k in range(5):
        tr = f != k
        for v in np.unique(keys[~tr]):
            m = (keys == v) & tr; s[(keys == v) & ~tr] = (y[m].sum() + 1) / (m.sum() + 2) if m.any() else y[tr].mean()
    return S.auroc(s, y)
L = ["# Manager gate on public agent outcomes (SWE-agent trajectories)", time.strftime("%Y-%m-%d %H:%M"), "",
     f"tasks used {len(set(r['key'] for r in recs))}, runs {len(recs)}", "", "```", txt, "```", "",
     f"baseline per-agent pass-rate AUROC {rate_auc('action'):.3f}   per-repo pass-rate AUROC {rate_auc('app'):.3f}", ""]
# transfer: gate fitted on all public runs, scored on the user's own ledger (143 real manager outcomes)
own = S.load_records()
if own:
    Eo = S.embed([S.text_of(r) for r in own]); yo = np.array([r["y"] for r in own])
    g = S.Gate(); g.fit(recs, E, y, np.arange(len(recs)))
    Xo = np.stack([np.concatenate([Eo[i], S.history_feats(recs, np.arange(len(recs)), own[i]["app"], Eo[i], E, y)]) for i in range(len(own))])
    p, _, _ = g.predict_raw(Xo)
    L += [f"transfer SWE -> user's manager ledger ({len(own)} records, {int(yo.sum())} PASS): AUROC {S.auroc(p, yo):.3f}  (0.5 = no transfer)"]
open(os.path.join(ROOT, "GATE_PUBLIC.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
