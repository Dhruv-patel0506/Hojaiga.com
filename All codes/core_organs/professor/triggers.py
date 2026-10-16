"""professor.triggers -- TRIGGER BUTTONS: a few verified stand-ins for controls the run could not operate.

When EVERY ordinary route of a control the guide needs failed (the control was not found, or acting on it changed nothing), the executor may look for another way in to the SAME
command - the same command filed elsewhere in the catalog (another tab / menu / panel), that command's own id through the application's object model or scripting engine, its
shortcut, or the point where the vision scan saw it - and try those once. The first one that produces a visible effect is kept as a TRIGGER for that control: next time it is
the first thing tried, so the run does not grope through failing routes again.

Triggers are exceptional on purpose (an automation with many private shortcuts becomes unpredictable):
  * created only for a step of the application's own guide, and only after all ordinary routes failed
  * only for commands classified 'safe' or 'commit' (never unsafe / sensitive / runtime) and never from a context menu
  * kept only when the effect was SEEN (a before/after difference, or the application's own engine reporting the command finished)
  * capped: at most MAX_PER_APP live triggers per application, at most MAX_NEW_PER_RUN created per run
  * retired after RETIRE_AFTER consecutive failures (the application changed; the ordinary routes take over again)
Stored per application in data/professor/triggers/<app>.json, with how each one was found and its record."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from . import config as CFG
from .schema import fold

TRIGGER_DIR = os.path.join(CFG.DATA_DIR, "triggers")
MAX_PER_APP = int(os.environ.get("HOJAIGA_TRIGGERS_MAX", "8"))
MAX_NEW_PER_RUN = int(os.environ.get("HOJAIGA_TRIGGERS_NEW_PER_RUN", "3"))
RETIRE_AFTER = 2
ALLOWED_SAFETY = ("safe", "commit")


@dataclass
class Trigger:
    target: str                      # the control it stands in for: 'path > label' (folded)
    label: str
    via: str                         # the catalog entry whose route works: its text path
    route: str                       # that entry's route label ('object_model:mso:HeaderFooterEditHeader', 'control:...', 'shortcut:Ctrl+E', 'click:...')
    why: str = ""                    # how it was found
    created: float = field(default_factory=time.time)
    uses: int = 0
    ok: int = 0
    fails_in_row: int = 0
    retired: bool = False
    last: float = 0.0


def target_key(v: Any) -> str:
    return fold(" > ".join([str(p) for p in (getattr(v, "path", None) or [])] + [getattr(v, "label", "") or ""]))


class TriggerBank:
    """The triggers of ONE application (loaded once per run, saved after every change)."""

    def __init__(self, app_key: str, path: str = ""):
        self.app_key = app_key or "app"
        self.path = path or os.path.join(TRIGGER_DIR, self.app_key + ".json")
        self.items: Dict[str, Trigger] = {}
        self.new_this_run = 0
        self.events: List[Dict[str, Any]] = []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for d in json.load(fh).get("triggers", []):
                    t = Trigger(**{k: d[k] for k in Trigger.__dataclass_fields__ if k in d})
                    self.items[t.target] = t
        except Exception:
            pass

    # ------------------------------------------------------------------ reading
    def active(self) -> List[Trigger]:
        return [t for t in self.items.values() if not t.retired]

    def get(self, v: Any) -> Optional[Trigger]:
        t = self.items.get(target_key(v))
        return t if t is not None and not t.retired else None

    def may_create(self, v: Any) -> str:
        """'' when a new trigger may be created for this control, else why not."""
        if getattr(v, "safety", "safe") not in ALLOWED_SAFETY:
            return f"not for a '{v.safety}' command"
        if v.path and str(v.path[0]).startswith("Context menu"):
            return "not for a context-menu item"
        old = self.items.get(target_key(v))
        if old is not None and old.retired:
            return "a trigger for it was retired (it stopped working)"
        if self.new_this_run >= MAX_NEW_PER_RUN:
            return f"this run already created {MAX_NEW_PER_RUN} triggers"
        if len(self.active()) >= MAX_PER_APP:
            return f"the application already has {MAX_PER_APP} triggers"
        return ""

    # ------------------------------------------------------------------ writing
    def create(self, v: Any, via: Any, route_label: str, why: str) -> Trigger:
        t = Trigger(target_key(v), v.label, via.text_path, route_label, why, uses=1, ok=1, last=time.time())
        self.items[t.target] = t
        self.new_this_run += 1
        self.events.append({"created": t.target, "via": t.via, "route": t.route, "why": why})
        self.save()
        return t

    def record(self, t: Trigger, worked: bool) -> None:
        t.uses += 1
        t.last = time.time()
        if worked:
            t.ok += 1
            t.fails_in_row = 0
        else:
            t.fails_in_row += 1
            if t.fails_in_row >= RETIRE_AFTER:
                t.retired = True
                self.events.append({"retired": t.target, "after": t.fails_in_row})
        self.save()

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump({"app": self.app_key, "max_per_app": MAX_PER_APP, "triggers": [asdict(t) for t in self.items.values()]}, fh, indent=1, ensure_ascii=False)
        except Exception:
            pass

    def summary(self) -> Dict[str, Any]:
        return {"active": len(self.active()), "retired": sum(1 for t in self.items.values() if t.retired), "created_this_run": self.new_this_run, "events": self.events[-12:]}
