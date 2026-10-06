import sys, time, ctypes, ctypes.wintypes as wt, threading
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import si_tests_behavior as sb, background_window as bw
u32 = ctypes.windll.user32
def desc(h):
    if not h: return "none"
    c = ctypes.create_unicode_buffer(60); u32.GetClassNameW(h, c, 60)
    t = ctypes.create_unicode_buffer(40); u32.GetWindowTextW(h, t, 40)
    p = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(p))
    return f"{h}:{c.value[:18]}:{t.value[:28]}:pid{p.value}:iconic={bool(u32.IsIconic(h))}"
for it in range(int(sys.argv[1]) if len(sys.argv) > 1 else 4):
    fg0 = u32.GetForegroundWindow()
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
        s = bw.BackgroundSession(la.hwnd); s.__enter__()
        time.sleep(1.5)
        g = bw._parked[la.hwnd].guard
        print(f"iter {it}: note={note!r} fg0={desc(fg0)} user_fg={desc(g.user_fg)} _last_user_fg={desc(bw._last_user_fg)}", flush=True)
        time.sleep(6)
        print(f"   guard refocused={g.refocused} trace={getattr(g, 'focus_trace', None)} moved={g.moved}; fg now={desc(u32.GetForegroundWindow())}", flush=True)
        s.__exit__(None, None, None)
        time.sleep(1)
        print(f"   after exit fg={desc(u32.GetForegroundWindow())}", flush=True)
    stop[0] = True; th.join(1)
    for e in log[-8:]: print("     ", e)
    time.sleep(1.5)
