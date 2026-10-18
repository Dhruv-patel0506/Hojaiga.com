"""
harvest.start_screen -- an application that opens on a CHOOSER, not on its work area.

Many applications greet you with a question before anything else: Office's start screen (blank document / recent files), a 3D suite's splash (new file / open recent / which template), an IDE's welcome page, a
database client's connection list. A scan that does not recognise this reads the chooser as if it were the application and learns nothing about the real interface -- or opens somebody's previous file.

`pick_start_control` looks at the controls of the first screen and, when it looks like a chooser (a 'recent' list beside an option to start something new), returns the SAFE way in: a blank / new / empty / default
choice, else a skip / not-now / close. Never a recent item, never an 'open' or a 'sign in'. `register` writes the handling to the RAG (Sub-RAG 3 procedure + lexicon) so the agent knows, on the next launch,
what the first screen is and how to get past it. The click itself goes through the recorder's own click path, so it is also a training pair (goal 'Click the <name> ...') and a graph transition.
Nothing here names an application.
"""
from __future__ import annotations

import contextlib
import re
from typing import Any, Dict, List, Optional, Sequence

# in order of preference: start something EMPTY first, then decline / dismiss. 'start' / 'continue' / 'open' / 'sign in' are never in the list.
PREFERENCE = ("blank document", "blank workbook", "blank presentation", "blank database", "blank", "empty document", "empty project", "empty", "new project", "new file", "new document", "new",
              "general", "default", "standard", "skip", "no thanks", "not now", "maybe later", "later", "close")
RECENT_RX = re.compile(r"\b(recent|previous|pinned|open (file|project|model|recent)|last (file|project|session)|continue where|restore)\b", re.I)
NEVER_RX = re.compile(r"\b(open|sign|log ?in|account|buy|purchase|trial|upgrade|subscribe|download|update|install|share|import|recent|previous|restore)\b", re.I)
KINDS = ("ButtonControl", "ListItemControl", "HyperlinkControl", "TabItemControl", "MenuItemControl", "DataItemControl", "RadioButtonControl", "SplitButtonControl")


def looks_like_chooser(controls: Sequence[Dict[str, Any]]) -> bool:
    """A first screen with a 'recent / previous' list or a 'blank / new' choice, and not a full workbench (a screen with hundreds of controls is the application itself)."""
    names = [str(c.get("name", "")) for c in controls]
    if len(names) > 120:
        return False
    has_recent = any(RECENT_RX.search(n) for n in names)
    has_new = any(n.strip().lower() in PREFERENCE[:-3] for n in names)
    return has_recent or has_new


def pick_start_control(controls: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The control to press to get past a chooser, or None when the screen is not one."""
    if not looks_like_chooser(controls):
        return None
    best = None
    for c in controls:
        if c.get("type") not in KINDS and not str(c.get("type", "")).endswith(KINDS):
            continue
        n = str(c.get("name", "")).strip()
        low = n.lower()
        if not n or len(n) > 48 or (NEVER_RX.search(n) and low not in PREFERENCE):
            continue
        for rank, pref in enumerate(PREFERENCE):
            if low == pref or (len(pref) >= 5 and low.startswith(pref + " ")):
                if best is None or rank < best[0]:
                    best = (rank, c)
                break
    return best[1] if best else None


def describe(controls: Sequence[Dict[str, Any]], chosen: Dict[str, Any]) -> Dict[str, Any]:
    names = [str(c.get("name", "")) for c in controls if str(c.get("name", "")).strip()]
    return {"chosen": chosen.get("name", ""), "recent_entries": [n for n in names if RECENT_RX.search(n)][:6], "options": [n for n in names if n.strip().lower() in PREFERENCE][:8], "n_controls": len(names)}


def register(rag: Any, app_key: str, app_name: str, info: Dict[str, Any]) -> Dict[str, int]:
    """The chooser and how to pass it -> Sub-RAG 3 (a procedure) and the lexicon."""
    n = {"procedures": 0, "commands": 0}
    if rag is None:
        return n
    with contextlib.suppress(Exception):
        steps = [{"text": f"START SCREEN: {app_name} opens on a chooser, not on its work area. Options seen: {', '.join(info['options']) or '(none named)'}." + (f" It also lists recent entries ({', '.join(info['recent_entries'])}): never open one." if info["recent_entries"] else ""), "route_hint": "observe"},
                 {"text": f"Click '{info['chosen']}' to start with an empty / new item (never a recent file, never sign in).", "target": info["chosen"], "route_hint": "uia_invoke"}]
        r = rag.proc.ingest_procedure(app_key, f"Get past the start screen of {app_name} (choose '{info['chosen']}')", steps, "local_recorder:start_screen", trust="learned")
        n["procedures"] += r.inserted + r.updated
    with contextlib.suppress(Exception):
        rag.lex.add_command(app_key, info["chosen"], source="executor", trust="learned")
        n["commands"] += 1
    return n
