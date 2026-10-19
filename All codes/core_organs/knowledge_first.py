"""
knowledge_first -- Tier 0 of the executor: a verified, PARAMETERISED plan is replayed before any model is asked.

    lookup(app_key, task)            -> list of goals | None     the stored plan for this intent family, parameters bound from the new task (no planner call, no RAG call)
    store(app_key, task, goals, ok)  -> bool                     after a run: a plan whose goals were ALL done and checked is kept as a template ({0}, {1} ... are the task's own parameters);
                                                                 a replayed plan that failed is demoted (2 failures) so the next run plans again and overwrites it
    record(...)                      latency + model-call line per run (data/latency_log.jsonl): the cold / warm table is built from it

A template is only kept when binding the same parameters back reproduces the plan exactly (a plan that depends on the parameters in another way - digit by digit on a calculator - is not cached; it costs no model call anyway).
The intent signature is the task with its parameters masked: quoted text, the words after 'type / write / enter', the two words of 'change A to B' / 'replace A with B', a title / subtitle, numbers.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
CACHE = os.path.join(DATA, "proc_cache.json")
LOG = os.path.join(DATA, "latency_log.jsonl")
_LOCK = threading.Lock()

_Q = re.compile(r"[\"“']([^\"”']{1,200})[\"”']")
_TYPED = re.compile(r"\b(?:type|write|enter)\s+(?:the\s+(?:words?|text|sentence)\s+)?(?!\")([^,;\"]+?)(?=\s*(?:,|;|\bthen\b|$))", re.I)
_CHANGE = re.compile(r"\b(?:change|swap)\s+(?:every\s+|all\s+|the\s+word\s+)?(\S+)\s+(?:to|into)\s+(\S+)", re.I)
_REPL = re.compile(r"\breplace\s+(?:every\s+|all\s+|the\s+word\s+)?(\S+)\s+(?:with|by)\s+(\S+)", re.I)
_TITLE = re.compile(r"\b(?:title|subtitle|heading)\s+(?:of\s+|called\s+|named\s+|as\s+)?([^,;]+?)(?=\s+and\s+(?:a\s+)?(?:sub)?title\b|[,;]|$)", re.I)
_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def slots_of(task: str) -> List[Tuple[int, int, str]]:
    """Non-overlapping parameter spans of a task, left to right: (start, end, text)."""
    spans: List[Tuple[int, int, str]] = []
    for rx in (_Q, _CHANGE, _REPL, _TITLE, _TYPED, _NUM):
        for m in rx.finditer(task):
            groups = range(1, (m.re.groups or 0) + 1) or [0]
            for g in groups:
                a, b = m.start(g), m.end(g)
                if a >= 0 and b > a and not any(a < e and b > s for s, e, _t in spans):
                    spans.append((a, b, task[a:b]))
    return sorted(spans)


def signature(task: str) -> Tuple[str, List[str]]:
    spans = slots_of(task)
    out, last, params = [], 0, []
    for i, (a, b, t) in enumerate(spans):
        out.append(task[last:a])
        out.append("{%d}" % i)
        params.append(t)
        last = b
    out.append(task[last:])
    return re.sub(r"\s+", " ", "".join(out)).strip().lower(), params


def _load() -> Dict[str, Any]:
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        return {}


def _save(d: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(tmp, CACHE)


def _template(goals: Sequence[str], params: Sequence[str]) -> List[str]:
    out = []
    for g in goals:
        t = g
        for i, p in sorted(enumerate(params), key=lambda x: -len(x[1])):
            if p and p in t:
                t = t.replace(p, "{%d}" % i)
        out.append(t)
    return out


def _bind(template: Sequence[str], params: Sequence[str]) -> Optional[List[str]]:
    try:
        return [re.sub(r"\{(\d+)\}", lambda m: params[int(m.group(1))], t) for t in template]
    except Exception:
        return None


def lookup(app_key: str, task: str) -> Optional[List[str]]:
    sig, params = signature(task)
    with _LOCK:
        e = _load().get(f"{app_key}|{sig}")
    if not e or e.get("n_fail", 0) >= 2 or e.get("n_ok", 0) < 1:
        return None
    goals = _bind(e["template"], params)
    return goals if goals and len(params) == e.get("n_params", len(params)) else None


def store(app_key: str, task: str, goals: Sequence[str], all_done: bool, replayed: bool = False, source: str = "planner") -> bool:
    sig, params = signature(task)
    key = f"{app_key}|{sig}"
    with _LOCK:
        d = _load()
        e = d.get(key)
        if replayed:                                                       # a cached plan was used: its outcome is the evidence
            if e is not None:
                e["n_ok" if all_done else "n_fail"] = e.get("n_ok" if all_done else "n_fail", 0) + 1
                if all_done:
                    e["n_fail"] = 0
                _save(d)
            return bool(e)
        if not all_done or not goals:
            return False
        tpl = _template(goals, params)
        used = {int(i) for t in tpl for i in re.findall(r"\{(\d+)\}", t)}
        if _bind(tpl, params) != list(goals) or used != set(range(len(params))):   # a parameter the plan never uses whole (digits typed one by one) means the plan depends on it in another way: not a template
            return False
        d[key] = {"template": tpl, "n_params": len(params), "n_ok": 1, "n_fail": 0, "source": source, "app_key": app_key, "ts": time.time()}
        _save(d)
        return True


def record(case: str, app_key: str, seconds: float, model_calls: int, tier: str, cold: bool, ok: bool, states: Optional[Dict[str, float]] = None) -> None:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with _LOCK, open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "case": case, "app": app_key, "seconds": round(seconds, 1), "model_calls": model_calls, "tier": tier, "cold": cold, "ok": ok, "states": states or {}}) + "\n")
