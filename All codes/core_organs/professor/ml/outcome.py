"""
professor.ml.outcome -- the ACTION-OUTCOME model: given an application, its toolkit, a control (role, label), the route about to be used and the safety class, what will happen?

  P(ok)        will the action change anything at all?
  P(effect)    no_effect | state_change | context_change | opens_dialog | visual_only

It learns ONLINE from the state-transition log (professor.history): every action the Professor performs - probing, executing a guide's procedure, exploring - is a labelled example
(the label is what the before / after delta measured), so the model keeps training for as long as the automation is used (see ml.learner). What it is for:
  * ROUTE ORDER   `rank_routes()` orders the routes of a verb (command / shortcut / control / click / value) by predicted P(ok), with a count-based exploration bonus so a route that was
                  never tried in this toolkit is still tried now and then; the planner blends it with the static ladder - the model can re-order routes, it can NEVER relax a safety gate
  * EXPECTATION   a step whose predicted P(ok) is high but whose measured effect was 'no_effect' is an anomaly worth recording (the app changed, or the route stopped working)
  * HONESTY       `metrics()` reports the PREQUENTIAL accuracy (every example is predicted BEFORE the model learns from it), against the majority-class baseline - a model that does not beat
                  the baseline says so.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .nn import SparseMLP, hash_features

EFFECTS = ["no_effect", "state_change", "context_change", "opens_dialog", "visual_only"]
N_IN = 2048
WINDOW = 500
_WORD = re.compile(r"[a-z0-9]+")


def route_kind(route: str, primitive: str = "") -> str:
    """'shortcut:Ctrl+M' -> 'shortcut'; a probe row's 'UIA Invoke' -> its primitive."""
    r = (route or "").lower()
    if ":" in r and r.split(":", 1)[0] in ("value", "command", "shortcut", "control", "click"):
        return r.split(":", 1)[0]
    return {"key": "shortcut", "invoke": "control", "select": "control", "toggle": "control", "set_value": "value", "command": "command", "click": "click"}.get(primitive or "", primitive or r or "control")


def context_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """A history row (or an executor attempt) -> the context the model sees."""
    note = row.get("s0_note") or ""
    m = re.match(r"(\d+) controls", note)
    ctx = {"app": row.get("app_key", ""), "toolkit": row.get("toolkit", "") or "", "role": row.get("role", "") or "", "route": route_kind(row.get("route", ""), row.get("primitive", "")),
           "safety": row.get("safety", "") or "", "source": row.get("source", "") or "", "archetype": row.get("archetype", "") or "", "label": row.get("target", "") or "",
           "has_shortcut": bool((row.get("detail") or {}).get("shortcut")) or str(row.get("route", "")).startswith("shortcut"), "n_controls": int(m.group(1)) if m else 0}
    if row.get("prev_effect"):
        ctx["prev_effect"] = row["prev_effect"]
    return ctx


def tokens(ctx: Dict[str, Any]) -> List[Tuple[str, float]]:
    app, tk, role, route, safety = ctx.get("app", ""), ctx.get("toolkit", ""), ctx.get("role", ""), ctx.get("route", ""), ctx.get("safety", "")
    words = _WORD.findall((ctx.get("label") or "").lower())[:4]
    t: List[Tuple[str, float]] = [("bias", 1.0), (f"route={route}", 1.0), (f"toolkit={tk}", 0.7), (f"role={role}", 0.7), (f"safety={safety}", 0.5), (f"src={ctx.get('source', '')}", 0.4),
                                 (f"arch={ctx.get('archetype', '')}", 0.4), (f"tk|route={tk}|{route}", 1.0), (f"role|route={role}|{route}", 1.0), (f"tk|role|route={tk}|{role}|{route}", 1.0),
                                 (f"app|route={app}|{route}", 0.8), (f"app|role|route={app}|{role}|{route}", 0.8), (f"safety|route={safety}|{route}", 0.6)]
    for w in words:
        t.append((f"w={w}", 0.5))
        t.append((f"w|route={w}|{route}", 0.5))
    if ctx.get("has_shortcut"):
        t.append(("has_shortcut", 0.6))
        t.append((f"shortcut|route={route}", 0.5))
    n = int(ctx.get("n_controls") or 0)
    t.append((f"nctl={min(8, int(math.log2(n + 1)))}", 0.4))
    for key, wgt in (("hist_lr", 1.0), ("hist_l", 0.6)):                    # what happened before to THIS control (on this route / on any route): the strongest signal there is
        h = ctx.get(key)
        if h is not None:
            okn, n = h
            b = "none" if n == 0 else ("all_ok" if okn == n else ("all_fail" if okn == 0 else ("mostly_ok" if okn * 2 > n else "mostly_fail")))
            c = "1" if n == 1 else ("2-3" if n <= 3 else "4+")
            t.append((f"{key}={b}", wgt))
            t.append((f"{key}={b}|n={c}", wgt * 0.6))
            t.append((f"{key}={b}|route={route}", wgt * 0.6))
    prev = ctx.get("prev_effect")
    if prev:
        t.append((f"prev={prev}", 0.6))
        t.append((f"prev|route={prev}|{route}", 0.6))
    return t


class OutcomeModel:
    def __init__(self, path: Optional[str] = None, hidden: int = 64, lr: float = 0.007, seed: int = 7):
        self.path = path
        self.net = SparseMLP(N_IN, hidden, {"effect": len(EFFECTS), "ok": 1}, lr=lr, seed=seed)
        self.seen = 0
        self.route_counts: Dict[str, int] = {}                  # "toolkit|route" -> times observed (exploration bonus)
        self.eff_counts = np.zeros(len(EFFECTS))
        self.preq = {"n": 0, "ok_correct": 0, "eff_correct": 0, "ok_brier": 0.0, "base_ok_correct": 0, "base_eff_correct": 0, "pos": 0}
        self.recent: List[Tuple[Any, Dict[str, Any]]] = []       # reservoir for replay
        self.hist: Dict[str, List[int]] = {}                      # "app|label|route" and "app|label" -> [ok, n]: the per-control outcome memory the features read
        self.window: List[int] = []                               # the last WINDOW prequential hits (1 / 0): the CURRENT accuracy (the all-time figure carries the cold start)
        self.last_saved = 0.0
        self.updates = 0
        self._last_sig = None                                     # the event the last observe() saw (burst guard, see BURST_CAP)
        self._streak = 0                                          # how many times in a row that exact same event has arrived
        if path and os.path.isfile(path):
            self._load(path)

    # ------------------------------------------------------------------------------------------------------ predict
    @staticmethod
    def _keys(ctx: Dict[str, Any]) -> Tuple[str, str]:
        lab = " ".join(_WORD.findall((ctx.get("label") or "").lower()))[:60]
        return f"{ctx.get('app', '')}|{lab}|{ctx.get('route', '')}", f"{ctx.get('app', '')}|{lab}"

    def with_history(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """The context plus what this model has SEEN happen to the same control before (read before learning the example: prequential stays honest)."""
        if not ctx.get("label"):
            return ctx
        k1, k2 = self._keys(ctx)
        return {**ctx, "hist_lr": tuple(self.hist.get(k1, (0, 0))), "hist_l": tuple(self.hist.get(k2, (0, 0)))}

    def featurize(self, ctx: Dict[str, Any]):
        if "hist_lr" not in ctx:
            ctx = self.with_history(ctx)
        return hash_features(tokens(ctx), N_IN)

    def predict(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        out = self.net.predict(self.featurize(ctx))
        p_eff = out["effect"]
        return {"p_ok": float(out["ok"][0]), "effect": {e: round(float(p), 4) for e, p in zip(EFFECTS, p_eff)}, "likely_effect": EFFECTS[int(np.argmax(p_eff))], "seen": self.seen}

    def rank_routes(self, ctx: Dict[str, Any], routes: Sequence[str], prior_weight: float = 0.35, min_seen: int = 40) -> List[Tuple[str, float]]:
        """[(route_kind, score)] best first. Blends the learned P(ok) with the static ladder's order (a prior) and an exploration bonus for routes this toolkit has rarely seen.
        Until the model has seen `min_seen` examples the static order wins outright."""
        kinds = list(dict.fromkeys(routes))
        n = len(kinds)
        out = []
        for i, k in enumerate(kinds):
            prior = 1.0 - i / max(1, n)                                   # the ladder's own preference
            if self.seen < min_seen:
                out.append((k, prior))
                continue
            p = float(self.net.predict(self.featurize({**ctx, "route": k}))["ok"][0])
            bonus = 0.15 / math.sqrt(1 + self.route_counts.get(f"{ctx.get('toolkit', '')}|{k}", 0))
            out.append((k, (1 - prior_weight) * p + prior_weight * prior + bonus))
        out.sort(key=lambda t: -t[1])
        return out

    # ------------------------------------------------------------------------------------------------------- learn
    BURST_CAP = 3                                                  # an IDENTICAL consecutive example trains the net and enters the reservoir at most this many times

    @staticmethod
    def _signature(ctx: Dict[str, Any], y_eff: int, y_ok: float):
        # the example AS AN EVENT, not as features: the featurizer mixes growing history counters in, so two identical repeats rarely share byte-identical features (measured) - the identity
        # is the plain context (app, label, route, effect...) plus the labels themselves.
        core = {k: v for k, v in sorted(ctx.items()) if isinstance(v, (str, int, float, bool, type(None))) and k not in ("hist_lr", "hist_l")}
        return repr(core), y_eff, y_ok

    def observe(self, ctx: Dict[str, Any], effect: str, ok: bool, train: bool = True) -> None:
        """Test-then-train: the example is PREDICTED first (prequential metrics), then learned."""
        if effect not in EFFECTS:
            effect = "no_effect" if not ok else "state_change"
        f = self.featurize(ctx)
        y_eff = EFFECTS.index(effect)
        y_ok = 1.0 if ok else 0.0
        if self.seen >= 1:
            pr = self.net.predict(f)
            p = self.preq
            p["n"] += 1
            hit = int((pr["ok"][0] >= 0.5) == bool(ok))
            p["ok_correct"] += hit
            self.window = (self.window + [hit])[-WINDOW:]
            p["eff_correct"] += int(int(np.argmax(pr["effect"])) == y_eff)
            p["ok_brier"] += float((pr["ok"][0] - y_ok) ** 2)
            p["base_ok_correct"] += int((p["pos"] * 2 >= self.seen) == bool(ok))                  # majority-class baseline (using only the past)
            p["base_eff_correct"] += int(int(np.argmax(self.eff_counts)) == y_eff)
        if ctx.get("label"):
            for k in self._keys(ctx):
                h = self.hist.setdefault(k, [0, 0])
                h[0] += int(ok)
                h[1] += 1
        self.preq["pos"] += int(ok)
        self.eff_counts[y_eff] += 1
        key = f"{ctx.get('toolkit', '')}|{ctx.get('route', '')}"
        self.route_counts[key] = self.route_counts.get(key, 0) + 1
        self.seen += 1
        ex = (f, {"effect": y_eff, "ok": y_ok})
        # Burst guard (measured, generic): an executor retrying the SAME action in a row logs a run of identical events; without a cap the reservoir fills with the burst and replay keeps
        # training the same point, teaching overconfidence at exactly the moment the automation is floundering (measured: a 12-row identical no-effect burst drove a stale 0.70 "will work" belief).
        # Counts and prequential scoring still record EVERY row - only the repeated gradient step and the duplicate cache entry are capped.
        sig = self._signature(ctx, y_eff, y_ok)
        self._streak = self._streak + 1 if sig == self._last_sig else 1
        self._last_sig = sig
        if self._streak <= self.BURST_CAP:
            if len(self.recent) < 4000:
                self.recent.append(ex)
            else:
                self.recent[int(np.random.randint(0, len(self.recent)))] = ex
            if train:
                self.net.train_batch([ex])
                self.updates += 1

    def replay(self, n: int = 32, lr: Optional[float] = None) -> float:
        """One mini-batch from the reservoir (the background trainer calls this while the automation is in use)."""
        if len(self.recent) < 8:
            return 0.0
        idx = np.random.choice(len(self.recent), size=min(n, len(self.recent)), replace=False)
        self.updates += 1
        return self.net.train_batch([self.recent[i] for i in idx], lr)

    def fit_rows(self, rows: Iterable[Dict[str, Any]], epochs: int = 3, batch: int = 32) -> Dict[str, Any]:
        """Learn from stored history rows (cold start / catch-up): observe each once (prequential), then a few replay epochs."""
        n = 0
        for r in rows:
            self.observe(context_from_row(r), r.get("effect") or ("state_change" if r.get("ok") else "no_effect"), bool(r.get("ok")), train=True)
            n += 1
        loss = 0.0
        for _ in range(max(0, epochs) * max(1, len(self.recent) // max(1, batch))):
            loss = self.replay(batch)
        return {"rows": n, "loss": round(loss, 4), **self.metrics()}

    # ----------------------------------------------------------------------------------------------------- report
    def metrics(self) -> Dict[str, Any]:
        p = self.preq
        n = max(1, p["n"])
        return {"seen": self.seen, "updates": self.updates, "prequential_n": p["n"], "ok_accuracy": round(p["ok_correct"] / n, 4), "ok_baseline": round(p["base_ok_correct"] / n, 4),
                "effect_accuracy": round(p["eff_correct"] / n, 4), "effect_baseline": round(p["base_eff_correct"] / n, 4), "ok_brier": round(p["ok_brier"] / n, 4),
                "beats_baseline": bool(p["n"] >= 20 and p["ok_correct"] >= p["base_ok_correct"] and p["eff_correct"] >= p["base_eff_correct"]), "parameters": self.net.n_params(),
                "ok_accuracy_recent": round(sum(self.window) / len(self.window), 4) if self.window else None, "recent_n": len(self.window)}

    # -------------------------------------------------------------------------------------------------- persistence
    def save(self, path: Optional[str] = None) -> None:
        path = path or self.path
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.net.save(path)
        meta = {"seen": self.seen, "updates": self.updates, "route_counts": self.route_counts, "eff_counts": self.eff_counts.tolist(), "preq": self.preq, "hist": self.hist, "window": self.window}
        with open(path + ".json", "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
        self.last_saved = time.time()

    def _load(self, path: str) -> None:
        if self.net.load(path):
            try:
                with open(path + ".json", "r", encoding="utf-8") as fh:
                    m = json.load(fh)
                self.seen, self.updates = int(m.get("seen", 0)), int(m.get("updates", 0))
                self.route_counts = dict(m.get("route_counts", {}))
                self.eff_counts = np.array(m.get("eff_counts", [0] * len(EFFECTS)), float)
                self.preq.update(m.get("preq", {}))
                self.hist = {k: list(v) for k, v in (m.get("hist") or {}).items()}
                self.window = list(m.get("window") or [])
            except Exception:
                pass
