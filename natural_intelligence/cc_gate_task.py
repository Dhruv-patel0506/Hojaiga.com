"""Gate 1, task level: does NI predict outcomes that matter more than "did this one tool call error"?

T2 downstream  For every file edit (Edit/Write/NotebookEdit): does the NEXT shell command in the same turn fail?
               Predicted at the moment of the edit, from what was known then.
T3 turn        Will the human correct or interrupt this turn (cc_turns.py)? Scored at the end of the turn, before the
               human has reacted, from the turn's actions. This is the "should a human review this?" signal.

Same time split as cc_gate.py (oldest 75% of actions = train window). Baselines are what a simple rule would use.
Output: CC_GATE1_TASK.md
"""
import os, sys, time, collections, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import cc_core, cc_turns
from cc_gate import build, err_block, fit_ni, predict_ni, metrics, texts
import ni_outer

OUT = os.path.join(cc_core.ROOT, "CC_GATE1_TASK.md")
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")
SHELL = ("Bash", "PowerShell")


def boot(sa, sb, y, B=1000, seed=0):
    rng = np.random.RandomState(seed); d = []
    for _ in range(B):
        i = rng.randint(0, len(y), len(y))
        if 0 < y[i].sum() < len(i):
            d.append(ni_outer._auc(sa[i], y[i]) - ni_outer._auc(sb[i], y[i]))
    d = np.array(d)
    return d.mean(), np.percentile(d, 2.5), np.percentile(d, 97.5), (d > 0).mean()


def main():
    t0 = time.time()
    recs = [r for r in sorted(cc_core.load_actions().values(), key=lambda r: r["ts"]) if r["outcome"] != "unknown"]
    n = len(recs); cut = int(0.75 * n); cut_ts = recs[cut]["ts"]
    tools = [t for t, _ in collections.Counter(r["tool"] for r in recs[:cut]).most_common(14)]
    models = [m for m, _ in collections.Counter(r["model"] for r in recs[:cut]).most_common(4)]
    Xh, _ = build(recs, tools, models); ctx = build.err_ctx
    ta, _ = texts(recs); Ea = cc_core.embed(ta); Xe = err_block(Ea, ctx); cc_core.save_cache()
    X = np.concatenate([Xh, Ea, Xe], 1)
    fail = np.array([int(r["outcome"] != "ok") for r in recs])
    from sklearn.ensemble import HistGradientBoostingClassifier
    L = ["# Gate 1, task level", "", f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `cc_gate_task.py`. Train window = actions before "
         f"{time.strftime('%Y-%m-%d', time.localtime(cut_ts))}; test window = after. NI = outer brain on history features + action text + recent-error features.", ""]

    # ---------------------------------------------------------------- T2 downstream
    by_turn = collections.defaultdict(list)
    for i, r in enumerate(recs):
        by_turn[(r["session"], r.get("turn"))].append(i)
    D, yd, tj = [], [], []
    for idx in by_turn.values():
        for k, i in enumerate(idx):
            if recs[i]["tool"] in EDIT_TOOLS and recs[i]["outcome"] == "ok":
                nxt = next((j for j in idx[k + 1:] if recs[j]["tool"] in SHELL), None)
                if nxt is not None:
                    D.append(i); yd.append(fail[nxt]); tj.append(recs[nxt]["ts"])
    o = np.argsort([recs[i]["ts"] for i in D]); D = np.array(D)[o]; yd = np.array(yd)[o]; tj = np.array(tj)[o]
    # baseline: downstream failure rate so far for this file type, updated only once the later run has happened
    rate, pend, base = collections.defaultdict(lambda: [0, 0]), [], []
    allr = [0, 0]
    for i, y_, t_ in zip(D, yd, tj):
        ts = recs[i]["ts"]
        for p in [p for p in pend if p[0] < ts]:
            rate[p[1]][0] += 1; rate[p[1]][1] += p[2]; allr[0] += 1; allr[1] += p[2]; pend.remove(p)
        ext = os.path.splitext(recs[i].get("target", ""))[1].lower()
        p0 = (allr[1] + 1) / (allr[0] + 2); c = rate[ext]
        base.append((c[1] + 5 * p0) / (c[0] + 5)); pend.append((t_, ext, y_))
    base = np.array(base)
    trm = np.array([recs[i]["ts"] < cut_ts for i in D]); tem = ~trm
    L += ["## T2 - after an edit, will the next run in the same turn fail?", "",
          f"Edits followed by a shell command in the same turn: {len(D)} (train {trm.sum()}, test {tem.sum()}); "
          f"next run failed: {yd.sum()} ({yd.mean():.1%}), test failures {yd[tem].sum()}.", ""]
    res2 = {}
    if yd[trm].sum() >= 10 and 0 < yd[tem].sum() < tem.sum():
        res2["B1 failure rate of the next run after edits to this file type, so far"] = base[tem]
        h = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, class_weight="balanced", random_state=0).fit(Xh[D[trm]], yd[trm])
        res2["B2 gradient-boosted trees, history features"] = h.predict_proba(Xh[D[tem]])[:, 1]
        m = fit_ni(X[D[trm]], 1 - yd[trm]); res2["NI"] = predict_ni(m, X[D[tem]])
        L += ["| Method | AUROC | AUPRC | R@10% |", "|---|---|---|---|"]
        for k, s in res2.items():
            mm = metrics(s, yd[tem]); L.append(f"| {k} | {mm['auroc']:.3f} | {mm['auprc']:.3f} | {mm['r@10%']:.2f} |")
        bb = max((k for k in res2 if k != "NI"), key=lambda k: ni_outer._auc(res2[k], yd[tem]))
        d = boot(res2["NI"], res2[bb], yd[tem])
        L += ["", f"NI minus best baseline ({bb}) AUROC: {d[0]:+.3f} [95% {d[1]:+.3f}, {d[2]:+.3f}], P(NI better) {d[3]:.0%}.", ""]
    else:
        L += ["Too few failures in one of the windows to evaluate.", ""]

    # ---------------------------------------------------------------- T3 turn outcome
    out, rep = cc_turns.turn_outcomes(recs)
    L += ["## T3 - will the human correct or interrupt this turn?", "",
          f"Correction classifier (fallback for unlabelled messages only; 5-fold grouped CV on {rep['n']} teacher labels): "
          f"AUROC {rep['cv_auroc']:.3f}, accuracy {rep['cv_accuracy']:.3f} vs {rep['majority_accuracy']:.3f} for always-'no', "
          f"precision {rep['cv_precision']:.2f}, recall {rep['cv_recall']:.2f}. It is weak, so every turn evaluated here uses a teacher "
          "label, an interrupt or a rejection.", ""]
    turns = {}
    for key, idx in by_turn.items():
        t = key[1]
        if t in out and out[t][1] != "classifier":
            turns[t] = (idx, out[t][0])
    tr_t = [t for t, (idx, _) in turns.items() if recs[idx[0]]["ts"] < cut_ts]
    te_t = [t for t, (idx, _) in turns.items() if recs[idx[0]]["ts"] >= cut_ts]
    yt_tr = np.array([turns[t][1] for t in tr_t]); yt_te = np.array([turns[t][1] for t in te_t])
    L += [f"Turns with a known outcome: {len(turns)} (train {len(tr_t)} with {yt_tr.sum()} bad, test {len(te_t)} with {yt_te.sum()} bad).", ""]

    def agg(t):
        idx = turns[t][0]; f = fail[idx]; dur = recs[idx[-1]]["ts"] - recs[idx[0]]["ts"]
        return [np.log1p(len(idx)), f.sum(), f.mean(), np.log1p(max(dur, 0)), len({recs[i]["tool"] for i in idx}), fail[idx[-3:]].sum()]
    A_tr = np.array([agg(t) for t in tr_t]); A_te = np.array([agg(t) for t in te_t])
    res3 = {}
    if yt_tr.sum() >= 8 and 0 < yt_te.sum() < len(yt_te):
        res3["B1 number of actions in the turn"] = A_te[:, 0]
        res3["B2 number of failed actions in the turn"] = A_te[:, 1] + 1e-3 * A_te[:, 0]
        res3["B3 share of failed actions in the turn"] = A_te[:, 2]
        h = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, max_depth=3, class_weight="balanced", random_state=0).fit(A_tr, yt_tr)
        res3["B4 gradient-boosted trees on turn summaries"] = h.predict_proba(A_te)[:, 1]
        ai = np.concatenate([turns[t][0] for t in tr_t]); ay = np.concatenate([[turns[t][1]] * len(turns[t][0]) for t in tr_t])
        m = fit_ni(X[ai], 1 - ay)
        r_te = [predict_ni(m, X[turns[t][0]]) for t in te_t]
        res3["NI, riskiest action in the turn"] = np.array([r.max() for r in r_te])
        res3["NI, mean over the turn's actions"] = np.array([r.mean() for r in r_te])
        L += ["| Method | AUROC | AUPRC | Bad turns in riskiest 20% |", "|---|---|---|---|"]
        for k, s in res3.items():
            mm = metrics(s, yt_te); o_ = np.argsort(-s)[:max(1, int(0.2 * len(s)))]
            L.append(f"| {k} | {mm['auroc']:.3f} | {mm['auprc']:.3f} | {yt_te[o_].sum()} of {yt_te.sum()} |")
        bn = max((k for k in res3 if k.startswith("NI")), key=lambda k: ni_outer._auc(res3[k], yt_te))
        bb = max((k for k in res3 if k.startswith("B")), key=lambda k: ni_outer._auc(res3[k], yt_te))
        d = boot(res3[bn], res3[bb], yt_te)
        L += ["", f"{bn} minus best baseline ({bb}) AUROC: {d[0]:+.3f} [95% {d[1]:+.3f}, {d[2]:+.3f}], P(NI better) {d[3]:.0%}.", ""]
    else:
        L += ["Too few bad turns in one of the windows to evaluate.", ""]
    L += ["## Honest limits", "",
          "- Turn labels come from one teacher (Claude) reading the first ~170 characters of each follow-up message, on one person's sessions. "
          "They have not been checked by the person.",
          "- The test windows are small, so the bootstrap intervals are wide; treat these as direction, not proof.",
          f"- Runtime {time.time() - t0:.0f} s."]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
