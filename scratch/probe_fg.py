import sys, time, ctypes, ctypes.wintypes as wt, threading
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import si_tests_behavior as sb, background_window as bw
u32 = ctypes.windll.user32
def desc(h):
    if not h: return "none"
    c = ctypes.create_unicode_buffer(60); u32.GetClassNameW(h, c, 60)
    t = ctypes.create_unicode_buffer(40); u32.GetWindowTextW(h, t, 40)
    p = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(p))
    return f"{h}:{c.value}:{t.value}:pid{p.value}"
print("fg before:", desc(u32.GetForegroundWindow()), "| next_user_window:", desc(bw.next_user_window(0)), "| tray:", desc(u32.FindWindowW("Shell_TrayWnd", None)), flush=True)
t0 = time.time()
log = []
stop = [False]
def watch():
    last = None
    while not stop[0]:
        d = desc(u32.GetForegroundWindow())
        if d != last:
            log.append((round(time.time() - t0, 2), d)); last = d
        time.sleep(0.02)
th = threading.Thread(target=watch, daemon=True); th.start()
with sb.LiveApp("notepad", park=True) as la:
    print("entered", la.ok, la.launch_note, flush=True)
    time.sleep(6)
stop[0] = True; th.join(1)
for e in log: print(e)
