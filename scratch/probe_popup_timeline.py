"""Timeline of a parked app's flyout windows during a menu crawl: when each appears, where it is, whether it is concealed (layered alpha 0)."""
import sys, os, time, threading, tempfile, uuid, ctypes, ctypes.wintypes as wt
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import si_tests_behavior as sb, organ_48_app_behavior_model as bm, background_window as bw
u32 = ctypes.windll.user32
app = sys.argv[1] if len(sys.argv) > 1 else "paint"
ev = []
stop = [False]
state = {}


def cls(h):
    b = ctypes.create_unicode_buffer(80); u32.GetClassNameW(h, b, 80); return b.value


def sample(pid, t0):
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        p = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value != pid or not u32.IsWindowVisible(h):
            return True
        c = cls(h)
        if "Popup" not in c and "Pop-up" not in c and c != "#32770":
            return True
        r = wt.RECT(); u32.GetWindowRect(h, ctypes.byref(r))
        on = any(min(r.right, sr) - max(r.left, sl) > 0 and min(r.bottom, sb_) - max(r.top, st) > 0 for sl, st, sr, sb_ in bw._screens())
        ex = u32.GetWindowLongW(h, -20)
        al = ctypes.c_ubyte(255); fl = wt.DWORD(0); ck = wt.DWORD(0)
        lay = bool(ex & 0x80000)
        a = al.value
        if lay and u32.GetLayeredWindowAttributes(h, ctypes.byref(ck), ctypes.byref(al), ctypes.byref(fl)):
            a = al.value
        key = (int(h), on, lay, a)
        if state.get(int(h)) != key:
            state[int(h)] = key
            ev.append((round((time.perf_counter() - t0) * 1000), int(h), c[-14:], f"rect=({r.left},{r.top},{r.right},{r.bottom})", "ON-SCREEN" if on else "off", "layered" if lay else "-", f"alpha={a}"))
        return True
    u32.EnumWindows(cb, 0)


db = os.path.join(tempfile.gettempdir(), "hj_tl_" + uuid.uuid4().hex[:6] + ".db")
m = bm.BehaviorModel(db)
with sb.LiveApp(app, park=True) as la:
    pid = wt.DWORD(); u32.GetWindowThreadProcessId(la.hwnd, ctypes.byref(pid))
    t0 = time.perf_counter()

    def loop():
        while not stop[0]:
            sample(pid.value, t0)
            time.sleep(0.002)
    th = threading.Thread(target=loop, daemon=True); th.start()
    bm.crawl_e0(m, app, la.hwnd)
    stop[0] = True; th.join(2)
for e in ev[:60]:
    print(e)
print("events", len(ev))
