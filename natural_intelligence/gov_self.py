"""L18 self-governance: NI's own predictor is an agent too, with its own measured trust.

Data: (a) the gate's held-out scores on the newest 25% of actions (cc_gate.py -> gate1_test_scores.npz, model trained on
the oldest 75% only) and (b) live shadow scores joined to their real outcomes (live_scores.jsonl x actions.jsonl).

Measured:
  ECE   = sum_b (n_b / n) |mean(risk_b) - fail_rate_b| over 10 equal-count bins
  rel   = ECE / base failure rate             (rare failures make absolute ECE look tiny; the relative error is honest)
  budget b = clip(1 - rel, 0.2, 1)           NI's autonomy budget: q_eff = b q_gate + (1 - b) q_counts  (gov_decide)
Recalibration (L16 paired acceptance): isotonic map fitted on the OLDER half of the held-out window, adopted only if it
lowers log-loss on the NEWER half. Otherwise the raw score is kept. The decision is written to self_state.json with the
numbers, and the budget is then measured on the newer half with whichever score was adopted.
NI cannot change its own policy file (gov_policy lock); it can only shrink or restore its own budget from evidence.
"""
import os, json, time
import numpy as np
import cc_core, gov_core

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVED = "NI + action text + recent errors"


def ece(p, y, bins=10):
    o = np.argsort(p); chunks = np.array_split(o, bins); e = 0.0; rows = []
    for c in chunks:
        if len(c):
            e += len(c) / len(p) * abs(p[c].mean() - y[c].mean())
            rows.append((float(p[c].mean()), float(y[c].mean()), len(c)))
    return float(e), rows


def logloss(p, y):
    p = np.clip(p, 1e-5, 1 - 1e-5); return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def live_pairs():
    f = os.path.join(cc_core.CC_DIR, "live_scores.jsonl")
    if not os.path.exists(f):
        return np.zeros(0), np.zeros(0)
    acts = cc_core.load_actions(); p, y = [], []
    for line in open(f, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        a = acts.get(r.get("tool_use_id"))
        if a and a["outcome"] != "unknown" and not str(r.get("tool_use_id", "")).startswith("e2e_test"):
            p.append(r["risk"]); y.append(int(a["outcome"] != "ok"))
    return np.array(p, float), np.array(y, int)


def run(write=True):
    z = np.load(os.path.join(cc_core.CC_DIR, "gate1_test_scores.npz"))
    p, y = z[SERVED].astype(float), z["fail"].astype(int)
    h = len(p) // 2
    from sklearn.isotonic import IsotonicRegression
    iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-4, y_max=0.9999).fit(p[:h], y[:h])
    raw_ll, iso_ll = logloss(p[h:], y[h:]), logloss(iso.predict(p[h:]), y[h:])
    adopt = iso_ll < raw_ll
    p_new = iso.predict(p[h:]) if adopt else p[h:]
    e_raw, rows_raw = ece(p[h:], y[h:]); e_new, rows_new = ece(p_new, y[h:])
    base = float(y[h:].mean()); rel = e_new / max(base, 1e-3); budget = float(np.clip(1 - rel, 0.2, 1.0))
    lp, ly = live_pairs()
    live = None
    if len(lp) >= 30:
        lp2 = np.array([gov_core.apply_calibration(x, None) for x in lp])
        live = dict(n=len(lp), fails=int(ly.sum()), ece=ece(lp2, ly)[0] if ly.sum() else None)
    cal = None
    if adopt:
        xs = np.unique(np.concatenate([[0.0], iso.X_thresholds_, [1.0]]))
        cal = dict(x=xs.tolist(), y=np.clip(iso.predict(xs), 1e-4, 0.9999).tolist())
    st = dict(ts=time.strftime("%Y-%m-%d %H:%M:%S"), served_variant=SERVED, n_fit=h, n_check=len(p) - h,
              base_fail_rate=round(base, 4), logloss_raw=round(raw_ll, 5), logloss_isotonic=round(iso_ll, 5),
              calibration_adopted=bool(adopt), ece_raw=round(e_raw, 5), ece_adopted=round(e_new, 5),
              relative_ece=round(rel, 4), budget=round(budget, 4), reliability_raw=rows_raw, reliability_adopted=rows_new,
              live=live, calibration=cal,
              note="budget shrinks NI's own gate toward simple counts when its probabilities are off (L18)")
    if write:
        prev = gov_core.load_self_state(); prev.pop("note", None)
        prev.update(st)
        json.dump(prev, open(gov_core.SELF_STATE, "w", encoding="utf-8"), indent=1)
        st = prev
    return st


def set_choice(**kw):
    """Record validation-chosen settings (belief gamma/k, autonomy unit) next to the self-check numbers."""
    st = gov_core.load_self_state(); st.update(kw)
    json.dump(st, open(gov_core.SELF_STATE, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    s = run()
    print(json.dumps({k: v for k, v in s.items() if k not in ("calibration", "reliability_raw", "reliability_adopted")}, indent=1))
