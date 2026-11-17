"""debug_savedlg.py -- Notepad Ctrl+Shift+S: what does the Save as window look like to Win32 (class tree) - why is its file-name field not found?"""
import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, dialogs as DG
from core_organs.professor.effectors import Effector
from core_organs import headless_input as hin

run = AR.AppRun(AR.SPECS["notepad"], vision=False, log=lambda s: None, phases=())
try:
    assert run.start()
    fx = Effector(run.hwnd, allow_input=True, owned=True)
    base = set(hin.popup_windows(run.hwnd))
    with fx.focus_watch():
        print("key:", fx.key("ctrl+shift+s"))
        time.sleep(2.5)
        for w in hin.popup_windows(run.hwnd):
            if w in base:
                continue
            print(f"\nPOPUP {w}: class={hin._class_name(w)!r} title={hin.safe_window_text(w, 200)!r} heavy={DG.is_heavy_dialog(w)}")
            kids = DG._w32_children(w, 120)
            print("  children:", len(kids))
            for h, p, c, t, i in kids[:60]:
                print(f"   {h:>9} parent={p:>9} {c:<26} id={i:<6} text={t[:50]!r}")
            info = DG.inspect(w)
            print("  inspect ->", info.brief() if info else None, "| edit_hwnd", getattr(info, "edit_hwnd", None), "| filter", getattr(info, "filter_text", ""), getattr(info, "filter_exts", ""), "| default", getattr(info, "default_name", ""))
            fx.close_popups(list(base))
        print("done")
finally:
    run.finish()
