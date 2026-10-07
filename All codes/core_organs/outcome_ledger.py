"""
outcome_ledger.py - the honest half of "it learns from what happened": a per-app, per-goal record of
whether the run SUCCEEDED or FAILED (and why), plus a prefetch that turns that history into a soft nudge.

This is deliberately NOT sentience and NOT a claim to "know what you'll say next". It is the plain,
auditable substrate that makes the agent feel like it knows you: it REMEMBERS the outcome of each goal
in each app, PREFETCHES the plan that worked last time, and WARNS (and adapts tone) when the same goal
has already failed here repeatedly. Every field is written from a REAL run result; nothing is inferred.

Why a failure ledger at all: the recipe store (desktop_grounding.distill_recipe) only records SUCCESS.
A goal that kept failing left no trace, so the next identical attempt walked into the same wall with no
advance warning and the same confident tone. Failures are half of learning, so they are remembered here.

Honest by construction:
  * prefetch NEVER changes a verdict - it only hands back a hint and a tone string; the postcondition
    verifier still decides every step independently;
  * keys are the goal's stable fingerprint, app-scoped, so a plan from another app is never suggested;
  * a corrupted/unreadable ledger degrades to empty (the run behaves exactly as before), never raises.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hojaiga.outcome_ledger")

# The file lives beside the other Hojaiga state at the repo root; override with HOJAIGA_OUTCOME_LEDGER.
_PATH = os.environ.get(
    "HOJAIGA_OUTCOME_LEDGER",
    os.path.join(r"D:\new_automation", "hojaiga_outcome_ledger.json"))

_LOCK = threading.Lock()
_MAX_KEEP_PER_APP = 60          # bounded: the freshest goals only, so the file cannot grow without limit
_WARN_AFTER_FAILS = 2           # repeated failures before the prefetch starts cautioning


def _app_key(app: str) -> str:
    return (app or "").strip().lower() or "_unknown"


def _goal_fp(goal: str) -> str:
    g = " ".join((goal or "").strip().lower().split())
    return hashlib.md5(g.encode("utf-8")).hexdigest()[:12]


def _load() -> Dict[str, Any]:
    try:
        with open(_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("[ledger] unreadable (%s): starting fresh, no crash", exc)
        return {}


def _save(data: Dict[str, Any]) -> None:
    tmp = _PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
        os.replace(tmp, _PATH)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[ledger] save failed (%s): this run's outcome is not persisted", exc)


def record(app: str, goal: str, *, ok: bool, note: str = "", steps: int = 0,
           elapsed_s: float = 0.0) -> None:
    """Store one whole-task outcome for (app, goal). Successes and failures are BOTH kept, so prefetch can
    tell 'this worked before' from 'this keeps failing here'. Never raises: learning is a bonus, not a dependency."""
    key, fp = _app_key(app), _goal_fp(goal)
    with _LOCK:
        data = _load()
        app_bucket = data.setdefault(key, {})
        row = app_bucket.get(fp) or {"goal": (goal or "")[:200], "successes": 0, "failures": 0}
        row["goal"] = (goal or "")[:200]
        if ok:
            row["successes"] = int(row.get("successes", 0)) + 1
            if note:
                row["last_plan"] = note[:400]      # e.g. the decomposed press sequence that worked
        else:
            row["failures"] = int(row.get("failures", 0)) + 1
            row["last_block"] = note[:200]
        row["last_verdict"] = "PASS" if ok else "FAIL"
        row["last_ts"] = time.time()
        row["last_steps"] = steps
        row["last_elapsed_s"] = round(float(elapsed_s or 0), 1)
        app_bucket[fp] = row
        # bound the bucket by recency
        if len(app_bucket) > _MAX_KEEP_PER_APP:
            keep = sorted(app_bucket.items(), key=lambda kv: float(kv[1].get("last_ts") or 0), reverse=True)
            data[key] = dict(keep[:_MAX_KEEP_PER_APP])
        _save(data)


def prefetch(app: str, goal: str) -> Dict[str, Any]:
    """What the ledger knows about doing THIS goal in THIS app. Returns a soft, honest read:
      seen, successes, failures, hint (a plan that worked before, if any), caution (repeated failure note),
      tone (one word the capsule can use). It NEVER asserts the goal will pass."""
    key, fp = _app_key(app), _goal_fp(goal)
    with _LOCK:
        row = _load().get(key, {}).get(fp)
    if not row:
        return {"seen": False, "successes": 0, "failures": 0, "hint": "", "caution": "", "tone": ""}
    s, f = int(row.get("successes", 0)), int(row.get("failures", 0))
    hint = row.get("last_plan", "") if s > 0 else ""
    caution = ""
    tone = ""
    if f >= _WARN_AFTER_FAILS and f > s:
        caution = (f"this goal failed {f}x here (last block: {row.get('last_block', 'unknown')}); "
                   "trying the same way again is unlikely to work - it may need a different route or your input")
        tone = "cautious"
    elif s > 0:
        tone = "confident"        # it has actually done THIS in THIS app before
    return {"seen": True, "successes": s, "failures": f, "hint": hint,
            "caution": caution, "tone": tone, "last_verdict": row.get("last_verdict", "")}


def app_summary(app: str) -> List[Dict[str, Any]]:
    """Every goal remembered for one app, freshest first - the 'what does it know about this app' view."""
    with _LOCK:
        bucket = _load().get(_app_key(app), {})
    rows = [dict(v, fp=k) for k, v in bucket.items()]
    rows.sort(key=lambda r: float(r.get("last_ts") or 0), reverse=True)
    return rows
