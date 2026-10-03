"""Controlled canvas test: a Tk window whose ONLY change is a canvas rectangle recolor.
UIA/Win32 structure must stay identical while the pixel hash must move (and must NOT move
when nothing changes). Evidence -> grounding_reports/canvas_hash_controlled.json."""
import ctypes, json, os, sys, time, tkinter as tk
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.desktop_grounding import DesktopGrounding, DesktopVerifier  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "grounding_reports", "canvas_hash_controlled.json")
root = tk.Tk(); root.title("HojaigaCanvasProbe"); root.geometry("500x400+200+150")
cv = tk.Canvas(root, width=480, height=380, bg="white"); cv.pack()
rect = cv.create_rectangle(100, 100, 300, 250, fill="red")
root.attributes("-topmost", True)


def pump(n=15):
    for _ in range(n):
        root.update(); time.sleep(0.05)


pump(20)
g, v = DesktopGrounding(), DesktopVerifier()
hwnd = ctypes.windll.user32.FindWindowW(None, "HojaigaCanvasProbe")
els = g._walk_uia(hwnd) or g._walk_win32(hwnd)
s0 = v.snapshot(hwnd, els)
pump(10)
s_idle = v.snapshot(hwnd, g._walk_uia(hwnd) or g._walk_win32(hwnd))      # nothing changed
cv.itemconfigure(rect, fill="blue"); pump(15)                              # canvas-only change
els2 = g._walk_uia(hwnd) or g._walk_win32(hwnd)
s1 = v.snapshot(hwnd, els2)
res = {"hwnd": hwnd, "n_elements": len(els),
       "idle_pixel_changed": s0.region_hash != s_idle.region_hash,
       "idle_structure_changed": s0.signature() != s_idle.signature(),
       "canvas_change_pixel_changed": s0.region_hash != s1.region_hash,
       "canvas_change_structure_changed": s0.signature() != s1.signature(),
       "hashes": [s0.region_hash, s_idle.region_hash, s1.region_hash]}
json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2)
print(json.dumps(res, indent=2))
root.destroy()
