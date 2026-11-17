"""Paired CPU probe: does a gradient-boosted-tree learner add anything the four NI predictors miss? Same split, same fit seed."""
import os, sys, time, json
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
import numpy as np, torch
import ni_outer
from ni_common import ROOT, seed_for, split_train_mask
from ni_data import load_task
from sklearn.ensemble import HistGradientBoostingClassifier
torch.set_num_threads(4)
ni_outer.ALGO = "v3"
tasks = sys.argv[1].split(","); rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 2; cap = 20000
L = ["| task | n_tr | D | NI v3 vote | HistGB alone | best single NI | mean(NI vote, HistGB) |", "|---|---|---|---|---|---|---|"]
for task in tasks:
    d = load_task(task)
    if d is None: L.append(f"| {task} | no data |"); continue
    if len(d["y"]) > cap:
        k = np.sort(np.random.RandomState(7).choice(len(d["y"]), cap, replace=False)); d = dict(d, X=d["X"][k], y=d["y"][k], gid=d["gid"][k])
    ob = ni_outer.OuterBrain(torch.device("cpu")); A = []; Bv = []; Cv = []; Dv = []; n_tr = 0
    for r in range(rounds):
        out = ob.run_round(task, d, seed_for(task, r, 1), seed_for(task, r, 2))
        if out is None: continue
        row = out[1]; A.append(row["acc_vote"]); Cv.append(max(row["acc_pred"].values())); n_tr = row["n_train"]
        m = split_train_mask(d["gid"], seed_for(task, r, 1)); tr, va = np.where(m)[0], np.where(~m)[0]
        g = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.08, early_stopping=True, random_state=0)
        g.fit(d["X"][tr], d["y"][tr]); Bv.append(float((g.predict(d["X"][va]) == d["y"][va]).mean()))
    L.append(f"| {task} | {n_tr} | {d['X'].shape[1]} | {np.mean(A):.4f} | {np.mean(Bv):.4f} | {np.mean(Cv):.4f} | - |")
    print(L[-1], flush=True)
open(os.path.join(ROOT, "PROBE_gbdt.md"), "a", encoding="utf-8").write(time.strftime("## %Y-%m-%d %H:%M\n") + "\n".join(L) + "\n\n")
