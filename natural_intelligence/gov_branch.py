"""Branch engine: keep every child of a decision alive, evaluate all of them on copies, and pick with proof.

The "second child" problem: a tree search that commits to one branch never learns what the other would have done. NI keeps
every branch alive until MEASURED evidence separates them. Only one irreversible action can happen in the real world,
so the branches run on copies (gov_cow, L15); the original's hash is checked at every step.

Definitions
  branch b      an alternative transform of the same source (from any agent or plan); children compose on their parent
  feasible      the branch's check passed and its copy kept the invariant (lexicographic: never traded)
  v(b)          measured value vector, each dimension oriented "higher is better" and min-max scaled across the branches:
                  quality   score of the check (default 1 = passed)          speed    -(check seconds)
                  compact   -(changed lines vs the original)                  + any extra measured dims the caller supplies
  weights w     uncertain: w ~ Dirichlet(alpha) restricted by every answer the human gave (w_i > w_j)
  P_best(b)     = P_w( b = argmax_{feasible} w . v )   by Monte Carlo over w

Rules
  prune         a branch is dropped from the recommendation set only if it is infeasible or Pareto-dominated on v;
                it is still KEPT in the record with the reason (failures are knowledge, brief 2 section 6.3)
  recommend     b* = argmax P_best, only if P_best(b*) >= confidence (0.8); otherwise
  cross-question: ask the pairwise question "which matters more here, i or j?" with the highest expected information
                gain about argmax:  IG(i,j) = H(argmax) - sum_ans P(ans) H(argmax | ans)
  proof         the evidence table, why each loser lost, and the smallest weight change that flips the pick
"""
import os, sys, json, time, math, difflib, itertools, uuid, re
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import gov_cow, gov_ledger

OUT_DIR = os.path.join(gov_ledger.GOV_DIR, "branches"); os.makedirs(OUT_DIR, exist_ok=True)
DIM_WORDS = {"quality": "the check's score", "speed": "how fast the check runs", "compact": "how small the change is"}


def changed_lines(src, copy_dir):
    """Lines added + removed between the original and the transformed copy (text files only)."""
    n = 0
    base = src if os.path.isdir(src) else os.path.dirname(src)
    files = []
    if os.path.isdir(src):
        for dp, dn, fn in os.walk(copy_dir):
            dn[:] = [d for d in dn if d not in gov_cow.SKIP]
            files += [os.path.relpath(os.path.join(dp, f), copy_dir) for f in fn]
    else:
        files = [os.path.basename(src)]
    for rel in files:
        a, b = os.path.join(base, rel), os.path.join(copy_dir, rel)
        try:
            ta = open(a, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(a) else []
            tb = open(b, encoding="utf-8", errors="replace").read().splitlines()
        except (OSError, UnicodeError):
            continue
        n += sum(1 for l in difflib.unified_diff(ta, tb, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---"))
    return n


def flatten(branches, prefix="", parent=None):
    """Branch tree -> list of (path name, composed transform, agent). Children apply on top of their parent."""
    out = []
    for b in branches:
        name = prefix + b["name"]
        tf = b["transform"] if parent is None else (lambda d, p=parent, t=b["transform"]: (p(d), t(d)))
        out.append(dict(name=name, transform=tf, agent=b.get("agent", "?"), extra=b.get("extra", {})))
        if b.get("children"):
            out += flatten(b["children"], name + "/", tf)
    return out


class Weights:
    """Dirichlet prior over value weights, conditioned on the human's pairwise answers (w_i > w_j)."""

    def __init__(self, dims, alpha=None, n=6000, seed=0):
        self.dims = list(dims); rng = np.random.default_rng(seed)
        a = np.array([(alpha or {}).get(d, 1.0) for d in self.dims], float)
        self.W = rng.dirichlet(a, n); self.answers = []

    def condition(self, i, j):
        """The human said dimension i matters more than j here."""
        keep = self.W[:, self.dims.index(i)] > self.W[:, self.dims.index(j)]
        if keep.sum() >= 50:
            self.W = self.W[keep]
        self.answers.append((i, j))


def _p_best(V, W, feas):
    """P(branch is the argmax) over weight samples; exact ties share the win equally (no list-order bias)."""
    s = W @ V.T; s[:, ~feas] = -np.inf
    top = s >= s.max(1, keepdims=True) - 1e-12
    share = top / top.sum(1, keepdims=True)
    return share.mean(0), np.argmax(s, 1)


def _entropy(p):
    p = p[p > 0]; return float(-(p * np.log2(p)).sum())


NOISE_FLOOR = {"quality": 0.05, "speed": 1.0, "compact": 1.0}    # 1 check in 20 / seconds of timing jitter / one line
REL_FLOOR = {"compact": 0.10}                                     # a change-size difference under 10% of the typical change is noise
REGRET_TOL = 0.05                                                 # ask only if picking now could lose more than this (scaled value)


def floors(raw, feas, dims):
    f = []
    for k, d in enumerate(dims):
        base = NOISE_FLOOR.get(d, 1e-9)
        if d in REL_FLOOR and feas.any():
            base = max(base, REL_FLOOR[d] * float(np.median(np.abs(raw[feas, k]))))
        f.append(base)
    return np.array(f)


def analyse(rows, dims, weights, confidence=0.8):
    names = [r["name"] for r in rows]
    raw = np.array([[r["v_raw"][d] for d in dims] for r in rows], float)
    feas = np.array([r["feasible"] for r in rows])
    fl = floors(raw, feas, dims)
    raw = np.round(raw / fl) * fl                                 # measured values on their noise grid: sub-noise gaps vanish
    ref = raw[feas] if feas.any() else raw                        # scale over the branches that can actually be chosen
    lo, hi = ref.min(0), ref.max(0)
    # scale by max(range, noise floor): differences smaller than what can be measured stay small instead of
    # being stretched to the full [0, 1] range (a 10 ms timing jitter must not decide anything)
    span = np.maximum(hi - lo, fl)
    V = (raw - lo) / span
    # Pareto dominance among feasible branches, counted only beyond the noise floor of each dimension
    dom = {}
    for a, b in itertools.permutations(range(len(rows)), 2):
        d = (raw[a] - raw[b]) / fl
        if feas[a] and feas[b] and np.all(d > -1) and np.any(d >= 1) and b not in dom:
            dom[b] = a
    res = dict(dims=dims, scaled={n: dict(zip(dims, map(float, V[i]))) for i, n in enumerate(names)})
    if not feas.any():
        res.update(verdict="no_feasible_branch", recommend=None, p_best={}, question=None,
                   message="No branch passed the check. Keep the original; every branch is recorded with its failure.")
        return res, V, feas, dom
    pb, win = _p_best(V, weights.W, feas)
    top = int(np.argmax(pb)); res["p_best"] = {n: round(float(p), 4) for n, p in zip(names, pb)}
    # flips: for the runner-up, which single dimension's extra weight would make it win
    flips = []
    for b in range(len(rows)):
        if b != top and feas[b]:
            for k, d in enumerate(dims):
                if V[b, k] > V[top, k]:
                    flips.append(dict(branch=names[b], if_more_weight_on=d))
    res["flips"] = flips
    S = weights.W @ V[feas].T                                       # expected regret of picking the leader now
    regret = float(np.mean(S.max(1) - weights.W @ V[top]))
    res["expected_regret"] = round(regret, 4)
    if pb[top] >= confidence:
        res.update(verdict="recommend", recommend=names[top], question=None)
    elif regret < REGRET_TOL:
        res.update(verdict="recommend_equivalent", recommend=names[top], question=None)
    else:
        best_q, best_ig = None, 0.0
        H0 = _entropy(pb)
        for i, j in itertools.combinations(dims, 2):
            m = weights.W[:, dims.index(i)] > weights.W[:, dims.index(j)]
            if m.sum() < 50 or (~m).sum() < 50:
                continue
            pa, _ = _p_best(V, weights.W[m], feas); pbb, _ = _p_best(V, weights.W[~m], feas)
            ig = H0 - (m.mean() * _entropy(pa) + (1 - m.mean()) * _entropy(pbb))
            if ig > best_ig:
                best_ig, best_q = ig, (i, j)
        res.update(verdict="cross_question", recommend=None,
                   question=None if best_q is None else dict(more_important=best_q, info_gain_bits=round(best_ig, 4),
                                                             text=f"Which matters more here: {DIM_WORDS.get(best_q[0], best_q[0])} "
                                                                  f"or {DIM_WORDS.get(best_q[1], best_q[1])}?"))
    return res, V, feas, dom


def explore(src, branches, test_cmd, extra_dims=(), alpha=None, confidence=0.8, workers=4, timeout=600, ledger=None, seed=0):
    """Run every branch on its own copy (in parallel), measure, keep all, then recommend or cross-question."""
    src = os.path.abspath(src); bid = time.strftime("%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    h0 = gov_cow.tree_hash(src)[0]; flat = flatten(branches)

    def one(b):
        p = gov_cow.propose(src, b["transform"], test_cmd, timeout=timeout)
        copy_dir = os.path.join(gov_cow.SANDBOX, p["id"], "copy")
        t = p["tests"].get("copy", {})
        m = re.search(r"PASSED (\d+)/(\d+)", t.get("tail") or "")       # graded check output, if the check prints one
        qual = (int(m.group(1)) / max(int(m.group(2)), 1)) if m else float(t.get("code") == 0)
        v = dict(quality=qual, speed=-float(t.get("secs") or timeout), compact=-float(changed_lines(src, copy_dir)))
        for d in extra_dims:
            v[d] = float(b["extra"].get(d, 0.0))
        feasible = bool(t.get("code") == 0 and not p["invariant_violation"] and p["transform_error"] is None)
        why = None if feasible else ("invariant violation: touched the original" if p["invariant_violation"] else
                                     f"transform error {p['transform_error']}" if p["transform_error"] else
                                     f"check failed (exit {t.get('code')}): {(t.get('tail') or '')[-160:]}")
        return dict(name=b["name"], agent=b["agent"], proposal=p["id"], feasible=feasible, infeasible_reason=why,
                    v_raw=v, check_tail=(t.get("tail") or "")[-300:])
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(one, flat))
    dims = ["quality", "speed", "compact"] + list(extra_dims)
    W = Weights(dims, alpha, seed=seed)
    res, V, feas, dom = analyse(rows, dims, W, confidence)
    for i, r in enumerate(rows):                      # every branch kept, with the reason it is not the pick
        if not r["feasible"]:
            r["kept_because"] = "failed: " + r["infeasible_reason"]
        elif i in dom:
            r["kept_because"] = f"dominated by {rows[dom[i]]['name']} (no better beyond noise anywhere, worse beyond noise somewhere)"
        elif res.get("recommend") == r["name"]:
            r["kept_because"] = "recommended"
        else:
            r["kept_because"] = f"on the Pareto front; P_best {res['p_best'].get(r['name'], 0):.2f}"
    invariant_ok = gov_cow.tree_hash(src)[0] == h0
    rec = dict(id=bid, src=src, ts=time.time(), branches=rows, invariant_ok=invariant_ok, confidence=confidence,
               alpha=alpha, answers=[], **res)
    rec["message"] = message(rec)
    json.dump(rec, open(os.path.join(OUT_DIR, bid + ".json"), "w", encoding="utf-8"), indent=1)
    if ledger is not None:
        ledger.append("branch", dict(id=bid, src=src, n=len(rows), verdict=rec["verdict"], recommend=rec["recommend"], invariant_ok=invariant_ok))
    return rec


def answer(rec, more, less, seed=0):
    """Fold in the human's answer ('more' matters more than 'less') and re-decide. The record is updated in place."""
    W = Weights(rec["dims"], rec.get("alpha"), seed=seed)
    for i, j in rec.get("answers", []):
        W.condition(i, j)
    W.condition(more, less); rec["answers"] = W.answers
    res, _, _, _ = analyse(rec["branches"], rec["dims"], W, rec["confidence"])
    rec.update(res); rec["message"] = message(rec)
    json.dump(rec, open(os.path.join(OUT_DIR, rec["id"] + ".json"), "w", encoding="utf-8"), indent=1)
    return rec


def message(rec):
    L = []
    if rec["verdict"] == "recommend":
        L.append(f"Pick '{rec['recommend']}' (best under {rec['p_best'][rec['recommend']]:.0%} of plausible value weights).")
    elif rec["verdict"] == "recommend_equivalent":
        L.append(f"Pick '{rec['recommend']}'. The leading branches are equivalent within measurement noise (expected loss from "
                 f"picking now {rec['expected_regret']:.3f} < {REGRET_TOL}), so asking you would not be worth your time.")
    elif rec["verdict"] == "cross_question":
        L.append("The evidence does not separate the best branches yet. " + (rec["question"]["text"] if rec["question"] else ""))
    else:
        L.append(rec.get("message", "No branch passed the check."))
    for r in rec["branches"]:
        v = r["v_raw"]
        L.append(f"- {r['name']} ({r['agent']}): check {'passed' if r['feasible'] else 'FAILED'} (quality {v['quality']:.2f}), {-v['speed']:.2f}s, "
                 f"{int(-v['compact'])} lines changed -> {r['kept_because']}")
    if rec.get("flips"):
        f = rec["flips"][0]; L.append(f"Would change to '{f['branch']}' if {DIM_WORDS.get(f['if_more_weight_on'], f['if_more_weight_on'])} mattered more.")
    L.append(f"Original unchanged: {rec['invariant_ok']}.")
    return "\n".join(L)


if __name__ == "__main__":
    print(__doc__)
