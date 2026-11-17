"""
atlas.explorer -- open EVERYTHING that can be opened, read it, and put it back. Fast, generic, verified.

Passes (all inside one parked, invisible session):

  MENUS     expand each menu-bar entry (UIA ExpandCollapse: it runs no application code), read every item with its accelerator / help / patterns,
            recurse into submenus, collapse.
  TABS      select each tab, read what it reveals, restore the originally selected one.
  OPENERS   every control that promises a surface (an ellipsis label, a menu item or button whose effect is unknown on a disposable instance) is
            TRIGGERED, the surface is read as a SCHEMA, then closed with a verified unwind.
  DIALOGS   the dialog protocol: master/detail lists and trees (select every item, diff the detail pane), tab strips, WIZARDS (follow Next up to
            four pages), then Cancel -- never the commit button. The main window must come back to its starting state.

THE TRIGGER LADDER (a measured finding, not a preference): a UIA Invoke on a control whose handler opens a MODAL dialog does not return until the
dialog closes, and while it is pending EVERY UIA call into that process blocks (measured: >25 s from this process and from a second one). So an opener
is triggered asynchronously:  1) Win32 BM_CLICK to the control's own window,  2) a posted mouse click at the control's centre,  3) UIA Invoke only as a
last resort, on a thread that is abandoned if it blocks.

Everything learned is written into the shared behaviour database (commands at 'learned' trust, dialog schemas, transitions), so the planner, the
registry and the automation loop use it immediately.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import re
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from . import common as C

# A PRIVATE user32 with explicit signatures: the process-wide ctypes.windll.user32 has its argtypes rewritten by other modules, and a pointer passed as
# LPARAM (LB_GETTEXT buffers) then overflows. (Measured: list items silently vanished until this was a private instance.)
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_u32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_u32.SendMessageW.restype = ctypes.c_ssize_t
_u32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_size_t)]
_u32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
_u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_u32.PostMessageW.restype = wt.BOOL
for _fn in ("IsWindow", "IsWindowVisible", "IsWindowEnabled", "GetDlgCtrlID", "GetWindowTextLengthW"):
    getattr(_u32, _fn).argtypes = [wt.HWND]
_u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_u32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_u32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
_u32.GetWindowLongW.restype = ctypes.c_long
_u32.EnumChildWindows.argtypes = [wt.HWND, ctypes.c_void_p, wt.LPARAM]
BM_CLICK = 0x00F5
COMMIT_RX = re.compile(r"^(ok|save|open|apply|yes|done|finish|select|add|create|continue|install|accept|go|export|import|replace|delete|remove|reset|clear|run|start|send)\b", re.I)
CANCEL_RX = re.compile(r"^(cancel|close|no|discard|dismiss|abort|exit|not now)\b", re.I)
NEXT_RX = re.compile(r"^(next|continue|forward)\b|^>\s*$|next\s*>", re.I)
OPENER_RX = re.compile(r"(\.\.\.|…)\s*$")
UNSAFE_RX = re.compile(r"\b(exit|quit|close|delete|remove|erase|format|uninstall|sign out|log ?out|shutdown|restart|kill|terminate|empty|wipe|purge|factory|reset all)\b", re.I)
# Controls that start capturing the user's screen, camera or microphone, or send/publish/sign something, are never opened by a scan (an ellipsis does not make them a harmless dialog).
SENSITIVE_RX = re.compile(r"\b(record(ing)?|capture|screen ?(clip|shot|recording)|screenshot|camera|cameo|webcam|microphone|dictat\w*|share|send|e-?mail|publish|post|upload|sign ?(in|out)|log ?(in|out)|account|"
                          r"profile|invite|collaborat\w*|comment|present in teams|print|fax|pay|purchase|buy|subscribe|activate|license|feedback|contact support|report a problem|telemetry|privacy|online|stock|brand images|onedrive|sharepoint|cloud|bing|marketplace|store|get add-?ins|templates and themes|sign|connected)\b", re.I)
CHROME = {"minimize", "maximize", "restore", "close", "system", "keep on top"}


def _fold(s: str) -> str:
    return C.fold(s)


def _hwnd_of(node) -> int:
    try:
        return int(node.ctrl.NativeWindowHandle or 0)
    except Exception:
        return 0


def _item(n, popup: int, local: bool) -> SimpleNamespace:
    """fast_uia.Node has __slots__: a menu item read from a drop-down carries the drop-down window and whether its rectangle is local to it."""
    return SimpleNamespace(name=n.name, rect=n.rect, pats=n.pats, accel=n.accel, aid=n.aid, help=n.help, ctype=n.ctype, idx=n.idx, enabled=n.enabled, offscreen=n.offscreen,
                           _popup=popup, _local=local, el=n.el, node=n)


def _center(node) -> Tuple[int, int]:
    l, t, r, b = node.rect
    return (l + r) // 2, (t + b) // 2


def _enum_children(top: int) -> List[Tuple[int, str, str]]:
    out: List[Tuple[int, str, str]] = []
    cb_t = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(h, _):
        n = _u32.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 2)
        _u32.GetWindowTextW(h, b, n + 2)
        c = ctypes.create_unicode_buffer(128)
        _u32.GetClassNameW(h, c, 128)
        out.append((int(h), b.value, c.value))
        return True
    _u32.EnumChildWindows(top, cb_t(cb), 0)
    return out


class Explorer:
    def __init__(self, hwnd: int, app_name: str, app_key: str, model, *, store: Optional[C.AtlasStore] = None, pristine: bool = False, budget_s: float = 60.0,
                 log=None, run_id: str = "", learner=None):
        from core_organs import fast_uia
        from core_organs import headless_input as hin
        from core_organs import organ_48_app_behavior_model as bm
        from core_organs import organ_63_app_mastery as m63
        from core_organs import knowledge_store as ks
        self.fast_uia, self.hin, self.bm, self.m63, self.ks = fast_uia, hin, bm, m63, ks
        self.hwnd, self.name, self.key, self.model = hwnd, app_name, app_key, model
        self.store = store or C.get_store()
        self.pristine = pristine
        self.budget_s = budget_s
        self.log = log or (lambda s: None)
        self.run_id = run_id or f"x_{int(time.time())}"
        self.learner = learner
        self.t0 = time.time()
        self.stats: Dict[str, Any] = {"menus": 0, "menu_items": 0, "tabs": 0, "openers": 0, "dialogs": 0, "pages": 0, "controls": 0, "commands": 0, "unwind_failures": 0, "timings": {}}
        self.seen_dialogs: Dict[str, Dict[str, Any]] = {}
        self.baseline_sig = ""
        self.records: List[Dict[str, Any]] = []
        self.probed: Set[str] = set()
        self.carto = None
        self.uimap: Dict[str, Any] = {}

    # ---- helpers
    def left(self) -> float:
        return self.budget_s - (time.time() - self.t0)

    def snap(self, h: Optional[int] = None, ms: int = 5000):
        return self.fast_uia.snapshot(h or self.hwnd, timeout_ms=ms) or []

    def popups(self) -> List[int]:
        out: List[int] = []
        try:
            for w in self.bm._popups(self.hwnd):
                c = ctypes.create_unicode_buffer(64)
                _u32.GetClassNameW(w, c, 64)
                if c.value != "SysShadow":
                    out.append(int(w))
        except Exception:
            pass
        return out

    def signature(self, nodes) -> str:
        return self.m63.derive_state(nodes)["signature"] if nodes else ""

    def opnames(self, nodes) -> Set[str]:
        return {_fold(n.name) for n in nodes if n.name and n.ctype in ("ButtonControl", "MenuItemControl", "TabItemControl", "CheckBoxControl", "RadioButtonControl", "ComboBoxControl", "EditControl", "ListItemControl", "SplitButtonControl", "HyperlinkControl")}

    def uia(self, node, getter: str, call: str, wait: float = 1.5) -> Tuple[bool, str]:
        return self.m63._uia_call(node, getter, call, wait_s=wait)

    def close_surfaces(self, base: List[int]) -> bool:
        ok = self.m63.close_popups(self.hwnd, base, timeout_s=1.5)
        t_end = time.time() + 1.5
        while time.time() < t_end:
            left = [w for w in self.popups() if w not in base]
            if not left:
                return True
            for w in left:
                _u32.PostMessageW(w, 0x0010, 0, 0)
            time.sleep(0.15)
        return not [w for w in self.popups() if w not in base]

    # ---- reading a surface when UIA may be blocked
    def safe_snap(self, h: int, limit: float = 2.0):
        """UIA snapshot with a hard wall-clock limit (a call into a process whose UIA provider is stuck behind a modal Invoke never returns)."""
        box: Dict[str, Any] = {}

        def run():
            try:
                box["v"] = self.fast_uia.snapshot(h, timeout_ms=int(limit * 1000))
            except Exception:
                box["v"] = None
        th = threading.Thread(target=run, daemon=True)
        th.start()
        th.join(limit + 0.5)
        return box.get("v") if not th.is_alive() else None

    def win32_schema(self, dlg: int) -> List[Dict[str, Any]]:
        """Controls of a dialog read with plain Win32 (child windows, button styles, list-box messages): independent of UI Automation. Edit values are NEVER read."""
        out: List[Dict[str, Any]] = []
        for h, text, cls in _enum_children(dlg):
            up = cls.upper()
            if not _u32.IsWindowVisible(h):
                continue
            kind = None
            if "BUTTON" in up:
                bs = _u32.GetWindowLongW(h, -16) & 0xF
                kind = "checkbox" if bs in (2, 3, 5, 6) else "radio" if bs in (4, 9) else None if bs == 7 else "button"
            elif "COMBOBOX" in up:
                kind, text = "combobox", ""
            elif "EDIT" in up:
                kind, text = "edit", ""
            elif "LISTBOX" in up:
                kind, text = "list", ""
            elif "STATIC" in up or "LABEL" in up:
                kind = "label" if text else None
            elif "TRACKBAR" in up:
                kind, text = "slider", ""
            elif "TABCONTROL" in up:
                kind, text = "tab", ""
            if not kind:
                continue
            ent = {"name": text, "kind": kind, "enabled": bool(_u32.IsWindowEnabled(h)), "pats": [], "aid": "", "hwnd": h}
            out.append(ent)
            if kind == "list":
                try:
                    n = int(_u32.SendMessageW(h, 0x018B, 0, 0))               # LB_GETCOUNT
                    for i in range(min(n, 40)):
                        ln = int(_u32.SendMessageW(h, 0x018A, i, 0))          # LB_GETTEXTLEN
                        if 0 < ln < 200:
                            buf = ctypes.create_unicode_buffer(ln + 2)
                            _u32.SendMessageW(h, 0x0189, i, ctypes.addressof(buf))   # LB_GETTEXT
                            if buf.value:
                                out.append({"name": buf.value, "kind": "listitem", "enabled": True, "pats": [], "aid": "", "hwnd": h, "index": i})
                except Exception:
                    pass
        return out

    def read_surface(self, w: int, uia_first: bool = True) -> Tuple[List[Dict[str, Any]], str, List[Any]]:
        """(controls, via, uia nodes). UIA first (bounded) unless the opening call is known to have blocked it; plain Win32 otherwise."""
        nodes = self.safe_snap(w, 1.8) if uia_first else None
        if nodes:
            return self.schema(nodes), "uia", nodes
        return self.win32_schema(w), "win32", []

    def win32_master_detail(self, dlg: int, title: str, via: str, base_names: Set[str], all_ctrls: List[Dict[str, Any]], info: Dict[str, Any]) -> None:
        """Select every item of a native list box (LB_SETCURSEL + the LBN_SELCHANGE notification a user's click would send) and diff the dialog."""
        lists = [c for c in self.win32_schema(dlg) if c["kind"] == "list"]
        for lst in lists:
            lh = lst["hwnd"]
            items = [c for c in self.win32_schema(dlg) if c["kind"] == "listitem" and c.get("hwnd") == lh]
            if len(items) < 2:
                continue
            info["master_detail"] = True
            ctl_id = _u32.GetDlgCtrlID(lh)
            res = ctypes.c_size_t(0)
            for it in items[:14]:
                if self.left() < 3:
                    break
                _u32.SendMessageTimeoutW(lh, 0x0186, it["index"], 0, 0x0002, 1500, ctypes.byref(res))                 # LB_SETCURSEL
                _u32.SendMessageTimeoutW(dlg, 0x0111, (1 << 16) | (ctl_id & 0xFFFF), lh, 0x0002, 1500, ctypes.byref(res))   # WM_COMMAND, LBN_SELCHANGE
                time.sleep(0.25)
                pg = self.win32_schema(dlg)
                pc = [c for c in pg if _fold(c["name"]) not in base_names and c["kind"] not in ("listitem", "list") and c["name"]]
                shown = [c for c in pg if c["kind"] in ("edit", "combobox", "checkbox", "radio", "slider", "button") and c["hwnd"] not in {a.get("hwnd") for a in all_ctrls}]
                if pc or shown:
                    info["pages"] += 1
                    self.stats["pages"] += 1
                    page_ctrls = pc + [c for c in shown if c not in pc]
                    all_ctrls += page_ctrls
                    self.stats["commands"] += self.put_commands([c for c in page_ctrls if c["name"]], f"{title} > {it['name']}", "atlas:dialog-page")
                    try:
                        self.ks.put_dialog(self.model, self.key, f"{title} > {it['name']}", page_ctrls, source="atlas:explorer", via=f"{via} > {it['name']}")
                    except Exception:
                        pass
                    for c in page_ctrls:
                        c["hwnd"] = c.get("hwnd")
            if items:
                _u32.SendMessageTimeoutW(lh, 0x0186, items[0]["index"], 0, 0x0002, 1500, ctypes.byref(res))
                _u32.SendMessageTimeoutW(dlg, 0x0111, (1 << 16) | (ctl_id & 0xFFFF), lh, 0x0002, 1500, ctypes.byref(res))

    def click_button(self, dlg: int, name: str) -> bool:
        """BM_CLICK to the dialog's own button with that text: asynchronous, needs no UIA, and unblocks a pending modal Invoke."""
        for hh, txt, cc in _enum_children(dlg):
            if txt == name and "BUTTON" in cc.upper():
                return bool(_u32.PostMessageW(hh, BM_CLICK, 0, 0))
        return False

    # ---- triggering (the ladder)
    def trigger(self, node, *, owner_top: Optional[int] = None) -> Tuple[bool, str]:
        top = owner_top or self.hwnd
        h = _hwnd_of(node)
        cls = ""
        if h:
            c = ctypes.create_unicode_buffer(128)
            _u32.GetClassNameW(h, c, 128)
            cls = c.value
        if h and h != top and re.search(r"button", cls, re.I):
            return bool(_u32.PostMessageW(h, BM_CLICK, 0, 0)), f"BM_CLICK->{cls}"
        if h == 0 and node.name:                                   # a button whose HWND UIA did not report: find it by text
            for hh, txt, cc in _enum_children(top):
                if txt == node.name and re.search(r"button", cc, re.I):
                    return bool(_u32.PostMessageW(hh, BM_CLICK, 0, 0)), f"BM_CLICK->{cc}"
        l, t, r, b = node.rect
        if r > l and b > t and not (l == t == r == b == 0):
            from . import gestures as G
            cx, cy = (l + r) // 2, (t + b) // 2
            ptr = G.Pointer(top)
            ok, note = ptr.click(cx, cy, "left")
            return ok, "posted click " + note
        ok, how = self.uia(node, "GetInvokePattern", "Invoke", wait=1.2)
        return ok, "UIA " + how + " (last resort)"

    # ---- schema of a surface
    def schema(self, nodes) -> List[Dict[str, Any]]:
        out = []
        kind = {"ButtonControl": "button", "CheckBoxControl": "checkbox", "RadioButtonControl": "radio", "EditControl": "edit", "ComboBoxControl": "combobox", "ListControl": "list",
                "ListItemControl": "listitem", "TabItemControl": "tab", "SliderControl": "slider", "SpinnerControl": "spinner", "TreeControl": "tree", "TreeItemControl": "treeitem",
                "DataGridControl": "grid", "HyperlinkControl": "link", "SplitButtonControl": "splitbutton", "MenuItemControl": "menuitem", "DocumentControl": "document", "TextControl": "label"}
        for n in nodes:
            k = kind.get(n.ctype)
            if not k or (k == "label" and not n.name) or (n.name and _fold(n.name) in CHROME):
                continue
            if k in ("button", "edit", "combobox", "spinner", "slider", "checkbox", "radio") and not n.name and not n.aid:
                continue
            out.append({"name": n.name or n.aid, "kind": k, "enabled": bool(n.enabled), "pats": list(n.pats), "aid": n.aid})
        return out

    # ---- persistence into the engine's database
    def put_commands(self, controls: List[Dict[str, Any]], path_prefix: str, origin: str) -> int:
        n = 0
        for c in controls:
            if not c["name"] or c["kind"] in ("label", "listitem", "treeitem", "document"):
                continue
            nm = re.sub(r"\s+", " ", c["name"]).strip()
            if not nm or len(nm) > 80:
                continue
            try:
                self.model.upsert_command(self.key, {"name": nm, "menu_path": f"{path_prefix} > {nm}" if path_prefix else nm, "verb": "invoke" if c["kind"] in ("button", "menuitem", "splitbutton", "link") else c["kind"],
                                                     "risk": "E2" if UNSAFE_RX.search(nm) else None, "automation_id": c.get("aid") or None},
                                          source="learned", origin=origin, evidence=f"read from a {c['kind']} while exploring {path_prefix or 'the main window'}")
                n += 1
            except Exception:
                continue
        return n

    # ---- PASS 1: menus
    def menus(self, nodes) -> None:
        t0 = time.time()
        bars = [n for n in nodes if n.ctype == "MenuBarControl" and _fold(n.name) != "system"]
        tops: List[Any] = []
        for b in bars:
            tops += [nodes[i] for i in b.children if nodes[i].ctype == "MenuItemControl" and nodes[i].name and _fold(nodes[i].name) not in CHROME]
        if not tops:
            tops = [n for n in nodes if n.ctype == "MenuItemControl" and ("expand" in n.pats or "invoke" in n.pats) and n.name and _fold(n.name) not in CHROME and n.depth <= 4 and n.rect != (0, 0, 0, 0)]
        for top in tops:
            if self.left() < 3:
                break
            self._menu_branch(top)
        self.stats["timings"]["menus_s"] = round(time.time() - t0, 2)

    def _open_header(self, top) -> Tuple[List[int], List[Any]]:
        """Open a menu-bar entry. Returns (new popup windows, its items). Items are read from the popup window when it carries a UIA tree, otherwise
        from the header's children in the main tree (WinForms/WPF expose drop-down items there, with coordinates local to the drop-down)."""
        base = self.popups()
        if "expand" in top.pats:
            self.uia(top, "GetExpandCollapsePattern", "Expand", wait=1.0)
        else:
            self.trigger(top)
        end = time.time() + 1.6
        new: List[int] = []
        while time.time() < end:
            time.sleep(0.12)
            new = [w for w in self.popups() if w not in base]
            if new:
                break
        time.sleep(0.2)
        items: List[Any] = []
        for w in new[:3]:
            for n in self.snap(w, ms=3000):
                if n.ctype == "MenuItemControl" and n.name and _fold(n.name) not in CHROME:
                    items.append(_item(n, w, False))
        if not items:
            tree = self.snap(ms=3000)
            kid = {n.idx for n in tree if n.parent == top.idx}
            # re-find the header in the fresh tree (indices change between snapshots)
            hdr = next((n for n in tree if n.ctype == "MenuItemControl" and n.name == top.name and n.rect == top.rect), None) or next((n for n in tree if n.ctype == "MenuItemControl" and n.name == top.name), None)
            if hdr is not None:
                for n in tree:
                    if n.parent == hdr.idx and n.ctype == "MenuItemControl" and n.name and _fold(n.name) not in CHROME:
                        items.append(_item(n, new[0] if new else 0, True))
        return new, items

    def _menu_branch(self, top) -> None:
        base = self.popups()
        new, items = self._open_header(top)
        if not items:
            self.close_surfaces(base)
            return
        self.stats["menus"] += 1
        opener_names: List[str] = []
        for n in items:
            full = f"{top.name} > {n.name}"
            self.stats["menu_items"] += 1
            try:
                self.model.upsert_command(self.key, {"name": n.name, "menu_path": full, "verb": "invoke", "shortcut": (n.accel or "").replace(" ", "") or None,
                                                     "risk": "E2" if UNSAFE_RX.search(n.name) else None, "automation_id": n.aid or None},
                                          source="learned", origin="atlas:menu", evidence="read from the open menu" + (f"; accelerator {n.accel}" if n.accel else "") + (f"; help {n.help[:60]}" if n.help else ""))
                self.stats["commands"] += 1
            except Exception:
                pass
            if OPENER_RX.search(n.name) and not UNSAFE_RX.search(n.name):
                opener_names.append(n.name)
        self.close_surfaces(base)
        for nm in opener_names:
            if self.left() < 5:
                break
            self._menu_opener(top, nm)

    def _menu_opener(self, top, item_name: str) -> None:
        t0 = time.time()
        base = self.popups()
        sig0 = self.signature(self.snap())
        new, items = self._open_header(top)
        node = next((n for n in items if n.name == item_name), None)
        if node is None:
            self.close_surfaces(base)
            return
        # a modal menu loop reads the PHYSICAL pointer (a posted click closes the menu), so a menu ITEM is invoked through UIA on a worker thread:
        # the call may block until the dialog it opens is closed, which is why the dialog is then read with the bounded/Win32 ladder
        ok, how = self.uia(node.node, "GetInvokePattern", "Invoke", wait=1.2)
        end = time.time() + 2.5
        dlgs: List[int] = []
        while ok and time.time() < end:
            time.sleep(0.12)
            dlgs = [w for w in self.popups() if w not in base and w not in new and _u32.IsWindow(w)]
            if not dlgs:                                   # a dialog that is not matched as a popup: any new visible window of the process
                dlgs = [w for w in self.hin.process_windows(self.hwnd, include_hidden=False) if w != self.hwnd and w not in base and w not in new and _u32.IsWindowVisible(w)
                        and not (ctypes.create_unicode_buffer(64) and False)]
                dlgs = [w for w in dlgs if self._class_of(w) != "SysShadow"]
            if dlgs:
                break
        rec: Dict[str, Any] = {"label": f"{top.name} > {item_name}", "via": how}
        if dlgs:
            time.sleep(0.3)
            w = dlgs[0]
            title = self.bm._win_title(w) or self.bm._win_class(w)
            info = self.learn_dialog(w, title, via=f"{top.name} > {item_name}", uia_blocked="still running" in how)
            rec.update(effect="dialog", dialog=title, controls=info.get("controls"), pages=info.get("pages"), read_via=info.get("read_via"))
            self.stats["openers"] += 1
        else:
            rec["effect"] = "none"
        rec["unwound"] = self.close_surfaces(base)
        rec["restored"] = self.signature(self.snap()) == sig0
        if not (rec["unwound"] and rec["restored"]):
            self.stats["unwind_failures"] += 1
        rec["seconds"] = round(time.time() - t0, 2)
        self.records.append(rec)

    @staticmethod
    def _class_of(h: int) -> str:
        c = ctypes.create_unicode_buffer(128)
        _u32.GetClassNameW(h, c, 128)
        return c.value

    # ---- PASS 2: tabs
    def tabs(self, nodes) -> None:
        t0 = time.time()
        groups: Dict[int, List[Any]] = {}
        for n in nodes:
            if n.ctype == "TabItemControl" and "select" in n.pats:
                groups.setdefault(n.parent, []).append(n)
        for parent, items in groups.items():
            if len(items) < 2:
                continue
            orig = next((i for i in items if i.selected), None)
            base_nodes = self.snap()
            base_names = self.opnames(base_nodes)
            for it in items:
                if self.left() < 3:
                    break
                if it is orig:
                    continue
                ok, how = self.uia(it, "GetSelectionItemPattern", "Select", wait=1.0)
                if not ok:
                    continue
                time.sleep(0.3)
                after = self.snap()
                new = [n for n in after if n.name and _fold(n.name) not in base_names and n.ctype in ("ButtonControl", "CheckBoxControl", "RadioButtonControl", "ComboBoxControl", "EditControl", "SpinnerControl", "SliderControl", "ListControl", "ListItemControl", "SplitButtonControl", "TabItemControl")]
                ctrls = self.schema(after)
                revealed = [c for c in ctrls if _fold(c["name"]) not in base_names]
                self.stats["tabs"] += 1
                self.stats["controls"] += len(revealed)
                self.stats["commands"] += self.put_commands(revealed, it.name, "atlas:tab")
                try:
                    self.ks.put_dialog(self.model, self.key, f"tab: {it.name}", revealed, source="atlas:explorer", via=f"tab {it.name}")
                except Exception:
                    pass
                self.openers([n for n in after if _fold(n.name) not in base_names], tag=f"tab {it.name}")
            if orig is not None:
                self.uia(orig, "GetSelectionItemPattern", "Select", wait=1.0)
                time.sleep(0.25)
            elif items:
                pass
        self.stats["timings"]["tabs_s"] = round(time.time() - t0, 2)

    # ---- PASS 3: openers + the dialog protocol
    def openers(self, nodes, tag: str = "") -> None:
        t0 = time.time()
        cands: List[Any] = []
        for n in nodes:
            if not n.name or n.ctype not in ("ButtonControl", "SplitButtonControl", "HyperlinkControl") or _fold(n.name) in CHROME or not n.enabled or "invoke" not in n.pats and "expand" not in n.pats:
                continue
            if SENSITIVE_RX.search(n.name):
                continue
            par = nodes[n.parent] if 0 <= n.parent < len(nodes) else None
            if par is not None and par.ctype in ("SpinnerControl", "SliderControl", "ScrollBarControl", "ComboBoxControl", "ThumbControl", "TabControl", "TitleBarControl", "EditControl"):
                continue                                        # an internal part of a composite control (arrows, page buttons): clicking it changes a VALUE
            if n.rect == (0, 0, 0, 0) or n.offscreen and not self.pristine:
                continue
            if OPENER_RX.search(n.name) or (self.pristine and not UNSAFE_RX.search(n.name)):
                cands.append(n)
        # ellipsis openers first (they promise a surface), then unknown buttons
        cands.sort(key=lambda n: (not OPENER_RX.search(n.name), n.rect[1], n.rect[0]))
        done: Set[str] = set()
        for n in cands:
            if self.left() < 4:
                break
            k = _fold(n.name)
            if k in done:
                continue
            if k in self.probed:
                continue
            done.add(k)
            self.probed.add(k)
            rec = self.probe_opener(n)
            if rec:
                rec["where"] = tag or "main window"
                self.records.append(rec)
        self.stats["timings"]["openers_s"] = round(self.stats["timings"].get("openers_s", 0) + time.time() - t0, 2)

    def probe_opener(self, node) -> Optional[Dict[str, Any]]:
        t0 = time.time()
        base = self.popups()
        before = self.snap()
        sig0, names0 = self.signature(before), self.opnames(before)
        ok, how = self.trigger(node)
        deadline = time.time() + (2.5 if OPENER_RX.search(node.name or "") else 0.9)
        new: List[int] = []
        while ok and time.time() < deadline:
            time.sleep(0.1)
            new = [w for w in self.popups() if w not in base]
            if new:
                break
        pred = None
        if self.learner:
            pred = self.learner.predict("opener", {"label": node.name, "ctype": node.ctype})
        rec: Dict[str, Any] = {"label": node.name, "trigger": how, "seconds": 0.0}
        if not new:
            time.sleep(0.4)
            after = self.snap()
            changed = self.signature(after) != sig0 or self.opnames(after) != names0
            rec["effect"] = "inline_change" if changed else "none"
            if changed:
                self.stats["commands"] += self.put_commands([{"name": node.name, "kind": "button", "aid": node.aid}], "", "atlas:opener")
            if self.learner:
                self.learner.observe("opener", {"label": node.name, "ctype": node.ctype}, pred or "", rec["effect"], node.name)
            rec["seconds"] = round(time.time() - t0, 2)
            return rec
        time.sleep(0.25)
        self.stats["openers"] += 1
        for w in new[:1]:
            title = self.bm._win_title(w) or self.bm._win_class(w)
            info = self.learn_dialog(w, title, via=node.name)
            rec.update(effect="dialog", dialog=title, **{k: v for k, v in info.items() if k in ("controls", "pages", "wizard", "master_detail", "fields", "file_dialog", "commit", "cancel")})
        rec["unwound"] = self.close_surfaces(base)
        back = self.snap()
        rec["restored"] = self.signature(back) == sig0 and self.opnames(back) == names0
        if not (rec["unwound"] and rec["restored"]):
            self.stats["unwind_failures"] += 1
        if self.learner:
            self.learner.observe("opener", {"label": node.name, "ctype": node.ctype}, pred or "", "dialog", node.name)
        rec["seconds"] = round(time.time() - t0, 2)
        try:
            self.model.record_transition(self.key, self.m63._observed(self.hwnd, before), f"invoke:{node.name}", how, self.m63._observed(self.hwnd, before), f"opened '{rec.get('dialog')}'")
        except Exception:
            pass
        return rec

    # ---- the dialog protocol
    FILE_DLG_RX = re.compile(r"^(file ?name|folder|save as type|files of type|file type)", re.I)

    def learn_dialog(self, dlg: int, title: str, *, via: str, depth: int = 0, uia_blocked: bool = False) -> Dict[str, Any]:
        ctrls, how, nodes = self.read_surface(dlg, uia_first=not uia_blocked)
        file_dlg = any(self.FILE_DLG_RX.search(c.get("name") or "") for c in ctrls)
        if file_dlg:                                      # a file chooser lists the USER'S files and folders: the structure (fields, buttons) is knowledge, the contents are personal
            ctrls = [c for c in ctrls if c["kind"] not in ("listitem", "treeitem", "grid", "tree", "list")]
        info: Dict[str, Any] = {"title": title, "controls": len(ctrls), "pages": 0, "wizard": False, "master_detail": False, "read_via": how}
        base_names = {_fold(c["name"]) for c in ctrls}
        all_ctrls = list(ctrls)
        if how == "uia":                                   # master / detail: a list, tree or tab strip whose items can be selected
            masters: Dict[int, List[Any]] = {}
            for n in nodes:
                if n.ctype in ("ListItemControl", "TreeItemControl", "TabItemControl") and "select" in n.pats and n.name:
                    masters.setdefault(n.parent, []).append(n)
            for parent, items in masters.items():
                if len(items) < 2 or self.left() < 3:
                    continue
                info["master_detail"] = True
                for it in items[:12]:
                    ok, _ = self.uia(it, "GetSelectionItemPattern", "Select", wait=1.0)
                    if not ok:
                        continue
                    time.sleep(0.25)
                    pg = self.safe_snap(dlg, 2.0) or []
                    pc = [c for c in self.schema(pg) if _fold(c["name"]) not in base_names and _fold(c["name"]) != _fold(it.name)]
                    if pc:
                        info["pages"] += 1
                        self.stats["pages"] += 1
                        all_ctrls += pc
                        self.stats["commands"] += self.put_commands(pc, f"{title} > {it.name}", "atlas:dialog-page")
                        try:
                            self.ks.put_dialog(self.model, self.key, f"{title} > {it.name}", pc, source="atlas:explorer", via=f"{via} > {it.name}")
                        except Exception:
                            pass
        if not info["master_detail"] and any(c["kind"] in ("listitem", "list") for c in (ctrls if how == "win32" else self.win32_schema(dlg))):
            self.win32_master_detail(dlg, title, via, base_names, all_ctrls, info)
        # wizard: follow Next (Win32 click, then re-read)
        steps = 0
        while steps < 4 and self.left() > 3:
            cur, _how, _n = self.read_surface(dlg)
            nxt = next((c for c in cur if c["kind"] == "button" and c.get("enabled", True) and NEXT_RX.search(c["name"] or "")), None)
            if nxt is None or not self.click_button(dlg, nxt["name"]):
                break
            before_names = {_fold(c["name"]) for c in cur}
            time.sleep(0.45)
            pg, _h2, _n2 = self.read_surface(dlg)
            newc = [c for c in pg if _fold(c["name"]) not in base_names]
            page_title = next((c["name"] for c in pg if c["kind"] == "label" and c["name"] and _fold(c["name"]) not in before_names), f"page {steps + 2}")
            info["wizard"] = True
            info["pages"] += 1
            self.stats["pages"] += 1
            all_ctrls += newc
            self.stats["commands"] += self.put_commands(newc, f"{title} > {page_title}", "atlas:wizard-page")
            try:
                self.ks.put_dialog(self.model, self.key, f"{title} > {page_title}", pg, source="atlas:explorer", via=f"{via} > next")
            except Exception:
                pass
            steps += 1
        try:
            self.ks.put_dialog(self.model, self.key, title, [c for c in ctrls if c["name"] or c["kind"] in ("edit", "combobox", "list", "slider")], source="atlas:explorer", via=via)
        except Exception:
            pass
        self.stats["dialogs"] += 1
        self.stats["controls"] += len(all_ctrls)
        self.stats["commands"] += self.put_commands(ctrls, title, "atlas:dialog")
        info["controls"] = len(all_ctrls)
        info["file_dialog"] = file_dlg
        NOISE = re.compile(r"(to open this link|translate options|automatic profile switching|app available|search instead|preview pane|view slider|line up|context help|^new folder$|^organize$|^details$|^&?help$|richedit control)", re.I)
        info["fields"] = [{"name": c["name"], "kind": c["kind"]} for c in all_ctrls if c.get("name") and c["kind"] not in ("listitem", "treeitem", "grid", "document") and not (file_dlg and c["kind"] == "list") and not NOISE.search(c["name"])][:80]
        info["cancel"] = next((c["name"] for c in ctrls if c["kind"] == "button" and CANCEL_RX.search(c["name"] or "")), None)
        info["commit"] = next((c["name"] for c in ctrls if c["kind"] == "button" and COMMIT_RX.search(c["name"] or "")), None)
        self.seen_dialogs[title] = info
        # leave through Cancel (never the commit button); WM_CLOSE if there is none
        if info["cancel"] and self.click_button(dlg, info["cancel"]):
            time.sleep(0.45)
        else:
            _u32.PostMessageW(dlg, 0x0010, 0, 0)
            time.sleep(0.3)
        return info

    # ---- run
    def alive(self) -> bool:
        return bool(_u32.IsWindow(self.hwnd))

    def run(self, passes: Sequence[str] = ("ribbon", "menus", "tabs", "openers")) -> Dict[str, Any]:
        nodes = self.snap()
        self.baseline_sig = self.signature(nodes)
        names0 = self.opnames(nodes)
        main_ctrls = [c for c in self.schema(nodes) if c["kind"] not in ("label", "listitem", "treeitem", "document", "menuitem")]
        self.stats["commands"] += self.put_commands(main_ctrls, "", "atlas:main-window")
        self.stats["controls"] += len(main_ctrls)
        carto_ok = False
        if "ribbon" in passes and self.left() > 20:
            from . import uimap
            self.carto = uimap.Cartographer(self, budget_s=max(20.0, self.left() - 10.0), log=self.log, run_id=self.run_id)
            try:
                m = self.carto.run()
                carto_ok = bool(m.get("applicable")) and bool(m.get("surfaces"))
                self.stats["ribbon"] = {k: v for k, v in self.carto.stats.items()}
                self.stats["ribbon"]["seconds"] = m.get("seconds")
                if m.get("died"):
                    self.stats["ribbon"]["died"] = m["died"]
                if m.get("surfaces"):
                    self.stats["uimap_file"] = self.carto.save()
                    self.uimap = m
            except Exception as exc:
                self.stats["ribbon"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
            if not self.alive():
                self.stats["seconds"] = round(time.time() - self.t0, 1)
                self.stats["window_gone"] = True
                return self.stats
        if "menus" in passes and not carto_ok:
            self.menus(nodes)
        if "tabs" in passes and self.left() > 3 and not carto_ok:
            self.tabs(self.snap())
        if "openers" in passes and self.left() > 3:
            self.openers(self.snap())
        end = self.snap()
        self.stats["records"] = self.records[:40]
        self.stats["left_as_found"] = bool(self.signature(end) == self.baseline_sig and self.opnames(end) == names0 and not self.popups())
        self.stats["seconds"] = round(time.time() - self.t0, 1)
        return self.stats
