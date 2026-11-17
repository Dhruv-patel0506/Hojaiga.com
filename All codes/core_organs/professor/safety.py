"""
professor.safety -- one place that decides whether a verb / control may be TRIED by the Professor (probing, hover, execution), and what to do when it may not.

Classes (a verb gets exactly one, the first that matches):
  unsafe     destroys or leaves: exit, close, delete, remove, erase, format, uninstall, sign out, reset all ...           -> never tried automatically
  sensitive  captures, sends, publishes, signs in, pays, shares, prints, goes online, records screen / camera / microphone  -> never tried automatically
  runtime    starts something that keeps running or takes over the screen: present, play, run, record, start, launch      -> never tried automatically
  commit     applies / saves / overwrites / imports / exports (changes files or settings, usually reversible only by hand)   -> needs a human yes
  safe       everything else (select, add, insert, show, toggle, zoom, undo, ...)
The patterns are the ones Atlas learned the hard way (a scan once started a slide show and a screen capture); they are reused, not re-invented, and are CATEGORIES of
wording, never application names (law L3). Input of any kind is only ever sent to a window the Professor launched itself or one the user explicitly authorised.
"""

from __future__ import annotations

import re
from typing import Tuple

try:                                                                                    # the Atlas lists are the source of truth when importable
    from core_organs.atlas.explorer import SENSITIVE_RX, UNSAFE_RX
    from core_organs.atlas.uimap import RUNTIME_RX
except Exception:                                                                       # pragma: no cover - standalone fallback with the same intent
    UNSAFE_RX = re.compile(r"\b(exit|quit|close|delete|remove|erase|format|uninstall|sign out|log ?out|shutdown|restart|kill|terminate|empty|wipe|purge|factory|reset all)\b", re.I)
    SENSITIVE_RX = re.compile(r"\b(record(ing)?|capture|screenshot|camera|webcam|microphone|share|send|e-?mail|publish|post|upload|sign ?(in|out)|log ?(in|out)|account|profile|"
                              r"print|fax|pay|purchase|buy|subscribe|activate|license|online|cloud)\b", re.I)
    RUNTIME_RX = re.compile(r"\b(from beginning|present(ing)?|play|start|run|preview|rehearse|launch|go live|broadcast|stream|connect|join|begin|resume|record(ing)?)\b", re.I)

COMMIT_RX = re.compile(r"\b(save|save as|overwrite|apply|ok|import|export|replace|install|merge|commit|publish|confirm|accept|yes|done|finish)\b", re.I)
# wording that REPLACES the user's current work without deleting a named thing: a bare 'New' (new document), clear / revert / discard / reset (reset view-like verbs excepted)
REPLACES_RX = re.compile(r"^\s*new(\.\.\.)?\s*$|\b(clear|revert|discard)\b|\breset\b(?!\s+(view|zoom|layout|camera|selection))", re.I)
CHROME = {"minimize", "maximize", "restore", "close", "system"}


STORAGE_RX = re.compile(r"\b(disk|drive|partition|volume|card|storage|usb|device|media|memory|hard ?drive|ssd)\b", re.I)


def _only_text_formatting(label: str, path: str = "") -> bool:
    """'Format Text Effects', 'Format Painter', 'Format Shape...': FORMATTING content, not formatting a disk. True when 'format' is the only destructive word of the label and nothing
    in the label or its path names storage (then it is classified like any other command - it changes the look of the run's own document)."""
    words = {m.group(0).lower() for m in UNSAFE_RX.finditer(label)}
    return words <= {"format"} and bool(words) and not STORAGE_RX.search(f"{path} {label}")


# a MODE / SURFACE of the interface a person walks in and out of; closing one returns to the document, it destroys nothing
VIEW_SURFACE_RX = re.compile(r"\b(header|footer|pane|panel|ribbon|tool ?bar|side ?bar|sidebar|view|preview|navigator|search|menu|dock|flyout|dialog box|start screen|start page)\b", re.I)


def _closes_a_view(label: str) -> bool:
    """'Close Header and Footer', 'Exit Preview', 'Close the search box': the destructive word only LEAVES a surface of the interface - navigation, not loss. 'Close file', 'Exit the
    application', 'Close tab' keep their weight (no surface word)."""
    words = {m.group(0).lower() for m in UNSAFE_RX.finditer(label)}
    return bool(words) and words <= {"close", "exit"} and bool(VIEW_SURFACE_RX.search(label))


def classify(label: str, path: str = "") -> str:
    """'unsafe' | 'sensitive' | 'runtime' | 'commit' | 'safe' for a verb label (and the menu path it lives under)."""
    text = f"{path} {label}".strip()
    if not label:
        return "safe"
    if UNSAFE_RX.search(label) and not _only_text_formatting(label, path) and not _closes_a_view(label):
        return "unsafe"
    if SENSITIVE_RX.search(label) or SENSITIVE_RX.search(path or ""):
        return "sensitive"
    if RUNTIME_RX.search(label):
        return "runtime"
    if COMMIT_RX.search(label) or REPLACES_RX.search(label):
        return "commit"
    return "safe"


def may_probe(label: str, path: str = "", owned: bool = False) -> Tuple[bool, str]:
    """(allowed, reason). Probing only ever tries 'safe' verbs; 'commit' verbs only in a window the Professor owns (a fixture / a document it created)."""
    c = classify(label, path)
    if c == "safe":
        return True, "safe"
    if c == "commit" and owned:
        return True, "commit verb in an owned window"
    return False, c


def needs_human(label: str, path: str = "") -> bool:
    """Execution: anything that is not plainly safe goes to the learner for a yes (never auto-accepted)."""
    return classify(label, path) != "safe"


# inverse pairs used to put the application back after a probe (the first matching rule wins); `{x}` is whatever follows the verb
INVERSES = [(r"^add (.+)$", ["clear {x}s", "clear {x}", "remove {x}", "delete {x}"]), (r"^insert (.+)$", ["undo"]), (r"^show (.+)$", ["hide {x}"]), (r"^hide (.+)$", ["show {x}"]),
            (r"^zoom in$", ["zoom out"]), (r"^zoom out$", ["zoom in"]), (r"^enable (.+)$", ["disable {x}"]), (r"^disable (.+)$", ["enable {x}"]),
            (r"^expand (.+)$", ["collapse {x}"]), (r"^collapse (.+)$", ["expand {x}"])]


def inverse_candidates(label: str) -> list:
    low = (label or "").strip().lower()
    for rx, outs in INVERSES:
        m = re.match(rx, low)
        if m:
            x = m.group(1) if m.groups() else ""
            return [o.format(x=x).strip() for o in outs]
    return []
