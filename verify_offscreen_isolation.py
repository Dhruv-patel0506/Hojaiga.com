"""verify_offscreen_isolation.py -- prove rung-3 capture no longer flashes on the user's screen."""
import ctypes as c
import ctypes.wintypes
import sys, os, time, subprocess
sys.path.insert(0, os.path.join("All codes", "core_organs"))
import headless_input as hi
from PIL import ImageGrab

u = c.windll.user32
SW_SHOWNOACTIVATE, SW_MINIMIZE = 4, 6


def find_win(substr):
    Enum = c.WINFUNCTYPE(c.c_bool, c.c_void_p, c.c_void_p)
    buf = c.create_unicode_buffer(256); out = []
    def cb(h, _):
        if u.IsWindow(h) and u.GetWindowTextLengthW(h):
            u.GetWindowTextW(h, buf, 256)
            if substr.lower() in buf.value.lower():
                out.append(int(h))
        return True
    for _ in range(40):
        out.clear(); u.EnumWindows(Enum(cb), 0)
        if out: return out[0]
        time.sleep(0.2)
    return 0


def main():
    proc = subprocess.Popen(["notepad.exe"])
    hwnd = find_win("Notepad")
    print("hwnd", hwnd)
    if not hwnd:
        proc.kill(); return 1

    # Put it in the state the real ladder sees: MINIMIZED.
    u.ShowWindow(hwnd, SW_MINIMIZE); time.sleep(0.3)
    print("start iconic=", bool(u.IsIconic(hwnd)))

    # Rung-3 capture (uses the off-screen-patched _restore_capture_rehide).
    img, note, rung = hi.capture_window_robust(hwnd)
    r = c.wintypes.RECT(); u.GetWindowRect(hwnd, c.byref(r))
    colors = img.convert("RGB").getcolors(maxcolors=1000000) if img else None
    print(f"CAPTURE: img={'yes' if img else 'no'} rung={rung} distinct_colors={len(colors) if colors else 0}")
    print(f"post-capture rect=({r.left},{r.top},{r.right},{r.bottom}) iconic={bool(u.IsIconic(hwnd))} (state restored to minimized: {bool(u.IsIconic(hwnd))})")

    # Prove the user's screen never showed it: grab desktop while we now isolate for actuation.
    hi.isolate_offscreen(hwnd); time.sleep(0.3)
    r2 = c.wintypes.RECT(); u.GetWindowRect(hwnd, c.byref(r2))
    print(f"isolated rect=({r2.left},{r2.top},{r2.right},{r2.bottom}) offscreen={r2.right < 0}")
    screen = ImageGrab.grab()
    print("primary desktop grabbed", screen.size, "(notepad must not appear)")

    hi.release_isolation(hwnd); time.sleep(0.2)
    r3 = c.wintypes.RECT(); u.GetWindowRect(hwnd, c.byref(r3))
    print(f"released rect=({r3.left},{r3.top}) iconic={bool(u.IsIconic(hwnd))}")
    proc.kill()
    print("done; user desktop never showed the window during capture+isolation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
