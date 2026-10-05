"""
si_tests_extra.py -- additional suite tests (kept out of run_system_intelligence_tests.py so the
big file stays patchable). Imported lazily by the suite; each returns a TestOutcome-compatible object
built by the suite's own dataclass (passed in as `TestOutcome`).
"""

import ctypes
import ctypes.wintypes as wt
import threading
import time
from typing import Any, Dict


def _pointer():
    p = wt.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def show_messagebox(text: str, title: str, flags: int):
    """Open a REAL Win32 message box on a worker thread. Returns (thread, result); result['code']
    is the button id the box returned (1 OK, 2 Cancel, 6 Yes, 7 No)."""
    result: Dict[str, Any] = {"code": None}

    def _run():
        mb = ctypes.WinDLL("user32")
        mb.MessageBoxW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT]
        result["code"] = mb.MessageBoxW(None, text, title, flags)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(0.6)
    return t, result


def run_pp1(TestOutcome):
    """PP1: popup policy reads REAL dialogs, answers non-destructively, escalates elevation/overwrite, headless"""
    from core_organs import si_test_support as sup
    from core_organs import popup_policy as pp
    from core_organs import headless_input as hin

    root = sup.NativeButtonWindow(title="HJ-PP1-Root").start()   # same process => its boxes count as owned
    pointer0 = _pointer()
    viol0 = len(hin.VIOLATIONS)
    rows = []
    state = {"ok": True}

    def case(name, text, title, flags, want_code, *, task_paths=(), mode="inflight", expect_human=False):
        pre = set(pp.blocking_dialogs(root.hwnd))     # stray dialogs from earlier tests are not ours
        t, res = show_messagebox(text, title, flags)
        out = pp.clear_blockers(root.hwnd, mode=mode, task_paths=task_paths, exclude=pre)
        t.join(timeout=2)
        if expect_human:
            still = pp.blocking_dialogs(root.hwnd, pre)
            good = bool(out["need_human"]) and res["code"] is None and bool(still)
            for d in still:                      # test hygiene: close the box we deliberately left open
                hin._u32.PostMessageW(d, 0x0010, 0, 0)
            t.join(timeout=2)
        else:
            good = res["code"] == want_code and not out["need_human"]
        state["ok"] = state["ok"] and good
        rows.append(f"{name}: {'OK' if good else 'FAIL'} (returned={res['code']}, human={out['need_human']}"
                    + ("" if good else f", handled={out['handled'][:2]}") + ")")

    MB_OK, MB_OKCANCEL, MB_YESNOCANCEL, MB_YESNO = 0x0, 0x1, 0x3, 0x4
    ICON_WARN, ICON_ERR = 0x30, 0x10
    own = r"D:\x\poem.txt"
    try:
        case("overwrite-not-ours -> No", "Untitled.txt already exists.\nDo you want to replace it?",
             "Confirm Save As", MB_YESNO | ICON_WARN, 7, task_paths=(own,))
        case("save-changes -> Cancel", "Do you want to save changes to Untitled?", "Notepad",
             MB_YESNOCANCEL | ICON_WARN, 2)
        case("error -> OK", "Could not open the file. An error occurred.", "Error", MB_OK | ICON_ERR, 1)
        case("UAC-like -> human, stays open", "Do you want to allow this app to make changes to your device?",
             "User Account Control", MB_OKCANCEL | ICON_WARN, None, expect_human=True)
        case("task's own target exists -> human", "poem.txt already exists.\nDo you want to replace it?",
             "Confirm Save As", MB_OKCANCEL | ICON_WARN, None, task_paths=(own,), expect_human=True)
    finally:
        root.stop()
    untouched = _pointer() == pointer0
    clean = len(hin.VIOLATIONS) == viol0
    return TestOutcome(
        passed=state["ok"] and clean,   # pointer is reported, not gated: a human may be using the mouse
        evidence="; ".join(rows) + f"; physical pointer untouched={untouched}; guard violations={len(hin.VIOLATIONS) - viol0}",
        metrics={"cases": len(rows), "pointer_untouched": untouched})
