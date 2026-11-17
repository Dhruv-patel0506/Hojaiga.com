"""
professor.reveal -- CLICK THROUGH THE INTERFACE: every control that hides more options is opened once, what appears is read into the catalog and drawn, and the application is put back.

menus.expand_menus opens the openers that UI Automation marks as expandable (menu bar, drop-downs, ribbon tabs) and goes down into submenus (View > Zoom). This module goes the rest of the way: the
controls that open a DIALOG or a whole PAGE / PANE - 'Page setup', 'Font', 'Find', 'Settings', 'Options', 'Resize and skew' ... - none of which announce themselves as openers.

  reveal_surfaces()   candidates -> for each one: back to the home state, open the path to it (the same way a guide step would), invoke it once, wait for the interface to settle, read every control
                      that is new (they are filed in the catalog under  opener > item  as source 'reveal'), draw it, then LEAVE (a Cancel / Back / Close button that the surface itself offers,
                      else Escape, else closing the windows it opened) and compare the application with its home state. If it cannot be proved back, the exploring STOPS and says so.
  build_map()         the hidden-options map: every menu / dialog / page that was opened, with the controls found in it.

What may be clicked is decided by WORDING CATEGORIES and by what the live tree says (patterns, roles) - never by application names:
  - a '...' label, or settings-like wording (setup, settings, options, preferences, properties, customize, font, find, replace, go to, resize, canvas, ...)   -> worth opening
  - toggles (a state change, nothing is revealed), file pickers / save / print (they touch the person's files), web / account / update / help links (they leave the application),
    the person's own recent files and history, and anything professor.safety calls unsafe / sensitive / runtime                                            -> never opened; listed WITH the reason
Input only goes to a window the Professor launched itself (the effector refuses otherwise).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from . import menus as MN, safety
from .harvest import Catalog, Verb, verb_id
from .probe import delta, diff_state, snapshot
from .schema import fold

ELLIPSIS_RX = re.compile(r"(\.\.\.|…)\s*$")
DIALOG_RX = re.compile(r"(?i)\b(set ?up|settings?|options?|preferences?|properties|customi[sz]e|configur\w*|manage|advanced|fonts?|format|find|replace|go ?to|search|about|more|details?|information|"
                       r"shortcuts?|keyboard|appearance|themes?|language|layout|resize|skew|canvas|page|edit colou?rs?|panel|pane|gallery|all settings|extensions?|accessibility|general|display|"
                       r"dictionary|spelling|autocorrect|proofing|customize|toolbar|ribbon|status ?bar options|view all|show all)\b")
FILEPICK_RX = re.compile(r"(?i)^(open|browse|import|export|attach|save|print|share|send)\b(?!\s+(settings|options|preferences|navigation|nav|menu|sidebar|pane|drawer|panel|view|gallery))|\b(choose|select|pick|insert|add|attach|upload) (a |an |the )?(file|folder|pictures?|images?|photos?|videos?|audio|documents?)\b|\bfrom (file|computer|device|disk)\b")
EXTERNAL_RX = re.compile(r"(?i)\b(bing|web|online|website|browser|learn more|feedback|help|store|updates?|download|cloud|sign ?(in|out)|log ?(in|out)|account|avatar|profile|subscribe|copilot|rewrite|"
                         r"what'?s new|news|ai|upgrade|premium|trial|buy|purchase)\b")
MUTATES_RX = re.compile(r"(?i)^(undo|redo|cut|copy|paste|delete|clear|select all|insert|add|new|create|duplicate|bold|italic|underline|strikethrough|fill|erase|rotate|flip|invert|crop|apply|reset|"
                        r"toggle|show|hide|enable|disable|status bar|word wrap|time/?date|date|time)\b")
NOISE_RX = re.compile(r"(?i)\b(next|previous|prev|again|forward|backward)\b")
HELP_OK_RX = re.compile(r"(?i)\b(about|shortcuts?|keyboard|version|licen[sc]e|credits)\b")
NESTED_RX = re.compile(r"(?i)\b(options|advanced|settings|more|customi[sz]e|properties|format|set ?up|tabs|preferences|details|configure|manage|edit (?:list|styles?)|modify)\b")
LEAVE_RX = re.compile(r"(?i)^(cancel|close|back|go back|done|dismiss|not now|no thanks|close dialog)$")
BACK_AID_RX = re.compile(r"(?i)(back|cancel)")
SURFACE_ROLES = MN.ITEM_ROLES | {"text"}
WORTH_ROLES = {"button", "menuitem", "hyperlink", "splitbutton", "listitem"}


HAZARDS_PATH = None


def _hazards_path() -> str:
    import os
    from . import config as CFG
    return os.path.join(CFG.DATA_DIR, "hazards.json")


def load_hazards(app_key: str) -> dict:
    """Controls that made THIS application stop responding when they were clicked in an owned, parked instance (learned, per application): never clicked again by exploring."""
    import json
    try:
        with open(_hazards_path(), encoding="utf-8") as fh:
            return json.load(fh).get(app_key, {})
    except Exception:
        return {}


def record_hazard(app_key: str, label: str, why: str) -> None:
    import json, os
    p = _hazards_path()
    try:
        d = json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}
    except Exception:
        d = {}
    d.setdefault(app_key, {})[label] = {"why": why, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1, ensure_ascii=False)


def app_hung(hwnd: int) -> bool:
    """Has the application stopped answering its window messages (Windows' own 'Not Responding' test)?"""
    import ctypes
    try:
        return bool(ctypes.windll.user32.IsHungAppWindow(hwnd))
    except Exception:
        return False


def _forgive_hung() -> None:
    try:
        from .executor import _HUNG
        _HUNG.clear()
    except Exception:
        pass


@dataclass
class Cand:
    path: List[str]
    label: str
    role: str
    aid: str
    ellipsis: bool
    rank: float


def judge(label: str, path: Sequence[str], role: str, pats: Sequence[str], enabled: bool = True) -> Tuple[bool, str, bool]:
    """(may be clicked to reveal something, why / why not, looked-like-an-opener). The third value says whether a refusal is worth listing (it looked like it would open something)."""
    lab = (label or "").strip()
    if not lab:
        return False, "unnamed", False
    if not enabled:
        return False, "disabled in the current state", False
    p = set(pats or [])
    if "toggle" in p:
        return False, "a toggle: switching it changes the state, it reveals nothing", False
    if "expand" in p:
        return False, "an opener: menus.expand_menus reads it", False
    ell = bool(ELLIPSIS_RX.search(lab))
    base = ELLIPSIS_RX.sub("", lab).strip()
    hit = bool(DIALOG_RX.search(base))
    looks = ell or hit
    if MN.PRIVATE_RX.search(lab):
        return False, "lists the person's own files / history - not opened", True
    if EXTERNAL_RX.search(lab):
        return False, "leaves the application (web, account, update, help) - not opened", True
    if path and re.search(r"(?i)\bhelp\b", str(path[0])) and not HELP_OK_RX.search(base):
        return False, "a help link usually opens a browser - not opened", True
    if FILEPICK_RX.search(base):
        return False, "opens a file picker / saves / prints: it would touch the person's files - not opened", True
    cls = safety.classify(base, " ".join(path))
    if cls in ("unsafe", "sensitive", "runtime"):
        return False, f"safety class '{cls}' - not opened", looks
    if cls == "commit" and not hit:
        return False, "safety class 'commit' - not opened", looks
    if not looks:
        return False, "nothing suggests it opens a dialog or a page", False
    if not ell and MUTATES_RX.search(base):
        return False, "changes the document rather than opening something", False
    if NOISE_RX.search(base):
        return False, "steps through results instead of opening anything", False
    return True, "label ends in '...'" if ell else "settings-like wording", True


def collect(read: Sequence[Dict[str, Any]], main_nodes: Sequence[Any]) -> Tuple[List[Cand], List[Dict[str, str]]]:
    """Candidates from (a) items read out of flyouts / tabs by expand_menus and (b) the buttons of the window itself."""
    cands: List[Cand] = []
    skipped: List[Dict[str, str]] = []
    seen: Set[Tuple[Tuple[str, ...], str]] = set()

    def consider(path: List[str], label: str, role: str, pats: Sequence[str], aid: str, enabled: bool) -> None:
        key = (tuple(path), fold(label))
        if key in seen:
            return
        seen.add(key)
        ok, why, looks = judge(label, path, role, pats, enabled)
        if ok:
            ell = bool(ELLIPSIS_RX.search(label))
            cands.append(Cand(list(path), label, role, aid, ell, (2.0 if ell else 1.0) + (0.3 if not path else 0.0)))
        elif looks:
            skipped.append({"path": " > ".join(list(path) + [label]), "why": why})

    for it in read:
        if it.get("role") in WORTH_ROLES:
            consider(list(it["path"]), it["label"], it["role"], it.get("pats") or [], it.get("aid") or "", bool(it.get("enabled", True)))
    for n in main_nodes:
        if n.role in WORTH_ROLES and n.name and not n.offscreen and n.rect[2] > n.rect[0]:
            consider([], MN._item_label(n)[0], n.role, n.pats or [], n.aid or "", bool(n.enabled))
    cands.sort(key=lambda c: -c.rank)
    return cands, skipped


def _bbox(nodes: Sequence[Any]) -> Optional[Tuple[int, int, int, int]]:
    if not nodes:
        return None
    return (min(n.rect[0] for n in nodes), min(n.rect[1] for n in nodes), max(n.rect[2] for n in nodes), max(n.rect[3] for n in nodes))


def _inside(r: Sequence[int], box: Sequence[int], slack: int = 4) -> bool:
    return r[0] >= box[0] - slack and r[1] >= box[1] - slack and r[2] <= box[2] + slack and r[3] <= box[3] + slack


# an IN-PLACE expander and its counterpart ('More >>' / '<< Less', 'Show details' / 'Hide details'): it opens no window, so it is undone by the counterpart, never by Escape (that closes the dialog)
OPPOSITE_WORDS = [(r"\bmore\b", r"\b(less|fewer)\b"), (r"\bshow\b", r"\bhide\b"), (r"\bexpand\b", r"\bcollapse\b"), (r">>", r"<<"), (r"\badvanced\b", r"\b(basic|simple|fewer)\b"),
                  (r"\bopen\b", r"\bclose\b")]


def counterpart_rx(label: str) -> Optional["re.Pattern"]:
    for a, b in OPPOSITE_WORDS:
        if re.search(a, label, re.I):
            return re.compile(b, re.I)
        if re.search(b, label, re.I):
            return re.compile(a, re.I)
    return None


class Revealer:
    def __init__(self, ex: Any, fx: Any, hwnd: int, cat: Catalog, history: Any = None, toolkit: str = "", archetype: str = "", popups0: Sequence[int] = (),
                 on_surface: Optional[Callable[[str, Cand, List[Any]], None]] = None, reset: Optional[Callable[[], None]] = None, restore: Optional[Callable[[], int]] = None,
                 budget_s: float = 80.0, max_surfaces: int = 14, max_depth: int = 3, learner: Any = None, per_surface_s: float = 45.0):
        self.ex, self.fx, self.hwnd, self.cat = ex, fx, hwnd, cat
        self.history, self.toolkit, self.archetype = history, toolkit, archetype
        self.popups0 = list(popups0)
        self.on_surface = on_surface
        self.reset = reset
        self.restore = restore                                                 # puts back what the run itself had changed at home (a toolbar it showed) - an application may reset it when a page is left
        self.budget_s, self.max_surfaces = budget_s, max_surfaces
        self.tainted = False
        self.hung = False
        self.have = {(tuple(v.path), fold(v.label)) for v in cat.verbs}
        self.max_depth = max_depth                                             # 1 = the surface itself; 2 = a dialog opened from inside it; 3 = one more level
        self.learner = learner                                                 # professor.ml: orders the candidates by the learnt chance that clicking reveals something
        self.per_surface_s = per_surface_s
        self.tried: List[Tuple[Tuple[str, ...], str]] = []                    # every (path, label) clicked - the button-coverage numerator
        self.deepest = 0

    # ---- helpers
    def _home(self) -> None:
        if self.reset is not None:
            try:
                self.reset()
                return
            except Exception:
                pass
        try:
            self.fx.close_popups(self.popups0)
            self.fx.key("escape")
        except Exception:
            pass
        time.sleep(0.3)

    def _settle(self, max_s: float = 3.0) -> Any:
        time.sleep(0.45)
        last = None
        end = time.time() + max_s
        while time.time() < end:
            s = snapshot(self.hwnd)
            if last is not None and s.sig == last.sig:
                return s
            last = s
            time.sleep(0.3)
        return last or snapshot(self.hwnd)

    def _leave_button(self, new: Sequence[Any], home_ids: Set[Tuple[str, str, str]]) -> Any:
        """A button the surface itself offers for going away: Cancel / Close / Back / Done among the controls that are NEW (never the window's own Close), or a navigation Back button, or a
        Close button INSIDE the surface's own area (a task pane's 'Close' carries the same name as the window's caption button, so it is not 'new' by identity - its place says it belongs to the pane)."""
        best = None
        box = _bbox([n for n in new if n.rect[2] > n.rect[0]])
        nodes = self.ex._all_nodes()
        top = nodes[0].rect[1] if nodes else 0
        for n in nodes:
            if n.offscreen or not n.enabled or n.role not in ("button", "hyperlink"):
                continue
            name_str = (n.name or "").strip()
            fresh = MN._ident(n) not in home_ids or (box is not None and LEAVE_RX.match(name_str) is not None and _inside(n.rect, box) and n.rect[1] > top + 40)      # never the caption row
            nav_back = bool(re.search(r"(?i)^(back|go back)$", name_str)) or bool(n.aid and re.search(r"(?i)back", n.aid) and not re.search(r"(?i)close|minimi|maximi", n.aid))
            if not ((fresh and (LEAVE_RX.match(name_str) or (n.aid and BACK_AID_RX.search(n.aid)))) or nav_back):
                continue
            if name_str and safety.classify(name_str) == "unsafe" and not LEAVE_RX.match(name_str):
                continue
            rank = 0 if fresh else 1
            if best is None or rank < best[0]:
                best = (rank, n)
        return best[1] if best else None

    def _reselect(self, selected0: Sequence[Tuple[str, str, str]]) -> int:
        """Opening a path through a ribbon tab selects that tab: select the tab(s) that were selected at home again."""
        n_done = 0
        if not selected0:
            return 0
        for n in self.ex._all_nodes():
            if n.role == "tabitem" and MN._ident(n) in selected0 and n.selected is not True and n.enabled and not n.offscreen:
                ok, _how = self.fx.node(n)
                n_done += 1 if ok else 0
        return n_done

    def _leave(self, new: Sequence[Any], s0: Any, home_ids: Set[Tuple[str, str, str]], selected0: Sequence[Tuple[str, str, str]] = (), nested: bool = False,
               opener: Any = None) -> Tuple[str, bool, str]:
        """Go away from the surface and prove the application is back where it started. Returns (how, restored, what still differs)."""
        tol = 0.02 if len(s0.names) + len(s0.texts) >= 8 else 0.003
        tried: List[str] = []
        why: List[str] = []
        ways = ("button", "escape", "popups") if nested else ("button", "back_nav", "escape", "popups", "reselect", "restore", "escape2", "sweep")     # a nested level never escalates past its own window (a second Escape would close the parent)
        if opener is not None:
            ways = ways[:1] + ("opener",) + ways[1:]                                # a PANE (no window of its own, no Cancel - 'Office Clipboard'): the control that opened it toggles it shut
        for how in ways:
            if how == "opener":
                live = self.ex._live_node(opener)
                if live is None:
                    continue
                self.fx.node(live)
                tried.append(f"'{opener.label}' again (toggles the pane)")
            elif how == "button":
                btn = self._leave_button(new, home_ids)
                if btn is None:
                    continue
                self.fx.node(btn)
                tried.append(f"'{btn.name or getattr(btn, 'aid', 'back')}' button")
            elif how == "back_nav":
                self.fx.key("alt+left")
                tried.append("Alt+Left")
            elif how.startswith("escape"):
                self.fx.key("escape")
                tried.append("Escape")
            elif how == "reselect":
                if not self._reselect(selected0):
                    continue
                tried.append("re-selected the starting tab")
            elif how == "restore":
                if self.restore is None or not self.restore():
                    continue
                tried.append("re-applied the display the run had set up")
            elif how == "sweep":
                self.fx.close_popups(s0.windows)
                self._reselect(selected0)
                self.fx.key("escape")
                tried.append("closed leftover windows + re-selected the home tab + Escape")
            else:
                self.fx.close_popups(s0.windows)
                tried.append("closed its windows")
            end = time.time() + 3.5                                                  # a page that is left re-lays itself out: judge it only after it has had the time to settle
            while True:
                time.sleep(0.5)
                _forgive_hung()                                                       # a window skipped as 'hung' while a modal child was open is read again: skipping it would look like 'closed'
                s = snapshot(self.hwnd)
                why = diff_state(s0, s, tol)
                if not why or time.time() > end:
                    break
            if not why:
                return " + ".join(tried), True, ""
        return " + ".join(tried), False, "; ".join(why)[:200]

    # ---- inside an open surface (dialog / page): tabs, drop-down lists, nested dialogs
    def _surface_nodes(self, outside: Set[Tuple[str, str, str]]) -> List[Any]:
        return [n for n in self.ex._all_nodes() if MN._ident(n) not in outside and n.name and not n.offscreen and n.rect[2] > n.rect[0]]

    def _file(self, vpath: Sequence[str], nodes: Sequence[Any], cap: int = 140) -> int:
        added = 0
        for n in [x for x in nodes if x.role in MN.ITEM_ROLES][:cap]:
            added += 1 if MN.add_item_verb(self.cat, self.have, list(vpath), n, source="reveal") else 0
        return added

    def _explore(self, vpath: List[str], depth: int, outside: Set[Tuple[str, str, str]], t_end: float) -> Dict[str, Any]:
        """The surface opened by `vpath` is OPEN. Read what it hides: every TAB of it (selected, read, the first tab selected again), every DROP-DOWN list (expanded, read, collapsed) and -
        while depth < max_depth - every button inside it that opens a further dialog (opened, explored the same way, LEFT through its own Cancel / Close / Escape, and the parent surface
        proved back to the state it had before). Returns counts and a trail; restored=False stops all exploring."""
        st: Dict[str, Any] = {"depth": depth, "tabs": 0, "tab_controls": 0, "lists": 0, "list_items": 0, "nested": 0, "nested_controls": 0, "restored": True, "trail": []}
        self.deepest = max(self.deepest, depth)
        surf = self._surface_nodes(outside)
        # 1 tabs of the surface
        tabs = [n for n in surf if n.role == "tabitem" and n.enabled]
        if len(tabs) >= 2:
            sel0 = next((t for t in tabs if t.selected), None)
            if sel0 is not None:
                st["tab_controls"] += self._file(vpath + [sel0.name], [n for n in surf if n.role != "tabitem"])
            for t in tabs:
                if time.time() > t_end:
                    st["trail"].append("time allowance reached inside the surface")
                    break
                if t.selected or (sel0 is not None and MN._ident(t) == MN._ident(sel0)):
                    continue
                pre = {MN._ident(n) for n in self.ex._all_nodes()}
                ok, how = MN._expand(self.fx, t)
                time.sleep(0.6)
                new = [n for n in self.ex._all_nodes() if MN._ident(n) not in pre and n.name and not n.offscreen and n.rect[2] > n.rect[0] and n.role != "tabitem"]
                st["tabs"] += 1 if ok else 0
                st["tab_controls"] += self._file(vpath + [t.name], new)
                st["trail"].append(f"tab '{t.name}': {len(new)} controls" + ("" if ok else f" ({how})"))
                self.tried.append((tuple(vpath), t.name))
            if sel0 is not None:
                live = next((n for n in self.ex._all_nodes() if MN._ident(n) == MN._ident(sel0)), None)
                if live is not None and not live.selected:
                    MN._expand(self.fx, live)
                    time.sleep(0.4)
        # 2 drop-down lists of the surface (their options are what a guide says to 'choose')
        for cb in [n for n in self._surface_nodes(outside) if n.role == "combobox" and n.enabled and ("expand" in (n.pats or []) or n.expand_state in (0, 1))][:8]:
            if time.time() > t_end:
                break
            pre = {MN._ident(n) for n in self.ex._all_nodes()}
            lab = MN._item_label(cb)[0]
            with self.fx.holding():
                ok, how = MN._expand(self.fx, cb)
                _nodes, items = MN._await_items(self.ex._all_nodes, pre, wait_s=1.5)
                items = [n for n in items if n.role in ("listitem", "menuitem", "radiobutton", "treeitem")][:40]
                st["list_items"] += self._file(vpath + [lab], items, cap=40)
                st["lists"] += 1 if items else 0
                MN.collapse(cb)
                time.sleep(0.2)
            self.tried.append((tuple(vpath), lab))
        # 3 dialogs opened from inside this one
        if depth >= self.max_depth:
            return st
        nested = []
        for n in self._surface_nodes(outside):
            if n.role not in ("button", "hyperlink", "splitbutton") or not n.enabled or LEAVE_RX.match((n.name or "").strip()):
                continue
            lab = MN._item_label(n)[0]
            if re.match(r"(?i)^(ok|apply|yes|no|default|set as default|reset)\b", lab):
                continue
            lab = ELLIPSIS_RX.sub("", lab).strip()                                   # 'Options...' is filed as 'Options' (the path a guide names)
            ell = bool(ELLIPSIS_RX.search(n.name or ""))
            if not (ell or NESTED_RX.search(lab)):
                continue                                                         # inside a dialog, 'Replace' / 'Find' / 'Insert' are the dialog's ACTIONS, not doors to another dialog
            ok, why, _looks = judge(lab, vpath, n.role, n.pats or [], n.enabled)
            if ok:
                nested.append((self._p_reveals(lab, n.role) + (1.0 if ell else 0.0), n, lab))
        nested.sort(key=lambda t: -t[0])
        for _score, b, lab in nested[:4]:
            if time.time() > t_end:
                st["trail"].append("time allowance reached before the nested dialogs")
                break
            s_par = snapshot(self.hwnd)
            pre_nodes = self.ex._all_nodes()
            pre = {MN._ident(n) for n in pre_nodes}
            with self.fx.holding():
                live = next((n for n in pre_nodes if MN._ident(n) == MN._ident(b)), None)
                if live is None:
                    continue
                ok, how = self.fx.node(live)
            self.tried.append((tuple(vpath), lab))
            s_new = self._settle()
            new = [n for n in self.ex._all_nodes() if MN._ident(n) not in pre and n.name and not n.offscreen and n.rect[2] > n.rect[0]]
            d = delta(s_par, s_new)
            if not new and d.new_windows:                                         # a modal child whose tree was not ready (or whose provider stalled): read it once more
                time.sleep(1.5)
                _forgive_hung()
                new = [n for n in self.ex._all_nodes() if MN._ident(n) not in pre and n.name and not n.offscreen and n.rect[2] > n.rect[0]]
            if not new and d.effect() == "no_effect":
                st["trail"].append(f"'{lab}': nothing opened")
                continue
            if not d.new_windows and not new:
                st["trail"].append(f"'{lab}': acted inside the dialog, no window opened (the dialog is cancelled at the end, so nothing is kept)")
                continue
            if not d.new_windows:                                                 # an IN-PLACE expander ('More >>'): its controls are read, then it is undone by its counterpart ('<< Less')
                added = self._file(vpath + [lab], new)
                st["nested_controls"] += added
                how_left, restored, still = self._undo_inplace(b, lab, pre, s_par)
                st["trail"].append({"expanded in place": " > ".join(vpath + [lab]), "controls": added, "undone_by": how_left, "back_to_parent": restored})
                if not restored:
                    st["restored"] = False
                    st["trail"].append(f"could not prove the parent surface is back after '{lab}' ({still[:120]})")
                    return st
                continue
            st["nested"] += 1
            added = self._file(vpath + [lab], new)
            st["nested_controls"] += added
            sub = self._explore(vpath + [lab], depth + 1, pre, t_end)
            st["nested_controls"] += sub["tab_controls"] + sub["list_items"] + sub["nested_controls"]
            how_left, restored, still = self._leave(new, s_par, pre, (), nested=True)
            st["trail"].append({"opened": " > ".join(vpath + [lab]), "depth": depth + 1, "controls": added, "inside": sub["trail"][:6], "left_by": how_left, "back_to_parent": restored})
            if not (restored and sub["restored"]):
                st["restored"] = False
                st["trail"].append(f"could not prove the parent surface is back after '{lab}' ({still[:120]})")
                return st
        return st

    def _undo_inplace(self, opener: Any, lab: str, pre: Set[Tuple[str, str, str]], s_par: Any) -> Tuple[str, bool, str]:
        """Undo an in-place expansion: the counterpart button that appeared ('<< Less' for 'More >>'), else the same control again when it is still there (a toggle). Never Escape."""
        rx = counterpart_rx(lab)
        tried: List[str] = []
        nodes = self.ex._all_nodes()
        cands = []
        if rx is not None:
            cands += [n for n in nodes if MN._ident(n) not in pre and n.role in ("button", "splitbutton", "hyperlink") and n.enabled and not n.offscreen and n.name and rx.search(n.name)]
        cands += [n for n in nodes if MN._ident(n) == MN._ident(opener) and n.enabled and not n.offscreen]
        why: List[str] = ["no counterpart control"]
        for n in cands[:2]:
            self.fx.node(n)
            tried.append(f"'{n.name}'")
            time.sleep(0.6)
            _forgive_hung()
            why = diff_state(s_par, snapshot(self.hwnd), 0.02 if len(s_par.names) + len(s_par.texts) >= 8 else 0.003)
            if not why:
                return " + ".join(tried), True, ""
        return " + ".join(tried) or "nothing to click", False, "; ".join(why)[:200]

    def _p_reveals(self, label: str, role: str) -> float:
        """The learnt chance that clicking this control OPENS something (a dialog, a page) - the order in which candidates are tried. 0 when no model."""
        if self.learner is None:
            return 0.0
        try:
            pr = self.learner.predict({"app": self.cat.app_key, "toolkit": self.toolkit, "role": MN.VERB_ROLE.get(role, role), "route": "control", "safety": "safe", "source": "reveal",
                                       "archetype": self.archetype, "label": label, "n_controls": len(self.cat.verbs)})
            e = pr.get("effect", {})
            return float(e.get("opens_dialog", 0.0)) + 0.5 * float(e.get("context_change", 0.0))
        except Exception:
            return 0.0

    # ---- one candidate
    def _try(self, c: Cand) -> Dict[str, Any]:
        t0 = time.time()
        self._home()
        s0 = snapshot(self.hwnd)
        home_nodes = self.ex._all_nodes()
        home_ids = {MN._ident(n) for n in home_nodes}
        selected0 = {MN._ident(n) for n in home_nodes if n.role == "tabitem" and n.selected is True}
        v = Verb(verb_id(c.path, c.label), ELLIPSIS_RX.sub("", c.label).strip(), list(c.path), aid=c.aid, role=MN.VERB_ROLE.get(c.role, c.role), sources=["menu-expand"] if c.path else [])
        out: Dict[str, Any] = {"path": " > ".join(c.path + [c.label]), "label": c.label, "kind": "none", "controls": [], "how": "", "left_by": "", "restored": True, "seconds": 0.0}
        with self.fx.holding():
            if c.path:
                self.ex._open_path(v)
            pre_ids = {MN._ident(n) for n in self.ex._all_nodes()}
            node = self.ex._live_node(v)
            if node is None and v.sources:                                        # a ribbon item read through its tab lives in the window, not in a flyout
                v.sources = []
                node = self.ex._live_node(v)
            pending = None
            if node is None and ELLIPSIS_RX.search(c.label or "") and hasattr(self.ex, "trigger_attempt"):
                pending = self.ex.trigger_attempt(v, "deep scan")                    # the worst case of a scan: a dialog's door is unreachable - one capped stand-in is tried
            if node is None and pending is None:
                out["kind"], out["how"] = "unreachable", "the control was not in the live tree after opening its path"
                out["seconds"] = round(time.time() - t0, 1)
                return out
            if pending is not None:
                ok, how = pending[2], pending[3]
                out["how"] = f"trigger? {pending[0].text_path} {pending[1].label()} -> {how}"
            else:
                ok, how = self.fx.node(node)
                out["how"] = how
        for _ in range(6):                                                          # a click that opens a modal surface can leave the application 'Not Responding' while it is parked
            time.sleep(0.5)
            if not app_hung(self.hwnd):
                break
        if app_hung(self.hwnd):
            why = "the application stopped responding after this control was clicked in a parked instance"
            record_hazard(self.cat.app_key, c.label, why)
            out.update(kind="hung", restored=False, still_differs=why, seconds=round(time.time() - t0, 1))
            self.hung = True
            return out
        s1 = self._settle()
        d = delta(s0, s1)
        nodes1 = self.ex._all_nodes()
        main_n = self.ex._main_n
        fresh = [(i, n) for i, n in enumerate(nodes1) if MN._ident(n) not in pre_ids and MN._ident(n) not in home_ids and n.name and not n.offscreen and n.rect[2] > n.rect[0] and n.role in SURFACE_ROLES]
        new = [n for _i, n in fresh]
        actionable = [n for n in new if n.role in MN.ITEM_ROLES]
        in_popup = any(i >= main_n and n.role in MN.ITEM_ROLES for i, n in fresh)                    # its controls live in a window of their own: a dialog
        if d.new_windows or in_popup:
            kind = "dialog"
        elif len(actionable) >= 3:
            kind = "page"
        elif actionable:
            kind = "inline"
        else:
            kind = "none"
        out["kind"] = kind
        out["effect"] = d.effect()
        if pending is not None and kind in ("dialog", "page", "inline") and self.ex.triggers is not None:
            self.ex.triggers.create(v, pending[0], pending[1].label(), f"deep scan: '{c.label}' was unreachable; '{pending[0].text_path}' through {pending[1].kind} opened its {kind}")
            out["trigger"] = pending[0].text_path
        if actionable:
            vpath = list(c.path) + [v.label]
            added = 0
            for n in actionable[:140]:
                added += 1 if MN.add_item_verb(self.cat, self.have, vpath, n, source="reveal") else 0
            out["controls"] = [MN._item_label(n)[0] for n in actionable[:60]]
            out["added"] = added
            for cv in self.cat.verbs:                                              # the opener now says what it opens
                if cv.label == v.label and list(cv.path) == list(c.path) and not cv.leads_to:
                    cv.leads_to = f"opens a {'dialog' if kind == 'dialog' else 'page' if kind == 'page' else 'panel'} ({len(actionable)} controls)"
            if self.on_surface is not None:
                try:
                    self.on_surface(kind, c, actionable)                          # the surface is OPEN right now: a picture of it can be taken
                except Exception:
                    pass
            if kind in ("dialog", "page") and self.max_depth >= 1:
                try:
                    ex = self._explore(vpath, 1, pre_ids | home_ids, time.time() + self.per_surface_s)
                except Exception as exc:
                    ex = {"restored": True, "trail": [f"exploring stopped: {type(exc).__name__}: {str(exc)[:80]}"], "tabs": 0, "tab_controls": 0, "lists": 0, "list_items": 0, "nested": 0, "nested_controls": 0}
                out["inside"] = ex
                out["added"] = out.get("added", 0) + ex.get("tab_controls", 0) + ex.get("list_items", 0) + ex.get("nested_controls", 0)
                if not ex.get("restored", True):
                    out["restored"], out["still_differs"] = False, "a nested dialog could not be closed back to its parent"
                    out["seconds"] = round(time.time() - t0, 1)
                    return out
        self.tried.append((tuple(c.path), c.label))
        how_left, restored, still = self._leave(new, s0, home_ids, selected0, opener=(v if not d.new_windows and kind in ("page", "inline") else None))
        out["left_by"], out["restored"] = how_left, restored
        if not restored:
            out["still_differs"] = still
        if self.history is not None:
            try:
                self.history.log(self.cat.app_key, "reveal", "invoke", c.label, out["how"], s0.sig, f"{len(s0.names)} controls", s1.sig, d.summary()[:120], d.effect(), bool(actionable), restored,
                                 c.aid, {"kind": kind, "new": len(actionable), "left_by": how_left}, toolkit=self.toolkit, archetype=self.archetype, role=MN.VERB_ROLE.get(c.role, c.role), safety="safe")
            except Exception:
                pass
        out["seconds"] = round(time.time() - t0, 1)
        return out

    # ---- the run
    def run(self, read: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        t0 = time.time()
        rep: Dict[str, Any] = {"candidates": 0, "tried": 0, "opened": 0, "dialogs": 0, "pages": 0, "inline": 0, "nothing": 0, "controls": 0, "left_ok": 0, "skipped": [], "surfaces": [],
                               "stopped": "", "tainted": False, "seconds": 0.0}
        if not self.fx.allowed:
            rep["stopped"] = "dry run: " + self.fx.why_not()
            return rep
        self._home()
        main = self.ex._all_nodes()[: self.ex._main_n] if self.ex._all_nodes() else []
        cands, rep["skipped"] = collect(read, main)
        hz = load_hazards(self.cat.app_key)
        if hz:
            rep["skipped"] += [{"path": " > ".join(c.path + [c.label]), "why": "learned hazard: " + hz[c.label]["why"]} for c in cands if c.label in hz]
            cands = [c for c in cands if c.label not in hz]
        if self.learner is not None:
            cands.sort(key=lambda c: -(c.rank + self._p_reveals(c.label, c.role)))
        rep["candidates"] = len(cands)
        streak, taints = 0, {}                                                    # surfaces that could not be proved closed: consecutive count, per-label history
        with self.fx.focus_watch():
            for c in cands[: self.max_surfaces]:
                if time.time() - t0 > self.budget_s:
                    rep["stopped"] = "time budget"
                    break
                try:
                    r = self._try(c)
                except Exception as exc:
                    r = {"path": " > ".join(c.path + [c.label]), "label": c.label, "kind": "error", "how": f"{type(exc).__name__}: {str(exc)[:100]}", "controls": [], "restored": False,
                         "left_by": "", "seconds": round(time.time() - t0, 1)}
                rep["tried"] += 1
                rep["surfaces"].append(r)
                k = r["kind"]
                if k in ("dialog", "page", "inline"):
                    rep["opened"] += 1
                    rep[{"dialog": "dialogs", "page": "pages", "inline": "inline"}[k]] += 1
                    rep["controls"] += int(r.get("added", len(r["controls"])))
                elif k == "none":
                    rep["nothing"] += 1
                if r.get("kind") == "hung":
                    self.tainted = True
                    rep["stopped"] = f"the application stopped responding after '{r['label']}' (recorded as a hazard - never clicked again): exploring stopped"
                    rep["tainted"], rep["app_hung"] = True, True
                    rep["seconds"] = round(time.time() - t0, 1)
                    return rep
                if r.get("restored"):
                    rep["left_ok"] += 1
                    streak = 0
                else:
                    taints[r["label"]] = taints.get(r["label"], 0) + 1
                    streak += 1
                    rep.setdefault("taints", []).append({"path": r["path"], "still": str(r.get("still_differs", ""))[:120]})
                    if taints[r["label"]] >= 2:
                        record_hazard(self.cat.app_key, r["label"], "left a state that could not be proved closed (twice)")
                    if streak >= 3:                                       # three surfaces in a row that will not go back: the home state itself is unreliable, stop
                        self.tainted = True
                        rep["stopped"] = f"three surfaces in a row could not be proved closed (last: '{r['label']}'): exploring stopped"
                        rep["tainted"] = True
                        rep["seconds"] = round(time.time() - t0, 1)
                        return rep
                    # one surface left a residue: the next _try starts from _home() anyway; a still-open modal makes the neighbours read 'unreachable', not dangerous
                    continue
        self._home()
        rep["tainted"] = self.tainted
        rep["app_hung"] = self.hung
        rep["deepest_level"] = self.deepest
        rep["dialog_tabs"] = sum(int((s.get("inside") or {}).get("tabs", 0)) for s in rep["surfaces"])
        rep["nested_dialogs"] = sum(int((s.get("inside") or {}).get("nested", 0)) for s in rep["surfaces"])
        rep["tried_controls"] = [" > ".join(list(p) + [l]) for p, l in self.tried]
        rep["seconds"] = round(time.time() - t0, 1)
        self.cat.sources["reveal"] = self.cat.sources.get("reveal", 0) + rep["controls"]
        self.cat.verbs.sort(key=lambda v: (v.path, v.label.lower()))
        return rep


def reveal_surfaces(ex: Any, fx: Any, hwnd: int, cat: Catalog, read: Sequence[Dict[str, Any]], **kw: Any) -> Dict[str, Any]:
    return Revealer(ex, fx, hwnd, cat, **kw).run(read)


def build_map(cat: Catalog, surfaces: Sequence[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    """The hidden-options map: one row per menu / submenu / dialog / page the scan opened - its path, what kind of surface it is, and the controls found in it."""
    kinds = {s["path"]: s.get("kind", "") for s in surfaces}
    groups: Dict[Tuple[str, ...], List[Verb]] = {}
    for v in cat.verbs:
        if v.path and set(v.sources or []) & {"menu-expand", "reveal"}:
            groups.setdefault(tuple(v.path), []).append(v)
    rows: List[Dict[str, Any]] = []
    for p, vs in sorted(groups.items()):
        path = " > ".join(p)
        revealed = any("reveal" in (x.sources or []) for x in vs)
        kind = kinds.get(path) or ("dialog / page" if revealed else ("submenu" if len(p) > 1 else "menu"))
        rows.append({"path": path, "kind": kind, "count": len(vs), "items": [x.label for x in vs][:40], "depth": len(p)})
    return rows
