"""Gate 1 evaluator: does NI predict which agent actions will fail or be refused, BEFORE they run, better than simple baselines?

Data   : data_user/cc/actions.jsonl (cc_harvest.py), real Claude Code tool calls with their real outcomes.
Split  : by TIME. Models are fitted on the oldest 75% of actions and frozen; they are scored on the newest 25%, exactly as a
         gate deployed at the cut date would have been. History features keep updating through the test window (a live gate
         knows earlier outcomes too), but never with the outcome of the action being scored.
Target : fail = any outcome other than ok (exit code, tool error, blocked by harness/classifier, rejected by the human).
Output : CC_GATE1.md (results), data_user/cc/cc_model.pt (with --save: a model refitted on ALL actions, for cc_serve.py).
"""
import os, sys, json, time, argparse, collections
os.environ.setdefault("NI_ALGO", "v4")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import torch
import cc_core
import ni_outer

DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")
REPORT = os.path.join(cc_core.ROOT, "CC_GATE1.md")
MODEL_F = os.path.join(cc_core.CC_DIR, "cc_model.pt")


def build(recs, tools, models):
    """Numeric history features for every record, in time order, online (leak-free)."""
    H = cc_core.History(tools, models); X = []; ctx = []
    for r in recs:
        X.append(H.features(r)); ctx.append(H.err_ctx(r)); H.update(r)
    build.err_ctx = ctx                       # (last failed action text, its error) per record, known before the record ran
    return np.stack(X), H


def err_block(Ea, ctx):
    has = np.array([float(bool(a)) for a, _ in ctx], np.float32)
    El = cc_core.embed([a or "(none)" for a, _ in ctx]); Ee = cc_core.embed([e or "(none)" for _, e in ctx])
    return cc_core.err_cos(Ea, El, Ee, has)


def metrics(risk, fail):
    risk = np.asarray(risk, float); fail = np.asarray(fail, int)
    o = np.argsort(-risk); n = len(risk); P = fail.sum()
    out = dict(auroc=ni_outer._auc(risk, fail))
    prec, tp = [], 0
    for i, j in enumerate(o):                      # average precision (area under precision-recall)
        if fail[j]:
            tp += 1; prec.append(tp / (i + 1))
    out["auprc"] = float(np.mean(prec)) if prec else 0.0
    for q in (0.02, 0.05, 0.10):
        k = max(1, int(round(q * n))); top = fail[o[:k]]
        out[f"p@{int(q * 100)}%"] = float(top.mean()); out[f"r@{int(q * 100)}%"] = float(top.sum() / max(P, 1))
    half = o[n // 2:]                              # the safest half by predicted risk
    out["fail_rate_safest_half"] = float(fail[half].mean())
    return out


def fit_ni(Xtr, ytr, seed=0):
    mu, sd = Xtr.mean(0, keepdims=True), Xtr.std(0, keepdims=True) + 1e-4
    Xt = torch.as_tensor((Xtr - mu) / sd, dtype=torch.float32, device=DEV); yt = torch.as_tensor(ytr, dtype=torch.long, device=DEV)
    preds, cal, diag = ni_outer.fit_v3(Xt, yt, 2, 4242 + seed, DEV, use_lda=True)
    return dict(preds=preds, cal=cal, diag=diag, mu=mu, sd=sd)


def predict_ni(m, X):
    Xn = torch.as_tensor((X - m["mu"]) / m["sd"], dtype=torch.float32, device=DEV)
    ctx = ni_outer.RoundContext(m["preds"], None, None, Xn, None, 2, np.ones(4, np.float32), m["cal"])
    out = []
    for i in range(0, len(Xn), 4096):
        Pr = ctx.probs(Xn[i:i + 4096]); out.append(ctx.vote(Pr)[:, 0].float().cpu().numpy())   # class 0 = fail
    return np.concatenate(out)


def texts(recs):
    return [r["text"] for r in recs], [(r.get("plan") or "(no stated plan)") for r in recs]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--save", action="store_true"); ap.add_argument("--cut", type=float, default=0.75)
    ap.add_argument("--save-only", default=None, help="skip the evaluation; refit this variant on all actions and save it")
    a = ap.parse_args()
    if a.save_only:
        return save_only(a.save_only)
    t0 = time.time()
    recs = [r for r in sorted(cc_core.load_actions().values(), key=lambda r: r["ts"]) if r["outcome"] != "unknown"]
    n = len(recs); cut = int(a.cut * n)
    tr_recs = recs[:cut]
    tools = [t for t, _ in collections.Counter(r["tool"] for r in tr_recs).most_common(14)]
    models = [m for m, _ in collections.Counter(r["model"] for r in tr_recs).most_common(4)]
    Xh, H = build(recs, tools, models)
    fail = np.array([int(r["outcome"] != "ok") for r in recs]); y = 1 - fail          # y: 1 = ok (gate convention: class 1 = pass)
    ta, tp = texts(recs)
    Ea = cc_core.embed(ta); Ep = cc_core.embed(tp); cc_core.save_cache()
    print(f"[gate1] {n} actions, {fail.sum()} fails; features {Xh.shape[1]} numeric + 2x384 text; built in {time.time() - t0:.0f}s", flush=True)
    tr, te = np.arange(cut), np.arange(cut, n)
    names = H.names(); ix = {k: i for i, k in enumerate(names)}
    res = collections.OrderedDict(); SC = {}

    def add(name, score):
        SC[name] = np.asarray(score, float); res[name] = metrics(score, fail[te])
    add("B0 everything passes (chance)", np.zeros(len(te)) + np.random.RandomState(0).rand(len(te)) * 1e-9)
    add("B1 failure rate of this tool so far", Xh[te, ix["g_tool_fail"]])
    add("B2 failure rate of this kind of action so far", Xh[te, ix["g_head_fail"]])
    add("B3 failure rate of this exact action so far", Xh[te, ix["g_key_fail"]])
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    mu, sd = Xh[tr].mean(0), Xh[tr].std(0) + 1e-4
    lr = LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5).fit((Xh[tr] - mu) / sd, fail[tr])
    add("B4 logistic regression, history features", lr.predict_proba((Xh[te] - mu) / sd)[:, 1])
    hgb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, class_weight="balanced", random_state=0).fit(Xh[tr], fail[tr])
    add("B5 gradient-boosted trees, history features", hgb.predict_proba(Xh[te])[:, 1])
    Xe = err_block(Ea, build.err_ctx); cc_core.save_cache()
    variants = {"NI history features only": Xh,
                "NI + action text": np.concatenate([Xh, Ea], 1),
                # "agent's plan text" variant dropped: it lost in both earlier runs (AUROC 0.774, 0.760) and cost 6 min per fit
                "NI + action text + recent errors": np.concatenate([Xh, Ea, Xe], 1)}
    diags = {}
    for name, X in variants.items():
        t1 = time.time(); m = fit_ni(X[tr], y[tr])
        add(name, predict_ni(m, X[te])); res[name]["fit_s"] = round(time.time() - t1, 1)
        diags[name] = {k: m["diag"].get(k) for k in ("n_fit", "n_cal", "D", "imbalance", "stack", "T", "tree_mix", "prior_shift") if k in m["diag"]}
        print(f"[gate1] {name}: AUROC {res[name]['auroc']:.3f}  ({res[name]['fit_s']}s)", flush=True)
    # the NI variant with the best AUROC (the stated criterion) is analysed below and is the one served live
    name = max((k for k in res if k.startswith("NI")), key=lambda k: res[k]["auroc"]); X = variants[name]
    boot = paired_bootstrap(SC, fail[te], name, [k for k in res if k.startswith("B") and not k.startswith("B0")])
    np.savez(os.path.join(cc_core.CC_DIR, "gate1_test_scores.npz"), fail=fail[te], **{k: v for k, v in SC.items()})
    risk = SC[name]; k = int(0.05 * len(te)); top = set(te[np.argsort(-risk)[:k]].tolist())
    by = collections.defaultdict(lambda: [0, 0])
    for i in te:
        if fail[i]:
            by[recs[i]["outcome"]][0] += 1; by[recs[i]["outcome"]][1] += int(i in top)
    per_tool = {}
    for t in tools[:8]:
        sel = [j for j, i in enumerate(te) if recs[i]["tool"] == t]
        if sum(fail[te][sel]) >= 5:
            per_tool[t] = (len(sel), int(fail[te][sel].sum()), ni_outer._auc(risk[sel], fail[te][sel]))
    write_report(recs, cut, fail, res, diags, by, per_tool, time.time() - t0, name, boot)
    if a.save:
        save_model(variants[name], y, tools, models, name, n)


def save_model(X, y, tools, models, name, n):
    t1 = time.time(); mf = fit_ni(X, y)
    q = np.quantile(predict_ni(mf, X), np.linspace(0, 1, 201)).tolist()       # live risk -> percentile of the training risks
    torch.save(dict(model=mf, tools=tools, models=models, variant=name, n=n, risk_quantiles=q,
                    trained_at=time.strftime("%Y-%m-%d %H:%M:%S")), MODEL_F)
    print(f"[gate1] saved serving model ({name}, all {n} actions) in {time.time() - t1:.0f}s -> {MODEL_F}")


def save_only(variant):
    recs = [r for r in sorted(cc_core.load_actions().values(), key=lambda r: r["ts"]) if r["outcome"] != "unknown"]
    tools = [t for t, _ in collections.Counter(r["tool"] for r in recs[:int(0.75 * len(recs))]).most_common(14)]
    models = [m for m, _ in collections.Counter(r["model"] for r in recs[:int(0.75 * len(recs))]).most_common(4)]
    Xh, _ = build(recs, tools, models)
    y = np.array([int(r["outcome"] == "ok") for r in recs])
    ta, tp = texts(recs)
    Ea = cc_core.embed(ta)
    parts = {"NI history features only": [Xh], "NI + action text": [Xh, Ea],
             "NI + action text + agent's plan text": [Xh, Ea, cc_core.embed(tp)],
             "NI + action text + recent errors": [Xh, Ea, err_block(Ea, build.err_ctx)]}[variant]
    cc_core.save_cache()
    save_model(np.concatenate(parts, 1), y, tools, models, variant, len(recs))


def fmt_ts(t):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def paired_bootstrap(SC, fail, ni_name, base_names, B=1000, seed=0):
    """Resample the test actions with replacement; the SAME resample scores both methods, so the difference is paired."""
    rng = np.random.RandomState(seed); n = len(fail); out = {}
    for b in base_names:
        da, dp = [], []
        for _ in range(B):
            i = rng.randint(0, n, n)
            if fail[i].sum() < 2:
                continue
            ma, mb = metrics(SC[ni_name][i], fail[i]), metrics(SC[b][i], fail[i])
            da.append(ma["auroc"] - mb["auroc"]); dp.append(ma["auprc"] - mb["auprc"])
        da, dp = np.array(da), np.array(dp)
        out[b] = dict(auroc=(da.mean(), *np.percentile(da, [2.5, 97.5]), (da > 0).mean()),
                      auprc=(dp.mean(), *np.percentile(dp, [2.5, 97.5]), (dp > 0).mean()))
    return out


def write_report(recs, cut, fail, res, diags, by, per_tool, secs, ni_name=None, boot=None):
    n = len(recs); te_fail = int(fail[cut:].sum()); tr_fail = int(fail[:cut].sum())
    L = ["# Gate 1 - can NI tell, before an agent acts, that the action will fail or be refused?", "",
         f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `cc_gate.py` in {secs:.0f} s. Data: every Claude Code tool call on this machine "
         f"({n} actions with a known outcome, harvested from local transcripts by `cc_harvest.py`).", "",
         "| | Actions | Failed or refused | Dates |", "|---|---|---|---|",
         f"| Train (oldest 75%) | {cut} | {tr_fail} ({tr_fail / cut:.1%}) | {fmt_ts(recs[0]['ts'])} to {fmt_ts(recs[cut - 1]['ts'])} |",
         f"| Test (newest 25%, never seen) | {n - cut} | {te_fail} ({te_fail / (n - cut):.1%}) | {fmt_ts(recs[cut]['ts'])} to {fmt_ts(recs[-1]['ts'])} |", "",
         "Models are fitted on the train window and frozen. History features (how often this tool, this kind of action, this exact "
         "action, this session have failed) are computed online from earlier actions only, as a live gate would see them.", "",
         "## Results on the test window", "",
         "AUROC: 0.5 = chance, 1.0 = perfect ranking of risky actions above safe ones. AUPRC: area under precision-recall; "
         f"chance = the failure rate ({te_fail / (n - cut):.3f}). P@5% = share of the 5% riskiest-rated actions that really failed. "
         "R@5% = share of all failures caught in that 5%.", "",
         "| Method | AUROC | AUPRC | P@2% | P@5% | R@5% | R@10% | Fail rate in safest half |", "|---|---|---|---|---|---|---|---|"]
    for k, v in res.items():
        L.append(f"| {k} | {v['auroc']:.3f} | {v['auprc']:.3f} | {v['p@2%']:.2f} | {v['p@5%']:.2f} | {v['r@5%']:.2f} | {v['r@10%']:.2f} | {v['fail_rate_safest_half']:.3%} |")
    best_b = max((v["auroc"], k) for k, v in res.items() if k.startswith("B"))
    best_n = max((v["auroc"], k) for k, v in res.items() if k.startswith("NI"))
    L += ["", "## Verdict", "",
          f"- Best baseline: **{best_b[1]}**, AUROC {best_b[0]:.3f}.",
          f"- Best NI variant: **{best_n[1]}**, AUROC {best_n[0]:.3f}.",
          f"- Gate 1 criterion (NI beats every baseline on the held-out window): **{'MET' if best_n[0] > best_b[0] else 'NOT MET'}** "
          f"(margin {best_n[0] - best_b[0]:+.3f}).",
          "- Claude Code exposes no per-action confidence, so 'beats the agent's own confidence' cannot be measured here; the baselines "
          "above stand in for it.", "",
          f"## Is the difference real? Paired bootstrap, {ni_name} minus each baseline (1000 resamples of the test window)", "",
          "| Baseline | AUROC difference [95% interval] | P(NI better) | AUPRC difference [95% interval] | P(NI better) |", "|---|---|---|---|---|"]
    for b, d in (boot or {}).items():
        a, p = d["auroc"], d["auprc"]
        L.append(f"| {b} | {a[0]:+.3f} [{a[1]:+.3f}, {a[2]:+.3f}] | {a[3]:.0%} | {p[0]:+.3f} [{p[1]:+.3f}, {p[2]:+.3f}] | {p[3]:.0%} |")
    L += ["", "An interval that contains 0 means the test window cannot tell the two methods apart.", "",
          f"## What {ni_name} catches in its riskiest 5%, by outcome class (test window)", "",
          "| Outcome | Failures in test | Caught in riskiest 5% |", "|---|---|---|"]
    for k, (a, b) in sorted(by.items(), key=lambda x: -x[1][0]):
        L.append(f"| {k} | {a} | {b} ({b / max(a, 1):.0%}) |")
    L += ["", f"## Per tool ({ni_name}, tools with at least 5 test failures)", "", "| Tool | Test actions | Failures | AUROC |", "|---|---|---|---|"]
    for t, (a, b, c) in per_tool.items():
        L.append(f"| {t} | {a} | {b} | {c:.3f} |")
    L += ["", "## Fit diagnostics", "", "```", json.dumps(diags, indent=1, default=str), "```", "",
          "## Honest limits", "",
          "- The outcome is the immediate tool result, not whether the whole task was right. Task-level outcomes (did the user keep the "
          "work, did tests pass at the end) are the next labels to add.",
          "- One user, one machine, mostly one agent family (Claude models in Claude Code). It says nothing yet about other people or other vendors.",
          "- Some failures are harness rules (for example blocked `sleep`), which are easy to learn; the outcome-class table shows how much of the score comes from them."]
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("[gate1] wrote", REPORT)


if __name__ == "__main__":
    main()
