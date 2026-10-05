"""
Full OBS Settings test. Designed to be launched via:
  cmd /c start /wait python d:\new_automation\scratch_obs_full_test.py
"""
import ctypes
import time
import sys
import json
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(r"d:\new_automation")
sys.path.insert(0, r"d:\new_automation")

import win32gui
import win32con
import uiautomation as auto
import organ_30_app_scanner as s

user32 = ctypes.windll.user32
RESULT_FILE = r"d:\new_automation\scratch_obs_full_result.json"

result = {"steps": []}

def log(msg):
    print(msg)
    result["steps"].append(msg)

s.ensure_interactive_desktop()

log(f"PID: {os.getpid()}")

# Check our console
console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
log(f"Console HWND: {console_hwnd}")

fg = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, buf, 512)
log(f"Initial foreground: hwnd={fg} title='{buf.value}'")

# Find OBS
hwnd = s.find_hwnd_by_title_substring("OBS")
if not hwnd:
    log("OBS not running, launching...")
    hwnd = s.ensure_obs_running()
    time.sleep(3)

if not hwnd:
    log("FATAL: Could not find/launch OBS")
    with open(RESULT_FILE, "w") as f:
        json.dump(result, f, indent=2)
    sys.exit(1)

log(f"OBS HWND: {hwnd}")

# Bring OBS to foreground - click its console first, then OBS
user32.ShowWindow(hwnd, 9)
time.sleep(0.1)

# SetForegroundWindow - should work since we have a foreground console
res = user32.SetForegroundWindow(hwnd)
log(f"SetForegroundWindow: {res}")
time.sleep(0.3)

fg = user32.GetForegroundWindow()
user32.GetWindowTextW(fg, buf, 512)
log(f"Foreground after SetFG: hwnd={fg} title='{buf.value}'")

if fg != hwnd:
    log("Trying Alt-pulse + SetForegroundWindow...")
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.05)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    fg = user32.GetForegroundWindow()
    user32.GetWindowTextW(fg, buf, 512)
    log(f"Foreground after Alt-pulse: hwnd={fg} title='{buf.value}'")

# Check cursor movement
user32.SetCursorPos(960, 540)
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
pt = POINT()
user32.GetCursorPos(ctypes.byref(pt))
log(f"Cursor at: ({pt.x}, {pt.y})")

# Now try clicking Settings
root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
log(f"Settings btn exists: {settings_btn.Exists(3)}")

if settings_btn.Exists(0):
    box = s.safe_bounding_rect(settings_btn)
    cx, cy = s.center_of(box)
    log(f"Settings center: ({cx}, {cy})")

    # Click it
    log("Clicking Settings via auto.Click...")
    auto.Click(cx, cy)
    time.sleep(2.0)

    # Check
    found = False
    for win in auto.GetRootControl().GetChildren():
        wname = (win.Name or "").lower()
        if "settings" in wname:
            log(f"SUCCESS: Settings dialog opened! hwnd={win.NativeWindowHandle}")
            found = True
            result["settings_opened"] = True

            trav = s.DialogTraversal()
            tabs = trav._find_tabs(win)
            tab_names = [t.Name for t in tabs]
            log(f"Tabs ({len(tabs)}): {tab_names}")
            result["tabs"] = tab_names

            for tab in tabs:
                tbox = s.safe_bounding_rect(tab)
                if tbox and s.is_onscreen(tbox):
                    tcx, tcy = s.center_of(tbox)
                    log(f"  Clicking tab '{tab.Name}'...")
                    auto.Click(tcx, tcy)
                    time.sleep(0.3)
                    controls = trav._collect_controls(win, parent_tab=tab.Name)
                    log(f"  Tab '{tab.Name}' has {len(controls)} controls")

            trav._close_safely(win, win.NativeWindowHandle)
            log("Settings dialog safely closed.")
            break

    if not found:
        log("Settings dialog NOT opened via click.")
        result["settings_opened"] = False

        # Try via InvokePattern
        log("Trying InvokePattern...")
        try:
            pat = settings_btn.GetInvokePattern()
            if pat:
                pat.Invoke()
                log("Invoke called.")
                time.sleep(2.0)
                for win in auto.GetRootControl().GetChildren():
                    wname = (win.Name or "").lower()
                    if "settings" in wname:
                        log(f"SUCCESS via Invoke: {win.Name}")
                        result["settings_opened"] = True
                        trav = s.DialogTraversal()
                        trav._close_safely(win, win.NativeWindowHandle)
                        break
        except Exception as e:
            log(f"InvokePattern error: {e}")

# Menu test
log("\n--- Menu Test ---")
user32.SetForegroundWindow(hwnd)
time.sleep(0.3)
s.send_alt_sequence("%f")
time.sleep(0.4)
fc = auto.GetFocusedControl()
mf = fc.Name if fc else None
log(f"Focused in File menu: {mf}")
result["menu_focused"] = mf
s.send_keys(win32con.VK_ESCAPE)

with open(RESULT_FILE, "w") as f:
    json.dump(result, f, indent=2)

log(f"\nResults written to {RESULT_FILE}")
