"""
professor.privacy -- WHAT THE PERSON HAS OPEN IS NOT PART OF ANY APPLICATION'S INTERFACE.

Some menus list the person's own things: a 'Screenshot' gallery lists the titles of every open window (the page they are reading, the chat they are in), a 'Window' menu lists other
documents, a recent-files list names their files. Reading those into a catalog, a report or a picture would copy the person's life into the Professor's data.
(menus.PRIVATE_RX already leaves 'Recent' / 'History' submenus closed; this module catches what wording cannot: an item whose NAME is the title of a window that is open right now.)

  looks_private(label)    True when the label is (or contains) the title of a currently open top-level window of another program   (titles cached ~5 s)
Used by menus.add_item_verb (never filed), the flyout / dialog pictures of a run (never saved), and the knowledge records.
"""

from __future__ import annotations

import re
import time
from typing import Set

from .schema import fold

_cache: dict = {"t": 0.0, "titles": set()}
_MIN_LEN = 12


def window_titles(max_age_s: float = 5.0) -> Set[str]:
    if time.time() - _cache["t"] < max_age_s:
        return _cache["titles"]
    titles: Set[str] = set()
    try:
        from core_organs import universal_scan as us
        for _h, (_pid, _cls, title) in us._top_windows().items():
            t = fold(title or "")
            if len(t) >= _MIN_LEN:
                titles.add(t)
    except Exception:
        pass
    _cache.update(t=time.time(), titles=titles)
    return titles


def looks_private(label: str) -> bool:
    lab = fold(label or "")
    if len(lab) < _MIN_LEN:
        return False
    for t in window_titles():
        if lab == t or (len(t) >= _MIN_LEN and (t in lab or lab in t)):
            return True
    return bool(re.search(r"(?i) - (google chrome|microsoft edge|mozilla firefox|brave|opera|file explorer|whatsapp|discord|outlook)$", label or ""))
