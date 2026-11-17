"""debug_savedlg2.py -- Save as in Notepad: set a sandbox path, press Save, and READ what comes next (the confirm prompt's text)."""
import sys, time, os
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, dialogs as DG
from core_organs.professor.effectors import Effector
from core_organs import headless_input as hin

run = AR.AppRun(AR.SPECS["notepad"], vision=False, log=lambda s: None, phases=())
try:
    assert run.start()
    fx = Effector(run.hwnd, allow_input=True, owned=True)
    sb = DG.Sandbox("notepad", "dbg")
    base = set(hin.popup_windows(run.hwnd))
    drv = DG.DialogDriver(fx, run.hwnd, sb, baseline=base)
    with fx.focus_watch():
        fx.key("ctrl+o")
        time.sleep(2.0)
        print("open handled:", [(h["kind"], h["ok"]) for h in drv.settle(max_s=8.0)])
        time.sleep(1.5)
        fx.key("ctrl+shift+s")
        time.sleep(2.5)
        infos = drv.look()
        print("dialogs:", [i.brief() for i in infos])
        i = infos[0]
        res = drv.drive(i)
        print("drive:", res)
        time.sleep(3.0)
        for w in drv.windows():
            j = DG.inspect(w)
            print("STILL OPEN:", w, j.brief() if j else None, j.texts[:3] if j else "")
        print("outbox now:", os.listdir(sb.outbox), "inbox:", os.listdir(sb.inbox))
        fx.close_popups(list(base))
        print("done")
finally:
    run.finish()
