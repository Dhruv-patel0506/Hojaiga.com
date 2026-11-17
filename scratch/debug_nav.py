"""debug_nav.py -- which way makes a Vista-style Save dialog GO to a typed folder? Variants: (a) WM_SETTEXT + BM_CLICK (b) WM_SETTEXT + Enter key to the edit (c) UIA ValuePattern on that one hwnd + UIA Invoke on Save."""
import sys, time, os
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, dialogs as DG
from core_organs.professor.effectors import Effector
from core_organs import headless_input as hin

run = AR.AppRun(AR.SPECS["notepad"], vision=False, log=lambda s: None, phases=())
try:
    assert run.start()
    fx = Effector(run.hwnd, allow_input=True, owned=True)
    sb = DG.Sandbox("notepad", "nav")
    base = set(hin.popup_windows(run.hwnd))
    drv = DG.DialogDriver(fx, run.hwnd, sb, baseline=base)
    u = DG._u
    with fx.focus_watch():
        fx.key("ctrl+shift+s")
        time.sleep(2.5)
        i = drv.look()[0]
        print("start address:", drv._address_of(i.hwnd))
        folder = sb.outbox

        def addr():
            time.sleep(1.2)
            return drv._address_of(i.hwnd)
        # (a)
        DG._u.SendMessageTimeoutW(i.edit_hwnd, DG.WM_SETTEXT, 0, folder, DG.SMTO_ABORTIFHUNG, 1000, DG.ctypes.byref(DG.ctypes.c_size_t(0)))
        u.PostMessageW(i.buttons_w32["__ok__"], DG.BM_CLICK, 0, 0)
        print("(a) settext+BM_CLICK ->", addr())
        # (b)
        DG._u.SendMessageTimeoutW(i.edit_hwnd, DG.WM_SETTEXT, 0, folder, DG.SMTO_ABORTIFHUNG, 1000, DG.ctypes.byref(DG.ctypes.c_size_t(0)))
        u.PostMessageW(i.edit_hwnd, DG.WM_KEYDOWN, DG.VK_RETURN, 0)
        u.PostMessageW(i.edit_hwnd, DG.WM_KEYUP, DG.VK_RETURN, 0)
        print("(b) settext+Enter to edit ->", addr())
        # (c) UIA on the single hwnd
        try:
            import uiautomation as ua
            ed = ua.ControlFromHandle(i.edit_hwnd)
            vp = ed.GetValuePattern()
            vp.SetValue(folder)
            print("(c) uia set value ->", repr(DG._w32_text(i.edit_hwnd)))
            bt = ua.ControlFromHandle(i.buttons_w32["__ok__"])
            bt.GetInvokePattern().Invoke()
            print("(c) uia set+invoke ->", addr())
        except Exception as exc:
            print("(c) failed:", type(exc).__name__, str(exc)[:120])
        print("windows still open:", [(w, hin.safe_window_text(w, 100)) for w in drv.windows()])
        fx.close_popups(list(base))
finally:
    run.finish()
