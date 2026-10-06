"""Probe 3: how does a background-parked spreadsheet get a value into a cell, headlessly?

A grid is not an edit: measured, the worksheet is a DataGridControl with 492 DataItemControl cells, while the
only real EditControls are the search strip, the name box, and the formula bar. So the loop cannot 'type into
a cell' the way it types into a box. This measures the two candidate roads:
  A. select the cell (post_click on the grid at the cell's own rect) -> post characters to the window under it
  B. same, plus F2 to enter edit mode first
and reads the result out of the cell's own UIA name, not a screenshot.
"""
import ctypes
import os
import sys
import time

os.environ.setdefault("PYTHONPATH", r"D:\new_automation;D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs import fast_uia as fu                                # noqa: E402
from core_organs import headless_input as hin                         # noqa: E402
from core_organs import organ_48_app_behavior_model as bmx            # noqa: E402
from core_organs.desktop_grounding import DesktopGrounding            # noqa: E402

g = DesktopGrounding()
hwnd = g.find_window("excel")
if not hwnd:
    print("no excel window")
    sys.exit(2)
hwnd = int(hwnd)
u = ctypes.windll.user32


def cells():
    return [n for n in (fu.snapshot(hwnd, timeout_ms=8000) or [])
            if str(n.ctype) == "DataItemControl"]


def grid():
    return next((n for n in (fu.snapshot(hwnd, timeout_ms=8000) or [])
                 if str(n.ctype) == "DataGridControl"), None)


def child_class_of(n):
    l, t, r, b = n.rect
    try:
        c = n.ctrl
        return (int(c.NativeWindowHandle or 0) or 0, str(c.ClassName or ""))
    except Exception:
        return 0, ""


gn = grid()
print("grid:", None if gn is None else (gn.name, gn.rect, child_class_of(gn)))
cs = cells()
print("cells:", len(cs))
for n in cs[:6]:
    print("   cell:", repr(str(n.name))[:30], n.rect, n.pats, child_class_of(n))

if gn is None:
    sys.exit(1)

# the window that actually receives keyboard input inside the grid
l, t, r, b = gn.rect
under = hin.child_at(hwnd, (l + r) // 2, (t + b) // 2)
print("\nchild_at grid centre:", under, hin._class_name(under))
print("all descendant classes of XLMAIN:")
seen = []


def walk(h, depth=0):
    seen.append((depth, int(h), hin._class_name(h)))
    child = u.GetWindow(int(h), 5)          # GW_CHILD
    while child:
        walk(child, depth + 1)
        child = u.GetWindow(child, 2)       # GW_HWNDNEXT
    return


walk(hwnd)
for d, h, c in seen:
    if d <= 2 and c:
        print(f"   {'  ' * d}{c:<22} {h}")

target = under or hwnd


def try_road(label, value, f2):
    # press Enter first to leave any half-typed edit state, then re-read
    hin.post_key_combo(target, "enter")
    time.sleep(0.6)
    cs2 = cells()
    if not cs2:
        print(f"[{label}] no cells found")
        return
    cell = cs2[0]
    cl, ct, cr, cb = cell.rect
    ok, note = hin.post_click(target, (cl + cr) // 2, (ct + cb) // 2)
    print(f"[{label}] click cell0 -> {ok} {note}")
    time.sleep(0.7)
    if f2:
        print(f"[{label}] F2 ->", hin.post_key_combo(target, "f2")[1])
        time.sleep(0.7)
        ed = hin.focused_control(hwnd)
        print(f"[{label}] focused after F2:", ed, hin._class_name(ed))
        kt = ed or target
    else:
        kt = target
    print(f"[{label}] type {value!r} ->", hin.post_text(kt, value)[1])
    time.sleep(1.2)
    after = cells()
    hit = [(str(n.name)[:20], n.rect) for n in after if value in str(n.name or "")]
    nb = [str(n.name)[:20] for n in (fu.snapshot(hwnd, timeout_ms=8000) or [])
          if str(n.ctype) == "EditControl" and n.rect[0] < 130 and 220 < n.rect[1] < 270]
    print(f"[{label}] cells holding {value!r}: {hit[:4]} | name-box reads: {nb}")


try_road("A no-F2", "42", False)
hin.post_key_combo(target, "enter")
time.sleep(0.8)
hin.post_key_combo(target, "esc")
time.sleep(0.8)
try_road("B with-F2", "7", True)
