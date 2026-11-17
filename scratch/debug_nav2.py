"""debug_nav2.py -- navigate a Vista-style dialog through its ADDRESS BAND: click the empty part of the band (it turns into an edit), type the folder, Enter."""
import sys, time, os, ctypes
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, dialogs as DG
from core_organs.professor.effectors import Effector
from core_organs import headless_input as hin
import ctypes.wintypes as wt

run = AR.AppRun(AR.SPECS["notepad"], vision=False, log=lambda s: None, phases=())
try:
    assert run.start()
    fx = Effector(run.hwnd, allow_input=True, owned=True)
    sb = DG.Sandbox("notepad", "nav2")
    base = set(hin.popup_windows(run.hwnd))
    drv = DG.DialogDriver(fx, run.hwnd, sb, baseline=base)
    u = DG._u
    with fx.focus_watch():
        fx.key("ctrl+shift+s")
        time.sleep(2.5)
        i = drv.look()[0]
        print("start address:", drv._address_of(i.hwnd))
        kids = DG._w32_children(i.hwnd, 200)
        band = next((k for k in kids if k[2] == "msctls_progress32"), None)
        print("band:", band)
        r = wt.RECT()
        u.GetClientRect(band[0], ctypes.byref(r))
        print("band client rect:", r.left, r.top, r.right, r.bottom)
        x, y = r.right - 6, (r.bottom - r.top) // 2
        lp = (y << 16) | (x & 0xFFFF)
        u.PostMessageW(band[0], 0x0201, 1, lp)      # WM_LBUTTONDOWN
        u.PostMessageW(band[0], 0x0202, 0, lp)      # WM_LBUTTONUP
        time.sleep(0.8)
        kids2 = DG._w32_children(i.hwnd, 250)
        edits = [k for k in kids2 if k[2] == "Edit" and k[0] != i.edit_hwnd]
        print("edits after click:", [(k[0], k[1], k[3][:50], k[4]) for k in edits])
        cands = [k for k in kids2 if k[2] in ("ComboBoxEx32", "ComboBox") and k[0] not in {x[0] for x in kids}]
        print("new combos:", [(k[0], k[2], k[3][:40]) for k in cands])
        if edits:
            ed = edits[-1][0]
            DG._u.SendMessageTimeoutW(ed, DG.WM_SETTEXT, 0, sb.outbox, DG.SMTO_ABORTIFHUNG, 1000, ctypes.byref(ctypes.c_size_t(0)))
            u.PostMessageW(ed, DG.WM_KEYDOWN, DG.VK_RETURN, 0)
            u.PostMessageW(ed, DG.WM_KEYUP, DG.VK_RETURN, 0)
            time.sleep(1.5)
            print("address after:", drv._address_of(i.hwnd), "| wanted:", sb.outbox)
        print("windows:", [(w, hin.safe_window_text(w, 100)) for w in drv.windows()])
        fx.close_popups(list(base))
finally:
    run.finish()
