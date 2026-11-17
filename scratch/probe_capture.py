import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs import background_window as bw
from core_organs.atlas import scanner as SC
from core_organs.professor import apprun as AR, capture as CAP

key = sys.argv[1] if len(sys.argv) > 1 else "notepad"
spec = AR.SPECS[key]
prep = AR._Prep(spec.prep)
print("prep", prep.before())
info = AR.launch(spec, prep)
h = int(info.get("hwnd") or 0)
print("launch", {k: v for k, v in info.items() if k != "trace"})
try:
    bg = bw.BackgroundSession(h)
    bg.__enter__()
    print("mode", bg.mode, "info", CAP.window_info(h).box, "minimized", CAP.window_info(h).minimized, "visible", CAP.window_info(h).visible)
    nodes, waited, fo = SC.ensure_tree(h, bg, max_s=6.0)
    print("tree", len(nodes), waited, fo)
    for label, fn in (("printwindow", lambda: CAP._printwindow(h)), ("wgc", lambda: CAP.wgc_grab(h))):
        img = fn()
        print(label, None if img is None else (img.size, "blank" if CAP._is_blank(img) else "content"))
        if img is not None:
            img.save(f"D:/new_automation/scratch/cap_{key}_{label}_0.png")
    bg.lay_out(settle_s=1.0)
    print("after lay_out box", CAP.window_info(h).box)
    for label, fn in (("printwindow", lambda: CAP._printwindow(h)), ("wgc", lambda: CAP.wgc_grab(h))):
        img = fn()
        print(label, None if img is None else (img.size, "blank" if CAP._is_blank(img) else "content"))
        if img is not None:
            img.save(f"D:/new_automation/scratch/cap_{key}_{label}_1.png")
    fr = CAP.grab_window(h)
    print("grab_window", None if fr is None else (fr.image.size, fr.via))
    bg.__exit__(None, None, None)
finally:
    print("close", SC.close_owned(h))
    print("prep after", prep.after())
