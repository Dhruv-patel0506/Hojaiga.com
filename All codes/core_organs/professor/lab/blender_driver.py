"""GestureDriver (the guide-step path) against the live Blender test instance: kind -> verbs -> learned routes, verified by Blender's own state."""
import os, sys, tempfile, json, time, ctypes, ctypes.wintypes as wt
os.environ["HOJAIGA_PROF_DIR"] = os.path.join(tempfile.gettempdir(), "hojaiga_prof_lab2")
sys.path.insert(0, r"D:\new_automation"); sys.path.insert(0, r"D:\new_automation\All codes")
from types import SimpleNamespace as NS
from core_organs.professor import gestures as GE, pointer as PT
from core_organs.professor.adapters.script_bridge import ScriptBridge
from core_organs.professor.lab.lab_matrix import Fx
s = json.load(open(os.path.join(os.environ["TEMP"], "hojaiga_blender_probe", "session.json")))
br = ScriptBridge(s["port"], s["token"], ""); hwnd = s["hwnd"]
u = ctypes.WinDLL("user32"); origin = wt.POINT(0, 0); u.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]; u.ClientToScreen(hwnd, ctypes.byref(origin))
lay = br.request("layout")["layout"][0]["areas"]; v3d = [a for a in lay if a["type"] == "VIEW_3D"][0]["region"]
rect = (origin.x + v3d["x"], origin.y + v3d["y"], origin.x + v3d["x"] + v3d["w"], origin.y + v3d["y"] + v3d["h"])
# one big surface node (what the tree/vision would say is the viewport)
node = NS(role="pane", ctype="PaneControl", name="3D Viewport", offscreen=False, rect=rect, enabled=True)
class BridgeNoGesture:                      # the bridge WITHOUT its scripted gesture(): forces the pointer path (digest still gives Blender's own verdict)
    digest = staticmethod(br.digest)
drv = GE.GestureDriver("blender_lab2", hwnd, Fx(), lambda: [node], scripting=BridgeNoGesture())
for kind in (sys.argv[1:] or ("orbit", "pan", "zoom", "select_area", "drag", "right_click", "double_click", "hover", "scroll")):
    r = drv.perform(kind)
    rr = wt.RECT(); u.GetWindowRect(hwnd, ctypes.byref(rr))
    print(f"{kind:13s} ok={r.ok} route={r.route} iconic={u.IsIconic(hwnd)} rect=({rr.left},{rr.top}) :: {(r.why or chr(32))[:400]}")
print("traits:", GE.load_traits("blender_lab2"))
drv.pointer().close()
