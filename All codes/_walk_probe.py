"""Temporary probe: compare uiautomation.WalkControl vs manual GetChildren walk."""
import sys, time
sys.path.insert(0, r"D:\new_automation\All codes")

import uiautomation as auto
import win32gui

auto.SetGlobalSearchTimeout(1.0)
auto.InitializeUIAutomationInCurrentThread()

hwnd = win32gui.GetForegroundWindow()
print("Foreground:", win32gui.GetWindowText(hwnd), hwnd)
ctrl = auto.ControlFromHandle(hwnd)
print("ctrl:", ctrl)

# --- Native walker ---
t0 = time.perf_counter()
n_native, d_native = 0, 0
try:
    for c, d in auto.WalkControl(ctrl, includeTop=False, maxDepth=32):
        n_native += 1
        d_native = max(d_native, d)
except Exception as e:
    print("native error:", type(e).__name__, e)
t_native = time.perf_counter() - t0

# --- Manual walker (current organ_30 fallback style) ---
def manual(c, depth=0, max_d=32):
    if depth > max_d:
        return
    try:
        for ch in c.GetChildren():
            yield (ch, depth)
            yield from manual(ch, depth + 1, max_d)
    except Exception:
        return

t0 = time.perf_counter()
n_manual, d_manual = 0, 0
for c, d in manual(ctrl):
    n_manual += 1
    d_manual = max(d_manual, d)
t_manual = time.perf_counter() - t0

print(f"native : {n_native:5d} nodes  max_depth={d_native:<3d} time={t_native*1000:.0f} ms")
print(f"manual : {n_manual:5d} nodes  max_depth={d_manual:<3d} time={t_manual*1000:.0f} ms")

# --- Organ-30's current broken wrapper (times the RecursionError waste) ---
import logging
logging.disable(logging.CRITICAL)
from core_organs.organ_30_app_scanner import _safe_walk_control
t0 = time.perf_counter()
n_wrap, d_wrap = 0, 0
for c, d in _safe_walk_control(ctrl, includeTop=False, maxDepth=32):
    n_wrap += 1
    d_wrap = max(d_wrap, d)
t_wrap = time.perf_counter() - t0
print(f"wrapper: {n_wrap:5d} nodes  max_depth={d_wrap:<3d} time={t_wrap*1000:.0f} ms")

auto.UninitializeUIAutomationInCurrentThread()
