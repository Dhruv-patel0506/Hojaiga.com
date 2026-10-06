"""Does the SHAPES-only recognizer see the dialog that the class-literal one missed?

Opens the app's own Save dialog (the quick-access Save, the exact move that hid it last time) and asks
organ_24's shared shape test what is on screen -- no class name, no title word is consulted by the
test itself. Read-only apart from pressing the app's Save button; tears the dialog and the app down.
"""
import sys, os, time
sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
os.environ["HOJAIGA_WEBAPP_WATCH"] = "0"
import psutil
from core_organs import universal_scan as us, fast_uia, headless_input as hin, background_window as bw
from core_organs import organ_48_app_behavior_model as bm, desktop_grounding as dg
from core_organs import organ_24_dap as dap

pids0 = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "excel.exe"}
li = us.launch_hidden("excel", fast=True)
h = li["hwnd"]
loop = dg.DesktopAutonomyLoop(grounding=dg.DesktopGrounding())
ok = False
try:
    with bw.BackgroundSession(h):
        time.sleep(1.0)
        us.leave_start_screen(h, timeout_s=8)
        time.sleep(1.0)
        snap = fast_uia.snapshot(h, timeout_ms=8000) or []
        qs = next((n for n in snap if n.name == "Save" and n.ctype == "ButtonControl"), None)
        print("QAT Save button found:", bool(qs), bm.invoke_node_safely(qs)[0] if qs else None, flush=True)
        t0 = time.time()
        pid = hin.window_pid(h)
        reps = []
        while time.time() - t0 < 12.0:
            time.sleep(1.0)
            reps = dap.find_file_dialogs(owner_pid=pid, limit=6)
            if reps:
                break
        print(f"dialog appeared after {time.time()-t0:.1f}s; windows of this pid:",
              [(w, hin._class_name(w), (hin.safe_window_text(w) or "")[:24])
               for w in hin.process_windows(h, include_hidden=False)], flush=True)
        for r in reps:
            print("SHAPE", os.path.basename(str(r["class"])),
                  {k: v for k, v in r.items() if k != "class"},
                  "owned=", dap.is_owned_top_level(int(r["hwnd"])), flush=True)
        ok = bool(reps)
        print("VERDICT: shapes-only recognizer", "SAWS the dialog" if ok else "MISSED it", flush=True)
        for r in reps:                       # let the dialog go without saving anything
            hin.post_key_combo(int(r["hwnd"]), "escape")
        time.sleep(1.0)
finally:
    hin._u32.PostMessageW(h, 0x0010, 0, 0)   # WM_CLOSE the frame we launched (nothing was typed)
    time.sleep(2.0)
    for p in psutil.process_iter(["name", "pid"]):
        if (p.info["name"] or "").lower() == "excel.exe" and p.pid not in pids0:
            try:
                p.terminate()
            except Exception:
                pass
print("done", flush=True)
