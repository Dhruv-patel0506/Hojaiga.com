"""
episodic_memory -- Part (i): a zero-GPU self-improvement cache of VERIFIED trajectories.

Once the verifier (Part ii) reliably certifies an action, every fully-verified task run is
written here as ground truth. On a later task the agent queries the store: "have I already
solved this or a near-identical task in THIS app?" and, on a hit, reuses the proven
trajectory instead of re-deriving (or re-guessing) it. This is instant self-improvement:
0 training compute, 0 extra VRAM -- exactly the layer that should sit under LoRA.

Storage: SQLite (stdlib). Retrieval: exact normalized-intent match, then a token/difflib
fuzzy fallback -- no PyTorch/CUDA embeddings needed (matches the "zero-compute retrieval"
brief). The verified-trajectory rows are the same objects the LoRA/DPO flywheel (Parts 1-2)
will later train on, so this cache doubles as the curated dataset.

DB: brain/episodic_memory.db
Usage: python episodic_memory.py            # self-test: store + retrieve
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("HOJAIGA_EPISODIC_DB", "brain/episodic_memory.db"))
CACHE_ON = os.environ.get("HOJAIGA_EPISODIC", "1").strip().lower() not in ("0", "false", "no", "off")
MATCH_THRESHOLD = float(os.environ.get("HOJAIGA_EPISODIC_MIN", "0.6"))


def _norm(text: str) -> str:
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    stop = {"the", "a", "an", "to", "in", "of", "and", "on", "for", "please", "app", "window"}
    return " ".join(sorted(t for t in toks if t not in stop))


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), timeout=20)
    c.execute("""CREATE TABLE IF NOT EXISTS verified_trajectories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_name TEXT NOT NULL,
        task_intent TEXT NOT NULL,
        intent_normalized TEXT NOT NULL,
        trajectory_json TEXT NOT NULL,
        verification_type TEXT NOT NULL,
        step_count INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_app_intent ON verified_trajectories(app_name, intent_normalized)")
    c.commit()
    return c


def save_verified(app_name: str, task_intent: str, trajectory, verification_type: str = "MIXED") -> bool:
    """Store a fully-verified trajectory (idempotent per app+normalized-intent: keeps newest)."""
    if not CACHE_ON or not app_name or not task_intent:
        return False
    steps = trajectory or []
    if not steps:
        return False
    vt = verification_type or "MIXED"
    norm = _norm(task_intent)
    try:
        c = _conn()
        c.execute("DELETE FROM verified_trajectories WHERE app_name=? AND intent_normalized=?",
                  (app_name, norm))
        c.execute("INSERT INTO verified_trajectories(app_name,task_intent,intent_normalized,trajectory_json,verification_type,step_count) "
                  "VALUES(?,?,?,?,?,?)",
                  (app_name, task_intent, norm, json.dumps(steps, ensure_ascii=False), vt, len(steps)))
        c.commit()
        c.close()
        return True
    except Exception:
        return False


def _similarity(a: str, b: str) -> float:
    import difflib
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    jaccard = inter / len(ta | tb)
    containment = inter / min(len(ta), len(tb))      # "word wrap" is a subset of the stored intent
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return max(jaccard, ratio, 0.9 * containment)


def lookup(app_name: str, task_intent: str):
    """Return (trajectory_list, score, row_meta) for the best verified match, or None."""
    if not CACHE_ON or not task_intent:
        return None
    norm = _norm(task_intent)
    try:
        c = _conn()
        rows = c.execute(
            "SELECT task_intent,intent_normalized,trajectory_json,verification_type,step_count "
            "FROM verified_trajectories WHERE app_name=?", (app_name,)).fetchall()
        c.close()
    except Exception:
        return None
    best = None
    for ti, inorm, tj, vt, sc in rows:
        score = 1.0 if inorm == norm else _similarity(norm, inorm)
        if best is None or score > best[1]:
            best = (ti, score, tj, vt, sc)
    if best and best[1] >= MATCH_THRESHOLD:
        try:
            return json.loads(best[2]), round(best[1], 3), {"intent": best[0], "verification_type": best[3], "steps": best[4]}
        except Exception:
            return None
    return None


def stats() -> dict:
    try:
        c = _conn()
        n = c.execute("SELECT COUNT(*) FROM verified_trajectories").fetchone()[0]
        apps = c.execute("SELECT COUNT(DISTINCT app_name) FROM verified_trajectories").fetchone()[0]
        c.close()
        return {"rows": n, "apps": apps, "db": str(DB_PATH)}
    except Exception as e:
        return {"error": str(e)}


def _selftest():
    ok = save_verified("DemoApp", "toggle word wrap in the editor",
                       [{"step_id": 1, "ui_target": {"element_name": "Word wrap"}}], "VLM_SEMANTIC")
    hit = lookup("DemoApp", "word wrap")
    miss = lookup("DemoApp", "completely unrelated thing zzz")
    print("save:", ok)
    print("hit :", json.dumps(hit[2]) if hit else None)
    print("miss:", miss)
    print("stats:", stats())


if __name__ == "__main__":
    _selftest()
