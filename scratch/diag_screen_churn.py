"""Why do PIX1/PAR1 keep getting ABORTED-ENV while the user says they are idle?

Two separate questions, measured over ~20 s of an untouched machine:
  1. WHAT is changing the composed desktop? (PIX1's idle-noise gate fires at 3857-6542 px)
     -> diff full-resolution frames and report the bounding box + size of the changed region.
  2. WHO is moving the pointer? (the sentinel says 'human-hand' but reports 145 px in 6 ms, which a
     hand does not do; it only means "not injected by us")
     -> a low-level mouse hook that records each HWMDATA (time, flags, LLMHF_INJECTED, extra_info)
        and which process owns the window under the cursor at that moment.

Read-only. Zero input. Run: python -X utf8 -u scratch/diag_screen_churn.py
"""
import ctypes
import ctypes.wintypes as wt
import threading
import time
from collections import Counter

from PIL import ImageGrab

user32 = ctypes.windll.user32
kern32 = ctypes.windll.kernel32

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_MOUSEMOVE = 0x0200
WM_MOUSEWHEEL = 0x020A
WH_MOUSE_LL = 14
LLMHF_INJECTED = 0x00000010
LLMHF_LOWER_IL_INJECTED = 0x00000002


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_void_p)]


WM_RBUTTONUP = 0x0205
HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wt.WPARAM, ctypes.POINTER(MSLLHOOKSTRUCT))

_rows = []          # (perf_counter, msg, x, y, flags, extra_info)
_stop = [False]
_tick0 = kern32.GetTickCount()


def _owner_at(x, y):
    """(pid, class, title) of the window under a pointer event - who is the cursor on top of."""
    pt = wt.POINT(x, y)
    h = user32.WindowFromPoint(pt)
    if not h:
        return (0, "", "")
    root = user32.GetAncestor(h, 2) or h        # GA_ROOT
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(root, ctypes.byref(pid))
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(root, buf, 256)
    ttl = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(root, ttl, 256)
    return (pid.value, buf.value, ttl.value)


def _proc(code, wparam, lparam):
    if code >= 0 and not _stop[0]:
        st = lparam.contents
        dt = (st.time - _tick0) / 1000.0
        _rows.append((dt, wparam, st.pt.x, st.pt.y, st.flags, st.dwExtraInfo or 0))
    return user32.CallNextHookEx(0, code, wparam, lparam)


_proc_ref = HOOKPROC(_proc)


def hook_thread():
    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, _proc_ref, kern32.GetModuleHandleW(None), 0)
    if not hook:
        print("[hook] SetWindowsHookExW failed, gle=", kern32.GetLastError())
        return
    msg = wt.MSG()
    while not _stop[0]:
        while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.001)
    user32.UnhookWindowsHookEx(hook)


# ---------------------------------------------------------------- screen churn
def grab():
    return ImageGrab.grab(all_screens=True).convert("RGB")


def churn():
    print("[1] composed-desktop churn over 12 s (two frames 1 s apart, full resolution)")
    a = grab()
    print("    desktop size:", a.size)
    for i in range(6):
        time.sleep(1.0)
        b = grab()
        if a.size != b.size:
            print(f"    frame {i}: RESOLUTION CHANGED {a.size} -> {b.size}")
            a = b
            continue
        from PIL import ImageChops
        d = ImageChops.difference(a, b)
        bbox = d.getbbox()
        # count pixels whose max channel delta exceeds 24 (a real change, not dither)
        hist = d.convert("L").point(lambda v: 255 if v > 24 else 0).histogram()
        px = hist[255]
        tot = a.width * a.height
        print(f"    frame {i}: changed_px={px} ({100.0*px/max(tot,1):.4f}%) bbox={bbox}"
              + ("" if not bbox else f" bbox_area={bbox[2]-bbox[0]}x{bbox[3]-bbox[1]}"))
        a = b


# ---------------------------------------------------------------- pointer events
def pointer():
    print("\n[2] low-level mouse hook over 12 s - every pointer event, injected or not")
    th = threading.Thread(target=hook_thread, daemon=True)
    th.start()
    time.sleep(12.0)
    _stop[0] = True
    time.sleep(0.3)
    print(f"    total events: {len(_rows)}")
    if not _rows:
        print("    NO pointer events at all while idle -> the sentinel's 'human-hand' count is NOT the mouse")
        return
    names = {WM_MOUSEMOVE: "MOVE", WM_LBUTTONDOWN: "LB.DOWN", WM_LBUTTONUP: "LB.UP",
             WM_RBUTTONDOWN: "RB.DOWN", WM_RBUTTONUP: "RB.UP", WM_MOUSEWHEEL: "WHEEL"}
    inj = sum(1 for r in _rows if r[4] & LLMHF_INJECTED)
    print(f"    LLMHF_INJECTED set on {inj}/{len(_rows)} events")
    # jumps: a move that teleports further than a hand can in the elapsed time
    moves = [r for r in _rows if r[1] == WM_MOUSEMOVE]
    prev = None
    fast = 0
    for r in moves[:200]:
        if prev:
            dd = ((r[2] - prev[2]) ** 2 + (r[3] - prev[3]) ** 2) ** 0.5
            dtt = max(r[0] - prev[0], 1e-4)
            if dd / dtt > 5000:                       # px/s, well beyond a hand
                fast += 1
        prev = r
    print(f"    moves faster than 5000 px/s: {fast}")
    print("    first 12 events:")
    for r in _rows[:12]:
        pid, cls, ttl = _owner_at(r[2], r[3])
        print(f"      t={r[0]:7.3f} {names.get(r[1], hex(r[1])):8s} ({r[2]},{r[3]}) "
              f"flags={r[4]:#x} extra={r[5]:#x} -> pid={pid} [{cls}] '{ttl[:40]}'")
    owners = Counter(_owner_at(r[2], r[3])[:2] for r in _rows)
    print("    top window-under-cursor:", owners.most_common(5))
    ids = Counter(r[5] for r in _rows)
    print("    distinct dwExtraInfo values:", len(ids), ids.most_common(4))


if __name__ == "__main__":
    churn()
    pointer()
    print("\ndone. A 'human-hand' ABORTED-ENV is only honest if a hand made these events.")
