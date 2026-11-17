"""Probe: start an OWNED parked Blender with the scripting bridge, read its command registry, orbit / zoom / pan the 3D view through it, verify by the view state."""
import sys, time, ctypes, os, tempfile
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.professor.adapters import script_bridge as SB
from core_organs.professor import launcher as LN, state_protect as SPT
from core_organs import universal_scan as us, background_window as bw
from core_organs.atlas import scanner as SC

u = ctypes.windll.user32
cur0 = (ctypes.c_long * 2)(); u.GetCursorPos(ctypes.byref(cur0))
fg0 = u.GetForegroundWindow()
t = LN.resolve("blender")
fam, real = SB.scripting_exe(t.exe); print("exe", t.exe, "->", real, fam)
br, args = SB.ScriptBridge.prepare(tempfile.mkdtemp(prefix="hojaiga_bridge_"))
info = us.launch_hidden(real, timeout_s=90, fast=True, args=args)
h = info.get("hwnd")
print("launched", info.get("launched"), h, info.get("notes"))
try:
    if h:
        bg = bw.BackgroundSession(h); bg.__enter__()
        t0 = time.time(); print("bridge alive:", br.alive(), round(time.time() - t0, 1), "s")
        print("ping", br.request("ping"))
        reg = br.registry(); print("registry commands:", len(reg), reg[:3])
        print("state0", br.request("state"))
        for k in ("orbit", "zoom", "pan"):
            print(k, br.gesture(k))
        print("add cube:", br.execute("mesh.primitive_cube_add"), br.request("state"))
        bg.__exit__(None, None, None)
finally:
    if h:
        print("close", SC.close_owned(h))
    cur1 = (ctypes.c_long * 2)(); u.GetCursorPos(ctypes.byref(cur1))
    print("fg changed?", u.GetForegroundWindow() != fg0, "| mouse moved?", tuple(cur0) != tuple(cur1))
