"""
rag.fastpaths -- Sub-RAG 4: the Superhuman Macro & Hotkey Vault (DESIGN.md section 5.4).

The fastest correct route to a command or a whole task: hotkeys, chord sequences, WM_COMMAND ids, menu accelerators, CLI lines, scripts (bpy / AutoCAD .scr / VBA / COM / PowerShell).

EXECUTION GATE (project law): a row is returned as a DIRECT step only when it is verified, or its trust is verified/learned. Anything else (a scraped table, an LLM-written chord, a seed) comes back as
a PROBE step -- the executor tries it with before/after verification and reports the outcome through observe(), which is how a probe earns its way to verified (PROMOTE_AFTER_OK successes
in distinct runs) and how a failing one loses trust (DEMOTE_AFTER_FAIL consecutive failures drop it one level).

Templates are filled by DETERMINISTIC slot extraction from the user's goal (numbers with units, quoted names, paths). A slot is validated before it is placed in code (numbers parse; strings
are a conservative character class; paths are path characters only) and a required slot with no value is reported as a gap (needs_param:<slot>) -- a script is never run with a guessed value.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import config as C
from . import lt
from .lexicon import canon, surface
from .types import Evidence, Outcome, UpsertReport

try:
    import safety_guard as _SG                      # type: ignore
except Exception:                                   # pragma: no cover
    try:
        from core_organs import safety_guard as _SG
    except Exception:
        _SG = None

KIND_ROUTE = {"hotkey": "hotkey", "chord_seq": "hotkey", "menu_accel": "hotkey", "wm_command": "wm_command", "cli": "script", "script": "script", "com": "script"}
SOURCE_TRUST = {"keymap_file": "catalog", "registry": "catalog", "probe": "learned", "skill": "verified", "seed": "seed", "web_table": "web", "tldr": "seed", "llm": "llm"}
DIRECT_TRUST = {"verified", "learned"}
_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_QUOTED = re.compile(r"\"([^\"]{1,80})\"|(?<!\w)'([^']{1,80})'(?!\w)|“([^”]{1,80})”|‘([^’]{1,80})’")
_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|\.{0,2}[\\/])[\w .\\/:-]{1,200}")
_SLOT = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_SAFE_STR = re.compile(r"^[\w .,\-]{0,80}$")
_SAFE_PATH = re.compile(r"^[\w .:\\/\-]{1,260}$")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def safety_of(text: str) -> str:
    if _SG is None:
        return "allow"
    d = _SG.check(text or "x")
    return "allow" if d.allowed else d.category


def fast_id(app_key: str, kind: str, payload: str, context: str = "") -> str:
    return hashlib.sha1(f"{app_key}|{kind}|{_norm(payload)}|{_norm(context)}".encode("utf-8")).hexdigest()


# ---- template filling ------------------------------------------------------------------------------------------------------------------------------
def extract_slots(goal: str, schema: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """(values, missing_required). Numbers bind to number slots by a nearby slot-name word first, then in order; quoted strings and paths bind in order."""
    values: Dict[str, Any] = {}
    g = goal or ""
    nums = [(m.start(), m.group(0)) for m in _NUM.finditer(g)]
    used: set = set()
    num_slots = [k for k, v in schema.items() if v.get("type") == "number"]
    for k in num_slots:                                             # 'radius 5', '5 radius'
        name = k.replace("_", " ")
        for pos, txt in nums:
            if pos in used:
                continue
            around = g[max(0, pos - 18):pos + len(txt) + 18].lower()
            if name in around or k.lower() in around:
                values[k], _ = float(txt), used.add(pos)
                break
    free = [(p, t) for p, t in nums if p not in used]
    for k in num_slots:
        if k not in values and free:
            p, t = free.pop(0)
            values[k] = float(t)
    quoted = [next(x for x in m.groups() if x is not None) for m in _QUOTED.finditer(g)]
    paths = [m.group(0).strip() for m in _PATH.finditer(g)]
    for k, spec in schema.items():
        t = spec.get("type", "string")
        if t == "string" and quoted:
            values[k] = quoted.pop(0)
        elif t == "path" and paths:
            values[k] = paths.pop(0)
    for k, spec in schema.items():
        if k not in values and "default" in spec:
            values[k] = spec["default"]
    missing = [k for k, spec in schema.items() if spec.get("required", True) and k not in values]
    return values, missing


def render(template: str, schema: Dict[str, Dict[str, Any]], values: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Fill {slots} after validating each value. Returns (text, rejected_slots). An invalid value is rejected, never sanitised into something the user did not say."""
    rejected, safe = [], {}
    for k, spec in schema.items():
        if k not in values:
            continue
        v, t = values[k], spec.get("type", "string")
        if t == "number":
            try:
                x = float(v)
                safe[k] = str(int(x)) if x == int(x) else repr(x)
            except Exception:
                rejected.append(k)
        elif t == "path":
            if isinstance(v, str) and _SAFE_PATH.match(v) and ".." not in v.replace("\\", "/").split("/"):
                safe[k] = v
            else:
                rejected.append(k)
        else:
            if isinstance(v, str) and _SAFE_STR.match(v):
                safe[k] = v
            else:
                rejected.append(k)
    missing_in_template = [s for s in _SLOT.findall(template) if s not in safe]
    out = _SLOT.sub(lambda m: safe.get(m.group(1), m.group(0)), template)
    return out, rejected + [s for s in missing_in_template if s not in rejected]


def ctx_ok(pre: Dict[str, Any], ctx: Optional[Dict[str, Any]]) -> bool:
    """Preconditions ({window_kind, mode, editor}) hold in the current context (a prefix match for window_kind). No context given: nothing can be ruled out."""
    if not pre or not ctx:
        return True
    for k, want in pre.items():
        have = ctx.get(k)
        if have is None:
            continue
        if k == "window_kind":
            if not str(have).startswith(str(want)):
                return False
        elif str(have).lower() != str(want).lower():
            return False
    return True


def _reliability(r: Dict[str, Any]) -> float:
    a, b = C.PRIORS.get(r.get("trust", "seed"), (1, 1))
    return (r.get("n_ok", 0) + a) / (r.get("n_ok", 0) + r.get("n_fail", 0) + a + b)


class FastPaths:
    name = "fast"

    def __init__(self, st):
        self.st = st
        self.db = st.sql("learn")

    def _overlay(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge the mutable learning state (learn.db:fast_stats) over the immutable Lance rows: counts add to the ingest-time seed counts; a promotion / demotion overrides trust and verified."""
        if not rows:
            return rows
        ids = ", ".join("?" for _ in rows)
        stats = {s["fast_id"]: s for s in self.db.rows(f"SELECT * FROM fast_stats WHERE fast_id IN ({ids})", [r["fast_id"] for r in rows])}
        for r in rows:
            s = stats.get(r["fast_id"])
            if not s:
                continue
            r["n_ok"] = int(r["n_ok"]) + s["n_ok"]
            r["n_fail"] = int(r["n_fail"]) + s["n_fail"]
            r["consecutive_fail"] = s["consecutive_fail"]
            r["ok_runs"] = json.loads(s["ok_runs_json"] or "[]")
            r["last_ok_ts"] = max(float(r.get("last_ok_ts") or 0), float(s["last_ok_ts"] or 0))
            if s["trust_override"]:
                r["trust"] = s["trust_override"]
            if s["verified"] >= 0:
                r["verified"] = bool(s["verified"])
        return rows

    # ---- writes -------------------------------------------------------------------------------------------------------------------------------------
    def upsert(self, records: Iterable[Dict[str, Any]]) -> UpsertReport:
        rows = []
        for r in records:
            r = dict(r)
            kind = r.get("kind", "hotkey")
            payload = r.get("payload", "")
            if not payload or not r.get("app_key"):
                continue
            r["kind"] = kind
            r["fast_id"] = r.get("fast_id") or fast_id(r["app_key"], kind, payload, r.get("context", ""))
            r["trust"] = r.get("trust") or SOURCE_TRUST.get(r.get("source", ""), "seed")
            r["verified"] = bool(r.get("verified", r["trust"] == "verified"))
            r["safety"] = r.get("safety") or safety_of(" ".join([r.get("task_pattern", ""), r.get("command_label", ""), str(r.get("command_id", "")).split(":", 1)[-1]]))
            if kind in ("script", "com", "cli") and not r.get("sandbox"):
                r["sandbox"] = "scripting_route"
            for k in ("params_schema_json", "preconditions_json"):
                if isinstance(r.get(k), (dict, list)):
                    r[k] = json.dumps(r[k], sort_keys=True)
            r.pop("command_label", None)
            rows.append(r)
        ins, upd, deg = lt.upsert(self.st, "fast_paths", rows, "task_pattern", lambda x: x.get("task_pattern") or x.get("command_id", ""))
        for app in {r["app_key"] for r in rows}:
            self.st.bump(f"fast:{app}")
        return UpsertReport(self.name, ins, upd, 0, deg)

    # ---- reads --------------------------------------------------------------------------------------------------------------------------------------
    def _evidence(self, r: Dict[str, Any], goal: str = "", ctx: Optional[Dict[str, Any]] = None, score: float = 0.0) -> Evidence:
        direct = bool(r["verified"]) or r["trust"] in DIRECT_TRUST
        payload, missing, rejected = r["payload"], [], []
        schema = json.loads(r.get("params_schema_json") or "{}")
        if schema:
            vals, missing = extract_slots(goal, schema)
            payload, rejected = render(r["payload"], schema, vals)
            missing = sorted(set(missing) | set(s for s in rejected))
        route = KIND_ROUTE.get(r["kind"], "hotkey")
        probe = (not direct) or bool(missing)
        return Evidence("fast", r["app_key"], r["kind"], r["task_pattern"] or payload, [r["command_id"]] if r.get("command_id") else [],
                        {"fast_id": r["fast_id"], "kind": r["kind"], "payload": payload, "route": route, "verified": bool(r["verified"]), "probe": probe, "missing": missing,
                         "sandbox": r.get("sandbox", ""), "context": r.get("context", "")},
                        r["trust"], round(_reliability(r), 4), C.ROUTE_COST_MS.get(route, 100), r["safety"], f"fast:{r['fast_id'][:10]}:{r['source']}", "", score)

    def by_command(self, app_key: str, command_id: str, ctx: Optional[Dict[str, Any]] = None, limit: int = 5) -> List[Evidence]:
        rows = self._overlay(lt.fetch(self.st, "fast_paths", lt.where_app(app_key, f"command_id = {lt.q(command_id)}"), 200))
        rows = [r for r in rows if ctx_ok(json.loads(r.get("preconditions_json") or "{}"), ctx)]
        rows.sort(key=lambda r: (-(1 if (r["verified"] or r["trust"] in DIRECT_TRUST) else 0), -_reliability(r), C.ROUTE_COST_MS.get(KIND_ROUTE.get(r["kind"], "hotkey"), 100)))
        return [self._evidence(r, "", ctx) for r in rows[:limit]]

    def by_goal(self, app_key: str, goal: str, ctx: Optional[Dict[str, Any]] = None, limit: int = 5) -> List[Evidence]:
        out = []
        for r in self._overlay(lt.search(self.st, "fast_paths", goal, app_key, limit=limit * 2)):
            if ctx_ok(json.loads(r.get("preconditions_json") or "{}"), ctx):
                out.append(self._evidence(r, goal, ctx, r["_rrf"]))
        return out[:limit]

    def get(self, fid: str) -> Optional[Dict[str, Any]]:
        rows = self._overlay(lt.fetch(self.st, "fast_paths", f"fast_id = {lt.q(fid)}", 1))
        return rows[0] if rows else None

    # ---- learning -----------------------------------------------------------------------------------------------------------------------------------
    def observe(self, o: Outcome) -> Optional[Dict[str, Any]]:
        """Record a tried route. State lives in learn.db (not in the Lance row), so a hot-path update never makes a row invisible to FTS."""
        fid = (o.step.args or {}).get("fast_id")
        if not fid:
            return None
        r = self.get(fid)
        if not r:
            return None
        ok_runs = list(r.get("ok_runs") or [])
        vals: Dict[str, Any] = {}
        with self.db.lock:
            self.db.execute("INSERT OR IGNORE INTO fast_stats(fast_id) VALUES(?)", (fid,))
            if o.ok:
                if o.run_id and o.run_id not in ok_runs:
                    ok_runs.append(o.run_id)
                self.db.execute("UPDATE fast_stats SET n_ok=n_ok+1, consecutive_fail=0, last_ok_ts=?, ok_runs_json=? WHERE fast_id=?", (time.time(), json.dumps(ok_runs[-20:]), fid))
                vals = {"ok": True}
                if not r["verified"] and len(set(ok_runs)) >= C.PROMOTE_AFTER_OK:
                    self.db.execute("UPDATE fast_stats SET verified=1, trust_override='verified' WHERE fast_id=?", (fid,))
                    vals["promoted"] = True
            else:
                cf = int(r["consecutive_fail"]) + 1
                self.db.execute("UPDATE fast_stats SET n_fail=n_fail+1, consecutive_fail=? WHERE fast_id=?", (cf, fid))
                vals = {"ok": False}
                if cf >= C.DEMOTE_AFTER_FAIL:
                    ladder = C.TRUST_LADDER
                    i = ladder.index(r["trust"]) if r["trust"] in ladder else 0
                    self.db.execute("UPDATE fast_stats SET trust_override=?, verified=0, consecutive_fail=0 WHERE fast_id=?", (ladder[max(0, i - 1)], fid))
                    vals["demoted_to"] = ladder[max(0, i - 1)]
            self.db.commit()
        self.st.bump(f"fast:{r['app_key']}")
        return vals

    def stats(self, app_key: str = "") -> Dict[str, Any]:
        n = self.st.table("fast_paths").count_rows(lt.where_app(app_key)) if self.st.count("fast_paths") else 0
        return {"rows": int(n)}

    def forget_app(self, app_key: str) -> int:
        n = lt.drop_app(self.st, "fast_paths", app_key)
        self.st.bump(f"fast:{app_key}")
        return n
