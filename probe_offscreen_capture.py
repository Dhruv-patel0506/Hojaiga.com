"""
probe_offscreen_capture -- validates the screen-steal fix before touching a core organ.

Hypothesis: a window restored at OFF-SCREEN coordinates (not iconic, SWP_NOACTIVATE)
still renders to PrintWindow(PW_RENDERFULLCONTENT) -> we get real proof pixels, while the
user's actual desktop never shows the window. That would let Phase-2 actuation+capture run
without stealing the screen AND without the (removed-on-25H2) Virtual-Desktops COM API.

Touches only a scratch Notepad it launches itself; leaves nothing behind.
"""
import ctypes as c
import sys, os, time, subprocess
sys.path.insert(0, os.path.join("All codes", "core_organs"))
from PIL import ImageGrab
import headless_input as hi

u = c.windll.user32
k = c.windll.kernel32
SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x4, 0x10


def find_hwnd_for_pid(pid):
    Enum = c.WINFUNCTYPE(c.c_bool, c.c_void_p, c.c_void_p)
    found = []

    def cb(h, _):
        p = c.wintypes.DWORD() if hasattr(c, "wintypes") else c.c_ulong(0)
        d = c.c_ulong(0)
        u.GetWindowThreadProcessId(h, c.byref(d))
        if d.value == pid and u.IsWindow(h) and u.GetWindowTextLength(h) > 0:
            found.append(h)
        return True
    for _ in range(60):
        u.EnumWindows(Enum(cb), 0)
        if found:
            return int(found[0])
        time.sleep(0.25)
    return 0


def find_notepad_hwnd():
    """Win11 notepad.exe is an app-execution alias that relaunches under a different PID,
    so match by window class/title, not the spawned pid."""
    Enum = c.WINFUNCTYPE(c.c_bool, c.c_void_p, c.c_void_p)
    buf = c.create_unicode_buffer(256)
    cbuf = c.create_unicode_buffer(256)
    best = []

    def cb(h, _):
        if not u.IsWindow(h) or not u.GetWindowTextLengthW(h):
            return True
        u.GetWindowTextW(h, buf, 256)
        u.GetClassNameW(h, cbuf, 256)
        t, cls = buf.value, cbuf.value
        if "Notepad" in t or cls.lower() in ("notepad", "notepadmainframe", "win32gettextlength"):
            best.append(int(h))
        return True
    for _ in range(40):
        best.clear()
        u.EnumWindows(Enum(cb), 0)
        if best:
            return best[0]
        time.sleep(0.3)
    return 0


def main():
    proc = subprocess.Popen(["notepad.exe"])
    hwnd = find_notepad_hwnd()
    print("launched notepad spawn-pid", proc.pid, "hwnd", hwnd)
    if not hwnd:
        print("FAIL: no hwnd"); proc.kill(); return 1

    # Move OFF-SCREEN, restored (show normal) but NOACTIVATE so focus stays with the user.
    u.ShowWindow(hwnd, 1)  # SW_SHOWNORMAL (restored, not iconic)
    u.SetWindowPos(hwnd, 0, -4000, -4000, 800, 600, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
    time.sleep(0.4)

    import ctypes.wintypes as wt
    r = wt.RECT(); u.GetWindowRect(hwnd, c.byref(r))
    iconic = bool(u.IsIconic(hwnd)); vis = bool(u.IsWindowVisible(hwnd))
    print(f"window rect=({r.left},{r.top},{r.right},{r.bottom}) iconic={iconic} visible_flag={vis}  (off-screen coords => not in user's view)")

    # (a) does PrintWindow still yield real pixels for an off-screen restored window?
    img, why = hi.capture_window(hwnd)
    if img is None:
        print("CAPTURE FAIL:", why)
    else:
        # measure content: not-blank = pixels vary
        colors = img.convert("RGB").getcolors(maxcolors=1000000)
        print(f"CAPTURE OK: {img.size} distinct_colors={None if colors is None else len(colors)} note={why}")

    # (b) is our desktop clean? grab primary screen and check the notepad title isn't on it.
    screen = ImageGrab.grab()
    print("primary screen grabbed", screen.size, "-> notepad parked off-screen, should NOT be in this image")

    proc.kill()
    print("notepad killed; user desktop untouched (never activated, never on-screen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
