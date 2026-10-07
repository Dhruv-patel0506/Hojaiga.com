"""Read-only desktop census: which Notepad/Paint windows exist, visible or parked off-screen, and who owns them.

Why: MIN1/LM1 evidence in f6 and h1 named notepad documents from OTHER tests (poem1.txt, poem2.txt) as the
windows being *exposed*. A parked window is invisible but alive; a released one returns to its old spot and
starts interfering with every test that enumerates windows. This script answers the question with a list, not
a theory - it never moves, closes or focuses anything.
"""
import ctypes
import ctypes.wintypes as w

u = ctypes.windll.user32
rows = []


def cb(h, _l):
    buf = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(h, buf, 512)
    cl = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(h, cl, 256)
    title = buf.value
    cls = cl.value
    if not (title or cls):
        return True
    low = (title + " " + cls).lower()
    if "notepad" not in low and "paint" not in low:
        return True
    r = w.RECT()
    u.GetWindowRect(h, ctypes.byref(r))
    pid = w.DWORD()
    u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    vis = bool(u.IsWindowVisible(h))
    icon = bool(u.IsIconic(h))
    on_screen = r.right > 0 and r.bottom > 0 and (r.left > -20000 or not vis)
    rows.append({"hwnd": h, "title": title[:44], "cls": cls[:24], "visible": vis,
                 "minimized": icon, "rect": (r.left, r.top, r.right, r.bottom), "pid": pid.value})
    return True


PROCBESTATE = ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
u.EnumWindows(PROCBESTATE(cb), 0)

print(f"{len(rows)} Notepad/Paint top-level window(s)")
for x in sorted(rows, key=lambda a: (a["title"], a["hwnd"])):
    off = x["rect"][0] <= -20000 or x["rect"][0] > 4000
    print(f"  hwnd={x['hwnd']:<10} pid={x['pid']:<7} vis={int(x['visible'])} min={int(x['minimized'])} "
          f"{'PARKED-OFF-SCREEN ' if off else '               '}{str(x['rect']):<28} {x['cls']:<24} {x['title']}")
