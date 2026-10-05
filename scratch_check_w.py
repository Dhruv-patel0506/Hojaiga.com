import ctypes
import win32gui

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

hwnds = []
def enum_w(h, _):
    if win32gui.IsWindowVisible(h):
        t = win32gui.GetWindowText(h)
        c = win32gui.GetClassName(h)
        if t or "paint" in c.lower():
            hwnds.append((h, t, c, win32gui.GetWindowRect(h)))

win32gui.EnumWindows(enum_w, None)
for h, t, c, r in hwnds:
    if any(k in t.lower() or k in c.lower() for k in ["paint", "chrome", "notepad", "calc", "untitled"]):
        print(f"HWND: {h} | Title: '{t}' | Class: '{c}' | Rect: {r}")
