"""The extended Blender bridge: panels (settings with their paths), file commands inside the sandbox only, setting values, preconditions. Launches its own parked, throw-away instance."""
import sys, time, ctypes, ctypes.wintypes as wt, os, subprocess, json, tempfile, shutil
sys.path.insert(0, r"D:\new_automation"); sys.path.insert(0, r"D:\new_automation\All codes")
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
from core_organs.professor.adapters import script_bridge as SB
from core_organs.professor import dialogs as DG

KEEP = "--keep" in sys.argv
SAND = tempfile.mkdtemp(prefix="hojaiga_bpr_")
sb = DG.Sandbox("blender_probe", "t1", root=os.path.join(SAND, "sandbox"))
br, args = SB.ScriptBridge.prepare(os.path.join(SAND, "bridge"), "python-startup", sb.root)
cfg = os.path.join(SAND, "cfg")
env = dict(os.environ, BLENDER_USER_CONFIG=cfg, BLENDER_USER_SCRIPTS=os.path.join(SAND, "scripts"), BLENDER_USER_DATAFILES=os.path.join(SAND, "data"))
for k in ("BLENDER_USER_SCRIPTS", "BLENDER_USER_DATAFILES"):
    os.makedirs(env[k], exist_ok=True)
os.makedirs(cfg, exist_ok=True)
proc = subprocess.Popen([r"D:\blender.exe", "--factory-startup", "--no-window-focus", "-p", "-24000", "-24000", "1280", "800"] + args, env=env)
print("pid", proc.pid)


def windows_of(pid):
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        p = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(200); u.GetWindowTextW(h, buf, 200)
            r = wt.RECT(); u.GetWindowRect(h, ctypes.byref(r))
            out.append((h, buf.value, (r.left, r.top, r.right, r.bottom)))
        return True
    u.EnumWindows(cb, 0)
    return out


t0 = time.time(); hwnd = 0
while time.time() - t0 < 120 and not hwnd:
    w = [x for x in windows_of(proc.pid) if "Blender" in x[1]]
    if w:
        hwnd = w[0][0]
    time.sleep(0.5)
u.SetWindowPos(hwnd, None, -24000, -24000, 0, 0, 0x0001 | 0x0004 | 0x0010)
print("window", hwnd, "after", round(time.time() - t0, 1), "windows", windows_of(proc.pid))
try:
    print("ping", br.request("ping", timeout=90))
    t = time.time()
    props = br.props()
    print("panels:", len(props), "settings in", round(time.time() - t, 1), "s")
    lang = [p for p in props if p["id"] == "language"]
    print("language entries:", [(p["path"], p["label"], p["type"], len(p.get("items", []))) for p in lang][:3])
    by_editor = {}
    for p in props:
        by_editor[p["path"][0]] = by_editor.get(p["path"][0], 0) + 1
    print("by editor:", by_editor)
    verbs = SB.prop_verbs(props)
    print("prop verbs:", len(verbs), [ (v.text_path if hasattr(v, 'text_path') else v.label) for v in verbs[:6]])
    # a boolean and an enum
    bools = [p for p in props if p["type"] == "BOOLEAN" and not p["readonly"]][:3]
    print("sample booleans:", [(p["path"], p["label"], p["value"]) for p in bools])
    if bools:
        b = bools[0]
        print("flip:", br.apply_setting(b["key"], ""))
        print("set on:", br.apply_setting(b["key"], "on"), "| set off:", br.apply_setting(b["key"], "off"))
    if lang:
        print("language -> English:", br.apply_setting(lang[0]["key"], "English"))
        print("language bad choice:", br.apply_setting(lang[0]["key"], "Klingon"))
    # file commands
    for op in ("wm.open_mainfile", "wm.save_as_mainfile", "wm.obj_import", "wm.stl_import", "wm.ply_import", "wm.save_mainfile", "screen.redo_last", "wm.window_new"):
        try:
            print("fileinfo", op, br.fileinfo(op))
        except Exception as e:
            print("fileinfo", op, "ERR", e)
    print("open without path:", br.execute("wm.open_mainfile"))
    print("outside sandbox:", br.execute_file("wm.save_as_mainfile", r"C:\Users\Public\evil.blend"))
    fx_path = os.path.join(sb.inbox, "fixture.blend")
    print("save_copy:", br.save_copy(fx_path), os.path.isfile(fx_path))
    print("open fixture:", br.execute_file("wm.open_mainfile", fx_path))
    obj_path = sb.fixture("cube", ["obj"])
    print("import obj:", br.execute_file("wm.obj_import", obj_path), "| objects:", br.request("state").get("objects"))
    out_path = sb.save_target("hojaiga-output", ["blend"])
    print("save as:", br.execute_file("wm.save_as_mainfile", out_path), os.path.isfile(out_path))
    print("redo_last:", br.execute("screen.redo_last"))
finally:
    if not KEEP:
        proc.kill()
        time.sleep(1)
        shutil.rmtree(SAND, ignore_errors=True)
