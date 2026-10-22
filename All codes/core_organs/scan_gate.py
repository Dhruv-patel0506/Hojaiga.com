"""
scan_gate -- the pre-save validation gate for an app scan, and the status store behind the recursive re-scan.

A scan is written to the master RAG as COMPLETE only when it contains the core controls of its application's Universal UI Archetype (rag/archetypes.py): a Calculator needs a keypad and a
display, a raster editor a canvas and a tool set, a chat app a conversation list and an input. Anything else is stored as INCOMPLETE_SCAN, is NOT retrievable as a workflow, and is listed by
pending_rescans() so the caller scans again (recursive_scan runs that loop with a growing discovery budget).

    validate_scan(controls, app_name="", title="")  -> verdict {status, archetype, archetype_source, components[], missing[], verified, reason}
    record_scan(db_path, app_key, app_name, verdict, purpose, steps)  -> {saved, status, ...}      never raises
    pending_rescans(db_path) / get_status(db_path, app_key)
    recursive_scan(scan_fn, app_name, max_rescans=2)                  -> (scan, verdict, history)

Which archetype an app belongs to is decided from the app's NAME when it is a known example of a class (so a scan that captured the wrong window is judged against the app it was meant to be),
otherwise from the words of its own controls (ArchetypeRouter.assess). Component vocabularies are generic UI words, never application names.

Storage: the master FTS table (causal_procedures_fts) has no status column and cannot be altered, so the status lives in a small regular side table `app_scan_status` in the same database. The
FTS row is written only for COMPLETE scans. Offline, CPU only; the only I/O is the sqlite file the caller names.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from .rag import archetypes as _A
except ImportError:                                                           # flat import (core_organs on sys.path)
    from core_organs.rag import archetypes as _A                              # type: ignore

COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE_SCAN"
MIN_CONTROLS = 5
UNRESOLVED_MIN_CONTROLS = 12            # an archetype-less scan is accepted (verified=False) only when it is this rich and spans >= 2 roles

DIGITS = "zero one two three four five six seven eight nine".split()
_DIGIT_WORD = {str(i): w for i, w in enumerate(DIGITS)}
# verbs that make a control an ACTION on a region ("Import to canvas") rather than the region itself
_REGION_VERBS = {"import", "export", "paste", "resize", "clear", "save", "open", "insert", "add", "to", "new", "close", "show", "hide"}

# archetype id -> core components. kind "controls": distinct vocabulary hits across the scan; kind "region": a named surface (verbs above disqualify a name);
# "roles": an alternative way to satisfy the component (a control of that role exists).
CORE: Dict[str, List[Dict[str, Any]]] = {
    "calculator": [
        {"id": "keypad", "kind": "controls", "min": 8,
         "words": set(DIGITS) | {"plus", "minus", "equals", "divide", "multiply", "times", "subtract", "percent", "decimal", "point", "negate", "backspace", "clear"}},
        {"id": "display", "kind": "region", "min": 1, "words": {"display", "result", "results", "expression", "output", "answer"}},
    ],
    "raster_editor": [
        {"id": "canvas", "kind": "region", "min": 1, "words": {"canvas", "drawing", "artboard", "whiteboard"}},
        {"id": "tools", "kind": "controls", "min": 3,
         "words": {"brush", "brushes", "pencil", "eraser", "fill", "shapes", "shape", "select", "selection", "text", "magnifier", "picker", "color", "colors", "crop", "rotate"}},
    ],
    "chat_messenger": [
        {"id": "conversations", "kind": "controls", "min": 2,
         "words": {"chat", "chats", "conversation", "conversations", "channel", "channels", "message", "messages", "direct", "calls", "status", "community", "communities", "inbox"}},
        {"id": "input", "kind": "controls", "min": 1, "words": {"compose", "type", "search"}, "roles": {"edit"}},
    ],
    "text_editor": [
        {"id": "surface", "kind": "controls", "min": 1, "words": {"editor", "text"}, "roles": {"document", "edit"}},
        {"id": "menus", "kind": "controls", "min": 3, "words": {"file", "edit", "view", "format", "find", "replace", "save"}},
    ],
    "word_processor": [
        {"id": "surface", "kind": "controls", "min": 1, "words": {"document"}, "roles": {"document", "edit"}},
        {"id": "formatting", "kind": "controls", "min": 3, "words": {"font", "paragraph", "styles", "style", "bold", "italic", "underline", "heading", "align", "bullets", "numbering"}},
    ],
    "spreadsheet": [
        {"id": "grid", "kind": "controls", "min": 2, "words": {"cell", "cells", "sheet", "sheets", "column", "row", "formula", "formulas"}},
    ],
    "presentation": [
        {"id": "slides", "kind": "controls", "min": 3, "words": {"slide", "slides", "layout", "design", "transitions", "animations", "notes", "theme", "themes"}},
    ],
    "browser": [
        {"id": "navigation", "kind": "controls", "min": 3, "words": {"back", "forward", "reload", "refresh", "address", "bookmarks", "history", "downloads", "extensions"}},
        {"id": "input", "kind": "controls", "min": 1, "words": {"address", "search"}, "roles": {"edit"}},
    ],
    "code_ide": [
        {"id": "workbench", "kind": "controls", "min": 3, "words": {"explorer", "terminal", "debug", "run", "search", "extensions", "source", "output", "problems"}},
    ],
}


def _toks(name: str) -> List[str]:
    s = (name or "").strip().lower()
    if s in _DIGIT_WORD:
        return [_DIGIT_WORD[s]]
    return re.findall(r"[a-z][a-z0-9]*|[0-9]", s)


def _role(c: Dict[str, Any]) -> str:
    r = str(c.get("role") or c.get("type") or c.get("control_type") or "").strip()
    return re.sub(r"Control$", "", r).lower()


def _name(c: Dict[str, Any]) -> str:
    return str(c.get("name") or c.get("text") or "").strip()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def name_archetype(app_name: str) -> Optional[str]:
    """The archetype an application belongs to by its own name (an exact known example first, then a containing name), else None."""
    n = _norm(app_name)
    if len(n) < 3:
        return None
    for a in _A.ARCHETYPES:
        if n in {_norm(x) for x in a["train"] + a["test"]}:
            return a["id"]
    for a in _A.ARCHETYPES:
        for x in a["train"] + a["test"]:
            m = _norm(x)
            if len(m) >= 4 and (m in n or n in m):
                return a["id"]
    return None


def content_archetype(controls: Sequence[Dict[str, Any]], app_name: str = "", title: str = "") -> Tuple[Optional[str], Dict[str, Any]]:
    """The archetype the scan's own control words point at (no name used), with the router's assessment."""
    sig = {"app": "", "title": title or "", "controls": [(_role(c), _name(c)) for c in controls]}
    a = _A.ArchetypeRouter().assess(sig, top=3)
    if a["status"] in ("candidate", "weak_candidate") and a["ranked"] and a["ranked"][0][1] > 0:
        return a["ranked"][0][0], a
    return None, a


def _eval_component(spec: Dict[str, Any], controls: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    words = spec["words"]
    hits = set()
    for c in controls:
        toks = _toks(_name(c))
        if not toks:
            continue
        if spec["kind"] == "region" and (set(toks) & _REGION_VERBS):
            continue
        hits |= set(toks) & words
    role_hit = bool(spec.get("roles")) and any(_role(c) in spec["roles"] for c in controls)
    ok = len(hits) >= spec["min"] or role_hit
    return {"id": spec["id"], "ok": ok, "need": spec["min"], "hits": sorted(hits), "by_role": role_hit and len(hits) < spec["min"]}


def _generic_components(archetype_id: str) -> List[Dict[str, Any]]:
    sig = set(_A.BY_ID[archetype_id]["signals"])
    return [{"id": "class_signals", "kind": "controls", "min": 2, "words": sig}]


def validate_scan(controls: Sequence[Dict[str, Any]], app_name: str = "", title: str = "") -> Dict[str, Any]:
    """Judge a scan against its archetype's core components. `controls` carry name + role/type (any scanner format). Never raises."""
    try:
        controls = [c for c in (controls or []) if isinstance(c, dict)]
        n = len(controls)
        by_name = name_archetype(app_name)
        by_content, assess = content_archetype(controls, app_name, title)
        aid, source = (by_name, "name") if by_name else ((by_content, "content") if by_content else (None, "none"))
        verdict: Dict[str, Any] = {"status": INCOMPLETE, "archetype": aid, "archetype_source": source, "content_archetype": by_content,
                                   "components": [], "missing": [], "verified": False, "n_controls": n, "reason": ""}
        if by_name and by_content and by_name != by_content:
            verdict["window_mismatch"] = True                                 # the scan looks like another class of app than its name: the wrong window may have been captured
        if n < MIN_CONTROLS:
            verdict["reason"] = "too_few_controls"
            return verdict
        if aid is None:
            roles = {_role(c) for c in controls if _role(c)}
            if n >= UNRESOLVED_MIN_CONTROLS and len(roles) >= 2:
                verdict.update(status=COMPLETE, reason="archetype_unresolved_accepted_unverified")
            else:
                verdict["reason"] = "archetype_unresolved"
            return verdict
        specs = CORE.get(aid) or _generic_components(aid)
        comps = [_eval_component(s, controls) for s in specs]
        missing = [c["id"] for c in comps if not c["ok"]]
        verdict.update(components=comps, missing=missing, verified=True)
        if missing:
            verdict["reason"] = "missing:" + ",".join(missing)
        else:
            verdict.update(status=COMPLETE, reason="core_components_present")
        return verdict
    except Exception as e:                                                    # a gate that crashes must fail closed, not open
        return {"status": INCOMPLETE, "archetype": None, "archetype_source": "none", "components": [], "missing": [], "verified": False,
                "n_controls": 0, "reason": f"gate_error:{type(e).__name__}"}


# ---- persistence ---------------------------------------------------------------------------------------------------------
_FTS = ("CREATE VIRTUAL TABLE IF NOT EXISTS causal_procedures_fts USING fts5(arch_id, domain, goal, steps_json, trap_guard, tokenize='porter unicode61')")
_SIDE = ("CREATE TABLE IF NOT EXISTS app_scan_status (app_key TEXT PRIMARY KEY, app_name TEXT, status TEXT NOT NULL, archetype TEXT, verified INTEGER, "
         "missing_json TEXT, n_controls INTEGER, attempts INTEGER DEFAULT 0, fts_rowid INTEGER, reason TEXT, updated_at REAL)")


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def record_scan(db_path: str, app_key: str, app_name: str, verdict: Dict[str, Any], purpose: str = "", steps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Store the verdict. COMPLETE -> side-table row + the retrievable FTS procedure; INCOMPLETE_SCAN -> side-table row only (never retrievable). Never raises."""
    try:
        conn = _connect(db_path)
        try:
            conn.execute(_FTS)
            conn.execute(_SIDE)
            old = conn.execute("SELECT attempts, fts_rowid FROM app_scan_status WHERE app_key=?", (app_key,)).fetchone()
            attempts = (old[0] if old else 0) + 1
            rowid = old[1] if old else None
            status = verdict.get("status", INCOMPLETE)
            if status == COMPLETE:
                if rowid:
                    conn.execute("DELETE FROM causal_procedures_fts WHERE rowid=?", (rowid,))
                cur = conn.execute("INSERT INTO causal_procedures_fts (arch_id, domain, goal, steps_json, trap_guard) VALUES (?,?,?,?,?)",
                                   (f"UI_{(verdict.get('archetype') or 'unclassified').upper()}", "desktop_app",
                                    f"Reverse-Engineered Workflow for {app_name}: {purpose}", json.dumps(steps or []),
                                    "AUTO_DISCOVERY_VERIFIED" if verdict.get("verified") else "AUTO_DISCOVERY_UNVERIFIED_ARCHETYPE"))
                rowid = cur.lastrowid
            conn.execute("INSERT OR REPLACE INTO app_scan_status (app_key, app_name, status, archetype, verified, missing_json, n_controls, attempts, fts_rowid, reason, updated_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (app_key, app_name, status, verdict.get("archetype"), int(bool(verdict.get("verified"))), json.dumps(verdict.get("missing", [])),
                          verdict.get("n_controls", 0), attempts, rowid, verdict.get("reason", ""), time.time()))
            conn.commit()
        finally:
            conn.close()
        return {"saved": True, "status": status, "attempts": attempts, "fts_rowid": rowid}
    except Exception as e:
        return {"saved": False, "status": verdict.get("status", INCOMPLETE), "error": f"{type(e).__name__}: {e}"}


def get_status(db_path: str, app_key: str) -> Optional[Dict[str, Any]]:
    try:
        conn = _connect(db_path)
        try:
            r = conn.execute("SELECT status, archetype, verified, missing_json, n_controls, attempts, reason FROM app_scan_status WHERE app_key=?", (app_key,)).fetchone()
        finally:
            conn.close()
    except Exception:
        return None
    if not r:
        return None
    return {"status": r[0], "archetype": r[1], "verified": bool(r[2]), "missing": json.loads(r[3] or "[]"), "n_controls": r[4], "attempts": r[5], "reason": r[6]}


def pending_rescans(db_path: str, max_attempts: int = 6) -> List[str]:
    """App keys whose last scan was INCOMPLETE_SCAN and still have attempts left."""
    try:
        conn = _connect(db_path)
        try:
            return [r[0] for r in conn.execute("SELECT app_key FROM app_scan_status WHERE status=? AND attempts<? ORDER BY updated_at", (INCOMPLETE, max_attempts))]
        finally:
            conn.close()
    except Exception:
        return []


def recursive_scan(scan_fn: Callable[[int], Dict[str, Any]], app_name: str, max_rescans: int = 2,
                   on_attempt: Optional[Callable[[int, Dict[str, Any]], None]] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    """Scan, validate, and scan again (attempt index grows so scan_fn can widen its discovery) until COMPLETE or the rescans are used up.
    scan_fn(attempt) returns {"controls": [...], "title": str, ...} or None when nothing could be scanned. The best scan (most components present) is returned on failure."""
    history: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None
    best_v: Dict[str, Any] = {"status": INCOMPLETE, "reason": "no_scan", "missing": [], "components": [], "n_controls": 0, "verified": False, "archetype": None}
    best_score = -1
    for attempt in range(max_rescans + 1):
        try:
            scan = scan_fn(attempt)
        except Exception as e:
            history.append({"attempt": attempt, "status": INCOMPLETE, "reason": f"scan_error:{type(e).__name__}"})
            continue
        if not scan:
            history.append({"attempt": attempt, "status": INCOMPLETE, "reason": "no_scan"})
            continue
        v = validate_scan(scan.get("gate_controls") or scan.get("controls") or [], app_name, scan.get("title", ""))
        history.append({"attempt": attempt, "status": v["status"], "reason": v["reason"], "missing": v["missing"], "n_controls": v["n_controls"]})
        if on_attempt:
            on_attempt(attempt, v)
        score = sum(1 for c in v["components"] if c["ok"]) * 1000 + v["n_controls"]
        if score > best_score:
            best, best_v, best_score = scan, v, score
        if v["status"] == COMPLETE:
            return scan, v, history
    return best, best_v, history
