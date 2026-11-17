"""L2 capability beliefs: who is good at what, how sure we are, and whether it just changed.

Definitions (brief 1, 4.3 L2)
  agent k = the model that issued the action; region R(x) = kind of action (cc_core.head_of: the program a shell command
  runs, the file type a file tool touches, the tool name otherwise). Regions are derived from the data, not listed.
  For every key (global, region, agent x region) keep discounted counts of successes s and failures f.

Update rule (O(1) per event, no retraining)
  s <- gamma * s + o,   f <- gamma * f + (1 - o)          o = 1 if the action succeeded
  Undiscounted counts N, F are kept too (reference rate for drift and for the report card).

Hierarchical prior (population prior -> personal posterior, brief 1 5.7 / 6.4)
  m_global = (S + 1) / (N + 2)
  m_region = (s_r + k * m_global) / (n_r + k)
  posterior for agent x region:  Beta( s_kr + k * m_region,  f_kr + k * (1 - m_region) )
  A new agent starts at the region's pooled rate and moves to its own rate as evidence arrives.

Drift (vendor update, "right on Monday, wrong on Tuesday")
  Bernoulli CUSUM on the failure stream of each key, reference p0 = undiscounted failure rate so far,
  alternative p1 = min(0.5, max(2 p0, p0 + 0.05)):
     S <- max(0, S + llr(o)),  llr(fail) = ln(p1/p0),  llr(ok) = ln((1-p1)/(1-p0));  alarm when S > h.
  On alarm: the alarm is logged, S resets, old discounted counts shrink by `shock` (new evidence dominates) and the key is
  marked drifting for `hold` events, which demotes its autonomy level by one (brief 2, 3.4: demotion is automatic).

Lower confidence bound used for autonomy: LCB = Beta quantile (1 - conf) of the agent x region posterior.
Hoeffding: n >= ln(2/delta) / (2 eps^2) probes to know a rate within eps with confidence 1-delta (brief 1, 7.5).
"""
import math, json
from scipy.stats import beta as _beta
import cc_core


def hoeffding_n(eps=0.05, delta=0.05):
    return int(math.ceil(math.log(2 / delta) / (2 * eps * eps)))


class Key:
    __slots__ = ("s", "f", "N", "F", "S", "alarms", "drift_until", "last_ts", "reasons")

    def __init__(self):
        self.s = 0.0; self.f = 0.0; self.N = 0; self.F = 0; self.S = 0.0
        self.alarms = []; self.drift_until = -1; self.last_ts = None; self.reasons = {}


class Beliefs:
    def __init__(self, gamma=0.995, k=5.0, h=5.0, min_n=20, shock=0.3, hold=30):
        self.gamma, self.k, self.h, self.min_n, self.shock, self.hold = gamma, k, h, min_n, shock, hold
        self.keys = {}

    # ------------------------------------------------------------------ keys
    @staticmethod
    def agent_of(rec):
        return rec.get("model") or "?"

    @staticmethod
    def region_of(rec):
        return cc_core.head_of(rec["tool"], rec["text"], rec.get("target", ""))

    def _get(self, key):
        k = self.keys.get(key)
        if k is None:
            k = self.keys[key] = Key()
        return k

    # ------------------------------------------------------------------ posterior
    def _mean(self, key, prior):
        k = self.keys.get(key)
        if k is None:
            return prior
        return (k.s + self.k * prior) / (k.s + k.f + self.k)

    def posterior(self, agent, region, unit="kind"):
        """dict with mean success, alpha, beta, discounted n, raw N, LCB, drift flag, and the prior chain.
        unit='kind': agent x kind of command (region = head);  unit='class': agent x action class (region = class name)."""
        g = self.keys.get(("global",))
        m0 = (g.N - g.F + 1) / (g.N + 2) if g else 0.5
        pk, ak = (("region", region), ("agent_region", agent, region)) if unit == "kind" else (("class", region), ("agent_class", agent, region))
        mr = self._mean(pk, m0)
        k = self.keys.get(ak)
        s, f = (k.s, k.f) if k else (0.0, 0.0)
        a, b = s + self.k * mr, f + self.k * (1 - mr)
        drift = bool(k and k.N <= k.drift_until)
        return dict(mean=a / (a + b), alpha=a, beta=b, n=s + f, N=(k.N if k else 0), F=(k.F if k else 0),
                    prior_global=m0, prior_region=mr, drift=drift, alarms=len(k.alarms) if k else 0)

    def lcb(self, post, conf=0.95):
        return float(_beta.ppf(1 - conf, post["alpha"], post["beta"]))

    def p_fail(self, rec):
        return 1.0 - self.posterior(self.agent_of(rec), self.region_of(rec))["mean"]

    # ------------------------------------------------------------------ update
    def _cusum(self, key, k, fail, ts):
        if k.N < self.min_n:
            return None
        p0 = min(max(k.F / k.N, 1e-3), 0.45)
        p1 = min(0.5, max(2 * p0, p0 + 0.05))
        k.S = max(0.0, k.S + (math.log(p1 / p0) if fail else math.log((1 - p1) / (1 - p0))))
        if k.S > self.h:
            k.S = 0.0; k.s *= self.shock; k.f *= self.shock; k.drift_until = k.N + self.hold
            ev = dict(key=list(key), ts=ts, n=k.N, p0=round(p0, 4))
            k.alarms.append(ev)
            return ev
        return None

    def update(self, rec, reason=None, cls=None):
        """Feed one resolved action (cls = its policy action class, if known). Returns the drift alarms it raised."""
        fail = int(rec["outcome"] != "ok"); o = 1 - fail; ts = rec.get("ts")
        agent, region = self.agent_of(rec), self.region_of(rec)
        alarms = []
        keys = [("global",), ("region", region), ("agent", agent), ("agent_region", agent, region)]
        if cls:
            keys += [("class", cls), ("agent_class", agent, cls)]
        for key in keys:
            k = self._get(key)
            k.s = self.gamma * k.s + o; k.f = self.gamma * k.f + fail
            k.N += 1; k.F += fail; k.last_ts = ts
            if fail and reason:
                k.reasons[reason] = k.reasons.get(reason, 0) + 1
            if key[0] in ("agent_region", "agent", "agent_class"):
                ev = self._cusum(key, k, fail, ts)
                if ev:
                    alarms.append(ev)
        return alarms

    # ------------------------------------------------------------------ export
    def table(self, kind="agent_region"):
        out = []
        for key, k in self.keys.items():
            if key[0] == kind:
                out.append(dict(key=list(key[1:]), N=k.N, F=k.F, s=round(k.s, 2), f=round(k.f, 2), alarms=k.alarms,
                                drifting=k.N <= k.drift_until, reasons=k.reasons, last_ts=k.last_ts))
        return out

    def dump(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict(params=dict(gamma=self.gamma, k=self.k, h=self.h, min_n=self.min_n, shock=self.shock, hold=self.hold),
                           agent_region=self.table(), agent=self.table("agent"), region=self.table("region")), f, indent=0)
