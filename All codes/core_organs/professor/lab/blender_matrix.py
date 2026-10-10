"""Blender through the virtual mouse (shim route), each verb checked by Blender's own state through the scripting bridge."""
import os, sys, tempfile, time, json, ctypes, ctypes.wintypes as wt
os.environ["HOJAIGA_PROF_DIR"] = os.path.join(tempfile.gettempdir(), "hojaiga_prof_lab")
sys.path.insert(0, r"D:\new_automation"); sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.professor import pointer as PT
from core_organs.professor.lab.lab_matrix import Fx
from core_organs.professor.adapters.script_bridge import ScriptBridge
u = ctypes.WinDLL("user32", use_last_error=True)
u.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
s = json.load(open(os.path.join(os.environ["TEMP"], "hojaiga_blender_probe", "session.json")))
br = ScriptBridge(s["port"], s["token"], ""); hwnd = s["hwnd"]
origin = wt.POINT(0, 0); u.ClientToScreen(hwnd, ctypes.byref(origin))
route = sys.argv[1] if len(sys.argv) > 1 else "shim"
vp = PT.VirtualPointer(hwnd, "blender_lab", Fx(), only=[route])
def S(p): return (origin.x + p[0], origin.y + p[1])
lay = br.request("layout")["layout"][0]["areas"]
v3d = [a for a in lay if a["type"] == "VIEW_3D"][0]
objs = v3d["objects_px"]; reg = v3d["region"]
def state(): return br.request("state")
def sel(): return state()["selected"]
print("objects", objs, "region", reg)
R = {}
def rec(name, ok, extra=""): R[name] = ("OK " if ok else "-- ") + extra; print(f"  {name:22s} {R[name]}")
# click selection
vp.click(*S(objs["Camera"])); rec("click select", sel() == ["Camera"], str(sel()))
# shift-click adds
vp.click(*S(objs["Light"]), mods=("shift",)); st = sorted(sel()); rec("shift+click extend", st == ["Camera", "Light"], str(st))
# click in empty space deselects (select-box tool)
empty = (reg["x"] + 60, reg["y"] + reg["h"] - 80)
vp.click(*S(empty)); rec("click empty deselect", sel() == [] , str(sel()))
# box select (drag from empty space around Light + Camera)
L = objs["Light"]; p0 = (L[0] - 60, L[1] - 50); p1 = (L[0] + 60, L[1] + 50)
vp.drag_select(S(p0), S(p1)); st = sorted(sel()); rec("drag-select (box)", st == ["Light"], str(st))
# lasso
vp.click(*S(empty))
# orbit via middle drag
v0 = state()["view"]
vp.drag(S((reg["x"] + 400, reg["y"] + 300)), S((reg["x"] + 560, reg["y"] + 360)), button="middle"); v1 = state()["view"]
rec("middle-drag orbit", v0 != v1, f"{v0[:4]} -> {v1[:4]}")
# wheel zoom
d0 = state()["view"][4]
vp.wheel(*S((reg["x"] + 500, reg["y"] + 300)), clicks=3); d1 = state()["view"][4]
rec("wheel zoom in", d1 < d0, f"{d0} -> {d1}")
vp.wheel(*S((reg["x"] + 500, reg["y"] + 300)), clicks=-2); d2 = state()["view"][4]
rec("wheel zoom out", d2 > d1, f"{d1} -> {d2}")
# shift+middle pan
loc0 = state()["pan"]
vp.drag(S((reg["x"] + 400, reg["y"] + 300)), S((reg["x"] + 300, reg["y"] + 260)), button="middle", mods=("shift",))
rec("shift+middle pan", state()["pan"] != loc0, f"{loc0} -> {state()[chr(112)+chr(97)+chr(110)]}")
# click-drag object with the tweak? default tool is select box -> drag from object moves? skip
# right click -> context menu opens (look at screen pixels? use bridge: no) -> report delivered only
r = vp.right_click(*S(objs["Cube"])); rec("right-click delivered", r.ok, r.note[:60])
vp.click(*S(empty))  # close menu / deselect
vp.close()
print(json.dumps(R, indent=1))
