"""
professor.ml.learner -- CONTINUOUS TRAINING while the automation is in use.

The Learner owns the three models (action-outcome / route, vision-candidate, motor timing) and keeps them learning SIMULTANEOUSLY with the work:
  * every transition logged to the history (probing, executing a guide's procedure, exploring) is a labelled example -> the outcome model learns it the moment it is logged (the history calls
    `on_transition`; nothing in the executor has to know);
  * every scan of a window that has an accessibility tree labels the vision tier's candidates for free -> the candidate model learns it (`observe_scan`);
  * while any part of the architecture is running (`with learner.training():` - the executor, the probe engine, the explorer and the sweeper all open it), a background thread keeps taking replay
    mini-batches from each model's reservoir, saves checkpoints and appends metrics to `train_log.jsonl`, then stops when the work stops.
Models are saved under data/professor/ml/ and reloaded on the next run, so what was learnt on Tuesday is there on Wednesday. Switch off with HOJAIGA_PROF_ML=0.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .. import config as CFG
from .candidates import CandidateModel
from .motor import MotorModel
from .outcome import OutcomeModel, context_from_row

ML_DIR = os.path.join(CFG.DATA_DIR, "ml")


def enabled() -> bool:
    return os.environ.get("HOJAIGA_PROF_ML", "1") != "0"


class Learner:
    def __init__(self, directory: Optional[str] = None, interval_s: float = 1.5, save_every_s: float = 30.0, log_every_s: float = 10.0):
        self.dir = directory or ML_DIR
        os.makedirs(self.dir, exist_ok=True)
        self.outcome = OutcomeModel(os.path.join(self.dir, "outcome.npz"))
        self.candidates = CandidateModel(os.path.join(self.dir, "candidates.npz"))
        self.motor = MotorModel(os.path.join(self.dir, "motor.json"))
        self._apply_motor_timing()                                           # the gesture compiler's Fitts parameters = what the motor model learned (professor.pointing.set_fitts); see _apply_motor_timing
        self.lock = threading.RLock()
        self.interval_s, self.save_every_s, self.log_every_s = interval_s, save_every_s, log_every_s
        self.log_path = os.path.join(self.dir, "train_log.jsonl")
        self.meta_path = os.path.join(self.dir, "learner.json")
        self.last_row_id = 0
        try:
            with open(self.meta_path, "r", encoding="utf-8") as fh:
                self.last_row_id = int(json.load(fh).get("last_row_id", 0))
        except Exception:
            pass
        self.last_effect: Dict[Tuple[str, str], str] = {}
        self.history: Any = None
        self._refs = 0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.rounds = 0
        self.events = {"transitions": 0, "scans": 0, "replay_rounds": 0, "checkpoints": 0}

    def _apply_motor_timing(self) -> None:
        """Feed the learned (a, b) back into the gesture compiler: professor.pointing.fitts_seconds is what sizes every drag glide, so the motor model's parameters change HOW the pointer moves,
        not just what the report says. fitts_seconds clamps to a believable band, so a bad intermediate fit can never make a gesture absurd."""
        try:
            from .. import pointing as PN
            a, b = self.motor.params()
            PN.set_fitts(a, b)
        except Exception:
            pass

    # ------------------------------------------------------------------------------------------------- the inputs
    def attach(self, history: Any, catch_up: bool = True) -> Dict[str, Any]:
        """Subscribe to a history: every future transition trains the outcome model; rows logged while nobody was listening are learnt first (once)."""
        self.history = history
        if self.on_transition not in history.listeners:
            history.listeners.append(self.on_transition)
        n = 0
        if catch_up:
            rows = history.rows(since_id=self.last_row_id, limit=20000)
            with self.lock:
                for r in rows:
                    self._observe_row(r)
                    self.last_row_id = max(self.last_row_id, int(r["id"]))
                    n += 1
        return {"caught_up_rows": n}

    def _observe_row(self, row: Dict[str, Any]) -> None:
        ctx = context_from_row(row)
        key = (ctx["app"], ctx["label"])
        prev = self.last_effect.get(key)
        if prev:
            ctx["prev_effect"] = prev
        self.outcome.observe(ctx, row.get("effect") or ("state_change" if row.get("ok") else "no_effect"), bool(row.get("ok")))
        if row.get("effect"):
            self.last_effect[key] = row["effect"]

    def on_transition(self, row: Dict[str, Any]) -> None:
        if not enabled():
            return
        with self.lock:
            self._observe_row(row)
            self.last_row_id = max(self.last_row_id, int(row.get("id", 0)))
            self.events["transitions"] += 1

    def observe_scan(self, cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray], truth: Sequence[Any], source: str = "") -> Dict[str, Any]:
        if not enabled():
            return {"examples": 0, "disabled": True}
        with self.lock:
            self.events["scans"] += 1
            return self.candidates.observe_scan(cands, size, ink, truth, source=source)

    def observe_motion(self, distance: float, width: float, seconds: float) -> None:
        with self.lock:
            self.motor.observe(distance, width, seconds)

    # ------------------------------------------------------------------------------------------------ the outputs
    def rank_routes(self, ctx: Dict[str, Any], routes: Sequence[str]) -> List[Tuple[str, float]]:
        with self.lock:
            return self.outcome.rank_routes(ctx, routes)

    def predict(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            return self.outcome.predict(ctx)

    def candidate_filter(self, cands: Sequence[Any], size: Tuple[int, int], ink: Optional[np.ndarray]) -> Tuple[List[Any], int]:
        with self.lock:
            return self.candidates.filter(cands, size, ink)

    # ------------------------------------------------------------------------------------------- continuous training
    @contextlib.contextmanager
    def training(self):
        """Hold the background trainer open while a part of the architecture runs (re-entrant; the thread stops when the last holder leaves)."""
        self.start()
        try:
            yield self
        finally:
            self.stop()

    def start(self) -> None:
        if not enabled():
            return
        with self.lock:
            self._refs += 1
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="professor-ml-trainer", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if not enabled():
            return
        with self.lock:
            self._refs = max(0, self._refs - 1)
            last = self._refs == 0
        if last:
            self._stop.set()
            th = self._thread
            if th is not None:
                th.join(3.0)
            self.save()

    def _loop(self) -> None:
        t_save = t_log = time.time()
        last_updates = -1
        while not self._stop.wait(self.interval_s):
            try:
                with self.lock:
                    lo = self.outcome.replay(32)
                    lc = self.candidates.replay(48)
                    self.events["replay_rounds"] += 1
                    self.rounds += 1
                    ups = self.outcome.updates + self.candidates.updates
                now = time.time()
                if now - t_save >= self.save_every_s and ups != last_updates:
                    self.save()
                    t_save = now
                    last_updates = ups
                if now - t_log >= self.log_every_s:
                    self._log({"loss_outcome": round(lo, 4), "loss_candidates": round(lc, 4)})
                    t_log = now
            except Exception as exc:                                           # a trainer must never take the automation down
                self._log({"error": f"{type(exc).__name__}: {str(exc)[:100]}"})

    def _log(self, extra: Dict[str, Any]) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": round(time.time(), 1), **self.report(), **extra}) + "\n")
        except OSError:
            pass

    def save(self) -> None:
        with self.lock:
            self.outcome.save()
            self.candidates.save()
            self.motor.save()
            self._apply_motor_timing()                                       # keep the gesture compiler in step with what the motor model now knows
            with open(self.meta_path, "w", encoding="utf-8") as fh:
                json.dump({"last_row_id": self.last_row_id, "events": self.events}, fh)
            self.events["checkpoints"] += 1

    def report(self) -> Dict[str, Any]:
        with self.lock:
            return {"outcome": self.outcome.metrics(), "candidates": self.candidates.metrics(), "motor": self.motor.summary(), "events": dict(self.events), "training_now": bool(self._thread and self._thread.is_alive())}


_L: Optional[Learner] = None


def get_learner() -> Learner:
    global _L
    if _L is None:
        _L = Learner()
    return _L
