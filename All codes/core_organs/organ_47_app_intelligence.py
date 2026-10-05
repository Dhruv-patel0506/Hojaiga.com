"""
organ_47_app_intelligence.py — App Intelligence Organ (the "pro knowledge" layer).

WHY THIS EXISTS
---------------
Scanning can only ever tell the system WHERE a control is. It can never tell it
WHAT a professional would do. "Insert a cube in Blender" is Ctrl+Numpad0 -> Mesh
-> Cube, or Shift+A -> Mesh -> Cube; a pixel-perfect scan of the viewport is
useless without that procedural knowledge. So perception (desktop_grounding) and
knowledge (this organ) are separate, and the judge is fed by both.

This is the organ that holds, for every app it has ever seen or heard of, the
*how to work it* knowledge:

  - menu paths            ("File > Export > glTF 2.0 (.glb)")
  - keyboard shortcuts    ("ctrl+a", "shift+s")
  - verified step recipes ("CLICK 'Export' THEN TYPE path THEN CLICK 'Save'")
  - element fingerprints  (name/role anchors so a recipe can re-ground itself)
  - per-app and per-step reliability, reinforced by real outcomes

KNOWLEDGE SOURCES, in strict precedence order (never hardcoded per app):

  1. learned      — traces this host actually executed and the verifier PASSed.
                    Highest trust. Grows continuously; nothing to ship.
  2. profile      — declarative app profiles already stored by organ_04
                    (AppCatalog / AppIntelligence: name, path, version,
                    capabilities, reliability_score). Bootstrap only.
  3. archetype    — generic UI-family playbooks (3D suite, raster editor, IDE,
                    office, media player, browser, file manager). These are NOT
                    per-app hardcodes: they are per-*kind* conventions that hold
                    across thousands of apps, keyed by winget/PE classification
                    hints and by what the scan actually found on screen.
  4. distilled    — a one-time LLM "briefing" generated on first contact with an
                    unknown app, cached with low confidence and marked UNVERIFIED.
                    It guides ranking only; it is never trusted as fact.

Everything degrades honestly: if a tier has nothing, it reports nothing, and the
loop falls back to pure perception. Confidence only ever rises from VERIFIED
outcomes, never from a model asserting it knows something.

Storage: single SQLite file, WAL, safe to open from multiple organs.
"""

from __future__ import annotations

import os
import re
import json
import time
import sqlite3
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.organ_47_app_intelligence")

DB_PATH = os.environ.get(
    "HOJAIGA_APP_INTEL_DB",
    os.path.join(r"D:\new_automation", "data", "app_intelligence.db"),
)

# distilled briefings are cached this long before we re-ask (hours)
DISTILL_TTL_H = float(os.environ.get("HOJAIGA_INTEL_DISTILL_TTL_H", "168"))
# confidence below this -> stop surfacing the step at all
SUPPRESS_BELOW = float(os.environ.get("HOJAIGA_INTEL_SUPPRESS", "0.15"))
BRAINS_CHAT_URL = os.environ.get("HOJAIGA_BRAIN_URL", "http://127.0.0.1:11434/api/chat")
INTEL_MODEL = os.environ.get("HOJAIGA_INTEL_MODEL", os.environ.get("HOJAIGA_JUDGE_MODEL", "qwen2.5:7b"))
DISTILL_TIMEOUT_S = float(os.environ.get("HOJAIGA_INTEL_DISTILL_TIMEOUT_S", "20"))

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    app_key        TEXT PRIMARY KEY,
    display_name   TEXT,
    exe_path       TEXT,
    version        TEXT,
    archetype      TEXT,
    source         TEXT,
    confidence     REAL DEFAULT 0.5,
    successes      INTEGER DEFAULT 0,
    failures       INTEGER DEFAULT 0,
    first_seen     REAL,
    last_seen      REAL,
    meta_json      TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS steps (
    step_id        TEXT PRIMARY KEY,
    app_key        TEXT,
    goal           TEXT,
    verb           TEXT,
    element_name   TEXT,
    element_role   TEXT,
    shortcut       TEXT,
    menu_path      TEXT,
    fingerprint    TEXT,
    outcome        TEXT,
    source         TEXT,
    confidence     REAL DEFAULT 0.5,
    hits           INTEGER DEFAULT 0,
    ts             REAL
);
CREATE INDEX IF NOT EXISTS steps_app ON steps(app_key, goal);
CREATE INDEX IF NOT EXISTS steps_goal ON steps(app_key, goal);

CREATE TABLE IF NOT EXISTS briefings (
    app_key        TEXT PRIMARY KEY,
    briefing_json  TEXT,
    source         TEXT,
    ts             REAL
);
"""


# ---------------------------------------------------------------------------
# Generic UI archetypes — per-KIND conventions, not per-app hardcodes
# ---------------------------------------------------------------------------

ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "3d_suite": {
        "match": ("blender", "maya", "cinema 4d", "4d", "zbrush", "fusion 360",
                  "freeCAD", "sketchup", "3ds max", "houdini"),
        "conventions": [
            {"goal": "add mesh primitive", "verb": "shortcut", "shortcut": "shift+a",
             "menu_path": "Add > Mesh", "note": "object mode required"},
            {"goal": "add cube", "verb": "shortcut", "shortcut": "shift+a",
             "menu_path": "Add > Mesh > Cube"},
            {"goal": "enter edit mode", "verb": "shortcut", "shortcut": "tab"},
            {"goal": "extrude", "verb": "shortcut", "shortcut": "e"},
            {"goal": "scale", "verb": "shortcut", "shortcut": "s"},
            {"goal": "save project", "verb": "shortcut", "shortcut": "ctrl+s",
             "menu_path": "File > Save"},
            {"goal": "export file", "verb": "invoke", "menu_path": "File > Export",
             "note": "export format submenu opens"},
            {"goal": "delete selection", "verb": "shortcut", "shortcut": "x",
             "destructive": True},
            {"goal": "undo", "verb": "shortcut", "shortcut": "ctrl+z"},
        ],
    },
    "text_editor": {
        "match": ("notepad", "wordpad", "textedit", "gedit", "text editor"),
        "conventions": [
            {"goal": "new document", "verb": "shortcut", "shortcut": "ctrl+n"},
            {"goal": "save as", "verb": "shortcut", "shortcut": "ctrl+shift+s",
             "menu_path": "File > Save As"},
            {"goal": "find", "verb": "shortcut", "shortcut": "ctrl+f"},
            {"goal": "select all", "verb": "shortcut", "shortcut": "ctrl+a"},
        ],
    },
    "raster_editor": {
        "match": ("photoshop", "gimp", "paint.net", "krita", "affinity photo",
                  "paint", "photo"),
        "conventions": [
            {"goal": "new document", "verb": "shortcut", "shortcut": "ctrl+n",
             "menu_path": "File > New"},
            {"goal": "save as", "verb": "shortcut", "shortcut": "ctrl+shift+s",
             "menu_path": "File > Save As"},
            {"goal": "export", "verb": "invoke", "menu_path": "File > Export"},
            {"goal": "undo", "verb": "shortcut", "shortcut": "ctrl+z"},
            {"goal": "fill selection", "verb": "shortcut", "shortcut": "ctrl+back"},
        ],
    },
    "ide": {
        "match": ("visual studio code", "vscode", "pycharm", "intellij", "eclipse",
                  "sublime", "notepad++", "android studio", "devenv"),
        "conventions": [
            {"goal": "open file", "verb": "shortcut", "shortcut": "ctrl+o",
             "menu_path": "File > Open"},
            {"goal": "save", "verb": "shortcut", "shortcut": "ctrl+s"},
            {"goal": "save all", "verb": "shortcut", "shortcut": "ctrl+k s"},
            {"goal": "find and replace", "verb": "shortcut", "shortcut": "ctrl+h"},
            {"goal": "command palette", "verb": "shortcut", "shortcut": "ctrl+shift+p"},
            {"goal": "run", "verb": "shortcut", "shortcut": "f5"},
        ],
    },
    "office_doc": {
        "match": ("word", "excel", "powerpoint", "libreoffice", "writer", "calc",
                  "outlook", "onenote"),
        "conventions": [
            {"goal": "save", "verb": "shortcut", "shortcut": "ctrl+s"},
            {"goal": "save as", "verb": "shortcut", "shortcut": "f12",
             "menu_path": "File > Save As"},
            {"goal": "find", "verb": "shortcut", "shortcut": "ctrl+f"},
            {"goal": "paste plain", "verb": "shortcut", "shortcut": "ctrl+shift+v"},
        ],
    },
    "media_player": {
        "match": ("vlc", "mpv", "potplayer", "windows media", "itunes", "spotify"),
        "conventions": [
            {"goal": "open file", "verb": "shortcut", "shortcut": "ctrl+o"},
            {"goal": "toggle play", "verb": "shortcut", "shortcut": "space"},
            {"goal": "mute", "verb": "shortcut", "shortcut": "m"},
            {"goal": "fullscreen", "verb": "shortcut", "shortcut": "f"},
        ],
    },
    "file_manager": {
        "match": ("explorer", "file explorer", "total commander", "directory opus",
                  "nothing"),
        "conventions": [
            {"goal": "new folder", "verb": "shortcut", "shortcut": "ctrl+shift+n"},
            {"goal": "rename", "verb": "shortcut", "shortcut": "f2"},
            {"goal": "select all", "verb": "shortcut", "shortcut": "ctrl+a"},
            {"goal": "address bar", "verb": "shortcut", "shortcut": "ctrl+l"},
        ],
    },
    "browser": {
        "match": ("chrome", "edge", "firefox", "brave", "opera", "chromium"),
        "conventions": [
            {"goal": "new tab", "verb": "shortcut", "shortcut": "ctrl+t"},
            {"goal": "close tab", "verb": "shortcut", "shortcut": "ctrl+w",
             "destructive": True},
            {"goal": "address bar", "verb": "shortcut", "shortcut": "ctrl+l"},
            {"goal": "find on page", "verb": "shortcut", "shortcut": "ctrl+f"},
        ],
    },
    # Generic Windows app: applies when nothing more specific matched. The
    # conventions here are true for essentially every Win32 app.
    "generic_win32": {
        "match": (),
        "conventions": [
            {"goal": "save", "verb": "shortcut", "shortcut": "ctrl+s",
             "menu_path": "File > Save"},
            {"goal": "save as", "verb": "invoke", "menu_path": "File > Save As"},
            {"goal": "open", "verb": "shortcut", "shortcut": "ctrl+o",
             "menu_path": "File > Open"},
            {"goal": "new", "verb": "shortcut", "shortcut": "ctrl+n",
             "menu_path": "File > New"},
            {"goal": "find", "verb": "shortcut", "shortcut": "ctrl+f",
             "menu_path": "Edit > Find"},
            {"goal": "undo", "verb": "shortcut", "shortcut": "ctrl+z"},
            {"goal": "close", "verb": "shortcut", "shortcut": "alt+f4",
             "destructive": True},
        ],
    },
}


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _app_key(display_name: str, exe_path: str = "") -> str:
    base = _norm(display_name) or os.path.basename(exe_path or "").lower()
    base = re.sub(r"\.(exe|lnk)$", "", base)
    return base or "unknown"


def _fingerprint(element_name: str, element_role: str, menu_path: str = "") -> str:
    raw = f"{_norm(element_name)}|{_norm(element_role)}|{_norm(menu_path)}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


_EV_ARCH_CACHE: Dict[str, Tuple[float, str]] = {}


def _evidence_archetype(app_name: str) -> str:
    """The family the app's OWN evidence says it is (file types it opens + the vocabulary of its commands + dialogs, see
    static_knowledge.infer_profile), stored by a scan/mastery run. '' when nothing was learned or the evidence is thin.
    Cached 60 s: classify_archetype runs on every step."""
    key = _app_key(app_name)
    now = time.time()
    hit = _EV_ARCH_CACHE.get(key)
    if hit and now - hit[0] < 60.0:
        return hit[1]
    arch = ""
    try:
        from core_organs import organ_48_app_behavior_model as bm
        from core_organs import knowledge_store as ks
        prof = ks.get_fact(bm.get_model(), bm._app_key(app_name), "profile", None) or {}
        cand = prof.get("archetype", "")
        if cand and cand != "unclassified":
            arch = cand
    except Exception:
        arch = ""
    _EV_ARCH_CACHE[key] = (now, arch)
    return arch


def classify_archetype(app_name: str, exe_path: str = "") -> str:
    """Map an app to a generic UI family. EVIDENCE first (what the app was observed to open / offer: learned at runtime,
    no app names), then the name/exe tokens below as a prior for an app nothing has been learned about yet. Data-driven:
    adding a family means adding tokens or an evidence rule, never control-flow code."""
    ev = _evidence_archetype(app_name)
    if ev:
        return ev
    hay = _norm(app_name) + " " + os.path.basename(exe_path or "").lower()
    for family, spec in ARCHETYPES.items():
        if family == "generic_win32":
            continue
        for tok in spec["match"]:
            if tok in hay:
                return family
    return "generic_win32"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

_CHROME_STEP_NAMES = frozenset({"close", "minimize", "maximize", "restore", "restore down", "system", "system menu"})


@dataclass
class StepHint:
    """One ranked suggestion from the playbook, ready to feed the judge."""
    step_id: str
    goal: str
    verb: str
    element_name: str = ""
    element_role: str = ""
    shortcut: str = ""
    menu_path: str = ""
    confidence: float = 0.5
    hits: int = 0
    source: str = "learned"
    destructive: bool = False
    successes: int = 0              # verified PASSes (hits also counts failures)

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def label(self) -> str:
        if self.shortcut:
            return f"shortcut {self.shortcut}"
        if self.menu_path:
            return f"menu {self.menu_path}"
        return f"'{self.element_name}' [{self.element_role}]"


@dataclass
class AppIntel:
    app_key: str
    display_name: str
    archetype: str
    confidence: float
    known: bool
    source: str
    hints: List[StepHint] = field(default_factory=list)
    briefing: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The organ
# ---------------------------------------------------------------------------

class AppIntelligence:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, timeout=15, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        # 6.4: `hits` counts EVERY recorded outcome (a FAIL bumps it too), so it can never gate muscle memory. `successes`
        # counts verified PASSes only. Migrated rows: a row whose last outcome was PASS keeps min(hits, 1) - one trace
        # is exactly what must not be trusted blind - and earns the rest by passing again.
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(steps)")}
        if "successes" not in cols:
            self._conn.execute("ALTER TABLE steps ADD COLUMN successes INTEGER DEFAULT 0")
            self._conn.execute("UPDATE steps SET successes = CASE WHEN outcome='PASS' THEN MIN(hits, 1) ELSE 0 END")
        self._conn.commit()
        # in-session memo so a long task does not re-query per step
        self._memo: Dict[str, AppIntel] = {}

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def _bust_memo(self, key: str) -> None:
        """Drop every cached playbook for this app (memo is keyed app|goal)."""
        for k in [k for k in self._memo if k == key or k.startswith(key + "|")]:
            self._memo.pop(k, None)

    # ---- app registry ----------------------------------------------------
    def register_app(self, display_name: str, exe_path: str = "", version: str = "",
                     source: str = "observed", archetype: str = "") -> str:
        key = _app_key(display_name, exe_path)
        family = archetype or classify_archetype(display_name, exe_path)
        now = time.time()
        row = self._conn.execute("SELECT app_key FROM apps WHERE app_key=?", (key,)).fetchone()
        if row:
            self._conn.execute(
                "UPDATE apps SET display_name=?, exe_path=COALESCE(NULLIF(?, ''), exe_path),"
                " version=COALESCE(NULLIF(?, ''), version), archetype=?, last_seen=?,"
                " source=? WHERE app_key=?",
                (display_name, exe_path, version, family, now, source, key))
        else:
            self._conn.execute(
                "INSERT INTO apps(app_key, display_name, exe_path, version, archetype,"
                " source, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?)",
                (key, display_name, exe_path, version, family, source, now, now))
        self._conn.commit()
        self._bust_memo(key)
        return key

    def get_app(self, app_name: str) -> Optional[dict]:
        key = _app_key(app_name)
        row = self._conn.execute("SELECT * FROM apps WHERE app_key=?", (key,)).fetchone()
        return dict(row) if row else None

    def bootstrap_from_catalog(self) -> int:
        """Seed known apps from organ_40's AppCatalog (already scans Start Menu +
        winget). Reuses existing host knowledge instead of re-scanning."""
        imported = 0
        try:
            from core_organs.organ_40_app_launcher import AppCatalog
            catalog = AppCatalog()
            catalog.ensure_scanned()
            with sqlite3.connect(catalog.db) as conn:
                rows = conn.execute(
                    "SELECT name, launcher_path, version FROM app_catalog").fetchall()
            for name, path, version in rows:
                self.register_app(name, path or "", version or "", source="catalog")
                imported += 1
        except Exception as exc:
            logger.debug("[intel] catalog bootstrap unavailable: %s", exc)
        return imported

    # ---- learning from verified outcomes ---------------------------------
    def record_step(self, app_name: str, goal: str, verb: str, *,
                    element_name: str = "", element_role: str = "",
                    shortcut: str = "", menu_path: str = "",
                    outcome: str = "PASS", source: str = "learned",
                    confidence: Optional[float] = None) -> str:
        """Store one executed step. PASS reinforces, anything else erodes.
        Callers do not compute confidence — this is the only place it changes."""
        key = _app_key(app_name)
        try:                                      # the knowledge store is synced to a repository: a person's name is not knowledge
            from core_organs.knowledge_store import redact as _redact
            if element_name and _redact(element_name) != element_name:
                return ""                         # 'Signed in as <name>' / 'Welcome back, <name>' controls are never recorded as a step
            goal, menu_path = _redact(goal), _redact(menu_path)
        except Exception:  # noqa: BLE001
            pass
        if outcome == "PASS" and (element_name or "").strip().lower() in _CHROME_STEP_NAMES                 and not re.search(r"(close|exit|quit|minimi[sz]e|maximi[sz]e|restore|window|dismiss|cancel)", (goal or "").lower()):
            return ""                             # a title-bar Close / Minimize / System is never 'the way' to an in-app goal (a sign-in screen taught "Close" at 0.97)
        fp = _fingerprint(element_name, element_role or verb, menu_path) + (shortcut or "")
        step_id = f"{key}:{fp}"
        row = self._conn.execute("SELECT * FROM steps WHERE step_id=?", (step_id,)).fetchone()
        if row:
            hits = int(row["hits"]) + 1
            conf = confidence if confidence is not None else _reinforce(
                float(row["confidence"]), outcome, row["source"] or source)
            prev_ok = int(row["successes"] or 0) if "successes" in row.keys() else 0
            succ = prev_ok + 1 if outcome == "PASS" else max(0, prev_ok - 1)       # a failure takes one verification away
            self._conn.execute(
                "UPDATE steps SET confidence=?, hits=?, outcome=?, source=?, ts=?, successes=? WHERE step_id=?",
                (conf, hits, outcome, row["source"] or source, time.time(), succ, step_id))
        else:
            conf = confidence if confidence is not None else _initial_confidence(outcome, source)
            self._conn.execute(
                "INSERT INTO steps(step_id, app_key, goal, verb, element_name, element_role,"
                " shortcut, menu_path, fingerprint, outcome, source, confidence, hits, ts, successes)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (step_id, key, _norm(goal), verb, element_name, element_role, shortcut,
                 menu_path, fp, outcome, source, conf, 1, time.time(), 1 if outcome == "PASS" else 0))
        # roll the app-level reliability up as well
        if outcome == "PASS":
            self._conn.execute("UPDATE apps SET successes=successes+1, confidence=?,"
                               " last_seen=? WHERE app_key=?",
                               (_app_conf(key, self._conn), time.time(), key))
        else:
            self._conn.execute("UPDATE apps SET failures=failures+1, confidence=?,"
                               " last_seen=? WHERE app_key=?",
                               (_app_conf(key, self._conn), time.time(), key))
        self._conn.commit()
        self._bust_memo(key)
        return step_id

    # ---- retrieval -------------------------------------------------------
    def hints_for_goal(self, app_name: str, goal: str = "", limit: int = 12) -> List[StepHint]:
        key = _app_key(app_name)
        sql = "SELECT * FROM steps WHERE app_key=? AND confidence>?"
        params: list = [key, SUPPRESS_BELOW]
        if goal:
            sql += " AND goal LIKE ?"
            params.append(f"%{_norm(goal)}%")
        sql += " ORDER BY confidence DESC, hits DESC LIMIT ?"
        params.append(limit)
        out: List[StepHint] = []
        try:
            rows = list(self._conn.execute(sql, params))
        except Exception as exc:
            logger.debug("[intel] hint query failed: %s", exc)
            return out
        for row in rows:
            out.append(StepHint(
                step_id=row["step_id"], goal=row["goal"], verb=row["verb"],
                element_name=row["element_name"] or "", element_role=row["element_role"] or "",
                shortcut=row["shortcut"] or "", menu_path=row["menu_path"] or "",
                confidence=float(row["confidence"]), hits=int(row["hits"] or 0),
                successes=int(row["successes"] or 0) if "successes" in row.keys() else 0,
                source=row["source"] or "learned",
                destructive=_is_destructive(row["verb"], row["element_name"],
                                            row["menu_path"], row["outcome"])))
        return out

    def _archetype_hints(self, app_name: str, goal: str = "") -> List[StepHint]:
        family = classify_archetype(app_name)
        key = _app_key(app_name)
        goals_norm = _norm(goal)
        out: List[StepHint] = []
        for conv in ARCHETYPES.get(family, {}).get("conventions", []):
            cgoal = _norm(conv["goal"])
            if goal and not _goal_relevant(cgoal, goals_norm):
                continue
            out.append(StepHint(
                step_id=f"{key}:arch:{_fingerprint(cgoal, 'convention')}",
                goal=conv["goal"], verb=conv.get("verb", "invoke"),
                element_name=_menu_leaf(conv.get("menu_path", "")),
                element_role="menuitem",
                shortcut=conv.get("shortcut", ""),
                menu_path=conv.get("menu_path", ""),
                # unverified convention: useful for ranking, never trusted blind
                confidence=0.45, source="archetype",
                destructive=bool(conv.get("destructive"))))
        return out

    def playbook(self, app_name: str, goal: str = "",
                 allow_llm_briefing: bool = True) -> AppIntel:
        """The full answer to 'what does a pro do in THIS app for THIS goal'.

        Merge order encodes trust: learned (verified here) > profile > archetype
        conventions > LLM briefing. Nothing is ever silently invented: the
        briefing is labelled 'distilled' and capped below the archetype floor.
        """
        key = _app_key(app_name)
        memo_slot = f"{key}|{_norm(goal)}"
        if memo_slot in self._memo:
            return self._memo[memo_slot]

        app_row = self.get_app(app_name)
        if app_row is None:
            self.register_app(app_name, source="perceived")
            app_row = self.get_app(app_name) or {}
        learned = self.hints_for_goal(app_name, goal)
        arch = self._archetype_hints(app_name, goal)

        briefing: Dict[str, Any] = {}
        distilled: List[StepHint] = []
        stored = self._conn.execute(
            "SELECT briefing_json, ts FROM briefings WHERE app_key=?", (key,)).fetchone()
        if stored and stored["briefing_json"]:
            try:
                briefing = json.loads(stored["briefing_json"])
            except Exception:
                briefing = {}
        # Only pay for an LLM briefing when we have nothing verified and nothing
        # generic to lean on — otherwise the model is just noise (and it is slow).
        if allow_llm_briefing and not learned and (
                not stored or (time.time() - float(stored["ts"] or 0)) > DISTILL_TTL_H * 3600.0):
            fresh = self._distill_briefing(app_name, goal)
            if fresh:
                briefing = fresh
                self._store_briefing(key, briefing)
            distilled = self._hints_from_briefing(key, briefing, goal)
        elif briefing:
            distilled = self._hints_from_briefing(key, briefing, goal)

        merged: Dict[str, StepHint] = {}
        for h in learned + arch + distilled:
            ident = _fingerprint(h.element_name, h.verb + h.element_role, h.menu_path) + h.shortcut
            prev = merged.get(ident)
            if prev is None or h.confidence > prev.confidence:
                merged[ident] = h
        ranked = sorted(merged.values(), key=lambda h: (-h.confidence, -h.hits))

        intel = AppIntel(
            app_key=key, display_name=app_row.get("display_name", app_name),
            archetype=app_row.get("archetype") or classify_archetype(app_name),
            confidence=float(app_row.get("confidence") or 0.5),
            known=bool(learned), source="learned" if learned else (
                "archetype" if arch else ("distilled" if distilled else "none")),
            hints=ranked, briefing=briefing)
        self._memo[memo_slot] = intel
        return intel

    def _hints_from_briefing(self, key: str, briefing: Dict[str, Any], goal: str) -> List[StepHint]:
        out: List[StepHint] = []
        for raw in (briefing.get("steps") or [])[:8]:
            if not isinstance(raw, dict):
                continue
            menu = str(raw.get("menu_path", ""))
            out.append(StepHint(
                step_id=f"{key}:dist:{_fingerprint(menu or str(raw.get('element', '')), 'brief')}",
                goal=str(raw.get("goal", goal)), verb=str(raw.get("verb", "invoke")),
                element_name=str(raw.get("element", "")) or _menu_leaf(menu),
                element_role="menuitem", shortcut=str(raw.get("shortcut", "")),
                menu_path=menu, confidence=0.3, source="distilled",
                destructive=_is_destructive(str(raw.get("verb", "")),
                                            str(raw.get("element", "")), menu, "")))
        return out

    # ---- LLM briefing (first-contact bootstrap, cached, never trusted) ----
    def _briefing_stale(self, key: str) -> bool:
        row = self._conn.execute(
            "SELECT ts FROM briefings WHERE app_key=?", (key,)).fetchone()
        if not row:
            return True
        return (time.time() - float(row["ts"])) > DISTILL_TTL_H * 3600.0

    def _store_briefing(self, key: str, briefing: Dict[str, Any]) -> None:
        try:
            self._conn.execute(
                "INSERT INTO briefings(app_key, briefing_json, source, ts) VALUES (?,?,?,?)"
                " ON CONFLICT(app_key) DO UPDATE SET briefing_json=excluded.briefing_json,"
                " source=excluded.source, ts=excluded.ts",
                (key, json.dumps(briefing), "distilled", time.time()))
            self._conn.commit()
        except Exception as exc:
            logger.debug("[intel] briefing store failed: %s", exc)

    def _distill_briefing(self, app_name: str, goal: str) -> Dict[str, Any]:
        """Ask the local model for a procedural briefing about an app we have
        never verified. Bounded so a cold model can never stall the loop (the
        29.5s popup lesson). Returns {} on any failure — that is a normal state."""
        prompt = (
            "You are an expert desktop-application operator.\n"
            f"APP: {app_name}\nGOAL: {goal or 'general day-to-day operation'}\n"
            "List the shortest reliable way to reach the goal: keyboard shortcuts "
            "first, then menu paths, then the exact label of each clickable control.\n"
            "Return STRICT JSON: {\"steps\": [{\"goal\": str, \"verb\": "
            "\"click|type|shortcut|key|invoke\", \"shortcut\": str, "
            "\"menu_path\": str, \"element\": str}], \"gotchas\": [str]}"
            " — at most 6 steps, no prose."
        )
        payload = {"model": INTEL_MODEL,
                   "messages": [{"role": "user", "content": prompt}],
                   "stream": False, "format": "json",
                   "options": {"temperature": 0.0, "num_predict": 260}}
        try:
            import urllib.request
            req = urllib.request.Request(
                BRAINS_CHAT_URL, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=DISTILL_TIMEOUT_S) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body.get("message", {}).get("content", "") or body.get("response", "")
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if not m:
                return {}
            data = json.loads(m.group(0))
            if not isinstance(data.get("steps"), list) or not data["steps"]:
                return {}
            data["unverified"] = True
            return data
        except Exception as exc:
            logger.debug("[intel] briefing distillation unavailable: %s", exc)
            return {}

    # ---- convenience for the capsule / reporting -------------------------
    def describe(self, app_name: str) -> str:
        intel = self.playbook(app_name, allow_llm_briefing=False)
        verified = [h for h in intel.hints if h.source == "learned"]
        return (f"{intel.display_name} [{intel.archetype}] "
                f"{len(verified)} verified step(s), {len(intel.hints)} known, "
                f"source={intel.source}")

    def top_actions(self, app_name: str, limit: int = 5) -> List[str]:
        return [f"{h.verb} {h.label} ({h.source} {h.confidence:.2f})"
                for h in self.playbook(app_name, allow_llm_briefing=False).hints[:limit]]


# ---------------------------------------------------------------------------
# Confidence math — deliberately simple, monotone, auditable
# ---------------------------------------------------------------------------

_SOURCE_FLOOR = {"learned": 0.55, "catalog": 0.35, "archetype": 0.45,
                 "distilled": 0.30, "perceived": 0.30}


def _initial_confidence(outcome: str, source: str) -> float:
    floor = _SOURCE_FLOOR.get(source, 0.35)
    if outcome == "PASS":
        return min(0.85, floor + 0.30)
    return max(0.2, floor - 0.05)


def _reinforce(current: float, outcome: str, source: str) -> float:
    """Verified PASS climbs toward 0.97; failure drops fast. One PASS on a
    distilled guess must not turn a guess into a fact, hence the cap by source."""
    if outcome == "PASS":
        ceiling = {"learned": 0.97, "archetype": 0.90}.get(source, 0.75)
        return min(ceiling, max(current, _SOURCE_FLOOR.get(source, 0.35)) + 0.12)
    return max(0.05, current - 0.25)


def _app_conf(key: str, conn: sqlite3.Connection) -> float:
    row = conn.execute(
        "SELECT AVG(confidence) a, COUNT(*) c FROM steps WHERE app_key=?", (key,)).fetchone()
    if not row or not row["c"]:
        return 0.5
    return round(float(row["a"] or 0.5), 3)


_DESTRUCTIVE_TOKENS = ("delete", "remove", "discard", "empty", "format",
                       "overwrite", "close", "quit", "uninstall", "erase")


def _is_destructive(verb: str, element_name: str, menu_path: str, outcome: str) -> bool:
    hay = _norm(f"{element_name} {menu_path}")
    return any(tok in hay for tok in _DESTRUCTIVE_TOKENS)


def _menu_leaf(menu_path: str) -> str:
    if not menu_path:
        return ""
    return menu_path.split(">")[-1].strip()


def _goal_relevant(conv_goal: str, goal_norm: str) -> bool:
    """Loose semantic match between a convention goal and the current goal.
    Token overlap only — no per-app synonym tables."""
    if not goal_norm:
        return True
    ct = set(re.findall(r"[a-z0-9]+", conv_goal))
    gt = set(re.findall(r"[a-z0-9]+", goal_norm))
    if ct & gt:
        return True
    # cheap stemming so 'export' matches 'exporting', 'save' matches 'saves'
    cs = {t[:4] for t in ct}
    gs = {t[:4] for t in gt}
    return bool(cs & gs)


# ---------------------------------------------------------------------------
# Singleton accessor (organs are cheap but the DB handle should be single)
# ---------------------------------------------------------------------------

_intel_singleton: Optional[AppIntelligence] = None


def get_intel() -> AppIntelligence:
    global _intel_singleton
    if _intel_singleton is None:
        _intel_singleton = AppIntelligence()
    return _intel_singleton


def playbook(app_name: str, goal: str = "", allow_llm_briefing: bool = True) -> AppIntel:
    return get_intel().playbook(app_name, goal, allow_llm_briefing)


def record_outcome(app_name: str, goal: str, verb: str, *, element_name: str = "",
                   element_role: str = "", shortcut: str = "", menu_path: str = "",
                   outcome: str = "PASS", step_id: str = "",
                   source: str = "learned") -> str:
    if step_id:
        conn = get_intel()._conn
        row = conn.execute("SELECT source, confidence FROM steps WHERE step_id=?",
                           (step_id,)).fetchone()
        if row:
            source = row["source"] or source
            new_conf = _reinforce(float(row["confidence"]), outcome, source)
            conn.execute("UPDATE steps SET confidence=?, outcome=?, hits=hits+1, ts=?, "
                         "successes=CASE WHEN ?='PASS' THEN successes+1 ELSE MAX(0, successes-1) END "
                         "WHERE step_id=?", (new_conf, outcome, time.time(), outcome, step_id))
            conn.execute("UPDATE apps SET successes=successes+?, failures=failures+? "
                         "WHERE app_key=?",
                         (1 if outcome == "PASS" else 0,
                          0 if outcome == "PASS" else 1, step_id.split(":")[0]))
            conn.commit()
            get_intel()._memo.clear()
            return step_id
    return get_intel().record_step(app_name, goal, verb, element_name=element_name,
                                   element_role=element_role, shortcut=shortcut,
                                   menu_path=menu_path, outcome=outcome, source=source)
