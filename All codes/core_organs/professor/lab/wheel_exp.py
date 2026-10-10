import os, sys, tempfile, time, ctypes, ctypes.wintypes as wt
os.environ["HOJAIGA_PROF_DIR"] = os.path.join(tempfile.gettempdir(), "hojaiga_prof_lab")
sys.path.insert(0, r"D:\new_automation"); sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.professor import pointer as PT
from core_organs.professor.lab.labkit import Lab, client_origin
from core_organs.professor.lab.lab_matrix import Fx
u = ctypes.WinDLL("user32", use_last_error=True)
u.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
lab = Lab("wpf"); h = lab.hwnd; ox, oy = client_origin(h)
vp = PT.VirtualPointer(h, "x", Fx(), only=["shim"])
vp.hover(ox + 200, oy + 160)
ag = vp.agent
sx, sy = ox + 200, oy + 160
def wheel(label, wp, lp, pre_move=True):
    m = lab.mark()
    ag.set(sx, sy, 0, 0, 1.0, h)
    if pre_move:
        u.PostMessageW(h, 0x200, 0, PT._lp(200, 160)); time.sleep(0.05)
    u.PostMessageW(h, 0x20A, wp, lp); time.sleep(0.4)
    print(label, [e["kind"] for e in lab.since(m)])
wheel("screen lParam", (120 << 16), PT._lp(sx, sy))
wheel("client lParam", (120 << 16), PT._lp(200, 160))
wheel("delta 240", (240 << 16), PT._lp(sx, sy))
wheel("no premove", (120 << 16), PT._lp(sx, sy), False)
# many wheel notches
m = lab.mark()
for i in range(5):
    u.PostMessageW(h, 0x20A, (120 << 16), PT._lp(sx, sy)); time.sleep(0.05)
time.sleep(0.5); print("5 notches", [e["kind"] for e in lab.since(m)])
# horizontal
m = lab.mark(); u.PostMessageW(h, 0x20E, (120 << 16), PT._lp(sx, sy)); time.sleep(0.4); print("hwheel", [e["kind"] for e in lab.since(m)])
vp.close(); lab.close()
