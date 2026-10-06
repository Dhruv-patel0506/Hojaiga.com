"""Probe 11: the last unread road - the mirror surface exposes a TEXT pattern, not a value pattern.

Measured: the formula-bar control carries pats=['text'] and its ValuePattern came back None on a live thread,
so probe 10's 'SetValue dispatched' was no such thing for it. A TextPattern range write is a different call and
the one headless road not yet tried. Judge it the same way: does the selected cell change, and does the payload
show up anywhere in the process.
"""
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
from core_organs import organ_48_app_behavior_model as bmx              # noqa: E402
from core_organs.desktop_grounding import DesktopGrounding              # noqa: E402

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


def payload_visible(payload):
    ns = snap()
    cells = [(str(n.name), n.rect) for n in body(ns)
             if str(n.name).strip() and not REF_RE.match(str(n.name).strip().upper())]
    sel = [str(n.name) for n in body(ns) if n.selected]
    return {"cells_with_content": cells[:6], "selected": sel[:3], "window_texts": payload in
            " | ".join(hin.safe_window_text(w, 120) or "" for w, _t in hin.process_windows(hwnd))}


print("state:", hin.window_state(hwnd), "foreground:",
      hin._u32.GetForegroundWindow())

ns = snap()
fbn = [n for n in ns if "edit" in str(n.ctype).lower() and (n.rect[2] - n.rect[0]) > 300]
print("mirror edits:", [(str(n.name), n.rect, n.pats) for n in fbn])


def text_write(value):
    res = {}

    def _w():
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(hwnd)
            stack, hit = [root], []
            while stack:
                c = stack.pop()
                try:
                    if (c.ControlTypeName or "").lower().startswith("edit"):
                        hit.append(c)
                    stack.extend(c.GetChildren())
                except Exception:
                    continue
            res["edits"] = [((x.Name or "")[:18], tuple(map(int, (x.BoundingRectangle.left,
                              x.BoundingRectangle.top, x.BoundingRectangle.right, x.BoundingRectangle.bottom))))
                            for x in hit]
            for x in hit:
                w = x.BoundingRectangle.right - x.BoundingRectangle.left
                if w < 300:
                    continue
                try:
                    tp = x.GetTextPattern()
                except Exception as exc:
                    res.setdefault("errors", []).append(f"{(x.Name or '')[:12]}:GetTextPattern {type(exc).__name__}")
                    continue
                if tp is None:
                    res.setdefault("errors", []).append(f"{(x.Name or '')[:12]}:no text pattern")
                    continue
                try:
                    dr = tp.DocumentRange
                    dr.SetText(value)
                    res["settext"] = f"on {(x.Name or '')[:14]!r}"
                    time.sleep(0.6)
                    res["read_back"] = (tp.DocumentRange.GetText(-1) or "")[:30]
                except Exception as exc:
                    res.setdefault("errors", []).append(f"SetText {type(exc).__name__}:{str(exc)[:60]}")
    t = threading.Thread(target=_w, daemon=True)
    t.start()
    t.join(20)
    print("  live TextPattern ->", res)
    time.sleep(1.2)
    print("  visible:", payload_visible(value))


print("\n--- pick A1 by UIA select, then write through the mirror's text pattern ---")
ns = snap()
a1 = next((n for n in body(ns) if str(n.name).strip().upper() == "A1"), None)
if a1 is not None:
    print("  select:", bmx.invoke_node_safely(a1))
    time.sleep(0.8)
text_write("42")

print("\n--- commit what the mirror now holds ---")
for attempt in ("enter-mirror-edit", "enter-child"):
    ns = snap()
    e = [n for n in ns if "edit" in str(n.ctype).lower() and (n.rect[2] - n.rect[0]) > 300]
    for n in e:
        nh = int(getattr(n.ctrl, "NativeWindowHandle", 0) or 0)
        if nh:
            print(f"  Enter to {nh} ({hin._class_name(nh)}):", hin.post_key_combo(nh, "enter")[1])
    if attempt == "enter-mirror-edit":
        time.sleep(1.2)
        print("  visible:", payload_visible("42"))
