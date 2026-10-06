"""Probe 6: pin down the one road that really writes a cell, and PROVE it from the whole grid.

Probes 3-5 disagreed because a cell's UIA name is its reference when empty and its value once written, so
'look for a cell named C3' silently loses the cell it renamed. This reads the entire labelled-by-position
picture: column headers, row headers, and every cell rect, before and after each road.
"""
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


def snap():
    return fu.snapshot(hwnd, timeout_ms=8000) or []


def parts(ns):
    grid = next((n for n in ns if str(n.ctype) == "DataGridControl"), None)
    cols = [n for n in ns if str(n.ctype) == "DataItemControl" and "GridColumnHeader" in str(n.cls)]
    rows = [n for n in ns if str(n.ctype) == "DataItemControl" and "GridRowHeader" in str(n.cls)]
    body = [n for n in ns if str(n.ctype) == "DataItemControl"
            and grid and n.rect[1] > grid.rect[1] + 2 and "Header" not in str(n.cls)]
    return grid, cols, rows, body


def table():
    ns = snap()
    grid, cols, rows, body = parts(ns)
    print(f"  grid={grid.rect if grid else None} cols={len(cols)} rows={len(rows)} body={len(body)}")
    occupied = [(str(n.name), n.rect, n.selected) for n in body
                if not (n.rect[2] - n.rect[0]) and False or str(n.name) and not _looks_like_ref(str(n.name))]
    print("  cells holding something that is not a reference:", occupied[:12])
    return body


def _looks_like_ref(s):
    import re
    return bool(re.fullmatch(r"[A-Z]{1,3}[0-9]{1,7}", s.strip().upper()))


body = table()
a1 = next((n for n in body if str(n.name).strip().upper() == "A1"), None)
print("\nA1:", None if a1 is None else (a1.rect, a1.pats, a1.selected))

# every road, then one whole-table read
if a1 is not None:
    l, t, r, b = a1.rect
    cx, cy = (l + r) // 2, (t + b) // 2
    # the keyboard window: the child under the grid, proven in probe 3
    gl = grid = next((n for n in snap() if str(n.ctype) == "DataGridControl"), None)
    keyboard = hin.child_at(hwnd, (gl.rect[0] + gl.rect[2]) // 2, (gl.rect[1] + gl.rect[3]) // 2)
    print("keyboard window:", keyboard, hin._class_name(keyboard))

    print("\n--- ROAD 1: click A1, type straight (no F2) ---")
    hin.post_key_combo(keyboard, "esc")
    time.sleep(0.5)
    print("  click:", hin.post_click(keyboard, cx, cy)[1])
    time.sleep(0.7)
    b1 = table()
    sel1 = [str(n.name) for n in b1 if n.selected]
    print("  selected:", sel1[:4])
    print("  type:", hin.post_text(keyboard, "42")[1])
    time.sleep(0.8)
    hin.post_key_combo(keyboard, "enter")
    time.sleep(1.0)
    table()

    print("\n--- ROAD 2: click A1, F2, type, Enter ---")
    hin.post_key_combo(keyboard, "esc")
    time.sleep(0.5)
    print("  click:", hin.post_click(keyboard, cx, cy)[1])
    time.sleep(0.7)
    print("  F2:", hin.post_key_combo(keyboard, "f2")[1])
    time.sleep(0.6)
    ed = hin.focused_control(hwnd)
    print("  focused now:", ed, hin._class_name(ed))
    print("  type:", hin.post_text(ed, "99")[1])
    time.sleep(0.8)
    table()
    hin.post_key_combo(ed, "enter")
    time.sleep(1.2)
    table()

    print("\n--- ROAD 3: UIA select + UIA SetValue on the cell, no keyboard at all ---")
    ns = snap()
    _, _, _, bd = parts(ns)
    a1b = next((n for n in bd if n.rect == a1.rect), None) or \
        next((n for n in bd if str(n.name).strip().upper() == "A1"), None)
    print("  target:", None if a1b is None else (str(a1b.name), a1b.rect))
    if a1b is not None:
        try:
            a1b.ctrl.GetValuePattern().SetValue("123")
            print("  SetValue('123') dispatched")
        except Exception as exc:
            print("  SetValue error:", type(exc).__name__, str(exc)[:70])
        time.sleep(1.2)
        table()
