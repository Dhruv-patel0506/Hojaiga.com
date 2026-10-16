"""
safety_guard -- ONE place that decides whether a control may be clicked during exploration or autonomous driving.

Before this module the same question was answered five different ways (atlas.explorer.UNSAFE_RX, hojaiga_sprint_prober.DESTRUCTIVE, desktop_grounding.DESTRUCTIVE_CUES,
organ_47._DESTRUCTIVE_TOKENS, popup_policy.DESTRUCTIVE_COMMIT_KEYWORDS) and none of them covered the whole Checkpoint-0 list (Delete, Format, Reset, Uninstall, Purchase).
New code asks this module; the older lists are left untouched (they are measured and tested) and are a superset-merge candidate for a later change.

Policy (conservative on purpose -- a skipped control costs a little coverage, a clicked one can cost the person their data):
    DESTRUCTIVE  destroys or overwrites data, or ends the session   delete, remove, erase, wipe, format, reset, uninstall, discard, exit, quit, close, shutdown ...
    FINANCIAL    spends money or commits an order                    purchase, buy, pay, checkout, subscribe, place order, upgrade ...
    COMMIT       sends or publishes something that cannot be recalled  submit, send, publish, post, confirm, sign out ...
A decision is always one of: allow / block, with the matching term and category so the caller can log WHY. There is no silent allow: an empty label is blocked
(a control nobody can name is not one to click blind). Only an explicit `allow=` category set, given by a human-approved caller, lifts a block, and it never lifts FINANCIAL.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional

_TERMS = {
    "destructive": (
        "delete", "remove", "erase", "wipe", "purge", "format", "reset", "uninstall", "discard", "clear all", "empty", "factory",
        "exit", "quit", "close", "shutdown", "shut down", "restart", "terminate", "kill", "force quit", "overwrite", "don't save", "do not save",
    ),
    "financial": (
        "purchase", "buy", "pay", "payment", "checkout", "check out", "subscribe", "place order", "order now", "upgrade", "donate", "add to cart",
    ),
    "commit": (
        "submit", "send", "publish", "post", "confirm", "sign out", "log out", "logout", "sign off", "transfer", "withdraw",
    ),
}


def _fold(s: str) -> str:
    """Case, accents and curly quotes folded; access-key ampersands and ellipses dropped ('&Delete...' -> 'delete')."""
    s = unicodedata.normalize("NFKD", s or "").replace("’", "'").replace("‘", "'")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[&…]|\.{2,}", "", s).casefold().strip()


def _rx(terms: Iterable[str]) -> "re.Pattern[str]":
    # \b on both sides: 'format' must not fire on 'information', 'pay' not on 'display', 'post' not on 'postscript'.
    alt = "|".join(sorted((re.escape(t).replace(r"\ ", r"\s+") for t in terms), key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{alt})(?![a-z0-9])")


_RX = {cat: _rx(terms) for cat, terms in _TERMS.items()}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    category: str = ""          # "" when allowed; else destructive | financial | commit | unnamed
    term: str = ""              # the matched word, for the log
    label: str = ""

    def __bool__(self) -> bool:
        return self.allowed

    def why(self) -> str:
        return "" if self.allowed else f"blocked ({self.category}): {self.term!r} in {self.label!r}"


def check(label: Optional[str], *, allow: Iterable[str] = ()) -> Decision:
    """May a control with this visible name be clicked? `allow` lifts destructive/commit categories only; financial is never liftable."""
    raw = label or ""
    low = _fold(raw)
    if not low:
        return Decision(False, "unnamed", "", raw)
    lifted = {c for c in allow if c != "financial"}
    for cat in ("financial", "destructive", "commit"):
        m = _RX[cat].search(low)
        if m and cat not in lifted:
            return Decision(False, cat, m.group(0), raw)
    return Decision(True, "", "", raw)


def is_safe(label: Optional[str], *, allow: Iterable[str] = ()) -> bool:
    return check(label, allow=allow).allowed
