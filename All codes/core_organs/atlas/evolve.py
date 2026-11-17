"""
atlas.evolve -- the system gets better by being wrong in public.

  * PREDICTION LEDGER   before a probe the learner predicts its outcome from what it has seen on OTHER controls/regions ("a label ending in
                        an ellipsis opens a dialog"; "a drag on a canvas pans"); after the probe the observed outcome is stored next to
                        the prediction. `accuracy()` is the learning curve, measured.
  * ACTIVE ORDERING     features -> outcome counts (atlas_priors). `rank()` puts the probes whose outcome the learner is LEAST sure of first
                        (highest entropy), so a limited budget buys the most information.
  * DRIFT DETECTION     a fingerprint (program version hash + structure signature + counts) is stored per scan; the next scan reports exactly
                        what changed (version, controls added/removed) so only the changed part needs relearning.
  * OVERNIGHT LOOP      `learn_loop` visits a list of applications, each in its own watchdog subprocess (a hung app cannot stop the night).

Nothing here is per-application: features are generic (label shape, control type, region kind, gesture).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import common as C


def feature_keys(kind: str, feats: Dict[str, Any]) -> List[str]:
    keys = [f"{kind}|any"]
    for k, v in feats.items():
        if v in (None, "", False):
            continue
        keys.append(f"{kind}|{k}={str(v)[:40]}")
    label = str(feats.get("label") or "")
    if label:
        if label.endswith("...") or label.endswith("…"):
            keys.append(f"{kind}|label=ellipsis")
        if re.search(r"[▾▼>v]\s*$", label):
            keys.append(f"{kind}|label=dropdown-mark")
        if len(label) <= 3:
            keys.append(f"{kind}|label=short")
        if label[:1].isupper() and " " not in label:
            keys.append(f"{kind}|label=single-word")
    return keys


class Learner:
    def __init__(self, store: Optional[C.AtlasStore] = None, app_key: str = "", run_id: str = ""):
        self.store = store or C.get_store()
        self.app_key = app_key
        self.run_id = run_id

    # ---- priors
    def _counts(self, keys: Sequence[str]) -> Dict[str, float]:
        if not keys:
            return {}
        ph = ",".join("?" * len(keys))
        rows = self.store._rows(f"SELECT outcome, SUM(n) n FROM atlas_priors WHERE feature IN ({ph}) GROUP BY outcome", list(keys))
        return {r["outcome"]: float(r["n"]) for r in rows}

    def distribution(self, kind: str, feats: Dict[str, Any]) -> Dict[str, float]:
        c = self._counts(feature_keys(kind, feats))
        tot = sum(c.values())
        return {k: v / tot for k, v in c.items()} if tot else {}

    def predict(self, kind: str, feats: Dict[str, Any]) -> Optional[str]:
        d = self.distribution(kind, feats)
        if not d:
            return None
        best = max(d.items(), key=lambda kv: kv[1])
        return best[0] if best[1] >= 0.4 else None

    def entropy(self, kind: str, feats: Dict[str, Any]) -> float:
        d = self.distribution(kind, feats)
        if not d:
            return 3.0                                     # never seen: maximally informative
        return -sum(p * math.log(p + 1e-12, 2) for p in d.values())

    def rank(self, items: Sequence[Any], kind: str, feats_of: Callable[[Any], Dict[str, Any]]) -> List[Any]:
        return sorted(items, key=lambda it: -self.entropy(kind, feats_of(it)))

    # ---- ledger
    def observe(self, kind: str, feats: Dict[str, Any], predicted: str, observed: str, subject: str = "") -> None:
        keys = feature_keys(kind, feats)
        with self.store._lock:
            for k in keys:
                self.store._conn.execute("INSERT INTO atlas_priors (feature, outcome, n) VALUES (?,?,1) ON CONFLICT(feature, outcome) DO UPDATE SET n = n + 1", (k, observed))
            self.store._conn.execute("INSERT INTO atlas_predictions (app_key, run_id, subject, features, predicted, observed, correct, ts) VALUES (?,?,?,?,?,?,?,?)",
                                     (self.app_key, self.run_id, subject[:120], json.dumps(feats, default=str)[:600], predicted or "", observed,
                                      None if not predicted else int(predicted == observed), time.time()))
            self.store._conn.commit()

    def accuracy(self, app_key: str = "", last: int = 400) -> Dict[str, Any]:
        sql = "SELECT predicted, observed, correct FROM atlas_predictions WHERE correct IS NOT NULL"
        args: List[Any] = []
        if app_key:
            sql += " AND app_key=?"
            args.append(app_key)
        rows = self.store._rows(sql + " ORDER BY id DESC LIMIT ?", args + [last])
        n = len(rows)
        ok = sum(r["correct"] for r in rows)
        first, second = rows[len(rows) // 2:], rows[:len(rows) // 2]          # older half, newer half (rows are newest-first)
        rate = lambda rs: round(sum(r["correct"] for r in rs) / len(rs), 3) if rs else None
        return {"n": n, "correct": ok, "rate": round(ok / n, 3) if n else None, "older_half": rate(first), "newer_half": rate(second)}


# --------------------------------------------------------------------------------------------------
# drift
# --------------------------------------------------------------------------------------------------

def structure_signature(names: Iterable[str]) -> str:
    return hashlib.sha1("\n".join(sorted(set(n.lower() for n in names if n))).encode("utf-8", "ignore")).hexdigest()[:16]


def fingerprint(store: C.AtlasStore, app_key: str, exe: str, control_names: Iterable[str], n_commands: int) -> Dict[str, Any]:
    """Store this scan's fingerprint and report what changed since the previous one."""
    try:
        from core_organs import organ_48_app_behavior_model as bm
        vh = bm.app_version_hash(exe) if exe else ""
    except Exception:
        vh = ""
    names = sorted(set(n for n in control_names if n))
    sig = structure_signature(names)
    prev = store.fingerprints(app_key, 1)
    report: Dict[str, Any] = {"version_hash": vh, "structure_sig": sig, "controls": len(names), "first_scan": not prev}
    if prev:
        p = prev[0]
        report["version_changed"] = bool(p["version_hash"]) and bool(vh) and p["version_hash"] != vh
        report["structure_changed"] = p["structure_sig"] != sig
        try:
            old = set(json.loads(p.get("extra_json") or "{}").get("names", []))
        except Exception:
            old = set()
        report["added"] = sorted(set(names) - old)[:40]
        report["removed"] = sorted(old - set(names))[:40]
        report["delta_controls"] = len(names) - int(p["n_controls"] or 0)
    store.put_fingerprint(app_key, vh, sig, n_commands, len(names), {"names": names[:2000]})
    return report


# --------------------------------------------------------------------------------------------------
# overnight loop
# --------------------------------------------------------------------------------------------------

def learn_loop(apps: Sequence[str], *, cycles: int = 1, tier: str = "deep", budget_s: float = 120.0, per_app_timeout_s: float = 900.0,
               out_dir: str = "", log: Callable[[str], None] = print, python: str = "", main_py: str = "") -> List[Dict[str, Any]]:
    """Visit each app (own subprocess + watchdog). Returns the per-visit summaries; also written as JSON lines + a markdown digest."""
    out_dir = C.ensure_dir(out_dir or os.path.join(C.ATLAS_DIR, "overnight"))
    python = python or sys.executable
    main_py = main_py or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hojaiga_atlas.py")
    results: List[Dict[str, Any]] = []
    stamp = time.strftime("%Y%m%d_%H%M%S")
    jl = os.path.join(out_dir, f"loop_{stamp}.jsonl")
    for cyc in range(cycles):
        for app in apps:
            t0 = time.time()
            cmd = [python, "-X", "utf8", main_py, "learn1", app, "--tier", tier, "--budget", str(int(budget_s)), "--json"]
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            rec: Dict[str, Any] = {"app": app, "cycle": cyc, "tier": tier, "started": t0}
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=per_app_timeout_s, env=env)
                rec["returncode"] = p.returncode
                txt = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
                try:
                    rec["result"] = json.loads(txt)
                except Exception:
                    rec["stdout_tail"] = p.stdout[-600:]
                    rec["stderr_tail"] = p.stderr[-600:]
            except subprocess.TimeoutExpired:
                rec["error"] = f"watchdog: no answer within {per_app_timeout_s:.0f}s; subprocess ended"
            except Exception as exc:
                rec["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            rec["seconds"] = round(time.time() - t0, 1)
            results.append(rec)
            with open(jl, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
            log(f"[loop] {app} cycle {cyc}: {rec.get('seconds')}s " + ("ok" if rec.get("result") else rec.get("error", "no result")))
    md = [f"# Atlas overnight digest {stamp}", ""]
    for r in results:
        res = r.get("result") or {}
        md.append(f"- **{r['app']}** (cycle {r['cycle']}): {r['seconds']}s; " + (f"claims={res.get('claims_total')}, commands={res.get('commands')}, gestures={res.get('gestures')}" if res else r.get("error", "no result")))
    with open(os.path.join(out_dir, f"digest_{stamp}.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    return results
