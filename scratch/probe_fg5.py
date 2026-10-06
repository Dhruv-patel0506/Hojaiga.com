import sys, time, ctypes, ctypes.wintypes as wt
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import si_tests_behavior as sb, background_window as bw
u32 = ctypes.windll.user32; k32 = ctypes.windll.kernel32


def desc(h):
    if not h:
        return "none"
    c = ctypes.create_unicode_buffer(60); u32.GetClassNameW(h, c, 60)
    t = ctypes.create_unicode_buffer(40); u32.GetWindowTextW(h, t, 40)
    return f"{h}:{c.value[:16]}:{t.value[:24]}"


user = u32.GetForegroundWindow()
print("user fg:", desc(user), flush=True)
with sb.LiveApp("notepad", park=False) as la:
    s = bw.BackgroundSession(la.hwnd); s.__enter__()
    g = bw._parked[la.hwnd].guard
    for _ in range(60):
        if "Notepad" in desc(u32.GetForegroundWindow()):
            break
        time.sleep(0.25)
    print("holder:", desc(u32.GetForegroundWindow()), "guard trace", getattr(g, "focus_trace", None), flush=True)
    g.halt(); g.join(2)
    if "Notepad" not in desc(u32.GetForegroundWindow()):
        print("NOT REPRODUCED")
        s.__exit__(None, None, None)
        sys.exit()
    holder = u32.GetForegroundWindow()
    ftid = u32.GetWindowThreadProcessId(holder, None); me = k32.GetCurrentThreadId()
    ut = u32.GetWindowThreadProcessId(user, None)

    def attempt(name, fn):
        fn(); time.sleep(0.5)
        fg = u32.GetForegroundWindow()
        print(f"{name:40s} -> fg={desc(fg)} {'OK' if fg == user else 'no'}", flush=True)
        return fg == user

    attempt("SwitchToThisWindow(user,True)", lambda: u32.SwitchToThisWindow(user, True))

    def a2():
        u32.AttachThreadInput(me, ftid, True); r = u32.SetForegroundWindow(user); u32.AttachThreadInput(me, ftid, False); print("   ret", r)
    attempt("Attach(holder)+SetForegroundWindow", a2)

    def a3():
        u32.AttachThreadInput(me, ut, True); u32.AttachThreadInput(me, ftid, True)
        u32.BringWindowToTop(user); r = u32.SetForegroundWindow(user); u32.SetActiveWindow(user)
        u32.AttachThreadInput(me, ftid, False); u32.AttachThreadInput(me, ut, False); print("   ret", r)
    attempt("Attach both+BringToTop+SetFg+Active", a3)

    def a4():
        u32.AttachThreadInput(me, ut, True); r = u32.SetForegroundWindow(user); u32.AttachThreadInput(me, ut, False); print("   ret", r)
    attempt("Attach(user)+SetForegroundWindow", a4)
    attempt("SetWindowPos(holder, HWND_BOTTOM)", lambda: u32.SetWindowPos(la.hwnd, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010))
    attempt("SwitchToThisWindow(user,False)", lambda: u32.SwitchToThisWindow(user, False))
    def a7():
        # Windows hands the foreground to the next window when the holder MINIMIZES: do it for one beat, then restore off-screen
        u32.ShowWindow(la.hwnd, 7)
    attempt("minimize holder (SW_SHOWMINNOACTIVE)", a7)
    s.__exit__(None, None, None)
