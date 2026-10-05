"""Verifier hardening test: does the pixel delta now ignore occlusion and flicker, while still
catching a real canvas-only change?

Four cases on a Tk canvas window we control, plus one control that shows what the OLD behaviour
(screen grab of the window rect, exact-byte hash) would have reported in the occlusion case.
Evidence -> grounding_reports/region_hash_hardening.json.
"""
import ctypes, ctypes.wintypes as wt, hashlib, json, os, sys, time, tkinter as tk

sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
from core_organs.desktop_grounding import (  # noqa: E402
    DesktopGrounding, DesktopVerifier, Snapshot, REGION_MIN_CHANGED_FRACTION)

OUT = os.path.join(os.path.dirname(__file__), "grounding_reports", "region_hash_hardening.json")
root = tk.Tk(); root.title("HojaigaRegionHardeningProbe"); root.geometry("500x400+220+150")
cv = tk.Canvas(root, width=480, height=380, bg="white"); cv.pack()
rect = cv.create_rectangle(100, 100, 300, 250, fill="red")
root.attributes("-topmost", True)


def pump(n=15, win=None):
    for _ in range(n):
        root.update()
        if win:
            win.update()
        time.sleep(0.04)


g, v = DesktopGrounding(), DesktopVerifier()
pump(25)   # the window must exist before FindWindowW can see it
hwnd = ctypes.windll.user32.FindWindowW(None, "HojaigaRegionHardeningProbe")
assert hwnd, "probe window not found"
elements = lambda: g._walk_uia(hwnd) or g._walk_win32(hwnd)  # noqa: E731
shot = lambda: v.snapshot(hwnd, elements())                  # noqa: E731

s_base = shot()
cases = {"capture_source": s_base.region_source, "hash_present": bool(s_base.region_hash)}

# A: nothing happens at all -> no pixel change, no structure change.
time.sleep(1.2); pump(20)
s_idle = shot()
changed, evidence = v.pixels_changed(s_base, s_idle)
cases["A_idle"] = {"changed": changed, "expect": False, "evidence": evidence,
                   "structure_changed": s_base.signature() != s_idle.signature()}

# B: a caret-sized flicker (3x24 dark line drawn, then removed) -> below tolerance.
caret = cv.create_line(110, 110, 110, 134, fill="black", width=3)
pump(12)
s_flick = shot()
cv.delete(caret); pump(12)
changed, evidence = v.pixels_changed(s_base, s_flick)
cases["B_caret_flicker"] = {"changed": changed, "expect": False, "evidence": evidence}

# C: a real canvas-only change (recolor a 200x150 rectangle) -> detected.
cv.itemconfigure(rect, fill="blue"); pump(20)
s_canvas = shot()
changed, evidence = v.pixels_changed(s_base, s_canvas)
cases["C_canvas_recolor"] = {"changed": changed, "expect": True, "evidence": evidence,
                             "structure_changed": s_base.signature() != s_canvas.signature()}

# D: the window gets fully covered by another window -> its OWN pixels must still hash the same
# as s_canvas (PrintWindow), which is the occlusion bug being fixed.
cover = tk.Toplevel(root); cover.title("HojaigaOccluder")
cover.geometry("500x400+220+150"); cover.attributes("-topmost", True)
cover.configure(bg="magenta"); cover.lift(); cover.focus_force()
pump(25, win=cover)
s_covered = shot()
changed, evidence = v.pixels_changed(s_canvas, s_covered)
# Control: measure the same moment the OLD way (screen grab of the window rect, no PrintWindow)
# and push it through the same comparison, so the fix is shown against the bug it replaces.
try:
    from PIL import ImageGrab
    rr = wt.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rr))
    grabbed = ImageGrab.grab(bbox=(rr.left, rr.top, rr.right, rr.bottom))
    thumb = DesktopVerifier._region_thumb(grabbed)
    fake = Snapshot(title=s_canvas.title, element_ids=list(s_canvas.element_ids),
                    region_hash=hashlib.md5(thumb).hexdigest(), region_thumb=thumb,
                    region_source="screen-grab-fallback")
    old_changed, old_evidence = v.pixels_changed(s_canvas, fake)
    old_style = {"would_have_reported_change": old_changed, "evidence": old_evidence}
except Exception as exc:  # the control is optional; never hide a real failure behind it
    old_style = {"control_skipped": repr(exc)}
cases["D_occluded"] = {"changed": changed, "expect": False, "evidence": evidence,
                       "source_after": s_covered.region_source, "control": old_style}

cover.destroy(); root.destroy()

checks = {k: cases[k]["changed"] == cases[k]["expect"]
          for k in ("A_idle", "B_caret_flicker", "C_canvas_recolor", "D_occluded")}
cases["all_as_expected"] = all(checks.values()) and cases["hash_present"] \
    and cases["capture_source"] == "printwindow" \
    and cases["C_canvas_recolor"]["structure_changed"] is False
cases["per_case_pass"] = checks
cases["tolerance"] = REGION_MIN_CHANGED_FRACTION
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(cases, f, indent=2)
print(json.dumps(cases, indent=2))
sys.exit(0 if cases["all_as_expected"] else 1)
