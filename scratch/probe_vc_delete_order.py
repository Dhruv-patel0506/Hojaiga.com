"""Measure: does visual_cursor's per-frame delete order leak a GDI handle?

Replicates the exact sequence in _render_frame: GetDC(0) -> CreateCompatibleDC ->
CreateDIBSection -> SelectObject -> draw -> [finally] DeleteObject(hbmp); DeleteDC(mem);
ReleaseDC(screen). A DIB that is STILL SELECTED when DeleteObject runs cannot be deleted
(API returns 0), and DeleteDC does not free the bitmap it was holding -> one leak per frame.
"""
import ctypes
import time

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32          # default restype (c_int) -> the -1 pseudo handle, which converts fine

_H = ctypes.c_void_p
for _lib, _name, _args, _res in [
    (user32, "GetDC", [_H], _H),
    (user32, "ReleaseDC", [_H, _H], ctypes.c_int),
    (user32, "GetGuiResources", [_H, ctypes.c_uint], ctypes.c_uint),
    (gdi32, "CreateCompatibleDC", [_H], _H),
    (gdi32, "CreateDIBSection", [_H, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(_H), ctypes.c_void_p, ctypes.c_uint], _H),
    (gdi32, "SelectObject", [_H, _H], _H),
    (gdi32, "CreatePen", [ctypes.c_int, ctypes.c_int, ctypes.c_uint], _H),
    (gdi32, "DeleteObject", [_H], ctypes.c_int),
    (gdi32, "DeleteDC", [_H], ctypes.c_int),
    (gdi32, "Ellipse", [_H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int),
]:
    getattr(_lib, _name).argtypes = _args
    getattr(_lib, _name).restype = _res


kernel32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
kernel32.OpenProcess.restype = _H
kernel32.CloseHandle.argtypes = [_H]
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SELF_PID = ctypes.windll.kernel32.GetCurrentProcessId()


def gui(kind):
    """REAL count for this process. Passing the -1 pseudo-handle makes GetGuiResources fail and
    return 0 (which reads as 'perfect, nothing outstanding') -- an availability process handle is
    the only honest way to measure our own budget."""
    ph = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, _SELF_PID)
    if not ph:
        return -1
    try:
        return int(user32.GetGuiResources(ph, kind))
    finally:
        kernel32.CloseHandle(ph)


class BMI(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


def frame(deselect_first: bool, w=1024, h=768, leak_dc: bool = False):
    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    bmi = BMI()
    bmi.biSize = ctypes.sizeof(BMI)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    ppv = _H()
    hbmp = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(ppv), None, 0)
    old = gdi32.SelectObject(hdc_mem, hbmp)
    pen = gdi32.CreatePen(0, 1, 0x00FF00)
    old_pen = gdi32.SelectObject(hdc_mem, pen)
    gdi32.Ellipse(hdc_mem, 10, 10, 40, 40)
    gdi32.SelectObject(hdc_mem, old_pen)
    gdi32.DeleteObject(pen)
    if deselect_first:
        gdi32.SelectObject(hdc_mem, old)          # put the surface back before deleting
    del_obj_ok = gdi32.DeleteObject(hbmp)
    del_dc_ok = 1 if leak_dc else gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)
    return int(del_obj_ok), int(del_dc_ok), int(bool(hbmp)), int(bool(hdc_screen))


def run(label, deselect_first, n=200, leak_dc=False):
    g0, u0 = gui(0), gui(1)
    ok_fail = 0
    made_bmp = 0
    made_dc = 0
    t = time.time()
    for _ in range(n):
        do, ddc, bmp, sdc = frame(deselect_first, leak_dc=leak_dc)
        ok_fail += 1 if do == 0 else 0
        made_bmp += 1 if bmp else 0
        made_dc += 1 if sdc else 0
    g1, u1 = gui(0), gui(1)
    print(f"{label:<28} gdi {g0}->{g1} ({g1-g0:+d})  user {u0}->{u1} ({u1-u0:+d})  "
          f"DeleteObject refused {ok_fail}/{n}  dib_created {made_bmp}/{n}  screen_dc {made_dc}/{n}  "
          f"{time.time()-t:.1f}s")
    return g1 - g0


def control(n=300):
    """Meter validation: hold n DIBs alive, the count must rise by n, then fall back on release."""
    hdc = gdi32.CreateCompatibleDC(None)
    g0 = gui(0)
    keep = []
    bmi = BMI()
    bmi.biSize = ctypes.sizeof(BMI)
    bmi.biWidth, bmi.biHeight, bmi.biPlanes, bmi.biBitCount = 16, 16, 1, 32
    for _ in range(n):
        ppv = _H()
        h = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(ppv), None, 0)
        if h:
            keep.append(h)
    g1 = gui(0)
    pseudo_loaded = int(user32.GetGuiResources(kernel32.GetCurrentProcess(), 0))
    print(f"METER CHECK UNDER LOAD ({n} held): OpenProcess={g1}  pseudo-handle={pseudo_loaded} "
          f"-> {'both agree' if g1 == pseudo_loaded else 'PSEUDO HANDLE READS WRONG'}")
    for h in keep:
        gdi32.DeleteObject(h)
    gdi32.DeleteDC(hdc)
    print(f"CONTROL (hold {n} DIBs)     gdi {g0}->{g1} ({g1-g0:+d} for {len(keep)} held) -> back to {gui(0)}")
    pseudo = int(user32.GetGuiResources(kernel32.GetCurrentProcess(), 0))
    print(f"METER CHECK: OpenProcess handle says {gui(0)}, GetCurrentProcess() pseudo-handle says {pseudo}"
          f" -> {'pseudo works' if gui(0) == pseudo else 'PSEUDO HANDLE FAILS (reads 0 = looks clean)'}")


if __name__ == "__main__":
    print("screen", user32.GetSystemMetrics(0), "x", user32.GetSystemMetrics(1))
    control()
    a = run("visual_cursor order (as-is)", False, n=1000)
    b = run("deselect before delete", True, n=1000)
    c = run("no DeleteDC (deliberate leak)", False, n=100, leak_dc=True)
    print("VERDICT:", "LEAK in the current order" if a > 10 else "no leak from delete order")
