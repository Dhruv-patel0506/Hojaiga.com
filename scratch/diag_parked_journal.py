"""Diagnose parked-window journals WITHOUT restoring anything.

recover_parked() calls SetWindowPlacement, which sends messages to the window's owning
thread and blocks forever on a thread that no longer pumps. This probe answers: which
journal is pending, does its window still exist, who owns it now, and does it answer a
SendMessageTimeout(WM_NULL) - the same responsiveness test Win32 itself uses for 'hung'.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

u = ctypes.windll.user32
k = ctypes.windll.kernel32

WM_NULL = 0x0000
SMTO_ABORTIFHUNG = 0x0002
SMTO_BLOCK = 0x0001

# background_window writes one journal per process into %TEMP% - match that, not a guess.
_JOURNAL_DIR = os.environ.get("HOJAIGA_PARK_JOURNAL_DIR", os.environ.get("TEMP", "."))


def _resp(hwnd: int, ms: int = 500):
    res = wt.DWORD()
    ok = u.SendMessageTimeoutW(wt.HWND(hwnd), WM_NULL, 0, 0,
                               SMTO_ABORTIFHUNG | SMTO_BLOCK, ms, ctypes.byref(res))
    return bool(ok), res.value


def _pid(hwnd: int) -> int:
    pid = wt.DWORD()
    u.GetWindowThreadProcessId(wt.HWND(hwnd), ctypes.byref(pid))
    return pid.value


def _alive(pid: int) -> bool:
    h = k.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    code = wt.DWORD()
    ok = k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return bool(ok) and code.value == 259


def _title(hwnd: int) -> str:
    n = u.GetWindowTextLengthW(wt.HWND(hwnd))
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(wt.HWND(hwnd), b, n + 1)
    cls = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(wt.HWND(hwnd), cls, 256)
    return f"{b.value!r} [{cls.value}]"


def main() -> int:
    if not os.path.isdir(_JOURNAL_DIR):
        print(f"no journal dir at {_JOURNAL_DIR!r}")
        return 0
    names = [f for f in os.listdir(_JOURNAL_DIR)
             if f.startswith("hojaiga_parked_") and f.endswith(".json")]
    print(f"journal dir: {_JOURNAL_DIR}")
    print(f"pending journals: {len(names)}")
    t_all = time.perf_counter()
    for fn in sorted(names):
        try:
            owner = int(fn[len("hojaiga_parked_"):-len(".json")])
        except ValueError:
            print(f"  {fn}: unparsable owner")
            continue
        alive = _alive(owner)
        print(f"  {fn}  owner_pid={owner} alive={alive}")
        if alive:
            print("      owner still running -> recover_parked skips it")
            continue
        try:
            with open(os.path.join(_JOURNAL_DIR, fn), encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            print(f"      unreadable: {type(exc).__name__}: {exc}")
            continue
        for h in data:
            hwnd = int(h)
            t0 = time.perf_counter()
            if not u.IsWindow(wt.HWND(hwnd)):
                print(f"      hwnd={hwnd} gone")
                continue
            ok, mr = _resp(hwnd)
            print(f"      hwnd={hwnd} {_title(hwnd)} pid={_pid(hwnd)} "
                  f"visible={bool(u.IsWindowVisible(wt.HWND(hwnd)))} "
                  f"iconic={bool(u.IsIconic(wt.HWND(hwnd)))} "
                  f"responds={ok} msgresult={mr} probe={time.perf_counter() - t0:.2f}s")
    print(f"total {time.perf_counter() - t_all:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
