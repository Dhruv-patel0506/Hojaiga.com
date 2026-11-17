"""Cross-run comparison: for every dataset, hand-built features vs frozen-encoder features, and algorithm v1 vs v2.

    python ni_compare.py            # writes COMPARE.md and prints it

Numbers are the mean of the LAST 30 rounds of every run that trained that (dataset, feature kind, algorithm), measured against
dataset ground-truth labels on the held-out 30% window. 'rounds' is the number of rounds pooled. Rounds from killed or crashed runs
are included (their metrics.jsonl is written after every round), which is why the counts differ.
"""
import os, json, glob, collections
import numpy as np
from ni_common import RUNS, ROOT

LAST = 30
NAMES = ["Predictor_Logic", "Predictor_Pattern", "Predictor_Verifier", "Predictor_Exploratory"]


def load():
    groups = collections.defaultdict(list)          # (dataset, kind, algo) -> [(run, row)]
    for mf in glob.glob(os.path.join(RUNS, "*", "metrics.jsonl")):
        per_task = collections.defaultdict(list)
        try:
            with open(mf, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    per_task[r["task"]].append(r)
        except Exception:
            continue
        run = os.path.basename(os.path.dirname(mf))
        for task, rows in per_task.items():
            parts = task.split("/")
            if parts[0] in ("enc", "hand", "enc2"):
                kind, ds = parts[0], "/".join(parts[1:])
            else:
                kind, ds = "legacy-hand", task          # overnight / restart runs on shard features (also hand-built)
            for r in rows[-LAST:]:
                algo = r["outer"].get("algo", "v1")
                groups[(ds, kind, algo)].append((run, r))
    return groups


def mean(xs):
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else None


def f(x, nd=3):
    return "-" if x is None else f"{x:.{nd}f}"


def summarize(rows):
    o = [r["outer"] for _, r in rows]
    inn = [r["inner"]["selective"] for _, r in rows if r.get("inner") and (r["inner"].get("selective") or {}).get("inner_auc") is not None]
    return dict(n=len(rows), runs=len({a for a, _ in rows}), acc=mean([x["acc_vote"] for x in o]), uni=mean([x["acc_uniform"] for x in o]),
                bal=mean([x.get("acc_bal") for x in o]), auroc=mean([x.get("auroc") for x in o]), maj=mean([x["chance"] for x in o]),
                logic=mean([x["acc_pred"].get(NAMES[0]) for x in o]), best=mean([max(x["acc_pred"].values()) for x in o]),
                iauc=mean([s.get("inner_auc") for s in inn]), cauc=mean([s.get("voteconf_auc") for s in inn]))


def main():
    G = load(); ds_all = sorted({k[0] for k in G})
    L = ["# NI comparison: feature kind and algorithm", "",
         f"Mean of the last {LAST} rounds per run, against ground-truth labels (held-out 30% window). hand = old hand-built features, "
         "enc = frozen pretrained encoder (graphs: Weisfeiler-Lehman fingerprint). v1 = original algorithm, v2 = LDA Logic + class weights + wider MLP, v3 = v2 + calibration slice (per-predictor temperature, log-loss stack weights, class-prior shift on imbalanced tasks) + tuned Verifier + multi-scale Exploratory + seed-ensembled Pattern. v4 = v3 + a boosted-tree learner in the Exploratory slot that joins only when it beats all four predictors on the calibration slice. enc2 = stronger frozen encoders (bge-base text, dinov2-base image, dinov2+VideoMAE+X-CLIP video, AST+Whisper+CLAP audio, rich spectral/WL graph features).", "",
         "| dataset | variant | rounds | vote acc | uniform acc | balanced acc | AUROC | Logic | best single | majority | inner AUC | vote-conf AUC |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    best = {}
    for ds in ds_all:
        for kind in ("legacy-hand", "hand", "enc", "enc2"):
            for algo in ("v1", "v2", "v3", "v4"):
                rows = G.get((ds, kind, algo))
                if not rows:
                    continue
                s = summarize(rows); best.setdefault(ds, {})[(kind, algo)] = s
                L.append(f"| {ds} | {kind} {algo} | {s['n']} ({s['runs']} run{'s' if s['runs'] > 1 else ''}) | {f(s['acc'])} | {f(s['uni'])} | {f(s['bal'])} | {f(s['auroc'])} | "
                         f"{f(s['logic'])} | {f(s['best'])} | {f(s['maj'])} | {f(s['iauc'])} | {f(s['cauc'])} |")
    L += ["", "## Gains (vote accuracy, points)", "", "| dataset | hand -> enc | enc v1 -> v2 | enc v2 -> v3 | enc v3 -> v4 | enc -> enc2 (best algo) | note |", "|---|---|---|---|---|---|---|"]
    for ds, d in best.items():
        h = d.get(("hand", "v1")) or d.get(("legacy-hand", "v1")) or d.get(("hand", "v2"))
        e1, e2 = d.get(("enc", "v1")), d.get(("enc", "v2"))
        e = e2 or e1
        he = None if not (h and e) else 100 * (e["acc"] - h["acc"])
        v = None if not (e1 and e2) else 100 * (e2["acc"] - e1["acc"])
        note = ""
        if h and h["acc"] is not None and h["maj"] is not None and h["acc"] - h["maj"] < 0.01:
            note = "hand features at majority-class level (accuracy alone hides this; see balanced acc / AUROC)"
        e4 = d.get(("enc", "v4")); u4 = None if not (e4 and d.get(("enc", "v3"))) else 100 * (e4["acc"] - d[("enc", "v3")]["acc"])
        e3 = d.get(("enc", "v3")); w = None if not (e2 and e3) else 100 * (e3["acc"] - e2["acc"])
        b = lambda kind: d.get((kind, "v4")) or d.get((kind, "v3")) or d.get((kind, "v2")) or d.get((kind, "v1"))
        q = None if not (b("enc") and b("enc2")) else 100 * (b("enc2")["acc"] - b("enc")["acc"])
        L.append(f"| {ds} | {'-' if he is None else f'{he:+.1f}'} | {'-' if v is None else f'{v:+.1f}'} | {'-' if w is None else f'{w:+.1f}'} | {'-' if u4 is None else f'{u4:+.1f}'} | {'-' if q is None else f'{q:+.1f}'} | {note} |")
    L += ["", "Read honestly: runs differ in how many rounds they got (several were killed by GPU faults), so compare the tables, not single numbers; "
          "'enc v1 -> v2' is only filled where both algorithms trained the same dataset."]
    out = "\n".join(L) + "\n"
    with open(os.path.join(ROOT, "COMPARE.md"), "w", encoding="utf-8") as fh:
        fh.write(out)
    print(out)


if __name__ == "__main__":
    main()
