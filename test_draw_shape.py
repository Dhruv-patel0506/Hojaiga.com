"""
Dynamic Drawing Test — FIXED TOOL SELECTION.
Uses keyboard shortcuts (Alt+H -> P) to ensure Pencil is selected.

Usage:
  python test_draw_shape.py hexagon
  python test_draw_shape.py "a futuristic spaceship"
"""
import sys
import time
import os
import ctypes

sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation")

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

user32 = ctypes.windll.user32

from core_organs.visual_cursor import VisualCursor

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT_UNION)]

def send_key(vk, down=True):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp._input.ki.wVk = vk
    inp._input.ki.wScan = 0
    inp._input.ki.dwFlags = 0 if down else KEYEVENTF_KEYUP
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

def send_mouse(x, y, flags):
    screen_w, screen_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp._input.mi.dx = int(x * 65535 / screen_w)
    inp._input.mi.dy = int(y * 65535 / screen_h)
    inp._input.mi.dwFlags = flags | MOUSEEVENTF_ABSOLUTE
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

def force_foreground(hwnd):
    import win32gui, win32con
    send_key(0x12, down=True)  # Alt
    time.sleep(0.02)
    send_key(0x12, down=False)
    time.sleep(0.05)
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    time.sleep(0.5)

if __name__ == "__main__":
    shape_name = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "hexagon"
    print(f"\n[1] Drawing: {shape_name}")

    from core_organs.organ_01_crewai_engine import _ensure_interactive_desktop
    _ensure_interactive_desktop()

    import win32gui, subprocess
    hwnds = []
    def find_paint(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = (win32gui.GetWindowText(hwnd) or "").lower()
        cls = (win32gui.GetClassName(hwnd) or "").lower()
        if any(bad in title for bad in ["antigravity", "visual studio", "code -", "chrome", "edge", "terminal", "powershell"]):
            return True
        if "paint" in title or "paint" in cls:
            hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(find_paint, None)

    if not hwnds:
        print("  Paint not found! Launching via cmd start mspaint.exe...")
        subprocess.Popen(["cmd.exe", "/c", "start", "mspaint.exe"])
        time.sleep(3.5)
        win32gui.EnumWindows(find_paint, None)
    
    if not hwnds:
        print("Fail: Could not find or launch MS Paint window.")
        sys.exit(1)


    paint_hwnd = hwnds[0]
    force_foreground(paint_hwnd)

    print("[2] Clearing canvas...")
    send_key(0x11, True) # Ctrl
    send_key(0x41, True); time.sleep(0.05); send_key(0x41, False) # A
    send_key(0x11, False)
    time.sleep(0.1)
    send_key(0x2E, True); time.sleep(0.05); send_key(0x2E, False) # Delete
    time.sleep(0.3)
    # Press Escape to deselect marquee
    send_key(0x1B, True); time.sleep(0.05); send_key(0x1B, False)
    time.sleep(0.1)

    print("[3] Selecting Pencil using Keyboard Shortcuts (Alt, H, P)...")
    # Windows 11 Paint: Alt -> H -> P selects the pencil
    send_key(0x12, True); time.sleep(0.05); send_key(0x12, False) # Alt
    time.sleep(0.2)
    send_key(0x48, True); time.sleep(0.05); send_key(0x48, False) # H
    time.sleep(0.2)
    send_key(0x50, True); time.sleep(0.05); send_key(0x50, False) # P
    time.sleep(0.2)
    send_key(0x1B, True); time.sleep(0.05); send_key(0x1B, False)
    time.sleep(0.1)

    rect = win32gui.GetWindowRect(paint_hwnd)
    canvas_cx, canvas_cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2 + 50
    draw_size = 500

    print("[4] Ensuring canvas focus...")
    send_mouse(canvas_cx, canvas_cy, MOUSEEVENTF_MOVE)
    time.sleep(0.1)
    send_mouse(canvas_cx, canvas_cy, MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.1)
    send_mouse(canvas_cx, canvas_cy, MOUSEEVENTF_LEFTUP)
    time.sleep(0.2)

    print(f"\n[5] Drawing '{shape_name}' with Qwen2.5:3b...")
    vc = VisualCursor()
    vc.show()
    time.sleep(0.5)
    
    vc.draw_shape(shape_name, canvas_cx, canvas_cy, width=draw_size, height=draw_size, steps=60)
    
    time.sleep(2)
    vc.hide()
    print("Done!")
