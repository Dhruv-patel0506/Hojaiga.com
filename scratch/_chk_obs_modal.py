"""WHY did the learner's modal-hygiene miss OBS's startup QMessageBox? Timeline probe: launch OBS
(the last exit was taskkill /F, so the crash prompt should return), poll every 2 s for 90 s and print
every top-level window of the obs64 processes: class, title, visible, OWNER hwnd, plus what
organ_48._popups/_open_popups(main_hwnd) see and what find_window('obs studio') resolves to."""
import sys, time, ctypes
sys.path.insert(0, r"d:\new_automation\All codes")
import win32gui, win32con, win32process
from core_organs import organ_48_app_behavior_model as bm

EXE = r"D:\obs-studio\bin\64bit\obs64.exe"
user32 = ctypes.windll.user32

u = win32gui.FindWindow("OBSAppWindow", None)  # probe both possible main classes
procs = set()
import subprocess
p = subprocess.Popen([EXE])
procs.add(p.pid)
print(f"[diag] launched obs64 pid {p.pid}")


def top_windows(pids):
    out = []

    def _cb(h, _):
        pid = win32process.GetWindowThreadProcessId(h)[1]
        if pid in pids:
            r = win32gui.GetWindowRect(h)
            out.append({"hwnd": h, "cls": win32gui.GetClassName(h), "title": win32gui.GetWindowText(h)[:48],
                        "vis": bool(win32gui.IsWindowVisible(h)), "owner": win32gui.GetWindow(h, win32con.GW_OWNER) or 0,
                        "area": max(0, r[2]-r[0]) * max(0, r[3]-r[1])})
    win32gui.EnumWindows(_cb, None)
    return out


t0 = time.time()
seen_printed = set()
main = 0
while time.time() - t0 < 90:
    # OBS can spawn/reattach pids; track by image name too
    o = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True).stdout
    for ln in o.splitlines():
        if "obs64" in ln:
            try:
                procs.add(int(ln.split(",")[1].strip('"')))
            except Exception:
                pass
    wins = top_windows(procs)
    sig = tuple(sorted((w["cls"], w["vis"], w["owner"]) for w in wins))
    if sig not in seen_printed:
        seen_printed.add(sig)
        print(f"[+{time.time()-t0:5.1f}s] windows:")
        for w in wins:
            print(f"    {w['hwnd']:>8} cls={w['cls']:<24} vis={int(w['vis'])} owner={w['owner']:<8} area={w['area']:<9} title='{w['title']}'")
        main = next((w["hwnd"] for w in wins if w["cls"] == "OBSApp" and w["area"] > 100000), 0)
        if main:
            pop = bm._popups(main)
            popopen = bm._open_popups(main)
            print(f"    [diag] _popups(main={main}) -> {pop}")
            print(f"    [diag] _open_popups(main) -> {popopen}")
            try:
                from core_organs import desktop_grounding as dg
                g = dg.DesktopGrounding()
                fw = g.find_window("obs studio")
                print(f"    [diag] find_window('obs studio') -> {fw} (main is {main})")
            except Exception as exc:
                print(f"    [diag] find_window err {exc}")
            if not pop:
                break   # main window up with no popup: modal already gone/answered
    time.sleep(2)

print(f"[diag] done; closing OBS windows we launched")
for w in top_windows(procs):
    try:
        win32gui.PostMessage(w["hwnd"], win32con.WM_CLOSE, 0, 0)
    except Exception:
        pass
time.sleep(4)
for pid in procs:
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
print("[diag] cleaned")
