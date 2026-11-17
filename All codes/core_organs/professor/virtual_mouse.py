"""
professor.virtual_mouse -- the VIRTUAL MOUSE: a pointer that exists only as an overlay (and as a row in the database), never as input.

When the Professor performs an action it first moves this pointer to the control along a continuous Fitts's-law route (professor.pointing.Trajectory), shows what it is about to do, and records the
trace: start, end, planned and actual seconds, number of waypoints - linked to the action's row in the transition log. The ACTION itself is delivered headlessly (window messages / UI Automation);
the physical mouse and keyboard are never used, blocked or moved, so a person can keep working while the Professor works.

  visible=True    the overlay draws the pointer (use it when the target window is on a visible monitor: a demonstration, or watching a run)
  visible=False   the application is parked off-screen, so there is nothing to draw on: the route is still PLANNED and RECORDED, the overlay is not touched
Measured timing (planned vs the overlay's actual arrival) is what the motor model (professor.ml.motor) is checked against.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional, Tuple

from . import pointing
from .schema import Box


class VirtualMouse:
    def __init__(self, overlay: Any = None, history: Any = None, app_key: str = "", visible: bool = False, learner: Any = None, speed: float = 1.0):
        self.overlay, self.history, self.app_key, self.visible, self.learner, self.speed = overlay, history, app_key, visible, learner, speed
        self.pos: Tuple[float, float] = (0.0, 0.0)
        self.traces: List[dict] = []

    def move_to(self, box: Box, label: str = "", action: str = "click", hotkey: str = "", step: Optional[int] = None, transition_id: Optional[int] = None) -> dict:
        """Glide to a control. Returns the trace {planned_s, actual_s, ...}. Blocks only while a VISIBLE pointer is actually travelling."""
        target = pointing.landing_point(box, action)
        width = max(6.0, min(box.w, box.h))
        traj = pointing.stitch([self.pos, target], [0.0, width])
        planned = traj.duration / max(0.1, self.speed)
        t0 = time.time()
        if self.visible and self.overlay is not None:
            try:
                self.overlay.glide([target], [width])
                self.overlay.point(box, label, step, action, bool(label or hotkey), label, False, False, hotkey)
                wait = getattr(self.overlay, "wait_idle", None)
                if wait:
                    wait(planned + 2.0)
            except Exception:
                pass
        actual = (time.time() - t0) if self.visible else planned
        trace = {"x0": self.pos[0], "y0": self.pos[1], "x1": target[0], "y1": target[1], "planned_s": round(planned, 3), "actual_s": round(actual, 3), "waypoints": 2, "visible": self.visible, "label": label}
        self.traces.append(trace)
        if self.visible and self.learner is not None:                       # a real overlay glide is a measured movement: feed the motor model (consistency check of the law)
            try:
                import math
                self.learner.observe_motion(math.hypot(target[0] - self.pos[0], target[1] - self.pos[1]), width, actual)
            except Exception:
                pass
        if self.history is not None:
            try:
                trace["pointer_id"] = self.history.log_pointer(self.app_key, trace["x0"], trace["y0"], trace["x1"], trace["y1"], trace["planned_s"], trace["actual_s"], 2, self.visible, transition_id)
            except Exception:
                pass
        self.pos = target
        return trace

    def clear(self) -> None:
        if self.visible and self.overlay is not None:
            try:
                self.overlay.clear()
            except Exception:
                pass
