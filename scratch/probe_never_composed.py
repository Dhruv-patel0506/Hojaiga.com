"""probe_never_composed.py -- does a window that was HIDDEN FROM BIRTH ever paint into PrintWindow?

The suite launches with SW_SHOWMINNOACTIVE and parks the window off every monitor; my first probe
launched normally (the window painted on a real monitor first) and every capture succeeded. This
probe reproduces the birth-hidden case and walks the nudge ladder, printing the capture diagnostics
that headless_input now carries.
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
SW_SHOWNOACTIVATE = 4


def show(hwnd, label, g, bw):
    from core_organs import headless_input as hin
    img, note = hin.capture_window(hwnd)
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    d = hin.CAPTURE_DIAG
    print(f"  {label:<40} rect=({r.left},{r.top},{r.right},{r.bottom}) "
          f"min={bool(u32.IsIconic(hwnd))} vis={bool(u32.IsWindowVisible(hwnd))} "
          f"-> {'OK' if img else 'BLANK'} {note[:110]}")
    return img is not None


def raw_pw(hwnd, flag):
    """PrintWindow alone: does Windows say it drew (1) and did the pixels come out non-black?"""
    mdc = ctypes.windll.gdi32.CreateCompatibleDC(ctypes.windll.user32.GetDC(0))
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    bmp = ctypes.windll.gdi32.CreateCompatibleBitmap(ctypes.windll.user32.GetDC(0), w, h)
    old = ctypes.windll.gdi32.SelectObject(mdc, bmp)
    ok = ctypes.windll.user32.PrintWindow(hwnd, mdc, flag)
    err = ctypes.GetLastError()
    buf = (ctypes.c_ubyte * (w * h * 4))()

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]
    bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    rows = ctypes.windll.gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
    nz = sum(1 for b in buf[::4000] if b) / max(1, len(buf[::4000]))
    ctypes.windll.gdi32.SelectObject(mdc, old)
    ctypes.windll.gdi32.DeleteObject(bmp)
    ctypes.windll.gdi32.DeleteDC(mdc)
    return f"pw={ok} err={err} dib={rows} nonzero={nz:.3f}"


def main():
    from core_organs import background_window as bw
    from core_organs import universal_scan as us
    from core_organs import headless_input as hin

    print("launching notepad HIDDEN (the way the suite does: minimized from the first moment)")
    info = us.launch_hidden("notepad", timeout_s=40)
    hwnd = int(info.get("hwnd") or 0)
    print(f"  launched={info.get('launched')} hwnd={hwnd} notes={str(info.get('notes'))[:120]}")
    if not hwnd:
        print("no window -> cannot probe")
        return 1
    time.sleep(1.0)

    try:
        show(hwnd, "A born-minimized", None, bw)
        with bw.BackgroundSession(hwnd) as bg:
            print(f"  BackgroundSession mode={bg.mode}")
            show(hwnd, "B parked off every monitor", None, bw)
            ok = show(hwnd, "C parked, after 3s wait", None, bw)
            if not ok:
                bw.sliver(hwnd)
                time.sleep(1.2)
                show(hwnd, "D parked + 1px sliver on-screen", None, bw)
            if not ok:
                # nudge with a shallow UIA read (the existing _await_paint trick)
                try:
                    hin_walk = __import__("core_organs.desktop_grounding", fromlist=["x"]).DesktopGrounding()
                    hin_walk._walk_uia(hwnd)
                except Exception as exc:
                    print("   uia nudge error", type(exc).__name__, exc)
                time.sleep(1.0)
                show(hwnd, "E parked + UIA tree read", None, bw)
            show(hwnd, "F parked, attempt after the nudges", None, bw)
            print("   plain WM_PRINT (flag=0) on the parked window:", raw_pw(hwnd, 0), "| RENDERFULLCONTENT:", raw_pw(hwnd, 2))
        # now let it compose for real, once, on a monitor (no activation)
        r = wt.RECT()
        u32.GetWindowRect(hwnd, ctypes.byref(r))
        u32.SetWindowPos(hwnd, 0, 40, 40, r.right - r.left, r.bottom - r.top,
                         0x1 | 0x4 | 0x10)   # NOSIZE|NOZORDER|NOACTIVATE kept off; size used from rect
        u32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        time.sleep(1.5)
        show(hwnd, "G composed once on a real monitor", None, bw)
        with bw.BackgroundSession(hwnd):
            time.sleep(0.8)
            show(hwnd, "H re-parked AFTER having composed", None, bw)
    finally:
        print("closing the Notepad we launched")
        u32.PostMessageW(hwnd, 0x0010, 0, 0)
        time.sleep(1.0)
    print(f"blank log entries this session: {len(hin.CAPTURE_LOG)}")
    for e in hin.CAPTURE_LOG[-3:]:
        print("   ", {k: v for k, v in e.items() if k in ("pw", "err", "dib", "obj", "px", "where", "rect")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
