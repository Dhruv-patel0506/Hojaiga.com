"""What does WinUI Calculator ACTUALLY expose? Ground a live Calculator and dump every element's
role/name/value, and separately show how many survive the engine's ACTIONABLE-role offer filter.
This decides whether the calc miss is 'content not realized' vs 'buttons present but named/filtered
in a way the judge can't use' - stop guessing with 150s runs."""
import io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation")
import os, win32gui, win32con
from core_organs import desktop_grounding as dg, capability_probe as cp

os.startfile("calc.exe")
hwnd = 0
for _ in range(24):
    time.sleep(0.5)
    hs = []
    win32gui.EnumWindows(lambda h, _: hs.append(h) if win32gui.IsWindowVisible(h)
                         and (win32gui.GetWindowText(h) or "") == "Calculator" else None, None)
    if hs:
        hwnd = hs[0]; break
print("hwnd=", hwnd, "verdict=", cp.support_verdict(hwnd) if hwnd else None)

g = dg.DesktopGrounding()
els = g._walk_uia(hwnd) if hwnd else []
print("TOTAL elements walked=", len(els))
digity = [(e.role, e.name, getattr(e, "value", "") or "") for e in els
          if (e.name or "") and any(c.isdigit() for c in (e.name or "")) or
          (e.name or "").strip() in ("+", "=", "plus", "equals", "two", "one")]
print("digit/operator-named elements=", len(digity))
for row in digity[:25]:
    print("   ", row)
# what roles exist + a sample of ALL names, to see how buttons are labelled
from collections import Counter
print("role counts=", Counter(e.role for e in els).most_common(12))
names = [e.name for e in els if e.name][:40]
print("first 40 names=", names)

hs = []
win32gui.EnumWindows(lambda h, _: hs.append(h) if (win32gui.GetWindowText(h) or "") == "Calculator" else None, None)
for h in hs:
    win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
print("closed")
