"""Is the desk free? 12 s of pointer sampling + the app windows a test would refuse to touch."""
import ctypes, ctypes.wintypes as wt, time

u = ctypes.windll.user32


def cursor():
    p = wt.POINT()
    u.GetCursorPos(ctypes.byref(p))
    return (p.x, p.y)


def hard_events():
    class MSG(ctypes.Structure):
        _fields_ = [("hwnd", wt.HWND), ("message", ctypes.c_uint), ("wParam", wt.WPARAM),
                    ("lParam", wt.LPARAM), ("time", ctypes.c_uint), ("pt", wt.POINT)]
    m = MSG()
    n = 0
    end = time.time() + 12
    t0, pos0 = time.time(), cursor()
    moved = 0
    while time.time() < end:
        while u.PeekMessageW(ctypes.byref(m), 0, 0x0200, 0x020A, 1):   # WM_MOUSE* range
            n += 1
        c = cursor()
        moved = max(moved, abs(c[0] - pos0[0]) + abs(c[1] - pos0[1]))
        time.sleep(0.1)
    return n, moved, cursor(), t0


def app_windows():
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if u.IsWindowVisible(h) or u.IsIconic(h):
            cls = ctypes.create_unicode_buffer(128)
            u.GetClassNameW(h, cls, 128)
            n = u.GetWindowTextLengthW(h)
            t = ""
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(h, b, n + 1)
                t = b.value
            low = cls.value.lower()
            if any(k in low for k in ("notepad", "mspaint", "applicationframewindow", "win32", "chrome_xinternal")) \
                    or any(k in t.lower() for k in ("notepad", "paint", "calculator")):
                out.append((cls.value, t[:48]))
        return True
    u.EnumWindows(cb, 0)
    return out


ev, moved, now, _t = hard_events()
print(f"12 s of pointer: hardware mouse messages={ev} max travel from start={moved}px end={now}")
w = app_windows()
print("app windows that make a live test refuse:", len(w))
for c, t in w[:12]:
    print(f"   class={c:28} title={t!r}")
