"""Held-out evaluation of the governor on real Claude Code actions -> GOV_REPORT.md.  Offline; nothing is run live.

A. L2 beliefs: time split (oldest 75% history, newest 25% test). gamma and k are chosen on the LAST 20% OF HISTORY only,
   then the test window is predicted online (predict, then learn the outcome) - exactly how it runs live.
   Baselines: running global failure rate; per-kind rate frozen at the split.
B. Decisions: the newest HALF of the gate's held-out window (the older half fitted the L18 isotonic map). Every policy sees
   the same actions. Measured, not modelled: escalation load, failure recall, escalation precision. Modelled: utility under
   the policy's own loss table (reported separately, because it uses NI's own assumptions).
C. Real drift alarms: after each CUSUM alarm, was the failure rate of the next 30 events above the reference rate?
D. Failure map: reasons per agent (the bad examples, kept).
"""
import os, sys, json, time, math, collections, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import cc_core, ni_outer, gov_policy, gov_beliefs, gov_core, gov_decide, gov_ledger, gov_self, gov_select

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "GOV_REPORT.md")
EVAL_JSON = os.path.join(gov_ledger.GOV_DIR, "eval_last.json")


def ll(p, y):
    p = np.clip(p, 1e-5, 1 - 1e-5); return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def boot_ci(f, n, B=1000, seed=0):
    rng = np.random.default_rng(seed); v = [f(rng.integers(0, n, n)) for _ in range(B)]
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))


def part_a(recs):
    n = len(recs); cut = int(0.75 * n); vcut = int(0.8 * cut)
    y = np.array([int(r["outcome"] != "ok") for r in recs])

    def run(gamma, k, start, stop):
        B = gov_beliefs.Beliefs(gamma=gamma, k=k); p = []
        for i, r in enumerate(recs[:stop]):
            if i >= start:
                p.append(B.p_fail(r))
            B.update(r)
        return np.array(p)
    grid = [(g, k) for g in (1.0, 0.9995, 0.999, 0.995, 0.99) for k in (2.0, 5.0, 20.0)]
    val = {(g, k): ll(run(g, k, vcut, cut), y[vcut:cut]) for g, k in grid}
    g, k = min(val, key=val.get)
    p_ni = run(g, k, cut, n); yt = y[cut:]
    # baselines
    glob, f, c = [], 0, 0
    for i, r in enumerate(recs):
        if i >= cut:
            glob.append((f + 1) / (c + 2))
        f += y[i]; c += 1
    glob = np.array(glob)
    cnt = collections.defaultdict(lambda: [0, 0])
    for r, yy in zip(recs[:cut], y[:cut]):
        h = gov_beliefs.Beliefs.region_of(r); cnt[h][0] += yy; cnt[h][1] += 1
    g0 = y[:cut].mean()
    frozen = np.array([(cnt[gov_beliefs.Beliefs.region_of(r)][0] + 5 * g0) / (cnt[gov_beliefs.Beliefs.region_of(r)][1] + 5) for r in recs[cut:]])
    rows = {}
    for name, p in (("running global failure rate", glob), ("per-kind rate frozen at the split", frozen), ("NI L2 beliefs (online, hierarchical)", p_ni)):
        rows[name] = dict(logloss=ll(p, yt), brier=float(np.mean((p - yt) ** 2)), auroc=ni_outer._auc(p, yt), ece=gov_self.ece(p, yt)[0])
    d = lambda ix: ll(frozen[ix], yt[ix]) - ll(p_ni[ix], yt[ix])
    ci = boot_ci(d, len(yt))
    return dict(n_test=len(yt), fails=int(yt.sum()), chosen=dict(gamma=g, k=k), val=dict((f"{a}|{b}", round(v, 5)) for (a, b), v in val.items()),
                rows=rows, ll_gain_vs_frozen=d(np.arange(len(yt))), ll_gain_ci=ci)


def align(recs, z):
    fail = z["fail"]; n = len(fail)
    y = np.array([int(r["outcome"] != "ok") for r in recs])
    for off in range(0, 40):
        for sgn in (1, -1):
            st = len(recs) - n - sgn * off
            if 0 <= st and st + n <= len(recs) and np.array_equal(y[st:st + n], fail):
                return st
    return None


def outcome_util(verdict, fail, L, P, a):
    G, C, cov = P["gain_success"], P["cost"], P["verify_coverage"]
    if verdict == "proceed":
        return -L if fail else G
    if verdict == "verify":
        return (-(1 - cov) * L - C["verify"]) if fail else (G - C["verify"])
    if verdict == "stop":
        return 0.0
    # ask_human: modelled human with accuracy a (expected value; human cost charged at the base rate)
    hc = P["human"]["cost_base"]
    return (a * 0.0 + (1 - a) * -L - hc) if fail else (a * G - hc)


def run_window(recs, a, b, risk, selfst, lk):
    """Governor warmed on recs[:a], then predict-then-learn over recs[a:b] with the gate's held-out risk."""
    G = gov_core.Governor(ledger=False, lock_path=lk); G.selfst = selfst
    G.B = gov_beliefs.Beliefs(**(selfst.get("beliefs") or {}))
    G.warm(recs[:a]); out = []; t0 = time.time()
    for r, rr in zip(recs[a:b], risk):
        tr = G.govern(r, risk=rr, now=r.get("ts"), record=False)
        out.append(dict(v=tr["verdict"], b=tr["binding"], cls=tr["cls"], q=tr["factors"]["q"], loss=tr["factors"]["loss"],
                        auth=bool(tr["factors"]["requires_human"]), fail=int(r["outcome"] != "ok"), region=tr["factors"]["region"],
                        level=tr["factors"]["level"]))
        G.observe(r)
    return out, G, (time.time() - t0) / max(b - a, 1) * 1000


def j_modelled(out, P, a):
    return float(np.mean([outcome_util(o["v"], o["fail"], o["loss"], P, a) for o in out]))


def part_b(recs, z, selfst):
    st = align(recs, z)
    if st is None:
        return dict(error="could not align the saved held-out scores with the action store")
    n = len(z["fail"]); h = n // 2
    risk_raw = z[gov_self.SERVED].astype(float)
    tmp = tempfile.mkdtemp(); lk = os.path.join(tmp, "eval.lock")
    open(lk, "w").write(gov_policy.sha(gov_policy.POLICY) + " eval-only lock\n")
    P, _ = gov_policy.load(gov_policy.POLICY, lk)
    a0 = P["human"]["accuracy_prior"][0] / sum(P["human"]["accuracy_prior"])
    # choose the autonomy unit on the VALIDATION half (older half of the window) by the objective J itself
    val = {}
    for unit in ("kind", "class"):
        s2 = dict(selfst); s2["autonomy_unit"] = unit
        o, _, _ = run_window(recs, st, st + h, risk_raw[:h], s2, lk); val[unit] = j_modelled(o, P, a0)
    unit = max(val, key=val.get); selfst = dict(selfst); selfst["autonomy_unit"] = unit
    out, G, ms = run_window(recs, st + h, st + n, risk_raw[h:], selfst, lk)
    abl = {}
    for u2 in ("kind", "class"):
        if u2 != unit:
            s3 = dict(selfst); s3["autonomy_unit"] = u2; abl[u2] = run_window(recs, st + h, st + n, risk_raw[h:], s3, lk)[0]
    rk = risk_raw[h:]; yt = z["fail"][h:].astype(int)
    shutil.rmtree(tmp, ignore_errors=True)
    a = G.human[0] / sum(G.human)
    esc = np.array([o["v"] != "proceed" for o in out]); fails = yt.astype(bool); auth = np.array([o["auth"] for o in out])
    qr = np.array([o["q"] for o in out]); Ls = np.array([o["loss"] for o in out])
    k = int(esc.sum())
    cal_risk = np.array([gov_core.apply_calibration(x, selfst.get("calibration")) for x in rk])

    def summarize(name, ev, verdicts):
        m = dict(name=name, escalations=int(ev.sum()), per_100=round(100 * ev.mean(), 2),
                 asks_per_100=round(100 * np.mean([v == "ask_human" for v in verdicts]), 2),
                 fail_recall=float((ev & fails).sum() / max(fails.sum(), 1)),
                 precision_fail=float((ev & fails).sum() / max(ev.sum(), 1)),
                 precision_needed=float((ev & (fails | auth)).sum() / max(ev.sum(), 1)),
                 fails_let_through=int((~ev & fails).sum()),
                 utility_modelled=float(np.mean([outcome_util(v, f, L, P, a) for v, f, L in zip(verdicts, yt, Ls)])))
        return m
    rows = [summarize("agent alone (always proceed)", np.zeros(len(out), bool), ["proceed"] * len(out))]
    rule = auth.copy()
    rows.append(summarize("fixed permission rule (escalate irreversible classes only)", rule, ["ask_human" if x else "proceed" for x in rule]))
    o = np.argsort(-cal_risk); thr = np.zeros(len(out), bool); thr[o[:k]] = True
    rows.append(summarize(f"gate risk threshold, same budget as NI ({k} escalations)", thr, ["verify" if x else "proceed" for x in thr]))
    rows.append(summarize(f"NI governor (L2+L5+L11+L18), autonomy unit '{unit}' chosen on validation", esc, [x["v"] for x in out]))
    for u2, o2 in abl.items():
        rows.append(summarize(f"ablation: NI with autonomy unit '{u2}'", np.array([x["v"] != "proceed" for x in o2]), [x["v"] for x in o2]))
    rows.append(summarize("oracle (escalates exactly the failures)", fails.copy(), ["stop" if f else "proceed" for f in fails]))
    by_v = collections.Counter(x["v"] for x in out); by_b = collections.Counter(x["b"] or "expected utility" for x in out)
    by_cls = collections.defaultdict(lambda: dict(n=0, fails=0, esc=0, caught=0))
    for x in out:
        c = by_cls[x["cls"]]; c["n"] += 1; c["fails"] += x["fail"]; c["esc"] += int(x["v"] != "proceed"); c["caught"] += int(x["v"] != "proceed" and x["fail"])
    # paired bootstrap: NI vs same-budget threshold on failure recall
    def rec_diff(ix):
        f = fails[ix]
        return (esc[ix] & f).sum() / max(f.sum(), 1) - (thr[ix] & f).sum() / max(f.sum(), 1)
    ci = boot_ci(rec_diff, len(out))
    nonauth = ~auth
    def rec_diff_na(ix):
        f = fails[ix] & nonauth[ix]
        return (esc[ix] & f).sum() / max(f.sum(), 1) - (thr[ix] & f).sum() / max(f.sum(), 1)
    return dict(n=len(out), fails=int(fails.sum()), auth=int(auth.sum()), human_acc_assumed=a, rows=rows, verdicts=dict(by_v),
                unit=unit, unit_val=val,
                bindings=dict(by_b), by_class=dict(by_cls), recall_diff_vs_threshold_ci=ci, ms_per_decision=round(ms, 2),
                recall_diff_nonauth_ci=boot_ci(rec_diff_na, len(out)),
                levels=dict(collections.Counter(x["level"] for x in out)))


def part_c(recs):
    B = gov_beliefs.Beliefs(gamma=1.0)
    idx = collections.defaultdict(list)
    alarms = []
    for i, r in enumerate(recs):
        key = (B.agent_of(r), B.region_of(r)); idx[key].append(i)
        for a in B.update(r):
            if a["key"][0] == "agent_region":
                alarms.append((a, len(idx[key]) - 1, key))
    rows = []
    for a, pos, key in alarms:
        nxt = idx[key][pos + 1: pos + 31]; prev = idx[key][max(0, pos - 30): pos + 1]
        fr_next = np.mean([recs[j]["outcome"] != "ok" for j in nxt]) if nxt else None
        fr_prev = np.mean([recs[j]["outcome"] != "ok" for j in prev])
        rows.append(dict(agent=key[0], region=key[1], when=time.strftime("%Y-%m-%d %H:%M", time.localtime(a["ts"] or 0)),
                         n=a["n"], p0=a["p0"], fail_prev30=float(fr_prev), fail_next30=None if fr_next is None else float(fr_next), n_next=len(nxt)))
    judged = [r for r in rows if r["fail_next30"] is not None and r["n_next"] >= 10]
    hit = sum(r["fail_next30"] > r["p0"] for r in judged)
    return dict(alarms=rows, judged=len(judged), held=hit)


def part_d(recs):
    P, _ = gov_policy.load(); m = collections.defaultdict(collections.Counter)
    for r in recs:
        if r["outcome"] != "ok":
            m[r["model"]][gov_policy.failure_reason(r["outcome"], r.get("err_head", ""), P)] += 1
    return {k: dict(v.most_common()) for k, v in m.items()}


def fmt(x, d=3):
    return "-" if x is None else (f"{x:.{d}f}" if isinstance(x, float) else str(x))


def report(A, Bres, C, D, S, T, sim):
    L = [f"# NI governor - held-out report ({time.strftime('%Y-%m-%d %H:%M')})", "",
         "Generated by `gov_eval.py`. Real Claude Code actions from this machine; nothing was run live. "
         "BUILT AND MEASURED unless a line says SIMULATED or MODELLED.", ""]
    L += ["## Tests (gov_tests.py)", "", f"{sum(t['ok'] for t in T)}/{len(T)} property tests pass "
          "(monotonicity on 4,000 random scenarios per factor, 11 counterfactual pairs, VOI >= 0, Shapley efficiency, "
          "trace re-derivation, tone honesty, CUSUM, ledger tamper, copy-on-write, policy lock, classifier).", ""]
    fails = [t for t in T if not t["ok"]]
    if fails:
        L += ["Failing:"] + [f"- {t['name']} {t['detail']}" for t in fails] + [""]
    L += ["## A. L2 capability beliefs vs simple rates (time split, online)", "",
          f"Test window: {A['n_test']} actions, {A['fails']} failures. Chosen on the last 20% of history only: "
          f"gamma = {A['chosen']['gamma']}, prior strength k = {A['chosen']['k']}.", "",
          "| Predictor of P(fail) | log-loss | Brier | AUROC | ECE |", "|---|---|---|---|---|"]
    for k, v in A["rows"].items():
        L.append(f"| {k} | {v['logloss']:.4f} | {v['brier']:.4f} | {v['auroc']:.3f} | {v['ece']:.4f} |")
    L += ["", f"Log-loss gain of NI beliefs over the frozen per-kind rate: {A['ll_gain_vs_frozen']:+.4f} "
          f"(95% bootstrap {A['ll_gain_ci'][0]:+.4f} to {A['ll_gain_ci'][1]:+.4f}).", "",
          "The beliefs are counts, not the gate: they are what earns autonomy levels and raises drift alarms. "
          "The gate (outer brain on text + history) remains the per-action risk score.", ""]
    if "error" in Bres:
        L += ["## B. Decisions", "", Bres["error"], ""]
    else:
        L += ["## B. Governor decisions vs baselines (same actions)", "",
              f"Newest half of the gate's held-out window: {Bres['n']} actions, {Bres['fails']} failures, "
              f"{Bres['auth']} actions in human-authority classes. Policy evaluated as if approved (eval-only lock). "
              f"NI self budget {S.get('budget')} with the adopted isotonic map. {Bres['ms_per_decision']} ms per decision (CPU).", "",
              f"Autonomy unit chosen on the older half by the objective J: '{Bres['unit']}' (J per action {Bres['unit_val']}).", "",
              "| Policy | escalations / 100 | of which human asks / 100 | failure recall | precision (failed) | precision (failed or authority) | failures let through | utility per action (MODELLED) |",
              "|---|---|---|---|---|---|---|---|"]
        for r in Bres["rows"]:
            L.append(f"| {r['name']} | {r['per_100']} | {r['asks_per_100']} | {r['fail_recall']:.3f} | {r['precision_fail']:.3f} | {r['precision_needed']:.3f} | {r['fails_let_through']} | {r['utility_modelled']:+.4f} |")
        ci = Bres["recall_diff_vs_threshold_ci"]; ci2 = Bres["recall_diff_nonauth_ci"]
        L += ["", f"Failure recall, NI minus same-budget threshold: 95% bootstrap {ci[0]:+.3f} to {ci[1]:+.3f}; "
              f"on non-authority actions only {ci2[0]:+.3f} to {ci2[1]:+.3f}.",
              f"Verdicts: {Bres['verdicts']}. Binding constraint: {Bres['bindings']}. Earned levels seen: {Bres['levels']}.", "",
              "| Action class | actions | failures | escalated | failures caught |", "|---|---|---|---|---|"]
        for c, v in sorted(Bres["by_class"].items(), key=lambda kv: -kv[1]["n"]):
            L.append(f"| {c} | {v['n']} | {v['fails']} | {v['esc']} | {v['caught']} |")
        L += ["", "Utility is MODELLED: it uses the policy file's own loss table and a human of accuracy "
              f"{Bres['human_acc_assumed']:.2f} (the prior; no human answers to NI exist yet). Recall and precision are measured.", ""]
    L += ["## C. Drift alarms on the real history (CUSUM per agent x kind of action)", "",
          f"{len(C['alarms'])} alarms. Judged (>= 10 later events): {C['judged']}; failure rate in the next 30 events above the "
          f"reference rate: {C['held']} of {C['judged']}.", "",
          "| agent | kind | when | events before | ref fail rate | fail rate prev 30 | fail rate next 30 |", "|---|---|---|---|---|---|---|"]
    for r in C["alarms"][:25]:
        L.append(f"| {r['agent']} | {r['region']} | {r['when']} | {r['n']} | {r['p0']:.3f} | {r['fail_prev30']:.2f} | {fmt(r['fail_next30'], 2)} ({r['n_next']}) |")
    L += ["", "## D. Failure map (bad examples kept with a reason)", "", "| agent | reasons |", "|---|---|"]
    for k, v in D.items():
        L.append(f"| {k} | " + ", ".join(f"{a} {b}" for a, b in v.items()) + " |")
    L += ["", "## E. L18 self-check (gov_self.py)", "",
          f"Gate raw ECE {S.get('ece_raw')} vs base failure rate {S.get('base_fail_rate')}; isotonic map fitted on the older half "
          f"{'ADOPTED' if S.get('calibration_adopted') else 'rejected'} (log-loss {S.get('logloss_raw')} -> {S.get('logloss_isotonic')} on the newer half); "
          f"ECE after {S.get('ece_adopted')}, relative {S.get('relative_ece')}, autonomy budget {S.get('budget')}. Live pairs: {S.get('live')}.", "",
          "## F. L6 selection (SIMULATED vendor update, 20 seeds)", "", "| policy | regret at 3000 | regret at 6000 | slope last 1000 |", "|---|---|---|---|"]
    for k, v in sim.items():
        L.append(f"| {k} | {v['regret_at'][3000]} | {v['regret_at'][6000]} | {v['slope_last_1000']} |")
    L += ["", "No real evaluation of selection is possible yet: the human chooses the model, so no randomised choices are logged.", ""]
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")


def main():
    recs = [r for r in sorted(cc_core.load_actions().values(), key=lambda r: r["ts"]) if r["outcome"] != "unknown"]
    t0 = time.time()
    A = part_a(recs); print(f"[eval] A done {time.time() - t0:.0f}s", flush=True)
    gov_self.set_choice(beliefs=A["chosen"])
    S = gov_self.run(write=True)
    z = np.load(os.path.join(cc_core.CC_DIR, "gate1_test_scores.npz"))
    Bres = part_b(recs, z, S); print(f"[eval] B done {time.time() - t0:.0f}s", flush=True)
    if "unit" in Bres:
        gov_self.set_choice(autonomy_unit=Bres["unit"]); S["autonomy_unit"] = Bres["unit"]
    C = part_c(recs); D = part_d(recs)
    T = json.load(open(os.path.join(gov_ledger.GOV_DIR, "tests_last.json"), encoding="utf-8")) if os.path.exists(os.path.join(gov_ledger.GOV_DIR, "tests_last.json")) else []
    sim = gov_select.simulate()
    report(A, Bres, C, D, S, T, sim)
    json.dump(dict(A=A, B=Bres, C=C, D=D, S={k: v for k, v in S.items() if k != "calibration"}), open(EVAL_JSON, "w", encoding="utf-8"), indent=1, default=str)
    print(f"[eval] wrote {OUT} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
