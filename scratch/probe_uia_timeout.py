"""Read-only probe: does IUIAutomation6.TransactionTimeout actually bound ONE snapshot, and what does
the cheap control-view rung cost vs the raw-view one? Prints timings only - no window is changed."""
import sys, time, ctypes
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import fast_uia

u32 = ctypes.windll.user32
hwnd = int(u32.GetForegroundWindow() or 0)
b = ctypes.create_unicode_buffer(256)
u32.GetWindowTextW(hwnd, b, 256)
print(f"target hwnd={hwnd} title={b.value!r}")

# 1) can the timeout setter even get IUIAutomation6?
try:
    iua, core, _ = fast_uia._client()
    iua6 = iua.QueryInterface(core.IUIAutomation6)
    iua6.TransactionTimeout = 1500
    print(f"iua6 OK: TransactionTimeout reads back {iua6.TransactionTimeout}")
    iua6.TransactionTimeout = 12000
except Exception as exc:
    print(f"iua6 UNAVAILABLE -> _set_timeout is a silent no-op: {type(exc).__name__}: {exc}")

for label, ms, cheap in (("raw 1500ms", 1500, False),
                         ("raw 12000ms", 12000, False),
                         ("cheap 1500ms", 1500, True),
                         ("cheap 12000ms", 12000, True)):
    t = time.perf_counter()
    nodes = fast_uia.snapshot(hwnd, timeout_ms=ms, cheap=cheap) or []
    dt = time.perf_counter() - t
    depth = max((n.depth for n in nodes), default=0)
    print(f"{label:>14}: {dt:6.2f}s  nodes={len(nodes):6}  depth={depth}")
