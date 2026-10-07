import ctypes, ctypes.wintypes as wt, time, os
u = ctypes.windll.user32
os.startfile("calc.exe")
time.sleep(3.5)

found = []


@ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
def cb(h, l):
    if u.IsWindowVisible(h):
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, buf, 256)
        t = u.GetWindowTextLengthW(h)
        tb = ctypes.create_unicode_buffer(t + 1)
        u.GetWindowTextW(h, tb, t + 1)
        if "Calculator" in tb.value or "calc" in buf.value.lower():
            found.append((int(h), buf.value, tb.value))
    return True


u.EnumWindows(cb, 0)

from core_organs import headless_input as hin, dap_actuator as da, fast_uia as fu
import core_organs.desktop_grounding as dg

g = dg.DesktopGrounding()
for h, c, t in found:
    kids = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cbk(hh, ll):
        b = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hh, b, 256)
        kids.append(b.value)
        return True

    u.EnumChildWindows(h, cbk, 0)
    print("hwnd", h, "class", repr(c), "title", repr(t))
    print("  is_xaml_host", hin.is_xaml_host(h), "family_of", da.family_of(h))
    print("  child classes(first8)", kids[:8])
    snap = fu.snapshot(h, max_nodes=1600, timeout_ms=8000) or []
    named_btn = [n.name for n in snap if n.role == "button" and (n.name or "").strip()]
    print("  fast_uia nodes", len(snap), "named buttons", len(named_btn), named_btn[:8])
    raw = g._ground_raw(h)
    walked = g._walk_uia(h)
    print("  _ground_raw", len(raw), [e.name for e in raw[:8]])
    print("  _walk_uia", len(walked), [e.name for e in walked[:8]])

# cleanup: close the calc window we opened
for h, c, t in found:
    try:
        u.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
    except Exception:
        pass
print("closed", len(found))
