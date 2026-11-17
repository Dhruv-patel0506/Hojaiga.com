"""Popup trap disambiguation (RAG 5 front end).

The adapters were trained on prompts with one listed element, so their prior is
``target_id: 1``.  When a modal offers both a work-losing button and a work-keeping
one, the choice has to come from what each button *does*, not from the prior.

``resolve`` reads the numbered controls out of a prompt (both the trained
``#<id> button '<label>'`` form and the ``[<id>] Button '<label>'`` form), scores each
label by its effect on unsaved work, and returns the safest id with the reason.
A model reply that picks a work-losing button is overridden by ``guard_reply``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_CTRL_RES = (
    # the label may itself contain an apostrophe ("Don't Save"): close on a quote that precedes the
    # coordinate bracket/paren or the end of the line
    re.compile(r"#(\d+)\s+(\w+)\s+'(.+?)'(?=\s*[\[(]|\s*$)", re.M),
    re.compile(r"\[(\d+)\]\s+(\w+)\s+'(.+?)'(?=\s*[\[(]|\s*$)", re.M),
)
_POPUP_CUES = ("popup", "pop-up", "modal", "dialog", "unsaved", "are you sure", "confirm",
               "resolve the", "without losing")

# Effect on the user's work.  Phrase-level first so "don't save" is not read as "save".
_DESTRUCTIVE = ("don't save", "dont save", "do not save", "without saving", "without save",
                "without backing", "no save", "discard", "delete", "remove", "erase",
                "overwrite", "replace", "revert", "reset", "close without", "exit without",
                "lose", "abandon", "throw away", "permanently", "format", "empty", "wipe", "clear all",
                "yes, delete", "uninstall", "sign out", "log out", "quit anyway")
_PRESERVING = ("save", "keep", "stay", "continue", "go back", "back to", "return to", "resume",
               "cancel", "not now", "later", "no thanks", "backup", "back up", "export", "apply")
_COMMIT_ONLY = ("ok", "yes", "confirm", "proceed", "accept", "agree", "allow", "done")


@dataclass
class Control:
    id: int
    role: str
    label: str
    score: float = 0.0
    why: str = ""


@dataclass
class Resolution:
    is_popup: bool
    controls: List[Control] = field(default_factory=list)
    safest: Optional[Control] = None
    destructive_ids: List[int] = field(default_factory=list)


def parse_controls(prompt: str) -> List[Control]:
    seen: Dict[int, Control] = {}
    for rx in _CTRL_RES:
        for m in rx.finditer(prompt):
            cid = int(m.group(1))
            seen.setdefault(cid, Control(cid, m.group(2).lower(), m.group(3).strip()))
    return list(seen.values())


def _label_score(label: str):
    l = label.lower()
    neg = [w for w in _DESTRUCTIVE if w in l]
    if neg:
        return -10.0, f"loses work ('{neg[0]}')"
    pos = [w for w in _PRESERVING if re.search(rf"\b{re.escape(w)}", l)]
    if pos:
        # "Save & Continue" beats a bare "Cancel": it keeps the work and finishes the task.
        bonus = 2.0 if ("save" in l or "keep" in l) else 0.0
        return 5.0 + bonus + 0.5 * len(pos), f"keeps work ('{pos[0]}')"
    if l in _COMMIT_ONLY:
        return 1.0, "neutral commit"
    return 0.0, "unknown effect"


def resolve(prompt: str) -> Resolution:
    controls = parse_controls(prompt)
    low = prompt.lower()
    is_popup = bool(controls) and any(c in low for c in _POPUP_CUES)
    for c in controls:
        c.score, c.why = _label_score(c.label)
    destructive = [c.id for c in controls if c.score <= -10.0]
    safest = None
    if controls:
        ranked = sorted(controls, key=lambda c: c.score, reverse=True)
        # Only a positive-scoring, non-destructive control counts as a safe resolution.
        if ranked[0].score > 0:
            safest = ranked[0]
    return Resolution(is_popup, controls, safest, destructive)


def prompt_hint(res: Resolution) -> str:
    """Prompt text for the model: names the trap and the safe control in the prompt's own ids."""
    if not (res.is_popup and res.safest):
        return ""
    trap = ", ".join(f"[{i}]" for i in res.destructive_ids)
    out = f"\n[POPUP_PLAYBOOK]: safe control is target_id {res.safest.id} ('{res.safest.label}', {res.safest.why})."
    if trap:
        out += f" Never choose {trap}: it loses work."
    return out


def guard_reply(raw_reply: str, res: Resolution) -> tuple[str, bool]:
    """If the reply targets a work-losing (or lower-ranked) control in a popup, swap in the safest id."""
    if not (res.is_popup and res.safest):
        return raw_reply, False
    try:
        data = json.loads(raw_reply)
    except Exception:
        data = None
    items = data if isinstance(data, list) else ([data] if isinstance(data, dict) else None)
    if not items or not isinstance(items[0], dict):
        item = {"step": 1, "action": "click", "target_id": res.safest.id, "hotkey": None, "text": None,
                "verify_expectation": f"Popup closed via '{res.safest.label}' with work preserved"}
        return json.dumps([item]), True
    item = items[0]
    tid = item.get("target_id", item.get("id", item.get("target")))
    by_id = {c.id: c for c in res.controls}
    try:
        cur = by_id.get(int(tid))
    except (TypeError, ValueError):
        cur = None
    if cur is None or cur.score < res.safest.score:
        item["action"] = "click"
        item["target_id"] = res.safest.id
        return json.dumps(items), True
    return raw_reply, False
