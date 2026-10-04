"""
headless_input.py -- the ONLY way Hojaiga delivers input to an application.

Design law (product requirement):
  * The user's physical pointer and keyboard are NEVER touched. There is no
    SetCursorPos / mouse_event / keybd_event / SendInput / pyautogui in this
    layer, and none may be added. The visible blue-arrow sprite (visual_cursor)
    is the only cursor the user ever sees.
  * Every action is addressed to a specific window handle (HWND) and works while
    that window is minimized, covered, or partly off-screen.
  * Delivery preference per action: UIA pattern (done by the caller, desktop_grounding)
    -> window messages posted to the exact child HWND (this module).
  * If an action genuinely cannot be delivered headless, return (False, "UNDELIVERABLE: ...")
    with the reason. Never fall back to physical input.

Return convention for every public action: (ok: bool, note: str). ``ok`` means the
message was DELIVERED to the window; whether it had the intended effect is decided
by the caller's postcondition check (the DesktopVerifier), never assumed here.
"""

import ctypes
import ctypes.wintypes as wt
import logging
import os
import re
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.headless_input")

_IS_WINDOWS = os.name == "nt"

if _IS_WINDOWS:
    # Private DLL handles: never mutate the process-wide ctypes.windll prototypes.
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _g32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
    _H = ctypes.c_void_p

    _u32.PostMessageW.argtypes = [_H, wt.UINT, wt.WPARAM, wt.LPARAM]
    _u32.PostMessageW.restype = wt.BOOL
    _u32.SendMessageTimeoutW.argtypes = [_H, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                         ctypes.POINTER(ctypes.c_size_t)]
    _u32.SendMessageTimeoutW.restype = ctypes.c_size_t
    _u32.ScreenToClient.argtypes = [_H, ctypes.POINTER(wt.POINT)]
    _u32.ChildWindowFromPointEx.argtypes = [_H, wt.POINT, wt.UINT]
    _u32.ChildWindowFromPointEx.restype = _H
    _u32.GetWindowRect.argtypes = [_H, ctypes.POINTER(wt.RECT)]
    _u32.IsIconic.argtypes = [_H]
    _u32.IsWindow.argtypes = [_H]
    _u32.IsWindowVisible.argtypes = [_H]
    _u32.IsWindowEnabled.argtypes = [_H]
    _u32.GetDlgCtrlID.argtypes = [_H]
    _u32.GetWindowLongW.argtypes = [_H, ctypes.c_int]
    _u32.GetWindowLongW.restype = ctypes.c_long
    _u32.GetClassNameW.argtypes = [_H, wt.LPWSTR, ctypes.c_int]
    _u32.GetWindowTextW.argtypes = [_H, wt.LPWSTR, ctypes.c_int]
    _u32.GetWindowTextLengthW.argtypes = [_H]
    _u32.GetWindowThreadProcessId.argtypes = [_H, ctypes.POINTER(wt.DWORD)]
    _u32.GetWindowThreadProcessId.restype = wt.DWORD
    _u32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
    _u32.GetKeyboardState.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
    _u32.SetKeyboardState.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
    _u32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
    _u32.GetAncestor.argtypes = [_H, wt.UINT]
    _u32.GetAncestor.restype = _H
    _u32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wt.BOOL, _H, wt.LPARAM), wt.LPARAM]
    _u32.PrintWindow.argtypes = [_H, _H, wt.UINT]
    _u32.GetDC.argtypes = [_H]
    _u32.GetDC.restype = _H
    _u32.ReleaseDC.argtypes = [_H, _H]
    _g32.CreateCompatibleDC.argtypes = [_H]
    _g32.CreateCompatibleDC.restype = _H
    _g32.CreateCompatibleBitmap.argtypes = [_H, ctypes.c_int, ctypes.c_int]
    _g32.CreateCompatibleBitmap.restype = _H
    _g32.SelectObject.argtypes = [_H, _H]
    _g32.SelectObject.restype = _H
    _g32.DeleteObject.argtypes = [_H]
    _g32.DeleteDC.argtypes = [_H]
    _g32.GetDIBits.argtypes = [_H, _H, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
    _k32.GetCurrentThreadId.restype = wt.DWORD
    _dwm.DwmGetWindowAttribute.argtypes = [_H, wt.DWORD, ctypes.c_void_p, wt.DWORD]

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEWHEEL = 0x020A
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
EM_REPLACESEL = 0x00C2
WM_SETTEXT = 0x000C
SMTO_ABORTIFHUNG = 0x0002
CWP_SKIPINVISIBLE, CWP_SKIPDISABLED, CWP_SKIPTRANSPARENT = 0x1, 0x2, 0x4
MK_LBUTTON, MK_RBUTTON = 0x0001, 0x0002

UNDELIVERABLE = "UNDELIVERABLE"

# Generic Windows virtual-key table (no app logic).
_VK: Dict[str, int] = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "menu": 0x12,
    "win": 0x5B, "meta": 0x5B, "super": 0x5B,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "back": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}
_MODS = {0x11, 0x10, 0x12, 0x5B}
_EXTENDED = {0x25, 0x26, 0x27, 0x28, 0x21, 0x22, 0x23, 0x24, 0x2D, 0x2E}


def token_to_vk(tok: str) -> Optional[int]:
    t = (tok or "").strip().lower()
    if t in _VK:
        return _VK[t]
    if len(t) == 1 and t.isalnum():
        return ord(t.upper())
    return None


# ---------------------------------------------------------------------------
# Window inspection
# ---------------------------------------------------------------------------

def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _u32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_pid(hwnd: int) -> int:
    pid = wt.DWORD(0)
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def is_alive(hwnd: int) -> bool:
    return bool(_IS_WINDOWS and hwnd and _u32.IsWindow(hwnd))


def is_minimized(hwnd: int) -> bool:
    return bool(_IS_WINDOWS and hwnd and _u32.IsIconic(hwnd))


def is_cloaked(hwnd: int) -> bool:
    try:
        v = ctypes.c_int(0)
        _dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(v), ctypes.sizeof(v))
        return bool(v.value)
    except Exception:
        return False


def window_state(hwnd: int) -> Dict[str, object]:
    """Honest description of how reachable a window is (drives tier selection + reporting)."""
    if not is_alive(hwnd):
        return {"alive": False, "minimized": False, "covered": False, "state": "gone"}
    mini = is_minimized(hwnd)
    return {"alive": True, "minimized": mini, "cloaked": is_cloaked(hwnd),
            "state": "minimized" if mini else "normal"}


# Window classes that mark a XAML / WinUI host. These UI stacks take keyboard and pointer input through their own
# input pipeline (InputSite / CoreWindow), NOT through the window messages post_key_combo / post_drag send, so a posted
# key or drag is simply ignored. Detecting the host lets the caller REPORT that instead of failing silently, and
# route the action through UIA Invoke / ValuePattern (which XAML does honour).
_XAML_CLASSES = frozenset({
    "applicationframewindow", "windows.ui.core.corewindow", "winuidesktopwin32windowclass",
    "microsoft.ui.content.desktopchildsitebridge", "microsoft.ui.content.popupwindowsitebridge",
    "windows.ui.input.inputsite.windowclass", "inputsitewindowclass", "xaml_windowedpopupclass",
})


def is_xaml_host(hwnd: int) -> bool:
    """True when ``hwnd`` (or any window inside it) is a XAML / WinUI host window."""
    if not is_alive(hwnd):
        return False
    if _class_name(hwnd).lower() in _XAML_CLASSES:
        return True
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, ctypes.c_void_p, wt.LPARAM)
    def _cb(h, _l):
        try:
            if _class_name(h).lower() in _XAML_CLASSES:
                found.append(int(h))
                return False
        except Exception:
            pass
        return True
    try:
        _u32.EnumChildWindows(hwnd, _cb, 0)
    except Exception:
        pass
    return bool(found)


def process_windows(hwnd: int, include_hidden: bool = True) -> List[int]:
    """All top-level windows owned by the same process as ``hwnd`` (the app frame PLUS its
    popup hosts / menus / dialogs, which live in separate top-level windows and are invisible
    to a UIA walk of the main frame alone)."""
    if not is_alive(hwnd):
        return []
    pid = window_pid(hwnd)
    found: List[int] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, ctypes.c_void_p, wt.LPARAM)
    def _cb(h, _l):
        try:
            if window_pid(h) == pid and (include_hidden or _u32.IsWindowVisible(h)):
                found.append(int(h))
        except Exception:
            pass
        return True

    _u32.EnumWindows(_cb, 0)
    return found


def popup_windows(hwnd: int) -> List[int]:
    """Popups/menus/flyouts/dialogs of ``hwnd``'s app: same process, VISIBLE, not cloaked, and a
    DIFFERENT window class than the app frame. (Multi-window apps own many frames of the same
    class; those are other documents, not popups, and must never be merged into this window's UI.)"""
    if not is_alive(hwnd):
        return []
    main_cls = _class_name(hwnd)
    out = [w for w in process_windows(hwnd, include_hidden=False)
           if w != hwnd and not is_cloaked(w) and _class_name(w) != main_cls]
    # genuine popup/menu/flyout/dialog classes first, so a caller's cap never drops the open menu
    return sorted(out, key=lambda w: 0 if any(k in _class_name(w).lower()
                                              for k in ("popup", "menu", "#32768", "#32770", "flyout", "tooltip")) else 1)


def child_at(top_hwnd: int, sx: int, sy: int) -> int:
    """Deepest child window of ``top_hwnd`` under SCREEN point (sx, sy); falls back to top."""
    cur = top_hwnd
    for _ in range(12):
        pt = wt.POINT(int(sx), int(sy))
        _u32.ScreenToClient(cur, ctypes.byref(pt))
        child = _u32.ChildWindowFromPointEx(
            cur, pt, CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT)
        if not child or int(child) == int(cur):
            break
        cur = int(child)
    return cur


def safe_window_text(hwnd: int, timeout_ms: int = 150) -> str:
    """A window's title WITHOUT the deadlock GetWindowText can cause. For a window owned by THIS process,
    GetWindowText sends WM_GETTEXT to the thread that created it; a thread that never pumps messages (an overlay window
    created from a worker, or a test's main thread parked in an asyncio loop) never answers, so an EnumWindows+
    GetWindowText sweep from another thread hangs forever. This asks with a bounded SendMessageTimeout instead and
    returns '' when the owner does not answer in ``timeout_ms``."""
    if not (_IS_WINDOWS and hwnd):
        return ""
    buf = ctypes.create_unicode_buffer(512)
    res = ctypes.c_size_t(0)
    try:
        ok = _u32.SendMessageTimeoutW(hwnd, 0x000D, 512, ctypes.addressof(buf), SMTO_ABORTIFHUNG, timeout_ms,
                                      ctypes.byref(res))      # WM_GETTEXT
    except Exception:
        return ""
    return buf.value if ok else ""


def top_level_titles(visible_only: bool = True) -> List[Tuple[int, str]]:
    """[(hwnd, title)] for the top-level windows, read with safe_window_text (see there)."""
    out: List[Tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, ctypes.c_void_p, wt.LPARAM)
    def _cb(h, _l):
        try:
            if (not visible_only) or _u32.IsWindowVisible(h) or _u32.IsIconic(h):
                t = safe_window_text(int(h))
                if t:
                    out.append((int(h), t))
        except Exception:
            pass
        return True
    _u32.EnumWindows(_cb, 0)
    return out


BM_CLICK = 0x00F5
GWL_STYLE = -16
# BS_PUSHBUTTON, BS_DEFPUSHBUTTON, BS_COMMANDLINK, BS_DEFCOMMANDLINK: the button kinds that ANSWER a dialog (check
# boxes, radio buttons and group boxes share the "Button" class but only change a setting).
_BS_PUSH_KINDS = frozenset({0x0, 0x1, 0xE, 0xF})


def native_dialog_parts(top_hwnd: int) -> Tuple[List[Tuple[int, str, int]], List[str]]:
    """Read a classic Win32 dialog (a message box / #32770) WITHOUT UI Automation: ([(button_hwnd, caption, control_id)],
    [static text lines]). Plain GetClassName / WM_GETTEXT / GetDlgCtrlID queries - a few milliseconds and independent of
    how loaded the machine is, where a UIA walk of the same dialog was measured taking seconds while a model held the
    CPUs. Only visible, enabled push buttons are returned (the ids are the standard IDOK=1 / IDCANCEL=2 / IDYES=6 /
    IDNO=7 ..., so a caller can rank them by role rather than by caption)."""
    buttons: List[Tuple[int, str, int]] = []
    texts: List[str] = []
    if not is_alive(top_hwnd):
        return buttons, texts

    @ctypes.WINFUNCTYPE(wt.BOOL, ctypes.c_void_p, wt.LPARAM)
    def _cb(h, _l):
        try:
            h = int(h)
            cls = _class_name(h).lower()
            if cls == "button":
                style = int(_u32.GetWindowLongW(h, GWL_STYLE)) & 0xFFFFFFFF
                if ((style & 0xF) in _BS_PUSH_KINDS and _u32.IsWindowVisible(h) and _u32.IsWindowEnabled(h)):
                    cap = safe_window_text(h)
                    if cap:
                        buttons.append((h, cap, int(_u32.GetDlgCtrlID(h))))
            elif cls == "static":
                t = safe_window_text(h)
                if t.strip():
                    texts.append(t.strip())
        except Exception:
            pass
        return True
    try:
        _u32.EnumChildWindows(top_hwnd, _cb, 0)
    except Exception:
        pass
    return buttons, texts


def post_button_click(button_hwnd: int) -> Tuple[bool, str]:
    """Press a native push button by POSTING BM_CLICK to its own window - the button then does what a click on it does
    (WM_COMMAND to its dialog). No pointer, no keyboard, no focus change."""
    if not is_alive(button_hwnd):
        return False, f"{UNDELIVERABLE}: button window gone"
    if not _u32.PostMessageW(button_hwnd, BM_CLICK, 0, 0):
        return False, f"{UNDELIVERABLE}: PostMessage refused for BM_CLICK"
    return True, "bm-click"


def focused_control(top_hwnd: int) -> int:
    """The control that has keyboard focus INSIDE ``top_hwnd``'s UI thread (GetGUIThreadInfo - a read-only query),
    else ``top_hwnd`` itself. Posted characters belong to the focused control, not to the frame."""
    if not is_alive(top_hwnd):
        return top_hwnd

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", _H), ("hwndFocus", _H),
                    ("hwndCapture", _H), ("hwndMenuOwner", _H), ("hwndMoveSize", _H), ("hwndCaret", _H),
                    ("rcCaret", wt.RECT)]
    try:
        tid = _u32.GetWindowThreadProcessId(top_hwnd, None)
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        _u32.GetGUIThreadInfo.argtypes = [wt.DWORD, ctypes.POINTER(GUITHREADINFO)]
        if _u32.GetGUIThreadInfo(tid, ctypes.byref(info)) and info.hwndFocus:
            f = int(info.hwndFocus)
            if f == top_hwnd or _u32.GetAncestor(f, 2) == top_hwnd:
                return f
    except Exception:
        pass
    return top_hwnd


def _lparam_xy(x: int, y: int) -> int:
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)


# ---------------------------------------------------------------------------
# Mouse (window messages to the exact child HWND)
# ---------------------------------------------------------------------------

def post_click(hwnd: int, sx: int, sy: int, *, right: bool = False,
               double: bool = False) -> Tuple[bool, str]:
    if not _IS_WINDOWS:
        return False, f"{UNDELIVERABLE}: non-windows"
    if not is_alive(hwnd):
        return False, f"{UNDELIVERABLE}: window gone"
    if is_minimized(hwnd):
        return False, (f"{UNDELIVERABLE}: window minimized - screen coordinates are meaningless; "
                       "address the control through UIA instead")
    target = child_at(hwnd, sx, sy)
    pt = wt.POINT(int(sx), int(sy))
    _u32.ScreenToClient(target, ctypes.byref(pt))
    lp = _lparam_xy(pt.x, pt.y)
    down, up, mk = ((WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON) if right
                    else (WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON))
    ok = _u32.PostMessageW(target, WM_MOUSEMOVE, 0, lp)
    ok = _u32.PostMessageW(target, down, mk, lp) and ok
    time.sleep(0.03)
    ok = _u32.PostMessageW(target, up, 0, lp) and ok
    if double:
        time.sleep(0.03)
        _u32.PostMessageW(target, WM_LBUTTONDBLCLK, mk, lp)
        _u32.PostMessageW(target, up, 0, lp)
    note = f"postmessage-{'rclick' if right else 'click'}->{_class_name(target)}@({pt.x},{pt.y})"
    return bool(ok), note if ok else f"{UNDELIVERABLE}: PostMessage refused ({note})"


WM_MBUTTONDOWN, WM_MBUTTONUP, MK_MBUTTON = 0x0207, 0x0208, 0x0010
_DRAG_MESSAGES = {"left": (WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON),
                  "right": (WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON),
                  "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, MK_MBUTTON)}


def ellipse_points(cx: float, cy: float, rx: float, ry: float, n: int = 48,
                   start_deg: float = -90.0) -> List[Tuple[int, int]]:
    """Parametric ellipse sampled at ``n`` points (closed: the last point repeats the first). A circle is
    rx == ry. The result feeds post_drag(path=...) - there is no separate 'draw circle' code path."""
    import math
    n = max(8, int(n))
    a0 = math.radians(start_deg)
    pts = [(int(round(cx + rx * math.cos(a0 + 2 * math.pi * i / n))),
            int(round(cy + ry * math.sin(a0 + 2 * math.pi * i / n)))) for i in range(n)]
    pts.append(pts[0])
    return pts


def post_drag(hwnd: int, x0: int, y0: int, x1: int, y1: int, *, steps: int = 24, button: str = "left",
              duration_s: float = 0.4, path: Optional[List[Tuple[int, int]]] = None,
              on_point=None) -> Tuple[bool, str]:
    """Drag with the left (or right/middle) button WITHOUT touching the physical pointer:

        WM_MOUSEMOVE -> WM_xBUTTONDOWN -> N x WM_MOUSEMOVE (button flag held) -> WM_xBUTTONUP

    posted to the child control under the start point (``child_at``), with client-relative coordinates
    (the same convention post_click uses). Coordinates are SCREEN pixels, like post_click.

    ``path`` replaces the straight line with a sampled point list (circle/oval/any stroke): the same
    messages, the same ordering, the first point is where the button goes down and the last is where it
    comes up. The moves are TIME-SLICED over ``duration_s`` (a canvas needs ordered move events, not a
    burst that arrives in one scheduler quantum).

    Returns (delivered, note). ``delivered`` means every message was accepted by the target's queue; whether
    a stroke actually landed is decided by the caller's postcondition (pixel diff), never assumed here.

    ``on_point(x, y)`` (optional) is called as each point is posted, so an overlay (the visible blue-arrow
    sprite) can follow the stroke in step with the real messages."""
    if not _IS_WINDOWS:
        return False, f"{UNDELIVERABLE}: non-windows"
    if not is_alive(hwnd):
        return False, f"{UNDELIVERABLE}: window gone"
    if is_minimized(hwnd):
        return False, (f"{UNDELIVERABLE}: window minimized - screen coordinates are meaningless; "
                       "park it (background_window) or address the control through UIA")
    if button not in _DRAG_MESSAGES:
        return False, f"{UNDELIVERABLE}: unknown button '{button}'"
    down, up, mk = _DRAG_MESSAGES[button]
    if path and len(path) >= 2:
        pts = [(int(x), int(y)) for x, y in path]
    else:
        n = max(2, int(steps))
        pts = [(int(round(x0 + (x1 - x0) * i / n)), int(round(y0 + (y1 - y0) * i / n))) for i in range(n + 1)]
    target = child_at(hwnd, pts[0][0], pts[0][1])

    def lp(sx: int, sy: int) -> int:
        pt = wt.POINT(int(sx), int(sy))
        _u32.ScreenToClient(target, ctypes.byref(pt))
        return _lparam_xy(pt.x, pt.y)

    ok = _u32.PostMessageW(target, WM_MOUSEMOVE, 0, lp(*pts[0]))
    time.sleep(0.02)
    ok = _u32.PostMessageW(target, down, mk, lp(*pts[0])) and ok
    if on_point:
        on_point(*pts[0])
    slice_s = max(0.0, float(duration_s)) / max(1, len(pts) - 1)
    t_next = time.perf_counter()
    for sx, sy in pts[1:]:
        t_next += slice_s
        ok = _u32.PostMessageW(target, WM_MOUSEMOVE, mk, lp(sx, sy)) and ok
        if on_point:
            on_point(sx, sy)
        wait = t_next - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
    time.sleep(0.02)
    ok = _u32.PostMessageW(target, up, 0, lp(*pts[-1])) and ok
    note = (f"postmessage-drag-{button}->{_class_name(target)} {len(pts)} points "
            f"({pts[0][0]},{pts[0][1]})->({pts[-1][0]},{pts[-1][1]}) over {duration_s:.2f}s")
    return bool(ok), note if ok else f"{UNDELIVERABLE}: PostMessage refused ({note})"


def changed_pixels(before, after, threshold: int = 24) -> Tuple[int, Optional[Tuple[int, int, int, int]]]:
    """(# pixels whose grayscale moved by more than ``threshold``, bounding box of the change) between two
    same-size PIL images; (-1, None) when they cannot be compared. The independent evidence a stroke landed."""
    try:
        from PIL import ImageChops
        if before is None or after is None or before.size != after.size:
            return -1, None
        diff = ImageChops.difference(before.convert("RGB"), after.convert("RGB")).convert("L")
        mask = diff.point(lambda v: 255 if v > threshold else 0)
        return int(sum(1 for v in mask.getdata() if v)), mask.getbbox()
    except Exception:
        return -1, None


def post_drag_verified(hwnd: int, x0: int, y0: int, x1: int, y1: int, **kw) -> Dict[str, object]:
    """post_drag + a before/after capture of the window's OWN pixels. ``effective`` is None when the window
    cannot be captured, False when messages were delivered but NOTHING changed (the target ignores posted
    mouse input - XAML / WinUI canvases do), True only when pixels moved. Never reports success for a
    delivery alone."""
    before, why_b = capture_window(hwnd)
    ok, note = post_drag(hwnd, x0, y0, x1, y1, **kw)
    time.sleep(0.35)
    after, why_a = capture_window(hwnd)
    n, bbox = changed_pixels(before, after)
    effective = None if n < 0 else (n > 0)
    verdict = ("delivered but INEFFECTIVE: the window did not react to posted mouse input (no pixel changed)"
               if ok and effective is False else note)
    return {"delivered": ok, "effective": effective, "changed_pixels": n, "bbox": bbox, "note": verdict,
            "capture": f"{why_b}/{why_a}"}


def post_scroll(hwnd: int, sx: int, sy: int, clicks: int) -> Tuple[bool, str]:
    """Positive clicks scroll up, negative down (one click = 120 wheel units)."""
    if not is_alive(hwnd) or is_minimized(hwnd):
        return False, f"{UNDELIVERABLE}: window unavailable/minimized"
    target = child_at(hwnd, sx, sy)
    wparam = ((int(clicks) * 120) & 0xFFFF) << 16
    ok = _u32.PostMessageW(target, WM_MOUSEWHEEL, wparam, _lparam_xy(sx, sy))
    return bool(ok), f"postmessage-wheel->{_class_name(target)}"


# ---------------------------------------------------------------------------
# Text and keys
# ---------------------------------------------------------------------------

_EDIT_CLASSES = ("edit", "richedit", "scintilla", "tedit", "textbox")


def post_text(hwnd: int, text: str) -> Tuple[bool, str]:
    if not _IS_WINDOWS:
        return False, f"{UNDELIVERABLE}: non-windows"
    if not is_alive(hwnd):
        return False, f"{UNDELIVERABLE}: window gone"
    cls = _class_name(hwnd).lower()
    if any(c in cls for c in _EDIT_CLASSES):
        res = ctypes.c_size_t(0)
        buf = ctypes.create_unicode_buffer(text)
        ret = _u32.SendMessageTimeoutW(hwnd, EM_REPLACESEL, 1, ctypes.addressof(buf),
                                       SMTO_ABORTIFHUNG, 800, ctypes.byref(res))
        if ret:
            return True, f"em_replacesel->{_class_name(hwnd)}"
    # Generic: per-character WM_CHAR to this exact HWND (works on custom/owner-drawn editors).
    delivered = 0
    for ch in text:
        if _u32.PostMessageW(hwnd, WM_CHAR, ord(ch), 1):
            delivered += 1
    if delivered == len(text) and text:
        return True, f"postmessage-wm_char->{_class_name(hwnd)} ({delivered} chars)"
    return False, f"{UNDELIVERABLE}: could not post characters to {_class_name(hwnd)}"


def parse_combo(combo: str) -> Optional[List[int]]:
    toks = [t for t in re.split(r"[+\-]", combo or "") if t.strip()]
    vks = [token_to_vk(t) for t in toks]
    if not vks or any(v is None for v in vks):
        return None
    return [int(v) for v in vks]


def post_key_combo(hwnd: int, combo: str) -> Tuple[bool, str]:
    """Deliver a key combo (e.g. 'ctrl+shift+s') to ``hwnd`` WITHOUT synthesising physical input.

    Posted key messages do not carry modifier state, so the target thread's keyboard-state
    table is set for the duration (AttachThreadInput + SetKeyboardState), which is what
    accelerator/GetKeyState-based handlers read. This only changes our attached input
    queue's table - the physical keyboard is untouched. Frameworks that read raw input
    (some XAML/WinUI/games) ignore posted keys; the caller's postcondition detects that and
    the action is reported as not-effective rather than silently retried physically.
    """
    if not _IS_WINDOWS:
        return False, f"{UNDELIVERABLE}: non-windows"
    if not is_alive(hwnd):
        return False, f"{UNDELIVERABLE}: window gone"
    vks = parse_combo(combo)
    if vks is None:
        return False, f"{UNDELIVERABLE}: unknown key in '{combo}'"
    return post_vk_chord(hwnd, vks, label=combo)


def post_vk_chord(hwnd: int, vks: List[int], label: str = "") -> Tuple[bool, str]:
    """Post a chord of virtual-key codes (modifiers first) to ``hwnd`` - see post_key_combo."""
    if not _IS_WINDOWS or not is_alive(hwnd):
        return False, f"{UNDELIVERABLE}: window unavailable"
    combo = label or "+".join(hex(v) for v in vks)
    mods = [v for v in vks if v in _MODS]
    keys = [v for v in vks if v not in _MODS] or [mods.pop()]  # lone modifier press
    target_tid = _u32.GetWindowThreadProcessId(hwnd, None)
    my_tid = _k32.GetCurrentThreadId()
    attached = bool(target_tid and target_tid != my_tid
                    and _u32.AttachThreadInput(my_tid, target_tid, True))
    saved = (ctypes.c_ubyte * 256)()
    have_state = bool(_u32.GetKeyboardState(saved))
    try:
        if have_state:
            state = (ctypes.c_ubyte * 256)()
            ctypes.memmove(state, saved, 256)
            for m in mods:
                state[m] = 0x80
                if m == 0x11:
                    state[0xA2] = 0x80
                elif m == 0x10:
                    state[0xA0] = 0x80
                elif m == 0x12:
                    state[0xA4] = 0x80
            _u32.SetKeyboardState(state)
        sys_key = 0x12 in mods
        dn, up = (WM_SYSKEYDOWN, WM_SYSKEYUP) if sys_key else (WM_KEYDOWN, WM_KEYUP)

        def lp(vk: int, is_up: bool) -> int:
            scan = _u32.MapVirtualKeyW(vk, 0)
            v = 1 | (scan << 16)
            if vk in _EXTENDED:
                v |= 1 << 24
            if sys_key:
                v |= 1 << 29
            if is_up:
                v |= (1 << 30) | (1 << 31)
            return v

        ok = True
        for m in mods:
            ok = _u32.PostMessageW(hwnd, dn, m, lp(m, False)) and ok
        for k in keys:
            ok = _u32.PostMessageW(hwnd, dn, k, lp(k, False)) and ok
            if not mods or mods == [0x10]:  # printable char only without ctrl/alt
                if 0x20 <= k <= 0x7E and (chr(k).isalnum() or k == 0x20):
                    ch = chr(k) if 0x10 in mods else chr(k).lower()
                    _u32.PostMessageW(hwnd, WM_CHAR, ord(ch), lp(k, False))
            time.sleep(0.02)
            ok = _u32.PostMessageW(hwnd, up, k, lp(k, True)) and ok
        for m in reversed(mods):
            ok = _u32.PostMessageW(hwnd, up, m, lp(m, True)) and ok
        time.sleep(0.05)  # let the target thread drain before state is restored
    finally:
        if have_state:
            _u32.SetKeyboardState(saved)
        if attached:
            _u32.AttachThreadInput(my_tid, target_tid, False)
    return bool(ok), (f"postmessage-keys:{combo}->{_class_name(hwnd)}" if ok
                      else f"{UNDELIVERABLE}: PostMessage refused for '{combo}'")


# ---------------------------------------------------------------------------
# Capture (works for covered / partly off-screen windows; minimized reported honestly)
# ---------------------------------------------------------------------------

def capture_window(hwnd: int):
    """Return (PIL.Image | None, reason). Uses PrintWindow(PW_RENDERFULLCONTENT) so the pixels
    are the window's OWN content even when other windows cover it or it is partly off-screen
    (a screen grab would capture whatever is on top instead). Minimized windows are not
    rendered by Windows, so that case returns (None, 'window-minimized')."""
    if not (_IS_WINDOWS and is_alive(hwnd)):
        return None, "window-gone"
    if is_minimized(hwnd):
        return None, "window-minimized"
    try:
        from PIL import Image
        r = wt.RECT()
        _u32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        if w <= 0 or h <= 0 or w * h > 8000 * 5000:
            return None, "bad-window-size"
        sdc = _u32.GetDC(None)
        mdc = _g32.CreateCompatibleDC(sdc)
        bmp = _g32.CreateCompatibleBitmap(sdc, w, h)
        old = _g32.SelectObject(mdc, bmp)
        try:
            ok = _u32.PrintWindow(hwnd, mdc, 0x2)  # PW_RENDERFULLCONTENT

            class BIH(ctypes.Structure):
                _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                            ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                            ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                            ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                            ("biClrImportant", wt.DWORD)]
            bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
            buf = (ctypes.c_ubyte * (w * h * 4))()
            _g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
        finally:
            _g32.SelectObject(mdc, old)
            _g32.DeleteObject(bmp)
            _g32.DeleteDC(mdc)
            _u32.ReleaseDC(None, sdc)
        img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1).convert("RGB")
        if not ok or img.getbbox() is None or not any(img.resize((8, 8)).getdata()):
            return None, "capture-blank (window did not render into PrintWindow)"
        return img, "ok"
    except Exception as exc:  # noqa: BLE001
        return None, f"capture-error: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Physical-input guard (product law: the user's pointer/keyboard are never touched)
# ---------------------------------------------------------------------------
# Legacy code paths (older crew tools, scanners) still call the Win32/pyautogui injection APIs.
# Rather than trusting every call site, those APIs are replaced process-wide with a guard that
# REFUSES the call, records who tried (VIOLATIONS), and returns a failure value. Opt-out for
# deliberate legacy debugging only: HOJAIGA_ALLOW_PHYSICAL_INPUT=1.

VIOLATIONS: List[Dict[str, str]] = []
_GUARDED_USER32 = ("SetCursorPos", "mouse_event", "keybd_event", "SendInput")
_GUARDED_WIN32API = ("SetCursorPos", "mouse_event", "keybd_event")
_GUARDED_PYAUTOGUI = ("click", "doubleClick", "rightClick", "middleClick", "tripleClick", "moveTo",
                      "move", "moveRel", "dragTo", "drag", "dragRel", "press", "write", "typewrite",
                      "hotkey", "keyDown", "keyUp", "mouseDown", "mouseUp", "scroll", "hscroll",
                      "vscroll")
_guard_installed = False


def physical_input_blocked(what: str) -> bool:
    """True (and recorded) when a physical-input attempt must be refused."""
    if os.environ.get("HOJAIGA_ALLOW_PHYSICAL_INPUT") == "1":
        return False
    import traceback
    frames = traceback.extract_stack(limit=5)[:-1]
    where = " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno}" for f in reversed(frames))
    VIOLATIONS.append({"api": what, "where": where})
    logger.warning("[INPUT-GUARD] physical input REFUSED: %s from %s (use headless_input)", what, where)
    return True


def _make_guard(name: str, original):
    def _guarded(*a, **k):
        if physical_input_blocked(name):
            return 0
        return original(*a, **k)
    _guarded.__name__ = f"guarded_{name}"
    return _guarded


def install_physical_input_guard() -> None:
    global _guard_installed
    if _guard_installed or not _IS_WINDOWS:
        return
    _guard_installed = True
    try:
        for name in _GUARDED_USER32:
            orig = getattr(ctypes.windll.user32, name)
            setattr(ctypes.windll.user32, name, _make_guard(f"user32.{name}", orig))
    except Exception as exc:  # noqa: BLE001
        logger.debug("user32 guard partial: %s", exc)
    try:
        import win32api
        for name in _GUARDED_WIN32API:
            if hasattr(win32api, name):
                setattr(win32api, name, _make_guard(f"win32api.{name}", getattr(win32api, name)))
    except Exception:
        pass
    try:
        import sys
        pag = sys.modules.get("pyautogui")
        if pag is None:
            import pyautogui as pag  # noqa: F811
        for name in _GUARDED_PYAUTOGUI:
            if hasattr(pag, name):
                setattr(pag, name, _make_guard(f"pyautogui.{name}", getattr(pag, name)))
    except Exception:
        pass


install_physical_input_guard()


# ---------------------------------------------------------------------------
# Desktop attachment: only when actually needed
# ---------------------------------------------------------------------------

def _desktop_name(hdesk) -> str:
    try:
        buf = ctypes.create_unicode_buffer(256)
        needed = wt.DWORD(0)
        _u32.GetUserObjectInformationW.argtypes = [_H, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
        if _u32.GetUserObjectInformationW(hdesk, 2, buf, ctypes.sizeof(buf), ctypes.byref(needed)):  # UOI_NAME
            return buf.value
    except Exception:
        pass
    return ""


def on_input_desktop() -> bool:
    """True when this thread already runs on the interactive input desktop (the normal case).
    Callers must then NOT call SetProcessWindowStation/SetThreadDesktop: doing so at import time
    (organ_30, visual_cursor) measurably degraded UIA pattern access for the rest of the process
    (Invoke silently became DoDefaultAction on a Pane wrapper)."""
    if not _IS_WINDOWS:
        return True
    try:
        _u32.GetThreadDesktop.restype = _H
        _u32.OpenInputDesktop.restype = _H
        _u32.OpenInputDesktop.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        cur = _u32.GetThreadDesktop(_k32.GetCurrentThreadId())
        inp = _u32.OpenInputDesktop(0, False, 0x0001)   # DESKTOP_READOBJECTS
        if not cur or not inp:
            return False
        same = _desktop_name(cur) == _desktop_name(inp) != ""
        _u32.CloseDesktop(inp)
        return same
    except Exception:
        return False
