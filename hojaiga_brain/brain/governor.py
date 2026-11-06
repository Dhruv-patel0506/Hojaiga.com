# brain/governor.py
"""
AI model governor — the brain as the manager of AI models.

Every model the brain can use is registered here: its own networks (HojaigaOmni, the inner LLM,
classifiers the conveyor trained) and outside ones (local Ollama models, Claude, any HTTP model).

The SWITCHBOARD (SQLite, in the workspace) is the controlling switch: for every (task domain, model)
pair it stores a Beta(α, β) belief about the model's success rate, its average latency and cost.
Every decision reads it; every outcome writes it.

Decision rule (expected utility):   EU = P(success) · value − cost_weight · cost − latency_weight · seconds
  * exploit: rank by the posterior mean
  * explore: Thompson sampling — draw P(success) from each Beta, so new or uncertain models still get tried
Models whose success is clearly poor after enough trials are retired automatically (and can be revived).
"""
import json
import math
import random
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ModelCard:
    name: str
    kind: str                                  # internal | local | external
    capabilities: List[str]                    # e.g. ["answer", "describe_image", "classify"]
    invoke: Callable[..., Any]
    cost: float = 0.0                          # relative cost per call (0 = free/local)
    meta: Dict[str, Any] = field(default_factory=dict)


class ModelGovernor:
    def __init__(self, db_path: Path, value: float = 1.0, cost_weight: float = 0.3, latency_weight: float = 0.02,
                 retire_after: int = 20, retire_below: float = 0.25, seed: Optional[int] = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.value, self.cost_weight, self.latency_weight = value, cost_weight, latency_weight
        self.retire_after, self.retire_below = retire_after, retire_below
        self.rng = random.Random(seed)
        self.models: Dict[str, ModelCard] = {}
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS switchboard (domain TEXT, model TEXT, alpha REAL, beta REAL, uses INTEGER,
                latency REAL, retired INTEGER DEFAULT 0, updated REAL, PRIMARY KEY (domain, model));
            CREATE TABLE IF NOT EXISTS outcomes (ts REAL, domain TEXT, model TEXT, success REAL, latency REAL,
                counterfactual INTEGER, note TEXT);
        """)

    # ------------------------------------------------------------------ registry
    def register(self, name: str, capabilities: List[str], invoke: Callable[..., Any], kind: str = "internal",
                 cost: float = 0.0, **meta) -> None:
        self.models[name] = ModelCard(name, kind, capabilities, invoke, cost, meta)

    def unregister(self, name: str) -> None:
        self.models.pop(name, None)

    def candidates(self, capability: str) -> List[ModelCard]:
        return [m for m in self.models.values() if capability in m.capabilities]

    # ------------------------------------------------------------------ switchboard
    def _row(self, domain: str, model: str):
        r = self.db.execute("SELECT alpha, beta, uses, latency, retired FROM switchboard WHERE domain=? AND model=?",
                            (domain, model)).fetchone()
        return r or (1.0, 1.0, 0, 0.0, 0)

    def belief(self, domain: str, model: str) -> Dict[str, float]:
        a, b, uses, lat, retired = self._row(domain, model)
        return {"p_success": a / (a + b), "alpha": a, "beta": b, "uses": uses, "latency": lat, "retired": bool(retired)}

    def expected_utility(self, domain: str, card: ModelCard, sample: bool = False) -> float:
        a, b, _, lat, _ = self._row(domain, card.name)
        p = self.rng.betavariate(a, b) if sample else a / (a + b)
        return p * self.value - self.cost_weight * card.cost - self.latency_weight * lat

    def rank(self, capability: str, domain: str, explore: bool = True, include_retired: bool = False) -> List[Dict[str, Any]]:
        with self.lock:
            out = []
            for c in self.candidates(capability):
                bel = self.belief(domain, c.name)
                if bel["retired"] and not include_retired:
                    continue
                out.append({"model": c.name, "kind": c.kind, "p_success": round(bel["p_success"], 3),
                            "uses": bel["uses"], "eu": round(self.expected_utility(domain, c, sample=explore), 4)})
            return sorted(out, key=lambda r: -r["eu"])

    def choose(self, capability: str, domain: str, explore: bool = True) -> Optional[ModelCard]:
        ranked = self.rank(capability, domain, explore)
        return self.models[ranked[0]["model"]] if ranked else None

    def record(self, domain: str, model: str, success: float, latency: float = 0.0, counterfactual: bool = False,
               note: str = "") -> Dict[str, Any]:
        """success in [0, 1]. Counterfactual outcomes (branches that were simulated but not chosen) count
        half, so the switchboard learns from every world, not only the one that was acted on."""
        w = 0.5 if counterfactual else 1.0
        with self.lock:
            a, b, uses, lat, retired = self._row(domain, model)
            a, b = a + w * success, b + w * (1 - success)
            uses += 1
            lat = latency if uses == 1 else 0.8 * lat + 0.2 * latency
            p = a / (a + b)
            if uses >= self.retire_after and p < self.retire_below:
                retired = 1
            self.db.execute("INSERT OR REPLACE INTO switchboard VALUES (?,?,?,?,?,?,?,?)",
                            (domain, model, a, b, uses, lat, retired, time.time()))
            self.db.execute("INSERT INTO outcomes VALUES (?,?,?,?,?,?,?)",
                            (time.time(), domain, model, success, latency, int(counterfactual), note))
            self.db.commit()
        return {"model": model, "domain": domain, "p_success": round(p, 3), "uses": uses, "retired": bool(retired)}

    def revive(self, domain: str, model: str) -> None:
        with self.lock:
            self.db.execute("UPDATE switchboard SET retired=0, alpha=1, beta=1, uses=0 WHERE domain=? AND model=?",
                            (domain, model))
            self.db.commit()

    def invoke(self, capability: str, domain: str, *args, **kwargs) -> Dict[str, Any]:
        card = self.choose(capability, domain)
        if card is None:
            raise LookupError(f"no model registered for {capability}")
        t0 = time.time()
        result = card.invoke(*args, **kwargs)
        return {"model": card.name, "result": result, "latency": time.time() - t0}

    # ------------------------------------------------------------------ reporting
    def report(self) -> Dict[str, Any]:
        rows = self.db.execute("SELECT domain, model, alpha, beta, uses, latency, retired FROM switchboard "
                               "ORDER BY domain, alpha/(alpha+beta) DESC").fetchall()
        return {"models": {n: {"kind": c.kind, "capabilities": c.capabilities, "cost": c.cost}
                           for n, c in self.models.items()},
                "switchboard": [{"domain": d, "model": m, "p_success": round(a / (a + b), 3), "uses": u,
                                 "latency_s": round(l, 3), "retired": bool(r)} for d, m, a, b, u, l, r in rows]}

    def plot(self, out: Path) -> Optional[str]:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return None
        rows = self.report()["switchboard"]
        if not rows:
            return None
        labels = [f"{r['domain']}\n{r['model']}" for r in rows]
        fig, ax = plt.subplots(figsize=(max(6, len(rows) * 0.9), 4))
        ax.bar(range(len(rows)), [r["p_success"] for r in rows],
               color=["#999" if r["retired"] else "#3b6fd8" for r in rows])
        ax.set_xticks(range(len(rows)), labels, rotation=45, ha="right", fontsize=8)
        ax.set_ylim(0, 1)
        ax.set_ylabel("believed success rate")
        ax.set_title("Model governor switchboard (grey = retired)")
        fig.tight_layout()
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=110)
        plt.close(fig)
        return str(out)
