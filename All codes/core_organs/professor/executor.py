"""
professor.executor -- PRO-GRADE EXECUTION: hotkeys over pixels, guided by what the application and its guide say, and remembered once it works.

A professional does not hunt for pixels. They press the chord, choose the command, or type the value. This module turns a goal into an ordered plan of VERBS the application itself
declared (the harvested catalog), performs each verb through the most reliable route that exists, checks what happened, and says so honestly.

WHERE A PLAN COMES FROM (first that applies):
    1 skill       a chain that was VERIFIED on this application before (professor.skills): no lookup, no model, the whole chain at once
    2 words       every clause of the goal names a catalog verb with confidence >= 0.66: plain grounding, nothing else needed
    3 guide       the application's indexed USER GUIDE (knowledge.guide_finder / manual_rag): the best-grounded procedure for the goal, cited; manual prose is parsed into steps and each
                  step is matched to a real control (knowledge.guide_steps); steps that match nothing are reported UNKNOWN with the manual's words, never invented
    4 archetype   skills learned in OTHER applications of the same kind whose every step resolves here: offered as HYPOTHESES (the self-healing path for an application without a guide)
    5 model       a language model may CHOOSE among catalog verbs (grammar-constrained; "(none)" allowed; a pick with no lexical tie to the request is rejected)
ROUTE ladder per verb (the next route is tried only when the previous one produced NO effect):
    value (text into a named field: UIA ValuePattern, no focus needed) > command (WM_COMMAND) > shortcut (chord the application printed) > control (UIA pattern / BM_CLICK) > posted click
VERIFY: every step is followed by a before/after delta (professor.probe). 'No effect' on every route is reported as failure. An optional vision check can confirm a milestone.
LEARN: a run in which EVERY step was verified becomes a skill (professor.skills); a skill that fails three times in a row is retired; `achieve()` falls back to the guide / rules when a
skill fails before it changed anything.
SAFETY: dry-run by default. Verbs that are not plainly 'safe' (professor.safety) stop the plan and wait for a human yes. Input is only ever sent to a window the Professor launched or the user
authorised (professor.effectors), headless, with the user's focus handed back.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import safety
from .effectors import Effector
from .harvest import Catalog, Verb
from .knowledge.guide_steps import GROUNDED_HOW
from .dialogs import COPY_RX, PASTE_RX
from .schema import ScreenModel, fold


# ------------------------------------------------------------------------------------------------------------------ types
@dataclass
class Route:
    kind: str                       # value | command | shortcut | control | click
    detail: str
    rank: int
    arg: Any = None

    def label(self) -> str:
        return f"{self.kind}:{self.detail}"


@dataclass
class Step:
    index: int
    goal: str                       # what this step is for (plain words)
    verb: Optional[str] = None      # catalog verb label (None for text / unknown)
    verb_id: str = ""
    path: List[str] = field(default_factory=list)
    kind: str = "verb"              # verb | text | unknown
    text: str = ""
    safety: str = "safe"
    need_human: bool = False
    routes: List[str] = field(default_factory=list)
    expected: str = ""
    note: str = ""
    conf: float = 0.0               # how well the wording matches the verb's label (1.0 = exact); the model is only asked when this is low
    source: str = "rules"           # rules | model | guide | skill:<id> | archetype:<app>
    cite: str = ""                  # the manual passage the step came from
    aid: str = ""
    want: str = ""                  # '' | 'on' | 'off' (a check box / toggle: do nothing when it already is in that state)
    prefer: str = ""                # the route that worked last time (tried first)
    target: str = ""                # the interface term the MANUAL named for this step (kept when the step could not be grounded yet, so it can be grounded just in time)
    expect: Any = None              # professor.verify.Expectation: what the step should do (the manual's own result sentence, else what the control is known to do)


@dataclass
class StepResult:
    index: int
    verb: str
    status: str                     # done | no_effect | refused | needs_human | skipped | unknown | dry_run | failed | disabled
    route: str = ""
    tried: List[str] = field(default_factory=list)
    effect: str = ""
    summary: str = ""
    vision_ok: Optional[bool] = None
    ms: int = 0
    expected: str = ""              # the expectation the step was checked against
    verified: Optional[bool] = None # True = the screen shows the expected result; False = it does not; None = cannot tell
    evidence: str = ""


@dataclass
class ExecReport:
    goal: str
    steps: List[Step] = field(default_factory=list)
    results: List[StepResult] = field(default_factory=list)
    dry_run: bool = True
    ok: bool = False
    stopped: str = ""
    seconds: float = 0.0
    by: str = "rules"               # skill | rules | guide | archetype | rules+model
    cite: str = ""                  # manual passage a guide plan came from
    skill_id: str = ""              # skill a plan was taken from
    lineage: str = ""               # skill of ANOTHER application a hypothesis plan was adapted from
    learned: str = ""               # skill compiled from this run
    fallback: str = ""              # why a skill was replaced by a fresh plan
    unknown: List[str] = field(default_factory=list)   # what the guide said that could not be matched to a control

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def line(self) -> str:
        ok = sum(1 for r in self.results if r.status == "done")
        return (f"{'DRY-RUN ' if self.dry_run else ''}{ok}/{len(self.steps)} steps done [{self.by}{(' ' + self.cite) if self.cite else ''}]" + (f"; stopped: {self.stopped}" if self.stopped else "")
                + (f"; learned skill {self.learned}" if self.learned else ""))


# --------------------------------------------------------------------------------------------------------------- planning
CREDENTIAL_RX = re.compile(r"password|passcode|credential|payment|credit card|billing|bank|ssn|social security|secret|api key|token|2fa|two-factor|sign[- ]?in|log[- ]?in|sign[- ]?out|log[- ]?out", re.I)
KEY_AS_TEXT = {"enter": "\r\n", "tab": "\t", "space": " "}                 # when a toolkit ignores the posted key, the same character can be inserted through the editor's value pattern
SOFT_KEYS = {"escape", "home", "end", "up", "down", "left", "right", "pageup", "pagedown", "tab", "space"}
MOUSE_KEY_WORDS = {                                                        # a 'key' step whose word is a MOUSE button ('press LMB', PLAIN_KEYS' 'click'): no keyboard has that key; it means the mouse button, so the virtual mouse presses it
    "click": ("left", 1), "lmb": ("left", 1), "leftmouse": ("left", 1), "mouseleft": ("left", 1), "leftbutton": ("left", 1), "lmbclick": ("left", 1),
    "doubleclick": ("left", 2), "dblclick": ("left", 2), "leftclick": ("left", 2),
    "rightclick": ("right", 1), "rmb": ("right", 1), "rightmouse": ("right", 1), "mouseright": ("right", 1), "rightbutton": ("right", 1), "rmbclick": ("right", 1),
    "middleclick": ("middle", 1), "mmb": ("middle", 1), "middlemouse": ("middle", 1), "mousemiddle": ("middle", 1), "mmbclick": ("middle", 1),
}
SPLIT_RX = re.compile(r"\s*(?:,|;|\bthen\b|\band then\b|\bafter that\b|\bnext\b|\band\b)\s*", re.I)
TYPE_RX = re.compile(r"^(?:type|enter|write|input)\s+['\"“]?(.+?)['\"”]?$", re.I)
QUOTED_RX = re.compile(r"[\"“‘']([^\"”’']{1,80})[\"”’']")
# wording that means "something is sitting in front of the application": a card, a notice, a consent panel, a tour. Read from the PICTURE, not from a control name - this is what the eye is
# asked about when the hand has already failed, so it can say out loud what is holding the run back (a step that no route could move is often not a routing problem at all).
BLOCKER_RX = re.compile(r"(?i)\b(splash|welcome|what'?s new|whats new|tour|get started|sign ?in|log ?in|create (an )?account|trial|license|licence|consent|cookie|privacy|update[ds]?|restart now|reminder|banner|popup|dialog|modal|overlay|survey|feedback|rate|review|subscribe|upgrade|offer|promo|notice|allow|accept|agree)\b")
FIELD_ROLES = {"field", "edit", "text_field"}
# a verb that sounds destructive but only changes the DOCUMENT the run created (Delete, Remove background, Clear) may be performed in a throw-away document of an editor; one that touches the system, an account,
# files, history, or that would end the application itself (close / exit) may not. Categories of wording and of application kind - no application names.
STRONG_UNSAFE_RX = re.compile(r"(?i)\b(uninstall|shut ?down|restart|reboot|kill|terminate|wipe|purge|factory|reset all|format|sign ?out|log ?out|exit|quit|empty|close)\b")
DOC_OBJECT_RX = re.compile(r"(?i)\b(account|profile|history|data|cookies?|cache|passwords?|saved|files?|folders?|drive|disk|apps?|applications?|everything|device|windows?|system|browsing|all|tabs?)\b")
NEW_DOC_RX = re.compile(r"^(new|new (blank )?(document|presentation|workbook|window|file)|blank (document|presentation|workbook)|new from template)$")
DOC_EDITOR_ARCHETYPES = {"document_text", "raster_editor", "canvas_layout", "spreadsheet_data", "code_ide", "spatial_3d", "temporal_media"}


def _nl(name: str) -> str:
    """A control's name as a catalog label: folded, without a trailing '...' and without the accelerator text a menu item carries ('This Device...' / 'Open	Ctrl+O' -> 'this device' / 'open')."""
    t = re.sub(r"	.*$", "", name or "")
    t = re.sub(r"(\.\.\.|…)\s*$", "", t.strip())
    return fold(t)


_HUNG: Dict[int, float] = {}
_READ_COST: Dict[int, float] = {}                                     # hwnd -> seconds its LAST whole-tree read took (measured, never assumed): what a caller may wait for is derived from it
_KEEP: List[Any] = []                                             # every node list read during a run: released only after the owned application is closed (release_kept)


def release_kept() -> None:
    """Drop the kept UI Automation elements. Call AFTER the owned application is gone: releasing an element of a process whose UI thread is blocked blocks the caller (measured: Paint)."""
    _KEEP.clear()                                      # window -> until when it is skipped (its UIA provider did not answer)


def _timed_snapshot(hwnd: int, wall_s: float) -> Optional[List[Any]]:
    """fast_uia.snapshot with a WALL-CLOCK bound. This UIA build has no transaction timeout, and a modal dialog's provider can block a call forever (measured: a Word dialog snapshot
    held a whole run for minutes). The call runs in a worker thread (UIA client objects are free-threaded); when it is late, its result is abandoned and None returned.
    THE BOUND IS MEASURED, NOT GUESSED: a window whose last read took 22 s is given 22 s, because a read abandoned one second before it finishes throws away a complete tree AND
    leaves its worker thread walking the provider (every abandoned call slows the next one). `_READ_COST` is what the window actually costs."""
    import threading
    from core_organs import fast_uia
    box: Dict[str, Any] = {}
    bound = max(float(wall_s), min(60.0, _READ_COST.get(int(hwnd), 0.0) * 1.6)) if _READ_COST.get(int(hwnd), 0.0) else float(wall_s)

    def work() -> None:
        a = time.time()
        box["nodes"] = fast_uia.snapshot(hwnd, timeout_ms=int(bound * 1000))
        if box["nodes"]:
            _READ_COST[int(hwnd)] = round(time.time() - a, 2)        # measured: the next bound for this window is derived from it
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(bound)
    _KEEP.append(box)                                             # kept alive (also when abandoned): see release_kept
    if len(_KEEP) > 4000:
        del _KEEP[:1000]
    return box.get("nodes") if not t.is_alive() else None


def _frame_enabled(hwnd: int) -> bool:
    """Can this window still act? A modal dialog of the same process DISABLES the frame (Win32 `EnableWindow(FALSE)`): measured on Word, whose frame answered 174 nodes after 22 s while its
    'Save your changes to this file?' dialog answered 31 nodes in 0.3 s. A disabled frame cannot change, no matter how often or how long it is read - the only thing that matters is the dialog."""
    try:
        import ctypes
        return bool(ctypes.windll.user32.IsWindowEnabled(int(hwnd)))
    except Exception:                                                # noqa: BLE001
        return True


class _TreeMirror:
    """ONE window's accessibility tree, read continuously by one background thread and published as generations (a finished read, stamped with when it began and ended).

    WHY (measured on Word): a whole-tree provider read costs ~22 s for 1128 nodes (~20 ms per element - Office paints its UI lazily and answers element by element). A step that reads the
    tree before and after every route attempt therefore costs ~45 s, and a read a step can afford to wait for (12 s) is always abandoned: the run ends up working from an EMPTY window and
    reports 'control not found in the live tree' for controls that exist, while each abandoned call keeps hammering the provider and makes the next read slower. So the tree is read at the
    provider's own pace in the background; the step loop takes the newest published generation and waits for NOTHING. A window whose frame a modal dialog has disabled is not read at all
    (it cannot change while the dialog owns it), which is also what makes the dialog's own fast tree the only thing worth looking at."""

    def __init__(self, hwnd: int):
        self.hwnd = int(hwnd)
        self.gens: List[Tuple[float, float, List[Any]]] = []                # (began, ended, nodes) oldest first, newest last
        self.lock = threading.Lock()
        self.busy = False
        self.stopped = False
        self.reads = 0
        self.skipped = 0                                        # reads not attempted (a modal owns the window, or the process is gone)
        self.thread: Optional[threading.Thread] = None

    def _loop(self) -> None:
        from core_organs import fast_uia
        import ctypes
        while not self.stopped:
            try:
                if not ctypes.windll.user32.IsWindow(self.hwnd):
                    return
                if not _frame_enabled(self.hwnd):                        # a dialog owns this window: its tree is frozen; the dialog is read through light_popups instead
                    self.skipped += 1
                    time.sleep(0.7)
                    continue
                self.busy = True
                began = time.time()
                nodes = fast_uia.snapshot(self.hwnd, max_nodes=20000, timeout_ms=int(_READ_BOUND_S * 1000))
                self.busy = False
                if nodes:
                    ended = time.time()
                    _READ_COST[self.hwnd] = round(ended - began, 2)
                    with self.lock:
                        self.gens.append((began, ended, nodes))
                        del self.gens[:-3]                                # three generations: enough for a before/after pair plus one spare
                    self.reads += 1
                    # PACING (measured the hard way: a run that published 7996 generations in 1632 s had the reader spinning on a small tree,
                    # and the provider it was hammering is the one the steps need answered). A window is refreshed at its own cost: a 17 s tree
                    # needs no pause, a 0.05 s shell waits a full second before it is looked at again.
                    time.sleep(max(1.0, min(4.0, (ended - began) * 0.35)))
                else:
                    time.sleep(1.0)                                       # nothing came back: the window is starting, hung, or painted by itself
            except Exception:                                            # noqa: BLE001
                self.busy = False
                time.sleep(1.0)

    def latest(self) -> Optional[List[Any]]:
        with self.lock:
            return self.gens[-1][2] if self.gens else None

    def began_after(self, t: float) -> Optional[List[Any]]:
        """A generation whose read STARTED after `t`: the state it shows cannot contain anything that happened before `t`, so it is an honest 'after' for an action taken at `t`."""
        with self.lock:
            for began, _e, nodes in reversed(self.gens):
                if began > t:
                    return nodes
        return None

    def start(self) -> "_TreeMirror":
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._loop, daemon=True, name=f"uiamirror{self.hwnd}")
            self.thread.start()
        return self

    def stats(self) -> Dict[str, Any]:
        with self.lock:
            return {"reads": self.reads, "skipped_modal": self.skipped, "last_nodes": len(self.gens[-1][2]) if self.gens else 0,
                    "read_s": _READ_COST.get(self.hwnd, 0.0), "age_s": round(time.time() - self.gens[-1][1], 1) if self.gens else None}


_READ_BOUND_S = 45.0                                              # the background reader's own ceiling for one window: long enough for a slow provider (Word 22 s) to FINISH
_MIRRORS: Dict[int, _TreeMirror] = {}


def mirror_for(hwnd: int) -> Optional[_TreeMirror]:
    """The window's background tree reader, started on first use (one per hwnd for the whole process). None when windowing calls are unavailable."""
    try:
        key = int(hwnd)
    except Exception:                                                # noqa: BLE001
        return None
    m = _MIRRORS.get(key)
    if m is None:
        m = _MIRRORS[key] = _TreeMirror(key).start()
    elif m.stopped or (m.thread is not None and not m.thread.is_alive()):
        m.stopped = False
        m.start()
    return m


def stop_mirrors() -> None:
    for m in list(_MIRRORS.values()):
        m.stopped = True
    _MIRRORS.clear()


from core_organs.fast_uia import _UNLAID, _offscreen_by_window  # noqa: E402,F401 - the correction lives in the tree reader (every reader gets it)


class Executor:
    def __init__(self, hwnd: int, effector: Effector, catalog: Catalog, sm: Optional[ScreenModel] = None, brain: Any = None, owned: bool = False,
                 vision_check: Optional[Callable[[Step, Any, Any], Optional[bool]]] = None, skills: Any = None, guide_index: Any = None, archetype: str = "", app_version: str = "",
                 history: Any = None, learner: Any = None, toolkit: str = "", pointer: Any = None, adapter: Any = None):
        self.hwnd, self.fx, self.catalog, self.sm, self.brain, self.owned = hwnd, effector, catalog, sm, brain, owned
        self.adapter = adapter                                   # professor.adapters.*: a protocol route (DevTools) for toolkits UI Automation cannot drive alone
        self.learner = learner                                   # professor.ml.Learner: re-orders routes by learnt P(ok) and trains while this runs
        self.toolkit = toolkit                                   # the application's toolkit family (professor.interaction): a feature of every logged action
        self.pointer = pointer                                   # professor.virtual_mouse.VirtualMouse: glides to each control before the action is delivered (overlay + database trace)
        self._last_trace: Optional[Dict[str, Any]] = None
        self.vision_check = vision_check
        self.history = history                                   # professor.history.History or None: every route tried leaves a state-transition row
        self.skills, self.guide_index, self.archetype, self.app_version = skills, guide_index, archetype, app_version
        self._main_n = 0
        self.mirror = mirror_for(hwnd)                             # the window's tree read in the BACKGROUND (_TreeMirror): a step takes the newest published generation instead of waiting 22 s for a provider read
        self.step_cap = float(os.environ.get("HOJAIGA_STEP_CAP", "90"))   # the most wall clock ONE step may spend: a procedure that cannot move in that time is reported with its reason, not retried into the night
        self.modal_log: List[Dict[str, Any]] = []                  # dialogs that took the window (its frame disabled) and what the run answered to get it back
        self.eye_log: List[Dict[str, Any]] = []                    # what the EYE saw sitting in front of the window when a route could not move it, and whether it backed out of it
        self.sibling = 0                                               # a SIBLING window of the same process whose tree is bigger than the handle the run owns: the application moved its own screen
        self._sib_nodes: Any = None                                    # its tree, kept fresh for a few seconds so the merge is not paid for twice
        self.sibling_log: List[Dict[str, Any]] = []                  # when that happened and what each window held - the report must say 'we were reading a shell', not 'the control is missing'
        self._sib_at = 0.0
        self._eye_sig = ""                                               # the screen the eye last read (one look per picture, never two)
        self._eye_said = ""                                              # and what it said was sitting in front of it
        self._t_run = time.time()
        self.follow: List[int] = []                              # windows the application opened AFTER one of our steps (a picker, an online-content browser, a preview): they may be hosted by a helper process, so the same-process popup merge never finds them - the run FOLLOWS them
        self._last_verb: Optional[Verb] = None                      # the verb the previous step performed: the next step's words are resolved NEAR it
        self._sticky_left = 0
        self._sticky = None                                          # a held foreground while a flyout menu opened by an earlier step is still to be used by the next one
        self.placeholder = "Hojaiga test"                         # what goes into a field when the guide says only 'enter a name' (never data of the user's)
        self.sandboxed = False                                    # the run created the state it works in (a throw-away profile, a backed-up and restored data folder)
        self.allow: Optional["re.Pattern"] = None                 # verbs that look 'sensitive' to the generic safety rules but are harmless HERE (the profile of a throw-away Chrome the run itself created)
        self.dialogs: Any = None                                  # professor.dialogs.DialogDriver: file dialogs (sandbox files), message boxes, print dialogs
        self.clip: Any = None                                     # professor.dialogs.ClipboardGuard: the person's clipboard is saved before a run writes to it and put back after
        self.sandbox: Any = None                                  # professor.dialogs.Sandbox: the only place a dialog may read from / write to
        self.dialog_log: List[Dict[str, Any]] = []
        self._file_followups = 0                                  # file-dialog steps of the guide that follow a dialog the handler already completed
        self.deny: Optional["re.Pattern"] = None                  # an application-level policy: verbs matching this are NEVER performed without a human yes (Save As in a throw-away document, Send in a messenger)
        self.app_words: Tuple[str, ...] = ()                      # the words the guide uses for the application itself ('Open PowerPoint' = the launcher's job)
        self.on_step: Optional[Callable[[str, Step, Optional["StepResult"]], None]] = None   # narration / teaching hook: ('before' | 'after', step, result)
        self.verify_log: List[Dict[str, Any]] = []                # every step's stated expectation and whether the screen confirmed it (professor.verify)
        self._last: Any = None                                     # (before, after, delta) of the step that just ran
        self.pointer_stats: Dict[str, int] = {"aimed": 0, "reached": 0, "no_box": 0, "errors": 0}     # the virtual mouse: steps it was sent to a control, and how many it reached
        self.triggers: Any = None                                 # professor.triggers.TriggerBank: verified stand-ins for controls no ordinary route could operate (capped, see triggers.py)
        self.script_bridge: Any = None                            # professor.adapters.script_bridge.ScriptBridge: the application's own scripting engine (commands + view gestures)
        self.gesture_driver: Any = None                           # professor.gestures.GestureDriver: pointer gestures through the route the application accepts
        try:
            self.fx.app_key = catalog.app_key or ""                # the virtual mouse files what it learns about this application under this key
        except Exception:
            pass
        self.object_model: Any = None                             # professor.adapters.object_model.*: the SAME command through the application's own automation model (the reroute when the UI cannot reach it)
        self.activation_first = bool(self._traits().get(catalog.app_key or "", {}).get("activation_first"))   # learnt: this application shows flyouts only after an activation message (see _nudge_active)
        self.entered_contexts: List[str] = []                     # contextual tabs (modes: Slide Master) a step entered to reach its control - left again by leave_contexts()
        self.supervisor: Any = None                               # professor.supervision.Supervisor: the person's tiered policy, asked before EVERY step (it can only add a pause)

    @property
    def app_key(self) -> str:
        return self.catalog.app_key

    # ---- grounding
    def resolve_scored(self, text: str) -> Tuple[Optional[Verb], float]:
        """(verb, confidence) for a phrase: exact label = 1.0, else the share of the (content) words that the label explains. Enabled, plainly safe, shallow verbs win ties."""
        from .knowledge.guide_steps import resolve_label
        return resolve_label(self.catalog, text)

    def resolve(self, text: str) -> Optional[Verb]:
        """The catalog verb a phrase means (see resolve_scored)."""
        return self.resolve_scored(text)[0]

    def _snap(self, **kw: Any) -> Any:
        from .probe import snapshot
        extra = None
        if self.adapter is not None:
            try:
                extra = self.adapter.state_texts()
            except Exception:
                extra = None
        kw = dict(kw)                                                    # the frame's tree comes from the background reader (the snapshot stays honest: its picture, its pop-ups and its window list are always live)
        fr = self._frame_nodes()
        if fr is not None:
            kw["nodes"] = fr
        if extra:
            return snapshot(self.hwnd, extra=extra, **kw)
        return snapshot(self.hwnd, **kw)

    def routes_for(self, v: Verb, text: str = "") -> List[Route]:
        out: List[Route] = []
        if self.script_bridge is not None and v.aid.startswith("script:rna:"):
            return [Route("scripting", f"set '{v.label}' through the application itself", 5, (v.aid[len("script:rna:"):], text))]       # a setting is not a command: it is read / set by name, with the value the step names
        if self.adapter is not None and self.adapter.owns(v):
            out.append(Route("adapter", f"{self.adapter.name}: {v.label}", 0, text))
            return out
        if text and (v.role in FIELD_ROLES or v.role == "field"):
            out.append(Route("value", f"set value of '{v.label}'", 0, text))
        if v.command_id:
            out.append(Route("command", f"WM_COMMAND {v.command_id}", 1, v.command_id))
        if v.shortcut:
            out.append(Route("shortcut", v.shortcut, 2, v.shortcut))
        opener = not text and (v.role in ("dropdown", "menu_item") or "menu" in (v.leads_to or ""))
        if opener and "menu" in (v.leads_to or ""):                                       # a control that EXPANDS (drop-down, split button): Expand opens it; Invoke may do nothing or perform its main action (measured on Paint's Rotate)
            out.append(Route("expand", f"open '{v.label}' (ExpandCollapse)", 3, v.aid or v.label))
        if (v.role != "menu_item" or not v.command_id) and not (text and v.role in FIELD_ROLES):
            out.append(Route("control", v.label, 3, v.aid or v.label))
        if opener and "menu" not in (v.leads_to or ""):
            out.append(Route("expand", f"open '{v.label}' (ExpandCollapse)", 3, v.aid or v.label))
        el = self._element_for(v)
        if el is not None and not text:
            out.append(Route("click", f"centre of '{v.label}'", 4, (int(el.bbox.cx), int(el.bbox.cy))))
        if self.script_bridge is not None and v.aid.startswith("script:") and not text:
            sr = Route("scripting", f"the application's own command {v.aid[7:]}", 5, v.aid[7:])
            if getattr(self, "blind", False):
                return [sr]                                                      # a window whose interface tree is blind: the UI routes cannot find the control; the application runs it itself
            out.append(sr)
        mso = self._mso_for(v) if self.object_model is not None and not text else ""
        if mso:
            out.append(Route("object_model", f"ExecuteMso {mso}", 5, mso))           # last rung: the same command through the application's object model
        return out

    def _mso_for(self, v: Verb) -> str:
        """The application's own command id for a verb: its aid when the vendor manifest gave one, else the manifest verb of the same name UNDER THE SAME OPENER / GROUP (the closest container
        of both must be the same term). Two commands may share a name ('This Device' inserts a picture under 'Pictures' and a 3D model under '3D Models' - measured: taking the wrong one
        opened the 3D-model dialog and a later step crashed Word), so a same-named command elsewhere is never taken."""
        if v.aid.startswith("mso:"):
            return v.aid[4:]
        from .knowledge.guide_steps import _container_eq
        same = [x for x in self.catalog.verbs if x.aid.startswith("mso:") and fold(x.label) == fold(v.label) and not (x.path and str(x.path[0]).startswith("Context menu"))]
        if v.path:
            same = [x for x in same if x.path and _container_eq(str(v.path[-1]), str(x.path[-1]))]
        if not same:
            return ""
        same.sort(key=lambda x: -len(set(fold(p) for p in x.path) & set(fold(p) for p in v.path)))
        return same[0].aid[4:]

    def _element_for(self, v: Verb) -> Any:
        if self.sm is None:
            return None
        for e in self.sm.elements:
            if v.aid and e.aid == v.aid:
                return e
        exact = next((e for e in self.sm.elements if fold(e.label) == fold(v.label) and e.bbox.w > 2), None)
        if exact is not None:
            return exact
        # the scanner could not read this control, but the vision side saw SOMETHING of the right shape there: a namesake picture (vision 'Bold' ~ tree 'Bold (Ctrl+B)') is the place to click
        from .symbol_eval import agree
        return next((e for e in self.sm.elements if (e.label or "").strip() and e.bbox.w >= 4 and e.bbox.h >= 4 and (agree(v.label, e.label) or agree(e.label, v.label))), None)

    def _step_for_verb(self, v: Verb, goal: str, conf: float, source: str, cite: str = "", want: str = "", text: str = "", prefer: str = "") -> Step:
        cls = safety.classify(v.label, " ".join(v.path))
        hum = safety.needs_human(v.label, " ".join(v.path)) and not (self.owned and cls == "commit")
        if hum and cls == "sensitive" and self.sandboxed and not CREDENTIAL_RX.search(v.label + " " + " ".join(v.path)):
            hum = False                                                   # 'Profile', 'Account settings' in a throw-away profile: nothing of the user's is touched; credentials / payment / sign-in still wait for a human
        if hum and cls == "sensitive" and self.allow is not None and self.allow.search(v.label):
            hum = False
        if hum and cls == "unsafe" and self._doc_local(v):
            hum = False                                                   # 'Remove background' / 'Delete' in a throw-away document of an editor
        if self.deny is not None and self.deny.search(v.label + " " + " ".join(v.path)):
            hum, cls = True, ("sensitive" if cls == "safe" else cls)
        if NEW_DOC_RX.match(fold(v.label)) and getattr(self.object_model, "multi_document", False):
            hum, cls = True, ("sensitive" if cls == "safe" else cls)               # a NEW document window of a multi-document application would open on the person's screen (it is not the parked one)
        # SANDBOX POLICY RELAXATION: allow harmless formatting/layout commits in sandboxed documents
        if hum and cls == "commit" and self.sandboxed:
            # Allow safe formatting and layout actions when working in throw-away sandbox
            if re.search(r"\b(format|layout|style|theme|colors?|fonts?|spacing|align|indent)\b", v.label + " " + " ".join(v.path), re.I) and \
                    not re.search(r"\b(save|export|install|import|publish|overwrite|replace|upload|share|send|default)\b", v.label, re.I):
                hum = False                                                       # applying a format in the throw-away document - never saving / exporting / changing a default
        exp = ("opens a dialog" if v.leads_to else "changes the application state")
        return Step(0, goal, v.label, v.id, list(v.path), "verb", text=text, safety=cls, need_human=hum, routes=[r.label() for r in self.routes_for(v, text)], expected=exp, conf=conf,
                    source=source, cite=cite, aid=v.aid, want=want, prefer=prefer)

    def _ground(self, goal: str, verb_label: Optional[str], index: int) -> Step:
        text_m = TYPE_RX.match(goal.strip())
        if text_m:
            return Step(index, goal, None, "", [], "text", text=text_m.group(1), safety="safe", need_human=False, routes=["text:posted characters"], expected="the typed text appears")
        if verb_label is not None and fold(verb_label) in ("none", "(none)"):
            return Step(index, goal, None, "", [], "unknown", note="none of the application's commands does this (it may sit in a menu that was never opened) -- not invented", safety="unknown", need_human=True)
        v, conf = self.resolve_scored(verb_label or goal)
        if v is None:
            return Step(index, goal, None, "", [], "unknown", note="no verb in the catalog matches this step -- not invented", safety="unknown", need_human=True)
        st = self._step_for_verb(v, goal, conf, "model" if verb_label else "rules")
        st.index = index
        return st

    def _tied_to_request(self, goal: str, st: Step) -> bool:
        """A verb the MODEL picked is only used when its own name / description / tooltip shares a content word with the request. A small model will happily answer 'View' for 'zoom in'."""
        gw = {w for w in fold(goal).split() if len(w) > 2 and w not in ("the", "and", "then", "with", "into", "for", "from")}
        v = next((x for x in self.catalog.verbs if x.id == st.verb_id), None)
        if v is None:
            return False
        vw = {w for w in fold(" ".join([v.label, v.desc, self.catalog.tooltips.get(fold(v.label), "")])).split() if len(w) > 2}
        return bool(gw & vw)

    # ---- plans from skills / the guide / other applications
    def steps_from_skill(self, sk: Any, goal: str) -> List[Step]:
        """A skill's chain, re-grounded in the CURRENT catalog (safety is recomputed now). Quoted strings in the goal fill the skill's text slots in order."""
        quotes = QUOTED_RX.findall(goal)
        out: List[Step] = []
        for st in sk.steps:
            if st.kind == "key":
                out.append(Step(len(out), goal, None, "", [], "key", text=st.text, safety="safe", routes=[f"key:{st.text}"], expected=f"the {st.text} key is delivered", source=f"skill:{sk.id}"))
                continue
            if st.kind == "text":
                txt = quotes.pop(0) if quotes else st.text
                out.append(Step(len(out), goal, None, "", [], "text", text=txt, safety="safe", routes=["text:posted characters"], expected="the typed text appears", source=f"skill:{sk.id}"))
                continue
            v = next((x for x in self.catalog.verbs if st.verb_id and x.id == st.verb_id), None) or self.resolve(st.label)
            if v is None:
                out.append(Step(len(out), goal, None, "", [], "unknown", safety="unknown", need_human=True, note=f"skill step '{st.label}' no longer exists in the application", source=f"skill:{sk.id}"))
                continue
            txt = ""
            if st.text:
                txt = quotes.pop(0) if quotes else st.text
            s = self._step_for_verb(v, goal, 1.0, f"skill:{sk.id}", st.cite, st.want, txt, st.route)
            s.index = len(out)
            out.append(s)
        return out

    def steps_from_guide(self, gp: Dict[str, Any], max_steps: int = 10) -> List[Step]:
        out: List[Step] = []
        for g in gp["steps"][:max_steps]:
            st = g.step
            if g.how in ("path", "label", "chord", "group") and g.verb is not None:
                want = st.action if st.action in ("on", "off") else ""
                if not want and st.action == "open" and g.verb.role in ("toggle", "checkbox"):
                    want = "on"                                                       # 'switch to Slide Master view': a view toggle that is already on needs nothing
                txt = st.text if (st.action == "type" and st.text) else ""
                placeholder = False
                if not txt and st.action in ("type", "set") and (g.verb.role in FIELD_ROLES or g.verb.role == "field"):
                    txt, placeholder = self.placeholder_for(g.verb), True            # the manual says WHAT to enter only in general terms ('a descriptive name'): a neutral test value stands in, and the step says so
                s = self._step_for_verb(g.verb, st.raw, g.conf, "guide", gp["cite"], want, txt)
                if placeholder:
                    s.note = (s.note + " " if s.note else "") + "the manual gives no literal value: a neutral placeholder is entered"
            elif g.how == "typed":
                s = Step(0, st.raw, None, "", [], "text", text=st.text, safety="safe", routes=["text:posted characters", "text:uia value"], expected="the typed text appears", source="guide", cite=gp["cite"])
            elif g.how == "optional":
                s = Step(0, st.raw, None, "", [], "skip", safety="safe", routes=["optional: skipped"], expected="nothing - the manual calls it optional", source="guide", cite=gp["cite"], note=g.note)
            elif g.how == "dialog":
                s = Step(0, st.raw, None, "", [], "dialog", safety="safe", routes=["dialog: sandbox file"], expected="the file dialog is completed with a file of the run's sandbox", source="guide", cite=gp["cite"],
                         note=g.note, target=st.target)
            elif g.how == "human":
                s = Step(0, st.raw, None, "", [], "unknown", safety="sensitive", need_human=True, note=g.note, source="guide", cite=gp["cite"], target=st.target)
            elif g.how in ("gesture", "gesture_ok"):
                from .gestures import kind_of
                gk = kind_of(st.raw)
                s = Step(0, st.raw, None, "", [], "gesture", text=gk, safety="safe", routes=[f"gesture:{gk} (scripting > posted > synthetic touch on the visible window)"],
                         expected=f"the canvas / view shows the {gk}", source="guide", cite=gp["cite"], note=g.note, target=st.target)
            elif g.how == "key":
                from .knowledge.guide_steps import PLAIN_KEYS
                key = st.chord if st.chord else PLAIN_KEYS.get(fold(st.target), fold(st.target))
                s = Step(0, st.raw, None, "", [], "key", text=key, safety="safe", routes=[f"key:{key}"], expected=f"the {key} key is delivered", source="guide", cite=gp["cite"])
            elif g.how in ("app", "outside"):
                s = Step(0, st.raw, None, "", [], "skip", safety="safe", routes=["not a step of this application: skipped"], expected="nothing", source="guide", cite=gp["cite"],
                         note=("the application is already open (the run launched it)" if g.how == "app" else "outside this application: " + g.note))
            elif g.how == "content":
                s = self._content_step(st, gp["cite"])
            elif g.how == "dialog_button":
                from .knowledge.version_fit import DIALOG_BUTTON_RX
                m = DIALOG_BUTTON_RX.match(re.sub(r"\*\*", "", st.raw or "").strip())
                btn = (m.group(1) if m else (st.target or "OK")).strip()
                hum = bool(self.deny is not None and self.deny.search(btn))
                s = Step(0, st.raw, btn, "", [], "dialog_button", text=btn, safety="sensitive" if hum else "safe", need_human=hum, routes=[f"button '{btn}' of the open dialog"],
                         expected="the dialog takes the answer (closes or moves on)", source="guide", cite=gp["cite"], target=btn)
            elif g.how == "choice" and g.verb is None:
                s = Step(0, st.raw, None, "", [], "choice", safety="safe", routes=["first plain item of what is open"], expected="one option of the open menu / gallery / list is taken",
                         source="guide", cite=gp["cite"], note=g.note, target=st.target)
            elif g.how == "choice" and g.verb is not None:
                s = self._step_for_verb(g.verb, st.raw, g.conf, "guide", gp["cite"])
                s.note = (s.note + " " if s.note else "") + "the manual leaves the choice open: the first option was taken"
            else:
                s = Step(0, st.raw, None, "", [], "unknown", safety="unknown", need_human=True, note=g.note or "the manual's step matches no control", source="guide", cite=gp["cite"], target=st.target)
                s.text = st.text
            s.index = len(out)
            out.append(s)
        return out

    OBJECT_KIND_RX = re.compile(r"(?i)\b(placeholder|shape|picture|image|photo|chart|table|text ?box|wordart|smartart|video|audio|equation|graphic|diagram|3d model|slide|thumbnail)s?\b")
    ENTRY_RX = re.compile(r"(?i)^(edit|open|show|view|go to|enter)\s+\S")      # an entry command of a mode: 'Edit Header', 'Show Comments'
    SCENE_OBJECT_RX = re.compile(r"(?i)\b(mesh elements?|vertices|vertex|edges?|faces?|armature|bones?|camera|light|curve|mesh(?:es)?|empty|lattice|objects?)\b")
    CONTROL_WORD_RX = re.compile(r"(?i)\b(button|tab|menu|command|toolbar|ribbon|tool|icon|gallery|drop-?down|option)\b")
    CONTENT_SELECT_RX = re.compile(r"(?i)\b(select|highlight|choose)\b.{0,30}\b(text|word|words|paragraph|paragraphs|sentence|line|lines|all|it)\b")
    CONTENT_TYPE_RX = re.compile(r"(?i)^(?:\d+[.)]\s*)?(?:type|enter|write|begin typing|start typing)\b")
    CONTENT_CARET_RX = re.compile(r"(?i)\b(where you want|insertion point|place (?:your|the) cursor|position the cursor|click (?:outside|anywhere|in the (?:document|body|pane|slide)|on your new blank page))\b")

    def _content_step(self, st: Any, cite: str) -> Step:
        """A step on the DOCUMENT's own content ('select the text', 'click where you want', 'type some text'), made concrete in the run's throw-away document: select = the application's own
        Select All; type = a neutral test sentence; caret = nothing to do (the insertion point is already in the document). Anything else needs an object the run did not create: named."""
        raw = re.sub(r"\*\*", "", st.raw or "")
        from .knowledge.version_fit import OBJECT_REF_RX
        om = OBJECT_REF_RX.search(raw)
        kind = (om.group(1) if om else "") or (self.OBJECT_KIND_RX.search(raw).group(1) if self.OBJECT_KIND_RX.search(raw) else "")
        if fold(kind) in ("text", "word", "words", "paragraph", "paragraphs", "line", "lines", "sentence", "cell", "cells", "it", "them", "all"):
            kind = ""                                                             # 'select the text to convert': the document's own text (Select All), not an object
        if not kind and self.script_bridge is not None and hasattr(self.script_bridge, "select_object"):
            sm = self.SCENE_OBJECT_RX.search(raw)
            if sm and re.search(r"(?i)\b(select|click|tap|choose|pick)\b", raw):
                kind = sm.group(1)                                                # 'select an object or mesh element(s)': the scene's own objects, through its scripting engine
        if kind and (self.object_model is not None or self.script_bridge is not None) and re.search(r"(?i)\b(select|click|tap|double-click|choose|highlight)\b", raw) and not self.CONTENT_CARET_RX.search(raw) and (om or not self.CONTROL_WORD_RX.search(raw)):
            return Step(0, st.raw, None, "", [], "object", text=kind, safety="safe", routes=["object model: select the run's own object"], expected=f"a {kind} in the document is selected",
                        source="guide", cite=cite, note=f"the step works on an object in the document (a {kind}): the run selects one it created itself")
        if self.CONTENT_SELECT_RX.search(raw):
            v = next((x for x in self.catalog.verbs if fold(x.label) in ("select all", "select all text") and x.enabled and x.safety == "safe" and (set(x.sources or []) - {"vendor-manifest"})), None) \
                or next((x for x in self.catalog.verbs if fold(x.label) in ("select all", "select all text") and x.enabled), None)
            if v is not None and (v.shortcut or (set(v.sources or []) - {"vendor-manifest", "atlas-uimap"}) or (self.object_model is not None and v.aid.startswith("mso:"))):
                s = self._step_for_verb(v, st.raw, 0.8, "guide", cite)
                s.note = "a selection in the document: the application's own Select All stands in"
                return s
            return Step(0, st.raw, None, "", [], "key", text="ctrl+a", safety="safe", routes=["key:ctrl+a"], expected="the document's content is selected", source="guide", cite=cite,
                        note="a selection in the document: the universal Select All chord (the application's own Select All is only documented, not reachable on screen)")
        if self.CONTENT_TYPE_RX.search(raw) and not st.text:
            is_num = bool(re.search(r"(?i)\b(amount|value|values|number|numbers|digits|quantity|sum|total|price)\b", raw))
            type_txt = "100" if is_num else (self.placeholder + " text")
            return Step(0, st.raw, None, "", [], "text", text=type_txt, safety="safe", routes=["text:posted characters", "text:uia value"], expected="the typed text appears",
                        source="guide", cite=cite, note="the manual says enter an amount/value: a neutral test number is typed" if is_num else "the manual says only 'type some text': a neutral test sentence is typed")
        if self.CONTENT_CARET_RX.search(raw):
            return Step(0, st.raw, None, "", [], "skip", safety="safe", routes=["insertion point: nothing to do"], expected="nothing", source="guide", cite=cite,
                        note="the insertion point is already in the run's throw-away document")
        return Step(0, st.raw, None, "", [], "unknown", safety="unknown", need_human=True, source="guide", cite=cite, target=st.target,
                    note="the step acts on an object in the document (a picture, a shape, a slide's item) that this run did not create")

    def plan_from_procedure(self, goal: str, cite: str, steps: Sequence[Any], max_steps: int = 12, text: str = "") -> ExecReport:
        """A plan from ONE named procedure of the guide (parsed GuideStep list), grounded against the CURRENT catalog - no retrieval, no model: 'run what the manual says'. `text`: the guide passage,
        so each step's expected result can be taken from the manual's own words."""
        from .knowledge import guide_steps as GS
        g = GS.ground(list(steps), self.catalog, self.app_words)
        rep = ExecReport(goal=goal)
        rep.steps, rep.by, rep.cite = self.steps_from_guide({"steps": g, "cite": cite}, max_steps), "guide", cite
        rep.unknown = [x.note or x.step.raw for x in g if x.how not in GROUNDED_HOW]
        self.attach_expectations(rep, text)
        return rep

    def attach_expectations(self, rep: ExecReport, text: str = "") -> None:
        from . import verify as VF
        for st in rep.steps:
            if st.expect is None:
                v = next((x for x in self.catalog.verbs if st.verb_id and x.id == st.verb_id), None)
                try:
                    st.expect = VF.expectation_for(st, v, text)
                except Exception:
                    st.expect = None
            if st.expect is not None and not st.expected:
                st.expected = st.expect.text()

    def plan(self, goal: str, max_steps: int = 8, use_skills: bool = True, use_guide: bool = True) -> ExecReport:
        """Goal text -> grounded steps (see the module doc for the order of the sources)."""
        rep = ExecReport(goal=goal)
        # 1 a verified skill of this application
        if use_skills and self.skills is not None:
            try:
                sk = self.skills.find(goal, self.app_key, self.catalog)
            except Exception:
                sk = None
            if sk is not None:
                rep.steps, rep.by, rep.skill_id = self.steps_from_skill(sk, goal), "skill", sk.id
                return rep
        clauses = [c for c in SPLIT_RX.split(goal) if c.strip()]
        rule_steps = [self._ground(c, None, i) for i, c in enumerate(clauses[:max_steps])]
        sure = bool(rule_steps) and all(st.kind == "text" or (st.kind == "verb" and st.conf >= 0.66) for st in rule_steps)
        if sure:                                                                                 # 2 the words alone ground every clause
            rep.steps = rule_steps
            return rep
        # 3 the application's own guide
        if use_guide and self.guide_index is not None:
            try:
                from .knowledge import guide_steps as GS
                gp = GS.plan_from_guide(goal, self.catalog, self.guide_index, self.app_key, self.brain)
            except Exception:
                gp = None
            if gp is not None:
                rep.steps, rep.by, rep.cite = self.steps_from_guide(gp, max_steps + 2), "guide", gp["cite"]
                rep.unknown = list(gp.get("unknown", []))
                return rep
        # 4 skills learned on other applications of the same kind (hypotheses)
        if use_skills and self.skills is not None and self.archetype:
            try:
                sug = self.skills.suggest_cross_app(goal, self.app_key, self.archetype, self.catalog)
            except Exception:
                sug = []
            if sug:
                sk, _c = sug[0]
                steps = self.steps_from_skill(sk, goal)
                for s in steps:
                    s.source = f"archetype:{sk.app_key}"
                    s.note = (s.note + " " if s.note else "") + "adapted from another application of the same kind: a hypothesis, verified now"
                rep.steps, rep.by, rep.lineage = steps, "archetype", sk.id
                return rep
        # 5 the model chooses among catalog verbs
        steps: List[Step] = []
        if self.brain is not None and not TYPE_RX.match(goal.strip()):
            try:
                if self.brain.available():
                    cands: List[str] = []
                    for c in clauses + [goal]:
                        for v in self.catalog.best(c, 6):
                            if v.label not in cands:
                                cands.append(v.label)
                    for v in self.catalog.verbs:
                        if len(cands) >= 70:
                            break
                        if v.safety == "safe" and v.label not in cands and v.enabled:
                            cands.append(v.label)
                    if cands:
                        schema = {"type": "object", "properties": {"steps": {"type": "array", "maxItems": max_steps, "items": {"type": "object", "properties": {
                            "verb": {"type": "string", "enum": cands + ["(none)"]}, "why": {"type": "string"}}, "required": ["verb", "why"]}}}, "required": ["steps"]}
                        r = self.brain.generate("You plan GUI work as a short ordered list of the application's OWN commands. Use ONLY the verbs offered, and ONLY steps the goal needs - never pad. "
                                                "If a step needs a command that is not offered, answer \"(none)\" for it. Fewest steps. One sentence 'why' each.",
                                                f"Goal: {goal}\nApplication: {self.catalog.title}\nVerbs: {json.dumps(cands)}", schema=schema, max_tokens=420, temperature=0.0, timeout=90)
                        if r.ok and isinstance(r.json, dict) and r.json.get("steps"):
                            for i, s in enumerate(r.json["steps"][:max_steps]):
                                st = self._ground(str(s.get("why") or s["verb"]), str(s["verb"]), i)
                                if st.kind == "verb" and not self._tied_to_request(goal, st):
                                    st = Step(i, str(s.get("why") or goal), None, "", [], "unknown", safety="unknown", need_human=True,
                                              note=f"the model suggested '{st.verb}' but nothing in its name or description ties it to the request -- not used")
                                steps.append(st)
                            rep.by = "rules+model"
            except Exception:
                steps = []
        if not steps:
            # the words alone matched a control only weakly: that is a COINCIDENCE of one shared word ('remove every marker' vs 'Add Marker'), not a plan - never forced onto the nearest control
            steps = []
            for st in rule_steps:
                if st.kind == "verb" and st.conf < 0.66:
                    steps.append(Step(st.index, st.goal, None, "", [], "unknown", safety="unknown", need_human=True,
                                      note=f"the closest control, '{st.verb}', explains only {st.conf:.0%} of the words of '{st.goal}' - not used (no guide, skill or model could ground this step)"))
                else:
                    steps.append(st)
        rep.steps = steps
        return rep

    # ---- doing
    def _frame_nodes(self) -> Optional[List[Any]]:
        """The frame's tree as the background reader last published it (see _TreeMirror). None means 'nothing published yet and a synchronous read is worth waiting for'; an empty list means
        'there is nothing to read in the frame right now' - measured on Word, whose frame is DISABLED while one of its dialogs owns the input: it cannot change and its read is the slowest call
        in the run, so the dialog's own tree (0.3 s) is the only honest source of what is on screen."""
        got = self.mirror.latest() if self.mirror is not None else None
        if got is not None:
            return got
        if not _frame_enabled(self.hwnd):
            return []
        return None

    MODAL_DOORS = ("cancel", "no", "not now", "never for now", "dismiss", "ok", "okay", "don't save", "no, thanks", "discard")

    def _clear_owning_dialog(self) -> str:
        """Answer a dialog that has TAKEN the window. Measured on Word: a 'Save your changes to this file?' backstage left the frame disabled (nothing on it can be pressed, its tree cannot
        change) and the run burned 22 s per read on a window that could not respond; a second close request then stacked 'You cannot close Microsoft Word because a dialog box is open'.
        A person reads the card and takes the door back out of the request. The dialogs answer in 0.3 s, so this costs almost nothing; the word on the button decides it (never the
        application's name), and only a door that backs out of the request is taken - the run's own throw-away document may lose edits, nothing of the person's is ever committed."""
        if _frame_enabled(self.hwnd) or not self.fx.allowed:
            return ""
        try:
            from core_organs import headless_input as hin
            pops = [p for p in hin.popup_windows(self.hwnd) if p != self.hwnd][:6]
        except Exception:                                                 # noqa: BLE001
            return ""
        for p in pops:
            nodes = _timed_snapshot(p, 5.0) or []
            if not nodes:
                continue
            buttons = [n for n in nodes if (getattr(n, "role", "") or "") in ("button", "menuitem") and str(getattr(n, "name", "") or "").strip()]
            named = {fold(str(getattr(b, "name", "") or "")): b for b in buttons}
            pick = None
            for door in self.MODAL_DOORS:
                for k, b in named.items():
                    if k == door or k.startswith(door + " "):
                        cls = safety.classify(str(b.name or ""))
                        if cls == "safe" or (cls == "commit" and self.owned):
                            pick = b
                            break
                if pick is not None:
                    break
            how = ""
            if pick is not None:
                ok, how = self.fx.node(pick)
                note = f"'{str(pick.name or '')[:30]}' pressed on the dialog that owned the window ({'delivered' if ok else how})"
            else:                                                          # no named door: Escape is the request's own undo, posted to the dialog (not to the frozen frame)
                from .effectors import Effector
                ok, how = Effector(p, allow_input=True, owned=self.owned).key("escape")
                note = f"the dialog that owned the window named no door: sent it Escape ({'delivered' if ok else how})"
            self.modal_log.append({"at": time.time(), "dialog": p, "did": note,
                                   "saw": [str(b.name or "")[:28] for b in buttons][:10]})
            time.sleep(1.0)
            return note
        return ""

    BACKING_OUT_DOORS = ("cancel", "no thanks", "no, thanks", "not now", "not today", "later", "maybe later", "skip", "skip for now",
                         "dismiss", "remind me later", "no maybe later", "i'll explore later", "not interested")

    def _eye_blocker(self, st: Step) -> Tuple[str, str]:
        """THE EYE ANSWERS 'WHAT IS HOLDING THIS UP'. The hand has already failed on this step; the PICTURE may say why: a card, an update notice, a
        consent panel, a tour drawn inside the application's own canvas owns no accessibility objects, so every route "finds no control" while the
        screen is plainly covered. One look per UNCHANGED screen (looking twice at the same picture costs 15 s and says the same thing), and the
        eye is honest even when it names no door - what it saw travels into the step, so the report explains the stall instead of reporting a miss.
        Only a door that backs OUT of the request is pressed, and only when the safety rules call it safe: the eye clears what was in front, it never
        decides for the person."""
        look = getattr(self, "look_here", None)
        if look is None or not self.fx.allowed:
            return "", ""
        try:
            s = self._snap()
            sig = s.sig if s is not None else ""
        except Exception:                                                # noqa: BLE001
            return "", ""
        if sig and getattr(self, "_eye_sig", "") == sig:
            return getattr(self, "_eye_said", ""), ""
        self._eye_sig = sig
        try:
            seen = list(look("standard") or [])
        except Exception:                                                # noqa: BLE001
            return "", ""
        named: List[str] = []
        for e in seen:
            lab = str(getattr(e, "label", "") or "").strip()
            role = str(getattr(e, "role", "") or "").strip().lower()
            if not lab:
                continue
            if BLOCKER_RX.search(lab + " " + role):
                named.append(f"{role or 'element'} '{lab[:44]}'")
            if fold(lab) not in self.BACKING_OUT_DOORS:
                continue
            node = next((n for n in self._all_nodes() if fold(str(getattr(n, "name", "") or "")) == fold(lab)
                         and str(getattr(n, "role", "") or "") in ("button", "menuitem", "hyperlink")
                         and safety.classify(str(getattr(n, "name", "") or "")) == "safe"), None)
            box = getattr(e, "bbox", None)
            how = ""
            if node is not None:
                ok, how = self.fx.node(node)
            elif box is not None and safety.classify(lab) == "safe" and getattr(box, "cx", 0) and getattr(box, "cy", 0):
                ok, how = self.fx.click_xy(int(box.cx), int(box.cy))
            else:
                continue
            if ok:
                self.eye_log.append({"at": time.time(), "saw": lab, "step": st.index + 1, "did": f"backed out of it: {how}"})
                return lab, f"the eye saw '{lab[:40]}' in front of the window and backed out of it ({how})"
        said = "; ".join(named[:6])
        self._eye_said = said
        if said:
            self.eye_log.append({"at": time.time(), "saw": said[:200], "step": st.index + 1, "did": ""})
        return said, ""

    def _all_nodes(self) -> List[Any]:
        """The window's tree PLUS the trees of its process's popups (an open menu, a flyout or a dialog is a separate top-level window that the main tree does not contain)."""
        from core_organs import fast_uia
        cached = self._frame_nodes()
        nodes = list(_timed_snapshot(self.hwnd, 12.0) or []) if cached is None else list(cached)
        # THE SCREEN HAS MOVED. A suite re-creates or re-parents its own main window (a start screen, a second document frame, a backstage) and leaves the handle the run owns as a shell of a
        # few nodes while the interface the guide describes lives on a SIBLING window of the same process (measured on Word: four procedures failed 'control not found in the live tree' against
        # a 7-node frame while 5119 verbs were catalogued). Neighbours are read ONLY when what we own is nearly empty - a full tree costs seconds and there is nothing to look for then.
        if len(nodes) < 60 and len(self.catalog.verbs) > 200:
            import ctypes as _ct
            fresh = (getattr(self, "_sib_nodes", None) and time.time() - getattr(self, "_sib_at", 0.0) < 20.0
                     and _ct.windll.user32.IsWindow(int(self.sibling or 0)))
            if not fresh and time.time() - getattr(self, "_sib_at", 0.0) > 15.0:
                self._sib_at = time.time()
                try:
                    import ctypes
                    from core_organs import headless_input as hin
                    pid = hin.window_pid(self.hwnd)
                    known = {int(self.hwnd)} | {int(w) for w in (getattr(self, "follow", []) or [])}
                    best, best_nodes = 0, []
                    for w in hin.process_windows(self.hwnd):
                        wh = int(w)
                        if wh in known or hin.window_pid(wh) != pid or not ctypes.windll.user32.IsWindowVisible(wh):
                            continue
                        got = _timed_snapshot(wh, max(6.0, min(45.0, _READ_COST.get(wh, 0.0) * 1.6))) or []
                        if len(got) > len(best_nodes):
                            best, best_nodes = wh, got
                    if len(best_nodes) > len(nodes):
                        self.sibling = best
                        self._sib_nodes = best_nodes
                        self.sibling_log.append({"at": round(time.time() - self._t_run, 1), "owned": self.hwnd, "owned_nodes": len(nodes),
                                                 "adopted": best, "adopted_nodes": len(best_nodes)})
                except Exception:                                        # noqa: BLE001
                    pass
            if fresh:
                nodes += fast_uia.rebased(list(self._sib_nodes or []), len(nodes))
        self._main_n = len(nodes)                                          # nodes[_main_n:] belong to pop-up windows (flyouts, dialogs)
        try:
            from .dialogs import light_popups
            now = time.time()
            for w in light_popups(self.hwnd):
                if _HUNG.get(w, 0.0) > now:
                    continue                                               # this window's provider hung recently: skipped for a while instead of freezing the whole run
                got = _timed_snapshot(w, 5.0)
                if got is None:
                    _HUNG[w] = now + 20.0
                    self.hung_windows = getattr(self, "hung_windows", 0) + 1
                # INDEX-ALIGNED: each window's snapshot numbers its own nodes from 0; a plain merge made a node's parent index land in ANOTHER window
                # (measured: a browser's controls filed under a Word toolbar, then saved as Word's own verbs). Copies keep the links inside their window.
                nodes += fast_uia.rebased(got or [], len(nodes))
        except Exception:
            pass
        # FOLLOW THE WINDOW THE APPLICATION JUST OPENED: a suite can host its online-content picker / preview in a helper PROCESS, so no same-process merge sees it, and the frame we own goes quiet
        # while the real interface lives there. Which windows qualify is measured, not known beforehand: they appeared after one of our steps (Delta.new_windows) and still exist.
        try:
            import ctypes
            for w in list(getattr(self, "follow", []) or []):
                try:
                    if not ctypes.windll.user32.IsWindow(w):
                        self.follow.remove(w)
                        continue
                except Exception:
                    continue
                got = _timed_snapshot(w, 5.0)                                      # same-process popups were merged above; a helper-process window was not
                if got:
                    nodes += fast_uia.rebased(got, len(nodes))
        except Exception:
            pass
        return nodes

    def _note_follow(self, d: Any) -> None:
        """Remember the windows a step opened, so the NEXT step can read them (a picker's search box is only useful once the picker is part of what we look at)."""
        for w in list(getattr(d, "new_windows", []) or []):
            if w != self.hwnd and w not in self.follow:
                self.follow.append(int(w))
        self.follow = self.follow[-4:]

    def _live_node(self, v: Verb) -> Any:
        nodes = self._all_nodes()
        if "menu-expand" in (v.sources or []):                           # an item read out of a flyout lives in the FLYOUT's window, never in the main window's gallery of the same name
            pops = nodes[self._main_n:]
            if not any(_nl(n.name) == _nl(v.label) for n in pops):          # ...or (Office) under the opener in the main tree, placed where the pop-up window is
                try:
                    from core_organs import headless_input as hin
                    from core_organs import background_window as bw
                    boxes = [bw._rect(w) for w in hin.popup_windows(self.hwnd)]
                except Exception:
                    boxes = []
                in_boxes = [n for n in nodes[: self._main_n] if any(b[0] - 4 <= n.rect[0] and b[1] - 4 <= n.rect[1] and n.rect[2] <= b[2] + 4 and n.rect[3] <= b[3] + 4 for b in boxes)]
                if in_boxes:
                    pops = pops + in_boxes
            if any(_nl(n.name) == _nl(v.label) for n in pops):
                nodes = pops
        ACTIVE = {"invoke", "toggle", "select", "expand", "value", "range", "scroll"}

        def best(cands):
            """A button and the text label inside it share a name: take the one that can be ACTED on (patterns), then the one whose control type matches the verb's role."""
            return min(cands, key=lambda n: (not (set(n.pats or []) & ACTIVE), n.role in ("text", "image", "pane", "group", "custom"), (n.role or "") not in (v.role or "", {"menu_item": "menuitem", "tab": "tabitem", "list_item": "listitem", "tree_item": "treeitem", "radio": "radiobutton", "field": "edit", "dropdown": "combobox"}.get(v.role, "")),
                                       n.idx)) if cands else None
        valid = lambda n: (n.rect[2] > n.rect[0] and n.rect[3] > n.rect[1]) or bool(set(getattr(n, "pats", []) or []) & ACTIVE)
        by_aid = [n for n in nodes if v.aid and n.aid == v.aid and not n.offscreen]
        if not by_aid:
            by_aid = [n for n in nodes if v.aid and n.aid == v.aid and valid(n)]
        if by_aid:
            return best(by_aid)
        by_lbl = [n for n in nodes if _nl(n.name) == _nl(v.label) and not n.offscreen]
        if not by_lbl:
            by_lbl = [n for n in nodes if _nl(n.name) == _nl(v.label) and valid(n)]
        return best(by_lbl)

    def refresh_catalog(self) -> int:
        """Add what is on screen NOW (including open menus / dialogs) to the catalog. Returns how many verbs were new."""
        from .harvest import harvest_tree
        try:
            fresh = harvest_tree(self.hwnd, self.app_key, nodes=self._all_nodes())
        except Exception:
            return 0
        have = {(tuple(v.path), fold(v.label)) for v in self.catalog.verbs}
        new = [v for v in fresh.verbs if (tuple(v.path), fold(v.label)) not in have]
        self.catalog.verbs += new
        return len(new)

    def _reground(self, st: Step) -> Optional[Step]:
        """A guide step that named a control which was not in the catalog when the plan was made (it lives in a menu / dialog that opens only after an earlier step): look again NOW."""
        from .knowledge import guide_steps as GS
        self.refresh_catalog()
        gs = GS.parse_line(st.goal, st.index + 1, st.cite)
        if gs is None:
            return None
        if st.target:                                                     # a sentence that named several fields produced several steps: each keeps ITS term
            gs.target = st.target
            gs.path = [p for p in gs.path if fold(p) == fold(st.target)] if len(gs.path) < 2 else gs.path
            if st.text:
                gs.text = st.text
        g = GS.ground_step(gs, self.catalog, GS.near_of(self._last_verb))
        if g.how in ("path", "label", "chord", "group") and g.verb is not None:
            txt = gs.text if (gs.action == "type" and gs.text) else ""
            if not txt and gs.action in ("type", "set") and (g.verb.role in FIELD_ROLES or g.verb.role == "field"):
                txt = self.placeholder_for(g.verb)                        # the manual says only 'enter a name': a neutral placeholder stands in
            ns = self._step_for_verb(g.verb, st.goal, g.conf, "guide", st.cite, gs.action if gs.action in ("on", "off") else "", txt)
            ns.index = st.index
            ns.note = "grounded just in time (the control appeared after an earlier step)" + (" - the manual gives no literal value: a neutral placeholder is entered" if txt == self.placeholder_for(g.verb) else "")
            return ns
        return None

    def placeholder_for(self, v: Verb) -> str:
        """What goes into a field when the manual says only 'enter a value': a number where the field is numeric (its range, when the application states one, or a size-like name), else a neutral string."""
        m = re.search(r"range (-?\d+)\.\.(-?\d+)", v.desc or "")
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            return str(min(max(100, lo), hi))
        if re.search(r"\b(width|height|size|number|count|percent|zoom|quantity|opacity|angle|degrees|pixels|amount|margin|spacing|radius|rows|columns|value)\b", fold(v.label)):
            return "100"
        return self.placeholder

    def _is_opener(self, v: Optional[Verb]) -> bool:
        """A verb whose activation opens a flyout (menu bar item, drop-down, split button): the foreground must stay with the application until the next step has used the flyout."""
        return bool(v is not None and (v.role in ("menu_item", "dropdown") or "menu" in (v.leads_to or "") or "submenu" in (v.leads_to or "")) and not v.command_id)

    def _hold_open(self) -> None:
        if self._sticky is None and self.fx.allowed:
            import contextlib
            self._sticky = contextlib.ExitStack()
            self._sticky.enter_context(self.fx.holding())

    def _hold_release(self) -> None:
        if self._sticky is not None:
            st, self._sticky = self._sticky, None
            try:
                st.close()
            except Exception:
                pass

    def _value_shown(self, v: Verb, text: str) -> bool:
        """Does an edit field belonging to this verb (its own node, or an Edit whose name starts with the verb's label - a spinner's 'Width: Minimum1 Maximum99999') already hold `text`?"""
        try:
            from .probe import _editable_value
            want, lab = text.strip(), fold(v.label)
            for n in self._all_nodes():
                if n.ctype in ("EditControl", "DocumentControl") and not n.offscreen and (fold(n.name) == lab or fold(n.name).startswith(lab) or lab.startswith(fold(n.name)) and fold(n.name)):
                    if (_editable_value(n) or "").strip() == want:
                        return True
        except Exception:
            pass
        return False

    def _open_items(self, nodes: Optional[List[Any]] = None) -> List[Any]:
        """What is OPEN right now: the pop-up windows' trees, plus the main-tree nodes that sit inside a pop-up window's rectangle (Office files a flyout's items under the opener in the
        MAIN window's tree, placed where the pop-up window is)."""
        nodes = nodes if nodes is not None else self._all_nodes()
        out = list(nodes[self._main_n:])
        try:
            from core_organs import headless_input as hin
            from core_organs import background_window as bw
            boxes = [bw._rect(w) for w in hin.popup_windows(self.hwnd)]
        except Exception:
            boxes = []
        if boxes:
            out += [n for n in nodes[: self._main_n] if n.rect[2] > n.rect[0] and any(b[0] - 4 <= n.rect[0] and b[1] - 4 <= n.rect[1] and n.rect[2] <= b[2] + 4 and n.rect[3] <= b[3] + 4 for b in boxes)]
        return out

    def _flyout_has(self, label: str) -> bool:
        """Is an item of that name present in a POP-UP window right now (a flyout that is already open)?"""
        nodes = self._all_nodes()
        if any(_nl(x.name) == _nl(label) and not x.offscreen and x.name for x in nodes[self._main_n:]):
            return True
        try:                                                                   # Office files a flyout's items under the opener in the MAIN window's tree, placed where the pop-up window is
            from core_organs import headless_input as hin
            from core_organs import background_window as bw
            boxes = [bw._rect(w) for w in hin.popup_windows(self.hwnd)]
        except Exception:
            boxes = []
        return any(_nl(x.name) == _nl(label) and x.name and not x.offscreen and any(b[0] - 4 <= x.rect[0] and b[1] - 4 <= x.rect[1] and x.rect[2] <= b[2] + 4 and x.rect[3] <= b[3] + 4 for b in boxes)
                   for x in nodes[: self._main_n])

    def _open_path(self, v: Verb) -> bool:
        """Open the menu / drop-down / tab chain a verb lives under, outermost first, so that its item exists in the live tree. A flyout that is already open is left alone (expanding it again
        toggles it shut); one that does not appear is collapsed and asked once more. Returns whether anything was opened."""
        from . import menus as MN
        opened = False
        chain = list(v.path) + [v.label]
        for i, name in enumerate(chain[:-1]):
            nxt = fold(chain[i + 1])
            if self._flyout_has(nxt):
                opened = True                                                  # already open (the previous step opened it and the foreground is held)
                continue
            nodes = self._all_nodes()
            unlaid = _UNLAID.get(self.hwnd, False)                            # a parked window whose content is not laid out: zero-size controls are real (patterns work)
            cand = [n for n in nodes if _nl(n.name) == _nl(name) and not n.offscreen and n.enabled and (n.rect[2] > n.rect[0] or unlaid or bool(set(getattr(n, "pats", []) or []) & {"expand", "invoke", "select"}))]
            if not cand:
                continue
            if i > 0 and len(cand) > 1:                                      # two openers may carry the same name ('More Options' of the Selection AND the Brushes group): take the one inside the group named before it
                grp = [n for n in nodes if fold(n.name) == fold(chain[i - 1]) and n.rect[2] > n.rect[0]]
                inside = [c for c in cand if any(g.rect[0] <= c.rect[0] and g.rect[1] <= c.rect[1] and c.rect[2] <= g.rect[2] and c.rect[3] <= g.rect[3] for g in grp)]
                cand = inside or cand
            cand = [c for c in cand if c.role in ("menuitem", "button", "splitbutton", "combobox", "tabitem", "listitem", "radiobutton") or "expand" in (c.pats or [])] or cand
            flyout = cand[0].role != "tabitem"
            for attempt in (1, 2):
                nudged = flyout and (attempt == 2 or self.activation_first)
                if nudged:
                    self._nudge_active()
                ok, how = MN._expand(self.fx, cand[0])
                opened = opened or ok
                end = time.time() + 2.5
                found = False
                while ok and time.time() < end:                                  # wait for the flyout's items to exist (Office files them under the opener in the MAIN window's tree)
                    time.sleep(0.25)
                    if self._flyout_has(nxt) or any(_nl(x.name) == _nl(nxt) and x.idx != cand[0].idx and not x.offscreen and (x.rect[2] > x.rect[0] or unlaid or bool(set(getattr(x, "pats", []) or []) & ACTIVE)) for x in self._all_nodes()):
                        found = True
                        break
                if found or not ok:
                    if nudged and attempt == 2 and found:
                        self._learn_activation()                                   # this application shows its flyouts only when it believes it is active: nudge first from now on
                    break
                MN.collapse(cand[0], deadline_s=1.0)                              # it never showed: it may have been toggled shut - close it properly and ask once more
                time.sleep(0.4)
        return opened

    def _nudge_active(self) -> None:
        """A parked application that never has the foreground may refuse to show a flyout or a dialog until it believes it is active (measured on Office: a ribbon drop-down's menu and an
        ExecuteMso dialog appear only after WM_ACTIVATEAPP). The message is POSTED to the owned window: the real foreground and keyboard focus stay with the person."""
        if not self.fx.allowed or not self.owned:
            return
        try:
            import ctypes
            ctypes.windll.user32.PostMessageW(self.hwnd, 0x001C, 1, 0)
            time.sleep(0.25)
        except Exception:
            pass

    def _expand_node(self, n0: Any) -> Tuple[bool, str]:
        """Expand an opener; when nothing opens, close it, nudge the application's activation and expand once more (and remember that this application needs the nudge)."""
        from . import menus as MN
        if self.activation_first:
            self._nudge_active()
        ok, how = MN._expand(self.fx, n0)
        if not ok or "expand" not in (n0.pats or []):
            return ok, how
        if self._expanded_now(n0, 2.5):                                          # its own state says it is open (a popup window alone does not: measured, a parked Office 'Pictures' opened an online picture dialog instead of its menu)
            return ok, how
        MN.collapse(n0, deadline_s=1.0)
        time.sleep(0.3)
        self._nudge_active()
        ok2, how2 = MN._expand(self.fx, n0)
        if ok2 and self._expanded_now(n0, 2.5):
            self._learn_activation()
            return ok2, how2 + " (after an activation message)"
        return ok2, how2

    from . import config as _CFG
    TRAITS_PATH = os.path.join(_CFG.DATA_DIR, "app_traits.json")

    @classmethod
    def _traits(cls) -> Dict[str, Any]:
        try:
            with open(cls.TRAITS_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _learn_activation(self) -> None:
        """Remember (per application, across runs) that its flyouts appear only after an activation message - measured, not configured."""
        self.activation_first = True
        try:
            t = self._traits()
            row = t.setdefault(self.app_key or "app", {})
            if not row.get("activation_first"):
                row["activation_first"] = True
                row["learnt"] = time.strftime("%Y-%m-%d %H:%M:%S")
                os.makedirs(os.path.dirname(self.TRAITS_PATH), exist_ok=True)
                with open(self.TRAITS_PATH, "w", encoding="utf-8") as fh:
                    json.dump(t, fh, indent=1)
        except Exception:
            pass

    def _dialog_expected(self, st: Step, v: Optional[Verb], rep: ExecReport) -> bool:
        """Should this step open a dialog? Its control says so (leads to a dialog / its live name ends in '...') or the manual's next step works inside a dialog."""
        if v is not None and "dialog" in (v.leads_to or ""):
            return True
        nxt = rep.steps[st.index + 1] if st.index + 1 < len(rep.steps) else None
        if nxt is not None and nxt.kind in ("dialog", "dialog_button"):
            return True
        try:
            n = self._live_node(v) if v is not None else None
            return bool(n is not None and re.search(r"(\.\.\.|…)\s*$", n.name or ""))
        except Exception:
            return False

    def _expanded_now(self, n0: Any, wait_s: float) -> bool:
        end = time.time() + wait_s
        while time.time() < end:
            time.sleep(0.25)
            nodes = self._all_nodes()
            live = next((x for x in nodes[: self._main_n or len(nodes)] if x.name == n0.name and x.role == n0.role and (x.aid == n0.aid) and not x.offscreen), None)
            if live is not None and getattr(live, "expand_state", -1) == 1:
                return True
            if live is None:
                return True                                                       # cannot tell (the tree changed): leave it as it is
        return False

    def _keymap_command(self, key: str) -> Optional[Tuple[str, Dict[str, Any], str]]:
        """The command the application's own keymap binds to this chord: asked of its scripting engine for its CURRENT state (mode, editor: Tab is 'toggle edit mode' in the 3D viewport and
        'edit group' in a node editor), else the one command the catalog's shortcuts bind it to. Only a safe command; one that opens a menu or starts an interactive transform is left to the
        posted key (it needs a choice / a gesture value). -> (command id, its properties, label) or None."""
        if self.script_bridge is None or not key:
            return None
        from .harvest import normalize_chord
        want = normalize_chord(key)
        if not want:
            return None
        cid, props = "", {}
        self._key_poll = True
        if hasattr(self.script_bridge, "key_resolve"):
            try:
                r = self.script_bridge.key_resolve(want)
            except Exception:                                                     # noqa: BLE001
                r = {}
            if r.get("ok"):
                if r.get("kind") != "command":
                    return None
                cid, props = str(r.get("id", "")), dict(r.get("props") or {})
                self._key_poll = r.get("poll", True)                               # False: bound here, but its precondition is not met now
        if not cid:
            hits = {v.aid for v in self.catalog.verbs if v.aid.startswith("script:") and not v.aid.startswith("script:rna:") and v.shortcut and normalize_chord(v.shortcut) == want}
            if len(hits) != 1:
                return None
            cid = next(iter(hits))[7:]
        v = next((x for x in self.catalog.verbs if x.aid == "script:" + cid), None)
        label = v.text_path if v is not None else cid
        if v is not None and (not v.enabled or v.safety != "safe"):
            return None
        if v is None and safety.classify(cid.replace(".", " ").replace("_", " ")) != "safe":
            return None
        if self.deny is not None and self.deny.search(label + " " + cid):
            return None
        return cid, props, label

    def _twins(self, aid: str, v: Any) -> List[str]:
        """Safe, enabled commands of the scripting engine with the same name as `v` (other editors' versions), the 3D viewport's / object's first, without duplicates."""
        label = fold(getattr(v, "label", "") or "")
        if not label:
            return []
        out: List[str] = []
        for x in (getattr(getattr(self, "catalog", None), "verbs", None) or []):
            a = str(getattr(x, "aid", ""))
            if a.startswith("script:") and not a.startswith("script:rna:") and fold(x.label) == label and a[7:] != aid and x.enabled and x.safety == "safe" and a[7:] not in out:
                out.append(a[7:])
        return sorted(out, key=lambda a: a.split(".")[0] not in ("view3d", "object", "mesh", "transform"))

    def _live_twin(self, aid: str, v: Optional[Verb] = None) -> str:
        """Several editors declare a command of the SAME name ('Select Box' of the Info editor, of the 3D viewport, of the node editor): when the chosen one cannot run in the
        application's current state and a namesake can, the namesake is the one the manual means. The engine's own poll() decides; unchanged when it cannot tell."""
        if not hasattr(self.script_bridge, "polls"):
            return aid
        label = fold(v.label) if v is not None else ""
        if not label:
            return aid
        twins = self._twins(aid, v)
        if not twins:
            return aid
        try:
            p = self.script_bridge.polls([aid] + twins[:40])
        except Exception:                                                         # noqa: BLE001
            return aid
        if p.get(aid, True):
            return aid
        return next((x for x in twins[:40] if p.get(x)), aid)

    def _script_command(self, aid: str, v: Optional[Verb] = None) -> Tuple[bool, str]:
        """A command of the application's own scripting engine. One that takes a FILE would open the application's own file browser (drawn inside its window, not a system dialog): it is given a file
        of the run's sandbox instead - a fixture of the type it asks for to read, the outbox to write - through the bridge, which refuses any other path."""
        aid = self._live_twin(aid, v)
        info = self.script_bridge.fileinfo(aid)
        if not info.get("path_props"):
            ok, how = self.script_bridge.execute(aid)
            if not ok and "precondition not met" in how and v is not None:
                for twin in self._twins(aid, v)[:40]:                             # a namesake of another editor: the engine refuses it unrun when it cannot run here either
                    if self.script_bridge.fileinfo(twin).get("path_props"):
                        continue
                    ok2, how2 = self.script_bridge.execute(twin)
                    if ok2:
                        return ok2, how2 + f" (the namesake of '{aid}' that can run here)"
            return ok, how
        sb = self.sandbox
        if sb is None:
            return False, f"scripting: {aid} needs a file and there is no sandbox folder to take it from"
        exts = [e for e in (info.get("exts") or []) if e]
        label = (v.label if v is not None else info.get("label", "")) or ""
        if info.get("direction") == "save":
            path = sb.save_target("hojaiga-output", exts)
            ok, how = self.script_bridge.execute_file(aid, path)
            return ok, how + (f" (wrote {os.path.basename(path)} into the sandbox)" if ok else "")
        if "blend" in exts or not exts:
            path = os.path.join(sb.inbox, "hojaiga-fixture.blend")                       # a document of the application's own kind: a copy of the current one
            okc, howc = self.script_bridge.save_copy(path)
            if not okc:
                return False, f"scripting: could not prepare a sandbox document ({howc})"
        else:
            path = sb.fixture(label, exts)
        ok, how = self.script_bridge.execute_file(aid, path)
        return ok, how + (f" (read {os.path.basename(path)} from the sandbox)" if ok else "")

    def _pointer_anchor(self) -> Optional[Tuple[int, int]]:
        """Where a BARE mouse-button step ('press LMB' after the cursor was aimed by the previous step) presses: the manual means 'where the pointer is'; the nearest honest anchor the run owns is
        the middle of the application's working surface (professor.gestures.surface_of: the largest canvas / free block, else the window itself)."""
        try:
            import ctypes
            import ctypes.wintypes as wt
            from .gestures import surface_of
            r = wt.RECT()
            ctypes.windll.user32.GetWindowRect(self.hwnd, ctypes.byref(r))
            surf, _how = surface_of(self._all_nodes(), (r.left, r.top, r.right, r.bottom))
            s = surf or (r.left, r.top, r.right, r.bottom)
            return ((s[0] + s[2]) // 2, (s[1] + s[3]) // 2) if s[2] > s[0] and s[3] > s[1] else None
        except Exception:
            return None

    def _deliver(self, v: Verb, r: Route) -> Tuple[bool, str]:
        if r.kind in ("control", "expand", "value") and v is not None and self._live_node(v) is None:
            got = self._search_to_reveal(v)                                       # the lazy interfaces (a settings list, a masked ribbon gallery) hide what a search finds: the app's own search is asked before the control is called missing
            if got is not None:
                node = got
                if r.kind == "value":
                    ok, how = self.fx.set_value(node, str(r.arg))
                else:
                    ok, how = self.fx.node(node)
                return ok, f"{how} (brought on screen by the application's own search)"
        if r.kind == "command":
            return self.fx.command(int(r.arg))
        if r.kind == "shortcut":
            return self.fx.key(str(r.arg))
        if r.kind == "click":
            return self.fx.click_xy(*r.arg)
        if r.kind == "adapter":
            if not self.fx.allowed:
                return False, "refused: " + self.fx.why_not()
            return self.adapter.act(v, str(r.arg or ""))
        if r.kind == "scripting":
            if not self.fx.allowed:
                return False, "refused: " + self.fx.why_not()
            self._script_effect = None
            if isinstance(r.arg, tuple):                                                     # a setting: (key[=choice], value)
                ok, how = self.script_bridge.apply_setting(str(r.arg[0]), str(r.arg[1] or ""))
                self._script_effect = {"changed": getattr(self.script_bridge, "last_changed", None), "how": how}
                return ok, how
            d0 = self.script_bridge.digest() if hasattr(self.script_bridge, "digest") else None
            ok, how = self._script_command(str(r.arg), v)
            d1 = self.script_bridge.digest() if (ok and d0 is not None) else None
            self._script_effect = {"changed": (d0 != d1) if (d0 is not None and d1 is not None) else None, "how": how}
            return ok, how
        if r.kind == "object_model":
            if not self.fx.allowed:
                return False, "refused: " + self.fx.why_not()
            ok, how = self.object_model.execute(str(r.arg))
            if not ok and v.path and not getattr(self, "_entering", False):
                entered = self._enter_context(v)                                # a command of a mode (Slide Master) is refused outside that mode: enter it and ask once more
                if entered:
                    ok, how = self.object_model.execute(str(r.arg))
                    how += f" (after: {entered})"
            return ok, how
        if r.kind == "expand":
            from . import menus as MN
            n0 = self._live_node(v)
            if n0 is None:
                return False, "control not found in the live tree" + self._searched_note(v)
            return self._expand_node(n0)
        node = self._live_node(v)
        if node is None and self._reveal_hidden_ui():                           # the application's own tool bar / ribbon / navigation pane is collapsed: shown, the control may be there
            end = time.time() + 3.0
            while node is None and time.time() < end:                           # the panel animates open: poll for the control a little
                node = self._live_node(v)
                if node is None:
                    time.sleep(0.4)
        path_needed = False
        if v.path:
            if node is None or node.rect[2] <= node.rect[0] or getattr(node, "offscreen", False):
                path_needed = True
            elif not self._flyout_has(fold(v.label)):
                nodes = self._all_nodes()
                for p_name in v.path:
                    p_cand = [n for n in nodes if _nl(n.name) == _nl(p_name) and not n.offscreen and n.enabled]
                    if p_cand and (p_cand[0].role in ("button", "menuitem", "splitbutton", "combobox") or "expand" in (getattr(p_cand[0], "pats", []) or [])):
                        if getattr(p_cand[0], "expand_state", "") != "expanded":
                            path_needed = True
                            break
        if path_needed and v.path:                                              # the control lives in a closed menu / drop-down (or unrendered drawer): open its path first (File > Page setup)
            with self.fx.holding():                                             # ...and use it before the foreground is handed back (that would close the flyout)
                opened = self._open_path(v)
                node = self._live_node(v) if opened else node
                entered = ""
                if node is None or node.rect[2] <= node.rect[0]:
                    entered = self._enter_context(v)                            # its tab is a contextual one (a mode): enter the mode, then open the path again
                    if entered:
                        opened = self._open_path(v) or opened
                        node = self._live_node(v)
                if node is None:
                    return False, "control not found in the live tree (menu path opened: " + str(bool(opened)) + ")" + (f"; {entered}" if entered else "") + self._searched_note(v)
                if r.kind == "value":
                    return self.fx.set_value(node, str(r.arg))
                return self.fx.node(node)
        if node is None and v.role == "tab" and not v.path:
            entered = self._enter_context(v)                                     # a contextual tab exists only inside its mode: enter the mode, then the tab is there
            node = self._live_node(v) if entered else None
        if node is None:
            return False, "control not found in the live tree" + self._searched_note(v)
        if r.kind == "value":
            return self.fx.set_value(node, str(r.arg))
        return self.fx.node(node)

    SAYS_RX = re.compile(r"(?i)\b(cannot|can'?t|can not|unable to|not able to|is not available|are not available|no (?:valid |active |objects? |selection\b)|requires?\b|needs?\b|must be|must (?:first|have)|is in use|invalid|failed|error|not found|nothing (?:selected|chosen|is selected)|first (?:select|create|insert|add|switch)|please (?:select|create|insert))\b")

    def _app_says(self) -> str:
        """The application's OWN words right now: short lines that appeared or changed in its text areas between the step's before/after snapshots and read like a refusal or a report
        ('Cannot link objects into the same scene'). A person reads these and creates what is missing first; the run does the same: the line rides along in the step's summary and AppRun's
        precondition machinery treats it as 'create/select X first'. Text areas only — a changed button label is not the application 'saying' something."""
        last = getattr(self, "_last", None)
        if not last or last[0] is None or last[1] is None:
            return ""
        s0, s1 = last[0], last[1]
        out: List[str] = []
        lines: List[str] = []
        t0, t1 = getattr(s0, "texts", None) or {}, getattr(s1, "texts", None) or {}   # a snapshot that carries no text areas says nothing; it must never take the step down (measured: AttributeError crash path)
        for k, v in t1.items():
            if k not in t0 or t0[k] != v:
                lines.append(str(v))
        for ln in lines:
            val = ln.split("=", 1)[1] if "=" in ln else ln
            val = re.sub(r"\[\d+\]$", "", val).strip()
            if 8 <= len(val) <= 120 and "\n" not in val and self.SAYS_RX.search(val):
                if val.lower() not in [x.lower() for x in out]:
                    out.append(val)
            if len(out) >= 2:
                break
        return "; ".join(out[:2])

    def _trigger_route(self, t: Any) -> Optional[Tuple[Any, Route]]:
        """(the catalog entry a trigger goes through, its route) - None when that entry or route no longer exists."""
        via = next((x for x in self.catalog.verbs if x.text_path == t.via), None)
        if via is None:
            return None
        r = next((r for r in self.routes_for(via) if r.label() == t.route), None)
        return (via, r) if r is not None else None

    def _trigger_candidates(self, v: Verb, done_labels: Sequence[str]) -> List[Tuple[Any, Route]]:
        """Other ways in to the SAME command: entries of the catalog with the same name (another tab / menu / panel) or the same command id, and their routes that were not tried yet.
        Never a context-menu entry, never a command that is not 'safe' / 'commit'."""
        from .triggers import ALLOWED_SAFETY
        name = fold(v.label)
        twins = [x for x in self.catalog.verbs if x.id != v.id and x.enabled and x.safety in ALLOWED_SAFETY and not (x.path and str(x.path[0]).startswith("Context menu"))
                 and (fold(x.label) == name or (v.aid and x.aid == v.aid))]
        twins.sort(key=lambda x: (not (set(x.sources or []) - {"vendor-manifest"}), len(x.path)))
        out: List[Tuple[Any, Route]] = []
        seen = set(done_labels)
        for x in twins[:6]:
            for r in self.routes_for(x):
                if r.kind == "value":
                    continue
                same_command = r.kind in ("object_model", "scripting", "shortcut", "command")      # these name the COMMAND: the same label is the same thing already tried
                key = r.label() if same_command else f"{x.id}|{r.label()}"                       # a control / click route is a PLACE: the same name elsewhere is another way in
                if key in seen:
                    continue
                seen.add(key)
                out.append((x, r))
        return out[:6]

    def trigger_attempt(self, v: Verb, why: str = "") -> Optional[Tuple[Any, Route, bool, str]]:
        """For a caller that verifies the effect itself (the deep scan): an existing trigger of this control, else the first other way in to the same command that DELIVERS.
        -> (via, route, ok, how) or None when none may / can be tried. The caller creates the trigger only when it saw the effect."""
        if self.triggers is None:
            return None
        t = self.triggers.get(v)
        if t is not None:
            tp = self._trigger_route(t)
            if tp is not None:
                ok, how = self._deliver(tp[0], tp[1])
                self.triggers.record(t, ok)
                return (tp[0], tp[1], ok, how) if ok else None
        cv = next((x for x in self.catalog.verbs if fold(x.label) == fold(v.label) and [fold(p) for p in x.path] == [fold(p) for p in v.path]), v)
        if self.triggers.may_create(cv):
            return None
        for via, r in self._trigger_candidates(cv, []):
            ok, how = self._deliver(via, r)
            if ok:
                return via, r, ok, how
            if how.startswith("refused"):
                return None
        return None

    def _make_trigger(self, st: Step, v: Verb, label: str, routes: Sequence[Route], tried: List[str], settle_s: float) -> Optional[StepResult]:
        """Every ordinary route of a guide step failed: try the other ways in to the same command once; the first with a SEEN effect becomes a trigger (TriggerBank caps and retires them)."""
        from .probe import delta
        why_not = self.triggers.may_create(v)
        if why_not:
            tried.append(f"trigger: none created ({why_not})")
            return None
        cands = self._trigger_candidates(v, [x.label() for x in routes if x.kind in ("object_model", "scripting", "shortcut", "command")])
        if not cands:
            tried.append("trigger: no other way in to the same command is catalogued")
        for via, r in cands:
            s0 = self._snap()
            ok, how = self._deliver(via, r)
            tried.append(f"trigger? {via.text_path} {r.label()} -> {how}")
            if not ok:
                if how.startswith("refused"):
                    return None
                continue
            s1 = self._settle(s0, settle_s)
            d = delta(s0, s1)
            if d.effect() == "no_effect" and r.kind != "scripting":
                continue
            self._last = (s0, s1, d)
            t = self.triggers.create(v, via, r.label(), f"all {len(routes)} ordinary route(s) of '{v.text_path}' failed; '{via.text_path}' through {r.kind} worked")
            return StepResult(st.index, label, "done", route=f"trigger:{r.label()}", tried=tried, effect=d.effect() if d.effect() != "no_effect" else "state_change",
                              summary=f"trigger created for '{v.label}' -> {t.via} ({r.kind}); " + d.summary())
        return None

    REVEAL_RX = re.compile(r"(?i)^(show|expand|open|restore|unhide)\s+(the\s+)?(tool\s?bar|ribbon|tool\s?box|tools( panel)?|tool panel|navigation( pane| menu| bar)?|nav pane|side\s?bar|menu bar|commands|panel)\s*$")

    def _reveal_hidden_ui(self) -> str:
        """A control the catalog knows is not on screen because the application's own chrome is COLLAPSED (Paint's 'Show toolbar', an Office 'Expand ribbon', a narrow window's 'Open
        Navigation'): the application's own reveal control is used - once per name in a run - and its name returned; '' when there is none."""
        done = getattr(self, "_revealed", None)
        if done is None:
            done = self._revealed = {}
        log = getattr(self, "revealed_log", None)
        if log is None:
            log = self.revealed_log = []
        try:
            nodes = self._all_nodes()
        except Exception:                                                         # noqa: BLE001
            return ""
        for n in nodes:
            name = (getattr(n, "name", "") or "").strip()
            if not name or done.get(name.lower(), 0) >= 4 or not self.REVEAL_RX.match(name) or not getattr(n, "enabled", True) or getattr(n, "offscreen", False):
                continue
            if getattr(n, "role", "") not in ("button", "toggle", "menuitem", "splitbutton", "checkbox", "tabitem"):
                continue
            done[name.lower()] = done.get(name.lower(), 0) + 1                   # an application may collapse it again (a relaunch restores the person's preference): a few times per run
            ok, _how = self.fx.node(n)
            if ok:
                if name not in log:
                    log.append(name)                                              # the run puts it back as it found it at the end (AppRun.unreveal_ui)
                time.sleep(0.8)
                return name
        return ""

    SEARCH_RX = re.compile(r"(?i)\bsearch\b")
    FIELD_ROLES = ("edit", "document", "combo", "combobox", "dropdown", "search", "text", "spinbutton", "field", "text_field")   # 'field' / 'text_field' are the harvester's names for an edit (the module FIELD_ROLES above): a catalogued search box must not be rejected for its role name

    def _search_to_reveal(self, v: Verb):
        """The application's OWN search used to FIND a control: a lazy list (a settings page builds only the rows in view), a masked gallery (Office hides every ribbon command until its name
        is searched) hold controls the catalog knows but the live tree does not show. The search field is asked for the control's name and the tree is re-read - the same way a person uses
        'Search Settings'. Returns the revealed node, or None; tried once per control in a run, and never when the control is already on screen. WHY it did not search is recorded per control
        (`_search_whys`): the failed step says so instead of failing silently."""
        tried = getattr(self, "_searched", None)
        if getattr(self, "_in_searchnav", False):
            return None                                                                # opening the expander must not start another search (the hand is already busy with this one)
        if tried is None:
            tried = self._searched = {}
        whys = getattr(self, "_search_whys", None)
        if whys is None:
            whys = self._search_whys = {}
        key = fold(v.label or "")
        if not key:
            return None
        if tried.get(key, 0) >= 2:
            return None
        tried[key] = tried.get(key, 0) + 1
        cands = [c for c in self.catalog.verbs
                 if c.enabled and self.SEARCH_RX.search(c.label or "")
                 and ((c.role or "").lower() in self.FIELD_ROLES or "search" in " ".join(c.path).lower()
                      or (c.role or "").lower() in ("button", "dropdown"))]     # a field named search, a control filed under a search path, or a button that OPENS one ('Expand search box')
        # THE BOX MUST BE THIS WINDOW'S OWN. A catalog can carry a control of ANOTHER application's window (an embedded pane read on an earlier build, saved, reused on the next): measured on
        # Word, where a browser's 'Address and search bar' outranked Word's own box, and the run "typed" Home into a field that does not exist in Word. So the field is chosen from the
        # candidates that answer IN THE LIVE TREE of the process we drive - the same test a person uses before typing into a box.
        try:
            from core_organs import headless_input as hin
            own_pid = int(hin.window_pid(self.hwnd) or 0)
        except Exception:                                                # noqa: BLE001
            own_pid = 0
        skipped: List[str] = []

        def ours(n: Any) -> bool:
            pid = int(getattr(n, "pid", 0) or 0) if n is not None else 0
            return n is not None and (not own_pid or not pid or pid == own_pid)
        fields = [c for c in cands if (c.role or "").lower() in self.FIELD_ROLES]
        field, fnode = None, None
        for c in fields[:6] + [c for c in cands if c not in fields][:4]:      # a real box beats a button that only opens one, whatever the catalog order
            n = self._live_node(c)
            if ours(n):
                field, fnode = c, n
                break
            if n is not None:
                skipped.append(str(c.label or "")[:28])                     # it answered, but from another process's window
            elif field is None and c in fields:
                field = c                                                   # nothing live yet: keep the best catalogued box for the expander route below
        if field is None:
            field = (fields or cands or [None])[0]
        if field is None:
            whys[key] = "this application has no search control catalogued"
            return None
        # A modern interface often SHOWS ONLY AN EXPANDER and builds the real box when it is pressed (a collapsed search field is a button until a person clicks it). So the box is asked for once;
        # if the live window has no box but does have the expander, the EXPANDER is pressed and the box is asked for again. Which control plays which part is read from the live tree and the catalogued
        # words - never from an application's name.
        opener = next((c for c in cands if c is not field and (c.role or "").lower() in ("button", "dropdown", "splitbutton")), None)
        fnode = fnode if fnode is not None else self._live_node(field)
        if fnode is None and opener is not None and self.fx.allowed:
            self._open_quiet(opener)
            whys["__opener__"] = str(opener.label or "")[:30]                  # remembered: the note can say the collapsed box was expanded first
            time.sleep(0.6)
            fnode = self._live_node(field) or self._search_field_node()
        if fnode is None and self.fx.allowed:                                    # the field itself may be a button that OPENS a search (a palette): invoke it, then the focused field takes the typed words
            self._open_quiet(field)
            fnode = self._live_node(field)
        if fnode is None:                                                        # the lazy interface never catalogued its search box: ask the LIVE tree for one on screen right now
            fnode = self._search_field_node()
        q = (v.label or "").strip()
        if len(q) < 3:
            whys[key] = f"search box '{field.label}' found but the name '{q}' is too short to ask for"
            return None
        base = {fold(str(getattr(m, "name", "") or "")) for m in self._all_nodes()}      # the window's names BEFORE the words: a result list is recognised as names that were not there
        words = [w for w in re.findall(r"[a-z0-9&]+", q.lower()) if len(w) >= 4]
        try:
            if fnode is not None:
                ok, _how = self.fx.set_value(fnode, q)
                if getattr(fnode, "rect", (0, 0, 0, 0))[2] > fnode.rect[0] and self.fx.allowed:
                    l, t, r, b = fnode.rect                                      # keystrokes as well: some toolkits answer SetValue but wait for typing to start the search (a WinUI palette, a collapsed box)
                    self.fx.click_xy((l + r) // 2, (t + b) // 2)
            else:
                ok, _how = self.fx.node(field)                                   # a 'Search' button: pressing it focuses the palette / field
            if not ok:
                whys[key] = f"the search control '{field.label}' would not take the words '{q}'"
                return None
            time.sleep(0.5)
            self.fx.insert_text(q, deadline_s=2.0)                               # where the caret landed (the opened field) takes the words too - some toolkits answer typing but not SetValue
        except Exception as exc:                                                 # noqa: BLE001
            whys[key] = f"searching for '{q}' raised {type(exc).__name__}"
            return None
        end = time.time() + float(os.environ.get("HOJAIGA_SEARCH_WAIT", "4.0"))
        grew = 0
        while time.time() < end:
            n = self._live_node(v)
            if n is not None and (n.rect[2] > n.rect[0]):
                whys[key] = f"searched '{q}': it appeared"
                return n
            now = self._all_nodes()
            hits = [m for m in now if (q.lower() in (getattr(m, "name", "") or "").lower()
                                       or (words and sum(1 for w in words if w in (getattr(m, "name", "") or "").lower()) >= max(2, len(words))))
                    and not getattr(m, "offscreen", False)]
            if hits:
                whys[key] = f"searched '{q}': it appeared"
                return hits[0]
            fresh = [m for m in now if fold(str(getattr(m, "name", "") or "")) and fold(str(getattr(m, "name", "") or "")) not in base]
            grew = max(grew, len(fresh))
            time.sleep(0.4)
        opener_note = f" (its expander '{whys.get('__opener__', '')}' was pressed first)" if whys.get("__opener__") else ""
        foreign_note = f" (skipped {'; '.join(skipped[:3])}: that box belongs to another application's window, not this one)" if skipped else ""
        whys[key] = (f"asked the search ('{field.label}') for '{q}'{opener_note}{foreign_note} and typed it: nothing that reads like it appeared"
                     + (f" - the search did change the tree ({grew} new names), none of them matching" if grew else " - and the tree did not change at all (the words likely never reached the box)"))
        return None

    def _open_quiet(self, c: Verb) -> None:
        """Press a control that only OPENS something (a collapsed search box, a palette) without letting the reveal machinery re-enter itself: the hand is already busy with this search."""
        self._in_searchnav = True
        try:
            self._deliver(c, Route("control", "search-open", 9))
        except Exception:                                                        # noqa: BLE001
            pass
        finally:
            self._in_searchnav = False

    def _search_field_node(self):
        """A search / find field present in the LIVE tree right now but never catalogued (a lazy interface builds its home page differently each run): an on-screen edit / combo whose name,
        help or automation id says 'search' or 'find'. The application's own search, found the way a person finds it - by looking at the window."""
        for n in self._all_nodes():
            try:
                if getattr(n, "offscreen", False) or getattr(n, "rect", (0, 0, 0, 0))[2] <= n.rect[0]:
                    continue
                words = " ".join(str(getattr(n, k, "") or "") for k in ("name", "help", "aid"))
                role = (str(getattr(n, "role", "") or "") or str(getattr(n, "ctype", "") or "")).lower()
                if (role in self.FIELD_ROLES or "edit" in role or "combo" in role or "search" in role) and re.search(r"(?i)\b(search|find)\b", words):
                    return n
            except Exception:                                                        # noqa: BLE001
                continue
        return None

    def _searched_note(self, v: Verb) -> str:
        """Why the application's own search did NOT bring this control on screen (recorded by `_search_to_reveal`), or '' when it was never in a position to try: a silent search is a mystery to everyone but the one who ran it."""
        why = getattr(self, "_search_whys", {}).get(fold(v.label or "")) if v is not None else None
        return f"; the app's own search: {why}" if why else ""

    def _book(self) -> Dict[str, str]:
        """The guidebook library of this application, read ONCE per run: control label -> the route that finished the step last time.
        data/professor/workflows/<app>.md|.json is THE BOOK WITH ITS HISTORY - every procedure of the vendor guide plus the result of the last run that attempted it. The file is downloaded and
        written alongside runs, so a step that finds itself stuck is not the first time anyone has met that paragraph."""
        if getattr(self, "_book_map", None) is not None:
            return self._book_map
        seen: Dict[str, str] = {}
        try:
            from . import workflows as WF
            for w in (WF.load(self.app_key) or {}).get("workflows", []):
                if (w.get("last_run") or {}).get("result") != "ok":               # only a precedent that actually finished
                    continue
                for s in w.get("steps", []):
                    k = fold(str(s.get("verb") or s.get("target") or ""))
                    if k and str(s.get("route") or "") and k not in seen:
                        seen[k] = s["route"]
        except Exception:                                                        # noqa: BLE001
            pass
        self._book_map = seen
        return seen

    def _book_prefer(self, st: Step, v: Any) -> str:
        """MID-RUN REFERENCE TO THE BOOK: which way of delivering this control has already worked HERE. Two sources, in order of honesty - the run's own state-transition log (what this
        application actually answered), then the guide library (what an earlier finished procedure recorded). '' means the book has nothing to say and ordinary routing / the learnt order
        applies. Nothing is invented and nothing is hardcoded per application: it is a lookup of the target's own words."""
        want = fold(str(st.verb or (v.label if v is not None else "") or ""))
        if not want:
            return ""
        if self.history is not None:
            try:
                got = self.history.best_route(self.app_key, st.verb or (v.label if v is not None else ""))
                if got:
                    return str(got)
            except Exception:                                                    # noqa: BLE001
                pass
        return self._book().get(want, "")

    def _already(self, v: Verb, want: str) -> bool:
        """A toggle that already is in the wanted state needs no click (a check box asked to be 'on' must never be switched off)."""
        try:
            n = self._live_node(v)
        except Exception:
            return False
        if n is None:
            return False
        state = getattr(n, "toggle_state", -1)
        if state in (0, 1):
            return (state == 1) == (want == "on")
        sel = getattr(n, "selected", None)
        if sel is not None:
            return bool(sel) == (want == "on")
        return False

    def run(self, rep: ExecReport, dry_run: bool = True, approve: Optional[Callable[[Step], bool]] = None, settle_s: float = 2.5, learn: bool = True) -> ExecReport:
        """Perform the plan. Nothing is sent when dry_run (or the effector is closed). A step that needs a human stops the plan unless `approve(step)` says yes."""
        if dry_run or not self.fx.allowed:
            return self._run(rep, dry_run, approve, settle_s)
        import contextlib
        with (self.learner.training() if self.learner is not None else contextlib.nullcontext()), self.fx.focus_watch():
            self._run(rep, dry_run, approve, settle_s)
        self._learn(rep, learn)
        try:                                                     # report what was attempted to the federated RAG (routes learn reliability); never raises, off with HOJAIGA_RAG=off
            from core_organs.rag import hooks as _rag_hooks
            _rag_hooks.observe_report(self.app_key, rep)
        except Exception:
            pass
        return rep

    def _run(self, rep: ExecReport, dry_run: bool, approve: Optional[Callable[[Step], bool]], settle_s: float) -> ExecReport:
        try:
            return self._run_inner(rep, dry_run, approve, settle_s)
        finally:
            self._hold_release()

    def _run_inner(self, rep: ExecReport, dry_run: bool, approve: Optional[Callable[[Step], bool]], settle_s: float) -> ExecReport:
        from .probe import snapshot, delta
        t_start = time.time()
        rep.dry_run = dry_run or not self.fx.allowed
        rep.results = []
        rep.stopped = ""
        self._file_followups = 0                                                  # what a file dialog of an EARLIER plan satisfied does not carry over
        for si, st in enumerate(list(rep.steps)):
            t0 = time.time()
            # THE EYE BEFORE THE HAND: a modal dialog of this application DISABLES the frame (measured on Word - the frame answers 174 nodes
            # after 22 s while its 'Save your changes?' dialog answers 31 nodes in 0.3 s). While a dialog owns the window no route can possibly
            # work, so the dialog is answered first and what answered it is written into the step, not left as a silent stall.
            modal_note = self._clear_owning_dialog()
            if modal_note and self.on_step is not None:
                try:
                    self.on_step("modal", st, modal_note)
                except Exception:
                    pass
            if st.kind == "dialog" and not rep.dry_run and self.dialogs is not None and not self.dialogs.pending() and self._file_followups <= 0:
                alt = self._dialog_step_as_control(st)                            # 'Select **Save as**' / 'click **Audio**': no dialog is open yet - the named control is what opens it
                if alt is not None:
                    rep.steps[si] = st = alt
            if self.dialogs is not None and not rep.dry_run:
                if si > 0 and not self._is_file_step(st):
                    self._auto_dialogs(rep)                                       # a dialog the previous step opened (a message box, a print dialog, a file chooser) is dealt with before this step looks at the screen
                if self._is_file_step(st):
                    dres = self._file_step(st)
                    if dres is not None:
                        rep.results.append(dres)
                        if dres.status != "done":
                            rep.stopped = f"step {st.index + 1} ('{dres.verb}'): {dres.summary}"
                            break
                        continue
            if st.kind == "unknown" and st.source == "guide" and not rep.dry_run and st.goal:
                fresh = self._reground(st)
                if fresh is not None:
                    rep.steps[si] = st = fresh
            label = st.verb or st.text or st.goal
            self._last = None
            if self.on_step is not None:
                try:
                    self.on_step("before", st, None)
                except Exception:
                    pass
            if self.supervisor is not None and not rep.dry_run and st.kind not in ("skip", "unknown"):
                go, why = self.supervisor.allow(st)
                if not go and not (approve and approve(st)):
                    rep.results.append(StepResult(st.index, label, "needs_human", summary=f"supervision: {why}"))
                    rep.stopped = f"step {st.index + 1} ('{label}') waits for a human yes - {why}"
                    break
            if st.kind == "gesture" and not rep.dry_run:
                res = self._gesture_step(st)
                rep.results.append(res)
                self._after_step(st, res)
                if res.status != "done":
                    rep.stopped = f"step {st.index + 1} (a {st.text} gesture): {res.summary[:160]}"
                    break
                continue
            if st.kind in ("dialog_button", "choice") and not rep.dry_run:
                if st.need_human and not (approve and approve(st)):
                    rep.results.append(StepResult(st.index, label, "needs_human", summary=f"'{label}' is {st.safety}; waiting for a human yes"))
                    rep.stopped = f"step {st.index + 1} ('{label}') needs a human yes ({st.safety})"
                    break
                res = self._dialog_or_choice(st, settle_s)
                rep.results.append(res)
                self._after_step(st, res)
                if res.status != "done":
                    rep.stopped = f"step {st.index + 1} ('{label}'): {res.summary[:120]}"
                    break
                continue
            if st.kind == "skip":
                rep.results.append(StepResult(st.index, label, "done", route="skipped", effect="optional", summary=st.note, ms=0))
                continue
            if st.kind == "object" and not rep.dry_run:
                res = self._select_object(st, settle_s)
                rep.results.append(res)
                self._after_step(st, res)
                if res.status != "done":
                    rep.stopped = f"step {st.index + 1} ('{label}'): {res.summary[:120]}"
                    break
                continue
            if st.kind == "object":
                rep.results.append(StepResult(st.index, label, "dry_run", route="object model", summary=st.note))
                continue
            if st.kind == "unknown":
                rep.results.append(StepResult(st.index, label, "unknown", summary=st.note))
                rep.stopped = f"step {st.index + 1} cannot be grounded in the application's own commands"
                break
            if st.need_human and not (approve and approve(st)):
                rep.results.append(StepResult(st.index, label, "needs_human", summary=f"'{label}' is {st.safety}; waiting for a human yes"))
                rep.stopped = f"step {st.index + 1} ('{label}') needs a human yes ({st.safety})"
                break
            if rep.dry_run:
                why = "" if dry_run else self.fx.why_not()
                rep.results.append(StepResult(st.index, label, "dry_run", route=(st.routes or ["-"])[0], tried=[], summary=("would send " + (st.routes[0] if st.routes else "nothing")) + (f" (input closed: {why})" if why else "")))
                continue
            if st.kind in ("text", "key"):
                if st.kind == "text":
                    ways = [("text:posted", lambda: self.fx.text(st.text)), ("text:uia", lambda: self.fx.insert_text(st.text))]
                    if self.object_model is not None and self.fx.allowed:
                        ways.append(("text:object-model", lambda: self.object_model.type_text(st.text)))          # the reroute: the document's own text API
                else:
                    mw = MOUSE_KEY_WORDS.get(re.sub(r"[^a-z]", "", (st.text or "").lower()))
                    anchor = self._pointer_anchor() if mw else None
                    if mw and anchor is not None:                                   # the step's 'key' is a mouse button: there is no such keyboard key; the virtual mouse presses it on the working surface
                        ways = [(f"mouse:{st.text}", lambda b=mw[0], c=mw[1], p=anchor: self.fx.click_xy(p[0], p[1], button=b, count=c))]
                    else:
                        ways = [(f"key:{st.text}", lambda: self.fx.key(st.text))]
                        alt = KEY_AS_TEXT.get(st.text)
                        if alt:
                            ways.append(("text:uia", lambda: self.fx.insert_text(alt)))
                        if self.object_model is not None and self.fx.allowed and st.text.lower().replace(" ", "") in ("delete", "del", "backspace", "ctrl+a", "enter", "return"):
                            ways.append((f"key:object-model", lambda: self.object_model.key_equivalent(st.text)))      # the reroute: a posted key that never reaches the document pane
                        bound = self._keymap_command(st.text)
                        if bound is not None:                                     # the reroute: the command the application's OWN keymap binds to this chord, run by its scripting engine
                            sway = (f"key:scripting {bound[0]}", lambda b=bound: (self.script_bridge.execute(b[0], b[1]) if b[1] else self._script_command(b[0])) if self.fx.allowed else (False, "refused: " + self.fx.why_not()))
                            first_ok = getattr(self, "blind", False) and getattr(self, "_key_poll", True) is not False
                            ways.insert(0 if first_ok else len(ways), sway)        # a blind window: the posted key cannot be confirmed, the command can
                tried_t: List[str] = []
                status, effect, summary, route_used = "no_effect", "", "", ""
                for rname, fn in ways:
                    s0 = self._snap()
                    ok, how = fn()
                    tried_t.append(f"{rname} -> {how}")
                    if not ok:
                        status, summary = ("refused" if how.startswith("refused") else "no_effect"), how
                        if status == "refused":
                            break
                        continue
                    s1 = self._settle(s0, settle_s)
                    d = delta(s0, s1)
                    self._last = (s0, s1, d)
                    self._log_text_attempt(st, rname, how, s0, s1, d)
                    effect, summary, route_used = d.effect(), how + "; " + d.summary(), rname
                    if effect != "no_effect":
                        status = "done"
                        break
                    if rname.startswith("key:scripting"):
                        status, effect = "done", "state_change"
                        summary = how + " (the application itself reported the command bound to the chord finished)"
                        break
                    status = "no_effect"
                if status == "no_effect" and st.kind == "key" and st.text in SOFT_KEYS and route_used:
                    status = "done"                                       # a movement / dismiss key may legitimately change nothing that is visible
                    summary += " (key delivered; nothing visible was expected to change)"
                elif status == "no_effect" and st.kind == "key" and route_used:
                    try:
                        from . import verify as _VF
                        exp_k = st.expect or _VF.expectation_for(st, v)
                        exp_ok, exp_why = _VF.check(exp_k, s0, s1, d, self._all_nodes())
                        if exp_ok is True:
                            status, effect = "done", "already_satisfied"
                            summary += f" ({exp_why})"
                    except Exception:
                        pass
                rep.results.append(StepResult(st.index, label, status, route=route_used or (ways[0][0]), tried=tried_t, effect=effect, summary=summary, ms=int((time.time() - t0) * 1000)))
                self._after_step(st, rep.results[-1])
                if status != "done":
                    pre = next((t.split("precondition not met", 1)[1][:120] for t in tried_t if "precondition not met" in t), None)
                    rep.stopped = f"step {st.index + 1}: {'typing' if st.kind == 'text' else 'the ' + st.text + ' key'} had no visible effect" + (f" (its command's precondition not met{pre})" if pre is not None else "")
                    break
                continue
            v = next((x for x in self.catalog.verbs if st.verb_id and x.id == st.verb_id), None) or self.resolve(st.verb or st.goal)

            if v is not None and st.want and self._already(v, st.want):
                rep.results.append(StepResult(st.index, label, "done", route="already", effect="already", summary=f"already {st.want}; nothing to do", ms=int((time.time() - t0) * 1000)))
                continue
            if v is not None and st.text and (v.role in FIELD_ROLES or v.role == "field") and not rep.dry_run:
                if self._value_shown(v, st.text):                               # a field that already shows the wanted value needs no write (the test value can equal what the application derived itself)
                    rep.results.append(StepResult(st.index, label, "done", route="already", effect="already", summary=f"the field already shows '{st.text}'; nothing to do", ms=int((time.time() - t0) * 1000)))
                    continue
            live0 = None
            if v is not None and not rep.dry_run:
                try:
                    live0 = self._live_node(v)
                except Exception:
                    live0 = None
            if (live0 is not None and not rep.dry_run and not st.want and live0.selected is True and "toggle" not in (live0.pats or [])
                    and live0.role in ("listitem", "radiobutton", "tabitem", "treeitem", "button")):
                rep.results.append(StepResult(st.index, label, "done", route="already", effect="already", summary=f"'{label}' is already the selected one; nothing to do",
                                              ms=int((time.time() - t0) * 1000)))
                self._after_step(st, rep.results[-1])
                continue                                                           # choosing what is already chosen changes nothing - and is exactly what the guide asked for
            if (v is not None and not rep.dry_run and not st.want and (live0 is None or not getattr(live0, "selected", False))):
                lbl_f = fold(v.label)
                for an in self._all_nodes():
                    an_f = fold(getattr(an, "name", "") or "")
                    if (an_f == f"colour 1: {lbl_f}" or an_f == f"color 1: {lbl_f}" or an_f == f"colour 2: {lbl_f}" or an_f == f"color 2: {lbl_f}") and getattr(an, "role", "") in ("button", "splitbutton", "listitem", "radiobutton"):
                        rep.results.append(StepResult(st.index, label, "done", route="already", effect="already", summary=f"'{an.name}' is already the active color; nothing to do",
                                                      ms=int((time.time() - t0) * 1000)))
                        self._after_step(st, rep.results[-1])
                        live0 = None
                        break
                if live0 is None and rep.results and rep.results[-1].effect == "already":
                    continue
            if live0 is not None and not live0.enabled and not rep.dry_run:
                rep.results.append(StepResult(st.index, label, "disabled", summary=f"'{label}' is disabled in the application's current state: the guide assumes something done before it (a selection, an open document, a signed-in account)",
                                              ms=int((time.time() - t0) * 1000)))
                rep.stopped = f"step {st.index + 1} ('{label}'): disabled - a precondition the guide implies is not met"
                break
            if v is not None and not rep.dry_run and (self._is_opener(v) or (live0 is not None and "expand" in (live0.pats or []))):
                self._hold_open()                                                  # opening a flyout: keep the foreground for THIS step and the NEXT one (the item inside it)
                self._sticky_left = 2                                                  # opening a menu: keep the foreground until the next step used it (a flyout closes when its window loses activation)
            if self.clip is not None and v is not None and not rep.dry_run:
                ck = f"{v.label} {v.shortcut}"
                if COPY_RX.search(ck):
                    self.clip.begin()                                                  # the person's clipboard is saved BEFORE the application overwrites it
                elif PASTE_RX.search(ck):
                    cnote = self._prepare_paste(st, v)
                    if cnote.startswith("refused"):
                        rep.results.append(StepResult(st.index, label, "refused", summary=cnote, ms=int((time.time() - t0) * 1000)))
                        rep.stopped = f"step {st.index + 1} ('{label}'): {cnote}"
                        break
            routes = self.routes_for(v, st.text or (st.want if (v is not None and v.aid.startswith("script:rna:")) else "")) if v else []
            if not st.prefer and v is not None and not rep.dry_run:
                st.prefer = self._book_prefer(st, v)                                              # the book is consulted BEFORE the screen is attacked, not after it fails
            if st.prefer:                                                                        # the route that worked last time goes first
                pf = fold(st.prefer)
                routes.sort(key=lambda r: 0 if (fold(r.label()) == pf or pf in fold(r.label()) or fold(r.label()) in pf) else 1)
            elif self.learner is not None and v is not None and len(routes) > 1:                 # otherwise the LEARNT order (it can only re-order routes that exist and are allowed)
                try:
                    ctx = {"app": self.app_key, "toolkit": self.toolkit, "role": v.role, "safety": st.safety, "source": st.source, "archetype": self.archetype, "label": v.label,
                           "has_shortcut": bool(v.shortcut), "n_controls": len(self.catalog.verbs)}
                    order = [k for k, _s in self.learner.rank_routes(ctx, [r.kind for r in routes])]
                    routes.sort(key=lambda r: order.index(r.kind) if r.kind in order else 99)
                except Exception:
                    pass
            if v is not None and routes and (self._is_opener(v) or "menu" in (v.leads_to or "")) and not rep.dry_run:
                routes = routes + [routes[0]]                                          # a flyout left open by the previous step swallows the first click (light dismiss): the first route gets a second chance
            route_verb: Dict[int, Any] = {}
            trig = self.triggers.get(v) if (self.triggers is not None and v is not None and not rep.dry_run) else None
            if trig is not None:
                tp = self._trigger_route(trig)
                if tp is not None:                                                 # a verified stand-in for this control: tried FIRST (the routes that failed before come after it)
                    route_verb[id(tp[1])] = tp[0]
                    routes = [tp[1]] + routes
                else:
                    self.triggers.record(trig, False)                                  # its stand-in is no longer in the catalog
                    trig = None
            tried: List[str] = []
            result: Optional[StepResult] = None
            self._last_trace = None
            if self.pointer is not None and v is not None:                                       # the virtual mouse goes to the control first (it never moves the real one)
                ps = self.pointer_stats
                try:
                    node = self._live_node(v)
                    if node is not None and node.rect[2] > node.rect[0] and node.rect[3] > node.rect[1]:
                        from .schema import Box
                        ps["aimed"] += 1
                        self._last_trace = self.pointer.move_to(Box(*node.rect), v.label, "click", v.shortcut, st.index + 1)
                        ps["reached"] += 1 if self._last_trace is not None else 0
                    else:
                        ps["no_box"] += 1                                                    # the control is not on screen as a box (closed flyout / not laid out): the route acts without the pointer
                except Exception:
                    self._last_trace = None
                    ps["errors"] += 1
            for r in routes:
                # ONE STEP CANNOT EAT THE RUN: every route attempt costs at least one provider read, and on a lazy provider (Word: 22 s for a
                # whole tree) the attempts stack into minutes. Past the cap the step stops trying and says what it tried - the run moves on and
                # the next step gets the screen.
                if time.time() - t0 > self.step_cap:
                    tried.append(f"step cap: {self.step_cap:.0f} s spent on this step ({len(tried)} route attempts) - giving up on the rest")
                    break
                s0 = self._snap()
                ok, how = self._deliver(route_verb.get(id(r), v), r)
                tried.append(("trigger " if id(r) in route_verb else "") + f"{r.label()} -> {how}")
                if not ok:
                    if id(r) in route_verb and trig is not None:
                        self.triggers.record(trig, False)
                    if how.startswith("refused"):
                        result = StepResult(st.index, label, "refused", route=r.label(), tried=tried, summary=how)
                        break
                    continue
                s1 = self._settle(s0, max(settle_s, 3.5) if r.kind in ("expand", "control") and (self._is_opener(v) or "menu" in (v.leads_to or "")) else settle_s,
                                  expect_change=r.kind in ("expand", "control") and (self._is_opener(v) or "menu" in (v.leads_to or "")))
                d = delta(s0, s1)
                if r.kind in ("control", "click") and not d.new_windows and self._dialog_expected(st, v, rep):
                    self._nudge_active()                                           # a dialog that waits for the application to be 'active' (measured on Office: Insert Picture after 'This Device...')
                    s1b = self._settle(s0, 3.0, expect_change=True)
                    d2 = delta(s0, s1b)
                    if d2.new_windows:
                        s1, d = s1b, d2
                        how += " (the dialog appeared after an activation message)"
                self._last = (s0, s1, d)
                self._note_follow(d)                                       # a window this step opened becomes part of what the NEXT step can see (a picker that took the interface is hosted by another process)
                tried[-1] += f" => {d.effect()}" + (f" ({d.summary()[:80]})" if d.effect() == "no_effect" else "")
                self._log_attempt(st, v, r, how, s0, s1, d)
                if d.effect() == "no_effect" and r.kind == "scripting":
                    result = StepResult(st.index, label, "done", route=r.label(), tried=tried, effect="state_change", summary=how + " (the application itself reported the command finished)")
                    break
                if d.effect() == "no_effect":
                    node_now = self._live_node(v) if v is not None else None
                    is_already = False
                    already_why = ""
                    if node_now is not None:
                        if getattr(node_now, "selected", None) is True:
                            is_already, already_why = True, f"control '{v.label}' is already selected; nothing to do"
                        elif getattr(node_now, "toggle_state", -1) != -1:
                            tog = getattr(node_now, "toggle_state", -1)
                            if (tog == 1 and st.want in ("on", "1", "true")) or (tog == 0 and st.want in ("off", "0", "false")):
                                is_already, already_why = True, f"'{v.label}' is already in desired toggle state ({st.want})"
                    if not is_already and v is not None:
                        lbl_f = fold(v.label)
                        all_nodes_list = self._all_nodes()
                        for an in all_nodes_list:
                            an_f = fold(getattr(an, "name", "") or "")
                            is_col_match = (an_f == lbl_f or
                                            an_f.endswith(f": {lbl_f}") or
                                            an_f == f"colour 1: {lbl_f}" or
                                            an_f == f"color 1: {lbl_f}" or
                                            an_f == f"colour 2: {lbl_f}" or
                                            an_f == f"color 2: {lbl_f}")
                            if is_col_match and (getattr(an, "selected", None) is True or (getattr(an, "role", "") in ("button", "splitbutton", "radiobutton", "listitem") and (an_f.startswith("colour 1:") or an_f.startswith("color 1:")))):
                                is_already, already_why = True, f"'{an.name}' is already selected / active in live tree"
                                break
                        if not is_already and (v.role in ("tab", "tabitem", "listitem", "menuitem") or (v.path and any("nav" in p.lower() for p in v.path))):
                            all_texts = " | ".join(fold(x) for x in list((getattr(s1, "texts", {}) or {}).values()) + [getattr(n, "name", "") for n in all_nodes_list])
                            if lbl_f in all_texts:
                                is_already, already_why = True, f"view / mode '{v.label}' is already active"
                    if is_already:
                        vis = self.vision_check(st, s0.image, s1.image) if self.vision_check is not None else None
                        result = StepResult(st.index, label, "done", route=("trigger:" if id(r) in route_verb else "") + r.label(),
                                            tried=tried, effect="already_satisfied", summary=already_why, vision_ok=vis)
                        if id(r) in route_verb and trig is not None:
                            self.triggers.record(trig, True)
                        break
                    if id(r) in route_verb and trig is not None:
                        self.triggers.record(trig, False)
                    continue
                vis = self.vision_check(st, s0.image, s1.image) if self.vision_check is not None else None
                says = self._app_says()                                             # the application spoke: its own line travels with the result (precondition machinery reads it)
                result = StepResult(st.index, label, "done", route=("trigger:" if id(r) in route_verb else "") + r.label(), tried=tried, effect=d.effect(),
                                    summary=((f"app_says: {says[:120]}; " if says else "") + d.summary()), vision_ok=vis)
                if id(r) in route_verb and trig is not None:
                    self.triggers.record(trig, True)
                break
            if ((result is None or result.status in ("no_effect", "disabled")) and not rep.dry_run and v is not None
                    and time.time() - t0 < self.step_cap):
                # the routes did not move the step: ask the EYE what on the screen is in the way before concluding the control is missing
                said, did = self._eye_blocker(st)
                if did:
                    base = list(result.tried) if result is not None else list(tried)
                    base.insert(0, did)
                    r = routes[0] if routes else None
                    if r is not None:
                        s0 = self._snap()
                        ok, how = self._deliver(v, r)
                        if ok:
                            s1 = self._settle(s0, settle_s)
                            d = delta(s0, s1)
                            self._last = (s0, s1, d)
                            self._log_attempt(st, v, r, how, s0, s1, d)
                            if d.effect() != "no_effect":
                                result = StepResult(st.index, label, "done", route=r.label(), tried=base + [f"{r.label()} -> {how} => {d.effect()}"],
                                                    effect=d.effect(), summary="the eye cleared what was in front of this control; " + d.summary())
                        if result is None or result.status != "done":
                            tried = base
                elif said and result is not None:
                    result.tried.append(f"the eye: {said}")
                    result.summary += f" | what the eye sees in front of it: {said[:160]}"
            if result is None and v is not None and self.triggers is not None and st.source == "guide" and not rep.dry_run:
                result = self._make_trigger(st, v, label, routes, tried, settle_s)               # the worst case: every ordinary route failed - one stand-in may be created (capped)
            if result is None:
                says = self._app_says()
                result = StepResult(st.index, label, "no_effect", tried=tried,
                                    summary=(f"app_says: {says[:120]}" if says else "no route produced a visible effect"))
            result.ms = int((time.time() - t0) * 1000)
            if modal_note:                                                 # the step's real obstacle: a dialog had the window; the report says so
                result.tried.insert(0, f"modal: {modal_note}")
                result.summary = f"(a dialog owned the window: {modal_note}) " + result.summary
            rep.results.append(result)
            self._after_step(st, result)
            if v is not None and result.status == "done":
                self._last_verb = v
                if self.clip is not None and COPY_RX.search(f"{v.label} {v.shortcut}"):
                    self.clip.touch()                                                  # what is on the clipboard now is the run's own
            if self._sticky is not None:
                self._sticky_left -= 1
                if self._sticky_left <= 0 or result.status != "done":
                    self._hold_release()                                           # the flyout item was used (or the step failed): the foreground goes back to the user
            if result.status != "done":
                rep.stopped = f"step {st.index + 1} ('{label}'): {result.status}"
                break
        if self.dialogs is not None and not rep.dry_run:
            self._auto_dialogs(rep)                                                  # a dialog the LAST step opened
        rep.ok = bool(rep.results) and not rep.stopped and all(r.status in ("done", "dry_run") for r in rep.results) and len(rep.results) == len(rep.steps)
        contradicted = [r for r in rep.results if r.verified is False]
        if rep.ok and contradicted:
            rep.ok = False
            rep.stopped = f"step {contradicted[0].index + 1} ('{contradicted[0].verb}') did something, but not what was expected: expected {contradicted[0].expected}; {contradicted[0].evidence[:120]}"
        rep.seconds = round(time.time() - t_start, 2)
        return rep

    def _after_step(self, st: Step, res: StepResult) -> None:
        if res.status == "done" and st.kind == "object" and res.verified is True:
            self.verify_log.append({"step": st.index + 1, "goal": st.goal[:80], "expected": f"a {st.text or 'object'} is selected", "source": "object model", "said": "",
                                    "verified": True, "evidence": (res.evidence or res.summary)[:200]})     # the document's own model says what is selected: an already-selected object changes nothing on screen
        elif res.status == "done" and st.kind not in ("skip",):
            try:
                from . import verify as VF
                exp = st.expect or VF.expectation_for(st, next((x for x in self.catalog.verbs if st.verb_id and x.id == st.verb_id), None))
                last = getattr(self, "_last", None) or (None, None, None)
                se = getattr(self, "_script_effect", None) if str(res.route).startswith("scripting") else None
                if se is not None:                                                           # a step done by the application's own scripting engine: ITS state is the evidence, not a picture of a window we cannot read
                    self._script_effect = None
                    if se.get("changed"):
                        verdict, why = True, "the application's own state changed (selection / view / mode / objects / the setting itself)"
                    else:
                        verdict, why = None, "the application reported the command finished; its state digest did not change (a command may legitimately change nothing the digest covers)"
                elif last[2] is not None:
                    verdict, why = VF.check(exp, last[0], last[1], last[2], self._all_nodes())
                else:
                    verdict, why = (None, "no before/after pair for this step")
                if verdict is None and res.vision_ok is not None:
                    verdict, why = res.vision_ok, why + " | vision model: " + ("difference seen" if res.vision_ok else "no difference seen")
                res.expected, res.verified, res.evidence = exp.text(), verdict, why[:200]
                self.verify_log.append({"step": st.index + 1, "goal": st.goal[:80], "expected": exp.text(), "source": exp.source, "said": exp.said, "verified": verdict, "evidence": why[:200]})
            except Exception as exc:
                res.evidence = f"verification error {type(exc).__name__}"
        if self.on_step is not None:
            try:
                self.on_step("after", st, res)
            except Exception:
                pass

    def _gesture_step(self, st: Step) -> StepResult:
        """A pointer gesture the guide asks for (draw, drag, select by dragging, orbit / pan / zoom), through professor.gestures: the application's scripting engine, posted pointer
        messages, or a synthetic touch contact on the visible owned window - never the person's mouse."""
        t0 = time.time()
        if self.gesture_driver is None:
            from .gestures import GestureDriver
            self.fx.overlay = getattr(self.pointer, "overlay", None) if self.pointer is not None else None
            self.fx.visible_ok = bool(getattr(self, "visible", False))
            self.gesture_driver = GestureDriver(self.app_key, self.hwnd, self.fx, self._all_nodes, overlay=self.fx.overlay, scripting=self.script_bridge, visible_ok=self.fx.visible_ok,
                                                native=self.fx.native)
            self.gesture_driver.vp = self.fx.pointer() if self.fx.allowed else None             # ONE virtual mouse per window: clicks and gestures share its learned routes and its agent
        r = self.gesture_driver.perform(st.text or "drag", st.goal)
        return StepResult(st.index, f"{st.text} gesture", "done" if r.ok else "unknown", route=f"gesture:{r.route}" if r.ok else "", tried=r.tried, effect="visual_only" if r.ok else "",
                          summary=(r.why if r.ok else r.why) or "", ms=int((time.time() - t0) * 1000))

    def _dialog_or_choice(self, st: Step, settle_s: float) -> StepResult:
        """'Select OK' = the button of that name in the dialog open NOW (pop-up windows first, then fresh controls of the main window); 'choose the layout you want' = the first plain, enabled, safe item
        of the menu / gallery / list that is open now. Verified by a before/after delta like every step."""
        from .probe import delta
        t0 = time.time()
        nodes = self._all_nodes()
        pops = self._open_items(nodes)
        target = None
        if st.kind == "dialog_button":
            want = fold(st.text or "ok")
            for pool in (pops, nodes[: self._main_n]):
                cands = [n for n in pool if n.role in ("button", "hyperlink", "splitbutton") and n.enabled and not n.offscreen and (fold(n.name) == want or fold(n.name).startswith(want + " "))]
                if cands:
                    target = cands[0]
                    break
            if target is None:
                # THE EYE READS WHAT THE TREE CANNOT: a dialog painted inside the application's own canvas (a 3-D suite's file browser, an engine's picker) owns no accessibility objects at all - as far
                # as UI Automation is concerned there is no button. The word is still on the screen, so the screen is asked, and the virtual mouse presses the word it read.
                seen = getattr(self, "look_here", None)
                els = list(seen() if callable(seen) else [])
                wf = fold(st.text or "ok")
                hit = next((e for e in els if e.bbox.x2 > e.bbox.x1 and (fold(e.label or "") == wf or fold(e.label or "").startswith(wf + " "))
                            and safety.classify(e.label or "") == "safe" and not (self.deny is not None and self.deny.search(e.label or ""))), None)
                if hit is None:
                    return StepResult(st.index, st.text, "unknown", summary=f"no '{st.text}' button in any open dialog"
                                      + (f" - the screen was read as well ({len(els)} words seen) and '{st.text}' is not among them" if els else " (and the screen could not be read either)"),
                                      ms=int((time.time() - t0) * 1000))
                s0 = self._snap()
                ok, how = self.fx.click_xy(int(hit.bbox.cx), int(hit.bbox.cy))
                if not ok:
                    return StepResult(st.index, str(hit.label), "no_effect" if not how.startswith("refused") else "refused", route="read by the eye", tried=[f"screen:'{hit.label}' -> {how}"], summary=how,
                                      ms=int((time.time() - t0) * 1000))
                s1 = self._settle(s0, settle_s)
                d = delta(s0, s1)
                self._last = (s0, s1, d)
                self._note_follow(d)
                st.verb = str(hit.label or st.text)
                return StepResult(st.index, str(hit.label or st.text), "done" if d.effect() != "no_effect" else "no_effect", route="read by the eye",
                                  tried=[f"screen:'{hit.label}' -> {how}"], effect=d.effect(), summary="pressed a button only the screen can see: " + d.summary(), ms=int((time.time() - t0) * 1000))
        else:
            if not pops and st.target:                                             # 'Select an **Outline** style': nothing is open, but the manual names the drop-down the choice is in - open it first
                opener = next((n for n in nodes[: self._main_n] if _nl(n.name) == _nl(st.target) and n.enabled and not n.offscreen and "expand" in (n.pats or [])), None)
                if opener is not None:
                    self._hold_open()
                    self._sticky_left = 1
                    ok_o, _how_o = self._expand_node(opener)
                    if ok_o:
                        time.sleep(0.6)
                        nodes = self._all_nodes()
                        pops = self._open_items(nodes)
            # what is OPEN (a flyout / dialog) first; with nothing open, only a list / gallery item of the window (a page of templates) - never an arbitrary button of the window
            roles = ("listitem", "menuitem", "button", "radiobutton", "treeitem", "combobox") if pops else ("listitem", "radiobutton", "treeitem", "combobox")
            for n in pops or nodes[: self._main_n]:
                if n.role in roles and n.enabled and not n.offscreen and n.name and safety.classify(n.name) == "safe" and not (self.deny is not None and self.deny.search(n.name)):
                    target = n
                    break
            if target is None:
                return StepResult(st.index, st.goal[:40], "unknown", summary="nothing is open to choose from (the previous step opened no menu / gallery / list)", ms=int((time.time() - t0) * 1000))
        s0 = self._snap()
        ok, how = self.fx.node(target)
        if not ok:
            return StepResult(st.index, target.name, "refused" if how.startswith("refused") else "no_effect", route="control", tried=[how], summary=how, ms=int((time.time() - t0) * 1000))
        s1 = self._settle(s0, settle_s)
        d = delta(s0, s1)
        self._last = (s0, s1, d)
        st.verb = target.name
        return StepResult(st.index, target.name, "done" if d.effect() != "no_effect" else "no_effect", route="control", tried=[f"control:{target.name} -> {how}"], effect=d.effect(),
                          summary=d.summary(), ms=int((time.time() - t0) * 1000))

    # ---- objects, contextual tabs
    def _select_object(self, st: Step, settle_s: float) -> StepResult:
        """'Select the WordArt to change' / 'Select a text placeholder': an object in the run's OWN document is selected through the application's object model. When the document has no such
        object yet the result says 'needs_object' - the caller may create one through another procedure of the same guide first (AppRun._satisfy_precondition)."""
        from .probe import delta
        t0 = time.time()
        kind = st.text or "object"
        model = self.object_model if (self.object_model is not None and hasattr(self.object_model, "select_object")) else None
        route = "object_model"
        if model is None and self.script_bridge is not None and hasattr(self.script_bridge, "select_object"):
            model, route = self.script_bridge, "scripting"                      # the application's own scripting engine selects one of the document's objects of that kind
        if model is None:
            return StepResult(st.index, kind, "unknown", summary="the step acts on an object in the document (a picture, a shape, a slide's item) that this run did not create", ms=int((time.time() - t0) * 1000))
        if not self.fx.allowed:
            return StepResult(st.index, kind, "refused", summary="refused: " + self.fx.why_not())
        s0 = self._snap()
        ok, how = model.select_object(kind)
        if not ok:
            st_ = "unknown" if how.startswith(("no ", "needs_object")) else "no_effect"
            return StepResult(st.index, kind, st_, route=route, tried=[how], summary=("needs_object: " if st_ == "unknown" and not how.startswith("needs_object") else "") + how, ms=int((time.time() - t0) * 1000))
        s1 = self._settle(s0, settle_s)
        d = delta(s0, s1)
        self._last = (s0, s1, d)
        # the model itself says what is selected now: that is the verification (an object that was ALREADY selected changes nothing on screen)
        res = StepResult(st.index, kind, "done", route=route, tried=[how], effect=d.effect() if d.effect() != "no_effect" else "selected", summary=how + "; " + d.summary(),
                         ms=int((time.time() - t0) * 1000), verified=True, evidence=how)
        return res

    def _dialog_step_as_control(self, st: Step) -> Optional[Step]:
        """A step the guide words like a file-dialog step ('Select **Open**', 'Select **Save as**', 'click **Audio**') while NO dialog is open: the term it names is the control that opens the
        dialog. Grounded to that control (exact name, the one near the previous step first); None when the term names no control."""
        from .knowledge import guide_steps as GS
        term = (st.target or "").strip()
        if not term or len(term.split()) > 4:
            return None
        v, c = GS.resolve_label_ctx(self.catalog, term, GS.near_of(self._last_verb))
        if v is None or c < 1.0 or not v.enabled:
            return None
        ns = self._step_for_verb(v, st.goal, c, "guide", st.cite)
        ns.index = st.index
        ns.note = "no dialog was open yet: the control the step names opens it (the dialog handler takes over after)"
        ns.expect = st.expect
        return ns

    def _tab_live(self, name: str) -> bool:
        nodes = self._all_nodes()
        return any(n.role == "tabitem" and _nl(n.name) == _nl(name) and not n.offscreen for n in nodes[: self._main_n or len(nodes)])

    def _enter_context(self, v: Verb) -> str:
        """A control that lives on a CONTEXTUAL tab (shown only in a mode: 'Slide Master > Master Layout > Footers') whose tab is not in the window: the command of the same name as the tab
        ('View > Slide Master') puts the application in that mode first. Remembered, so the mode is left again after the procedure (leave_contexts). Returns what was done ('' = nothing)."""
        if getattr(self, "_entering", False) or not (v.path or v.role == "tab"):
            return ""
        from .knowledge.guide_steps import _words_eq
        tab = str(v.path[0]) if v.path else v.label                              # the step may name the contextual TAB itself ('select Header & Footer')
        if tab.startswith("Context menu") or self._tab_live(tab):
            return ""
        cands = [x for x in self.catalog.verbs if x.role != "tab" and _words_eq(x.label, tab) and x.enabled and x.id != v.id and x.path and not _words_eq(str(x.path[0]), tab)
                 and not str(x.path[0]).startswith("Context menu") and safety.classify(x.label, " ".join(x.path)) == "safe"]
        cands.sort(key=lambda x: (not (set(x.sources or []) - {"vendor-manifest"}), len(x.path)))
        if True:                                                                 # also the ENTRY command of the same-named group on another tab (after any command of the tab's name)
            entry: List[Verb] = []
            tw = set(fold(tab.replace("&", " ")).split())                         # ('Header & Footer' tab <- 'Insert > Header & Footer > Header > Edit Header')
            seen = {c.aid or c.text_path for c in cands}
            for x in self.catalog.verbs:
                if not x.path or _words_eq(str(x.path[0]), tab) or str(x.path[0]).startswith("Context menu") or not x.enabled or x.role == "tab":
                    continue
                if not any(_words_eq(str(p), tab) for p in x.path[1:]) or not self.ENTRY_RX.match(x.label or ""):
                    continue
                if (x.leads_to or "") and re.search(r"(?i)menu|dialog|gallery", x.leads_to) or safety.classify(x.label, " ".join(x.path)) != "safe":
                    continue
                if not (set(fold(x.label).split()[1:]) & tw) or (x.aid or x.text_path) in seen:
                    continue                                                      # 'Edit Header' (names the tab's subject), not 'Open Recent'
                seen.add(x.aid or x.text_path)
                entry.append(x)
            entry.sort(key=lambda x: (not x.label.lower().startswith("edit"), len(x.path)))
            cands = cands[:2] + entry[:2]
        self._entering = True
        try:
            for c in cands:
                for r in self.routes_for(c):
                    if r.kind not in ("control", "object_model", "command", "shortcut"):
                        continue
                    ok, how = self._deliver(c, r)
                    if not ok:
                        continue
                    end = time.time() + 4.0
                    while time.time() < end:
                        time.sleep(0.4)
                        if self._tab_live(tab):
                            self.entered_contexts.append(tab)
                            return f"entered the '{tab}' mode through '{c.text_path}' ({r.kind})"
        finally:
            self._entering = False
        return ""

    def leave_contexts(self, tabs: Sequence[str] = ()) -> List[str]:
        """Leave the modes the run entered (and any contextual tab named in `tabs`): the tab's own 'Close ...' command (Close Master View), live or through the object model."""
        done: List[str] = []
        want = list(dict.fromkeys(list(self.entered_contexts) + list(tabs)))
        self.entered_contexts = []
        for tab in want:
            if not self._tab_live(tab):
                continue
            closers = [x for x in self.catalog.verbs if x.path and fold(str(x.path[0])) == fold(tab) and re.match(r"(?i)^close\b", x.label or "") and x.enabled]
            for c in closers[:2]:
                left = False
                rs = self.routes_for(c)
                rs.sort(key=lambda r: 0 if r.kind == "object_model" else 1)          # the model's own command first: a bare 'Close' looked up by NAME could be the window's caption button
                for r in rs:
                    if r.kind not in ("control", "object_model", "command") or (r.kind == "control" and fold(c.label) == "close"):
                        continue
                    try:
                        ok, _how = self._deliver(c, r)
                    except Exception:
                        ok = False
                    if ok:
                        time.sleep(1.0)
                        if not self._tab_live(tab):
                            done.append(f"left '{tab}' through '{c.label}'")
                            left = True
                            break
                if left:
                    break
        return done

    # ---- dialogs, files, clipboard
    def _doc_local(self, v: Verb) -> bool:
        """May this 'unsafe'-sounding verb be performed here? Only a verb that changes the document of a throw-away editor session, and says nothing about files, accounts, the system or closing."""
        if not (self.owned and self.sandboxed and self.archetype in DOC_EDITOR_ARCHETYPES):
            return False
        text = v.label + " " + " ".join(v.path[-1:])
        return not (STRONG_UNSAFE_RX.search(text) or DOC_OBJECT_RX.search(v.label))

    def _is_file_step(self, st: Step) -> bool:
        """Does this step of the guide belong to a file dialog? By its wording; 'click OK / Done' only while a file dialog the handler completed is still being followed."""
        from .dialogs import is_file_step_text
        if st.kind == "dialog":
            return True
        if st.kind == "dialog_button" and self._file_followups > 0:
            return True                                                        # 'click OK / Save' of a file dialog the handler already completed
        if st.source != "guide" or st.kind not in ("unknown", "verb"):
            return False
        g = st.goal or ""
        return is_file_step_text(g) or (self._file_followups > 0 and bool(re.search(r"(?i)\b(click|press|select|choose)\b\W*(ok|done|apply|confirm)\b", g)))

    def _file_step(self, st: Step) -> Optional[StepResult]:
        """A step of the guide that belongs to a file dialog ('choose the image', 'type a name', 'click Save'): while a file dialog is open the handler completes it with a sandbox file; once it has been
        completed, the guide's remaining dialog steps are satisfied by it. A step that merely SOUNDS like a file step, with no dialog around, goes on as an ordinary step."""
        t0 = time.time()
        label = st.verb or st.goal[:60]
        if self.dialogs.pending():
            handled = self.dialogs.settle(max_s=10.0, intent="accept")
            if handled:
                self._file_followups = 3
                self.dialog_log += handled
                ok = all(h.get("ok") for h in handled)
                if any(h.get("needs_prime") for h in handled):
                    return StepResult(st.index, label, "no_effect", route="dialog-driver", effect="dialog_outside_sandbox",
                                      summary="the save dialog showed a folder outside the sandbox and was cancelled: " + "; ".join(h["steps"][-1] for h in handled if h.get("needs_prime"))[:240], ms=int((time.time() - t0) * 1000))
                return StepResult(st.index, label, "done" if ok else "no_effect", route="dialog-driver", effect="dialog_closed" if ok else "dialog_stuck",
                                  summary="; ".join(f"{h['kind']}: " + "; ".join(h["steps"])[:140] for h in handled)[:420], ms=int((time.time() - t0) * 1000))
        if self._file_followups > 0:
            self._file_followups -= 1
            return StepResult(st.index, label, "done", route="dialog-driver", effect="already", summary="the file dialog was already completed with a sandbox file by the dialog handler", ms=0)
        if st.kind == "dialog":
            opened = self._open_file_dialog_for(st)                             # the guide skipped the command that OPENS the dialog ('Open your code: open an existing folder'): perform it first
            if opened is not None:
                return opened
            return StepResult(st.index, label, "no_effect", summary="the manual speaks of a file dialog here, but none is open, and no command of the application opens one for this step",
                              ms=int((time.time() - t0) * 1000))
        return None

    OPENER_RX = re.compile(r"(?i)\b(open(?: folder| file| project| workspace| repository)?|import|browse|load|add (?:files?|folder|media|source)|insert (?:picture|image|file|media|audio|video)|"
                           r"choose (?:a )?(?:file|folder|picture|image)|select (?:a )?(?:file|folder)|upload|attach|place)\b")

    def _open_file_dialog_for(self, st: Step) -> Optional[StepResult]:
        """A file step with no dialog open: the application's OWN command that opens a file / folder dialog and whose name shares the most words with the step ('Open an existing folder' ->
        'Open Folder...'), performed once; the dialog it opens is completed by the dialog driver (a sandbox file, or a file the person named). None when no such command exists."""
        t0 = time.time()
        words = {w for w in fold(st.goal).split() if len(w) > 2}
        best, best_s = None, 0.0
        for v in self.catalog.verbs:
            if not v.enabled or v.safety not in ("safe", "commit") or not self.OPENER_RX.search(v.label) or re.search(r"(?i)\brecent\b", v.label + " ".join(v.path)):
                continue
            lw = {w for w in fold(v.label).split() if len(w) > 2}
            sc = len(words & lw) + (0.5 if "dialog" in (v.leads_to or "") else 0.0) + (0.3 if set(v.sources or []) - {"vendor-manifest", "script-registry"} else 0.0)
            if sc > best_s:
                best, best_s = v, sc
        if best is None or best_s < 1.0:
            return None
        step = self._step_for_verb(best, f"open the file dialog the manual speaks of ({st.goal[:60]})", 0.8, "internal")
        step.index = st.index
        before = len(self.dialog_log)
        sub = ExecReport(goal="open a file dialog", steps=[step])
        self._run_inner(sub, False, None, 2.5)
        if self.dialogs is not None and self.dialogs.pending():
            handled = self.dialogs.settle(max_s=10.0, intent="accept")
            self.dialog_log += handled
        new = self.dialog_log[before:]
        ok = bool(new) and all(h.get("ok") for h in new)
        self._file_followups = 3 if ok else 0
        summary = f"performed '{best.text_path}' first (the guide speaks of its dialog); " + ("; ".join(f"{h['kind']}: " + "; ".join(h["steps"])[:120] for h in new) if new else (sub.stopped or "no dialog appeared"))
        return StepResult(st.index, best.label, "done" if ok else "no_effect", route="dialog-driver", effect="dialog_closed" if ok else "", summary=summary[:420], ms=int((time.time() - t0) * 1000))

    def prime_dialog_folder(self) -> str:
        """Make the sandbox the folder file dialogs open in: complete one 'Open' of a sandbox fixture through the application's own Open command (Windows reopens a dialog where the last one was
        completed). Returns what was done, '' when the application has no Open command."""
        v = None
        for x in self.catalog.verbs:
            if fold(x.label) == "open" and x.enabled and x.safety in ("safe", "commit"):
                if v is None or (x.shortcut and not v.shortcut):
                    v = x
        if v is None:
            return ""
        step = self._step_for_verb(v, "open a sandbox file so file dialogs start in the sandbox", 1.0, "internal")
        rep = ExecReport(goal="prime file dialogs", steps=[step])
        step.index = 0
        self.run(rep, dry_run=False, approve=None, settle_s=2.5, learn=False)
        if self.dialogs is not None:
            self.dialogs.needs_prime = False
        return f"opened a sandbox fixture through '{v.label}' so file dialogs start in the sandbox ({'ok' if rep.ok else rep.stopped or 'no effect'})"

    def _auto_dialogs(self, rep: ExecReport) -> None:
        """Whatever dialog the last step left open (file chooser, message box, print dialog) is handled by policy; the result of that step says so."""
        if self.dialogs is None or not self.dialogs.pending():
            return
        handled = self.dialogs.settle(max_s=8.0, intent="accept")
        if not handled:
            return
        self.dialog_log += handled
        if any(h["kind"] in ("file_open", "file_save", "folder") for h in handled):
            self._file_followups = 3
        note = " | dialog handled: " + "; ".join(f"{h['kind']} '{h['title'][:30]}': " + "; ".join(h["steps"])[:120] for h in handled)
        if rep.results:
            rep.results[-1].summary = (rep.results[-1].summary + note)[:700]

    def _prepare_paste(self, st: Step, v: Verb) -> str:
        """A paste step needs something on the clipboard. What the run itself copied stays; otherwise a fixture (text, or a picture where the context is graphical) is placed - after the person's own
        clipboard has been saved. A clipboard that cannot be put back is never overwritten."""
        from .dialogs import IMAGE_CONTEXT_RX, ClipboardBusy
        try:
            if self.clip.has_run_content():
                return "the clipboard holds what this run copied"
            ctx = f"{st.goal} {v.label} {' '.join(v.path)} {self.archetype}"
            if self.sandbox is not None and (IMAGE_CONTEXT_RX.search(ctx) or self.archetype in ("raster_editor", "canvas_layout")):
                p = self.sandbox.fixture("image", ["png"])
                self.clip.put_image(p)
                return f"the clipboard now holds a fixture picture ({os.path.basename(p)}); the person's clipboard is put back afterwards"
            self.clip.put_text("Hojaiga clipboard fixture text")
            return "the clipboard now holds fixture text; the person's clipboard is put back afterwards"
        except ClipboardBusy as exc:
            return "refused: " + str(exc)
        except Exception as exc:
            return f"refused: clipboard not usable ({type(exc).__name__})"

    def _log_text_attempt(self, st: Step, route: str, how: str, s0: Any, s1: Any, d: Any) -> None:
        if self.history is None:
            return
        try:
            self.history.log(self.app_key, "guide" if st.source == "guide" else "exec", "type" if st.kind == "text" else "key", (st.text or st.goal)[:60], route, s0.sig, f"{len(s0.names)} controls", s1.sig,
                             d.summary(), d.effect(), d.effect() != "no_effect", None, "", {"how": how, "cite": st.cite}, toolkit=self.toolkit, archetype=self.archetype, role="document", safety="safe")
        except Exception:
            pass

    def _log_attempt(self, st: Step, v: Any, r: Route, how: str, s0: Any, s1: Any, d: Any) -> None:
        if self.history is None:
            return
        try:
            src = "skill" if st.source.startswith("skill") else ("guide" if st.source == "guide" else "exec")
            role = v.role if v else ""
            tid = self.history.log(self.app_key, src, r.kind if r.kind in ("command", "key") else {"shortcut": "key", "control": "invoke", "value": "set_value", "click": "click"}.get(r.kind, "click"),
                             st.verb or "", r.label(), s0.sig, f"{len(s0.names)} controls", s1.sig, d.summary(), d.effect(), d.effect() != "no_effect", None, v.aid if v else "",
                             {"how": how, "cite": st.cite, "shortcut": bool(v and v.shortcut)}, toolkit=self.toolkit, archetype=self.archetype, role=role, safety=st.safety)
            if self._last_trace and self._last_trace.get("pointer_id"):
                self.history.link_pointer(self._last_trace["pointer_id"], tid)
        except Exception:
            pass

    # ---- learning
    def _learn(self, rep: ExecReport, learn: bool) -> None:
        if self.skills is None or rep.dry_run:
            return
        try:
            if rep.by == "skill" and rep.skill_id:
                self.skills.record(rep.skill_id, bool(rep.ok))
                return
            if learn and rep.ok:
                src = f"guide:{rep.cite}" if rep.by == "guide" else ("archetype" if rep.by == "archetype" else rep.by)
                sk = self.skills.compile(rep, self.app_key, self.archetype, self.app_version, source=src, lineage=rep.lineage)
                if sk is not None:
                    rep.learned = sk.id
        except Exception:
            pass

    def _alternative_verbs(self, st: Step) -> List[Verb]:
        """Other controls that do what a failed step's control was meant to do: the same name elsewhere in the interface (the ribbon AND a menu AND a context menu often carry one command),
        else the best catalog match of the manual's own words that is not the one that failed. Enabled, safe, never the failed one."""
        failed = st.verb_id
        name = st.verb or st.target or ""
        out: List[Verb] = []
        if name:
            for v in self.catalog.verbs:
                if v.id != failed and fold(v.label) == fold(name) and v.enabled and v.safety in ("safe", "commit"):
                    out.append(v)
        if not out and (st.target or st.goal):
            from .knowledge.guide_steps import resolve_label_ctx
            v, c = resolve_label_ctx(self.catalog, st.target or st.goal, ())
            if v is not None and v.id != failed and c >= 0.66 and v.enabled:
                out.append(v)
        out = [v for v in out if not (v.path and str(v.path[0]).startswith("Context menu"))]                # a right-click menu cannot be opened headlessly: never an alternative route
        from .knowledge import guide_steps as GS
        gs = GS.parse_line(st.goal or "", 1) if st.goal else None
        manual_path = list(gs.path[:-1]) if gs is not None and len(gs.path) >= 2 else []
        if manual_path:                                                         # the manual NAMED where the control is ('Insert > Picture > This device'): a same-named control elsewhere ('3D Models > This Device') is another command
            out = [v for v in out if any(GS._container_eq(manual_path[-1], q) for q in v.path)]
        live_first = sorted(out, key=lambda v: (not (set(v.sources or []) - {"vendor-manifest", "atlas-uimap"}), len(v.path)))      # a control seen live beats one only documented
        return live_first[:3]

    GOAL_STOP = {"the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with", "your", "you", "how", "use", "using", "from", "into", "by", "at", "it", "is", "do", "can", "what", "want",
                 "more", "this", "that", "app", "microsoft", "windows", "11", "10", "change", "changes"}

    def same_goal(self, goal: str, cite: str, text: str = "") -> bool:
        """Is another passage of the guide about the SAME goal? Its heading (and opening words) must carry at least two thirds of the goal's own words (the application's name and filler
        words aside). Measured 2026-10-10: without this, 'Delete WordArt' was 're-planned' onto 'Share and collaborate with Word for the web' and counted as done."""
        from .knowledge.guide_steps import _stem
        stop = self.GOAL_STOP | {fold(w) for w in self.app_words}
        gw = {_stem(w) for w in re.findall(r"[a-z0-9]+", fold(goal)) if len(w) > 2 and w not in stop}
        if not gw:
            return True
        pw = {_stem(w) for w in re.findall(r"[a-z0-9]+", fold(cite)) if len(w) > 2}                    # the passage's HEADINGS: its body mentions many things it is not about
        need = max(1, -(-2 * len(gw) // 3))
        return len(gw & pw) >= need

    def replan(self, goal: str, failed: ExecReport, tried_cites: Sequence[str] = (), text: str = "") -> Optional[ExecReport]:
        """AUTONOMY after a failure: (1) the same procedure with the failing step's control swapped for another control of the same name / meaning; (2) ANOTHER passage of the guide for the same
        goal (a different citation) that grounds here. None when neither exists. The caller caps how many re-plans a task may get."""
        last = failed.results[-1] if failed.results else None
        if last is not None and last.status in ("no_effect", "unknown", "disabled", "failed") and last.index < len(failed.steps):
            st = failed.steps[last.index]
            alts = self._alternative_verbs(st)
            if alts:
                v = alts[0]
                new = ExecReport(goal=goal, by="replan:control", cite=failed.cite)
                new.steps = list(failed.steps)
                ns = self._step_for_verb(v, st.goal, 0.8, st.source, st.cite, st.want, st.text)
                ns.index = st.index
                ns.note = f"re-planned: '{st.verb or st.target}' had {last.status}; '{v.text_path}' is another control with that meaning"
                new.steps[st.index] = ns
                new.fallback = ns.note
                self.attach_expectations(new, text)
                return new
        if self.guide_index is not None:
            try:
                from .knowledge import guide_steps as GS
                gp = GS.plan_from_guide(goal, self.catalog, self.guide_index, self.app_key, self.brain, k=6, exclude_cites=list(tried_cites) + [failed.cite], app_words=self.app_words,
                                        relevant=lambda cite, text: self.same_goal(goal, cite, text))
            except Exception:
                gp = None
            if gp is not None:
                new = ExecReport(goal=goal, by="replan:passage", cite=gp["cite"])
                new.steps = self.steps_from_guide(gp, 12)
                new.unknown = list(gp.get("unknown", []))
                new.fallback = f"re-planned from another passage of the guide: {gp['cite']} ({gp['coverage']:.0%} grounded)"
                self.attach_expectations(new, gp.get("text", ""))
                return new
        return None

    def achieve(self, goal: str, approve: Optional[Callable[[Step], bool]] = None, dry_run: bool = False, settle_s: float = 2.5) -> ExecReport:
        """plan -> run, with SELF-HEALING: a skill that fails before it changed anything is replaced by a fresh plan from the guide / rules (never after a partial run - replaying could
        repeat a step that did take effect)."""
        rep = self.plan(goal)
        self.run(rep, dry_run, approve, settle_s)
        if rep.by == "skill" and not rep.ok and not dry_run and not any(r.status == "done" for r in rep.results):
            why = f"skill {rep.skill_id} failed at step 1 ({rep.stopped})"
            rep2 = self.plan(goal, use_skills=False)
            self.run(rep2, dry_run, approve, settle_s)
            rep2.fallback = why
            return rep2
        return rep

    def _settle(self, before: Any, max_s: float, expect_change: bool = False) -> Any:
        """Wait until the application stops changing. With expect_change (the step opens a flyout / dialog: those take a moment, a first-time XAML flyout up to a second or more) a snapshot that
        still equals the one taken BEFORE the action is not 'nothing happened yet' - keep looking for up to max_s."""
        from .probe import snapshot
        end = time.time() + max_s
        last = None
        time.sleep(0.3)
        while time.time() < end:
            s = self._snap()
            if expect_change and before is not None and s.sig == before.sig and len(s.windows) == len(before.windows):
                last = s
                time.sleep(0.3)
                continue
            if last is not None and s.sig == last.sig:
                return s
            last = s
            time.sleep(0.25)
        return last or self._snap()


def milestone_checker(vlm: Any) -> Callable[[Step, Any, Any], Optional[bool]]:
    """Optional VLM check, independent of the accessibility tree: BOTH pictures (before / after the step, pop-ups included) go to the vision model with the question 'is there a visible difference in
    the application?'. A step that opens a flyout, switches a tool or changes a value must change what is on screen; a model that sees NO difference contradicts a 'done' verdict. None when the model
    cannot answer (not running, no picture)."""
    def check(step: Step, before: Any, after: Any) -> Optional[bool]:
        try:
            if after is None or not vlm.available():
                return None
            imgs = [x for x in (before, after) if x is not None]
            if len(imgs) < 2:
                r = vlm.describe(after, f"Answer yes or no. After the user chose '{step.verb or step.goal}', is it visible that the application {step.expected}?", max_tokens=8, timeout=60)
            else:
                r = vlm.chat(f"Picture 1 is the application BEFORE the user chose '{step.verb or step.text or step.goal}', picture 2 is AFTER. Is there a visible difference in the application between the two "
                             f"pictures (a menu or dialog opened or closed, a tool or value changed, text appeared)? Answer yes or no.", images=imgs, max_tokens=8, timeout=90)
            return None if not r.ok else r.text.strip().lower().startswith("yes")
        except Exception:
            return None
    return check
