"""
Full OBS Settings test launched via `cmd /c start /wait`.
This process has its own console window and can inject input.
"""
import ctypes
import time
import sys
import json
import os
import win32gui
import win32con
import uiautomation as auto

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import organ_30_app_scanner as s

s.ensure_interactive_desktop()

hwnd = s.ensure_obs_running()
print(f"OBS HWND: {hwnd}")
time.sleep(2)

# Set OBS as foreground - we should be able to now
user32.ShowWindow(hwnd, 9)
time.sleep(0.1)
res = user32.SetForegroundWindow(hwnd)
print(f"SetForegroundWindow: {res}")
time.sleep(0.5)

fg = user32.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(512)
user32.GetWindowTextW(fg, buf, 512)
print(f"Foreground now: hwnd={fg} title='{buf.value}'")

root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print(f"Settings btn exists: {settings_btn.Exists(3)}")
box = s.safe_bounding_rect(settings_btn)
cx, cy = s.center_of(box)
print(f"Settings center: ({cx}, {cy})")

# Click the Settings button
print("Clicking Settings via auto.Click...")
auto.Click(cx, cy)
time.sleep(2.0)

# Check for Settings window
result = {"settings_opened": False, "tabs": []}
for win in auto.GetRootControl().GetChildren():
    wname = (win.Name or "").lower()
    if "settings" in wname:
        print(f"SUCCESS: Found Settings window: {win.Name} hwnd={win.NativeWindowHandle}")
        result["settings_opened"] = True
        
        trav = s.DialogTraversal()
        tabs = trav._find_tabs(win)
        tab_names = [t.Name for t in tabs]
        result["tabs"] = tab_names
        print(f"Tabs ({len(tabs)}): {tab_names}")
        
        # Click each tab and count controls
        for tab in tabs:
            tbox = s.safe_bounding_rect(tab)
            if tbox and s.is_onscreen(tbox):
                tcx, tcy = s.center_of(tbox)
                print(f"  Clicking tab '{tab.Name}'...")
                s.physical_click(tcx, tcy, tab)
                time.sleep(0.3)
                controls = trav._collect_controls(win, parent_tab=tab.Name)
                print(f"  Tab '{tab.Name}' has {len(controls)} controls")
        
        trav._close_safely(win, win.NativeWindowHandle)
        print("Settings dialog safely closed.")
        break

if not result["settings_opened"]:
    print("FAILED: Settings dialog did not open.")

# Also test menu navigation
print("\n--- Menu Test ---")
user32.SetForegroundWindow(hwnd)
time.sleep(0.3)
s.send_alt_sequence("%f")
time.sleep(0.3)
fc = auto.GetFocusedControl()
menu_focused = fc.Name if fc else None
print(f"Focused in File menu: {menu_focused}")
result["menu_focused"] = menu_focused
s.send_keys(win32con.VK_ESCAPE)

with open("scratch_interactive_result.json", "w") as f:
    json.dump(result, f, indent=2)

print("\nDone.")
time.sleep(1)
