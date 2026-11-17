"""Paired offline A/B of outer-brain algorithm variants on CACHED features (no GPU, no scheduler involvement).

    python ni_probe.py --tasks enc/text/imdb,enc/graph/imdb_binary --algos v2,v3 --rounds 2 --cap 20000

Every variant sees the identical 70/30 grouped split and the identical fit seed, so differences are the algorithm, not the draw.
Large tasks are randomly sub-sampled to --cap rows (stated in the output) so the CPU run finishes in minutes.
Writes PROBE.md (appended per invocation, newest first is not guaranteed - read the timestamp).
"""
import os, sys, time, json, argparse
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
import numpy as np
import torch
import ni_outer
from ni_common import ROOT, seed_for
from ni_data import load_task


def run(task, algo, rounds, cap, dev):
    ni_outer.ALGO = algo
    d = load_task(task)
    if d is None:
        return None
    if len(d["y"]) > cap:                                   # same sub-sample for every variant (fixed seed)
        keep = np.sort(np.random.RandomState(7).choice(len(d["y"]), cap, replace=False))
        d = dict(d, X=d["X"][keep], y=d["y"][keep], gid=d["gid"][keep])
    ob = ni_outer.OuterBrain(dev)
    rows = []
    for r in range(rounds):
        out = ob.run_round(task, d, seed_for(task, r, 1), seed_for(task, r, 2))
        if out is None:
            continue
        rows.append(out[1])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True); ap.add_argument("--algos", default="v2,v3")
    ap.add_argument("--rounds", type=int, default=2); ap.add_argument("--cap", type=int, default=20000)
    ap.add_argument("--threads", type=int, default=4); ap.add_argument("--out", default="PROBE.md")
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    algos = a.algos.split(",")
    L = [f"## probe {time.strftime('%Y-%m-%d %H:%M')}  algos={a.algos} rounds={a.rounds} cap={a.cap} device={dev.type}", "",
         "| task | algo | n_tr | vote acc | balanced acc | AUROC | NLL | Logic | Pattern | Verifier | Explor. | sec/round |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for task in a.tasks.split(","):
        for algo in algos:
            t0 = time.time()
            try:
                rows = run(task, algo, a.rounds, a.cap, dev)
            except Exception as e:
                import traceback; traceback.print_exc()
                L.append(f"| {task} | {algo} | ERROR {repr(e)[:80]} |"); continue
            if not rows:
                L.append(f"| {task} | {algo} | no data |"); continue
            m = lambda k: np.mean([r[k] for r in rows if r.get(k) is not None]) if any(r.get(k) is not None for r in rows) else float("nan")
            pn = lambda n: np.mean([r["acc_pred"][n] for r in rows])
            L.append(f"| {task} | {algo} | {rows[0]['n_train']} | {m('acc_vote'):.4f} | {m('acc_bal'):.4f} | {m('auroc'):.4f} | {m('nll'):.4f} | "
                     f"{pn(ni_outer.NAMES[0]):.3f} | {pn(ni_outer.NAMES[1]):.3f} | {pn(ni_outer.NAMES[2]):.3f} | {pn(ni_outer.NAMES[3]):.3f} | {(time.time() - t0) / a.rounds:.1f} |")
            if algo == "v3" and rows[-1].get("diag"):
                L.append(f"|  | v3 diag | | {json.dumps(rows[-1]['diag'])} |")
            print(L[-1] if not L[-1].startswith("|  |") else L[-2], flush=True)
    txt = "\n".join(L) + "\n\n"
    with open(os.path.join(ROOT, a.out), "a", encoding="utf-8") as f:
        f.write(txt)
    print(txt)


if __name__ == "__main__":
    main()
