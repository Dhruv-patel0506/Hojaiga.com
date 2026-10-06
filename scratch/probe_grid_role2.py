"""Probe 2: leave the start screen headlessly, then ask what the WORKSHEET is in UIA terms.

Two questions, both measured rather than assumed:
  1. Can a background-parked app be moved off its start screen by pressing the control the app ITSELF
     labels as creating a document (no app names, no physical cursor)?
  2. Once a document is open, which UIA node is the writable surface a typed payload belongs to, and does
     it appear to the grounder as an 'edit' at all?
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
print("excel hwnd:", hwnd)
if not hwnd:
    sys.exit(2)
hwnd = int(hwnd)


def dump(tag, min_area=30000):
    nodes = fu.snapshot(hwnd, timeout_ms=8000) or []
    print(f"\n===== {tag}: {len(nodes)} nodes; over {min_area}px =====")
    for n in nodes:
        l, t, r, b = n.rect
        a = abs(r - l) * abs(b - t)
        if a >= min_area:
            print(f"  area={a:>9} ctype={str(n.ctype):<20} name={str(n.name)[:34]!r:<38} "
                  f"aid={str(n.aid)[:26]!r:<28} cls={str(n.cls)[:16]!r} pats={n.pats}")
    kinds = {}
    for n in nodes:
        kinds[str(n.ctype)] = kinds.get(str(n.ctype), 0) + 1
    print("  kinds:", sorted(kinds.items(), key=lambda x: -x[1]))
    return nodes


dump("BEFORE (start screen)")

# 1. press the control whose own name says 'create a new document' - a data table of UI words, not an app
NEW_DOC_WORDS = ("blank", "new ", "create", "empty")
nodes = fu.snapshot(hwnd, timeout_ms=8000) or []
cand = [n for n in nodes if n.enabled and any(w in (n.name or "").lower() for w in NEW_DOC_WORDS)
        and (n.name or "").strip()]
print("\nnew-document candidates:", [(str(n.ctype), str(n.name)[:30]) for n in cand][:8])
pressed = None
for n in cand:
    if "invoke" in n.pats or "select" in n.pats:
        ok, note = bmx.invoke_node_safely(n)
        pressed = (str(n.name), ok, note)
        print("pressed:", pressed)
        if ok:
            break
time.sleep(6.0)
after = dump("AFTER press", min_area=30000)
print("\nstart screen gone?", not any((str(n.name).lower().find("backstage") >= 0) for n in after))

# 2. if still on the start screen, the generic 'new document' accelerator, posted headlessly
if any("backstage" in str(n.name).lower() for n in after):
    print("posting Ctrl+N to", hwnd, "->", hin.post_key_combo(hwnd, "ctrl+n"))
    time.sleep(7.0)
    after = dump("AFTER Ctrl+N", min_area=30000)

# 3. what is the grid, and does typed text land in it?
grid = [n for n in after if str(n.ctype).lower() in ("tablecontrol", "datagridcontrol", "dataitemcontrol")
        or abs(n.rect[2] - n.rect[0]) * abs(n.rect[3] - n.rect[1]) > 200000]
print("\nbig/grid nodes:", [(str(n.ctype), str(n.name)[:26], n.rect) for n in grid][:10])

for n in after:
    l, t, r, b = n.rect
    if (r - l) * (b - t) > 200000 and "edit" not in str(n.ctype).lower():
        target = n
        print("\nwidest surface:", str(target.ctype), repr(str(target.name))[:40], target.rect, target.pats)
        break
else:
    target = None

if target is not None:
    th = int(getattr(target, "hwnd", 0) or 0) or hwnd
    print("typing '42' via post_key char to", th)
    for ch in "42":
        ctypes.windll.user32.PostMessageW(th, 0x0102, ord(ch), 1)
    time.sleep(1.5)
    re_snap = fu.snapshot(hwnd, timeout_ms=8000) or []
    vals = [(str(n.ctype), str(n.name)[:30], str(n.aid)[:20]) for n in re_snap
            if "42" in str(n.name or "") or "42" in str(getattr(n, "help", "") or "")]
    print("nodes now containing '42':", vals[:10])
    edits = [(str(n.ctype), str(n.name)[:30], n.rect) for n in re_snap if "edit" in str(n.ctype).lower()]
    print("edits:", edits[:8])
