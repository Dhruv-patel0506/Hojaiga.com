"""L5 decision + L11 human value (VOI) + earned autonomy + L17 decision trace + L13 tone honesty rule.

Scenario factors s (brief 1, 5.1), every one named and measured:
  q            P(action succeeds)  - the gate's calibrated score, shrunk toward the counts prior by NI's own trust budget b
  q_prior      the agent x region posterior mean from L2 (used for the shrink and as a fallback)
  loss L       cost of a failure in this action class x environment multiplier (policy file)
  irreversible, requires_human, hard_value   from the action class (policy file, read-only to NI)
  level        autonomy level the agent has EARNED in this region (L2 lower bound), required_level from the class
  drift        L2 drift alarm active for this agent x region  -> level - 1 (automatic demotion)
  human_acc    a = P(the human judges this kind of action correctly) - Beta posterior from the human ledger
  asks_hour    how many times NI already asked the human in the last hour (their load)

Utilities (G = gain of success, cov = share of failures a verification catches before damage):
  U(proceed) = q G - (1-q) L - C_p
  U(verify)  = q G - (1-q) L (1-cov) - C_v
  U(stop)    = 0
  Human answer model: P(go | success) = P(no | failure) = a. Posterior after "go": q_go = a q / (a q + (1-a)(1-q)).
  V_h  = sum_ans P(ans) max_d U(d | q_ans)
  VOI  = V_h - max_d U(d | q)                              (brief 1, 5.4)
  c_h  = cost_base (1 + asks_hour / soft_cap) / (1 + L / stakes_relief)    rises with load, falls with stakes
  U(ask) = V_h - c_h

Decision rule (lexicographic, then expected utility):
  1. policy integrity broken            -> ask_human  (binding: policy_integrity)
  2. class requires human authority     -> ask_human  (binding: human_authority / hard value)
  3. irreversible and (1-q) > epsilon   -> ask_human  (binding: chance_constraint)
  4. d* = argmax over {stop, ask_human, verify, proceed} of U (ties go to the more cautious verdict)
  5. d* = proceed but level_eff < required_level -> verify  (binding: autonomy_level)
Monotone by construction: dU(proceed)/dq >= dU(d)/dq for every other d, and dU(proceed)/dL <= dU(d)/dL, so higher
reliability never raises escalation and higher stakes never lower it. gov_tests.py checks this on random scenarios.

Trace (L17): every term above, the binding constraint, and for each factor the nearest value that flips the verdict.
Reasons: exact Shapley attribution of the escalation margin U(d*) - U(proceed) over {uncertainty, stakes, human
reliability, human load} against a routine baseline (brief 1, 5.5). Lexicographic reasons are reported, not traded.
Tone (L13): assertiveness <= f(confidence) where f(c) = 3 (c - 0.5) / 0.5 on the calibrated confidence c = max(q, 1-q).
"""
import itertools, math

VERDICTS = ("stop", "ask_human", "verify", "proceed")     # cautious first: ties resolve toward safety
FACTORS = ("q", "loss", "human_acc", "asks_hour")
FACTOR_WORDS = {"q": "how likely this action is to fail", "loss": "how costly a failure here would be",
                "human_acc": "how often you judge this kind of action correctly", "asks_hour": "how busy you already are"}


def human_cost(s, P):
    h = P["human"]
    return h["cost_base"] * (1 + s["asks_hour"] / h["soft_cap_asks_per_hour"]) / (1 + s["loss"] / h["stakes_relief"])


def _u(q, L, P):
    G, C, cov = P["gain_success"], P["cost"], P["verify_coverage"]
    return {"proceed": q * G - (1 - q) * L - C["proceed"],
            "verify": q * G - (1 - q) * L * (1 - cov) - C["verify"],
            "stop": -C["stop"]}


def utilities(s, P):
    q, L, a = s["q"], s["loss"], s["human_acc"]
    U = _u(q, L, P)
    best_no_h = max(U.values())
    pg = a * q + (1 - a) * (1 - q)                      # P(human says go)
    vh = 0.0
    for p_ans, q_ans in ((pg, (a * q / pg) if pg > 0 else 0.0), (1 - pg, ((1 - a) * q / (1 - pg)) if pg < 1 else 0.0)):
        if p_ans > 0:
            vh += p_ans * max(_u(q_ans, L, P).values())
    ch = human_cost(s, P)
    U["ask_human"] = vh - ch
    return U, dict(V_h=vh, VOI=vh - best_no_h, c_h=ch)


def effective_q(s):
    b = s.get("self_budget", 1.0)
    return b * s["q_raw"] + (1 - b) * s.get("q_prior", s["q_raw"])


def decide(s, P, integrity_ok=True):
    """-> (verdict, binding constraint or None, utilities, voi terms). s['q'] must already be the effective q."""
    U, V = utilities(s, P)
    if not integrity_ok:
        return "ask_human", "policy_integrity", U, V
    if s["requires_human"]:
        return "ask_human", "human_authority:" + (s.get("hard_value") or "policy"), U, V
    if s["irreversible"] and (1 - s["q"]) > P["epsilon_irreversible"]:
        return "ask_human", "chance_constraint", U, V
    d = max(VERDICTS, key=lambda k: (U[k], -VERDICTS.index(k)))
    if d == "proceed":
        lvl = s["level"] - (1 if s.get("drift") else 0)
        if lvl < s["required_level"]:
            return "verify", "autonomy_level", U, V
    return d, None, U, V


# ---------------------------------------------------------------------------------------------- explanation
def _flip(s, P, integ, factor, grid, integer=False):
    """Nearest value of one factor that changes the verdict: coarse grid, then bisection toward the current value."""
    v0 = decide(s, P, integ)[0]
    cur = s[factor]; best = None

    def at(g):
        t = dict(s); t[factor] = g; return decide(t, P, integ)[0]
    for g in grid:
        v = at(g)
        if v != v0 and (best is None or abs(g - cur) < abs(best[0] - cur)):
            best = (g, v)
    if best is None:
        return None
    lo, hi = cur, best[0]                          # verdict(lo) == v0, verdict(hi) != v0
    for _ in range(0 if integer else 30):
        mid = (lo + hi) / 2
        if at(mid) == v0:
            lo = mid
        else:
            hi = mid
    hi = round(hi, 6)
    return dict(factor=factor, value_now=round(cur, 4), flips_at=hi, to=at(hi), direction="above" if hi > cur else "below")


GRIDS = {"q": [i / 40 for i in range(41)], "loss": [0, 0.5, 1, 2, 3, 5, 8, 12, 20, 30, 50, 80, 120, 200],
         "human_acc": [0.5 + i / 20 for i in range(11)], "asks_hour": [0, 1, 2, 4, 8, 15, 30, 60], "level": [0, 1, 2, 3, 4]}


def counterfactuals(s, P, integ=True):
    out = []
    for f in ("q", "loss", "human_acc", "asks_hour", "level"):
        c = _flip(s, P, integ, f, GRIDS[f], integer=f in ("level", "asks_hour"))
        if c:
            out.append(c)
    return out


def baseline(s, P):
    """The routine scenario the reasons are measured against: a read-class loss, the region's usual success rate,
    a human no better than a coin, and no load."""
    rd = next(c for c in P["classes"] if c["name"] == "read")["loss"]
    return dict(q=s.get("q_prior", 0.97), loss=rd, human_acc=0.5, asks_hour=0)


def shapley(s, P):
    """Exact Shapley values of the escalation margin m(s) = U(d*) - U(proceed) over FACTORS (16 evaluations)."""
    d = decide(s, P)[0]
    if d == "proceed":
        return {}
    base = baseline(s, P)

    def m(S):
        t = dict(s)
        for f in FACTORS:
            if f not in S:
                t[f] = base[f]
        U, _ = utilities(t, P)
        return U[d] - U["proceed"]
    n = len(FACTORS); phi = {}
    for f in FACTORS:
        rest = [g for g in FACTORS if g != f]; v = 0.0
        for r in range(n):
            for S in itertools.combinations(rest, r):
                w = math.factorial(r) * math.factorial(n - r - 1) / math.factorial(n)
                v += w * (m(set(S) | {f}) - m(set(S)))
        phi[f] = v
    return phi


def tone(s, verdict, binding):
    """Appraisal -> tone, under the honesty rule assertiveness <= f(confidence). Learned tone bandit: PROPOSED."""
    c = max(s["q"], 1 - s["q"]); cap = max(0.0, 3 * (c - 0.5) / 0.5)
    if binding and binding.startswith("human_authority") and s["loss"] >= 30:
        want, a = "firm", 2
    elif verdict in ("stop", "ask_human") and s["q"] < 0.5:
        want, a = "assertive", 3
    elif verdict == "proceed" and s["q"] > 0.95:
        want, a = "confident", 2
    else:
        want, a = "calm", 1
    while a > cap and a > 0:                              # never sound surer than the calibrated number
        want, a = {3: ("firm", 2), 2: ("calm", 1), 1: ("tentative", 0)}[a]
    return dict(tone=want, assertiveness=a, cap=round(cap, 3), confidence=round(c, 4))


def hedge(p):
    return "almost certainly" if p >= 0.95 else "likely" if p >= 0.7 else "possibly" if p >= 0.4 else "unlikely to"


def message(s, verdict, binding, phi, cls):
    fail = 1 - s["q"]
    if verdict == "proceed":
        return f"Go ahead: this kind of action has succeeded {s.get('N', 0) - s.get('F', 0)} of {s.get('N', 0)} times for this agent."
    lines = []
    if binding == "policy_integrity":
        lines.append("My policy file changed since you approved it, so I will not judge anything on my own until you re-approve it.")
    elif binding and binding.startswith("human_authority"):
        lines.append(f"I need you here: this is a '{cls}' action ({binding.split(':', 1)[1]}), which the policy reserves for a human.")
    elif binding == "chance_constraint":
        lines.append(f"I need you here: this cannot be undone and the failure chance ({fail:.1%}) is above the allowed limit.")
    elif binding == "autonomy_level":
        lines.append(f"Verify first: this agent has not yet earned autonomy for this kind of action (level {s['level']}"
                     f"{', demoted for a recent drift alarm' if s.get('drift') else ''}, needs {s['required_level']}).")
    else:
        head = {"ask_human": "I need you here.", "verify": "Verify first.", "stop": "Stop."}[verdict]
        lines.append(f"{head} The action will {hedge(fail)} fail ({fail:.1%}).")
    tot = sum(abs(v) for v in phi.values())
    if tot > 1e-9:
        for f, v in sorted(phi.items(), key=lambda kv: -abs(kv[1]))[:3]:
            if abs(v) / tot >= 0.05:
                lines.append(f"- {FACTOR_WORDS[f]} ({'+' if v >= 0 else '-'}{abs(v) / tot:.0%} of the reason)")
    return "\n".join(lines)


def govern(s, P, integ, cls_name, verify_hint=""):
    """Full decision + trace for one scenario. Pure function of (s, P, integ)."""
    verdict, binding, U, V = decide(s, P, integ)
    phi = shapley(s, P) if verdict != "proceed" and binding is None else {}
    tr = dict(verdict=verdict, binding=binding, cls=cls_name,
              factors={k: (round(v, 5) if isinstance(v, float) else v) for k, v in s.items()},
              U={k: round(v, 5) for k, v in U.items()}, VOI={k: round(v, 5) for k, v in V.items()},
              shapley={k: round(v, 5) for k, v in phi.items()},
              counterfactuals=counterfactuals(s, P, integ), tone=tone(s, verdict, binding),
              check=verify_hint if verdict == "verify" else None)
    tr["message"] = message(s, verdict, binding, phi, cls_name)
    return tr


def rederive(trace, P):
    """L17 test: recompute the verdict from the trace's own factors and policy only."""
    s = dict(trace["factors"])
    return decide(s, P, trace["binding"] != "policy_integrity")[0]
