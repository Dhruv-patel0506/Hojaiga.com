import time
import win32con
import win32gui
import uiautomation as auto
import organ_30_app_scanner as s

hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)
s.bring_to_foreground(hwnd)
time.sleep(1)

# Let's send Alt+F to open File menu
print("Sending Alt+F...")
s.send_alt_sequence("%f")
time.sleep(0.5)

# In File menu, let's list the menu items
fc = auto.GetFocusedControl()
print("Focused in menu:", fc.Name if fc else None)

# Press Down arrow and print focused control
for i in range(15):
    s.send_keys(win32con.VK_DOWN)
    time.sleep(0.15)
    fc = auto.GetFocusedControl()
    name = fc.Name if fc else None
    print(f"Down {i}: {name}")
    if name and "settings" in name.lower():
        print("Found Settings in File menu! Pressing Enter...")
        s.send_keys(win32con.VK_RETURN)
        time.sleep(1.5)
        break

print("Checking for Settings window...")
for win in auto.GetRootControl().GetChildren():
    if "settings" in (win.Name or "").lower():
        print("SUCCESS! Found Settings window:", win.Name, win.NativeWindowHandle)
        traversal = s.DialogTraversal()
        tabs = traversal._find_tabs(win)
        print(f"Tabs ({len(tabs)}): {[t.Name for t in tabs]}")
        traversal._close_safely(win, win.NativeWindowHandle)
        print("Safely closed Settings dialog.")
        break
