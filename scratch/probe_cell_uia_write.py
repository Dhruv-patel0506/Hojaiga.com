"""Probe 9: five posted keys all failed on this app in the background (probe 8, measured) - so write through
the app's OWN UIA patterns and see which one reaches the document.

The grid is reachable by UIA (invoke opened a document, select moved the selection, both measured). The
question is which settable pattern actually alters cell content: the value pattern of the cell, of the
surface that mirrors the selected cell, a Legacy IAccessible value, or a Text pattern range. The witness is
always the same two facts: what the mirror surface reads, and any cell whose name stops being a reference.
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


def body(ns):
    gl = next((n for n in ns if str(n.ctype) == "DataGridControl"), None)
    if not gl:
        return []
    return [n for n in ns if str(n.ctype) == "DataItemControl" and "Header" not in str(n.cls)
            and gl.rect[1] + 2 < n.rect[1] < gl.rect[3]]


def mirror(ns):
    """The surface that displays what the selected object holds (any app with a document has one)."""
    return [n for n in ns if "edit" in str(n.ctype).lower()
            and (n.rect[2] - n.rect[0]) > 400]


def witness(tag):
    ns = snap()
    out = [f"{tag}:"]
    for n in mirror(ns):
        try:
            v = str(n.ctrl.GetValuePattern().Value or "")
        except Exception:
            v = f"<{type(Exception).__name__}>"
        if v or "formula" in str(n.name).lower():
            out.append(f"    mirror {str(n.name)[:18]!r:<22} = {v[:30]!r}")
    vals = [(str(n.name), n.rect) for n in body(ns) if str(n.name) and not REF_RE.match(str(n.name).strip().upper())]
    out.append(f"    cells whose name is not a reference = {vals[:6]}")
    out.append(f"    selected = {[str(n.name) for n in body(ns) if n.selected][:4]}")
    print("\n".join(out))


def pick(ref):
    ns = snap()
    bd = body(ns)
    cell = next((n for n in bd if str(n.name).strip().upper() == ref.upper()), None)
    if cell is not None:
        bmx.invoke_node_safely(cell)
        time.sleep(0.8)
    return cell


witness("start")
cell = pick("A1")
print("A1 selectable:", cell is not None, cell.pats if cell else "")

print("\n=== W1: value pattern on the MIRROR surface ===")
ns = snap()
m = mirror(ns)
for n in m:
    try:
        n.ctrl.GetValuePattern().SetValue("42")
        print(f"  SetValue on {str(n.name)[:18]!r}: dispatched")
    except Exception as exc:
        print(f"  SetValue on {str(n.name)[:18]!r}: {type(exc).__name__} {str(exc)[:60]}")
    time.sleep(0.8)
    witness("    after")

print("\n=== W2: commit the mirror with its own keyboard (a real edit takes WM_CHAR) ===")
ns = snap()
m = mirror(ns)
for n in m:
    nh = int(getattr(n.ctrl, "NativeWindowHandle", 0) or 0)
    if not nh:
        continue
    print(f"  {str(n.name)[:18]!r} hwnd={nh} class={hin._class_name(nh)} value="
          f"{repr(str(hin.safe_window_text(nh))[:20])}")
    print("    Enter ->", hin.post_key_combo(nh, "enter")[1])
    time.sleep(1.2)
    witness("    after Enter")

print("\n=== W3: value pattern on the CELL itself ===")
cell = pick("B2")
if cell is not None:
    try:
        cell.ctrl.GetValuePattern().SetValue("77")
        print("  cell SetValue dispatched")
    except Exception as exc:
        print("  cell SetValue:", type(exc).__name__, str(exc)[:70])
    time.sleep(1.0)
    witness("    after")

print("\n=== W4: Legacy IAccessible value on the cell ===")
if cell is not None:
    try:
        lip = cell.ctrl.GetLegacyIAccessiblePattern()
        lip.SetValue("88")
        print("  LegacyIAccessible.SetValue dispatched")
    except Exception as exc:
        print("  legacy:", type(exc).__name__, str(exc)[:70])
    time.sleep(1.0)
    witness("    after")

print("\n=== W5: Text pattern range on the cell ===")
if cell is not None:
    try:
        tp = cell.ctrl.GetTextPattern()
        rng = tp.DocumentRange
        rng.SetText("99")
        print("  TextPattern SetText dispatched")
    except Exception as exc:
        print("  text pattern:", type(exc).__name__, str(exc)[:70])
    time.sleep(1.0)
    witness("    after")
