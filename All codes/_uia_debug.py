"""Temporary debug: organ_41 UIA walk directly."""
import sys, traceback
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_41_scanner import ScannerOrgan

s = ScannerOrgan()
s._uia.InitializeUIAutomationInCurrentThread()

try:
    active = s._uia.GetForegroundControl()
    print("active:", active)
except Exception:
    traceback.print_exc()
    active = None

if active is not None:
    try:
        nodes = s._collect_uia_frame(active, 8, 3000)
        print("nodes:", len(nodes))
        if nodes:
            n = nodes[0]
            print("root:", n["name"][:50], n["control_type"], "children:", len(n["child_idxs"]))
        els = s._nodes_to_elements(nodes)
        print("elements:", len(els))
        tree = s._nodes_to_tree(nodes)
        print("tree children:", len((tree or {}).get("children", [])))
    except Exception:
        traceback.print_exc()

# Compare with ControlFromHandle route
import win32gui
hwnd = win32gui.GetForegroundWindow()
print("fg hwnd:", hwnd, win32gui.GetWindowText(hwnd))
ctrl = s._uia.ControlFromHandle(hwnd)
print("ctrl:", ctrl)
nodes2 = s._collect_uia_frame(ctrl, 8, 3000)
print("nodes via handle:", len(nodes2))
