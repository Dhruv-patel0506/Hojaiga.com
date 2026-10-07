"""Does scrolling a PARKED UWP window via UIA ScrollPattern actually materialise the virtualised
footer ('About')? Isolates the realization mechanic from the judge/step loop: dump the full raw UIA
name set before, run _reveal_by_scrolling, dump after, and look for the target word. The raw dump
uses uiautomation directly so it reflects the LIVE visual tree regardless of our role filtering."""
import io, os, sys, time, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation")
import win32con, win32gui
from core_organs import desktop_grounding as dg, organ_40_app_launcher as l40
from core_organs import universal_scan as us

if dg._UIA_EXEC is None:
    from concurrent.futures import ThreadPoolExecutor
    dg._UIA_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia-probe",
                                      initializer=dg._uia_thread_init)


def all_names(hwnd):
    def work():
        import uiautomation as auto
        root = auto.ControlFromHandle(hwnd)
        out, stack, seen = [], [root], 0
        while stack and seen < 2500:
            c = stack.pop(); seen += 1
            try:
                n = c.Name
            except Exception:
                n = ""
            if n:
                out.append(n)
            try:
                stack.extend(c.GetChildren())
            except Exception:
                pass
        return seen, out
    return dg._UIA_EXEC.submit(work).result(timeout=30)


def find_settings():
    hits = []

    def cb(h, _):
        try:
            if win32gui.IsWindowVisible(h) and (win32gui.GetWindowText(h) or "").strip() == "Settings":
                hits.append(h)
        except Exception:
            pass
    win32gui.EnumWindows(cb, None)
    return hits[0] if hits else 0


os.startfile("ms-settings:")
hwnd = 0
for _ in range(30):
    time.sleep(0.5)
    sh = find_settings()
    if sh:
        _, ns = all_names(sh)
        if len(ns) >= 15:
            hwnd = sh
            break
        hwnd = hwnd or sh

seen_b, names_before = all_names(hwnd)
about_before = [n for n in names_before if "about" in (n or "").lower()]

loop = dg.DesktopAutonomyLoop()
moved = loop._reveal_by_scrolling(hwnd)
time.sleep(0.9)
seen_a, names_after = all_names(hwnd)
about_after = [n for n in names_after if "about" in (n or "").lower()]
new = [n for n in names_after if n not in set(names_before)]

print(json.dumps({
    "hwnd": hwnd, "scrolled_moved": moved,
    "nodes_before": seen_b, "nodes_after": seen_a,
    "about_before": about_before[:6], "about_after": about_after[:6],
    "new_count": len(new), "new_sample": new[:20],
}, ensure_ascii=False)[:1600])

if hwnd:
    us.close_window(hwnd, timeout_s=4.0, discard_unsaved=True)
print("done")
