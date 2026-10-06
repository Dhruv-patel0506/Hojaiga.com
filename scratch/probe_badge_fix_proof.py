"""P0-B proof: does the overlay's badge loop still walk the process to the GDI cap?

Before (traced suite prefix, 2026-10-05): 4,154 live fonts from visual_cursor._draw_badge,
process 1 -> 4,206 handles in 34 tests, captures going blank once the ~10,000 cap is reached.

This runs the REAL overlay with a badge for ~12 s (roughly 700 frames) plus a sprite, then
captures a parked Notepad 60 times and reports whether the pixels are still there -- i.e. whether
the eyes stay open while the cursor thread works, which is exactly what the suite lost.
"""
import os
import sys
import time

os.environ.setdefault("HOJAIGA_GDI_TRACE", "1")
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs import gdi_budget_trace as gbt          # noqa: E402

gbt.install(force=True)

from core_organs import headless_input as hin            # noqa: E402
from core_organs.visual_cursor import get_cursor, for_agent, release_agent   # noqa: E402


def gui():
    return hin._gui_objects()


def cursor_soak(secs=12.0):
    vc = get_cursor()
    vc.show()
    vc._visible = True
    vc._show_state_badge = True
    vc._active_state = "MOVING"
    vc._fly_label = "MOVING"
    spr = for_agent("hj_probe_spr", "ProbeSprite")
    g0 = gui()
    t0 = time.time()
    frames = 0
    while time.time() - t0 < secs:
        # keep the cursor and the sprite visibly active so the badge path runs every frame
        vc._x = vc._target_x = 300 + 80 * (1 if int(time.time() * 4) % 2 else -1)
        vc._y = vc._target_y = 300
        spr._x = spr._target_x = 500.0
        spr._y = spr._target_y = 500.0
        spr._visible = True
        time.sleep(0.05)
        frames += 1
    g1 = gui()
    release_agent("hj_probe_spr")
    print(f"overlay soak {secs:.0f}s: gdi/user {g0} -> {g1}  (font handles live now: {gbt.live_count()})")
    return g1


def capture_check(captures=60):
    """The thing the suite lost: capture must return real pixels after the cursor thread worked."""
    import subprocess
    from core_organs import background_window as bw
    p = subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    hwnd = 0
    import ctypes
    u = ctypes.windll.user32

    def cb(h, _):
        nonlocal hwnd
        if not hwnd and u.IsWindowVisible(h) and hin.window_pid(h) == p.pid:
            hwnd = h
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    u.EnumWindows(WNDENUMPROC(cb), 0)
    if not hwnd:
        print("NO NOTEPAD HWND -- cannot check capture")
        return
    blanks = 0
    notes = []
    minfrac = 1.0
    with bw.BackgroundSession(hwnd):
        for _ in range(captures):
            img, reason = hin.capture_window(hwnd)
            if img is None:
                blanks += 1
                notes.append(reason)
                continue
            w, h2 = img.size
            px = list(img.getdata())
            nz = sum(1 for q in px if q[:3] != (0, 0, 0))
            minfrac = min(minfrac, nz / max(1, w * h2))
            time.sleep(0.01)
    print(f"captures={captures} blanks={blanks} min_nonzero_pixel_fraction={minfrac:.4f} "
          f"notes={sorted(set(notes))[:3]}")
    try:
        p.terminate()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    print("baseline gdi/user:", gui())
    after = cursor_soak()
    capture_check()
    print("after everything gdi/user:", gui())
    print(gbt.report(8))
    print("EYE JUDGEMENT:", "handles still climbing -> leak remains"
          if after[0] > 400 else "flat budget -> capture stays honest")
