import ctypes, time, win32gui, win32con

def _ensure_interactive_desktop():
    user32 = ctypes.windll.user32
    hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x0002 | 0x0100 | 0x0200)
    if hwinsta: user32.SetProcessWindowStation(hwinsta)
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF) or user32.OpenDesktopW("default", 0, False, 0x01FF)
    if hdesk: user32.SetThreadDesktop(hdesk)

_ensure_interactive_desktop()

target_hwnd = 0
def _find(h, _):
    global target_hwnd
    if win32gui.IsWindowVisible(h):
        t = win32gui.GetWindowText(h).lower()
        c = win32gui.GetClassName(h).lower()
        if "antigravity" in t: return True
        if "paint" in t or c in ("mspaintapp", "paintapp"):
            target_hwnd = h
            return False
    return True

win32gui.EnumWindows(_find, None)
print("Paint HWND:", target_hwnd)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
fg_hwnd = user32.GetForegroundWindow()
fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
cur_tid = kernel32.GetCurrentThreadId()

if fg_tid and fg_tid != cur_tid:
    user32.AttachThreadInput(cur_tid, fg_tid, True)

user32.keybd_event(0x12, 0, 0, 0); time.sleep(0.02); user32.keybd_event(0x12, 0, 2, 0); time.sleep(0.05)
win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
user32.SetWindowPos(target_hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
user32.SetWindowPos(target_hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
user32.SetForegroundWindow(target_hwnd)
user32.SwitchToThisWindow(target_hwnd, True)
win32gui.ShowWindow(target_hwnd, win32con.SW_MAXIMIZE)

if fg_tid and fg_tid != cur_tid:
    user32.AttachThreadInput(cur_tid, fg_tid, False)

time.sleep(0.5)

# Click canvas center to give focus
screen_w = user32.GetSystemMetrics(0)
screen_h = user32.GetSystemMetrics(1)
cx, cy = 750, 500
user32.mouse_event(0x8001, int(cx * 65535 / screen_w), int(cy * 65535 / screen_h), 0, 0)
time.sleep(0.05)
user32.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.05); user32.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(0.2)

# Select all and delete (clean slate)
user32.keybd_event(0x11, 0, 0, 0); user32.keybd_event(0x41, 0, 0, 0); time.sleep(0.05)
user32.keybd_event(0x41, 0, 2, 0); user32.keybd_event(0x11, 0, 2, 0); time.sleep(0.15)
user32.keybd_event(0x2E, 0, 0, 0); time.sleep(0.05); user32.keybd_event(0x2E, 0, 2, 0)
time.sleep(0.3)

# Escape to clear any selection rectangle
user32.keybd_event(0x1B, 0, 0, 0); time.sleep(0.03); user32.keybd_event(0x1B, 0, 2, 0)
time.sleep(0.2)

from PIL import ImageGrab
im = ImageGrab.grab()
p = r"C:\Users\dhruv\.gemini\antigravity-ide\brain\96f3e7c2-9e2e-4858-9056-491a84fb8130\clean_paint_proof.png"
im.save(p)
print("Paint clean proof saved to:", p)
