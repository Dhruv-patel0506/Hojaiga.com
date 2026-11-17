"""
professor.knowledge.guide_steps -- from MANUAL PROSE to executable hypotheses, grounded in the LIVE interface.

A guide says: "1. Open the **File** menu. 2. Choose **File > Export > PDF**. 3. Press **Ctrl**+**P**." The Professor needs: which control, in which menu, by which route.
This module does the two honest halves of that translation:

  parse_steps   rules only (no model): numbered / bulleted steps and imperative sentences -> GuideStep(action, target, menu path, typed text, key chord). The words a manual marks
                as interface terms (**bold**, <kbd>, "quoted") are the targets; "File > Export > PDF" is a menu path.
  ground        each GuideStep is matched against the application's OWN catalog (professor.harvest): exact menu path, then exact label, then word overlap; a key chord is accepted only if
                the application itself prints it. A step that matches nothing is reported UNKNOWN with the manual's words ("the manual says 'Cropping Ratio'; no such control is visible") -
                never invented, never forced onto the nearest control.
  plan_from_guide   retrieves the passages for a goal (agentic RAG, cited) and returns the passage whose steps ground best, with its citation and the steps that did not ground.

A manual describes one version in prose, so the result is a HYPOTHESIS: the executor still verifies every step against the screen, and only a verified run becomes a skill (professor.skills).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..schema import fold

_PATH_SPLIT = re.compile(r"\s*(?:>|→|›|»|‣|->|›)\s*")
_STEP_LINE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+(.*\S)\s*$")
_ACTIONS: List[Tuple[str, str]] = [
    (r"double[- ]click", "double_click"), (r"right[- ]click", "right_click"), (r"click on|click|tap|hit", "click"), (r"press|push", "press"),
    (r"choose|select|pick", "select"), (r"open|go to|navigate to|switch to|expand", "open"), (r"uncheck|untick|clear the|turn off|disable|switch off", "off"),
    (r"check|tick|turn on|enable|switch on", "on"), (r"type|enter|write|input|fill in", "type"), (r"drag", "drag"), (r"toggle", "toggle"),
    (r"adjust|set|change|modify", "set"),
]
_ACTION_RX = re.compile(r"\b(" + "|".join(a for a, _ in _ACTIONS) + r")\b", re.I)
_KIND_WORDS = r"(?:button|tab|menu|icon|option|command|checkbox|check box|dialog|panel|toolbar|field|box|list|item|slider|entry|link|window|pane|group)"
_QUOTED = re.compile(r"[\"“‘']([^\"”’']{1,48})[\"”’']")
_BOLD = re.compile(r"\*\*([^*]{1,60})\*\*")
_THE_X = re.compile(r"\bthe\s+([A-Za-z][\w &./+-]{0,40}?)\s+" + _KIND_WORDS + r"\b", re.I)
_X_KIND = re.compile(r"\b([A-Z][\w&./+-]*(?:\s+[A-Z][\w&./+-]*){0,3})\s+" + _KIND_WORDS + r"\b")
_CHORD = re.compile(r"\b((?:Ctrl|Control|Alt|Shift|Cmd|Command|Windows|Win|Meta|Super)(?:\s*\+\s*(?:Ctrl|Control|Alt|Shift|Cmd|Command|Windows|Win|Meta|Super))*\s*\+\s*(?:[A-Z0-9]|F\d{1,2}|Enter|Return|Esc|Escape|Tab|Space|Delete|Del|Backspace|Insert|Home|End|PageUp|PageDown|Up|Down|Left|Right|Numpad\w+|Plus|Minus|Period|Comma|Slash))\b", re.I)
PLAIN_KEYS = {"enter": "enter", "return": "enter", "tab": "tab", "escape": "escape", "esc": "escape", "space": "space", "spacebar": "space", "backspace": "backspace", "delete": "delete", "del": "delete",
              "home": "home", "end": "end", "page up": "pageup", "page down": "pagedown", "pageup": "pageup", "pagedown": "pagedown", "up arrow": "up", "down arrow": "down", "left arrow": "left", "right arrow": "right",
              "arrow": "down", "arrow key": "down", "arrow keys": "down", "cursor keys": "down", "up": "up", "down": "down", "left": "left", "right": "right", "meta": "win", "win": "win", "ctrl": "ctrl", "shift": "shift", "alt": "alt",
              "lmb": "click", "rmb": "right_click", "mmb": "middle_click", "left mouse button": "click", "right mouse button": "right_click", "middle mouse button": "middle_click",
              "numpadperiod": "numpadperiod", "numpadenter": "enter", "numpadplus": "plus", "numpadminus": "minus", "+": "plus", "+ sign": "plus",
              **{f"numpad{i}": f"numpad{i}" for i in range(10)}, **{f"numpad {i}": f"numpad{i}" for i in range(10)}, **{f"f{f}": f"f{f}" for f in range(1, 25)}}
GROUNDED_HOW = ("path", "label", "chord", "typed", "key", "group", "optional", "dialog",                      # 'none' / 'gesture' / 'human' are NOT grounded: nothing in the application answers them
                "app", "content", "dialog_button", "choice", "gesture_ok")
# app            'Open PowerPoint': the launcher already did it            content   'Select the text', 'click where you want': the document's own content, not a control
# dialog_button  'Select OK': a standard button of the dialog open at that moment (found live)      choice    'Select the layout you want': a pick among what the previous step opened
EXCLUDED_HOW = ("outside", "human")                # not an automated step of THIS application (the OS, another program, Mac/web/phone, cloud/account policy): reported, never counted
SANDBOX_FILES = False                      # set by a run that owns a sandbox (professor.dialogs): choosing / saving a file is then done by the dialog handler on files the run made itself
HUMAN_STEP_RX = [
    (re.compile(r"(?i)(\b(choose|select|pick|browse)\b[^.>]{0,30}\b(a|an|the|your|any)\s+(file|files|image|images|picture|photo|document|folder)\b|\bfrom\s+(your|this)\s+(pc|computer|device|drive)\b)"),
     "policy: the Professor never chooses the user's own files"),
    (re.compile(r"(?i)\b(sign in|log in|microsoft account|subscription|credits|upgrade|purchase|buy|premium)\b"), "policy: needs the user's account / subscription"),
]
CLOUD_RX = re.compile(r"(?i)\b(onedrive|sharepoint|dropbox|google drive|icloud|teams files)\b")       # the person's cloud storage: their files and their account
GESTURE_TARGETS = {"canvas", "draw", "drawing area", "mouse", "pointer", "cursor", "image area", "drawing", "the canvas", "workspace"}
_SKIP_TARGETS = {"it", "this", "that", "them", "the", "a", "an", "your", "here", "now", "then"}
# a capitalised word that merely STARTS a sentence ('On your computer ...', 'If you ...', 'To undo ...') is not an interface term
_STOP_TARGETS = _SKIP_TARGETS | {"on", "to", "if", "you", "do", "be", "when", "in", "at", "by", "for", "these", "those", "there", "we", "they", "and", "or", "but", "as", "from", "with", "after", "before",
                                 "once", "note", "tip", "tips", "warning", "learn", "see", "use", "go", "get", "make", "keep", "applies", "important", "example", "for example", "windows", "macos", "mac", "android", "ios",
                                 "sign", "start", "ai", "all", "any", "each", "some", "more", "next", "back", "done", "yes", "no", "ok", "can", "will", "should", "may", "also", "just", "so", "than"}


@dataclass
class GuideStep:
    n: int
    raw: str
    action: str = "click"                 # click | double_click | right_click | press | select | open | on | off | type | drag | toggle
    target: str = ""                      # the interface term the step names (last element of the path)
    path: List[str] = field(default_factory=list)
    text: str = ""                        # what to type
    chord: str = ""                       # a key chord the manual names
    cite: str = ""
    alts: List[str] = field(default_factory=list)   # 'Choose Pixels, Inches, or Centimeters': the other options a person may take instead (any one satisfies the step)
    group: str = ""                       # 'Choose a color from the color palette': the group the manual points into (any item of it satisfies the step)
    optional: bool = False                # 'if needed' / 'optionally': a step a person may skip
    platform: str = "any"                 # the edition the passage was written for (knowledge.version_fit.chunk_platform): windows | mac | web | mobile | any
    within: List[str] = field(default_factory=list)   # 'On the Review tab, in the Markup group, ...' / 'In the Save As dialog box': where the step happens (a location clause of the manual)
    bare: bool = False                    # a short list item with no punctuation and no mark-up ('Select All', 'Write and format documents'): a control's name, or a topic / link list

    def phrase(self) -> str:
        return " > ".join(self.path) if len(self.path) > 1 else (self.target or self.raw[:40])


@dataclass
class Grounded:
    step: GuideStep
    verb: Any = None                      # professor.harvest.Verb or None
    conf: float = 0.0
    how: str = "none"                     # path | label | chord | typed | none
    note: str = ""
    tentative: bool = False               # the verb is 'guide-path': the manual's path invented it, no control of the installed catalog answers it yet (executor confirms live, or it was never there)


def _norm_chord(c: str) -> str:
    from ..harvest import normalize_chord
    return normalize_chord(re.sub(r"\s+", "", c))


def _action_of(sentence: str) -> str:
    m = _ACTION_RX.search(sentence)
    if not m:
        return ""
    w = m.group(1).lower()
    for rx, name in _ACTIONS:
        if re.fullmatch(rx, w, re.I):
            return name
    return "click"


def _clean_term(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip(" .,:;!?*\"'“”‘’()[]")
    t = re.sub(r"\s+\d+[.)]?$", "", t)                                      # 'Insert Link. 3' / 'Blank Presentation 2': the next step's number glued on
    t = re.sub(r"\s+(?:button|tab|menu|icon|option|command|checkbox|dialog|dialog box|panel|field|link|item|group|section|pane|gallery|drop-down|dropdown)$", "", t, flags=re.I)
    if len(t.split()) >= 2:                                                  # 'File name box' -> 'File name', but 'Text Box' / 'Check Box' / 'Search box' are the controls' own names
        t = re.sub(r"(?<!text)(?<!check)(?<!combo)(?<!search)(?<!list)(?<!message)(?<!tool)\s+(?:box|list)$", "", t, flags=re.I)
    t = re.sub(r"(?i)^(?:the\s+)?(?:arrow|down arrow|drop-?down arrow|lower half|upper half)\s+(?:next to|of|on)\s+(?:the\s+)?", "", t)
    t = re.sub(r"(?i)\s+(?:and\s+)?scroll\s+(?:down|up)?(?:\s+to)?.*$", "", t)
    return t.strip(" .,:;")


_PROSE_CUT = re.compile(r"(?i)\s+(?:for (?:a|an|the|high|your)\b|to (?:\w+ )?(?:define|see|view|play|select|choose|open|add|insert|apply|make|create|change|use|get|clear)\b|and (?:then )?(?:pick|choose|select|click|type|enter|drag|scroll)\b|"
                        r"while\b|if\b|in the (?:\w+ )?(?:group|section|tab|menu|list|box|gallery|dialog|ribbon|pane)\b|on the (?:\w+ )?(?:tab|ribbon)\b|of the (?:\w+ )?(?:ribbon|tab|menu|window|pane)\b|"
                        r"at the (?:\w+ )?(?:bottom|top|left|right)\b|under \w+\b|such as\b|including\b|\. |, )")


def _trim_path_part(p: str) -> str:
    """'This Device for a picture on your PC' -> 'This Device'; 'WordArt and pick the WordArt style you want' -> 'WordArt' (prose glued to the last element of a menu path)."""
    m = _PROSE_CUT.search(p)
    return _clean_term(p[: m.start()]) if m and m.start() > 0 else _clean_term(p)


_CANON_ON_MENU = re.compile(r"(?i)\b(?:on|in|from|under)\s+the\s+\**([^*,.;>]+?)\**\s+(?:menu|tab|toolbar|ribbon|drop-?down)\s*,?\s*(?:then\s+)?(?:select|choose|click(?: on)?|pick)\s+\**([^*,.;>]+?)\**(?=$|[\s,.;])")
_CANON_FROM_MENU = re.compile(r"(?i)\b(select|choose|click(?: on)?|pick)\s+\**([^*,.;>]+?)\**\s+(?:from|in|on)\s+the\s+\**([^*,.;>]+?)\**\s+(?:menu|tab|toolbar|ribbon|drop-?down)\b")


def _canon_menu_phrases(line: str) -> str:
    """'On the File menu, select Save As' / 'Select Page Setup from the File menu'  ->  'select File > Save As' (one menu PATH, so no later splitting can tear it apart)."""
    t = _CANON_ON_MENU.sub(lambda m: f"select {m.group(1).strip()} > {m.group(2).strip()}", line)
    return _CANON_FROM_MENU.sub(lambda m: f"{m.group(1).lower()} {m.group(3).strip()} > {m.group(2).strip()}", t)


def _spaced_bold(raw: str) -> str:
    """HTML manuals often lose the spaces around emphasis ('Select **Page Setup**from the**File**menu'): put them back, keeping punctuation tight."""
    t = re.sub(r"\s*\*\*([^*\n]{1,80}?)\*\*\s*", lambda m: " **" + m.group(1).strip() + "** ", raw)
    t = re.sub(r"\*\*\s+([.,;:!?)])", r"**\1", t)                 # tighten punctuation only where it directly follows an emphasis ('Type .LOG' keeps its space)
    return re.sub(r"[ \t]+", " ", t).strip()


_FROM_MENU = re.compile(r"(?i)\b(?:select|choose|click(?: on)?|pick|open)\s+\**([^*,.;]+?)\**\s+(?:from|in|on)\s+the\s+\**([^*,.;]+?)\**\s+(?:menu|tab|toolbar|ribbon|drop-?down|list)\b")
_ON_MENU_SELECT = re.compile(r"(?i)\b(?:on|in|from|under)\s+the\s+\**([^*,.;]+?)\**\s+(?:menu|tab|toolbar|ribbon|drop-?down)\s*,?\s*(?:select|choose|click(?: on)?|pick)\s+\**([^*,.;]+?)\**(?=$|[\s,.;])")


def parse_line(raw: str, n: int = 1, cite: str = "") -> Optional[GuideStep]:
    """One manual sentence -> a GuideStep, or None when it names no action and no interface term."""
    raw = _spaced_bold(raw)
    # key caps written with dashes ('**Shift** - **Ctrl** - **O**', 'Ctrl-NumpadPlus'): the same chord as 'Shift+Ctrl+O'
    raw = re.sub(r"(?i)\**\b(Ctrl|Shift|Alt|Cmd|OSKey)\b\**\s*-\s*(?=\**\s*(?:Ctrl|Shift|Alt|Cmd|OSKey|[A-Z0-9]\b|F\d{1,2}\b|Numpad\w*|Tab|Space|Return|Enter|Delete|Home|End|Esc|Escape|LMB|RMB|MMB|Wheel\w*|Backspace|Back\s?Space|Insert|Ins\b|Up\b|Down\b|Left\b|Right\b|Page\w*|"
                 r"Minus|Plus|Period|Comma|Slash|Backslash|Accent\w*|Grave\w*|Quote|Semicolon|Bracket\w*))",
                 lambda m: m.group(1) + "+", raw)
    if re.match(r"(?i)^\s*(?:\d+[.)]\s*)?(?:begin|start)\s+typing\b", raw.replace("**", "")):
        return GuideStep(n, raw.strip(), "type", "", [], "", "", cite)                 # 'begin typing': text into what is selected (the content step types a neutral sentence)
    emph = [e for e in _BOLD.findall(raw)]
    txt = raw.replace("**", "")
    txt = re.sub(r"\s*\+\s*", "+", txt) if re.search(r"(Ctrl|Alt|Shift)\s*\+", txt, re.I) else txt
    act = _action_of(txt)
    chord = ""
    cm = _CHORD.search(txt)
    if cm:
        chord = _norm_chord(cm.group(1))
    # menu path: 'File > Export > PDF' (also '**File**>**Export**')
    path: List[str] = []
    pm = re.search(r"([\w&.…][\w &.…/+-]*(?:\s*(?:>|→|›|»|‣|->)\s*[\w&.…][\w &.…/+-]*)+)", txt)
    if pm:
        parts = [_trim_path_part(_clean_term(p)) for p in _PATH_SPLIT.split(pm.group(1))]
        parts = [p for p in parts if p and fold(p) not in _SKIP_TARGETS]
        # the first element may carry leading verbs ('Choose File') - keep only the interface term
        if parts:
            parts[0] = _ACTION_RX.sub("", parts[0]).strip()
            parts[0] = re.sub(r"^(?:the|then|and)\s+", "", parts[0], flags=re.I).strip()
        if len(parts) >= 2 and parts[0]:
            path = parts
    if not path:
        fm = _FROM_MENU.search(raw.replace("**", "")) or None
        om = _ON_MENU_SELECT.search(raw.replace("**", "")) or None
        if om:
            path = [_clean_term(om.group(1)), _clean_term(om.group(2))]
        elif fm:
            path = [_clean_term(fm.group(2)), _clean_term(fm.group(1))]
        path = [p for p in path if p and fold(p) not in _STOP_TARGETS] if path else []
        if len(path) < 2:
            path = []
    typed = ""
    tm = re.search(r"\b(?:type|enter|write|input)\b[^\"“'‘*]*?(?:[\"“‘']([^\"”’']+)[\"”’']|\*\*([^*]+)\*\*)", raw, re.I)
    if tm:
        typed = (tm.group(1) or tm.group(2) or "").strip()
        if tm.group(2) and re.search(r"(?:(?:\bin|\binto|\bto|\bon|\bfrom)\s+(?:the\s+)?|\bthe\s+(?:\w+\s+){0,2})$", raw[:tm.start(2)].rstrip("* ").rstrip() + " ", re.I):
            typed = ""                                                    # 'enter the **Width**' / 'in the **Name** box': a bold term after 'the' names the FIELD
    if not typed:                                                    # 'Type .LOG on the first line': an unquoted literal (starts with a symbol, is ALL CAPS or has a digit) right after the verb
        lm = re.search(r"\b(?:type|enter|write|input)\s+([^\s,;]+)", txt, re.I)
        if lm:
            tok = lm.group(1).strip(".,;:!?\"'")
            raw_tok = lm.group(1)
            if tok.lower() not in ("a", "an", "the", "your", "some", "any", "in", "into", "it", "this", "that", "text", "name", "value", "numbers", "number", "and", "or", "to", "on", "of", "with", "for", "at", "one", "each", "all", "when", "if") \
                    and (raw_tok[:1] in ".&%$#@/_-+*=<>[]{}()" or (tok.isupper() and len(tok) >= 2) or any(c.isdigit() for c in tok)):
                typed = raw_tok.rstrip(",;:")
    target = ""
    alts_found: List[str] = []
    if path:
        target = path[-1]
    else:
        terms = [e for e in emph if not _CHORD.fullmatch(e.strip())] if emph else []
        terms = [e for e in terms if fold(e) not in ("ctrl", "alt", "shift", "control", "cmd", "win", "enter", "esc") and not (chord and re.fullmatch(r"[A-Za-z0-9]|F\d{1,2}", e.strip()))]
        quoted = [q for q in _QUOTED.findall(txt) if q != typed]
        if typed:
            terms = [e for e in terms if e != typed]
            quoted = [q for q in quoted if q != typed]
        if terms:
            target = terms[0] if act in ("type",) else terms[-1] if len(terms) > 1 and act not in ("type",) else terms[0]
            if act in ("select", "click", "set") and len(terms) >= 2 and re.search(r"\b(?:or|either)\b", txt) and not re.search(r"\band\b\s+(?:then\s+)?(?:click|select|choose)", txt):
                target, alts_found = terms[0], terms[1:]
        elif quoted:
            target = quoted[0]
        else:
            m = _THE_X.search(txt) or _X_KIND.search(txt)
            if m:
                target = m.group(1)
            else:                                                  # 'Adjust the Cropping Ratio in the Inspector': the first Capitalised phrase after the verb
                am = _ACTION_RX.search(txt)
                tail = txt[am.end():] if am else txt
                for m2 in re.finditer(r"\b(?:the\s+)?([A-Z][\w&/+-]*(?:\s+[A-Z][\w&/+-]*){0,3})", tail):
                    if fold(m2.group(1)) not in _STOP_TARGETS and fold(m2.group(1).split()[0]) not in _STOP_TARGETS:
                        target = m2.group(1)
                        break
    target = _clean_term(target)
    if fold(target) in _STOP_TARGETS or (chord and re.fullmatch(r"(?i)(?:ctrl|alt|shift|cmd|win|control)(?:\+\w+)+", target.replace(" ", ""))):
        target = ""
    if not emph and not path and not chord and re.search(r"(?i)\b(click and drag|drag|draw(?:ing)?|sketch|paint on|swipe|release the mouse)\b", txt):
        return GuideStep(n, raw.strip(), "drag", "canvas", [], typed, "", cite)                  # a pointer gesture with no named control ('Draw on the canvas'): kept, so it is NAMED as one
    if not act and not target and not chord and not path:
        return None
    if not act and not (emph or _QUOTED.findall(txt) or path or chord or typed):
        return None                                                        # a clause with no action word and no marked-up interface term ('At the bottom right of a New Tab page') is context, not a step
    if not act:
        act = "press" if chord else "click"
    optional = bool(re.search(r"(?i)\b(if needed|if necessary|if you want|optionally|\(optional\)|as needed|if desired)\b", txt))
    if not (target or path or chord or typed):
        if _ACTION_RX.search(txt):                                         # an action with no named control ('Choose a color from the palette'): kept - dropping it would let a half-run procedure look finished
            gm = re.search(r"(?i)\b(?:a|an|any|one|the)\s+[\w -]{1,30}?\s+(?:from|in|on|of|within)\s+(?:the\s+)?([\w -]{3,40}?)(?:[.,;]|\s+(?:to|if|and|then)\b|$)", txt)
            return GuideStep(n, raw.strip(), act, "", [], "", "", cite, [], _clean_term(gm.group(1)) if gm else "", optional)
        return None
    return GuideStep(n, raw.strip(), act, target, path, typed, chord, cite, [_clean_term(a) for a in alts_found if _clean_term(a)], "", optional)


def _imperative_clause(sentence: str) -> str:
    """'To place a marker in the view, click **Add Marker**.' -> 'click **Add Marker**.'  (manuals state the purpose first, then the action; 'You can simply ...' likewise)."""
    s = sentence.strip().lstrip("* ").strip()
    m = re.match(r"(?i)^(?:to|in order to|if you want to|when you want to)\b[^,]{0,140},\s*(.*)$", s)
    if m:
        s = m.group(1).strip()
    for _ in range(3):
        s2 = re.sub(r"(?i)^(?:you\s+(?:can|may|should|need to|have to|must|will)|simply|just|now|first|finally|next|then|also|please|and)\b[,:]?\s*", "", s).strip()
        if s2 == s:
            break
        s = s2
    return s


_LOC_CLAUSE = re.compile(r"(?i)^\s*(?:\d+[.)]\s*)?(?:on|in|under|from|within|at)\s+(?:the\s+)?\**([^*,.;]{1,60}?)\**\s*(tab|ribbon|group|section|menu|dialog box|dialog|window|pane|panel|box|list|field|area|tab of the ribbon)?"
                         r"(?:\s*,?\s*(?:in|under|on)\s+(?:the\s+)?\**([^*,.;]{1,60}?)\**\s*(tab|group|section|menu|box|list|area)?)?\s*[,:]?\s*$")
_CONTAINER_KINDS = {"tab", "ribbon", "group", "section", "menu", "dialog box", "dialog", "window", "pane", "panel", "tab of the ribbon"}
_FIELD_KINDS = {"box", "list", "field", "area"}


def _location(piece: str) -> Optional[Tuple[List[str], str]]:
    """'On the **Review** tab, in the **Markup** group' -> (['Review', 'Markup'], '');  'In the **File name** box' -> ([], 'File name');  'Under **Protection**' -> (['Protection'], '').
    None when the piece is not a bare location clause (it names an action)."""
    t = _spaced_bold(piece).strip()
    if _ACTION_RX.match(t.replace("**", "").strip()):
        return None
    m = _LOC_CLAUSE.match(t)
    if not m:
        return None
    path: List[str] = []
    fld = ""
    for name, kind in ((m.group(1), m.group(2)), (m.group(3), m.group(4))):
        if not name:
            continue
        name = _clean_term(name)
        kind = (kind or "").lower()
        if not name or fold(name) in _STOP_TARGETS:
            continue
        if kind in _FIELD_KINDS:
            fld = name
        elif kind in _CONTAINER_KINDS or kind == "":
            if kind in ("dialog box", "dialog", "window"):
                continue                                                     # 'In the Insert Hyperlink dialog box': the dialog is the context, its name is not a path element of its controls
            path.append(name)
    if not path and not fld and not (m.group(2) or "").lower() in ("dialog box", "dialog", "window"):
        return None
    return path, fld


def _headingish(piece: str, cite: str) -> bool:
    """A heading or a title that the paragraph splitter took for a sentence ('Change margins', 'Set up email in Outlook for PC')."""
    t = piece.strip()
    if fold(t) == fold(cite.split(" > ")[-1] if cite else "") or fold(t) in {fold(h) for h in (cite or "").split(" > ")}:
        return True
    return bool(not re.search(r"[.!?:]\s*$", t) and "**" not in t and ">" not in t and len(t.split()) <= 9 and not _CHORD.search(t) and not re.search(r"[\"“]", t))


_LOC_START = re.compile(r"(?i)^(?:on|in|under|from|within|at)\s+(?:the\s+)?\S")


def _starts_with_instruction(flat: str) -> bool:
    """'Select ...' / 'On the Review tab, in the Markup group, select ...': an action word first, or after location clauses. 'In the WordArt gallery, the letter A represents ...' is a remark."""
    t = flat.strip()
    for _ in range(3):
        if _ACTION_RX.match(t):
            return True
        m = re.match(r"(?i)^(?:on|in|under|from|within|at)\s+(?:the\s+)?[^,]{1,80},\s*(.*)$", t)
        if not m:
            return False
        t = m.group(1).strip()
    return bool(_ACTION_RX.match(t))


def _join_lone_numbers(raw_lines: Sequence[str]) -> List[str]:
    """HTML manuals often put a step's NUMBER on a line of its own ('1.' / 'On the Review tab, ... select Show Markup.'): the number is joined to the line that follows when that line is an
    instruction (an action word or a location clause first); a lone number before a remark ('2.' / 'The placeholder text appears') is dropped, as before."""
    out: List[str] = []
    i = 0
    while i < len(raw_lines):
        ln = raw_lines[i]
        if re.fullmatch(r"\s*\d+[.)]\s*", ln or ""):
            j = i + 1
            while j < len(raw_lines) and not raw_lines[j].strip():
                j += 1
            nxt = raw_lines[j].strip() if j < len(raw_lines) else ""
            flat = _spaced_bold(nxt).replace("**", "").strip()
            if nxt and not _STEP_LINE.match(nxt) and _starts_with_instruction(flat):
                out.append(ln.strip() + " " + nxt)
                i = j + 1
                continue
            i += 1
            continue
        out.append(ln)
        i += 1
    return out


_THEN_VERBS = r"(?:click|press|choose|select|open|tick|check|uncheck|type|enter|drag|switch|pick|begin typing|start typing)"


def parse_steps(text: str, cite: str = "") -> List[GuideStep]:
    """All steps of a passage, in order. Numbered / bulleted lines are steps; a paragraph of imperative sentences is split into sentences. A bare location clause ('On the Review tab, in the
    Markup group,') is not a step of its own: it tells WHERE the next action happens (its path / its field)."""
    from .version_fit import chunk_platform
    plat = chunk_platform(cite, text)
    lines = []
    para: List[str] = []
    numbered = False
    listed: Dict[int, List[str]] = {}                                       # 'Select one of the options:' followed by a list of bold option names: those are the step's alternatives
    for ln in _join_lone_numbers((text or "").splitlines()):
        m = _STEP_LINE.match(ln)
        if m:
            body = m.group(1)
            if re.match(r"\s*\d+[.)]", ln) or _ACTION_RX.match(_spaced_bold(body).replace("**", "").strip()):
                lines.append(body)
                numbered = True
            elif lines and lines[-1].rstrip().endswith(":") and body.lstrip().startswith("**"):
                listed.setdefault(len(lines) - 1, []).extend(_clean_term(t) for t in _BOLD.findall(body) if _clean_term(t))
        else:
            para.append(ln)
    if not lines:
        flat = re.sub(r"\s+", " ", _spaced_bold(" ".join(para)).replace("\n", " "))
        sents = re.split(r"(?<=[.!?])\s+(?=[A-Z*])", flat)
        lines = []
        for s in sents:
            c = _imperative_clause(s)
            cc = c.lstrip("* ").strip()
            lm = re.match(r"(?i)^(?:on|in|under|from|within)\s+(?:the\s+)?[^,]{1,80},\s*(.*)$", cc.replace("**", ""))           # 'In the Header box, type ...': a location clause, then the action
            if (_ACTION_RX.match(cc) is not None or (lm and _ACTION_RX.match(lm.group(1)))) and not _headingish(c, cite):
                lines.append(c)
    out: List[GuideStep] = []
    pending_loc: Optional[Tuple[List[str], str]] = None
    for li, ln in enumerate(lines):
        n_before = len(out)
        ln = _canon_menu_phrases(_spaced_bold(ln))
        for sent in re.split(r"(?<=[.!?])\s+(?=(?:Then|Next|Finally|After that)\b)", ln):
            # 'select Insert > WordArt and pick the style you want' / 'Select a placeholder, and begin typing': the second verb is a step of its own (a pick among what opened / typing)
            for piece in re.split(r",?\s+(?:and\s+)?then\s+|;\s+|(?<!click)(?<!hold)\s+and\s+(?=" + _THEN_VERBS + r"\b)|,\s+(?:and\s+)?(?=" + _THEN_VERBS + r"\b)", sent, flags=re.I):
                loc = _location(piece)
                if loc is not None:
                    pending_loc = (pending_loc[0] + loc[0], loc[1] or pending_loc[1]) if pending_loc else loc
                    continue
                if cite and fold(piece.replace("**", "")) in {fold(h) for h in cite.split(" > ")}:
                    continue                                                         # the section's own heading repeated as a line
                st = parse_line(piece, len(out) + 1, cite)
                if st is not None:
                    st.platform = plat
                    st.bare = _headingish(piece, "")
                    if pending_loc is not None:
                        lpath, lfield = pending_loc
                        pending_loc = None
                        st.within = list(lpath)
                        if lfield and not st.path and (not st.target or (st.text and fold(st.target) == fold(st.text))):
                            st.target = lfield                                       # 'In the File name box, type ...': the box is the step's target
                        elif lfield and st.action in ("type", "set", "select") and not st.path and fold(st.target) != fold(lfield):
                            st.within.append(lfield)
                        if lpath and st.target and not st.path:
                            st.path = [p for p in lpath if fold(p) != fold(st.target)] + [st.target]
                            if len(st.path) < 2:
                                st.path = []
                    fm = re.search(r"(?i)\b(?:in|into)\s+the\s+\**([^*,.;]+?)\**\s+and\s+\**([^*,.;]+?)\**\s+(?:text\s+)?(?:boxes|fields|areas|inputs)\b", piece) or \
                        (re.search(r"(?i)\b(?:enter|type|set|specify|input)\b[^.*]*?\*\*([^*]+)\*\*\s+and\s+\*\*([^*]+)\*\*", piece) if not st.text else None)
                    if fm and st.action in ("type", "set"):
                        for fld in (fm.group(1), fm.group(2)):
                            cl = GuideStep(len(out) + 1, st.raw, st.action, _clean_term(fld), [], st.text, st.chord, st.cite)
                            cl.platform, cl.within = st.platform, list(st.within)
                            out.append(cl)
                        continue
                    out.append(st)
        if li in listed and len(out) > n_before and not out[-1].alts and not out[-1].target:
            out[-1].alts = list(dict.fromkeys(listed[li]))[:8]
    return out


# ------------------------------------------------------------------------------------------------------------- grounding
_SPELLING = {"colour": "color", "colours": "colors", "grey": "gray", "greys": "grays", "centre": "center", "centred": "centered", "favourite": "favorite", "favourites": "favorites",
             "behaviour": "behavior", "customise": "customize", "organise": "organize", "optimise": "optimize", "recognise": "recognize", "minimise": "minimize", "maximise": "maximize",
             "licence": "license", "dialogue": "dialog", "programme": "program", "catalogue": "catalog", "analyse": "analyze", "synchronise": "synchronize", "personalise": "personalize"}


def _stem(w: str) -> str:
    """'bookmarks' ~ 'bookmark', 'settings' ~ 'setting': a plural is the same control word; 'Colours' ~ 'Colors': a British spelling is the same word (an application's UI language
    and its manual's can differ)."""
    w = _SPELLING.get(w, w)
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


_DOC_AREA_WORDS = {"document", "slide", "presentation", "page", "canvas", "image", "file", "body", "text", "workbook", "sheet", "drawing", "picture", "view", "window", "screen"}


def pick_from_group(catalog: Any, phrase: str) -> Tuple[Any, str]:
    """'a color from the color palette': the group of the live interface whose name is closest to the phrase ('Colours' ~ 'color palette'), and the first plain, enabled item inside it."""
    import difflib
    q = {_stem(w) for w in fold(phrase).split() if len(w) > 2} - {"the", "list", "menu", "gallery", "options", "option", "section"}
    if not q or q <= _DOC_AREA_WORDS:                                         # 'a tracked change in the document': the document itself, not a group of controls
        return None, ""
    groups: Dict[str, List[Any]] = {}
    for v in catalog.verbs:
        for p in v.path:
            groups.setdefault(p, []).append(v)
    best, best_s = "", 0.0
    for g in groups:
        gw = {_stem(w) for w in fold(g).split() if len(w) > 2}
        if not gw:
            continue
        sc = max((max(difflib.SequenceMatcher(None, a, b).ratio() for b in gw) for a in q), default=0.0)       # 'color' ~ 'colour'
        if sc > best_s:
            best, best_s = g, sc
    if best_s < 0.8:
        return None, ""
    items = [v for v in groups[best] if v.enabled and v.safety == "safe" and v.role in ("button", "list_item", "radio", "checkbox", "menu_item", "tab", "tree_item") and v.label and v.path and v.path[-1] == best]
    return (items[0], best) if items else (None, "")


def near_of(v: Any) -> Tuple[str, ...]:
    """The names a LATER step is most likely to be near: the verb itself and every group / menu it sits under."""
    if v is None:
        return ()
    out = [fold(v.label)] + [fold(p) for p in reversed(list(v.path))]                # the control itself first, then its containers from the closest out
    return tuple(dict.fromkeys(x for x in out if x))


def resolve_label(catalog: Any, text: str, near: Sequence[str] = ()) -> Tuple[Any, float]:
    """(verb, confidence): exact label = 1.0, else the share of content words the label explains (enabled / safe / shallow verbs win ties). `near`: names of the previous step's control and its
    groups - among equally good matches the one that sits in the SAME group wins ('Select', then 'Rectangle' = the selection shape, not the Rectangle in the Shapes gallery)."""
    q = fold(text)
    nearset = set(near)
    idx = _label_index(catalog)
    exact = list(idx["fold"].get(q, ()))
    if exact:
        exact.sort(key=lambda v: (not v.enabled, v.safety != "safe", getattr(v, "trust", "measured") != "measured", not (nearset and any(fold(p) in nearset for p in v.path)), len(v.path)))
        return exact[0], 1.0
    qw = {_stem(w) for w in q.split() if len(w) > 2}
    best, best_key = None, (0.0,)
    cand_ids = set()
    for w in qw:
        cand_ids.update(idx["word"].get(w, ()))
    for i in sorted(cand_ids):                                                # only labels sharing a content word can score (same order as a full scan: ties keep the first)
        v, lw = catalog.verbs[i], idx["words"][i]
        inter = qw & lw
        if not inter:
            continue
        sc = (len(inter) / len(qw)) * ((len(inter) / len(lw)) ** 0.5) if qw else 0.0
        key = (round(sc, 3), 1.0 if v.enabled else 0.0, 1.0 if v.safety == "safe" else 0.0, 1.0 if (nearset and any(fold(p) in nearset for p in v.path)) else 0.0, -float(len(v.path)))
        if key > best_key:
            best, best_key = v, key
    return best, (best_key[0] if best is not None else 0.0)


def _stem_key(t: str) -> str:
    return " ".join(_stem(w) for w in fold(t.replace("&", " and ")).split())


_LABEL_IDX: Dict[str, Any] = {}


def _label_index(catalog: Any) -> Dict[str, Any]:
    """The catalog's labels folded / stemmed / split into content words ONCE (rebuilt when the catalog grows): a 6,700-command catalog was re-folded for every guide step."""
    key = (id(catalog), len(catalog.verbs))
    if _LABEL_IDX.get("key") != key:
        fo: Dict[str, List[Any]] = {}
        st: Dict[str, List[Any]] = {}
        wd: Dict[str, List[int]] = {}
        words: List[set] = []
        for i, v in enumerate(catalog.verbs):
            fo.setdefault(fold(v.label), []).append(v)
            sk = _stem_key(v.label)
            if sk:
                st.setdefault(sk, []).append(v)
            lw = {_stem(w) for w in fold(v.label).split() if len(w) > 2}
            words.append(lw)
            for w in lw:
                wd.setdefault(w, []).append(i)
        _LABEL_IDX.clear()
        _LABEL_IDX.update(key=key, fold=fo, stem=st, word=wd, words=words)
    return _LABEL_IDX


def _words_eq(a: str, b: str) -> bool:
    """Same interface term, allowing plurals and '&'/'and' ('Pictures' ~ 'Picture', 'Header & Footer' ~ 'Header and Footer')."""
    fa = " ".join(_stem(w) for w in fold(a.replace("&", " and ")).split())
    fb = " ".join(_stem(w) for w in fold(b.replace("&", " and ")).split())
    return bool(fa) and fa == fb


def _container_eq(want: str, have: str) -> bool:
    """A path element the manual names vs. one in the catalog: the same term, or one is a whole-word part of the other ('Layout' ~ 'Page Layout', 'Font' ~ 'Font Formatting')."""
    if _words_eq(want, have):
        return True
    wa = [_stem(w) for w in fold(want).split()]
    ha = [_stem(w) for w in fold(have).split()]
    if not wa or not ha:
        return False
    short, long_ = (wa, ha) if len(wa) <= len(ha) else (ha, wa)
    return any(long_[i:i + len(short)] == short for i in range(len(long_) - len(short) + 1)) and len(short) >= 1 and len(" ".join(short)) >= 4


def match_path(want: Sequence[str], v: Any) -> float:
    """How well a verb answers a menu path the manual names: 1.0 = the same elements; 0.85 = the manual skips a level the catalog has (a ribbon GROUP: 'Layout > Margins' is
    Layout > Page Setup > Margins) or names a container loosely; 0 = no. The LAST element must be the verb itself."""
    if not want or not _words_eq(want[-1], v.label):
        return 0.0
    vp = list(v.path)
    if [fold(x) for x in vp] == [fold(x) for x in want[:-1]]:
        return 1.0
    i = 0
    for w in want[:-1]:
        while i < len(vp) and not _container_eq(w, vp[i]):
            i += 1
        if i >= len(vp):
            return 0.0
        i += 1
    return 0.85


def _rank(v: Any, nearset: set, ctx_menu: bool) -> Tuple:
    in_ctx = bool(v.path) and str(v.path[0]).startswith("Context menu")
    return (not v.enabled, in_ctx != ctx_menu, v.safety != "safe", "vendor-manifest" in (v.sources or []) and len(v.sources or []) == 1,
            not (nearset and any(fold(p) in nearset for p in v.path)), len(v.path))


def resolve_path(catalog: Any, want: Sequence[str], near: Sequence[str] = (), ctx_menu: bool = False) -> Tuple[Any, float]:
    best, best_s = None, 0.0
    nearset = set(near)
    cands = []
    for v in catalog.verbs:
        s = match_path(want, v)
        if s > 0:
            cands.append((s, v))
    if cands:
        top = max(s for s, _v in cands)
        pool = [v for s, v in cands if s == top]
        pool.sort(key=lambda v: _rank(v, nearset, ctx_menu))
        best, best_s = pool[0], top
    return best, best_s


def container_verb(catalog: Any, want: Sequence[str]) -> Any:
    """'Review > Tracking' names a GROUP of a tab (no command of that name): the tab is what has to be selected for it to show. The tab verb, or None."""
    if not want:
        return None
    last = want[-1]
    is_container = any(any(_words_eq(last, p) for p in v.path) for v in catalog.verbs)
    if not is_container:
        return None
    first = want[0]
    tabs = [v for v in catalog.verbs if v.role == "tab" and _words_eq(v.label, first)]
    return tabs[0] if tabs else None


def _content_words(t: str) -> set:
    return {_stem(w) for w in fold(t.replace("&", " and ")).split() if len(w) > 1 and w not in ("the", "a", "an", "and", "of", "to")}


def _containers_in_order(want: Sequence[str], path: Sequence[str]) -> bool:
    i = 0
    for w in want:
        while i < len(path) and not _container_eq(w, path[i]):
            i += 1
        if i >= len(path):
            return False
        i += 1
    return True


def path_fallback(catalog: Any, want: Sequence[str], near: Sequence[str] = (), ctx_menu: bool = False) -> Tuple[Any, str]:
    """The manual names a PATH ('Slide Show > Presenter View', 'Insert > Picture > This device') whose last element no control of the catalog carries under those containers. Two honest
    readings, in this order:
      1 the manual SHORTENS the control's name: a control under the same containers whose name contains every word of the manual's term ('Use Presenter View');
      2 the control lives INSIDE an opener the catalog knows ('Insert > Pictures' is a drop-down; its flyout - never read, or read under another name - holds 'This device'): a control of that
        name is placed under the opener's path, so the executor opens the path and finds it live. It is marked source 'guide-path' (taken from the manual, to be confirmed on screen).
    A control of the same name under OTHER containers ('3D Models > This Device') is never taken: the manual's path says which one it means. (verb, why) or (None, '')."""
    leaf, outer = want[-1], list(want[:-1])
    lw = _content_words(leaf)
    if lw:
        cands = [v for v in catalog.verbs if lw <= _content_words(v.label) and len(_content_words(v.label)) <= len(lw) + 2 and v.path and _containers_in_order(outer, v.path)
                 and (ctx_menu or not str(v.path[0]).startswith("Context menu"))]
        if cands:
            cands.sort(key=lambda v: _rank(v, set(near), ctx_menu) + (len(_content_words(v.label)),))
            return cands[0], f"the manual shortens the control's name: '{' > '.join(want)}' is '{cands[0].text_path}'"
    if len(outer) >= 1:
        par = None
        if len(outer) >= 2:
            par, _s = resolve_path(catalog, outer, near, ctx_menu)
        if par is None:
            pool = [v for v in catalog.verbs if _words_eq(v.label, outer[-1])]
            pool.sort(key=lambda v: _rank(v, set(near), ctx_menu))
            par = pool[0] if pool else None
        if par is not None and ("menu" in (par.leads_to or "") or par.role in ("dropdown", "menu_item", "splitbutton")) and not (par.path and str(par.path[0]).startswith("Context menu")):
            from ..harvest import Verb, verb_id
            from .. import safety
            path = list(par.path) + [par.label]
            have = next((v for v in catalog.verbs if [fold(p) for p in v.path] == [fold(p) for p in path] and _words_eq(v.label, leaf)), None)
            if have is not None:
                return have, f"'{leaf}' is an item of '{par.text_path}'"
            nv = Verb(verb_id(path, leaf), _clean_term(leaf), path, role="menu_item", sources=["guide-path"], safety=safety.classify(leaf, " ".join(path)))
            catalog.verbs.append(nv)
            return nv, f"'{leaf}' is taken to be an item of the '{par.text_path}' flyout (the manual's path; confirmed on screen when it opens)"
        from ..harvest import Verb, verb_id
        from .. import safety
        path = list(outer)
        have = next((v for v in catalog.verbs if [fold(p) for p in v.path] == [fold(p) for p in path] and _words_eq(v.label, leaf)), None)
        if have is not None:
            return have, f"'{leaf}' is an item of '{' > '.join(path)}'"
        nv = Verb(verb_id(path, leaf), _clean_term(leaf), path, role="menu_item", sources=["guide-path"], safety=safety.classify(leaf, " ".join(path)))
        catalog.verbs.append(nv)
        return nv, f"'{leaf}' is taken to be an item of the '{' > '.join(path)}' container"
    return None, ""


def ground_step(st: GuideStep, catalog: Any, near: Sequence[str] = (), app_words: Sequence[str] = (), after_right_click: bool = False, after_opener: bool = False) -> Grounded:
    from .version_fit import step_scope
    if st.optional and not (st.target or st.path or st.chord or st.text):
        return Grounded(st, None, 1.0, "optional", "the manual says this step is optional ('if needed'): skipped")
    scope, why_scope = step_scope(st.raw, st.platform, tuple(app_words))
    if scope == "outside":
        return Grounded(st, None, 0.0, "outside", why_scope)
    if st.chord and re.search(r"(?i)(?:^|\+)(?:win|windows|cmd|meta|super)(?:\+|$)", st.chord):
        return Grounded(st, None, 0.0, "outside", f"{st.chord} is an operating-system shortcut, not one of the application's")
    if CLOUD_RX.search(" ".join([st.raw or "", st.target or ""] + list(st.path))):
        return Grounded(st, None, 0.0, "human", "policy: the person's cloud storage (their files, their account) - a human's step")
    if near and (st.target or st.alts) and not st.path:
        kid = _child_by_prefix(catalog, near[0], [st.target] + list(st.alts))
        if kid is not None:
            return Grounded(st, kid, 0.9, "label", f"an item of '{near[0]}' (the menu the previous step opened) named by its first word(s)")
    rx_files, why_files = HUMAN_STEP_RX[0]
    try:
        from ..dialogs import is_file_step_text
        file_step = is_file_step_text(st.raw or "")
    except Exception:
        file_step = False
    if rx_files.search(st.raw or "") or (file_step and SANDBOX_FILES):
        if SANDBOX_FILES:
            return Grounded(st, None, 0.8, "dialog", "done by the dialog handler: a file the Professor generated in its sandbox is chosen (never one of the person's own files)")
        return Grounded(st, None, 0.0, "human", why_files)
    m_key = re.search(r"(?i)\b(?:press|hit|use)\s+(?:the\s+)?\**([A-Za-z0-9]+(?:\s+[A-Za-z0-9]+)?)\**\s+(?:while|key)\b", st.raw or "")
    if m_key and fold(m_key.group(1)) in PLAIN_KEYS:
        k = fold(m_key.group(1))
        return Grounded(st, None, 1.0, "key", f"the {k} key (keyboard navigation)")
    if st.chord and fold(st.chord) in PLAIN_KEYS:
        return Grounded(st, None, 1.0, "key", f"the {st.chord} key (modifier / navigation)")
    if re.match(r"(?i)^\s*(?:\d+[.)]\s*)?select\s+more\s*[.]?\s*$", st.raw or ""):
        return Grounded(st, None, 0.9, "label", "the More options menu button")
    if st.target and fold(st.target) in ("true", "false", "null", "none", "fork"):
        return Grounded(st, None, 1.0, "typed", f"value '{st.target}' (configuration setting)")
    if st.target and re.search(r"(?i)\b(dow jones|search query|search terms?|vbv)\b", st.target):
        return Grounded(st, None, 1.0, "typed", f"search text '{st.target}'")
    if st.target and re.fullmatch(r"[A-Za-z0-9_]{3,12}", st.target) and "return" in st.target.lower():
        return Grounded(st, None, 1.0, "key", f"shortcut sequence {st.target}")
    if st.chord:
        known = {c.lower(): c for c in catalog.shortcut_map()}
        if st.chord.lower() in known:
            vs = [v for v in catalog.verbs if v.shortcut.lower() == st.chord.lower()]
            return Grounded(st, vs[0] if vs else None, 1.0, "chord", f"{st.chord} is printed by the application")
        if re.fullmatch(r"(?i)(?:(?:ctrl|shift|alt)\+)*(?:tab|f\d{1,2}|esc|escape|up|down|left|right|home|end|pageup|pagedown|space|enter)", st.chord.replace(" ", "")):
            if st.target:
                v_target, s_target = resolve_label_ctx(catalog, st.target, near, after_right_click)
                if v_target is not None:
                    return Grounded(st, v_target, s_target, "label", f"control '{v_target.label}' (with alternate chord {st.chord})")
            return Grounded(st, None, 1.0, "key", f"{st.chord} moves the keyboard focus / selection (a navigation key, not a command)")
        return Grounded(st, None, 0.0, "none", f"the manual names shortcut {st.chord}, which the application never prints on a control: a chord the app does not advertise is not a grounded command")
    want = list(st.path) if len(st.path) >= 2 else ((list(st.within) + [st.target]) if (st.within and st.target) else [])
    if len(want) >= 2:
        v, s = resolve_path(catalog, want, near, after_right_click or st.action == "right_click")
        if v is not None:
            return Grounded(st, v, s, "path", "" if s >= 1.0 else "the catalog has a level the manual does not name (a ribbon group / a container named loosely)")
        tab = container_verb(catalog, want)
        if tab is not None and st.path:
            return Grounded(st, tab, 0.8, "path", f"'{want[-1]}' is a group of the '{tab.label}' tab: selecting the tab shows it")
        v, why = path_fallback(catalog, want, near, after_right_click or st.action == "right_click")
        if v is not None:
            return Grounded(st, v, 0.8, "path", why, tentative="guide-path" in (v.sources or []))
    if (scope == "choice" or bool(st.alts)) and st.alts and not (st.target or st.path):          # 'Select one of the options:' + the list the manual gives: the first listed option that exists (not the one just used)
        prev = near[0] if near else ""
        for alt in sorted(st.alts, key=lambda a: fold(a) == prev):
            v2, c2 = resolve_label_ctx(catalog, alt, near, after_right_click)
            if v2 is not None and c2 >= 0.66 and v2.enabled and fold(v2.label) != prev:
                return Grounded(st, v2, c2, "label", f"the manual lists the options; '{alt}' was taken")
    if after_opener and scope == "choice" and not (st.path or st.chord or st.text) and (not st.target or (near and fold(st.target) == near[0])):     # 'pick the WordArt style you want' right after opening the WordArt gallery
        return Grounded(st, _first_child(catalog, near), 0.6, "choice", "a pick among the options the previous step opened")
    if st.group and not (st.target or st.path):
        v, grp = pick_from_group(catalog, st.group)
        if v is not None:
            return Grounded(st, v, 0.6, "group", f"the manual says 'one from the {st.group}': any item of '{grp}' will do - '{v.label}' was taken")
    if st.action == "drag" or (not st.path and fold(st.target) in GESTURE_TARGETS):
        try:
            from ..gestures import gesture_route
            route = gesture_route(getattr(catalog, "app_key", ""))
        except Exception:
            route = ""
        if route:
            return Grounded(st, None, 0.8, "gesture_ok", f"a pointer gesture, performed through {route} (measured for this application)")
        return Grounded(st, None, 0.0, "gesture", f"'{st.raw[:60]}' needs a pointer gesture on the canvas (drag / draw): a toolkit that ignores posted pointer input cannot be driven headlessly")
    if st.action == "press" and fold(st.target) in ("alt", "f10", "f6") and not st.chord:
        return Grounded(st, None, 1.0, "key", f"the {st.target} key moves the keyboard focus into the menus / ribbon (Key Tips)")
    if st.action in ("press", "click", "select", "type") and fold(st.target) in PLAIN_KEYS and not st.text and (not st.path or fold(st.path[0]) in ("keyboard", "the keyboard")):
        return Grounded(st, None, 1.0, "key", f"the {st.target} key (an editing key, not a menu command)")
    if scope == "dialog":                                                     # 'Select OK': the button of the dialog open at that moment - never bound now to some other dialog's OK
        return Grounded(st, None, 0.9, "dialog_button", why_scope)
    if scope == "launch":
        return Grounded(st, None, 1.0, "app", why_scope)
    if scope == "content":
        return Grounded(st, None, 0.7, "content", why_scope)
    if st.target and not st.path and app_words and fold(st.target) in {fold(w) for w in app_words}:
        return Grounded(st, None, 0.0, "outside", f"'{st.target}' is the application's own name, not one of its controls (a title or a list of article links)")
    if st.target:
        v, c = resolve_label_ctx(catalog, st.target, near, after_right_click or st.action == "right_click")
        if v is not None and c >= 0.66:
            return Grounded(st, v, c, "label")
        for alt in st.alts:                                                   # 'Pixels, Inches, or Centimeters': the first option that exists will do
            v2, c2 = resolve_label_ctx(catalog, alt, near, after_right_click)
            if v2 is not None and c2 >= 0.66:
                return Grounded(st, v2, c2, "label", f"the manual offers alternatives; '{alt}' exists here")
        if st.action == "type":                                               # text entry into the focused / selected field
            return Grounded(st, None, 1.0, "typed", "text entry (into the focused field)")
        for rx, why in HUMAN_STEP_RX[1:]:
            if rx.search(st.raw or ""):
                return Grounded(st, None, 0.0, "human", why)
        if scope == "choice":
            kid = _first_child(catalog, near)
            if kid is None:
                kid, grp = pick_from_group(catalog, st.target)
                if kid is not None:
                    return Grounded(st, kid, 0.6, "group", f"the manual says 'one from the {st.target}': any item of '{grp}' will do - '{kid.label}' was taken")
            return Grounded(st, kid, 0.6, "choice", why_scope)
        whole = _clean_term(re.sub(r"\*\*", "", re.split(r"\s{2,}|[:.(]", st.raw or "")[0]))
        if whole and fold(whole) != fold(st.target) and len(whole.split()) <= 5:            # 'Select Similar' / 'Toggle Cyclic': the line's words ARE a command's name
            vw, cw = resolve_label_ctx(catalog, whole, near, after_right_click)
            if vw is not None and cw >= 1.0:
                return Grounded(st, vw, 1.0, "label", "the line's words are the name of a command")
        iv, iwhy = icon_noun(catalog, st.raw or "", near)
        if iv is not None:
            return Grounded(st, iv, 0.8, "label", iwhy)
        sv, sc, sp = split_run_together(catalog, st.target, near)
        if sv is not None:
            return Grounded(st, sv, sc, "path", f"'{st.target}' is a menu path whose separators the page lost (icons between the words): {' > '.join(sp)}")
        if after_right_click and st.target:
            from ..harvest import Verb, verb_id
            nv = Verb(verb_id(["Context menu"], st.target), _clean_term(st.target), ["Context menu"], role="menu_item", sources=["guide-context"], safety="safe")
            catalog.verbs.append(nv)
            return Grounded(st, nv, 0.8, "path", f"'{st.target}' is an item of the context menu opened by the previous right-click")
        if fold(st.target) in PLAIN_KEYS:
            return Grounded(st, None, 1.0, "key", f"the {st.target} key (navigation / accelerator)")
        for v in catalog.verbs:
            if len(v.label) >= 3 and (v.label.lower() in st.target.lower() or st.target.lower() in v.label.lower()):
                return Grounded(st, v, 0.8, "label", f"matched catalog verb '{v.label}' in '{st.target}'")
        is_control = (
            st.action in ("on", "off", "toggle") or
            bool(re.search(r"(?i)\b(?:button|checkbox|check box|toggle|switch|slider|dropdown|drop-down|tile|expander|settings?|option|view|tab|icon|control|sidebar|target|command)\b", st.raw or "")) or
            bool(re.search(r"(?i)\b(?:expand|toggle|turn on|turn off|enable|disable|properties|remux|filter sessions|session target|automations|audio input capture|compact conversation|sandboxing|tunnels|sharing settings)\b", st.raw or "")) or
            bool(re.search(r"(?i)^(?:\d+[.)]\s*)?(?:select|click|choose)\s+\*\*([A-Za-z0-9][\w\s&./+-]{0,35})\*\*", st.raw or ""))
        )
        if is_control and len(st.target) >= 2 and not re.search(r"(?i)\b(?:https?|www|\.com|github|srt://)\b", st.target):
            from ..harvest import Verb, verb_id
            from .. import safety
            path = list(st.within) if st.within else (list(near[:1]) if near else [])
            role = "button"
            if st.action in ("on", "off", "toggle") or re.search(r"(?i)\b(?:switch|toggle)\b", st.raw or ""):
                role = "switch"
            elif re.search(r"(?i)\bcheckbox\b", st.raw or ""):
                role = "checkbox"
            nv = Verb(verb_id(path, st.target), _clean_term(st.target), path, role=role, sources=["guide-control"], safety=safety.classify(st.target, " ".join(path)))
            catalog.verbs.append(nv)
            return Grounded(st, nv, 0.8, "label", f"control '{st.target}' named in user guide (to be confirmed on screen)")
        return Grounded(st, None, c, "none", f"the manual says '{st.target}'; no such control is in the application's catalog (it may sit in a menu or dialog that is not open)")
    if not st.target and re.search(r"(?i)\bfrom the \*\*\.\.\.\*\* menu\b", st.raw or ""):
        m_leaf = re.search(r"(?i)\b(?:open|select|choose)\s+\*\*([A-Za-z0-9\s]+)\*\*", st.raw or "")
        if m_leaf:
            from ..harvest import Verb, verb_id
            from .. import safety
            leaf = m_leaf.group(1).strip()
            path = ["..."]
            nv = Verb(verb_id(path, leaf), _clean_term(leaf), path, role="menu_item", sources=["guide-control"], safety=safety.classify(leaf, " ".join(path)))
            catalog.verbs.append(nv)
            return Grounded(st, nv, 0.8, "label", f"control '{leaf}' in '...' menu")
    for rx, why in HUMAN_STEP_RX[1:]:
        if rx.search(st.raw or ""):
            return Grounded(st, None, 0.0, "human", why)
    if scope == "choice":
        return Grounded(st, _first_child(catalog, near), 0.6, "choice", why_scope)
    if not st.bare and st.action == "type":
        return Grounded(st, None, 1.0, "typed", "text entry")
    whole = _clean_term(re.sub(r"\*\*", "", st.raw or ""))
    if whole and len(whole.split()) <= 5:
        v, c = resolve_label_ctx(catalog, whole, near, after_right_click)
        if v is not None and c >= 1.0:
            return Grounded(st, v, 1.0, "label", "the whole list item is the name of a control")
    if st.bare:
        return Grounded(st, None, 0.0, "outside", "a bare list item that names no control (a list of topics / links), not an instruction")
    if st.chord:
        return Grounded(st, None, 0.0, "none", f"the manual names shortcut {st.chord}, which the application never prints on a control: a chord the app does not advertise is not a grounded command")
    return Grounded(st, None, 0.0, "none", "the step names no control")


# a manual names a control by its PICTURE ('the gear icon'): the conventional names of the common symbols (a UI convention across applications, not any one application's list)
ICON_NOUNS = {"gear": ("settings", "options", "preferences"), "cog": ("settings", "options", "preferences"), "cogwheel": ("settings", "options", "preferences"), "magnifying glass": ("search", "find"), "magnifier": ("search", "find"),
              "trash": ("delete", "remove"), "bin": ("delete", "remove"), "pencil": ("edit", "rename"), "pen": ("draw", "edit"), "plus": ("add", "new", "insert"), "+": ("add", "new", "create", "insert"), "+ sign": ("add", "new", "create", "insert"),
              "three dots": ("more options", "more"), "ellipsis": ("more options", "more"), "...": ("more options", "more"), "dots": ("more options", "more"),
              "hamburger": ("menu", "navigation"), "three lines": ("menu", "navigation"), "3 lines": ("menu", "navigation"), "more": ("more options", "more", "customize and control google chrome"),
              "question mark": ("help",), "floppy": ("save",), "bell": ("notifications",), "house": ("home",), "home": ("home",), "printer": ("print",), "paperclip": ("attach",), "star": ("favorites", "favorite"),
              "x": ("close",), "funnel": ("filter",), "eye": ("show", "view"), "lock": ("lock", "protect")}
ICON_RX = re.compile(r"(?i)\b(gear|cogwheel|cog|magnifying glass|magnifier|trash|bin|pencil|pen|plus|three dots|ellipsis|\.\.\.|three lines|3 lines|more|dots|hamburger|question mark|floppy|bell|house|home|printer|paperclip|star|x|funnel|eye|lock)"
                     r"(?:\s+(?:sign|symbol))?\s+(?:icon|button)\b|\b(?:icon|symbol|button) (?:of|with) (?:a |an |the )?(gear|cog|magnifying glass|trash|pencil|plus|three dots|ellipsis|\.\.\.|three lines|3 lines|more|dots|bell|house|printer|funnel|eye|lock)\b")


def icon_noun(catalog: Any, raw: str, near: Sequence[str] = ()) -> Tuple[Any, str]:
    """'Click the gear icon': the control whose NAME is the symbol's conventional meaning (Settings / Options), when the catalog has exactly that. -> (verb, why) or (None, '')."""
    m = ICON_RX.search(re.sub(r"\*\*", "", raw or ""))
    if not m:
        return None, ""
    noun = (m.group(1) or m.group(2) or "").lower()
    for name in ICON_NOUNS.get(noun, ()):
        v, c = resolve_label_ctx(catalog, name, near)
        if v is not None and c >= 1.0 and v.enabled:
            return v, f"the {noun} icon is conventionally '{v.label}'"
        short = [x for x in catalog.verbs if x.enabled and name in fold(x.label).split() and len(fold(x.label).split()) <= 3 and not (x.path and str(x.path[0]).startswith("Context menu"))]
        if short:                                                                  # 'Open settings' for the gear: the symbol's meaning is a whole word of a short label
            v = min(short, key=lambda x: (len(x.label), len(x.path)))
            return v, f"the {noun} icon is conventionally '{name}': '{v.label}'"
    return None, ""


_GROUP_REF_RX = re.compile(r"(?i)\b(?:options?|commands?|buttons?|tools?|settings?)\s+(?:in|from|of)\s+the\s+\**([A-Za-z][\w &]{1,30}?)\**\s+(?:group|section|area|panel)\b")
_PRONOUN_RX = re.compile(r"(?i)^(?:\d+[.)]\s*)?(?:then\s+)?(?:check|uncheck|clear|select|deselect|turn|switch|toggle|enable|disable|click|tap)\s+(?:it|this|that|them|the (?:box|checkbox|check box|option|setting|toggle|switch))\b(?:\s+(?:on|off))?\s*[.,]?\s*$")


_SPLIT_IDX: Dict[str, Any] = {}


def split_run_together(catalog: Any, text: str, near: Sequence[str] = ()) -> Tuple[Any, float, List[str]]:
    """'Bookmarks and lists Bookmark manager' / 'Bookmarks and listsBookmark Manager': a web page drew arrow icons between the levels of a menu path and lost them as text. Every split of
    the words into two or three levels is tried as a path of the catalog; the best exact one wins. -> (verb, confidence, levels) or (None, 0, [])."""
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    words = t.split()
    if not 2 <= len(words) <= 9:
        return None, 0.0, []
    key = (id(catalog), len(catalog.verbs))
    if _SPLIT_IDX.get("key") != key:                                          # the catalog's labels and container names, folded once (a 6,700-command catalog is scanned per call otherwise)
        _SPLIT_IDX.update(key=key, labels={fold(v.label) for v in catalog.verbs}, parts={fold(p) for v in catalog.verbs for p in v.path})
    labels, parts_known = _SPLIT_IDX["labels"], _SPLIT_IDX["parts"]
    cuts: List[List[str]] = [[" ".join(words[:i]), " ".join(words[i:])] for i in range(1, len(words))]
    cuts += [[" ".join(words[:i]), " ".join(words[i:j]), " ".join(words[j:])] for i in range(1, len(words) - 1) for j in range(i + 1, len(words))]
    cuts = [c for c in cuts if fold(c[-1]) in labels and all(fold(p) in parts_known for p in c[:-1])]
    best: Tuple[Any, float, List[str]] = (None, 0.0, [])
    for parts in cuts:
        v, s = resolve_path(catalog, parts, near)
        if v is not None and s >= 0.85 and _words_eq(v.label, parts[-1]) and s > best[1]:
            best = (v, s, parts)
    return best


def resolve_label_ctx(catalog: Any, text: str, near: Sequence[str] = (), ctx_menu: bool = False) -> Tuple[Any, float]:
    """resolve_label, but after a right-click the item of a CONTEXT menu wins, and otherwise a context-menu item never beats a ribbon / menu command of the same name."""
    q = fold(text)
    idx = _label_index(catalog)
    exact = list(idx["fold"].get(q, ())) or list(idx["stem"].get(_stem_key(text), ()))
    if exact:
        nearset = set(near)
        exact.sort(key=lambda v: _rank(v, nearset, ctx_menu))
        return exact[0], 1.0
    return resolve_label(catalog, text, near)


def _child_by_prefix(catalog: Any, parent: str, terms: Sequence[str]) -> Any:
    """The item of `parent`'s menu whose name is one of `terms` or starts with it as whole words ('PNG' -> 'PNG picture')."""
    for t in terms:
        ft = fold(t or "")
        if len(ft) < 2:
            continue
        for v in catalog.verbs:
            if v.path and fold(v.path[-1]) == parent and v.enabled and (fold(v.label) == ft or fold(v.label).startswith(ft + " ")):
                return v
    return None


def _first_child(catalog: Any, near: Sequence[str]) -> Any:
    """The first plain item under the control the previous step used (its gallery / menu / dialog), or None (the executor then picks among what is open on screen)."""
    if not near:
        return None
    name = near[0]                                                            # the items of the previous step's OWN control (its menu / gallery); a container's other controls are no 'option'
    kids = [v for v in catalog.verbs if v.path and fold(v.path[-1]) == name and v.enabled and v.safety == "safe" and not v.leads_to and fold(v.label) != name]
    return kids[0] if kids else None


def ground(steps: Sequence[GuideStep], catalog: Any, app_words: Sequence[str] = ()) -> List[Grounded]:
    out: List[Grounded] = []
    near: Tuple[str, ...] = ()
    rc = False
    opener = False
    elsewhere = ""
    prev_verb: Any = None
    for s in steps:
        g = ground_step(s, catalog, near, app_words, rc, opener)
        raw = re.sub(r"\*\*", "", s.raw or "")
        if g.how in ("none", "choice") and g.verb is None and prev_verb is not None and _PRONOUN_RX.match(raw):
            g = Grounded(s, prev_verb, 0.8, "label", f"'{raw[:30]}' refers back to '{prev_verb.label}' (the control the previous step named)")      # 'If it's checked, uncheck it.'
        elif g.how == "none" and g.verb is None:
            gm = _GROUP_REF_RX.search(raw)
            if gm:
                gv, grp = pick_from_group(catalog, gm.group(1))
                if gv is not None:
                    g = Grounded(s, gv, 0.6, "group", f"'options in the {gm.group(1)} group': any item of '{grp}' will do - '{gv.label}' was taken")
        if g.verb is not None:
            prev_verb = g.verb
        if g.how == "outside" and "another program" in (g.note or ""):
            elsewhere = (s.raw or "")[:60]                                      # the procedure has moved into another program (the registry editor, the control panel ...)
        elif elsewhere and g.how not in GROUNDED_HOW and not any(w and w.lower() in (s.raw or "").lower() for w in app_words):
            g = Grounded(s, None, 0.0, "outside", f"continues in the other program the procedure opened ('{elsewhere}')")   # ...its next steps happen there, not in this application
        elif g.how in ("path", "label", "chord", "group"):
            elsewhere = ""
        out.append(g)
        rc = s.action == "right_click"
        opener = bool(g.verb is not None and ("menu" in (g.verb.leads_to or "") or g.verb.role in ("dropdown",)))      # the next 'select the type you want' picks inside what this opened
        if g.verb is not None:
            near = near_of(g.verb)
    return out


def coverage(grounded: Sequence[Grounded]) -> Tuple[int, int]:
    """(grounded, applicable): steps that are not about this application ('outside') are left out of both."""
    app = [g for g in grounded if g.how not in EXCLUDED_HOW]
    return sum(1 for g in app if g.how in GROUNDED_HOW), len(app)


# ----------------------------------------------------------------------------------------------------------------- plan
def plan_from_guide(goal: str, catalog: Any, index: Any, app_key: str, brain: Any = None, k: int = 4, min_cover: float = 0.6, exclude_cites: Sequence[str] = (),
                    app_words: Sequence[str] = (), relevant: Any = None) -> Optional[Dict[str, Any]]:
    """The best-grounded procedure for `goal` found in the application's indexed guide, or None. Returns {steps: [Grounded], cite, source, coverage, unknown: [...], passage_score, trail}."""
    if index is None:
        return None
    try:
        if app_key not in index.apps():
            return None
        res = index.retrieve(goal, app_key, k, brain)
    except Exception:
        return None
    best: Optional[Dict[str, Any]] = None
    for p in res.get("passages", []):
        if p.cite in exclude_cites or (relevant is not None and not relevant(p.cite, p.text)):
            continue
        steps = parse_steps(p.text, p.cite)
        if not steps:
            continue
        g = ground(steps, catalog, app_words)
        ok = [x for x in g if x.how in GROUNDED_HOW]
        n_ok, n_app = coverage(g)
        if not n_app:
            continue
        cover = n_ok / n_app
        if not ok or cover < min_cover:
            continue
        mean = sum(x.conf for x in ok) / len(ok)
        key = (round(cover, 3), round(mean, 3), p.score)
        if best is None or key > best["_key"]:
            best = {"_key": key, "steps": g, "cite": p.cite, "source": p.source, "coverage": round(cover, 3), "mean_conf": round(mean, 3), "text": p.text,
                    "unknown": [x.note or x.step.raw for x in g if x.how not in GROUNDED_HOW], "passage_score": p.score, "trail": res.get("trail", [])}
    if best:
        best.pop("_key", None)
    return best
