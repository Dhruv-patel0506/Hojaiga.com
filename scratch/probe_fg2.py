import sys, time, ctypes, ctypes.wintypes as wt, threading
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import si_tests_behavior as sb, background_window as bw
u32 = ctypes.windll.user32
def desc(h):
    if not h: return "none"
    c = ctypes.create_unicode_buffer(60); u32.GetClassNameW(h, c, 60)
    t = ctypes.create_unicode_buffer(40); u32.GetWindowTextW(h, t, 40)
    p = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(p))
    return f"{h}:{c.value}:{t.value}:pid{p.value}:iconic={bool(u32.IsIconic(h))}:vis={bool(u32.IsWindowVisible(h))}"
for it in range(6):
    t0 = time.time(); log = []; stop = [False]
    def watch():
        last = None
        while not stop[0]:
            d = desc(u32.GetForegroundWindow())
            if d != last:
                log.append((round(time.time() - t0, 2), d)); last = d
            time.sleep(0.02)
    th = threading.Thread(target=watch, daemon=True); th.start()
    with sb.LiveApp("notepad", park=False) as la:
        note = la.launch_note
        pid = wt.DWORD(); u32.GetWindowThreadProcessId(la.hwnd, ctypes.byref(pid))
        time.sleep(8)
        fg = u32.GetForegroundWindow(); p2 = wt.DWORD(); u32.GetWindowThreadProcessId(fg, ctypes.byref(p2))
        print(f"iter {it}: note={note!r} fg_end_is_notepad={p2.value == pid.value} fg={desc(fg)}", flush=True)
    stop[0] = True; th.join(1)
    if len(log) > 3 or any(f"pid{pid.value}" in d for _, d in log[-1:]):
        for e in log[-6:]: print("   ", e)
    time.sleep(2)
