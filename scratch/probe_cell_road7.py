"""Probe 7: the definitive cell-write road, judged by witnesses that cannot lie.

Corrected after probe 6 exposed a bad read: a cell's UIA Name is its REFERENCE, so 'type 7 into D4' was
"verified" by finding the row header named 7. The two surfaces that actually show a cell's content are
  * the formula-bar edit (aid 'FormulaBar', pats ['text']) - it mirrors the SELECTED cell
  * an EditControl that appears AT the cell's own rect the moment the cell enters edit mode (probe 2 saw
    one named 'Edit Cell' sitting exactly on A1's rect)
Road under test: UIA select the cell -> confirm by the reference box -> enter edit mode -> find the edit
that appeared on the cell's rect -> post characters to IT -> commit -> confirm through the formula bar.
"""
import os
import re
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
REF_RE = re.compile(r"^[A-Z]{1,3}[0-9]{1,7}$")


def snap():
    return fu.snapshot(hwnd, timeout_ms=8000) or []


def grid(ns):
    return next((n for n in ns if str(n.ctype) == "DataGridControl"), None)


def body(ns):
    gl = grid(ns)
    if not gl:
        return []
    return [n for n in ns if str(n.ctype) == "DataItemControl" and "Header" not in str(n.cls)
            and gl.rect[1] + 2 < n.rect[1] < gl.rect[3]]


def edit_controls(ns):
    return [n for n in ns if "edit" in str(n.ctype).lower()]


def state(tag):
    ns = snap()
    bd = body(ns)
    sel = [n for n in bd if n.selected]
    lines = [f"{tag}: selected={[(str(n.name), n.rect) for n in sel]}"]
    for n in edit_controls(ns):
        nm = str(n.name)
        if (nm and not REF_RE.match(nm.upper()) and "search" not in nm.lower()
                and nm.lower() not in ("font", "font size", "number format")):
            try:
                v = n.ctrl.GetValuePattern().Value
            except Exception:
                v = ""
            lines.append(f"    edit {nm[:22]!r:<26} rect={n.rect} value={str(v)[:28]!r}")
    print("\n".join(lines))
    return ns, sel


def find_cell(ns, ref):
    bd = body(ns)
    return next((n for n in bd if str(n.name).strip().upper() == ref.upper()), None)


state("initial")

ns = snap()
target = find_cell(ns, "A1") or (body(ns) or [None])[0]
if target is None:
    print("no grid cells: not on a document?")
    sys.exit(1)
tre = target.rect
print("\ntarget rect:", tre, "pats:", target.pats)

gl = grid(ns)
keyboard = hin.child_at(hwnd, (gl.rect[0] + gl.rect[2]) // 2, (gl.rect[1] + gl.rect[3]) // 2)
print("keyboard window:", keyboard, hin._class_name(keyboard))

print("\n--- step 1: UIA select ---")
print("  ", bmx.invoke_node_safely(target))
time.sleep(0.9)
ns, sel = state("after select")

print("\n--- step 2: enter edit mode (F2 to the keyboard window) ---")
print("  ", hin.post_key_combo(keyboard, "f2")[1])
time.sleep(1.0)
ns, sel = state("after F2")
on_cell = [n for n in edit_controls(ns)
           if abs(n.rect[0] - tre[0]) < 12 and abs(n.rect[1] - tre[1]) < 12]
print("  edit that appeared on the cell:", [(str(n.name), n.rect) for n in on_cell])

print("\n--- step 3: type into it ---")
if on_cell:
    eh = int(getattr(on_cell[0].ctrl, "NativeWindowHandle", 0) or 0) or keyboard
    print("  cell-edit hwnd:", eh, hin._class_name(eh))
    print("  type:", hin.post_text(eh, "42")[1])
    time.sleep(1.0)
    state("after typing")
    print("  commit Enter:", hin.post_key_combo(eh, "enter")[1])
    time.sleep(1.4)
    state("after Enter")

print("\n--- step 4: does a value show anywhere at all? (whole-grid scan) ---")
ns = snap()
vals = [(str(n.name), n.rect) for n in body(ns)
        if str(n.name) and not REF_RE.match(str(n.name).strip().upper())]
print("  non-reference cells:", vals[:10])
for n in edit_controls(ns):
    try:
        v = n.ctrl.GetValuePattern().Value
    except Exception:
        v = ""
    if v and "42" in str(v):
        print("  edit holding 42:", str(n.name), repr(str(v))[:40])
