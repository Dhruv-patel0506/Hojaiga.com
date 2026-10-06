"""Does the thread-patched GDI tracer see handles allocated on a BACKGROUND thread?

The first version of gdi_budget_trace only wrapped the installing thread's ctypes.windll
instances (windll loaders are thread-local since Python 3.3), so it reported "0 allocations
seen" for a run whose leaker was a worker thread -- a meter that reads zero is worse than no
meter. This asserts the patch actually covers threads started after install().
"""
import ctypes
import os
import sys
import threading
import time

os.environ["HOJAIGA_GDI_TRACE"] = "1"
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs import gdi_budget_trace as gbt      # noqa: E402

assert gbt.install(force=True), "install should report True"

N = 40
keep = []


def worker():
    g32 = ctypes.windll.gdi32
    u32 = ctypes.windll.user32
    hdc = g32.CreateCompatibleDC(None)
    for _ in range(N):
        bmp = g32.CreateCompatibleBitmap(hdc, 8, 8)          # never deleted -> must show as live
        if bmp:
            keep.append(bmp)
    # a background-thread delete must also be understood
    if keep:
        g32.DeleteObject(keep[0])


def timer_thread():
    g32 = ctypes.windll.gdi32
    for _ in range(5):
        h = g32.CreateSolidBrush(0x00FF00)
        g32.DeleteObject(h)


t = threading.Thread(target=worker, name="gbt-worker")
t.start()
t.join()
t2 = threading.Thread(target=timer_thread, name="gbt-timer")
t2.start()
t2.join()

rep = gbt.report(6)
print(rep)
print("main-thread seen:", gbt._created)
live = gbt.live_count()
print(f"EXPECTED ~{N-1} live (held bitmaps minus the one deleted on the worker thread), got {live}")
assert live >= N - 2, "background-thread allocations were NOT traced (thread patch ineffective)"
print("THREAD TRACE OK")
