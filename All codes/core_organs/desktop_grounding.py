"""
desktop_grounding.py — General Desktop Autonomy Loop (Workstreams 1-5 of the
Desktop Autonomy & Robustness Master Plan).

One closed loop that makes ANY desktop app operable without per-app hardcoding:

    perceive (tiered grounding ladder)
      -> decide (constrained forced-choice judge, never open-ended ReAct)
      -> act (UIA patterns first, PostMessage second, physical input last)
      -> verify (structural + filesystem + pixel-delta postconditions)
      -> recover (retry ladder, popup triage, native file picker)
      -> checkpoint (resumable state) and learn (recipe distillation to organ_04)

Design rules:
- No per-app branches. Everything is data-driven from the live UI tree.
- Every tier degrades gracefully and REPORTS which tiers ran, so tests and
  users always know the real capability state of the machine (e.g. vision
  tier is skipped when torch is not installed — never silently faked).
- Never destroys user data: destructive element names require a checkpoint
  snapshot of the affected file or an explicit allow_destructive opt-in (HITL).

Dependency pins (do NOT "upgrade to fix" -- verified with `pip check`):
- transformers==4.51.3  (Florence-2 in OmniParser breaks on 5.x; organ_13 voice
  path and timm/tokenizers were import-swept against this pin)
- pydantic-settings==2.15.0: `pip check` reports crewai-cli wanting ~=2.10.1, but litellm needs
  >=2.14.1 -- mutually unsatisfiable; 2.15.0 is the working side (crewai imports/runs fine).
  Do NOT downgrade to 'fix' pip check: it breaks litellm.
- torch CPU wheels; easyocr is imported lazily and its model download is
  triggered once by DesktopGrounding.warmup_vision().
"""

import os
import re
import json
import time
import uuid
import contextlib
import ctypes
import hashlib
import logging
import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.desktop_grounding")

from core_organs import headless_input as hin  # the ONLY input-delivery layer (no physical input)

_IS_WINDOWS = os.name == "nt"

# ---------------------------------------------------------------------------
# Environment-derived capability flags (probed once, never assumed)
# ---------------------------------------------------------------------------

def _module_available(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False

HAS_UIA = _module_available("uiautomation")
HAS_PIL = _module_available("PIL")
HAS_PYTESSERACT = _module_available("pytesseract")
HAS_TORCH = _module_available("torch")

OMNI_LOCAL_REPO = r"D:\new_automation\OmniParser"

# --- vision/OCR environment preflight ----------------------------------------
# Fail LOUD at import when an installed dependency is past a documented breaking
# boundary (e.g. transformers>=5 silently bricks Florence-2 in OmniParser only at
# the first vision call). Runs hard when the vision tier is present, soft otherwise;
# an absent optional package is a warning, never a failure, so non-vision paths still
# import. A missing guard module must not itself break this organ -> catch ImportError
# only, letting a real EnvPinError propagate. See core_organs/env_guard.py.
try:
    from core_organs import env_guard as _env_guard

    _env_guard.check_runtime_pins(strict=bool(HAS_TORCH))
except ImportError:
    _env_guard = None

# Vision (OmniParser) is far slower than UIA on CPU, so it is budgeted per goal
# and cached per window pixel-signature. Both are env-tunable.
VISION_MAX_CALLS = int(os.environ.get("HOJAIGA_VISION_MAX_CALLS", "2"))
VISION_CACHE_TTL_S = float(os.environ.get("HOJAIGA_VISION_CACHE_TTL_S", "2.0"))

# Actionable control type families (generic UIA roles — not app specific).
ACTIONABLE_ROLES = {
    "button", "edit", "combobox", "dropdownbutton", "splitbutton", "menuitem",
    "checkbox", "radiobutton", "tabitem", "listitem", "treeitem", "hyperlink",
    "slider", "spinner", "group", "pane", "document", "thumb",
    "datagrid", "table", "dataitem",
}
# Roles accepted even with an EMPTY Name. A spreadsheet's document grid is a custom UIA control whose Name is empty
# (or a generic 'Grid'); it is recognised by what it IS (DataGrid / Table), not by what it is called.
UNNAMED_OK_ROLES = ("edit", "pane", "datagrid", "table")
# A grid exposes every cell as a DataItem (Excel: ~500 on the first screen). They are sampled, not enumerated, so
# they cannot crowd the real controls out of the judge's shortlist; the totals are reported (never silently cut).
GRID_CELL_CAP = int(os.environ.get("HOJAIGA_GRID_CELL_CAP", "120"))
# The tree walk costs one COM round trip PER NODE VISITED. max_nodes only ever capped how many controls get
# SURFACED, so a wide or pathological tree (a grid of thousands of cells, a host whose sibling enumeration never
# ends) could spin there for minutes and grow the process to gigabytes. These two budgets cap the VISITING,
# generic to any UIA app: the walk returns what it found inside the budget and says it stopped.
UIA_WALK_BUDGET_S = float(os.environ.get("HOJAIGA_UIA_WALK_BUDGET_S", "6.0"))
UIA_WALK_NODE_BUDGET = int(os.environ.get("HOJAIGA_UIA_WALK_NODE_BUDGET", "5000"))
# The time budget never cuts a walk that has barely begun (a slow but normal tree must still be grounded), and a
# single COM call can overrun it - so there is a hard extra stop, exactly like the deep scan's own rails.
UIA_WALK_MIN_NODES = int(os.environ.get("HOJAIGA_UIA_WALK_MIN_NODES", "300"))
UIA_WALK_HARD_EXTRA_S = float(os.environ.get("HOJAIGA_UIA_WALK_HARD_EXTRA_S", "2.0"))
# Smallest share of the visible screen an empty edit box must cover to count as a surface that can hold a
# document's text (a one-line address/name/search strip is not one). Geometry, so it travels with the window size.
_CANVAS_MIN_FRACTION = float(os.environ.get("HOJAIGA_CANVAS_MIN_FRACTION", "0.05"))

# Verbs the constrained judge is allowed to choose. Keeping this tiny is what
# stops the 7B model from hallucinating tool calls (the old flailing failure).
LEGAL_VERBS = ("click", "type", "key", "invoke", "scroll", "wait", "done")
_POPUP_LOCK = threading.RLock()

# A learned shortcut this confident is executed directly, skipping the LLM
# judge entirely — this is the "pro muscle memory" path (Ctrl+S to save, etc.).
PRO_SHORTCUT_CONF = float(os.environ.get("HOJAIGA_PRO_SHORTCUT_CONF", "0.70"))
# 6.4: direct control (executing a remembered shortcut without the judge) needs this many VERIFIED successes - one lucky
# trace once poisoned a step (a weak 'the UI changed' PASS on Ctrl+N turned into 'Ctrl+N does whatever the goal says')
DIRECT_MIN_SUCCESSES = int(os.environ.get("HOJAIGA_DIRECT_MIN_SUCCESSES", "2"))

# Destructive patterns are generic word cues, not per-app hardcodes.
MAX_RELAUNCHES = int(os.environ.get("HOJAIGA_MAX_RELAUNCHES", "1"))     # G2: one relaunch per run, then fail with evidence
DESTRUCTIVE_CUES = ("delete", "remove", "format", "overwrite", "discard", "erase", "don't save", "don’t save",
                    "do not save", "dont save")

BRAINS_CHAT_URL = os.environ.get("HOJAIGA_BRAIN_URL", "http://127.0.0.1:11434/api/chat")
JUDGE_MODEL = os.environ.get("HOJAIGA_JUDGE_MODEL", "qwen2.5:7b")
JUDGE_TIMEOUT_S = float(os.environ.get("HOJAIGA_JUDGE_TIMEOUT_S", "12"))
MAX_JUDGE_ELEMENTS = 8
TEACH_MAX_CONTROLS = int(os.environ.get("HOJAIGA_TEACH_MAX_CONTROLS", "60"))   # the teacher sees this many ranked controls (and the window picture)
INVALID_CHOICE_LIMIT = 3
CHECKPOINT_DIR = os.path.join(os.environ.get("TEMP", "."), "hojaiga_desktop_checkpoints")

# Readiness backoff: heavy apps (Blender, Office, Electron) show a splash and
# expose controls seconds after the window first appears. Poll the live tree
# with growing waits so the loop never mistakes 'still booting' for 'wrong
# state'. Bounded so a genuinely broken app still escalates to HITL promptly.
READY_TIMEOUT_S = float(os.environ.get("HOJAIGA_READY_TIMEOUT_S", "10"))
READY_BACKOFF_S = float(os.environ.get("HOJAIGA_READY_BACKOFF_S", "0.35"))
READY_BACKOFF_MAX_S = float(os.environ.get("HOJAIGA_READY_BACKOFF_MAX_S", "1.5"))
# The 10 s above is the deadline for an app that shows NO sign of starting. While the app visibly IS starting
# (its window set changes - splash -> login -> main frame - or its processes keep burning CPU) the deadline is
# pushed out by READY_GRACE_S at a time, never past READY_HARD_CAP_S. Measured on this host: Steam shows a 199x34
# update splash for ~39 s, then a login window from a DIFFERENT process 12 s later; a flat 10 s gave up on it.
READY_GRACE_S = float(os.environ.get("HOJAIGA_READY_GRACE_S", "12"))
READY_WAKE_S = float(os.environ.get("HOJAIGA_READY_WAKE_S", "6"))   # a packaged window still on its splash after this long is shown once (no focus) to lay out
READY_HARD_CAP_S = float(os.environ.get("HOJAIGA_READY_HARD_CAP_S", "90"))
READY_RICH_ELEMENTS = 8        # a window with this many controls is a real UI, not a splash: no stability poll needed


# ---------------------------------------------------------------------------
# Unified grounding contract (same mental model as the web side)
# ---------------------------------------------------------------------------

def _dialog_holds_name_box(hwnd: int) -> bool:
    """True when a window's own UIA tree shows an editable box that is not a file-list cell (one bulk read).

    Shape, not a label: the earlier version asked for the English words 'file name', so the same dialog in
    another language was invisible to it. The window is only a *candidate* here; organ_24's shape test (which
    also wants an accept button and filesystem evidence) is what decides."""
    try:
        from core_organs import fast_uia as _fu
        for n in (_fu.snapshot(int(hwnd), timeout_ms=2500) or []):
            if n.ctype in ("EditControl", "ComboBoxControl") and not str(n.aid or "").startswith("System."):
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


# What a "name box" IS, in UI terms, never what it is called. Two places in the loop used to ask the control
# for the English words 'file name': the same picker in another language (or one whose label the app wrote
# freely) was invisible to them and the goal's path went in as a bare base name. The caption survives here
# only as ONE hint among three, never as the only gate.
FILE_NAME_BOX_ROLES = ("edit", "document", "combobox", "richedit", "text")
_NAME_BOX_CAPTION_HINT = re.compile(r"file ?name", re.I)

# An edit control whose OWN name says it searches, filters, navigates or addresses is a TOOL, not the document:
# a payload typed for 'write ... into the file' belongs in the surface that HOLDS content. Measured twice on a
# spreadsheet - first into the cell-reference strip (named 'A1' by the row it shows), then into 'Search for a
# file' - both times the run typed two characters, both times a UI change looked like progress, and the saved
# workbook was empty. The words are UI conventions collected as data; the rule below still lets a goal that
# NAMES the box ('type gmail.com in the address bar') win, because that goal's own tokens match its name.
UTILITY_BOX_NAMES = ("search", "filter", "address", "goto", "go to", "find", "url", "name box",
                     "navigation", "lookup", "jump")


def _is_name_box_element(elem: Any, app_hwnd: int) -> bool:
    """Is this grounded element the box a file name is typed into?"""
    role = (getattr(elem, "role", "") or "").lower()
    if role not in FILE_NAME_BOX_ROLES:
        return False
    if _NAME_BOX_CAPTION_HINT.search(str(getattr(elem, "name", "") or "")):
        return True
    try:
        from core_organs import organ_24_dap as _dap
        aids = tuple(str(a) for a in getattr(_dap, "DIALOG_NAME_FIELD_AIDS", ()))
        aid = str(getattr(elem, "automation_id", "") or "")
        if aid and any(a and a in aid for a in aids):      # Win32 IDFILENAME: locale-independent
            return True
        root = _root_of(int(getattr(elem, "hwnd", 0) or 0) or int(app_hwnd or 0))
        if not root:
            return False
        rep = _dap.file_dialog_shape(root, timeout_ms=1500)
        return bool(rep.get("name_edit")) and bool(rep.get("shape_ok"))
    except Exception:  # noqa: BLE001
        return False


_ACCOUNT_NAME = re.compile(r"^[A-Z][\w'.-]+,\s+[A-Z][\w'.-]+$|^(?:sign|log)\s?(?:in|out)\b|^signed in as\b|^switch account|^(?:my )?account$|^manage (?:your )?(?:account|profile)", re.I)
_ACCOUNT_GOAL = re.compile(r"\b(account|profile|sign|log ?(?:in|out)|user|switch)\b", re.I)


def is_account_control(name: str, goal: str) -> bool:
    """A control that names the signed-in PERSON or an account action ('Signed in as ...', 'Last, First', 'Sign out'): never a step toward a goal
    that does not talk about accounts - pressing it opens the user's profile menu (measured: an Excel save goal expanded the user's name)."""
    if _ACCOUNT_GOAL.search(goal or ""):
        return False
    return bool(_ACCOUNT_NAME.search((name or "").strip()))


@dataclass
class GroundedElement:
    id: str                       # stable-ish per-tree hash
    name: str                     # visible label / UIA name / OCR text
    role: str                     # button | edit | menuitem | ...
    bbox: Tuple[int, int, int, int]
    tier: str                     # "uia" | "win32" | "ocr" | "vision"
    confidence: float = 0.9
    hwnd: int = 0
    automation_id: str = ""
    value: str = ""
    enabled: bool = True
    rel: Optional[Tuple[float, float, float, float]] = None   # bbox normalized to the window rect (survives moves/reflow); pixel tiers set it

    @property
    def center(self) -> Tuple[int, int]:
        return ((self.bbox[0] + self.bbox[2]) // 2, (self.bbox[1] + self.bbox[3]) // 2)

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "role": self.role,
                "bbox": list(self.bbox), "tier": self.tier,
                "confidence": round(self.confidence, 3),
                "center": list(self.center)}


def _is_parked_offscreen(hwnd: int) -> bool:
    """True for a window that background_window has moved fully off every monitor (its parked rectangle sits at
    the park origin, far outside any real screen)."""
    if not (_IS_WINDOWS and hwnd):
        return False
    try:
        import ctypes.wintypes as wt
        r = wt.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
        return r.right <= -10000 and r.bottom <= -10000
    except Exception:
        return False


def _element_id(hwnd: int, role: str, name: str, bbox: Tuple[int, int, int, int]) -> str:
    raw = f"{hwnd}|{role}|{name.strip().lower()}|{bbox}"
    return "el_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


def _window_rect(hwnd: int) -> Tuple[int, int, int, int]:
    """Current window rect (l, t, r, b); (0,0,0,0) if unreadable."""
    try:
        import ctypes.wintypes as wt
        rr = wt.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
        return (rr.left, rr.top, rr.right, rr.bottom)
    except Exception:  # noqa: BLE001
        return (0, 0, 0, 0)


def _rel_of_window(bbox: Tuple[int, int, int, int], hwnd: int) -> Optional[Tuple[float, float, float, float]]:
    """Normalize a screen bbox to the window rect (0..1), so a pixel-found target survives a move/reflow.
    None when the window rect is unreadable or degenerate."""
    win = _window_rect(hwnd)
    w, h = win[2] - win[0], win[3] - win[1]
    if w <= 0 or h <= 0:
        return None
    return (round((bbox[0] - win[0]) / w, 4), round((bbox[1] - win[1]) / h, 4),
            round((bbox[2] - win[0]) / w, 4), round((bbox[3] - win[1]) / h, 4))


def _abs_from_rel(rel: Tuple[float, float, float, float], hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """Map stored normalized coords back to the window's CURRENT screen rect. None if the window is gone."""
    win = _window_rect(hwnd)
    w, h = win[2] - win[0], win[3] - win[1]
    if w <= 0 or h <= 0:
        return None
    return (int(win[0] + rel[0] * w), int(win[1] + rel[1] * h),
            int(win[0] + rel[2] * w), int(win[1] + rel[3] * h))


def _get_bridge():
    """The knowledge bridge (unified command knowledge from scans + explorations). None when unavailable or disabled."""
    try:
        from core_organs import knowledge_bridge as _kb
        return _kb.get_bridge() if _kb.ENABLED else None
    except Exception:
        return None


def _get_intel():
    """Lazily reach the app-intelligence organ (W8). Returns None if it is not
    importable — the loop then runs on pure perception, never crashes."""
    try:
        from core_organs.organ_47_app_intelligence import get_intel
        return get_intel()
    except Exception as exc:  # pragma: no cover - environmental
        logger.debug("[intel] organ_47 unavailable: %s", exc)
        return None


def get_dap_core():
    """Lazily reach DAPRuntimeCore from organ_24_dap (Workstream 1 facade)."""
    try:
        from core_organs.organ_24_dap import DAPRuntimeCore
        return DAPRuntimeCore()
    except Exception as exc:
        logger.debug("[dap] organ_24 DAPRuntimeCore unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# W1 — DesktopGrounding: tiered perception ladder
# ---------------------------------------------------------------------------

_HOST_PIDS_CACHE: Dict[str, Any] = {"t": 0.0, "pids": frozenset()}


def _agent_host_pids() -> frozenset:
    """PIDs of the processes THIS agent runs inside: its ancestors (the IDE / terminal / desktop app that
    launched it). Their windows are the agent's own host, never an automation target. Data-driven - it replaces a
    hardcoded list of editor titles that also made a user's real VS Code ungroundable. A window of the same app that
    the user (or the launcher) started separately has a different process and is unaffected. Cached for 30 s."""
    now = time.monotonic()
    if now - _HOST_PIDS_CACHE["t"] < 30.0 and _HOST_PIDS_CACHE["pids"]:
        return _HOST_PIDS_CACHE["pids"]
    pids: set = set()          # ANCESTORS only: this process's own windows (test fixtures, overlays) are legitimate targets
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        for _ in range(10):
            proc = proc.parent()
            if proc is None:
                break
            name = (proc.name() or "").lower()
            if name in ("explorer.exe", "services.exe", "wininit.exe", "winlogon.exe", "svchost.exe", "system"):
                break                       # the desktop shell / system: not an app host
            pids.add(proc.pid)
    except Exception:
        pass
    _HOST_PIDS_CACHE.update(t=now, pids=frozenset(pids))
    return _HOST_PIDS_CACHE["pids"]


class DesktopGrounding:
    """Grounds one app window into a unified list of actionable elements.

    Ladder (stops at the first tier that yields confident candidates, unless
    the caller demands a specific target text and earlier tiers missed it):
      Tier 1  UIA tree walk via uiautomation (deep, proven on this host)
      Tier 2  Win32 child enumeration + window text (no deps, always works)
      Tier 3  OCR over a window screenshot (only when pytesseract present)
      Tier 4  OmniParser vision (only when local repo + torch present)
    Every call reports tiers_ran + tiers_skipped so nothing is silently faked.
    """

    def __init__(self):
        self.last_report: Dict[str, Any] = {}
        self.last_walk: Dict[str, Any] = {}
        self._dap = None
        self._vision_calls = 0
        # (hwnd, window-signature) -> (monotonic ts, elements)
        self._vision_cache: Dict[Tuple[int, str], Tuple[float, List[GroundedElement]]] = {}

    def reset_vision_budget(self) -> None:
        """Called at the start of every goal so one goal cannot run OmniParser N times."""
        self._vision_calls = 0

    @property
    def dap_core(self):
        if self._dap is None:
            self._dap = get_dap_core()
        return self._dap

    # ---- window location (dynamic, name-substring based like organ_24) ----
    _BROWSER_PROCS = frozenset({"chrome", "msedge", "firefox", "brave", "opera", "vivaldi",
                                "iexplore", "arc", "chromium"})

    @staticmethod
    def _process_stem(hwnd: int) -> str:
        """Lower-case exe stem of the window's owning process ('' when unreadable)."""
        try:
            import ctypes.wintypes as wt
            k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
            pid = wt.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            k32.OpenProcess.restype = ctypes.c_void_p
            h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(520)
                size = wt.DWORD(520)
                k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wt.DWORD,
                                                           ctypes.c_wchar_p, ctypes.POINTER(wt.DWORD)]
                if k32.QueryFullProcessImageNameW(ctypes.c_void_p(h), 0, buf, ctypes.byref(size)):
                    return os.path.splitext(os.path.basename(buf.value))[0].lower()
            finally:
                k32.CloseHandle(ctypes.c_void_p(h))
        except Exception:
            pass
        return ""

    def find_window(self, app_hint: str, all_candidates: bool = False):
        """Locate the target app window. Ranked, NOT first-substring-wins:

          5  owning process image name matches the hint   (notepad.exe for 'notepad')
          4  window class matches the hint
          3  title is '<hint>' / ends with ' - <hint>' (classic document-window title)
          1  hint merely appears somewhere in the title

        Browser windows are excluded unless the hint itself names a browser: a Chrome/Edge
        tab titled 'Windows Notepad - Search' must never be mistaken for Notepad (a live
        E2E run once typed a haiku into the user's browser because of exactly that).
        """
        user32 = ctypes.windll.user32
        if not _IS_WINDOWS:
            return [] if all_candidates else None
        hint = (app_hint or "").lower().strip()
        token = hint.split()[0] if hint else ""
        hint_is_browser = any(b in hint for b in self._BROWSER_PROCS) or "browser" in hint
        host_pids = _agent_host_pids()
        _generic = {"microsoft", "windows", "app", "the", "for", "and", "of", "new"}
        hint_tokens = [w for w in re.findall(r"[a-z0-9\+\.#]+", hint) if w not in _generic and len(w) > 1] or ([token] if token else [])
        found: List[Tuple[int, int]] = []
        hidden_pass = {"on": False}       # second pass: apps parked in the tray keep a HIDDEN top-level window whose UIA tree still answers

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                if not hidden_pass["on"]:
                    return True
                r_h = ctypes.wintypes.RECT() if hasattr(ctypes, "wintypes") else None
                import ctypes.wintypes as _wth
                r_h = _wth.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r_h))
                if (r_h.right - r_h.left) < 200 or (r_h.bottom - r_h.top) < 150 or not hin.safe_window_text(int(hwnd)).strip():
                    return True           # helper / hook / IME windows are hidden too: only a real sized, titled window counts
            title = hin.safe_window_text(int(hwnd)).lower()      # never blocks on a window whose thread does not pump messages
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cname = cls_buf.value.lower()
            # Skip infrastructure windows, same spirit as organ_01 filters.
            if cname in ("shell_traywnd", "progman", "workerw", "mintaskswnd",
                         "shell_dock", "topmosttoplevelwindowclass",
                         "#32768"):           # a classic MENU window (the popup of a menu bar) is never the app's window; it was picked once after a menu crawl
                return True
            # A UWP app's CoreWindow is its content host, not an app window: it cannot be minimized, parked or
            # closed on its own (its ApplicationFrameWindow is the real top level, and UIA on the frame already
            # contains the content). Matching it by PROCESS NAME (CalculatorApp.exe) used to beat the frame, so
            # the loop grounded and tried to park a window that cannot be parked.
            if cname == "windows.ui.core.corewindow":
                return True
            if hin.window_pid(int(hwnd)) in host_pids:
                return True          # the agent's own host (the IDE / terminal / app this process runs inside): never a target
            proc = self._process_stem_cached(hwnd)
            # every distinctive word of the hint may name the app: 'visual studio code' is process 'code', title 'x - Visual
            # Studio Code' or nothing at all; matching only the FIRST word made a perfectly good window unfindable
            def _tin(t: str, hay: str) -> bool:
                return (t in re.findall(r"[a-z0-9]+", hay)) if len(t) < 3 else (t in hay)
            hit = next((t for t in hint_tokens if _tin(t, proc)), None) or next((t for t in hint_tokens if _tin(t, cname)), None)                 or next((t for t in hint_tokens if _tin(t, title)), None)
            if not hint_tokens or hit is None:
                return True
            if len(hint_tokens) > 1 and not any(_tin(t, proc) for t in hint_tokens) and not all(_tin(t, cname + " " + title) for t in hint_tokens):
                return True      # a multi-word name that only SOME of its words reach through the class / title is another window ('HJ-TY1-Nothing' is not 'HJ-TY1-Alpha')
            if proc in self._BROWSER_PROCS and not hint_is_browser:
                return True
            blob = proc + " " + cname + " " + title
            matched = sum(1 for t in hint_tokens if _tin(t, blob))            # a window that carries MORE of the hint's words is the better match
            if title == hint:
                score = 6                                                 # the window is literally titled what was asked for
            elif any(_tin(t, proc) for t in hint_tokens):
                score = 5
            elif any(_tin(t, cname) for t in hint_tokens):
                score = 4
            elif title == hint or title.endswith(" - " + hint) or title.startswith(hint + " "):
                score = 3
            else:
                score = 1
            # Skip cloaked (hidden UWP/virtual-desktop) and tiny helper windows; among the
            # rest the largest window of the best-scoring class is the real app frame.
            try:
                import ctypes.wintypes as _wt
                cloaked = ctypes.c_int(0)
                ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    _wt.HWND(hwnd), 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
                if cloaked.value and not hin.is_minimized(hwnd):
                    return True
                rr = _wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rr))
                w, h = rr.right - rr.left, rr.bottom - rr.top
            except Exception:
                w = h = 1000
            if not hin.is_minimized(hwnd) and (w < 120 or h < 80):
                return True  # (minimized windows report a tiny parked rect; they are still real)
            found.append((score * 1_000_000_000 + matched * 100_000_000 + w * h, hwnd))
            return True

        self._proc_cache = {}
        try:
            user32.EnumWindows(_cb, 0)
            if not found:                     # nothing visible matches: look at hidden (tray-parked) windows of the app
                hidden_pass["on"] = True
                user32.EnumWindows(_cb, 0)
        except Exception as exc:
            logger.debug("[grounding] EnumWindows failed: %s", exc)
            return [] if all_candidates else None
        if not found:
            return [] if all_candidates else None
        found.sort(key=lambda t: -t[0])  # stable: Z-order preserved among equal scores
        if all_candidates:
            return [h for _s, h in found]
        return found[0][1]

    def family_activity(self, app_hint: str) -> Tuple[frozenset, float]:
        """(window-set signature, CPU seconds) of everything that looks like this app. A change in the window
        set (a splash replaced by a login window, a main frame appearing) or CPU still being spent means the
        app is still STARTING; both flat means it is either ready or not starting at all."""
        sig = frozenset((h, self.window_title(h)) for h in self.find_window(app_hint, all_candidates=True))
        cpu = 0.0
        token = (app_hint or "").lower().split()[0] if (app_hint or "").strip() else ""
        if token:
            try:
                import psutil
                for pr in psutil.process_iter(["name", "cpu_times"]):
                    nm = (pr.info.get("name") or "").lower()
                    ct = pr.info.get("cpu_times")
                    if token in nm and ct:
                        cpu += float(ct.user + ct.system)
            except Exception:
                pass
        return sig, cpu

    def _process_stem_cached(self, hwnd: int) -> str:
        cache = getattr(self, "_proc_cache", None)
        if cache is None:
            cache = self._proc_cache = {}
        if hwnd not in cache:
            cache[hwnd] = self._process_stem(hwnd)
        return cache[hwnd]

    def window_title(self, hwnd: int) -> str:
        if not (_IS_WINDOWS and hwnd):
            return ""
        return hin.safe_window_text(int(hwnd))

    def _ground_raw(self, hwnd: int, max_nodes: int = 1500) -> List[GroundedElement]:
        """Grounded elements from ONE bulk read of the RAW UIA tree (fast_uia): actionable, named, enabled controls. Chromium / Electron / CEF
        expose their whole DOM there (measured: 966 nodes, 179 invokable, in 0.4 s; the control-view walk found 8)."""
        from core_organs import fast_uia as _fu
        mini = hin.is_minimized(hwnd) or _is_parked_offscreen(hwnd) or not ctypes.windll.user32.IsWindowVisible(hwnd)
        out: List[GroundedElement] = []
        seen = set()
        for n in (_fu.snapshot(hwnd, max_nodes=max_nodes, timeout_ms=8000) or []):
            role = n.role
            if role not in ACTIONABLE_ROLES or not (n.name or "").strip() or not n.enabled:
                continue
            if n.offscreen and not mini:
                continue
            if not mini and not (n.rect[2] > n.rect[0] and n.rect[3] > n.rect[1]):
                continue
            key = (n.name.strip().lower(), role, n.rect[0] // 6, n.rect[1] // 6)
            if key in seen:
                continue
            seen.add(key)
            out.append(GroundedElement(id=_element_id(hwnd, role, n.name, n.rect), name=n.name.strip()[:120], role=role, bbox=n.rect,
                                       tier="uia", confidence=0.85, hwnd=hwnd))
        return out

    # ---- Tier 1: UIA ----
    def _walk_uia(self, root_hwnd: int, max_depth: int = 12, max_nodes: int = 900,
                  budget_s: Optional[float] = None) -> List[GroundedElement]:
        """Ground the actionable controls of one window by UIA.

        `budget_s` lets a CALLER that has several walks to fund (organ_48's observation, which also walks the
        popup windows and takes a bulk snapshot) hand this walk its share of one deadline instead of each call
        getting a fresh default. The default stays UIA_WALK_BUDGET_S."""
        if not HAS_UIA:
            return []
        _t_walk = time.perf_counter()
        _bud = UIA_WALK_BUDGET_S if budget_s is None else max(0.2, float(budget_s))
        import uiautomation as auto
        elements: List[GroundedElement] = []
        try:                                        # a frame that hosts a Chromium content window (WebView2 / CEF): its DOM tree is THERE
            from core_organs import dap_actuator as _da
            if _da.family_of(root_hwnd) == "chromium":
                _content = _da.chromium_content_hwnd(root_hwnd)
                if _content and _content != root_hwnd:
                    root_hwnd = _content
        except Exception:  # noqa: BLE001
            pass
        try:                                          # a Chromium DOM / a XAML-WinUI visual tree lives in the RAW UIA view: the per-node control-view
            from core_organs import dap_actuator as _da2   # walk sees only the title bar (measured: Chromium 966 raw vs 8 control; a parked UWP app 4
            _fam = _da2.family_of(root_hwnd)                # chrome controls in the control view vs its whole navigation in the raw view). Read the RAW
            if _fam == "chromium" or _fam == "winui" or hin.is_xaml_host(root_hwnd):   # view for these host families too, or the agent only ever sees chrome.
                _raw = self._ground_raw(root_hwnd, max_nodes=max(max_nodes, 1500))
                if len(_raw) >= 3:
                    return _raw
        except Exception:  # noqa: BLE001
            pass
        try:
            ctrl = auto.ControlFromHandle(root_hwnd)
        except Exception:
            return []
        if ctrl is None:
            return []
        count = 0
        visited = 0
        deepest = 0
        stopped_by = ""
        walk_errors = 0
        first_error = ""
        cells_seen = cells_kept = 0
        # A minimized window reports every control as off-screen with bogus (-32000) rects, but
        # its UIA patterns still work. Keep them (addressable by pattern, not by coordinates).
        # A window PARKED off-screen (background_window) behaves the same for UWP/WinUI apps: they do not lay out
        # content that is entirely off every monitor, so their controls report IsOffscreen / empty rectangles
        # while Invoke / Value / Toggle patterns work. Treat it like minimized.
        mini = hin.is_minimized(root_hwnd) or _is_parked_offscreen(root_hwnd) or not ctypes.windll.user32.IsWindowVisible(root_hwnd)   # hidden (tray) windows report everything off-screen too

        def _visit(c, depth: int):
            nonlocal count, cells_seen, cells_kept, visited, stopped_by, walk_errors, first_error, deepest
            if stopped_by:
                return
            if depth > deepest:
                deepest = depth
            if depth > max_depth:
                return
            if count >= max_nodes:
                # Stopping at a cap has to be a STOP, not a per-node early return: the caller is still walking
                # siblings, and with an endless chain an early return means the walk never ends.
                stopped_by = f"surface-budget({max_nodes})"
                return
            visited += 1
            if visited > UIA_WALK_NODE_BUDGET:
                stopped_by = f"node-budget({UIA_WALK_NODE_BUDGET})"
                return
            el = time.perf_counter() - _t_walk
            if (el > _bud and visited >= UIA_WALK_MIN_NODES) \
                    or el > _bud + UIA_WALK_HARD_EXTRA_S:
                stopped_by = f"time-budget({_bud:g}s)"
                return
            try:
                role = (c.ControlTypeName or "").lower().replace("control", "")
                name = (c.Name or "").strip()
                rect = c.BoundingRectangle
                bbox = (rect.left, rect.top, rect.right, rect.bottom)
                enabled = bool(getattr(c, "IsEnabled", True))
                visible = mini or bool(getattr(c, "IsOffscreen", False)) is False
                if role == "dataitem":
                    cells_seen += 1
                    if cells_kept >= GRID_CELL_CAP:
                        return                       # sampled: counted above, not surfaced
                if (role in ACTIONABLE_ROLES and (name or role in UNNAMED_OK_ROLES)
                        and visible and enabled
                        and (mini or (bbox[2] > bbox[0] and bbox[3] > bbox[1]))):
                    value = ""
                    if role != "dataitem" or cells_kept < 40:      # a value read is one COM round trip per cell
                        try:
                            vp = c.GetValuePattern()
                            if vp:
                                value = (vp.Value or "")[:80]
                        except Exception:
                            pass
                    if role == "dataitem":
                        cells_kept += 1
                    label = name or (str(getattr(c, "AutomationId", "") or "").strip()
                                     if role in ("datagrid", "table") else "") or role
                    elements.append(GroundedElement(
                        id=_element_id(root_hwnd, role, name or label, bbox),
                        name=label, role=role, bbox=bbox, tier="uia",
                        confidence=0.9 if name else 0.55,
                        hwnd=root_hwnd, value=value))
                    count += 1
                # ONE COM call at a time. Control.GetChildren() materialises the whole sibling list first, so a
                # provider with a broken or cyclic sibling chain makes that single call never return: it grew the
                # suite process to gigabytes inside one walk (measured, py-spy: GetNextSiblingControl).
                # The depth rail is tested BEFORE the chain is opened - every sibling shares one depth, so
                # returning per node here would leave the sibling loop spinning forever on an endless chain.
                if depth + 1 <= max_depth:
                    child = c.GetFirstChildControl()
                    while child is not None:
                        _visit(child, depth + 1)
                        if stopped_by:
                            break
                        child = child.GetNextSiblingControl()
            except Exception as exc:
                # A node that throws prunes its own subtree; the walk continues. It is COUNTED, never silent.
                walk_errors += 1
                first_error = first_error or f"{type(exc).__name__}: {str(exc)[:70]}"
                return

        _visit(ctrl, 0)
        self.last_walk = {"grid_cells_seen": cells_seen, "grid_cells_surfaced": cells_kept,
                          "grid_cells_sampled_out": max(0, cells_seen - cells_kept),
                          "nodes_walked": visited, "surfaced": count,
                          "max_depth_seen": deepest, "walk_max_depth": max_depth,
                          "depth_hit_cap": deepest >= max_depth,
                          "time_budget_ms": int(_bud * 1000),
                          "node_budget": UIA_WALK_NODE_BUDGET,
                          "time_budget_hit": stopped_by.startswith("time"),
                          "node_budget_hit": stopped_by.startswith("node"),
                          "surface_budget_hit": stopped_by.startswith("surface"),
                          "truncated": bool(stopped_by) or deepest >= max_depth,
                          "stopped_by": stopped_by,
                          "node_errors": walk_errors, "first_error": first_error,
                          "walk_ms": int((time.perf_counter() - _t_walk) * 1000)}
        if stopped_by:
            logging.getLogger("desktop_grounding").warning(
                "UIA walk of %s stopped by %s after %d node(s) (%d surfaced) - returning the partial ground",
                root_hwnd, stopped_by, visited, count)
        return elements

    # ---- Tier 2: Win32 children ----
    def _walk_win32(self, root_hwnd: int) -> List[GroundedElement]:
        if not _IS_WINDOWS:
            return []
        user32 = ctypes.windll.user32
        elements: List[GroundedElement] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(child, _l):
            try:
                if not user32.IsWindowVisible(child):
                    return True
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(child, cls_buf, 256)
                cname = cls_buf.value.lower()
                length = user32.GetWindowTextLengthW(child)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(child, buf, length + 1)
                name = buf.value.strip()
                role = ""
                if "button" in cname:
                    role = "button"
                elif "edit" in cname:
                    role = "edit"
                elif "combobox" in cname:
                    role = "combobox"
                elif "syslistview" in cname or "list" in cname:
                    role = "listitem"
                if not role or (not name and role != "edit"):
                    return True
                r = ctypes.wintypes.RECT() if hasattr(ctypes, "wintypes") else None
                import ctypes.wintypes as wt
                rr = wt.RECT()
                user32.GetWindowRect(child, ctypes.byref(rr))
                bbox = (rr.left, rr.top, rr.right, rr.bottom)
                if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                    return True
                elements.append(GroundedElement(
                    id=_element_id(root_hwnd, role, name, bbox),
                    name=name or role, role=role, bbox=bbox, tier="win32",
                    confidence=0.75, hwnd=child))
            except Exception:
                pass
            return True

        try:
            user32.EnumChildWindows(root_hwnd, _cb, 0)
        except Exception as exc:
            logger.debug("[grounding] EnumChildWindows failed: %s", exc)
        return elements

    # ---- Tier 3: OCR ----
    def _window_png(self, hwnd: int) -> Optional[str]:
        """Capture the window's OWN pixels (PrintWindow): correct while covered or partly
        off-screen. Minimized windows cannot be rendered by Windows -> None + honest note."""
        self._capture_note = ""
        if not (HAS_PIL and _IS_WINDOWS and hwnd):
            self._capture_note = "no-PIL-or-non-windows"
            return None
        img, why = hin.capture_window(hwnd)
        self._capture_note = why
        if img is None:
            logger.debug("[grounding] window capture unavailable: %s", why)
            return None
        if self._unpainted(img):
            # GPU / DirectComposition UIs (CEF clients such as Steam, many Electron shells) are composited only while
            # the window is actually visible: PrintWindow of a hidden one returns just the native frame. OCR and a
            # 46 s vision parse of that would read nothing - say so instead of pretending a tier ran.
            self._capture_note = "unpainted (the window's content was not painted into the capture; it is composited only while visible)"
            logger.debug("[grounding] %s", self._capture_note)
            return None
        try:
            path = os.path.join(os.environ.get("TEMP", "."), f"hj_ground_{hwnd}_{int(time.time()*1000)}.png")
            img.save(path, format="PNG")
            return path
        except Exception as exc:
            self._capture_note = f"save-error: {exc}"
            return None

    @staticmethod
    def _unpainted(img) -> bool:
        """True for a capture that carries no content: near-zero contrast and only a few brightness bands. Measured on
        this host: the unpainted Steam login window = stddev 3.9 / 4 bands; Paint 109 / 27; the plain Win32 test window
        71 / 20."""
        try:
            from PIL import ImageStat
            g = img.convert("L")
            bands = len({v // 8 for v in g.resize((48, 48)).getdata()})
            return ImageStat.Stat(g).stddev[0] < 8.0 and bands <= 6
        except Exception:
            return False

    def _window_origin(self, hwnd: int) -> Tuple[int, int]:
        try:
            import ctypes.wintypes as wt
            rr = wt.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
            return rr.left, rr.top
        except Exception:
            return 0, 0

    def _walk_ocr(self, hwnd: int) -> List[GroundedElement]:
        """OCR of the window's own pixels. ``self._ocr_ran`` says whether OCR really ran (a capture that came back blank,
        unpainted or minimized is NOT an OCR pass that found nothing); ``self._ocr_skip`` carries the reason."""
        self._ocr_ran = False
        self._ocr_skip = ""
        if not (HAS_PYTESSERACT and HAS_PIL):
            self._ocr_skip = "ocr:engine-missing"
            return []
        path = self._window_png(hwnd)
        if not path:
            self._ocr_skip = f"ocr:capture({str(getattr(self, '_capture_note', '') or 'no-capture')[:80]})"
            return []
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(path)
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            self._ocr_ran = True
            ox, oy = self._window_origin(hwnd)
            out: List[GroundedElement] = []
            for i, text in enumerate(data["text"]):
                text = (text or "").strip()
                conf = float(data["conf"][i] or -1)
                if len(text) >= 2 and conf > 60:
                    x, y, w, hgt = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    bbox = (x + ox, y + oy, x + w + ox, y + hgt + oy)
                    out.append(GroundedElement(
                        id=_element_id(hwnd, "text", text, bbox),
                        name=text, role="text", bbox=bbox, tier="ocr",
                        confidence=conf / 100.0, hwnd=hwnd,
                        rel=_rel_of_window(bbox, hwnd)))
            return out
        except Exception as exc:
            logger.debug("[grounding] OCR pass failed: %s", exc)
            return []
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    # ---- Tier 4: OmniParser vision (honest availability only) ----
    # Module-level singleton so the expensive Florence-2 + YOLO load happens ONCE
    # across the entire process lifetime, not on every _walk_vision call.
    _vision_parser = None
    _vision_parser_init_tried = False
    # Background warmup: the 20-250 s model load must never sit in a goal's path.
    _warm: Dict[str, Any] = {"state": "idle", "result": None, "started": 0.0}
    _warm_lock = threading.Lock()

    @classmethod
    def start_warmup(cls) -> str:
        """Kick off the one-time OmniParser load (+ easyocr model fetch) in a daemon thread."""
        if os.environ.get("HOJAIGA_VISION_WARMUP", "1") == "0":
            return "disabled"
        with cls._warm_lock:
            if cls._warm["state"] != "idle":
                return cls._warm["state"]
            cls._warm.update(state="warming", started=time.time())

        def _run():
            res = cls.warmup_vision()
            with cls._warm_lock:
                cls._warm.update(state="ready" if res.get("warmed") else "failed", result=res)
            logger.info("[vision-warmup] %s", res)

        threading.Thread(target=_run, daemon=True, name="vision-warmup").start()
        return "warming"

    @classmethod
    def wait_vision_ready(cls, timeout_s: float = 300.0) -> bool:
        """For tests / explicit callers only; the loop itself never blocks on this."""
        cls.start_warmup()
        end = time.time() + timeout_s
        while time.time() < end:
            if cls._warm["state"] in ("ready", "failed"):
                break
            time.sleep(0.5)
        return cls._warm["state"] == "ready"

    @staticmethod
    def _png_signature(path: str) -> str:
        """Cheap pixel signature (16x16 grayscale hash): same window state => same key."""
        try:
            from PIL import Image
            img = Image.open(path).convert("L").resize((16, 16))
            return hashlib.md5(img.tobytes()).hexdigest()
        except Exception:
            return ""

    @classmethod
    def _get_vision_parser(cls):
        """Process-wide OmniParserScanner singleton (model init is 17-24 s)."""
        if not cls._vision_parser_init_tried:
            cls._vision_parser_init_tried = True
            from core_organs.organ_44_enhanced_scanner import OmniParserScanner
            parser = OmniParserScanner()
            parser._init_model()
            if getattr(parser, "_available", False):
                cls._vision_parser = parser
        p = cls._vision_parser
        return p if p is not None and getattr(p, "_available", False) else None

    @classmethod
    def warmup_vision(cls) -> Dict[str, Any]:
        """One-time warmup: load models AND trigger the lazy easyocr model download on a
        small PNG so no later goal pays a hidden multi-minute stall. Returns timing."""
        t0 = time.time()
        if not (HAS_TORCH and HAS_PIL and os.path.isdir(OMNI_LOCAL_REPO)):
            return {"warmed": False, "reason": "vision-prereqs-missing", "ms": 0}
        path = os.path.join(os.environ.get("TEMP", "."), f"hj_warm_{uuid.uuid4().hex[:6]}.png")
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (240, 90), "white")      # real text so OCR + detector + captioner all run
            dr = ImageDraw.Draw(img)
            dr.rectangle([10, 20, 110, 60], outline="black")
            dr.text((30, 33), "File", fill="black")
            dr.rectangle([125, 20, 225, 60], outline="black")
            dr.text((150, 33), "Save", fill="black")
            img.save(path, format="PNG")
            parser = cls._get_vision_parser()
            if parser is None:
                return {"warmed": False, "reason": "parser-unavailable",
                        "ms": int((time.time() - t0) * 1000)}
            parser.parse_screenshot(path)
            return {"warmed": True, "ms": int((time.time() - t0) * 1000)}
        except Exception as exc:
            return {"warmed": False, "reason": f"{type(exc).__name__}: {exc}",
                    "ms": int((time.time() - t0) * 1000)}
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def _qwen_locate(self, hwnd: int, target_text: str, report: Dict[str, Any]) -> List[GroundedElement]:
        """Targeted vision: ask the local Qwen2.5-VL server (llama.cpp :8081, booted by start_hojaiga.bat) WHERE one named
        control is. Measured on this machine against UIA ground truth: ~4.5 s per control and 90% hits on a plain Win32
        window (Notepad) but only 20% on a dense icon toolbar (Paint), versus 80-260 s for a full OmniParser parse on CPU.
        The postcondition verifier still judges whatever gets clicked, so a wrong box costs time, never a false PASS."""
        if os.environ.get("HOJAIGA_QWEN_VL", "1") == "0" or not (target_text or "").strip():
            return []
        try:
            from core_organs import qwen_vl_scanner as qv
            if not qv.available():
                report.setdefault("tiers_skipped", []).append("vision:qwen-locate(server :8081 not reachable)")
                return []
            img, why = hin.capture_window(hwnd)
            if img is None or self._unpainted(img):
                report.setdefault("tiers_skipped", []).append(f"vision:qwen-locate(no painted capture: {why})")
                return []
            box, meta = qv.locate(img, target_text, backend="llamacpp", timeout_s=40)
            report["vision_engine"] = "qwen-locate"
            report["vision_locate_ms"] = meta.get("ms")
            if not box:
                report.setdefault("tiers_skipped", []).append(f"vision:qwen-locate(no box for '{target_text[:24]}'{': ' + meta['error'][:40] if meta.get('error') else ''})")
                return []
            ox, oy = self._window_origin(hwnd)
            bbox = (int(box[0]) + ox, int(box[1]) + oy, int(box[2]) + ox, int(box[3]) + oy)
            self._vision_ran = True
            return [GroundedElement(id=_element_id(hwnd, "vision", target_text, bbox), name=target_text, role="unknown",
                                    bbox=bbox, tier="vision", confidence=0.5, hwnd=hwnd)]
        except Exception as exc:
            logger.debug("[grounding] qwen locate unavailable: %s", exc)
            return []

    def _walk_vision(self, hwnd: int, report: Optional[Dict[str, Any]] = None, target_text: str = "") -> List[GroundedElement]:
        report = report if report is not None else {}
        self._vision_ran = False
        located = self._qwen_locate(hwnd, target_text, report)
        if located:
            return located
        if not (HAS_TORCH and os.path.isdir(OMNI_LOCAL_REPO) and HAS_PIL):
            return []
        self._vision_ran = False
        state = DesktopGrounding._warm["state"]
        if state in ("idle", "warming"):
            DesktopGrounding.start_warmup()
            report.setdefault("tiers_skipped", []).append("vision:warming-up")
            return []
        if state == "failed" and DesktopGrounding._vision_parser is None:
            report.setdefault("tiers_skipped", []).append("vision:warmup-failed")
            return []
        if self._vision_calls >= VISION_MAX_CALLS:
            report.setdefault("tiers_skipped", []).append("vision:budget-exhausted")
            return []
        path = self._window_png(hwnd)
        if not path:
            report.setdefault("tiers_skipped", []).append(
                f"vision:capture({str(getattr(self, '_capture_note', '') or 'no-capture')[:80]})")
            return []
        try:
            key = (hwnd, self._png_signature(path))
            hit = self._vision_cache.get(key)
            if hit and key[1] and (time.monotonic() - hit[0]) <= VISION_CACHE_TTL_S:
                report["vision_cache_hit"] = True
                self._vision_ran = True
                return list(hit[1])           # same element objects: any captions the background job finished are already in them
            parser = self._get_vision_parser()
            if parser is None:
                report.setdefault("tiers_skipped", []).append("vision:no-parser")
                return []
            self._vision_calls += 1
            self._vision_ran = True
            t_parse = time.time()
            elements = parser.parse_screenshot(path)
            report["vision_parse_ms"] = int((time.time() - t_parse) * 1000)
            report["vision_captions"] = "background" if getattr(parser, "caption_future", None) is not None else "none/sync"
            # parse_screenshot returns image-pixel bounds; the window PNG is a grab
            # of the window rect, so add the window origin to get SCREEN coords.
            ox = oy = 0
            try:
                import ctypes.wintypes as wt
                rr = wt.RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
                ox, oy = rr.left, rr.top
            except Exception:
                pass
            out: List[GroundedElement] = []
            src_of: List[Tuple[GroundedElement, Any]] = []
            for e in elements:
                b = e.bounds
                screen_bbox = (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy)
                ge = GroundedElement(
                    id=_element_id(hwnd, e.role, e.text, screen_bbox),
                    name=e.text or ("icon" if e.role != "text" else "vision"), role=e.role, bbox=screen_bbox,
                    tier="vision", confidence=float(e.confidence or 0.35), hwnd=hwnd,
                    rel=_rel_of_window(screen_bbox, hwnd))
                out.append(ge)
                src_of.append((ge, e))
            fut = getattr(parser, "caption_future", None)
            if fut is not None:
                def _fill(_f, _pairs=src_of):
                    """Background captions finished: write the names into the SAME GroundedElement objects the cache holds."""
                    try:
                        for ge_, e_ in _pairs:
                            if e_.text and ge_.name in ("icon", "vision"):
                                ge_.name = e_.text
                    except Exception:
                        pass
                fut.add_done_callback(_fill)
            if key[1]:
                self._vision_cache[key] = (time.monotonic(), out)           # the cache holds the live objects: captions land in them
                if len(self._vision_cache) > 8:
                    self._vision_cache.pop(next(iter(self._vision_cache)))
            return out
        except Exception as exc:
            logger.debug("[grounding] vision pass unavailable: %s", exc)
            return []
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    # ---- capture-restore-capture rung for MINIMIZED windows ----
    def _await_paint(self, hwnd: int, timeout_s: float = 6.0) -> float:
        """A window that was just un-minimized off-screen needs a moment before PrintWindow returns real
        pixels (XAML / Chromium repaint lazily). Poll with a small growing delay, bounded; returns seconds.
        A WinUI window that still has not painted after ~1 s is nudged once with a shallow UIA read - touching its
        accessibility tree makes it lay out and compose (measured: Paint rendered blank for 3 s inside a long process
        and fine on a fresh one)."""
        t0 = time.perf_counter()
        delay = 0.15
        nudged = False
        while time.perf_counter() - t0 < timeout_s:
            img, _why = hin.capture_window(hwnd)
            if img is not None:
                break
            if not nudged and time.perf_counter() - t0 > 1.0 and HAS_UIA:
                nudged = True
                try:
                    self._walk_uia(hwnd, max_depth=3, max_nodes=60)
                except Exception:
                    pass
            time.sleep(delay)
            delay = min(delay * 1.5, 0.5)
        return time.perf_counter() - t0

    def _ground_offscreen(self, hwnd: int, report: Dict[str, Any], max_tier: int,
                          target_text: str = "") -> Tuple[List[GroundedElement], bool]:
        """Perception for a MINIMIZED window whose structure missed the target. The window is PARKED off-screen
        (background_window: restored, never on a monitor, never activated), read, then re-minimized exactly as it
        was. Never a visible restore.

          1. UIA again, now that the window is laid out (a parked tree is far richer than a minimized one:
             measured 22 -> 56+ controls for the same Notepad). If the target is there, stop - no pixels needed.
          2. otherwise OCR, then vision, over the window's OWN pixels (PrintWindow).

        Guards: a window the user can currently SEE that we did not launch is not touched - the rung refuses and
        the report says to escalate. Everything measured goes into report['offscreen'].
        Returns (elements, replace_structural)."""
        from core_organs import background_window as bw
        rep: Dict[str, Any] = {"used": False}
        report["offscreen"] = rep
        out: List[GroundedElement] = []
        t_all = time.perf_counter()
        if not bw.ENABLED:
            rep["refused"] = "parking-disabled(HOJAIGA_PARK_MINIMIZED=0)"
            report["tiers_skipped"] += ["ocr:offscreen-disabled", "vision:offscreen-disabled"]
            return out, False
        rep["ours"] = bw.is_ours(hwnd)
        if not rep["ours"] and bw.user_can_see(hwnd):
            rep.update(refused="user-can-see", escalate_to_human=True)
            report["tiers_skipped"] += ["ocr:offscreen-refused(user-can-see)", "vision:offscreen-refused(user-can-see)"]
            return out, False
        replace = False
        with bw.BackgroundSession(hwnd) as sess:
            rep["mode"] = sess.mode
            rep["park_ms"] = round((time.perf_counter() - t_all) * 1000, 1)
            if sess.mode != "parked":
                rep["refused"] = f"could not park ({sess.mode})"
                report["tiers_skipped"] += [f"ocr:offscreen-{sess.mode}", f"vision:offscreen-{sess.mode}"]
            else:
                rep["used"] = True
                rep["paint_wait_ms"] = round(self._await_paint(hwnd) * 1000, 1)
                via: List[str] = []
                resolved = False
                if HAS_UIA:
                    _t = time.perf_counter()
                    parked = self._walk_uia(hwnd)
                    for w in hin.popup_windows(hwnd)[:10]:
                        parked.extend(self._walk_uia(w, max_depth=8, max_nodes=300))
                    report["tier_ms"]["uia@offscreen"] = round((time.perf_counter() - _t) * 1000, 1)
                    report["tiers_ran"].append("uia@offscreen")
                    rep["uia_parked_elements"] = len(parked)
                    if parked:
                        out, replace = parked, True
                    resolved = bool(target_text) and any(target_text.lower() in e.name.lower() for e in parked)
                    if resolved:
                        rep["resolved_by"] = "uia-parked"
                        via.append("uia:offscreen-capture")
                if not resolved:
                    if HAS_PYTESSERACT and HAS_PIL:
                        _t = time.perf_counter()
                        ocr_els = self._walk_ocr(hwnd)
                        report["tier_ms"]["ocr"] = round((time.perf_counter() - _t) * 1000, 1)
                        note = str(getattr(self, "_capture_note", ""))
                        if getattr(self, "_ocr_ran", False):
                            out = out + ocr_els
                            report["tiers_ran"].append("ocr")
                            via.append("ocr:offscreen-capture")
                        else:
                            # The window did not render into PrintWindow even after the paint wait (an unpainted GPU/
                            # XAML surface, or a WinUI window that stops composing while off-screen): there is nothing
                            # for OCR or vision to read, and saying either "ran" would be a fabricated tier.
                            rep["content_painted"] = False
                            rep["escalate_to_human"] = True
                            rep["capture_note"] = note[:120]
                            report["tiers_skipped"] += [str(getattr(self, "_ocr_skip", "") or "ocr:offscreen-capture(no capture)"),
                                                        f"vision:offscreen-capture(no painted capture: {note[:60]})"]
                            max_tier = min(max_tier, 3)             # do not spend a 46 s vision parse on an empty frame
                    else:
                        report["tiers_skipped"].append("ocr:engine-missing")
                    if rep.get("content_painted") is False:
                        pass                                        # already reported above
                    elif max_tier >= 4 and HAS_TORCH:
                        _t = time.perf_counter()
                        vis = self._walk_vision(hwnd, report, target_text)
                        report["tier_ms"]["vision"] = round((time.perf_counter() - _t) * 1000, 1)
                        if getattr(self, "_vision_ran", False):
                            report["tiers_ran"].append("vision")
                            via.append("vision:offscreen-capture")
                        else:
                            report["tiers_skipped"].append("vision:offscreen-capture(not run: see vision:* reason)")
                        out = out + vis
                    elif max_tier >= 4:
                        report["tiers_skipped"].append("vision:torch-missing")
                    else:
                        report["tiers_skipped"].append("vision:offscreen-capture(cap)")
                rep["tiers_via"] = via
        rep["round_trip_ms"] = round((time.perf_counter() - t_all) * 1000, 1)     # includes the verified re-minimize
        rep["ended_minimized"] = hin.is_minimized(hwnd)
        if rep["used"] and not rep["ended_minimized"]:
            report["tiers_skipped"].append("offscreen:NOT-reminimized")           # loud: the window is somewhere it should not be
        return out, replace

    # ---- public API ----
    def ground(self, app_hint: str, target_text: str = "",
               max_tier: int = 2) -> Tuple[Optional[int], List[GroundedElement], Dict[str, Any]]:
        """Returns (hwnd, elements, ladder_report).

        max_tier: 1 uia only, 2 +win32 (default; ms-level fast), 3 +ocr, 4 +vision.
        Escalation past tier 2 happens automatically ONLY when the caller is
        looking for target_text and the structural tiers found no match — this
        is the 'after 2 UIA misses' rule from the plan.
        """
        hwnd = self.find_window(app_hint)
        report = {"app_hint": app_hint, "hwnd": hwnd, "tiers_ran": [], "tiers_skipped": [],
                  "escalated": False, "tier_ms": {}}
        if not hwnd:
            report["reason"] = "window-not-found"
            return None, [], report

        elements: List[GroundedElement] = []
        if HAS_UIA:
            _t = time.perf_counter()
            elements = self._walk_uia(hwnd)
            report["tier_ms"]["uia"] = round((time.perf_counter() - _t) * 1000, 1)
            report["tiers_ran"].append("uia")
        else:
            report["tiers_skipped"].append("uia:no-uiautomation")

        # Menus, flyouts and dialogs are separate top-level windows of the SAME process; a UIA
        # walk of the main frame cannot see them. Ground them too (bounded).
        if HAS_UIA:
            extra = hin.popup_windows(hwnd)[:10]
            for w in extra:
                elements.extend(self._walk_uia(w, max_depth=8, max_nodes=300))
            if extra:
                report["popup_windows"] = len(extra)
        report["window_state"] = hin.window_state(hwnd).get("state")
        lw = getattr(self, "last_walk", None)
        if lw and lw.get("grid_cells_seen"):
            report["grid"] = dict(lw)          # honest: how many grid cells exist vs how many were surfaced

        if not elements and max_tier >= 2:
            _t = time.perf_counter()
            elements = self._walk_win32(hwnd)
            report["tier_ms"]["win32"] = round((time.perf_counter() - _t) * 1000, 1)
            report["tiers_ran"].append("win32")

        need_target = bool(target_text)
        structural_miss = not any(target_text.lower() in e.name.lower() for e in elements)

        if need_target and structural_miss and report["window_state"] == "minimized":
            # Windows does not render a minimized window, so a pixel tier cannot read it AS IT IS. It can read it
            # off-screen: park it (restored, never on a monitor, never activated), capture, re-minimize exactly as
            # it was. Only reached when UIA/Win32 already missed the target - an app grounded structurally never
            # pays this round trip.
            report["escalated"] = True
            if max_tier >= 3:
                extra, replace = self._ground_offscreen(hwnd, report, max_tier, target_text)
                if replace:
                    elements = extra          # the parked window's own UIA tree supersedes the degraded minimized one
                else:
                    elements.extend(extra)
            else:
                report["tiers_skipped"] += ["ocr:window-minimized", "vision:window-minimized"]
        elif need_target and structural_miss:
            report["escalated"] = True
            if HAS_PYTESSERACT and HAS_PIL and max_tier >= 3:
                _t = time.perf_counter()
                ocr = self._walk_ocr(hwnd)
                report["tier_ms"]["ocr"] = round((time.perf_counter() - _t) * 1000, 1)
                if getattr(self, "_ocr_ran", False):
                    report["tiers_ran"].append("ocr")
                else:
                    report["tiers_skipped"].append(getattr(self, "_ocr_skip", "") or "ocr:no-capture")
                elements.extend(ocr)
            elif max_tier >= 3:
                report["tiers_skipped"].append("ocr:engine-missing")
                if max_tier < 4:
                    report["tiers_skipped"].append("ocr:cap")
            if HAS_TORCH and max_tier >= 4:
                _t = time.perf_counter()
                vis = self._walk_vision(hwnd, report, target_text)
                report["tier_ms"]["vision"] = round((time.perf_counter() - _t) * 1000, 1)
                if getattr(self, "_vision_ran", False):
                    report["tiers_ran"].append("vision")
                elements.extend(vis)
            elif max_tier >= 4:
                report["tiers_skipped"].append("vision:torch-missing")

        # Dedup by id, sort confident-first then top-to-bottom.
        uniq: Dict[str, GroundedElement] = {}
        for e in elements:
            if e.id not in uniq or e.confidence > uniq[e.id].confidence:
                uniq[e.id] = e
        final = sorted(uniq.values(), key=lambda e: (-e.confidence, e.bbox[1]))
        report["element_count"] = len(final)
        self.last_report = report
        return hwnd, final, report


# ---------------------------------------------------------------------------
# W2 — DesktopVerifier: outcome assertions (the trust core)
# ---------------------------------------------------------------------------

# Pixel-delta tolerance. The window is reduced to a small grayscale thumbnail quantized into
# REGION_LEVEL_BANDS brightness bands, and a change only counts when at least
# REGION_MIN_CHANGED_FRACTION of the cells moved. Two reasons, both measured on real windows:
# an exact-byte hash of a screen grab let a blinking caret / ticking clock read as "the app
# reacted", and it hashed whatever window was ON TOP of the target. The measured fraction always
# goes into the evidence string, so a suppressed small change stays visible to a human.
REGION_THUMB_SIZE = (48, 48)
REGION_LEVEL_BANDS = 16
REGION_MIN_CHANGED_FRACTION = 0.02


@dataclass
class Snapshot:
    title: str
    element_ids: List[str]
    region_hash: str = ""
    region_thumb: bytes = b""
    region_source: str = ""
    text: str = ""
    names: List[str] = field(default_factory=list)   # EVERY UIA name (text/labels too); filled only when a postcondition asks
    # MODE indicators read from the same pass: 'name|selected' (tab / list item / radio / tool that is on) and
    # 'name|expanded' (an open menu / combo / tree node). An app's mode is state the structure hash cannot see.
    modes: List[str] = field(default_factory=list)

    def signature(self) -> str:
        return hashlib.md5(("|".join(sorted(self.element_ids)) + self.title).encode("utf-8")).hexdigest()


_TITLEBAR_NAMES = frozenset({"close", "minimize", "maximize", "restore", "restore down", "system", "system menu"})


def _titlebar_buttons(elements, hwnd: int) -> set:
    """ids (python id()) of the window's OWN title-bar buttons. 'Close' is not in the generic chrome list (an app has its own Close), so a title-bar Close is
    recognised by WHERE it is: inside the window's title-bar band, or beside a 'titlebar' element when the tree gives no geometry. Pressing it for an
    in-app goal closes the app (measured: a sign-in screen was 'completed' by pressing Close)."""
    out = set()
    try:
        import ctypes.wintypes as _wt
        import re as _re
        r = _wt.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
        title = (hin.safe_window_text(int(hwnd)) or "").strip().lower()
        _CAPTION_VERBS = ("minimize", "maximize", "restore", "close", "min", "max")

        def _is_caption(nm: str) -> bool:
            # Bare 'Minimize' / 'Close', OR the UWP / WPF style '<verb> <window title>' ('Minimize Settings').
            # The trailing word is matched against the window's OWN title, so this stays generic (no app table).
            # Pressing 'Minimize Settings' for an in-app goal only shrinks the window - it is chrome, never a step.
            if nm in _TITLEBAR_NAMES:
                return True
            m = _re.match(r"^(%s)\b(?:\s+(.+))?$" % "|".join(_CAPTION_VERBS), nm)
            if not m:
                return False
            tail = (m.group(2) or "").strip()
            if not tail:
                return True
            return bool(title) and (tail == title or tail in title or title in tail)
        names = {(e.name or "").strip().lower() for e in elements if (e.role or "").lower() not in ("window", "pane", "titlebar", "text", "image", "")}
        has_bar = any((e.role or "").lower() == "titlebar" for e in elements) or any(_is_caption(n) for n in names)   # Close beside Minimize / Maximize IS the title bar
        only_chrome = bool(names) and all(_is_caption(n) for n in names)                                             # nothing else is on screen at all
        for e in elements:
            if not _is_caption((e.name or "").strip().lower()):
                continue
            b = e.bbox or (0, 0, 0, 0)
            geometric = any(b) and (r.top - 4) <= b[1] <= (r.top + 48) and (b[3] - b[1]) <= 48
            if geometric or only_chrome or (has_bar and not any(b)):
                out.add(id(e))
    except Exception:  # noqa: BLE001
        pass
    return out


class DesktopVerifier:
    def snapshot(self, hwnd: int, elements: List[GroundedElement], text: str = "") -> Snapshot:
        snap = Snapshot(title=_quick_title(hwnd), element_ids=[e.id for e in elements], text=text)
        snap.region_hash, snap.region_thumb, snap.region_source = self._region_capture(hwnd)
        return snap

    def _region_capture(self, hwnd: int) -> Tuple[str, bytes, str]:
        """(hash, quantized thumbnail, capture source) of the window's OWN pixels.

        PrintWindow is tried first because a screen grab of the window rect hashes whatever is on
        top, so an occluded app could fake both a change and a no-change. A screen grab is still
        used as a fallback (some GPU windows return no PrintWindow content) but the source tag
        says so — the fallback is never silent. Minimized windows are not rendered by Windows, so
        no fallback happens there: grabbing their parked 1x1 rect would be meaningless noise.
        """
        if not (HAS_PIL and _IS_WINDOWS and hwnd):
            return "", b"", "unavailable"
        img, why = None, "no-capture"
        try:
            img, why = hin.capture_window(hwnd)
        except Exception as exc:
            img, why = None, f"error({type(exc).__name__})"
        if img is not None:
            return self._thumb_pair(img, "printwindow")
        if why == "window-minimized":
            return "", b"", "window-minimized"
        try:
            from PIL import ImageGrab
            import ctypes.wintypes as wt
            rr = wt.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
            if rr.right - rr.left < 8 or rr.bottom - rr.top < 8:
                return "", b"", f"no-usable-rect({why})"
            img = ImageGrab.grab(bbox=(rr.left, rr.top, rr.right, rr.bottom))
        except Exception as exc:
            return "", b"", f"capture-failed({why}/{type(exc).__name__})"
        if img is None:
            return "", b"", f"capture-failed({why})"
        return self._thumb_pair(img, "screen-grab-fallback")

    @staticmethod
    def _thumb_pair(img, source: str) -> Tuple[str, bytes, str]:
        try:
            thumb = DesktopVerifier._region_thumb(img)
        except Exception as exc:
            return "", b"", f"thumb-error({type(exc).__name__})"
        return hashlib.md5(thumb).hexdigest(), thumb, source

    @staticmethod
    def _region_thumb(img) -> bytes:
        """Grayscale, fixed 48x48, quantized into REGION_LEVEL_BANDS bands."""
        gray = img.convert("L").resize(REGION_THUMB_SIZE)
        band = 256 // REGION_LEVEL_BANDS
        return bytes(min(REGION_LEVEL_BANDS - 1, px // band) for px in gray.getdata())

    def _region_hash(self, hwnd: int) -> str:
        """Kept as the hash-only entry point (organ_48 uses it)."""
        return self._region_capture(hwnd)[0]

    @staticmethod
    def pixels_changed(before: Snapshot, after: Snapshot) -> Tuple[bool, str]:
        """Tolerance-based pixel delta -> (changed, evidence carrying the measured fraction)."""
        if not (before.region_hash and after.region_hash):
            # Name the side that failed and why, so 'no pixel evidence' is never mistaken for
            # 'pixels proved nothing changed' (a minimized window is not rendered by Windows).
            missing = before if not before.region_hash else after
            which = "before" if missing is before else "after"
            return False, f"region pixel-delta unavailable({which}:{missing.region_source or 'no-capture'})"
        b, a = before.region_thumb, after.region_thumb
        if b and a and len(b) == len(a):
            moved = sum(1 for x, y in zip(b, a) if x != y)
            fraction = moved / float(len(b))
            ok = fraction >= REGION_MIN_CHANGED_FRACTION
            return ok, (f"region pixel-delta {fraction:.3f} of cells via "
                        f"{after.region_source or before.region_source} "
                        + ("detected" if ok else "below tolerance"))
        ok = before.region_hash != after.region_hash
        return ok, "region pixel-delta " + ("detected" if ok else "none")

    def _file_proof(self, p: str, since: Optional[float]) -> Tuple[bool, str]:
        """Did the app WRITE this file, or was it just there?

        `since` is the wall-clock moment the goal began (None keeps the old existence-only behaviour).
        A save lands in the same second the goal can start, so 1 s of slack is allowed; nothing larger
        is, because the whole point is refusing a stale file from a previous run."""
        _end = time.time() + 3.0                      # bounded: apps write asynchronously
        name = os.path.basename(p)
        st = None
        while True:
            try:
                st = os.stat(p)
            except OSError:
                st = None
            if st is not None and (since is None or st.st_mtime >= float(since) - 1.0):
                break
            if time.time() >= _end:
                break
            time.sleep(0.25)
        if st is None:
            return False, f"file {name} MISSING"
        if st.st_size <= 0:
            return False, f"file {name} exists but is 0 bytes (nothing was written)"
        if since is not None and st.st_mtime < float(since) - 1.0:
            age = float(since) - st.st_mtime
            return False, (f"file {name} was ALREADY on disk before this goal "
                           f"(written {age:.0f}s earlier) — not proof we saved it")
        return True, (f"file {name} written ({st.st_size} bytes"
                      + (f", {time.time() - float(since):.1f}s after goal start" if since is not None
                         else "") + ")")

    def check_expect(self, expect: Dict[str, Any], before: Snapshot,
                     after: Snapshot, elements_now: List[GroundedElement]) -> Tuple[bool, str]:
        """Evaluate a postcondition dict. Returns (ok, evidence)."""
        if not expect:
            # Default postcondition: something about the UI changed. Three independent signals: the structure of
            # the actionable controls, the window's own pixels (tolerance-based), and the set of EVERY UIA name
            # (read-outs and labels included - pressing an operator key on a keypad changes a text label and
            # almost no pixels, which the first two cannot see). Still "something changed", still reported weak.
            pixel_changed, pixel_evidence = self.pixels_changed(before, after)
            nb, na = set(before.names or ()), set(after.names or ())
            names_changed = bool(nb and na and nb != na)
            mb, ma = set(before.modes or ()), set(after.modes or ())
            modes_changed = bool(mb or ma) and mb != ma
            changed = before.signature() != after.signature() or pixel_changed or names_changed or modes_changed
            name_note = f"; names +{len(na - nb)}/-{len(nb - na)}" if names_changed else ""
            if modes_changed:
                name_note += f"; modes +{sorted(ma - mb)[:3]}/-{sorted(mb - ma)[:3]}"
            return changed, f"ui-{'changed' if changed else 'unchanged'}; {pixel_evidence}{name_note}"

        checks: List[Tuple[bool, str]] = []
        if "title_contains" in expect:
            ok = str(expect["title_contains"]).lower() in after.title.lower()
            checks.append((ok, f"title={'has' if ok else 'missing'}'{expect['title_contains']}'"))
        if "element_appeared" in expect:
            want = str(expect["element_appeared"]).lower()
            ok = any(want in (e.name or "").lower() for e in elements_now)
            checks.append((ok, f"element '{want}' {'present' if ok else 'absent'}"))
        if "element_disappeared" in expect:
            want = str(expect["element_disappeared"]).lower()
            ok = not any(want in (e.name or "").lower() for e in elements_now)
            checks.append((ok, f"element '{want}' {'gone' if ok else 'still-present'}"))
        if "text_contains" in expect:
            want = str(expect["text_contains"])
            hay = after.text or ""
            # Compare WORDS, not line-break bytes: Notepad's RichEdit stores a typed "\n" as "\r" (and other editors as
            # "\r\n"), so a multi-line haiku was reported MISSING right after it had been typed in, and the retry then
            # typed it again (the document filled with duplicates).
            _flat = lambda t: re.sub(r"\s+", " ", t).strip().lower()
            ok = bool(want) and _flat(want) in _flat(hay)
            checks.append((ok, f"text {'has' if ok else 'MISSING'} '{want[:24]}'"
                          + ("" if hay else " (control text unreadable)")
                          + f" [read {len(hay)} chars]"))
        if "name_visible" in expect:
            # Some control on screen (labels and read-outs included, not just actionable ones) carries this text.
            # A number must match as a whole number: '56' is not satisfied by 'Display is 156'.
            want = str(expect["name_visible"]).strip().lower()
            pat = (re.compile(r"(?<![\d.,])" + re.escape(want) + r"(?![\d]|[.,]\d)")
                   if re.fullmatch(r"-?[\d.,]+", want or "") else None)
            ok = bool(want) and any((pat.search(n) if pat else want in n) for n in (after.names or []))
            checks.append((ok, f"name '{want[:24]}' {'visible' if ok else 'NOT visible'} among {len(after.names or [])} UIA names"))
        if "mode_on" in expect:
            # the named control is SELECTED / EXPANDED now (active tool, open tab, checked radio, open menu)
            want = str(expect["mode_on"]).strip().lower()
            ok = any(m.split("|", 1)[0] == want or want in m.split("|", 1)[0] for m in (after.modes or []))
            checks.append((ok, f"mode '{want}' {'on' if ok else 'NOT on'} among {len(after.modes or [])} mode indicator(s)"))
        if "file_created" in expect or "file_saved" in expect:
            target_path = expect.get("file_created") or expect.get("file_saved")
            p = os.path.abspath(str(target_path))
            # "The file exists" is NOT the proof of "we made it". Measured 2026-10-05: an Excel run was
            # reported as a success because e1.xlsx from an earlier, killed run was still sitting on disk —
            # the loop had saved nothing. So when the caller says when the goal started
            # (`file_fresh_since`), the file must have been WRITTEN after that moment, not merely be there.
            ok, note = self._file_proof(p, expect.get("file_fresh_since"))
            checks.append((ok, note))
            if ok and expect.get("file_format"):
                fmt_ok, fmt_note = file_has_format(p, str(expect["file_format"]))
                checks.append((fmt_ok, fmt_note))
        if "file_text_contains" in expect:
            # A file can be WRITTEN and still hold nothing: a workbook was measured saved to the exact path with
            # an EMPTY sheet, because 'exists + has bytes' was the whole proof. The text the run was told to put
            # in is checked inside the file itself.
            tk, tnote = file_holds_text(p, str(expect["file_text_contains"]))
            _nm = os.path.basename(p)
            if tk is None:
                checks.append((True, f"content of {_nm} not checkable ({tnote})"))
            else:
                checks.append((tk, f"content of {_nm}: {tnote}"))
        if "region_changed" in expect and bool(expect["region_changed"]):
            checks.append(self.pixels_changed(before, after))
        return all(c[0] for c in checks), "; ".join(c[1] for c in checks) or "no-expect"

    _MAY_CLOSE_RE = re.compile(r"\b(close|exit|quit|dismiss|cancel|ok|accept|decline|done|apply|save|submit|discard|yes|no|finish|sign ?out|log ?out|shut)\b", re.I)

    # A goal that asks to REACH a named PLACE. Deliberately narrow so it only fires on the bug class it was
    # made for (a navigation that lands on the wrong screen) and never on 'open the File menu' or 'open
    # <app>' (those are proved by the change itself, not by a named destination screen). It demands a
    # SURFACE word ('page', 'tab', 'screen', ...) so the destination is an explicit, named place.
    _NAV_GOAL_RE = re.compile(
        r"\b(?:open|go\s+to|goto|navigate\s+to|switch\s+to|jump\s+to|show|reveal)\b\s+(?:the\s+|your\s+|a\s+)?(.+?)\s+"
        r"\b(page|tab|screen|section|panel|view)\b",
        re.I)
    # Words describing the ACTION or the generic surface, never the destination itself. Stripped from the
    # captured phrase so 'open the About page' demands 'about', not 'open'/'page'. Generic UI vocabulary
    # only - no app names, no screen names - so this stays universal.
    _NAV_STOP = frozenset({
        "open", "go", "to", "goto", "navigate", "switch", "jump", "show", "reveal", "the", "a", "an",
        "page", "tab", "screen", "section", "panel", "view", "window", "menu", "settings", "options",
        "and", "then", "it", "its", "this", "that", "in", "on", "of", "for", "with", "my", "please",
    })

    def _nav_destination(self, goal: str) -> List[str]:
        """The destination words a navigation goal demands, [] if this is not a 'reach a named place' goal."""
        if not goal:
            return []
        m = self._NAV_GOAL_RE.search(goal)
        if not m:
            return []
        toks = [t for t in re.findall(r"[a-z0-9]+", m.group(1).lower()) if t not in self._NAV_STOP and len(t) > 1]
        return toks

    def verdict(self, expect: Dict[str, Any], before: Snapshot, after: Snapshot,
                elements_now: List[GroundedElement], goal: str = "") -> Tuple[str, str]:
        """PASS / NO_CHANGE / WRONG_STATE with evidence."""
        if (goal and not expect and before.title and not after.title and not elements_now and not after.region_hash
                and not self._MAY_CLOSE_RE.search(goal)):
            # the default postcondition is 'something changed', and a window that is GONE has changed more than anything: pressing a title-bar Close on a
            # sign-in screen passed 'open the Library tab' (measured). Closing the window is only progress for a goal that talks about closing / answering.
            return "WRONG_STATE", f"the window disappeared: closing it is not progress toward '{goal[:50]}'"
        ok, evidence = self.check_expect(expect, before, after, elements_now)
        if ok:
            # A navigation goal whose ONLY proof is 'the UI moved' is not done until the destination it named is
            # actually on screen. Measured on a UWP app: 'open the About page' clicked the account button, the
            # window genuinely changed (pixel-delta .3, +73 names), and the old lax postcondition PASSed it as
            # About while the app had opened Accounts. The destination word is read from the goal itself and
            # matched against the new screen's own UIA names/modes - generic, no per-app screen table.
            if not expect:
                dest = self._nav_destination(goal)
                if dest:
                    hay = " ".join((after.names or []) + (after.modes or []))
                    if not any(d in hay for d in dest):
                        return "WRONG_STATE", (f"ui-changed but not at the named destination {dest}: "
                                               f"'{goal[:40]}' - the destination word is absent from the new screen")
            return "PASS", evidence
        pixel_moved, _ = self.pixels_changed(before, after)
        structurally_dead = before.signature() == after.signature() and not pixel_moved
        if expect and structurally_dead:
            return "NO_CHANGE", evidence
        if structurally_dead:
            return "NO_CHANGE", evidence
        return "WRONG_STATE", evidence


# Module-level verifier facade alias per Workstream 2
desktop_verifier = DesktopVerifier()

# Postconditions that a single step CANNOT honestly be graded by: they live outside the app's UI.
# `file_fresh_since` travels WITH the file it timestamps (the moment the goal began): split it off and the
# split below would see a leftover key, judge every intermediate step (clicking File) by "the file must be
# written by now", and the WRONG_STATE would erode a command that was actually right.
TERMINAL_EXPECT_KEYS = ("file_created", "file_saved", "file_format", "file_fresh_since", "file_text_contains")


def split_terminal_expect(expect: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Separate a goal's TERMINAL proof from what one step of the chain can be graded by.

    'save the document as D:\\x\\poem.txt' has exactly one postcondition: the file on disk. Applied to every
    step, clicking File - which correctly opened the menu - could only ever be WRONG_STATE, and that cost two
    real things: the command was eroded in knowledge as a FAILURE, and the control was marked spent, so the
    learned re-run could not re-select it and wandered (measured: E2E-1 run2 = 12 unrelated clicks).
    A step is now graded by 'the UI moved toward the goal' and the GOAL advances only when the file is really
    there. A postcondition that mixes UI and terminal parts is left whole - every part of it stays checked."""
    term = {k: v for k, v in (expect or {}).items() if k in TERMINAL_EXPECT_KEYS}
    if not term:
        return dict(expect or {}), None
    rest = {k: v for k, v in expect.items() if k not in TERMINAL_EXPECT_KEYS}
    if rest:
        return dict(expect), None
    return {}, term


def _quick_title(hwnd: int) -> str:
    if not (_IS_WINDOWS and hwnd):
        return ""
    try:
        import ctypes.wintypes as wt
        return hin.safe_window_text(int(hwnd))
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# W3 — ConstrainedJudge: forced choice, never open-ended generation
# ---------------------------------------------------------------------------

class ConstrainedJudge:
    """Asks the local model to pick ONE numbered element + ONE legal verb.

    A multiple-choice answer is a task 7B models do reliably; free-form tool
    selection (what caused the live-run flailing) is not. Invalid answers are
    surfaced, and the loop escalates to HITL after INVALID_CHOICE_LIMIT misses.
    """

    model: Optional[str] = None   # per-instance override of JUDGE_MODEL (used by model benchmarks)
    _TYPE_WORDS = ("type", "write", "enter", "input", "compose", "fill", "paste", "text")
    _TEXT_ROLES = ("edit", "document", "combobox")
    # file extension -> the words a format menu uses for it (generic file formats, not app names)
    _FORMAT_WORDS = {"jpg": ("jpeg", "jpg"), "jpeg": ("jpeg", "jpg"), "tif": ("tiff", "tif"), "tiff": ("tiff", "tif"),
                     "htm": ("html", "htm"), "html": ("html", "htm")}
    _STOP = frozenset({"the", "a", "an", "to", "in", "into", "on", "of", "and", "then", "it",
                       "for", "with", "as", "at", "by", "from", "this", "that", "my"})

    @classmethod
    def rank_candidates(cls, goal: str, elements: List[GroundedElement],
                        pro_hint: Optional[Dict[str, Any]] = None) -> List[Tuple[int, GroundedElement]]:
        return [(i, e) for _sc, i, e in cls.rank_scored(goal, elements, pro_hint)]

    @classmethod
    def _conventional_menu(cls, g: str, elements: List["GroundedElement"]) -> str:
        """The top-level menu a command conventionally lives under, when the command itself is NOT among the elements on screen ('' otherwise)."""
        for menu, verbs in cls._MENU_CONVENTION.items():
            if re.search(r"\b(?:" + "|".join(verbs) + r")\b", g) and not any((e.name or "").strip().lower() in verbs for e in elements):
                return menu
        return ""

    @classmethod
    def rank_scored(cls, goal: str, elements: List[GroundedElement],
                    pro_hint: Optional[Dict[str, Any]] = None) -> List[Tuple[float, int, GroundedElement]]:
        """Goal-aware shortlist. Truncating to the first N by confidence/y hid the very
        control the goal named (a 58-element Notepad tree never offered its text area).
        Score = lexical overlap(goal, element name) + role affinity for the goal's intent
        + expert-hint match + the grounding confidence as a tie-break. Generic: no app names.
        """
        g = cls._PATH_TOKEN_RE.sub(" ", (goal or "").lower())  # a path's tokens are not UI words
        gtoks = cls._goal_tokens(goal)
        save_as = bool(re.search(r"\bsave\b.{0,40}\bas\b", g)) or bool(re.search(r"\bsave as\b", g)) or (bool(re.search(r"\bsave\b", (goal or "").lower())) and bool(re.search(r"[a-z]:[\\/]", (goal or "").lower())))
        file_verb = bool(re.search(r"\b(save|open|export|import|print|close|exit)\b", g))
        wants_text = cls._wants_text(goal)
        has_path = bool(re.search(r"[a-z]:[\\/]", (goal or "").lower()))
        # which top-level menu a command conventionally lives under, when the command itself is not among the elements on screen
        menu_for_goal = cls._conventional_menu(g, elements)
        hint_segments = [x.strip().lower() for x in ((pro_hint or {}).get("menu_path") or "").split(">") if x.strip()]
        if not hint_segments and (pro_hint or {}).get("element_name"):
            hint_segments = [pro_hint["element_name"].strip().lower()]
        hint_name = ((pro_hint or {}).get("element_name") or (pro_hint or {}).get("menu_path") or "").lower()
        # The file FORMAT the goal's path asks for ('...\a.png'): a "Save as" submenu that lists formats (Paint offers
        # "PNG picture" next to "Save as project") must be answered with the matching format, not the first "Save as".
        ext_m = re.search(r"[a-z]:[\\/][^'<>|?*\r\n]*?\.([a-z0-9]{2,5})(?![a-z0-9])", (goal or "").lower())
        fmt_words = set(cls._FORMAT_WORDS.get(ext_m.group(1), (ext_m.group(1),))) if ext_m else set()
        scored = []
        # SURFACE, not label, is what a typed payload asks for. Measured on a spreadsheet: 'type 42 in cell A1'
        # gave every edit the same role score and the tie-break (y-position, top first) picked the name/reference
        # strip - so '42' went into the box that NAVIGATES cells instead of a cell, the workbook saved empty, and
        # the goal still looked done because a UI change is a UI change. A bigger text surface is the document;
        # a one-line strip is an address/reference/search box. Kept below the lexical score on purpose: a goal
        # that NAMES a small box ('type gmail.com in the address bar') still wins.
        max_text_area = max((abs(e.bbox[2] - e.bbox[0]) * abs(e.bbox[3] - e.bbox[1])
                             for e in elements if e.role in cls._TEXT_ROLES), default=0)
        for i, e in enumerate(elements):
            name = (e.name or "").lower()
            ntoks = set(re.findall(r"[a-z0-9]+", name))
            score = 3.0 * len(gtoks & ntoks)
            if name.strip() in cls._WINDOW_CHROME and not (gtoks & cls._CHROME_GOAL_WORDS):
                score -= 60.0           # the window's own title-bar buttons are never a step toward an in-app goal (measured: an Office save
                                        # goal looped Minimize / Restore forever, each a 'UI changed' pass)
            if fmt_words and e.role in ("menuitem", "listitem", "button") and (fmt_words & ntoks):
                score += 25.0           # the requested format outranks any learned hint (a hint once taught "Save as project")
            score += 1.5 * sum(1 for t in gtoks if len(t) > 3 and t in name and t not in ntoks)
            if save_as and e.role in ("menuitem", "listitem", "button", "tabitem", "treeitem") and name.startswith("save as"):
                score += 7.0   # an explicit target path/name means Save AS, not in-place Save (a ribbon app lists it as a list item / button)
            if save_as and e.role in ("menuitem", "listitem", "button", "tabitem", "treeitem") and name.startswith("save as ") \
                    and not (set(name.split()[2:]) & gtoks) and not (fmt_words & ntoks):
                score -= 3.0   # 'Save as project / template / copy' is a variant the goal did not ask for: plain 'Save as' wins
            if save_as and e.role in ("menuitem", "listitem", "button", "tabitem", "treeitem") and name in ("new", "new window", "new tab", "new image", "clear", "exit"):
                score -= 4.0   # a save goal is never advanced by a command that discards or replaces the document
            if save_as and e.role in ("menuitem", "listitem", "button", "tabitem", "treeitem") and name in ("save", "autosave"):
                score -= 4.0   # the in-place Save / quick-access Save button opens no 'as' flow (it opened a half-built pane that never loaded)
            if file_verb and e.role in ("menuitem", "button", "tabitem") and name in cls._FILE_ENTRY_NAMES:
                score += 5.0   # universal UI convention: file operations live under the File menu / File tab
            if menu_for_goal and name == menu_for_goal and e.role in ("menuitem", "button", "tabitem", "splitbutton"):
                score += 5.0   # standard menu convention: Paste / Copy / Undo live under Edit, Zoom under View ... (a command that is not on screen yet is behind its menu)
            if has_path and file_verb and name.startswith("browse") and e.role in ("button", "hyperlink", "listitem", "tabitem", "splitbutton"):
                score += 9.0   # 'Browse...' opens the OS file picker, which the file-dialog rung drives for real; an in-app 'File name' pane is fragile
            if wants_text and e.role in cls._TEXT_ROLES:
                score += 4.0 + (1.0 if e.role in ("edit", "document") else 0.0)
                if max_text_area > 0:
                    area = abs(e.bbox[2] - e.bbox[0]) * abs(e.bbox[3] - e.bbox[1])
                    score += 3.0 * (area / max_text_area)      # the document outranks a one-line strip
            if cls._is_utility_strip(goal, e):
                # A control whose OWN NAME says it is a search / filter / address / go-to strip is never the home
                # for a payload the goal did not ask for by name. This is not only a typing concern: measured, a
                # save goal put 'Microsoft search' at the top of the shortlist (9.4) because the demotion sat
                # inside the typing branch, and the step was spent opening the app's web search.
                score -= 8.0
            if hint_name and hint_name in name:
                score += 3.0
            # Follow the expert's menu path ('File > Save As'): a segment that exactly names this
            # element is the next step to take, earlier segments first (menus open one level at a time).
            for depth, seg in enumerate(hint_segments):
                if save_as and name == "save":
                    break  # explicit target => never the in-place Save, whatever an old hint says
                if name == seg or (name.startswith(seg + " ") and len(seg) > 3):
                    score += 6.0 - min(depth, 3)
                    break
            score += 0.5 * float(e.confidence or 0.0)
            scored.append((score, -e.bbox[1], i, e))
        scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
        return [(sc, i, e) for sc, _y, i, e in scored]

    # UI convention (not an app): the top-level menu a command usually lives under
    _MENU_CONVENTION = {
        "edit": ("cut", "copy", "paste", "undo", "redo", "select all", "find", "replace", "clear"),
        "view": ("zoom", "full screen", "fullscreen", "gridlines", "ruler", "status bar"),
        "insert": ("insert", "add picture", "add image"),
        "format": ("font", "bold", "italic", "underline", "word wrap", "align"),
    }
    _WINDOW_CHROME = frozenset({"minimize", "maximize", "restore", "restore down", "system", "system menu", "min", "max"})
    _CHROME_GOAL_WORDS = frozenset({"minimize", "maximize", "restore", "minimise", "maximise", "window", "resize", "fullscreen"})
    _DECISIVE_TEXT_MARGIN = 2.5
    _DECISIVE_PATH_MARGIN = 4.0

    @classmethod
    def _wants_text(cls, goal: str) -> bool:
        gl = (goal or "").lower()
        # 'paste the image from the clipboard' is the app's PASTE COMMAND, not text to type: 'paste' means typing only when a literal payload
        # is given in quotes ("paste 'hello' into the box")
        if re.match(r"^\s*(?:please\s+)?paste\b", gl) and not re.search(r"[\"“'].+[\"”']", gl):
            gl = re.sub(r"\bpaste\b", " ", gl, count=1)
        return bool(re.search(r"\b(" + "|".join(cls._TYPE_WORDS) + r")\b", gl))

    _PATH_TOKEN_RE = re.compile(r"[a-z]:[\\/][^\s'<>|?*]+")

    @classmethod
    def _goal_tokens(cls, goal: str) -> frozenset:
        """The words a goal really asks for. A file path is a LOCATION, not a label: its tokens are dropped so a
        control is never called a match because the goal happened to contain 'new' or 'tmp'."""
        g = cls._PATH_TOKEN_RE.sub(" ", (goal or "").lower())
        return frozenset(t for t in re.findall(r"[a-z0-9]+", g) if t not in cls._STOP and len(t) > 1)

    @classmethod
    def _is_utility_strip(cls, goal: str, e: "GroundedElement") -> bool:
        """True for a search / filter / address / go-to strip that the goal does not NAME. The control's own label
        says what it exists for, so it is never a step toward any other goal: clicking one opens the app's web
        search (measured twice in one save run, at rank 1.4 of 261 - the judge picked it anyway)."""
        gtoks = cls._goal_tokens(goal)
        if not gtoks:
            return False
        name = (e.name or "").lower()
        return not (gtoks & set(re.findall(r"[a-z0-9]+", name))) and any(u in name for u in UTILITY_BOX_NAMES)

    # UI convention, not app knowledge: the entry that opens the file surface, and the control that opens the
    # operating-system picker. Both are labels the accessibility tree of many apps carry; a new label is a table edit.
    _FILE_ENTRY_NAMES = frozenset({"file", "file tab", "file menu"})
    _PICKER_ROUTE_WORDS = ("browse",)

    _CLICK_ROLES = ("button", "menuitem", "tabitem", "listitem", "hyperlink", "checkbox", "radiobutton",
                    "splitbutton", "dropdownbutton", "treeitem")
    _PRESS_RE = re.compile(r"^(?:please\s+)?(?:press|click|tap|hit|select|choose|push|invoke|toggle|activate)"
                           r"\s+(?:on\s+)?(?:the\s+)?[\"'“]?(.+?)[\"'”]?(?:\s+(?:button|key|control|tab|item))?\s*$", re.I)

    @classmethod
    def _norm_label(cls, s: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()

    @classmethod
    def _exact_named_target(cls, goal: str, scored: List[Tuple[float, int, "GroundedElement"]]):
        """(score, index, element) of the clickable control whose whole name equals the object of a 'press X'
        style goal, else None. Digits match their word form ('6' == 'Six'), the way Calculator-style UIs label keys."""
        m = cls._PRESS_RE.match((goal or "").strip())
        if not m:
            return None
        obj = cls._norm_label(m.group(1))
        if not obj or len(obj.split()) > 4:
            return None
        try:
            from core_organs.task_runner import _DIGIT_WORDS
            obj = _DIGIT_WORDS.get(obj, obj)
        except Exception:
            pass
        hits = [c for c in scored if c[2].role in cls._CLICK_ROLES and cls._norm_label(c[2].name) == obj]
        return hits[0] if hits else None

    # The payload is read from the goal's own words ONLY when the goal also says WHERE it goes ('... in cell A1').
    # That is the shape of a machine-checkable instruction; 'type the current date' names no place and its "payload"
    # is something the model must generate, so it keeps going through the composer below.
    _OWN_WORD_RE = re.compile(r"^(?:my|your|his|her|its|our|their|the|this|that|some|any)\b", re.I)

    def _literal_payload(self, goal: str) -> str:
        lit = literal_typed_text(goal or "")
        if not lit or _LOCATION_TAIL_RE.search(goal or "") is None:
            return ""
        if self._OWN_WORD_RE.match(lit.strip()):
            return ""                      # 'type my password into the form' asks for a value, not these words
        return lit

    def _compose_text(self, goal: str) -> str:
        """Small LLM call used ONLY to author the text for a typing goal (the element was chosen
        deterministically). A quoted string in the goal wins without any LLM call.

        A goal that already SPELLS OUT its payload ('type 42 in cell A1') is answered from its own words, by the
        same literal reader the postconditions use, and no model is called at all. Measured reason: the model was
        busy behind the vision tier, this call timed out to '' twice in one run, '' cancels the decisive pick, and
        the judge then aimed '42' at 'Formula Bar' - a one-line strip - instead of the cell the goal named."""
        m = re.search(r"[\"'“]([^\"'”]{2,300})[\"'”]", goal or "")
        if m:
            return m.group(1)
        literal = self._literal_payload(goal)
        if literal:
            return literal
        payload = {"model": JUDGE_MODEL, "stream": False,
                   "messages": [{"role": "user", "content":
                                 "Return ONLY the exact text to type for this instruction, with no "
                                 f"quotes or commentary.\nINSTRUCTION: {goal}"}],
                   "options": {"temperature": 0.7, "num_predict": 80}}
        try:
            import urllib.request
            req = urllib.request.Request(BRAINS_CHAT_URL, data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=JUDGE_TIMEOUT_S) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return ((body.get("message", {}) or {}).get("content", "") or "").strip().strip('"')
        except Exception as exc:
            logger.debug("[judge] compose_text failed: %s", exc)
            return ""

    _CELL_REF_RE = re.compile(r"\b([A-Za-z]{1,3}[1-9]\d{0,5})\b")

    def _cell_target(self, goal: str, elements: List[GroundedElement]):
        """(index, element) of the grid cell a typing goal means: the one it names ('in cell B2'), else the first cell
        (A1 - the active cell of a fresh sheet). None when the grid exposes no addressable cell."""
        cells = [(i, e) for i, e in enumerate(elements)
                 if e.role == "dataitem" and re.fullmatch(r"[A-Za-z]{1,3}[1-9]\d{0,5}", (e.name or "").strip())]
        if not cells:
            return None
        named = {m.group(1).upper() for m in self._CELL_REF_RE.finditer(goal or "")} - {"A", "I"}
        for i, e in cells:
            if e.name.strip().upper() in named:
                return i, e
        if named:
            return None                  # it names a cell that is not on screen: do not type somewhere else

        def _key(ie):
            m = re.fullmatch(r"([A-Za-z]+)(\d+)", ie[1].name.strip())
            return (int(m.group(2)), len(m.group(1)), m.group(1).upper())
        return min(cells, key=_key)

    def decisive(self, goal: str, elements: List[GroundedElement],
                 pro_hint: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Deterministic pick when the evidence is overwhelming; None => ask the LLM judge.

          * typing goal + a clearly-best editable control   -> type (LLM only writes the text)
          * the next segment of the expert's menu path is an exact on-screen match -> click
        A 7B model chose a tab titled like the typed text over the editor; decisive evidence must
        never be left to it."""
        scored = self.rank_scored(goal, elements, pro_hint)
        if not scored:
            return None
        top = scored[0]
        # The goal NAMES one control exactly ("press Six", "click 'Save'", "select the Settings tab") and exactly
        # such a clickable control is on screen: that is a lookup, not a judgement. Skipping the 7B here removed
        # every invalid-choice strike a correct, unambiguous goal could earn (it said "type Six" on a button).
        exact = self._exact_named_target(goal, scored)
        if exact is not None:
            return {"choice": exact[1], "verb": "click", "text": "", "why": "decisive: goal names this control exactly",
                    "element_index": exact[1], "element": exact[2].as_dict(), "decisive": True}
        # the same control is often exposed twice (hidden + popup copy): measure the margin against
        # the best candidate with a DIFFERENT name
        rival = next((c[0] for c in scored[1:] if (c[2].name or "").strip().lower()
                      != (top[2].name or "").strip().lower()), 0.0)
        margin = top[0] - rival
        g = (goal or "").lower()
        # Cells are their own addressable surface; the grid container is sometimes not exposed (a virtualized
        # view, a provider that hands out the items only). Requiring the container's exact role string used to
        # cancel this branch on a screen that DID offer the named cell, and the payload went to an edit strip.
        if re.search(r"\b(" + "|".join(self._TYPE_WORDS) + r")\b", g):
            cell = self._cell_target(goal, elements)
            if cell is not None:
                text = self._compose_text(goal)
                if text:
                    return {"choice": cell[0], "verb": "type", "text": text, "why": "decisive: spreadsheet cell",
                            "element_index": cell[0], "element": cell[1].as_dict(), "decisive": True}
        if self._wants_text(goal):
            # Typing goal: only an editable control can receive text, so the candidate set IS the
            # editable controls (a tab/label/button that merely shares a word must never win).
            # This branch used to test the raw _TYPE_WORDS regex on the goal. 'paste' IS a type-word, so
            # "paste the image from the clipboard" arrived here, Paint's Zoom box was the only editable
            # control on screen, and the run typed the 34-character GOAL SENTENCE into the zoom field - seven
            # steps in a row, at a moment when the ranking had already put the menu item 'Paste' first.
            # _wants_text is the authority that exists to tell a typing goal from a command that happens to be
            # spelled like one (its own comment cites this exact sentence); the decisive path must consult it.
            texty = [c for c in scored if c[2].role in self._TEXT_ROLES]
            if texty and (len(texty) == 1 or texty[0][0] - texty[1][0] >= 1.0):
                text = self._compose_text(goal)
                if text:
                    return {"choice": texty[0][1], "verb": "type", "text": text,
                            "why": "decisive: editable control", "element_index": texty[0][1],
                            "element": texty[0][2].as_dict(), "decisive": True}
        conv = self._conventional_menu(re.sub(r"[a-z]:[\\/][^\s'<>|?*]+", " ", g), elements)
        if conv and (top[2].name or "").strip().lower() == conv and margin >= 2.0 and top[2].role in ("menuitem", "button", "tabitem", "splitbutton"):
            return {"choice": top[1], "verb": "click", "text": "", "why": f"decisive: '{conv}' is the conventional menu of this command",
                    "element_index": top[1], "element": top[2].as_dict(), "decisive": True}
        if (re.search(r"\bsave\b", g) and re.search(r"[a-z]:[\\/]", g) and (top[2].name or "").strip().lower().startswith("save as")
                and margin >= 2.0 and top[0] >= 9.0 and top[2].role in ("menuitem", "button", "listitem", "tabitem")):
            return {"choice": top[1], "verb": "click", "text": "", "why": "decisive: 'Save as' for a goal that names a target path",
                    "element_index": top[1], "element": top[2].as_dict(), "decisive": True}
        # A goal that names a FILE LOCATION can only advance through the two entries that hold it, and both are UI
        # conventions rather than app knowledge. Measured on a spreadsheet save run: the shortlist put the file entry
        # first both times, the 7B judge clicked the app's web-search box instead, and the goal took 9 steps where the
        # identical run took 5. Evidence this strong is not a judgement call.
        entry = (top[2].name or "").strip().lower()
        asks_location = bool(re.search(r"\b(save|open|export|import|print|close)\b", g)) \
            and bool(re.search(r"[a-z]:[\\/]", g))
        if (asks_location and top[2].role in ("menuitem", "button", "tabitem", "splitbutton")
                and entry in self._FILE_ENTRY_NAMES and margin >= 2.0):
            return {"choice": top[1], "verb": "click", "text": "",
                    "why": "decisive: file commands live behind the app's file entry",
                    "element_index": top[1], "element": top[2].as_dict(), "decisive": True}
        if (asks_location and top[2].role in self._CLICK_ROLES
                and any(entry.startswith(w) for w in self._PICKER_ROUTE_WORDS) and margin >= 2.0):
            return {"choice": top[1], "verb": "click", "text": "",
                    "why": "decisive: the picker route is the only control that takes a full location",
                    "element_index": top[1], "element": top[2].as_dict(), "decisive": True}
        if top[0] >= 10.0 and margin >= 4.0 and top[2].role in ("menuitem", "button", "tabitem", "listitem",
                                                                  "hyperlink", "checkbox", "radiobutton"):
            return {"choice": top[1], "verb": "click", "text": "", "why": "decisive: overwhelming match",
                    "element_index": top[1], "element": top[2].as_dict(), "decisive": True}
        segs = [x.strip().lower() for x in ((pro_hint or {}).get("menu_path") or "").split(">") if x.strip()]
        if segs and margin >= self._DECISIVE_PATH_MARGIN and (top[2].name or "").strip().lower() in segs:
            return {"choice": top[1], "verb": "click", "text": "", "why": "decisive: expert menu path",
                    "element_index": top[1], "element": top[2].as_dict(), "decisive": True}
        return None

    _picker_state: Dict[str, Any] = {"checked": 0.0, "up": False}

    def _ask_trained_picker(self, goal: str, ranked: List[Tuple[int, "GroundedElement"]], app_hint: str) -> Optional[Dict[str, Any]]:
        """The locally TRAINED adapter (mind.picker) gets the first word when HOJAIGA_PICKER_URL is set and the server answers. Its answer is checked (an index inside the list, a verb that exists);
        anything else - server down, bad index, no answer - returns None and the existing judge decides exactly as before."""
        if not os.environ.get("HOJAIGA_PICKER_URL"):
            return None
        try:
            from core_organs.mind import picker as PK
            st = self._picker_state
            if time.time() - st["checked"] > 30:
                st.update(checked=time.time(), up=PK.available())
            if not st["up"]:
                return None
            shortlist = ranked[:40]
            els = [{"role": e.role or "control", "name": (e.name or "")[:80]} for _i, e in shortlist]
            ans = PK.ask(f"desktop:{app_hint}", els, goal)
            if not ans:
                return None
            idx = ans["target_id"] - 1 if ans["action"] in ("click", "confirm") else -1
            if idx < 0:
                return None
            el = shortlist[idx][1]
            dec = {"choice": idx, "verb": "click", "text": "", "why": "trained adapter pick", "element": el.as_dict(), "element_index": shortlist[idx][0], "picker": True}
            if ans["action"] == "confirm":
                dec["picker_confirm"] = {"risk": ans.get("text"), "does": ans.get("verify_expectation")}
            return dec
        except Exception as exc:                                    # the adapter is an extra opinion, never a dependency
            logger.debug("[judge] trained picker failed: %s", exc)
            return None

    def decide(self, goal: str, elements: List[GroundedElement],
               app_hint: str = "", history: List[str] = None,
               pro_hint: Optional[Dict[str, Any]] = None, use_decisive: bool = True) -> Optional[Dict[str, Any]]:
        """The natural brain decides; while it is not ready a teacher (Claude on the user's key, else a free hosted model) is consulted and the brain checks
        and keeps what it says (mind.brain). A deterministic fast-path answer is the brain's own and never costs a teacher call."""
        fast = self.decisive(goal, elements, pro_hint) if use_decisive else None
        if fast is not None:
            return fast
        local = self._decide_local(goal, elements, app_hint, history, pro_hint, use_decisive=False)
        try:
            from core_organs.mind import brain as BR
            md = BR.mode()
            if md == "off" or not elements:
                return local
            mine = (str(local.get("verb", "")), str((local.get("element") or {}).get("name", ""))) if local and not local.get("invalid") else None
            if md == "local" and mine is not None:
                local["brain_id"] = BR.record(app_hint, goal, [(e.role, e.name) for e in elements[:1]], None, mine, "brain")
                return local
            ranked = [e for _i, e in self.rank_candidates(goal, elements, pro_hint)][:TEACH_MAX_CONTROLS]
            shown = ranked or list(elements[:TEACH_MAX_CONTROLS])
            t = BR.teach(goal, app_hint, [(e.role, e.name) for e in shown], _window_png_b64(shown[0].hwnd))
            if t is None:
                return local
            el = shown[t["index"]]
            verb = {"done": "done", "type": "type", "key": "key"}.get(t["verb"], "click")
            dec = {"choice": t["index"], "verb": verb, "text": t.get("text", ""), "why": f"teacher {t['who']}: {t.get('why', '')}"[:200], "element": el.as_dict(),
                   "element_index": elements.index(el), "teacher": t["who"]}
            dec["brain_id"] = BR.record(app_hint, goal, [(e.role, e.name) for e in shown], t, mine, t["who"])
            return dec
        except Exception as exc:                                    # the brain's own answer stands whenever the teacher path fails
            logger.debug("[judge] teacher path failed: %s", exc)
            return local

    def _decide_local(self, goal: str, elements: List[GroundedElement],
                      app_hint: str = "", history: List[str] = None,
                      pro_hint: Optional[Dict[str, Any]] = None, use_decisive: bool = True) -> Optional[Dict[str, Any]]:
        fast = self.decisive(goal, elements, pro_hint) if use_decisive else None
        if fast is not None:
            return fast
        ranked = self.rank_candidates(goal, elements, pro_hint)
        picks = [e for _i, e in ranked[:MAX_JUDGE_ELEMENTS]]
        orig_index = [i for i, _e in ranked[:MAX_JUDGE_ELEMENTS]]
        if not picks:
            return None
        trained = self._ask_trained_picker(goal, ranked, app_hint)
        if trained is not None:
            return trained
        lines = []
        for i, e in enumerate(picks):
            cx, cy = e.center
            lines.append(f"{i}. [{e.role}] \"{e.name[:48]}\" at {cx},{cy} ({e.tier})")
        tried = "\n".join(f"- {h}" for h in (history or [])[-4:]) or "- (none yet)"
        pro_block = ""
        if pro_hint:
            if pro_hint.get("kind") == "element":
                label = pro_hint.get("menu_path") or pro_hint.get("element_name") or ""
                hv = pro_hint.get("verb", "click")
                if hv == "type" and not self._wants_text(goal):
                    hv = "click"      # a hint must not tell the model to type when the goal never asked for text
                hv = "key" if hv == "shortcut" else hv  # 'shortcut' is not a legal verb; 'key' is
                key_note = ""  # posted keys do not reach every UI framework; never advertise them
                hv = "click" if hv == "key" else hv
                pro_block = (
                    "EXPERT HINT (from prior verified runs on this app, prefer "
                    f"matching it): aim for \"{label}\" using verb "
                    f"{hv}. This is guidance, not a "
                    f"guarantee — still pick the numbered element that matches it.{key_note}\n")
            elif pro_hint.get("shortcut"):
                pro_block = (f"EXPERT HINT: shortcut {pro_hint['shortcut']} is known "
                             "for this goal.\n")
        prompt = (
            "You are a precise desktop automation executor. Pick EXACTLY ONE numbered "
            "on-screen element and ONE verb that best advances the goal RIGHT NOW.\n"
            f"GOAL: {goal}\nAPP: {app_hint}\n{pro_block}"
            f"ALREADY TRIED (do not repeat):\n{tried}\n"
            "ELEMENTS:\n" + "\n".join(lines) + "\n"
            f"VERBS: {', '.join(LEGAL_VERBS)}\n"
            "RULES: prefer click / type / invoke on a LISTED element. Use verb key ONLY for an "
            "explicit keyboard shortcut named in the goal, never on a tab or document.\n"
            "Return STRICT JSON: {\"choice\": <number>, \"verb\": \"<verb>\", "
            "\"text\": \"<only for type>\", \"why\": \"<5 words>\"}"
        )
        payload = {
            "model": self.model or JUDGE_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_predict": 120},
        }
        try:
            import urllib.request
            req = urllib.request.Request(
                BRAINS_CHAT_URL, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=JUDGE_TIMEOUT_S) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body.get("message", {}).get("content", "") or body.get("response", "")
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if not m:
                return None
            decision = json.loads(m.group(0))
            idx = int(decision.get("choice", -1))
            verb = str(decision.get("verb", "")).lower().strip()
            if 0 <= idx < len(picks) and verb == "type" and picks[idx].role not in self._TEXT_ROLES:
                if self._wants_text(goal) and not any(p.role in self._TEXT_ROLES for p in picks):
                    # The goal types and the window has NO text box at all (Calculator): the app takes the keys itself. Typing is sent to
                    # the window as characters and the verifier judges what changed. Live Nov-02: 'type 7 + 5 =' was rejected three times
                    # as 'type on a non-editable control' and went to a human; posted characters gave 'Display is 12'.
                    decision["keys_to_window"] = True
                    decision["coerced"] = "type into the window: no text box on screen, the app takes the keys itself"
                elif self._wants_text(goal):
                    return {"invalid": True, "raw": decision, "why": "type on a non-editable control"}
                # The goal never asked for typing and the element is a plain control: the model picked the right
                # control and the wrong verb (a low-trust 'distilled' hint said "type" and it echoed it). That is
                # not a hallucinated choice and must not count toward the 3-strike human escalation; click it.
                # The postcondition verifier still decides whether the click achieved anything.
                decision["verb"] = verb = "click"
                decision["coerced"] = "type->click: goal has no typing intent and the target is not editable"
            if 0 <= idx < len(picks) and verb == "type" and not self._wants_text(goal):
                # The same rule for an EDITABLE target: a `type` whose goal never asked for text is not typing,
                # whatever role the element has. Measured 2026-10-06 (PAINT1): the ranking put the menu item
                # 'Paste' first at 12.4, and the model answered by typing the 34-CHARACTER GOAL SENTENCE into
                # Paint's 'Zoom' edit box - the same step six times, because the guard above only fires on a
                # NON-editable target and an ordinary edit slipped through. Take the element the DATA-driven
                # ranking already put first; the postcondition verifier still decides if it achieved anything.
                if picks[0].role in self._CLICK_ROLES:
                    decision["coerced"] = (f"type->click on top-ranked '{picks[0].name[:30]}': the goal asks for "
                                           f"no text, so 'type' would have typed the goal sentence itself")
                    idx = 0
                    decision["verb"] = verb = "click"
                # If nothing on the shortlist is clickable there is nothing better to do than leave the model's
                # own answer alone. This guard exists to stop a goal sentence being typed into a stray edit box;
                # it must not become a NEW way to reject a step that used to run (f8 showed two unrelated apps
                # going BLOCKED right after a change here, so the rejection path was removed rather than trusted).
            if idx < 0 or idx >= len(picks) or verb not in LEGAL_VERBS:
                return {"invalid": True, "raw": decision}
            # A control the shortlist DEMOTED because its own label says what it is for (search / address / go-to) and
            # the goal never names it: the model does not get the last word on that, or every save run burns steps
            # opening the app's web search. Take the control the ranking already put first, and say why in the trace.
            if (idx != 0 and self._is_utility_strip(goal, picks[idx])
                    and not self._is_utility_strip(goal, picks[0])
                    and picks[0].role in self._CLICK_ROLES
                    and (verb in ("click", "invoke", "select", "expand", "toggle")
                         or (verb == "type" and not self._wants_text(goal)))):
                decision["coerced"] = (f"'{picks[idx].name[:30]}' is a utility strip the goal does not name; "
                                       f"took the top-ranked '{picks[0].name[:30]}'")
                idx = 0
                decision["verb"] = verb = "click"
            # element_index always refers to the ORIGINAL grounded list (callers index into it)
            decision.update({"element": picks[idx].as_dict(), "element_index": orig_index[idx]})
            return decision
        except Exception as exc:
            logger.debug("[judge] call failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Action primitives: UIA patterns -> PostMessage -> physical input (cursor-clip aware)
# ---------------------------------------------------------------------------

def _pattern_of(target, pattern_name: str):
    """A control's TYPED pattern getter is missing on some UIA wrapper classes (a PaneControl has no
    GetExpandCollapsePattern), which does not mean the element lacks the pattern - ask UIA for the pattern id
    instead. Measured: a collapsed submenu on such a wrapper never expanded, and the click fell through to a
    default action that changed nothing, spending a step per retry."""
    try:
        return getattr(target, pattern_name)()
    except AttributeError:
        import uiautomation as _ua
        pid = getattr(_ua.PatternId, pattern_name[3:], None)
        return target.GetPattern(pid) if pid else None


def _uia_act(elem: GroundedElement, verb: str, text: str):
    """UIA pattern delivery. Returns (result|None, native_hwnd). Runs on _UIA_EXEC's thread."""
    native = 0
    if elem.tier == "uia" and HAS_UIA:
        import uiautomation as auto
        try:
            uroot = auto.ControlFromHandle(elem.hwnd)
            target = _find_control_by_identity(uroot, elem)
            if target is not None:
                native = int(getattr(target, "NativeWindowHandle", 0) or 0)
                if verb == "locate":
                    # Resolution only: the caller posts characters to the real control hwnd, which
                    # appends at the caret instead of replacing the value like SetValue does.
                    return None, native
                if verb == "read":
                    # What the control actually holds right now. The structure hash and the coarse
                    # pixel hash both miss typing: a short line into a document changes no element id
                    # and can move well under 2% of the pixels.
                    for getter, extractor in (("GetValuePattern", lambda p: p.Value),
                                              ("GetTextPattern", lambda p: p.DocumentRange.GetText(-1))):
                        try:
                            pat = getattr(target, getter)()
                            if pat:
                                return True, str(extractor(pat) or "")
                        except Exception:
                            continue
                    return None, native
                if verb == "type":
                    for getter, setter in (("GetValuePattern", "SetValue"),
                                           ("GetLegacyIAccessiblePattern", "SetValue")):
                        try:
                            pat = getattr(target, getter)()
                            if pat:
                                getattr(pat, setter)(text)
                                return True, "uia-SetValue"
                        except Exception:
                            continue
                else:  # click family
                    _errs: List[str] = []
                    # A collapsed menu item that offers no Invoke but HAS a submenu (Paint's "Save as" -> PNG / JPEG / ...):
                    # LegacyIAccessible's default action "succeeds" without opening it, so the format items never appear.
                    # Expand it for real.
                    try:
                        _ec = _pattern_of(target, "GetExpandCollapsePattern")
                        if _ec is not None and int(_ec.ExpandCollapseState) == 0:
                            _inv = _pattern_of(target, "GetInvokePattern")
                            if _inv is None:
                                _ec.Expand()
                                return True, "uia-expand"
                    except Exception as _e0:
                        _errs.append(f"expand-first:{type(_e0).__name__}")
                    _order = [("GetInvokePattern", "invoke"),
                              ("GetLegacyIAccessiblePattern", "do-default"),
                              ("GetSelectionItemPattern", "select"),
                              ("GetTogglePattern", "toggle"),
                              ("GetExpandCollapsePattern", "expand")]
                    if (elem.role or "").lower() in ("listitem", "tabitem", "radiobutton"):
                        # Pressing a list/tab item MEANS selecting it. LegacyIAccessible's default action "succeeds"
                        # on Office's backstage list (File > Save As) without switching the pane, so Select goes first.
                        _order.insert(1, _order.pop(2))
                    for pattern_name, attempts in _order:
                        try:
                            pat = _pattern_of(target, pattern_name)
                            if pat is None:
                                continue
                            {"invoke": lambda: pat.Invoke(),
                             "do-default": lambda: pat.DoDefaultAction(),
                             "select": lambda: pat.Select(),
                             "toggle": lambda: pat.Toggle(),
                             "expand": lambda: pat.Expand()}[attempts]()
                            return True, f"uia-{attempts}" + (f" (after {','.join(_errs)})" if _errs else "")
                        except Exception as _e:
                            _errs.append(f"{attempts}:{type(_e).__name__}:{str(_e)[:40]}")
                            continue
        except Exception as exc:
            logger.debug("[act] uia path failed: %s", exc)

    return None, native


_UIA_EXEC = None


def _uia_thread_init():
    # a dedicated thread with its OWN properly initialised COM apartment: the UIA client state of
    # the calling thread is shared with every other organ (organ_30, pywin32...), and a different
    # apartment/initialisation there made Invoke silently degrade to DoDefaultAction.
    try:
        import uiautomation as _a
        _a.UIAutomationInitializerInThread().__enter__()
    except Exception:
        pass


def reveal_by_scrolling(hwnd: int, *, to_bottom: bool = True, timeout_s: float = 14.0) -> bool:
    """Module-level scroll-reveal (used by the stuck-goal widening AND by fast_scan's map): drive every
    vertically-scrollable container of this window to its end through UIA's ScrollPattern - the only
    delivery that works on XAML/WinUI/Chromium - forcing the layout manager to materialise virtualized
    items (a NavigationView footer, a long list). Containers are chosen by the PRESENCE of the pattern,
    never by an app's control name: generic. `to_bottom=False` scrolls them back to the top, so a caller
    that revealed, re-read and merged can leave the app exactly as found (UI-restoration law).
    Returns whether at least one container moved."""
    global _UIA_EXEC
    if _UIA_EXEC is None:
        from concurrent.futures import ThreadPoolExecutor
        _UIA_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia-act", initializer=_uia_thread_init)

    def work():
        import uiautomation as auto
        try:
            root = auto.ControlFromHandle(hwnd)
        except Exception:
            return False
        NoScroll = -1.0                            # -1 = leave the horizontal position alone
        target = 100.0 if to_bottom else 0.0
        stack, seen, moved, containers = [root], 0, False, 0
        while stack and seen < 800 and containers < 12:    # bounded fan-out
            c = stack.pop(); seen += 1
            try:
                stack.extend(c.GetChildren())
            except Exception:
                pass
            try:
                p = c.GetScrollPattern()
            except Exception:
                p = None
            if p is None:
                continue
            containers += 1
            try:
                if getattr(p, "VerticallyScrollable", False):
                    p.SetScrollPercent(NoScroll, target)
                    moved = True
            except Exception:
                pass
        return moved
    try:
        ok = bool(_UIA_EXEC.submit(work).result(timeout=timeout_s))
    except Exception as exc:  # noqa: BLE001
        logger.debug("[reveal] scroll-reveal failed: %s", exc)
        return False
    if ok:
        time.sleep(0.5)                            # let the layout pass build the now-visible items
    return ok


def _uia_dispatch(elem: GroundedElement, verb: str, text: str):
    global _UIA_EXEC
    if _UIA_EXEC is None:
        from concurrent.futures import ThreadPoolExecutor
        _UIA_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia-act", initializer=_uia_thread_init)
    try:
        return _UIA_EXEC.submit(_uia_act, elem, verb, text).result(timeout=10)
    except Exception as exc:
        logger.debug("[act] uia worker failed: %s", exc)
        return None, 0


def _window_png_b64(hwnd: int, max_side: int = 1568) -> str:
    """The window's own pixels (PrintWindow ladder, never the screen around it) as base64 PNG for the teacher; '' when it cannot be captured."""
    try:
        import base64
        import io
        img = hin.capture_window_robust(_root_of(hwnd))[0] if hwnd else None
        if img is None:
            return ""
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


def _root_of(hwnd: int) -> int:
    """Top-level (GA_ROOT) window for a possibly-child hwnd."""
    try:
        return int(hin._u32.GetAncestor(hwnd, 2) or hwnd)
    except Exception:
        return hwnd


def _act_on_element(elem: GroundedElement, verb: str, text: str = "") -> Tuple[bool, str]:
    """Every action leaves through the DAP actuation backbone (dap_actuator): the element is described neutrally, the app FAMILY picks the
    ordered providers (UIA patterns / Chromium / WinUI / window messages / parked pixel click), the first that delivers wins, and the
    per-provider trace is kept. `HOJAIGA_LEGACY_ACT=1` runs the previous in-line ladder (kept for parity checks)."""
    if os.environ.get("HOJAIGA_LEGACY_ACT") == "1":
        return _act_on_element_legacy(elem, verb, text)
    from core_organs import dap_actuator
    return dap_actuator.get_actuator().act(elem, verb, text)


def _act_on_element_legacy(elem: GroundedElement, verb: str, text: str = "") -> Tuple[bool, str]:
    """Deliver one action to ``elem`` WITHOUT touching the physical pointer or keyboard and
    without changing which window is in front. Ladder: window messages to the exact HWND for
    typing (append at the caret), UIA pattern otherwise, then the other rung. When nothing can
    deliver, returns (False, 'UNDELIVERABLE: <why>') - there is deliberately no physical-input
    rung (product law)."""
    if verb == "wait":
        time.sleep(min(2.0, 0.8))
        return True, "waited"
    if verb == "done":
        return True, "declared-done"
    root = _root_of(elem.hwnd) if elem.hwnd else 0

    if verb in ("key", "shortcut"):
        combo = text or elem.name
        return hin.post_key_combo(root, combo)

    if verb == "scroll":
        cx, cy = elem.center
        return hin.post_scroll(root, cx, cy, -3)

    if verb == "invoke":
        verb = "click"  # invoke is the UIA-safe synonym handled by the click ladder

    if verb == "type" and text and (elem.role or "").lower() not in ("dataitem", "cell"):
        # Typing is the one verb where the UIA pattern is wrong by default: ValuePattern.SetValue
        # REPLACES the control's content, so the second 'type' goal of a multi-part entry silently
        # deletes the first (a real unattended Notepad run wrote line 2 over line 1 and line 3 over
        # line 2, each still 'verified' because the UI did change). Posting characters to the
        # control's own hwnd appends at the caret instead, so it goes first; SetValue stays as the
        # fallback for controls that ignore posted characters. Neither is trusted - the verifier
        # judges the postcondition either way.
        native = 0
        if elem.tier == "uia" and HAS_UIA:
            out = _uia_dispatch(elem, "locate", "")
            native = out[1] if out else 0
        ok, note = hin.post_text(native or elem.hwnd, text)
        if ok:
            return True, f"append:{note}"

    res, native = (None, 0)
    if elem.tier == "uia" and HAS_UIA:
        out = _uia_dispatch(elem, verb, text)
        if out and out[0] is True:      # delivered by a UIA pattern: (True, 'uia-...')
            return out
        native = out[1] if out and out[0] is None else 0

    # Window messages to the exact HWND (works while covered / partly off-screen).
    if verb == "click" and root:
        cx, cy = elem.center
        if elem.tier in ("ocr", "vision") and hin.is_minimized(root):
            # A pixel-found element has screen coordinates, which only mean something while the window is laid
            # out. Deliver the click while it is parked off-screen (same rect the capture used), let the app
            # handle the message, then it is re-minimized as it was. Never a visible restore.
            from core_organs import background_window as bw
            with bw.BackgroundSession(root) as sess:
                if sess.mode == "parked":
                    ok, note = hin.post_click(root, cx, cy)
                    time.sleep(0.4)
                    return ok, note + " [delivered while parked off-screen]"
            return False, f"{hin.UNDELIVERABLE}: pixel-found element in a minimized window and it could not be parked ({sess.mode})"
        return hin.post_click(root, cx, cy)
    if verb == "type" and (native or elem.hwnd):
        ok, note = hin.post_text(native or elem.hwnd, text)
        if ok:
            return True, note
        return False, note
    return False, f"{hin.UNDELIVERABLE}: no UIA pattern and no addressable HWND for '{elem.name}' ({verb})"


def _find_control_by_identity(root, elem: GroundedElement):
    """Re-locate the grounded control in the live tree (trees go stale, and apps often expose the
    same control twice - a hidden duplicate without patterns plus the real one). Every name match is
    scored: exact name+role, same on-screen box, and actually supporting an invoke-style pattern."""
    want_name = (elem.name or "").lower()
    cands = []

    def _visit(c, depth, budget=[0]):
        if depth > 14 or budget[0] > 1500:
            return
        budget[0] += 1
        try:
            cname = (c.Name or "").strip().lower()
            crole = (c.ControlTypeName or "").lower().replace("control", "")
            if cname and (cname == want_name or (len(want_name) > 3 and (want_name in cname or cname in want_name))):
                r = c.BoundingRectangle
                sc = 0.0
                sc += 3.0 if (cname == want_name and crole == elem.role) else (1.0 if crole == elem.role else 0.0)
                if abs(r.left - elem.bbox[0]) < 6 and abs(r.top - elem.bbox[1]) < 6:
                    sc += 3.0
                try:
                    if c.GetInvokePattern() is not None or c.GetSelectionItemPattern() is not None                             or c.GetTogglePattern() is not None or c.GetExpandCollapsePattern() is not None:
                        sc += 2.0
                except Exception:
                    pass
                if sc >= 3.0:
                    cands.append((sc, len(cands), c))
            for ch in c.GetChildren():
                _visit(ch, depth + 1)
        except Exception:
            return

    _visit(root, 0, [0])
    if not cands:
        return None
    cands.sort(key=lambda t: (-t[0], t[1]))
    return cands[0][2]


def _postmessage_action(elem: GroundedElement, verb: str, text: str) -> bool:
    """Headless retry rung used by the NO_CHANGE ladder: post straight to the element's HWND."""
    if not _IS_WINDOWS or not elem.hwnd:
        return False
    root = _root_of(elem.hwnd)
    if verb == "click":
        cx, cy = elem.center
        return hin.post_click(root, cx, cy)[0]
    if verb == "type":
        return hin.post_text(elem.hwnd, text)[0]
    return False


def _token_to_vk(tok: str) -> Optional[int]:
    return hin.token_to_vk(tok)


def _send_shortcut(combo: str, hwnd: int = 0) -> Tuple[bool, str]:
    """Deliver a key combo to ``hwnd`` as posted window messages (never physical keys)."""
    if not hwnd:
        return False, f"{hin.UNDELIVERABLE}: no target window for '{combo}'"
    return hin.post_key_combo(_root_of(hwnd), combo)


# ---------------------------------------------------------------------------
# W4 — DesktopAutonomyLoop: the closed perceive->decide->act->verify loop
# ---------------------------------------------------------------------------

@dataclass
class StepTrace:
    goal: str
    element: str
    verb: str
    verdict: str
    method: str
    evidence: str
    tiers: List[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {"goal": self.goal, "element": self.element, "verb": self.verb,
                "verdict": self.verdict, "method": self.method,
                "evidence": self.evidence, "tiers": self.tiers, "ts": self.ts}


_FILE_DIALOG_TITLES = ("save as", "save", "open", "export", "import", "browse", "select a file",
                       "select file", "choose file", "choose a file", "upload")
_OVERWRITE_CUES = ("confirm save as", "overwrite", "replace", "already exists")


def _is_file_dialog_title(title: str) -> bool:
    """A Save/Open picker is a TASK STEP the file-dialog rung resolves, not a roadblock."""
    low = (title or "").strip().lower()
    if any(c in low for c in _OVERWRITE_CUES):
        return False
    return any(low == w or low.startswith(w + " ") or low.endswith(" " + w) for w in _FILE_DIALOG_TITLES)


def _is_overwrite_confirm(title: str) -> bool:
    low = (title or "").lower()
    return any(c in low for c in _OVERWRITE_CUES)


class DesktopAutonomyLoop:
    def __init__(self, grounding: Optional[DesktopGrounding] = None,
                 verifier: Optional[DesktopVerifier] = None,
                 judge: Optional[ConstrainedJudge] = None,
                 capsule_cb: Optional[Callable[[str, str], None]] = None,
                 cursor_cb: Optional[Callable[[float, float], None]] = None,
                 session_id: Optional[str] = None):
        self.grounding = grounding or DesktopGrounding()
        self.verifier = verifier or DesktopVerifier()
        self.judge = judge or ConstrainedJudge()
        self.capsule_cb = capsule_cb or (lambda state, text: None)
        # cursor_cb drives the blue-arrow virtual cursor (magnet detaches on act)
        self.cursor_cb = cursor_cb
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self.trace: List[StepTrace] = []
        self.invalid_streak = 0
        self.awaiting_human = False
        self._history: List[str] = []
        # consecutive non-PASS attempts per goal; drives the keyboard-route recovery rung
        self._goal_fails: Dict[str, int] = {}
        self._shortcut_tried: set = set()
        # per goal: controls that were pressed and CHANGED the screen without completing the goal (WRONG_STATE) - a menu
        # or submenu that is now open. Pressing the same control again cannot advance the goal; its children can.
        self._opened_not_done: Dict[str, set] = {}
        self._pending_clicks: Dict[str, Dict[str, int]] = {}   # goal -> control -> clicks that 'passed' while the goal's terminal proof was still missing
        self.escalation_shots: List[Dict[str, str]] = []
        self._relaunches = 0
        # A typing task needs a document on screen; when the instance loses it mid-run the prepare step may run again,
        # a bounded number of times per run (see _canvas_needed / the in-goal canvas recovery).
        self._canvas_needed = False
        self._canvas_prep_left = 0
        self._dap = None
        # Windows kept parked off-screen for the current run (hwnd -> BackgroundSession), apps WE started, run nesting
        self._held: Dict[int, Any] = {}
        self._launched_apps: set = set()
        self._run_depth = 0
        self._last_window_mode = "not-needed"
        # W8 app-intelligence organ (None => run on perception alone)
        self.intel = _get_intel()
        # behavior-model knowledge (unified commands, routes, transitions); None => the loop runs without it
        self.bridge = _get_bridge()

    @property
    def dap_core(self):
        if self._dap is None:
            self._dap = get_dap_core()
        return self._dap

    # ---- popup triage (organ_29 + generic Win32/UIA dialogs) ----
    def _save_escalation_shot(self, owner_hwnd: int, why: str) -> str:
        """Evidence for a human: a PNG of the dialog(s) that stopped the run (PrintWindow, so nothing is raised or shown).
        Returns the path ('' when nothing could be captured). Kept on self.escalation_shots and in the run result."""
        try:
            from core_organs import popup_policy as _pp
            targets = _pp.blocking_dialogs(owner_hwnd) or [owner_hwnd]
            last_note = ""
            for h in targets[:2]:
                img, note = hin.capture_window(h)
                if img is None:
                    last_note = note
                    continue
                folder = os.path.join(r"D:\new_automation\data", "escalations")
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, f"esc_{int(time.time())}_{h}.png")
                img.save(path, format="PNG")
                self.escalation_shots.append({"path": path, "why": why[:120], "title": hin.safe_window_text(h)[:60]})
                return path
            # Nothing captured: the human still gets the record, with the Win32 reason, instead of silence.
            self.escalation_shots.append({"path": "", "why": why[:120],
                                          "title": hin.safe_window_text(owner_hwnd)[:60],
                                          "capture": (last_note or "no-dialog-window-found")[:160]})
        except Exception as exc:
            logger.debug("[escalate] screenshot failed: %s", exc)
        return ""

    def _triage_popups(self, app_hint: str, mode: str = "inflight") -> List[str]:
        """Resolve blocking dialogs of the target app (popup_policy), then let organ_29 take any
        remaining system-level modal. Headless; destructive/elevation prompts escalate to a human."""
        handled: List[str] = []
        if not _IS_WINDOWS:
            return handled
        from core_organs import popup_policy as pp
        hwnd = self.grounding.find_window(app_hint)
        if hwnd:
            try:
                with _POPUP_LOCK:                   # TASK is process-global state: set + use as one unit (parallel children)
                    pp.TASK.paths = tuple(getattr(self, "_task_paths", ()))
                    pp.TASK.allow_destructive = bool(getattr(self, "_allow_destructive", False))
                    pp.TASK.mode = mode
                    res = pp.clear_blockers(hwnd, mode=mode, task_paths=getattr(self, "_task_paths", ()),
                                            allow_destructive=getattr(self, "_allow_destructive", False))
                handled.extend(res["handled"])
                if res["need_human"]:
                    self.awaiting_human = True
                    self._save_escalation_shot(hwnd, "; ".join(res.get("handled") or [])[:100])
                    self.capsule_cb("input_needed", "A dialog needs your decision")
            except Exception as exc:
                logger.debug("[popups] policy pass note: %s", exc)

        # organ_29: anything else on top of the desktop that is not a dialog of this app
        try:
            from core_organs.organ_29_popup_handler import DesktopInteractionManager
            if getattr(self, "_o29", None) is None:
                self._o29 = DesktopInteractionManager()
            ph = self._o29
            for mhwnd, title, _cls in ph._detect_desktop_top_modals():
                low = (title or "").lower()
                if any(k in low for k in ("uac", "user account control", "elevate", "password", "administrator")):
                    self.awaiting_human = True
                    self.capsule_cb("input_needed", "Approval dialog needs you")
                    handled.append(f"uac-shield->HITL '{title[:30]}'")
                    continue
                if hwnd and hin.window_pid(mhwnd) == hin.window_pid(hwnd):
                    continue  # already handled by the policy engine
                if _is_file_dialog_title(title) or _is_overwrite_confirm(title):
                    continue
                node = ph.wrap_hwnd(mhwnd)
                if node:
                    success, _, _, action = ph.resolve_and_mitigate(node)
                    if success:
                        handled.append(f"organ29-dismissed '{title[:30]}' via '{action}'")
        except Exception as exc:
            logger.debug("[popups] organ_29 triage note: %s", exc)
        return handled

    def _click_dialog_button(self, hwnd: int, wanted: Tuple[str, ...]) -> Optional[str]:
        if not HAS_UIA:
            return False
        import uiautomation as auto
        try:
            ctrl = auto.ControlFromHandle(hwnd)
            if ctrl is None:
                return None
            stack = [ctrl]
            while stack:
                c = stack.pop()
                try:
                    role = (c.ControlTypeName or "").lower()
                    name = (c.Name or "").strip().lower()
                    if "button" in role and any(w in name for w in wanted):
                        try:
                            c.GetInvokePattern().Invoke()
                            return name
                        except Exception:
                            r = c.BoundingRectangle
                            ok, _n = hin.post_click(hwnd, (r.left + r.right) // 2, (r.top + r.bottom) // 2)
                            return name if ok else None
                    stack.extend(c.GetChildren())
                except Exception:
                    continue
        except Exception:
            pass
        return None

    # ---- native Open/Save dialog driver (organ_24 NativeFilePicker + UIA) ----
    def handle_native_file_dialog(self, path: str, confirm_words: Tuple[str, ...] =
                                  ("save", "open", "ok"),
                                  owner_hwnd: int = 0) -> Tuple[bool, str]:
        """Runs on the dedicated, initialised UIA thread (same as every other UIA action).

        ``owner_hwnd`` scopes the rung to the app being driven: a Save/Open picker belonging to
        some other still-open app must never be filled in and confirmed."""
        global _UIA_EXEC
        if _UIA_EXEC is None:
            from concurrent.futures import ThreadPoolExecutor
            _UIA_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia-act", initializer=_uia_thread_init)
        try:
            ok, note = _UIA_EXEC.submit(self._handle_native_file_dialog_impl, path,
                                        confirm_words, owner_hwnd).result(timeout=25)
            # what the recognizer could NOT settle inside the dialog (a name box that may refuse a path) goes
            # into the step evidence, so a run says it rather than leaving the reader to infer it
            side_note = getattr(self, "_file_dialog_note", "") or ""
            self._file_dialog_note = ""
            return ok, (f"{note} | {side_note}" if side_note else note)
        except Exception as exc:
            self._file_dialog_note = ""
            return False, f"file-dialog worker failed: {type(exc).__name__}: {exc}"

    def _handle_native_file_dialog_impl(self, path: str, confirm_words: Tuple[str, ...] =
                                  ("save", "open", "ok"), owner_hwnd: int = 0) -> Tuple[bool, str]:
        if not _IS_WINDOWS:
            return False, "non-windows"
        want_proc = self.grounding._process_stem_cached(owner_hwnd) if owner_hwnd else ""

        # Try organ_24 NativeFilePicker when available
        try:
            dap = self.dap_core
            if dap and hasattr(dap, "file_picker") and dap.file_picker:
                dlg = dap.file_picker.locate_dialog()
                dlg_proc = (self.grounding._process_stem_cached(int(getattr(dlg, "hwnd", 0) or 0))
                            if dlg is not None and want_proc else "")
                if dlg and not (want_proc and dlg_proc != want_proc):
                    # success is only claimed after the box was READ BACK and the accept result came back
                    # SUCCESS; anything else drops to the shape recognizer below, which does the same job
                    # with UIA and reports its own reason. An ERROR result used to be returned as True.
                    dap.file_picker.select_path(dlg, path)      # raises unless the box read the value back
                    res = dap.file_picker.confirm(dlg)
                    status = str(getattr(res, "status", "") or "")
                    if status == "SUCCESS":
                        return True, f"organ_24 file-picker selected '{path}'"
                    note = str(((getattr(res, "error", None) or {}).get("message") if isinstance(getattr(res, "error", None), dict) else getattr(res, "error", "")) or "accept did not report SUCCESS")
                    logger.info("[file-picker] organ_24 rung not claimed: %s (falling through to the shape recognizer)", note)
        except Exception as exc:
            logger.info("[file-picker] organ_24 rung not claimed: %s: %s (falling through to the shape recognizer)",
                        type(exc).__name__, exc)

        # ONE recognizer for the whole system (organ_24 SECTION 11B). It asks a window for its SHAPE - a name
        # box, an enabled accept button, evidence it is about the file system - instead of matching a vendor's
        # window-class name in a branch, so a family that draws its picker differently is still seen. Measured
        # here: an UNTITLED dialog of a non-common class held the entire save, every step answered
        # 'no-file-dialog-visible', and the app sat modal behind a screen the loop kept clicking.
        try:
            from core_organs import organ_24_dap as _dap_mod
        except Exception:  # noqa: BLE001
            _dap_mod = None
        owner_pid = 0
        if owner_hwnd:
            try:
                owner_pid = int(hin.window_pid(int(owner_hwnd)) or 0)
            except Exception:  # noqa: BLE001
                owner_pid = 0
        user32 = ctypes.windll.user32
        target = None
        target_shape: Dict[str, Any] = {}
        foreign: List[str] = []

        def _adopt(reps: List[Dict[str, Any]]) -> None:
            nonlocal target, target_shape
            for rep in reps:
                h = int(rep.get("hwnd") or 0)
                if not h or h == int(owner_hwnd or 0):
                    continue
                if want_proc:
                    proc = self.grounding._process_stem_cached(h)
                    if proc != want_proc:
                        # Somebody else's picker: never type a path into it, never click Save.
                        foreign.append(f"'{_quick_title(h)}'({proc or 'unknown-proc'})")
                        continue
                target, target_shape = h, rep
                return

        if _dap_mod is not None:
            try:
                _adopt(_dap_mod.find_file_dialogs(owner_pid=owner_pid, limit=6))
            except Exception as exc:  # noqa: BLE001
                logger.debug("[file-dialog] shape scan failed: %s", exc)

        if target is None:
            # Fallback kept on purpose: a dialog whose UIA tree could not be read (timeout, or UIA off) is
            # still a dialog by window kind, and losing it used to be silent. Class kinds come from the same
            # data table, so this path cannot drift from the recognizer above.
            _kinds = tuple(getattr(_dap_mod, "DIALOG_CLASS_CERTAIN", ("#32770", "NUIDialog"))) + tuple(
                getattr(_dap_mod, "DIALOG_CLASS_RECOGNISED", ())) if _dap_mod else ("#32770", "NUIDialog")
            _hints = tuple(getattr(_dap_mod, "DIALOG_TITLE_HINTS", ("save", "open"))) if _dap_mod else ("save", "open")

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def _cb(hwnd, _l):
                nonlocal target
                if target is not None or not user32.IsWindowVisible(hwnd):
                    return True
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                if cls_buf.value not in _kinds:
                    return True
                t = _quick_title(hwnd).lower()
                # a titled dialog of a known kind is taken on the hint; an UNTITLED one has to show its
                # name box, otherwise every pane of that class would look like a save dialog
                if not any(w in t for w in _hints) and not _dialog_holds_name_box(int(hwnd)):
                    return True
                if want_proc:
                    proc = self.grounding._process_stem_cached(hwnd)
                    if proc != want_proc:
                        foreign.append(f"'{_quick_title(hwnd)}'({proc or 'unknown-proc'})")
                        return True
                target = hwnd
                return True

            user32.EnumWindows(_cb, 0)

        # Only a Win32 common dialog is KNOWN to take an absolute path: its IDFILENAME edit is a path box by
        # OS contract. Any other shape may refuse one (measured: with 'D:\...\file.xlsx' in its name box the
        # accept button stayed DISABLED however long we waited, while a bare name kept it live). So ask the
        # app, through its own controls, for the full picker - walking routes that are DATA, never a
        # hard-coded road per family - and if nothing answers, SAY so instead of clicking an empty screen.
        def _full_picker() -> Dict[str, Any]:
            """Cheap first (window kind + process), then one bounded shape read to confirm it takes a path."""
            if _dap_mod is None:
                return {}
            probe: Dict[str, Any] = {}
            listed = tuple(getattr(_dap_mod, "DIALOG_CLASS_CERTAIN", ("#32770",)))

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def _f(h2, _l2):
                if probe:
                    return True
                h = int(h2)
                if h == int(target or 0):
                    return True
                if hin._class_name(h) in listed and user32.IsWindowVisible(h2):
                    if not want_proc or self.grounding._process_stem_cached(h) == want_proc:
                        probe.update({"hwnd": h, "certain": True})
                return True

            user32.EnumWindows(_f, 0)
            return probe

        if (target and path and target_shape and re.match(r"^[A-Za-z]:[\\/]", path)
                and not target_shape.get("certain")):
            try:
                from core_organs import fast_uia as _fu
                from core_organs import organ_48_app_behavior_model as _bmx

                def _press(root_hwnd: int, pattern: str, wait_s: float) -> bool:
                    """Press whatever control this app CALLS the next hop, by prefix. Not found is an answer,
                    not a reason to poke: it returns False and the route moves on."""
                    end = time.time() + wait_s
                    while time.time() < end:
                        for n in (_fu.snapshot(int(root_hwnd), timeout_ms=3000) or []):
                            if (n.name and n.name.lower().startswith(pattern)
                                    and n.ctype in ("ButtonControl", "HyperlinkControl", "SplitButtonControl")
                                    and "invoke" in n.pats and n.enabled):
                                return bool(_bmx.invoke_node_safely(n)[0])
                        time.sleep(0.4)
                    return False

                routes = tuple(getattr(_dap_mod, "DIALOG_PATH_ROUTES", ()))
                t_end = time.time() + 12.0
                for route in routes:
                    if _full_picker() or time.time() >= t_end:
                        break
                    for hop, pattern in enumerate(route):
                        # hop 0 lives in the dialog, the hops after it in the pane the previous one opened.
                        # A hop that is not there YET is normal (Office's Save As page renders empty for
                        # seconds while it asks for places), so look again instead of giving up the route.
                        root = int(target) if hop == 0 else int(owner_hwnd or _root_of(int(target)))
                        t_hop = min(t_end, time.time() + 5.0)
                        pressed = False
                        while time.time() < t_hop and not _full_picker():
                            if pressed:
                                time.sleep(0.6)              # wait for the surface the press opened
                                continue
                            pressed = _press(root, pattern, 1.5)
                            if not pressed:
                                time.sleep(0.7)
                    cd = _full_picker()
                    if cd:
                        cd = dict(cd, **(_dap_mod.file_dialog_shape(int(cd["hwnd"]), timeout_ms=2000) or {}))
                        target, target_shape = int(cd["hwnd"]), cd
                        logger.info("[file-dialog] name-only dialog -> route %s -> full picker %s", route, cd["hwnd"])
                        break
                if not target_shape.get("certain"):
                    # Say what was actually found rather than pretending the path will go in: the box before
                    # the loop takes a NAME, and a full path may be refused by it. The driver still tries it
                    # (some name boxes do accept one) and the file postcondition, not this note, judges.
                    self._file_dialog_note = (f"dialog {target} ({target_shape.get('class') or 'unknown-kind'}) "
                                              f"offers a name box; no control in its own tree opened the full "
                                              f"picker (routes tried: {len(routes)})")
                    logger.info("[file-dialog] %s", self._file_dialog_note)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[file-dialog] path-route failed: %s", exc)
        if not target:
            if foreign:
                return False, (f"file-dialog belongs to another app, not the target "
                               f"({', '.join(foreign[:3])}) -> not touched")
            return False, "no-file-dialog-visible"
        if HAS_UIA:
            import uiautomation as auto
            stage = "read the dialog's control tree"
            try:
                ctrl = auto.ControlFromHandle(target)
                edits, buttons = [], []
                stack = [ctrl]
                while stack:
                    c = stack.pop()
                    try:
                        role = (c.ControlTypeName or "").lower()
                        if "edit" in role:
                            edits.append(c)
                        if "button" in role:
                            buttons.append(c)
                        stack.extend(c.GetChildren())
                    except Exception:
                        continue

                def _aid(c) -> str:
                    return (getattr(c, "AutomationId", "") or "").strip()

                def _field_ok(c, ids_attr: str, hint) -> bool:
                    """Data table first (a Win32 control id is locale-independent), the caption hint second,
                    and 'not a file-list column cell' as the floor. No English word is ever the only gate."""
                    ids = tuple(str(a) for a in getattr(_dap_mod, ids_attr, ()) or ()) if _dap_mod else ()
                    a = _aid(c)
                    if any(i and i == a for i in ids):
                        return True
                    if a.startswith("System."):                       # a column cell, never the name box
                        return False
                    return bool(hint and hint.search((c.Name or "") or ""))

                # The filename box is the Edit carrying the Win32 name-field id (or a name-box caption, or a
                # plain edit that is not a file-list column). The first Edit in the tree is usually a
                # file-LIST CELL ('System.ItemNameDisplay'), and writing the path into that silently does nothing.
                fname = next((c for c in edits if _field_ok(c, "DIALOG_NAME_FIELD_AIDS", _NAME_BOX_CAPTION_HINT)), None) \
                    or next((c for c in edits if not _aid(c).startswith("System.")), None)
                if fname is None:
                    return False, "file-dialog: filename field not found"
                # Type it the way the dialog expects (real EN_CHANGE events), headless: select-all,
                # clear, then one WM_CHAR per character to the edit's own HWND. A programmatic
                # SetValue/WM_SETTEXT changes the visible text but Save keeps the old default name.
                stage = "write the file-name field"
                eh = int(getattr(fname, "NativeWindowHandle", 0) or 0)
                if eh:
                    _res = ctypes.c_size_t(0)
                    hin._u32.SendMessageTimeoutW(eh, 0x00B1, 0, -1, 0x2, 800, ctypes.byref(_res))   # EM_SETSEL(0,-1)
                    hin._u32.SendMessageTimeoutW(eh, 0x0303, 0, 0, 0x2, 800, ctypes.byref(_res))    # WM_CLEAR
                    for _ch in path:
                        hin._u32.PostMessageW(eh, 0x0102, ord(_ch), 1)                                # WM_CHAR
                    time.sleep(0.6)
                else:
                    fname.GetValuePattern().SetValue(path)
                try:
                    got = fname.GetValuePattern().Value
                    if os.path.basename(path).lower() not in (got or "").lower():
                        return False, f"file-dialog: filename field did not take the value (has '{got}')"
                except Exception:
                    pass
                # Vista-style dialogs commit the typed name on an Enter delivered to the edit itself (a
                # programmatic set alone leaves the dialog's internal 'current name' untouched). Post
                # Enter to the edit's HWND; if the dialog is still up afterwards, fall back to Save.
                if eh:
                    hin.post_key_combo(eh, "enter")
                    _end = time.time() + 1.5
                    while time.time() < _end:
                        time.sleep(0.15)
                        if not hin.is_alive(target) or not hin._u32.IsWindowVisible(target):
                            return True, "file-dialog name set + Enter posted to the filename edit"
                stage = "choose the dialog's accept control"
                accept_ids = tuple(str(a) for a in getattr(_dap_mod, "DIALOG_ACCEPT_AIDS", ("1",)) or ()) if _dap_mod else ("1",)
                _never = tuple(getattr(_dap_mod, "DIALOG_NEVER_PRESS", ()) or ()) if _dap_mod else ()
                confirm = next((b for b in buttons if _aid(b) in accept_ids), None) \
                    or next((b for b in buttons
                             if (b.Name or "").strip().lower() in confirm_words
                             and not any(b.Name.strip().lower().startswith(n) for n in _never)), None) \
                    or next((b for b in buttons if any(w == (b.Name or "").strip().lower() for w in confirm_words)), None)
                if confirm is None:
                    return False, "file-dialog: confirm button not found"
                stage = "press the dialog's accept control"
                confirm.GetInvokePattern().Invoke()
                return True, f"file-dialog name set + clicked '{(confirm.Name or '').strip()}'"
            except Exception as exc:
                # Name the window and the stage. A bare COM number ('-2147220992') said nothing about WHERE the
                # picker broke, so eight failures in a row could not be told apart from one kind. Measured: it is
                # the tree read of a dialog stacked behind another modal dialog that throws, not the name field.
                ident = f"{hin._class_name(target) or 'no-class'}"
                title = hin.safe_window_text(target)
                if title:
                    ident += f" '{title[:40]}'"
                return False, (f"file-dialog uia failed while trying to {stage} on dialog {target} ({ident}): "
                               f"{type(exc).__name__}: {str(exc)[:90]}")
        return False, "no-uia-for-dialog"

    # ---- stuck goal -> WIDEN PERCEPTION (a stuck goal means the loop is not seeing what it needs, not that it should poke harder) ----
    _COMMIT_VERBS = ("save", "open", "export", "import", "print", "apply", "ok", "submit", "send", "create", "add", "confirm", "done", "finish")

    def _goal_is_stuck(self, goal: str) -> bool:
        pend = sum((self._pending_clicks.get(goal) or {}).values())
        return pend >= 2 or self._goal_fails.get(goal, 0) >= 2 or len(self._opened_not_done.get(goal) or ()) >= 2

    def _realize_and_relook(self, hwnd: int, goal: str, elements, ladder) -> List[GroundedElement]:
        """Nothing actionable was perceived. On a virtualizing host (XAML/WinUI/UWP, and Chromium behind a
        wall) that is almost always because the content was never MATERIALIZED - not because the app has no
        controls (measured 2026-10-07: 'add 21 and 21' on Calculator judged 'invalid' three times because the
        parked window had laid out no buttons, then burned straight to HITL). Before handing the judge nothing,
        force a realization and look again: the 1-px sliver makes a parked UWP/WinUI app lay its content out
        (the same invisible nudge the actuation session already relies on), re-walk the tree, then widen. This
        is keyed by structure, never by an app name, so it lifts EVERY virtualizing app at once. Returns the
        freshest element list (the same object if genuinely nothing changed)."""
        try:
            from core_organs import background_window as bw
            bw.sliver(int(hwnd))                             # invisible; makes a parked UWP/WinUI window lay out
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.4)
        fresh = elements
        if HAS_UIA:
            try:
                walked = self.grounding._walk_uia(hwnd) or []
                if walked:
                    fresh = walked
            except Exception:  # noqa: BLE001
                pass
        try:
            widened = self._widen_perception(hwnd, goal, fresh, ladder)
            if widened:
                fresh = widened
        except Exception:  # noqa: BLE001
            pass
        return fresh

    def _reveal_by_scrolling(self, hwnd: int) -> bool:
        """Scroll a host's content through UIA's ScrollPattern - the one delivery path that works on a
        XAML/WinUI window (a posted wheel is dropped there). This exists for virtualized lists: a NavigationView
        footer item ('About') is not in the visual tree until it is scrolled into view, so no amount of re-reading
        finds it until something scrolls. The technique mirrors organ_50_layout_map: SetScrollPercent to the
        BOTTOM, which forces the layout manager to materialise items below the fold.

        Measured defect this removes: scrolling only the FIRST scrollable container lands on the outer window
        frame, not the navigation list, so the footer never realised. Every vertically-scrollable container is
        now driven to its end (bounded count), then left there so the caller's re-walk sees the realised items.
        The container is chosen by the PRESENCE of a vertical ScrollPattern, never by an app's control name -
        generic."""
        return reveal_by_scrolling(hwnd)

    def _widen_perception(self, hwnd: int, goal: str, elements: List[GroundedElement], ladder: Dict[str, Any]) -> List[GroundedElement]:
        """Two steps of a goal went by without the goal moving: more of the same controls would only repeat that. Look WIDER, cheapest first:
        (1) the RAW UIA view (one bulk read): Office / WinUI panes expose their commit buttons as non-'control' elements that the control-view
            walk never lists; (2) the pixel tiers aimed at the control the goal's own verb implies ('save ... as X' -> the Save control): OCR,
            then the local Qwen2.5-VL locator. Everything found is added to the grounded list with its tier named; the verifier still judges
            whatever gets pressed. Reported in ladder['stuck_widen'] so a stuck run says what it tried to see."""
        rep: Dict[str, Any] = {"raw_added": 0, "pixel": "not needed"}
        # PATIENCE first: a surface that opened but is still LOADING (measured: Office's Save As pane stays an empty page for seconds while it
        # asks the network for places) looks exactly like a screen with nothing to press. Poll the bulk tree, bounded, for it to grow.
        try:
            from core_organs import fast_uia as _fw
            t_w = time.time()
            _spent = getattr(self, "_patience_spent", {})
            _left = max(0.0, 12.0 - _spent.get(goal, 0.0))          # at most 12 s of waiting per goal, however often it stalls
            base_n = len(_fw.snapshot(hwnd, timeout_ms=5000) or [])
            while time.time() - t_w < min(5.0, _left):
                time.sleep(1.0)
                now_n = len(_fw.snapshot(hwnd, timeout_ms=5000) or [])
                if now_n >= base_n + 6:
                    rep["waited_s"] = round(time.time() - t_w, 1)
                    rep["grew"] = now_n - base_n
                    fresh = self.grounding._walk_uia(hwnd)
                    if fresh:
                        elements = fresh
                    break
            else:
                rep["waited_s"] = round(time.time() - t_w, 1)
                rep["grew"] = 0
            _spent[goal] = _spent.get(goal, 0.0) + (time.time() - t_w)
            self._patience_spent = _spent
        except Exception as exc:  # noqa: BLE001
            rep["wait_error"] = f"{type(exc).__name__}"
        have = {((e.name or "").strip().lower(), e.role, round(e.bbox[0] / 6), round(e.bbox[1] / 6)) for e in elements}
        mini = hin.is_minimized(hwnd) or _is_parked_offscreen(hwnd)
        added: List[GroundedElement] = []
        # only controls that NAME something the goal is about: the raw view also lists every hidden duplicate behind an open pane (measured: +95
        # elements, and the judge then oscillated between 'File Tab' and a hidden 'Backstage view')
        g_clean = re.sub(r"[a-z]:[\\/][^\s'<>|?*]+", " ", (goal or "").lower())
        about = {t for t in re.findall(r"[a-z0-9]+", g_clean) if t not in ConstrainedJudge._STOP and len(t) > 2}
        if re.search(r"[a-z]:[\\/]", (goal or "").lower()) and re.search(r"\b(save|open|export|import)\b", g_clean):
            about |= {"browse", "pc", "computer", "folder"}      # a goal that names a path is answered through the OS file picker ('Browse...')
        try:
            from core_organs import fast_uia as _fu

            def _scan_raw_into(dst: List[GroundedElement]) -> None:
                for n in (_fu.snapshot(hwnd, timeout_ms=6000) or []):
                    role = n.role
                    if role not in ACTIONABLE_ROLES or not (n.name or "").strip() or not n.enabled or (n.offscreen and not mini):
                        continue
                    if not (about & set(re.findall(r"[a-z0-9]+", n.name.lower()))):
                        continue
                    if not mini and not (n.rect[2] > n.rect[0] and n.rect[3] > n.rect[1]):
                        continue
                    key = (n.name.strip().lower(), role, round(n.rect[0] / 6), round(n.rect[1] / 6))
                    if key in have:
                        continue
                    have.add(key)
                    dst.append(GroundedElement(id=_element_id(hwnd, role, n.name, n.rect), name=n.name.strip(), role=role, bbox=n.rect,
                                               tier="uia", confidence=0.8, hwnd=hwnd))
            _scan_raw_into(added)
            rep["raw_added"] = len(added)
        except Exception as exc:  # noqa: BLE001
            rep["raw_error"] = f"{type(exc).__name__}: {str(exc)[:60]}"
            _scan_raw_into = None       # the import that drives it failed; the scroll step must not try to call it
        # A virtualized surface (a UWP NavigationView footer, a long list) builds its items only when they
        # scroll into view - the raw view above cannot name a control the visual tree has not made yet. When
        # none of the goal's own words surfaced at all, scroll once through the pattern XAML honours and read
        # again. Generic: it reacts to an ABSENT word the goal asked for, not to any particular app or item.
        if about and _scan_raw_into:
            seen_words = {t for e in (list(elements) + added) for t in re.findall(r"[a-z0-9]+", (e.name or "").lower())}
            if not (about & seen_words):
                try:
                    if self._reveal_by_scrolling(hwnd):
                        _before = len(added)
                        _scan_raw_into(added)
                        rep["scrolled_reveal"] = len(added) - _before
                except Exception as exc:  # noqa: BLE001
                    rep["scroll_error"] = f"{type(exc).__name__}: {str(exc)[:60]}"
        first = re.match(r"\s*(?:please\s+)?([a-z]+)", (goal or "").lower())
        target = first.group(1) if first and first.group(1) in self._COMMIT_VERBS else ""
        has_target = bool(target) and any(target == (e.name or "").strip().lower() and e.role in ("button", "splitbutton", "menuitem")
                                          for e in list(elements) + added)
        if target and not has_target:
            try:                                         # the verb's control is still not on the list: look at the PIXELS
                px: List[GroundedElement] = []
                if HAS_PYTESSERACT and HAS_PIL:
                    px = [e for e in self.grounding._walk_ocr(hwnd) if target in (e.name or "").lower()]
                    rep["pixel"] = f"ocr found {len(px)}"
                if not px:
                    r2: Dict[str, Any] = {}
                    px = self.grounding._qwen_locate(hwnd, target, r2)
                    rep["pixel"] = f"qwen-vl locate '{target}': {len(px)} hit(s)" + (f" {r2.get('tiers_skipped')}" if r2.get("tiers_skipped") else "")
                added.extend(px)
            except Exception as exc:  # noqa: BLE001
                rep["pixel"] = f"failed: {type(exc).__name__}: {str(exc)[:60]}"
        ladder["stuck_widen"] = rep
        try:                       # a picture of what the loop is stuck ON (the same evidence a human gets when it escalates)
            _n_shots = getattr(self, "_stuck_shots", {})
            if _n_shots.get(goal, 0) < 8:
                _n_shots[goal] = _n_shots.get(goal, 0) + 1
                self._stuck_shots = _n_shots
                from core_organs import task_lifecycle as _tl
                shot = _tl.capture_evidence("", f"stuck: {goal[:60]}", hwnd=hwnd)
                rep["screenshot"] = shot.get("path") or shot.get("note")
        except Exception:  # noqa: BLE001
            pass
        if rep["raw_added"] or added:
            logger.info("[stuck] goal %r: widened perception (+%d element(s)): %s", (goal or "")[:50], len(added), rep)
        return list(elements) + added

    # ---- W8: consult app intelligence (the "pro knowledge" layer) ----
    def _consult_intel(self, app_hint: str, goal: str) -> Optional[Dict[str, Any]]:
        """Ask organ_47 what an expert would do for this goal in this app.

        Returns a normalized dict, or None when intel is unavailable/blank:
          {kind: 'shortcut', shortcut, confidence, source, step_id}
          {kind: 'element', element_name, element_role, menu_path, confidence, ...}
        A confident LEARNED shortcut is executed directly; everything else is
        handed to the judge as a ranked hint (never as an authoritative answer).
        """
        if self.intel is None:
            return None
        try:
            pb = self.intel.playbook(app_hint, goal, allow_llm_briefing=True)
        except Exception as exc:
            logger.debug("[intel] playbook failed: %s", exc)
            return None
        if not pb or not pb.hints:
            return None
        top = pb.hints[0]
        # Best non-destructive keyboard route among ALL hints (the top hint may be an element
        # click with no shortcut, which would hide the keyboard route from the recovery rung).
        kb_route = next((h.shortcut for h in pb.hints if h.shortcut and not h.destructive), "")
        # Only a genuinely-verified shortcut may skip the judge. An unverified
        # archetype guess must never take direct control of the machine.
        if (top.shortcut and top.source == "learned"
                and top.confidence >= PRO_SHORTCUT_CONF and not top.destructive
                and getattr(top, "successes", DIRECT_MIN_SUCCESSES) >= DIRECT_MIN_SUCCESSES):
            return {"kind": "shortcut", "shortcut": top.shortcut,
                    "confidence": top.confidence, "source": top.source,
                    "step_id": top.step_id, "goal": goal, "kb_route": kb_route}
        return {"kind": "element", "kb_route": kb_route, "element_name": top.element_name,
                "element_role": top.element_role, "menu_path": top.menu_path,
                "verb": top.verb, "shortcut": top.shortcut,
                "confidence": top.confidence, "source": top.source,
                "step_id": top.step_id, "goal": goal}

    def _reinforce(self, app_hint: str, goal: str, pro: Optional[Dict[str, Any]],
                   verdict: str) -> None:
        """Feed the outcome back into organ_47. PASS climbs, anything else erodes."""
        if self.intel is None or not pro:
            return
        try:
            self.intel.record_step(
                app_hint, goal, pro.get("verb", "click"),
                element_name=pro.get("element_name", ""),
                element_role=pro.get("element_role", ""),
                shortcut=pro.get("shortcut", ""),
                menu_path=pro.get("menu_path", ""),
                outcome="PASS" if verdict == "PASS" else "FAIL",
                source="learned")
        except Exception as exc:
            logger.debug("[intel] reinforce failed: %s", exc)

    def _recipe_hint_for(self, goal: str) -> Optional[Dict[str, Any]]:
        """Turn the recalled organ_04 recipe into a soft judge hint for THIS goal.

        distill_recipe writes: "VERB on 'element' (method) to achieve: goal THEN ...".
        We extract the element name whose 'to achieve' clause best matches the goal and
        hand it to the ranker as an element_name hint (never as an authoritative shortcut,
        so the postcondition verifier stays the only thing that can produce a PASS)."""
        recipe = getattr(self, "_recalled_recipe", "") or ""
        if not recipe or " to achieve: " not in recipe:
            return None
        gl = (goal or "").lower().strip()
        best_name, best_score = "", 0.0
        for verb, name, achieved in re.findall(
                r"([A-Za-z_]+) on '([^']*)' \([^)]*\) to achieve:\s*(.*?)(?= THEN | \||$)", recipe):
            a = (achieved or "").lower().strip()
            gtokens = set(re.findall(r"[a-z]+", gl))
            atokens = set(re.findall(r"[a-z]+", a))
            score = len(gtokens & atokens) / (len(gtokens | atokens) or 1)
            if score > best_score:
                best_name, best_score = name, score
        if best_score < 0.34 or not best_name:
            return None
        return {"kind": "element", "element_name": best_name, "menu_path": "",
                "kb_route": "", "shortcut": "", "verb": "click",
                "confidence": round(min(0.6, best_score + 0.2), 2),
                "source": "recipe", "step_id": "", "goal": goal}

    # ---- one closed-loop step ----
    def is_app_crashed_or_hung(self, hwnd: int) -> bool:
        if not (_IS_WINDOWS and hwnd):
            return False
        try:
            if ctypes.windll.user32.IsHungAppWindow(hwnd):
                return True
            t = _quick_title(hwnd).lower()
            if "not responding" in t or "(hung)" in t:
                return True
        except Exception:
            pass
        return False

    def step(self, goal: str, app_hint: str, expect: Optional[Dict[str, Any]] = None,
             allow_destructive: bool = False, max_tier: int = 2) -> Dict[str, Any]:
        expect = expect or {}
        self._run_depth += 1                       # a bare step() (no run()) releases what it parked when it returns
        try:
            return self._step_impl(goal, app_hint, expect, allow_destructive, max_tier)
        finally:
            self._run_depth -= 1
            if self._run_depth == 0:
                self._release_held()

    def _step_impl(self, goal: str, app_hint: str, expect: Dict[str, Any],
                   allow_destructive: bool, max_tier: int) -> Dict[str, Any]:
        self._hold_hidden(app_hint)
        self._triage_popups(app_hint)

        hwnd, elements, ladder = self.grounding.ground(app_hint,
                                                      target_text=str(expect.get("element_appeared", "")),
                                                      max_tier=max_tier)

        # Crash / "Not Responding" detection: relaunch via organ_40 and resume
        if hwnd and self.is_app_crashed_or_hung(hwnd):
            try:                                                           # B2: one stat before any relaunch
                from core_organs import organ_48_app_behavior_model as _bm2
                _exe = _bm2._exe_of_hwnd(hwnd)
            except Exception:
                _exe = ""
            if _exe and not os.path.isfile(_exe):
                self._launch_note = f"executable missing ({_exe}); not relaunching"
                logger.warning("[autonomy] %s", self._launch_note)
                entry = StepTrace(goal, "-", "-", "WRONG_STATE", "relaunch", self._launch_note, ladder["tiers_ran"])
                self.trace.append(entry)
                return self._step_result(entry, elements=[])
            logger.warning("[autonomy] App %s (hwnd=%s) is hung/crashed. Relaunching...", app_hint, hwnd)
            self.capsule_cb("working", f"Relaunching {app_hint} (not responding)")
            try:
                from core_organs.organ_40_app_launcher import resolve_and_launch
                resolve_and_launch(app_hint)
                time.sleep(2.0)
                hwnd, elements, ladder = self._wait_for_ready(app_hint)
            except Exception as e_relaunch:
                logger.error("[autonomy] Relaunch failed: %s", e_relaunch)

        if not elements:
            self.capsule_cb("working", f"Scanning {app_hint} (no controls yet)")
            entry = StepTrace(goal, "-", "-", "WRONG_STATE", "ground",
                              f"no elements; ladder={ladder}", ladder["tiers_ran"])
            self.trace.append(entry)
            return self._step_result(entry, elements=[])

        # A TYPING goal needs a surface to hold its payload. The instance can lose it mid-run (it dies, the fresh one
        # opens on its own start screen), and the run-start prepare step has already been spent. Measured: after such
        # a loss the loop typed into a launcher's search field and clicked 'Backstage view'. Bounded retries, and only
        # for goals that ask for text: pressing a create-document control during a SAVE goal would discard the very
        # unsaved work the goal is trying to keep.
        if (self._canvas_needed and self._canvas_prep_left > 0
                and re.match(r"^\s*(?:type|write|enter|input)\b", goal or "", re.I)
                and self._writable_surface(elements)[0] == 0):
            self._canvas_prep_left -= 1
            try:
                prep_note = self._ensure_blank_document(app_hint)
            except Exception as prep_exc:
                prep_note = f"canvas recovery failed ({type(prep_exc).__name__})"
            logger.info("[autonomy] canvas recovery inside goal: %s", prep_note)
            self.trace.append(StepTrace(goal, "(prepare)", "check", "PASS", "hygiene", prep_note, ladder["tiers_ran"]))
            hwnd, elements, ladder = self._wait_for_ready(app_hint)
            if not elements:
                entry = StepTrace(goal, "-", "-", "WRONG_STATE", "ground",
                                  f"no elements after canvas recovery; ladder={ladder}", ladder["tiers_ran"])
                self.trace.append(entry)
                return self._step_result(entry, elements=[])

        if hwnd and self._goal_is_stuck(goal):
            elements = self._widen_perception(hwnd, goal, elements, ladder)
        before = self.verifier.snapshot(hwnd, elements)
        if not expect:
            before.names = self._all_names(hwnd)      # the default postcondition also compares every UIA name
            before.modes = list(getattr(self, "_last_modes", []))
        elif self.bridge is not None:                 # 3.2/3.3: the state a transition starts from (names + mode indicators)
            before.names = self._all_names(hwnd)
            before.modes = list(getattr(self, "_last_modes", []))

        step_expect, goal_terminal = split_terminal_expect(expect)

        def _grade(after_els: List[GroundedElement]) -> Tuple[str, str, Optional[bool]]:
            """Judge the STEP by what the step can prove, and ask separately whether the goal's TERMINAL
            condition (a file on disk) now holds. The terminal truth outranks a step verdict in both
            directions: a step that produced the file is never a non-PASS, and a step that only moved the
            UI does not complete the goal (the caller advances on goal_done, not on a moved pixel)."""
            snap = self._snap(hwnd, after_els, step_expect)
            v, ev = self.verifier.verdict(step_expect, before, snap, after_els, goal=goal)
            if goal_terminal is None:
                return v, ev, None
            t_ok, t_ev = self.verifier.check_expect(goal_terminal, before, snap, after_els)
            if t_ok:
                v, ev = "PASS", (ev if v == "PASS" else f"{ev} | goal terminal condition met ({t_ev})")
            elif v == "PASS":
                ev = f"{ev} | goal still pending ({t_ev})"
            return v, ev, bool(t_ok)

        # ---- Native file dialog rung: a goal naming an absolute path + a visible
        # Save/Open dialog is resolved deterministically (type path, confirm), not by the LLM.
        path_m = re.search(r"[A-Za-z]:[\\/][^\s'<>|?*]+", goal or "")
        if path_m:
            fd_ok, fd_note = self.handle_native_file_dialog(path_m.group(0), owner_hwnd=hwnd)
            logger.info("[autonomy] file-dialog rung: ok=%s note=%s", fd_ok, fd_note)
            if fd_ok:
                time.sleep(0.6)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                verdict, evidence, goal_done = _grade(after_elements)
                self._history.append(f"file-dialog {path_m.group(0)} -> {verdict}")
                entry = StepTrace(goal, "file-dialog", "file-dialog", verdict, "native-file-dialog",
                                  f"{fd_note}; {evidence}", ladder["tiers_ran"])
                self.trace.append(entry)
                self._write_checkpoint(entry)
                self.capsule_cb("working", f"[{app_hint}] file dialog -> {verdict}")
                return self._step_result(entry, elements=after_elements, goal_done=goal_done)

        # ---- W8 PRO PATH: a confidently-learned shortcut beats the LLM ----
        pro = self._consult_intel(app_hint, goal)
        if pro is not None and pro.get("kind") == "shortcut" and self.judge._wants_text(goal):
            # typing goes into an editor: a "learned" shortcut for it (Ctrl+N after a weak 'the UI changed' pass) is not typing
            logger.info("[intel] ignoring learned shortcut %s for a typing goal", pro.get("shortcut"))
            pro = None
        # W5 learned re-run: with no organ_47 route, fall back to the distilled recipe hint
        # (soft ranking hint only - never takes direct control, only nudges the judge).
        if pro is None:
            pro = self._recipe_hint_for(goal)
        # Recovery rung: after 2 failed attempts on this goal the element route is evidently
        # not reachable (menus often live in a popup host the UIA tree cannot see), so try the
        # expert hint's keyboard route ONCE. Non-destructive only, focus proven, and the result
        # is still judged by the postcondition (an unverified guess never counts as success).
        # ---- K: unified command knowledge learned by scans/explorations (statically from the program file, live from
        # menus, explored surfaces, tested conventions). A VERIFIED command (>= 2 successes, postcondition, not E2) runs
        # directly; anything less only ranks the judge's shortlist.
        kb = None
        if self.bridge is not None:
            kb = self.bridge.consult(app_hint, goal, wants_text=self.judge._wants_text(goal))
            if kb is not None:
                direct, why = self.bridge.direct_ok(kb, goal)
                logger.info("[knowledge] goal=%r -> %r score=%.1f sources=%s direct=%s (%s)", goal[:40], kb["name"], kb["score"],
                            kb["sources"], direct, why)
                if direct and (pro is None or pro.get("kind") != "shortcut"):
                    return self._run_kb_route(kb, goal, app_hint, hwnd, before, expect, elements, ladder)
                acc, acc_why = self.bridge.accelerator_ok(kb, goal)
                if acc and (pro is None or pro.get("kind") != "shortcut") and self._goal_fails.get(goal, 0) < 2:
                    logger.info("[knowledge] declared accelerator attempt: %s", acc_why)
                    return self._run_kb_route(kb, goal, app_hint, hwnd, before, expect, elements, ladder, only="key",
                                              tag="knowledge:accelerator")
                if pro is None or pro.get("source") not in ("learned",):
                    pro = self.bridge.as_hint(kb)
        kb_key = (pro.get("shortcut") or pro.get("kb_route") or "") if pro is not None else ""
        kb_recovery = (pro is not None and pro["kind"] == "element" and bool(kb_key)
                       and self._goal_fails.get(goal, 0) >= 4
                       and (goal, kb_key) not in self._shortcut_tried)
        if kb_recovery:
            pro = dict(pro, shortcut=kb_key)
            self._shortcut_tried.add((goal, kb_key))
        if pro is not None and (pro["kind"] == "shortcut" or kb_recovery):
            self.capsule_cb("working", f"[{app_hint}] {pro['shortcut']} ("
                            + ("recovery" if kb_recovery else "learned pro") + ")")
            ok, method = _send_shortcut(pro["shortcut"], hwnd)
            time.sleep(0.8)  # let a dialog/menu open before verifying
            after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
            verdict, evidence, goal_done = _grade(after_elements)
            if verdict != "PASS" and hin.is_xaml_host(_root_of(hwnd)):
                evidence += " [XAML/WinUI host: posted keys are not delivered to XAML input - the shortcut cannot work headless; use the element route]"
                method += "+xaml-ignores-posted-keys"
            self._reinforce(app_hint, goal, pro, verdict)
            self._record_knowledge(app_hint, goal, kb=None, verb="key", target=pro.get("shortcut", ""), effector="key", verdict=verdict,
                                   before=before, expect=expect, hwnd=hwnd, evidence=evidence)
            self._goal_fails[goal] = 0 if verdict == "PASS" else self._goal_fails.get(goal, 0) + 1
            self._history.append(f"shortcut {pro['shortcut']} -> {verdict}")
            entry = StepTrace(goal, f"shortcut:{pro['shortcut']}", "shortcut", verdict,
                              method, evidence + " [intel:shortcut]", ladder["tiers_ran"])
            self.trace.append(entry)
            self._write_checkpoint(entry)
            if verdict == "PASS":
                self.capsule_cb("working", f"[{app_hint}] Verified: shortcut executed")
            return self._step_result(entry, elements=after_elements, goal_done=goal_done)

        spent = set(self._opened_not_done.get(goal) or set())
        # a control pressed twice with a 'UI changed' pass while the goal's terminal proof (the file) is still missing is not advancing the goal:
        # stop offering it (measured: an Office save goal pressed the toolbar 'Save' 11 times; each press 'passed' as a weak UI change)
        spent |= {n for n, c in (self._pending_clicks.get(goal) or {}).items() if c >= 2}
        # a menu / dropdown that is ALREADY OPEN is not pressed again (that closes it): its items are on screen. Measured: with 'File' open the hint
        # bonus kept 'File' on top and the loop toggled it shut, then pressed 'New' on a document holding the picture it had just pasted.
        try:
            spent |= {str(m).split("|", 1)[0] for m in (before.modes or []) if str(m).endswith("|expanded")}
        except Exception:  # noqa: BLE001
            pass
        if re.search(r"\b(?:save|export)\b", goal or "", re.I) and not re.search(r"\b(?:close|exit|quit|discard|don'?t)\b", goal or "", re.I):
            # a goal that SAVES is never advanced by closing the document or app (an unsaved sheet was once closed
            # with "Don't Save" four steps into a save-as); those controls are not offered to the judge for it
            spent |= {"close", "exit", "quit", "don't save", "do not save", "discard", "discard changes"}
        # an ACCOUNT control (a person's name, Sign in / Sign out / Switch account) is never a step toward an in-app goal that does not talk about
        # accounts: pressing it opens the user's profile menu (measured: an Excel save goal expanded the signed-in user's name)
        _chrome_ok = bool(self.judge._goal_tokens(goal) & self.judge._CHROME_GOAL_WORDS) or bool(DesktopVerifier._MAY_CLOSE_RE.search(goal or ""))
        _bar = _titlebar_buttons(elements, hwnd)
        _not_chrome = lambda e: _chrome_ok or ((e.name or "").strip().lower() not in self.judge._WINDOW_CHROME and id(e) not in _bar)
        offered = [e for e in elements if (e.name or "").strip().lower() not in spent and _not_chrome(e)
                   and not (e.role in ("menuitem", "button", "listitem", "splitbutton") and is_account_control(e.name, goal))]             or [e for e in elements if _not_chrome(e)]       # never fall back to the window's own title-bar buttons: with only chrome on screen there is NOTHING to press
        if logger.isEnabledFor(logging.INFO):
            try:
                _top = [(round(sc, 1), e.name[:20], e.role) for sc, _i, e in self.judge.rank_scored(goal, offered, pro)[:5]]
                logger.info("[judge] goal=%r offered=%d avoided=%s top=%s", goal[:50], len(offered), sorted(spent)[:4], _top)
            except Exception:
                pass
        if not offered:
            # Nothing actionable yet. On a virtualizing host (XAML/WinUI/UWP, Chromium walls) that usually
            # means the content was never materialized, NOT that the app has none - so force a realization
            # and look again before handing the judge nothing. Generic: keyed by structure, never app name.
            elements = self._realize_and_relook(hwnd, goal, elements, ladder)
            # The re-walk returned BRAND-NEW element objects: recompute the chrome guard against them. A
            # title-bar button's identity was carried in the OLD objects' ids, so with the stale set the fresh
            # 'Minimize Calculator' passed the filter and the judge pressed it - minimizing the target and
            # killing every later step (measured 2026-10-07, a decomposed six-press calculation self-minimized
            # on its third step). Re-deriving the bar here is what keeps the never-touch-the-window-chrome rule.
            _bar = _titlebar_buttons(elements, hwnd)
            _not_chrome = lambda e: _chrome_ok or ((e.name or "").strip().lower() not in self.judge._WINDOW_CHROME and id(e) not in _bar)
            offered = [e for e in elements if (e.name or "").strip().lower() not in spent and _not_chrome(e)
                       and not (e.role in ("menuitem", "button", "listitem", "splitbutton") and is_account_control(e.name, goal))] \
                      or [e for e in elements if _not_chrome(e)]
        _typed = re.match(r"""^\s*type\s+["“']([^"”']+)["”'](?:\s+(?:in|into)\s+.{1,60})?\s*$""", goal or "", re.I)   # 'in calculation field': a place the window does not have
        if not offered:                                     # still only chrome (or nothing): not a decision the judge may be asked to make
            decision = {"invalid": True, "raw": "", "why": "nothing but the window's title-bar buttons is on screen: no control to press for this goal"}
        elif _typed and len(elements) >= READY_RICH_ELEMENTS and not any(e.role in self.judge._TEXT_ROLES for e in elements):   # a laid-out UI with no text box, never a half-loaded shell
            # a typing goal in a window with NO text box anywhere (Calculator): the app takes the keys itself, so there is no control to choose and
            # the judge must not be asked (live Nov-02: it clicked the display pane '0' five times, UNDELIVERABLE each time, then BLOCKED)
            decision = {"element_index": 0, "verb": "type", "text": _typed.group(1), "keys_to_window": True,
                        "coerced": "type into the window: no text box on screen, the app takes the keys itself"}
        else:
            decision = self.judge.decide(goal, offered, app_hint=app_hint, history=self._history,
                                         pro_hint=pro)
        if decision and not decision.get("invalid") and offered is not elements:
            try:                                    # element_index must keep referring to the FULL grounded list
                decision["element_index"] = elements.index(offered[int(decision["element_index"])])
            except (ValueError, IndexError, KeyError, TypeError):
                decision = {"invalid": True, "raw": decision, "why": "index mapping lost"}
        if not decision or decision.get("invalid"):
            self.invalid_streak += 1
            evidence = f"invalid judge choice x{self.invalid_streak}"
            if self.invalid_streak >= INVALID_CHOICE_LIMIT:
                self.awaiting_human = True
                self.capsule_cb("input_needed", "Agent needs your input")
                entry = StepTrace(goal, "-", "-", "HITL", "judge", evidence, ladder["tiers_ran"])
                self.trace.append(entry)
                return self._step_result(entry)
            entry = StepTrace(goal, "-", "-", "NO_CHANGE", "judge", evidence, ladder["tiers_ran"])
            self.trace.append(entry)
            return self._step_result(entry)
        self.invalid_streak = 0

        elem = elements[decision["element_index"]]
        verb = decision["verb"]
        text = str(decision.get("text", ""))
        keys_mode = bool(decision.get("keys_to_window")) and verb == "type"
        if keys_mode:                                                          # the app SHOWS a result, not the keys typed ('7+5=' -> 12): the step passes on a
            step_expect = {k: v for k, v in (step_expect or {}).items() if k != "text_contains"}   # visible change, and the run's proof judges the result
        if verb == "type" and text and "text_contains" not in step_expect and not keys_mode:
            # A typed payload is verified by CONTENT, not by a hash: the text the judge actually
            # delivered becomes the postcondition, so a keystroke that landed cannot be called
            # NO_CHANGE (which used to make the ladder type it again) and text that went into the
            # wrong control cannot be called PASS (a path once went into 'Save as type:' and still
            # 'verified' because the dialog's pixels moved).
            step_expect = dict(step_expect, text_contains=text)

        if verb == "done":
            # A declared-done is never accepted on the declaration alone when the goal has a terminal proof:
            # the file either exists or the step is graded WRONG_STATE with the reason.
            d_snap = self._snap(hwnd, elements, step_expect)
            d_ok, d_ev = (True, "no terminal condition") if goal_terminal is None else \
                self.verifier.check_expect(goal_terminal, before, d_snap, elements)
            verdict = "PASS" if d_ok else "WRONG_STATE"
            entry = StepTrace(goal, elem.name, "done", verdict, "judge",
                              f"declared-done; terminal check: {d_ev}", ladder["tiers_ran"])
            self.trace.append(entry)
            self.capsule_cb("working", f"[{app_hint}] {'Verified' if d_ok else 'declared-done but goal not met'}")
            return self._step_result(entry, elements=elements, goal_done=bool(d_ok))

        # Blast radius guard: destructive element names need explicit opt-in.
        if any(cue in (elem.name or "").lower() for cue in DESTRUCTIVE_CUES) \
                and not allow_destructive:
            self.awaiting_human = True
            self.capsule_cb("input_needed", f"About to '{elem.name[:30]}' — confirm?")
            entry = StepTrace(goal, elem.name, verb, "HITL", "safety",
                              "destructive cue without allow_destructive", ladder["tiers_ran"])
            self.trace.append(entry)
            return self._step_result(entry)

        # Consequence gate (mind.consequence): money / publish / delete / sign-out / consent / install, a password typed by a script, a chord that closes the session.
        # The person is told WHAT it does and what to do instead; the answer has to come from them (allow_destructive), never from the model.
        try:
            if os.environ.get("HOJAIGA_CONSEQUENCE_GATE", "1") == "0":
                raise RuntimeError("gate switched off")
            from core_organs.mind import consequence as _CQ
            _cq = _CQ.assess_step(verb, elem.name, goal=goal, typed_text=text if verb == "type" else "", field=elem.name, chord=text if verb in ("key", "shortcut") else "", role=elem.role)
            if verb == "click" and decision.get("picker_confirm") and _cq["gate"] == "allow":
                _cq = {"gate": "confirm", "question": f"The trained model flagged '{elem.name[:40]}' as {decision['picker_confirm'].get('risk')}: {decision['picker_confirm'].get('does')}"}
        except Exception:
            _cq = {"gate": "allow"}
        if _cq.get("gate") == "block" or (_cq.get("gate") == "confirm" and not allow_destructive):
            self.awaiting_human = True
            self.capsule_cb("input_needed", _cq["question"][:140])
            entry = StepTrace(goal, elem.name, verb, "HITL", "consequence", _cq["question"][:300], ladder["tiers_ran"])
            self.trace.append(entry)
            return self._step_result(entry)

        if verb == "type" and path_m and _is_name_box_element(elem, hwnd):
            text = path_m.group(0)             # the goal's own path, verbatim (a model typed just the file's base name)
        self._typed_into = elem if verb == "type" else None
        self.capsule_cb("working", f"[{app_hint}] {verb} '{elem.name[:30]}'")
        if self.cursor_cb:
            try:
                cx, cy = elem.center
                self.cursor_cb(float(cx), float(cy))
            except Exception:
                pass

        if self.bridge is not None and verb in ("click", "invoke", "key", "shortcut"):
            gate = self.bridge.precheck(app_hint, elem.name, hwnd, self.grounding)
            if gate is not None and not gate["ok"]:             # 3.2: never fire a command whose mode precondition is unmet
                self._history.append(f"{verb} '{elem.name}' refused: {gate['why'][:60]}")
                entry = StepTrace(goal, elem.name, verb, "WRONG_STATE", "precondition", gate["why"], ladder["tiers_ran"])
                self.trace.append(entry)
                self._write_checkpoint(entry)
                self.capsule_cb("working", f"[{app_hint}] '{elem.name[:24]}' needs another mode first")
                return self._step_result(entry, elements=elements)
            if gate is not None and gate["repaired"]:
                self._history.append(f"mode repaired via {gate['repaired']} before '{elem.name}'")
        if keys_mode:                                                          # the characters go to the app's window, not into one control
            ok, method = hin.post_text(hwnd, text)
            method = f"keys-to-window:{method}"
        else:
            ok, method = _act_on_element(elem, verb, text)
        if not ok:
            # Delivery itself failed, so nothing that the UI does afterwards may be read as success.
            # A real run once "PASSed" a type whose window had already gone (UNDELIVERABLE), because
            # an unrelated structure change satisfied the default postcondition. Force NO_CHANGE and
            # re-ground on the next attempt; the retry ladder below is skipped on purpose, since
            # re-delivering into a control that refused the first time is how text got duplicated.
            self._goal_fails[goal] = self._goal_fails.get(goal, 0) + 1
            self._history.append(f"{verb} '{elem.name}' undeliverable")
            entry = StepTrace(goal, elem.name, verb, "NO_CHANGE", method,
                              "action not delivered -> never a PASS regardless of UI diff",
                              ladder["tiers_ran"])
            self.trace.append(entry)
            self._write_checkpoint(entry)
            self.capsule_cb("working", f"[{app_hint}] not delivered: {method[:44]}")
            return self._step_result(entry, elements=elements)
        if ok and verb in ("click", "invoke", "key", "shortcut"):
            self._settle(hwnd)

        # Verification step
        after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
        verdict, evidence, goal_done = _grade(after_elements)

        # NO_CHANGE retry ladder through organ_24 RecoveryEngine sequence:
        # wait/reinvoke -> PostMessage -> physical click
        if verdict == "NO_CHANGE" and ok and not keys_mode:                    # keys sent again would be typed twice
            # 1. Brief wait + re-invoke
            time.sleep(0.3)
            _act_on_element(elem, "invoke" if verb == "click" else verb, text)
            after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
            verdict, evidence, goal_done = _grade(after_elements)
            method += "+retry-invoke"

            # 2. If still NO_CHANGE, try PostMessage
            if verdict == "NO_CHANGE" and elem.hwnd:
                _postmessage_action(elem, verb, text)
                time.sleep(0.2)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                verdict, evidence, goal_done = _grade(after_elements)
                method += "+retry-postmessage"

            # 3. If still NO_CHANGE, post a coordinate click to the exact window (headless)
            if verdict == "NO_CHANGE":
                cx, cy = elem.center
                hin.post_click(_root_of(elem.hwnd or hwnd), cx, cy)
                time.sleep(0.25)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                verdict, evidence, goal_done = _grade(after_elements)
                method += "+retry-postclick"

        # A posted KEY into a XAML/WinUI host is not delivered by that UI stack: say so (and keep the verdict honest)
        # instead of letting it look like an unexplained NO_CHANGE.
        if verb in ("key", "shortcut") and verdict != "PASS" and hin.is_xaml_host(_root_of(hwnd)):
            evidence += " [XAML/WinUI host: posted keys are not delivered to XAML input - use a UIA-invokable element instead]"
            method += "+xaml-ignores-posted-keys"
            self._history.append(f"{verb} ignored by a XAML host")

        # A FILE NAME box (a Save As pane drawn inside the app, not a dialog window) that now holds the goal's path is COMMITTED the way a
        # person commits it: Enter in that very control. The dialog rung does this for real dialogs; Office's backstage has no dialog.
        if (verb == "type" and verdict == "PASS" and goal_done is False and path_m
                and _is_name_box_element(elem, hwnd) and "text has '" in (evidence or "")):
            try:
                _loc = _uia_dispatch(elem, "locate", "")
                _nat = int(_loc[1]) if _loc else 0
                # the pane's own COMMIT button first (a UIA Invoke is delivered by the control itself), Enter in the field otherwise
                # The commit button is looked up in the RAW UIA view (one bulk read): Office's pane exposes it as a non-'control' element, so the
                # ground list (control view) does not carry it - the left-hand 'Save' LIST ITEM is the only 'Save' it sees.
                _ok_e, _note_e = False, "no-commit-control"
                try:
                    from core_organs import fast_uia as _fu
                    from core_organs import organ_48_app_behavior_model as _bmx
                    from core_organs import organ_24_dap as _dap_c
                    _snap = _fu.snapshot(_root_of(elem.hwnd) or hwnd, timeout_ms=6000) or []
                    # the accept button by the SAME data tables the dialog rung uses (words and kinds live in data, not here)
                    _accept_words = tuple(getattr(_dap_c, "DIALOG_ACCEPT_WORDS", ("save", "ok")))
                    _never_press = tuple(getattr(_dap_c, "DIALOG_NEVER_PRESS", ("cancel", "close")))
                    _accept_kinds = tuple(k.lower() for k in getattr(_dap_c, "DIALOG_ACCEPT_ROLES", ("buttoncontrol",)))
                    _btn = next((n for n in _snap if str(n.ctype or "").lower() in _accept_kinds
                                 and any((n.name or "").strip().lower().startswith(w) for w in _accept_words)
                                 and not any(v in (n.name or "").lower() for v in _never_press)
                                 and "invoke" in n.pats and n.enabled), None)
                    logger.info("[commit] raw view of hwnd %s: %d nodes, commit button %s%s", _root_of(elem.hwnd), len(_snap), "found" if _btn is not None else "NOT found",
                                "" if _btn is not None else "; buttons=" + str([(n.name[:18], n.pats[:2], n.enabled) for n in _snap if n.ctype == "ButtonControl" and n.name][:14]))
                    if _btn is not None:
                        _ok_e, _how_e = _bmx.invoke_node_safely(_btn)
                        _note_e = f"invoked '{_btn.name}' ({_how_e})"
                except Exception as _exc2:  # noqa: BLE001
                    logger.info("[commit] raw-view commit lookup failed: %s: %s", type(_exc2).__name__, _exc2)
                if not _ok_e and (_nat or elem.hwnd):
                    _ok_e, _note_e = hin.post_key_combo(_nat or elem.hwnd, "enter")
                if _ok_e:
                    time.sleep(1.2)
                    after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                    verdict, evidence, goal_done = _grade(after_elements)
                    evidence += f" | committed from '{elem.name}': {_note_e}"
                    method += "+commit"
            except Exception as _exc:  # noqa: BLE001
                logger.debug("[commit] enter-commit skipped: %s", _exc)

        # On WRONG_STATE, triage popups first to dismiss unexpected roadblocks, then re-check
        if verdict == "WRONG_STATE":
            popup_notes = self._triage_popups(app_hint)
            if popup_notes:
                evidence += " | cleared: " + "; ".join(popup_notes)
                time.sleep(0.2)
                after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
                verdict, evidence, goal_done = _grade(after_elements)

        if verdict == "PASS":
            popup_notes = self._triage_popups(app_hint)
            if popup_notes:
                evidence += " | popups: " + "; ".join(popup_notes)
            # Capsule reports verified outcome, never bare "clicked"
            outcome_desc = evidence.replace(";", ",") if evidence else f"{verb} completed"
            self.capsule_cb("working", f"[{app_hint}] Verified: {outcome_desc[:36]}")

        # Reinforce the app-intelligence organ with the verified (or failed)
        # outcome, so the next run against this app gets a stronger honest prior.
        # A step that only 'changed the UI' while the goal's TERMINAL proof (the file) is still missing has proved nothing about the goal: it is not
        # taught as the way to do it (measured: 'File > New' reached confidence 0.97 for "save the document as ..." that way, then drove the
        # judge to press New on a canvas holding the user's drawing). The goal's steps are reinforced when the goal is proven done.
        # Likewise a PASS whose ONLY evidence is 'some names changed' with NO pixel moving and no mode change (default postcondition) is the signature of a
        # blank / hidden / closing window, not of a command that worked: it is not taught (a sign-in screen's title-bar Close reached 0.97 that way).
        _blank_pass = (verdict == "PASS" and not step_expect and goal_done is None and "below tolerance" in (evidence or "") and "modes +" not in (evidence or ""))
        if not (verdict == "PASS" and goal_done is False) and not _blank_pass:
            self._reinforce(app_hint, goal, {"kind": "element", "verb": verb,
                            "element_name": elem.name, "element_role": elem.role}, verdict)
        if verdict == "PASS" and goal_done:
            _seen_steps = set()
            for _st in self.trace:
                if _st.goal == goal and _st.verdict == "PASS" and _st.verb in ("click", "type", "invoke") and _st.element not in _seen_steps                         and _st.element != (elem.name or ""):
                    _seen_steps.add(_st.element)
                    self._reinforce(app_hint, goal, {"kind": "element", "verb": _st.verb, "element_name": _st.element, "element_role": ""}, "PASS")
        self._record_knowledge(app_hint, goal, kb=kb, verb=verb, target=elem.name, effector=method, verdict=verdict,
                               before=before, expect=step_expect, hwnd=hwnd, evidence=evidence)

        self._goal_fails[goal] = 0 if verdict == "PASS" else self._goal_fails.get(goal, 0) + 1
        if verb in ("click", "invoke") and verdict == "PASS" and goal_done is False:
            _pc = self._pending_clicks.setdefault(goal, {})
            _nm = (elem.name or "").strip().lower()
            _pc[_nm] = _pc.get(_nm, 0) + 1
        elif verdict == "PASS" and goal_done:
            self._pending_clicks.pop(goal, None)
        if verdict == "WRONG_STATE" and verb in ("click", "invoke"):
            self._opened_not_done.setdefault(goal, set()).add((elem.name or "").strip().lower())
        elif verdict == "WRONG_STATE" and verb == "type" and "text has '" in (evidence or ""):
            # The text IS in that control (the goal's other conditions - the file, the dialog - are what is missing):
            # typing it there again appends a duplicate (a filename box once read 401 chars of the same path).
            self._opened_not_done.setdefault(goal, set()).add((elem.name or "").strip().lower())
        elif verb == "type" and verdict == "PASS" and goal_done is False and "text has '" in (evidence or ""):
            # the control now HOLDS the text but the goal's terminal proof (the saved file) is still missing: the next move is to COMMIT it
            # (Save / Enter), not to type it again (measured: an Office backstage 'File name' box was typed five times, 210 chars)
            self._opened_not_done.setdefault(goal, set()).add((elem.name or "").strip().lower())
        elif verdict == "PASS":
            self._opened_not_done.pop(goal, None)
        self._history.append(f"{verb} '{elem.name}' -> {verdict}")
        entry = StepTrace(goal, elem.name, verb, verdict, method, evidence, ladder["tiers_ran"])
        if decision.get("brain_id"):                                        # the proven result goes back to the brain's ledger (and, for a teacher step, into the knowledge base)
            try:
                from core_organs.mind import brain as BR
                BR.outcome(decision["brain_id"], verdict, evidence)
            except Exception:
                pass
        self.trace.append(entry)
        self._write_checkpoint(entry)
        return self._step_result(entry, elements=after_elements, goal_done=goal_done)

    def _run_kb_route(self, kb: Dict[str, Any], goal: str, app_hint: str, hwnd: int, before: "Snapshot",
                      expect: Dict[str, Any], elements: List[GroundedElement], ladder: Dict[str, Any],
                      only: str = "", tag: str = "knowledge:direct") -> Dict[str, Any]:
        """Execute a VERIFIED unified command through its best route, then let the postcondition verifier judge it.
        A failure erodes the command (it stops qualifying for direct control) and the next step falls back to the judge."""
        self.capsule_cb("working", f"[{app_hint}] {kb['name']} (verified x{kb['successes']})")
        gate = self.bridge.precheck(app_hint, kb["name"], hwnd, self.grounding)
        if gate is not None and not gate["ok"]:
            entry = StepTrace(goal, kb["name"], "kb-route", "WRONG_STATE", "precondition", gate["why"] + f" [{tag} blocked]", ladder["tiers_ran"])
            self.trace.append(entry)
            self._write_checkpoint(entry)
            return self._step_result(entry, elements=elements)
        ok, eff, note = self.bridge.execute(kb, hwnd, self.grounding, only=only)
        if ok:
            self._settle(hwnd)
        after_elements = self.grounding._walk_uia(hwnd) if HAS_UIA else self.grounding._walk_win32(hwnd)
        # Same split as the judge path: a verified command that opens a menu is graded on the UI it moved,
        # and the goal's out-of-UI proof (the file) is asked separately - otherwise direct control would
        # erode its own best command on every intermediate step.
        step_expect, goal_terminal = split_terminal_expect(expect)
        snap = self._snap(hwnd, after_elements, step_expect)
        goal_done: Optional[bool] = None
        if ok:
            verdict, evidence = self.verifier.verdict(step_expect, before, snap, after_elements, goal=goal)
        else:
            verdict, evidence = "NO_CHANGE", f"route not delivered ({note})"
        if goal_terminal is not None:
            t_ok, t_ev = self.verifier.check_expect(goal_terminal, before, snap, after_elements)
            goal_done = bool(t_ok)
            if t_ok and verdict != "PASS":
                verdict, evidence = "PASS", f"{evidence} | goal terminal condition met ({t_ev})"
            elif verdict == "PASS":
                evidence = f"{evidence} | goal still pending ({t_ev})"
        self._record_knowledge(app_hint, goal, kb=kb, verb="invoke", target=kb["name"], effector=eff, verdict=verdict,
                               before=before, expect=expect, hwnd=hwnd, evidence=evidence)
        self._goal_fails[goal] = 0 if verdict == "PASS" else self._goal_fails.get(goal, 0) + 1
        self._history.append(f"knowledge {kb['name']} via {eff} -> {verdict}")
        entry = StepTrace(goal, kb["name"], "kb-route", verdict, eff, evidence + f" [{tag}]", ladder["tiers_ran"])
        self.trace.append(entry)
        self._write_checkpoint(entry)
        return self._step_result(entry, elements=after_elements, goal_done=goal_done)

    def _record_knowledge(self, app_hint: str, goal: str, *, kb: Optional[Dict[str, Any]], verb: str, target: str,
                          effector: str, verdict: str, before: "Snapshot", expect: Dict[str, Any], hwnd: int,
                          evidence: str) -> None:
        """3.3: every verified step becomes behavior knowledge: the command is reinforced/eroded, the effector outcome is
        recorded and the (state, action, effector) -> (state', evidence) transition is written. Never raises."""
        if self.bridge is None:
            return
        try:
            if kb is not None:
                from core_organs import command_registry as _cr
                if _cr.canon(target) not in {_cr.canon(n) for n in kb["names"]}:
                    kb = None                          # the judge chose something else: do not credit the hinted command
            after_names = self._all_names(hwnd) if verdict == "PASS" else []
            b = self.bridge.observe_light(hwnd, before.title, list(before.names or []), list(before.modes or []))
            a = self.bridge.observe_light(hwnd, _quick_title(hwnd), after_names, list(getattr(self, "_last_modes", []))) if verdict == "PASS" else None
            self.bridge.record(app_hint, goal, verb=verb, target=target, effector=effector, verdict=verdict,
                               before_state=b, after_state=a, evidence=evidence, kb=kb, strong=bool(expect))
        except Exception as exc:
            logger.debug("[knowledge] record failed: %s", exc)

    def _control_text(self, elements: List[GroundedElement]) -> str:
        """Longest readable text among the editable controls (UIA value/text pattern)."""
        best = ""
        checked = 0
        typed = getattr(self, "_typed_into", None)
        if typed is not None and (typed.role or "").lower() in ("dataitem", "cell") and typed.tier == "uia":
            out = _uia_dispatch(typed, "read", "")
            got = out[1] if out and out[0] is True else ""
            if isinstance(got, str) and got:
                best = got
        for e in elements:
            if (e.role or "").lower() not in ("edit", "document", "text", "richedit", "combobox"):
                continue
            if e.tier != "uia" or checked >= 6:
                continue
            checked += 1
            out = _uia_dispatch(e, "read", "")
            got = out[1] if out and out[0] is True else ""
            if isinstance(got, str) and len(got) > len(best) and not (best and typed is not None and typed.role in ("dataitem", "cell")):
                best = got
            if len(best) >= 4000:
                break
        return best[:8000]

    def _snap(self, hwnd: int, elements: List[GroundedElement],
              expect: Optional[Dict[str, Any]] = None) -> Snapshot:
        """Snapshot, reading control text only when a postcondition actually asks for it (the UIA
        value read costs a round trip per editable control)."""
        want_text = bool((expect or {}).get("text_contains"))
        snap = self.verifier.snapshot(hwnd, elements,
                                      text=self._control_text(elements) if want_text else "")
        if (expect or {}).get("name_visible") or (expect or {}).get("mode_on") or not expect:
            snap.names = self._all_names(hwnd)
            snap.modes = list(getattr(self, "_last_modes", []))
        return snap

    def _all_names(self, hwnd: int) -> List[str]:
        """Lower-cased name of EVERY UIA node of the window and its popups (one bulk CacheRequest snapshot)."""
        names: List[str] = []
        modes: List[str] = []
        try:
            from core_organs import fast_uia
            for w in [hwnd] + hin.popup_windows(hwnd)[:6]:
                for n in (fast_uia.snapshot(w, timeout_ms=3000) or []):
                    if not n.name:
                        continue
                    nm = (n.name or "").lower()
                    names.append(nm)
                    if n.selected:
                        modes.append(f"{nm}|selected")
                    if n.expand_state == 1:
                        modes.append(f"{nm}|expanded")
                    if getattr(n, "toggle_state", -1) == 1:
                        modes.append(f"{nm}|checked")
        except Exception as exc:
            logger.debug("[verify] name read failed: %s", exc)
        self._last_modes = modes
        return names

    def _settle(self, hwnd: int, timeout_s: float = 1.6, interval_s: float = 0.22) -> int:
        """Wait (bounded) until the app's element tree - popups/menus/dialogs included - stops
        changing. Menus and flyouts populate after the click returns; grounding too early sees
        the old UI and the loop would act on stale state (it re-clicked 'File' forever)."""
        if not HAS_UIA:
            time.sleep(0.4)
            return 0

        def _sig() -> Tuple[int, int, int]:
            main = len(self.grounding._walk_uia(hwnd, max_depth=8, max_nodes=300))
            extra = hin.popup_windows(hwnd)[:10]
            return main, len(extra), sum(len(self.grounding._walk_uia(w, max_depth=6, max_nodes=120)) for w in extra)

        deadline = time.time() + timeout_s
        last, stable, polls = _sig(), 0, 1
        while time.time() < deadline and stable < 2:
            time.sleep(interval_s)
            cur = _sig()
            polls += 1
            stable = stable + 1 if cur == last else 0
            last = cur
        # a menu reported EXPANDED whose flyout window has not appeared yet is still opening (XAML flyouts render a beat after the pattern call):
        # 'stable' was reached on the old tree. Wait, bounded, for the flyout - grounding now would offer the menu again instead of its items.
        try:
            from core_organs import fast_uia as _fu
            if any(n.ctype == "MenuItemControl" and n.expand_state == 1 for n in (_fu.snapshot(hwnd, timeout_ms=3000) or [])) and not hin.popup_windows(hwnd):
                t_end = time.time() + 3.0
                while time.time() < t_end and not hin.popup_windows(hwnd):
                    time.sleep(0.25)
                time.sleep(0.3)
        except Exception:  # noqa: BLE001
            pass
        return polls

    def resume_session(self, session_id: str, app_hint: str = "") -> Optional[Dict[str, Any]]:
        """Resume execution from a persisted checkpoint: relaunch app, restore trace, re-ground."""
        cp = self.load_checkpoint(session_id)
        if not cp:
            return None
        self.session_id = session_id
        recent = cp.get("recent", [])
        if recent:
            self.trace = [
                StepTrace(goal=t["goal"], element=t["element"], verb=t["verb"],
                          verdict=t["verdict"], method=t["method"],
                          evidence=t["evidence"], tiers=t.get("tiers", []))
                for t in recent
            ]
        if app_hint and not self.grounding.find_window(app_hint):
            try:
                from core_organs.organ_40_app_launcher import resolve_and_launch
                resolve_and_launch(app_hint)
                time.sleep(1.5)
            except Exception:
                pass
            self._wait_for_ready(app_hint)
        return cp

    def _hold_hidden(self, app_hint: str) -> Optional[int]:
        """Find the app's window and, when it is MINIMIZED, keep it parked off-screen (laid out, never on a monitor,
        focus untouched) until this run ends. A window of an app WE started that has just appeared on the user's
        screen (the splash -> main-frame handoff) is minimized first. A window the user is looking at, and any
        window of an app we did not start, is left exactly where it is."""
        hwnd = self.grounding.find_window(app_hint)
        if not hwnd:
            return None
        if hwnd in self._held:
            return hwnd
        from core_organs import background_window as bw
        ours = bw.is_ours(hwnd) or (app_hint or "").lower() in self._launched_apps
        if ours:
            bw.mark_ours(hwnd)
            if not hin.is_minimized(hwnd) and hin.is_alive(hwnd) and bw.user_can_see(hwnd):
                ctypes.windll.user32.ShowWindow(hwnd, 7)            # SW_SHOWMINNOACTIVE: put it away, take no focus
                time.sleep(0.12)
        if hin.is_minimized(hwnd):
            sess = bw.BackgroundSession(hwnd)
            sess.__enter__()
            self._last_window_mode = sess.mode or "failed"
            if sess.mode == "parked":
                self._held[hwnd] = sess
                # A window parked ENTIRELY off every monitor is not laid out by UWP/WinUI apps, and a flyout
                # inside it is never realized - so a background run could not reach any command that lives in a
                # menu (measured: Paint 'Edit' -> Paste exists 0.8 s after the sliver, and never while fully
                # parked). An ACTUATION run needs this for its whole life, not just for one layout read.
                sess.lay_out()
                logger.info("[autonomy] %s hwnd=%s held parked off-screen", app_hint, hwnd)
            else:
                sess.__exit__(None, None, None)
        return hwnd

    def _release_held(self) -> None:
        for hwnd, sess in list(self._held.items()):
            try:
                sess.__exit__(None, None, None)
            except Exception:
                pass
        self._held.clear()
        # "apps we started" is PER-RUN state: the loop is a process-wide singleton, and a window the USER opens later
        # under the same app name must never be treated as ours (minimized / parked). Windows we created stay known
        # precisely, by handle, through background_window.is_ours().
        self._launched_apps.clear()

    def _tame_family(self, app_hint: str) -> None:
        """Cheap sweep during an extended startup wait: any visible window of an app WE started goes straight back
        to minimized (a splash chain keeps creating new top-levels)."""
        if (app_hint or "").lower() not in self._launched_apps:
            return
        try:
            from core_organs import background_window as bw
            for h in self.grounding.find_window(app_hint, all_candidates=True):
                if hin.is_alive(h) and not hin.is_minimized(h) and h not in self._held and bw.user_can_see(h):
                    ctypes.windll.user32.ShowWindow(h, 7)
                    bw.mark_ours(h)
        except Exception:
            pass

    def _wait_for_ready(self, app_hint: str, target_text: str = "",
                        max_tier: int = 2) -> Tuple[Optional[int], List[GroundedElement], Dict[str, Any]]:
        """Readiness poll: bring up the target and wait (bounded, growing waits) until it exposes a live control
        tree. Prevents 'still booting' from being misread as an empty/wrong state on heavy apps.

        The deadline is READY_TIMEOUT_S for an app that shows no sign of starting; while its window set changes or
        its processes keep working the deadline slides out by READY_GRACE_S, never beyond READY_HARD_CAP_S. A tiny
        window is not 'ready' until it has stayed the same for a poll (a splash vanishes; a real UI does not)."""
        t0 = time.time()
        deadline = t0 + READY_TIMEOUT_S
        hard = t0 + READY_HARD_CAP_S
        delay = READY_BACKOFF_S
        hwnd, elements, report = None, [], {}
        last_sig, last_cpu, stable, extended = None, 0.0, 0, 0.0
        woken = False
        while True:
            self._hold_hidden(app_hint)
            hwnd, elements, report = self.grounding.ground(
                app_hint, target_text=target_text, max_tier=max_tier)
            if hwnd and len(elements) >= READY_RICH_ELEMENTS:
                break                                  # a real UI is up: skip the (slower) startup-activity probe
            sig, cpu = self.grounding.family_activity(app_hint)
            progressing = (last_sig is not None and sig != last_sig) or (last_sig is not None and cpu - last_cpu > 0.15)
            if progressing and time.time() < hard:
                new_deadline = min(hard, time.time() + READY_GRACE_S)
                if new_deadline > deadline:
                    extended += new_deadline - deadline
                    deadline = new_deadline
            stable = 0 if (last_sig is not None and sig != last_sig) else stable + 1
            last_sig, last_cpu = sig, cpu
            if hwnd and elements and stable >= 1:
                # A XAML/WinUI host lays its content out lazily: a tree that is only title-bar chrome
                # plus a bare pane is NOT a ready UI, it is the pre-realization shell every UWP app shows
                # before its controls materialize (measured: Settings parked off-screen returned 4 chrome
                # elements, then 59 a few seconds later). Acting on that shell is how a click landed on an
                # empty pane; so keep waiting for real content until the hard cap.
                if hin.is_xaml_host(_root_of(hwnd)) and not self._xaml_has_content(elements) and time.time() < hard:
                    deadline = max(deadline, min(hard, time.time() + READY_GRACE_S))
                    if not woken and time.time() - t0 > READY_WAKE_S:
                        woken = self._wake_packaged(hwnd, app_hint)
                else:
                    break
            if time.time() >= deadline:
                break
            self.capsule_cb("working", f"Waiting for {app_hint} to be ready")
            end = time.time() + delay
            while time.time() < end:                 # sleep in slices so a new splash-chain window is put away fast
                time.sleep(0.1)
                self._tame_family(app_hint)
            delay = min(delay * 1.6, READY_BACKOFF_MAX_S)
        report = dict(report or {})
        report["ready_wait_s"] = round(time.time() - t0, 2)
        if extended:
            report["ready_deadline_extended_s"] = round(extended, 1)
        # An unready app ENDS the run at step zero, so the reason has to be in the log, not only in the returned
        # dict (a measured run died exactly this way: 42.8 s, zero steps, and the log said nothing about why).
        logger.info("[ready] %s: hwnd=%s elements=%d wait=%.1fs extended=%.1fs threshold=%d reason=%s tiers=%s",
                    app_hint or "?", hwnd or 0, len(elements or []), report["ready_wait_s"], extended,
                    READY_RICH_ELEMENTS, report.get("reason", ""), report.get("tiers_ran", ""))
        return hwnd, elements, report

    def _wake_packaged(self, hwnd: int, app_hint: str) -> bool:
        """A packaged (XAML) app started minimized never draws its interface: it stays on its splash with ~3 controls (measured Nov-02: Calculator
        3 controls after a 90 s wait in 4 of 6 runs, 41 controls in 1.5 s in the others; the same was measured for the recorder, local_recorder.py).
        OUR window only: it is shown once WITHOUT activation (no focus is taken), given a few seconds to lay out, then put away again so the
        run continues parked. Returns True once tried, so it happens at most once per wait."""
        try:
            from core_organs import background_window as bw
            root = _root_of(hwnd)
            if not (bw.is_ours(root) or (app_hint or "").lower() in self._launched_apps):
                return True
            sess = self._held.pop(root, None) or self._held.pop(hwnd, None)
            if sess is not None:
                with contextlib.suppress(Exception):
                    sess.__exit__(None, None, None)
            ctypes.windll.user32.ShowWindow(root, 4)                   # SW_SHOWNOACTIVATE
            import ctypes.wintypes
            r = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(root, ctypes.byref(r))
            vx, vy = ctypes.windll.user32.GetSystemMetrics(76), ctypes.windll.user32.GetSystemMetrics(77)          # the virtual screen (all monitors)
            vw, vh = ctypes.windll.user32.GetSystemMetrics(78), ctypes.windll.user32.GetSystemMetrics(79)
            if r.right <= vx or r.left >= vx + vw or r.bottom <= vy or r.top >= vy + vh or r.right - r.left < 200:
                # shown where it was parked = still on no monitor, and a XAML app does not draw there (live Nov-02: woken 4 times, 3 controls each time)
                ctypes.windll.user32.SetWindowPos(root, 0, vx + 40, vy + 40, max(400, r.right - r.left), max(500, r.bottom - r.top), 0x0004 | 0x0010)  # NOZORDER|NOACTIVATE
                logger.info("[ready] %s: the parked window was off every monitor (%d,%d,%d,%d): moved on screen to lay out", app_hint, r.left, r.top, r.right, r.bottom)
            end = time.time() + 6.0
            while time.time() < end:
                time.sleep(0.5)
                els = self.grounding._walk_uia(root) if HAS_UIA else []
                if self._xaml_has_content(els):
                    break
            logger.info("[ready] %s: woke the packaged window hwnd=%s (shown without focus to lay out its interface)", app_hint, root)
            ctypes.windll.user32.ShowWindow(root, 7)                   # SW_SHOWMINNOACTIVE: away again, the loop re-parks it
            time.sleep(0.2)
        except Exception as exc:
            logger.info("[ready] %s: wake failed: %s", app_hint, exc)
        return True

    @staticmethod
    def _xaml_has_content(elements) -> bool:
        """True once a XAML/WinUI host has exposed REAL content: any NAMED control that is not window
        chrome and not a pure container. The pre-realization shell offers only 'Minimize/Maximize/Close
        <app>' plus an unnamed pane, which this rejects - so readiness waits for the UI to materialize
        instead of pressing an empty pane. Generic (no app names); structural roles only."""
        for e in (elements or []):
            nm = (e.name or "").strip().lower()
            if not nm:
                continue
            if nm.startswith(("minimize ", "maximize ", "close ", "restore ", "show desktop")):
                continue
            if (e.role or "").lower() in ("pane", "window", "group", "titlebar", "custom", "separator", "image"):
                continue
            return True
        return False

    def run(self, goals: List[str], app_hint: str, max_steps_per_goal: int = 4,
            allow_destructive: bool = False,
            expect_map: Optional[Dict[int, Dict[str, Any]]] = None,
            max_tier: int = 2) -> Dict[str, Any]:
        """Execute ordered micro-goals. Each goal gets up to max_steps_per_goal
        closed-loop attempts; a PASS or declared-done advances to the next goal. A minimized target is held parked
        off-screen for the whole run and put back as it was when the run ends."""
        self._run_depth += 1
        try:
            return self._run_impl(goals, app_hint, max_steps_per_goal, allow_destructive, expect_map, max_tier)
        finally:
            self._run_depth -= 1
            if self._run_depth == 0:
                self._release_held()

    def _content_author_goal(self, goals: List[str], gi: int, want: str) -> int:
        """Index of the earlier goal that was supposed to PUT this content on screen (the one whose literal is
        `want`); the last earlier goal when none names it. Pure bookkeeping for the honest failure message -
        it never chooses an action, so no app or format knowledge lives here."""
        for k in range(gi):
            if literal_typed_text(goals[k]) == want:
                return k
        return max(0, gi - 1)

    def _run_impl(self, goals: List[str], app_hint: str, max_steps_per_goal: int,
                  allow_destructive: bool,
                  expect_map: Optional[Dict[int, Dict[str, Any]]], max_tier: int) -> Dict[str, Any]:
        expect_map = expect_map or {}
        # The loop object is a process-wide singleton: per-RUN state must not leak from the previous run
        # (stale 'already tried' history made the judge avoid exactly the steps that had worked).
        self._history = []
        self._goal_fails = {}
        self._shortcut_tried = set()
        self._opened_not_done = {}
        self._pending_clicks = {}
        self.escalation_shots = []
        self._relaunches = 0
        self.invalid_streak = 0
        self.awaiting_human = False
        self._task_paths = tuple(m.group(0) for g_ in goals
                                 for m in re.finditer(r"[A-Za-z]:[\\/][^\s'<>|?*]+", g_ or ""))
        self._allow_destructive = bool(allow_destructive)
        # W5 learned re-run: pull the distilled recipe for this task once. It is a soft hint
        # only - the postcondition verifier still judges every step, so a stale/wrong recall
        # can never fake a PASS; it just points the judge at the element that worked last time.
        self._recalled_recipe = self.recall_recipe(" / ".join(goals), app_hint) or ""
        if self._recalled_recipe:
            logger.info("[learn] recalled recipe for %s: %s", app_hint, self._recalled_recipe[:160])
        # Clear the deck: stale dialogs from earlier runs must not be mistaken for task UI.
        cleared = self._triage_popups(app_hint, mode="preflight")
        if cleared:
            logger.info("[autonomy] preflight cleared: %s", cleared)
        # Readiness backoff up front: never start acting on an app that is still
        # booting or was never brought up — surface to human instead of flailing.
        _rhwnd, _relts, _rrep = self._wait_for_ready(app_hint)
        if not _rhwnd or not _relts:
            self.awaiting_human = True
            self.capsule_cb("input_needed", f"{app_hint} not ready (no controls)")
            reason = (_rrep or {}).get("reason", "no-controls-within-ready-window")
            return {"completed": False, "blocked_at_goal": 0, "steps": 0,
                    "awaiting_human": True, "ready_reason": reason,
                    "trace": [t.as_dict() for t in self.trace]}
        # A compound instruction ('add 21 and 21') is broken into atomic, individually-verified presses NOW,
        # against the controls the readiness pass just laid out - before any word of it can be matched to a
        # stray button. Skipped when the caller passed a positional expect_map (its keys would shift); an
        # un-groundable goal is left exactly as it was. Generic - goal_planner reads the words, never an app.
        if not expect_map:
            _expanded, _plan_note = expand_compound_goals(goals, _relts)
            if _plan_note:
                goals = _expanded
                self._launch_note = (self._launch_note + "; " if self._launch_note else "") + "decomposed: " + _plan_note[:280]
                logger.info("[plan] %s", _plan_note[:280])
        results = []
        fresh_note = ""
        self._canvas_needed = self._canvas_expected(goals, app_hint)
        self._canvas_prep_left = 2 if self._canvas_needed else 0
        if self._canvas_needed:
            try:
                fresh_note = self._ensure_blank_document(app_hint)
            except Exception as exc:
                fresh_note = f"blank-document check failed ({type(exc).__name__})"
            if fresh_note:
                self.trace.append(StepTrace("(prepare) blank document", "-", "check", "PASS", "hygiene", fresh_note, []))
        for gi, goal in enumerate(goals):
            advanced = False
            content_notes = 0                        # times this goal's file exists but its CONTENT is missing
            self.grounding.reset_vision_budget()
            asserted = assertion_text(goal)
            goal_expect = expect_map.get(gi) or (derive_expectation(goal) if asserted is None else None)
            if goal_expect and ("file_created" in goal_expect or "file_saved" in goal_expect):
                # Stamp WHEN this goal started, so its proof is "the app wrote the file after this moment"
                # and not "a file of that name happens to be on the disk": a stale e1.xlsx from an earlier,
                # killed run made a task that had saved nothing report as a success (measured 2026-10-05).
                # A copy, so no wall-clock value is ever carried into distilled knowledge.
                goal_expect = dict(goal_expect)
                goal_expect.setdefault("file_fresh_since", time.time())
                # ...and the file must hold what this run was told to write, not merely be a file: 'type 42 in
                # cell A1' followed by 'save as <path>' was measured completing on an EMPTY sheet.
                if "file_text_contains" not in goal_expect:
                    _lit = next((t for t in (literal_typed_text(gg) for gg in goals[:gi + 1]) if t), "")
                    if _lit:
                        goal_expect["file_text_contains"] = _lit
            # Saving to a named file through a rich app (Office's backstage: File > Save As > type > name > Save) honestly
            # needs more than the few steps a menu click does; the WRITE is what ends the goal, not the budget.
            _terminal_file = bool(goal_expect and (("file_created" in goal_expect) or ("file_saved" in goal_expect)))
            steps_here = max_steps_per_goal + (6 if _terminal_file else 0)
            for _ in range(steps_here):
                if asserted is not None:
                    res = self._assert_step(goal, app_hint, asserted, max_tier)
                else:
                    res = self.step(goal, app_hint, expect=goal_expect,
                                    allow_destructive=allow_destructive, max_tier=max_tier)
                results.append(res)
                # A step PASSes the STEP; the goal is done only when its own terminal proof holds (the file
                # exists). Advancing on an intermediate PASS made 'save as' look complete after one menu click.
                if self.awaiting_human or (res["verdict"] == "PASS" and res.get("goal_done", True)):
                    advanced = True
                    break
                # The file is ON THE DISK but does not hold the text this run was told to write: the save flow is
                # proven working, so replaying it only burns steps on a goal that can no longer be met by saving.
                # Name the earlier authorship goal as the block and stop, so the run reports WHY with evidence.
                if (_terminal_file and res["verdict"] == "PASS" and not res.get("goal_done", True)
                        and goal_expect.get("file_text_contains")):
                    _p = str(goal_expect.get("file_created") or goal_expect.get("file_saved") or "")
                    _got, _why = file_holds_text(_p, str(goal_expect["file_text_contains"]))
                    if _p and _got is False:
                        content_notes += 1
                        if content_notes >= 2:
                            ai = self._content_author_goal(goals, gi, str(goal_expect["file_text_contains"]))
                            note = (f"the file was written and holds no '{goal_expect['file_text_contains']}': "
                                    f"the save flow is done, the unsatisfied goal is {ai + 1}/{len(goals)} "
                                    f"({goals[ai][:60]!r}) where that content should have been authored -> failing here "
                                    f"instead of re-saving ({_why})")
                            logger.info("[autonomy] %s", note)
                            self.trace.append(StepTrace(goal, "-", "diagnose", "WRONG_STATE", "verifier", note, []))
                            return {"completed": False, "blocked_at_goal": ai, "steps": len(results),
                                    "content_missing": str(goal_expect["file_text_contains"]),
                                    "trace": [t.as_dict() for t in self.trace]}
                # G2: the app's window is GONE mid-run (it crashed / was closed under us). Relaunch it ONCE, wait for it
                # to be groundable and carry on with the SAME goal (earlier goals stay done); a second loss is a failure
                # with evidence, never a loop of relaunches.
                if res["verdict"] == "WRONG_STATE" and "window-not-found" in str(res.get("evidence", "")):
                    if self._relaunches < MAX_RELAUNCHES:
                        self._relaunches += 1
                        try:
                            launched = _launch_if_missing(self, app_hint, self.capsule_cb)
                            if launched:
                                self._launched_apps.add((app_hint or "").lower())
                            self._wait_for_ready(app_hint)
                            note = f"app window vanished: relaunched once (launched={launched}); resuming goal {gi + 1}/{len(goals)}"
                            # A fresh instance opens where it opens (its start screen, a restored file), NOT on the
                            # canvas the earlier goals used. Whatever survived the loss is gone; the least the loop
                            # can do is put a writable surface back on screen instead of driving a save goal against
                            # a launcher and clicking its search box.
                            if self._canvas_expected(goals, app_hint):
                                try:
                                    note += "; canvas re-prepared: " + (self._ensure_blank_document(app_hint) or "unchanged")
                                except Exception as exc2:
                                    note += f"; canvas re-preparation failed ({type(exc2).__name__})"
                        except Exception as exc:
                            note = f"app window vanished: relaunch failed ({type(exc).__name__}: {exc})"
                        self.trace.append(StepTrace(goal, "-", "relaunch", "NO_CHANGE", "crash-recovery", note, []))
                        self._history.append("window vanished -> relaunched once")
                        continue
                    self.trace.append(StepTrace(goal, "-", "relaunch", "WRONG_STATE", "crash-recovery",
                                                f"the window vanished again after {MAX_RELAUNCHES} relaunch(es): failing with evidence", []))
                    return {"completed": False, "blocked_at_goal": gi, "steps": len(results), "crashed": True,
                            "relaunches": self._relaunches, "trace": [t.as_dict() for t in self.trace]}
            if self.awaiting_human:
                break
            if not advanced:
                return {"completed": False, "blocked_at_goal": gi, "steps": len(results),
                        "relaunches": self._relaunches, "trace": [t.as_dict() for t in self.trace]}
        return {"completed": not self.awaiting_human, "steps": len(results), "relaunches": self._relaunches,
                "trace": [t.as_dict() for t in self.trace],
                "awaiting_human": self.awaiting_human, "escalation_shots": list(self.escalation_shots)}

    # ---- checkpoint + resume ----
    def _checkpoint_path(self) -> str:
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        return os.path.join(CHECKPOINT_DIR, f"{self.session_id}.json")

    def _write_checkpoint(self, entry: StepTrace) -> None:
        try:                                    # every step's verdict AND its evidence reach the log (a bare 'WRONG_STATE' is undiagnosable)
            d = entry.as_dict()
            logger.info("[step] %s '%s' via %s -> %s | %s", d.get("verb"), str(d.get("element"))[:30], str(d.get("method"))[:60],
                        d.get("verdict"), str(d.get("evidence"))[:260])
        except Exception:
            pass
        try:
            payload = {"session_id": self.session_id, "steps": len(self.trace),
                       "last": entry.as_dict(),
                       "recent": [t.as_dict() for t in self.trace[-25:]]}
            with open(self._checkpoint_path(), "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
        except Exception as exc:
            logger.debug("[checkpoint] write failed: %s", exc)

    @staticmethod
    def load_checkpoint(session_id: str) -> Optional[Dict[str, Any]]:
        p = os.path.join(CHECKPOINT_DIR, f"{session_id}.json")
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    # ---- W5: skill distillation to organ_04 knowledge ----------------------
    def distill_recipe(self, task_goal: str, app_name: str) -> Tuple[bool, str]:
        passes = [t for t in self.trace if t.verdict == "PASS"]
        if len(passes) < 2:
            return False, "not enough verified steps to distill"
        lines = []
        for t in passes:
            lines.append(f"{t.verb.upper()} on '{t.element}' ({t.method}) to achieve: {t.goal}")
        recipe = (f"SKILL[{app_name}] goal='{task_goal}': " + " THEN ".join(lines)
                  + f" | tiers={sorted({tt for t in passes for tt in t.tiers})}")
        try:
            from core_organs.organ_04_knowledge import KnowledgeOrgan, QueryDispatcher
            root = os.environ.get("HOJAIGA_KNOWLEDGE_ROOT",
                                  os.path.join(r"D:\new_automation", "organ_04_knowledge"))
            organ = KnowledgeOrgan(root_dir=root)

            async def _flow():
                await organ.start()
                res = await organ.dispatcher.dispatch(
                    QueryDispatcher.OP_INGEST_KNOWLEDGE,
                    {"doc_type": "skill_recipe", "content_text": recipe})
                await organ.stop()
                return res
            res = asyncio.run(_flow())
            return bool(res.get("ingested_chunks", 0) > 0), f"recipe ingested to organ_04 ({len(lines)} verified steps)"
        except Exception as exc:
            logger.debug("[learn] distill failed: %s", exc)
            return False, f"distill unavailable: {exc}"

    @staticmethod
    def recall_recipe(goal: str, app_name: str) -> str:
        """Retrieve learned recipe text for a similar goal, from THIS app only (empty when none)."""
        try:
            from core_organs.organ_04_knowledge import KnowledgeOrgan, QueryDispatcher
            root = os.environ.get("HOJAIGA_KNOWLEDGE_ROOT",
                                  os.path.join(r"D:\new_automation", "organ_04_knowledge"))
            organ = KnowledgeOrgan(root_dir=root)

            async def _flow():
                await organ.start()
                res = await organ.dispatcher.dispatch(
                    QueryDispatcher.OP_SEARCH_KNOWLEDGE,
                    {"text": f"SKILL {app_name} {goal}", "limit": 3})
                await organ.stop()
                matches = res.get("matches", []) if isinstance(res, dict) else []
                want = (app_name or "").strip().lower()
                for h in matches:
                    content = (h.get("snippet") or h.get("content") or h.get("chunk") or h.get("text") or "") if isinstance(h, dict) else str(h)
                    if not content.startswith("SKILL[") or "]" not in content:
                        continue
                    # The recipe carries the app it was distilled IN. Goals across apps read as similar text ('save the
                    # workbook as C:\..\hj_xls2.xlsx' and 'save the file as C:\..\hj_lc2.txt'): matching on the goal alone
                    # replayed an Excel backstage walk inside Calculator (measured 2026-10-06), and its steps name
                    # controls that do not exist there. A hint about another app is not a hint.
                    got = content[content.index("[") + 1:content.index("]")].strip().lower()
                    if want and got and got != want:
                        logger.info("[learn] recalled recipe for '%s' rejected: it belongs to '%s'", want, got)
                        continue
                    return content
                return ""
            return asyncio.run(_flow())
        except Exception as exc:
            logger.debug("[learn] recall unavailable: %s", exc)
            return ""

    _NEW_DOC_RE = re.compile(r"^(?:add )?new (?:tab|document|file)$|^new tab$", re.I)
    # What "make me a document I can write into" is CALLED, as UI vocabulary collected from the families seen on
    # this host - never keyed on an app's name. Measured: an office suite's start screen offers a list item whose
    # own label begins 'Blank'; a text editor offers 'New tab'; a browser offers 'New window'. The rule below
    # presses whichever of these the running app actually shows, and then checks that a surface appeared.
    _NEW_DOC_WORDS = ("blank", "new file", "new document", "new tab", "new window", "new image",
                      "create new", "create document", "empty", "untitled")
    _NEW_DOC_ROLES = ("listitem", "button", "splitbutton", "hyperlink", "menuitem", "tabitem")

    def _writable_surface(self, els: List[GroundedElement]) -> Tuple[int, str]:
        """How many things on this screen could HOLD typed content, and what the loop makes of that.

        A grid cell (addressable by its own reference) or an editable surface that is not a tool strip. Measured
        with the app still on its start screen: neither existed, the payload went into 'Search for a file', the
        UI changed so every step 'passed', and the saved document was empty.

        An edit box only counts when it occupies a real part of the screen. Measured on the same start screen: it
        lists an unnamed one-line edit of 98x23 px (a navigate-by-name strip), and counting it as a canvas made the
        loop decide a document was already open - so it never pressed the app's own create-a-document control and
        the payload had nowhere to go. The test is geometry in the screen's own units, never an app's name."""
        cells = [e for e in els if e.role == "dataitem"
                 and re.fullmatch(r"[A-Za-z]{1,3}[1-9]\d{0,5}", (e.name or "").strip())]
        if cells:
            return len(cells), "grid"
        docs = [e for e in els if e.role in ("document", "datagrid", "table")]
        if docs:
            return len(docs), "document surface"
        boxes = [e for e in els if e.role in ConstrainedJudge._TEXT_ROLES
                 and not any(u in (e.name or "").lower() for u in UTILITY_BOX_NAMES)]
        if boxes:
            left = min(e.bbox[0] for e in els)
            top = min(e.bbox[1] for e in els)
            span_w = max(e.bbox[2] for e in els) - left
            span_h = max(e.bbox[3] for e in els) - top
            span = max(1, span_w * span_h)
            boxes = [e for e in boxes
                     if abs(e.bbox[2] - e.bbox[0]) * abs(e.bbox[3] - e.bbox[1]) >= _CANVAS_MIN_FRACTION * span]
        return (len(boxes), "edit box") if boxes else (0, "nothing")

    def _canvas_expected(self, goals: List[str], app_hint: str) -> bool:
        """True when this task asks for content to be typed AND the instance is one WE started, so the loop owns the
        document on screen. Never prepared on an app the user left open, and never for a task that types nothing."""
        return ((app_hint or "").lower() in self._launched_apps
                and any(re.match(r"^\s*(?:type|write|enter|input)\b", g or "", re.I) for g in goals))

    def _ensure_blank_document(self, app_hint: str) -> str:
        """Prepare a typing task's canvas, non-destructively, in the two ways apps block it.

        (a) The instance WE launched reopened last session's unsaved document (Notepad restores tabs): a
            'type X then save as Y' task would save the old text with X. Press the app's own new-document
            control when it has one.
        (b) The instance opened on a START SCREEN with no document at all, so there is nothing to type into.
            Press whatever control the app itself labels as creating one (see _NEW_DOC_WORDS) and PROVE a
            writable surface appeared - the run then says so instead of typing into a search strip.
        Returns a note ('' when there was nothing to do)."""
        self._hold_hidden(app_hint)          # the window is held parked for the whole run, like every other step
        hwnd, els, _rep = self.grounding.ground(app_hint, max_tier=2)
        if not hwnd or not els:
            return ""
        n_surface, kind = self._writable_surface(els)
        if n_surface == 0:                   # (b): no canvas on screen at all
            maker = next((e for e in els if e.role in self._NEW_DOC_ROLES
                          and any(w in (e.name or "").lower() for w in self._NEW_DOC_WORDS)), None)
            if maker is None:
                return (f"the screen offers nothing that can hold text ({len(els)} controls, no "
                        f"{ConstrainedJudge._TEXT_ROLES}) and names no control that would create one: a typed payload "
                        "here would land in a tool strip, so it is not typed")
            ok, how = _act_on_element(maker, "click", "")
            time.sleep(1.2)
            self._settle(hwnd)
            _h2, els2, _r2 = self.grounding.ground(app_hint, max_tier=2)
            n2, kind2 = self._writable_surface(els2 or [])
            return (f"opened a document first: the start screen held no writable surface, pressed "
                    f"'{maker.name}' ({maker.role}) via {how} -> "
                    + (f"{n2} addressable {kind2} now on screen" if n2 else
                       "still no writable surface: the press did not create a document"))
        before = self._control_text(els)
        if not before.strip():
            return ""
        new = next((e for e in els if e.role in ("button", "splitbutton") and self._NEW_DOC_RE.match((e.name or "").strip())), None)
        if new is None:
            return (f"the launched instance restored a document with {len(before)} chars and offers no 'new tab' control: "
                    "typed text will be APPENDED to it")
        ok, how = _act_on_element(new, "click", "")
        time.sleep(0.8)
        self._settle(hwnd)
        hwnd2, els2, _r2 = self.grounding.ground(app_hint, max_tier=2)
        after = self._control_text(els2 or [])
        return (f"restored document ({len(before)} chars) kept in its tab; opened a new blank one via '{new.name}' "
                f"({how}); the editor now holds {len(after)} chars")

    def _assert_step(self, goal: str, app_hint: str, text: str, max_tier: int) -> Dict[str, Any]:
        """A pure assertion goal: PASS only when some control's name (labels and read-outs included) or the editor's text
        really holds ``text``; NO_CHANGE otherwise. Nothing is clicked."""
        self._hold_hidden(app_hint)
        self._triage_popups(app_hint)
        hwnd, elements, ladder = self.grounding.ground(app_hint, max_tier=min(max_tier, 3))
        if not elements:
            entry = StepTrace(goal, "-", "expect", "WRONG_STATE", "assert",
                              f"no elements to assert against; ladder={ladder}", ladder["tiers_ran"])
            self.trace.append(entry)
            return self._step_result(entry, elements=[])
        want = {"name_visible": text, "text_contains": text}
        snap = self._snap(hwnd, elements, want)
        ok_name, ev_name = self.verifier.check_expect({"name_visible": text}, snap, snap, elements)
        ok_text, ev_text = self.verifier.check_expect({"text_contains": text}, snap, snap, elements)
        verdict = "PASS" if (ok_name or ok_text) else "NO_CHANGE"
        evidence = ev_name if ok_name else (ev_text if ok_text else f"{ev_name}; {ev_text}")
        entry = StepTrace(goal, "-", "expect", verdict, "assert", evidence, ladder["tiers_ran"])
        self.trace.append(entry)
        self._write_checkpoint(entry)
        self.capsule_cb("working", f"[{app_hint}] expect '{text[:30]}' -> {verdict}")
        return self._step_result(entry, elements=elements)

    def _step_result(self, entry: StepTrace, elements: List[GroundedElement] = None,
                     goal_done: Optional[bool] = None) -> Dict[str, Any]:
        out = {"verdict": entry.verdict, "element": entry.element, "verb": entry.verb,
               "method": entry.method, "evidence": entry.evidence,
               "tiers_ran": entry.tiers, "awaiting_human": self.awaiting_human,
               "seen_elements": len(elements or []), "session": self.session_id}
        if goal_done is not None:
            out["goal_done"] = goal_done      # the GOAL's own truth, when it has a terminal condition
        return out


_WEBAPP_WATCHER = None
_LOOP_SINGLETON: Optional[DesktopAutonomyLoop] = None


# leading bytes of common binary formats: a file named x.<ext> must really start with one of these
FILE_MAGIC: Dict[str, Tuple[bytes, ...]] = {
    "png": (b"\x89PNG\r\n\x1a\n",), "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",), "bmp": (b"BM",),
    "gif": (b"GIF87a", b"GIF89a"), "pdf": (b"%PDF",), "zip": (b"PK\x03\x04",), "docx": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",), "pptx": (b"PK\x03\x04",), "tif": (b"II*\x00", b"MM\x00*"), "tiff": (b"II*\x00", b"MM\x00*"),
}


def file_has_format(path: str, ext: str) -> Tuple[bool, str]:
    """(ok, note): does the file at ``path`` start with the signature of format ``ext``? Unknown formats pass (nothing to check)."""
    sigs = FILE_MAGIC.get((ext or "").lower())
    if not sigs:
        return True, f"no signature known for .{ext}"
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError as exc:
        return False, f"unreadable ({type(exc).__name__})"
    ok = any(head.startswith(sg) for sg in sigs)
    return ok, (f"is a real .{ext}" if ok else f"NOT a .{ext} (starts {head[:6]!r})")


# Extensions whose content is readable as text, and containers whose text lives inside compressed members.
# Data, not a per-app rule: the format decides the reader, and an unknown format is reported as "not
# checkable" rather than being handed a free pass.
PLAIN_TEXT_EXTS = ("txt", "md", "log", "csv", "tsv", "json", "xml", "html", "htm", "ini", "cfg", "conf",
                   "py", "js", "css", "yaml", "yml", "srt", "vtt", "rtf", "bat", "ps1")
CONTAINER_TEXT_EXTS = ("xlsx", "xlsm", "xlsb", "docx", "pptx", "odt", "ods", "odp", "epub", "zip")
# the OOXML/OpenDocument tags that hold a VALUE or a TEXT run - a cell's number, a paragraph's words
_TEXT_LEAF_RE = re.compile(r"<(?:[A-Za-z_]+:)?(?:v|t)(?:\s[^>]*)?>([^<]+)<", re.S)


def file_holds_text(path: str, want: str) -> Tuple[Optional[bool], str]:
    """(ok, note) - or (None, why the check could not run): does the WRITTEN file contain ``want``?

    'The file exists and has bytes' is not the whole truth: measured 2026-10-05, a workbook was saved to the
    exact path it was given and its only sheet was empty, and the goal still read DONE. The text the run was
    told to put in is now looked for INSIDE the file - plain bytes for a text format, the value/text leaves of
    each compressed member for the document containers."""
    import zipfile
    want = (want or "").strip()
    if not want:
        return None, "nothing to look for"
    ext = (path.rsplit(".", 1)[-1].lower() if "." in os.path.basename(path) else "")
    leaves: List[str] = []
    try:
        if ext in CONTAINER_TEXT_EXTS or zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                for info in z.infolist()[:400]:
                    if info.file_size > 4_000_000:
                        continue
                    try:
                        blob = z.read(info).decode("utf-8", "ignore")
                    except Exception:  # noqa: BLE001
                        continue
                    leaves += [t.strip() for t in _TEXT_LEAF_RE.findall(blob) if t.strip()]
            if not leaves:
                # A document format with NO text or value anywhere is not "unreadable", it is EMPTY - which is
                # exactly the case that must not pass (the measured workbook had bytes and an empty sheet).
                if ext in CONTAINER_TEXT_EXTS:
                    return False, f"the .{ext} holds no text or value at all (an empty document)"
                return None, f"no text leaves readable in a .{ext}"
        elif ext in PLAIN_TEXT_EXTS:
            with open(path, "rb") as fh:
                leaves = [fh.read(4_000_000).decode("utf-8", "ignore")]
        else:
            return None, f".{ext or '?'} has no text form to read"
    except (OSError, ValueError) as exc:
        return None, f"unreadable ({type(exc).__name__})"
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    target = norm(want)
    hit = any(target == norm(l) or (len(target) > 2 and target in norm(l)) for l in leaves)
    if not hit and len(target) > 2:
        # a phrase can be split across runs (a .docx 'text run' is a formatting span, not a sentence), so the
        # pieces are also searched as one stream
        hit = target in " ".join(norm(l) for l in leaves)
    return hit, (f"'{want[:24]}' {'IS' if hit else 'is NOT'} inside "
                 f"({len(leaves)} text piece(s), {sum(len(l) for l in leaves)} chars)")


_GOAL_PATH_RE = re.compile(r"[A-Za-z]:[\\/](?:[^\\/:*?\"<>|\r\n;]+[\\/])*[^\\/:*?\"<>|\r\n;]*?\.[A-Za-z0-9]{1,6}(?![A-Za-z0-9])")
_ASSERT_GOAL_RE = re.compile(r"^\s*(?:expect|verify|check|assert|ensure|confirm)\b[:\s,]*(?:that\s+)?(.+?)\s*$", re.I)


_TYPE_LITERAL_RE = re.compile(r"""^\s*(?:type|enter|input|write)\s+(?:in\s+)?(?:the\s+)?(?:text\s+|number\s+|value\s+)?(.+?)\s*$""", re.I)
_NOT_LITERAL = frozenset({"a", "an", "some", "something", "about", "poem", "haiku", "sentence", "paragraph", "story", "message",
                          "letter", "note", "essay", "email", "text", "anything", "whatever", "random", "short", "long", "just",
                          "into", "in", "on", "to", "of", "for",
                          # pronouns are not the user's words: 'type it in the box' asks for no literal, and
                          # letting 'it' stand as one would grade any control that happens to contain those
                          # two letters as satisfied
                          "it", "this", "that", "these", "those", "them", "something", "everything", "nothing"})
# 'type 42 IN CELL A1': the words after the literal say WHERE, not WHAT. Cutting the place off is what gives
# the goal a postcondition at all -- measured, a spreadsheet run completed 'type 42 in cell A1' by clicking a
# ribbon tab, because the whole phrase (the 'in' inside it) was read as 'needs composing' and graded as 'the
# UI moved'. Location tails are ordinary English prepositions, so this is a shape rule, not a word list per app.
_LOCATION_TAIL_RE = re.compile(r"\s+(?:in|into|onto|on|at|inside|within|to)\s+(?:the\s+|a\s+|an\s+|this\s+|that\s+|your\s+|my\s+)?"
                               r"[\w.'-]+(?:\s+[\w.'-]+){0,3}\s*$", re.I)


def literal_typed_text(goal: str) -> Optional[str]:
    """The exact text a 'type X' goal asks for, when X is a LITERAL (quoted, or a few plain words / a number such as 'type
    42' or 'type hello world'); None for 'type a haiku' style goals whose text must be composed."""
    m = _TYPE_LITERAL_RE.match(goal or "")
    if not m:
        return None
    body = m.group(1).strip()
    q = re.fullmatch(r"[\"'\u201c](.+)[\"'\u201d]", body)
    if q:
        return q.group(1)
    stripped = _LOCATION_TAIL_RE.sub("", body).strip()
    if stripped and stripped != body:
        body = stripped                      # the place it named stays out of the postcondition: '42', not '42 in cell A1'
    words = re.findall(r"\S+", body)
    if not words or len(words) > 5 or re.search(r"[A-Za-z]:[\\/]", body):
        return None
    if re.match(r"(?:and|then)\b", body, re.I) or re.search(r"\b(?:and|then)\s+(?:save|open|click|press|close|type|print|export)\b",
                                                          body, re.I):
        return None                      # a compound instruction ('write text and save as file'), not a literal
    if any(w.lower().strip(".,;:!?") in _NOT_LITERAL for w in words):
        return None
    return body.rstrip(".")


def derive_expectation(goal: str) -> Dict[str, Any]:
    """A machine-checkable postcondition read from the goal's OWN WORDS, for a caller that gave none.

    A goal 'save the file as <absolute path>' is only done when that file exists; clicking the File menu changes the UI
    and used to be accepted as 'saved' by the default (weak) postcondition - a task bench measured two tasks claiming
    DONE with no file on disk. Only a goal that names an absolute path WITH a file extension and a saving verb gets one;
    everything else keeps the default (and is reported weak by its callers)."""
    g = goal or ""
    lit = literal_typed_text(g)
    if lit:
        return {"text_contains": lit}          # a typed literal must really be in the control, whatever action typed it
    m = _GOAL_PATH_RE.search(g)
    if not m or not re.search(r"\b(?:save|saved|export|download|write)\b", g, re.I):
        return {}
    path = m.group(0).rstrip(".,;:!)\"'")
    if not re.search(r"\.[A-Za-z0-9]{1,6}$", path):
        return {}
    exp: Dict[str, Any] = {"file_created": path}
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in FILE_MAGIC:
        exp["file_format"] = ext          # existence is not enough: "Save as project" wrote a non-PNG named .png
    return exp


def assertion_text(goal: str) -> Optional[str]:
    """The text a pure ASSERTION goal ("expect Display is 100") says must be on screen, else None. An assertion needs no
    action: the judge used to pick some control to click for it and the click could never satisfy it."""
    m = _ASSERT_GOAL_RE.match(goal or "")
    if not m:
        return None
    t = re.sub(r"\s+(?:(?:is|are|to be)\s+)?(?:shown|visible|displayed|present|showing|on the screen|on screen)\s*$", "",
               m.group(1).strip(), flags=re.I)
    t = t.strip().strip("'\"").strip()
    return t or None


def split_goals(goals: str) -> List[str]:
    """Newline / semicolon / lowercase-comma separated micro-goals -> ordered list."""
    return [g.strip() for g in re.split(r"[\n;]+|(?<=[a-z]),\s", goals or "") if g and g.strip()]


def expand_compound_goals(goal_list: List[str], elements: List["GroundedElement"]) -> Tuple[List[str], str]:
    """Split any COMPOUND instruction ('add 21 and 21', 'click File then click Save') into atomic,
    individually-verifiable sub-goals grounded in the controls THIS app actually shows on screen, so the
    one-action-per-step loop can drive it (a multi-action sentence otherwise has no single valid pick and the
    judge burns its three strikes to human-in-the-loop - or, worse, a word like 'add' matches a stray 'Memory
    add' button and a weak postcondition calls it done). Generic: goal_planner reads the instruction's own
    words and matches the result to real control labels; a goal that cannot be fully grounded is returned
    exactly as it was, so decomposition can only ever match the old behaviour, never regress or fake a step.
    Called with the elements the loop has ALREADY laid out (post-readiness), so it never races the launch.
    Returns (possibly-expanded goals, a note for the trace)."""
    try:
        from core_organs import goal_planner
    except Exception:  # noqa: BLE001
        return goal_list, ""
    if not any(goal_planner.is_compound(g) for g in goal_list):
        return goal_list, ""
    _clicky = ConstrainedJudge._CLICK_ROLES
    labels = [e.name for e in (elements or []) if e.role in _clicky and (e.name or "").strip()]
    if not labels:
        return goal_list, ""
    out, notes = [], []
    for g in goal_list:
        exp = goal_planner.expand(g, labels)
        if len(exp) > 1:
            notes.append(f"'{g[:40]}' -> " + " THEN ".join(exp))
        out.extend(exp)
    return (out or goal_list), "; ".join(notes)


def operate_app(app_name: str, goals, allow_destructive: bool = False,
                capsule_cb=None, cursor_cb=None, max_steps_per_goal: int = 5,
                expect_map: Optional[Dict[int, Dict[str, Any]]] = None, isolated: bool = False) -> Dict[str, Any]:
    """The whole 'leave the bot working' flow in one callable (the CrewAI
    operate_desktop_tool delegates here, and the E2E suite calls it directly):

      self-sufficient launch -> closed-loop run -> recipe distillation on success.

    Returns the loop result dict plus: goals, launched, recipe, elapsed_s.
    """
    t0 = time.perf_counter()
    goal_list = list(goals) if isinstance(goals, (list, tuple)) else split_goals(goals)
    if not goal_list:
        return {"completed": False, "steps": 0, "trace": [], "goals": [],
                "error": "no goals provided"}
    # isolated=True: this call gets its OWN loop (own trace / history / goal state / cursor callback). A child cursor of a parallel run needs
    # that: the shared singleton carries per-call state, so two concurrent calls on it would read each other's trace.
    loop = DesktopAutonomyLoop(capsule_cb=capsule_cb, cursor_cb=cursor_cb) if isolated else get_loop(capsule_cb=capsule_cb, cursor_cb=cursor_cb)
    loop.trace = []  # one trace per operate_app call (the loop is a shared singleton)
    loop.awaiting_human = False
    loop._launch_note = ""
    launched = _launch_if_missing(loop, app_name, capsule_cb)
    if launched:
        loop._launched_apps.add((app_name or "").lower())
        try:        # an Office-style app opens on a START / backstage screen with no document: take its own 'Blank ...' tile (our instance only)
            from core_organs import universal_scan as _us
            _h0 = loop.grounding.find_window(app_name) or 0
            if _h0:
                from core_organs import background_window as _bwx
                with _bwx.BackgroundSession(_h0):          # a minimized Office window exposes no tiles: the read needs it parked off-screen
                    time.sleep(0.8)
                    _ss = _us.leave_start_screen(_h0, timeout_s=8.0)
                if _ss and _ss.get("start_screen") and _ss.get("tile"):
                    loop._launch_note = (loop._launch_note + "; " if loop._launch_note else "") + f"start screen left via '{_ss.get('tile')}'"
        except Exception as _exc:  # noqa: BLE001
            logger.debug("[operate] start-screen step skipped: %s", _exc)
    # No fixed sleep after the launch: run() starts with _wait_for_ready (bounded, growing waits, polling the live
    # control tree), which is what a slow starter (Steam's splash chain, Office, packaged apps) actually needs.
    # A minimized window is held parked off-screen by the loop for the whole run (laid out, never on a monitor,
    # focus untouched) and put back exactly as it was; a window the user can see is left exactly where it is.
    loop._last_window_mode = "not-needed"
    # Jarvis honest substrate: PREFETCH what this app already remembers about this exact goal. A past plan is
    # surfaced as a soft hint (the judge/verifier still decide every step); repeated past failures shift the
    # tone to cautious. It never touches a verdict - it only says, truthfully, "I have done/failed this here".
    _task_key = " / ".join(goal_list)
    _outcome_hint = ""
    try:
        from core_organs import outcome_ledger as _ledger
        _pf = _ledger.prefetch(app_name, _task_key)
        if _pf.get("seen"):
            if _pf.get("hint"):
                _outcome_hint = _pf["hint"]
            if _pf.get("caution"):
                loop._launch_note = (loop._launch_note + "; " if loop._launch_note else "") + f"[memory] {_pf['caution']}"
                try:
                    capsule_cb("thinking", f"[{app_name}] {_pf['caution']}")
                except Exception:  # noqa: BLE001
                    pass
            logger.info("[memory] %s / '%s': %s pass / %s fail (tone=%s)", app_name, _task_key[:40],
                        _pf.get("successes"), _pf.get("failures"), _pf.get("tone"))
    except Exception as _pf_exc:  # noqa: BLE001
        logger.debug("[memory] prefetch skipped: %s", _pf_exc)
    result = loop.run(goal_list, app_name, max_steps_per_goal=max_steps_per_goal,
                      allow_destructive=allow_destructive, expect_map=expect_map)
    result["window_mode"] = loop._last_window_mode
    result["memory_hint"] = _outcome_hint
    try:
        if result.get("completed"):
            ok, note = loop.distill_recipe(" / ".join(goal_list), app_name)
            result["recipe"] = note
            result["recipe_ingested"] = bool(ok)
    except Exception:
        pass
    hwnd = loop.grounding.find_window(app_name) or 0
    if launched and hwnd:
        _mark_ours(hwnd)
    result.update(goals=goal_list, launched=launched, hwnd=hwnd, launch_note=getattr(loop, "_launch_note", ""),
                  window_title=loop.grounding.window_title(hwnd) if hwnd else "",
                  elapsed_s=round(time.perf_counter() - t0, 2))
    # RECORD the whole-task outcome (success AND failure) so the next run's prefetch is honest about it.
    # Placed AFTER result.update: launch_note / elapsed_s only carry their final values there.
    try:
        from core_organs import outcome_ledger as _ledger2
        _ok = bool(result.get("completed"))
        _blk = ""
        if not _ok:
            _bi = result.get("blocked_at_goal")
            _tail = (result.get("trace") or [])
            _why = (_tail[-1].get("evidence") if isinstance(_tail[-1], dict) else getattr(_tail[-1], "evidence", "")) if _tail else ""
            _blk = f"goal #{(_bi if _bi is not None else '?')}: {(_why or 'incomplete')[:120]}"
        _ledger2.record(app_name, _task_key, ok=_ok,
                        note=(result.get("launch_note") or "") if _ok else _blk,
                        steps=int(result.get("steps") or 0),
                        elapsed_s=float(result.get("elapsed_s") or 0))
    except Exception as _rec_exc:  # noqa: BLE001
        logger.debug("[memory] record skipped: %s", _rec_exc)
    return result


def _mark_ours(hwnd: int) -> None:
    try:
        from core_organs import background_window as bw
        bw.mark_ours(hwnd)
    except Exception:
        pass


def _launch_if_missing(loop: "DesktopAutonomyLoop", app_name: str, capsule_cb=None) -> bool:
    """Start the app only when no window for it exists (single instance, never a second copy).

    Launched MINIMIZED and unfocused (universal_scan.launch_hidden: every new window is minimized the instant it
    appears) so a task never pops a window onto the user's screen. Only an app the Start menu does not know falls
    back to the organ_40 resolver (aliases / catalog / crawl)."""
    try:
        if loop.grounding.find_window(app_name):
            return False
        if capsule_cb:
            capsule_cb("working", f"Launching {app_name}")
        try:
            from core_organs import universal_scan as us
            # B2: verify the launch TARGET exists before trying (and before any retry): a missing exe is reported as such,
            # not retried through a search or an alias resolver that would launch something else
            tgt = us.launch_target_status(app_name)
            loop._launch_note = (f"target {tgt['kind']} '{str(tgt['app_id'])[:60]}': exists={tgt['exists']}" if tgt["found"]
                                 else "not in the Start menu catalog")
            if tgt["found"] and tgt["exists"] is False:
                loop._launch_note += " - the executable is MISSING; not launching (no retry could succeed)"
                logger.warning("[operate_app] %s", loop._launch_note)
                return False
            info = us.launch_hidden(app_name, timeout_s=30.0)
            if info.get("hwnd"):
                return True
            if not any("not in the Start menu" in n for n in info.get("notes", [])):
                return True          # it was started but showed no window yet: poll for it, never start a second copy
        except Exception as exc:
            logger.debug("[operate_app] hidden launch unavailable: %s", exc)
        # B2: the fuzzy resolver maps a nonsense name onto a REAL app (it once launched Excel for an invented name). Only a
        # resolution that actually names what was asked may launch; otherwise report it and stop - no retry, no guess.
        ok_res, why = _fallback_resolution_ok(app_name)
        if not ok_res:
            loop._launch_note = (getattr(loop, "_launch_note", "") + f" | no installed app resolves to '{app_name}': {why}; nothing launched").strip(" |")
            logger.warning("[operate_app] %s", loop._launch_note)
            return False
        from core_organs.organ_40_app_launcher import resolve_and_launch
        resolve_and_launch(app_name)
        return True
    except Exception as exc:
        logger.debug("[operate_app] auto-launch note: %s", exc)
        return False


def _fallback_resolution_ok(app_name: str) -> Tuple[bool, str]:
    """True when SOME installed program faithfully answers to `app_name`: a program/package/App-Paths resolution
    (static_knowledge.exe_for) or the organ_40 catalog's pick sharing a distinctive word with the request."""
    try:
        from core_organs import static_knowledge as sk
        if sk.exe_for(app_name):
            return True, "resolved to an installed program"
    except Exception:
        pass
    try:
        from core_organs.organ_40_app_launcher import AppCatalog, VerbAliasEngine, plan_task_app
        catalog = AppCatalog()
        catalog.ensure_scanned()
        plan = plan_task_app(app_name, catalog=catalog, engine=VerbAliasEngine(catalog, None))
        target = (plan.get("target_app") or "") if plan.get("action") == "launch_app" else ""
        want = {w for w in re.findall(r"[a-z0-9]+", (app_name or "").lower()) if len(w) > 2}
        got = {w for w in re.findall(r"[a-z0-9]+", target.lower()) if len(w) > 2}
        if want & got:
            return True, f"catalog resolved to '{target}'"
        return False, f"the catalog's pick '{target or 'nothing'}' shares no word with the request"
    except Exception as exc:
        return False, f"resolver unavailable ({type(exc).__name__})"


def prepare_app(app_name: str, capsule_cb=None, cursor_cb=None) -> Dict[str, Any]:
    """Bring an app to a usable state WITHOUT choosing or performing any UI action: launch if missing, clear stale
    dialogs, then wait (bounded, backoff) for a live control tree. Used for a command that only says 'open X'."""
    t0 = time.perf_counter()
    loop = get_loop(capsule_cb=capsule_cb, cursor_cb=cursor_cb)
    loop.awaiting_human = False
    loop._launch_note = ""
    launched = _launch_if_missing(loop, app_name, capsule_cb)
    if launched:
        loop._launched_apps.add((app_name or "").lower())
    loop._run_depth += 1
    try:
        try:
            loop._triage_popups(app_name, mode="preflight")
        except Exception as exc:
            logger.debug("[prepare_app] preflight note: %s", exc)
        hwnd, elements, report = loop._wait_for_ready(app_name)
    finally:
        loop._run_depth -= 1
        if loop._run_depth == 0:
            loop._release_held()
    if launched and hwnd:
        _mark_ours(hwnd)
    ready = bool(hwnd and elements) and not loop.awaiting_human
    return {"ready": ready, "hwnd": hwnd or 0, "launched": launched, "elements": len(elements or []),
            "window_title": loop.grounding.window_title(hwnd) if hwnd else "",
            "awaiting_human": loop.awaiting_human,
            "ready_reason": "" if ready else (report or {}).get("reason", "no-controls-within-ready-window"),
            "elapsed_s": round(time.perf_counter() - t0, 2)}


def get_loop(capsule_cb=None, cursor_cb=None) -> DesktopAutonomyLoop:
    global _LOOP_SINGLETON
    if _LOOP_SINGLETON is None:
        _LOOP_SINGLETON = DesktopAutonomyLoop(capsule_cb=capsule_cb, cursor_cb=cursor_cb)
        DesktopGrounding.start_warmup()   # load OmniParser once, off the goal path
        if os.environ.get("HOJAIGA_WEBAPP_WATCH", "1") != "0":
            try:   # learn every NEW web app origin (gmail, linkedin, ...) the moment Chrome shows it
                from core_organs import app_scan
                global _WEBAPP_WATCHER
                _WEBAPP_WATCHER = app_scan.WebAppWatcher()
                _WEBAPP_WATCHER.start()
            except Exception as exc:
                logger.debug("webapp watcher not started: %s", exc)
    else:
        if capsule_cb:
            _LOOP_SINGLETON.capsule_cb = capsule_cb
        if cursor_cb:
            _LOOP_SINGLETON.cursor_cb = cursor_cb
    return _LOOP_SINGLETON
