"""Probe 10: two things probes 8-9 left untested.

(1) Probe 8 only posted WM_CHAR. A grid that runs its own keyboard translation reads WM_KEYDOWN, not WM_CHAR.
    So: post real key-down/up pairs for the digits, to each candidate window of the process.
(2) Probe 9's pattern calls all failed on the CALLER's side ('NoneType has no SetValue'), not the app's: UIA
    patterns must be asked from an apartment-initialised thread, the way organ_48 does for Invoke.
Witness, both times: does the payload appear as the text of ANY window of the process, or as a cell name that
is no longer a cell reference. No screenshots, no assumptions.
"""
import ctypes
import os
import re
import sys
import threading
import time

os.environ.setdefault("PYTHONPATH", r"D:\new_automation;D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes")

import uiautomation as auto                                             # noqa: E402
from core_organs import fast_uia as fu                                  # noqa: E402
from core_organs import headless_input as hin                           # noqa: E402
from core_organs.desktop_grounding import DesktopGrounding              # noqa: E402

g = DesktopGrounding()
_h = g.find_window("excel")
if not _h:
    print("no excel window")
    sys.exit(2)
hwnd = int(_h)
REF_RE = re.compile(r"^[A-Z]{1,3}[0-9]{1,7}$")
u = ctypes.windll.user32


def snap():
    return fu.snapshot(hwnd, timeout_ms=8000) or []


def every_window_text(top):
    hits = []
    stack = [top]
    while stack:
        h = stack.pop()
        for nxt in (u.GetWindow(h, 5), u.GetWindow(h, 2)):   # child, then sibling
            if nxt:
                stack.append(int(nxt))
        t = hin.safe_window_text(int(h), timeout_ms=120)
        if t:
            hits.append((hin._class_name(int(h)), t[:40]))
    return hits


def payload_visible(payload):
    ns = snap()
    gl = next((n for n in ns if str(n.ctype) == "DataGridControl"), None)
    cells_hit = []
    if gl:
        for n in ns:
            if str(n.ctype) == "DataItemControl" and "Header" not in str(n.cls) and gl.rect[1] < n.rect[1] < gl.rect[3]:
                if str(n.name).strip() and not REF_RE.match(str(n.name).strip().upper()):
                    cells_hit.append((str(n.name), n.rect))
    txt_hit = [(c, t) for c, t in every_window_text(hwnd) if payload in t]
    return cells_hit, txt_hit


def body_cells(ns):
    gl = next((n for n in ns if str(n.ctype) == "DataGridControl"), None)
    if not gl:
        return []
    return [n for n in ns if str(n.ctype) == "DataItemControl" and "Header" not in str(n.cls)
            and gl.rect[1] + 2 < n.rect[1] < gl.rect[3]]


# ---------------------------------------------------------------- (1) key pairs
grid_child = hin.child_at(hwnd, 600, 600)
targets = {"XLMAIN(top)": hwnd, "grid child": grid_child}
print("windows:", {k: (v, hin._class_name(v)) for k, v in targets.items()})

for label, hwnd_t in targets.items():
    payload = "42" if label.startswith("XL") else "57"
    print(f"\n### key-down/up pairs of {payload!r} to {label} ({hin._class_name(hwnd_t)})")
    for ch in payload:
        vk = ord(ch)
        print(f"  {ch}: ", hin.post_vk_chord(hwnd_t, [vk], label=f"vk-{ch}")[1])
        time.sleep(0.35)
    time.sleep(1.2)
    print("  visible:", payload_visible(payload))
    hin.post_key_combo(hwnd_t, "enter")
    time.sleep(1.2)
    print("  after Enter:", payload_visible(payload))

# ------------------------------------------------------- (2) patterns on a thread
def uia_write(ref, value, which):
    """Resolve the cell by name in a FRESH tree on an initialised thread, then try one pattern."""
    res = {}

    def _w():
        with auto.UIAutomationInitializerInThread():
            try:
                root = auto.ControlFromHandle(hwnd)
                found = None
                stack = [root]
                while stack and found is None:
                    c = stack.pop()
                    try:
                        if (c.ControlTypeName or "") == "DataItemControl" and (c.Name or "").strip().upper() == ref.upper():
                            found = c
                            break
                        stack.extend(c.GetChildren())
                    except Exception:
                        continue
                if found is None:
                    res["err"] = "cell not found on thread"
                    return
                res["rect"] = (found.BoundingRectangle.left, found.BoundingRectangle.top,
                               found.BoundingRectangle.right, found.BoundingRectangle.bottom)
                if which in ("value", "both"):
                    vp = found.GetValuePattern()
                    res["value_pattern"] = "None" if vp is None else "present"
                    if vp is not None:
                        vp.SetValue(value)
                        res["value_write"] = "dispatched"
                if which in ("legacy", "both"):
                    lp = found.GetLegacyIAccessiblePattern()
                    res["legacy_pattern"] = "None" if lp is None else "present"
                    if lp is not None:
                        try:
                            lp.SetValue(value)
                            res["legacy_write"] = "dispatched"
                        except Exception as exc:
                            res["legacy_write"] = f"{type(exc).__name__}:{str(exc)[:50]}"
                try:
                    res["name_after"] = (found.Name or "")[:20]
                except Exception:
                    pass
            except Exception as exc:
                res["err"] = f"{type(exc).__name__}:{str(exc)[:80]}"

    t = threading.Thread(target=_w, daemon=True)
    t.start()
    t.join(15)
    print("  live-UIA", which, "->", res)
    time.sleep(1.2)
    print("  visible:", payload_visible(value))


print("\n### live-tree UIA writes (apartment-initialised thread)")
uia_write("B2", "777", "value")
uia_write("B2", "777", "legacy")
uia_write("C3", "333", "both")

print("\n### and the mirror surface, written live")


def uia_formula_bar(value):
    res = {}

    def _w():
        with auto.UIAutomationInitializerInThread():
            try:
                root = auto.ControlFromHandle(hwnd)
                stack, fb = [root], None
                while stack and fb is None:
                    c = stack.pop()
                    try:
                        if (c.AutomationId or "") == "FormulaBar" or "formula" in (c.Name or "").lower():
                            fb = c
                            break
                        stack.extend(c.GetChildren())
                    except Exception:
                        continue
                if fb is None:
                    res["err"] = "no mirror surface found"
                    return
                vp = fb.GetValuePattern()
                res["pattern"] = "None" if vp is None else "readable=" + repr(str(vp.Value)[:20])
                if vp is not None:
                    vp.SetValue(value)
                    res["write"] = "dispatched"
            except Exception as exc:
                res["err"] = f"{type(exc).__name__}:{str(exc)[:80]}"
    t = threading.Thread(target=_w, daemon=True)
    t.start()
    t.join(15)
    print("  mirror ->", res)
    time.sleep(1.2)
    print("  visible:", payload_visible(value))


uia_formula_bar("4242")
