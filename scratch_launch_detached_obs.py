import subprocess
import time
import os
import ctypes
import uiautomation as auto

obs_exe = r"D:\obs-studio\bin\64bit\obs64.exe"
cwd = os.path.dirname(obs_exe)

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

print("Launching detached OBS...")
proc = subprocess.Popen(
    [obs_exe],
    cwd=cwd,
    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
)
print(f"Launched PID: {proc.pid}")

# Dismiss safe mode dialog if it appears
main_hwnd = None
for second in range(15):
    time.sleep(1)
    for win in auto.GetRootControl().GetChildren():
        try:
            wname = win.Name or ""
            wcls = win.ClassName or ""
            if "Crash Detected" in wname or "QMessageBox" in wcls:
                btn = win.ButtonControl(Name="Run in Safe Mode")
                if btn.Exists(0.5):
                    pat = btn.GetInvokePattern()
                    if pat:
                        pat.Invoke()
                        print(f"[{second}s] Clicked Run in Safe Mode!")
                        time.sleep(1)
                        break
            elif "profile:" in wname.lower() or ("obs" in wname.lower() and "crash" not in wname.lower()):
                main_hwnd = win.NativeWindowHandle
                print(f"[{second}s] FOUND OBS MAIN WINDOW: {main_hwnd} title='{wname}'")
                break
        except Exception:
            continue
    if main_hwnd:
        break

print(f"Final OBS HWND: {main_hwnd}")
