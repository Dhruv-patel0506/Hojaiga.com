"""Prove the two primitives before wiring them: UIA gives us each node's process, and rebased() keeps parent links inside their own window."""
import sys

sys.path.insert(0, r"d:\new_automation\All codes")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core_organs import fast_uia as FU, headless_input as hin

# 1. pid on a real tree
import ctypes
import ctypes.wintypes as wt
u = ctypes.windll.user32
u.GetWindowLongW.restype = ctypes.c_long
found = []
PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


def cb(h, _l):
    try:
        if not u.IsWindowVisible(h):
            return True
        owner = u.GetWindowLongW(h, -8)            # GW_OWNER: an owned tool window is not a frame of its own
        t = u.GetWindowTextLengthW(h)
        if t > 8 and not owner:
            found.append(int(h))
    except Exception as exc:
        print("cb", type(exc).__name__, exc)
    return True


u.EnumWindows(PROC(cb), 0)
print(f"{len(found)} visible top-levels")
for h in found[:6]:
    buf = ctypes.create_unicode_buffer(300)
    u.GetWindowTextW(h, buf, 300)
    nodes = FU.snapshot(h, max_nodes=400, timeout_ms=4000)
    if not nodes:
        print(f"  hwnd {h} '{buf.value[:50]}': no tree")
        continue
    pids = {}
    for n in nodes:
        pids[int(getattr(n, "pid", 0) or 0)] = pids.get(int(getattr(n, "pid", 0) or 0), 0) + 1
    print(f"  hwnd {h} pid={hin.window_pid(h)} '{buf.value[:44]}' nodes={len(nodes)} pids={pids}")

# 2. rebased(): parent links stay inside the part
if len(found) > 1:
    a = FU.snapshot(found[0], max_nodes=200, timeout_ms=3000) or []
    b = FU.snapshot(found[1], max_nodes=200, timeout_ms=3000) or []
else:
    a = b = []
if a and b:
    bb = FU.rebased(b, len(a))
    merged = a + bb
    # every link of the appended part must land on a COPY of its own window's node
    wrong = 0
    for i, o in enumerate(b):
        c = bb[i]
        if c.idx != len(a) + o.idx:
            wrong += 1
        if o.parent >= 0 and (c.parent != len(a) + o.parent or merged[c.parent].name != b[o.parent].name):
            wrong += 1
        for ch_o, ch_c in zip(o.children, c.children):
            if ch_c != len(a) + ch_o or merged[ch_c].name != b[ch_o].name:
                wrong += 1
    crossed = sum(1 for n in bb if n.parent < len(a) and n.parent >= 0)
    raw_crossed = sum(1 for n in b if n.parent >= len(a))          # what a plain merge would point OUT of the window
    print(f"\nrebased: {len(bb)} copies, {wrong} broken index/parent/child links, {crossed} links reaching into the first window")
    print(f"plain merge (no rebase): {raw_crossed} of {len(b)} nodes had a parent index beyond their own window")
    print(f"names kept: {bb[0].name == b[0].name}, element shared: {bb[0].el is b[0].el}, originals untouched: {b[0].idx == 0}")
