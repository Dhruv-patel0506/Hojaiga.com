import sys, time
sys.path.append("All codes")
from core_organs.visual_cursor import get_cursor

print("Initializing VisualCursor...")
vc = get_cursor()
vc.show()
time.sleep(1)
print(f"HWND: {vc._hwnd}, Running: {vc._running}, Visible: {vc._visible}, Pos: {vc.get_position()}")

# Test Bezier flight with label
print("Testing Bezier flight...")
vc.fly_to(500, 500, label="Nonagon Ready", duration=0.4)
time.sleep(0.5)

# Test drawing nonagon parametrically (physical=False for unit test)
print("Testing nonagon drawing points...")
vc.draw_shape("nonagon", 500, 500, width=200, height=200, steps=54, label="Nonagon", physical=False)
time.sleep(0.5)

print("Pos after drawing:", vc.get_position())
print("Test completed successfully with NO exceptions!")
vc.hide()
