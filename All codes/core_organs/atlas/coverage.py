"""
atlas.coverage -- how do we KNOW the scan was complete?

Three independent answers, none of which needs to know the application:

  1. independent_recall   walk the live window with a DIFFERENT UI Automation implementation (the `uiautomation` library, not fast_uia),
                          collect every named, actionable control, and ask what share of them the knowledge base already holds.
  2. exhaustion           run the explorer a second time over the same window; if it discovers nothing new (no new command, dialog,
                          transition) the reachable surface is exhausted -- the universal, oracle-free proof.
  3. oracles              OPTIONAL independent lists (a truth file the program ships, its own menu resources, its COM object model).
                          They only sharpen the number; they never gate what is discovered.

Everything is reported as measured numbers with the sets that disagree, so a gap is a list of names, not a feeling.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from . import common as C

ACTIONABLE_TYPES = {"ButtonControl", "MenuItemControl", "TabItemControl", "CheckBoxControl", "RadioButtonControl", "ListItemControl", "ComboBoxControl",
                    "SplitButtonControl", "HyperlinkControl", "TreeItemControl", "SliderControl", "SpinnerControl", "EditControl", "ToggleButtonControl"}
CHROME = {"minimize", "maximize", "restore", "close", "system", "keep on top"}


def nm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"\(.*?\)|&", "", (s or "").lower())).strip()


def independent_names(hwnd: int, *, max_nodes: int = 6000, budget_s: float = 8.0) -> Dict[str, Any]:
    """Names of actionable controls of the window found by an independent walk (uiautomation library)."""
    t0 = time.time()
    out: Dict[str, Any] = {"names": set(), "walked": 0, "error": ""}
    try:
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(hwnd)
            stack = [root]
            while stack and out["walked"] < max_nodes and time.time() - t0 < budget_s:
                c = stack.pop()
                out["walked"] += 1
                try:
                    if c.ControlTypeName in ACTIONABLE_TYPES and (c.Name or "").strip() and nm(c.Name) not in CHROME:
                        out["names"].add(nm(c.Name))
                    stack.extend(c.GetChildren())
                except Exception:
                    continue
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
    out["seconds"] = round(time.time() - t0, 2)
    return out


def known_names(model, app_key: str) -> Set[str]:
    names: Set[str] = set()
    try:
        for r in model._conn.execute("SELECT name, menu_path FROM bm_commands WHERE app_key=?", (app_key,)):
            names.add(nm(r[0]))
            if r[1]:
                names.update(nm(p) for p in str(r[1]).split(">"))
    except Exception:
        pass
    try:
        for r in model._conn.execute("SELECT name FROM bm_layout WHERE app_key=?", (app_key,)):
            names.add(nm(r[0]))
    except Exception:
        pass
    try:
        for r in model._conn.execute("SELECT controls_json FROM bm_dialogs WHERE app_key=?", (app_key,)):
            for c in json.loads(r[0] or "[]"):
                names.add(nm(c.get("name", "") if isinstance(c, dict) else str(c)))
    except Exception:
        pass
    names.discard("")
    return names


def independent_recall(model, app_key: str, hwnd: int) -> Dict[str, Any]:
    ind = independent_names(hwnd)
    known = known_names(model, app_key)
    seen = ind["names"]
    hit = {n for n in seen if n in known or any(n in k or k in n for k in known if len(k) >= 4 and len(n) >= 4)}
    miss = sorted(seen - hit)
    return {"independent_controls": len(seen), "known": len(hit), "recall": round(len(hit) / len(seen), 4) if seen else None, "missing": miss[:60],
            "walked": ind["walked"], "seconds": ind["seconds"], "error": ind["error"]}


# --------------------------------------------------------------------------------------------------
# oracles (optional, pluggable, generic)
# --------------------------------------------------------------------------------------------------

class Oracle:
    name = "oracle"

    def commands(self) -> Set[str]:
        return set()


class TruthFileOracle(Oracle):
    """A JSON file a test program (or a program that ships a command list) provides: {'menu_items': [...], 'toolbar': [...], 'controls': [...], 'dialogs': {...}}."""
    name = "truth-file"

    def __init__(self, path: str):
        self.path = path

    def commands(self) -> Set[str]:
        with open(self.path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        out: Set[str] = set()
        for it in d.get("menu_items", []):
            out.add(nm(it.split(">")[-1]))
        for k in ("toolbar", "controls", "tabs"):
            out.update(nm(x) for x in d.get(k, []))
        for ctrls in d.get("dialogs", {}).values():
            out.update(nm(x) for x in ctrls)
        out.discard("")
        return out


class StaticMenuOracle(Oracle):
    """The program's own menu resources (classic Win32 programs): declared commands the live scan should also have found."""
    name = "pe-menu-resources"

    def __init__(self, exe: str):
        self.exe = exe

    def commands(self) -> Set[str]:
        from core_organs import pe_resources as pr
        res = pr.read_resources(self.exe)
        out = {nm(c["name"]) for c in pr.commands_from_resources(res) if c.get("name")}
        out.discard("")
        return out


def oracle_coverage(model, app_key: str, oracle: Oracle) -> Dict[str, Any]:
    want = oracle.commands()
    have = known_names(model, app_key)
    got = {w for w in want if w in have or any(w in h or h in w for h in have if len(h) >= 4 and len(w) >= 4)}
    return {"oracle": oracle.name, "declared": len(want), "discovered": len(got), "coverage": round(len(got) / len(want), 4) if want else None, "missing": sorted(want - got)[:60]}


def exhaustion(model, app_key: str, before: Dict[str, Any], after: Dict[str, Any], *, names_before: Optional[Set[str]] = None,
               dialogs_before: Optional[Set[str]] = None, dialogs_after: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Did a repeat exploration find anything NEW? Judged by DISTINCT names (commands, control labels, dialog titles) -- row counts also move when the
    same knowledge is re-written, which is not discovery."""
    keys = ("commands", "dialogs", "regions", "statevars", "transitions")
    rows = {k: max(0, (after.get(k) or 0) - (before.get(k) or 0)) for k in keys}
    new_names = sorted(known_names(model, app_key) - (names_before or set()))
    new_dialogs = sorted((dialogs_after or set()) - (dialogs_before or set()))
    return {"new_names": new_names[:40], "n_new_names": len(new_names), "new_dialogs": new_dialogs, "row_gain": rows,
            "exhausted": not new_names and not new_dialogs, "frontier_open": (after.get("frontier") or {}).get("by_status", {}).get("open", 0)}
