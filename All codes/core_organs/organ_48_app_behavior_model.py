"""
organ_48_app_behavior_model.py — the BEHAVIOR MODEL: how an app WORKS, not how it looks.

organ_47 answers "what shortcut / menu path does a pro use for this goal".
This organ answers the deeper questions that make unattended, same-quality
operation on *any* app possible:

  - what STATE is the app in (mode indicators, open dialogs)           -> modes
  - what does each control DO, proven by a before/after diff           -> transitions
  - which EFFECTOR actually works on this app (uia / wm_command / key) -> effector stats
  - how is a big task decomposed into verified sub-goals               -> templates (DATA)
  - what is the app allowed to do UNATTENDED right now                 -> autonomy gate
  - what did it do all day, honestly                                   -> audit + day report

HARD RULES (project laws, enforced here, not just documented)
  * Task decomposition is DATA (template rows in the DB / pack JSON), never an
    app-specific Python function. Adding an app = adding a pack file.
  * Trust order learned > catalog > archetype > distilled, with organ_47's
    confidence math (climb on verified PASS, erode on failure). A pack can NEVER
    claim `learned`; only a verified postcondition promotes an entry.
  * Every pre/postcondition is machine-checkable from perception (UIA diff,
    window titles, element values, OCR numbers, files). If no tier can observe an
    effect the entry is `opaque` and never auto-executes.
  * Exploration is graded: E0 read-only, E1 reversible-with-unwind, E2 never
    explored. The crawler never actuates anything in E0 and always unwinds E1.
  * No physical input (headless_input only). A tier that cannot run is reported
    as skipped, never faked.
  * App-version hash change demotes learned entries to unverified.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.organ_48_app_behavior_model")

_IS_WINDOWS = os.name == "nt"

DB_PATH = os.environ.get(
    "HOJAIGA_BEHAVIOR_DB", os.path.join(r"D:\new_automation", "data", "app_behavior.db"))
PACK_DIR = os.environ.get(
    "HOJAIGA_PACK_DIR", os.path.join(r"D:\new_automation", "data", "knowledge_packs"))

PACK_SCHEMA = "hojaiga.pack/1"
GATE_MIN_SUCCESSES = int(os.environ.get("HOJAIGA_GATE_MIN_SUCCESSES", "3"))
CRAWL_BUDGET_S = float(os.environ.get("HOJAIGA_CRAWL_BUDGET_S", "5"))   # soft base (organ_40's 5 s lesson)
CRAWL_MAX_S = float(os.environ.get("HOJAIGA_CRAWL_MAX_S", "45"))        # hard cap; soft extends while yield continues
CLI_HARVEST_TIMEOUT_S = float(os.environ.get("HOJAIGA_CLI_HARVEST_TIMEOUT_S", "20"))

TRUST_RANK = {"learned": 4, "catalog": 3, "archetype": 2, "distilled": 1}
PACK_MAX_TRUST = {"catalog", "archetype", "distilled"}      # packs can never self-declare learned
RISK_CLASSES = ("E0", "E1", "E2", "EU")  # EU = unclassified: effect/reversibility unknown

SCHEMA = """
CREATE TABLE IF NOT EXISTS bm_packs (
    pack_id TEXT PRIMARY KEY, app_key TEXT, version_hash TEXT, sources_json TEXT, loaded_ts REAL);
CREATE TABLE IF NOT EXISTS bm_app_versions (app_key TEXT PRIMARY KEY, version_hash TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS bm_modes (
    app_key TEXT, mode TEXT, indicator_json TEXT, PRIMARY KEY (app_key, mode));
CREATE TABLE IF NOT EXISTS bm_commands (
    cmd_id TEXT PRIMARY KEY, app_key TEXT, name TEXT, goal TEXT, verb TEXT,
    shortcut TEXT, menu_path TEXT, automation_id TEXT, menu_id INTEGER,
    risk TEXT, pre_json TEXT, post_json TEXT, unwind TEXT, opaque INTEGER DEFAULT 0,
    source TEXT, confidence REAL, successes INTEGER DEFAULT 0, failures INTEGER DEFAULT 0,
    stale INTEGER DEFAULT 0, origin TEXT, evidence TEXT, ts REAL);
CREATE INDEX IF NOT EXISTS bm_cmd_app ON bm_commands(app_key, goal);
CREATE TABLE IF NOT EXISTS bm_transitions (
    tid TEXT PRIMARY KEY, app_key TEXT, state_from TEXT, action TEXT, effector TEXT,
    state_to TEXT, evidence TEXT, count INTEGER DEFAULT 1, ts REAL);
CREATE INDEX IF NOT EXISTS bm_tr_from ON bm_transitions(app_key, state_from);
CREATE TABLE IF NOT EXISTS bm_templates (
    tpl_id TEXT PRIMARY KEY, app_key TEXT, name TEXT, aliases_json TEXT, steps_json TEXT,
    source TEXT, confidence REAL, hits INTEGER DEFAULT 0, failures INTEGER DEFAULT 0,
    stale INTEGER DEFAULT 0, seed_note TEXT, ts REAL);
CREATE INDEX IF NOT EXISTS bm_tpl_app ON bm_templates(app_key);
CREATE TABLE IF NOT EXISTS bm_stats (
    key TEXT PRIMARY KEY, successes INTEGER DEFAULT 0, failures INTEGER DEFAULT 0,
    consecutive_fail INTEGER DEFAULT 0, confidence REAL DEFAULT 0.3, last_outcome TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS bm_effectors (
    app_key TEXT, verb TEXT, effector TEXT, successes INTEGER DEFAULT 0,
    failures INTEGER DEFAULT 0, PRIMARY KEY (app_key, verb, effector));
CREATE TABLE IF NOT EXISTS bm_ui_regions (
    region_id TEXT PRIMARY KEY, app_key TEXT, title TEXT, via TEXT, elements_json TEXT,
    n_elements INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS bm_queue (
    qid TEXT PRIMARY KEY, run_id TEXT, app_key TEXT, task TEXT, reason TEXT,
    context_json TEXT, status TEXT DEFAULT 'pending', ts REAL);
CREATE TABLE IF NOT EXISTS bm_audit (
    aid INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, run_id TEXT, app_key TEXT,
    kind TEXT, subject TEXT, decision TEXT, reason TEXT, evidence TEXT);
"""


# ===========================================================================
# 1. Observation: ObservedState — what perception can machine-check
# ===========================================================================

def _win_title(h: int) -> str:
    if not _IS_WINDOWS or not h:
        return ""
    try:
        n = ctypes.windll.user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(max(n, 0) + 2)
        ctypes.windll.user32.GetWindowTextW(h, buf, n + 2)
        return buf.value
    except Exception:
        return ""


def _win_class(h: int) -> str:
    try:
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(h, buf, 256)
        return buf.value
    except Exception:
        return ""


@dataclass
class ObservedState:
    """Everything an assertion may read. OCR is lazy and tri-state: a tier that
    cannot run reports `skipped:<why>` rather than an empty string that would
    look like 'nothing on screen'."""
    title: str = ""
    names: List[str] = field(default_factory=list)       # lowercased control names
    values: List[str] = field(default_factory=list)      # lowercased control values
    windows: List[str] = field(default_factory=list)     # other top-level windows (dialogs, popups)
    ocr: Optional[str] = None
    ocr_status: str = "not-requested"                    # ok | not-requested | skipped:<why>
    region_hash: str = ""
    hwnd: int = 0
    mode: str = ""

    def uia_signature(self) -> str:
        return hashlib.md5(("|".join(sorted(self.names)) + "|".join(sorted(self.windows))
                            + self.title).encode("utf-8")).hexdigest()


def ocr_window_text(hwnd: int) -> Tuple[Optional[str], str]:
    """OCR the window's own pixels. Returns (text|None, status)."""
    try:
        import pytesseract                                   # noqa: F401
    except Exception:
        return None, "skipped:pytesseract-missing"
    try:
        from core_organs import headless_input as hin
        img, why = hin.capture_window(hwnd)
        if img is None:
            return None, f"skipped:capture-unavailable({why})"
        import pytesseract as pt
        return pt.image_to_string(img) or "", "ok"
    except Exception as exc:
        return None, f"skipped:ocr-error({type(exc).__name__})"


def observe(hwnd: int, *, grounding=None, want_ocr: bool = False,
            want_region: bool = False, max_nodes: int = 500) -> ObservedState:
    """Snapshot the app: title, control names/values (UIA incl. popup hosts),
    sibling windows, and optionally OCR text / pixel hash."""
    from core_organs import desktop_grounding as dg
    from core_organs import headless_input as hin
    g = grounding or dg.DesktopGrounding()
    st = ObservedState(hwnd=hwnd, title=_win_title(hwnd))
    elements = []
    try:
        elements = g._walk_uia(hwnd, max_depth=14, max_nodes=max_nodes) if dg.HAS_UIA else g._walk_win32(hwnd)
    except Exception:
        pass
    others: List[int] = []
    try:
        others = _open_popups(hwnd)[:10]
        for w in others:
            try:
                elements += g._walk_uia(w, max_depth=8, max_nodes=200) if dg.HAS_UIA else []
            except Exception:
                continue
    except Exception:
        pass
    names = [(e.name or "").lower() for e in elements if (e.name or "").lower() != "pop-uphost"]
    # The old walk drops controls with empty rectangles, which is EVERYTHING in a hidden UWP app (Calculator's
    # display, Settings' pages). A bulk snapshot needs no geometry, so union its names in: otherwise a step that
    # really changed the UI looks like "nothing happened" and gets wrongly failed.
    try:
        from core_organs import fast_uia
        snap = fast_uia.snapshot(hwnd, timeout_ms=6000)
        if snap:
            seen = set(names)
            for n in snap:
                nm = (n.name or "").lower().strip()
                if nm and nm != "pop-uphost" and nm not in seen:
                    names.append(nm)
                    seen.add(nm)
    except Exception:
        pass
    st.names = names
    st.values = [(e.value or "").lower() for e in elements if getattr(e, "value", "")]
    st.windows = sorted({(_win_title(w) or _win_class(w)).lower() for w in others})
    if want_ocr:
        st.ocr, st.ocr_status = ocr_window_text(hwnd)
    if want_region:
        try:
            st.region_hash = dg.DesktopVerifier()._region_hash(hwnd)
        except Exception:
            pass
    return st


# ===========================================================================
# 2. Assertions — machine-checkable pre/postconditions (pure functions)
# ===========================================================================
# An assertion is a dict {"kind": ..., ...params}. Evaluating returns
#   (True|False|None, evidence)   None == this tier cannot observe it (SKIPPED).

def _num(s: str) -> Optional[int]:
    try:
        return int(re.sub(r"[^\d]", "", s))
    except Exception:
        return None


def _ocr_num(state: Optional[ObservedState], pattern: str) -> Tuple[Optional[int], str]:
    if state is None:
        return None, "no-state"
    if state.ocr is None:
        return None, state.ocr_status
    m = re.search(pattern, state.ocr, re.IGNORECASE)
    if not m:
        return None, "pattern-not-found"
    return _num(m.group(1)), "ok"


def _a_title_contains(p, b, a, ctx):
    ok = str(p["value"]).lower() in (a.title or "").lower()
    return ok, f"title {'has' if ok else 'lacks'} '{p['value']}'"


def _a_title_not_contains(p, b, a, ctx):
    ok = str(p["value"]).lower() not in (a.title or "").lower()
    return ok, f"title {'lacks' if ok else 'has'} '{p['value']}'"


def _a_element_present(p, b, a, ctx):
    want = str(p["name"]).lower()
    ok = any(want in n for n in a.names)
    return ok, f"element '{want}' {'present' if ok else 'absent'}"


def _a_element_absent(p, b, a, ctx):
    want = str(p["name"]).lower()
    ok = not any(want in n for n in a.names)
    return ok, f"element '{want}' {'gone' if ok else 'still present'}"


def _a_element_appeared(p, b, a, ctx):
    want = str(p["name"]).lower()
    was = b is not None and any(want in n for n in b.names)
    now = any(want in n for n in a.names)
    return (now and not was), f"'{want}' before={was} after={now}"


def _a_value_contains(p, b, a, ctx):
    want = str(p["text"]).lower()
    ok = any(want in v for v in a.values)
    return ok, f"value-text '{want[:30]}' {'found' if ok else 'not found'} in {len(a.values)} control value(s)"


def _a_window_opened(p, b, a, ctx):
    before = set(b.windows) if b else set()
    new = [w for w in a.windows if w not in before]
    want = str(p.get("title_contains", "")).lower()
    if want:
        new = [w for w in new if want in w]
    return bool(new), f"new window(s): {new[:3]}" if new else "no new window"


def _a_window_closed(p, b, a, ctx):
    before = set(b.windows) if b else set()
    gone = [w for w in before if w not in a.windows]
    return bool(gone), f"closed: {gone[:3]}" if gone else "no window closed"


def _a_window_count_delta(p, b, a, ctx):
    d = len(a.windows) - (len(b.windows) if b else 0)
    want = int(p.get("min", 1))
    ok = d >= want if want >= 0 else d <= want
    return ok, f"window count delta {d:+d}"


def _a_ui_changed(p, b, a, ctx):
    if b is None:
        return None, "no before-state"
    ok = b.uia_signature() != a.uia_signature()
    return ok, "UIA tree/title/windows " + ("changed" if ok else "unchanged")


def _a_region_changed(p, b, a, ctx):
    if not (b and b.region_hash and a.region_hash):
        return None, "pixel hash unavailable"
    ok = b.region_hash != a.region_hash
    return ok, "pixels " + ("changed" if ok else "unchanged")


def _a_ocr_contains(p, b, a, ctx):
    if a.ocr is None:
        return None, f"ocr {a.ocr_status}"
    ok = str(p["text"]).lower() in a.ocr.lower()
    return ok, f"ocr {'has' if ok else 'lacks'} '{p['text']}'"


def _a_ocr_regex(p, b, a, ctx):
    if a.ocr is None:
        return None, f"ocr {a.ocr_status}"
    ok = re.search(p["pattern"], a.ocr, re.IGNORECASE) is not None
    return ok, f"ocr regex {'matched' if ok else 'no match'}"


def _a_ocr_number_increase(p, b, a, ctx):
    """e.g. Blender overlay 'verts: 0 -> N' proves geometry was added."""
    pat = p.get("pattern", r"verts?\w*\s*[:=]?\s*([\d,]+)")
    after, why_a = _ocr_num(a, pat)
    before, why_b = _ocr_num(b, pat)
    if why_a.startswith("skipped") or why_b.startswith("skipped"):
        return None, f"ocr {why_a if why_a.startswith('skipped') else why_b}"
    if after is None:
        return False, f"counter not readable after ({why_a})"
    if before is None:
        before = 0 if p.get("missing_before_is_zero") else None
        if before is None:
            return False, f"counter not readable before ({why_b})"
    d = after - before
    ok = d >= int(p.get("min_delta", 1))
    return ok, f"counter {before} -> {after} (delta {d:+d})"


def _a_ocr_number_min(p, b, a, ctx):
    after, why = _ocr_num(a, p["pattern"])
    if why.startswith("skipped"):
        return None, f"ocr {why}"
    if after is None:
        return False, f"counter not readable ({why})"
    return after >= int(p["min"]), f"counter {after} (min {p['min']})"


def _a_file_exists(p, b, a, ctx):
    path = os.path.abspath(str(p["path"]))
    end = time.time() + float(p.get("wait_s", 3.0))
    ok = os.path.exists(path)
    while not ok and time.time() < end:           # apps write asynchronously; bounded wait
        time.sleep(0.25)
        ok = os.path.exists(path)
    return ok, f"file {os.path.basename(path)} {'exists' if ok else 'MISSING'}"


def _a_file_contains(p, b, a, ctx):
    path = os.path.abspath(str(p["path"]))
    end = time.time() + float(p.get("wait_s", 3.0))
    text = ""
    while time.time() < end:
        try:
            with open(path, "r", encoding=p.get("encoding", "utf-8"), errors="replace") as fh:
                text = fh.read()
            if str(p["text"]) in text:
                break
        except Exception:
            pass
        time.sleep(0.25)
    ok = str(p["text"]) in text
    return ok, f"file {'contains' if ok else 'lacks'} expected text ({len(text)} chars)"


def _a_mode_is(p, b, a, ctx):
    ok = (a.mode or "") == str(p["mode"])
    return ok, f"mode={a.mode or '?'} (want {p['mode']})"


ASSERTIONS: Dict[str, Callable] = {
    "title_contains": _a_title_contains, "title_not_contains": _a_title_not_contains,
    "element_present": _a_element_present, "element_absent": _a_element_absent,
    "element_appeared": _a_element_appeared, "value_contains": _a_value_contains,
    "window_opened": _a_window_opened, "window_closed": _a_window_closed,
    "window_count_delta": _a_window_count_delta, "ui_changed": _a_ui_changed,
    "region_changed": _a_region_changed, "ocr_contains": _a_ocr_contains,
    "ocr_regex": _a_ocr_regex, "ocr_number_increase": _a_ocr_number_increase,
    "ocr_number_min": _a_ocr_number_min, "file_exists": _a_file_exists,
    "file_contains": _a_file_contains, "mode_is": _a_mode_is,
}


def needs_ocr(assertions: List[dict]) -> bool:
    return any(str(a.get("kind", "")).startswith("ocr_") for a in assertions or [])


def needs_region(assertions: List[dict]) -> bool:
    return any(a.get("kind") == "region_changed" for a in assertions or [])


def fmt_params(obj: Any, params: Dict[str, Any]) -> Any:
    """Substitute {slot} placeholders in strings, recursively (data stays data)."""
    if isinstance(obj, str):
        for k, v in (params or {}).items():
            obj = obj.replace("{" + k + "}", str(v))
        return obj
    if isinstance(obj, list):
        return [fmt_params(x, params) for x in obj]
    if isinstance(obj, dict):
        return {k: fmt_params(v, params) for k, v in obj.items()}
    return obj


@dataclass
class AssertionResult:
    verdict: str                                  # PASS | FAIL | OPAQUE
    evidence: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    observed: int = 0                             # assertions that a tier could actually evaluate

    @property
    def ok(self) -> bool:
        return self.verdict == "PASS"

    def text(self) -> str:
        t = "; ".join(self.evidence)
        if self.skipped:
            t += (" | " if t else "") + "skipped: " + "; ".join(self.skipped)
        return t


def evaluate(assertions: List[dict], before: Optional[ObservedState],
             after: ObservedState, params: Optional[Dict[str, Any]] = None) -> AssertionResult:
    """All evaluable assertions must hold. Skipped (unobservable) ones never count as
    satisfied: if NOTHING could be observed the result is OPAQUE, never PASS."""
    res = AssertionResult("OPAQUE")
    for raw in assertions or []:
        a = fmt_params(raw, params or {})
        fn = ASSERTIONS.get(a.get("kind"))
        if fn is None:
            res.skipped.append(f"unknown-assertion:{a.get('kind')}")
            continue
        try:
            ok, ev = fn(a, before, after, params or {})
        except Exception as exc:
            ok, ev = None, f"{a.get('kind')} error {type(exc).__name__}"
        if ok is None:
            res.skipped.append(f"{a.get('kind')}={ev}")
            continue
        res.observed += 1
        res.evidence.append(("OK " if ok else "FAIL ") + ev)
        if not ok:
            res.verdict = "FAIL"
    if res.verdict != "FAIL" and res.observed > 0:
        res.verdict = "PASS"
    return res


# ===========================================================================
# 3. Risk classification (generic word cues — not per-app)
# ===========================================================================

_E2_RE = re.compile(r"\b(delete|remove|erase|format|overwrite|uninstall|purchase|buy|pay|"
                    r"checkout|send|publish|post|submit|discard|empty|reset|clear all|"
                    r"don.?t save|close|exit|quit|sign out|log ?out)\b", re.I)
# E1 means "opens a surface that Escape / WM_CLOSE reliably unwinds" (dialog, pane, palette).
# View/zoom/status-bar style TOGGLES change persistent state with no cheap unwind, so they stay EU.
_E1_RE = re.compile(r"(\.\.\.|…|\bsettings\b|\bpreferences\b|\boptions\b|\babout\b|\bproperties\b|"
                    r"\bpage setup\b|\bfind\b|\breplace\b|\bgo to\b)", re.I)


def classify_risk(name: str, menu_path: str = "", verb: str = "") -> str:
    """E2 destructive/irreversible (never explored) | E1 reversible (opens/views, has an
    unwind) | EU unclassified. E0 is a property of the *method* (read-only harvest), not of
    an action, so actions are never labelled E0."""
    hay = f"{name} {menu_path}"
    if _E2_RE.search(hay):
        return "E2"
    if _E1_RE.search(hay):
        return "E1"
    return "EU"


# ===========================================================================
# 4. App-version hash (a version change demotes trust)
# ===========================================================================

def app_version_hash(exe_path: str = "", version: str = "") -> str:
    try:
        st = os.stat(exe_path) if exe_path and os.path.exists(exe_path) else None
    except Exception:
        st = None
    raw = f"{version}|{st.st_size if st else 0}|{int(st.st_mtime) if st else 0}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _exe_of_hwnd(hwnd: int) -> str:
    if not _IS_WINDOWS:
        return ""
    try:
        from core_organs import headless_input as hin
        pid = hin.window_pid(hwnd)
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = wt.DWORD(1024)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return buf.value
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _bg(hwnd: int):
    """Scannable-but-invisible window session (background_window): a minimized app is parked
    off-screen without activation for the duration, then re-minimized exactly as it was. Visible
    windows are left untouched. Never raises: no parking support => no-op context."""
    try:
        from core_organs import background_window as bw
        return bw.BackgroundSession(hwnd)
    except Exception:
        import contextlib
        return contextlib.nullcontext()


def _popups(hwnd: int) -> List[int]:
    """Popups/dialogs/flyouts that belong to `hwnd` by OWNERSHIP (never the taskbar, the desktop, another
    window of the same process, or a shell window). headless_input.popup_windows is process-based."""
    try:
        from core_organs import background_window as bw
        return bw.target_popups(hwnd)
    except Exception:
        from core_organs import headless_input as hin
        return hin.popup_windows(hwnd)


def _keep_hidden(hwnd: int) -> None:
    try:
        from core_organs import background_window as bw
        bw.keep_hidden(hwnd)
    except Exception:
        pass


def _app_key(name: str) -> str:
    try:
        from core_organs.organ_47_app_intelligence import _app_key as k47
        return k47(name)
    except Exception:
        return re.sub(r"\.(exe|lnk)$", "", _norm(name)) or "unknown"


def _tok(s: str) -> set:
    return {t[:5] for t in re.findall(r"[a-z0-9]+", _norm(s)) if len(t) > 1}


# ===========================================================================
# 5. Pack format: validate / load (packs are untrusted-until-verified DATA)
# ===========================================================================

VERBS = ("key", "type", "invoke", "menu", "wm_command", "file_dialog", "wait", "judge")


def validate_pack(pack: Dict[str, Any]) -> List[str]:
    """Return a list of problems (empty == valid). Enforces: schema tag, trust cap,
    only known assertion kinds / verbs / risk classes, every step has an id + goal."""
    errs: List[str] = []
    if not isinstance(pack, dict):
        return ["pack is not an object"]
    if pack.get("schema") != PACK_SCHEMA:
        errs.append(f"schema must be '{PACK_SCHEMA}'")
    if not (pack.get("app") or pack.get("archetype")):
        errs.append("pack needs 'app' or 'archetype'")
    trust = pack.get("trust", "catalog")
    if trust not in PACK_MAX_TRUST:
        errs.append(f"trust '{trust}' not allowed (packs may not self-declare learned)")

    def _chk_assertions(where: str, lst: Any):
        if lst in (None, []):
            return
        if not isinstance(lst, list):
            errs.append(f"{where}: assertions must be a list")
            return
        for a in lst:
            if not isinstance(a, dict) or a.get("kind") not in ASSERTIONS:
                errs.append(f"{where}: unknown assertion {a!r}")

    for i, m in enumerate(pack.get("modes", []) or []):
        if not m.get("name"):
            errs.append(f"modes[{i}] missing name")
        _chk_assertions(f"modes[{i}].indicator", m.get("indicator"))
    for i, c in enumerate(pack.get("commands", []) or []):
        if not c.get("name"):
            errs.append(f"commands[{i}] missing name")
        if c.get("risk") and c["risk"] not in RISK_CLASSES:
            errs.append(f"commands[{i}] bad risk {c['risk']}")
        _chk_assertions(f"commands[{i}].pre", c.get("pre"))
        _chk_assertions(f"commands[{i}].post", c.get("post"))
    for i, t in enumerate(pack.get("templates", []) or []):
        if not t.get("name"):
            errs.append(f"templates[{i}] missing name")
        if not t.get("steps"):
            errs.append(f"templates[{i}] has no steps")
        seen = set()
        for j, s in enumerate(t.get("steps", []) or []):
            w = f"templates[{i}].steps[{j}]"
            if not s.get("id") or not s.get("goal"):
                errs.append(f"{w} needs id and goal")
            if s.get("id") in seen:
                errs.append(f"{w} duplicate id {s.get('id')}")
            seen.add(s.get("id"))
            if s.get("risk") and s["risk"] not in RISK_CLASSES:
                errs.append(f"{w} bad risk {s['risk']}")
            for k, d in enumerate(s.get("do", []) or []):
                if d.get("verb") not in VERBS:
                    errs.append(f"{w}.do[{k}] unknown verb {d.get('verb')!r}")
            _chk_assertions(w + ".pre", s.get("pre"))
            _chk_assertions(w + ".post", s.get("post"))
    return errs


# ===========================================================================
# 6. The behavior model (DB-backed state machine + templates + gate)
# ===========================================================================

@dataclass
class GateDecision:
    action: str                 # EXECUTE | SAFE_ATTEMPT | QUEUE
    reason: str
    risk: str = "EU"


@dataclass
class TemplateMatch:
    tpl_id: str
    app_key: str
    name: str
    steps: List[dict]
    source: str
    confidence: float
    score: float
    seed_note: str = ""


class BehaviorModel:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=15, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    # ---- confidence math: organ_47's, so trust means the same thing everywhere ----
    @staticmethod
    def _climb(cur: float, outcome: str, source: str) -> float:
        from core_organs.organ_47_app_intelligence import _reinforce
        return _reinforce(cur, outcome, source)

    @staticmethod
    def _initial(source: str) -> float:
        from core_organs.organ_47_app_intelligence import _SOURCE_FLOOR
        return _SOURCE_FLOOR.get(source, 0.35)

    # ---- packs ----------------------------------------------------------------
    def load_pack(self, pack: Any, *, version_hash: str = "") -> Dict[str, Any]:
        """Ingest a pack (path or dict). Everything enters UNVERIFIED at <= catalog trust."""
        origin = ""
        if isinstance(pack, str):
            origin = pack
            with open(pack, "r", encoding="utf-8") as fh:
                pack = json.load(fh)
        errs = validate_pack(pack)
        if errs:
            return {"loaded": False, "errors": errs}
        scope = pack.get("scope") or ("archetype" if pack.get("archetype") and not pack.get("app")
                                       else "app")
        app_key = (f"@archetype:{pack['archetype']}" if scope == "archetype"
                   else _app_key(pack["app"]))
        trust = pack.get("trust", "catalog")
        if scope == "archetype" and trust == "catalog":
            trust = "archetype"
        declared = pack.get("version_hash", "*")
        pack_id = hashlib.sha1(json.dumps(pack, sort_keys=True).encode()).hexdigest()[:12]
        now = time.time()
        counts = {"modes": 0, "commands": 0, "templates": 0}
        for m in pack.get("modes", []) or []:
            self._conn.execute(
                "INSERT OR REPLACE INTO bm_modes(app_key, mode, indicator_json) VALUES (?,?,?)",
                (app_key, m["name"], json.dumps(m.get("indicator", []))))
            counts["modes"] += 1
        for c in pack.get("commands", []) or []:
            self.upsert_command(app_key, c, source=trust, origin=origin or f"pack:{pack_id}")
            counts["commands"] += 1
        for t in pack.get("templates", []) or []:
            self.upsert_template(app_key, t, source=trust)
            counts["templates"] += 1
        self._conn.execute(
            "INSERT OR REPLACE INTO bm_packs(pack_id, app_key, version_hash, sources_json, loaded_ts)"
            " VALUES (?,?,?,?,?)",
            (pack_id, app_key, declared if declared != "*" else (version_hash or "*"),
             json.dumps(pack.get("sources", [])), now))
        self._conn.commit()
        return {"loaded": True, "app_key": app_key, "pack_id": pack_id, "trust": trust,
                "counts": counts, "declared_version": declared}

    def load_pack_dir(self, directory: str = PACK_DIR) -> List[Dict[str, Any]]:
        out = []
        if not os.path.isdir(directory):
            return out
        for fn in sorted(os.listdir(directory)):
            if fn.endswith(".pack.json"):
                try:
                    r = self.load_pack(os.path.join(directory, fn))
                except Exception as exc:
                    r = {"loaded": False, "errors": [f"{type(exc).__name__}: {exc}"]}
                r["file"] = fn
                out.append(r)
        return out

    def check_version(self, app_key: str, version_hash: str) -> int:
        """Version change => demote every entry to unverified (never silently trusted)."""
        row = self._conn.execute(
            "SELECT version_hash FROM bm_app_versions WHERE app_key=?", (app_key,)).fetchone()
        demoted = 0
        if row and version_hash and row["version_hash"] != version_hash:
            cur = self._conn.execute(
                "UPDATE bm_commands SET source=CASE WHEN source='learned' THEN 'catalog' ELSE source END,"
                " confidence=MIN(confidence, 0.5), stale=1 WHERE app_key=?", (app_key,))
            demoted += cur.rowcount
            cur = self._conn.execute(
                "UPDATE bm_templates SET source=CASE WHEN source='learned' THEN 'catalog' ELSE source END,"
                " confidence=MIN(confidence, 0.5), stale=1 WHERE app_key=?", (app_key,))
            demoted += cur.rowcount
            self._conn.execute("UPDATE bm_stats SET successes=0, consecutive_fail=0"
                               " WHERE key LIKE ?", (app_key + ":%",))
            self.audit("", app_key, "version", app_key, "DEMOTE",
                       f"version hash {row['version_hash']} -> {version_hash}",
                       f"{demoted} entries demoted to unverified")
        if not row or row["version_hash"] != version_hash:
            self._conn.execute(
                "INSERT OR REPLACE INTO bm_app_versions(app_key, version_hash, ts) VALUES (?,?,?)",
                (app_key, version_hash, time.time()))
        self._conn.commit()
        return demoted

    # ---- commands ---------------------------------------------------------------
    def upsert_command(self, app_key: str, cmd: Dict[str, Any], *, source: str,
                       origin: str = "", evidence: str = "") -> str:
        assert source in TRUST_RANK
        name = cmd.get("name", "")
        ident = f"{app_key}|{_norm(name)}|{_norm(cmd.get('menu_path', ''))}|{_norm(cmd.get('shortcut', ''))}"
        cmd_id = "cmd_" + hashlib.md5(ident.encode()).hexdigest()[:12]
        risk = cmd.get("risk") or classify_risk(name, cmd.get("menu_path", ""))
        post = cmd.get("post") or []
        opaque = 1 if cmd.get("opaque") or not post else 0
        row = self._conn.execute("SELECT source, confidence FROM bm_commands WHERE cmd_id=?",
                                 (cmd_id,)).fetchone()
        if row:
            # never let a weaker source overwrite a stronger one
            if TRUST_RANK.get(row["source"], 0) >= TRUST_RANK[source]:
                source, conf = row["source"], row["confidence"]
            else:
                conf = self._initial(source)
        else:
            conf = self._initial(source)
        self._conn.execute(
            "INSERT OR REPLACE INTO bm_commands(cmd_id, app_key, name, goal, verb, shortcut, menu_path,"
            " automation_id, menu_id, risk, pre_json, post_json, unwind, opaque, source, confidence,"
            " successes, failures, stale, origin, evidence, ts)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, COALESCE((SELECT successes FROM bm_commands WHERE cmd_id=?),0),"
            " COALESCE((SELECT failures FROM bm_commands WHERE cmd_id=?),0),0,?,?,?)",
            (cmd_id, app_key, name, _norm(cmd.get("goal") or name), cmd.get("verb", "invoke"),
             cmd.get("shortcut", ""), cmd.get("menu_path", ""), cmd.get("automation_id", ""),
             cmd.get("menu_id"), risk, json.dumps(cmd.get("pre") or []), json.dumps(post),
             cmd.get("unwind", ""), opaque, source, conf, cmd_id, cmd_id, origin,
             evidence or cmd.get("evidence", ""), time.time()))
        self._conn.commit()
        return cmd_id

    def commands(self, app_key: str, goal: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM bm_commands WHERE app_key=? ORDER BY confidence DESC LIMIT 2000",
            (app_key,)).fetchall()
        out = [dict(r) for r in rows]
        if goal:
            gt = _tok(goal)
            out = [r for r in out if gt & (_tok(r["goal"]) | _tok(r["name"]) | _tok(r["menu_path"]))]
        out.sort(key=lambda r: (-TRUST_RANK.get(r["source"], 0), -r["confidence"]))
        return out[:limit]

    def command_outcome(self, cmd_id: str, outcome: str, evidence: str = "",
                        promote: bool = False) -> None:
        row = self._conn.execute("SELECT * FROM bm_commands WHERE cmd_id=?", (cmd_id,)).fetchone()
        if not row:
            return
        src = row["source"]
        if outcome == "PASS":
            if promote and src != "learned":
                src, conf = "learned", min(0.85, self._initial("learned") + 0.30)
            else:
                conf = self._climb(row["confidence"], "PASS", src)
            self._conn.execute(
                "UPDATE bm_commands SET source=?, confidence=?, successes=successes+1, stale=0,"
                " evidence=?, ts=? WHERE cmd_id=?", (src, conf, evidence or row["evidence"],
                                                     time.time(), cmd_id))
        else:
            self._conn.execute(
                "UPDATE bm_commands SET confidence=?, failures=failures+1, ts=? WHERE cmd_id=?",
                (self._climb(row["confidence"], "FAIL", src), time.time(), cmd_id))
        self._conn.commit()

    def command_by_name(self, app_key: str, name: str) -> Optional[Dict[str, Any]]:
        """Best known command for a control label (exact label or menu-path leaf), highest trust first."""
        want = _norm(name.replace("&", ""))
        if not want:
            return None
        best = None
        for r in self._conn.execute("SELECT * FROM bm_commands WHERE app_key=?", (app_key,)):
            leaf = _norm((r["menu_path"] or "").split(">")[-1].replace("&", ""))
            if _norm(r["name"]) == want or leaf == want:
                k = (TRUST_RANK.get(r["source"], 0), r["confidence"])
                if best is None or k > best[0]:
                    best = (k, dict(r))
        return best[1] if best else None

    def record_region(self, app_key: str, title: str, elements: List[Dict[str, Any]], via: str = "") -> str:
        """Persist the FULL tree of a UI region a probe revealed (dialog / settings pane / palette),
        so what a child window contains is knowledge, not something re-discovered every scan."""
        slim = [{"name": e.get("name", ""), "type": e.get("type", e.get("role", "")),
                 "parent": e.get("parent_tab") or e.get("parent_menu") or ""} for e in elements][:400]
        rid = hashlib.md5(f"{app_key}|{_norm(title)}|{sorted(x['name'] for x in slim)[:40]}".encode()).hexdigest()[:14]
        self._conn.execute(
            "INSERT OR REPLACE INTO bm_ui_regions(region_id, app_key, title, via, elements_json, n_elements, ts)"
            " VALUES (?,?,?,?,?,?,?)", (rid, app_key, title[:200], via[:200], json.dumps(slim), len(slim), time.time()))
        self._conn.commit()
        return rid

    def regions(self, app_key: str) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._conn.execute(
            "SELECT region_id, title, via, n_elements FROM bm_ui_regions WHERE app_key=? ORDER BY ts DESC", (app_key,))]

    # ---- state machine: modes + transitions --------------------------------------
    def modes(self, app_key: str) -> Dict[str, List[dict]]:
        rows = self._conn.execute("SELECT mode, indicator_json FROM bm_modes WHERE app_key=?",
                                  (app_key,)).fetchall()
        return {r["mode"]: json.loads(r["indicator_json"] or "[]") for r in rows}

    def current_mode(self, app_keys: List[str], state: ObservedState) -> str:
        for ak in app_keys:
            for mode, indicator in self.modes(ak).items():
                if indicator and evaluate(indicator, None, state).ok:
                    return mode
        return ""

    @staticmethod
    def state_signature(state: ObservedState) -> str:
        title = re.sub(r"^\*", "", _norm(state.title))
        title = title.split(" - ")[-1] if " - " in title else title   # drop document name
        raw = f"{title}|{','.join(sorted(state.windows))}|{state.mode}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def record_transition(self, app_key: str, before: ObservedState, action: str,
                          effector: str, after: ObservedState, evidence: str = "") -> str:
        """(state, action, effector) -> (state', evidence). Re-observing the same
        transition just increments its count — verified branches are not re-probed."""
        s0, s1 = self.state_signature(before), self.state_signature(after)
        tid = hashlib.md5(f"{app_key}|{s0}|{action}|{effector}|{s1}".encode()).hexdigest()[:14]
        self._conn.execute(
            "INSERT INTO bm_transitions(tid, app_key, state_from, action, effector, state_to, evidence, count, ts)"
            " VALUES (?,?,?,?,?,?,?,1,?) ON CONFLICT(tid) DO UPDATE SET count=count+1, ts=excluded.ts,"
            " evidence=excluded.evidence", (tid, app_key, s0, action, effector, s1, evidence[:600], time.time()))
        self._conn.commit()
        return tid

    def transitions(self, app_key: str, state_from: str = "") -> List[Dict[str, Any]]:
        if state_from:
            rows = self._conn.execute(
                "SELECT * FROM bm_transitions WHERE app_key=? AND state_from=? ORDER BY count DESC",
                (app_key, state_from)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM bm_transitions WHERE app_key=? ORDER BY count DESC", (app_key,)).fetchall()
        return [dict(r) for r in rows]

    def path_to_mode(self, app_keys: List[str], from_mode: str, to_mode: str,
                     max_depth: int = 4) -> Optional[List[Dict[str, Any]]]:
        """BFS over commands whose pre/post mention mode_is: the shortest verified-or-seed
        command chain from one mode to another (state-machine recovery, no LLM)."""
        edges: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for ak in app_keys:
            for r in self._conn.execute("SELECT * FROM bm_commands WHERE app_key=?", (ak,)):
                pre = [a for a in json.loads(r["pre_json"] or "[]") if a.get("kind") == "mode_is"]
                post = [a for a in json.loads(r["post_json"] or "[]") if a.get("kind") == "mode_is"]
                if pre and post and r["risk"] != "E2":
                    edges.setdefault(pre[0]["mode"], []).append((post[0]["mode"], dict(r)))
        frontier, seen = [(from_mode, [])], {from_mode}
        while frontier:
            mode, path = frontier.pop(0)
            if mode == to_mode:
                return path
            if len(path) >= max_depth:
                continue
            for nxt, cmd in sorted(edges.get(mode, []), key=lambda e: -TRUST_RANK.get(e[1]["source"], 0)):
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append((nxt, path + [cmd]))
        return None

    # ---- templates (task decomposition as DATA) ----------------------------------
    def upsert_template(self, app_key: str, tpl: Dict[str, Any], *, source: str) -> str:
        assert source in TRUST_RANK
        tpl_id = "tpl_" + hashlib.md5(f"{app_key}|{_norm(tpl['name'])}".encode()).hexdigest()[:12]
        row = self._conn.execute("SELECT source, confidence, hits, failures FROM bm_templates WHERE tpl_id=?",
                                 (tpl_id,)).fetchone()
        if row and TRUST_RANK.get(row["source"], 0) >= TRUST_RANK[source]:
            source, conf = row["source"], row["confidence"]
        else:
            conf = self._initial(source)
        self._conn.execute(
            "INSERT OR REPLACE INTO bm_templates(tpl_id, app_key, name, aliases_json, steps_json, source,"
            " confidence, hits, failures, stale, seed_note, ts) VALUES (?,?,?,?,?,?,?,"
            " COALESCE((SELECT hits FROM bm_templates WHERE tpl_id=?),0),"
            " COALESCE((SELECT failures FROM bm_templates WHERE tpl_id=?),0),0,?,?)",
            (tpl_id, app_key, tpl["name"], json.dumps(tpl.get("aliases", [])),
             json.dumps(tpl["steps"]), source, conf, tpl_id, tpl_id, tpl.get("seed_note", ""), time.time()))
        self._conn.commit()
        return tpl_id

    def match_template(self, app_name: str, task_text: str,
                       archetype: str = "", threshold: float = 0.34) -> Optional[TemplateMatch]:
        """Scope order app > archetype > generic, then token overlap with name/aliases, then
        trust. Pure data lookup — no LLM, no per-app branches."""
        scopes = [_app_key(app_name)]
        if archetype:
            scopes.append(f"@archetype:{archetype}")
        scopes.append("@archetype:generic_win32")
        tt = _tok(task_text)
        best: Optional[Tuple[tuple, TemplateMatch]] = None
        for si, sc in enumerate(scopes):
            for r in self._conn.execute("SELECT * FROM bm_templates WHERE app_key=?", (sc,)):
                phrases = [r["name"]] + json.loads(r["aliases_json"] or "[]")
                score = max((len(tt & _tok(p)) / (len(_tok(p)) or 1)) if tt else 0.0 for p in phrases)
                if score < threshold:
                    continue
                key = (round(score, 2), -si, TRUST_RANK.get(r["source"], 0), r["confidence"])
                m = TemplateMatch(r["tpl_id"], sc, r["name"], json.loads(r["steps_json"]),
                                  r["source"], r["confidence"], score, r["seed_note"] or "")
                if best is None or key > best[0]:
                    best = (key, m)
        return best[1] if best else None

    def template_outcome(self, tpl_id: str, outcome: str) -> None:
        row = self._conn.execute("SELECT source, confidence FROM bm_templates WHERE tpl_id=?",
                                 (tpl_id,)).fetchone()
        if not row:
            return
        if outcome == "PASS":
            # an end-to-end run whose every postcondition verified is what earns `learned`
            self._conn.execute(
                "UPDATE bm_templates SET source='learned', confidence=?, hits=hits+1, stale=0, ts=?"
                " WHERE tpl_id=?",
                (self._climb(max(row["confidence"], self._initial("learned")), "PASS", "learned"),
                 time.time(), tpl_id))
        else:
            self._conn.execute(
                "UPDATE bm_templates SET confidence=?, failures=failures+1, ts=? WHERE tpl_id=?",
                (self._climb(row["confidence"], "FAIL", row["source"]), time.time(), tpl_id))
        self._conn.commit()

    # ---- per-step stats + effector learning ----------------------------------------
    def step_stats(self, key: str) -> Dict[str, Any]:
        r = self._conn.execute("SELECT * FROM bm_stats WHERE key=?", (key,)).fetchone()
        return dict(r) if r else {"key": key, "successes": 0, "failures": 0,
                                  "consecutive_fail": 0, "confidence": 0.3, "last_outcome": ""}

    def record_step_outcome(self, key: str, outcome: str) -> Dict[str, Any]:
        s = self.step_stats(key)
        if outcome == "PASS":
            conf = self._climb(max(s["confidence"], 0.55), "PASS", "learned")
            s.update(successes=s["successes"] + 1, consecutive_fail=0, confidence=conf)
        else:
            s.update(failures=s["failures"] + 1, consecutive_fail=s["consecutive_fail"] + 1,
                     confidence=self._climb(s["confidence"], "FAIL", "learned"))
        s.update(last_outcome=outcome, ts=time.time())
        self._conn.execute(
            "INSERT OR REPLACE INTO bm_stats(key, successes, failures, consecutive_fail, confidence,"
            " last_outcome, ts) VALUES (?,?,?,?,?,?,?)",
            (key, s["successes"], s["failures"], s["consecutive_fail"], s["confidence"],
             s["last_outcome"], s["ts"]))
        self._conn.commit()
        return s

    def record_effector(self, app_key: str, verb: str, effector: str, ok: bool) -> None:
        self._conn.execute(
            "INSERT INTO bm_effectors(app_key, verb, effector, successes, failures) VALUES (?,?,?,?,?)"
            " ON CONFLICT(app_key, verb, effector) DO UPDATE SET successes=successes+?, failures=failures+?",
            (app_key, verb, effector, int(ok), int(not ok), int(ok), int(not ok)))
        self._conn.commit()

    def effector_order(self, app_key: str, verb: str, defaults: List[str]) -> List[str]:
        """Learned effector preference for this app (what the app ACCEPTS), defaults as tie-break."""
        rows = {r["effector"]: r for r in self._conn.execute(
            "SELECT * FROM bm_effectors WHERE app_key=? AND verb=?", (app_key, verb))}

        def score(e: str) -> Tuple[float, int]:
            r = rows.get(e)
            if not r:
                return (0.0, -defaults.index(e))
            tot = r["successes"] + r["failures"]
            return ((r["successes"] - r["failures"]) / (tot or 1) * min(tot, 5) / 5.0, -defaults.index(e))
        return sorted(defaults, key=score, reverse=True)

    def effector_coverage(self, app_key: str) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for r in self._conn.execute("SELECT * FROM bm_effectors WHERE app_key=?", (app_key,)):
            out.setdefault(r["verb"], {})[r["effector"]] = {"ok": r["successes"], "fail": r["failures"]}
        return out

    # ---- autonomy gate -----------------------------------------------------------------
    def gate(self, stat_key: str, *, risk: str, post: List[dict], has_unwind: bool = False,
             allow_destructive: bool = False, min_successes: int = GATE_MIN_SUCCESSES,
             opaque: bool = False) -> GateDecision:
        """May this action run UNATTENDED right now?
          (a) learned-verified: >= N successes and no failure since the last success
          (b) reversible / low-risk class
          (c) a machine-checkable postcondition exists
        Failing the gate: attempt in a safe (reversible, fully verified) form, else queue
        for the human with context. Never stalls the queue, never fakes completion."""
        s = self.step_stats(stat_key)
        verified = s["successes"] >= min_successes and s["consecutive_fail"] == 0
        if opaque or not post:
            return GateDecision("QUEUE", "no machine-checkable postcondition (opaque)", risk)
        if risk == "E2":
            if allow_destructive and verified:
                return GateDecision("EXECUTE", "destructive step explicitly allowed + learned-verified", risk)
            return GateDecision("QUEUE", "destructive/irreversible class: needs explicit allow + "
                                         f"{min_successes} verified successes", risk)
        if verified:
            return GateDecision("EXECUTE", f"learned-verified ({s['successes']} ok, 0 recent fails)", risk)
        if risk == "EU" and not has_unwind:
            return GateDecision("QUEUE", "unclassified effect, no unwind, not yet verified", risk)
        return GateDecision("SAFE_ATTEMPT", f"reversible class, verifying ({s['successes']}/{min_successes} ok)", risk)

    # ---- queue / audit / day report --------------------------------------------------------
    def audit(self, run_id: str, app_key: str, kind: str, subject: str, decision: str,
              reason: str, evidence: str = "") -> None:
        self._conn.execute(
            "INSERT INTO bm_audit(ts, run_id, app_key, kind, subject, decision, reason, evidence)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), run_id, app_key, kind, subject[:200], decision, reason[:300], evidence[:600]))
        self._conn.commit()

    def enqueue(self, run_id: str, app_key: str, task: str, reason: str,
                context: Dict[str, Any]) -> str:
        qid = "q_" + uuid.uuid4().hex[:10]
        self._conn.execute(
            "INSERT INTO bm_queue(qid, run_id, app_key, task, reason, context_json, ts) VALUES (?,?,?,?,?,?,?)",
            (qid, run_id, app_key, task, reason[:300], json.dumps(context, default=str)[:4000], time.time()))
        self._conn.commit()
        return qid

    def pending_queue(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM bm_queue WHERE status='pending' ORDER BY ts")]

    def day_report(self, run_id: str) -> Dict[str, Any]:
        """The honest end-of-day report: done / attempted-failed / escalated + evidence."""
        rows = [dict(r) for r in self._conn.execute(
            "SELECT * FROM bm_audit WHERE run_id=? AND kind='task' ORDER BY aid", (run_id,))]
        rep = {"run_id": run_id, "done": [], "attempted_failed": [], "escalated": []}
        for r in rows:
            item = {"task": r["subject"], "app": r["app_key"], "reason": r["reason"],
                    "evidence": r["evidence"]}
            bucket = {"DONE": "done", "FAILED": "attempted_failed", "ESCALATED": "escalated"}.get(r["decision"])
            if bucket:
                rep[bucket].append(item)
        rep["counts"] = {k: len(rep[k]) for k in ("done", "attempted_failed", "escalated")}
        return rep


_MODEL: Optional[BehaviorModel] = None


def get_model() -> BehaviorModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = BehaviorModel()
    return _MODEL


# ===========================================================================
# 7. Harvesters — every machine-readable source the app ships (candidates only)
# ===========================================================================

def _norm_chord(s: str) -> str:
    s = (s or "").replace("\t", " ").strip().lower()
    s = s.replace("control", "ctrl").replace("return", "enter").replace("escape", "esc")
    s = re.sub(r"\s*\+\s*", "+", s)
    return s.strip("+ ")


# -- keymap parsers: format-adaptive, registered by data shape (no app names) --------

def _parse_keymap_json(text: str) -> List[Dict[str, Any]]:
    """VS Code-style keybindings.json: [{"key": "ctrl+s", "command": "workbench.action.files.save"}]."""
    # JSON-with-comments: drop // comments that start a line or follow whitespace/[ { , — never a
    # '//' inside a string (URLs) because those are preceded by ':' or a word character
    data = json.loads(re.sub(r"(^|[\s\[\{,])//[^\n]*", r"\1", text))
    out = []
    if isinstance(data, list):
        for e in data:
            if isinstance(e, dict) and e.get("key") and e.get("command"):
                out.append({"name": e["command"], "shortcut": _norm_chord(e["key"]),
                            "verb": "key", "origin_fmt": "json-keybindings"})
    return out


_PYKM_RE = re.compile(
    r"\(\s*\"(?P<cmd>[\w\.]+)\"\s*,\s*\{(?P<props>[^}]*)\}", re.S)


def _parse_keymap_pyliteral(text: str) -> List[Dict[str, Any]]:
    """Blender-style exported keymap: ("object.mode_set", {"type": 'TAB', "value": 'PRESS', "ctrl": True}, ...)."""
    out = []
    for m in _PYKM_RE.finditer(text):
        props = m.group("props")
        t = re.search(r"[\"']type[\"']\s*:\s*[\"'](\w+)[\"']", props)
        if not t:
            continue
        mods = [k for k in ("ctrl", "shift", "alt") if re.search(rf"[\"']{k}[\"']\s*:\s*True", props)]
        key = t.group(1).lower()
        out.append({"name": m.group("cmd"), "shortcut": "+".join(mods + [key]),
                    "verb": "key", "origin_fmt": "pyliteral-keymap"})
    return out


def _parse_keymap_ini(text: str) -> List[Dict[str, Any]]:
    """name=Ctrl+S / name: Ctrl+S accelerator tables (INI/conf style)."""
    out = []
    for line in text.splitlines():
        m = re.match(r"\s*([\w\.\- ]{2,60}?)\s*[=:]\s*((?:ctrl|alt|shift|win|meta|cmd)\+[\w\+]+|f\d{1,2})\s*$",
                     line, re.I)
        if m:
            out.append({"name": m.group(1).strip(), "shortcut": _norm_chord(m.group(2)),
                        "verb": "key", "origin_fmt": "ini-accel"})
    return out


KEYMAP_PARSERS = (("json", _parse_keymap_json), ("pyliteral", _parse_keymap_pyliteral),
                  ("ini", _parse_keymap_ini))


def harvest_keymap_text(text: str) -> List[Dict[str, Any]]:
    for _name, fn in KEYMAP_PARSERS:
        try:
            got = fn(text)
        except Exception:
            got = []
        if got:
            return got
    return []


def harvest_settings_schema(text: str) -> List[Dict[str, Any]]:
    """Config/settings schemas (JSON or INI) enumerate every toggle the app has. They are
    recorded as OPAQUE settings entries: known to exist, not auto-executable (no observer)."""
    out: List[Dict[str, Any]] = []

    def _flat(prefix: str, obj: Any):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _flat(f"{prefix}.{k}" if prefix else str(k), v)
        elif isinstance(obj, bool):
            out.append({"name": f"toggle {prefix}", "verb": "setting", "opaque": True,
                        "risk": "EU", "origin_fmt": "settings-json"})
    try:
        _flat("", json.loads(text))
        return out
    except Exception:
        pass
    for line in text.splitlines():
        m = re.match(r"\s*([\w\.\-]+)\s*=\s*(true|false|0|1|yes|no|on|off)\s*$", line, re.I)
        if m:
            out.append({"name": f"toggle {m.group(1)}", "verb": "setting", "opaque": True,
                        "risk": "EU", "origin_fmt": "settings-ini"})
    return out


def harvest_cli_json(cmd: List[str], *, marker: str = "", exe: str = "",
                     timeout: float = CLI_HARVEST_TIMEOUT_S) -> Tuple[List[Dict[str, Any]], str]:
    """Run an app's own READ-ONLY command-registry dump (e.g. a headless `--python-expr` that
    prints `bpy.ops` names, an OBS WebSocket request list) and parse its JSON. Only ever
    called for packs from the local pack dir; bounded; failures are normal and reported."""
    argv = [a.replace("{exe}", exe) for a in cmd]
    if not argv or (argv[0] == "{exe}" or not argv[0]):
        return [], "skipped:no-exe"
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           creationflags=0x08000000 if _IS_WINDOWS else 0)
    except FileNotFoundError:
        return [], "skipped:exe-not-found"
    except subprocess.TimeoutExpired:
        return [], f"skipped:timeout>{timeout:.0f}s"
    except Exception as exc:
        return [], f"skipped:{type(exc).__name__}"
    blob = p.stdout or ""
    if marker:
        i = blob.find(marker)
        if i < 0:
            return [], "skipped:marker-not-in-output"
        blob = blob[i + len(marker):].splitlines()[0]
    try:
        data = json.loads(blob.strip())
    except Exception:
        return [], "skipped:output-not-json"
    out = []
    for e in data if isinstance(data, list) else []:
        if isinstance(e, str):
            e = {"name": e}
        if isinstance(e, dict) and e.get("name"):
            out.append({"name": e["name"], "goal": e.get("description") or e["name"],
                        "verb": e.get("verb", "invoke"), "shortcut": e.get("shortcut", ""),
                        "origin_fmt": "cli-json"})
    return out, "ok"


def harvest_pack_sources(model: BehaviorModel, app_name: str, sources: List[dict],
                         exe: str = "") -> Dict[str, Any]:
    """Run a pack's declared artifact sources and ingest results as catalog/distilled candidates."""
    key = _app_key(app_name)
    report: Dict[str, Any] = {"ingested": 0, "skipped": []}
    for src in sources or []:
        kind = src.get("kind")
        found: List[Dict[str, Any]] = []
        status = "ok"
        if kind == "keymap_file":
            path = os.path.expandvars(src.get("path", ""))
            if not os.path.exists(path):
                status = "skipped:file-not-found"
            else:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    found = harvest_keymap_text(fh.read())
        elif kind == "settings_file":
            path = os.path.expandvars(src.get("path", ""))
            if not os.path.exists(path):
                status = "skipped:file-not-found"
            else:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    found = harvest_settings_schema(fh.read())
        elif kind == "cli_json":
            found, status = harvest_cli_json(src.get("cmd", []), marker=src.get("marker", ""), exe=exe)
        else:
            status = f"skipped:unknown-source-kind:{kind}"
        if status != "ok":
            report["skipped"].append(f"{kind}:{status}")
        trust = "distilled" if src.get("llm_derived") else "catalog"
        for c in found:
            model.upsert_command(key, c, source=trust, origin=f"{kind}:{c.get('origin_fmt', '')}")
            report["ingested"] += 1
    return report


# -- UIA / Win32 menu crawler (E0 read-only) ------------------------------------------------

class DiscoveryBudget:
    """Complexity-adaptive crawl budget — no easy/hard app classes. A small app finishes in a
    few seconds because its discoveries flatten fast; a large one earns more time only while
    each unit of work keeps yielding NEW knowledge. Hard cap protects against a runaway.
        soft deadline  = base_s, extended by extend_s per productive unit
        stop early     = `patience` consecutive units yield nothing new
        hard deadline  = max_s (never exceeded)"""

    def __init__(self, base_s: float = CRAWL_BUDGET_S, extend_s: float = 4.0,
                 max_s: float = CRAWL_MAX_S, patience: int = 3):
        self.t0 = time.time()
        self.soft = base_s
        self.extend_s = extend_s
        self.max_s = max_s
        self.patience = patience
        self.dry = 0
        self.units = 0
        self.yield_total = 0

    def elapsed(self) -> float:
        return time.time() - self.t0

    def credit(self, new_items: int) -> None:
        """Report one unit of work (a menu, a dialog) and how many NEW items it yielded."""
        self.units += 1
        self.yield_total += new_items
        if new_items > 0:
            self.dry = 0
            self.soft = min(self.max_s, max(self.soft, self.elapsed() + self.extend_s))
        else:
            self.dry += 1

    def extend(self, new_items: int) -> None:
        """Incremental yield inside a long unit (a deep submenu chain): any node that finds
        something pushes the soft deadline out right away, without counting a finished unit."""
        if new_items > 0:
            self.soft = min(self.max_s, max(self.soft, self.elapsed() + self.extend_s))

    def reason_to_stop(self) -> str:
        if self.elapsed() >= self.max_s:
            return "hard-cap"
        if self.elapsed() >= self.soft:
            return "budget"
        if self.dry >= self.patience:
            return "flattened"
        return ""


@dataclass
class CrawlReport:
    method: str = ""
    commands: List[Dict[str, Any]] = field(default_factory=list)
    nodes_seen: int = 0
    elapsed_s: float = 0.0
    stopped: str = ""                 # "" | budget | node-cap
    actuations: int = 0               # E0 contract: MUST stay 0 for win32; expand/collapse only for uia
    expand_collapse: int = 0
    skipped: List[str] = field(default_factory=list)


def _clean_label(s: str) -> Tuple[str, str]:
    """('&Save As…\\tCtrl+Shift+S') -> ('Save As…', 'ctrl+shift+s'); also returns accel char via &."""
    label, _, accel = (s or "").partition("\t")
    label = label.replace("&", "").strip()
    return label, _norm_chord(accel)


def crawl_win32_menu(hwnd: int, *, budget_s: float = CRAWL_BUDGET_S) -> CrawlReport:
    """E0: read the classic Win32 HMENU tree (labels, accelerators, command IDs, enabled state).
    Pure reads — GetMenu*/GetMenuString — zero actuation, no popup is ever opened."""
    rep = CrawlReport(method="win32-hmenu")
    t0 = time.time()
    u32 = ctypes.windll.user32
    u32.GetMenu.restype = ctypes.c_void_p
    u32.GetSubMenu.restype = ctypes.c_void_p
    hmenu = u32.GetMenu(hwnd)
    if not hmenu:
        rep.skipped.append("no-classic-menu-bar")
        return rep

    def _walk(hm, path: List[str], depth: int):
        if depth > 5:
            return
        n = u32.GetMenuItemCount(ctypes.c_void_p(hm))
        for i in range(max(n, 0)):
            if time.time() - t0 > budget_s:
                rep.stopped = "budget"
                return
            buf = ctypes.create_unicode_buffer(256)
            u32.GetMenuStringW(ctypes.c_void_p(hm), i, buf, 255, 0x400)       # MF_BYPOSITION
            rep.nodes_seen += 1
            label, accel = _clean_label(buf.value)
            if not label:
                continue                                                      # separator
            sub = u32.GetSubMenu(ctypes.c_void_p(hm), i)
            if sub:
                _walk(sub, path + [label], depth + 1)
                continue
            mid = u32.GetMenuItemID(ctypes.c_void_p(hm), i)
            state = u32.GetMenuState(ctypes.c_void_p(hm), i, 0x400)
            if state != 0xFFFFFFFF and (state & 0x3):                          # grayed / disabled
                continue
            mp = " > ".join(path + [label])
            rep.commands.append({"name": label, "goal": label, "menu_path": mp, "shortcut": accel,
                                 "verb": "wm_command", "menu_id": int(mid) if mid != 0xFFFFFFFF else None,
                                 "origin_fmt": "win32-hmenu"})

    _walk(hmenu, [], 0)
    rep.elapsed_s = round(time.time() - t0, 3)
    return rep


def _uia_item_info(c) -> Dict[str, Any]:
    def g(attr):
        try:
            return getattr(c, attr, "") or ""
        except Exception:
            return ""
    label, accel_in_name = _clean_label(g("Name"))
    accel = _norm_chord(g("AcceleratorKey")) or accel_in_name
    return {"name": label, "shortcut": accel, "automation_id": g("AutomationId"),
            "help": g("HelpText"), "access_key": g("AccessKey"),
            "enabled": bool(getattr(c, "IsEnabled", True))}


def _menu_items_under(ctrl, limit: int = 400) -> List[Any]:
    out: List[Any] = []

    def _v(c, d):
        if d > 10 or len(out) >= limit:
            return
        try:
            for ch in c.GetChildren():
                if (ch.ControlTypeName or "") == "MenuItemControl":
                    out.append(ch)
                _v(ch, d + 1)
        except Exception:
            return
    _v(ctrl, 0)
    return out


def _all_roots(hwnd: int):
    """Main window + this app's popup hosts (menus/flyouts often live in a separate window)."""
    import uiautomation as auto
    from core_organs import headless_input as hin
    roots = [auto.ControlFromHandle(hwnd)]
    for w in _popups(hwnd)[:8]:
        try:
            roots.append(auto.ControlFromHandle(w))
        except Exception:
            continue
    return [r for r in roots if r is not None]


def _cheap_key(c) -> str:
    try:
        r = c.BoundingRectangle
        name = (c.Name or "").replace("&", "").strip()
        return f"{name}|{r.left},{r.top}" if name else ""
    except Exception:
        return ""


def _item_key(info: Dict[str, Any], c) -> str:
    try:
        r = c.BoundingRectangle
        return f"{info['name']}|{r.left},{r.top}"
    except Exception:
        return info["name"]


def win32_window_controls(hwnd: int, limit: int = 400) -> List[Dict[str, Any]]:
    """Controls of a classic Win32 dialog (#32770 and friends) WITHOUT UIA: EnumChildWindows +
    text/class/rect. Instant and incapable of hanging on a slow accessibility provider (a UIA
    snapshot of Paint's Page Setup took 65 s). Returns [{'name','class','rect'}]."""
    out: List[Dict[str, Any]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if len(out) >= limit:
            return False
        try:
            n = ctypes.windll.user32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(max(n, 0) + 2)
            ctypes.windll.user32.GetWindowTextW(h, buf, n + 2)
            c = ctypes.create_unicode_buffer(128)
            ctypes.windll.user32.GetClassNameW(h, c, 128)
            r = wt.RECT()
            ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r))
            text = buf.value.replace("&", "").strip()
            if text or c.value in ("Edit", "ComboBox", "ComboBoxEx32", "Button", "ListBox", "SysListView32",
                                   "SysTreeView32", "msctls_trackbar32"):
                out.append({"name": text, "class": c.value, "rect": (r.left, r.top, r.right, r.bottom)})
        except Exception:
            pass
        return True
    try:
        ctypes.windll.user32.EnumChildWindows(hwnd, cb, 0)
    except Exception:
        pass
    return out


def _open_popups(hwnd: int) -> List[int]:
    """Popup windows of the app that are actually OPEN: a classic menu / dialog, or a popup host
    whose UIA subtree contains controls. WinUI keeps EMPTY popup-host windows alive after a flyout
    or tooltip closes; those are not open UI and must not read as 'a menu was left open'."""
    try:
        import uiautomation as auto
        from core_organs import headless_input as hin
    except Exception:
        return []
    out = []
    for w in _popups(hwnd):
        cls = _win_class(w)
        if cls in ("#32768", "#32770"):
            out.append(w)
            continue
        try:
            if auto.ControlFromHandle(w).GetChildren():
                out.append(w)
        except Exception:
            out.append(w)                    # cannot tell: assume open (fail safe)
    return out


def _focus_menu_container(hwnd: int):
    """Some UI frameworks (WinUI XAML islands) keep an open flyout's items OUT of the window's
    enumerable tree, but the UIA focus moves into the flyout. The focused item's parent is the
    menu container holding all its siblings. Pure UIA read, no input."""
    try:
        import uiautomation as auto
        from core_organs import headless_input as hin
        fc = auto.GetFocusedControl()
        if fc is None or fc.ProcessId != hin.window_pid(hwnd):
            return None
        if (fc.ControlTypeName or "") not in ("MenuItemControl", "ListItemControl", "MenuControl"):
            return None
        return fc.GetParentControl()
    except Exception:
        return None


def _popup_roots(hwnd: int):
    """Where an opened menu's items can live: this app's popup-host windows, plus the focus
    container (see above). Small trees => fast."""
    import uiautomation as auto
    from core_organs import headless_input as hin
    out = []
    for w in _popups(hwnd)[:8]:
        try:
            out.append(auto.ControlFromHandle(w))
        except Exception:
            continue
    fc = _focus_menu_container(hwnd)
    if fc is not None:
        out.append(fc)
    return [r for r in out if r is not None]


def crawl_menus_uia_e0(hwnd: int, *, budget: Optional[DiscoveryBudget] = None,
                       max_items: int = 400, max_depth: int = 4) -> CrawlReport:
    """E0 for apps whose menus are UIA-only (WinUI/Electron/Office): ExpandCollapse every menu node,
    harvest labels/accelerators/AutomationIds/help text, collapse again. No Invoke, no clicks.

    FAST PATH: every look at the UI is ONE bulk UIA snapshot (fast_uia) instead of thousands of tiny
    per-node COM calls, so the only real time left is the app's own Expand latency. If snapshots are
    unavailable the per-node implementation below runs instead (same results, slower).

    Robustness (flyouts light-dismiss on focus loss; the app may be busy):
      * a verified clean slate between top-level menus (Escape first, pattern Collapse as fallback)
      * Expand retried once; a menu that still yields nothing gets a bounded second pass
      * every menu that could not be opened is listed in `skipped` — never dropped silently"""
    try:
        from core_organs import fast_uia as _fu
        _fu.wait_ready(hwnd, timeout_s=10.0)                 # never crawl a tree that is still populating
    except Exception:
        pass
    from core_organs import fast_uia
    if fast_uia.snapshot(hwnd, max_nodes=50) is None:
        return _crawl_menus_uia_e0_slow(hwnd, budget=budget, max_items=max_items, max_depth=max_depth)
    rep = CrawlReport(method="uia-expandcollapse-fast")
    budget = budget or DiscoveryBudget()
    from core_organs import headless_input as hin
    seen_cmds: set = set()
    cold = {"first": True}

    def _key(n) -> str:
        return f"{n.name.replace('&', '').strip()}|{n.rect[0]},{n.rect[1]}" if n.name else ""

    def _menu_nodes(snap) -> List[Any]:
        return [n for n in (snap or []) if n.ctype == "MenuItemControl" and n.name]

    def _roots() -> List[Any]:
        """Raw elements to search: popup hosts + the focus container (flyouts live there)."""
        out = []
        for c in _popup_roots(hwnd):
            try:
                out.append(c.Element)
            except Exception:
                continue
        return out

    def _open_menu_nodes() -> List[Any]:
        found = []
        for el in _roots():
            found += _menu_nodes(fast_uia.snapshot_element(el))
        return found

    def _is_open() -> bool:
        return bool(_open_popups(hwnd))

    def _clean_slate(tries: int = 3) -> bool:
        """Escape the open flyout chain (fast), verify, fall back to pattern Collapse."""
        for t in range(tries):
            if not _is_open() and _focus_menu_container(hwnd) is None:
                return True
            try:
                for w in _open_popups(hwnd):
                    hin.post_key_combo(w, "escape")
                hin.post_key_combo(hwnd, "escape")
            except Exception:
                pass
            time.sleep(0.08)
            if _is_open():
                snap = fast_uia.snapshot(hwnd)
                for n in reversed([x for x in (snap or []) if x.ctype == "MenuItemControl" and x.expand_state == 1]):
                    try:
                        n.ctrl.GetExpandCollapsePattern().Collapse()
                        rep.expand_collapse += 1
                    except Exception:
                        continue
        return not _is_open()

    def _collect_new(known: set, main_nodes) -> List[Any]:
        """Poll until the opened menu's item set stops growing. Long wait only while NOTHING has
        appeared yet (a cold first open), and after 0.8 s the search widens to the whole window."""
        found: List[Any] = []
        last_n, stable = -1, 0
        t_start = time.time()
        while True:
            waited = time.time() - t_start
            limit_empty = 3.0 if cold["first"] else 1.2
            if (found and stable >= 1) or waited > (0.6 if found else limit_empty):
                break
            _keep_hidden(hwnd)
            nodes = _open_menu_nodes()
            if not nodes and waited > 0.8:
                nodes = _menu_nodes(fast_uia.snapshot(hwnd))
            seen_keys: set = set()
            found = []
            for n in nodes:
                k = _key(n)
                if k and k not in known and k not in seen_keys:
                    seen_keys.add(k)
                    found.append(n)
            stable = stable + 1 if (found and len(found) == last_n) else 0
            last_n = len(found)
            if not (found and stable >= 1):
                time.sleep(0.03)
        return found

    def _expand_and_collect(node, path: List[str], depth: int, known: set) -> int:
        if budget.reason_to_stop() in ("hard-cap", "budget") or len(rep.commands) >= max_items:
            rep.stopped = rep.stopped or budget.reason_to_stop() or "node-cap"
            return 0
        label = " > ".join(path)
        children: List[Any] = []
        opened = False
        for attempt in (1, 2):
            try:
                node.ctrl.GetExpandCollapsePattern().Expand()
                rep.expand_collapse += 1
                opened = True
            except Exception:
                opened = False
            if opened:
                children = _collect_new(known, None)
                if children:
                    break
            if attempt == 1:
                if depth == 1:
                    _clean_slate(2)
                time.sleep(0.2)
        if not opened:
            rep.skipped.append(f"expand-failed:{label}")
            return 0
        cold["first"] = False
        if not children:
            rep.skipped.append(f"empty-menu:{label}")
            return 0
        budget.extend(len(children))
        for ch in children:
            known.add(_key(ch))
        gained = 0
        for ch in children:
            rep.nodes_seen += 1
            mp = " > ".join(path + [ch.name.replace("&", "").strip()])
            if "expand" in ch.pats and depth < max_depth:
                gained += _expand_and_collect(ch, path + [ch.name.replace("&", "").strip()], depth + 1, known)
            elif ch.enabled and mp not in seen_cmds:
                seen_cmds.add(mp)
                gained += 1
                budget.extend(1)
                lab, acc = _clean_label(ch.name)
                accel = _norm_chord(ch.accel) or acc
                rep.commands.append({"name": lab, "goal": lab, "menu_path": mp, "shortcut": accel,
                                     "automation_id": ch.aid, "verb": "invoke", "origin_fmt": "uia-menu",
                                     "evidence": (f"help={ch.help}" if ch.help else "")})
        return gained

    try:
        top_nodes: List[Any] = []
        delay, ready_by = 0.3, time.time() + 12.0
        while True:                                   # readiness: menu bar may appear late
            snap = fast_uia.snapshot(hwnd)
            top_nodes = [n for n in _menu_nodes(snap) if n.name != "System"]   # the title-bar system menu is not app UI
            if top_nodes or time.time() >= ready_by:
                break
            if snap and len(snap) >= 60:                # a populated tree with no menu bar (ribbon / toolbar app):
                ready_by = min(ready_by, time.time() + 1.5)   # do not wait 12 s for a menu bar that does not exist
            time.sleep(delay)
            delay = min(delay * 1.5, 1.5)
        if not top_nodes:
            rep.skipped.append("no-menu-items-exposed-within-12s")
        known_all = {_key(n) for n in top_nodes}
        _clean_slate(1)
        budget.soft = max(budget.soft, budget.elapsed() + 6.0 * len(top_nodes))

        def _explore(top) -> int:
            try:
                g = _expand_and_collect(top, [top.name.replace("&", "").strip()], 1, known_all)
            except Exception as exc:                  # COM hiccup on one menu: record, keep going
                rep.skipped.append(f"error:{top.name}:{type(exc).__name__}")
                g = 0
            _clean_slate(2)
            return g

        for top in top_nodes:
            budget.credit(_explore(top))
            why = budget.reason_to_stop()
            if why in ("hard-cap", "budget"):
                rep.stopped = why
                break
        have = {c["menu_path"].split(" > ")[0] for c in rep.commands}
        missing = [t for t in top_nodes if t.name.replace("&", "").strip() not in have and t.name != "System"]
        if missing and budget.reason_to_stop() != "hard-cap":
            budget.soft = max(budget.soft, budget.elapsed() + 6.0)
            nm = {t.name.replace("&", "").strip() for t in missing}
            rep.skipped = [x for x in rep.skipped if not any(x.endswith(":" + m) for m in nm)]
            for top in missing:
                if budget.reason_to_stop() == "hard-cap":
                    break
                budget.extend(_explore(top))
        if rep.stopped == "" and budget.reason_to_stop() in ("hard-cap", "budget"):
            rep.stopped = budget.reason_to_stop()
    except Exception as exc:
        rep.skipped.append(f"uia-error:{type(exc).__name__}")
    finally:
        try:
            if not _clean_slate(3):
                rep.skipped.append("cleanup:popup-still-open")
        except Exception:
            pass
    rep.elapsed_s = round(budget.elapsed(), 3)
    return rep


def _crawl_menus_uia_e0_slow(hwnd: int, *, budget: Optional[DiscoveryBudget] = None,
                       max_items: int = 400, max_depth: int = 4) -> CrawlReport:
    """E0 for apps whose menus are UIA-only (WinUI/Electron): ExpandCollapse every menu node,
    harvest labels/accelerators/AutomationIds/help text, then COLLAPSE it again. No Invoke,
    no clicks — a pattern call that cannot trigger a command.

    Robustness (the machine may be in use while this runs; flyouts light-dismiss on focus loss):
      * a verified clean slate (everything collapsed, no popup open) before each top-level menu
      * Expand retried once; a menu that still yields nothing is retried in a bounded second pass
      * every menu that could not be opened is listed in `skipped` — never dropped silently
      * cleanup collapses every expanded node, Escapes, and verifies no popup is left open"""
    rep = CrawlReport(method="uia-expandcollapse")
    budget = budget or DiscoveryBudget()
    try:
        import uiautomation as auto
        from core_organs import headless_input as hin
    except Exception:
        rep.skipped.append("uiautomation-missing")
        return rep
    seen_cmds: set = set()
    cold = {"first": True}                      # only the very first open may be slow (cold flyout)

    def _expanded_items() -> List[Any]:
        out = []
        try:
            roots = _popup_roots(hwnd) + [auto.ControlFromHandle(hwnd)]
            for r in roots:
                for it in _menu_items_under(r):
                    try:
                        pat = it.GetExpandCollapsePattern()
                        if pat is not None and int(pat.ExpandCollapseState) != 0:
                            out.append(it)
                    except Exception:
                        continue
        except Exception:
            pass
        return out

    def _clean_slate(tries: int = 3) -> bool:
        """Collapse every expanded node (deepest first), Escape, and verify nothing is open."""
        for _ in range(tries):
            opened = _expanded_items()
            for it in reversed(opened):
                try:
                    it.GetExpandCollapsePattern().Collapse()
                    rep.expand_collapse += 1
                except Exception:
                    continue
            try:
                popups = _open_popups(hwnd)
                if popups or _focus_menu_container(hwnd) is not None:
                    for w in popups:
                        hin.post_key_combo(w, "escape")
                    hin.post_key_combo(hwnd, "escape")
                    time.sleep(0.25)
            except Exception:
                pass
            if not _expanded_items() and not _open_popups(hwnd):
                return True
        return not _open_popups(hwnd)

    def _collect_new(known: set, main_root) -> List[Tuple[Dict[str, Any], Any]]:
        """Poll until the opened menu's item set stops growing. A COLD first open can take well over
        a second to materialise, so the wait is long only while NOTHING has appeared yet (bounded),
        and after 0.8 s the search widens from popup hosts/focus container to the main tree."""
        found: List[Tuple[Dict[str, Any], Any]] = []
        last_n, stable = -1, 0
        t_start = time.time()
        while True:
            waited = time.time() - t_start
            limit_empty = 3.0 if cold["first"] else 1.2
            if (found and stable >= 1) or waited > (1.0 if found else limit_empty):
                break
            found = []
            _keep_hidden(hwnd)
            roots = _popup_roots(hwnd)
            if not roots or waited > 0.8:
                roots = roots + [main_root]
            seen_keys: set = set()
            for root in roots:
                for it in _menu_items_under(root):
                    k = _cheap_key(it)                       # 2 COM reads; full info only for NEW items
                    if k and k not in known and k not in seen_keys:
                        seen_keys.add(k)
                        info = _uia_item_info(it)
                        if info["name"]:
                            found.append((info, it))
            stable = stable + 1 if (found and len(found) == last_n) else 0
            last_n = len(found)
            if not (found and stable >= 1):
                time.sleep(0.05)
        return found

    def _expand_and_collect(c, main_root, path: List[str], depth: int, known: set) -> int:
        """Returns the number of NEW leaf commands discovered under this node."""
        if budget.reason_to_stop() in ("hard-cap", "budget") or len(rep.commands) >= max_items:
            rep.stopped = rep.stopped or budget.reason_to_stop() or "node-cap"
            return 0
        try:
            pat = c.GetExpandCollapsePattern()
        except Exception:
            pat = None
        if pat is None:
            return 0
        label = " > ".join(path)
        children: List[Tuple[Dict[str, Any], Any]] = []
        opened = False
        for attempt in (1, 2):                    # a cold/loaded app can drop the first Expand
            try:
                pat.Expand()
                rep.expand_collapse += 1
                opened = True
            except Exception:
                opened = False
            if opened:
                children = _collect_new(known, main_root)
                if children:
                    break
            if attempt == 1:
                if depth == 1:
                    _clean_slate(2)               # reset before retrying a top-level menu
                time.sleep(0.3)
        if not opened:
            rep.skipped.append(f"expand-failed:{label}")      # never drop a menu silently
            return 0
        cold["first"] = False
        if not children:
            rep.skipped.append(f"empty-menu:{label}")
            return 0
        budget.extend(len(children))
        for info, it in children:
            known.add(_cheap_key(it) or _item_key(info, it))
        gained = 0
        for info, it in children:
            rep.nodes_seen += 1
            mp = " > ".join(path + [info["name"]])
            try:
                has_sub = it.GetExpandCollapsePattern() is not None
            except Exception:
                has_sub = False
            if has_sub and depth < max_depth:
                gained += _expand_and_collect(it, main_root, path + [info["name"]], depth + 1, known)
            elif info["enabled"] and mp not in seen_cmds:
                seen_cmds.add(mp)
                gained += 1
                budget.extend(1)
                rep.commands.append({"name": info["name"], "goal": info["name"], "menu_path": mp,
                                     "shortcut": info["shortcut"], "automation_id": info["automation_id"],
                                     "verb": "invoke", "origin_fmt": "uia-menu",
                                     "evidence": (f"help={info['help']}" if info["help"] else "")})
        return gained

    try:
        # readiness: a booting / loaded app exposes its menu bar late. Poll (bounded, growing waits)
        # instead of concluding "this app has no menus".
        top_items: List[Any] = []
        root = None
        delay, ready_by = 0.3, time.time() + 12.0
        while True:
            try:
                root = auto.ControlFromHandle(hwnd)
                top_items = [t for t in _menu_items_under(root) if (t.Name or "").strip()]
            except Exception:
                top_items = []
            if top_items or time.time() >= ready_by:
                break
            time.sleep(delay)
            delay = min(delay * 1.5, 1.5)
        if not top_items:
            rep.skipped.append("no-menu-items-exposed-within-12s")
        baseline = {_cheap_key(c) for c in top_items}
        known_all = set(baseline)
        _clean_slate(1)
        # the frontier size is observed structure, not an app label: give each top-level menu
        # room to be explored before the soft deadline can fire (yield then extends further)
        budget.soft = max(budget.soft, budget.elapsed() + 7.0 * len(top_items))

        def _explore(top) -> int:
            info = _uia_item_info(top)
            if not info["name"]:
                return 0
            gained = _expand_and_collect(top, root, [info["name"]], 1, known_all)
            _clean_slate(2)                       # clean slate before the next top-level menu
            return gained

        def _safe_explore(top) -> int:
            try:
                return _explore(top)
            except Exception as exc:              # COM hiccup on one menu: record it, keep going
                try:
                    nm = _uia_item_info(top)["name"]
                except Exception:
                    nm = "?"
                rep.skipped.append(f"error:{nm}:{type(exc).__name__}")
                try:
                    _clean_slate(2)
                except Exception:
                    pass
                return 0

        for top in top_items:
            budget.credit(_safe_explore(top))     # adaptive: yield extends, flatline stops
            why = budget.reason_to_stop()
            if why in ("hard-cap", "budget"):
                rep.stopped = why
                break
        # second pass: any top-level menu that produced nothing gets one more bounded try
        have = {c["menu_path"].split(" > ")[0] for c in rep.commands}
        missing = [t for t in top_items if (t.Name or "").strip() and _uia_item_info(t)["name"] not in have
                   and _uia_item_info(t)["name"] != "System"]
        if missing and budget.reason_to_stop() not in ("hard-cap",):
            budget.soft = max(budget.soft, budget.elapsed() + 6.0)
            rep.skipped = [x for x in rep.skipped if not any(x.endswith(":" + _uia_item_info(t)["name"])
                                                             for t in missing)]
            for top in missing:
                if budget.reason_to_stop() == "hard-cap":
                    break
                budget.extend(_safe_explore(top))
        if rep.stopped == "" and budget.reason_to_stop() in ("hard-cap", "budget"):
            rep.stopped = budget.reason_to_stop()
    except Exception as exc:
        rep.skipped.append(f"uia-error:{type(exc).__name__}")
    finally:
        try:
            if not _clean_slate(3):
                rep.skipped.append("cleanup:popup-still-open")
        except Exception:
            pass
    rep.elapsed_s = round(budget.elapsed(), 3)
    return rep


def crawl_e0(model: BehaviorModel, app_name: str, hwnd: int, *,
             budget: Optional[DiscoveryBudget] = None) -> Dict[str, Any]:
    with _bg(hwnd) as bg:
        out = _crawl_e0_impl(model, app_name, hwnd, budget=budget)
        out["window_mode"] = getattr(bg, "mode", "") or "visible"
        return out


def _crawl_e0_impl(model: BehaviorModel, app_name: str, hwnd: int, *,
                   budget: Optional[DiscoveryBudget] = None) -> Dict[str, Any]:
    """E0 acquisition for one live window, same pipeline for every app: Win32 HMENU read first
    (zero actuation, instant), then the UIA ExpandCollapse crawl. Time spent adapts to what the
    app actually exposes (DiscoveryBudget). Everything lands as `catalog` (unverified) —
    promotion to `learned` is E1 / a real verified run's job."""
    key = _app_key(app_name)
    exe = _exe_of_hwnd(hwnd)
    model.check_version(key, app_version_hash(exe))
    budget = budget or DiscoveryBudget()
    t0 = time.time()
    reports: List[CrawlReport] = []
    try:
        reports.append(crawl_win32_menu(hwnd))
    except Exception as exc:
        r = CrawlReport(method="win32-hmenu")
        r.skipped.append(f"error:{type(exc).__name__}")
        reports.append(r)
    budget.extend(len(reports[0].commands))          # a Win32 read is not a unit of exploration
    reports.append(crawl_menus_uia_e0(hwnd, budget=budget))
    ingested = 0
    seen: set = set()
    for rep in reports:
        for c in rep.commands:
            ident = (_norm(c["menu_path"]), c.get("shortcut", ""))
            if ident in seen:
                continue
            seen.add(ident)
            model.upsert_command(key, c, source="catalog", origin=f"e0:{rep.method}",
                                 evidence=c.get("evidence", ""))
            ingested += 1
    try:
        model.record_step_outcome(f"{key}:e0_done:{app_version_hash(exe)}", "PASS")   # E0 RAN for this version (even if it found nothing)
    except Exception:
        pass
    return {"app_key": key, "ingested": ingested, "elapsed_s": round(time.time() - t0, 2),
            "units": budget.units, "stopped": budget.reason_to_stop() or "complete",
            "methods": [{"method": r.method, "found": len(r.commands), "nodes": r.nodes_seen,
                         "stopped": r.stopped, "expand_collapse": r.expand_collapse,
                         "skipped": r.skipped} for r in reports]}


# ===========================================================================
# 8. Effector ladder — "which way does THIS app accept input" (learned)
# ===========================================================================

def _find_elements(grounding, hwnd: int, name: str, role: str = "") -> List[Any]:
    """Name match across the app window AND its popup hosts, exact before substring."""
    from core_organs import desktop_grounding as dg
    from core_organs import headless_input as hin
    want = _norm(name.replace("&", ""))
    pool = list(grounding._walk_uia(hwnd, max_depth=14, max_nodes=700) if dg.HAS_UIA
                else grounding._walk_win32(hwnd))
    for w in _popups(hwnd)[:8]:
        try:
            pool += grounding._walk_uia(w, max_depth=8, max_nodes=250)
        except Exception:
            continue
    exact = [e for e in pool if _norm((e.name or "").replace("&", "")) == want]
    part = [e for e in pool if want and want in _norm((e.name or "").replace("&", "")) and e not in exact]
    out = exact + part
    if role:
        out = sorted(out, key=lambda e: 0 if role in (e.role or "") else 1)
    return out


def _on_uia_thread(fn: Callable[[], Any], timeout: float = 20.0) -> Any:
    """Run a UIA action on the loop's dedicated, properly initialised COM thread (the same one
    every other UIA action uses): Invoke silently degrades on a differently-initialised apartment."""
    from core_organs import desktop_grounding as dg
    if dg._UIA_EXEC is None:
        from concurrent.futures import ThreadPoolExecutor
        dg._UIA_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia-act",
                                          initializer=dg._uia_thread_init)
    return dg._UIA_EXEC.submit(fn).result(timeout=timeout)


def open_menu_path(hwnd: int, path: str, *, settle_s: float = 1.2) -> Tuple[bool, str]:
    """Invoke a menu command by its path ('File > Save as') with UIA patterns only: ExpandCollapse
    on each parent, Invoke on the leaf. Works for apps whose menus are UIA-only and ignore posted
    keystrokes. Menu items are found in the window, its popup hosts, or the focus container."""
    parts = [p.strip() for p in (path or "").split(">") if p.strip()]
    if not parts:
        return False, "empty menu path"

    state: Dict[str, Any] = {"res": None, "invoking": False}

    def _run() -> Tuple[bool, str]:
        import uiautomation as auto
        root = auto.ControlFromHandle(hwnd)
        try:                                              # start from a clean slate: a leftover open menu/flyout makes
            if _open_popups(hwnd):                        # the first Expand toggle it shut instead of opening it
                from core_organs import headless_input as _hin
                for w in _open_popups(hwnd):
                    _hin.post_key_combo(w, "escape")
                _hin.post_key_combo(hwnd, "escape")
                time.sleep(0.25)
        except Exception:
            pass

        def _find(label: str, roots) -> Any:
            want = _norm(label.replace("&", ""))
            for r in roots:
                for it in _menu_items_under(r):
                    if _norm(_clean_label(it.Name or "")[0]) == want:
                        return it
            return None

        for i, part in enumerate(parts):
            it, end = None, time.time() + settle_s
            while it is None and time.time() < end:
                it = _find(part, [root] if i == 0 else (_popup_roots(hwnd) or [root]))
                if it is None:
                    time.sleep(0.08)
            if it is None:
                return False, f"menu item '{part}' not found"
            if i < len(parts) - 1:
                try:
                    it.GetExpandCollapsePattern().Expand()
                except Exception:
                    try:
                        it.GetInvokePattern().Invoke()
                    except Exception as exc:
                        return False, f"cannot open '{part}': {type(exc).__name__}"
                time.sleep(0.25)
            else:
                for getter, call in (("GetInvokePattern", "Invoke"), ("GetSelectionItemPattern", "Select"),
                                     ("GetTogglePattern", "Toggle")):
                    try:
                        state["invoking"] = True           # from here a blocking call means "modal opened"
                        getattr(getattr(it, getter)(), call)()
                        return True, f"uia-{call.lower()} '{path}'"
                    except Exception:
                        continue
                return False, f"'{part}' accepts no invoke-style pattern"
        return False, "unreachable"

    def _worker() -> None:
        try:
            import uiautomation as auto
            with auto.UIAutomationInitializerInThread():       # same COM init the loop's UIA thread uses
                res = _run()
                if not res[0] and "not found" in res[1] and not state["invoking"]:
                    time.sleep(0.4)                            # transient (menu still opening / closing): one more try
                    res = _run()
                state["res"] = res
        except Exception as exc:
            state["res"] = (False, f"{type(exc).__name__}: {str(exc)[:60]}")

    # Invoke on a command that opens a MODAL dialog does not return until the dialog closes (Paint's
    # Page Setup), so the call runs on its own daemon thread: if the leaf Invoke has started and does
    # not return within a moment, the command was dispatched and a modal surface is now open.
    import threading
    th = threading.Thread(target=_worker, daemon=True, name="menu-path")
    th.start()
    deadline, inv_since = time.time() + 25.0, None
    while th.is_alive() and time.time() < deadline:
        th.join(0.1)
        if state["invoking"]:
            inv_since = inv_since or time.time()
            if time.time() - inv_since > 1.5:
                break
    if state["res"] is not None:
        return state["res"]
    if state["invoking"]:
        return True, f"uia-invoke '{path}' (dispatched; the call blocks because the command opened a modal surface)"
    return False, "timeout before reaching the menu leaf"


def invoke_node_safely(node, wait_s: float = 1.5) -> Tuple[bool, str]:
    """Invoke a snapshot node's control without ever hanging on a modal: the call runs on its own
    thread; if it has not returned after `wait_s` the command was dispatched (and opened something)."""
    import threading
    state = {"res": None}

    def _w():
        try:
            import uiautomation as auto
            with auto.UIAutomationInitializerInThread():
                ctrl = node.ctrl
                for getter, call in (("GetInvokePattern", "Invoke"), ("GetSelectionItemPattern", "Select"),
                                     ("GetTogglePattern", "Toggle")):
                    try:
                        getattr(getattr(ctrl, getter)(), call)()
                        state["res"] = (True, f"uia-{call.lower()}")
                        return
                    except Exception:
                        continue
                state["res"] = (False, "no invoke-style pattern")
        except Exception as exc:
            state["res"] = (False, f"{type(exc).__name__}")
    th = threading.Thread(target=_w, daemon=True)
    th.start()
    th.join(wait_s)
    return state["res"] or (True, "dispatched (call still running: a modal surface opened)")


class EffectorLadder:
    """Maps a verb to whatever the app accepts: UIA pattern -> posted window messages ->
    WM_COMMAND (Win32 menu id) -> key chord. Records which one worked — that IS the
    knowledge ('this app is keyboard-driven', 'that one exposes UIA invoke')."""

    DEFAULTS = {"invoke": ["snapshot_invoke", "uia", "wm_command", "postmessage", "layout_click", "key"],
                "type": ["uia", "postmessage"],
                "key": ["key", "menu_command"],
                "menu": ["menu_command", "wm_command", "key"]}

    def __init__(self, model: BehaviorModel, grounding=None, loop=None):
        from core_organs import desktop_grounding as dg
        self._crawled: set = set()
        self.model = model
        self.g = grounding or dg.DesktopGrounding()
        self.loop = loop

    def perform(self, app_key: str, hwnd: int, action: Dict[str, Any],
                avoid: Optional[set] = None) -> Tuple[bool, str, str]:
        """Returns (delivered, effector_used, note). `avoid` = effectors already tried without
        an observable effect on an earlier attempt (rotation between retries)."""
        from core_organs import desktop_grounding as dg
        from core_organs import headless_input as hin
        verb = action.get("verb", "")
        avoid = avoid or set()
        self._cur_app = app_key
        if action.get("expect_popup"):             # this step WANTS a dialog: organ_29 must not "fix" it
            try:
                from core_organs import popup_mode
                popup_mode.expect_popup(*[str(x) for x in (action["expect_popup"] if isinstance(
                    action["expect_popup"], list) else [action["expect_popup"]])])
            except Exception:
                pass
        if verb == "wait":
            time.sleep(min(float(action.get("seconds", 0.5)), 3.0))
            return True, "wait", "waited"
        if verb == "file_dialog":
            if self.loop is None:
                return False, "file_dialog", "no loop available"
            from core_organs import fast_uia
            end = time.time() + 8.0                            # wait (bounded) until the dialog really has its filename box
            while time.time() < end:
                ready = False
                for w in _popups(hwnd)[:4]:
                    if _win_class(w) == "#32770":
                        kids = win32_window_controls(w)
                        ready = any(k["class"] in ("Edit", "ComboBox", "ComboBoxEx32") for k in kids)
                        if not ready:
                            snap = fast_uia.snapshot(w, timeout_ms=3000) or []
                            ready = any(n.ctype == "EditControl" for n in snap)
                    if ready:
                        break
                if ready:
                    break
                time.sleep(0.3)
            ok, note = self.loop.handle_native_file_dialog(str(action.get("path", "")))
            return bool(ok), "file_dialog", note
        order = [e for e in self.model.effector_order(app_key, verb, self.DEFAULTS.get(verb, ["key"]))
                 if e not in avoid] or list(self.DEFAULTS.get(verb, ["key"]))
        trail: List[str] = []
        for eff in order:
            ok, note = self._try(eff, verb, action, hwnd, dg, hin)
            if ok:
                return True, eff, note
            trail.append(f"{eff}: {note}")
        return False, "none", " | ".join(trail) or "no-effector-applicable"     # the WHOLE trail, not just the last miss

    def _command_for_chord(self, app_key: str, hwnd: int, chord: str) -> Optional[Dict[str, Any]]:
        """Knowledge lookup: which known menu command is bound to this chord? If nothing is known
        about the app yet, run the read-only E0 crawl once (this is knowledge doing real work)."""
        want = _norm_chord(chord)

        def _lookup():
            return next((c for c in self.model.commands(app_key, limit=5000)
                         if c["shortcut"] and _norm_chord(c["shortcut"]) == want and c["menu_path"]
                         and c["risk"] != "E2"), None)
        cmd = _lookup()
        if cmd is None and app_key not in self._crawled:
            self._crawled.add(app_key)
            try:
                crawl_e0(self.model, app_key, hwnd)
            except Exception:
                pass
            cmd = _lookup()
        return cmd

    def _try(self, eff: str, verb: str, a: Dict[str, Any], hwnd: int, dg, hin) -> Tuple[bool, str]:
        try:
            if eff == "snapshot_invoke":
                # label -> control, from ONE bulk snapshot of the live tree. Needs no geometry, so it works on
                # hidden/parked apps whose controls report empty rectangles (UWP), and it understands that a
                # person's "2" or "*" is the control named "Two" / "Multiply by".
                from core_organs import fast_uia
                from core_organs import task_runner as _tr
                label = a.get("label") or a.get("name") or (a.get("path", "").split(">")[-1].strip())
                if not label:
                    return False, "no label"
                node, cands = None, []
                for attempt in range(4):                           # a just-restored / just-changed UI may still be empty:
                    snap = fast_uia.snapshot(hwnd, timeout_ms=8000) or []      # look again a few times before giving up
                    for w in _popups(hwnd)[:6]:                    # open flyouts/menus are part of the live UI too
                        snap += fast_uia.snapshot(w, timeout_ms=3000) or []
                    cands = [(n, n.name) for n in snap if n.name and n.enabled
                             and (set(n.pats) & {"invoke", "select", "toggle", "expand"})]
                    node = _tr.match_label(label, cands)
                    if node is not None or len(cands) >= 12:      # found it, or the UI is populated and it is not there
                        break
                    time.sleep(0.6)
                if node is None:
                    return False, f"no control matches '{label}' ({len(cands)} operable controls seen)"
                ok, how = invoke_node_safely(node)
                return ok, f"{how} -> '{node.name}'"
            if eff == "layout_click":
                from core_organs import organ_50_layout_map as lm
                name = a.get("name") or (a.get("path", "").split(">")[-1].strip())
                hits = [h for h in lm.where(self.model, _app_key(self._cur_app or ""), name)
                        if h["score"] >= 2 and "invoke" in h["patterns"] + ["invoke"]]
                if not hits:
                    return False, f"'{name}' not in the layout map"
                rr = wt.RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
                cx, cy = hits[0]["center_rel"]
                x = int(rr.left + cx * (rr.right - rr.left))
                y = int(rr.top + cy * (rr.bottom - rr.top))
                return hin.post_click(dg._root_of(hwnd), x, y)
            if eff == "menu_command":
                path = a.get("path")
                if not path and a.get("keys"):
                    cmd = self._command_for_chord(_app_key(self._cur_app or ""), hwnd, a["keys"])
                    path = cmd["menu_path"] if cmd else ""
                if not path:
                    return False, "no known menu command for this action"
                return open_menu_path(hwnd, path)
            if verb == "key" or eff == "key":
                combo = a.get("keys") or a.get("alt_key") or a.get("shortcut")
                if not combo:
                    return False, "no key chord for this action"
                return hin.post_key_combo(dg._root_of(hwnd), combo)
            if verb in ("invoke", "menu") and eff in ("uia", "postmessage"):
                name = a.get("name") or (a.get("path", "").split(">")[-1].strip())
                els = _find_elements(self.g, hwnd, name, a.get("role", ""))
                if not els:
                    return False, f"element '{name}' not found"
                el = els[0]
                if eff == "uia":
                    out = dg._uia_dispatch(el, "click", "")
                    return (True, str(out[1] if out[0] is True else out)) if out and out[0] is True \
                        else (False, "no UIA pattern accepted")
                ok, note = hin.post_click(dg._root_of(el.hwnd or hwnd), *el.center)
                return ok, note
            if verb in ("invoke", "menu") and eff == "wm_command":
                mid = a.get("menu_id")
                if not mid:
                    return False, "no menu id"
                ok = ctypes.windll.user32.PostMessageW(hwnd, 0x0111, int(mid), 0)       # WM_COMMAND
                return bool(ok), f"WM_COMMAND {mid}"
            if verb == "type":
                role = a.get("target_role", "document|edit")
                els = [e for e in self.g._walk_uia(hwnd, max_depth=14, max_nodes=700)
                       if any(r in (e.role or "") for r in role.split("|"))] if dg.HAS_UIA else []
                if not els:
                    return False, "no text target"
                el = els[0]
                if eff == "uia":
                    out = dg._uia_dispatch(el, "type", str(a.get("text", "")))
                    return (True, str(out[1])) if out and out[0] is True else (False, "no value pattern")
                return hin.post_text(el.hwnd or hwnd, str(a.get("text", "")))
        except Exception as exc:
            return False, f"{type(exc).__name__}: {str(exc)[:60]}"
        return False, "effector not applicable to verb"


# ===========================================================================
# 9. E1 probing — reversible, hypothesis-driven exploration with a defined unwind
# ===========================================================================

def info_gain(cmd: Dict[str, Any]) -> float:
    """Expected information gain of probing a candidate: never-probed beats probed; a dialog
    opener (ellipsis) is high-yield; things already verified or with a known shortcut are low."""
    g = 0.0
    if cmd["source"] != "learned":
        g += 1.0
    if cmd["opaque"]:
        g += 0.5
    if re.search(r"(\.\.\.|…)\s*$", cmd["name"] or ""):
        g += 0.6
    if cmd["successes"]:
        g -= 0.8
    if cmd["failures"]:
        g -= 0.3
    return g


def _close_new_windows(hwnd: int, baseline: List[int], timeout_s: float = 2.0) -> bool:
    """Unwind: Escape each new window, then WM_CLOSE; True when the window set is back to baseline."""
    from core_organs import headless_input as hin
    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        new = [w for w in _popups(hwnd) if w not in baseline]
        if not new:
            return True
        for w in new:
            if attempt == 0:
                try:
                    hin.post_key_combo(w, "escape")
                except Exception:
                    pass
            else:
                ctypes.windll.user32.PostMessageW(w, 0x0010, 0, 0)                      # WM_CLOSE
        attempt += 1
        time.sleep(0.4)
    return not [w for w in _popups(hwnd) if w not in baseline]


def probe_e1(model: BehaviorModel, app_name: str, hwnd: int, cmd: Dict[str, Any], *,
             ladder: Optional[EffectorLadder] = None, run_id: str = "") -> Dict[str, Any]:
    with _bg(hwnd):
        return _probe_e1_impl(model, app_name, hwnd, cmd, ladder=ladder, run_id=run_id)


def _probe_e1_impl(model: BehaviorModel, app_name: str, hwnd: int, cmd: Dict[str, Any], *,
                   ladder: Optional[EffectorLadder] = None, run_id: str = "") -> Dict[str, Any]:
    """Open ONE reversible command (a dialog/pane opener), capture the new UI's full tree, then
    unwind and verify the app returned to baseline. The observed diff IS the knowledge: stored
    as a transition + postcondition, and the command is promoted to `learned` only if the
    effect was actually observed AND the unwind verified."""
    from core_organs import headless_input as hin
    key = _app_key(app_name)
    if cmd["risk"] == "E2":
        return {"probed": False, "reason": "E2 never explored"}
    ladder = ladder or EffectorLadder(model)
    base_windows = list(_popups(hwnd))
    before = observe(hwnd, grounding=ladder.g)
    action = {"verb": "menu" if cmd.get("menu_path") else "invoke", "name": cmd["name"],
              "path": cmd.get("menu_path", ""), "menu_id": cmd.get("menu_id"),
              "alt_key": cmd.get("shortcut", "")}
    t0 = time.time()
    ok, effector, note = ladder.perform(key, hwnd, action)
    # While a MODAL dialog is open the app's own UIA provider may not answer (Paint's Page Setup made
    # a main-window read block for ~2 minutes). So: detect the new window with Win32 only, read the
    # DIALOG's own tree (it is alive) in one bulk snapshot, UNWIND, and only then touch the main
    # window through UIA again.
    from core_organs import fast_uia
    new_hwnds: List[int] = []
    deadline = time.time() + 2.5
    while ok and time.time() < deadline:
        time.sleep(0.1)
        _keep_hidden(hwnd)
        new_hwnds = [w for w in _open_popups(hwnd) if w not in base_windows]   # open (non-empty) windows only
        if new_hwnds:
            break
    new_wins = sorted({(_win_title(w) or _win_class(w)).lower() for w in new_hwnds})
    dialog_names: List[str] = []
    if new_hwnds:
        time.sleep(0.2)                                      # let the dialog populate
        for w in new_hwnds:
            if _win_class(w) == "#32770":                    # classic dialog: Win32 child enumeration, no UIA
                kids = win32_window_controls(w)
                dialog_names += [k["name"].lower() for k in kids if k["name"]]
                dialog_names += [f"({k['class']})".lower() for k in kids if not k["name"]]
            else:
                snap = fast_uia.snapshot(w, max_nodes=3000, timeout_ms=3000)
                if snap is None:
                    dialog_names.append("(window tree unreadable within 3 s: provider too slow)")
                else:
                    dialog_names += [n.name.lower() for n in snap if n.name]
    unwound = _close_new_windows(hwnd, base_windows)         # Win32 only: Escape, then WM_CLOSE
    after = before
    new_names = sorted(set(dialog_names) - set(before.names))
    if ok and not new_hwnds:                                 # an in-window effect (pane/inline panel): diff the main tree
        end = time.time() + 1.5
        while time.time() < end:
            time.sleep(0.2)
            after = observe(hwnd, grounding=ladder.g)
            if after.uia_signature() != before.uia_signature():
                break
        new_names = sorted(set(after.names) - set(before.names))
    else:
        after = ObservedState(title=before.title, names=before.names + dialog_names,
                              windows=sorted(set(before.windows) | set(new_wins)), hwnd=hwnd)
    back = observe(hwnd, grounding=ladder.g)                 # now safe: nothing modal is open any more
    restored = unwound and set(back.windows) == set(before.windows)
    model.record_effector(key, action["verb"], effector, bool(ok and (new_wins or new_names)))
    effect = bool(new_wins or new_names)
    evidence = (f"effector={effector}; new_windows={new_wins[:3]}; new_controls={len(new_names)}"
                f" ({', '.join(new_names[:5])}); unwind={'restored' if restored else 'FAILED'}")
    if ok and effect:
        model.record_transition(key, before, f"{action['verb']}:{cmd['name']}", effector, after, evidence)
    promoted = False
    if ok and effect and restored:
        post = ([{"kind": "window_opened", "title_contains": new_wins[0]}] if new_wins
                else [{"kind": "ui_changed"}])
        model.upsert_command(key, {"name": cmd["name"], "goal": cmd["goal"], "menu_path": cmd["menu_path"],
                                   "shortcut": cmd["shortcut"], "verb": cmd["verb"],
                                   "menu_id": cmd.get("menu_id"), "risk": "E1", "post": post,
                                   "unwind": "escape/WM_CLOSE"},
                             source=cmd["source"], origin="e1-probe", evidence=evidence)
        model.command_outcome(cmd["cmd_id"], "PASS", evidence, promote=True)
        promoted = True
    elif not (ok and effect):
        model.command_outcome(cmd["cmd_id"], "FAIL", evidence)
    model.audit(run_id, key, "probe", cmd["menu_path"] or cmd["name"],
                "PROMOTED" if promoted else ("UNWIND_FAILED" if not restored else "NO_EFFECT"),
                note[:120], evidence)
    return {"probed": True, "effect_observed": effect, "unwound": restored, "promoted": promoted,
            "effector": effector, "new_windows": new_wins, "new_controls": new_names[:40],
            "elapsed_s": round(time.time() - t0, 2), "evidence": evidence}


def explore_e1(model: BehaviorModel, app_name: str, hwnd: int, *, max_actions: int = 6,
               budget_s: float = 40.0, run_id: str = "") -> Dict[str, Any]:
    with _bg(hwnd):
        return _explore_e1_impl(model, app_name, hwnd, max_actions=max_actions, budget_s=budget_s, run_id=run_id)


def _explore_e1_impl(model: BehaviorModel, app_name: str, hwnd: int, *, max_actions: int = 6,
                     budget_s: float = 40.0, run_id: str = "") -> Dict[str, Any]:
    """Hypothesis-driven E1 session: pick highest expected-information-gain candidates first,
    stop on action cap or time budget, never touch E2, never re-probe verified branches."""
    key = _app_key(app_name)
    ladder = EffectorLadder(model)
    cands = [c for c in model.commands(key, limit=2000) if c["risk"] in ("E1",)
             and c["verb"] != "setting" and not c["stale"] * 0]
    cands.sort(key=info_gain, reverse=True)
    t0 = time.time()
    results = []
    for c in cands:
        if len(results) >= max_actions or time.time() - t0 > budget_s:
            break
        if info_gain(c) <= 0:
            break
        res = probe_e1(model, app_name, hwnd, c, ladder=ladder, run_id=run_id)
        results.append({"cmd": c["menu_path"] or c["name"], **res})
        if res.get("probed") and not res.get("unwound", True):
            break                                   # app did not return to baseline: stop exploring
    return {"probes": results, "stopped": "action-cap" if len(results) >= max_actions else
            ("budget" if time.time() - t0 > budget_s else "exhausted"),
            "elapsed_s": round(time.time() - t0, 2)}


# ===========================================================================
# 10. Template runner — verified step graph; the LLM only picks among parsed elements
# ===========================================================================

@dataclass
class LeafResult:
    step_id: str
    verdict: str                  # PASS | FAIL | ESCALATED
    attempts: int = 0
    latency_s: float = 0.0
    effectors: List[str] = field(default_factory=list)
    evidence: str = ""
    gate: str = ""


class TemplateRunner:
    """Runs a template's leaf steps. A failing leaf retries ONLY itself (rotating effectors,
    re-perceiving between attempts), preconditions are repaired through the learned mode graph,
    and every step passes the autonomy gate. Never restarts the whole plan."""

    def __init__(self, model: Optional[BehaviorModel] = None, loop=None, grounding=None):
        from core_organs import desktop_grounding as dg
        self.model = model or get_model()
        self.g = grounding or dg.DesktopGrounding()
        # the loop is only needed for the native file dialog + judge micro-decisions; building it
        # is cheap (no vision warmup), so make one when the caller did not supply it
        self.loop = loop or dg.DesktopAutonomyLoop(grounding=self.g)
        self.ladder = EffectorLadder(self.model, self.g, self.loop)

    @staticmethod
    def _cheap_sig(hwnd: int) -> str:
        from core_organs import headless_input as hin
        try:
            wins = sorted((_win_title(w) or _win_class(w)) for w in _popups(hwnd)[:10])
        except Exception:
            wins = []
        return _win_title(hwnd) + "|" + ",".join(wins)

    def _settle(self, hwnd: int, timeout_s: float = 1.0) -> None:
        """Bounded wait until the app's visible shell (title + dialogs) stops changing."""
        last, stable, end = None, 0, time.time() + timeout_s
        while time.time() < end and stable < 2:
            _keep_hidden(hwnd)
            sig = self._cheap_sig(hwnd)
            stable = stable + 1 if sig == last else 0
            last = sig
            time.sleep(0.1)

    def run_leaf(self, app_name: str, hwnd_fn: Callable[[], int], tpl: TemplateMatch,
                 step: Dict[str, Any], params: Dict[str, Any], *, run_id: str,
                 allow_destructive: bool = False) -> LeafResult:
        key = _app_key(app_name)
        s = fmt_params(step, params)
        stat_key = f"{key}:{tpl.tpl_id}:{s['id']}"
        post = s.get("post") or []
        # E2 sticks from either the author's declaration or the generic word cues; otherwise the
        # author's reversible-class declaration (with its unwind) wins over the cue guess.
        declared, auto = s.get("risk"), classify_risk(s["goal"])
        risk = "E2" if "E2" in (declared, auto) else (declared or auto)
        decision = self.model.gate(stat_key, risk=risk, post=post,
                                   has_unwind=bool(s.get("unwind")), allow_destructive=allow_destructive,
                                   opaque=bool(s.get("opaque")))
        self.model.audit(run_id, key, "gate", f"{tpl.name}/{s['id']}", decision.action, decision.reason)
        res = LeafResult(s["id"], "FAIL", gate=decision.action)
        if decision.action == "QUEUE":
            res.verdict, res.evidence = "ESCALATED", decision.reason
            return res
        retries = int(s.get("retries", 2))
        avoid: set = set()
        t_leaf = time.time()
        for attempt in range(1 + retries):
            res.attempts = attempt + 1
            hwnd = hwnd_fn()
            if not hwnd:
                res.evidence = "app window not found"
                continue
            pre = s.get("pre") or []
            st = observe(hwnd, grounding=self.g, want_ocr=needs_ocr(pre) or needs_ocr(post),
                         want_region=needs_region(post))
            st.mode = self.model.current_mode([key, tpl.app_key], st)
            # ---- precondition (+ state-machine repair) ----
            if pre:
                pr = evaluate(pre, None, st, params)
                want_mode = next((a["mode"] for a in pre if a.get("kind") == "mode_is"), "")
                if pr.verdict == "FAIL" and want_mode and st.mode != want_mode:
                    path = self.model.path_to_mode([key, tpl.app_key], st.mode, want_mode)
                    if path:
                        for cmd in path:
                            self.ladder.perform(key, hwnd, {"verb": "key" if cmd["shortcut"] else "invoke",
                                                            "keys": cmd["shortcut"], "name": cmd["name"],
                                                            "menu_id": cmd["menu_id"]})
                            self._settle(hwnd)
                        st = observe(hwnd, grounding=self.g, want_ocr=needs_ocr(pre) or needs_ocr(post),
                                     want_region=needs_region(post))
                        st.mode = self.model.current_mode([key, tpl.app_key], st)
                        pr = evaluate(pre, None, st, params)
                if pr.verdict == "FAIL":
                    res.evidence = "precondition failed: " + pr.text()
                    continue
            before = st
            # ---- act ----
            did = []
            actions = s.get("do")
            if actions is None:                                        # absent => micro-decision fallback: judge
                actions = [{"verb": "judge", "goal": s["goal"]}] if self.loop is not None else []
            # an explicit [] is a VERIFY-ONLY leaf: it observes and asserts, it never acts
            for act in actions:
                if act.get("verb") == "judge" and self.loop is not None:
                    r = self.loop.step(act.get("goal", s["goal"]), app_name, expect={},
                                       allow_destructive=allow_destructive)
                    did.append("judge:" + str(r.get("method", "")))
                    continue
                ok, eff, note = self.ladder.perform(key, hwnd, act, avoid=avoid)
                did.append(f"{act.get('verb')}:{eff}")
                if not ok:
                    # A delivery failure says nothing about WHAT THE APP ACCEPTS (it is usually timing: the UI
                    # was not ready). Recording it taught the ladder to distrust the one effector that works.
                    res.evidence = f"delivery failed ({note})"
                    break
                self._settle(hwnd)
            else:
                after = observe(hwnd, grounding=self.g, want_ocr=needs_ocr(post),
                                want_region=needs_region(post))
                after.mode = self.model.current_mode([key, tpl.app_key], after)
                ev = evaluate(post, before, after, params)
                res.effectors = did
                res.evidence = ev.text()
                effect_seen = ev.verdict == "PASS"
                for act in actions:
                    eff = next((d.split(":")[1] for d in did if d.startswith(act.get("verb", "?") + ":")), "")
                    if eff and act.get("verb") not in ("wait", "judge"):
                        self.model.record_effector(key, act.get("verb", ""), eff, effect_seen)
                if ev.verdict == "PASS":
                    self.model.record_transition(key, before, s["goal"], ",".join(did), after, ev.text())
                    self.model.record_step_outcome(stat_key, "PASS")
                    res.verdict = "PASS"
                    res.latency_s = round(time.time() - t_leaf, 2)
                    return res
                if ev.verdict == "OPAQUE":
                    res.verdict = "ESCALATED"
                    res.evidence = "postcondition unobservable by any available tier: " + ev.text()
                    res.latency_s = round(time.time() - t_leaf, 2)
                    return res
                avoid |= {d.split(":")[1] for d in did if ":" in d}        # rotate effector next attempt
        self.model.record_step_outcome(stat_key, "FAIL")
        res.latency_s = round(time.time() - t_leaf, 2)
        return res

    def run(self, app_name: str, task_text: str, params: Optional[Dict[str, Any]] = None, *,
            run_id: str = "", archetype: str = "", allow_destructive: bool = False,
            hwnd_fn: Optional[Callable[[], int]] = None) -> Dict[str, Any]:
        params = dict(params or {})
        run_id = run_id or "run_" + uuid.uuid4().hex[:8]
        key = _app_key(app_name)
        if not archetype:
            try:
                from core_organs.organ_47_app_intelligence import classify_archetype
                archetype = classify_archetype(app_name)
            except Exception:
                archetype = ""
        tpl = self.model.match_template(app_name, task_text, archetype)
        if tpl is None:
            return {"matched": False, "run_id": run_id, "completed": False,
                    "reason": "no template for this task"}
        hwnd_fn = hwnd_fn or (lambda: self.g.find_window(app_name) or 0)
        t0 = time.time()
        leaves: List[LeafResult] = []
        bg = _bg(hwnd_fn() or 0)                       # minimized app: parked off-screen for the run
        bg.__enter__()
        try:
            return self._run_steps(app_name, task_text, params, run_id, key, tpl, hwnd_fn, leaves, t0,
                                   allow_destructive)
        finally:
            bg.__exit__(None, None, None)

    def _run_steps(self, app_name, task_text, params, run_id, key, tpl, hwnd_fn, leaves, t0,
                   allow_destructive) -> Dict[str, Any]:
        for step in tpl.steps:
            lr = self.run_leaf(app_name, hwnd_fn, tpl, step, params, run_id=run_id,
                               allow_destructive=allow_destructive)
            leaves.append(lr)
            self.model.audit(run_id, key, "leaf", f"{tpl.name}/{step['id']}", lr.verdict,
                             f"attempts={lr.attempts} gate={lr.gate}", lr.evidence)
            if lr.verdict != "PASS":
                break                                       # dependent steps cannot run; leaf retries already spent
        completed = len(leaves) == len(tpl.steps) and all(l.verdict == "PASS" for l in leaves)
        escalated = next((l for l in leaves if l.verdict == "ESCALATED"), None)
        self.model.template_outcome(tpl.tpl_id, "PASS" if completed else "FAIL")
        if escalated:
            self.model.enqueue(run_id, key, task_text, escalated.evidence,
                               {"template": tpl.name, "step": escalated.step_id, "params": params})
        return {"matched": True, "run_id": run_id, "template": tpl.name, "template_source": tpl.source,
                "completed": completed, "escalated": bool(escalated),
                "blocked_at": next((l.step_id for l in leaves if l.verdict != "PASS"), ""),
                "leaves": [l.__dict__ for l in leaves], "elapsed_s": round(time.time() - t0, 2),
                "seed_note": tpl.seed_note}


# ===========================================================================
# 11. Unattended day runner — never stalls the queue, honest end-of-day report
# ===========================================================================

def run_task_list(tasks: List[Dict[str, Any]], *, model: Optional[BehaviorModel] = None,
                  runner: Optional[TemplateRunner] = None, per_task_budget_s: float = 120.0,
                  verify_fn: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Tuple[bool, str]]] = None
                  ) -> Dict[str, Any]:
    """Run a day's task list with no human. A task that cannot pass the gate (or fails) is
    queued/recorded and the NEXT task proceeds. `verify_fn(task, result)` lets an independent
    check (file really on disk, etc.) override the runner's own claim — completion is only
    reported DONE if both agree."""
    model = model or get_model()
    runner = runner or TemplateRunner(model)
    run_id = "day_" + uuid.uuid4().hex[:8]
    for t in tasks:
        key = _app_key(t["app"])
        t0 = time.time()
        try:
            res = runner.run(t["app"], t["task"], t.get("params"), run_id=run_id,
                             allow_destructive=bool(t.get("allow_destructive")))
        except Exception as exc:
            res = {"matched": False, "completed": False, "reason": f"{type(exc).__name__}: {exc}"}
        if time.time() - t0 > per_task_budget_s:
            res["over_budget"] = True
        if res.get("completed"):
            ok, why = verify_fn(t, res) if verify_fn else (True, "no independent verifier supplied")
            decision = "DONE" if ok else "FAILED"
            reason, evidence = ("verified" if ok else f"runner claimed done but independent check failed: {why}"), why
        elif res.get("escalated"):
            decision, reason = "ESCALATED", "gate/observability: " + str(
                next((l["evidence"] for l in res.get("leaves", []) if l["verdict"] == "ESCALATED"), ""))
            evidence = json.dumps({"blocked_at": res.get("blocked_at")})
        else:
            decision = "FAILED"
            reason = res.get("reason") or f"blocked at leaf '{res.get('blocked_at', '?')}'"
            evidence = "; ".join(f"{l['step_id']}={l['verdict']}({l['evidence'][:60]})"
                                 for l in res.get("leaves", []))
        model.audit(run_id, key, "task", t.get("id") or t["task"], decision, reason, evidence)
    rep = model.day_report(run_id)
    rep["queue"] = [q for q in model.pending_queue() if q["run_id"] == run_id]
    return rep
