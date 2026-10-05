"""
knowledge_store.py -- persistence for the knowledge kinds the behavior model (organ_48) did not have a home for.

Lives in the SAME sqlite file as organ_48 (data/app_behavior.db) and rides its connection, so one app's whole
dossier is one database. Everything here is DATA about an app learned at runtime; nothing is per-app code.

    bm_facts       what is TRUE of the app (framework, file types it opens, manifest, capabilities, ...) with its source
    bm_dialogs     the control schema of every dialog / pane / flyout seen (statically or live): title, fields, buttons
    bm_frontier    every discovered-but-unexplored surface (menu leaf, tab, dropdown, ...) and what exploring it found;
                   this is what lets run N+1 continue exactly where run N stopped
    bm_statevars   the app's state variables: toggles, exclusive groups (active tool), tabs, expand states
    bm_conventions universal conventions (Ctrl+S ...) tested on THIS app: obeyed / ignored / unobservable
    bm_run_log     per-run, per-phase measurements (the learning curve)
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS bm_facts (
    app_key TEXT, fact TEXT, value_json TEXT, source TEXT, confidence REAL, ts REAL,
    PRIMARY KEY (app_key, fact));
CREATE TABLE IF NOT EXISTS bm_dialogs (
    dialog_id TEXT PRIMARY KEY, app_key TEXT, title TEXT, controls_json TEXT, source TEXT, via TEXT,
    n_controls INTEGER, ts REAL);
CREATE INDEX IF NOT EXISTS bm_dlg_app ON bm_dialogs(app_key);
CREATE TABLE IF NOT EXISTS bm_frontier (
    fid TEXT PRIMARY KEY, app_key TEXT, kind TEXT, label TEXT, path TEXT, status TEXT DEFAULT 'open',
    info_gain REAL DEFAULT 0, attempts INTEGER DEFAULT 0, last_run TEXT DEFAULT '', result_json TEXT DEFAULT '{}',
    version_hash TEXT DEFAULT '', ts REAL);
CREATE INDEX IF NOT EXISTS bm_fr_app ON bm_frontier(app_key, status);
CREATE TABLE IF NOT EXISTS bm_statevars (
    app_key TEXT, var_id TEXT, name TEXT, kind TEXT, values_json TEXT, group_id TEXT, aid TEXT, ts REAL,
    PRIMARY KEY (app_key, var_id));
CREATE TABLE IF NOT EXISTS bm_conventions (
    app_key TEXT, intent TEXT, chord TEXT, verdict TEXT, evidence TEXT,
    successes INTEGER DEFAULT 0, failures INTEGER DEFAULT 0, ts REAL,
    PRIMARY KEY (app_key, intent, chord));
CREATE TABLE IF NOT EXISTS bm_run_log (
    run_id TEXT, app_key TEXT, run_no INTEGER, phase TEXT, metrics_json TEXT, ts REAL);
CREATE INDEX IF NOT EXISTS bm_rl_app ON bm_run_log(app_key, run_no);
"""

def ensure(model) -> None:
    """Create the tables once per model. The flag lives ON the model object: an id()-keyed cache is wrong, because Python reuses
    the id of a garbage-collected connection and a brand-new database would then be believed to have its tables already."""
    if getattr(model, "_ks_ready", None) is model._conn:
        return
    model._conn.executescript(SCHEMA)
    model._conn.commit()
    model._ks_ready = model._conn


_PERSONAL = re.compile(r"^\s*(signed in as|logged in as|log(?:ged)? in as|account:|welcome back,?|welcome,?|hi,?|hello,?|profile of|user:)\s+\S.*$", re.I)


def redact(text: str) -> str:
    """A UI label that carries a PERSON ('Signed in as <name>', 'Welcome back, <name>') is stored without the person: the knowledge
    database is synced to a repository, and what an app calls a control is knowledge while who is signed in is not."""
    if not text:
        return text
    m = _PERSONAL.match(text)
    return (m.group(1).strip() + " <redacted>") if m else text


def origin_class(origin: str) -> str:
    """Which INDEPENDENT kind of source a command row came from (static program file / live menu crawl / explored / layout /
    shipped data pack). Corroboration counts distinct classes."""
    o = origin or ""
    for pre, label in (("static:", "static"), ("e0:", "menus_live"), ("e1:", "explored"), ("layout", "layout"), ("pack", "pack"),
                       ("keymap", "pack"), ("settings", "pack"), ("cli", "pack")):
        if o.startswith(pre):
            return label
    return "other"


# ---- facts -------------------------------------------------------------------------------

def put_fact(model, app_key: str, fact: str, value: Any, *, source: str, confidence: float = 0.9) -> None:
    ensure(model)
    model._conn.execute(
        "INSERT OR REPLACE INTO bm_facts(app_key, fact, value_json, source, confidence, ts) VALUES (?,?,?,?,?,?)",
        (app_key, fact, json.dumps(value, default=str), source, confidence, time.time()))
    model._conn.commit()


def get_fact(model, app_key: str, fact: str, default: Any = None) -> Any:
    ensure(model)
    r = model._conn.execute("SELECT value_json FROM bm_facts WHERE app_key=? AND fact=?", (app_key, fact)).fetchone()
    if not r:
        return default
    try:
        return json.loads(r["value_json"])
    except Exception:
        return default


def facts(model, app_key: str) -> Dict[str, Any]:
    ensure(model)
    out: Dict[str, Any] = {}
    for r in model._conn.execute("SELECT fact, value_json FROM bm_facts WHERE app_key=?", (app_key,)):
        try:
            out[r["fact"]] = json.loads(r["value_json"])
        except Exception:
            continue
    return out


# ---- dialogs -----------------------------------------------------------------------------

def put_dialog(model, app_key: str, title: str, controls: List[Dict[str, Any]], *, source: str, via: str = "") -> str:
    """One dialog schema. `controls` = [{kind|type, text|name, id|aid, ...}]. Same title + same control set = same row."""
    ensure(model)
    controls = [dict(c, **({"name": redact(c["name"])} if c.get("name") else {}), **({"text": redact(c["text"])} if c.get("text") else {})) for c in controls]
    title = redact(title)
    sig = sorted((str(c.get("kind") or c.get("type") or c.get("class") or ""), str(c.get("text") or c.get("name") or ""))
                 for c in controls)
    did = hashlib.md5(f"{app_key}|{(title or '').lower()}|{sig}".encode()).hexdigest()[:14]
    prev = model._conn.execute("SELECT source FROM bm_dialogs WHERE dialog_id=?", (did,)).fetchone()
    # a live observation outranks a static template of the same dialog; never overwrite live with static
    if prev and prev["source"].startswith("live") and source.startswith("static"):
        return did
    model._conn.execute(
        "INSERT OR REPLACE INTO bm_dialogs(dialog_id, app_key, title, controls_json, source, via, n_controls, ts)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (did, app_key, (title or "")[:200], json.dumps(controls[:300], default=str), source, via[:200], len(controls), time.time()))
    model._conn.commit()
    return did


def dialogs(model, app_key: str, with_controls: bool = False) -> List[Dict[str, Any]]:
    ensure(model)
    cols = "dialog_id, title, source, via, n_controls" + (", controls_json" if with_controls else "")
    out = []
    for r in model._conn.execute(f"SELECT {cols} FROM bm_dialogs WHERE app_key=? ORDER BY ts DESC", (app_key,)):
        d = dict(r)
        if with_controls:
            d["controls"] = json.loads(d.pop("controls_json") or "[]")
        out.append(d)
    return out


# ---- frontier ----------------------------------------------------------------------------

def frontier_id(app_key: str, kind: str, label: str, path: str) -> str:
    return "fr_" + hashlib.md5(f"{app_key}|{kind}|{label.lower()}|{path.lower()}".encode()).hexdigest()[:14]


def frontier_add(model, app_key: str, kind: str, label: str, path: str = "", *, info_gain: float = 0.5,
                 version_hash: str = "") -> str:
    """Register a surface to explore. Existing rows keep their status (an explored node is never reopened by a re-scan
    of the same app version); a NEW app version reopens everything."""
    ensure(model)
    fid = frontier_id(app_key, kind, label, path)
    row = model._conn.execute("SELECT status, version_hash FROM bm_frontier WHERE fid=?", (fid,)).fetchone()
    if row:
        if version_hash and row["version_hash"] and row["version_hash"] != version_hash:
            model._conn.execute("UPDATE bm_frontier SET status='open', version_hash=?, ts=? WHERE fid=?",
                                (version_hash, time.time(), fid))
            model._conn.commit()
        return fid
    model._conn.execute(
        "INSERT INTO bm_frontier(fid, app_key, kind, label, path, status, info_gain, version_hash, ts)"
        " VALUES (?,?,?,?,?,'open',?,?,?)", (fid, app_key, kind, label[:200], path[:400], info_gain, version_hash, time.time()))
    model._conn.commit()
    return fid


def frontier_open(model, app_key: str, limit: int = 50, kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    ensure(model)
    rows = [dict(r) for r in model._conn.execute(
        "SELECT * FROM bm_frontier WHERE app_key=? AND status='open' ORDER BY info_gain DESC, attempts ASC LIMIT ?",
        (app_key, limit * 3))]
    if kinds:
        rows = [r for r in rows if r["kind"] in kinds]
    return rows[:limit]


def frontier_done(model, fid: str, status: str, result: Dict[str, Any], run_id: str = "") -> None:
    """status: explored | no_effect | unsafe | failed (failed reopens after 2 attempts stay failed) | skipped"""
    ensure(model)
    model._conn.execute(
        "UPDATE bm_frontier SET status=?, attempts=attempts+1, last_run=?, result_json=?, ts=? WHERE fid=?",
        (status, run_id, json.dumps(result, default=str)[:3000], time.time(), fid))
    model._conn.commit()


def frontier_stats(model, app_key: str) -> Dict[str, Any]:
    ensure(model)
    by: Dict[str, int] = {}
    for r in model._conn.execute("SELECT status, COUNT(*) c FROM bm_frontier WHERE app_key=? GROUP BY status", (app_key,)):
        by[r["status"]] = r["c"]
    total = sum(by.values())
    # EXPLORABLE = everything except what is never probed on purpose (destructive-looking `unsafe`, deliberately `skipped`).
    # Explored = a probe ran and observed something (an effect, or honestly none). `failed` is attempted, not explored.
    explorable = total - by.get("unsafe", 0) - by.get("skipped", 0)
    explored = by.get("explored", 0) + by.get("no_effect", 0)
    return {"total": total, "by_status": by, "explorable": explorable, "explored_n": explored,
            "explored_fraction": round(explored / explorable, 3) if explorable else None}


# ---- state variables ---------------------------------------------------------------------

def put_statevar(model, app_key: str, var_id: str, name: str, kind: str, values: List[str], *,
                 group_id: str = "", aid: str = "") -> None:
    """Merge newly observed values into the variable's known value set."""
    ensure(model)
    row = model._conn.execute("SELECT values_json FROM bm_statevars WHERE app_key=? AND var_id=?", (app_key, var_id)).fetchone()
    known = set(json.loads(row["values_json"])) if row else set()
    known |= set(values)
    model._conn.execute(
        "INSERT OR REPLACE INTO bm_statevars(app_key, var_id, name, kind, values_json, group_id, aid, ts) VALUES (?,?,?,?,?,?,?,?)",
        (app_key, var_id, name[:120], kind, json.dumps(sorted(known)), group_id, aid, time.time()))
    model._conn.commit()


def statevars(model, app_key: str) -> List[Dict[str, Any]]:
    ensure(model)
    out = []
    for r in model._conn.execute("SELECT * FROM bm_statevars WHERE app_key=? ORDER BY kind, name", (app_key,)):
        d = dict(r)
        d["values"] = json.loads(d.pop("values_json") or "[]")
        out.append(d)
    return out


# ---- conventions -------------------------------------------------------------------------

def convention_result(model, app_key: str, intent: str, chord: str, verdict: str, evidence: str) -> None:
    """verdict: obeyed | ignored | unobservable.  obeyed twice => the chord is a verified shortcut for the intent."""
    ensure(model)
    ok = verdict == "obeyed"
    model._conn.execute(
        "INSERT INTO bm_conventions(app_key, intent, chord, verdict, evidence, successes, failures, ts)"
        " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(app_key, intent, chord) DO UPDATE SET verdict=excluded.verdict,"
        " evidence=excluded.evidence, successes=successes+?, failures=failures+?, ts=excluded.ts",
        (app_key, intent, chord, verdict, evidence[:400], int(ok), int(verdict == "ignored"), time.time(),
         int(ok), int(verdict == "ignored")))
    model._conn.commit()


def conventions(model, app_key: str) -> List[Dict[str, Any]]:
    ensure(model)
    return [dict(r) for r in model._conn.execute("SELECT * FROM bm_conventions WHERE app_key=? ORDER BY intent", (app_key,))]


# ---- run log -----------------------------------------------------------------------------

def log_run(model, run_id: str, app_key: str, run_no: int, phase: str, metrics: Dict[str, Any]) -> None:
    ensure(model)
    model._conn.execute("INSERT INTO bm_run_log(run_id, app_key, run_no, phase, metrics_json, ts) VALUES (?,?,?,?,?,?)",
                        (run_id, app_key, run_no, phase, json.dumps(metrics, default=str)[:4000], time.time()))
    model._conn.commit()


def run_count(model, app_key: str) -> int:
    ensure(model)
    r = model._conn.execute("SELECT MAX(run_no) m FROM bm_run_log WHERE app_key=?", (app_key,)).fetchone()
    return int(r["m"] or 0)


def run_log(model, app_key: str) -> List[Dict[str, Any]]:
    ensure(model)
    out = []
    for r in model._conn.execute("SELECT * FROM bm_run_log WHERE app_key=? ORDER BY ts", (app_key,)):
        d = dict(r)
        d["metrics"] = json.loads(d.pop("metrics_json") or "{}")
        out.append(d)
    return out
