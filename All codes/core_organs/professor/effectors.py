"""
professor.effectors -- the ONLY place where the Professor ever sends input to an application, and it is shut by default.

Policy (enforced here, not trusted to callers):
  * input is refused unless `allow_input=True` AND the window is either one the Professor launched itself (`owned=True`) or one the user explicitly authorised
  * everything is HEADLESS: window messages and UI Automation patterns delivered to the exact control; no SendInput, no physical mouse or keyboard, so the user's cursor and
    typing are never touched (a framework that ignores posted input simply reports 'no effect' -- it is never retried physically)
  * FOCUS: some toolkits take the foreground when they receive an action (measured on WinForms: a UI Automation Invoke or a tab click sometimes does). Every delivery is wrapped
    in a focus guard: if the target's process took the foreground, it is handed straight back to the window the user had (the repo's own primitive, no input synthesised).
    Actions that would open a modal dialog are not tried by the probe at all.
  * a UI Automation call can BLOCK for a long time when its handler opens a modal dialog (measured), so patterns run on a worker thread with a deadline
Each method returns (ok, how) and says honestly what was delivered; whether it had an EFFECT is decided by the caller from a before/after delta.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import contextlib
import functools
import re
import threading
import time
from typing import Any, List, Optional, Sequence, Tuple

_u = ctypes.WinDLL("user32", use_last_error=True)
_u.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_u.PostMessageW.restype = wt.BOOL
_u.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_u.GetWindow.argtypes = [wt.HWND, wt.UINT]
_u.GetWindow.restype = wt.HWND
WM_COMMAND, BM_CLICK, WM_CLOSE, WM_KEYDOWN, WM_KEYUP = 0x0111, 0x00F5, 0x0010, 0x0100, 0x0101
VK_ESCAPE = 0x1B
_fgu = ctypes.WinDLL("user32", use_last_error=True)            # a separate handle: focus bookkeeping must work even when tests stand in for `_u`
_fgu.GetForegroundWindow.restype = ctypes.c_void_p
_fgu.IsWindow.argtypes = [ctypes.c_void_p]
_fgu.IsIconic.argtypes = [ctypes.c_void_p]


def _fg() -> int:
    try:
        return int(_fgu.GetForegroundWindow() or 0)
    except Exception:
        return 0


def _guarded(fn):
    """Run a delivering method under the focus guard (see the module doc)."""
    @functools.wraps(fn)
    def wrapper(self, *a, **k):
        if not self.allowed:
            return fn(self, *a, **k)
        was = _fg()
        self._note_user_window(was)
        res = fn(self, *a, **k)
        self._return_focus(was)
        return res
    return wrapper


def pattern_of(ctrl: Any, name: str) -> Any:
    """The UI Automation pattern `name` ('Invoke', 'Toggle', 'SelectionItem', 'ExpandCollapse', 'Value', 'Text', 'LegacyIAccessible') of ANY control: the uiautomation package defines
    Get<Name>Pattern only on some control classes (a ListItem has no GetInvokePattern), GetPattern(PatternId) works on all of them."""
    g = getattr(ctrl, f"Get{name}Pattern", None)
    if g is not None:
        return g()
    import uiautomation as ua
    return ctrl.GetPattern(getattr(ua.PatternId, f"{name}Pattern"))


class InputRefused(Exception):
    pass


class Effector:
    def __init__(self, hwnd: int, allow_input: bool = False, owned: bool = False, authorized: bool = False):
        self.hwnd = hwnd
        self.allow_input = allow_input
        self.owned = owned
        self.authorized = authorized
        self.log: List[Tuple[float, str, bool, str]] = []
        self.keep_focus = True
        self.user_fg = 0                                   # the last foreground window that is NOT the target's: where focus goes back to
        self.focus_returns = 0                             # how many times the target took the foreground and it was handed back
        self._hold = 0                                     # >0 while a menu path is being opened and used: a flyout is dismissed the moment its window loses activation
        self.app_key = ""                                  # set by the executor: the key the learned pointer routes are filed under
        self.overlay: Any = None                           # the virtual cursor overlay (set by the executor): it glides along every pointer gesture
        self.native: Any = None                            # an adapter with .pointer_events(script): the application's own pointer interface
        self.visible_ok = False
        self._vp: Any = None
        self._note_user_window(_fg())

    def _pid(self, h: int) -> int:
        try:
            from core_organs import headless_input as hin
            return int(hin.window_pid(h)) if h else 0
        except Exception:
            return 0

    def _note_user_window(self, h: int) -> None:
        if h and self._pid(h) != self._pid(self.hwnd):
            self.user_fg = h

    # ---- the focus WATCH: while the Professor is probing / executing, a small thread notices the moment the target's process takes the foreground (toolkits activate themselves
    #      a little AFTER the message, longer under load) and hands it back to the user's window; it never fights the user (input within the last 300 ms = the user did it)
    def _user_busy(self) -> bool:
        try:
            from core_organs.background_window import user_idle_ms
            return user_idle_ms() < 300
        except Exception:
            return False

    @contextlib.contextmanager
    def holding(self, max_s: float = 6.0):
        """For the few seconds a flyout menu is open and being used: the foreground is NOT handed back (that would close the menu). It is handed back the moment this block ends."""
        self._hold += 1
        t0 = time.time()
        try:
            yield self
        finally:
            self._hold -= 1
            if self._hold <= 0:
                self._hold = 0
                time.sleep(0.15)
                self.restore_user_focus()
                self.log.append((time.time(), "hold released", True, f"held {time.time() - t0:.1f}s"))

    def restore_user_focus(self) -> bool:
        """Hand the foreground back to the user's window if the target's process holds it right now. True when it was handed back."""
        if self._hold:
            return False
        try:
            tpid = self._pid(self.hwnd)
            cur = _fg()
            back = self.user_fg
            if not cur or not tpid or self._pid(cur) != tpid or not back or not _fgu.IsWindow(back) or _fgu.IsIconic(back) or self._pid(back) == tpid:
                return False
            from core_organs import headless_input as hin
            hin._hand_back_focus(back)
            self.focus_returns += 1
            self.log.append((time.time(), "focus returned", _fg() == back, f"foreground handed back to {back} (watch)"))
            return True
        except Exception:
            return False

    @contextlib.contextmanager
    def focus_watch(self, interval: float = 0.05):
        if not (self.allowed and self.keep_focus):
            yield self
            return
        stop = threading.Event()
        self._note_user_window(_fg())

        def loop() -> None:
            last = 0.0
            while not stop.wait(interval):
                try:
                    cur = _fg()
                    if cur and self._pid(cur) == self._pid(self.hwnd):
                        if time.time() - last > 0.2 and not self._user_busy() and not self._hold:
                            self.restore_user_focus()
                            last = time.time()
                    else:
                        self._note_user_window(cur)
                except Exception:
                    pass

        th = threading.Thread(target=loop, name="effector-focus-watch", daemon=True)
        th.start()
        try:
            yield self
        finally:
            stop.set()
            th.join(1.0)
            time.sleep(0.15)
            self.restore_user_focus()

    def _return_focus(self, was: int) -> None:
        """The target's process now holds the foreground though it did not before -> give it back to the user's window. Never fights the USER: if the foreground moved to a
        window of some other process, that was the user's doing and is left alone."""
        if not self.keep_focus or self._hold:
            return
        try:
            time.sleep(0.12)                                # let the application react (toolkits activate themselves a moment after the message)
            cur = _fg()
            tpid = self._pid(self.hwnd)
            if not cur or not tpid or self._pid(cur) != tpid:
                return
            back = was if (was and self._pid(was) != tpid) else self.user_fg
            if not back or not _fgu.IsWindow(back) or _fgu.IsIconic(back) or self._pid(back) == tpid:
                return
            from core_organs import headless_input as hin
            hin._hand_back_focus(back)
            time.sleep(0.05)
            ok = _fg() == back
            self.focus_returns += 1
            self.log.append((time.time(), "focus returned", ok, f"foreground handed back to {back}"))
        except Exception:
            pass

    @property
    def allowed(self) -> bool:
        return bool(self.allow_input and (self.owned or self.authorized))

    def why_not(self) -> str:
        if not self.allow_input:
            return "input not enabled (allow_input is off)"
        if not (self.owned or self.authorized):
            return "the window is neither one the Professor launched nor one the user authorised"
        return ""

    def _gate(self, what: str) -> Optional[Tuple[bool, str]]:
        if self.allowed:
            return None
        res = (False, "refused: " + self.why_not())
        self.log.append((time.time(), what, False, res[1]))
        return res

    def _rec(self, what: str, res: Tuple[bool, str]) -> Tuple[bool, str]:
        self.log.append((time.time(), what, res[0], res[1]))
        return res

    # ------------------------------------------------------------------------------------------------------------ routes
    @_guarded
    def command(self, command_id: int) -> Tuple[bool, str]:
        """A native menu command: WM_COMMAND to the window that owns the menu -- exactly what clicking the item sends, without opening the menu."""
        g = self._gate(f"command {command_id}")
        if g:
            return g
        return self._rec(f"command {command_id}", (bool(_u.PostMessageW(self.hwnd, WM_COMMAND, int(command_id), 0)), f"WM_COMMAND {command_id}"))

    @_guarded
    def key(self, chord: str) -> Tuple[bool, str]:
        g = self._gate(f"key {chord}")
        if g:
            return g
        from core_organs import headless_input as hin
        ok, note = hin.post_key_combo(self.hwnd, chord.replace("Cmd", "Win").lower())
        return self._rec(f"key {chord}", (ok, note))

    @_guarded
    def text(self, text: str) -> Tuple[bool, str]:
        g = self._gate("text")
        if g:
            return g
        from core_organs import headless_input as hin
        return self._rec("text", hin.post_text(self.hwnd, text))

    @_guarded
    def insert_text(self, text: str, deadline_s: float = 2.5) -> Tuple[bool, str]:
        """Type into the window's main editor through UI Automation (ValuePattern, appending): for toolkits that ignore posted characters (XAML / WinUI measured on Notepad). No focus, no keystrokes."""
        g = self._gate("insert_text")
        if g:
            return g
        result: dict = {}

        def work() -> None:
            try:
                from core_organs import fast_uia
                nodes = fast_uia.snapshot(self.hwnd, timeout_ms=3000) or []
                def is_editor(n) -> bool:                                   # a DOCUMENT, or an edit big enough to be an editing surface (a 'Zoom' or 'Find' box is a field, not where text goes)
                    w, h = n.rect[2] - n.rect[0], n.rect[3] - n.rect[1]
                    return n.ctype == "DocumentControl" or (n.ctype == "EditControl" and w * h >= 40000 and h >= 60)
                cands = [n for n in nodes if "value" in (n.pats or []) and is_editor(n) and n.enabled and not n.offscreen and n.rect[2] > n.rect[0]]
                if not cands:
                    result["how"] = "no document / editor surface with a value pattern"
                    return

                def rank(n):
                    try:
                        foc = bool(n.ctrl.HasKeyboardFocus)
                    except Exception:
                        foc = False
                    return (1 if foc else 0, (n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1]))
                best = max(cands, key=rank)
                vp = pattern_of(best.ctrl, "Value")
                if vp is None or vp.IsReadOnly:
                    result["how"] = "editor is read-only"
                    return
                vp.SetValue((vp.Value or "") + text)
                result["how"] = f"UIA SetValue (append {len(text)} chars to '{best.name or best.ctype}')"
            except Exception as exc:
                result["how"] = f"UIA error {type(exc).__name__}"

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(deadline_s)
        how = result.get("how", "UIA call still running")
        return self._rec("insert_text", (how.startswith("UIA SetValue"), how))

    def pointer(self) -> Any:
        """The VIRTUAL MOUSE of this window (professor.pointer.VirtualPointer): every pointer action goes through it - posted messages, the in-process pointer agent, ghost touch, an adapter's own
        interface - in the order learned for this application; the person's mouse is never used."""
        if self._vp is None:
            from .pointer import VirtualPointer
            self._vp = VirtualPointer(self.hwnd, self.app_key, self, overlay=self.overlay, native=self.native, visible_ok=self.visible_ok)
        return self._vp

    def close_pointer(self) -> None:
        """Let the virtual mouse's in-process agent (if one was attached) leave the application."""
        if self._vp is not None:
            self._vp.close()
            self._vp = None

    def pointer_failed(self) -> None:
        """A pointer action was delivered but the screen did not change (the caller's verdict): the route that carried it is counted against, so a route that is only 'delivered' - never
        'effective' - is replaced by the next one (e.g. the in-process pointer agent) the next time."""
        if self._vp is not None:
            self._vp.note_ineffective()

    @_guarded
    def click_xy(self, sx: int, sy: int, button: str = "left", count: int = 1, mods: Sequence[str] = ()) -> Tuple[bool, str]:
        g = self._gate(f"click {sx},{sy}")
        if g:
            return g
        r = self.pointer().click(int(sx), int(sy), button, count, mods)
        return self._rec(f"click {sx},{sy}", (r.ok, f"virtual mouse ({r.route}): {r.note}" if r.ok else r.why))

    @_guarded
    def pointer_gesture(self, verb: str, *args: Any, **kw: Any) -> Tuple[bool, str]:
        """Any verb of the virtual mouse by name (hover, double_click, right_click, drag, drag_select, lasso, drag_drop, flick, wheel, hold ...); returns (delivered, how)."""
        g = self._gate(f"pointer {verb}")
        if g:
            return g
        fn = getattr(self.pointer(), verb, None)
        if fn is None or verb.startswith("_"):
            return self._rec(f"pointer {verb}", (False, f"the virtual mouse has no '{verb}'"))
        r = fn(*args, **kw)
        return self._rec(f"pointer {verb}", (r.ok, f"virtual mouse ({r.route}): {r.note}" if r.ok else r.why))

    @_guarded
    def node(self, node: Any, deadline_s: float = 1.5) -> Tuple[bool, str]:
        """Activate a UI Automation node (a fast_uia.Node): a Win32 button gets BM_CLICK; else the control's own pattern (Invoke / Toggle / SelectionItem / ExpandCollapse)
        on a worker thread; else a posted click at its centre."""
        name = getattr(node, "name", "") or "?"
        g = self._gate(f"node {name}")
        if g:
            return g
        try:
            from core_organs.atlas.explorer import _hwnd_of
            h = _hwnd_of(node)
        except Exception:
            h = 0
        if h and h != self.hwnd:
            c = ctypes.create_unicode_buffer(128)
            _u.GetClassNameW(h, c, 128)
            if re.search(r"button", c.value, re.I):
                return self._rec(f"node {name}", (bool(_u.PostMessageW(h, BM_CLICK, 0, 0)), f"BM_CLICK -> {c.value}"))
        result: dict = {}

        def work() -> None:
            try:
                ctrl = node.ctrl
                have = set(getattr(node, "pats", []) or [])
                for pname, call, label, need in (("Invoke", "Invoke", "Invoke", "invoke"), ("Toggle", "Toggle", "Toggle", "toggle"), ("SelectionItem", "Select", "Select", "select"),
                                                 ("ExpandCollapse", "Expand", "Expand", "expand")):
                    if have and need not in have:
                        continue
                    p = pattern_of(ctrl, pname)
                    if p is not None:
                        getattr(p, call)()
                        result["how"] = f"UIA {label}"
                        return
                try:                                                         # many XAML flyout items expose no standard pattern, only the legacy 'default action' (Press / Select)
                    lp = pattern_of(ctrl, "LegacyIAccessible")
                    if lp is not None and getattr(lp, "DefaultAction", ""):
                        lp.DoDefaultAction()
                        result["how"] = f"UIA LegacyIAccessible.DoDefaultAction ({lp.DefaultAction})"
                        return
                except Exception:
                    pass
                result["how"] = "no usable UIA pattern"
            except Exception as exc:
                result["how"] = f"UIA error {type(exc).__name__}"

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(deadline_s)
        if t.is_alive():
            return self._rec(f"node {name}", (True, f"UIA call still running after {deadline_s:.1f}s (its handler probably opened a modal dialog)"))
        how = result.get("how", "")
        if how.startswith("UIA ") and "error" not in how and "no usable" not in how:
            return self._rec(f"node {name}", (True, how))
        l, tp, r, b = getattr(node, "rect", (0, 0, 0, 0))
        if r > l and b > tp:
            ok, note = self.click_xy((l + r) // 2, (tp + b) // 2)
            return (ok, f"{how}; then {note}")
        return self._rec(f"node {name}", (False, how or "nothing deliverable"))

    @_guarded
    def set_value(self, node: Any, text: str, deadline_s: float = 1.5) -> Tuple[bool, str]:
        """Put `text` into an edit field through UI Automation's ValuePattern (no focus, no keystrokes): the application receives the value, the user's keyboard is not involved."""
        name = getattr(node, "name", "") or "?"
        g = self._gate(f"set_value {name}")
        if g:
            return g
        result: dict = {}

        def work() -> None:
            try:
                p = pattern_of(node.ctrl, "Value")
                if p is None:
                    result["how"] = "no value pattern"
                    return
                p.SetValue(text)
                result["how"] = "UIA SetValue"
            except Exception as exc:
                result["how"] = f"UIA error {type(exc).__name__}"

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(deadline_s)
        how = result.get("how", "UIA call still running")
        return self._rec(f"set_value {name}", (how == "UIA SetValue", how))

    @_guarded
    def deselect(self, node: Any, deadline_s: float = 1.5) -> Tuple[bool, str]:
        """Take a node out of the selection (SelectionItem.RemoveFromSelection) -- used to put a list back to 'nothing selected' after a probe selected an item."""
        name = getattr(node, "name", "") or "?"
        g = self._gate(f"deselect {name}")
        if g:
            return g
        result: dict = {}

        def work() -> None:
            try:
                p = pattern_of(node.ctrl, "SelectionItem")
                if p is None:
                    result["how"] = "no selection pattern"
                    return
                p.RemoveFromSelection()
                result["how"] = "UIA RemoveFromSelection"
            except Exception as exc:
                result["how"] = f"UIA error {type(exc).__name__}"

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(deadline_s)
        how = result.get("how", "UIA call still running")
        return self._rec(f"deselect {name}", ("error" not in how and how.startswith("UIA ") and "still" not in how, how))

    @_guarded
    def close_popups(self, before: Sequence[int]) -> int:
        """Dismiss top-level windows of THIS process that appeared since `before` (Escape, then WM_CLOSE) -- only ever windows our own probe opened."""
        g = self._gate("close popups")
        if g:
            return 0
        from core_organs import headless_input as hin
        n = 0
        known = set(before)
        # popups/menus (different window class) plus dialogs of the SAME toolkit class (a WinForms/Qt dialog has the frame's class): those count only when they are owned by this
        # window and did not exist before the probe -- i.e. something our own probe opened
        cands = list(hin.popup_windows(self.hwnd))
        try:
            for w in hin.process_windows(self.hwnd, include_hidden=False):
                if w != self.hwnd and w not in cands and w not in known and int(_u.GetWindow(w, 4) or 0) == int(self.hwnd):          # GW_OWNER
                    cands.append(w)
        except Exception:
            pass
        for w in cands:
            if w in known or not hin.is_alive(w):
                continue
            _u.PostMessageW(w, WM_KEYDOWN, VK_ESCAPE, 0)
            _u.PostMessageW(w, WM_KEYUP, VK_ESCAPE, 0)
            time.sleep(0.25)
            try:
                cls = hin._class_name(w)
            except Exception:
                cls = ""
            # a framework's own pop-up host (WinUI PopupWindowSiteBridge, the XAML core window ...) is NEVER destroyed: closing it breaks every later flyout of the application (measured on Notepad).
            # It is dismissed by Escape alone; only real dialogs / top-level windows get WM_CLOSE.
            if hin.is_alive(w) and not re.search(r"(popupwindowsitebridge|sitebridge|corewindow|xamlpopup|xaml_|popup|#32768|tooltip)", cls, re.I):
                _u.PostMessageW(w, WM_CLOSE, 0, 0)
                time.sleep(0.25)
            n += 0 if hin.is_alive(w) else 1
        return n
