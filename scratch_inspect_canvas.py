import ctypes
import win32gui
import uiautomation as auto

def _ensure_interactive_desktop():
    user32 = ctypes.windll.user32
    hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x0002 | 0x0100 | 0x0200)
    if hwinsta:
        user32.SetProcessWindowStation(hwinsta)
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    if not hdesk:
        hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)

_ensure_interactive_desktop()

ctrl = auto.ControlFromHandle(459306)
print("Root ctrl:", ctrl)
for c, depth in auto.WalkControl(ctrl, maxDepth=12):
    b = c.BoundingRectangle
    if b and (b.right - b.left > 200) and (b.bottom - b.top > 150):
        print(f"Depth {depth} | {c.ControlTypeName} | ID: {c.AutomationId} | Name: '{c.Name}' | Rect: ({b.left}, {b.top}, {b.right}, {b.bottom}) size: {b.right-b.left}x{b.bottom-b.top}")
