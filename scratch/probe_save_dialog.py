"""Why does Notepad's Save As dialog not count as a 'new window' while Paint's does?

The leaf's postcondition is `window_opened`, which diffs `ObservedState.windows` - and that list comes from
_popups() -> background_window.target_popups(), an OWNERSHIP test. If a packaged app hosts its picker on a
different window of the same process, the dialog is real but un-owned and the step is wrongly failed.

This measures it: invoke File > Save as headlessly, then enumerate the same PID four different ways.
"""
import ctypes
import sys
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs import organ_48_app_behavior_model as bm        # noqa: E402
from core_organs import background_window as bw                   # noqa: E402
from core_organs import si_tests_behavior as sib                  # noqa: E402

APPS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["notepad", "paint"]
_u32 = ctypes.windll.user32


def pid_windows(pid: int):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(h, _):
        try:
            if _u32.IsWindowVisible(h) and bw._pid(h) == pid:
                out.append(int(h))
        except Exception:
            pass
        return True
    _u32.EnumWindows(cb, 0)
    return out


def desc(h: int) -> str:
    return f"{h:#x} class={bm._win_class(h)!r} title={bm._win_title(h)!r} owner={_u32.GetWindow(h, 4) or 0:#x}"


def main() -> int:
    for app in APPS:
        with sib.LiveApp(app) as la:
            if not la.ok:
                print(f"{app}: env - {la.why}")
                continue
            hwnd = la.hwnd
            pid = bw._pid(hwnd)
            print(f"\n=== {app} hwnd={hwnd:#x} pid={pid} class={bm._win_class(hwnd)!r}")
            print(f"    path: {desc(hwnd)}")
            print(f"    owned popups of hwnd: {[desc(x) for x in bm._popups(hwnd)] or 'none'}")
            print(f"    visible windows of pid: {[desc(x) for x in pid_windows(pid)] or 'none'}")
            ok, note = bm.open_menu_path(hwnd, "File > Save as" if app == "notepad" else "File > Save")
            print(f"    open_menu_path -> {ok} {note}")
            seen = {}
            for t in (0.3, 0.8, 1.5, 2.5, 4.0, 6.0):
                time.sleep(max(0.0, t - (max(seen) if seen else 0)))
                pops = bm._popups(hwnd)
                wins = pid_windows(pid)
                seen[t] = (len(pops), len(wins))
                st = bm.observe(hwnd, max_nodes=200)
                print(f"    t={t:4.1f}s target_popups={len(pops)} pid_windows={len(wins)} state.windows={st.windows}")
                if len(wins) > 1 or pops:
                    for x in wins:
                        print(f"        pid-win {desc(x)} is_popup_of_hwnd={x in pops} "
                              f"is_target_popup={bw.is_target_popup(x, hwnd, pid) if x != hwnd else '-'}")
                    for x in pops:
                        print(f"        popup  {desc(x)}")
                    break
    return 0


if __name__ == "__main__":
    sys.exit(main())
