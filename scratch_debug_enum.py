import ctypes
user32 = ctypes.windll.user32
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk:
    user32.SetThreadDesktop(hdesk)

import win32gui
import traceback

def enum(hwnd, _):
    try:
        title = win32gui.GetWindowText(hwnd)
        if "obs" in title.lower():
            print(f"Enum found: hwnd={hwnd} title='{title}' vis={win32gui.IsWindowVisible(hwnd)}")
    except Exception as e:
        print("Error in callback:", e)
    return True

try:
    win32gui.EnumWindows(enum, None)
    print("EnumWindows completed successfully.")
except Exception:
    traceback.print_exc()
