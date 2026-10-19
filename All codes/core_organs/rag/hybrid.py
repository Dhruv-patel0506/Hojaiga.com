"""
rag.hybrid -- procedure retrieval that does not give up when the program's own key holds nothing.

The router looks for a goal inside ONE app key. That is exact when the key is right and silent when it is not: 'open the command palette' asked under the key 'vscode' (the store holds 'visual_studio_code'), or 'search for a flight'
asked of a generic browser (the store holds the same task under 'web:delta.com', 'web:ryanair.com' ...). This module widens the search in three steps and ranks the union:

    1. resolve_key        a loose app name -> the key the store really has ('vscode' -> 'visual_studio_code'; 'edge' -> 'msedge'); unknown stays unknown
    2. scoped + global    the app's own rows, and every app's rows (lexical + vector, reciprocal-rank fused by rag.lt.search)
    3. rank               own app x1.6, same master domain x1.15, trust, and a content-word guard: a row must share >= 34% (own app) / 40% (elsewhere) of the goal's content words, so the answer is 'nothing known' rather than a wrong step

    pathways(rag, goal, app_key, k)   [{steps, reliability, source, app, scope, procedure_id, overlap}] in the shape brain_planner.pathways returns
    recall_at_k(rag, cases, k)         honest measurement used by the AR test and the report

Nothing is generated: rows come back as stored, with the app they came from and whether they came from the asked-for app or a similar task elsewhere.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

from . import domains as DM
from . import lt
from .lexicon import toks

STOP = {"how", "do", "i", "to", "the", "a", "an", "in", "on", "of", "for", "and", "please", "can", "you", "me", "with", "using", "use", "want", "would", "like", "know", "help", "my", "is", "it", "this", "that", "from", "at"}
TRUST_MULT = {"verified": 1.25, "learned": 1.15, "catalog": 1.1, "web": 1.0, "seed": 0.9, "llm": 0.85}
_KEYS: Dict[int, List[str]] = {}


def squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def known_keys(rag: Any) -> List[str]:
    k = id(rag.proc.st)
    if k not in _KEYS:
        rows = lt.fetch(rag.proc.st, "procedures", "1=1", 500000, ["app_key"])
        _KEYS[k] = sorted({r["app_key"] for r in rows})
    return _KEYS[k]


def resolve_key(rag: Any, app: str) -> str:
    """'vscode' -> 'visual_studio_code' when exactly one stored key matches by squashed name or by letters in order (first letter equal); otherwise the name unchanged."""
    if not app:
        return ""
    keys = known_keys(rag)
    if app in keys:
        return app
    a = squash(app)
    exact = [k for k in keys if squash(k) == a or squash(k.split(":")[-1]) == a]
    if len(exact) == 1:
        return exact[0]

    def in_order(small: str, big: str) -> bool:
        it = iter(big)
        return all(ch in it for ch in small)
    loose = [k for k in keys if not k.startswith(("web:", "webapp:")) and len(a) >= 3 and squash(k)[:1] == a[:1] and in_order(a, squash(k)) and len(squash(k)) <= len(a) * 4]
    if len(loose) == 1:
        return loose[0]
    return app


def content_words(text: str) -> List[str]:
    return [w for w in toks(text) if w not in STOP and len(w) > 1]


def _clean_goal(goal: str, app_key: str) -> str:
    g = re.sub(r"\(logic chain\)", " ", goal or "", flags=re.I)
    g = re.sub(r"^\s*in\s+[A-Za-z0-9 .+_-]{2,30},\s*", "", g)
    return re.sub(r"\s+", " ", g).strip()


def _overlap(want: Sequence[str], text: str) -> float:
    have = set(content_words(text))
    if not want:
        return 0.0
    hit = sum(1 for w in want if w in have or any(len(w) >= 4 and len(h) >= 4 and (w.startswith(h[:4]) or h.startswith(w[:4])) for h in have))
    return hit / len(want)


def search(rag: Any, goal: str, app_key: str = "", k: int = 5) -> List[Dict[str, Any]]:
    st = rag.proc.st
    app = resolve_key(rag, app_key)
    g = _clean_goal(goal, app)
    want = content_words(g)
    own = lt.search(st, "procedures", g, [app] if app else [], limit=k * 3) if app else []
    anyapp = lt.search(st, "procedures", g, [], limit=k * 4)
    reg = DM.load(rag)
    dom = DM.domain_of(app, reg) if app else ""
    pool: Dict[str, Dict[str, Any]] = {}
    for scope, rows in (("own", own), ("global", anyapp)):
        for r in rows:
            pid = r["procedure_id"]
            steps = []
            try:
                steps = json.loads(r.get("steps_json") or "[]")
            except Exception:
                pass
            text = (r.get("goal") or "") + " " + " ".join(str(s.get("text", "")) for s in steps)
            ov = _overlap(want, text)
            if pid in pool:
                pool[pid]["rrf"] = max(pool[pid]["rrf"], float(r.get("_rrf", 0.0)))
                continue
            same_app = bool(app) and r["app_key"] == app
            if ov < (0.34 if same_app else 0.4):
                continue                                                  # a row that does not speak about the goal is noise, even in the asked-for app (better 'nothing known' than a wrong step)
            mult = 1.6 if same_app else (1.15 if dom and DM.domain_of(r["app_key"], reg) == dom else 1.0)
            score = (float(r.get("_rrf", 0.0)) + 0.35 * ov) * mult * TRUST_MULT.get(str(r.get("trust")), 1.0)
            pool[pid] = {"procedure_id": pid, "app": r["app_key"], "goal": r.get("goal", ""), "steps_raw": steps, "scope": "own" if same_app else "similar_task", "overlap": round(ov, 2), "score": score,
                         "rrf": float(r.get("_rrf", 0.0)), "trust": r.get("trust"), "source": (str(r.get("sources", "")).strip("[]'\" ")[:60])}
    out = sorted(pool.values(), key=lambda x: -x["score"])
    return out[:k]


def pathways(rag: Any, goal: str, app_key: str = "", k: int = 3) -> List[Dict[str, Any]]:
    """Same shape as brain_planner.pathways, with where each pathway came from."""
    from core_organs import brain_planner as BP
    out = []
    for h in search(rag, goal, app_key, k):
        steps = [BP.plain_step(str(s.get("text", ""))) for s in h["steps_raw"][:8] if s.get("text")]
        if not steps:
            continue
        out.append({"steps": steps, "reliability": round(min(0.9, 0.35 + 0.5 * h["overlap"]) * (1.0 if h["scope"] == "own" else 0.8), 2), "source": h["source"], "app": h["app"], "scope": h["scope"],
                    "procedure_id": h["procedure_id"], "overlap": h["overlap"]})
    return out


def recall_at_k(rag: Any, cases: Sequence[Dict[str, Any]], k: int = 5, use_hybrid: bool = True) -> Dict[str, Any]:
    """cases: [{query, app_key, procedure_id}]. A hit = the procedure the query was made from is among the top k."""
    hit = 0
    miss: List[Dict[str, Any]] = []
    for c in cases:
        if use_hybrid:
            ids = [h["procedure_id"] for h in search(rag, c["query"], c.get("app_key", ""), k)]
        else:
            ids = [e.payload["procedure_id"] for e in rag.proc.find_procedures(c.get("app_key", ""), c["query"], k=k)] if c.get("app_key") else []
        if c["procedure_id"] in ids:
            hit += 1
        else:
            miss.append(c)
    return {"n": len(cases), "hits": hit, "recall": round(hit / max(len(cases), 1), 3), "misses": miss[:5]}
