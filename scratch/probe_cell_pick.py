"""Probe 4: can a cell be PICKED headlessly (not by where the last click happened to land), and can the
reference box navigate to it?

Road B of probe 3 proved F2 -> editor window -> typed chars land in a cell. Two links are still missing:
  1. how to choose WHICH cell (the grid exposes 492 DataItemControl; do they carry SelectionItem/ScrollIntoView?)
  2. whether the little box beside the formula bar (the reference/name box) can be driven to select a named cell.
Both are UIA/pattern facts, not app knowledge.
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
_h = g.find_window("excel")
if not _h:
    print("no excel window")
    sys.exit(2)
hwnd = int(_h)
u = ctypes.windll.user32


def snap():
    return fu.snapshot(hwnd, timeout_ms=8000) or []


def read_reference_box(ns):
    """The edit that sits to the LEFT of the formula bar, at the same height - the cell-reference box."""
    fb = next((n for n in ns if str(n.aid) == "FormulaBar" or "formula" in str(n.name).lower()), None)
    if fb is None:
        return None, None
    fl, ft, fr, fb_ = fb.rect
    for n in ns:
        l, t, r, b = n.rect
        if str(n.ctype).lower().startswith("edit") and r <= fl + 4 and abs(t - ft) < 6 and (r - l) > 20:
            return n, fb
    return None, fb


ns = snap()
fb_edits = [(str(n.name)[:24], n.rect) for n in ns if str(n.ctype) == "EditControl"]
print("all edits:", fb_edits)
refbox, fb = read_reference_box(ns)
print("reference box:", None if refbox is None else (refbox.rect, refbox.pats, repr(str(refbox.name))))

print("\n-- DataItem patterns (first 12 cells inside the grid body, not headers) --")
grid = next((n for n in ns if str(n.ctype) == "DataGridControl"), None)
gl, gt, gr, gb = grid.rect
body = [n for n in ns if str(n.ctype) == "DataItemControl" and n.rect[1] > gt + 2]
for n in body[:12]:
    print(f"   {str(n.name)[:14]:<16} {n.rect} pats={n.pats} selected={n.selected} enabled={n.enabled}")
print("body cells:", len(body))

# 1. UIA-select a named cell directly
name = "A1"
match = [n for n in body if str(n.name).strip().upper() == name]
print(f"\ncells named {name!r}:", [(str(x.name), x.rect, x.pats) for x in match])
if match:
    ok, note = bmx.invoke_node_safely(match[0])
    print("invoke/select:", ok, note)
    time.sleep(1.0)
    _now = read_reference_box(snap())[0]
    print("reference box now:", repr(str(_now.name if _now else "")[:20]))

# 2. navigate by typing the reference into the box
target_box = read_reference_box(snap())[0]
if target_box is not None:
    bh = int(getattr(target_box.ctrl, "NativeWindowHandle", 0) or 0) or hwnd
    print("\nreference box native hwnd:", bh, hin._class_name(bh))
    for nm in ("B3", "A1"):
        u.SendMessageW(bh, 0x00B1, 0, -1)                      # EM_SETSEL(0,-1)
        u.SendMessageW(bh, 0x0303, 0, 0)                       # WM_CLEAR
        print(f"  type {nm!r} ->", hin.post_text(bh, nm)[1])
        time.sleep(0.3)
        print("  read back:", repr(str(hin.safe_window_text(bh) or "")[:20]))
        hin.post_key_combo(bh, "enter")
        time.sleep(1.0)
        after = read_reference_box(snap())
        print("  box reads after Enter:", repr(str(after[0].name if after[0] else ""))[:24])
