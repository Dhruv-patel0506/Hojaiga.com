"""
si_test_support.py -- helpers for run_system_intelligence_tests.py

Provides real, self-contained OS fixtures so tests can prove behaviour without
depending on a third-party app:

  NativeButtonWindow     a real Win32 top-level window with a native BUTTON child.
                         Counts BN_CLICKED so we can prove an action REALLY landed.
  clip_aware_action_proof()   PostMessage + UIA-Invoke reach the button even while
                         the OS pointer is clipped/frozen (no SetCursorPos needed).
  sprite_paint_proof()   screenshots under the virtual-cursor sprite and checks the
                         triangle actually painted (independent of pointer clip).
"""

import ctypes
import ctypes.wintypes as wt
import threading
import time
from typing import Any, Dict, Optional

user32 = ctypes.WinDLL("user32", use_last_error=True)  # private handle: never mutate shared windll.user32 prototypes
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetModuleHandleW.restype = wt.HMODULE

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wt.UINT]
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_KEYDOWN = 0x0100
WM_CHAR = 0x0102
BN_CLICKED = 0
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
BS_PUSHBUTTON = 0x0
BTN_ID = 1001


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


class NativeButtonWindow:
    """Real Win32 window + native push button. `clicks` increments per BN_CLICKED."""

    def __init__(self, title: str = "HJ-ClipProbe", button_text: str = "ProbeBtn",
                 x: int = 300, y: int = 300):
        self._x, self._y = x, y
        self.title = title
        self.button_text = button_text
        self.clicks = 0
        self.combos = []   # (ctrl, shift) for every 'S' keydown the window received
        self.chars = []    # WM_CHAR code points received
        self.hwnd: Optional[int] = None
        self.btn_hwnd: Optional[int] = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="NativeButtonWindow")
        self._cls = f"HJClipProbe_{int(time.time() * 1000) % 10_000_000}"

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_COMMAND and (wparam & 0xFFFF) == BTN_ID and ((wparam >> 16) & 0xFFFF) == BN_CLICKED:
            self.clicks += 1
            return 0
        if msg == WM_KEYDOWN and wparam == 0x53:
            ctrl = bool(user32.GetKeyState(0x11) & 0x8000)
            shift = bool(user32.GetKeyState(0x10) & 0x8000)
            self.combos.append((ctrl, shift))
            return 0
        if msg == WM_CHAR:
            self.chars.append(int(wparam))
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run(self):
        self._proc = WNDPROC(self._wndproc)  # keep a reference alive
        hinst = kernel32.GetModuleHandleW(None)
        wc = _WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = self._cls
        wc.hbrBackground = 6  # COLOR_WINDOW + 1
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(0, self._cls, self.title, WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                                           self._x, self._y, 360, 220, None, None, hinst, None)
        self.btn_hwnd = user32.CreateWindowExW(0, "BUTTON", self.button_text,
                                               WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                                               40, 40, 200, 60, self.hwnd, BTN_ID, hinst, None)
        self._ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def start(self) -> "NativeButtonWindow":
        self._thread.start()
        self._ready.wait(5)
        time.sleep(0.3)
        return self

    def button_center(self):
        r = wt.RECT()
        user32.GetWindowRect(self.btn_hwnd, ctypes.byref(r))
        return (r.left + r.right) // 2, (r.top + r.bottom) // 2

    def minimize(self):
        user32.ShowWindow(self.hwnd, 6)  # SW_MINIMIZE (our OWN fixture window)

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        self._thread.join(timeout=2)


def _wait_clicks(win: "NativeButtonWindow", before: int, timeout: float = 1.5) -> bool:
    """Poll (bounded) for the BN_CLICKED counter to advance."""
    end = time.time() + timeout
    while time.time() < end:
        if win.clicks > before:
            return True
        time.sleep(0.05)
    return win.clicks > before


def _cursor_pos():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def headless_action_proof() -> Dict[str, Any]:
    """Acceptance proof for the headless input layer, against REAL native windows:

      A  PostMessage click lands on a normal window's button
      B  UIA Invoke lands on a MINIMIZED window
      C  PostMessage click lands on a window COVERED by another window
      D  Ctrl+Shift+S posted as messages arrives WITH both modifiers (the old bug delivered a bare 'S')
      E  the user's physical pointer did not move by a single pixel during A-D
      F  the input guard refuses (and records) a legacy physical-input call
    """
    from core_organs import headless_input as hin
    from core_organs.desktop_grounding import DesktopGrounding, GroundedElement, _act_on_element
    out: Dict[str, Any] = {}
    guard_before = len(hin.VIOLATIONS)
    pointer_before = _cursor_pos()

    # ---- A: normal window
    a = NativeButtonWindow(title="HJ-Headless-A", x=200, y=200).start()
    try:
        r = wt.RECT()
        user32.GetWindowRect(a.btn_hwnd, ctypes.byref(r))
        cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
        before = a.clicks
        ok, note = hin.post_click(a.hwnd, cx, cy)
        out["A_postmessage_click"] = bool(ok) and _wait_clicks(a, before)
        out["A_note"] = note

        # ---- D: key combo with modifiers delivered headless
        a.combos.clear()
        ok, note = hin.post_key_combo(a.hwnd, "ctrl+shift+s")
        time.sleep(0.4)
        out["D_combo_mods_arrived"] = (True, True) in a.combos
        out["D_combos_seen"] = list(a.combos)
        out["D_note"] = note
        # plain text delivery
        a.chars.clear()
        hin.post_text(a.hwnd, "hi")
        time.sleep(0.2)
        out["text_wm_char_ok"] = [ord("h"), ord("i")] == a.chars or "hi" == "".join(map(chr, a.chars))

        # ---- B: minimized window, UIA invoke
        g = DesktopGrounding()
        a.minimize()
        time.sleep(0.6)
        out["B_window_minimized"] = bool(hin.is_minimized(a.hwnd))
        hwnd, els, rep = g.ground("HJ-Headless-A")
        target = next((e for e in els if "probebtn" in e.name.lower() and e.tier == "uia"), None)
        out["B_found_while_minimized"] = target is not None
        out["B_window_state"] = rep.get("window_state")
        if target is not None:
            before = a.clicks
            ok, how = _act_on_element(target, "click")
            out["B_uia_landed"] = bool(ok) and _wait_clicks(a, before)
            out["B_method"] = how
        else:
            out["B_uia_landed"] = False
    finally:
        a.stop()

    # ---- C: covered window
    under = NativeButtonWindow(title="HJ-Headless-Under", x=420, y=260).start()
    over = NativeButtonWindow(title="HJ-Headless-Over", x=420, y=260).start()  # same rect, on top
    try:
        r = wt.RECT()
        user32.GetWindowRect(under.btn_hwnd, ctypes.byref(r))
        cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
        b_under, b_over = under.clicks, over.clicks
        ok, note = hin.post_click(under.hwnd, cx, cy)
        time.sleep(0.4)
        out["C_covered_click_landed"] = under.clicks > b_under and over.clicks == b_over
        out["C_note"] = note
    finally:
        over.stop()
        under.stop()

    # ---- E / F
    pointer_after = _cursor_pos()
    out["E_pointer_untouched"] = pointer_before == pointer_after
    out["E_pointer"] = f"{pointer_before}->{pointer_after}"
    out["E_guard_violations_during"] = len(hin.VIOLATIONS) - guard_before
    n0 = len(hin.VIOLATIONS)
    try:
        import ctypes as _c
        _c.windll.user32.SetCursorPos(5, 5)     # legacy physical call: must be refused
    except Exception:
        pass
    out["F_guard_refused_legacy_call"] = (len(hin.VIOLATIONS) == n0 + 1) and _cursor_pos() == pointer_after
    out["ok"] = all([out["A_postmessage_click"], out.get("B_uia_landed"), out["C_covered_click_landed"],
                     out["D_combo_mods_arrived"], out["E_pointer_untouched"],
                     out["E_guard_violations_during"] == 0, out["F_guard_refused_legacy_call"]])
    return out


def sprite_paint_proof() -> Dict[str, Any]:
    """Capture the screen region under the virtual-cursor sprite tip (mss/DXGI-style
    grab, which -- unlike PIL ImageGrab -- includes layered overlay windows) and
    confirm the triangle actually painted. Independent of any pointer clip."""
    import numpy as np
    import mss
    from core_organs.visual_cursor import get_cursor, for_agent, release_agent

    vc = get_cursor()
    vc.show()
    time.sleep(0.5)

    def grab(region):
        with mss.MSS() as m:
            mon = m.monitors[1]
            shot = m.grab({"left": mon["left"] + region[0], "top": mon["top"] + region[1],
                           "width": region[2], "height": region[3]})
            return np.array(shot)[:, :, :3].astype(int)

    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    x, y = sw // 2, sh // 2
    region = (x - 40, y - 40, 240, 160)
    before = grab(region)
    spr = for_agent("hj_paint_probe", "PaintProbe")
    try:
        spr._x = spr._target_x = float(x)
        spr._y = spr._target_y = float(y)
        spr._visible = True
        time.sleep(0.8)
        after = grab(region)
    finally:
        release_agent("hj_paint_probe")
    changed = int((np.abs(before - after).sum(axis=2) > 60).sum())
    return {"changed_pixels": changed, "region": region, "painted": changed >= 100}
