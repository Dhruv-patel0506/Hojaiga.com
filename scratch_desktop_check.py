import ctypes
import win32gui
import uiautomation as auto

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
err = kernel32.GetLastError()
print(f"OpenInputDesktop: hdesk={hdesk}, err={err}")

if hdesk:
    set_res = user32.SetThreadDesktop(hdesk)
    err = kernel32.GetLastError()
    print(f"SetThreadDesktop: res={set_res}, err={err}")

res = user32.SetCursorPos(500, 500)
err = kernel32.GetLastError()
print(f"SetCursorPos(500, 500): res={res}, err={err}")

# Check uiautomation click or SendInput
print("Testing SendInput with MOUSEEVENTF_ABSOLUTE...")
# Let's test auto.Click or SendInput
try:
    auto.Click(500, 500)
    print("auto.Click(500, 500) completed without error")
except Exception as e:
    print("auto.Click error:", e)

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
pt = POINT()
user32.GetCursorPos(ctypes.byref(pt))
print(f"Cursor pos after auto.Click: ({pt.x}, {pt.y})")
