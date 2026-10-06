"""probe_capture_matrix.py -- why does PrintWindow come back blank INSIDE a long process?

Measures, per window state, the raw Win32 answer (PrintWindow return + GetLastError + pixel
statistics + GDI/USER object counts), not just headless_input's verdict. Read-only diagnosis.
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

u32 = ctypes.WinDLL("user32", use_last_error=True)
g32 = ctypes.WinDLL("gdi32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
H = ctypes.c_void_p
u32.GetGuiResources.argtypes = [H, wt.UINT]
u32.GetGuiResources.restype = wt.UINT
k32.GetCurrentProcess.restype = H
u32.PrintWindow.argtypes = [H, H, wt.UINT]
u32.PrintWindow.restype = wt.BOOL
u32.GetDC.argtypes = [H]
u32.GetDC.restype = H
u32.ReleaseDC.argtypes = [H, H]
u32.GetWindowRect.argtypes = [H, ctypes.POINTER(wt.RECT)]
u32.MoveWindow.argtypes = [H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.BOOL]
u32.ShowWindow.argtypes = [H, ctypes.c_int]
u32.IsIconic.argtypes = [H]
g32.CreateCompatibleDC.argtypes = [H]
g32.CreateCompatibleDC.restype = H
g32.CreateCompatibleBitmap.argtypes = [H, ctypes.c_int, ctypes.c_int]
g32.CreateCompatibleBitmap.restype = H
g32.SelectObject.argtypes = [H, H]
g32.SelectObject.restype = H
g32.DeleteObject.argtypes = [H]
g32.DeleteDC.argtypes = [H]
g32.GetDIBits.argtypes = [H, H, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]

SW_SHOWNOACTIVATE, SW_SHOWMINNOACTIVE, SW_RESTORE = 4, 7, 9
PARK = (-24000, -24000)


def gui_counts():
    proc = k32.GetCurrentProcess()
    return u32.GetGuiResources(proc, 0), u32.GetGuiResources(proc, 1)   # GDI, USER


class BIH(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def raw_capture(hwnd, flag):
    """PrintWindow with the given flag, returning the Win32 truth plus pixel stats."""
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return {"rect": (w, h), "note": "bad-rect"}
    sdc = u32.GetDC(None)
    mdc = g32.CreateCompatibleDC(sdc)
    bmp = g32.CreateCompatibleBitmap(sdc, w, h)
    if not mdc or not bmp:
        err = ctypes.get_last_error()
        g32.DeleteDC(mdc) if mdc else None
        g32.DeleteObject(bmp) if bmp else None
        u32.ReleaseDC(None, sdc)
        return {"rect": (w, h), "pw": None, "note": f"GDI-CREATE-FAILED(err={err})", "gdi": gui_counts()}
    old = g32.SelectObject(mdc, bmp)
    err = 0
    pw = u32.PrintWindow(hwnd, mdc, flag)
    err = ctypes.get_last_error()
    bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = (ctypes.c_ubyte * (w * h * 4))()
    rows = g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
    g32.SelectObject(mdc, old)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u32.ReleaseDC(None, sdc)
    data = bytes(buf)
    step = max(1, (w * h) // 4000) * 4
    sample = [data[i] for i in range(0, len(data) - 3, step)]
    nz = sum(1 for v in sample if v)
    return {"rect": (w, h), "pw": int(pw), "err": err, "rows": rows,
            "px_mean": round(sum(sample) / max(1, len(sample)), 1),
            "nonzero_frac": round(nz / max(1, len(sample)), 3)}


def report(label, hwnd, flag=0x2):
    before = gui_counts()
    t0 = time.time()
    out = raw_capture(hwnd, flag)
    after = gui_counts()
    from core_organs import headless_input as hin
    img, note = hin.capture_window(hwnd)
    print(f"  {label:<34} pw={out.get('pw')} err={out.get('err')} rows={out.get('rows')} "
          f"px_mean={out.get('px_mean')} nonzero={out.get('nonzero_frac')} "
          f"| hin={'OK' if img is not None else 'BLANK'}({note[:34]}) "
          f"| gdi {before[0]}->{after[0]} user {before[1]}->{after[1]} "
          f"({(time.time() - t0) * 1000:.0f}ms)")
    return img is not None


def main():
    from core_organs.desktop_grounding import DesktopGrounding
    from core_organs import background_window as bw

    print(f"PID={os.getpid()} GDI/USER at start={gui_counts()}")
    from core_organs.organ_40_app_launcher import resolve_and_launch
    g = DesktopGrounding()
    had = g.find_window("notepad") is not None
    print(f"pre-existing notepad window: {had}")
    if not had:
        resolve_and_launch("notepad")
        end = time.time() + 12
        while time.time() < end and not g.find_window("notepad"):
            time.time()
            time.sleep(0.3)
    hwnd = g.find_window("notepad")
    if not hwnd:
        print("NOTEPAD WINDOW NOT FOUND - cannot probe")
        return 1
    print(f"hwnd={hwnd} rect={background_rect(hwnd)}\n")

    print("STATE MATRIX (fresh process, few captures):")
    u32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    time.sleep(0.5)
    report("1 on-screen (no activate) pw=0x2", hwnd)
    report("2 on-screen pw=0", hwnd, 0)

    u32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    time.sleep(0.3)
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    u32.MoveWindow(hwnd, PARK[0], PARK[1], r.right - r.left, r.bottom - r.top, False)
    time.sleep(0.6)
    report("3 parked fully off-screen", hwnd)

    bw.sliver(hwnd)
    time.sleep(0.6)
    report("4 parked + 1px sliver on-screen", hwnd)

    u32.MoveWindow(hwnd, PARK[0], PARK[1], r.right - r.left, r.bottom - r.top, False)
    time.sleep(0.5)
    u32.ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
    time.sleep(0.5)
    report("5 minimized", hwnd)

    print("\nHEAT PHASE: 120 UIA walks + 120 captures while parked (does it decay?)")
    u32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    time.sleep(0.3)
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    u32.MoveWindow(hwnd, PARK[0], PARK[1], r.right - r.left, r.bottom - r.top, False)
    time.sleep(0.5)
    ok_run = blank_run = 0
    for i in range(120):
        try:
            g._walk_uia(hwnd)
        except Exception as exc:
            print("   walk error", type(exc).__name__, exc)
        img, _ = __import__("core_organs.headless_input", fromlist=["x"]).capture_window(hwnd)
        if img is None:
            blank_run += 1
        else:
            ok_run += 1
        if i in (0, 9, 29, 59, 89, 119):
            out = raw_capture(hwnd, 0x2)
            print(f"  i={i:<4} pw={out.get('pw')} err={out.get('err')} px_mean={out.get('px_mean')} "
                  f"nonzero={out.get('nonzero_frac')} gdi={gui_counts()[0]} ok/blank={ok_run}/{blank_run}")
    u32.ShowWindow(hwnd, SW_SHOWMINNOACTIVE)
    print("\ndone")
    return 0


def background_rect(hwnd):
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


if __name__ == "__main__":
    sys.exit(main())
