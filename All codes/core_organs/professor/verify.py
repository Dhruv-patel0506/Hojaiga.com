"""
professor.verify -- EVERY STEP CHECKED AGAINST ITS STATED EXPECTED RESULT.

'Something changed' is not the same as 'the step did what it says'. Each step carries an EXPECTATION, taken from the best source available:

  1 the guide itself     the manual's own result sentence right after the step: 'The Font dialog box opens', 'A new slide is added', 'The Header and Footer box appears', 'X is displayed'
  2 the control          what the catalog knows the control does: opens a dialog / a menu (leads_to), a toggle / check box flips, a field takes the value, a tab switches the context
  3 the step kind        typed text appears; a key is delivered; a pick from an open menu closes it
and after the step the screen is CHECKED for that specific outcome (new window whose title / controls carry the expected words, items appeared, the toggle state flipped, the field
shows the value, the text is there). The verdict is True / False / None (cannot tell from the tree: then the vision model's before/after check, when it runs, is the tiebreak).

  expectation_for(step, verb, guide_text)   -> Expectation(kind, words, source, said)
  check(exp, s0, s1, d, nodes)              -> (verdict, evidence)
Nothing here names an application; the result sentences are the general patterns manuals use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

from .schema import fold

RESULT_RX = re.compile(r"(?i)(?:the\s+)?\**([A-Z][\w &/.'-]{1,60}?)\**\s+(?:dialog box|dialog|window|pane|panel|menu|gallery|tab|list|box|page|view|bar|toolbar)?\s*(?:opens|appears|is displayed|is shown|"
                       r"pops up|is added|is inserted|is created|is applied|changes|is selected|becomes active|is turned on|is turned off|displays)\b")
SAID_RX = re.compile(r"(?i)\b(opens|appears|is displayed|is shown|pops up|is added|is inserted|is created|is applied|changes to|is selected|becomes|is turned (?:on|off)|you(?:'ll| will) see|you see)\b")
KIND_OF_SAID = [(re.compile(r"(?i)\b(dialog|window|box)\b.*\b(opens|appears|is displayed|pops up)\b|\b(opens|appears)\b.*\b(dialog|window)\b"), "dialog_opens"),
                (re.compile(r"(?i)\b(menu|gallery|list|drop-?down)\b.*\b(opens|appears|is displayed)\b"), "menu_opens"),
                (re.compile(r"(?i)\b(pane|panel|sidebar|task pane)\b.*\b(opens|appears|is displayed)\b"), "panel_opens"),
                (re.compile(r"(?i)\b(is added|is inserted|is created)\b"), "content_added"),
                (re.compile(r"(?i)\b(is turned on|is turned off|is selected|becomes active|is checked|is cleared)\b"), "state_changes")]


@dataclass
class Expectation:
    kind: str = "state_changes"          # dialog_opens | menu_opens | panel_opens | content_added | toggled | value_set | text_appears | key_delivered | state_changes | nothing
    words: List[str] = field(default_factory=list)
    source: str = "default"              # guide | control | step
    said: str = ""                       # the manual's own words, when it said what should happen

    def text(self) -> str:
        w = f" ({', '.join(self.words[:3])})" if self.words else ""
        return {"dialog_opens": "a dialog opens", "menu_opens": "a menu / gallery opens", "panel_opens": "a pane opens", "content_added": "something is added to the document",
                "toggled": "the option flips", "value_set": "the field shows the value", "text_appears": "the typed text appears", "key_delivered": "the key is delivered",
                "state_changes": "the application's state changes", "nothing": "nothing (skipped)"}.get(self.kind, self.kind) + w


def result_sentence(guide_text: str, raw_step: str) -> str:
    """The sentence of the manual right after a step that states what happens ('The Font dialog box opens.'), '' when there is none."""
    if not guide_text or not raw_step:
        return ""
    clean = guide_text.replace("**", "")
    key = raw_step.replace("**", "").strip()[:60]
    i = clean.find(key[:40]) if key else -1
    if i < 0:
        return ""
    tail = clean[i + len(key):i + len(key) + 260]
    for sent in re.split(r"(?<=[.!?])\s+|\n", tail)[:3]:
        if SAID_RX.search(sent) and not re.match(r"(?i)^\s*(\d+[.)]|select|click|choose|press|type|open|go to)\b", sent):
            return sent.strip()
    return ""


def expectation_for(step: Any, verb: Any = None, guide_text: str = "") -> Expectation:
    kind = getattr(step, "kind", "verb")
    raw = getattr(step, "goal", "") or ""
    said = result_sentence(guide_text, raw) if guide_text else ""
    m_inline = SAID_RX.search(raw.split(".", 1)[1]) if "." in raw[:-1] else None
    if said or m_inline:
        s = said or raw
        for rx, k in KIND_OF_SAID:
            if rx.search(s):
                m = RESULT_RX.search(s)
                words = [m.group(1).strip()] if m else []
                return Expectation(k, words, "guide", s[:160])
        return Expectation("state_changes", [], "guide", s[:160])
    if kind == "skip":
        return Expectation("nothing", [], "step")
    if kind == "text":
        return Expectation("text_appears", [getattr(step, "text", "")[:40]], "step")
    if kind == "key":
        return Expectation("key_delivered", [getattr(step, "text", "")], "step")
    if kind == "dialog_button":
        return Expectation("state_changes", [], "step", "the dialog takes the answer")
    if verb is not None:
        lead = (getattr(verb, "leads_to", "") or "").lower()
        role = getattr(verb, "role", "")
        if "dialog" in lead:
            return Expectation("dialog_opens", [verb.label], "control")
        if "menu" in lead or "submenu" in lead:
            return Expectation("menu_opens", [verb.label], "control")
        if "page" in lead or "panel" in lead:
            return Expectation("panel_opens", [verb.label], "control")
        if role in ("toggle", "checkbox") or getattr(step, "want", ""):
            return Expectation("toggled", [verb.label], "control")
        if getattr(step, "text", "") and role in ("field", "edit", "text_field"):
            return Expectation("value_set", [getattr(step, "text", "")], "control")
        if role == "tab":
            return Expectation("state_changes", [verb.label], "control", "the tab's contents show")
    return Expectation("state_changes", [], "default")


def check(exp: Expectation, s0: Any, s1: Any, d: Any, nodes_after: Sequence[Any] = ()) -> Tuple[Optional[bool], str]:
    """Does what the screen shows now match the expectation?"""
    if exp.kind in ("nothing",):
        return True, "nothing was expected"
    if exp.kind == "key_delivered":
        return True, "a key has no visible result of its own"
    eff = d.effect() if d is not None else "no_effect"
    if eff == "already_satisfied":
        return True, d.summary() if hasattr(d, "summary") else "already in requested state / mode"
    added = [a for a in (getattr(d, "added", []) or [])]
    names_now = " | ".join(fold(getattr(n, "name", "") or "") for n in nodes_after)
    words = [fold(w) for w in exp.words if w]
    texts_now = " | ".join(fold(v) for v in list((getattr(s1, "texts", {}) or {}).values()))
    if exp.kind == "dialog_opens":
        if getattr(d, "new_windows", None):
            hit = [w for w in words if w and w in names_now]
            return True, "a new window opened" + (f" showing '{exp.words[0]}'" if hit else "")
        if eff == "context_change" or len(added) >= 3:
            return True, "a new surface with its own controls appeared inside the window"
        if words and any(w in names_now for w in words):
            return True, f"dialog / window showing '{exp.words[0]}' is already open"
        return False, f"expected a dialog to open; seen: {d.summary() if d is not None else 'nothing'}"
    if exp.kind in ("menu_opens", "panel_opens"):
        if getattr(d, "new_windows", None) or len(added) >= 2 or eff in ("context_change", "opens_dialog"):
            return True, f"{len(added)} item(s) appeared"
        if words and any(w in names_now for w in words):
            return True, f"pane / menu showing '{words[0]}' is already active"
        return False, f"expected {exp.text()}; seen: {d.summary() if d is not None else 'nothing'}"
    if exp.kind == "toggled":
        if getattr(d, "changed_state", None):
            return True, "the state flipped: " + "; ".join(f"{k}: {a}->{b}" for k, a, b in d.changed_state[:2])
        for n in nodes_after:
            if n.name and words and any(w == fold(n.name) for w in words):
                if getattr(n, "toggle_state", -1) != -1:
                    return True, f"'{n.name}' toggle is in requested state"
        return (None, "no state flag changed in the tree (the toolkit may not expose it)") if eff != "no_effect" else (False, "nothing changed")
    if exp.kind in ("value_set", "text_appears"):
        want = words[0] if words else ""
        if want and (want in texts_now or want in names_now):
            return True, f"'{exp.words[0]}' is shown"
        if eff != "no_effect":
            return None, "the screen changed, but the text is not readable from the tree"
        return False, f"'{exp.words[0] if exp.words else ''}' is not shown"
    if exp.kind == "content_added":
        if added or getattr(d, "changed_text", None) or eff != "no_effect":
            return True, "the document changed"
        return False, "nothing was added"
    if eff != "no_effect":
        return True, d.summary()[:120]
    if exp.kind == "state_changes":
        for n in nodes_after:
            if n.name and words and any(w == fold(n.name) for w in words):
                if getattr(n, "selected", None) is True:
                    return True, f"'{n.name}' is already selected"
        hit = [w for w in words if w and (w in names_now or w in texts_now)]
        if hit:
            return True, f"already in requested state / mode ('{hit[0]}' active)"
    return False, "nothing changed"
