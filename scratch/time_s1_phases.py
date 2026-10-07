"""Where does S1's 20 s actually go? Runs the SAME call S1 runs (budget_s=10) and prints the scan's own
phase report. Avoids parking the IDE window by picking another visible top-level window as the target."""
import sys, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import fast_scan

u32 = ctypes.windll.user32
found = []


@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(h, _l):
    if u32.IsWindowVisible(h) and u32.GetWindowTextLengthW(h) > 2:
        r = wt.RECT()
        u32.GetWindowRect(h, ctypes.byref(r))
        if (r.right - r.left) > 200 and (r.bottom - r.top) > 200:
            n = u32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, buf, n + 1)
            cls = ctypes.create_unicode_buffer(256)
            u32.GetClassNameW(h, cls, 256)
            found.append((int(h), buf.value, cls.value))
    return True


u32.EnumWindows(cb, 0)
target = next(((h, t, c) for h, t, c in found
               if not any(s in c.lower() or s in t.lower() for s in ("qoder", "chrome_qoderwidget"))), found[0])
print(f"target hwnd={target[0]} title={target[1]!r} class={target[2]!r}  "
      f"(of {len(found)} candidates; the first snapshot probe showed the walk itself costs ~0.5s)")

t = time.perf_counter()
out = fast_scan.deep_scan_legacy_shape("s1-target", target_hwnd=target[0], budget_s=10.0)
wall = time.perf_counter() - t
print(f"wall={wall:.2f}s  seconds={out.get('seconds')}  within_budget={out.get('within_budget')}")
print("phases     :", out.get("phases"))
print("static     :", out.get("static"))
print("knowledge_e0:", {k: v for k, v in (out.get("knowledge_e0") or {}).items() if k != "methods"})
print("e0         :", {k: v for k, v in (out.get("e0") or {}).items() if k not in ("methods", "commands")})
print("tree       :", out.get("tree"))
print("vision     :", out.get("vision"))
ts = out.get("tree_stats") or {}
print("tree_stats :", {k: ts.get(k) for k in ("nodes_walked", "walk_ms", "walk_rung", "stopped_by",
                                              "time_budget_ms", "time_budget_hit")})
