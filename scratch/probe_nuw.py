import sys, ctypes, ctypes.wintypes as wt, os
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs import background_window as bw
u32 = ctypes.windll.user32
fg = u32.GetForegroundWindow()
print("fg", fg, bw._cls(fg), "pid", bw._pid(fg), "mypid", os.getpid())
print("visible", u32.IsWindowVisible(fg), "iconic", u32.IsIconic(fg), "cls in SHELL_CLASSES", bw._cls(fg) in bw.SHELL_CLASSES)
ex = u32.GetWindowLongW(fg, -20); print("ex", hex(ex), "tool", bool(ex & 0x80), "noactivate", bool(ex & 0x08000000))
print("text", repr(bw._safe_text(fg)), "rect", bw._rect(fg), "on_real_screen", bw._on_real_screen(bw._rect(fg)))
print("SHELL_CLASSES", bw.SHELL_CLASSES)
