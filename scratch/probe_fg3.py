import sys, time, ctypes, ctypes.wintypes as wt
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import si_tests_behavior as sb, background_window as bw
u32 = ctypes.windll.user32
def desc(h):
    if not h: return "none"
    c = ctypes.create_unicode_buffer(60); u32.GetClassNameW(h, c, 60)
    t = ctypes.create_unicode_buffer(40); u32.GetWindowTextW(h, t, 40)
    return f"{h}:{c.value}:{t.value}:iconic={bool(u32.IsIconic(h))}"
claude = u32.GetForegroundWindow()
print("start fg:", desc(claude), flush=True)
with sb.LiveApp("notepad", park=False) as la:
    time.sleep(2)
    print("after launch fg:", desc(u32.GetForegroundWindow()), "note:", la.launch_note, flush=True)
    # make Notepad the foreground the way the failing case does, then try each hand-back
    u32.ShowWindow(la.hwnd, 4); time.sleep(0.3); u32.ShowWindow(la.hwnd, 7); time.sleep(0.4)
    print("after unminimize+minimize fg:", desc(u32.GetForegroundWindow()), flush=True)
    tray = u32.FindWindowW("Shell_TrayWnd", None)
    u32.SwitchToThisWindow(tray, True); time.sleep(0.4)
    print("SwitchToThisWindow(tray) ->", desc(u32.GetForegroundWindow()), flush=True)
    u32.ShowWindow(la.hwnd, 4); time.sleep(0.3); u32.ShowWindow(la.hwnd, 7); time.sleep(0.4)
    print("again notepad fg:", desc(u32.GetForegroundWindow()), flush=True)
    r = u32.SetForegroundWindow(tray); time.sleep(0.4)
    print("SetForegroundWindow(tray)=", r, "->", desc(u32.GetForegroundWindow()), flush=True)
    u32.ShowWindow(la.hwnd, 4); time.sleep(0.3); u32.ShowWindow(la.hwnd, 7); time.sleep(0.4)
    u32.SwitchToThisWindow(claude, True); time.sleep(0.4)
    print("SwitchToThisWindow(claude) ->", desc(u32.GetForegroundWindow()), flush=True)
    print("next_user_window:", desc(bw.next_user_window(0)))
    print("bw._last_user_fg:", desc(bw._last_user_fg))
