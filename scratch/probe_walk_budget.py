"""Offline proof for the bounded UIA walk (desktop_grounding._walk_uia).

No app is touched: uiautomation.ControlFromHandle is replaced by a fake tree, so this measures ONLY the walker.
Case 1 is the failure mode py-spy caught in the suite: a sibling chain that never ends. The old code called
Control.GetChildren(), which walks that chain INSIDE ONE call and never returns - the per-node budget below
could not apply, and the process grew to gigabytes.
"""
import os
import sys
import time

os.environ["HOJAIGA_UIA_WALK_BUDGET_S"] = "1.0"
os.environ["HOJAIGA_UIA_WALK_MIN_NODES"] = "50"
os.environ["HOJAIGA_UIA_WALK_NODE_BUDGET"] = "2000"
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation")

import uiautomation as auto                      # noqa: E402
from core_organs import desktop_grounding as dg  # noqa: E402


class Rect:
    left, top, right, bottom = 10, 10, 120, 60


class Node:
    """A stand-in UIA control wrapper. `endless` = this node's CHILDREN form a sibling chain that never ends."""

    def __init__(self, depth=0, endless=False, fan=3, maxdepth=5, sibs=0, role="ButtonControl"):
        self._d, self._endless, self._fan, self._maxdepth, self._sibs = depth, endless, fan, maxdepth, sibs
        self._role = role

    @property
    def ControlTypeName(self):
        return self._role

    ClassName = "Fake"
    AutomationId = ""
    BoundingRectangle = Rect()
    IsEnabled = True
    IsOffscreen = False
    NativeWindowHandle = 12345

    @property
    def Name(self):
        return f"d{self._d}s{self._sibs}"

    def GetValuePattern(self):
        return None

    def GetFirstChildControl(self):
        if self._d >= self._maxdepth:
            return None
        return Node(self._d + 1, self._endless, self._fan, self._maxdepth, 0, self._role)

    def GetNextSiblingControl(self):
        nxt = self._sibs + 1
        if self._endless or nxt < self._fan:
            return Node(self._d, self._endless, self._fan, self._maxdepth, nxt, self._role)
        return None

    def GetChildren(self):                    # the call the old code used: never returns for an endless chain
        out, c = [], self.GetFirstChildControl()
        while c:
            out.append(c)
            c = c.GetNextSiblingControl()
        return out


def walk(root, label, max_depth=14, max_nodes=500):
    auto.ControlFromHandle = lambda hwnd: root
    g = dg.DesktopGrounding()
    t = time.perf_counter()
    els = g._walk_uia(12345, max_depth=max_depth, max_nodes=max_nodes)
    dt, w = time.perf_counter() - t, g.last_walk
    print(f"{label:<24} {dt:6.2f}s surfaced={len(els):<4} walked={w['nodes_walked']:<5} "
          f"truncated={str(w['truncated']):<6} by='{w['stopped_by']}' depth={w['max_depth_seen']} walk_ms={w['walk_ms']}")
    return dt, w, len(els)


print(f"budget={dg.UIA_WALK_BUDGET_S}s min_nodes={dg.UIA_WALK_MIN_NODES} node_budget={dg.UIA_WALK_NODE_BUDGET}")

dt, w, n = walk(Node(endless=True), "endless siblings:")
assert dt < 5.0 and w["truncated"] and w["stopped_by"], f"the endless chain still cost {dt:.1f}s {w}"
print(f"   -> terminated in {dt:.2f}s and named the rail ({w['stopped_by']}): OK (before: unbounded, gigabytes)")

# Endless chain of NON-actionable nodes: nothing fills the surface budget, so the node rail must catch it.
dt, w, n = walk(Node(endless=True, role="TextControl"), "endless, none surfaced:", max_nodes=100000)
assert dt < 5.0 and w["node_budget_hit"], (dt, w)
print(f"   -> the node rail catches it too: {w['stopped_by']} after {w['nodes_walked']} visits")

dt, w, n = walk(Node(endless=False, fan=3, maxdepth=5), "finite tree:")
assert not w["truncated"] and n > 20, w
print(f"   -> walked to the end, nothing reported as cut: OK ({n} controls surfaced)")

dt, w, n = walk(Node(endless=False, fan=30, maxdepth=1), "wide, shallow:")
assert not w["truncated"] and n == 30 + 1, w      # 30 siblings + the root they hang off
print(f"   -> a wide flat strip is still fully grounded: OK ({n} controls)")

# An endless chain BELOW the depth rail must not be opened at all (the rail is a stop, not a per-node skip).
dt, w, n = walk(Node(endless=True, maxdepth=40), "endless + depth rail:", max_depth=3)
assert dt < 5.0 and w["truncated"], (dt, w)
print(f"   -> depth rail terminates too: {w['stopped_by']} in {dt:.2f}s")
print("OK - the walk is bounded and honest about it")
