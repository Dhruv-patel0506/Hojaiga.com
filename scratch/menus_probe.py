import sys, time, tempfile, json
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.professor.adapters import script_bridge as SB
from core_organs.professor import launcher as LN
from core_organs import universal_scan as us, background_window as bw
from core_organs.atlas import scanner as SC
t = LN.resolve("blender"); fam, real = SB.scripting_exe(t.exe)
br, args = SB.ScriptBridge.prepare(tempfile.mkdtemp(prefix="hojaiga_bridge_"))
info = us.launch_hidden(real, timeout_s=90, fast=True, args=args); h = info.get("hwnd")
try:
    bg = bw.BackgroundSession(h); bg.__enter__(); br.alive()
    m = br.request("menus", timeout=90.0)
    print("ok", m.get("ok"), m.get("error"), "menus:", len(m.get("menus", {})))
    verbs = SB.menu_verbs(m.get("menus", {}))
    print("menu verbs:", len(verbs))
    for v in verbs:
        if v.path and v.path[0] in ("File", "Edit") and len(v.path) == 1: print("  ", v.path, v.label, v.aid)
    json.dump(m.get("menus", {}), open(r"D:\new_automation\data\professor\vendor_ui\cache\blender.menus.json", "w", encoding="utf-8"))
    bg.__exit__(None, None, None)
finally:
    SC.close_owned(h)
