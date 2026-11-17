"""
professor.history -- the RELATIONAL STORE behind the Professor's "muscle memory" (SQLite: a local RDBMS, no server, no keys).

  transitions     every action performed (probing, executing, exploring): before-state, motor primitive, after-state, effect, ok, toolkit, route ... - the training data of the ML models
  apps            the APP REGISTRY: which applications were seen, their toolkit family, executable, how many guide documents / verbs / actions each has
  guide_runs      every procedure taken from a USER GUIDE and what became of it: goal, citation, steps, how many grounded, performed?, ok?, WHY it failed (the fix-and-rerun record)
  pointer_traces  the VIRTUAL MOUSE's glide for an action: start, end, planned and actual seconds, number of waypoints (linked to the transition)

ONE `transitions` table with an `app_key` column (not a table per application: dynamic table names are an injection / migration hazard and cross-application queries stay trivial).
Only compact summaries are stored (state signatures + a one-line note), never screenshots. Local only; `forget(app)` removes an application everywhere.

  log(...)             append a transition                      effects_of / best_route / recoveries / order_effects / recent / stats
  register_app(...)    upsert an application in the registry    registry(app)  -> per-application summary (what actions, how reliable, which guides)
  log_guide_run(...)   record a guide procedure's outcome       guide_runs(app) / unresolved(app) -> what still fails and why
  log_pointer(...)     record a virtual-mouse trace
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from . import config as CFG

HISTORY_DB = os.path.join(CFG.DATA_DIR, "history.db")
PRIMITIVES = ("click", "invoke", "select", "toggle", "set_value", "key", "command", "text", "escape", "close", "pair", "glide", "adapter")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transitions(
    id INTEGER PRIMARY KEY, app_key TEXT NOT NULL, ts REAL, source TEXT, primitive TEXT, target TEXT, target_id TEXT, route TEXT,
    s0_sig TEXT, s0_note TEXT, s1_sig TEXT, s1_note TEXT, effect TEXT, ok INTEGER, unwound INTEGER, session TEXT, detail TEXT,
    toolkit TEXT, archetype TEXT, role TEXT, safety TEXT, latency_ms REAL);
CREATE INDEX IF NOT EXISTS i_tr_app ON transitions(app_key, target);
CREATE INDEX IF NOT EXISTS i_tr_src ON transitions(app_key, source);
CREATE TABLE IF NOT EXISTS apps(
    app_key TEXT PRIMARY KEY, name TEXT, exe TEXT, toolkit TEXT, tier INTEGER, first_seen REAL, last_seen REAL, guide_docs INTEGER DEFAULT 0, verbs INTEGER DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS guide_runs(
    id INTEGER PRIMARY KEY, app_key TEXT NOT NULL, ts REAL, source TEXT, cite TEXT, goal TEXT, steps INTEGER, grounded REAL, performed INTEGER, ok INTEGER, why TEXT, session TEXT, attempt INTEGER DEFAULT 1);
CREATE INDEX IF NOT EXISTS i_gr_app ON guide_runs(app_key, goal);
CREATE TABLE IF NOT EXISTS pointer_traces(
    id INTEGER PRIMARY KEY, transition_id INTEGER, app_key TEXT, ts REAL, x0 REAL, y0 REAL, x1 REAL, y1 REAL, planned_s REAL, actual_s REAL, waypoints INTEGER, virtual INTEGER);
"""
_NEW_TRANSITION_COLUMNS = {"toolkit": "TEXT", "archetype": "TEXT", "role": "TEXT", "safety": "TEXT", "latency_ms": "REAL"}


class History:
    def __init__(self, path: Optional[str] = None):
        self.path = path or HISTORY_DB
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.RLock()
        self.db.executescript(_SCHEMA)
        have = {r[1] for r in self.db.execute("PRAGMA table_info(transitions)")}
        for col, typ in _NEW_TRANSITION_COLUMNS.items():                  # a history written by an earlier version keeps working
            if col not in have:
                self.db.execute(f"ALTER TABLE transitions ADD COLUMN {col} {typ}")
        self.db.commit()
        self.session = uuid.uuid4().hex[:8]
        self.listeners: List[Any] = []                                      # callables(row_dict) - the ML learner subscribes here: every logged transition is a training example

    # ------------------------------------------------------------------------------------------------------------ writes
    def log(self, app_key: str, source: str, primitive: str, target: str, route: str = "", s0_sig: str = "", s0_note: str = "", s1_sig: str = "", s1_note: str = "", effect: str = "",
            ok: bool = False, unwound: Optional[bool] = None, target_id: str = "", detail: Optional[Dict[str, Any]] = None, toolkit: str = "", archetype: str = "", role: str = "",
            safety: str = "", latency_ms: float = 0.0) -> int:
        with self._lock:
            cur = self.db.execute("INSERT INTO transitions(app_key,ts,source,primitive,target,target_id,route,s0_sig,s0_note,s1_sig,s1_note,effect,ok,unwound,session,detail,toolkit,archetype,role,safety,latency_ms)"
                                  " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (app_key, time.time(), source, primitive, target, target_id, route, s0_sig, s0_note[:200], s1_sig, s1_note[:300], effect, int(bool(ok)),
                                   None if unwound is None else int(bool(unwound)), self.session, json.dumps(detail or {}, ensure_ascii=False, default=str)[:1500], toolkit, archetype, role, safety,
                                   float(latency_ms)))
            self.db.commit()
            rid = int(cur.lastrowid)
        if self.listeners:
            row = {"id": rid, "app_key": app_key, "source": source, "primitive": primitive, "target": target, "route": route, "effect": effect, "ok": int(bool(ok)), "toolkit": toolkit,
                   "archetype": archetype, "role": role, "safety": safety, "latency_ms": latency_ms, "s0_note": s0_note, "detail": detail or {}}
            for fn in list(self.listeners):
                try:
                    fn(row)
                except Exception:
                    pass
        return rid

    def register_app(self, app_key: str, name: str = "", exe: str = "", toolkit: str = "", tier: int = 0, guide_docs: Optional[int] = None, verbs: Optional[int] = None, notes: str = "") -> None:
        now = time.time()
        with self._lock:
            row = self.db.execute("SELECT app_key FROM apps WHERE app_key=?", (app_key,)).fetchone()
            if row is None:
                self.db.execute("INSERT INTO apps(app_key,name,exe,toolkit,tier,first_seen,last_seen,guide_docs,verbs,notes) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                (app_key, name, exe, toolkit, tier, now, now, guide_docs or 0, verbs or 0, notes))
            else:
                sets, vals = ["last_seen=?"], [now]
                for col, v in (("name", name), ("exe", exe), ("toolkit", toolkit), ("tier", tier or None), ("guide_docs", guide_docs), ("verbs", verbs), ("notes", notes)):
                    if v not in (None, "", 0) or (col in ("guide_docs", "verbs") and v is not None):
                        sets.append(f"{col}=?")
                        vals.append(v)
                self.db.execute(f"UPDATE apps SET {', '.join(sets)} WHERE app_key=?", vals + [app_key])
            self.db.commit()

    def log_guide_run(self, app_key: str, source: str, cite: str, goal: str, steps: int, grounded: float, performed: bool, ok: bool, why: str = "", attempt: int = 1) -> int:
        with self._lock:
            cur = self.db.execute("INSERT INTO guide_runs(app_key,ts,source,cite,goal,steps,grounded,performed,ok,why,session,attempt) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (app_key, time.time(), source, cite, goal, steps, float(grounded), int(bool(performed)), int(bool(ok)), why[:400], self.session, attempt))
            self.db.commit()
            return int(cur.lastrowid)

    def log_pointer(self, app_key: str, x0: float, y0: float, x1: float, y1: float, planned_s: float, actual_s: float, waypoints: int, virtual: bool = True, transition_id: Optional[int] = None) -> int:
        with self._lock:
            cur = self.db.execute("INSERT INTO pointer_traces(transition_id,app_key,ts,x0,y0,x1,y1,planned_s,actual_s,waypoints,virtual) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                  (transition_id, app_key, time.time(), x0, y0, x1, y1, planned_s, actual_s, waypoints, int(bool(virtual))))
            self.db.commit()
            return int(cur.lastrowid)

    def link_pointer(self, pointer_id: int, transition_id: int) -> None:
        """Attach a virtual-mouse trace to the action it was made for."""
        with self._lock:
            self.db.execute("UPDATE pointer_traces SET transition_id=? WHERE id=?", (transition_id, pointer_id))
            self.db.commit()

    # ---------------------------------------------------------------------------------------------------------- queries
    def recent(self, app_key: str, n: int = 20) -> List[Dict[str, Any]]:
        cur = self.db.execute("SELECT ts,source,primitive,target,route,effect,ok,unwound,s0_sig,s1_sig,s1_note,toolkit,role,latency_ms FROM transitions WHERE app_key=? ORDER BY id DESC LIMIT ?", (app_key, n))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def rows(self, app_key: str = "", since_id: int = 0, limit: int = 100000) -> List[Dict[str, Any]]:
        """Training rows in order (for the ML learner's replay)."""
        q = "SELECT id,app_key,source,primitive,target,route,effect,ok,toolkit,archetype,role,safety,latency_ms,s0_note,detail FROM transitions WHERE id>?" + (" AND app_key=?" if app_key else "") + " ORDER BY id LIMIT ?"
        cur = self.db.execute(q, (since_id, app_key, limit) if app_key else (since_id, limit))
        cols = [c[0] for c in cur.description]
        out = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            try:
                d["detail"] = json.loads(d.get("detail") or "{}")
            except Exception:
                d["detail"] = {}
            out.append(d)
        return out

    def effects_of(self, app_key: str, target: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for eff, n in self.db.execute("SELECT effect, COUNT(*) FROM transitions WHERE app_key=? AND target=? AND effect<>'' GROUP BY effect", (app_key, target)):
            out[eff] = n
        return out

    def best_route(self, app_key: str, target: str) -> str:
        r = self.db.execute("SELECT route, COUNT(*) c FROM transitions WHERE app_key=? AND target=? AND ok=1 AND route<>'' GROUP BY route ORDER BY c DESC LIMIT 1", (app_key, target)).fetchone()
        return r[0] if r else ""

    def recoveries(self, app_key: str) -> List[Dict[str, Any]]:
        """How the application was put back after something opened that should not stay open: [{trigger, primitive, route, times}]."""
        cur = self.db.execute("SELECT target, primitive, route, COUNT(*), SUM(ok) FROM transitions WHERE app_key=? AND source='recovery' GROUP BY target, primitive, route ORDER BY COUNT(*) DESC", (app_key,))
        return [{"trigger": t, "primitive": p, "route": r, "times": n, "worked": int(w or 0)} for t, p, r, n, w in cur.fetchall()]

    def order_effects(self, app_key: str) -> List[Dict[str, Any]]:
        out = []
        for target, effect, detail in self.db.execute("SELECT target, effect, detail FROM transitions WHERE app_key=? AND primitive='pair' ORDER BY id", (app_key,)):
            d = json.loads(detail or "{}")
            out.append({"pair": target, "verdict": effect, **d})
        return out

    def stats(self, app_key: str = "") -> Dict[str, Any]:
        q = "SELECT COUNT(*), SUM(ok), COUNT(DISTINCT target), COUNT(DISTINCT app_key) FROM transitions" + (" WHERE app_key=?" if app_key else "")
        n, ok, targets, apps = self.db.execute(q, (app_key,) if app_key else ()).fetchone()
        by_src = dict(self.db.execute("SELECT source, COUNT(*) FROM transitions" + (" WHERE app_key=?" if app_key else "") + " GROUP BY source", (app_key,) if app_key else ()).fetchall())
        return {"transitions": n or 0, "with_effect": int(ok or 0), "targets": targets or 0, "apps": apps or 0, "by_source": by_src}

    def registry(self, app_key: str = "") -> List[Dict[str, Any]]:
        """The app registry: for every application - toolkit, tier, guide documents, how many distinct actions were performed, how reliable they were, which routes worked, guide procedures tried / passed."""
        q = "SELECT app_key,name,exe,toolkit,tier,first_seen,last_seen,guide_docs,verbs,notes FROM apps" + (" WHERE app_key=?" if app_key else "") + " ORDER BY tier, app_key"
        out = []
        for r in self.db.execute(q, (app_key,) if app_key else ()).fetchall():
            ak = r[0]
            n, ok, targets = self.db.execute("SELECT COUNT(*), SUM(ok), COUNT(DISTINCT target) FROM transitions WHERE app_key=?", (ak,)).fetchone()
            routes = dict(self.db.execute("SELECT route, COUNT(*) FROM transitions WHERE app_key=? AND ok=1 AND route<>'' GROUP BY route ORDER BY COUNT(*) DESC LIMIT 5", (ak,)).fetchall())
            gr = self.db.execute("SELECT COUNT(DISTINCT goal), COUNT(DISTINCT CASE WHEN ok=1 THEN goal END) FROM guide_runs WHERE app_key=?", (ak,)).fetchone()
            out.append({"app": ak, "name": r[1], "exe": r[2], "toolkit": r[3], "tier": r[4], "guide_docs": r[7], "verbs": r[8], "actions_performed": n or 0, "distinct_targets": targets or 0,
                        "action_success": round((ok or 0) / n, 3) if n else None, "best_routes": routes, "guide_procedures_tried": gr[0], "guide_procedures_passed": gr[1], "notes": r[9]})
        return out

    def guide_runs(self, app_key: str, limit: int = 50) -> List[Dict[str, Any]]:
        cur = self.db.execute("SELECT ts,source,cite,goal,steps,grounded,performed,ok,why,attempt FROM guide_runs WHERE app_key=? ORDER BY id DESC LIMIT ?", (app_key, limit))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def unresolved(self, app_key: str) -> List[Dict[str, Any]]:
        """Guide procedures whose LATEST attempt failed: what still needs a fix, and why."""
        cur = self.db.execute("SELECT goal, cite, why, attempt, ts FROM guide_runs g WHERE app_key=? AND ok=0 AND id=(SELECT MAX(id) FROM guide_runs WHERE app_key=g.app_key AND goal=g.goal) ORDER BY ts", (app_key,))
        return [{"goal": g, "cite": c, "why": w, "attempts": a, "ts": t} for g, c, w, a, t in cur.fetchall()]

    def pointer_stats(self, app_key: str = "") -> Dict[str, Any]:
        q = "SELECT COUNT(*), AVG(planned_s), AVG(actual_s), SUM(virtual) FROM pointer_traces" + (" WHERE app_key=?" if app_key else "")
        n, p, a, v = self.db.execute(q, (app_key,) if app_key else ()).fetchone()
        return {"traces": n or 0, "avg_planned_s": round(p, 3) if p else None, "avg_actual_s": round(a, 3) if a else None, "virtual": int(v or 0)}

    def forget(self, app_key: str) -> int:
        with self._lock:
            n = 0
            for t in ("transitions", "guide_runs", "pointer_traces", "apps"):
                n += self.db.execute(f"DELETE FROM {t} WHERE app_key=?", (app_key,)).rowcount
            self.db.commit()
            return n

    def close(self) -> None:
        try:
            self.db.commit()
            self.db.close()
        except Exception:
            pass


_H: Optional[History] = None


def library() -> History:
    global _H
    if _H is None:
        _H = History()
    return _H


def primitive_of(how: str) -> str:
    """'UIA Invoke' / 'BM_CLICK -> ...' / 'WM_COMMAND 102' / 'posted click ...' / 'UIA SetValue' -> the motor primitive vocabulary."""
    h = (how or "").lower()
    for key, prim in (("setvalue", "set_value"), ("wm_command", "command"), ("select", "select"), ("toggle", "toggle"), ("invoke", "invoke"), ("bm_click", "click"), ("posted click", "click"),
                      ("click", "click"), ("key", "key"), ("text", "text")):
        if key in h:
            return prim
    return "click"
