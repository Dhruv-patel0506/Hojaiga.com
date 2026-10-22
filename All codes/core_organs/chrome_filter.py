"""
chrome_filter -- the operating system's own window frame is not part of the application: Minimize / Maximize / Restore / Close / the system menu never enter an explanation queue and are never operated.

    is_window_chrome(name, ctype="", box=None, size=None) -> bool     by name; when the control's box and the window size are known it must also sit in the caption strip
                                                                       (so an application's own 'Close' button in the middle of a dialog is NOT frame)
    drop_chrome(controls, size=None)                                   the list without frame controls

Measured cause: a walkthrough spent steps on the frame buttons and operating 'Restore' un-maximised the window under the task.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

CHROME_NAME = re.compile(r"^\s*(minimi[sz]e|maximi[sz]e|restore(\s+down)?|close|system(\s+menu)?|sys\s*command|sc_\w+)\s*(button|window)?\s*$", re.I)
CAPTION_TYPES = ("TitleBar", "TitleBarControl")


def is_window_chrome(name: str, ctype: str = "", box: Optional[Sequence[float]] = None, size: Optional[Tuple[int, int]] = None) -> bool:
    nm = (name or "").strip()
    if re.sub(r"Control$", "", ctype or "") == "TitleBar":
        return True
    if not CHROME_NAME.match(nm):
        return False
    if box is None or not size or not size[0] or not size[1]:
        return True                                                         # no geometry: the name alone decides (the old rule)
    x, y, w, h = box[:4]
    strip = max(48.0, 0.07 * size[1])                                       # the caption strip: the top of the window
    in_strip = (y + h) <= strip + 4
    if re.match(r"(?i)^system", nm):
        return in_strip and x < 0.2 * size[0]                               # the system menu is the icon at the top-left
    return in_strip and x > 0.45 * size[0]                                  # the three buttons are at the top-right


def drop_chrome(controls: Sequence[Dict[str, Any]], size: Optional[Tuple[int, int]] = None) -> List[Dict[str, Any]]:
    return [c for c in controls if not is_window_chrome(str(c.get("name", "")), str(c.get("type", "")), c.get("box"), size)]
