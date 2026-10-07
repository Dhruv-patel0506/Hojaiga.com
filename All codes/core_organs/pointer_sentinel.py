"""
pointer_sentinel.py -- who moved the mouse? (P0-C)

The suite asserts "the physical pointer was not touched". A person using the machine while a test runs moves it, and a
position-only check cannot tell a human hand from a synthetic jump (measured: a 648 px step between two samples ten
milliseconds apart failed KM1 and LC2 while the input guard counted ZERO physical-input calls).

This module watches the pointer AND the keyboard from OUTSIDE the code under test, read-only (GetCursorPos + low-level
mouse/keyboard HOOKS that only count; they inject nothing, so the AST purity guard has nothing to object to):

    hardware events   mouse events with the LLMHF_INJECTED bits clear: a physical device
    injected events   mouse events flagged injected (SendInput / mouse_event, from ANY process)
    hardware keys     the same two counts for the keyboard: a person can steal a run with the keyboard alone
    drift             net pointer displacement over the window, and the fastest step in px per real millisecond
                      (each sample carries its own timestamp, so a stalled sampler thread does not read as a teleport)

classify() then names the cause:

    ours-guard      the in-process input guard refused/recorded a physical call during the window       -> FAIL (our code)
    ours-injected   an injected event arrived and this process cannot rule itself out (guard saw none)   -> reported, still ENV
    human-hand      hardware events observed                                                           -> ABORTED-ENV
    foreign         injected events, guard saw nothing (another process / tool moved it)               -> ABORTED-ENV
    unattributed    the pointer moved with no event at all and no guard call (SetCursorPos from elsewhere) -> ABORTED-ENV
    still           it did not move at all                                                              -> clean

ABORTED-ENV is not a pass and not a code failure: the assertion could not be evaluated honestly on a machine somebody
is using. `abort_if_env_only()` converts a failed outcome when EVERY failing check is the pointer check (low floor:
ENV_HW_EVENTS_MIN), or when a hand is demonstrably working in the session (high floor: ENV_CONTAMINATION_MIN events /
ENV_CONTAMINATION_KEYS keystrokes) so that no assertion, goal checks included, is measurable.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

_IS_WINDOWS = hasattr(ctypes, "windll")
WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
# Win32 defines LLMHF_INJECTED as 0x00000010 and LLMHF_LOWER_IL_INJECTED as 0x00000002 (MSLLHOOKSTRUCT.flags).
# This module used 0x01 for the first one. 0x01 is not a flag in that struct at all, so an INJECTED event failed the
# test, fell through to the physical counter, and our own automation's pointer moves were booked as a human hand:
# measured 2026-10-06, PIX1 aborted with "451 physical input events, 0 synthetic" while an independent read-only
# hook on the untouched machine saw 0 events in 12 s and the cursor and desktop were both frozen; PAR1's mover
# covered 145 px in 6 ms (25.46 px/ms), which a hand does not do. The wrong bit also made `injected` stick at 0,
# which is what made every one of those aborts look like the user was on the machine.
LLMHF_INJECTED = 0x00000010
LLMHF_LOWER_IL_INJECTED = 0x00000002
WM_QUIT = 0x0012


def event_is_injected(flags: int) -> bool:
    """Does a low-level hook `flags` field mark this event as synthetic? The hook's counting rule, extracted so a
    test can assert the bit values against the SDK instead of only the classification built on top of them."""
    return bool(flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED))

# How much physical input counts as "somebody is using this machine" rather than one stray event. A person moving a
# mouse generates hundreds of events per second (measured: 831 during one spreadsheet run); a single sneeze on the
# desk is not enough to excuse a failure, so the floor is a number, not a feeling.
ENV_HW_EVENTS_MIN = int(os.environ.get("HOJAIGA_ENV_HW_EVENTS_MIN", "8"))

# A SECOND, much higher floor. The first one only excuses the assertion about the pointer. Stopping a whole run from
# being graded is different: a failing GOAL check is evidence about the code, and at 8 events a brush of the mouse
# would hide it (measured 2026-10-06: PTR1's own case - a real failure next to a pointer failure with 37 events -
# was being reported as ENV-BLOCKED). Past this floor a hand is demonstrably working IN the session (hundreds of
# moves plus keystrokes, i.e. it can click into the window under test and type there), so nothing the test asserts
# is measurable and the run is reported as ABORTED-ENV with the checks it could not settle.
ENV_CONTAMINATION_MIN = int(os.environ.get("HOJAIGA_ENV_CONTAMINATION_MIN", "200"))
ENV_CONTAMINATION_KEYS = int(os.environ.get("HOJAIGA_ENV_CONTAMINATION_KEYS", "20"))


def _cursor() -> Tuple[int, int]:
    p = wt.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class Sentinel:
    """Start it before the work, call `report()` after. Cheap: one hook thread + one 5 ms sampler."""

    def __init__(self, sample_s: float = 0.005):
        self.sample_s = sample_s
        self.p0 = _cursor() if _IS_WINDOWS else (0, 0)
        self.hardware = 0
        self.injected = 0
        self.hardware_keys = 0
        self.injected_keys = 0
        self.max_speed = 0.0                      # px per ms between two samples, using real timestamps
        self.max_step = 0
        self.max_dt_ms = 0.0
        self.samples = 0
        self.hook_ok = False
        self.violations0 = 0
        self._stop = threading.Event()
        self._hook = 0
        self._hook_tid = 0
        self._procs: List[Any] = []                # the hook callbacks, alive for the process lifetime
        self._t_hook: Optional[threading.Thread] = None
        self._t_keys: Optional[threading.Thread] = None
        self._t_samp: Optional[threading.Thread] = None
        try:
            from core_organs import headless_input as hin
            self._hin = hin
            self.violations0 = len(hin.VIOLATIONS)
        except Exception:  # noqa: BLE001
            self._hin = None

    # ---------------------------------------------------------------- the two watchers
    def _hook_thread(self, kind: str = "mouse") -> None:
        """One read-only low-level hook per device, each serviced by its own message loop. `kind` picks the struct
        and the counters; nothing here injects input, so the purity guard has nothing to object to."""
        if not _IS_WINDOWS:
            return
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)
        u32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM]
        u32.CallNextHookEx.restype = ctypes.c_ssize_t
        u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wt.DWORD]
        u32.SetWindowsHookExW.restype = ctypes.c_void_p
        hook_id, struct_cls = (WH_KEYBOARD_LL, _KBDLLHOOKSTRUCT) if kind == "keyboard" else (WH_MOUSE_LL, _MSLLHOOKSTRUCT)

        def _proc(n_code, w_param, l_param):
            try:
                if n_code >= 0:
                    st = ctypes.cast(l_param, ctypes.POINTER(struct_cls)).contents
                    # every event of the device counts, moves included; the injected bits say physical or synthetic
                    if event_is_injected(st.flags):
                        if kind == "keyboard":
                            self.injected_keys += 1
                        else:
                            self.injected += 1
                    elif kind == "keyboard":
                        self.hardware_keys += 1
                    else:
                        self.hardware += 1
            except Exception:  # noqa: BLE001
                pass
            return u32.CallNextHookEx(None, n_code, w_param, l_param)

        proc_ref = HOOKPROC(_proc)                                      # keep a reference alive for the hook's lifetime
        self._procs.append(proc_ref)
        hook = u32.SetWindowsHookExW(hook_id, proc_ref, None, 0)
        if kind == "mouse":
            self.hook_ok = bool(hook)
        msg = wt.MSG()
        while not self._stop.is_set():
            # a low-level hook is serviced by this thread's message loop; peek so the stop flag is honoured
            while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.002)
        if hook:
            u32.UnhookWindowsHookEx(ctypes.c_void_p(hook))

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
            self._t_hook = threading.Thread(target=self._hook_thread, args=("mouse",), daemon=True, name="pointer-hook")
            self._t_keys = threading.Thread(target=self._hook_thread, args=("keyboard",), daemon=True, name="key-hook")
            self._t_samp = threading.Thread(target=self._sampler, daemon=True, name="pointer-sampler")
            self._t_hook.start()
            self._t_keys.start()
            self._t_samp.start()
            time.sleep(0.05)
        return self

    def stop(self) -> None:
        self._stop.set()
        for t in (self._t_hook, self._t_keys, self._t_samp):
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
               "hardware_keys": self.hardware_keys, "injected_keys": self.injected_keys,
               "hook_ok": self.hook_ok}
        rep["cause"] = classify(rep)
        return rep


def classify(rep: Dict[str, Any]) -> str:
    if rep.get("guard_violations", 0) > 0:
        return "ours-guard"
    # A person on the KEYBOARD steals focus and input without ever touching the mouse: the pointer can be perfectly
    # still while the run is being wrecked, so physical keys count as a human hand too.
    if int(rep.get("hardware_events", 0) or 0) + int(rep.get("hardware_keys", 0) or 0) > 0 \
            and rep.get("injected_events", 0) == 0:
        return "human-hand"
    if not rep.get("moved"):
        return "still"
    if rep.get("injected_events", 0) > 0:
        return "foreign"
    return "unattributed"


def describe(rep: Dict[str, Any]) -> str:
    return (f"pointer {rep['p0']}->{rep['p1']} cause={rep['cause']} (guard calls={rep['guard_violations']}, "
            f"hardware events={rep['hardware_events']}, injected events={rep['injected_events']}, "
            f"hardware keys={rep.get('hardware_keys', 0)}, "
            f"fastest step={rep['max_step_px']}px at {rep['max_speed_px_ms']}px/ms, hook={'on' if rep['hook_ok'] else 'OFF'})")


_FAIL_CHECK = re.compile(r"(?:^|;\s*|\|\s*)([^;|=]+?)=FAIL(?=\(|;|\||\s|$)")

# The assertion this module can excuse, under whichever name a test spells it.
_POINTER_CHECK_WORDS = ("pointer", "cursor", "mouse")


def failing_checks(evidence: str) -> List[str]:
    """Names of the checks that failed in an evidence string built as 'name=OK(..); name=FAIL(..)'."""
    return [m.group(1).strip().lower() for m in _FAIL_CHECK.finditer(evidence or "")]


def abort_if_env_only(evidence: str, rep: Dict[str, Any]) -> Optional[str]:
    """When a test failed ONLY on the pointer assertion and the Sentinel says the pointer was moved by something other than this
    code, return the ABORTED-ENV note; otherwise None (a real failure stays a failure, and a pointer failure that coincides with
    other failures is never hidden).

    The second rule is the wider truth, measured on 2026-10-06: a person sat down at the machine during a spreadsheet run
    (831 physical events, 0 synthetic). It did not only move the pointer - it clicked into the window the agent was driving
    and typed in its cell, so the run failed on its GOAL and on its content check, and grading that as a code defect blamed
    the code for a hand. Past the floor of physical events the outcome is simply not measurable, and it is reported as
    ABORTED-ENV with the count and the checks it could not settle - never as a pass."""
    if rep.get("cause") in ("still", "ours-guard"):
        return None
    fails = failing_checks(evidence)
    if fails and all(any(w in f for w in _POINTER_CHECK_WORDS) for f in fails):
        return (f"ABORTED-ENV (not a code failure): the pointer assertion cannot be evaluated while it is being moved by something "
                f"else. {describe(rep)}")
    physical = int(rep.get("hardware_events", 0) or 0)
    keys = int(rep.get("hardware_keys", 0) or 0)
    if physical >= ENV_CONTAMINATION_MIN or keys >= ENV_CONTAMINATION_KEYS:
        return (f"ABORTED-ENV (not a code failure): somebody was using this machine while the test ran ({physical + keys} physical "
                f"input events, {rep.get('injected_events', 0)} synthetic) -> its outcome is not measurable. "
                f"Unsettled checks: {', '.join(fails[:6]) or 'the run itself'}. {describe(rep)}")
    return None


def preflight(seconds: float = 1.5) -> Dict[str, Any]:
    """Before the suite: is somebody using the mouse right now? Returns the Sentinel report for the quiet-window probe."""
    s = Sentinel().start()
    time.sleep(seconds)
    s.stop()
    return s.report()
