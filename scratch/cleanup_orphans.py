"""cleanup_orphans.py -- close ONLY the app windows Hojaiga parked off every monitor.

A suite run killed mid-test leaves its windows behind wherever the park put them (PARK_X/PARK_Y,
around -24000). Those orphans poison the next run (E2E-2 refuses to drive a Paint that is already
open; B2X counts every new window in the session). Anything sitting on a real monitor - including a
minimised window - is LEFT ALONE and only reported, because that one may be the user's.
"""
import ctypes
import ctypes.wintypes as wt
import sys

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

u32 = ctypes.windll.user32
INTEREST = ("notepad", "paint", "excel", "word", "calculator", "notepadex")


def info(h):
    r = wt.RECT()
    u32.GetWindowRect(h, ctypes.byref(r))
    cls = ctypes.create_unicode_buffer(128)
    u32.GetClassNameW(h, cls, 128)
    t = ctypes.create_unicode_buffer(256)
    u32.GetWindowTextW(h, t, 256)
    return cls.value, t.value, (r.left, r.top, r.right, r.bottom)


def main():
    from core_organs import universal_scan as us
    from core_organs import background_window as bw

    parked, onscreen = [], []
    for h in list(bw._parked or []):
        if u32.IsWindow(h):
            parked.append(h)

    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _l):
        cls, title, rect = info(h)
        if not any(k in cls.lower() for k in INTEREST) and not any(k in title.lower() for k in INTEREST):
            return True
        off = rect[0] < -1000 or rect[1] < -1000
        found.append((int(h), cls, title, rect, off, bool(u32.IsIconic(h)), bool(u32.IsWindowVisible(h))))
        return True

    u32.EnumWindows(cb, 0)
    print(f"registered-in-park list: {len(parked)} live hwnd(s)")
    if not found:
        print("no app windows of the interesting classes at all")
        return 0
    for h, cls, title, rect, off, iconic, vis in found:
        tag = "OFF-PARK (ours)" if off else "on a real monitor (leave alone)"
        print(f"  hwnd={h} class={cls!r} title={title!r} rect={rect} min={iconic} vis={vis} -> {tag}")
    closed = 0
    for h, cls, title, rect, off, iconic, vis in found:
        if not off:
            continue
        try:
            if us.close_window(h, timeout_s=5.0, discard_unsaved=True):
                closed += 1
                print(f"  closed orphan hwnd={h} ({title!r})")
            else:
                print(f"  close_window refused hwnd={h} ({title!r})")
        except Exception as exc:
            print(f"  close error hwnd={h}: {type(exc).__name__}: {exc}")
    print(f"orphans closed: {closed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
