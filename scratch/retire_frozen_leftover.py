"""Retire a FROZEN leftover app window that no hygiene pass can restore.

A window whose thread stopped answering cannot be closed politely (WM_CLOSE is a Send too,
and PostMessage only queues it behind a pump that never runs). Leaving it on the desktop makes
the next run's leg for that app observe a corpse, which is how a leftover Paint turned MIN1's
paint leg into 'effect=None unwound=None'.

Ownership rule is DATA, not app names: the harness parks the windows it uses at PARK_X/PARK_Y
(-24000,-24000), so a top-level window sitting entirely off the real screens with a dead-or-
wedged owner is a harness leftover. Anything else is the user's and is left alone.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import time

import psutil

u = ctypes.windll.user32
k = ctypes.windll.kernel32

PARK_X = int(os.environ.get("HOJAIGA_PARK_X", "-24000"))
PARK_Y = int(os.environ.get("HOJAIGA_PARK_Y", "-24000"))
WM_CLOSE, SMTO_ABORTIFHUNG, SMTO_BLOCK = 0x0010, 0x0002, 0x0001


def _rect(hwnd):
    r = wt.RECT()
    u.GetWindowRect(wt.HWND(hwnd), ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def _title(hwnd):
    n = u.GetWindowTextLengthW(wt.HWND(hwnd))
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(wt.HWND(hwnd), b, n + 1)
    return b.value


def _pid(hwnd):
    p = wt.DWORD()
    u.GetWindowThreadProcessId(wt.HWND(hwnd), ctypes.byref(p))
    return p.value


def _answers(hwnd, ms=500):
    res = ctypes.c_size_t(0)
    return bool(u.SendMessageTimeoutW(wt.HWND(hwnd), 0x0000, 0, 0,
                                      SMTO_ABORTIFHUNG | SMTO_BLOCK, ms, ctypes.byref(res)))


def _offscreen_parked(hwnd):
    """True when the window sits at the harness park position, i.e. entirely outside every real screen."""
    l, t, r, b = _rect(hwnd)
    return l <= PARK_X + 100 and t <= PARK_Y + 100


def _dead_journal_hwnds():
    """hwnd -> journal file for windows a DEAD suite process parked. Strongest ownership evidence there is:
    an interrupted recovery can leave the window back on screen, where the position rule alone cannot see it."""
    out = {}
    d = os.environ.get("TEMP", ".")
    try:
        names = [f for f in os.listdir(d) if f.startswith("hojaiga_parked_") and f.endswith(".json")]
    except Exception:
        return out
    for fn in names:
        try:
            owner = int(fn[len("hojaiga_parked_"):-len(".json")])
        except ValueError:
            continue
        if owner == os.getpid():
            continue
        h_proc = k.OpenProcess(0x1000, False, owner)       # PROCESS_QUERY_LIMITED_INFORMATION
        if h_proc:
            code = wt.DWORD()
            alive = k.GetExitCodeProcess(h_proc, ctypes.byref(code)) and code.value == 259
            k.CloseHandle(h_proc)
            if alive:
                continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as fh:
                for h in json.load(fh):
                    out[int(h)] = fn
        except Exception:
            pass
    return out


def main() -> int:
    dead_journals = _dead_journal_hwnds()
    victims, journal_hits, seen = [], set(), set()
    for hwnd in ([int(x) for x in sys.argv[1:]] or list(dead_journals)):
        if not u.IsWindow(wt.HWND(hwnd)):
            print(f"hwnd={hwnd} already gone")
            continue
        pid = _pid(hwnd)
        why = []
        if _offscreen_parked(hwnd):
            why.append("at the park position")
        if hwnd in dead_journals:
            why.append(f"listed in dead-owner journal {dead_journals[hwnd]}")
            journal_hits.add(dead_journals[hwnd])
        if not why:
            print(f"REFUSE hwnd={hwnd} ({_title(hwnd)!r}) - no harness ownership evidence, so not ours to kill")
            continue
        print(f"OURS   hwnd={hwnd} ({_title(hwnd)!r}) because " + " and ".join(why))
        victims.append((hwnd, pid))

    for hwnd, pid in victims:
        print(f"hwnd={hwnd} title={_title(hwnd)!r} pid={pid} "
              f"rect={_rect(hwnd)} answers={_answers(hwnd)}")
        if _answers(hwnd, 300):
            res = ctypes.c_size_t(0)
            u.SendMessageTimeoutW(wt.HWND(hwnd), WM_CLOSE, 0, 0,
                                  SMTO_ABORTIFHUNG | SMTO_BLOCK, 1500, ctypes.byref(res))
            time.sleep(1.0)
        if u.IsWindow(wt.HWND(hwnd)) and pid not in seen:
            seen.add(pid)
            try:
                p = psutil.Process(pid)
                print(f"  terminating pid={pid} {p.name()} (cmd={' '.join(p.cmdline())[:120]})")
                p.terminate()
                p.wait(timeout=5)
            except psutil.NoSuchProcess:
                print("  already exited")
            except Exception as exc:
                print(f"  terminate failed: {type(exc).__name__}: {exc}")
    for fn in sorted(journal_hits):                             # spent: the window it describes is gone
        try:
            os.remove(os.path.join(os.environ.get("TEMP", "."), fn))
            print(f"removed dead-owner journal {fn}")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
