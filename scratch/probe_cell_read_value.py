"""Probe 12: read the cells where the content actually lives.

Every previous witness looked at a cell's UIA NAME, which on this app is its REFERENCE ('A1'). A value goes
into the element's Value (the value pattern / legacy accessible value), which is what a screen reader speaks.
So probe 10's 'SetValue dispatched' may have SUCCEEDED and been read as a failure. This only reads - no writes -
over the whole grid, to find cells whose VALUE is non-empty.
"""
import os
import sys
import threading
import time

os.environ.setdefault("PYTHONPATH", r"D:\new_automation;D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation\All codes")

import uiautomation as auto                                             # noqa: E402
from core_organs.desktop_grounding import DesktopGrounding              # noqa: E402

g = DesktopGrounding()
_h = g.find_window("excel")
if not _h:
    print("no excel window")
    sys.exit(2)
hwnd = int(_h)

res: dict = {}


def _w():
    with auto.UIAutomationInitializerInThread():
        root = auto.ControlFromHandle(hwnd)
        cells = []
        stack = [root]
        while stack:
            c = stack.pop()
            try:
                if (c.ControlTypeName or "") == "DataItemControl":
                    cells.append(c)
                stack.extend(c.GetChildren())
            except Exception:
                continue
        res["count"] = len(cells)
        sample = []
        for c in cells[:40]:
            item = {"name": (c.Name or "")[:12], "aid": (c.AutomationId or "")[:12]}
            try:
                vp = c.GetValuePattern()
                item["value"] = (str(vp.Value)[:16] if vp is not None else None)
            except Exception as exc:
                item["value"] = f"err:{type(exc).__name__}"
            try:
                lp = c.GetLegacyIAccessiblePattern()
                item["legacy_value"] = (str(lp.Value)[:16] if lp is not None else None)
            except Exception as exc:
                item["legacy_value"] = f"err:{type(exc).__name__}"
            try:
                item["help"] = (c.HelpText or "")[:16]
            except Exception:
                pass
            sample.append(item)
        res["sample"] = sample
        filled = [i for i in sample if (i.get("value") or "") or (i.get("legacy_value") or "")]
        res["filled"] = filled


t = threading.Thread(target=_w, daemon=True)
t.start()
t.join(60)
print("cells:", res.get("count"))
for i in res.get("sample", [])[:18]:
    print("  ", i)
print("\ncells carrying a value:", res.get("filled"))
