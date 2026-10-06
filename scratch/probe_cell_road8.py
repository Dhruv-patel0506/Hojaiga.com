"""Probe 8: which HWND the grid actually reads its keyboard from, while the window stays in the background.

Probe 2 (accidentally) produced an EditControl named 'Edit Cell' sitting exactly on A1's rect, right after raw
WM_CHARs were posted to the TOP-LEVEL window - never reproduced when the same keys went to the grid's child
(EXCEL7) in probe 7. So the target of the keystrokes, not the keys, is the open question. Every road below is
judged by two witnesses that cannot lie: the 'Edit Cell' edit on the cell's own rect, and the formula bar text.
"""
import ctypes
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

u = ctypes.windll.user32
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


def witnesses(tag, tre):
    ns = snap()
    out = [f"{tag}:"]
    fb = next((n for n in ns if str(n.aid) == "FormulaBar"), None)
    fv = ""
    if fb is not None:
        try:
            fv = str(fb.ctrl.GetValuePattern().Value or "")
        except Exception:
            fv = hin.safe_window_text(int(fb.ctrl.NativeWindowHandle or 0))
    out.append(f"    formula bar = {fv[:40]!r}")
    oncell = [n for n in ns if "edit" in str(n.ctype).lower()
              and abs(n.rect[0] - tre[0]) < 14 and abs(n.rect[1] - tre[1]) < 14]
    out.append(f"    edit on the cell = {[(str(n.name), n.rect) for n in oncell]}")
    vals = [(str(n.name), n.rect) for n in body(ns) if str(n.name) and not REF_RE.match(str(n.name).strip().upper())]
    out.append(f"    cells with a non-reference name = {vals[:6]}")
    sel = [str(n.name) for n in body(ns) if n.selected]
    out.append(f"    selected = {sel[:4]}")
    print("\n".join(out))
    return ns, oncell


def esc_all():
    for h in (hwnd, hin.child_at(hwnd, 600, 600)):
        if h:
            hin.post_key_combo(h, "esc")
            time.sleep(0.3)


a1 = (43, 295, 123, 319)
esc_all()
witnesses("clean start", a1)
print("\nkeyboard windows: top-level", hwnd, hin._class_name(hwnd), "| under grid",
      hin.child_at(hwnd, 600, 600), hin._class_name(hin.child_at(hwnd, 600, 600)))

ROADS = [
    ("1 raw WM_CHAR to the TOP-LEVEL (probe 2's accident)", "top", None, "42"),
    ("2 select then raw WM_CHAR to the TOP-LEVEL", "top", "select", "7"),
    ("3 F2 to top-level, then chars to top-level", "top", "f2", "13"),
    ("4 chars to the focused control after selecting", "focus", "select", "99"),
    ("5 chars to the grid child window", "grid", "select", "5"),
]
for label, sink, pre, payload in ROADS:
    print(f"\n=== ROAD {label} (payload {payload!r}) ===")
    esc_all()
    ns = snap()
    bd = body(ns)
    cell = next((n for n in bd if n.rect == a1), None) or next(
        (n for n in bd if str(n.name).strip().upper() == "A1"), None)
    if cell is None:
        print("  A1 gone; visible cells:", [(str(n.name), n.rect) for n in bd[:4]])
        continue
    tre = cell.rect
    if pre == "select":
        print("  select:", bmx.invoke_node_safely(cell))
        time.sleep(0.8)
    target = {"top": hwnd, "grid": hin.child_at(hwnd, 600, 600)}.get(sink) or hwnd
    if pre == "f2":
        print("  F2 ->", hin.post_key_combo(target, "f2")[1])
        time.sleep(0.8)
        target = hin.focused_control(hwnd) or target
        print("  keys now go to", target, hin._class_name(target))
    if sink == "focus":
        target = hin.focused_control(hwnd) or hwnd
        print("  focused:", target, hin._class_name(target))
    print("  post_text ->", hin.post_text(target, payload)[1])
    time.sleep(1.2)
    witnesses(f"  after ROAD {label[:1]}", tre)
    print("  Enter ->", hin.post_key_combo(target, "enter")[1])
    time.sleep(1.2)
    witnesses(f"  after ROAD {label[:1]} commit", tre)

esc_all()
print("\nfinal:")
witnesses("  end", a1)
