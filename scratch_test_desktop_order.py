import ctypes
import sys
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

print("=== TEST 1: Before any COM / GUI imports ===")
hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
print("OpenInputDesktop:", hdesk, "err:", kernel32.GetLastError())
if hdesk:
    res = user32.SetThreadDesktop(hdesk)
    print("SetThreadDesktop:", res, "err:", kernel32.GetLastError())

res_pos = user32.SetCursorPos(500, 500)
print("SetCursorPos(500, 500):", res_pos, "err:", kernel32.GetLastError())

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
pt = POINT()
user32.GetCursorPos(ctypes.byref(pt))
print("Cursor pos:", (pt.x, pt.y))

fg = user32.GetForegroundWindow()
print("Foreground window:", fg)

print("\n=== NOW IMPORTING uiautomation ===")
import uiautomation as auto
print("Imported uiautomation.")

res_pos2 = user32.SetCursorPos(600, 600)
print("SetCursorPos(600, 600) after import:", res_pos2, "err:", kernel32.GetLastError())
user32.GetCursorPos(ctypes.byref(pt))
print("Cursor pos after import:", (pt.x, pt.y))

print("\n=== NOW TESTING THREAD DESKTOP SWITCH AFTER IMPORT ===")
if hdesk:
    res2 = user32.SetThreadDesktop(hdesk)
    print("SetThreadDesktop after import:", res2, "err:", kernel32.GetLastError())
