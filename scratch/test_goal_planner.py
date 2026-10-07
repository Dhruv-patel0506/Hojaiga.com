import ctypes, ctypes.wintypes as wt, time, os
from core_organs import goal_planner as gp

# unit: compound detection (no app knowledge, pure shape)
checks = {
    "add 21 and 21 is compound": gp.is_compound("add 21 and 21"),
    "type 21, press + then press = is compound": gp.is_compound("type 21, press + then press ="),
    "press 2 alone is NOT compound": not gp.is_compound("press 2"),
    "save the file as C:\\x\\a.txt is NOT compound": not gp.is_compound("save the file as C:\\x\\a.txt"),
    "click File then click Save is compound": gp.is_compound("click File then click Save"),
}
for k, v in checks.items():
    print(("PASS" if v else "FAIL"), "-", k)

# live grounded plan against a real Calculator
u = ctypes.windll.user32
os.startfile("calc.exe")
time.sleep(3.5)
found = []


@ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
def cb(h, l):
    if u.IsWindowVisible(h):
        buf = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(h, buf, 256)
        if buf.value.lower() == "applicationframewindow":
            t = u.GetWindowTextLengthW(h)
            tb = ctypes.create_unicode_buffer(t + 1)
            u.GetWindowTextW(h, tb, t + 1)
            if "Calculator" in tb.value:
                found.append(int(h))
    return True


u.EnumWindows(cb, 0)
from core_organs.desktop_grounding import DesktopGrounding
g = DesktopGrounding()
if found:
    labels = [e.name for e in g._walk_uia(found[0]) if e.role in gp.__dict__.get("_CLICK_ROLES", ("button", "menuitem", "tabitem", "listitem", "checkbox", "radiobutton", "splitbutton"))]
    print("calc click-labels sample:", labels[:40])
    plan = gp.expand("add 21 and 21", labels)
    print("PLAN for 'add 21 and 21' ->", plan)
    ok = plan != ["add 21 and 21"] and all(p.split("press ", 1)[1] in labels for p in plan)
    print(("PASS" if ok else "CHECK"), "- plan fully grounded in on-screen labels")
else:
    print("no calculator window found")

for h in found:
    u.PostMessageW(h, 0x0010, 0, 0)
print("closed", len(found))
