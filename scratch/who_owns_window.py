"""Read-only: what does _user_has() actually match, and who owns that window?
No windows are touched, no apps launched."""
import sys, ctypes
sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import headless_input as hin
from core_organs import background_window as bw
from core_organs import si_tests_knowledge as stk

u32 = ctypes.windll.user32
u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
u32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
ps = ctypes.c_uint()

for sub in ("notepad", "paint", "calculator"):
    print(f"=== _user_has({sub!r}) -> {stk._user_has(sub)!r}")
    for h, t in hin.top_level_titles(False):
        if sub in (t or "").lower():
            u32.GetWindowThreadProcessId(ctypes.c_void_p(h), ctypes.byref(ps))
            cls = ctypes.create_unicode_buffer(256)
            u32.GetClassNameW(ctypes.c_void_p(h), cls, 256)
            print(f"    hwnd={h} pid={ps.value} vis={bool(u32.IsWindowVisible(h))} "
                  f"iconic={bool(u32.IsIconic(h))} cls={cls.value!r} title={t!r} "
                  f"ours={bw.is_ours(h)}")
    print("    ours_alive:", list(bw.ours_alive()))
