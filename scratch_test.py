import sys
import time
import win32gui
import win32process
import uiautomation as auto
import organ_30_app_scanner as s

s.ensure_interactive_desktop()
hwnd = s.ensure_obs_running()
print("OBS HWND:", hwnd)
s.bring_to_foreground(hwnd)
time.sleep(1)

root = auto.ControlFromHandle(hwnd)
settings_btn = root.ButtonControl(Name="Settings")
print("Settings btn exists:", settings_btn.Exists(3))

if settings_btn.Exists(0):
    print("Calling settings_btn.GetInvokePattern().Invoke()...")
    try:
        pat = settings_btn.GetInvokePattern()
        if pat:
            pat.Invoke()
            print("Invoked successfully!")
        else:
            print("No invoke pattern, trying Click()...")
            settings_btn.Click()
    except Exception as e:
        print("Invoke error:", e)

    print("Waiting for settings window to appear...")
    found_dlg = None
    target_pid = s.get_pid_for_hwnd(hwnd)
    print("Target PID:", target_pid)

    for i in range(20):
        time.sleep(0.3)
        # Check 1: root children
        for win in auto.GetRootControl().GetChildren():
            try:
                wname = win.Name or ""
                wpid = win.ProcessId
                whwnd = win.NativeWindowHandle
                if wpid == target_pid and whwnd != hwnd:
                    print(f"Candidate child window: hwnd={whwnd} name='{wname}'")
                    if "settings" in wname.lower():
                        found_dlg = win
                        break
            except Exception as e:
                pass
        if found_dlg:
            break

    if found_dlg:
        print("Found Settings Dialog Window!", found_dlg.Name, found_dlg.NativeWindowHandle)
        traversal = s.DialogTraversal()
        tabs = traversal._find_tabs(found_dlg)
        print("Found tabs:", [t.Name for t in tabs])
        for t in tabs:
            box = s.safe_bounding_rect(t)
            print("Tab:", t.Name, "box:", box, "type:", t.ControlTypeName)
            try:
                t.GetInvokePattern().Invoke()
            except Exception:
                try:
                    t.GetSelectionItemPattern().Select()
                except Exception:
                    pass
            time.sleep(0.2)
            controls = traversal._collect_controls(found_dlg, parent_tab=t.Name)
            print(f"Tab '{t.Name}' has {len(controls)} controls")

        traversal._close_safely(found_dlg, found_dlg.NativeWindowHandle)
        print("Closed settings dialog successfully.")
    else:
        print("Settings dialog did not appear!")
