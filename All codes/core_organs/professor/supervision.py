"""
professor.supervision -- HYBRID TIERED SUPERVISION: autonomous inside the sandbox, a human yes for everything that reaches outside it.

The person's standing decision (data/professor/settings.json -> "supervision"):
  AUTONOMOUS    an instance the Professor launched itself, working on a throw-away document / canvas / sandboxed state (a blank presentation, primitives in Paint, harmless view toggles):
                probing and running guide procedures there needs nobody.
  APPROVAL      an explicit pause and a yes from the person (the step is reported 'needs_human' when nobody is there to answer):
                  - writing / modifying files outside the sandbox folder           - closing a document that is not the run's own
                  - submitting a form, sending, posting, sharing, replying            - sign-in, payment, account / subscription changes
                  - OS-level / terminal commands                                     - in a messaging application ANY submission (Enter, a Send button, a dispatch)
The executor asks `check(step)` before EVERY step; the existing guards (safety classes, the effector's ownership rule, the dialog sandbox) still apply on top - this gate can only add a pause,
never remove one. Every decision is kept (decisions) so a report can show what was asked and why.
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

SUBMIT_RX = re.compile(r"(?i)\b(send|post|submit|publish|share|reply|forward|invite|tweet|comment|upload|dispatch|confirm (?:order|purchase|payment)|place order|pay|purchase|buy|checkout|"
                       r"sign ?in|log ?in|sign ?out|log ?out|subscribe|unsubscribe|delete account|change password)\b")
OS_RX = re.compile(r"(?i)\b(command prompt|powershell|terminal|cmd\.exe|regedit|registry|run dialog|shutdown|restart (?:the )?(?:pc|computer)|format (?:the )?drive)\b")
CLOSE_RX = re.compile(r"(?i)^(close|exit|quit|close window|close document|close all)\b")
SAVE_RX = re.compile(r"(?i)\b(save|save as|export|save a copy|download)\b")


class Supervisor:
    def __init__(self, mode: str = "hybrid", owned: bool = True, sandboxed: bool = False, navigate: bool = False, messaging: bool = False, sandbox_dir: str = "",
                 ask: Optional[Callable[[Any, str], bool]] = None, log: Callable[[str], None] = lambda s: None):
        self.mode, self.owned, self.sandboxed, self.navigate, self.messaging = mode, owned, sandboxed, navigate, messaging
        self.sandbox_dir = sandbox_dir
        self.ask_fn = ask                      # a person's answer (CLI prompt / overlay button); None = nobody is there -> the step waits ('needs_human')
        self.log = log
        self.decisions: List[Dict[str, Any]] = []

    @staticmethod
    def from_settings(settings: Dict[str, Any], **kw: Any) -> "Supervisor":
        sup = (settings or {}).get("supervision") or {}
        return Supervisor(mode=sup.get("mode", "hybrid"), **kw)

    def check(self, step: Any) -> Tuple[str, str]:
        """('autonomous' | 'approval', why) for one executor Step."""
        words = " ".join(str(x) for x in (getattr(step, "verb", "") or "", getattr(step, "text", "") or "", getattr(step, "goal", "") or "", " ".join(getattr(step, "path", []) or [])))
        label = (getattr(step, "verb", "") or getattr(step, "text", "") or "").strip()
        kind = getattr(step, "kind", "")
        if self.mode == "supervised":
            return "approval", "supervised mode: every step is confirmed"
        if not self.owned:
            return "approval", "the window is not one the Professor launched"
        if (self.messaging or self.navigate) and kind == "key" and (getattr(step, "text", "") or "").lower() in ("enter", "return"):
            return "approval", "Enter in a messaging / account application submits what was typed"
        if (self.messaging or self.navigate) and kind == "text":
            return "approval", "typing into a messaging / account application composes something to send"
        if SUBMIT_RX.search(label) or (kind == "dialog_button" and SUBMIT_RX.search(label)):
            return "approval", f"'{label}' sends / submits / touches an account"
        if OS_RX.search(words):
            return "approval", "an operating-system / terminal command"
        if CLOSE_RX.match(label) and not self.sandboxed:
            return "approval", "closing a document that may not be the run's own"
        if SAVE_RX.search(label) and not self.sandboxed and not self.sandbox_dir:
            return "approval", "writing a file with no sandbox folder to force it into"
        if self.mode == "hybrid" and not (self.owned and (self.sandboxed or self.sandbox_dir)):
            return "approval", "hybrid mode: outside a sandbox every step is confirmed"
        return "autonomous", "owned instance working on throw-away state"

    def allow(self, step: Any) -> Tuple[bool, str]:
        """Check, and ask the person when the step needs a yes. Returns (go ahead, why)."""
        verdict, why = self.check(step)
        ok = verdict == "autonomous"
        asked = None
        if not ok and self.ask_fn is not None:
            try:
                asked = bool(self.ask_fn(step, why))
            except Exception:
                asked = False
            ok = asked
        self.decisions.append({"at": time.strftime("%H:%M:%S"), "step": (getattr(step, "verb", "") or getattr(step, "goal", "") or "")[:80], "verdict": verdict, "why": why, "asked": asked, "go": ok})
        if not ok:
            self.log(f"supervision: '{(getattr(step, 'verb', '') or getattr(step, 'goal', ''))[:50]}' waits for a human yes - {why}")
        return ok, why

    def summary(self) -> Dict[str, Any]:
        return {"mode": self.mode, "decisions": len(self.decisions), "paused": [d for d in self.decisions if not d["go"]][:20],
                "autonomous": sum(1 for d in self.decisions if d["verdict"] == "autonomous")}


def cli_ask(step: Any, why: str) -> bool:
    """A console prompt for an interactive run (a person at the keyboard)."""
    try:
        ans = input(f"\n[supervision] '{(getattr(step, 'verb', '') or getattr(step, 'goal', ''))[:60]}' - {why}. Allow this one step? [y/N] ")
    except Exception:
        return False
    return ans.strip().lower() in ("y", "yes")
