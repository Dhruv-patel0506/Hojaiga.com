"""Probe 13: WM_CHAR to the frame opened an in-cell editor once (probe 2, measured) - test that road again
with the witness that was missing: the cell's VALUE.

Probe 12 proved the right witness: a cell carries its reference in Name AND AutomationId, and its content in
the value pattern (every cell read '' after all the earlier writes). Probe 2, typing raw characters to the
top-level frame, produced an EditControl named 'Edit Cell' sitting on A1's rect - a cell editor - and no later
probe ever looked for it again. So: post characters to the frame, wait for the editor, type, commit, and read
the cell's value.
"""
import ctypes
import os
import sys
import threading
import time

os.environ.setdefault("PYTHONPATH", r"D:\new_automation;D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes")

import uiautomation as auto                                             # noqa: E402
from core_organs import fast_uia as fu                                  # noqa: E402
from core_organs import headless_input as hin                           # noqa: E402
from core_organs import organ_48_app_behavior_model as bmx              # noqa: E402
from core_organs.desktop_grounding import DesktopGrounding              # noqa: E402

g = DesktopGrounding()
_h = g.find_window("excel")
if not _h:
    print("no excel window")
    sys.exit(2)
hwnd = int(_h)
u = ctypes.windll.user32


def snap():
    return fu.snapshot(hwnd, timeout_ms=8000) or []


def cell_values(refs):
    """Read the VALUE of named cells on a UIA thread - the only place content lives."""
    out: dict = {}

    def _w():
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(hwnd)
            stack = [root]
            want = {r.upper() for r in refs}
            while stack:
                c = stack.pop()
                try:
                    if (c.ControlTypeName or "") == "DataItemControl":
                        aid = (c.AutomationId or "").strip().upper()
                        if aid in want:
                            vp = c.GetValuePattern()
                            out[aid] = (str(vp.Value) if vp is not None else None)
                    stack.extend(c.GetChildren())
                except Exception:
                    continue
    t = threading.Thread(target=_w, daemon=True)
    t.start()
    t.join(30)
    return out


def editors(tag):
    ns = snap()
    ed = [(str(n.name), n.rect, n.pats) for n in ns if "edit" in str(n.ctype).lower()
          and (n.rect[2] - n.rect[0]) < 400]
    print(f"  {tag}: narrow edits = {ed}")
    return ns


print("before:", cell_values(["A1", "B2", "C3"]))

# clear any half state, then select A1 through the app's own UIA
hin.post_key_combo(hwnd, "esc")
time.sleep(0.5)
ns = snap()
gl = next((n for n in ns if str(n.ctype) == "DataGridControl"), None)
a1 = next((n for n in ns if str(n.ctype) == "DataItemControl"
           and str(n.aid).strip().upper() == "A1"), None)
print("A1 node:", None if a1 is None else (a1.name, a1.rect, a1.pats))
print("select:", bmx.invoke_node_safely(a1) if a1 else "no cell")
time.sleep(0.8)
print("after select:", cell_values(["A1"]))

print("\n--- ROAD: raw WM_CHAR to the frame, as probe 2 did ---")
editors("before typing")
for ch in "42":
    u.PostMessageW(hwnd, 0x0102, ord(ch), 1)
    time.sleep(0.25)
time.sleep(1.0)
ns2 = editors("after typing")
oncell = [n for n in ns2 if "edit" in str(n.ctype).lower() and a1
          and abs(n.rect[0] - a1.rect[0]) < 16 and abs(n.rect[1] - a1.rect[1]) < 16]
print("  editor on the cell:", [(str(n.name), n.rect, n.pats) for n in oncell])
print("  A1 value now:", cell_values(["A1"]))
if oncell:
    eh = int(getattr(oncell[0].ctrl, "NativeWindowHandle", 0) or 0)
    print("  editor hwnd:", eh, hin._class_name(eh), "text:", repr(hin.safe_window_text(eh, 400)))
    if eh:
        for ch in "99":
            u.PostMessageW(eh, 0x0102, ord(ch), 1)
            time.sleep(0.2)
        time.sleep(0.8)
        print("  after extra typing:", repr(hin.safe_window_text(eh, 400)), cell_values(["A1"]))
print("commit Enter to the frame:", hin.post_key_combo(hwnd, "enter")[1])
time.sleep(1.5)
print("A1 value after commit:", cell_values(["A1"]))
print("editors now:", editors("post"))

print("\n--- ROAD: characters to the editor hwnd alone, no frame at all ---")
hin.post_key_combo(hwnd, "esc")
time.sleep(0.5)
bmx.invoke_node_safely(a1) if a1 else None
time.sleep(0.7)
for ch in "7":
    u.PostMessageW(hwnd, 0x0102, ord(ch), 1)
    time.sleep(0.2)
time.sleep(1.0)
ns3 = snap()
oncell3 = [n for n in ns3 if "edit" in str(n.ctype).lower() and a1
           and abs(n.rect[0] - a1.rect[0]) < 16 and abs(n.rect[1] - a1.rect[1]) < 16]
print("  editor:", [(str(n.name), n.rect) for n in oncell3])
if oncell3:
    ehh = int(getattr(oncell3[0].ctrl, "NativeWindowHandle", 0) or 0)
    print("  type via post_text:", hin.post_text(ehh, "123")[1])
    time.sleep(0.8)
    print("  editor text:", repr(hin.safe_window_text(ehh, 400)))
    hin.post_key_combo(ehh, "enter")
    time.sleep(1.4)
    print("  A1 value:", cell_values(["A1"]))
