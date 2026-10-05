"""
background_window.py — scan and operate apps WITHOUT ever showing them or taking the user's focus.

The product rule: automation must not pop windows onto the user's screen, raise them, or steal
focus. That is easy for a window that is already visible and covered (UIA reads it regardless).
It is hard for a MINIMIZED window, and that is the common case for "leave the bot working":

  * a minimized window has NO layout — every control reports bogus coordinates (-31942, ...)
  * some UI stacks (WinUI/XAML) do not even materialise their flyouts while minimized
  * PrintWindow cannot render a minimized window, so OCR/vision tiers go dark

Fix: PARK the window. Restore it to its normal size at far off-screen coordinates WITHOUT
activating it (SW_SHOWNOACTIVATE), do the work there, then put it back exactly as it was
(minimized, original normal rect, SW_SHOWMINNOACTIVE). While parked:

  * UIA sees a fully laid-out window: real sizes, real relative positions, working flyouts
  * the window, its flyouts and its dialogs are off-screen, so the user sees nothing
  * focus never moves (the foreground window is whatever the user is using)
  * PrintWindow works, so OCR / vision can read the app

Safety:
  * ref-counted per window: nested sessions (scanner -> crawler -> probe) park once
  * verified: if Windows ends up putting the window on a real monitor, it is minimized again
    immediately and the mode is reported as 'failed' (callers fall back to minimized-only)
  * crash-safe: the original placement is journalled; atexit and import-time recovery
    restore any window a dead process left parked
  * `keep_hidden()` sweeps any popup/dialog of the app that landed on a real monitor and
    moves it off-screen without activating it

Windows that are already visible are left completely alone (mode 'visible'): no raise, no move.
"""

from __future__ import annotations

import atexit
import ctypes
import ctypes.wintypes as wt
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.background_window")

_IS_WINDOWS = os.name == "nt"
_u32 = ctypes.windll.user32 if _IS_WINDOWS else None

SW_SHOWNOACTIVATE = 4
SW_SHOWMINNOACTIVE = 7
SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x4, 0x10
PARK_X = int(os.environ.get("HOJAIGA_PARK_X", "-24000"))
PARK_Y = int(os.environ.get("HOJAIGA_PARK_Y", "-24000"))
ENABLED = os.environ.get("HOJAIGA_PARK_MINIMIZED", "1") != "0"
_JOURNAL_DIR = os.environ.get("TEMP", ".")
_JOURNAL = os.path.join(_JOURNAL_DIR, f"hojaiga_parked_{os.getpid()}.json")   # one journal per process


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", wt.UINT), ("flags", wt.UINT), ("showCmd", wt.UINT),
                ("ptMinPosition", wt.POINT), ("ptMaxPosition", wt.POINT), ("rcNormalPosition", wt.RECT)]


def _placement(hwnd: int) -> WINDOWPLACEMENT:
    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(WINDOWPLACEMENT)
    _u32.GetWindowPlacement(hwnd, ctypes.byref(wp))
    return wp


def _copy(wp: WINDOWPLACEMENT) -> WINDOWPLACEMENT:
    n = WINDOWPLACEMENT()
    ctypes.memmove(ctypes.byref(n), ctypes.byref(wp), ctypes.sizeof(wp))
    return n


def _screens() -> List[Tuple[int, int, int, int]]:
    """Real monitor rectangles (virtual desktop bounds as a single box is wrong for L-shaped
    layouts, so enumerate monitors)."""
    out: List[Tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wt.RECT), ctypes.c_void_p)
    def cb(_m, _dc, rect, _d):
        r = rect.contents
        out.append((r.left, r.top, r.right, r.bottom))
        return 1
    try:
        _u32.EnumDisplayMonitors(None, None, cb, 0)
    except Exception:
        pass
    return out or [(0, 0, _u32.GetSystemMetrics(0), _u32.GetSystemMetrics(1))]


def _on_real_screen(rect: Tuple[int, int, int, int]) -> bool:
    l, t, r, b = rect
    if r <= l or b <= t:
        return False
    for sl, st, sr, sb in _screens():
        if l < sr and r > sl and t < sb and b > st:
            return True
    return False


def user_can_see(hwnd: int) -> bool:
    """Is any part of this window actually in the user's view right now? True when the window is
    visible, on a real monitor, and at least one of nine sample points inside it resolves (by
    WindowFromPoint) to this window or one of its own popups — i.e. nothing is covering that spot."""
    if not (_IS_WINDOWS and hwnd and _u32.IsWindow(hwnd)) or _u32.IsIconic(hwnd) or not _u32.IsWindowVisible(hwnd):
        return False
    l, t, r, b = _rect(hwnd)
    if not _on_real_screen((l, t, r, b)):
        return False
    pid = _pid(hwnd)
    for fx in (0.15, 0.5, 0.85):
        for fy in (0.15, 0.5, 0.85):
            x, y = int(l + (r - l) * fx), int(t + (b - t) * fy)
            if not _on_real_screen((x, y, x + 1, y + 1)):
                continue
            h = _u32.WindowFromPoint(wt.POINT(x, y))
            if not h:
                continue
            root = _u32.GetAncestor(h, 2) or h              # GA_ROOT
            if root == hwnd or (root != hwnd and _pid(root) == pid):
                return True
    return False


def is_minimized(hwnd: int) -> bool:
    return bool(_IS_WINDOWS and hwnd and _u32.IsIconic(hwnd))


def _rect(hwnd: int) -> Tuple[int, int, int, int]:
    r = wt.RECT()
    _u32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def _pid(hwnd: int) -> int:
    p = wt.DWORD()
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return int(p.value)


# ------------------------------------------------------------------ whose window is the user's?
# The focus guard must always know where to send focus back to. Relying on "whatever was foreground
# when the park began" fails exactly when it matters (the app grabbed focus while launching). A tiny
# tracker therefore remembers the last foreground window that is NOT an automation target, and
# callers can pin it explicitly with remember_user_window().
_last_user_fg = 0
_automation_pids: set = set()
_tracker_started = False


_pinned = 0


def pin_user_window(hwnd: int) -> None:
    """The user's window for the duration of one scan. While pinned, the tracker will not replace it
    (an app that grabs focus while launching must never be mistaken for the user's window)."""
    global _pinned, _last_user_fg
    if hwnd and _u32.IsWindow(hwnd):
        _pinned = hwnd
        _last_user_fg = hwnd


def unpin_user_window() -> None:
    global _pinned
    _pinned = 0


def remember_user_window(hwnd: int) -> None:
    global _last_user_fg
    if hwnd and _u32.IsWindow(hwnd) and not _u32.IsIconic(hwnd):
        _last_user_fg = hwnd


def mark_automation_pid(pid: int) -> None:
    _automation_pids.add(pid)


# Windows WE launched (launch_hidden / operate_app / prepare_app). Everything else - a window that merely
# looks like our target - belongs to the user until proven otherwise: off-screen capture of a window the user
# can currently SEE is refused, and only windows in this set are ever closed by the harness.
_ours: set = set()


def mark_ours(hwnd: int) -> None:
    if hwnd:
        _ours.add(int(hwnd))


def is_ours(hwnd: int) -> bool:
    h = int(hwnd or 0)
    if h in _ours and _IS_WINDOWS and _u32.IsWindow(h):
        return True
    _ours.discard(h)
    return False


def last_user_window() -> int:
    return _last_user_fg


def next_user_window(exclude_pid: int) -> int:
    """Topmost visible, non-minimized, titled, non-tool window that does not belong to `exclude_pid`
    (z-order top to bottom): where Windows would put focus if the automation target vanished."""
    found = 0

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        nonlocal found
        try:
            if _u32.IsWindowVisible(h) and not _u32.IsIconic(h) and _pid(h) != exclude_pid and _pid(h) != os.getpid():
                if _cls(h) in SHELL_CLASSES or _cls(h) in ("Progman", "WorkerW", "Shell_TrayWnd"):
                    return True
                ex = _u32.GetWindowLongW(h, -20)
                if ex & 0x80 or ex & 0x08000000:                 # tool window / no-activate
                    return True
                n = len(_safe_text(h))
                r = _rect(h)
                if n > 0 and (r[2] - r[0]) > 100 and (r[3] - r[1]) > 60 and _on_real_screen(r):
                    found = int(h)
                    return False
        except Exception:
            pass
        return True
    try:
        _u32.EnumWindows(cb, 0)
    except Exception:
        pass
    return found


def _track_user_focus() -> None:
    global _last_user_fg
    own = os.getpid()
    while True:
        try:
            fg = _u32.GetForegroundWindow()
            if _pinned and _u32.IsWindow(_pinned):
                pass                                              # pinned for this scan: keep it
            elif fg and not _u32.IsIconic(fg) and _u32.IsWindowVisible(fg):
                pid = _pid(fg)
                if pid != own and pid not in _automation_pids:
                    _last_user_fg = fg
        except Exception:
            pass
        time.sleep(0.05)


def _ensure_tracker() -> None:
    global _tracker_started
    if not _tracker_started and _IS_WINDOWS:
        _tracker_started = True
        threading.Thread(target=_track_user_focus, daemon=True, name="user-focus-tracker").start()


# A process is NOT an app: explorer.exe also owns the taskbar and the desktop, and every UWP app shares
# ApplicationFrameHost. Treating "same process" as "ours" made the guard shove the user's TASKBAR off the
# screen thousands of times during a File Explorer scan. A window belongs to the target only if it is OWNED
# by it (or is a recognised popup/dialog class of the same process) and is never a shell window.
SHELL_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "TaskListThumbnailWnd",
                 "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland", "Windows.UI.Core.CoreWindow",
                 "XamlExplorerHostIslandWindow", "TaskListOverlayWnd", "ForegroundStaging",
                 "ApplicationFrameInputSinkWindow", "ApplicationFrameTitleBarWindow", "MSTaskSwWClass", "ReBarWindow32"}
POPUP_CLASSES = {"Microsoft.UI.Content.PopupWindowSiteBridge", "Xaml_WindowedPopupClass", "Qt5QWindowToolSaveBits",
                 "Qt6QWindowToolSaveBits", "QTipLabel"}


INPUT_SITE_CLASSES = {"Windows.UI.Input.InputSite.WindowClass", "InputSiteWindowClass"}


def _tid(h: int) -> int:
    return int(_u32.GetWindowThreadProcessId(h, None))


def holds_app_focus(fg: int, target: int, pid: int = 0) -> bool:
    """For FOCUS decisions only: is the foreground window the target, one of its popups, or its own XAML
    input-site helper (same UI thread)? Never a shell window; never another main window of the app."""
    if is_target_popup(fg, target, pid):
        return True
    return _cls(fg) in INPUT_SITE_CLASSES and _pid(fg) == (pid or _pid(target)) and _tid(fg) == _tid(target)


def _safe_text(h: int) -> str:
    """Window title via a bounded SendMessageTimeout (GetWindowText can deadlock against a same-process window whose
    thread never pumps messages)."""
    buf = ctypes.create_unicode_buffer(300)
    res = ctypes.c_size_t(0)
    try:
        ok = ctypes.windll.user32.SendMessageTimeoutW(h, 0x000D, 300, ctypes.addressof(buf), 0x0002, 150, ctypes.byref(res))
    except Exception:
        return ""
    return buf.value if ok else ""


def _cls(h: int) -> str:
    c = ctypes.create_unicode_buffer(128)
    _u32.GetClassNameW(h, c, 128)
    return c.value


def _owner_chain_has(h: int, target: int) -> bool:
    cur, n = h, 0
    while cur and n < 6:
        if cur == target:
            return True
        cur = _u32.GetWindow(cur, 4)                     # GW_OWNER
        n += 1
    return False


def is_target_popup(h: int, target: int, pid: int = 0) -> bool:
    """True only for a popup / flyout / dialog that belongs to `target` (never a shell or desktop window,
    never another top-level window of the same app)."""
    if h == target or not _u32.IsWindow(h):
        return False
    cls = _cls(h)
    if cls in SHELL_CLASSES:
        return False
    if _owner_chain_has(h, target):
        return True
    return (pid or _pid(target)) == _pid(h) and cls in POPUP_CLASSES and cls != _cls(target)


def target_popups(target: int, visible_only: bool = True) -> List[int]:
    """Popup/dialog windows of `target` by OWNERSHIP, not by process."""
    out: List[int] = []
    pid = _pid(target)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        try:
            if (not visible_only or _u32.IsWindowVisible(h)) and _pid(h) == pid and is_target_popup(h, target, pid):
                out.append(int(h))
        except Exception:
            pass
        return True
    try:
        _u32.EnumWindows(cb, 0)
    except Exception:
        pass
    return out


class _PopupGuard(threading.Thread):
    """While a window is parked, its flyouts/dialogs still try to appear ON a monitor (XAML and the
    common dialogs clamp popups onto the screen even when their owner is far off-screen). Measured:
    `Expand()` blocks ~0.5 s and the popup is on screen ~23 ms after the call starts, so a sweep
    between calls leaves it visible for ~0.7 s. This thread sweeps every few ms for the whole
    session and moves any such window off every monitor (SWP_NOACTIVATE: no focus, no raise).
    Moving (not hiding) keeps the popup's UIA items fully readable — hiding it loses half of them."""

    def __init__(self, hwnd: int):
        super().__init__(daemon=True, name=f"popup-guard-{hwnd}")
        self.hwnd = hwnd
        self.pid = _pid(hwnd)
        self._halt = threading.Event()
        self.moved = 0
        self.hook_hits = 0
        self.refocused = 0
        _ensure_tracker()
        mark_automation_pid(self.pid)
        try:                                       # the guard shares an interpreter with a Python-heavy scanner:
            import sys as _sys                     # let it be scheduled within ~0.5 ms instead of the 5 ms default
            _sys.setswitchinterval(0.0005)
        except Exception:
            pass
        fg = _u32.GetForegroundWindow()
        self.user_fg = fg if (fg and _pid(fg) != self.pid) else _last_user_fg
        if self.user_fg and _pid(self.user_fg) == self.pid:
            self.user_fg = 0
        c = ctypes.create_unicode_buffer(128)
        _u32.GetClassNameW(hwnd, c, 128)
        self.main_cls = c.value

    def run(self) -> None:
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(h, _):
            try:
                if h != self.hwnd and _u32.IsWindowVisible(h) and _pid(h) == self.pid and not _u32.IsIconic(h) \
                        and is_target_popup(h, self.hwnd, self.pid):
                    if _on_real_screen(_rect(h)):
                        _u32.SetWindowPos(h, 0, PARK_X, PARK_Y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                        self.moved += 1
            except Exception:
                pass
            return True
        # EVENT PATH: a WinEvent hook (EVENT_OBJECT_CREATE..SHOW, filtered to this process) calls us within a
        # millisecond or two of ANY window appearing, so a popup is moved before it is ever composited
        # (polling can only react after its next sweep). The callback runs in THIS thread via the message
        # pump below. Polling stays as the backup for anything the hook misses.
        user32 = _u32
        WINEVENTPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, wt.DWORD, wt.HWND, wt.LONG, wt.LONG, wt.DWORD, wt.DWORD)

        def _on_event(hook, event, h, id_object, id_child, thread, ms):
            try:
                if id_object == 0 and h and h != self.hwnd and is_target_popup(h, self.hwnd, self.pid):
                    if _on_real_screen(_rect(h)):
                        _u32.SetWindowPos(h, 0, PARK_X, PARK_Y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                        self.moved += 1
                        self.hook_hits += 1
            except Exception:
                pass
        self._proc = WINEVENTPROC(_on_event)                                 # keep a reference alive
        self._hook = 0
        try:
            self._hook = user32.SetWinEventHook(0x8000, 0x8002, None, self._proc, self.pid, 0, 0x0000)   # CREATE..SHOW, out-of-context
        except Exception:
            self._hook = 0
        msg = wt.MSG()
        # FAST PATH: a flyout/dialog of this app is created on the app's own UI thread, so enumerating just
        # that thread's windows (a handful) is ~100x cheaper than every top-level window on the desktop.
        # The full-desktop sweep stays as a slower fallback for popups hosted on other threads.
        tid = _u32.GetWindowThreadProcessId(self.hwnd, None)
        n = 0
        while not self._halt.is_set():
            try:
                _u32.EnumThreadWindows(tid, cb, 0)
                if n % 12 == 0:
                    _u32.EnumWindows(cb, 0)
                self._hold_focus()
            except Exception:
                pass
            n += 1
            # pump this thread's messages so the WinEvent hook callbacks are delivered immediately
            try:
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception:
                pass
            self._halt.wait(0.001)
        try:
            if self._hook:
                user32.UnhookWinEvent(self._hook)
        except Exception:
            pass

    def _hold_focus(self) -> None:
        """UIA calls into a parked app (Expand/Invoke) make WinUI take the foreground — measured:
        the app's window and its input-site window become foreground and may never give it back.
        Remember the last window that belongs to someone else (the user's) and put focus straight
        back the moment the target's process takes it."""
        fg = _u32.GetForegroundWindow()
        if not fg:
            return
        c = ctypes.create_unicode_buffer(128)
        _u32.GetClassNameW(fg, c, 128)
        # ours = the target window itself, or a popup/dialog/helper of its process. ANOTHER main window
        # of the same app (same class) is the user's own work and is never fought over.
        ours = fg == self.hwnd or holds_app_focus(fg, self.hwnd, self.pid)
        if ours:
            tgt = self.user_fg or _last_user_fg
            if not (tgt and _u32.IsWindow(tgt) and not _u32.IsIconic(tgt) and _pid(tgt) != self.pid):
                tgt = next_user_window(self.pid)                     # remembered window was missing or the app's own
                if tgt:
                    self.user_fg = tgt
            if tgt and _u32.IsWindow(tgt) and not _u32.IsIconic(tgt) and _pid(tgt) != self.pid:
                _u32.SwitchToThisWindow(tgt, True)
                self.refocused += 1
        else:
            self.user_fg = fg

    def halt(self) -> None:
        self._halt.set()


class _Parked:
    def __init__(self, hwnd: int, orig: WINDOWPLACEMENT, rect: Tuple[int, int, int, int], kind: str = "minimized",
                 orig_rect: Tuple[int, int, int, int] = (0, 0, 0, 0)):
        self.hwnd, self.orig, self.rect, self.depth, self.ts = hwnd, orig, rect, 1, time.time()
        self.kind = kind                          # 'minimized' (restore -> re-minimize) | 'covered' (move back)
        self.orig_rect = orig_rect
        self.guard: Optional[_PopupGuard] = None


_lock = threading.RLock()
_parked: Dict[int, _Parked] = {}


# ------------------------------------------------------------------ journal (crash safety)
def _journal_write() -> None:
    try:
        if not _parked:
            if os.path.exists(_JOURNAL):
                os.remove(_JOURNAL)
            return
        data = {str(h): {"left": p.orig.rcNormalPosition.left, "top": p.orig.rcNormalPosition.top,
                         "right": p.orig.rcNormalPosition.right, "bottom": p.orig.rcNormalPosition.bottom,
                         "pid": _pid(h)} for h, p in _parked.items()}
        with open(_JOURNAL, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = wt.DWORD()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259                              # STILL_ACTIVE
    except Exception:
        return True                                                        # unknown => assume alive, don't touch


def recover_parked() -> int:
    """Restore windows a DEAD process left parked off-screen: minimize them again at their original
    normal rect. Journals of processes that are still alive are never touched."""
    n = 0
    try:
        names = [f for f in os.listdir(_JOURNAL_DIR) if f.startswith("hojaiga_parked_") and f.endswith(".json")]
    except Exception:
        return 0
    for fn in names:
        try:
            owner = int(fn[len("hojaiga_parked_"):-len(".json")])
        except ValueError:
            continue
        if owner == os.getpid() or _pid_alive(owner):
            continue
        path = os.path.join(_JOURNAL_DIR, fn)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {}
        for h, info in data.items():
            hwnd = int(h)
            try:
                if not _u32.IsWindow(hwnd):
                    continue
                rc = _rect(hwnd)
                if rc[0] <= PARK_X + 100 and rc[1] <= PARK_Y + 100 and not is_minimized(hwnd):
                    wp = _placement(hwnd)
                    wp.rcNormalPosition = wt.RECT(info["left"], info["top"], info["right"], info["bottom"])
                    wp.showCmd = SW_SHOWMINNOACTIVE
                    _u32.SetWindowPlacement(hwnd, ctypes.byref(wp))
                    n += 1
            except Exception:
                continue
        try:
            os.remove(path)
        except Exception:
            pass
    return n


# ------------------------------------------------------------------ park / unpark
def enter(hwnd: int) -> Dict[str, Any]:
    """Make `hwnd` scannable without showing it. Returns a state dict:
         mode: 'visible'  already visible, left untouched
               'parked'   minimized window restored off-screen, not activated
               'failed'   could not park (window left minimized; coordinates will be unreliable)
               'disabled' parking switched off by HOJAIGA_PARK_MINIMIZED=0"""
    if not (_IS_WINDOWS and hwnd and _u32.IsWindow(hwnd)):
        return {"mode": "failed", "why": "no-window"}
    with _lock:
        if hwnd in _parked:
            _parked[hwnd].depth += 1
            return {"mode": "parked", "rect": _parked[hwnd].rect, "nested": True}
        if not is_minimized(hwnd):
            if not ENABLED or user_can_see(hwnd):
                return {"mode": "visible", "user_can_see": user_can_see(hwnd)}
            # visible but fully covered: nobody is looking at it, yet its flyouts would pop up on top of
            # whatever the user IS looking at. Move it off-screen (z-order untouched) and guard focus.
            orig_rect = _rect(hwnd)
            guard = _PopupGuard(hwnd)
            guard.start()
            _u32.SetWindowPos(hwnd, 0, PARK_X, PARK_Y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            time.sleep(0.1)
            rect = _rect(hwnd)
            if _on_real_screen(rect):
                guard.halt()
                return {"mode": "visible", "why": "could-not-move-covered-window"}
            p = _Parked(hwnd, _placement(hwnd), rect, kind="covered", orig_rect=orig_rect)
            p.guard = guard
            _parked[hwnd] = p
            _journal_write()
            return {"mode": "parked", "rect": rect, "kind": "covered"}
        if not ENABLED:
            return {"mode": "disabled"}
        fg0 = _u32.GetForegroundWindow()
        orig = _placement(hwnd)
        rc = orig.rcNormalPosition
        w, h = rc.right - rc.left, rc.bottom - rc.top
        if w < 640 or h < 420:
            # A parked window is laid out at ITS OWN size; a small remembered one (Notepad persisted 415x253) collapses toolbars
            # into menus and halves what a scan can see. Only the PARKED size changes: exit() puts the original placement back.
            w, h = 1100, 760
        # Measured on this host, each variant on its own fresh minimized window:
        #   * SetWindowPos on a minimized/hidden window does NOT move its restore rectangle, so the
        #     show lands at the original position, fully visible (rejected)
        #   * a FULLY off-screen SetWindowPlacement is clamped back onto a monitor (rejected)
        #   * placement with only a 1x1 px corner on a monitor is honoured, and one SetWindowPos then
        #     moves the window fully off-screen: at most 1 px visible for a few ms, window never seen
        guard = _PopupGuard(hwnd)                  # running BEFORE the transition: focus + popups held
        guard.start()
        new = _copy(orig)
        new.rcNormalPosition = wt.RECT(-w + 1, -h + 1, 1, 1)
        new.showCmd = SW_SHOWNOACTIVATE
        _u32.SetWindowPlacement(hwnd, ctypes.byref(new))
        # A packaged / UWP frame leaves the minimized state ASYNCHRONOUSLY (measured: its rect still read
        # (-32000,-32000) and IsIconic stayed true past the old fixed 150 ms, so it was declared unparkable
        # about one run in three). A SetWindowPos on a still-iconic window moves nothing, so wait - bounded -
        # for the restore to land, then move it off every monitor.
        end = time.time() + 1.5
        while time.time() < end and is_minimized(hwnd):
            time.sleep(0.03)
        _u32.SetWindowPos(hwnd, 0, PARK_X, PARK_Y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        time.sleep(0.15)
        rect = _rect(hwnd)
        if is_minimized(hwnd) or _on_real_screen(rect):
            # Windows put it somewhere visible (or refused): undo at once and report honestly
            _u32.SetWindowPlacement(hwnd, ctypes.byref(_restore_cmd(orig)))
            guard.halt()
            return {"mode": "failed", "why": "window-not-parkable", "rect": rect}
        p = _Parked(hwnd, orig, rect)
        p.guard = guard
        _parked[hwnd] = p
        _journal_write()
        stole = _u32.GetForegroundWindow() == hwnd and fg0 != hwnd
        if stole and fg0:
            try:
                _u32.SetForegroundWindow(fg0)           # give focus straight back to what the user was using
            except Exception:
                pass
        return {"mode": "parked", "rect": rect, "stole_focus": bool(stole)}


def _restore_cmd(orig: WINDOWPLACEMENT) -> WINDOWPLACEMENT:
    wp = _copy(orig)
    wp.showCmd = SW_SHOWMINNOACTIVE                     # minimize WITHOUT activating
    return wp


def exit(hwnd: int) -> bool:                            # noqa: A001 - mirrors enter()
    """Undo `enter`. The window returns to minimized at its original normal rect."""
    with _lock:
        p = _parked.get(hwnd)
        if p is None:
            return True
        p.depth -= 1
        if p.depth > 0:
            return True
        _parked.pop(hwnd, None)
        _journal_write()
    if p.kind == "covered":                              # put it back exactly where it was; nothing was minimized
        try:
            if _u32.IsWindow(hwnd):
                l, t = p.orig_rect[0], p.orig_rect[1]
                _u32.SetWindowPos(hwnd, 0, l, t, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            if p.guard is not None:
                time.sleep(0.05)
                p.guard.halt()
                p.guard.join(timeout=1.0)
            return True
        except Exception:
            return False
    try:
        if _u32.IsWindow(hwnd):
            # order matters (measured): SetWindowPlacement with the ORIGINAL rect while the window is
            # still restored flashes the whole window at its old position. So minimize IN PLACE
            # (still off-screen), then write the original rect into the already-minimized window,
            # and only then stop the guard (which keeps focus/popups in check during the transition).
            _u32.ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
            time.sleep(0.05)
            _u32.SetWindowPlacement(hwnd, ctypes.byref(_restore_cmd(p.orig)))
            # verify: some apps (Win11 Notepad) restore themselves right after being minimized. A scan
            # must never leave the user's screen with a window it parked, so re-minimize until it sticks.
            end = time.time() + 2.5
            stuck = 0
            while time.time() < end and stuck < 5:
                time.sleep(0.1)
                if _u32.IsIconic(hwnd):
                    stuck += 1
                else:
                    stuck = 0
                    _u32.ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
        if p.guard is not None:
            time.sleep(0.05)
            p.guard.halt()
            p.guard.join(timeout=1.0)
        return True
    except Exception:
        return False


def stabilize_minimized(hwnd: int, fg_before: int = 0, seconds: float = 6.0) -> str:
    """Apps run their own startup: session restore re-opens tabs, un-minimizes the window and
    activates it AFTER the launcher's minimize. Keep the window minimized until it has stayed that
    way for 1.5 s and hand focus straight back to what the user was using. Returns a note."""
    pid = _pid(hwnd)
    mark_automation_pid(pid)             # from now on this process's windows are never "the user's window"
    notes: List[str] = []
    end, quiet_since = time.time() + seconds, time.time()
    while time.time() < end:
        if not _u32.IsIconic(hwnd):
            _u32.ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
            quiet_since = time.time()
            if "un-minimized" not in " ".join(notes):
                notes.append("app un-minimized itself during startup (re-minimized)")
        fg = _u32.GetForegroundWindow()
        if fg and _pid(fg) == pid and fg_before and fg_before != fg:
            try:
                _u32.SwitchToThisWindow(fg_before, True)
            except Exception:
                pass
            quiet_since = time.time()
            if "took focus" not in " ".join(notes):
                notes.append("app took focus at startup (returned)")
        if time.time() - quiet_since >= 1.0:
            break
        time.sleep(0.1)
    return "; ".join(notes)


def sliver(hwnd: int) -> bool:
    """UWP/WinUI apps stop laying out content that is entirely off every monitor (their controls report
    empty rectangles). Nudge a PARKED window so a single 1x1 px corner overlaps the screen: the app
    treats it as visible and lays out; no person can see one pixel. Returns True if applied."""
    with _lock:
        p = _parked.get(hwnd)
        if p is None:
            return False
        l, t, r, b = _rect(hwnd)
        w, h = r - l, b - t
        _u32.SetWindowPos(hwnd, 0, -w + 1, -h + 1, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        p.rect = _rect(hwnd)
        return True


def parked_rects() -> List[Tuple[int, int, int, int]]:
    with _lock:
        return [p.rect for p in _parked.values()]


def is_parked(hwnd: int) -> bool:
    with _lock:
        return hwnd in _parked


def point_in_parked(x: int, y: int) -> bool:
    return any(l <= x < r and t <= y < b for l, t, r, b in parked_rects())


def keep_hidden(hwnd: int) -> int:
    """Sweep this app's other windows (flyouts, dialogs, tooltips): any that landed on a real
    monitor is moved off-screen without activation. Cheap (one EnumWindows). Returns #moved."""
    if not (_IS_WINDOWS and is_parked(hwnd)):
        return 0
    pid, moved = _pid(hwnd), 0

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        nonlocal moved
        try:
            if h != hwnd and _pid(h) == pid and _u32.IsWindowVisible(h) and not _u32.IsIconic(h) \
                    and is_target_popup(h, hwnd, pid):
                rc = _rect(h)
                if _on_real_screen(rc):
                    _u32.SetWindowPos(h, 0, PARK_X, PARK_Y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                    moved += 1
        except Exception:
            pass
        return True
    _u32.EnumWindows(cb, 0)
    return moved


class BackgroundSession:
    """`with BackgroundSession(hwnd) as bg:` — scannable-but-invisible for the duration."""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.state: Dict[str, Any] = {}

    def __enter__(self):
        self.state = enter(self.hwnd)
        return self

    def __exit__(self, *exc):
        if self.state.get("mode") == "parked":
            exit(self.hwnd)
        return False

    @property
    def mode(self) -> str:
        return self.state.get("mode", "")


def _atexit() -> None:
    with _lock:
        hs = list(_parked.keys())
    for h in hs:
        with _lock:
            if h in _parked:
                _parked[h].depth = 1
        exit(h)


if _IS_WINDOWS:
    _ensure_tracker()
    atexit.register(_atexit)
    try:
        recover_parked()
    except Exception:
        pass
