"""Experiment: can a virtual pointer (posted messages + in-process polling shim) drive Blender, with the person's cursor untouched?"""
import sys, time, ctypes, ctypes.wintypes as wt, os, subprocess, json
sys.path.insert(0, r"D:\new_automation"); sys.path.insert(0, r"D:\new_automation\All codes")
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
from core_organs.professor.lab.labkit import CursorWatch, cursor_pos
from core_organs.professor.adapters.script_bridge import ScriptBridge
from core_organs.atlas import gestures as AG
import frida

SAND = os.path.join(os.environ["TEMP"], "hojaiga_blender_probe")
os.makedirs(SAND, exist_ok=True)
br, args = ScriptBridge.prepare(SAND)
env = dict(os.environ, BLENDER_USER_CONFIG=os.path.join(SAND, "cfg"), BLENDER_USER_SCRIPTS=os.path.join(SAND, "scripts"), BLENDER_USER_DATAFILES=os.path.join(SAND, "data"))
for k in ("BLENDER_USER_CONFIG", "BLENDER_USER_SCRIPTS", "BLENDER_USER_DATAFILES"):
    os.makedirs(env[k], exist_ok=True)
proc = subprocess.Popen([r"D:\blender.exe", "--factory-startup", "--no-window-focus", "-p", "-3000", "100", "1280", "800"] + args, env=env)
print("pid", proc.pid)

def find_hwnd(pid):
    res = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        p = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(200); u.GetWindowTextW(h, buf, 200)
            if "Blender" in buf.value:
                res.append((h, buf.value))
        return True
    u.EnumWindows(cb, 0)
    return res

t0 = time.time()
hwnd = 0
while time.time() - t0 < 120:
    w = find_hwnd(proc.pid)
    if w:
        hwnd = w[0][0]
        break
    time.sleep(1)
print("hwnd", hwnd, "after", round(time.time() - t0, 1))
r = wt.RECT(); u.GetWindowRect(hwnd, ctypes.byref(r)); print("rect", r.left, r.top, r.right, r.bottom)
# park off-screen without activating
u.SetWindowPos(hwnd, None, -3000, 100, 0, 0, 0x0001 | 0x0004 | 0x0010)
time.sleep(1)
u.GetWindowRect(hwnd, ctypes.byref(r)); print("rect parked", r.left, r.top, r.right, r.bottom)
print("ping", br.request("ping", timeout=90))
print("layout", json.dumps(br.request("layout")))
print("state", json.dumps(br.request("state")))
json.dump({"pid": proc.pid, "hwnd": hwnd, "port": br.port, "token": br.token}, open(os.path.join(SAND, "session.json"), "w"))
