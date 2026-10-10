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
SPLIT_RX = re.compile(r"\s*(?:,|;|\bthen\b|\band then\b|\bafter that\b|\bnext\b|\band\b)\s*", re.I)
TYPE_RX = re.compile(r"^(?:type|enter|write|input)\s+['\"“]?(.+?)['\"”]?$", re.I)
QUOTED_RX = re.compile(r"[\"“‘']([^\"”’']{1,80})[\"”’']")
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
_KEEP: List[Any] = []                                             # every node list read during a run: released only after the owned application is closed (release_kept)


def release_kept() -> None:
    """Drop the kept UI Automation elements. Call AFTER the owned application is gone: releasing an element of a process whose UI thread is blocked blocks the caller (measured: Paint)."""
    _KEEP.clear()                                      # window -> until when it is skipped (its UIA provider did not answer)


def _timed_snapshot(hwnd: int, wall_s: float) -> Optional[List[Any]]:
    """fast_uia.snapshot with a WALL-CLOCK bound. This UIA build has no transaction timeout, and a modal dialog's provider can block a call forever (measured: a Word dialog snapshot
    held a whole run for minutes). The call runs in a worker thread (UIA client objects are free-threaded); when it is late, its result is abandoned and None returned."""
    import threading
    from core_organs import fast_uia
    box: Dict[str, Any] = {}

    def work() -> None:
        box["nodes"] = fast_uia.snapshot(hwnd, timeout_ms=int(wall_s * 1000))
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(wall_s)
    _KEEP.append(box)                                             # kept alive (also when abandoned): see release_kept
    if len(_KEEP) > 4000:
        del _KEEP[:1000]
    return box.get("nodes") if not t.is_alive() else None


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
        return next((e for e in self.sm.elements if fold(e.label) == fold(v.label) and e.bbox.w > 2), None)

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
                key = PLAIN_KEYS.get(fold(st.target), fold(st.target))
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
        if kind and re.search(r"(?i)\b(select|click|tap|double-click|choose|highlight)\b", raw) and not self.CONTENT_CARET_RX.search(raw) and (om or not self.CONTROL_WORD_RX.search(raw)):
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
            return Step(0, st.raw, None, "", [], "text", text=self.placeholder + " text", safety="safe", routes=["text:posted characters", "text:uia value"], expected="the typed text appears",
                        source="guide", cite=cite, note="the manual says only 'type some text': a neutral test sentence is typed")
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
    def _all_nodes(self) -> List[Any]:
        """The window's tree PLUS the trees of its process's popups (an open menu, a flyout or a dialog is a separate top-level window that the main tree does not contain)."""
        from core_organs import fast_uia
        nodes = list(_timed_snapshot(self.hwnd, 12.0) or [])
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
                nodes += got or []
        except Exception:
            pass
        return nodes

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
                pops = pops + [n for n in nodes[: self._main_n] if any(b[0] - 4 <= n.rect[0] and b[1] - 4 <= n.rect[1] and n.rect[2] <= b[2] + 4 and n.rect[3] <= b[3] + 4 for b in boxes)]
            nodes = pops
        ACTIVE = {"invoke", "toggle", "select", "expand", "value", "range", "scroll"}

        def best(cands):
            """A button and the text label inside it share a name: take the one that can be ACTED on (patterns), then the one whose control type matches the verb's role."""
            return min(cands, key=lambda n: (not (set(n.pats or []) & ACTIVE), n.role in ("text", "image", "pane", "group", "custom"), (n.role or "") not in (v.role or "", {"menu_item": "menuitem", "tab": "tabitem", "list_item": "listitem", "tree_item": "treeitem", "radio": "radiobutton", "field": "edit", "dropdown": "combobox"}.get(v.role, "")),
                                       n.idx)) if cands else None
        by_aid = [n for n in nodes if v.aid and n.aid == v.aid and not n.offscreen]
        if by_aid:
            return best(by_aid)
        return best([n for n in nodes if _nl(n.name) == _nl(v.label) and not n.offscreen])

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
            cand = [n for n in nodes if _nl(n.name) == _nl(name) and not n.offscreen and n.enabled and n.rect[2] > n.rect[0]]
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
                    if self._flyout_has(nxt) or any(_nl(x.name) == _nl(nxt) and x.idx != cand[0].idx and not x.offscreen and x.rect[2] > x.rect[0] for x in self._all_nodes()):
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
        if not ok or self.activation_first or "expand" not in (n0.pats or []):
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

    def _script_command(self, aid: str, v: Optional[Verb] = None) -> Tuple[bool, str]:
        """A command of the application's own scripting engine. One that takes a FILE would open the application's own file browser (drawn inside its window, not a system dialog): it is given a file
        of the run's sandbox instead - a fixture of the type it asks for to read, the outbox to write - through the bridge, which refuses any other path."""
        info = self.script_bridge.fileinfo(aid)
        if not info.get("path_props"):
            return self.script_bridge.execute(aid)
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

    def _deliver(self, v: Verb, r: Route) -> Tuple[bool, str]:
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
                return False, "control not found in the live tree"
            return self._expand_node(n0)
        node = self._live_node(v)
        if node is None and v.path:                                             # the control lives in a closed menu / drop-down: open its path first (File > Page setup)
            with self.fx.holding():                                             # ...and use it before the foreground is handed back (that would close the flyout)
                opened = self._open_path(v)
                node = self._live_node(v) if opened else None
                entered = ""
                if node is None:
                    entered = self._enter_context(v)                            # its tab is a contextual one (a mode): enter the mode, then open the path again
                    if entered:
                        opened = self._open_path(v) or opened
                        node = self._live_node(v)
                if node is None:
                    return False, "control not found in the live tree (menu path opened: " + str(bool(opened)) + ")" + (f"; {entered}" if entered else "")
                if r.kind == "value":
                    return self.fx.set_value(node, str(r.arg))
                return self.fx.node(node)
        if node is None:
            return False, "control not found in the live tree"
        if r.kind == "value":
            return self.fx.set_value(node, str(r.arg))
        return self.fx.node(node)

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
                    ways = [(f"key:{st.text}", lambda: self.fx.key(st.text))]
                    alt = KEY_AS_TEXT.get(st.text)
                    if alt:
                        ways.append(("text:uia", lambda: self.fx.insert_text(alt)))
                    if self.object_model is not None and self.fx.allowed and st.text.lower().replace(" ", "") in ("delete", "del", "backspace", "ctrl+a"):
                        ways.append((f"key:object-model", lambda: self.object_model.key_equivalent(st.text)))      # the reroute: a posted key that never reaches the document pane
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
                    status = "no_effect"
                if status == "no_effect" and st.kind == "key" and st.text in SOFT_KEYS and route_used:
                    status = "done"                                       # a movement / dismiss key may legitimately change nothing that is visible
                    summary += " (key delivered; nothing visible was expected to change)"
                rep.results.append(StepResult(st.index, label, status, route=route_used or (ways[0][0]), tried=tried_t, effect=effect, summary=summary, ms=int((time.time() - t0) * 1000)))
                self._after_step(st, rep.results[-1])
                if status != "done":
                    rep.stopped = f"step {st.index + 1}: {'typing' if st.kind == 'text' else 'the ' + st.text + ' key'} had no visible effect"
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
            if st.prefer:                                                                        # the route that worked last time goes first
                routes.sort(key=lambda r: 0 if r.label() == st.prefer else 1)
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
            tried: List[str] = []
            result: Optional[StepResult] = None
            self._last_trace = None
            if self.pointer is not None and v is not None:                                       # the virtual mouse goes to the control first (it never moves the real one)
                try:
                    node = self._live_node(v)
                    if node is not None and node.rect[2] > node.rect[0]:
                        from .schema import Box
                        self._last_trace = self.pointer.move_to(Box(*node.rect), v.label, "click", v.shortcut, st.index + 1)
                except Exception:
                    self._last_trace = None
            for r in routes:
                s0 = self._snap()
                ok, how = self._deliver(v, r)
                tried.append(f"{r.label()} -> {how}")
                if not ok:
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
                tried[-1] += f" => {d.effect()}" + (f" ({d.summary()[:80]})" if d.effect() == "no_effect" else "")
                self._log_attempt(st, v, r, how, s0, s1, d)
                if d.effect() == "no_effect" and r.kind == "scripting":
                    result = StepResult(st.index, label, "done", route=r.label(), tried=tried, effect="state_change", summary=how + " (the application itself reported the command finished)")
                    break
                if d.effect() == "no_effect":
                    continue
                vis = self.vision_check(st, s0.image, s1.image) if self.vision_check is not None else None
                result = StepResult(st.index, label, "done", route=r.label(), tried=tried, effect=d.effect(), summary=d.summary(), vision_ok=vis)
                break
            if result is None:
                result = StepResult(st.index, label, "no_effect", tried=tried, summary="no route produced a visible effect")
            result.ms = int((time.time() - t0) * 1000)
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
        if res.status == "done" and st.kind not in ("skip",):
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
                return StepResult(st.index, st.text, "unknown", summary=f"no '{st.text}' button in any open dialog", ms=int((time.time() - t0) * 1000))
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
            roles = ("listitem", "menuitem", "button", "radiobutton", "treeitem") if pops else ("listitem", "radiobutton", "treeitem")
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
        if self.object_model is None or not hasattr(self.object_model, "select_object"):
            return StepResult(st.index, kind, "unknown", summary="the step acts on an object in the document (a picture, a shape, a slide's item) that this run did not create", ms=int((time.time() - t0) * 1000))
        if not self.fx.allowed:
            return StepResult(st.index, kind, "refused", summary="refused: " + self.fx.why_not())
        s0 = self._snap()
        ok, how = self.object_model.select_object(kind)
        if not ok:
            st_ = "unknown" if how.startswith("no ") else "no_effect"
            return StepResult(st.index, kind, st_, route="object_model", tried=[how], summary=("needs_object: " if st_ == "unknown" else "") + how, ms=int((time.time() - t0) * 1000))
        s1 = self._settle(s0, settle_s)
        d = delta(s0, s1)
        self._last = (s0, s1, d)
        # the model itself says what is selected now: that is the verification (an object that was ALREADY selected changes nothing on screen)
        res = StepResult(st.index, kind, "done", route="object_model", tried=[how], effect=d.effect() if d.effect() != "no_effect" else "selected", summary=how + "; " + d.summary(),
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
        if getattr(self, "_entering", False) or not v.path:
            return ""
        from .knowledge.guide_steps import _words_eq
        tab = str(v.path[0])
        if tab.startswith("Context menu") or self._tab_live(tab):
            return ""
        cands = [x for x in self.catalog.verbs if x.role != "tab" and _words_eq(x.label, tab) and x.enabled and x.id != v.id and x.path and not _words_eq(str(x.path[0]), tab)
                 and not str(x.path[0]).startswith("Context menu") and safety.classify(x.label, " ".join(x.path)) == "safe"]
        cands.sort(key=lambda x: (not (set(x.sources or []) - {"vendor-manifest"}), len(x.path)))
        self._entering = True
        try:
            for c in cands[:2]:
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
            return StepResult(st.index, label, "no_effect", summary="the manual speaks of a file dialog here, but none is open", ms=int((time.time() - t0) * 1000))
        return None

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
