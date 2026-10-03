import cv2
import numpy as np
import urllib.request
import os
import time

def download_sample_image():
    filepath = "sample_trace.png"
    if not os.path.exists(filepath):
        print("Creating sample image...")
        # Create a simple image with a hollow square and a circle inside
        img = np.zeros((400, 400), dtype=np.uint8)
        # Outer boundary (hollow box)
        cv2.rectangle(img, (50, 50), (350, 350), 255, 3)
        # Inner boundary (circle)
        cv2.circle(img, (200, 200), 50, 255, 3)
        cv2.imwrite(filepath, img)
    return filepath

if __name__ == "__main__":
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), "All codes"))
    from core_organs.visual_cursor import VisualCursor
    
    img_path = download_sample_image()
    
    print("=" * 50)
    print("  TESTING HIERARCHICAL TRACING")
    print("=" * 50)
    
    vc = VisualCursor()
    
    # 1. Bring Paint to foreground
    print("\n[1] Finding Paint...")
    import win32gui
    import win32con
    hwnd = win32gui.FindWindow(None, "Untitled - Paint")
    if not hwnd:
        import subprocess
        print("  Paint not found. Launching...")
        subprocess.Popen("mspaint.exe")
        time.sleep(2)
        hwnd = win32gui.FindWindow(None, "Untitled - Paint")
        
    print(f"  Found: 'Untitled - Paint'  HWND={hex(hwnd)}")
    
    print("\n[2] Bringing Paint to foreground...")
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"  Warning: SetForegroundWindow failed: {e}")
    
    print("\n[3] Clearing canvas (Ctrl+A, Delete)...")
    import pyautogui
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pyautogui.press('delete')
    time.sleep(0.5)
    
    print("\n[4] Selecting Pencil using Keyboard Shortcuts (Alt, H, P)...")
    pyautogui.hotkey('alt')
    time.sleep(0.2)
    pyautogui.press('h')
    time.sleep(0.2)
    pyautogui.press('p')
    time.sleep(0.5)
    
    print(f"\n[5] Tracing image: {img_path}")
    vc.draw_shape(img_path, cx=900, cy=500, width=400, height=400)
    
    print("=" * 50)
    print("  TRACING COMPLETE")
    print("=" * 50)
