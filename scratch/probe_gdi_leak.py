"""probe_gdi_leak.py -- count the process's GDI/USER objects around each capture/render path.

A window that "does not render into PrintWindow" inside a long suite process, but renders fine in a
fresh one, smells like the per-process GDI object quota being eaten by leaked objects. This measures
it per code path instead of guessing. Read-only, no app is touched.
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
H = ctypes.c_void_p
u32.GetGuiResources.argtypes = [H, wt.UINT]
u32.GetGuiResources.restype = wt.UINT
k32.GetCurrentProcess.restype = H


def counts():
    p = k32.GetCurrentProcess()
    return u32.GetGuiResources(p, 0), u32.GetGuiResources(p, 1)


def sample(label, fn, n):
    a = counts()[0]
    t0 = time.time()
    for _ in range(n):
        fn()
    b = counts()[0]
    print(f"  {label:<42} gdi {a} -> {b}  ({b - a:+d} for {n} calls, "
          f"{(time.time() - t0) / n * 1000:.1f} ms/call)")
    return b - a


def organ24_capture():
    from core_organs.organ_24_dap import WIN32
    hwnd = u32.GetDesktopWindow()
    WIN32.capture_window_bitmap_bytes(hwnd)


def headless_capture():
    from core_organs import headless_input as hin
    hin.capture_window(u32.GetDesktopWindow())


def cursor_render():
    from core_organs.visual_cursor import get_cursor
    c = get_cursor()
    c._render_frame()


if __name__ == "__main__":
    print(f"PID={sys.argv[0]} baseline gdi/user={counts()}")
    sample("organ_24.capture_window_bitmap_bytes", organ24_capture, 40)
    sample("headless_input.capture_window", headless_capture, 40)
    try:
        sample("visual_cursor._render_frame", cursor_render, 40)
    except Exception as exc:
        print("  visual_cursor path:", type(exc).__name__, exc)
    print(f"final gdi/user={counts()}")
