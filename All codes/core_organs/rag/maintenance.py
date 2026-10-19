"""
rag.maintenance -- keep the procedure store honest: one copy of each way to do a thing, and no chain that only says "look at the screen".

    report(rag)                      what is in there: rows by source, exact duplicates (same app + goal), near duplicates (same app + same steps), observe-only chains
    dedupe(rag, apply=False)         keep the best copy of every duplicate group (verified / learned > web > seed, then more successful runs, then more steps, then the older row) and forget the rest
    purge_observe_only(rag, apply)   chains whose every step is "look at the screen" teach nothing a retrieval can run
    run(rag, apply)                  both; returns the counts (and, when apply, writes them to data/rag_maintenance.json)

Nothing is invented: only existing rows are removed, and a dry run (apply=False, the default) changes nothing.
"""
from __future__ import annotations

import collections
import json
import os
import re
import time
from typing import Any, Dict, List, Sequence

from . import lt

TRUST_RANK = {"verified": 4, "learned": 3, "catalog": 2, "web": 1, "seed": 0, "llm": 0}


def _rows(rag: Any) -> List[Dict[str, Any]]:
    return lt.fetch(rag.proc.st, "procedures", "1=1", 500000, None)


def _steps(p: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        return json.loads(p.get("steps_json") or "[]")
    except Exception:
        return []


def _first_steps_key(p: Dict[str, Any]) -> str:
    return re.sub(r"\W+", " ", " ".join(str(s.get("text", "")) for s in _steps(p)).lower()).strip()[:1500]


def _quality(p: Dict[str, Any]) -> tuple:
    return (TRUST_RANK.get(str(p.get("trust")), 0), int(float(p.get("n_ok") or 0)), len(_steps(p)), -float(p.get("last_run_ts") or 0))


def _src_name(p: Dict[str, Any]) -> str:
    m = re.search(r"'([^']+)'", str(p.get("sources", "")))
    return ":".join(m.group(1).split(":")[:2]) if m else ""


def observe_only(p: Dict[str, Any]) -> bool:
    acts = [str(s.get("text", "")) for s in _steps(p)]
    acts = [t for t in acts if "ACTION:" in t]
    return bool(acts) and all("ACTION: look at the screen" in t for t in acts)


def duplicate_losers(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rows to forget: in every group of exact (app, goal) or near (app, first steps) duplicates, everything except the best copy."""
    losers: Dict[str, Dict[str, Any]] = {}
    for keyf in (lambda p: (p["app_key"], p["goal_norm"]), lambda p: (p["app_key"], _first_steps_key(p)) if _first_steps_key(p) else None):
        groups: Dict[Any, List[Dict[str, Any]]] = collections.defaultdict(list)
        for p in rows:
            if p["procedure_id"] in losers:
                continue
            k = keyf(p)
            if k is not None:
                groups[k].append(p)
        for g in groups.values():
            if len(g) > 1:
                best = max(g, key=_quality)
                for p in g:
                    if p is not best:
                        losers[p["procedure_id"]] = p
    return list(losers.values())


def report(rag: Any) -> Dict[str, Any]:
    rows = _rows(rag)
    los = duplicate_losers(rows)
    by_src = collections.Counter(_src_name(p) or "?" for p in rows)
    return {"procedures": len(rows), "by_source": dict(by_src.most_common(12)), "duplicates": len(los), "duplicates_by_source": dict(collections.Counter(_src_name(p) or "?" for p in los).most_common(8)),
            "observe_only": sum(1 for p in rows if observe_only(p))}


def run(rag: Any, apply: bool = False, out_path: str = "") -> Dict[str, Any]:
    rows = _rows(rag)
    junk = [p for p in rows if observe_only(p)]
    jid = {p["procedure_id"] for p in junk}
    los = [p for p in duplicate_losers([p for p in rows if p["procedure_id"] not in jid])]
    res = {"before": len(rows), "observe_only": len(junk), "duplicates": len(los), "applied": bool(apply), "ts": time.time()}
    if apply:
        ids = sorted(jid | {p["procedure_id"] for p in los})
        rag.proc.forget_procedure_ids(ids)
        for a in {p["app_key"] for p in rows}:
            rag.proc.st.bump(f"proc:{a}")
        res["after"] = len(_rows(rag))
        if out_path:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            json.dump(res, open(out_path, "w"), indent=1)
    return res
