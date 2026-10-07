"""Where does a deep scan's time actually go? Timed, on the real foreground window, with no input at all.

S1 failed f6/h1/h2 with the SAME numbers (2776 nodes, 15.1-22.7 s against a 10 s budget) - so it is not a
flake and not GC. The one call in that path that can cost seconds is the UIA cache build; `_flatten` after
it is in-memory. This separates the two, and shows what a cheaper CacheRequest (control view, fewer
properties) buys, because that is the rung a budget-aware scanner has to fall back to.
"""
import ctypes
import os
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
os.environ.setdefault("PYTHONPATH", r"D:\new_automation;D:\new_automation\All codes")

u = ctypes.windll.user32
hwnd = int(u.GetForegroundWindow() or 0)
buf = ctypes.create_unicode_buffer(200)
u.GetWindowTextW(hwnd, buf, 200)
cls = ctypes.create_unicode_buffer(120)
u.GetClassNameW(hwnd, cls, 120)
print(f"target hwnd={hwnd} class={cls.value!r} title={buf.value!r}")

from core_organs import fast_uia as fu   # noqa: E402

for label, kw in (("raw view, full props (what the scan uses)", {}),):
    t = time.perf_counter()
    try:
        iua, core, _ = fu._client()
        fu._set_timeout(30000)
        t_build = time.perf_counter()
        root = iua.ElementFromHandleBuildCache(hwnd, fu._request())
        after_build = time.perf_counter() - t_build
        nodes = fu._flatten(root, 20000)
    except Exception as exc:
        print(f"{label}: FAILED {type(exc).__name__}: {exc}")
        continue
    total = time.perf_counter() - t
    print(f"{label}: cache_build={after_build:.2f}s flatten={total - after_build:.2f}s "
          f"total={total:.2f}s nodes={len(nodes)}")

# what the UIA timeout actually caps: ask for the same tree with a short transaction timeout
for ms in (3000, 6000):
    t = time.perf_counter()
    els = fu.snapshot(hwnd, timeout_ms=ms)
    print(f"snapshot(timeout_ms={ms}) -> {len(els) if els else None} nodes in {time.perf_counter()-t:.2f}s")

# is the tree still being produced within the scan's own budget? time the product call end to end
from core_organs import fast_scan as fs   # noqa: E402

t = time.perf_counter()
rep = fs.deep_scan_legacy_shape("s1-target", target_hwnd=hwnd, budget_s=10.0)
ts = rep.get("tree_stats", {})
print(f"deep_scan_legacy_shape: {time.perf_counter()-t:.2f}s nodes={ts.get('nodes_walked')} "
      f"within_budget={rep.get('within_budget')} phases={rep.get('phases')} "
      f"knowledge_e0={ {k: v for k, v in (rep.get('knowledge_e0') or {}).items() if k != 'methods'} }")
