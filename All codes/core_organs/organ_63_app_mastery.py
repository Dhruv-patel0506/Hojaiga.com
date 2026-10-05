"""
organ_63_app_mastery.py -- learn HOW an app works, as completely as possible, from first contact, with code only.

The existing scan (universal_scan -> organ_48 E0 + organ_50 layout + a few E1 probes) answers "what is on screen and
where". Mastery answers the questions a pro answers: what are ALL the commands (and their shortcuts / IDs / routes),
what does each control DO, what does each dialog contain, what state does the app have and what moves it, which
universal conventions does it obey, how do I drive it (which input is delivered), what is still unknown.

Nothing is trained and nothing is per-app. Knowledge comes from five generic mechanisms:

  STATIC     static_knowledge: what the program file says (resources, manifest, toolkit, file types)  -- no launch
  STRUCTURAL one bulk UIA snapshot -> state variables (toggles, exclusive groups, tabs, expanders) and a FRONTIER:
             every surface that exists but has not been opened yet, ranked by expected information gain
  EXPLORED   the frontier is opened one surface at a time with a defined, VERIFIED unwind (tab -> select and reselect,
             dropdown -> expand and collapse, dialog opener -> read its schema and close, toggle -> flip and flip back,
             context menu -> read items and close, in-app button -> observe the diff). E2 (destructive) is never touched.
  HYPOTHESIS universal UI conventions (Ctrl+O opens a file dialog, Ctrl+F finds ...) are TESTED on this app, and the
             answer (obeyed / ignored / not deliverable) is recorded, including which input the app actually accepts
  VERIFIED   every effect is recorded as a (state, action, effector) -> (state', evidence) transition; commands are only
             promoted to `learned` by an observed effect with a verified unwind (organ_48's trust law, unchanged)

Runs are cumulative: the frontier persists in the database, so run N+1 continues exactly where run N stopped, and the
per-run measurements (bm_run_log) show the learning curve.

HARD RULES: invisible (BackgroundSession), bounded (DiscoveryBudget / per-probe caps), no physical input, E2 never, a
probe that cannot be unwound stops that probe family, a document that is not pristine is never mutated.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from core_organs import knowledge_store as ks

logger = logging.getLogger("hojaiga.organ_63_app_mastery")

_u32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None

# Extra destructive / outward-facing cues on top of organ_48's E2 regex. Over-blocking is the safe direction: an
# exploration probe that is skipped costs a little knowledge, one that is wrong costs the user something real.
_EXTRA_E2 = re.compile(
    r"\b(share|sign ?(in|out|up)|log ?(in|out)|feedback|download|install|update|upgrade|subscribe|buy|order|donate|invite|"
    r"connect|pair|unlock|activate|register|uninstall|restore defaults?|factory|wipe|shut ?down|restart|sleep|hibernate|"
    r"lock|kill|terminate|end task|empty|permanently|print|scan|burn|record|screen ?shot|new window|open in|open link|"
    r"report|translate|upload|sync|backup|restore|send to|email|"
    # window chrome: pressing these changes the WINDOW (minimised / maximised / snapped), not the app's content, and a
    # parked window that is minimised or maximised stops being scannable
    r"minimi[sz]e|maximi[sz]e|restore down|full ?screen|snap|always on top|keep on top|stay on top|on top|pin to|move|resize|"
    # settings that live OUTSIDE the app (system / network / privacy / security): a toggle there changes the machine, not the app
    r"wi-?fi|bluetooth|airplane|flight mode|vpn|firewall|defender|antivirus|proxy|hotspot|location|microphone|camera|password|"
    r"credential|privacy|startup|boot|bios|registry|driver|service|permission|administrator|elevat)\b", re.I)

SETTLE_S = 0.6


def is_unsafe(name: str, path: str = "") -> bool:
    from core_organs import organ_48_app_behavior_model as bm
    return bm.classify_risk(name, path) == "E2" or bool(_EXTRA_E2.search(f"{name} {path}"))


# ===========================================================================
# 1. State variables (mode indicators) from ONE bulk snapshot
# ===========================================================================

_TOGGLE = {0: "off", 1: "on", 2: "mixed"}
_OPERABLE = {"ButtonControl", "MenuItemControl", "TabItemControl", "ComboBoxControl", "SplitButtonControl",
             "CheckBoxControl", "RadioButtonControl", "ListItemControl", "TreeItemControl", "HyperlinkControl"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _chain(nodes, idx: int, depth: int = 3) -> str:
    """Names of the nearest named ancestors ('Toolbar > Format'): where a control lives, stable across runs."""
    out: List[str] = []
    p = nodes[idx].parent
    while p >= 0 and len(out) < depth:
        n = nodes[p]
        nm = (n.name or n.aid or "").strip()
        if nm and n.ctype not in ("WindowControl",):
            out.append(nm[:24])
        p = n.parent
    return " > ".join(reversed(out))


def _var_id(kind: str, name: str, aid: str, where: str) -> str:
    return hashlib.md5(f"{kind}|{_norm(name)}|{aid}|{_norm(where)}".encode()).hexdigest()[:12]


def derive_state(nodes) -> Dict[str, Any]:
    """The app's state variables as the UI exposes them right now:
         toggle     check boxes / toggle buttons                       -> off | on | mixed
         exclusive  siblings that are mutually selected (tabs, radios, tools) -> the selected one's name
         expand     collapsed/expanded containers (dropdowns, tree nodes, flyouts)  -> collapsed | expanded
    Returns {'vars': [{var_id,name,kind,value,group,aid}], 'signature', 'modes': ['name|on', ...]}."""
    out: List[Dict[str, Any]] = []
    groups: Dict[int, List[int]] = {}
    for n in nodes:
        if not n.name or n.ctype in ("TextControl", "WindowControl", "PaneControl", "ImageControl"):
            if not (n.name and n.toggle_state >= 0):
                continue
        where = _chain(nodes, n.idx)
        if n.toggle_state >= 0:
            out.append({"var_id": _var_id("toggle", n.name, n.aid, where), "name": n.name, "kind": "toggle",
                        "value": _TOGGLE.get(n.toggle_state, str(n.toggle_state)), "group": where, "aid": n.aid})
        elif n.selected is not None and n.parent >= 0:
            groups.setdefault(n.parent, []).append(n.idx)
        elif n.expand_state in (0, 1) and n.ctype not in ("MenuItemControl",):
            out.append({"var_id": _var_id("expand", n.name, n.aid, where), "name": n.name, "kind": "expand",
                        "value": "expanded" if n.expand_state == 1 else "collapsed", "group": where, "aid": n.aid})
    for parent, members in groups.items():
        if len(members) < 2:
            continue                                   # one selectable thing is not a mode
        pn = nodes[parent]
        gname = (pn.name or pn.aid or pn.ctype.replace("Control", "")).strip()
        sel = [nodes[i].name for i in members if nodes[i].selected]
        where = _chain(nodes, members[0])
        out.append({"var_id": _var_id("exclusive", gname, pn.aid, where), "name": gname, "kind": "exclusive",
                    "value": sel[0] if sel else "(none)", "group": where, "aid": pn.aid,
                    "choices": [nodes[i].name for i in members]})
    out.sort(key=lambda v: (v["kind"], v["name"].lower()))
    sig = hashlib.md5("|".join(f"{v['var_id']}={v['value']}" for v in out).encode()).hexdigest()[:12]
    modes = [f"{_norm(v['name'])}|{v['value']}" for v in out if v["kind"] in ("toggle", "expand") and v["value"] != "off"
             and v["value"] != "collapsed"] + [f"{_norm(v['value'])}|selected" for v in out if v["kind"] == "exclusive"]
    return {"vars": out, "signature": sig, "modes": modes}


def record_state_vars(model, app_key: str, state: Dict[str, Any]) -> int:
    n = 0
    for v in state["vars"]:
        ks.put_statevar(model, app_key, v["var_id"], v["name"], v["kind"], v.get("choices") or [v["value"]],
                        group_id=v.get("group", ""), aid=v.get("aid", ""))
        if v["kind"] == "exclusive":                     # also remember the value seen
            ks.put_statevar(model, app_key, v["var_id"], v["name"], v["kind"], [v["value"]], group_id=v.get("group", ""), aid=v.get("aid", ""))
        n += 1
    return n


# ===========================================================================
# 2. Observation helpers (Win32 for window sets, one bulk UIA snapshot for content)
# ===========================================================================

def _snap_all(hwnd: int, *, popups: bool = True, main_timeout_ms: int = 6000) -> Tuple[List[Any], List[Any]]:
    """(main-window nodes, popup-window nodes). One bounded CacheRequest per window."""
    from core_organs import fast_uia
    from core_organs import organ_48_app_behavior_model as bm
    main = fast_uia.snapshot(hwnd, timeout_ms=main_timeout_ms) or []
    extra: List[Any] = []
    if popups:
        for w in bm._open_popups(hwnd)[:6]:
            extra += fast_uia.snapshot(w, timeout_ms=3000) or []
    return main, extra


def _names(nodes) -> set:
    return {_norm(n.name) for n in nodes if n.name and _norm(n.name) != "pop-uphost"}


def _op_names(nodes) -> set:
    """Names of OPERABLE controls only (buttons, items, tabs ...). The STRUCTURE of an app's UI, as opposed to its content:
    a calculator display changing is content; its keypad disappearing behind a flyout is structure."""
    return {_norm(n.name) for n in nodes if n.name and n.ctype in _OPERABLE and _norm(n.name) != "pop-uphost"}


def _observed(hwnd: int, nodes, state: Optional[Dict[str, Any]] = None):
    """organ_48 ObservedState built from a snapshot already in hand (no second walk)."""
    from core_organs import organ_48_app_behavior_model as bm
    wins = sorted({(bm._win_title(w) or bm._win_class(w)).lower() for w in bm._open_popups(hwnd)})
    st = bm.ObservedState(title=bm._win_title(hwnd), names=sorted(_names(nodes)), windows=wins, hwnd=hwnd)
    st.mode = (state or derive_state(nodes))["signature"]
    return st


def _uia_call(node, getter: str, call: str, wait_s: float = 2.0) -> Tuple[bool, str]:
    """Run one UIA pattern call on a snapshot node on its own thread: a call that opens a MODAL surface does not return
    until it closes, so 'still running after wait_s' means 'dispatched'. Returns (ok, how)."""
    import threading
    box: Dict[str, Any] = {"res": None}

    def _w():
        try:
            import uiautomation as auto
            with auto.UIAutomationInitializerInThread():
                ctrl = node.ctrl
                if hasattr(ctrl, getter):
                    pat = getattr(ctrl, getter)()
                else:                                          # e.g. a RadioButtonControl that exposes ExpandCollapse
                    pat = ctrl.GetPattern(getattr(auto.PatternId, getter[3:]))
                if pat is None:
                    raise RuntimeError("pattern not supported")
                getattr(pat, call)()
                box["res"] = (True, f"uia-{call.lower()}")
        except Exception as exc:
            box["res"] = (False, f"{type(exc).__name__}: {str(exc)[:60]}")
    th = threading.Thread(target=_w, daemon=True, name="uia-probe")
    th.start()
    th.join(wait_s)
    return box["res"] or (True, "dispatched (call still running: a modal surface opened)")


def _settle(hwnd: int, timeout_s: float = 1.2) -> None:
    """Bounded wait until the shell of the app (title + popup set) stops changing."""
    from core_organs import organ_48_app_behavior_model as bm
    last, stable, end = None, 0, time.time() + timeout_s
    while time.time() < end and stable < 2:
        bm._keep_hidden(hwnd)
        sig = bm.TemplateRunner._cheap_sig(hwnd)
        stable = stable + 1 if sig == last else 0
        last = sig
        time.sleep(0.12)


def close_popups(hwnd: int, baseline: List[int], timeout_s: float = 2.5) -> bool:
    """Unwind every popup/dialog that was not there at baseline. Escape first, then WM_CLOSE (XAML hosts ignore posted
    keys; measured: a context menu stayed open after Escape and closed with WM_CLOSE). True when the set is baseline."""
    from core_organs import organ_48_app_behavior_model as bm
    return bm._close_new_windows(hwnd, baseline, timeout_s=timeout_s)


# ===========================================================================
# 3. Dialog / surface schema
# ===========================================================================

_COMMIT = re.compile(r"^(ok|save|open|apply|yes|done|finish|select|add|create|continue|next|install|accept|go|find next|replace)\b", re.I)
_CANCEL = re.compile(r"^(cancel|close|no|back|exit|dismiss|discard|abort)\b", re.I)
_KIND = {"ButtonControl": "button", "CheckBoxControl": "checkbox", "RadioButtonControl": "radio", "EditControl": "edit",
         "ComboBoxControl": "combobox", "ListControl": "list", "ListItemControl": "listitem", "TabItemControl": "tab",
         "SliderControl": "slider", "SpinnerControl": "spinner", "TreeControl": "tree", "TreeItemControl": "treeitem",
         "DataGridControl": "grid", "TextControl": "label", "HyperlinkControl": "link", "SplitButtonControl": "splitbutton",
         "MenuItemControl": "menuitem", "DocumentControl": "document", "ProgressBarControl": "progress",
         "GroupControl": "group", "TableControl": "table"}


def schema_from_nodes(nodes) -> List[Dict[str, Any]]:
    out = []
    for n in nodes:
        k = _KIND.get(n.ctype)
        if not k or (k == "label" and not n.name):
            continue
        d = {"kind": k, "name": n.name, "aid": n.aid, "enabled": n.enabled, "patterns": list(n.pats)}
        if n.toggle_state >= 0:
            d["state"] = _TOGGLE.get(n.toggle_state, "")
        out.append(d)
    return out


def schema_from_win32(w: int) -> List[Dict[str, Any]]:
    from core_organs import organ_48_app_behavior_model as bm
    kmap = {"button": "button", "edit": "edit", "combobox": "combobox", "comboboxex32": "combobox", "listbox": "list",
            "syslistview32": "list", "systreeview32": "tree", "static": "label", "msctls_trackbar32": "slider",
            "richedit20w": "edit", "richedit50w": "edit"}
    out = []
    for k in bm.win32_window_controls(w):
        out.append({"kind": kmap.get(k["class"].lower(), k["class"].lower()), "name": k["name"], "aid": "", "enabled": True, "patterns": []})
    return out


def dialog_roles(controls: List[Dict[str, Any]]) -> Dict[str, Any]:
    """commit / cancel buttons and the fields of a dialog: what a task needs to fill it in and to back out of it."""
    buttons = [c["name"] for c in controls if c["kind"] in ("button", "splitbutton") and c["name"]]
    commit = next((b for b in buttons if _COMMIT.match(b)), "")
    cancel = next((b for b in buttons if _CANCEL.match(b)), "")
    fields = [c["name"] or c.get("aid", "") for c in controls if c["kind"] in ("edit", "combobox", "spinner", "slider")]
    return {"commit": commit, "cancel": cancel, "fields": [f for f in fields if f][:12],
            "toggles": [c["name"] for c in controls if c["kind"] in ("checkbox", "radio") and c["name"]][:12]}


def capture_dialogs(model, app_key: str, windows: List[int], via: str) -> List[Dict[str, Any]]:
    """Read the full control schema of every NEW window (while it is open) and persist it. Win32 enumeration for classic
    #32770 dialogs (instant, cannot hang on a slow provider), one bounded UIA snapshot for everything else."""
    from core_organs import fast_uia
    from core_organs import organ_48_app_behavior_model as bm
    got = []
    for w in windows:
        title = bm._win_title(w) or bm._win_class(w)
        cls = bm._win_class(w)
        controls: List[Dict[str, Any]] = []
        src = "live:win32"
        if cls == "#32770":
            controls = schema_from_win32(w)
        if len(controls) < 2:
            snap = fast_uia.snapshot(w, max_nodes=3000, timeout_ms=3000)
            if snap:
                controls, src = schema_from_nodes(snap), "live:uia"
        if not controls:
            continue
        roles = dialog_roles(controls)
        did = ks.put_dialog(model, app_key, title, controls + [{"kind": "_roles", **roles}], source=src, via=via)
        got.append({"dialog_id": did, "title": title, "n": len(controls), **roles})
    return got


# ===========================================================================
# 4. Frontier: every surface that exists but has not been opened
# ===========================================================================

_GAIN = {"tab": 0.95, "opener": 0.85, "context": 0.75, "expander": 0.65, "toggle": 0.5, "button": 0.4}


_SINK_CLASS = re.compile(r"(InputSink|InputSite|ApplicationFrame|Chrome_|Intermediate|DesktopWindowXaml|XamlHost)", re.I)


def _in_titlebar(nodes, n) -> bool:
    """Window chrome (caption buttons, system menu) lives under the title bar: not part of the app's own UI."""
    p = n.parent
    while p >= 0:
        if nodes[p].ctype == "TitleBarControl":
            return True
        p = nodes[p].parent
    if n.ctype == "TitleBarControl":
        return True
    if (n.name or "").strip().lower() == "system" and n.ctype == "MenuItemControl":
        par = nodes[n.parent] if n.parent >= 0 else None
        return par is not None and par.ctype == "MenuBarControl" and (par.name or "").strip().lower() == "system"   # the window's own system menu
    return False


def _is_menubar_item(nodes, n) -> bool:
    p = n.parent
    while p >= 0:
        if nodes[p].ctype in ("MenuBarControl",):
            return True
        p = nodes[p].parent
    return False


def populate_frontier(model, app_key: str, hwnd: int, nodes, version_hash: str = "", *, max_new: int = 400) -> Dict[str, int]:
    """Turn a snapshot into frontier rows (idempotent). Destructive-looking controls are recorded as `unsafe` immediately:
    knowing that they exist, and that they are never explored, is knowledge too."""
    added: Dict[str, int] = {}
    win_area = 0
    for n in nodes[:1]:
        win_area = max(1, (n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1]))
    count = 0
    for n in nodes:
        if count >= max_new:
            break
        name = (n.name or "").strip()
        if not name or not n.enabled or _in_titlebar(nodes, n):
            continue
        kind = ""
        pats = set(n.pats)
        where = _chain(nodes, n.idx)
        if n.ctype == "TabItemControl" and "select" in pats and n.selected is False:
            kind = "tab"
        elif _is_menubar_item(nodes, n):
            continue                                         # the menu bar is E0's job (crawl), not a frontier item
        elif n.ctype in _OPERABLE and "toggle" in pats and n.toggle_state in (0, 1, 2):
            kind = "toggle"
        elif "expand" in pats and n.expand_state == 0 and n.ctype not in ("MenuItemControl", "TreeItemControl"):
            kind = "expander"
        elif n.ctype in ("ButtonControl", "MenuItemControl", "SplitButtonControl") and "invoke" in pats:
            kind = "opener" if re.search(r"(\.\.\.|…)\s*$", name) else "button"
        if not kind:
            continue
        personal = ks.redact(name) != name
        if personal:
            name = ks.redact(name)                       # the account / person behind a 'Signed in as ...' label is never stored
        path = f"{ks.redact(where)} > {name}" if where else name
        fid = ks.frontier_add(model, app_key, kind, name, path, info_gain=_GAIN[kind], version_hash=version_hash)
        if personal:
            ks.frontier_done(model, fid, "unsafe", {"why": "account / person label: recorded without the person, never pressed"})
        elif is_unsafe(name, path):
            ks.frontier_done(model, fid, "unsafe", {"why": "destructive/outward-facing cue; never explored"})
        added[kind] = added.get(kind, 0) + 1
        count += 1
    # context-menu targets: large content regions + tab strips (spatial, not named)
    targets = 0
    for n in nodes:
        if targets >= 6:
            break
        if n.ctype in ("DocumentControl", "EditControl", "ListControl", "TreeControl", "DataGridControl", "TableControl",
                       "PaneControl", "ImageControl", "TabControl") and n.rect[2] > n.rect[0] and n.rect[3] > n.rect[1]:
            area = (n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1])
            if n.ctype in ("PaneControl", "ImageControl") and area < 0.08 * win_area:
                continue
            if n.ctype == "TabControl" and area > 0.3 * win_area:
                continue
            if not n.name and not n.aid and _SINK_CLASS.search(n.cls or ""):
                continue                                       # framework plumbing, not a place with its own context menu
            label = (n.name or n.aid or n.cls or n.ctype.replace("Control", "")).strip()[:40]
            ks.frontier_add(model, app_key, "context", label, f"{_chain(nodes, n.idx)} > {label}".strip(" >"),
                            info_gain=_GAIN["context"], version_hash=version_hash)
            added["context"] = added.get("context", 0) + 1
            targets += 1
    return added


# ===========================================================================
# 5. Probes (each: act -> observe -> capture knowledge -> UNWIND -> verify)
# ===========================================================================

@dataclass
class ProbeResult:
    fid: str
    kind: str
    label: str
    status: str = "failed"          # explored | no_effect | unsafe | failed | skipped
    effect: str = ""                # window | inline | state | menu | none
    new_controls: List[str] = field(default_factory=list)
    windows: List[str] = field(default_factory=list)
    unwound: bool = True
    effector: str = ""
    evidence: str = ""
    elapsed_s: float = 0.0
    detail_unwind: Dict[str, Any] = field(default_factory=dict)   # why an unwind check failed (diagnostic)
    items: int = 0                  # knowledge items produced (commands/dialog controls/regions) for the budget's yield test

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class Prober:
    """Executes probes against ONE live window. Re-finds each control by identity in a fresh snapshot (stale nodes from an
    earlier snapshot are never used), so a probe works after the UI changed."""

    def __init__(self, model, app_key: str, hwnd: int, *, pristine: bool = True, run_id: str = ""):
        from core_organs import organ_48_app_behavior_model as bm
        self.model, self.key, self.hwnd, self.run_id = model, app_key, hwnd, run_id
        self.bm = bm
        self.pristine = pristine
        self.ladder = bm.EffectorLadder(model)
        self.dirty = 0
        self.broken = False
        self.base_ops: Optional[set] = None          # operable control names at the start: the structure to come back to
        self.base_open: List[int] = []
        self.open_label = ""                         # last control that opened a surface (to close it again)
        self.in_via = False

    # ---- locating ------------------------------------------------------------------
    def find(self, nodes, label: str, kind: str = "", path: str = ""):
        """Best node for a frontier row: exact name (+ ancestor chain) among nodes of a compatible type."""
        want = _norm(label)
        cands = [n for n in nodes if _norm(n.name) == want]
        if kind == "tab":
            cands = [n for n in cands if n.ctype == "TabItemControl"] or cands
        if len(cands) > 1 and path:
            tail = _norm(path.rsplit(">", 1)[0])
            best = [n for n in cands if _norm(_chain(nodes, n.idx)) == tail]
            cands = best or cands
        return cands[0] if cands else None

    # ---- shared bookkeeping ----------------------------------------------------------
    def _transition(self, before_nodes, after_nodes, action: str, effector: str, evidence: str) -> None:
        try:
            b = _observed(self.hwnd, before_nodes)
            a = _observed(self.hwnd, after_nodes)
            self.model.record_transition(self.key, b, action, effector, a, evidence)
        except Exception as exc:
            logger.debug("[mastery] transition not recorded: %s", exc)

    def _promote(self, label: str, path: str, verb: str, post: List[dict], evidence: str, risk: str = "E1") -> None:
        """An observed effect with a verified unwind earns the command `learned` (organ_48 trust law)."""
        cid = self.model.upsert_command(self.key, {"name": label, "goal": label, "menu_path": path, "verb": verb, "risk": risk,
                                                   "post": post, "unwind": "verified"},
                                        source="catalog", origin="e1:mastery", evidence=evidence)
        self.model.command_outcome(cid, "PASS", evidence, promote=True)

    # ---- tab ----------------------------------------------------------------------
    def probe_tab(self, row: Dict[str, Any]) -> ProbeResult:
        r = ProbeResult(row["fid"], "tab", row["label"])
        t0 = time.time()
        main, _ = _snap_all(self.hwnd, popups=False)
        node = self.find(main, row["label"], "tab", row["path"])
        if node is None:
            r.status, r.evidence = "failed", "tab not found in the live tree"
            return r
        before_names = _names(main)
        before_state = derive_state(main)
        prev = next((n for n in main if n.ctype == "TabItemControl" and n.selected and n.parent == node.parent), None)
        ok, how = _uia_call(node, "GetSelectionItemPattern", "Select", 2.0)
        r.effector = how
        _settle(self.hwnd, 1.0)
        after, _ = _snap_all(self.hwnd, popups=False)
        new = sorted(_names(after) - before_names)
        gone = sorted(before_names - _names(after))
        r.new_controls = new[:60]
        # unwind: reselect what was selected (or leave when there was no previous selection)
        if prev is not None:
            pn = self.find(after, prev.name, "tab", "")
            if pn is not None:
                _uia_call(pn, "GetSelectionItemPattern", "Select", 2.0)
                _settle(self.hwnd, 0.8)
        back, _ = _snap_all(self.hwnd, popups=False)
        r.unwound = derive_state(back)["signature"] == before_state["signature"] or prev is None
        if not ok:
            r.status, r.evidence = "failed", f"select failed ({how})"
        elif new or gone:
            r.status, r.effect = "explored", "inline"
            r.evidence = f"tab '{row['label']}' revealed {len(new)} control(s), hid {len(gone)}; unwind={'ok' if r.unwound else 'FAILED'}"
            self.model.record_region(self.key, f"tab:{row['label']}", [{"name": n, "type": "control", "parent_tab": row["label"]} for n in new], via="mastery:tab")
            by_name = {_norm(n.name): n for n in after if n.name and n.ctype in _OPERABLE}
            for nm in new[:200]:
                nd = by_name.get(nm)
                cmd = {"name": (nd.name if nd is not None else nm), "goal": nm, "menu_path": f"{row['label']} > {(nd.name if nd is not None else nm)}",
                       "verb": "invoke", "risk": "EU"}
                ev = f"visible only on tab '{row['label']}'"
                if nd is not None:
                    if nd.accel:
                        cmd["shortcut"] = self.bm._norm_chord(nd.accel)
                    if nd.help:
                        ev += f"; help={nd.help[:120]}"
                self.model.upsert_command(self.key, cmd, source="catalog", origin="e1:tab-content", evidence=ev)
            r.items = len(new)
            self._transition(main, after, f"select_tab:{row['label']}", how, r.evidence)
            self._promote(row["label"], row["path"], "invoke", [{"kind": "element_appeared", "name": new[0]}], r.evidence)
        else:
            r.status, r.effect = "no_effect", "none"
            r.evidence = "selecting the tab changed no names"
        return r

    # ---- expander (dropdown / split button / flyout / tree node) ---------------------
    def probe_expander(self, row: Dict[str, Any]) -> ProbeResult:
        r = ProbeResult(row["fid"], "expander", row["label"])
        main, extra = _snap_all(self.hwnd)
        node = self.find(main, row["label"], "expander", row["path"])
        if node is None:
            r.status, r.evidence = "failed", "control not found"
            return r
        base_popups = list(self.bm._open_popups(self.hwnd))
        before_names = _names(main) | _names(extra)
        ok, how = _uia_call(node, "GetExpandCollapsePattern", "Expand", 2.0)
        r.effector = how
        _settle(self.hwnd, 1.0)
        main2, extra2 = _snap_all(self.hwnd)
        new_pop = [w for w in self.bm._open_popups(self.hwnd) if w not in base_popups]
        new = sorted((_names(main2) | _names(extra2)) - before_names)
        items = [n.name for n in (main2 + extra2) if n.ctype in ("MenuItemControl", "ListItemControl", "ButtonControl") and n.name and _norm(n.name) in set(new)]
        r.new_controls = new[:80]
        # unwind: collapse through the same pattern, then close any popup window it opened
        fresh, _ = _snap_all(self.hwnd, popups=False)
        again = self.find(fresh, row["label"], "expander", row["path"])
        if again is not None:
            _uia_call(again, "GetExpandCollapsePattern", "Collapse", 1.5)
        if new_pop:
            close_popups(self.hwnd, base_popups)
        _settle(self.hwnd, 0.8)
        # a XAML flyout closes with an animation and its host keeps a (hidden) subtree for a moment: poll, bounded
        t_end = time.time() + 2.5
        while time.time() < t_end and [w for w in self.bm._open_popups(self.hwnd) if w not in base_popups]:
            if new_pop:
                close_popups(self.hwnd, base_popups, timeout_s=0.8)
            time.sleep(0.3)
        back, back_extra = _snap_all(self.hwnd)
        still_open = [w for w in self.bm._open_popups(self.hwnd) if w not in base_popups]
        d_now, d_then = _op_names(back + back_extra), _op_names(main + extra)
        r.unwound = (not still_open) and d_now == d_then
        if not r.unwound:
            r.detail_unwind = {"popups_left": len(still_open), "appeared": sorted(d_now - d_then)[:6], "vanished": sorted(d_then - d_now)[:6]}
        if not ok:
            r.status, r.evidence = "failed", f"expand failed ({how})"
        elif new:
            r.status, r.effect = "explored", "menu" if new_pop or items else "inline"
            r.evidence = f"'{row['label']}' opened {len(new)} item(s) ({', '.join(new[:5])}); unwind={'ok' if r.unwound else 'FAILED ' + str(r.detail_unwind)}"
            self.model.record_region(self.key, f"dropdown:{row['label']}", [{"name": n, "type": "item", "parent_menu": row["label"]} for n in new], via="mastery:expander")
            for n in (main2 + extra2):
                if n.ctype in ("MenuItemControl", "ListItemControl", "ButtonControl") and n.name and _norm(n.name) in set(new):
                    cmd = {"name": n.name, "goal": n.name, "menu_path": f"{row['label']} > {n.name}", "verb": "invoke", "risk": "EU"}
                    if n.accel:
                        cmd["shortcut"] = self.bm._norm_chord(n.accel)
                    self.model.upsert_command(self.key, cmd, source="catalog", origin="e1:dropdown-items",
                                              evidence=f"inside '{row['label']}'" + (f"; help={n.help[:120]}" if n.help else ""))
            r.items = len(new)
            self._transition(main, main2, f"expand:{row['label']}", how, r.evidence)
            self._promote(row["label"], row["path"], "invoke", [{"kind": "element_appeared", "name": new[0]}], r.evidence)
        else:
            r.status, r.effect, r.evidence = "no_effect", "none", "expanding revealed nothing new"
        return r

    # ---- toggle -------------------------------------------------------------------
    def probe_toggle(self, row: Dict[str, Any]) -> ProbeResult:
        r = ProbeResult(row["fid"], "toggle", row["label"])
        main, _ = _snap_all(self.hwnd, popups=False)
        node = self.find(main, row["label"], "toggle", row["path"])
        if node is None:
            r.status, r.evidence = "failed", "control not found"
            return r
        v0 = node.toggle_state
        before_state = derive_state(main)
        siblings_on = [_norm(n.name) for n in main if n.parent == node.parent and n.idx != node.idx and n.toggle_state == 1 and n.name]
        ok, how = _uia_call(node, "GetTogglePattern", "Toggle", 2.0)
        r.effector = how
        _settle(self.hwnd, 0.8)
        after, _ = _snap_all(self.hwnd, popups=False)
        node2 = self.find(after, row["label"], "toggle", row["path"])
        v1 = node2.toggle_state if node2 is not None else -1
        new = sorted(_names(after) - _names(main))
        r.new_controls = new[:40]
        if node2 is not None and v1 != v0:                     # unwind: toggle straight back
            _uia_call(node2, "GetTogglePattern", "Toggle", 2.0)
            _settle(self.hwnd, 0.6)
        back, _ = _snap_all(self.hwnd, popups=False)
        node3 = self.find(back, row["label"], "toggle", row["path"])
        r.unwound = node3 is not None and node3.toggle_state == v0
        if not r.unwound:
            r.detail_unwind = {"was": v0, "now": node3.toggle_state if node3 is not None else None, "siblings_on": siblings_on[:4]}
        if not r.unwound and siblings_on:
            # exclusive group (tools / view modes): the control cannot be switched off, selecting it switched ANOTHER one off.
            # Put the previous one back, then check the whole group is as it was.
            for sn in back:
                if sn.parent == (node3.parent if node3 is not None else node.parent) and _norm(sn.name) in siblings_on and sn.toggle_state == 0:
                    _uia_call(sn, "GetTogglePattern", "Toggle", 2.0)
            _settle(self.hwnd, 0.7)
            back2, _ = _snap_all(self.hwnd, popups=False)
            group_now = {_norm(n.name): n.toggle_state for n in back2 if n.parent == node.parent and n.toggle_state >= 0 and n.name}
            group_then = {_norm(n.name): n.toggle_state for n in main if n.parent == node.parent and n.toggle_state >= 0 and n.name}
            r.unwound = group_now == group_then
            if r.unwound:
                r.evidence = "exclusive group restored: "
        if ok and v1 != v0 and v1 != -1:
            r.status, r.effect = "explored", "state"
            vals = [_TOGGLE.get(v0, str(v0)), _TOGGLE.get(v1, str(v1))]
            r.evidence = f"'{row['label']}' toggles {vals[0]} <-> {vals[1]}; unwind={'ok' if r.unwound else 'FAILED'}" + \
                         (f"; revealed {len(new)} control(s)" if new else "")
            ks.put_statevar(self.model, self.key, _var_id("toggle", row["label"], node.aid, _chain(main, node.idx)), row["label"], "toggle",
                            vals, group_id=_chain(main, node.idx), aid=node.aid)
            r.items = 1 + len(new)
            self._transition(main, after, f"toggle:{row['label']}", how, r.evidence)
            self._promote(row["label"], row["path"], "invoke", [{"kind": "ui_changed"}], r.evidence)
        else:
            r.status, r.effect, r.evidence = "no_effect", "none", f"toggle state stayed {_TOGGLE.get(v0, v0)}"
        return r

    # ---- dialog opener / in-app button (windows are detected with Win32 only) -------------
    def probe_invoke(self, row: Dict[str, Any]) -> ProbeResult:
        """Invoke ONE control that is expected to open a window (ellipsis) or to do something unknown (EU button).
        Outcomes: a WINDOW (dialog schema captured, closed), a SURFACE (flyout / pane / list revealed inline: its items
        become commands + deeper frontier rows, then it is closed), or a MUTATION (content / state changed: recorded as a
        transition relative to the new state, never undone blindly)."""
        r = ProbeResult(row["fid"], row["kind"], row["label"])
        main, extra = _snap_all(self.hwnd)
        node = self.find(main + extra, row["label"], row["kind"], row["path"])
        if node is None:
            r.status, r.evidence = "failed", "control not found"
            return r
        base_open = list(self.bm._open_popups(self.hwnd))
        before_state = derive_state(main)
        before_names = _names(main) | _names(extra)
        ok, how = self.invoke_node(node)
        r.effector = how
        # an ellipsis control promises a dialog: wait for it. An unknown button usually acts inline: look briefly.
        deadline = time.time() + (2.5 if row["kind"] == "opener" else 0.7)
        new_hwnds: List[int] = []
        while ok and time.time() < deadline:
            time.sleep(0.1)
            self.bm._keep_hidden(self.hwnd)
            new_hwnds = [w for w in self.bm._open_popups(self.hwnd) if w not in base_open]
            if new_hwnds:
                break
        if new_hwnds:
            time.sleep(0.25)                                   # let it populate
            got = capture_dialogs(self.model, self.key, new_hwnds, via=f"{row['path']}")
            r.windows = [g["title"] for g in got] or [(self.bm._win_title(w) or self.bm._win_class(w)) for w in new_hwnds]
            r.new_controls = [f"{g['title']}: {g['n']} controls (commit={g['commit'] or '-'}, cancel={g['cancel'] or '-'})" for g in got]
            r.items = sum(g["n"] for g in got)
            r.unwound = close_popups(self.hwnd, base_open)
            t_end = time.time() + 2.0                          # a flyout host keeps its subtree for a moment after it closes
            while time.time() < t_end and [w for w in self.bm._open_popups(self.hwnd) if w not in base_open]:
                time.sleep(0.25)
            r.unwound = r.unwound or not [w for w in self.bm._open_popups(self.hwnd) if w not in base_open]
            back, back_x = _snap_all(self.hwnd)
            r.unwound = r.unwound and _op_names(back + back_x) == _op_names(main + extra)
            r.status, r.effect = ("explored" if got else "no_effect"), "window"
            r.evidence = f"opened {r.windows[:2]}; {r.items} control(s) captured; unwind={'ok' if r.unwound else 'FAILED'}"
            if got:
                after_obs = _observed(self.hwnd, main)
                after_obs.windows = sorted(set(after_obs.windows) | {w.lower() for w in r.windows})
                self.model.record_transition(self.key, _observed(self.hwnd, main), f"invoke:{row['label']}", how, after_obs, r.evidence)
                self._promote(row["label"], row["path"], "invoke", [{"kind": "window_opened", "title_contains": r.windows[0].lower()}], r.evidence)
            return r
        # no window: an inline effect?
        _settle(self.hwnd, 0.7)
        after, after_extra = _snap_all(self.hwnd)
        names_after = _names(after) | _names(after_extra)
        new = sorted(names_after - before_names)
        gone = sorted(before_names - names_after)
        st_after = derive_state(after)
        r.new_controls = new[:40]
        if not ok:
            r.status, r.evidence = "failed", f"invoke not delivered ({how})"
            return r
        if not (new or gone or st_after["signature"] != before_state["signature"]):
            r.status, r.effect, r.evidence = "no_effect", "none", "no observable change"
            return r
        # SURFACE (a flyout / pane / list: >= 3 operable controls appeared, or >= 3 disappeared behind it, or a popup window
        # is open) or MUTATION (display / state changed, the structure is the same)
        new_set = set(new)
        operable_new = [n for n in (after + after_extra) if n.ctype in _OPERABLE and n.name and _norm(n.name) in new_set]
        ops_gone = _op_names(main + extra) - _op_names(after + after_extra)
        popups_differ = self.bm._open_popups(self.hwnd) != base_open
        r.status = "explored"
        self._transition(main, after, f"invoke:{row['label']}", how, f"+{len(new)} -{len(gone)} names")
        if len(operable_new) >= 3 or len(ops_gone) >= 3 or popups_differ:
            r.effect = "surface"
            for n in operable_new[:120]:
                cmd = {"name": n.name, "goal": n.name, "menu_path": f"{row['label']} > {n.name}", "verb": "invoke", "risk": "EU"}
                if n.accel:
                    cmd["shortcut"] = self.bm._norm_chord(n.accel)
                self.model.upsert_command(self.key, cmd, source="catalog", origin="e1:surface-items",
                                          evidence=f"revealed by '{row['label']}'" + (f"; help={n.help[:120]}" if n.help else ""))
                # children are only reachable through their opener; a chain of openers (via inside via) is not supported, so a
                # surface found while already inside one registers its items as knowledge but no deeper frontier rows
                if (not self.in_via and n.ctype in ("ButtonControl", "MenuItemControl", "ListItemControl", "TabItemControl")
                        and not is_unsafe(n.name)):
                    ks.frontier_add(self.model, self.key, "button", n.name, f"@via:{row['label']}@ {row['label']} > {n.name}",
                                    info_gain=0.3)
            self.open_label = row["label"]
            self.model.record_region(self.key, f"surface:{row['label']}", [{"name": n.name, "type": n.ctype, "parent_menu": row["label"]} for n in operable_new[:200]],
                                     via="mastery:invoke")
            r.items = len(operable_new)
            r.unwound = self.unwind_surface(row["label"], base_open, _op_names(main + extra))
            if r.unwound:
                self.open_label = ""
            r.evidence = (f"'{row['label']}' opened a surface with {len(operable_new)} control(s) ({', '.join(n.name for n in operable_new[:4])}); "
                          f"unwind={'ok' if r.unwound else 'FAILED'}")
            if r.unwound:
                self._promote(row["label"], row["path"], "invoke", [{"kind": "element_appeared", "name": operable_new[0].name}], r.evidence)
        else:
            r.effect = "mutation"
            r.items = len(new) + 1
            r.unwound = False                                  # content changed: not restored on purpose
            r.evidence = (f"'{row['label']}' changed content/state: +{len(new)} -{len(gone)} names "
                          f"({', '.join(new[:3])}); recorded as a transition from the new state")
            self.dirty += 1
        return r

    def unwind_surface(self, opener_label: str, base_open: List[int], before_names: set) -> bool:
        """Close what an inline control opened. Ladder (stop at the first that restores the baseline): popup windows ->
        press the opener again (toggle) -> the surface's own Close / Back / Cancel control."""
        for step in range(3):
            cur_main, cur_extra = _snap_all(self.hwnd)
            if _op_names(cur_main + cur_extra) == before_names and self.bm._open_popups(self.hwnd) == base_open:
                return True
            if step == 0:
                close_popups(self.hwnd, base_open, timeout_s=1.5)
            elif step == 1:
                n = self.find(cur_main + cur_extra, opener_label, "button", "")
                if n is not None:
                    self.bm.invoke_node_safely(n)
            else:
                for n in cur_main + cur_extra:
                    if n.ctype == "ButtonControl" and n.name and _CANCEL.match(n.name) and _norm(n.name) not in before_names:
                        self.bm.invoke_node_safely(n)
                        break
            _settle(self.hwnd, 0.8)
        cur_main, cur_extra = _snap_all(self.hwnd)
        return _op_names(cur_main + cur_extra) == before_names and self.bm._open_popups(self.hwnd) == base_open

    def with_via(self, via_label: str, fn: Callable[[], ProbeResult]) -> ProbeResult:
        """A control that only exists while another control's surface is open: open it, run `fn`, close it again."""
        main, extra = _snap_all(self.hwnd)
        base_open = list(self.bm._open_popups(self.hwnd))
        before_ops = _op_names(main + extra)
        opener = self.find(main + extra, via_label, "button", "")
        if opener is None:
            return ProbeResult("", "button", via_label, status="failed", evidence=f"opener '{via_label}' not found")
        self.bm.invoke_node_safely(opener)
        _settle(self.hwnd, 1.0)
        self.in_via = True
        try:
            return fn()
        finally:
            self.in_via = False
            self.unwind_surface(via_label, base_open, before_ops)

    def invoke_node(self, node) -> Tuple[bool, str]:
        return self.bm.invoke_node_safely(node)

    # ---- context menu ---------------------------------------------------------------
    def probe_context(self, row: Dict[str, Any]) -> ProbeResult:
        """Open the context menu of a spatial target by posting WM_CONTEXTMENU to the child window under its centre
        (measured: works headless on XAML + Win32 hosts, opens in ~0.4 s), read its items, close with WM_CLOSE."""
        from core_organs import headless_input as hin
        r = ProbeResult(row["fid"], "context", row["label"])
        main, _ = _snap_all(self.hwnd, popups=False)
        label = _norm(row["label"])
        cands = [n for n in main if n.rect[2] > n.rect[0] and (_norm(n.name) == label or _norm(n.aid) == label or _norm(n.cls) == label
                                                               or n.ctype.replace("Control", "").lower() == label)]
        if not cands:
            r.status, r.evidence = "failed", "target not found"
            return r
        n = max(cands, key=lambda x: (x.rect[2] - x.rect[0]) * (x.rect[3] - x.rect[1]))
        cx, cy = (n.rect[0] + n.rect[2]) // 2, (n.rect[1] + n.rect[3]) // 2
        base_open = list(self.bm._open_popups(self.hwnd))
        tried = []
        items: List[Any] = []
        for rung in ("wm_contextmenu", "post_rclick"):
            tried.append(rung)
            if rung == "wm_contextmenu":
                child = hin.child_at(self.hwnd, cx, cy) or self.hwnd
                _u32.PostMessageW(child, 0x007B, child, (cy << 16) | (cx & 0xFFFF))
            else:
                hin.post_click(self.hwnd, cx, cy, right=True)
            end = time.time() + 1.6
            new = []
            while time.time() < end:
                time.sleep(0.15)
                new = [w for w in self.bm._open_popups(self.hwnd) if w not in base_open]
                if new:
                    time.sleep(0.25)
                    break
            if new:
                from core_organs import fast_uia
                for w in new:
                    items += [x for x in (fast_uia.snapshot(w, timeout_ms=2500) or []) if x.ctype == "MenuItemControl" and x.name]
                if items:
                    r.effector = rung
                    break
                close_popups(self.hwnd, base_open)
        r.unwound = close_popups(self.hwnd, base_open) if (self.bm._open_popups(self.hwnd) != base_open) else True
        if not items:
            r.status, r.effect = "no_effect", "none"
            r.evidence = f"no context menu opened headless (tried {', '.join(tried)})"
            return r
        r.status, r.effect = "explored", "menu"
        seen = set()
        for it in items:
            if _norm(it.name) in seen:
                continue
            seen.add(_norm(it.name))
            cmd = {"name": it.name, "goal": it.name, "menu_path": f"[right-click {row['label']}] > {it.name}", "verb": "context",
                   "risk": "E2" if is_unsafe(it.name) else "EU"}
            if it.accel:
                cmd["shortcut"] = self.bm._norm_chord(it.accel)
            self.model.upsert_command(self.key, cmd, source="catalog", origin="e1:context-menu",
                                      evidence=f"context menu of '{row['label']}' via {r.effector}" + ("" if it.enabled else " (disabled at rest)"))
        r.items = len(seen)
        r.new_controls = sorted(seen)[:40]
        r.evidence = f"right-click on '{row['label']}' ({r.effector}) -> {len(seen)} item(s): {', '.join(sorted(seen)[:5])}; unwind={'ok' if r.unwound else 'FAILED'}"
        self.model.record_region(self.key, f"context:{row['label']}", [{"name": n_, "type": "menuitem"} for n_ in sorted(seen)], via=f"mastery:{r.effector}")
        return r

    # ---- dispatcher -----------------------------------------------------------------
    def ensure_baseline(self) -> None:
        """Before each probe: if an earlier probe left a surface open (a popup window, or a chunk of the original structure
        hidden behind a flyout), close it first - otherwise every later probe works on a covered UI and fails."""
        main, extra = _snap_all(self.hwnd)
        if self.base_ops is None:
            self.base_ops = _op_names(main + extra)
            self.base_open = list(self.bm._open_popups(self.hwnd))
            return
        hidden = self.base_ops - _op_names(main + extra)
        if len(hidden) >= 4 or self.bm._open_popups(self.hwnd) != self.base_open:
            self.unwind_surface(self.open_label, self.base_open, self.base_ops)

    def run(self, row: Dict[str, Any]) -> ProbeResult:
        t0 = time.time()
        kind = row["kind"]
        try:
            if not self.in_via:
                self.ensure_baseline()
            if kind == "tab":
                r = self.probe_tab(row)
            elif kind == "expander":
                r = self.probe_expander(row)
            elif kind == "toggle":
                r = self.probe_toggle(row)
            elif kind in ("opener", "button"):
                if kind == "button" and not self.pristine:
                    r = ProbeResult(row["fid"], kind, row["label"], status="skipped",
                                    evidence="document not pristine: in-app buttons are not pressed (could mutate user content)")
                elif kind == "button" and self.dirty >= 14:
                    r = ProbeResult(row["fid"], kind, row["label"], status="skipped", evidence="app state already diverged 14 times; stopped pressing in-app buttons")
                else:
                    r = self.probe_invoke(row)
            elif kind == "context":
                r = self.probe_context(row)
            else:
                r = ProbeResult(row["fid"], kind, row["label"], status="skipped", evidence=f"unknown kind {kind}")
        except Exception as exc:
            r = ProbeResult(row["fid"], kind, row["label"], status="failed", evidence=f"{type(exc).__name__}: {str(exc)[:120]}")
        r.elapsed_s = round(time.time() - t0, 2)
        if not self.window_ok():
            self.broken = True
            r.evidence += " | WINDOW LOST: the app window is gone or minimised after this probe"
            r.unwound = False
        return r

    def window_ok(self) -> bool:
        """The window we are exploring must still exist and must not have been minimised by a probe."""
        try:
            if not _u32.IsWindow(self.hwnd):
                return False
            if _u32.IsIconic(self.hwnd):
                self.bm._keep_hidden(self.hwnd)                 # re-park; a window that stays iconic is lost to us
                time.sleep(0.4)
                return not _u32.IsIconic(self.hwnd)
        except Exception:
            return False
        return True

    # ---- a surface that only exists while a tab is selected ---------------------------
    def with_tab(self, tab_label: str, fn: Callable[[], ProbeResult]) -> ProbeResult:
        """Select a tab, run `fn` against what it shows, restore the previously selected tab (verified)."""
        main, _ = _snap_all(self.hwnd, popups=False)
        node = self.find(main, tab_label, "tab", "")
        if node is None:
            return ProbeResult("", "tab", tab_label, status="failed", evidence=f"tab '{tab_label}' not found")
        prev = next((n for n in main if n.ctype == "TabItemControl" and n.selected and n.parent == node.parent), None)
        if not node.selected:
            _uia_call(node, "GetSelectionItemPattern", "Select", 2.0)
            _settle(self.hwnd, 1.0)
        try:
            return fn()
        finally:
            if prev is not None and prev.name != tab_label:
                cur, _ = _snap_all(self.hwnd, popups=False)
                pn = self.find(cur, prev.name, "tab", "")
                if pn is not None:
                    _uia_call(pn, "GetSelectionItemPattern", "Select", 2.0)
                    _settle(self.hwnd, 0.8)


# ===========================================================================
# 6. Is the document pristine? (mutating probes only run on a clean, disposable instance)
# ===========================================================================

_MODIFIED = re.compile(r"(^\*|\*$|\bmodified\b|\bunsaved\b|•|●)", re.I)


def is_pristine(hwnd: int, nodes) -> Tuple[bool, str]:
    """No document content to lose: no modified marker in the title or tab names and no editable control holding text."""
    from core_organs import organ_48_app_behavior_model as bm
    title = bm._win_title(hwnd)
    if _MODIFIED.search(title or ""):
        return False, f"title shows modified state ({title[:40]!r})"
    for n in nodes:
        if n.ctype == "TabItemControl" and _MODIFIED.search(n.name or ""):
            return False, f"a tab is modified ({n.name[:40]!r})"
    checked = 0
    win_area = max(1, (nodes[0].rect[2] - nodes[0].rect[0]) * (nodes[0].rect[3] - nodes[0].rect[1])) if nodes else 1
    for n in nodes:
        area = (n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1])
        # a content area (a Document, or an edit that is a large part of the window); the zoom box / width field of a toolbar is a setting
        if n.ctype in ("DocumentControl", "EditControl") and "value" in n.pats and checked < 4 and (n.ctype == "DocumentControl" or area >= 0.08 * win_area):
            checked += 1
            try:
                val = n.ctrl.GetValuePattern().Value or ""
            except Exception:
                continue
            if val.strip():
                return False, f"an editable control already holds {len(val)} character(s)"
    return True, "no modified marker, no editable content"


# ===========================================================================
# 7. Universal conventions, TESTED on this app
# ===========================================================================

CONVENTIONS = [
    {"intent": "open file", "chord": "ctrl+o", "needs_untitled": False},
    {"intent": "find", "chord": "ctrl+f", "needs_untitled": False},
    {"intent": "replace", "chord": "ctrl+h", "needs_untitled": False},
    {"intent": "go to", "chord": "ctrl+g", "needs_untitled": False},
    {"intent": "settings", "chord": "ctrl+,", "needs_untitled": False},
    {"intent": "command palette", "chord": "ctrl+shift+p", "needs_untitled": False},
    {"intent": "save as", "chord": "ctrl+shift+s", "needs_untitled": True},
]


def _declared_chord(model, app_key: str, chord: str) -> bool:
    """Does a known command of this app already carry this chord (from its resources, live menu or shipped keymap)?"""
    from core_organs import organ_48_app_behavior_model as bm
    want = bm._norm_chord(chord)
    try:
        for r in model._conn.execute("SELECT shortcut FROM bm_commands WHERE app_key=? AND shortcut!=''", (app_key,)):
            if bm._norm_chord(r["shortcut"]) == want:
                return True
    except Exception:
        pass
    return False


def test_conventions(model, app_key: str, hwnd: int, *, pristine: bool, run_id: str = "", budget_s: float = 25.0,
                     skip_chords: Optional[set] = None) -> Dict[str, Any]:
    """For each universal chord: press it (posted, headless), watch for a new window or new controls, record the verdict,
    capture any dialog it opened, and unwind. Also answers 'does this app accept posted keys at all?'."""
    from core_organs import headless_input as hin
    from core_organs import desktop_grounding as dg
    from core_organs import organ_48_app_behavior_model as bm
    t_end = time.time() + budget_s
    out: Dict[str, Any] = {"tested": [], "delivery": "unknown"}
    obeyed = ignored = 0
    xaml = False
    try:
        xaml = bool(hin.is_xaml_host(dg._root_of(hwnd)))
    except Exception:
        pass
    for cv in CONVENTIONS:
        if time.time() > t_end:
            out["stopped"] = "budget"
            break
        chord, intent = cv["chord"], cv["intent"]
        if skip_chords and chord in skip_chords:
            continue
        if _declared_chord(model, app_key, chord):
            out["tested"].append({"intent": intent, "chord": chord, "verdict": "declared",
                                  "why": "the app declares this chord for a known command: that command's own route is what gets verified"})
            continue
        if ignored >= 3 and obeyed == 0:
            out["tested"].append({"intent": intent, "chord": chord, "verdict": "not-tested",
                                  "why": "3 universal chords already ignored: posted keys do not reach this app"})
            continue
        main, extra = _snap_all(hwnd)
        if cv["needs_untitled"] and not (pristine and is_pristine(hwnd, main)[0]):
            ks.convention_result(model, app_key, intent, chord, "unobservable", "skipped: document is not pristine (save could overwrite)")
            out["tested"].append({"intent": intent, "chord": chord, "verdict": "skipped", "why": "not pristine"})
            continue
        base_open = list(bm._open_popups(hwnd))
        before_names = _names(main) | _names(extra)
        before_state = derive_state(main)
        ok, note = hin.post_key_combo(dg._root_of(hwnd), chord)
        end = time.time() + 1.8
        new_wins: List[int] = []
        new_names: List[str] = []
        while ok and time.time() < end:
            time.sleep(0.15)
            bm._keep_hidden(hwnd)
            new_wins = [w for w in bm._open_popups(hwnd) if w not in base_open]
            if new_wins:
                time.sleep(0.25)
                break
            m2, x2 = _snap_all(hwnd)
            new_names = sorted((_names(m2) | _names(x2)) - before_names)
            if new_names:
                break
        verdict, evidence = "ignored", ""
        if not ok:
            verdict, evidence = "unobservable", f"key not delivered ({note})"
        elif new_wins:
            got = capture_dialogs(model, app_key, new_wins, via=f"convention {chord}")
            verdict = "obeyed"
            evidence = f"{chord} opened {[g['title'] for g in got] or 'a window'} ({sum(g['n'] for g in got)} controls)"
            unwound = close_popups(hwnd, base_open)
            evidence += f"; unwind={'ok' if unwound else 'FAILED'}"
            if got:
                model.upsert_command(app_key, {"name": f"{intent} (shortcut)", "goal": intent, "shortcut": chord, "verb": "key", "risk": "E1",
                                               "post": [{"kind": "window_opened", "title_contains": got[0]["title"].lower()}]},
                                     source="catalog", origin="e1:convention", evidence=evidence)
        elif new_names:
            verdict = "obeyed"
            evidence = f"{chord} revealed {len(new_names)} control(s): {', '.join(new_names[:4])}"
            hin.post_key_combo(dg._root_of(hwnd), "escape")              # unwind an inline pane (works when keys are delivered)
            time.sleep(0.5)
            back, _ = _snap_all(hwnd, popups=False)
            restored = _names(back) == _names(main)
            how = "escape"
            if not restored:                                             # a toggle pane (Find bar): the same chord closes it
                hin.post_key_combo(dg._root_of(hwnd), chord)
                time.sleep(0.7)
                back, _ = _snap_all(hwnd, popups=False)
                restored, how = _names(back) == _names(main), "same-chord toggle"
            evidence += f"; unwind={'ok via ' + how if restored else 'FAILED'}"
            model.upsert_command(app_key, {"name": f"{intent} (shortcut)", "goal": intent, "shortcut": chord, "verb": "key", "risk": "E1",
                                           "post": [{"kind": "element_appeared", "name": new_names[0]}]},
                                 source="catalog", origin="e1:convention", evidence=evidence)
        else:
            evidence = "no window and no new control within 1.8 s" + ("; XAML host: posted keys are not delivered to XAML input" if xaml else "")
        ks.convention_result(model, app_key, intent, chord, verdict, evidence)
        if verdict in ("obeyed", "ignored"):
            model.record_effector(app_key, "key", "key", verdict == "obeyed")
        obeyed += verdict == "obeyed"
        ignored += verdict == "ignored"
        out["tested"].append({"intent": intent, "chord": chord, "verdict": verdict, "evidence": evidence[:140]})
    out["delivery"] = "works" if obeyed else ("not-delivered" if ignored else "unknown")
    out["xaml_host"] = xaml
    ks.put_fact(model, app_key, "key_delivery", {"status": out["delivery"], "xaml_host": xaml, "obeyed": obeyed, "ignored": ignored},
                source="live:conventions", confidence=0.8 if (obeyed or ignored >= 3) else 0.4)
    return out


# ===========================================================================
# 8. The exploration loop (frontier -> probes), budgeted by yield
# ===========================================================================

_KIND_ORDER = {"tab": 0, "opener": 1, "context": 2, "expander": 3, "toggle": 4, "button": 5}
_KIND_CAP = {"button": 25, "context": 8, "toggle": 25, "expander": 25, "opener": 40, "tab": 20}


def record_resting_controls(model, app_key: str, nodes) -> int:
    """Operable, named controls visible in the CURRENT state that the knowledge base has no command for yet (matched by normalized name).
    Returns how many were added. Personal labels are redacted by the sink; nothing is pressed."""
    known = {_norm(r[0]) for r in model._conn.execute("SELECT name FROM bm_commands WHERE app_key=?", (app_key,))}
    added = 0
    for n in nodes:
        if n.ctype not in _OPERABLE or not n.name or _norm(n.name) in known or is_unsafe(n.name):
            continue
        cmd = {"name": n.name, "goal": n.name, "menu_path": n.name, "verb": "invoke", "risk": "EU"}
        if n.accel:
            from core_organs import organ_48_app_behavior_model as _bm
            cmd["shortcut"] = _bm._norm_chord(n.accel)
        model.upsert_command(app_key, cmd, source="catalog", origin="e0:resting", evidence="visible in the app's state after exploration")
        known.add(_norm(n.name))
        added += 1
    return added


def _bounded(fn: Callable[[], Any], deadline_s: float):
    """Run `fn` with a hard deadline. A probe talks to ANOTHER process; when that process stops answering (measured: Paint pegged
    at 100% CPU, not responding, after a colour dialog) an unbounded UIA call blocks the whole run for ever. The worker is a daemon
    thread, so an abandoned call cannot keep the run alive. Returns (finished, value-or-exception)."""
    import threading
    box: Dict[str, Any] = {}

    def _w():
        try:
            import uiautomation as auto
            with auto.UIAutomationInitializerInThread():
                box["v"] = fn()
        except BaseException as exc:                      # noqa: BLE001 - reported to the caller
            box["e"] = exc
    th = threading.Thread(target=_w, daemon=True, name="mastery-probe")
    th.start()
    th.join(deadline_s)
    if th.is_alive():
        return False, None
    if "e" in box:
        return True, box["e"]
    return True, box.get("v")


PROBE_DEADLINE_S = 75.0


def _hung(hwnd: int) -> bool:
    try:
        return bool(ctypes.windll.user32.IsHungAppWindow(hwnd))
    except Exception:
        return False


def explore(model, app_name: str, hwnd: int, *, run_id: str = "", budget_s: float = 60.0, max_probes: int = 80,
            pristine: bool = True, kinds: Optional[List[str]] = None, inside_tab_probes: int = 8) -> Dict[str, Any]:
    """Open frontier surfaces, most informative first, until the budget (extended while probes keep yielding), the
    probe cap, or exhaustion. Returns per-probe results + stop reason."""
    from core_organs import organ_48_app_behavior_model as bm
    key = bm._app_key(app_name)
    prober = Prober(model, key, hwnd, pristine=pristine, run_id=run_id)
    budget = bm.DiscoveryBudget(base_s=budget_s * 0.5, extend_s=8.0, max_s=budget_s, patience=10)
    results: List[ProbeResult] = []
    done_kind: Dict[str, int] = {}
    bad_unwind: Dict[str, int] = {}
    stop = "exhausted"
    vh = bm.app_version_hash(bm._exe_of_hwnd(hwnd))

    tried: set = set()                                      # fids attempted in THIS run (a transient failure is retried in the next run, not now)

    def _record(row: Dict[str, Any], r: ProbeResult) -> None:
        tried.add(row["fid"])
        status = r.status
        if status == "failed" and int(row.get("attempts") or 0) < 1:
            status = "open"                                      # first failure: could be a covered UI; keep it open for another pass
        ks.frontier_done(model, row["fid"], status,
                         {"effect": r.effect, "evidence": r.evidence[:300], "new": r.new_controls[:10], "unwound": r.unwound,
                          "effector": r.effector, "s": r.elapsed_s}, run_id)
        if not r.unwound and r.effect != "mutation":          # a MUTATION is not restored on purpose; everything else must be
            bad_unwind[r.kind] = bad_unwind.get(r.kind, 0) + 1

    def _inside_tab(tab_row: Dict[str, Any]) -> None:
        """While a tab is selected, queue and run the cheap non-mutating surfaces it shows (bounded)."""
        n_done = 0
        main, _ = _snap_all(hwnd, popups=False)
        rows_before = {r["fid"] for r in ks.frontier_open(model, key, limit=500)}
        populate_frontier(model, key, hwnd, main, vh)
        tab_name = tab_row["label"]
        fresh = [r for r in ks.frontier_open(model, key, limit=500) if r["fid"] not in rows_before and r["kind"] in ("opener", "expander", "toggle")]
        for rr in sorted(fresh, key=lambda x: -x["info_gain"])[:inside_tab_probes]:
            if budget.reason_to_stop() or bad_unwind.get(rr["kind"], 0) >= 2:
                break
            res = prober.run(rr)
            _record(rr, res)
            results.append(res)
            budget.credit(res.items)
            n_done += 1
        # what is left under this tab is explored on a later run: remember WHERE it lives
        for rr in ks.frontier_open(model, key, limit=500):
            if rr["fid"] not in rows_before and not rr["path"].startswith("@tab:") and rr["kind"] in ("opener", "expander", "toggle", "button", "context"):
                model._conn.execute("UPDATE bm_frontier SET path=? WHERE fid=?", (f"@tab:{tab_name}@ {rr['path']}", rr["fid"]))
        model._conn.commit()

    while True:
        rows = ks.frontier_open(model, key, limit=200)
        if kinds:
            rows = [r for r in rows if r["kind"] in kinds]
        rows = [r for r in rows if done_kind.get(r["kind"], 0) < _KIND_CAP.get(r["kind"], 20) and bad_unwind.get(r["kind"], 0) < 2
                and r["fid"] not in tried]
        rows.sort(key=lambda r: (_KIND_ORDER.get(r["kind"], 9), -r["info_gain"], r["attempts"]))
        if not rows:
            stop = "exhausted"
            break
        row = rows[0]
        if len(results) >= max_probes:
            stop = "probe-cap"
            break
        why = budget.reason_to_stop()
        if why:
            stop = why
            break
        if prober.broken:
            stop = "window-lost"
            break
        path = row["path"]
        tab_ctx = via_ctx = ""
        if path.startswith("@tab:"):
            tab_ctx, _, rest = path[5:].partition("@ ")
            row = dict(row, path=rest)
        elif path.startswith("@via:"):
            via_ctx, _, rest = path[5:].partition("@ ")
            row = dict(row, path=rest)
        def _go(row=row, tab_ctx=tab_ctx, via_ctx=via_ctx):
            if tab_ctx:
                rr_ = prober.with_tab(tab_ctx, lambda: prober.run(row))
                rr_.fid, rr_.kind = row["fid"], row["kind"]
                return rr_
            if via_ctx:
                rr_ = prober.with_via(via_ctx, lambda: prober.run(row))
                rr_.fid, rr_.kind = row["fid"], row["kind"]
                return rr_
            return prober.run(row)
        finished, r = _bounded(_go, PROBE_DEADLINE_S)
        if not finished or isinstance(r, BaseException):
            hung = _hung(hwnd)
            why = (f"probe exceeded {PROBE_DEADLINE_S:.0f}s" + (": the app stopped responding" if hung else "")) if not finished                 else f"probe raised {type(r).__name__}: {str(r)[:100]}"
            r = ProbeResult(row["fid"], row["kind"], row["label"], status="failed", unwound=False, evidence=why)
            _record(row, r)
            results.append(r)
            if not finished:
                prober.broken = True
                ks.frontier_done(model, row["fid"], "unsafe", {"why": "probing this froze the app: not pressed again", "evidence": why}, run_id)
                stop = "app-unresponsive" if hung else "probe-timeout"
                break
            continue
        _record(row, r)
        if _hung(hwnd):                                   # the probe returned but the app stopped answering: give it a moment, then stop
            t_end = time.time() + 15.0
            while time.time() < t_end and _hung(hwnd):
                time.sleep(0.5)
            if _hung(hwnd):
                ks.frontier_done(model, row["fid"], "unsafe", {"why": "the app stopped responding right after this probe: not pressed again",
                                                              "evidence": r.evidence[:200]}, run_id)
                r.evidence += " | APP UNRESPONSIVE after this probe"
                results.append(r)
                prober.broken = True
                stop = "app-unresponsive"
                break
        results.append(r)
        done_kind[row["kind"]] = done_kind.get(row["kind"], 0) + 1
        budget.credit(r.items)
        if row["kind"] == "tab" and r.status == "explored" and r.unwound and inside_tab_probes:
            prober.with_tab(row["label"], lambda: (_inside_tab(row), ProbeResult("", "tab", row["label"], status="explored"))[1])
        # a state we cannot get back from (modal left open, popup that will not close): stop everything that opens things
        leftover = [w for w in bm._open_popups(hwnd)]
        if leftover and not r.unwound:
            close_popups(hwnd, [])
    by_status: Dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return {"probes": len(results), "by_status": by_status, "stopped": stop, "app_unresponsive": stop in ("app-unresponsive", "probe-timeout"), "elapsed_s": round(budget.elapsed(), 1),
            "unwind_failures": bad_unwind, "dirty": prober.dirty,
            "detail": [{"kind": r.kind, "label": r.label[:30], "status": r.status, "effect": r.effect, "items": r.items,
                        "unwound": r.unwound, "s": r.elapsed_s, "why": r.evidence[:110] + ("" if r.unwound else " | " + str(r.detail_unwind)[:240])} for r in results]}


# ===========================================================================
# 9. Measuring what is known (counts, never a made-up score)
# ===========================================================================

def _count(conn, table: str, app_key: str) -> int:
    """Row count for an app in a table that may not exist yet (organ_50's layout tables are created lazily)."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        return 0
    return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE app_key=?", (app_key,)).fetchone()[0]


def measure(model, app_key: str) -> Dict[str, Any]:
    """What the knowledge base holds for this app right now, broken down by where it came from."""
    ks.ensure(model)
    c = model._conn
    cmds = [dict(r) for r in c.execute("SELECT origin, source, shortcut, risk, opaque, menu_path FROM bm_commands WHERE app_key=?", (app_key,))]

    def _origin(o: str) -> str:
        o = o or ""
        for pre, label in (("static:", "static"), ("e0:", "menus_live"), ("e1:", "explored"), ("layout", "layout"), ("pack", "pack"), ("keymap", "pack")):
            if o.startswith(pre):
                return label
        return "other"
    by_origin: Dict[str, int] = {}
    for r in cmds:
        by_origin[_origin(r["origin"])] = by_origin.get(_origin(r["origin"]), 0) + 1
    shortcuts = {r["shortcut"] for r in cmds if r["shortcut"]}
    out = {
        "commands": len(cmds), "commands_by_origin": by_origin,
        "commands_learned": sum(1 for r in cmds if r["source"] == "learned"),
        "commands_with_shortcut": sum(1 for r in cmds if r["shortcut"]), "distinct_shortcuts": len(shortcuts),
        "commands_unsafe_E2": sum(1 for r in cmds if r["risk"] == "E2"),
        "dialogs": len(ks.dialogs(model, app_key)),
        "dialogs_live": sum(1 for d in ks.dialogs(model, app_key) if d["source"].startswith("live")),
        "regions": _count(c, "bm_ui_regions", app_key),
        "layout_controls": _count(c, "bm_layout", app_key),
        "statevars": len(ks.statevars(model, app_key)),
        "transitions": _count(c, "bm_transitions", app_key),
        "conventions_obeyed": sum(1 for x in ks.conventions(model, app_key) if x["verdict"] == "obeyed"),
        "conventions_ignored": sum(1 for x in ks.conventions(model, app_key) if x["verdict"] == "ignored"),
        "facts": len(ks.facts(model, app_key)), "frontier": ks.frontier_stats(model, app_key),
    }
    return out


def _delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    d: Dict[str, Any] = {}
    for k, v in after.items():
        if isinstance(v, (int, float)) and isinstance(before.get(k), (int, float)):
            d[k] = v - before[k]
    return d


# ===========================================================================
# 10. The entry point: master(target) -- first contact AND every later run
# ===========================================================================

def _static_phase(model, app_name: str, hwnd: int) -> Dict[str, Any]:
    from core_organs import static_knowledge as sk
    from core_organs import organ_48_app_behavior_model as bm
    t = time.time()
    d = sk.harvest(hwnd if hwnd else app_name)
    rep = sk.ingest(model, app_name, d)
    rep.update(ok=d.get("ok", False), elapsed_s=round(time.time() - t, 2), exe=d.get("exe", ""),
               frameworks=[f["id"] for f in d.get("frameworks", [])], archetype=(d.get("profile") or {}).get("archetype", ""),
               file_types=len(d.get("file_types", [])), requires_elevation=d.get("requires_elevation", False))
    return rep


def master(target: str, *, model=None, budget_s: float = 90.0, runs: int = 1, fresh: bool = True,
           deepen: bool = True, conventions: bool = True, close_if_launched: bool = True, on_window=None,
           allow_visible: bool = False, kinds: Optional[List[str]] = None, e1_actions: int = 0) -> Dict[str, Any]:
    """Learn `target` (an app name) as completely as the budget allows. Safe to call again: each call continues from the
    persisted frontier and reports what THIS run added. Returns {'runs': [...], 'known': measure(...), 'converged': bool}."""
    from core_organs import universal_scan as us
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import background_window as bw
    from core_organs import fast_uia
    from core_organs import desktop_grounding as dg
    model = model or bm.get_model()
    ks.ensure(model)
    key = bm._app_key(target)
    out: Dict[str, Any] = {"target": target, "app_key": key, "runs": []}
    g = dg.DesktopGrounding()
    last_new = None
    for _ in range(max(1, runs)):
        run_no = ks.run_count(model, key) + 1
        run_id = f"mastery_{key}_{run_no}_{uuid.uuid4().hex[:5]}"
        before = measure(model, key)
        rep: Dict[str, Any] = {"run_no": run_no, "phases": {}}
        t_run = time.time()
        # 1. what the file already says (no launch)
        try:
            rep["static"] = _static_phase(model, target, 0)
        except Exception as exc:
            rep["static"] = {"error": f"{type(exc).__name__}: {str(exc)[:100]}"}
        rep["phases"]["static_s"] = (rep["static"] or {}).get("elapsed_s", 0)
        # 2. the live scan (launch hidden, wake, E0 menus, layout) - existing pipeline, reused as is
        t = time.time()
        scan = us.scan_desktop(target, model, fresh=fresh, force=False, deepen=deepen, e1_actions=e1_actions,
                               close_if_launched=False, on_window=on_window, allow_visible=allow_visible)
        rep["phases"]["scan_s"] = round(time.time() - t, 1)
        rep["scan"] = {k: scan.get(k) for k in ("error", "window_mode", "polite_mode", "known_commands", "regions_known", "tree_nodes_when_ready", "accessibility")}
        rep["scan"]["warm"] = scan.get("warm")
        hwnd = g.find_window(target) or 0
        launched = bool(scan.get("launch", {}).get("launched"))
        if not hwnd or scan.get("error"):
            rep["error"] = scan.get("error") or "window not found after the scan"
            out["runs"].append(rep)
            ks.log_run(model, run_id, key, run_no, "failed", {"error": rep["error"]})
            break
        # facts that need the live window (authoritative exe path, version)
        try:
            rep["static_live"] = _static_phase(model, target, hwnd)
        except Exception:
            pass
        polite = bool(scan.get("polite_mode"))
        if not polite:
            try:
                t = time.time()
                with bw.BackgroundSession(hwnd):
                    time.sleep(0.6)
                    main, extra = _snap_all(hwnd)
                    state = derive_state(main + extra)
                    rep["state_vars"] = record_state_vars(model, key, state)
                    pristine, why = is_pristine(hwnd, main)
                    rep["pristine"] = {"pristine": pristine, "why": why}
                    vh = bm.app_version_hash(bm._exe_of_hwnd(hwnd))
                    rep["frontier_added"] = populate_frontier(model, key, hwnd, main + extra, vh)
                    rep["phases"]["state_s"] = round(time.time() - t, 1)
                    t = time.time()
                    explore_kinds = kinds
                    exe_live = bm._exe_of_hwnd(hwnd).lower()
                    sysroot = (os.environ.get("SystemRoot") or ("C:" + os.sep + "Windows")).lower()
                    # a packaged (UWP) app is hosted by ApplicationFrameHost.exe in System32: that is the FRAME, not the program, so it is
                    # judged by the app, not by where the frame lives (measured: Calculator was wrongly made read-only and learned 0 transitions)
                    hosted = os.path.basename(exe_live) == "applicationframehost.exe"
                    if kinds is None and exe_live and not hosted and (exe_live.startswith(sysroot + os.sep) or os.sep + "systemapps" + os.sep in exe_live):
                        explore_kinds = ["tab", "opener", "context", "expander"]          # OS component: never press its toggles / buttons
                        rep["read_only_scope"] = "program lives in the Windows directory: tabs, dialogs, dropdowns and context menus only"
                    rep["explore"] = explore(model, target, hwnd, run_id=run_id, budget_s=budget_s, pristine=pristine, kinds=explore_kinds)
                    rep["phases"]["explore_s"] = round(time.time() - t, 1)
                    if rep["explore"].get("app_unresponsive"):
                        rep["app_hung"] = True
                        rep["note"] = "the app stopped answering during exploration: no further input was sent; what was learned before is kept"
                    if conventions and not rep.get("app_hung"):
                        t = time.time()
                        skip = {c["shortcut"] for c in model.commands(key, limit=5000) if c["shortcut"] and c["source"] == "learned"}
                        fin, val = _bounded(lambda: test_conventions(model, key, hwnd, pristine=pristine, run_id=run_id, skip_chords=skip), 150.0)
                        if not fin or isinstance(val, BaseException):
                            hung = (not fin) and _hung(hwnd)
                            rep["conventions"] = {"error": "convention tests did not finish" + (": the app stopped responding" if hung else ""), "tested": []}
                            if not fin:
                                rep["app_hung"] = True
                                rep["note"] = "the app stopped answering during the convention tests: no further input was sent"
                        else:
                            rep["conventions"] = val
                        rep["phases"]["conventions_s"] = round(time.time() - t, 1)
                    # state after exploration must equal state before: the app was left exactly as found
                    if rep.get("app_hung"):
                        rep["left_as_found"] = False
                    else:
                        def _final():
                            main2, extra2 = _snap_all(hwnd)
                            try:                       # the controls visible NOW are knowledge too (an app's mode may have changed during exploration)
                                rep["end_state_new_controls"] = record_resting_controls(model, key, main2 + extra2)
                            except Exception as exc:   # noqa: BLE001
                                rep["end_state_new_controls"] = f"error: {type(exc).__name__}"
                            return derive_state(main2 + extra2)["signature"] == state["signature"] and not bm._open_popups(hwnd)
                        fin, val = _bounded(_final, 45.0)
                        rep["left_as_found"] = bool(val) if fin and not isinstance(val, BaseException) else False
                        if not fin:
                            rep["app_hung"] = True
            except Exception as exc:
                import traceback
                rep["error_live"] = f"{type(exc).__name__}: {str(exc)[:160]}"
                rep["trace"] = traceback.format_exc()[-700:]
        else:
            rep["explore"] = {"skipped": "polite mode: the window is in the user's view, read passively only"}
        # 3. unify + profile from ALL labels now known
        try:
            from core_organs import command_registry as cr
            rep["registry"] = cr.refresh_profile(model, key)
        except Exception as exc:
            rep["registry"] = {"error": f"{type(exc).__name__}: {str(exc)[:100]}"}
        after = measure(model, key)
        rep["known"] = after
        rep["gain"] = _delta(before, after)
        rep["elapsed_s"] = round(time.time() - t_run, 1)
        ks.log_run(model, run_id, key, run_no, "run", {"gain": rep["gain"], "known": {k: after[k] for k in ("commands", "dialogs", "regions", "statevars", "transitions")},
                                                      "frontier": after["frontier"], "elapsed_s": rep["elapsed_s"]})
        out["runs"].append(rep)
        if launched and (close_if_launched or rep.get("app_hung")):
            rep["closed"] = False if rep.get("app_hung") else us.close_window(hwnd, discard_unsaved=True)
            if rep.get("app_hung") and not rep["closed"]:
                # a process THIS run launched and that no longer answers: end that exact process (by pid, never by image name)
                try:
                    from core_organs import headless_input as hin
                    pid = hin.window_pid(hwnd)
                    if pid:
                        os.system(f"taskkill /PID {int(pid)} /F >nul 2>&1")
                        rep["closed"] = "terminated-hung-launched-process"
                except Exception:
                    pass
        # converged: nothing left open, or this run learned (almost) nothing
        new_items = sum(max(0, v) for k, v in rep["gain"].items() if k in ("commands", "dialogs", "regions", "statevars", "transitions"))
        last_new = new_items
        open_left = after["frontier"]["by_status"].get("open", 0)
        if not open_left or new_items <= 2:
            out["converged"] = True
            break
    out["known"] = measure(model, key)
    out.setdefault("converged", False)
    return out


# ===========================================================================
# 11. "Give me ANY app" -- instant knowledge, deeper on demand
# ===========================================================================

def know(target: str, *, model=None, live: bool = False, runs: int = 1, budget_s: float = 90.0) -> Dict[str, Any]:
    """What is known about `target`, RIGHT NOW. Never launches anything unless live=True.
         1. static harvest (the program file: resources, toolkit, file types, shipped data)  - milliseconds, no launch
         2. live mastery when asked (`live=True`): scan + explore + conventions, cumulative over `runs`
    Returns the dossier plus `knowledge_level`: none | static | live-scanned | explored and how to deepen it."""
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import command_registry as cr
    model = model or bm.get_model()
    ks.ensure(model)
    key = bm._app_key(target)
    t0 = time.time()
    static = None
    try:
        static = _static_phase(model, target, 0)
    except Exception as exc:
        static = {"error": f"{type(exc).__name__}: {str(exc)[:100]}"}
    mastery = None
    if live:
        mastery = master(target, model=model, budget_s=budget_s, runs=runs)
    d = cr.dossier(model, key)
    n_runs = ks.run_count(model, key)
    explored = (d["frontier"].get("by_status") or {})
    level = ("explored" if explored.get("explored", 0) else "live-scanned" if n_runs or d["measure"].get("layout_controls") else
             "static" if d["measure"].get("facts") else "none")
    d["knowledge_level"] = level
    d["runs_so_far"] = n_runs
    d["static_phase"] = static
    d["elapsed_s"] = round(time.time() - t0, 2)
    d["deepen"] = ("know(target, live=True) scans and explores it (invisible, resumable, cumulative); repeat to go deeper"
                   if level in ("none", "static") else "know(target, live=True) continues from the persisted frontier")
    if mastery is not None:
        d["mastery"] = {"runs": len(mastery["runs"]), "converged": mastery.get("converged")}
    return d


def ask(target: str, goal: str, *, model=None, limit: int = 5) -> List[Dict[str, Any]]:
    """'How do I <goal> in <target>?' -> ranked commands with their ordered routes (WM_COMMAND id / menu path / key chord / control /
    context menu), trust and corroboration. Static knowledge answers it for a never-launched classic app."""
    from core_organs import organ_48_app_behavior_model as bm
    from core_organs import command_registry as cr
    model = model or bm.get_model()
    key = bm._app_key(target)
    if not model._conn.execute("SELECT 1 FROM bm_commands WHERE app_key=? LIMIT 1", (key,)).fetchone():
        try:
            _static_phase(model, target, 0)
        except Exception:
            pass
    return cr.lookup(model, key, goal, limit=limit)


def _cli(argv: List[str]) -> int:
    import json as _json
    if not argv or argv[0] not in ("know", "master", "ask", "static"):
        print("usage: organ_63_app_mastery.py know <app> [--live] [--runs N] [--budget S]\n"
              "       organ_63_app_mastery.py master <app> [--runs N] [--budget S]\n"
              "       organ_63_app_mastery.py ask <app> \"<goal>\"\n"
              "       organ_63_app_mastery.py static <app|exe path>")
        return 2
    cmd, target = argv[0], (argv[1] if len(argv) > 1 else "")
    opt = lambda f, d: type(d)(argv[argv.index(f) + 1]) if f in argv else d
    if cmd == "static":
        from core_organs import static_knowledge as sk
        d = sk.harvest(target)
        d["commands"] = [{k: c.get(k) for k in ("menu_path", "name", "shortcut", "menu_id", "help")} for c in d["commands"]][:40]
        print(_json.dumps(d, indent=1, default=str)[:12000])
    elif cmd == "ask":
        for h in ask(target, " ".join(argv[2:])):
            print(f"{h['score']:5.1f}  {h['name']}  [{h['kind']}] path='{h['menu_path']}' key='{h['shortcut']}' trust={h['trust']} "
                  f"verified={h['verified']}\n       routes: {[r['effector'] for r in h['routes']]}")
    elif cmd == "master":
        res = master(target, runs=opt("--runs", 1), budget_s=opt("--budget", 90.0))
        print(_json.dumps(res["known"], indent=1, default=str))
    else:
        d = know(target, live="--live" in argv, runs=opt("--runs", 1), budget_s=opt("--budget", 90.0))
        d.pop("measure", None)
        print(_json.dumps(d, indent=1, default=str)[:14000])
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
    _sys.exit(_cli(_sys.argv[1:]))
