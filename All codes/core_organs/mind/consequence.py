"""
consequence -- before a control is pressed or a plan is carried out: what will it do, can it be undone, and what is the safer way?

    classify_label("Place order")                       -> {'risk': 'money', 'severity': 3, 'gate': 'confirm', 'consequence': ..., 'safer': ...}
    assess_step("click", "Delete account", goal="...")  -> the same plus the question to put to the person
    critique_goal("delete all my old emails")           -> a heads-up for a PLAN the person is about to give (scope words raise the severity)

Rules are about the words a control carries, not about an app. 'Cancel' on its own is the harmless way out of a dialog; 'Cancel subscription' is not.
gate: 'allow' (nothing to say), 'note' (do it, mention it), 'confirm' (ask first; the answer must come from the person), 'block' (never from a script: card numbers, passwords typed into a field)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

# (class, base severity, regex over the lower-cased label, what it does, what to do instead). Order = tie-break when two classes have the same severity.
_RULES: List[Dict[str, Any]] = [
    {"risk": "money", "sev": 3, "re": r"\b(pay(?:\s+now)?|buy(?:\s+now)?|purchase|check\s*out|place\s+(?:your\s+|my\s+|the\s+)?order|order\s+now|complete\s+(?:order|purchase)|subscribe|upgrade|donate|send\s+money|transfer|withdraw|book\s+now|confirm\s+(?:booking|order|payment)|add\s+(?:a\s+)?card|pay\s+with)\b",
     "does": "charges or commits money; a refund is up to the seller and may not be possible", "safer": "check the item, the amount and the payment method first, or use the site's test / sandbox mode"},
    {"risk": "publish", "sev": 2, "re": r"\b(send|submit|publish|post|tweet|share|invite|reply\s+all|forward|apply(?:\s+now|\s+for\b|\s+to\s+(?:this|the)\s+(?:job|role|position)|\s*$)|announce|go\s+live|broadcast|email\s+all|send\s+to\s+all|request\s+to\s+join)\b",
     "does": "other people will see it, and most apps cannot take it back once it is out", "safer": "save it as a draft or preview it, then re-read the words and the recipients before sending"},
    {"risk": "delete", "sev": 2, "re": r"\b(delete|remove|erase|wipe|trash|discard|purge|uninstall|format\s+(?:drive|disk|partition|usb|sd\s*card|volume|c:)|factory\s+reset|reset\s+(?:password|settings|progress|all|everything|device|data|account|app|phone|windows|database|game)|empty\s+(?:the\s+)?(?:trash|bin|recycle(?:\s+bin)?)|clear\s+(?:all|history|data|cache|cookies|browsing))\b",
     "does": "removes data, and many apps have no undo for it", "safer": "export or copy it first, or move it to the trash instead of deleting it for good"},
    {"risk": "account", "sev": 2, "re": r"\b(sign\s*out|log\s*out|logout|log\s*off|disconnect|deactivate|unlink|revoke|unsubscribe|cancel\s+(?:my\s+|your\s+|the\s+)?(?:subscription|membership|plan|order|booking|account|trial)|close\s+(?:my\s+|your\s+)?account)\b",
     "does": "ends the session or the plan; unsaved work or access can be lost", "safer": "save what is open, and check what the plan includes before ending it"},
    {"risk": "consent", "sev": 2, "re": r"\b(i\s+agree|accept(?!\s+(?:\w+\s+)?(?:payments?|subscriptions?|donations?|cards?|orders?))(?:\s+(?:all|cookies|optional\s+cookies|terms|the\s+terms|and\s+continue|&\s*close))?|agree(?:\s+(?:and|&)\s+(?:continue|close|proceed))?|allow(?:\s+all)?|grant|authori[sz]e|sign\s*in\s+with\s+(?:google|facebook|apple|microsoft|github|linkedin|twitter|x|amazon)|connect\s+(?:your\s+|my\s+)?account|continue\s+with\s+(?:google|facebook|apple|microsoft|github))\b",
     "does": "agrees to terms or hands the app access to your data or account", "safer": "read what is being agreed to or shared; the person decides, not the script"},
    {"risk": "install", "sev": 2, "re": r"\b(install|download|enable\s+macros?|run\s+as\s+administrator|update\s+now|enable\s+content|allow\s+editing)\b",
     "does": "puts new files or code on the computer", "safer": "check where it comes from and what it is before it runs"},
    {"risk": "system", "sev": 1, "re": r"\b(shut\s*down|shutdown|restart|reboot|power\s+off|sleep|quit|exit|force\s+quit|end\s+task|kill|terminate|close\s+(?:all|window|tab|document|file))\b",
     "does": "closes running work; changes that are not saved can be lost", "safer": "save first, then close"},
    {"risk": "overwrite", "sev": 1, "re": r"\b(save|replace(?:\s+all)?|overwrite|apply\s+to\s+all|merge|move|rename|export)\b",
     "does": "changes an existing file or record", "safer": "keep a copy under another name"},
]
for _r in _RULES:
    _r["rx"] = re.compile(_r["re"], re.I)

# the same words in a sentence the person gives: these make the effect wider or the loss final
_SCOPE_UP = re.compile(r"\b(all|every|everything|entire|whole|permanently|forever|for\s+good|irreversibl\w*|bulk|mass|everyone|all\s+of\s+them)\b", re.I)
_SCOPE_OBJ = re.compile(r"\b(account|partition|drive|disk|database|repo|repository|production|server|backup|backups|inbox|everything|workspace|organi[sz]ation|team|company|customers?|clients?)\b", re.I)
_SAFE_CONTEXT = re.compile(r"\b(draft|preview|test|dry[\s-]*run|sandbox|copy|backup\s+first|undo|trash)\b", re.I)

# a typed value that must never be sent by a script
_SECRET_FIELD = re.compile(r"\b(password|passcode|pin|cvv|cvc|card\s*number|credit\s*card|debit\s*card|security\s*code|ssn|social\s*security|aadhaar|passport|iban|routing\s*number|account\s*number|otp|one[\s-]*time|secret|api[\s-]*key|token)\b", re.I)
_CARD_LIKE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

DANGEROUS_CHORDS = {"alt+f4", "ctrl+alt+delete", "ctrl+shift+escape", "win+l", "ctrl+w", "ctrl+shift+delete", "shift+delete", "ctrl+q"}

_SEV_NAME = {0: "none", 1: "low", 2: "medium", 3: "high"}


_INFO_START = re.compile(r"^(how|why|what|when|where|who|which|can|could|do|does|did|is|are|should|will|would|expand|collapse|show|hide|toggle|learn|read|about|see|view|explore|discover|compare|find|login\s+to|log\s+in\s+to)\b", re.I)
_NOT_THE_COMMAND = re.compile(r"\b(check\s+out\s+(?:our|the|this|these|more|what)|(?:bring|send)\s+(?:to\s+)?(?:front|back|forward|backward)|(?:bring|send)\s+forward)\b", re.I)
_MAX_COMMAND_WORDS = 7
_LEAD_IN = {"i", "please", "yes", "ok", "okay", "now", "just", "then", "and", "&", "confirm", "go", "continue", "yes,"}          # words that may stand before the verb of a command ("I agree", "Please confirm")


def _hits(text: str, strict: bool = False) -> List[Dict[str, Any]]:
    """strict=True is for the label of ONE control: a command starts with its verb (at most one word before it) and is short; a question, a headline or a marketing line that merely contains the word is not a command."""
    t = (text or "").lower()
    if strict:
        words = re.findall(r"[\w'’&-]+", t)
        if not words or len(words) > _MAX_COMMAND_WORDS or _INFO_START.match(t.strip()) or _NOT_THE_COMMAND.search(t) or "/" in t:   # a "/" is a path or an HTTP route in documentation, not a button
            return []
    out = []
    for r in _RULES:
        m = r["rx"].search(t)
        if m:
            if strict:
                before = re.findall(r"[\w'’&-]+", t[:m.start()])
                if len(before) > 1 or (len(before) == 1 and before[0] not in _LEAD_IN):
                    continue
            out.append({"risk": r["risk"], "sev": r["sev"], "word": m.group(0), "does": r["does"], "safer": r["safer"]})
    return out


def _bare_cancel(label: str) -> bool:
    """'Cancel', 'Close', 'Back', 'No thanks': the way OUT of a dialog. Never a risk by itself."""
    return bool(re.fullmatch(r"\s*(cancel|close|back|dismiss|not\s+now|no(?:\s+thanks)?|skip|later|maybe\s+later|go\s+back)\s*[.!]?\s*", (label or ""), re.I))


def classify_label(label: str, role: str = "", context: str = "") -> Dict[str, Any]:
    """What pressing a control with this label does. `context` = a goal or the dialog's text (widens the effect: 'delete ALL')."""
    lab = (label or "").strip()
    none = {"risk": "none", "severity": 0, "gate": "allow", "consequence": "", "safer": "", "word": ""}
    if not lab or _bare_cancel(lab):
        return none
    if (role or "").lower() in ("link", "hyperlink", "menuitem", "tab", "tabitem") and len(lab) > 60:
        return none                                                    # a long headline link ('Delete the 5 worst habits ...') is an article, not a command
    hits = _hits(lab, strict=True)
    if not hits:
        return none
    best = max(hits, key=lambda h: h["sev"])
    sev = best["sev"]
    ctx = f"{lab} {context}"
    if best["risk"] in ("delete", "account", "publish") and (_SCOPE_UP.search(ctx) or _SCOPE_OBJ.search(ctx)):
        sev = min(3, sev + 1)
    if _SAFE_CONTEXT.search(ctx) and sev == 2 and best["risk"] in ("publish", "delete"):
        sev -= 1                                                       # 'Save draft', 'Send test email', 'Move to trash': the safe form of the same verb
    if sev <= 0:
        return none
    gate = "confirm" if sev >= 2 else "note"
    return {"risk": best["risk"], "severity": sev, "level": _SEV_NAME[sev], "gate": gate, "consequence": best["does"], "safer": best["safer"], "word": best["word"],
            "also": sorted({h["risk"] for h in hits} - {best["risk"]})}


def assess_step(verb: str, label: str = "", goal: str = "", typed_text: str = "", field: str = "", chord: str = "", role: str = "") -> Dict[str, Any]:
    """One step of a run: the verb, the control it is aimed at, and what is typed. Returns the assessment with 'gate' and, when the person has to be asked, 'question'."""
    verb = (verb or "").lower()
    if verb in ("key", "hotkey", "shortcut") and chord:
        if re.sub(r"\s+", "", chord.lower()) in DANGEROUS_CHORDS:
            return _with_question({"risk": "system", "severity": 2, "level": "medium", "gate": "confirm", "consequence": "closes the window or the session; unsaved work can be lost", "safer": "save first", "word": chord}, verb, chord)
    if verb == "type":
        if _SECRET_FIELD.search(f"{field} {label}") or _CARD_LIKE.search(typed_text or ""):
            return _with_question({"risk": "secret", "severity": 3, "level": "high", "gate": "block", "consequence": "a password, card or identity number would be typed by a script and could be stored or leaked",
                                   "safer": "type it yourself", "word": field or label}, verb, label or field)
        return {"risk": "none", "severity": 0, "gate": "allow", "consequence": "", "safer": "", "word": ""}
    a = classify_label(label, role=role, context=goal)
    return _with_question(a, verb, label)


def _with_question(a: Dict[str, Any], verb: str, label: str) -> Dict[str, Any]:
    if a.get("gate") in ("confirm", "block"):
        what = f"'{label}'" if label else "this step"
        if a["gate"] == "block":
            a["question"] = f"I will not do {what} for you: {a['consequence']}. Please do it yourself."
        else:
            a["question"] = f"About to {verb} {what}: it {a['consequence']}. Safer: {a['safer']}. Go ahead?"
    return a


def critique_goal(goal: str) -> Dict[str, Any]:
    """A plan in the person's own words. Returns the risks it contains and, if any is medium or high, the heads-up (what would happen, what to do instead)."""
    g = goal or ""
    hits = _hits(g)
    risks = []
    for h in sorted(hits, key=lambda x: -x["sev"]):
        sev = h["sev"]
        if h["risk"] in ("delete", "account", "publish") and (_SCOPE_UP.search(g) or _SCOPE_OBJ.search(g)):
            sev = min(3, sev + 1)
        if _SAFE_CONTEXT.search(g) and sev == 2 and h["risk"] in ("publish", "delete"):
            sev -= 1
        risks.append({"risk": h["risk"], "severity": sev, "word": h["word"], "consequence": h["does"], "safer": h["safer"]})
    worst = max([r["severity"] for r in risks] or [0])
    no_backup = bool(re.search(r"\b(no\s+backup|without\s+(?:a\s+)?backup|don'?t\s+(?:need|want)\s+(?:a\s+)?backup)\b", g, re.I))
    if no_backup and worst >= 2:
        worst = 3
    out: Dict[str, Any] = {"risks": risks, "severity": worst, "level": _SEV_NAME[worst], "gate": "confirm" if worst >= 2 else ("note" if worst == 1 else "allow")}
    if worst >= 2:
        top = max(risks, key=lambda r: r["severity"])
        out["heads_up"] = (f"Before I do this: '{top['word']}' {top['consequence']}." + (" You said no backup, so there would be no way back." if no_backup else "")
                           + f" Safer: {top['safer']}. Shall I do it that way, or exactly as asked?")
    return out
