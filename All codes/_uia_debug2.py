"""Temporary debug 2: replicate _collect_uia_frame without swallowing errors."""
import sys, traceback
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_41_scanner import ScannerOrgan

s = ScannerOrgan()
s._uia.InitializeUIAutomationInCurrentThread()
active = s._uia.GetForegroundControl()

# Replicate the node-read WITHOUT try/except
rect = active.BoundingRectangle
print("rect ok:", rect)
cid = str(active.NativeWindowHandle or id(active))
print("cid ok:", cid)
name = active.Name or ""
print("name ok:", name[:40])
cls = active.ClassName or ""
print("class ok:", cls)
ctype = active.ControlTypeName or "Unknown"
print("ctype ok:", ctype)
vis = active.IsVisible
print("visible ok:", vis)
en = active.IsEnabled
print("enabled ok:", en)
bounds = (rect.left, rect.top, rect.right, rect.bottom)
print("bounds ok:", bounds)
node = {"control_id": cid, "name": name, "class_name": cls, "control_type": ctype,
        "bounds": bounds, "is_visible": vis, "is_enabled": en, "depth": 0,
        "parent_idx": -1, "child_idxs": []}
print("node built ok")

# Now the real method
nodes = s._collect_uia_frame(active, 8, 3000)
print("method nodes:", len(nodes))

# And children directly
ch = active.GetChildren()
print("direct GetChildren count:", len(ch))
