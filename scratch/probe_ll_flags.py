"""Verify pointer_sentinel's LLMHF_INJECTED constant, and measure what the flags on the
phantom events actually are while the machine is untouched (cursor frozen, desktop frozen).
Read-only. Zero input."""
import ctypes, ctypes.wintypes as wt, time
from collections import Counter
u = ctypes.windll.user32; k = ctypes.windll.kernel32
class MS(ctypes.Structure):
    _fields_=[("pt",wt.POINT),("mouseData",wt.DWORD),("flags",wt.DWORD),("time",wt.DWORD),("dwExtraInfo",ctypes.c_size_t)]
HP = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wt.WPARAM, ctypes.POINTER(MS))
u.SetWindowsHookExW.argtypes=[ctypes.c_int, HP, ctypes.c_void_p, wt.DWORD]
u.SetWindowsHookExW.restype=ctypes.c_void_p
u.CallNextHookEx.argtypes=[ctypes.c_void_p, ctypes.c_int, wt.WPARAM, ctypes.c_void_p]
u.CallNextHookEx.restype=ctypes.c_long
rows=[]; stop=[False]; t0=k.GetTickCount()
def proc(code,w,l):
    if code>=0 and not stop[0]:
        st=ctypes.cast(l,ctypes.POINTER(MS)).contents
        rows.append(((st.time-t0)/1000.0, w, st.pt.x, st.pt.y, st.flags, st.dwExtraInfo))
    return u.CallNextHookEx(None, code, w, l)
ref=HP(proc)
# WH_MOUSE_LL=14; hMod must be NULL for a global hook (a non-NULL module handle gives ERROR_MOD_NOT_FOUND 126)
h=u.SetWindowsHookExW(14, ref, None, 0)
print("hook handle:", h, "gle:", k.GetLastError())
msg=wt.MSG()
end=time.time()+12
while time.time()<end:
    while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
        u.TranslateMessage(ctypes.byref(msg)); u.DispatchMessageW(ctypes.byref(msg))
    time.sleep(0.002)
stop[0]=True
u.UnhookWindowsHookEx(h)
print("events in 12 s:", len(rows), " rate/s:", round(len(rows)/12.0,1))
print("flag histogram:", Counter(r[4] for r in rows).most_common(8))
print("extraInfo histogram:", Counter(r[5] for r in rows).most_common(4))
INJ_REAL=0x10; INJ_WRONG=0x01
print("bit 0x10 (MSLLHF_INJECTED) set on :", sum(1 for r in rows if r[4]&INJ_REAL), "/", len(rows))
print("bit 0x01 (what the sentinel tests) set on:", sum(1 for r in rows if r[4]&INJ_WRONG), "/", len(rows))
for r in rows[:10]:
    print("   t=%6.3f msg=%s (%d,%d) flags=%#x extra=%#x" % (r[0], hex(r[1]), r[2], r[3], r[4], r[5]))
