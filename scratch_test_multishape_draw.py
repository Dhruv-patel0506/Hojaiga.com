import os
import sys
import time
import ctypes

sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_01_crewai_engine import (
    _ensure_interactive_desktop,
    draw_shape_tool,
    launch_app_tool,
    scan_app_tool,
    _extract_all_drawing_shapes
)

_ensure_interactive_desktop()

cmd = "draw in paint the follwing shapes: rectangle, circle, squre, parallelogram, trapezium in one page only so adjuxt the sizes accrodingly!"
shapes = _extract_all_drawing_shapes(cmd)
print("Extracted shapes:", shapes)

# 1. Launch/focus paint
launch_res = launch_app_tool.run(app_name="paint")
print("Launch res:", launch_res)
time.sleep(1.0)

# 2. Clear canvas with Ctrl+A, Delete for a clean white sheet
user32 = ctypes.windll.user32
user32.keybd_event(0x11, 0, 0, 0) # Ctrl down
user32.keybd_event(0x41, 0, 0, 0) # A down
time.sleep(0.05)
user32.keybd_event(0x41, 0, 2, 0) # A up
user32.keybd_event(0x11, 0, 2, 0) # Ctrl up
time.sleep(0.1)
user32.keybd_event(0x2E, 0, 0, 0) # Delete down
time.sleep(0.05)
user32.keybd_event(0x2E, 0, 2, 0) # Delete up
time.sleep(0.3)
print("Canvas cleared with Ctrl+A, Delete")

# 3. Draw all 5 shapes across the single page
shapes_str = ", ".join(shapes)
print(f"Calling draw_shape_tool with: '{shapes_str}'")
t0 = time.time()
draw_res = draw_shape_tool.run(shape=shapes_str, tool_name="pencil")
print(f"Draw completed in {time.time() - t0:.2f}s: {draw_res}")

# 4. Capture screenshot proof
time.sleep(1.0)
from PIL import ImageGrab
im = ImageGrab.grab()
proof_path = r"C:\Users\dhruv\.gemini\antigravity-ide\brain\96f3e7c2-9e2e-4858-9056-491a84fb8130\multishape_paint_proof.png"
im.save(proof_path)
print("Saved proof screenshot to:", proof_path)
