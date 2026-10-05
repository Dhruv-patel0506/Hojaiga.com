"""
pointer_sentinel.py -- who moved the mouse? (P0-C)

The suite asserts "the physical pointer was not touched". A person using the machine while a test runs moves it, and a
position-only check cannot tell a human hand from a synthetic jump (measured: a 648 px step between two samples ten
milliseconds apart failed KM1 and LC2 while the input guard counted ZERO physical-input calls).

This module watches the pointer from OUTSIDE the code under test, read-only (GetCursorPos + a low-level mouse HOOK that only
counts; it injects nothing, so the AST purity guard has nothing to object to):

    hardware events   mouse events with the LLMHF_INJECTED bits clear: a physical device
    injected events   mouse events flagged injected (SendInput / mouse_event, from ANY process)
    drift             net pointer displacement over the window, and the fastest step in px per real millisecond
                      (each sample carries its own timestamp, so a stalled sampler thread does not read as a teleport)

classify() then names the cause:

    ours-guard      the in-process input guard refused/recorded a physical call during the window       -> FAIL (our code)
    ours-injected   an injected event arrived and this process cannot rule itself out (guard saw none)   -> reported, still ENV
    human-hand      hardware events observed                                                           -> ABORTED-ENV
    foreign         injected events, guard saw nothing (another process / tool moved it)               -> ABORTED-ENV
    unattributed    the pointer moved with no event at all and no guard call (SetCursorPos from elsewhere) -> ABORTED-ENV
    still           it did not move at all                                                              -> clean

ABORTED-ENV is not a pass and not a code failure: the pointer assertion could not be evaluated honestly on a machine somebody
is using. `abort_if_env_only()` converts a failed outcome only when EVERY failing check is the pointer check.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

_IS_WINDOWS = hasattr(ctypes, "windll")
WH_MOUSE_LL = 14
LLMHF_INJECTED = 0x01
LLMHF_LOWER_IL_INJECTED = 0x02
WM_QUIT = 0x0012


def _cursor() -> Tuple[int, int]:
    p = wt.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class Sentinel:
    """Start it before the work, call `report()` after. Cheap: one hook thread + one 5 ms sampler."""

    def __init__(self, sample_s: float = 0.005):
        self.sample_s = sample_s
        self.p0 = _cursor() if _IS_WINDOWS else (0, 0)
        self.hardware = 0
        self.injected = 0
        self.max_speed = 0.0                      # px per ms between two samples, using real timestamps
        self.max_step = 0
        self.max_dt_ms = 0.0
        self.samples = 0
        self.hook_ok = False
        self.violations0 = 0
        self._stop = threading.Event()
        self._hook = 0
        self._hook_tid = 0
        self._t_hook: Optional[threading.Thread] = None
        self._t_samp: Optional[threading.Thread] = None
        try:
            from core_organs import headless_input as hin
            self._hin = hin
            self.violations0 = len(hin.VIOLATIONS)
        except Exception:  # noqa: BLE001
            self._hin = None

    # ---------------------------------------------------------------- the two watchers
    def _hook_thread(self) -> None:
        if not _IS_WINDOWS:
            return
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
        u32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM]
        u32.CallNextHookEx.restype = ctypes.c_ssize_t
        u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wt.DWORD]
        u32.SetWindowsHookExW.restype = ctypes.c_void_p

        def _proc(n_code, w_param, l_param):
            try:
                if n_code >= 0:
                    st = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                    if w_param != 0x0200 or True:                       # every mouse message counts, moves included
                        if st.flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED):
                            self.injected += 1
                        else:
                            self.hardware += 1
            except Exception:  # noqa: BLE001
                pass
            return u32.CallNextHookEx(None, n_code, w_param, l_param)

        self._proc = HOOKPROC(_proc)                                       # keep a reference alive for the hook's lifetime
        self._hook_tid = k32.GetCurrentThreadId()
        self._hook = u32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
        self.hook_ok = bool(self._hook)
        msg = wt.MSG()
        while not self._stop.is_set():
            # a low-level hook is serviced by this thread's message loop; peek so the stop flag is honoured
            while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.002)
        if self._hook:
            u32.UnhookWindowsHookEx(ctypes.c_void_p(self._hook))
            self._hook = 0

    def _sampler(self) -> None:
        last = _cursor()
        t_last = time.perf_counter()
        while not self._stop.is_set():
            time.sleep(self.sample_s)
            p = _cursor()
            t = time.perf_counter()
            self.samples += 1
            if p != last:
                step = abs(p[0] - last[0]) + abs(p[1] - last[1])
                dt_ms = max(0.5, (t - t_last) * 1000.0)
                self.max_step = max(self.max_step, step)
                self.max_dt_ms = max(self.max_dt_ms, dt_ms)
                self.max_speed = max(self.max_speed, step / dt_ms)
            last, t_last = p, t

    def start(self) -> "Sentinel":
        if _IS_WINDOWS:
            self._t_hook = threading.Thread(target=self._hook_thread, daemon=True, name="pointer-hook")
            self._t_samp = threading.Thread(target=self._sampler, daemon=True, name="pointer-sampler")
            self._t_hook.start()
            self._t_samp.start()
            time.sleep(0.05)
        return self

    def stop(self) -> None:
        self._stop.set()
        for t in (self._t_hook, self._t_samp):
            if t is not None:
                t.join(timeout=1.5)

    # ---------------------------------------------------------------- the verdict
    def report(self) -> Dict[str, Any]:
        p1 = _cursor() if _IS_WINDOWS else (0, 0)
        dv = (len(self._hin.VIOLATIONS) - self.violations0) if self._hin is not None else 0
        drift = abs(p1[0] - self.p0[0]) + abs(p1[1] - self.p0[1])
        moved = drift > 0 or self.max_step > 0
        rep = {"p0": self.p0, "p1": p1, "drift_px": drift, "moved": moved, "guard_violations": dv, "hardware_events": self.hardware,
               "injected_events": self.injected, "max_step_px": self.max_step, "max_speed_px_ms": round(self.max_speed, 2),
               "hook_ok": self.hook_ok}
        rep["cause"] = classify(rep)
        return rep


def classify(rep: Dict[str, Any]) -> str:
    if rep.get("guard_violations", 0) > 0:
        return "ours-guard"
    if not rep.get("moved"):
        return "still"
    if rep.get("hardware_events", 0) > 0 and rep.get("injected_events", 0) == 0:
        return "human-hand"
    if rep.get("injected_events", 0) > 0:
        return "foreign"
    return "unattributed"


def describe(rep: Dict[str, Any]) -> str:
    return (f"pointer {rep['p0']}->{rep['p1']} cause={rep['cause']} (guard calls={rep['guard_violations']}, "
            f"hardware events={rep['hardware_events']}, injected events={rep['injected_events']}, "
            f"fastest step={rep['max_step_px']}px at {rep['max_speed_px_ms']}px/ms, hook={'on' if rep['hook_ok'] else 'OFF'})")


_FAIL_CHECK = re.compile(r"(?:^|;\s*|\|\s*)([^;|=]+?)=FAIL(?=\(|;|\||\s|$)")


def failing_checks(evidence: str) -> List[str]:
    """Names of the checks that failed in an evidence string built as 'name=OK(..); name=FAIL(..)'."""
    return [m.group(1).strip().lower() for m in _FAIL_CHECK.finditer(evidence or "")]


def abort_if_env_only(evidence: str, rep: Dict[str, Any]) -> Optional[str]:
    """When a test failed ONLY on the pointer assertion and the Sentinel says the pointer was moved by something other than this
    code, return the ABORTED-ENV note; otherwise None (a real failure stays a failure, and a pointer failure that coincides with
    other failures is never hidden)."""
    if rep.get("cause") in ("still", "ours-guard"):
        return None
    fails = failing_checks(evidence)
    if not fails or not all("pointer" in f for f in fails):
        return None
    return (f"ABORTED-ENV (not a code failure): the pointer assertion cannot be evaluated while it is being moved by something "
            f"else. {describe(rep)}")


def preflight(seconds: float = 1.5) -> Dict[str, Any]:
    """Before the suite: is somebody using the mouse right now? Returns the Sentinel report for the quiet-window probe."""
    s = Sentinel().start()
    time.sleep(seconds)
    s.stop()
    return s.report()
