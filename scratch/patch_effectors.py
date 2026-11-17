import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/effectors.py"
s = io.open(P, "r", encoding="utf-8").read()

# 1. doc + imports + helpers
s = s.replace("""  * everything is HEADLESS: window messages and UI Automation patterns delivered to the exact control; no SetForegroundWindow, no SendInput, no physical mouse or
    keyboard, so the user's focus, cursor and typing are never touched (a framework that ignores posted input simply reports 'no effect' -- it is never retried physically)""",
"""  * everything is HEADLESS: window messages and UI Automation patterns delivered to the exact control; no SendInput, no physical mouse or keyboard, so the user's cursor and
    typing are never touched (a framework that ignores posted input simply reports 'no effect' -- it is never retried physically)
  * FOCUS: some toolkits take the foreground when they receive an action (measured on WinForms: a UI Automation Invoke or a tab click sometimes does). Every delivery is wrapped
    in a focus guard: if the target's process took the foreground, it is handed straight back to the window the user had (the repo's own primitive, no input synthesised).
    Actions that would open a modal dialog are not tried by the probe at all.""", 1)
s = s.replace("import ctypes\nimport ctypes.wintypes as wt\nimport re\n", "import ctypes\nimport ctypes.wintypes as wt\nimport functools\nimport re\n", 1)
s = s.replace("""WM_COMMAND, BM_CLICK, WM_CLOSE, WM_KEYDOWN, WM_KEYUP = 0x0111, 0x00F5, 0x0010, 0x0100, 0x0101
VK_ESCAPE = 0x1B
""", """WM_COMMAND, BM_CLICK, WM_CLOSE, WM_KEYDOWN, WM_KEYUP = 0x0111, 0x00F5, 0x0010, 0x0100, 0x0101
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
    \"\"\"Run a delivering method under the focus guard (see the module doc).\"\"\"
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
""", 1)
s = s.replace("""        self.log: List[Tuple[float, str, bool, str]] = []

    @property
    def allowed""", """        self.log: List[Tuple[float, str, bool, str]] = []
        self.keep_focus = True
        self.user_fg = 0                                   # the last foreground window that is NOT the target's: where focus goes back to
        self.focus_returns = 0                             # how many times the target took the foreground and it was handed back
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

    def _return_focus(self, was: int) -> None:
        \"\"\"The target's process now holds the foreground though it did not before -> give it back to the user's window. Never fights the USER: if the foreground moved to a
        window of some other process, that was the user's doing and is left alone.\"\"\"
        if not self.keep_focus:
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
    def allowed""", 1)

# 2. decorate the delivering methods
for name in ("command", "key", "text", "click_xy", "node", "deselect", "close_popups"):
    marker = f"    def {name}("
    assert marker in s, name
    s = s.replace(marker, "    @_guarded\n" + marker, 1)

ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("effectors patched")
