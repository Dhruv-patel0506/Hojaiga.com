"""
rag_offline_benchmark.py -- offline, read-only measurements of the RAG: how fast it answers and how deep the saved scans are. No window, no GPU, no model server, no network, nothing written to the real stores.

    python rag_offline_benchmark.py [--queries 1500] [--out report.json]

  A  scan depth      every saved `*_scan_result.json` (21 apps): controls, distinct control types, named share, how long the scan took, and what the scan gate decides about it (archetype, verified, what is missing)
  B  master RAG      causal_procedures_fts (opened read-only): query latency p50/p95/p99 for (1) the exact task text and (2) the app name alone, and whether the right row comes back (hit@1 / hit@5)
  C  federated RAG   a COPY of data/ai_root/rag (SQL + vector tables), HashEmbedder, `Rag.retrieve` on 150 registered keys x 5 tasks: latency, tier, how many answered
  D  archetypes      the 70/30 held-out archetype evaluation (rag.archetypes.evaluate_70_30_split)

Honesty notes printed with the report: the master RAG rows are template-generated ("<task> in <app>"), so B measures retrieval plumbing and speed, not knowledge; C cannot judge embedding search (no embedder server); A depends on the saved traces
being real scans of those apps (they are, dated Sep-Oct).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "All codes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MASTER = ROOT / "data" / "hojaiga_master_rag.db"
RAG_DIR = ROOT / "data" / "ai_root" / "rag"
TASKS = ["save the file", "open the settings", "undo the last action", "export the project", "search for something"]


def lowered_priority() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 10)
    except Exception:
        pass


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * p))], 3) if xs else None


def lat(xs):
    return {"n": len(xs), "p50_ms": pct(xs, 0.5), "p95_ms": pct(xs, 0.95), "p99_ms": pct(xs, 0.99), "mean_ms": round(statistics.mean(xs), 3) if xs else None}


# ----------------------------------------------------------------------------------------------------------------------------------- A
def scan_depth() -> list:
    from core_organs import scan_gate as G, tutor_logic as TL
    out = []
    for f in sorted(glob.glob(str(ROOT / "*_scan_result.json"))):
        name = os.path.basename(f).replace("_scan_result.json", "")
        try:
            tr = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        surf = TL.controls_from_trace(tr)
        ctrls = surf["controls"]
        t = time.perf_counter()
        v = G.validate_scan(ctrls, app_name=name.replace("_deep", "").replace("_", " "), title=surf.get("title", ""))
        ms = (time.perf_counter() - t) * 1000
        roles = {c.get("role") for c in ctrls}
        named = sum(1 for c in ctrls if (c.get("name") or "").strip())
        el = tr.get("elapsed_seconds")
        out.append({"trace": name, "controls": len(ctrls), "failed": tr.get("controls_failed"), "distinct_types": len(roles), "named_pct": round(100 * named / max(len(ctrls), 1)),
                    "scan_seconds": el, "controls_per_min": round(60 * len(ctrls) / el, 1) if el else None, "scanned_at": (tr.get("scanned_at") or "")[:10],
                    "gate": v.get("status"), "archetype": v.get("archetype"), "verified": v.get("verified"), "missing": len(v.get("missing") or []), "gate_ms": round(ms, 2)})
    return out


# ----------------------------------------------------------------------------------------------------------------------------------- B
def _fts_query(text: str) -> str:
    toks = [t for t in re.findall(r"[A-Za-z0-9]+", text) if len(t) > 1]
    return " ".join(f'"{t}"' for t in toks[:12])


def master_rag(n: int, seed: int = 7) -> dict:
    c = sqlite3.connect(f"file:{MASTER}?mode=ro", uri=True)
    c.execute("PRAGMA query_only=1")
    rows = c.execute("SELECT rowid, domain, goal FROM causal_procedures_fts WHERE domain IN ('desktop_app','web_app','website') AND goal LIKE '% in %' "
                     "AND goal NOT LIKE '%#%' AND goal NOT LIKE '%via%'").fetchall()
    total = c.execute("SELECT count(*) FROM causal_procedures_fts").fetchone()[0]
    rows = [r for r in rows if " in " in r[2]]                  # LIKE is case-insensitive: keep only the '<task> in <app>' shape
    random.Random(seed).shuffle(rows)
    rows = rows[:n]
    exact_ms, app_ms, h1, h5, a5 = [], [], 0, 0, 0
    for rid, dom, goal in rows:
        t = time.perf_counter()
        got = c.execute("SELECT rowid, goal FROM causal_procedures_fts WHERE causal_procedures_fts MATCH ? ORDER BY rank LIMIT 5", (_fts_query(goal),)).fetchall()
        exact_ms.append((time.perf_counter() - t) * 1000)
        h1 += bool(got and got[0][1] == goal)                       # by goal text: 13% of goals are shared by several rows, so a row id would under-score
        h5 += any(g[1] == goal for g in got)
        app = goal.rsplit(" in ", 1)[1]
        t = time.perf_counter()
        got2 = c.execute("SELECT goal FROM causal_procedures_fts WHERE causal_procedures_fts MATCH ? ORDER BY rank LIMIT 5", (_fts_query("workflow " + app),)).fetchall()
        app_ms.append((time.perf_counter() - t) * 1000)
        a5 += any(app.lower() in g[0].lower() for g in got2)
    c.close()
    k = max(len(rows), 1)
    return {"rows_in_table": total, "sampled": len(rows), "exact_text": {**lat(exact_ms), "hit@1_pct": round(100 * h1 / k, 1), "hit@5_pct": round(100 * h5 / k, 1)},
            "app_name_only": {**lat(app_ms), "app_in_top5_pct": round(100 * a5 / k, 1)}}


# ----------------------------------------------------------------------------------------------------------------------------------- C
def federated() -> dict:
    from core_organs.rag import embed as E, storage as ST
    from core_organs.rag.router import Rag
    from core_organs.rag.types import Query
    tmp = tempfile.mkdtemp(prefix="rag_bench_")
    try:
        dst = os.path.join(tmp, "rag")
        os.makedirs(dst)
        for f in glob.glob(str(RAG_DIR / "*.db")) + glob.glob(str(RAG_DIR / "*.json")):
            shutil.copy2(f, dst)
        shutil.copytree(RAG_DIR / "lancedb", os.path.join(dst, "lancedb"), dirs_exist_ok=True)      # the vector tables (~680 MB), so the stores are not empty
        R = Rag(ST.Storage(tmp, E.HashEmbedder()), icons=False, seed=False)
        keys = list(json.load(open(RAG_DIR / "domains.json", encoding="utf-8")))
        ms, tiers, answered, per_tier = [], {}, 0, {}
        for k in keys:
            for task in TASKS:
                t = time.perf_counter()
                r = R.retrieve(Query(text=task, app_key=k, mode="tutor"))
                d = (time.perf_counter() - t) * 1000
                ms.append(d)
                tiers[r.tier] = tiers.get(r.tier, 0) + 1
                answered += bool(r.plans or r.evidence)
        counts = {}
        for tbl in ("fast_paths", "procedures", "ui_states", "error_playbooks", "knowledge_chunks"):
            try:
                counts[tbl] = R.st.count(tbl)
            except Exception:
                counts[tbl] = None
        return {"keys": len(keys), "queries": len(ms), **lat(ms), "answered_pct": round(100 * answered / max(len(ms), 1), 1), "tiers": tiers, "table_rows": counts,
                "note": "vector tables copied, but the query embedder is HashEmbedder (the stores were built with another embedder), so similarity search is not meaningful; lexical / graph / rule tiers are"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------------------------------------------------------------- D
def archetypes() -> dict:
    from core_organs.rag import archetypes as A
    t = time.time()
    r = A.evaluate_70_30_split(seeds=10)
    return {"seconds": round(time.time() - t, 1), **{k: v for k, v in r.items() if not isinstance(v, (list, dict))}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=int, default=1500)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    lowered_priority()
    rep = {"when": time.strftime("%Y-%m-%d %H:%M"), "scan_depth": scan_depth(), "master_rag": master_rag(a.queries), "federated_rag": federated(), "archetypes": archetypes()}
    txt = json.dumps(rep, indent=1, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
