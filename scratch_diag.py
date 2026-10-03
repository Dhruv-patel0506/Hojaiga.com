"""
Diagnose why input injection fails:
1. Check if OBS is elevated (UIPI blocks low->high input)
2. Check our own elevation status
3. Try SendInput (modern API) instead of mouse_event
4. Try BM_CLICK message to button's parent HWND
"""
import threading
import ctypes
import ctypes.wintypes
import time
import os
import win32gui
import win32process
import win32api
import win32con
import uiautomation as auto
import organ_30_app_scanner as s

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
advapi32 = ctypes.windll.advapi32
shell32 = ctypes.windll.shell32

# ---- Check elevation status ----
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def get_process_elevation(pid):
    """Check if a process is running elevated."""
    import ctypes.wintypes as wt
    PROCESS_QUERY_INFORMATION = 0x0400
    TOKEN_QUERY = 0x0008
    TokenElevation = 20

    hproc = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
    if not hproc:
        return "unknown (can't open process)"

    htoken = wt.HANDLE()
    if not advapi32.OpenProcessToken(hproc, TOKEN_QUERY, ctypes.byref(htoken)):
        kernel32.CloseHandle(hproc)
        return "unknown (can't open token)"

    class TOKEN_ELEVATION(ctypes.Structure):
        _fields_ = [("TokenIsElevated", ctypes.c_ulong)]

    elev = TOKEN_ELEVATION()
    retlen = ctypes.c_ulong()
    advapi32.GetTokenInformation(htoken.value, TokenElevation,
                                  ctypes.byref(elev), ctypes.sizeof(elev),
                                  ctypes.byref(retlen))
    kernel32.CloseHandle(htoken)
    kernel32.CloseHandle(hproc)
    return "ELEVATED" if elev.TokenIsElevated else "NOT elevated"

print("="*60)
print("ELEVATION DIAGNOSTICS")
print("="*60)
print(f"Our PID: {os.getpid()}")
print(f"Our process elevated: {is_admin()}")
print(f"Our elevation detail: {get_process_elevation(os.getpid())}")

hwnd = s.ensure_obs_running()
print(f"\nOBS HWND: {hwnd}")
time.sleep(1)

obs_pid = s.get_pid_for_hwnd(hwnd)
print(f"OBS PID: {obs_pid}")
if obs_pid:
    print(f"OBS elevation: {get_process_elevation(obs_pid)}")

# ---- Try SendInput ----
print("\n" + "="*60)
print("SENDINPUT TEST")
print("="*60)

root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(3)}")
box = s.safe_bounding_rect(settings_btn)
cx, cy = s.center_of(box)
print(f"Settings center: ({cx}, {cy})")

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _anonymous_ = ("_input",)
    _fields_ = [("type", ctypes.c_ulong),
                ("_input", _INPUT)]

def send_input_click(x, y):
    """Use SendInput with MOUSEEVENTF_ABSOLUTE for click."""
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    abs_x = int(x * 65535 / screen_w)
    abs_y = int(y * 65535 / screen_h)

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    INPUT_MOUSE = 0

    # Move
    inp_move = INPUT(type=INPUT_MOUSE)
    inp_move.mi.dx = abs_x
    inp_move.mi.dy = abs_y
    inp_move.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
    res = user32.SendInput(1, ctypes.byref(inp_move), ctypes.sizeof(INPUT))
    print(f"  SendInput MOVE: res={res} err={kernel32.GetLastError()}")
    time.sleep(0.1)

    # Down
    inp_down = INPUT(type=INPUT_MOUSE)
    inp_down.mi.dx = abs_x
    inp_down.mi.dy = abs_y
    inp_down.mi.dwFlags = MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE
    res = user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
    print(f"  SendInput LEFTDOWN: res={res} err={kernel32.GetLastError()}")
    time.sleep(0.08)

    # Up
    inp_up = INPUT(type=INPUT_MOUSE)
    inp_up.mi.dx = abs_x
    inp_up.mi.dy = abs_y
    inp_up.mi.dwFlags = MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE
    res = user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))
    print(f"  SendInput LEFTUP: res={res} err={kernel32.GetLastError()}")

def worker_sendinput(x, y):
    hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)
    print("Worker: Sending click via SendInput...")
    send_input_click(x, y)

t = threading.Thread(target=worker_sendinput, args=(cx, cy))
t.start()
t.join()
time.sleep(1.5)

print("\nChecking for Settings window...")
found = False
for win in auto.GetRootControl().GetChildren():
    wname = (win.Name or "").lower()
    if "settings" in wname:
        print(f"SUCCESS: Found Settings window: {win.Name}")
        found = True
        trav = s.DialogTraversal()
        trav._close_safely(win, win.NativeWindowHandle)
        break

if not found:
    print("Settings dialog NOT opened via SendInput.")
    print("\n--- Trying BM_CLICK to parent HWND ---")
    # WindowFromPoint to get the actual child HWND
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT(cx, cy)
    child_hwnd = user32.WindowFromPoint(pt)
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(child_hwnd, buf, 512)
    cls = ctypes.create_unicode_buffer(512)
    user32.GetClassNameW(child_hwnd, cls, 512)
    print(f"Child HWND at ({cx},{cy}): {child_hwnd} title='{buf.value}' class='{cls.value}'")

    # Try BM_CLICK
    BM_CLICK = 0x00F5
    user32.SendMessageW(child_hwnd, BM_CLICK, 0, 0)
    time.sleep(1.5)
    for win in auto.GetRootControl().GetChildren():
        wname = (win.Name or "").lower()
        if "settings" in wname:
            print(f"SUCCESS: Found Settings window via BM_CLICK: {win.Name}")
            found = True
            trav = s.DialogTraversal()
            trav._close_safely(win, win.NativeWindowHandle)
            break
    if not found:
        print("BM_CLICK also failed.")

print("\nDone.")
