# brain/parallel_worlds.py
"""
Parallel worlds: the same task is played out in several worlds at once — each world uses a
different model, strategy or condition — and the brain keeps the outcome with the highest
expected utility.

    task ──┬─▶ world A (e.g. the brain's own 8 layers)  ─▶ outcome A ─▶ score ─┐
           ├─▶ world B (e.g. local Qwen via Ollama)      ─▶ outcome B ─▶ score ─┼─▶ choose max EU ─▶ act
           └─▶ world C (e.g. HojaigaOmni / Claude / ...) ─▶ outcome C ─▶ score ─┘
                                                     every world's score ─▶ governor switchboard

Score of a world = its own evidence (verification, grounding) blended with agreement between
worlds (independent worlds reaching the same answer are more believable), and the governor's
prior belief about that model in this task domain. Worlds that were not chosen are recorded as
counterfactual outcomes, so the brain learns from every world it imagined, not just the one it lived.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import numpy as np


@dataclass
class World:
    name: str                                   # also the governor model name
    run: Callable[[], Any]                      # produces the outcome
    score: Callable[[Any], float]               # evidence in [0, 1] for this outcome
    text_of: Callable[[Any], str] = lambda o: str(o)
    cost: float = 0.0


class ParallelWorlds:
    def __init__(self, governor=None, embed: Optional[Callable[[str], np.ndarray]] = None, max_workers: int = 4,
                 agreement_weight: float = 0.25, prior_weight: float = 0.2):
        self.governor = governor
        self.embed = embed
        self.pool = ThreadPoolExecutor(max_workers=max_workers)
        self.agreement_weight, self.prior_weight = agreement_weight, prior_weight

    def _timed(self, w: World):
        t0 = time.time()
        try:
            return w.run(), None, time.time() - t0
        except Exception as exc:
            return None, f"{type(exc).__name__}: {exc}", time.time() - t0

    def explore(self, domain: str, worlds: List[World], timeout: float = 120.0) -> Dict[str, Any]:
        futures = {w.name: self.pool.submit(self._timed, w) for w in worlds}
        results = []
        for w in worlds:
            try:
                out, err, lat = futures[w.name].result(timeout=timeout)
            except Exception as exc:
                out, err, lat = None, f"timeout: {exc}", timeout
            evidence = 0.0 if out is None else float(np.clip(w.score(out), 0.0, 1.0))
            results.append({"world": w.name, "outcome": out, "error": err, "latency": round(lat, 3),
                            "evidence": round(evidence, 4), "text": "" if out is None else w.text_of(out), "cost": w.cost})
        # agreement: how much each world's outcome resembles the others' (consensus across worlds)
        live = [r for r in results if r["outcome"] is not None and r["text"]]
        if self.embed and len(live) > 1:
            vecs = {r["world"]: self.embed(r["text"]) for r in live}
            for r in live:
                others = [float(np.dot(vecs[r["world"]], vecs[o["world"]])) for o in live if o is not r]
                r["agreement"] = round(max(0.0, float(np.mean(others))), 4)
        for r in results:
            prior = self.governor.belief(domain, r["world"])["p_success"] if self.governor else 0.5
            r["prior"] = round(prior, 3)
            base = (1 - self.agreement_weight - self.prior_weight) * r["evidence"] + \
                self.agreement_weight * r.get("agreement", r["evidence"]) + self.prior_weight * prior
            r["eu"] = round(base - (self.governor.cost_weight * r["cost"] if self.governor else 0.0)
                            - (self.governor.latency_weight * r["latency"] if self.governor else 0.0), 4) \
                if r["outcome"] is not None else -1.0
        chosen = max(results, key=lambda r: r["eu"])
        if self.governor:
            for r in results:
                self.governor.record(domain, r["world"], r["evidence"] if r["outcome"] is not None else 0.0,
                                     r["latency"], counterfactual=r is not chosen,
                                     note="chosen" if r is chosen else "imagined")
        return {"chosen": chosen["world"], "outcome": chosen["outcome"],
                "worlds": [{k: v for k, v in r.items() if k not in ("outcome",)} for r in results]}
