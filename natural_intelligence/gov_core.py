"""The governor: one object that holds NI's state S_t = (B_t beliefs, M_t human model, Z_t scenario, policy, self-trust)
and turns (action, gate score) into a verdict with a trace. Brief 1 section 4.1; brief 2 section 3.

  observe(rec)        L1 + L2: a resolved action updates the beliefs (O(1)), with its failure reason kept
  scenario(rec, risk) L10: the named, measured factor vector s for this action
  govern(rec, risk)   L5/L11/L17: verdict in {proceed, verify, ask_human, stop} + reasons + counterfactuals
  level(post)         brief 2, 3.4: level = max{L : LCB_95(r) > tau_L and N >= n_min(L)}

Everything is rebuilt from the harvested action store at start-up (the beliefs are sufficient statistics, so replaying
them is exact), then kept current online. No GPU, no retraining.
"""
import os, json, time, collections
import gov_policy, gov_beliefs, gov_decide, gov_ledger
import cc_core

SELF_STATE = os.path.join(gov_ledger.GOV_DIR, "self_state.json")


def load_self_state():
    if os.path.exists(SELF_STATE):
        try:
            return json.load(open(SELF_STATE, encoding="utf-8"))
        except Exception:
            pass
    return dict(budget=1.0, calibration=None, note="no self-check run yet")


def apply_calibration(risk, cal):
    """Piecewise-linear map (isotonic knots) adopted by gov_self only after it beat the raw score on a later slice."""
    if not cal:
        return risk
    xs, ys = cal["x"], cal["y"]
    if risk <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if risk <= xs[i]:
            t = (risk - xs[i - 1]) / max(xs[i] - xs[i - 1], 1e-12)
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


class Governor:
    def __init__(self, beliefs=None, ledger=True, policy_path=None, lock_path=None):
        self.policy_path = policy_path or gov_policy.POLICY; self.lock_path = lock_path or gov_policy.LOCK
        self.selfst = load_self_state()
        bp = self.selfst.get("beliefs") or {}
        self.B = beliefs or gov_beliefs.Beliefs(gamma=bp.get("gamma", 0.995), k=bp.get("k", 5.0))
        self.human = list(gov_policy.load(self.policy_path, self.lock_path)[0]["human"]["accuracy_prior"])
        self.asks = collections.deque()
        self.L = gov_ledger.Ledger() if ledger else None
        self.alarms = []

    @property
    def policy(self):
        return gov_policy.load(self.policy_path, self.lock_path)

    # ------------------------------------------------------------------ learning
    def observe(self, rec):
        P, _ = self.policy
        reason = gov_policy.failure_reason(rec["outcome"], rec.get("err_head", ""), P)
        cls = gov_policy.classify(rec["tool"], rec["text"], P)[0]["name"]
        al = self.B.update(rec, reason, cls)
        self.alarms.extend(al)
        return reason, al

    def observe_human(self, correct):
        """The human judged an action and the outcome later showed whether they were right (brief 2, 5: the rater is checked)."""
        self.human[0 if correct else 1] += 1

    def warm(self, recs):
        for r in sorted(recs, key=lambda r: r.get("ts") or 0):
            if r["outcome"] != "unknown":
                self.observe(r)

    # ------------------------------------------------------------------ scenario
    def level(self, post):
        P, _ = self.policy
        A = P["autonomy"]; lcb = self.B.lcb(post, A["lcb_confidence"]); lvl = 0
        for L, (tau, nmin) in enumerate(zip(A["tau"], A["n_min"]), start=1):
            if lcb > tau and post["N"] >= nmin:
                lvl = L
        return lvl, lcb

    def autonomy_unit(self):
        u = self.policy[0]["autonomy"].get("unit", "kind")
        return self.selfst.get("autonomy_unit", "kind") if u == "validate" else u

    def asks_last_hour(self, now):
        while self.asks and self.asks[0] < now - 3600:
            self.asks.popleft()
        return len(self.asks)

    def scenario(self, rec, risk=None, now=None):
        P, _ = self.policy
        now = now or rec.get("ts") or time.time()
        cls, env, loss = gov_policy.classify(rec["tool"], rec["text"], P)
        agent, region = self.B.agent_of(rec), self.B.region_of(rec)
        post = self.B.posterior(agent, region)                          # finer: kind of command (counts prior, drift)
        unit = self.autonomy_unit()
        apost = post if unit == "kind" else self.B.posterior(agent, cls["name"], unit="class")
        lvl, lcb = self.level(apost)
        q_prior = post["mean"]
        post = dict(post); post["drift"] = post["drift"] or apost["drift"]
        if risk is None:
            q_raw, src = q_prior, "beliefs"
        else:
            q_raw, src = 1.0 - apply_calibration(float(risk), self.selfst.get("calibration")), "gate"
        b = float(self.selfst.get("budget", 1.0)) if src == "gate" else 1.0
        s = dict(q_raw=q_raw, q_prior=q_prior, self_budget=b, q_source=src, loss=loss, env=env,
                 irreversible=bool(cls.get("irreversible")), requires_human=bool(cls.get("requires_human")),
                 hard_value=cls.get("hard_value"), level=lvl, lcb=lcb, required_level=int(cls.get("required_level", 2)),
                 drift=post["drift"], N=post["N"], F=post["F"], agent=agent, region=region,
                 human_acc=self.human[0] / sum(self.human), asks_hour=self.asks_last_hour(now))
        s["q"] = gov_decide.effective_q(s)
        return s, cls

    # ------------------------------------------------------------------ decision
    def govern(self, rec, risk=None, now=None, record=True):
        P, integ = self.policy
        s, cls = self.scenario(rec, risk, now)
        tr = gov_decide.govern(s, P, integ["ok"], cls["name"], cls.get("verify", ""))
        tr["integrity"] = {k: integ[k] for k in ("ok", "reason")}
        tr["self"] = dict(budget=self.selfst.get("budget"), calibrated=bool(self.selfst.get("calibration")))
        if tr["verdict"] == "ask_human" and integ["ok"]:            # a locked governor's blanket asks are not load
            self.asks.append(now or rec.get("ts") or time.time())
        if record and self.L is not None:
            safe_text = "" if cls["name"] == "secret_exposure" else rec["text"][:200]
            self.L.append("decision", dict(id=rec.get("id"), ts=rec.get("ts"), agent=s["agent"], region=s["region"],
                                           x=safe_text, verdict=tr["verdict"], binding=tr["binding"], cls=cls["name"],
                                           q=round(s["q"], 5), loss=s["loss"], level=s["level"]))
        return tr

    def record_outcome(self, rec, reason):
        if self.L is not None:
            v = dict(quality=int(rec["outcome"] == "ok"), harm=int(rec["outcome"] != "ok"),
                     consent_violation=None, latency_s=round((rec.get("ts_res") or 0) - (rec.get("ts") or 0), 3))
            self.L.append("outcome", dict(id=rec.get("id"), o=rec["outcome"], reason=reason, h=None, v=v))
