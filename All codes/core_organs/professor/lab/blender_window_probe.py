"""Does an operator that opens a NEW window (Preferences) show it on the person's screen? Launch a parked throw-away Blender, run userpref_show with a 5 ms watcher that records where the new window first appears."""
import sys, time, ctypes, ctypes.wintypes as wt, os, subprocess, tempfile, shutil, threading
sys.path.insert(0, r"D:\new_automation"); sys.path.insert(0, r"D:\new_automation\All codes")
u = ctypes.WinDLL("user32", use_last_error=True)
u.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
from core_organs.professor.adapters import script_bridge as SB
from core_organs.professor import dialogs as DG
from core_organs import background_window as bw

SAND = tempfile.mkdtemp(prefix="hojaiga_bwp_")
sb = DG.Sandbox("blender_probe", "t1", root=os.path.join(SAND, "sandbox"))
br, args = SB.ScriptBridge.prepare(os.path.join(SAND, "bridge"), "python-startup", sb.root)
env = dict(os.environ, BLENDER_USER_CONFIG=os.path.join(SAND, "cfg"), BLENDER_USER_SCRIPTS=os.path.join(SAND, "s"), BLENDER_USER_DATAFILES=os.path.join(SAND, "d"))
for k in ("BLENDER_USER_CONFIG", "BLENDER_USER_SCRIPTS", "BLENDER_USER_DATAFILES"):
    os.makedirs(env[k], exist_ok=True)
proc = subprocess.Popen([r"D:\blender.exe", "--factory-startup", "--no-window-focus", "-p", "-24000", "-24000", "1280", "800"] + args, env=env)


def windows_of(pid):
    out = {}
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        p = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(200); u.GetWindowTextW(h, buf, 200)
            r = wt.RECT(); u.GetWindowRect(h, ctypes.byref(r))
            out[h] = (buf.value, (r.left, r.top, r.right, r.bottom))
        return True
    u.EnumWindows(cb, 0)
    return out


t0 = time.time(); hwnd = 0
while time.time() - t0 < 120 and not hwnd:
    w = {h: v for h, v in windows_of(proc.pid).items() if "Blender" in v[0]}
    if w:
        hwnd = next(iter(w))
    time.sleep(0.5)
u.SetWindowPos(hwnd, None, -24000, -24000, 0, 0, 0x0001 | 0x0004 | 0x0010)
print("main", hwnd)
assert br.request("ping", timeout=90).get("ok")
seen = {}
stop = False


def watch():
    base = set(windows_of(proc.pid))
    while not stop:
        for h, (title, rect) in windows_of(proc.pid).items():
            if h not in base and h not in seen:
                on_screen = rect[2] > 0 and rect[3] > 0 and rect[0] < ctypes.windll.user32.GetSystemMetrics(0) and rect[1] < ctypes.windll.user32.GetSystemMetrics(1)
                seen[h] = (time.time(), title, rect, on_screen)
                if on_screen:
                    u.SetWindowPos(h, None, -24000, -24000, 0, 0, 0x0001 | 0x0004 | 0x0010)           # conceal at once (what the popup guard does)
        time.sleep(0.003)


th = threading.Thread(target=watch, daemon=True); th.start()
t1 = time.time()
print("userpref_show ->", br.execute("screen.userpref_show")); print("new window ->", br.execute("wm.window_new"))
time.sleep(3.0)
stop = True; th.join(1)
for h, (ts, title, rect, on_screen) in seen.items():
    print("new window", hex(h), repr(title), rect, "first seen on a monitor:", on_screen, "after", round(ts - t1, 3), "s")
print("windows now", windows_of(proc.pid))
proc.kill(); time.sleep(1); shutil.rmtree(SAND, ignore_errors=True)
