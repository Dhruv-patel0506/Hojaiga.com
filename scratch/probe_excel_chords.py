"""Chord safety harness: post one key sequence at a time into a live Excel and report whether
the workbook is still there afterwards. This is what tells us which accelerators are safe to
use and which ones silently reach File -> Close."""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(r"D:\new_automation\All codes")))
for s in (sys.stdout, sys.stderr):
    try:
        rc = getattr(s, "reconfigure", None)
        if callable(rc):
            rc(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core_organs import fast_uia, headless_input  # noqa: E402

EXE = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"
UIA_INVOKE = 10000

CHORDS = ["ctrl+home", "ctrl+b", "ctrl+i", "ctrl+u", "ctrl+e", "ctrl+shift+l", "shift+f2",
          "escape", "ctrl+shift+4", "ctrl+shift+5", "ctrl+shift+3", "ctrl+l", "enter",
          "shift+f11", "alt+f1", "alt+h,o,i", "alt+w,f,f", "alt+p,o,a,l", "alt+h,l,g"]


def book():
    for h, t in headless_input.top_level_titles(visible_only=False):
        tl = (t or "").strip().lower()
        if tl.endswith("- excel") and "book" in tl:
            return int(h), t
    return None, None


def nodes(hwnd):
    return fast_uia.snapshot(hwnd, max_nodes=30000) or []


def tabs(hwnd):
    return [str(n.name) for n in nodes(hwnd) if "tabitem" in n.ctype.lower()]


proc = None
h, t = book()
if h is None:
    proc = subprocess.Popen([EXE, "/n"], creationflags=0x00000200)
    for _ in range(40):
        time.sleep(1.5)
        h, t = book()
        if h:
            break
        for hh, tt in headless_input.top_level_titles(visible_only=False):
            if (tt or "").strip().lower() == "excel":
                for n in nodes(int(hh)):
                    if "blank workbook" in str(n.name or "").lower():
                        try:
                            n.ctrl.GetPattern(UIA_INVOKE).Invoke()
                        except Exception:
                            pass
                        break
                break
print("workbook:", h, t)
if h is None:
    sys.exit(1)

print(f"\n{'chord':16s} {'posted':7s} {'alive':6s} {'nodes':>6s} {'tabs':>5s}  note")
for chord in CHORDS:
    before = len(nodes(h))
    ok, note = headless_input.post_key_combo(h, chord)
    time.sleep(1.6)
    headless_input.post_key_combo(h, "escape")       # back out of any menu that opened
    time.sleep(0.8)
    h2, t2 = book()
    alive = h2 is not None
    after = len(nodes(h2)) if alive else 0
    ntab = len(tabs(h2)) if alive else 0
    flag = ""
    if not alive:
        flag = "<<< WORKBOOK GONE"
    elif before and after and after < before * 0.4:
        flag = "(tree shrank a lot)"
    print(f"{chord:16s} {str(ok):7s} {str(alive):6s} {after:6d} {ntab:5d}  {flag}")
    if not alive:
        print("\nSTOP: this chord killed the session; the rest cannot be tested in one run.")
        break
    h = h2

if proc is not None and proc.poll() is None:
    proc.terminate()
