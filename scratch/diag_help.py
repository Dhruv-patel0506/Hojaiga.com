import sys, time
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.atlas.fixture import harness
from core_organs import background_window as bw
from core_organs.atlas import scanner as SC

h = harness.launch(minimized=True)
hwnd = h["hwnd"]
try:
    with bw.BackgroundSession(hwnd) as bg:
        nodes, waited, fo = SC.ensure_tree(hwnd, bg)
        for n in nodes:
            if n.name in ("Add Marker", "Clear Markers", "Run Wizard", "Delete All", "Export...", "Visible"):
                print(f"{n.name!r:18} help={n.help!r} accel={n.accel!r} aid={n.aid!r} cls={n.cls!r}")
finally:
    harness.close(h)
