import sys, time, ctypes, random
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.atlas.fixture import harness
from core_organs import background_window as bw
from core_organs.atlas import scanner as SC
from core_organs.professor.effectors import Effector

u = ctypes.WinDLL("user32")
u.GetForegroundWindow.restype = ctypes.c_void_p


def fgid():
    return int(u.GetForegroundWindow() or 0)


def by(nodes, name):
    return next(n for n in nodes if n.name == name)


def centre(n):
    l, t, r, b = n.rect
    return (l + r) // 2, (t + b) // 2


ROUTES = {
    "posted-click toolbar": lambda fx, nodes: fx.click_xy(*centre(by(nodes, "Add Marker"))),
    "posted-click tab": lambda fx, nodes: fx.click_xy(*centre(by(nodes, "Options"))),
    "UIA invoke toolbar": lambda fx, nodes: fx.node(by(nodes, "Add Marker")),
    "UIA select tab": lambda fx, nodes: fx.node(by(nodes, "Options")),
    "BM_CLICK checkbox": lambda fx, nodes: fx.node(by(nodes, "Visible")),
    "nothing": lambda fx, nodes: (True, "-"),
}
order = list(ROUTES) * 3
random.seed(5)
random.shuffle(order)
tally = {k: [0, 0, 0] for k in ROUTES}          # [trials, stolen_before_action (launch noise), stolen_by_action]
for name in order:
    h = harness.launch(minimized=True)
    hwnd = h["hwnd"]
    try:
        time.sleep(1.0)
        with bw.BackgroundSession(hwnd) as bg:
            nodes, waited, fo = SC.ensure_tree(hwnd, bg)
            fx = Effector(hwnd, allow_input=True, owned=True)
            time.sleep(1.5)
            fg_idle = fgid()
            noise = fg_idle == hwnd
            ROUTES[name](fx, nodes)
            time.sleep(1.0)
            fg_after = fgid()
            stolen = (fg_after == hwnd) and not noise
            tally[name][0] += 1
            tally[name][1] += int(noise)
            tally[name][2] += int(stolen)
            print(f"{name:22s} idle_stolen={noise} after_stolen={fg_after == hwnd}", flush=True)
    finally:
        harness.close(h)
        time.sleep(1.0)
print("\nSUMMARY [trials, launch-noise, stolen-by-action]")
for k, v in tally.items():
    print(f"  {k:22s} {v}")
