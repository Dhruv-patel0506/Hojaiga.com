"""
task_intake.py -- Phase A of the task lifecycle: Intake & Comprehension (checkpoints A1, A2, A3-feasibility).

    intake = analyse(text)            # pure, offline, bounded: no LLM, no desktop access
    intake.clean_text                 # A1  the text with credentials / tokens removed
    intake.tickets                    # A1  independent task tickets (a list of tasks becomes one ticket each)
    intake.domain                     # A2  web | desktop | mixed | system | unknown   (per ticket in .ticket_domains)
    intake.impossible                 # A3  reasons no effector of this system can deliver the task (declared at intake)
    intake.question / .assumptions    # A1  ONE clarifying question when the text names nothing to act on, else the
                                      #     safest interpretation, recorded
    intake.checkpoints                # [{"id","name","status","evidence"}] - the honest per-checkpoint record

Nothing here names an application: apps are recognised against the machine's own installed-app catalog
(universal_scan.start_apps) and the words of the text itself, so a new app needs no code change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------------------------------------------------------------------------ A1: secrets

_SECRET_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("api-key", re.compile(r"\b(?:sk|pk|rk|gsk|ghp|gho|xox[abp]|AKIA|AIza)[-_A-Za-z0-9]{16,}\b")),
    ("bearer-token", re.compile(r"\bbearer\s+[A-Za-z0-9._\-]{16,}", re.I)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("password", re.compile(r"(?i)(?:\b(?:my|the|our)\s+)?\b(pass(?:word|wd|code)?|pwd|secret|token|api[ _-]?key)\b\s*(?:is|=|:)\s*(\S+?)(?:[,;.]\s*|\s+|$)")),
    ("card-number", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("url-secret", re.compile(r"(?i)([?&](?:token|key|api_?key|access_token|auth|sig|signature|password)=)[^&\s]+")),
]


def sanitize(text: str) -> Tuple[str, List[str]]:
    """(clean_text, findings). Secrets are replaced by a marker so they never reach a plan, a log or a recipe; the
    task proceeds in its sanitized form (a secret that must be TYPED is a human-in-the-loop item, not plan text)."""
    found: List[str] = []
    out = text or ""

    def _luhn(num: str) -> bool:
        d = [int(c) for c in re.sub(r"\D", "", num)]
        if not 13 <= len(d) <= 19:
            return False
        s, alt = 0, False
        for x in reversed(d):
            if alt:
                x = x * 2 - 9 if x * 2 > 9 else x * 2
            s += x
            alt = not alt
        return s % 10 == 0

    for kind, pat in _SECRET_PATTERNS:
        if kind == "card-number":
            def _card(m):
                if _luhn(m.group(0)):
                    found.append(kind)
                    return "[REDACTED:card-number]"
                return m.group(0)
            out = pat.sub(_card, out)
        elif kind == "password":
            def _pw(m):
                found.append(kind)
                return ""             # the whole statement goes: it is neither plan text nor a goal
            out = pat.sub(_pw, out)
        elif kind == "url-secret":
            def _u(m):
                found.append(kind)
                return m.group(1) + "[REDACTED]"
            out = pat.sub(_u, out)
        else:
            def _g(m, k=kind):
                found.append(k)
                return f"[REDACTED:{k}]"
            out = pat.sub(_g, out)
    return out, found


# ------------------------------------------------------------------------------------------------ A1: tickets

_LIST_ITEM_RE = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*•])\s+(.*\S)\s*$")


def split_tickets(text: str) -> List[str]:
    """One ticket per independent task. A numbered / bulleted list, or blocks separated by a blank line, are separate
    tasks; a single line (even with ';' or 'then') is ONE task whose steps run in order."""
    lines = [l for l in (text or "").splitlines()]
    items = [m.group(1) for l in lines if (m := _LIST_ITEM_RE.match(l))]
    nonblank = [l for l in lines if l.strip()]
    if len(items) >= 2 and len(items) >= len(nonblank) - 1:          # a list (optionally with a one-line heading)
        return [i.strip() for i in items]
    blocks = [b.strip() for b in re.split(r"\n\s*\n", (text or "").strip()) if b.strip()]
    if len(blocks) >= 2:
        return [re.sub(r"\s*\n\s*", " ", b) for b in blocks]
    return [(text or "").strip()] if (text or "").strip() else []


# ------------------------------------------------------------------------------------------------ A2: routing

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b[a-z0-9\-]+\.(?:com|org|net|io|ai|edu|gov|co|app|dev)\b(?:/\S*)?")
_WEB_WORDS = re.compile(r"(?i)\b(website|web ?site|web ?page|browser|google|search (?:for|the web)|url|link|online|webmail|"
                        r"sign in to|log ?in to|download from)\b")
_BROWSER_NAMES = ("chrome", "edge", "firefox", "brave", "opera", "safari", "browser")
_RESEARCH_RE = re.compile(r"(?i)\b(find|search(?:\s+for)?|look\s*up|research|scrape|collect|gather|get me|list|compare)\b")
_SYSTEM_WORDS = re.compile(r"(?i)\b(rename|move|copy|delete|zip|unzip|extract|compress)\b.*(?:\b(?:file|folder|directory)\b|\b[\w\-]+\.[a-z0-9]{2,5}\b)|"
                           r"\b(list|find) (?:the )?files\b|\bdisk (?:space|usage)\b")


def installed_app_names() -> List[str]:
    """Display names from the machine's own Start-menu catalog (cached by universal_scan); [] when unavailable."""
    try:
        from core_organs import universal_scan as us
        return [n for n, _a in us.start_apps() if n]
    except Exception:
        return []


_APP_CUE_RE = re.compile(r"(?:\b(?:open|opens|launch|start|run|use|using|in|into|on|with|via|inside|from)|\bswitch to|\bgo to|\bthen)\s+(?:the\s+|my\s+|a\s+|an\s+)?$")


def _app_cue(low: str, pos: int) -> bool:
    before = low[max(0, pos - 24):pos]
    return pos <= 3 or bool(_APP_CUE_RE.search(before)) or bool(re.search(r"[.;:\n]\s*$", before))


def detect_apps(text: str, catalog: Optional[List[str]] = None) -> List[Tuple[str, int]]:
    """[(app, position)] for the installed apps the text names, in order of appearance. An app matches when ALL of the
    words of its display name appear in the text (single-word names need the whole word), so a catalog entry like
    'Microsoft Edge' matches 'open edge' through its distinctive word. Generic words never decide a match."""
    catalog = catalog if catalog is not None else installed_app_names()
    low = (text or "").lower()
    generic = {"microsoft", "windows", "app", "the", "for", "of", "and", "free", "edition", "desktop", "pro", "classic",
               "new", "preview", "beta", "store", "office", "tool", "tools", "viewer", "manager", "studio"}
    hits: Dict[str, int] = {}
    for name in catalog:
        words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in generic and len(w) > 2]
        if not words:
            continue
        pos = []
        for w in words:
            m = re.search(r"\b" + re.escape(w) + r"\b", low)
            if not m:
                pos = []
                break
            pos.append(m.start())
        if pos:
            first = min(pos)
            # A single common word that merely APPEARS ('click' for the app 'Click to Do', 'weather' in 'search for weather')
            # is not a mention of the app. A one-word name counts when it is introduced the way apps are ('open X', 'in X',
            # 'using X', 'switch to X'), or opens the text; a multi-word name is distinctive enough on its own.
            if len(words) == 1 and not _app_cue(low, first):
                continue
            key = name.lower()
            hits.setdefault(key, first)
    # several catalog entries can match the same words ('Notepad' / 'Notepad++', 'Paint' / 'Paint 3D'): the mention
    # means the most direct one - keep, per position, the entry with the shortest name
    best: Dict[int, str] = {}
    for key, p in sorted(hits.items(), key=lambda kv: (kv[1], len(kv[0]))):
        best.setdefault(p, key)
    return sorted(((k, p) for p, k in best.items()), key=lambda kv: kv[1])


def classify_domain(text: str, apps: Optional[List[Tuple[str, int]]] = None) -> Tuple[str, str]:
    """(domain, evidence). web: a URL/site is named or a browser is the target; desktop: an installed app is named;
    mixed: both; system: a pure file/system operation; unknown: nothing to act on."""
    t = text or ""
    has_url = bool(_URL_RE.search(t))
    web_word = bool(_WEB_WORDS.search(t))
    apps = apps if apps is not None else detect_apps(t)
    browser = any(any(b in a for b in _BROWSER_NAMES) for a, _p in apps)
    desktop_apps = [a for a, _p in apps if not any(b in a for b in _BROWSER_NAMES)]
    web = has_url or web_word or browser
    if web and desktop_apps:
        return "mixed", f"web cues (url={has_url}, word={web_word}, browser={browser}) + desktop apps {desktop_apps[:3]}"
    if web:
        return "web", f"url={has_url} web-word={web_word} browser={browser}"
    if desktop_apps:
        return "desktop", f"installed apps named: {desktop_apps[:3]}"
    if _SYSTEM_WORDS.search(t):
        return "system", "file/system operation, no app named"
    if _RESEARCH_RE.search(t):
        return "web", "research verbs (find/search/look up/collect...) with no app named imply the browser"
    return "unknown", "no URL, installed app or file operation recognised"


# ------------------------------------------------------------------------------------------------ A3: feasibility

# Capabilities this system does not have an effector for. Declared at intake, honestly, instead of 40 failed clicks.
_IMPOSSIBLE: List[Tuple[str, "re.Pattern[str]"]] = [
    ("physical-world action (no effector touches hardware outside the screen)",
     re.compile(r"(?i)\b(plug in|unplug|turn (?:on|off) the (?:printer|monitor|light|tv|router)|press the (?:physical|power) button|"
                r"insert (?:a )?(?:disk|usb|card)|pick up|carry|hand me|wave|point at)\b")),
    ("hand / body gesture or voice input (the input layer delivers window messages and UIA patterns only)",
     re.compile(r"(?i)\b(hand gestures?|swipe in the air|say (?:out loud|aloud)|speak into|dictate by voice|nod|blink)\b")),
    ("solving or bypassing a CAPTCHA / bot check (never automated)",
     re.compile(r"(?i)\b(solve|bypass|get past|defeat|crack)\b.{0,30}\b(captcha|recaptcha|bot[- ]?check|are you human)\b")),
    ("moving money / trading / buying with a stored payment method (a human does these)",
     re.compile(r"(?i)\b(transfer|wire|send|withdraw|deposit)\b.{0,25}(?:\$\s?\d|\b\d+\s?(?:dollars|usd|eur|btc|eth)\b|\b(?:money|funds)\b)|"
                r"\b(buy|sell|trade)\b.{0,25}\b(stocks?|shares?|crypto(?:currency)?|bitcoin|ethereum)\b")),
    ("entering passwords / card numbers into a form on the user's behalf (never automated)",
     re.compile(r"(?i)\b(type|enter|fill in|input)\b.{0,30}\b(my )?(password|passcode|card number|cvv|ssn|social security)\b")),
]


def feasibility(text: str) -> List[str]:
    return [why for why, pat in _IMPOSSIBLE if pat.search(text or "")]


# ------------------------------------------------------------------------------------------------ A1: ambiguity

_ACTION_VERB_RE = re.compile(r"(?i)\b(open|launch|start|run|type|write|enter|save|press|click|select|draw|create|make|add|"
                             r"set|search|go to|navigate|download|upload|send|close|calculate|compute|rename|move|copy|"
                             r"export|import|print|play|pause|install|update|turn|change|find|read|scan|pay|buy|sell|transfer|checkout|order|post|reply)\b")
_VAGUE_RE = re.compile(r"(?i)^\s*(?:please\s+)?(?:clean|fix|sort|tidy|organi[sz]e|handle|deal with|do|take care of|look at|"
                       r"check|improve|update)\s+(?:this|that|it|things?|stuff|everything|up)\b")


def ambiguity(ticket: str, domain: str, apps: List[Tuple[str, int]]) -> Tuple[Optional[str], List[str]]:
    """(question, assumptions). A question only when the ticket names nothing at all to act on; any other
    vagueness is resolved to the safest reading and the assumption is recorded."""
    assumptions: List[str] = []
    t = ticket or ""
    if _VAGUE_RE.search(t) and not apps and domain in ("unknown",):
        return ("Which application or file should I work on? The task ('%s') does not name one." % t[:60], assumptions)
    if domain == "unknown" and _ACTION_VERB_RE.search(t) and not apps:
        return ("Which application should I use for '%s'? No installed app, site or file is named." % t[:60], assumptions)
    if domain == "unknown" and not _ACTION_VERB_RE.search(t):
        return ("I could not find an action or an application in '%s'. What should I do, and in which app?" % t[:60], assumptions)
    if domain == "unknown":
        assumptions.append("no application named: assumed the foreground-independent default (a new window of the app the verbs imply)")
    if len(apps) > 1 and domain == "desktop":
        assumptions.append(f"several apps named {[a for a, _p in apps][:4]}: handled in the order they are mentioned")
    return None, assumptions


# ------------------------------------------------------------------------------------------------ the analysis

@dataclass
class Intake:
    original: str
    clean_text: str
    secrets_found: List[str] = field(default_factory=list)
    tickets: List[str] = field(default_factory=list)
    ticket_domains: List[str] = field(default_factory=list)
    domain: str = "unknown"
    apps: List[Tuple[str, int]] = field(default_factory=list)
    impossible: List[str] = field(default_factory=list)
    question: Optional[str] = None
    assumptions: List[str] = field(default_factory=list)
    checkpoints: List[Dict[str, str]] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return bool(self.impossible)

    def mark(self, cid: str, name: str, status: str, evidence: str) -> None:
        self.checkpoints.append({"id": cid, "name": name, "status": status, "evidence": evidence})


def analyse(text: str, catalog: Optional[List[str]] = None) -> Intake:
    clean, found = sanitize(text or "")
    it = Intake(original=text or "", clean_text=clean, secrets_found=found)
    it.mark("A1.sanitize", "strip credentials / tokens", "PASS",
            f"{len(found)} secret(s) redacted ({', '.join(sorted(set(found)))})" if found else "no secrets found")
    it.tickets = split_tickets(clean)
    it.mark("A1.split", "independent task tickets", "PASS" if it.tickets else "BLOCKED",
            f"{len(it.tickets)} ticket(s)" if it.tickets else "empty task text")
    cat = catalog if catalog is not None else installed_app_names()
    it.apps = detect_apps(clean, cat)
    domains = []
    for t in it.tickets:
        d, _ev = classify_domain(t, detect_apps(t, cat))
        domains.append(d)
    it.ticket_domains = domains
    uniq = set(domains)
    it.domain = domains[0] if len(uniq) == 1 else ("mixed" if uniq else "unknown")
    it.mark("A2.route", "execution domain", "PASS" if it.domain != "unknown" else "BLOCKED",
            f"domain={it.domain}; per ticket {domains}; apps={[a for a, _p in it.apps][:4]}")
    it.impossible = feasibility(clean)
    it.mark("A3.feasible", "declare impossible at intake", "BLOCKED" if it.impossible else "PASS",
            "; ".join(it.impossible) if it.impossible else "no capability the system lacks was required")
    if it.tickets and not it.impossible:
        q, a = ambiguity(it.tickets[0], domains[0] if domains else "unknown", detect_apps(it.tickets[0], cat))
        it.question, it.assumptions = q, a
    it.mark("A1.clarify", "ambiguity: one question or a recorded assumption", "BLOCKED" if it.question else "PASS",
            it.question or (("assumptions: " + "; ".join(it.assumptions)) if it.assumptions else "task is specific enough"))
    return it
