"""
harvest.spoken_facts -- shortcuts and modifier gestures that a presenter SAYS, parsed out of a transcript.

Narrators rarely read a shortcut table; they say "open the line editor with command plus enter", "hold shift while dragging to keep the proportions", "press control or command if you're on a Mac".
`rag.procedures.extract_steps` reads written chords ('Ctrl+S'); this reads the SPOKEN form (modifier words joined by 'plus'):

    chords(text)    [{chord, action, sentence}]   a modifier (command / control / option / alt / shift / windows) 'plus' a key, and what it does (the clause before 'with / using / press', or the one
                                                  after 'to / will / lets you / adds'), only when the action has >= 2 words
    gestures(text)  [{modifier, gesture, effect, sentence}]  'hold shift while dragging ...' : a modifier that changes how a drag / resize / draw behaves

They are LEADS: speech recognition errs, so each fact becomes a vote (one per video) and is written with the 'transcript' trust level, below anything seen on screen and far below anything verified.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_MOD = r"(?:command|cmd|control|ctrl|option|alt|shift|windows key|windows|win)"
_KEY = r"(?:enter|return|escape|esc|tab|space(?:bar)?|delete|backspace|home|end|page up|page down|up|down|left|right|plus|minus|equals|[a-z]|[0-9]|f(?:1[0-2]|[1-9]))"
CHORD_RX = re.compile(rf"\b({_MOD}(?:\s*(?:plus|\+)\s*{_MOD})*)\s*(?:plus|\+)\s*({_KEY})\b", re.I)
# What people actually say: 'Ctrl C', 'control A shortcut', 'command C or control and C' -- no 'plus'. Accepted only for a single key, and (to keep 'you control a lot of things' out) when the
# modifier is Ctrl / Cmd, or the key was spoken as a capital letter ('control M').
BARE_RX = re.compile(r"\b(command|cmd|control|ctrl)\s+(?:and\s+)?([A-Za-z0-9])\b", re.I)
_BAD_ACTION_START = re.compile(r"^(?:from|in|on|at|of|the|a|an|that|this|it|is|was|are|then|so|you|i)\b", re.I)
GESTURE_RX = re.compile(r"\b(?:hold(?:ing)?|press(?:ing)?|keep)\s+(?:down\s+)?(?:the\s+)?(shift|alt|option|control|ctrl|command|cmd)(?:\s+key)?\s+(?:while|as you|when you)\s+(\w+ing|\w+)\b(.*)", re.I)
_MOD_NORM = {"command": "cmd", "cmd": "cmd", "control": "ctrl", "ctrl": "ctrl", "option": "option", "alt": "alt", "shift": "shift", "windows key": "win", "windows": "win", "win": "win"}
_KEY_NORM = {"return": "enter", "escape": "esc", "spacebar": "space", "plus": "+", "minus": "-", "equals": "="}
_LEAD = re.compile(r"^(?:and|but|so|now|then|just|you can|you could|you may|you will|you'll|we can|we're going to|if you want to|you want to|to|also|simply)\s+", re.I)
_TAIL_LINK = re.compile(r"\b(?:with|using|by pressing|by using|press(?:ing)?|use|hit)\s*$", re.I)


def normalise(mods: str, key: str) -> str:
    parts = [_MOD_NORM.get(m.strip().lower(), m.strip().lower()) for m in re.split(r"\s*(?:plus|\+)\s*", mods) if m.strip()]
    k = key.strip().lower()
    return "+".join(parts + [_KEY_NORM.get(k.replace(" ", ""), k.replace(" ", ""))])


def _clause(text: str, start: int, end: int) -> str:
    """The words that say what the chord does."""
    before = re.split(r"[.,;!?]| and | but ", text[:start])[-1].strip()
    after = re.split(r"[.,;!?]| and | but ", text[end:])[0].strip()
    after = re.sub(r"^(?:(?:key\s+)?(?:shortcut|shortcuts|keys?|combination|command|option)\b\s*)+", "", after, flags=re.I)              # 'the control A shortcut to select all ...'
    after = re.split(r"\s+(?:works?|will work|is available)\b", after, maxsplit=1, flags=re.I)[0]
    m = re.match(r"^(?:to|will|would|lets you|let you|allows you to|helps you|can|and it)\s+(.*)", after, re.I)
    if m and len(m.group(1).split()) >= 2:
        return " ".join(m.group(1).split()[:8])
    if m and re.match(r"^to\s+[a-z]{3,}$", after, re.I) and not _TAIL_LINK.search(before):         # 'Ctrl Z to undo': one verb after 'to' is a clear action
        return m.group(1)
    if _TAIL_LINK.search(before):
        b = _LEAD.sub("", _TAIL_LINK.sub("", before).strip()).strip()
        b = re.sub(r"^(?:you want to|want to|need to|if you)\s+", "", b, flags=re.I)
        if len(b.split()) >= 2:
            return " ".join(b.split()[-8:])
    if len(after.split()) >= 2 and not after.lower().startswith(("if ", "when ", "or ")):
        return " ".join(after.split()[:8])
    return ""


_FILLER = {"or", "you", "can", "could", "may", "might", "also", "just", "simply", "now", "then", "and", "so", "will", "would", "your", "the", "to", "use", "using", "press", "pressing", "hit", "key", "keys"}


def _content_words(action: str) -> List[str]:
    """What is left of an action when the filler words are removed: 'Or you can' has nothing left, so it names no action."""
    return [w for w in re.findall(r"[A-Za-z]{3,}", action or "") if w.lower() not in _FILLER]


def _spans(text: str):
    """(start, end, modifiers, key) of every spoken chord, with-'plus' and bare forms, no overlaps."""
    spans = [(m.start(), m.end(), m.group(1), m.group(2)) for m in CHORD_RX.finditer(text or "")]
    for m in BARE_RX.finditer(text or ""):
        mod, key = m.group(1), m.group(2)
        if mod.lower() not in ("ctrl", "cmd") and not key.isupper() and not key.isdigit():
            continue                                                          # lowercase 'control a' is almost always the verb
        if key.lower() in ("a", "i") and not key.isupper():
            continue
        if any(s <= m.start() < e for s, e, _, _ in spans):
            continue
        spans.append((m.start(), m.end(), mod, key))
    return sorted(spans)


def chords(text: str) -> List[Dict[str, Any]]:
    out = []
    for st, en, mods, key in _spans(text):
        act = re.sub(r"\s+(?:it|that|this|them|those|these)$", "", _clause(text, st, en), flags=re.I)                # 'undo that' names the action 'undo'
        if (len(act.split()) < 2 and not re.match(r"^[a-z]{3,}$", act or "")) or _BAD_ACTION_START.match(act) or not _content_words(act):
            continue
        out.append({"chord": normalise(mods, key), "action": act, "sentence": text.strip()[:200]})
    return out


def gestures(text: str) -> List[Dict[str, Any]]:
    out = []
    for m in GESTURE_RX.finditer(text or ""):
        eff = re.sub(r"^[\s,.]*(?:you|we|it|and|to|will|can)?\s*", "", m.group(3).strip(" ."))
        if not eff:                                                          # 'to create a perfectly even shape, just hold shift while dragging': the effect came first
            mm = re.search(r"(?:want to|need to|if you|in order to|\bto)\s+([^,.;]+?)\s*,?\s*(?:just|simply)?\s*$", text[:m.start()], re.I)
            eff = re.sub(r"^(?:want to|need to)\s+", "", mm.group(1)) if mm else ""
        out.append({"modifier": _MOD_NORM.get(m.group(1).lower(), m.group(1).lower()), "gesture": m.group(2).lower(), "effect": " ".join(eff.split()[:12]), "sentence": text.strip()[:200]})
    return out
