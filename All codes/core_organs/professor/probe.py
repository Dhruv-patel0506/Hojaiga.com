"""
professor.probe -- HYPOTHESIS-DRIVEN STATE PROBING: learn how the application behaves by testing it the way a QA engineer would, never by clicking at random.

    hypothesis  "Add Marker changes the state"            (from the harvested verbs, safe ones only)
    S0          snapshot  accessibility tree (names, text values, control states, containers) + window pixels + open windows
    act         ONE headless action through professor.effectors (command / UIA pattern / posted click)  -- only in a window we own or the user authorised
    S1          snapshot after the interface settled
    delta       what changed:  visual (pixel rectangles) | tree (controls added / removed) | text (a value or label changed) | context (a container's contents changed:
                the inspector turned into another inspector) | windows (a dialog opened)
    rule        record the transition  verb -> effect  in a state graph
    unwind      put the application back (re-select the old tab, toggle again, the verb's inverse, Undo) and VERIFY S2 == S0; if it cannot be proved the probing STOPS

Budget: 10-15 probes per application. Only 'safe' verbs are tried (professor.safety); anything that deletes, sends, records, runs or saves is never probed.
"""

from __future__ import annotations

import json
import re
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from PIL import Image

from . import config as CFG
from . import safety
from .capture import changed_boxes, changed_fraction, grab_composite, grab_window
from .effectors import Effector
from .harvest import Catalog, Verb
from .schema import Box, fold

GRAPH_DIR = os.path.join(CFG.DATA_DIR, "graphs")
TEXTY = {"text", "edit", "statusbar", "document"}
PRIMARY = ("add", "new", "insert", "create", "select", "show", "hide", "toggle", "zoom", "expand", "collapse", "undo", "redo", "enable", "disable", "visible", "grid")
ACTIVE_ROLES = {"button", "menuitem", "tabitem", "checkbox", "radiobutton", "splitbutton", "listitem", "treeitem"}


# ------------------------------------------------------------------------------------------------------------ snapshots
@dataclass
class Snapshot:
    t: float
    names: Dict[str, str]                       # control key -> label (non-text controls)
    texts: Dict[str, str]                       # key -> value of text-like controls (a label whose words change)
    states: Dict[str, str]                      # key -> "sel=..,tog=..,exp=.." for stateful controls
    containers: Dict[str, Tuple[str, ...]]      # container name -> sorted names inside it (the context)
    windows: Tuple[int, ...]
    image: Optional[Image.Image] = None
    sig: str = ""

    def brief(self) -> Dict[str, Any]:
        return {"controls": len(self.names), "texts": len(self.texts), "windows": len(self.windows), "sig": self.sig}


def _key(n: Any, seen: Dict[str, int]) -> str:
    """A control's IDENTITY across snapshots: its automation id, else role + name + which one of that name it is (the n-th). Geometry is NOT part of it: a toolbar that shifts by a pixel
    when the window is (de)activated or re-laid-out must not look like 'the controls changed' (measured: it made a perfectly restored application look un-restored)."""
    role = n.role
    if n.aid:
        return f"aid:{n.aid}"
    base = f"{role}|#" if role in TEXTY else f"{role}|{fold(n.name)}|#"
    seen[base] = seen.get(base, 0) + 1
    return f"{base}{seen[base]}"


def _editable_value(n: Any) -> Optional[str]:
    """The text inside an edit field / document (UI Automation ValuePattern), or None. Password fields are never read."""
    try:
        if "value" not in (n.pats or []) or n.ctype not in ("EditControl", "DocumentControl"):
            return None
        c = n.ctrl
        if getattr(c, "IsPassword", False):
            return None
        from .effectors import pattern_of
        vp = pattern_of(c, "Value")
        v = vp.Value if vp is not None else None
        return None if v is None else str(v)
    except Exception:
        return None


def snapshot(hwnd: int, with_image: bool = True, nodes: Optional[list] = None, popups: bool = True, extra: Optional[Dict[str, str]] = None) -> Snapshot:
    """The application's state as the accessibility tree sees it: the window AND its open pop-ups / dialogs (a dialog's fields are part of what the step did), control identities, the text of
    labels, the VALUE of edit fields and documents (a typed character must show up), the state of toggles."""
    from core_organs import fast_uia
    from core_organs import headless_input as hin
    from .executor import _timed_snapshot, _HUNG
    nodes = nodes if nodes is not None else (_timed_snapshot(hwnd, 12.0) or [])
    groups: List[list] = [nodes]
    if popups:
        try:
            from .dialogs import light_popups
            for w in light_popups(hwnd):                           # a file dialog's tree (folders, OneDrive) is huge: it is read through window messages by professor.dialogs, never walked here
                if _HUNG.get(w, 0.0) > time.time():
                    continue
                g = _timed_snapshot(w, 5.0)
                if g is None:
                    _HUNG[w] = time.time() + 20.0
                g = g or []
                if g:
                    groups.append(g)
        except Exception:
            pass
    names: Dict[str, str] = {}
    texts: Dict[str, str] = dict(extra or {})                  # state a protocol adapter can see (tabs, current page) joins the tree's labels
    states: Dict[str, str] = {}
    cont: Dict[str, List[str]] = {}
    ordinals: Dict[str, int] = {}
    read_values = 0
    for gi, nodes in enumerate(groups):
        frame_ids: Set[int] = set()                               # the window's OWN frame (title bar, caption buttons, system menu) says where the window is, not what the application is doing
        pre = f"w{gi}:" if gi else ""
        for n in nodes:
            if n.ctype == "TitleBarControl" or (n.parent in frame_ids):
                frame_ids.add(n.idx)
                continue
            if n.offscreen or n.rect[2] <= n.rect[0]:
                continue
            val = _editable_value(n) if read_values < 10 else None
            if val is not None:
                read_values += 1
            if not n.name and val is None:
                continue
            if n.role in ("button", "menuitem") and fold(n.name) in safety.CHROME and n.parent >= 0 and nodes[n.parent].ctype in ("WindowControl", "TitleBarControl"):
                continue
            k = pre + _key(n, ordinals)
            if n.role in TEXTY:
                texts[k] = (n.name or n.role) if val is None else f"{n.name or n.role}={val[:60]}[{len(val)}]"
            else:
                names[k] = n.name
            if n.role in ACTIVE_ROLES or n.pats:
                states[k] = f"sel={n.selected},tog={n.toggle_state},exp={n.expand_state},en={n.enabled}"
            p, container = n.parent, ""
            while p >= 0:
                q = nodes[p]
                if q.name and q.role in ("pane", "group", "tab", "toolbar", "list", "tree", "menubar", "statusbar", "window", "custom"):
                    container = q.name
                    break
                p = q.parent
            cont.setdefault(container or "(window)", []).append(fold(n.name or n.role))
    try:
        wins = tuple(sorted(hin.process_windows(hwnd, include_hidden=False)))
    except Exception:
        wins = ()
    img = None
    if with_image:
        fr = _timed_capture(hwnd, popups, 6.0)                                 # PrintWindow waits for the window's UI thread: a modal loop there blocks it forever (measured on Paint)
        img = fr.image.convert("RGB").resize((max(8, fr.image.width // 2), max(8, fr.image.height // 2))) if fr is not None else None
    import hashlib
    sig = hashlib.sha1(json.dumps([sorted(names.values()), sorted(texts.items()), sorted(states.items())], sort_keys=True).encode("utf-8", "replace")).hexdigest()[:12]
    return Snapshot(time.time(), names, texts, states, {k: tuple(sorted(v)) for k, v in cont.items()}, wins, img, sig)


def _timed_capture(hwnd: int, popups: bool, wall_s: float) -> Any:
    """The window picture with a WALL-CLOCK bound (worker thread; abandoned when late -> None: the snapshot is then judged by its tree alone)."""
    import threading
    from core_organs import headless_input as hin
    box: Dict[str, Any] = {}

    def work() -> None:
        try:
            box["fr"] = grab_composite(hwnd, hin.popup_windows(hwnd)[:6]) if popups else grab_window(hwnd, isolated=True)
        except Exception:
            try:
                box["fr"] = grab_window(hwnd, isolated=True)
            except Exception:
                box["fr"] = None
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(wall_s)
    return None if t.is_alive() else box.get("fr")


CAPTION_ROWS = 24                      # snapshot pictures are half size: ~48 real pixels = the title bar, whose active / inactive painting flips with focus and says nothing about the app


def _below_caption(img: Image.Image) -> Image.Image:
    if img.height <= CAPTION_ROWS * 3:
        return img
    return img.crop((0, CAPTION_ROWS, img.width, img.height))


# -------------------------------------------------------------------------------------------------------------- delta
@dataclass
class Delta:
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    changed_text: List[Tuple[str, str, str]] = field(default_factory=list)
    changed_state: List[Tuple[str, str, str]] = field(default_factory=list)
    containers_changed: List[str] = field(default_factory=list)
    new_windows: List[int] = field(default_factory=list)
    closed_windows: List[int] = field(default_factory=list)
    pixel_boxes: List[List[int]] = field(default_factory=list)
    pixel_fraction: float = 0.0

    def effect(self) -> str:
        if self.new_windows:
            return "opens_dialog"
        if self.containers_changed and (len(self.added) + len(self.removed)) >= 3:
            return "context_change"
        if self.changed_text or self.changed_state or self.added or self.removed:
            return "state_change"
        if self.pixel_fraction > 0.0008:
            return "visual_only"
        return "no_effect"

    def summary(self) -> str:
        bits: List[str] = []
        if self.new_windows:
            bits.append(f"{len(self.new_windows)} new window(s)")
        for k, a, b in self.changed_text[:3]:
            bits.append(f"text '{a[:40]}' -> '{b[:40]}'")
        for k, a, b in self.changed_state[:3]:
            bits.append(f"{k.split('|')[-2] if '|' in k else k}: {a} -> {b}")
        if self.added:
            bits.append("added " + ", ".join(self.added[:5]))
        if self.removed:
            bits.append("removed " + ", ".join(self.removed[:5]))
        if self.containers_changed:
            bits.append("context changed in " + ", ".join(self.containers_changed[:3]))
        if self.pixel_fraction:
            bits.append(f"{self.pixel_fraction * 100:.2f}% of pixels changed")
        return "; ".join(bits) or "nothing changed"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["effect"] = self.effect()
        return d


def delta(a: Snapshot, b: Snapshot) -> Delta:
    d = Delta()
    for k, v in b.names.items():
        if k not in a.names:
            d.added.append(v)
    for k, v in a.names.items():
        if k not in b.names:
            d.removed.append(v)
    for k, v in b.texts.items():
        if k in a.texts and a.texts[k] != v:
            d.changed_text.append((k, a.texts[k], v))
        elif k not in a.texts:
            d.added.append(v)
    for k in a.texts:
        if k not in b.texts:
            d.removed.append(a.texts[k])
    for k, v in b.states.items():
        if k in a.states and a.states[k] != v:
            d.changed_state.append((k, a.states[k], v))
    for k in set(a.containers) | set(b.containers):
        if a.containers.get(k) != b.containers.get(k):
            d.containers_changed.append(k)
    d.new_windows = [w for w in b.windows if w not in a.windows]
    d.closed_windows = [w for w in a.windows if w not in b.windows]
    if a.image is not None and b.image is not None:
        if a.image.size == b.image.size:
            ia, ib = _below_caption(a.image), _below_caption(b.image)
            d.pixel_fraction = round(changed_fraction(ia, ib, cell=8, thresh=10.0), 5)
            off = a.image.height - ia.height
            d.pixel_boxes = [[bx.x1, bx.y1 + off, bx.x2, bx.y2 + off] for bx in changed_boxes(ia, ib, cell=8, thresh=10.0)[:8]]
        else:
            d.changed_state.append(("window_size", f"{a.image.size[0]}x{a.image.size[1]}", f"{b.image.size[0]}x{b.image.size[1]}"))
            d.pixel_fraction = 1.0
    return d


def diff_state(a: Snapshot, b: Snapshot, pixel_tol: float = 0.003) -> List[str]:
    """What still differs between two snapshots that should be the same (empty = the application has been put back)."""
    out: List[str] = []
    if a.names != b.names:
        out.append("controls: +%s -%s" % (sorted(set(b.names.values()) - set(a.names.values()))[:4], sorted(set(a.names.values()) - set(b.names.values()))[:4]))
    if a.texts != b.texts:
        out.append("text: " + "; ".join(f"{a.texts.get(k, '-')!r}->{b.texts.get(k, '-')!r}" for k in sorted(set(a.texts) | set(b.texts)) if a.texts.get(k) != b.texts.get(k))[:160])
    if a.states != b.states:
        out.append("states: " + "; ".join(f"{k.split('|')[-2] if '|' in k else k}: {a.states.get(k, '-')}->{b.states.get(k, '-')}" for k in sorted(set(a.states) | set(b.states)) if a.states.get(k) != b.states.get(k))[:160])
    if set(b.windows) - set(a.windows):
        out.append(f"extra windows {sorted(set(b.windows) - set(a.windows))}")
    if a.image is not None and b.image is not None and a.image.size == b.image.size:
        fr = changed_fraction(_below_caption(a.image), _below_caption(b.image), cell=8, thresh=10.0)
        if fr > pixel_tol:
            out.append(f"pixels {fr:.4f} > {pixel_tol}")
    return out


def same_state(a: Snapshot, b: Snapshot, pixel_tol: float = 0.003) -> bool:
    """Has the application been put back? Same controls, same text values, same control states, no open extra window, (almost) the same picture."""
    return not diff_state(a, b, pixel_tol)


# ------------------------------------------------------------------------------------------------------------- the graph
@dataclass
class Rule:
    verb: str
    path: List[str]
    role: str
    how: str
    effect: str
    delta: Dict[str, Any]
    expected: str
    confirmed: bool
    unwind: str
    restored: Optional[bool]
    ms: int
    from_sig: str = ""
    to_sig: str = ""
    note: str = ""
    benign: bool = False              # the application could not be put back exactly, but only a SELECTION moved (no data changed)
    restore_why: str = ""             # when `restored` is False: exactly what still differs from S0


class StateGraph:
    def __init__(self, app_key: str = ""):
        import networkx as nx
        self.app_key = app_key
        self.g = nx.MultiDiGraph()
        self.rules: List[Rule] = []

    def record(self, r: Rule) -> None:
        self.rules.append(r)
        self.g.add_edge(r.from_sig, r.to_sig or r.from_sig, verb=r.verb, effect=r.effect)

    def by_effect(self, effect: str) -> List[Rule]:
        return [r for r in self.rules if r.effect == effect]

    def mental_model(self) -> Dict[str, Any]:
        """What the probes taught: which verbs mutate state, which switch the context (inspector), which open dialogs, which do nothing."""
        return {"state_mutators": [r.verb for r in self.by_effect("state_change")], "context_switches": [(r.verb, r.delta.get("containers_changed", [])) for r in self.by_effect("context_change")],
                "opens_dialog": [r.verb for r in self.by_effect("opens_dialog")], "visual_only": [r.verb for r in self.by_effect("visual_only")], "no_effect": [r.verb for r in self.by_effect("no_effect")],
                "unwound_ok": sum(1 for r in self.rules if r.restored), "predictions_confirmed": sum(1 for r in self.rules if r.confirmed), "probes": len(self.rules)}

    def save(self) -> str:
        os.makedirs(GRAPH_DIR, exist_ok=True)
        p = os.path.join(GRAPH_DIR, (self.app_key or "app") + ".json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"app": self.app_key, "rules": [asdict(r) for r in self.rules], "model": self.mental_model()}, fh, indent=1, ensure_ascii=False, default=str)
        return p


# ------------------------------------------------------------------------------------------------------------ the engine
@dataclass
class Hypothesis:
    verb: str
    path: List[str]
    role: str
    aid: str
    kind: str                         # state | context | dialog
    expected: str
    rank: float = 0.0


@dataclass
class ProbeReport:
    rules: List[Rule] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)
    stopped: str = ""
    seconds: float = 0.0
    dry_run: bool = False
    model: Dict[str, Any] = field(default_factory=dict)


class ProbeEngine:
    def __init__(self, hwnd: int, effector: Effector, catalog: Optional[Catalog] = None, app_key: str = "", budget_s: float = 90.0, max_probes: int = 15, owned: bool = False,
                 history: Any = None, learner: Any = None, toolkit: str = "", archetype: str = ""):
        self.hwnd, self.fx, self.catalog, self.app_key = hwnd, effector, catalog, app_key
        self.learner, self.toolkit, self.archetype = learner, toolkit, archetype
        self.history = history                                   # professor.history.History or None: every probe leaves a state-transition row
        self.budget_s, self.max_probes, self.owned = budget_s, max_probes, owned
        self.graph = StateGraph(app_key)
        self.tainted = False

    # ---- choosing what to test
    def plan(self, k: Optional[int] = None) -> Tuple[List[Hypothesis], List[Tuple[str, str]]]:
        from core_organs import fast_uia
        nodes = fast_uia.snapshot(self.hwnd, timeout_ms=4000) or []
        out: List[Hypothesis] = []
        skipped: List[Tuple[str, str]] = []
        seen: Set[str] = set()
        groups: Set[Tuple[int, str]] = set()                     # (container, role): look-alike siblings behave alike -> one representative is enough
        for n in nodes:
            low = n.ctype.replace("Control", "").lower()
            if low not in ACTIVE_ROLES or not n.name or n.offscreen or not n.enabled or fold(n.name) in seen or n.rect[2] <= n.rect[0]:
                continue
            if len(n.name) > 40 or fold(n.name) in safety.CHROME:
                continue
            ok, why = safety.may_probe(n.name, "", self.owned)
            if not ok:
                skipped.append((n.name, why))
                continue
            if low == "menuitem" and n.parent >= 0 and nodes[n.parent].role == "menubar":
                skipped.append((n.name, "top-level menu: opening needs the pointer, not probed"))
                continue
            if n.name.rstrip().endswith(("...", "…")):
                skipped.append((n.name, "opens a dialog by convention ('...'): not tried, a dialog takes the focus; predicted opens_dialog"))
                continue
            if low in ("tabitem", "listitem", "treeitem", "radiobutton") and n.selected is True:
                skipped.append((n.name, "already selected: selecting it again tests nothing"))
                continue
            if low in ("listitem", "treeitem", "radiobutton"):
                gk = (n.parent, low)
                if gk in groups:
                    skipped.append((n.name, "look-alike sibling of an item already probed"))
                    continue
                groups.add(gk)
            seen.add(fold(n.name))
            kind = "context" if low in ("tabitem", "listitem", "treeitem", "radiobutton") else "state"
            exp = (f"selecting '{n.name}' switches the context (the inspector / panel contents change)" if kind == "context" else f"'{n.name}' changes the application state")
            rank = 5.0 if any(fold(n.name).startswith(p) for p in PRIMARY) else (3.0 if kind == "context" else (2.0 if low == "checkbox" else 1.0))
            if self.learner is not None:                                 # the learnt chance that trying it shows anything moves it up (the models choose the order among the safe ones)
                try:
                    pr = self.learner.predict({"app": self.app_key, "toolkit": self.toolkit, "role": low, "route": "control", "safety": "safe", "source": "probe", "archetype": self.archetype,
                                               "label": n.name, "n_controls": len(nodes)})
                    rank += 2.0 * (1.0 - float(pr.get("effect", {}).get("no_effect", 1.0)))
                except Exception:
                    pass
            out.append(Hypothesis(n.name, [], low, n.aid, kind, exp, rank))
        out.sort(key=lambda h: -h.rank)
        return out[: (k or self.max_probes)], skipped

    # ---- helpers
    def _find(self, nodes: list, h: Hypothesis) -> Any:
        for n in nodes:
            if h.aid and n.aid == h.aid:
                return n
        for n in nodes:
            if fold(n.name) == fold(h.verb) and n.ctype.replace("Control", "").lower() == h.role:
                return n
        return next((n for n in nodes if fold(n.name) == fold(h.verb)), None)

    def _settle(self, before: Snapshot, max_s: float = 2.5) -> Snapshot:
        end = time.time() + max_s
        last = None
        time.sleep(0.35)
        while time.time() < end:
            s = snapshot(self.hwnd)
            if last is not None and s.sig == last.sig:
                return s
            last = s
            time.sleep(0.25)
        return last or snapshot(self.hwnd)

    def _selected_sibling(self, nodes: list, node: Any) -> Any:
        if node is None:
            return None
        for n in nodes:
            if n.parent == node.parent and n.idx != node.idx and n.selected is True and n.ctype == node.ctype:
                return n
        return None

    def _unwind(self, h: Hypothesis, node: Any, nodes0: list, s0: Snapshot, s1: Snapshot, d: Delta) -> Tuple[str, Optional[Snapshot]]:
        """Put the application back and say HOW. Returns (how, snapshot after unwinding or None when nothing was needed)."""
        eff = d.effect()
        if eff == "no_effect":
            return "not needed (nothing changed)", None
        if d.new_windows:
            closed = self.fx.close_popups(s0.windows)
            self._log_recovery(h.verb, "close", "Escape then WM_CLOSE", closed > 0)
            return f"closed {closed} window(s)", self._settle(s1)
        how = ""
        if h.role in ("tabitem", "listitem", "treeitem", "radiobutton"):
            prev = self._selected_sibling(nodes0, node)
            if prev is not None:
                ok, note = self.fx.node(prev)
                how = f"re-selected '{prev.name}' ({note})"
            elif node is not None:                                   # nothing was selected before: take the selection away again
                ok, note = self.fx.deselect(node)
                how = f"cleared the selection ({note})" if ok else ""
        elif h.role == "checkbox" or (node is not None and "toggle" in getattr(node, "pats", [])):
            from core_organs import fast_uia
            n2 = self._find(fast_uia.snapshot(self.hwnd, timeout_ms=4000) or [], h)
            if n2 is not None:
                ok, note = self.fx.node(n2)
                how = f"toggled back ({note})"
        if not how:
            from core_organs import fast_uia
            nodes1 = fast_uia.snapshot(self.hwnd, timeout_ms=4000) or []
            for cand in safety.inverse_candidates(h.verb):
                inv = next((n for n in nodes1 if fold(n.name) == fold(cand)), None)
                cls = safety.classify(inv.name) if inv is not None else ""
                added_it = bool(re.match(r"(?i)^(add|new|insert|create|open)\b", h.verb)) and bool(re.match(r"(?i)^(close|remove|delete|clear)\b", cand))
                if inv is not None and (cls == "safe" or (self.owned and cls == "commit") or (self.owned and added_it)):      # a 'clear'-like inverse only where the Professor owns the data; closing the tab it just opened is the exact inverse
                    ok, note = self.fx.node(inv)
                    how = f"inverse '{inv.name}' ({note})"
                    break
        if not how and self.catalog is not None and self.catalog.shortcut_for("Undo"):
            ok, note = self.fx.key(self.catalog.shortcut_for("Undo"))
            how = f"Undo shortcut ({note})"
        if not how:
            return "no way to unwind found", None
        return how, self._settle(s1)

    # ---- the state-transition log
    def _log_probe(self, h: Hypothesis, rule: Rule, s0: Snapshot, s1: Snapshot, source: str = "probe") -> None:
        if self.history is None:
            return
        try:
            from .history import primitive_of
            self.history.log(self.app_key, source, primitive_of(rule.how), h.verb, rule.how, s0.sig, f"{len(s0.names)} controls, {len(s0.texts)} texts", s1.sig, rule.note, rule.effect,
                             rule.effect != "no_effect" and not rule.how.startswith("not delivered"), rule.restored, h.aid, {"unwind": rule.unwind, "restore_why": rule.restore_why, "benign": rule.benign},
                             toolkit=self.toolkit, archetype=self.archetype, role=h.role, safety=safety.classify(h.verb))
        except Exception:
            pass

    def _log_recovery(self, trigger: str, primitive: str, route: str, ok: bool) -> None:
        if self.history is None:
            return
        try:
            self.history.log(self.app_key, "recovery", primitive, trigger, route, effect="dialog_closed" if ok else "dialog_stuck", ok=ok)
        except Exception:
            pass

    # ---- the loop
    def run(self, hyps: Optional[Sequence[Hypothesis]] = None) -> ProbeReport:
        from core_organs import fast_uia
        t_start = time.time()
        import contextlib
        with (self.learner.training() if self.learner is not None else contextlib.nullcontext()), self.fx.focus_watch():
            return self._run(hyps, t_start)

    def _run(self, hyps: Optional[Sequence[Hypothesis]], t_start: float) -> ProbeReport:
        from core_organs import fast_uia
        rep = ProbeReport(dry_run=not self.fx.allowed)
        if hyps is None:
            hyps, rep.skipped = self.plan()
        if not self.fx.allowed:
            rep.stopped = "dry run: " + self.fx.why_not()
            rep.rules = [Rule(h.verb, h.path, h.role, "not sent", "untested", {}, h.expected, False, "-", None, 0) for h in hyps]
            return rep
        for h in list(hyps)[: self.max_probes]:
            if time.time() - t_start > self.budget_s:
                rep.stopped = "time budget"
                break
            if self.tainted:
                rep.stopped = "an earlier probe could not be unwound; probing stopped to protect the application"
                break
            ok, why = safety.may_probe(h.verb, "", self.owned)
            if not ok:
                rep.skipped.append((h.verb, why))
                continue
            t0 = time.time()
            nodes0 = fast_uia.snapshot(self.hwnd, timeout_ms=4000) or []
            s0 = snapshot(self.hwnd, nodes=nodes0)
            node = self._find(nodes0, h)
            if node is None:
                rep.skipped.append((h.verb, "control no longer present"))
                continue
            sent, how = self.fx.node(node)
            s1 = self._settle(s0)
            d = delta(s0, s1)
            eff = d.effect()
            unwind, s2 = self._unwind(h, node, nodes0, s0, s1, d)
            restored: Optional[bool] = None
            why_not: List[str] = []
            if eff != "no_effect":
                s2 = s2 or snapshot(self.hwnd)
                # WHO decides 'put back'? With a rich accessibility tree and a STRUCTURAL change, the tree does (controls, values, states, windows) and pixels only veto big drift: a toolbar
                # button keeps its focus highlight after an invoke (measured: 0.5 % of the cells) and that is not a changed application. A change that only showed up in pixels (visual_only), or an
                # application with almost no tree, is judged by pixels strictly - they are the only evidence there is.
                rich = len(s0.names) + len(s0.texts) >= 8
                tol = 0.02 if (rich and eff != "visual_only") else 0.003
                why_not = diff_state(s0, s2, tol)
                restored = not why_not
                if not restored:
                    time.sleep(0.5)
                    why_not = diff_state(s0, snapshot(self.hwnd), tol)
                    restored = not why_not
            predicted = {"state": ("state_change", "visual_only"), "context": ("context_change", "state_change"), "dialog": ("opens_dialog",)}.get(h.kind, ())
            rule = Rule(h.verb, h.path, h.role, how if sent else "not delivered: " + how, eff, d.to_dict(), h.expected, eff in predicted, unwind, restored, int((time.time() - t0) * 1000), s0.sig, s1.sig,
                        note=d.summary(), restore_why="; ".join(why_not))
            if restored is False and h.role in ("tabitem", "listitem", "treeitem", "radiobutton") and not d.new_windows and not d.added and not d.removed and not d.changed_text:
                rule.benign = True                                    # only a selection marker moved; nothing the user would call data
            self.graph.record(rule)
            self._log_probe(h, rule, s0, s1)
            rep.rules.append(rule)
            if eff != "no_effect" and restored is False and not rule.benign:
                self.tainted = True
        rep.seconds = round(time.time() - t_start, 2)
        rep.model = self.graph.mental_model()
        self.graph.save()
        return rep
