"""L6 selection - the anti-router: which agent should do this kind of task?

Rule: Thompson sampling on the L2 posteriors. For region r, draw theta_k ~ Beta(alpha_kr, beta_kr) for every agent k
(discounted counts, so a vendor update that degrades an agent is forgotten at rate gamma), pick argmax_k theta_k - lambda c_k.
Regret against the best agent in hindsight grows like O(sqrt(K T log T)) for a stationary world; with forgetting it keeps
tracking after a change. A fixed rule ("tasks like this go to agent X") never adapts.

On this machine the human picks the agent, so there is no logged randomisation to evaluate selection off-policy on real
data. The test below is a SIMULATION with a known vendor update and is labelled as such everywhere it is reported.
"""
import numpy as np


class Thompson:
    """gamma < 1: forget every arm toward the prior each step.  cusum=True: keep full counts (gamma = 1) but run the
    L2 Bernoulli CUSUM per arm; on an alarm the arm's counts shrink by `shock`, so only a detected change is forgotten."""

    def __init__(self, K, gamma=1.0, prior=(1.0, 1.0), cost=None, lam=0.0, seed=0, cusum=False, h=5.0, shock=0.05, min_n=20):
        self.a = np.full(K, prior[0], float); self.b = np.full(K, prior[1], float); self.g = gamma
        self.p0 = prior; self.c = np.zeros(K) if cost is None else np.asarray(cost, float); self.lam = lam
        self.rng = np.random.default_rng(seed)
        self.cusum, self.h, self.shock, self.min_n = cusum, h, shock, min_n
        self.N = np.zeros(K); self.F = np.zeros(K); self.S = np.zeros(K); self.alarms = []

    def choose(self):
        return int(np.argmax(self.rng.beta(self.a, self.b) - self.lam * self.c))

    def update(self, k, o, t=None):
        if self.g < 1:
            self.a = self.g * self.a + (1 - self.g) * self.p0[0]; self.b = self.g * self.b + (1 - self.g) * self.p0[1]
        self.a[k] += o; self.b[k] += 1 - o
        if self.cusum:
            self.N[k] += 1; self.F[k] += 1 - o
            if self.N[k] >= self.min_n:
                p0 = min(max(self.F[k] / self.N[k], 1e-3), 0.45); p1 = min(0.5, max(2 * p0, p0 + 0.05))
                self.S[k] = max(0.0, self.S[k] + (np.log(p1 / p0) if o == 0 else np.log((1 - p1) / (1 - p0))))
                if self.S[k] > self.h:
                    self.S[k] = 0.0; self.alarms.append((t, k))
                    self.a[k] = self.p0[0] + self.shock * (self.a[k] - self.p0[0])
                    self.b[k] = self.p0[1] + self.shock * (self.b[k] - self.p0[1])
                    self.N[k] = 0; self.F[k] = 0


def simulate(T=6000, K=4, change_at=3000, seeds=20):
    """Synthetic world: K agents with success rates p; at change_at the best agent's vendor ships a worse model.
    Policies: NI Thompson with forgetting, Thompson without forgetting, fixed router (best agent at the start),
    uniform random. Returns mean cumulative regret at checkpoints, and the per-window regret slope."""
    p_before = np.array([0.90, 0.80, 0.70, 0.60])[:K]
    p_after = np.array([0.55, 0.80, 0.70, 0.60])[:K]
    marks = [500, 1000, 2000, 3000, 3500, 4000, 5000, 6000]
    res = {}
    cfg = {"NI Thompson + CUSUM reset (L2 drift rule)": dict(cusum=True),
           "Thompson, forgetting 0.999": dict(gamma=0.999), "Thompson, forgetting 0.99": dict(gamma=0.99),
           "Thompson, no forgetting": dict(), "fixed router (best at start)": None, "uniform random": None}
    for name, kw in cfg.items():
        regs = []
        for sd in range(seeds):
            rng = np.random.default_rng(100 + sd)
            pol = Thompson(K, seed=sd, **(kw or {}))
            cum = 0.0; curve = []
            for t in range(T):
                p = p_before if t < change_at else p_after
                if name.startswith("fixed"):
                    k = int(np.argmax(p_before))
                elif name.startswith("uniform"):
                    k = int(rng.integers(K))
                else:
                    k = pol.choose()
                o = int(rng.random() < p[k])
                if not name.startswith(("fixed", "uniform")):
                    pol.update(k, o, t)
                cum += p.max() - p[k]; curve.append(cum)
            regs.append([curve[m - 1] for m in marks])
        r = np.mean(regs, 0)
        res[name] = dict(regret_at={m: round(float(v), 1) for m, v in zip(marks, r)},
                         slope_last_1000=round(float((r[-1] - r[-2]) / 1000), 4))
    return res


if __name__ == "__main__":
    import json
    print(json.dumps(simulate(), indent=1))
