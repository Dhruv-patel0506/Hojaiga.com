"""Scoped canvas pre-test (stand-in for Blender, which is not installed): does the 64x64
pixel-hash verifier detect a canvas-only change that the UIA structure cannot see?
Saves before/after evidence to benchmarks/grounding_reports/canvas_hash_pretest.json."""
import json, os, sys, time
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.desktop_grounding import DesktopGrounding, DesktopVerifier  # noqa: E402
from core_organs import headless_input as hin  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "grounding_reports", "canvas_hash_pretest.json")
g, v = DesktopGrounding(), DesktopVerifier()
hwnd, els, rep = g.ground("Paint")
assert hwnd, "Paint window not found"
import ctypes, ctypes.wintypes as wt
r = wt.RECT(); ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
cx0, cy0 = r.left + (r.right - r.left) // 3, r.top + (r.bottom - r.top) // 2
before = v.snapshot(hwnd, els)
for i in range(120):  # a horizontal stroke of posted clicks across the canvas
    hin.post_click(hwnd, cx0 + i * 4, cy0 + (i % 7))
    time.sleep(0.01)
time.sleep(0.8)
els2 = g._walk_uia(hwnd)
after = v.snapshot(hwnd, els2)
res = {"app": "Paint (canvas stand-in; Blender not installed)",
       "before": {"sig": before.signature(), "region_hash": before.region_hash, "n_elements": len(els)},
       "after": {"sig": after.signature(), "region_hash": after.region_hash, "n_elements": len(els2)},
       "structure_sig_changed": before.signature() != after.signature(),
       "pixel_hash_changed": before.region_hash != after.region_hash,
       "ids_same": sorted(e.id for e in els) == sorted(e.id for e in els2)}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(res, f, indent=2)
print(json.dumps(res, indent=2))
