"""
agent_verify -- goal-aware verification for the executor loop, and the UIA-name assist for dense icon strips. Pure functions over observation dicts; no GUI, no model.

An observation is {"image", "som", "controls"?}: `controls` (present when the app exposes UI Automation) is [{"name", "type", "box", "toggle"}] where `toggle` is the control's ToggleState (0 off / 1 on / 2 mixed)
or None. A first executor said "done" whenever the screen changed; a click on the WRONG toolbar icon (Link instead of Strikethrough) changes the screen too, opened a dialog, and derailed the rest of the task.
Verification now asks whether the effect matches the INTENT of the step:

    toggle   the target is a toggle control: its state must have flipped, and no dialog may have opened
    dialog   the step is meant to open one (its name says so: Link, Open, Save As, Font, Find ...): a modal must appear
    plain    anything else: the screen changed and no unexpected modal appeared
    and, when the goal names its control explicitly ("Click the Strikethrough button"), the control that was actually operated must carry that name -- whatever the screen did.

Where the app exposes no UIA tree the modal / toggle / name rules cannot be applied and only the base "the screen changed" test runs (said so in the verdict: `checked`).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

DIALOG_WORDS = ("link", "open", "save as", "font", "find", "replace", "go to", "settings", "options", "properties", "insert", "share", "print", "about", "browse", "preferences", "new window")
_EXPLICIT = re.compile(r"^\s*click\s+(?:on\s+)?(?:the\s+)?(.+?)\s+(?:button|menu item|tab|item|option|checkbox|tree item|toggle button)\s*$", re.I)
_CHORD = re.compile(r"\b(?:ctrl|control|shift|alt|cmd|win|fn)\s*\+\s*[a-z0-9]+\b|\([^)]*\)", re.I)


def explicit_name(goal: str) -> str:
    """The control a goal names when it is phrased 'Click the <name> <kind>', else ''. Paraphrased goals ('make the text bold') name no control: the name rule is then not applied."""
    m = _EXPLICIT.match(goal or "")
    return re.sub(r"\s+", " ", _CHORD.sub(" ", m.group(1))).strip() if m else ""


def _tokens(s: str) -> set:
    out = set()
    for w in re.findall(r"[a-z0-9]+", _CHORD.sub(" ", (s or "").lower())):
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        if len(w) > 1:
            out.add(w)
    return out


def name_match(wanted: str, actual: str) -> bool:
    """Every word of the wanted name is in the control's name ('Bold' ~ 'Bold (Ctrl+B)'), shortcut hints ignored."""
    w, a = _tokens(wanted), _tokens(actual)
    return bool(w) and w <= a


def control_for_box(controls: Sequence[Dict[str, Any]], box: Sequence[float]) -> Optional[Dict[str, Any]]:
    """The smallest control whose rectangle contains the centre of `box` (the element the model picked)."""
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    best = None
    for c in controls or []:
        x, y, w, h = c["box"]
        if x <= cx <= x + w and y <= cy <= y + h and (best is None or w * h < best["box"][2] * best["box"][3]):
            best = c
    return best


def _names(obs: Dict[str, Any]) -> set:
    return {(c.get("type", ""), (c.get("name") or "").lower()) for c in obs.get("controls") or [] if c.get("name")}


DISMISS_NAMES = {"cancel", "close", "ok", "no", "done", "apply", "insert", "save", "don't save", "dont save", "discard"}


def modal_change(pre: Dict[str, Any], post: Dict[str, Any]) -> Dict[str, Any]:
    """A dialog / overlay opened when several NEW controls appear AND either a good part of the old ones vanish (a Win32 modal disables the app behind it, so UIA stops listing it) or one of the new
    controls is a dismissal button (Cancel / Close / OK ...: MEASURED on Notepad's XAML Link dialog, whose toolbar stays listed behind it, so only the second signal fires). UIA-only."""
    a, b = _names(pre), _names(post)
    new, lost = sorted(n for _t, n in (b - a)), len(a - b)
    dismiss = [n for n in new if n in DISMISS_NAMES]
    cancel_like = [n for n in dismiss if n in ("cancel", "no", "discard")]
    # a lone new "Cancel" is enough: UIA lists only the ENABLED actionable controls, and a fresh Link dialog has its Insert button disabled and its fields are edits, so Cancel is the only new entry
    return {"modal": bool((len(new) >= 2 and (lost >= max(2, 0.3 * len(a)) or dismiss)) or cancel_like), "new": new, "lost": lost, "dismiss": dismiss}


def classify(goal_name: str, target: Optional[Dict[str, Any]]) -> str:
    """dialog if the goal or the control's own name says it opens one (checked FIRST: Notepad's 'Link' is a toggle button to UI Automation but opens a dialog), else toggle, else plain."""
    tname = (target or {}).get("name", "")
    low = f"{goal_name} {tname}".lower()
    if tname.endswith("...") or any(re.search(rf"\b{re.escape(w)}\b", low) for w in DIALOG_WORDS):
        return "dialog"
    if target is not None and target.get("toggle") is not None:
        return "toggle"
    return "plain"


def goal_verify(goal: str, action: Dict[str, Any], pre: Dict[str, Any], post: Dict[str, Any], base_worked: bool, base_effect: str) -> Dict[str, Any]:
    """The verdict: {worked, effect, reason, intent, target, checked, new}. `reason` is '' on success, else no_effect | wrong_control | unexpected_dialog | toggle_unchanged | no_dialog."""
    v: Dict[str, Any] = {"worked": False, "effect": base_effect, "reason": "no_effect", "intent": "", "target": "", "checked": "screen", "new": []}
    if not base_worked:
        return v
    v.update(worked=True, reason="")
    have_uia = bool(pre.get("controls")) and bool(post.get("controls"))
    if not have_uia:
        return v                                            # no UIA tree: only "the screen changed" can be checked
    v["checked"] = "uia"
    if action.get("action") == "hotkey":                    # a shortcut opens whatever it opens (a find bar, a dialog, a panel): that IS its effect, not an accident of a mis-aimed click
        return v
    target = None
    if action.get("action") == "click":
        el = next((e for e in pre["som"]["elements"] if e.get("id") == action.get("target_id")), None)
        target = control_for_box(pre["controls"], el["box"]) if el else None
    gname = explicit_name(goal)
    v["target"] = (target or {}).get("name", "")
    mod = modal_change(pre, post)
    v["new"] = mod["new"][:6]
    if gname and target is not None and not name_match(gname, target["name"]):
        return dict(v, worked=False, reason="wrong_control", effect=f"clicked {target['name']!r}, not {gname!r}")
    intent = classify(gname, target) if action.get("action") == "click" else "plain"
    v["intent"] = intent
    if intent in ("dialog", "plain") and (pre.get("doc") or post.get("doc")) and pre.get("doc") != post.get("doc"):
        return dict(v, effect="the document's text changed")                     # a button inside an already-open find / replace bar does its work on the document; no new dialog is the right outcome
    if intent == "toggle":
        if mod["modal"]:
            return dict(v, worked=False, reason="unexpected_dialog", effect="a dialog opened instead of a toggle: " + ", ".join(mod["new"][:4]))
        after = next((c for c in post["controls"] if c.get("name") == target["name"]), None)
        if after is not None and after.get("toggle") == target.get("toggle"):
            return dict(v, worked=False, reason="toggle_unchanged", effect=f"{target['name']!r} did not change state")
        return v
    if intent == "dialog":
        # The step is meant to open a dialog, so a modal appearing is the effect. Whether the NEW controls are "about the goal" cannot be told from button names alone (Notepad's Link dialog lists
        # Display text / Address / Insert / Cancel; the word "link" is only in the title and in edit fields UIA does not list as actionable): the named-control rule above is what stops a wrong opener.
        if not mod["modal"]:
            return dict(v, worked=False, reason="no_dialog", effect="no dialog opened")
        return v
    if mod["modal"]:
        return dict(v, worked=False, reason="unexpected_dialog", effect="an unexpected dialog opened: " + ", ".join(mod["new"][:4]))
    return v


def uia_assist(goal: str, action: Optional[Dict[str, Any]], pre: Dict[str, Any], element_at: Any) -> Tuple[Optional[Dict[str, Any]], str]:
    """For an app that exposes UIA: when the goal names its control explicitly and the model's target is a DIFFERENT control, and exactly one control carries that name, point the action at that one.
    (Measured: the adjacent unnamed toolbar icons, ~16 px each, shrink to ~7 px at the model's input size and look alike; their UIA names do not.) Returns (new action | None, note)."""
    gname = explicit_name(goal)
    controls = pre.get("controls") or []
    if not gname or not controls or not isinstance(action, dict) or action.get("action") != "click":
        return None, ""
    el = next((e for e in pre["som"]["elements"] if e.get("id") == action.get("target_id")), None)
    cur = control_for_box(controls, el["box"]) if el else None
    if cur is not None and name_match(gname, cur["name"]):
        return None, ""
    named = [c for c in controls if name_match(gname, c["name"])]
    if len(named) != 1:
        return None, ""
    target_el = element_at(pre["som"], named[0]["box"])
    if target_el is None:
        return None, ""
    return dict(action, target_id=target_el["id"]), f"UIA name assist: {(cur or {}).get('name', '?')!r} -> {named[0]['name']!r}"
