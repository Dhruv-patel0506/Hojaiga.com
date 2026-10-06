"""Probe 5: the decisive question - can a cell take a value through its OWN UIA patterns?

Probe 4 measured that spreadsheet cells are DataItemControl with pats=['invoke','select','value'] and a real
'selected' state (A1 selected=True, B1 False). If SetValue on the cell's ValuePattern lands, the loop writes a
cell exactly the way it writes any other box - headless, no click, no keyboard, no app knowledge. Otherwise the
fallback measured in probe 3 (select cell -> F2 -> post chars to the focused editor) is used.
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


def body_cells(ns):
    grid = next((n for n in ns if str(n.ctype) == "DataGridControl"), None)
    gt = grid.rect[1] if grid else 0
    return [n for n in ns if str(n.ctype) == "DataItemControl" and n.rect[1] > gt + 2]


def read(ref, rect=None):
    ns = snap()
    cs = body_cells(ns)
    # a cell that receives a value stops answering to its reference: match the SAME surface by position
    hit = next((n for n in cs if (rect and n.rect == rect)), None)
    hit = hit or next((n for n in cs if str(n.name).strip().upper() == str(ref).upper()), None)
    sel = [str(n.name) for n in cs if n.selected]
    return hit, sel


for ref, val in (("C3", "42"), ("D4", "7"), ("E5", "hello")):
    ns = snap()
    cs = body_cells(ns)
    cell = next((n for n in cs if str(n.name).strip().upper() == ref), None)
    if cell is None:
        print(f"{ref}: not in the tree (off-screen?) - cells visible: {len(cs)}")
        continue
    print(f"\n{ref}: rect={cell.rect} pats={cell.pats} selected={cell.selected}")
    here = cell.rect
    ok_sel, note_sel = bmx.invoke_node_safely(cell)
    print("  select/invoke:", ok_sel, note_sel)
    time.sleep(0.6)
    hit, sel = read(ref, here)
    print(f"  after select: selected cells = {sel[:4]} | cell name = {str(hit.name) if hit else None!r}")
    wrote = None
    try:
        vp = cell.ctrl.GetValuePattern()
        vp.SetValue(val)
        wrote = "uia SetValuePattern"
    except Exception as exc:
        print("  SetValue failed:", type(exc).__name__, str(exc)[:90])
    time.sleep(0.9)
    hit, sel = read(ref, here)
    print(f"  [{wrote}] cell now reads {str(hit.name) if hit else None!r}; selected={sel[:3]}")
    if not (hit and val in str(hit.name)):
        # fallback road: keyboard into the focused editor
        editor = hin.focused_control(hwnd)
        print("  fallback: focused control:", editor, hin._class_name(editor))
        print("  F2 ->", hin.post_key_combo(editor, "f2")[1])
        time.sleep(0.5)
        ed2 = hin.focused_control(hwnd)
        print("  type ->", hin.post_text(ed2, val)[1])
        time.sleep(0.8)
        hin.post_key_combo(ed2, "enter")
        time.sleep(1.0)
        hit, sel = read(ref, here)
        print(f"  AFTER keyboard road: cell reads {str(hit.name) if hit else None!r}")

print("\nfinal grid read:", [str(n.name) for n in body_cells(snap()) if str(n.name) in
                            ("42", "7", "hello", "C3", "D4", "E5")][:8])
