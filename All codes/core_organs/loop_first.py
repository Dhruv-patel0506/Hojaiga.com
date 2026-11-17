"""
loop_first.py -- route the product through the VERIFIED desktop autonomy loop before the ReAct crew runs.

Why this exists
    The crew (organ_01_crewai_engine) lets a 7B model pick tools freely; its judge accuracy on real apps
    is 50-67%. The tested, deterministic capability is desktop_grounding.operate_app (perceive -> decide ->
    act -> verify). This module is the bridge: it turns the user's command into per-app micro-goals
    (with postconditions where the words themselves carry one), runs operate_app for each detected desktop
    app IN ORDER, and returns an honest report that the crew receives as evidence instead of having to
    rediscover it.

Rules this module keeps
    * Only sequencing. There is NO clipboard / data hand-off between apps; each app's final hwnd and step
      trace are recorded (APP_HANDLES) so a later stage can reference them, nothing more.
    * awaiting_human from any app STOPS the sequence (later apps are not started) and surfaces the capsule.
    * A goal whose only postcondition is the generic "something in the UI changed" is labelled WEAK in the
      evidence; it can never be presented as a verified outcome.
    * Browser targets stay with the CDP pre-navigation in organ_01; canvas drawing stays with the Draw tools
      (they cannot be expressed as element-level goals). Both are reported as delegated, not as done.
    * HOJAIGA_LOOP_FIRST=0 switches the whole pass off (default "1") so pure-ReAct stays reachable for bisection.
    * No app names live here: segmentation uses the command's own words and the positions the compiler found.
"""

from __future__ import annotations

import ast
import json
import logging
import operator
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("hojaiga.loop_first")

# Browsers are driven through Organ 19 CDP (pre-navigation), never through element-level desktop goals.
BROWSER_APPS = frozenset({"google chrome", "chrome", "microsoft edge", "edge", "browser", "firefox", "brave",
                          "opera", "vivaldi"})

# Generic imperative verbs. They only decide WHERE a clause may be split into goals; they say nothing about
# any particular app.
_ACTION_VERBS = (
    "type", "write", "enter", "input", "save", "press", "click", "tap", "select", "choose", "set", "add", "insert",
    "copy", "paste", "cut", "open", "close", "search", "find", "calculate", "compute", "multiply", "divide",
    "subtract", "sum", "draw", "sketch", "paint", "rename", "create", "make", "play", "pause", "record", "stop",
    "export", "import", "print", "scroll", "zoom", "toggle", "turn", "check", "uncheck", "expand", "collapse",
    "navigate", "go", "read", "show", "hide", "undo", "redo", "format", "bold", "underline", "italicize",
    # irreversible verbs MUST be goals of their own so the risk gate (task_lifecycle D3) can see and queue them
    "delete", "remove", "erase", "send", "submit", "publish", "post", "pay", "buy", "purchase", "uninstall",
    "overwrite", "clear", "reset", "quit", "exit",
)
_VERB_ALT = "|".join(sorted(_ACTION_VERBS, key=len, reverse=True))

# Sequence boundaries between clauses of one command.
_BOUNDARY_RE = re.compile(
    r"(?:\s*;\s*|\.(?=\s|$)\s*|,?\s+and\s+then\s+|,?\s+then\s+|,?\s+after\s+that\s+|,?\s+afterwards\s+|,?\s+next\s*,?\s+"
    r"|,?\s+and\s+(?=(?:then\s+)?(?:open|launch|start|run|switch\s+to)\b)|,\s+(?=(?:open|launch|start|switch\s+to)\b))",
    re.I)

_DRAW_CUES = re.compile(r"\b(?:draw|sketch|doodle|trace|paint\s+(?:a|an|the|some)\b)", re.I)
_ARITH_RE = re.compile(r"(\d+(?:\.\d+)?(?:\s*[\+\-\*\/xX]\s*\d+(?:\.\d+)?)+)")
_COMPOSE_CUES = re.compile(r"\b(?:a|an|some|about|poem|haiku|story|summary|essay|paragraph|email|letter|joke|"
                           r"sentence|note|list|description|caption|slogan|quote)\b", re.I)
_PATH_RE = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/][^\s'\"<>|?*]+")          # a drive letter, not the 's:/' inside 'https://'
_URL_RE = re.compile(r"https?://[^\s'\"<>]*[^\s'\"<>.,;:!?)]", re.I)                    # a sentence's comma / full stop is not part of the address


def loop_first_enabled() -> bool:
    return os.environ.get("HOJAIGA_LOOP_FIRST", "1").strip().lower() not in ("0", "false", "no", "off")


def is_browser_app(app: str) -> bool:
    low = (app or "").lower()
    return low in BROWSER_APPS or any(b in low for b in ("chrome", "edge", "firefox", "browser"))


# ---------------------------------------------------------------------------------------------- planning

@dataclass
class AppPlan:
    app: str
    goals: List[str] = field(default_factory=list)
    expect_map: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    strength: List[str] = field(default_factory=list)       # per goal: "strong" | "weak"
    delegated: List[str] = field(default_factory=list)      # clauses left to other machinery (drawing)
    notes: List[str] = field(default_factory=list)
    clauses: List[str] = field(default_factory=list)        # the raw clause text assigned to this app
    steps: List[Dict[str, str]] = field(default_factory=list)   # the model's structured steps (refine_plan); goals[i] renders steps[i]

    def as_dict(self) -> Dict[str, Any]:
        return {"app": self.app, "goals": list(self.goals), "expect_map": {str(k): v for k, v in self.expect_map.items()},
                "strength": list(self.strength), "delegated": list(self.delegated), "notes": list(self.notes), "steps": list(self.steps)}


# ---------------------------------------------------------------------------------------------- the model plans the steps
# Live Oct-27: the word split kept 'type Item in A1 and Price in B1, Milk in A2 and 40 in B2' as ONE goal (the whole sentence went into A1), a
# 'slide titled X' was never typed, and Notepad typed into an old restored tab. The model now reads the clause and writes one structured step per
# action; the code checks that every value of the clause survived and renders each step as a goal the loop already understands.
STEP_KINDS = ("open_file", "new_document", "type", "click", "press", "select", "format", "add_slide", "draw", "save_as", "read", "insert_table", "insert_picture", "paste")
STEP_SYSTEM = ("You break one instruction for the desktop app APP into the smallest steps, each ONE action. Step kinds:\n"
               "open_file: open an existing file; 'text' = its full path\n"
               "new_document: start a new empty document (use it first when the task makes a new file, so old content is never edited)\n"
               "type: type text exactly as given; 'target' = where (a cell like A1, 'title', a field name) or ''\n"
               "click: press a visible button, menu item or tab; 'target' = its name\n"
               "press: a key or shortcut; 'text' = e.g. Ctrl+B, Enter, F12\n"
               "select: select a cell, text or item; 'target' = it\n"
               "format: apply formatting; 'text' = the words to format, 'format' = bold / italic / underline / a colour / a size\n"
               "add_slide: add a new slide (presentations)\n"
               "draw: draw something by hand on the canvas; 'text' = what to draw with its colour and shape\n"
               "save_as: save; 'text' = the full path exactly as given\n"
               "read: take data to use later; 'text' = where from (a web address, or '' for this document), 'target' = what (table, text, a range like A1:C9, "
               "words naming the table), 'format' = a short name to keep it under\n"
               "insert_table: put a table kept earlier into this document; 'text' = its name, 'target' = where (a cell like A1, or '')\n"
               "insert_picture: put a picture file into this document; 'text' = its path or the name it was kept under\n"
               "paste: type text kept earlier; 'text' = its name\n"
               "Copy every text, value, cell and path exactly. One value per type step; never split a text and never type the instruction's own words (and, then). "
               "Opening the app is already done.\n"
               "Use the step kinds themselves instead of clicking menus for them: save_as is ONE step (no File / Save / Save As / file-name steps around it), "
               "add_slide adds a slide, format formats, new_document starts a document.\n"
               "When a drawing names a colour or a tool, a click step choosing it comes first (target = the colour or tool's name).\n"
               "Reply JSON only: {\"steps\": [{\"do\": \"...\", \"text\": \"...\", \"target\": \"...\", \"format\": \"...\"}]}")


def app_commands(app: str, text: str, limit: int = 12) -> str:
    """The commands this app is KNOWN to have for this clause (static harvest + live scans + explorations, ranked by the command registry, no model):
    the planner names real buttons ('Red', 'New Slide') instead of guessing."""
    try:
        from core_organs import command_registry as CR
        from core_organs import organ_48_app_behavior_model as BM
        rows = CR.lookup(BM.get_model(), app.lower(), text, limit=limit)
    except Exception:
        return ""
    lines = []
    for r in rows:
        if r.get("api"):
            continue
        lines.append(f"- {r['name']}" + (f" [{r['shortcut']}]" if r.get("shortcut") else "") + (f" ({r['menu_path'][-60:]})" if r.get("menu_path") else ""))
    return "\n".join(dict.fromkeys(lines))


def _ask_planner(system: str, prompt: str) -> Optional[str]:
    try:
        from core_organs.mind import app_qa as QA
        return QA.ask_llm(prompt, system, timeout=120, model=os.environ.get("HOJAIGA_STEP_MODEL", ""), max_tokens=900, json_mode=True)
    except Exception:
        return None


def _values_of(text: str) -> List[str]:
    """What must survive planning: quoted text, numbers, cell addresses, paths."""
    t = _PATH_RE.sub(" ", text)
    vals = [q.strip("\"“”'") for q in re.findall(r"(\"[^\"]+\"|“[^”]+”)", t)]
    t = _URL_RE.sub(" ", t)
    vals += re.findall(r"\b[A-Z]{1,2}\d{1,5}\b", t) + re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", t) + _PATH_RE.findall(text) + _URL_RE.findall(text)
    return [v for v in vals if v]


def render_step(s: Dict[str, str]) -> str:
    """A structured step as the goal sentence the verified loop already understands."""
    do, text, target, fmt = s.get("do", ""), s.get("text", ""), s.get("target", ""), s.get("format", "")
    if do == "type":
        return f'type "{text}"' + (f" in {target}" if target else "")
    if do == "click":
        return f"click {target or text}"
    if do == "press":
        return f"press {text or target}"
    if do == "select":
        return f"select {target or text}"
    if do == "format":
        return f"make \"{text}\" {fmt}".strip()
    if do == "add_slide":
        return "add a new slide"
    if do == "new_document":
        return "create a new blank document"
    if do == "open_file":
        return f"open the file {text}"
    if do == "draw":
        return f"draw {text}"
    if do == "save_as":
        return f"save it as {text}"
    if do == "read":
        return f"read the {target or 'content'}" + (f" from {text}" if text else "") + (f" as {fmt}" if fmt else "")
    if do == "insert_table":
        return f"insert the table {text}" + (f" at {target}" if target else "")
    if do == "insert_picture":
        return f"insert the picture {text}"
    if do == "paste":
        return f"paste {text}"
    return text


_SAVE_UI = re.compile(r"^(?:file|save|save as\.*|save as\b.*|browse|file name:?|ok|enter|ctrl\+s|f12|this pc|auto ?save|automatically save|save (?:it|now|file|document|the \w+))$", re.I)
def _bare(label: str) -> str:
    """A control label without its shortcut hint: 'Save [Ctrl+S]' / 'Save (Ctrl+S)' -> 'Save' (live Nov-02: the hint hid a save click from the save filter)."""
    return re.sub(r"\s*[\[(][^\])]*[\])]\s*$", "", (label or "").strip()).strip()


_GLUE = re.compile(r"^\W*(?:and|then|also|,|;|\.)?\W*$", re.I)


def tidy_steps(steps: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """What a 7B planner adds around the step kinds (measured): a path typed into a 'File name' box instead of save_as, the menu clicks that lead
    there, and a connective typed as text (' and'). One save_as replaces the menu walk; connectives are dropped."""
    out: List[Dict[str, str]] = []
    for s in steps:
        if s["do"] == "type" and _PATH_RE.fullmatch(s["text"].strip()):
            s = {"do": "save_as", "text": s["text"].strip(), "target": "", "format": ""}
        if s["do"] == "type" and _GLUE.match(s["text"]):
            continue
        if s["do"] == "type" and s["target"].strip().lower().replace(" ", "_") in STEP_KINDS:          # (a CLICK on 'Format' is Notepad's real menu)
            continue                                                                                  # 'type "cities" in read': a step name used as a place (live Oct-28: the word landed on a slide)
        out.append(s)
    out = [s for s in out if not (s["do"] in ("click", "select") and not (s["target"] or s["text"]).strip())]   # a click on nothing (live Oct-28: it sent a Word plan to the slow window route)
    if not any(s["do"] in ("type", "save_as", "insert_table", "insert_picture", "paste", "draw") for s in out):
        out = [s for s in out if s["do"] != "new_document"]                                           # nothing is written into a document: no new one (live Nov-02: Calculator was given 'create a new blank document')
    if any(s["do"] == "save_as" for s in out):
        out = [s for s in out if not (s["do"] in ("click", "press", "select") and _SAVE_UI.match(_bare(s["target"] or s["text"])))]
    out = [s for k, s in enumerate(out) if not (s["do"] == "select" and k + 1 < len(out) and out[k + 1]["do"] == "read"
                                                and (s["target"] or s["text"]).strip().lower() in (out[k + 1]["target"] + " " + out[k + 1]["text"]).lower())]   # a read takes its range itself
    seen_save = set()
    return [s for s in out if not (s["do"] == "save_as" and (s["text"] in seen_save or seen_save.add(s["text"])))]


_COLOURS = ("red", "blue", "green", "yellow", "orange", "purple", "pink", "black", "white", "brown", "grey", "gray")


def complete_steps(steps: List[Dict[str, str]], text: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """What the clause's own words require and the 7B planner leaves out even when told (measured 3/3 runs): the formatting a clause names
    ('make it bold'), the colour a drawing names ('a red circle'), and a fresh document when text is typed into a file that is saved new (Notepad
    typed into an old restored tab). Added from the clause's words, never invented."""
    added: List[str] = []
    out = list(steps)
    fmt_words = "|".join(_FORMAT_WORDS + _COLOURS)
    tail = re.compile(rf"\s*,?\s*(?:in|as|and make it|and|,)?\s*(?:{fmt_words})(?:\s+(?:text|font|letters))?\s*$", re.I)
    for s in out:                                                                                     # live Oct-28: 'write the title Largest cities in bold' typed 'Largest cities in bold'
        if s["do"] in ("type", "format") and s["text"] and not _PATH_RE.search(s["text"]):
            m = tail.search(s["text"])
            word = m.group(0).strip(" ,").split()[-1].lower() if m else ""
            if word in _COLOURS and not any(word in (o["format"] + " " + o["target"]).lower() for o in out if o is not s and o["do"] in ("format", "click")):
                continue                                                                              # a colour no step carries stays in the words rather than being lost
            if m and m.start() > 0 and re.search(rf"\b{re.escape(m.group(0).strip(' ,').split()[-1])}\b", text, re.I) \
                    and not re.search(re.escape(s["text"].strip()) + r"\s*['\"]", text):              # a quoted text keeps every word: "type 'Feeling blue'"
                s["text"] = s["text"][:m.start()].rstrip(" ,")
                added.append("format words taken out of the text")
    # a font name / point size the words give ('in Cascadia Code Light font, 36 pt', 'use the font 'Arial' with size 36'): typed as text by the planner (live Nov-02:
    # Word typed "'Automation Practice' in Cascadia Code Light font, 36 pt"); it is a format of the typed text, and the text is what the quotes hold
    quoted = [q.strip("\"'“”‘’") for q in re.findall(r"(\"[^\"]+\"|“[^”]+”|(?<!\w)'[^']+'(?!\w))", text)]
    for s in out:
        if s["do"] == "type" and not _PATH_RE.search(s["text"]):
            q = next((q for q in quoted if q and s["text"].strip().strip("\"'").startswith(q) and len(s["text"].strip().strip("\"'")) > len(q) + 2), "")
            if q:
                s["text"] = q
                added.append("only the quoted text is typed")
    fname = (re.search(r"\bfont\s+(?:to\s+|name\s+)?['\"]([^'\"]{2,40})['\"]", text, re.I)
             or re.search(r"\b(?:in|use|using|with|to)\s+(?:the\s+)?['\"]?([A-Z][\w\-]*(?:\s+[A-Z0-9][\w\-()]*){0,5})['\"]?\s+font\b", text)
             or re.search(r"\bfont\s+(?:to\s+)?['\"]?([A-Z][\w\-]*(?:\s+[A-Z0-9][\w\-()]*){0,5})['\"]?", text))
    fsize = re.search(r"\b(\d{1,3})\s*(?:pt|point)s?\b|\b(?:font\s+)?size\s+(?:to\s+|of\s+)?(\d{1,3})\b", text, re.I)
    lone = [s for s in out if s["do"] == "press" and (s["text"] or s["target"]).strip().lower() in ("enter", "return", "tab", "escape", "esc")
            and not re.search(rf"\b{re.escape((s['text'] or s['target']).strip())}\b", text, re.I)]
    if lone:                                                                                          # a key the words never name is the planner's habit (live Nov-02: 'press Enter'
        out = [s for s in out if s not in lone]                                                       # after Calculator's '=' changed nothing, so the step failed and blocked the run)
        added.append(f"dropped {len(lone)} key press the task does not ask for")
    typed = [s for s in out if s["do"] == "type" and not _PATH_RE.search(s["text"])]
    want =", ".join(x for x in ((f"font {fname.group(1).strip()}" if fname else ""), (f"{fsize.group(1) or fsize.group(2)} pt" if fsize else "")) if x)
    if want and typed and not any(s["do"] == "format" and (("font" in s["format"].lower()) == bool(fname)) and (("pt" in s["format"].lower() or "size" in s["format"].lower()) == bool(fsize)) for s in out):
        out = [s for s in out if not (s["do"] in ("click", "select") and fname and fname.group(1).strip().lower() == (s["target"] or s["text"]).strip().lower())]
        out.insert(out.index(typed[-1]) + 1, {"do": "format", "text": typed[-1]["text"], "target": typed[-1]["target"], "format": want})
        added.append(f"format {want}")
    carried = " | ".join(s["format"].lower() for s in out if s["do"] == "format")
    echoes = [s for s in out if s["do"] in ("click", "select") and (s["target"] or s["text"]).strip() and (s["target"] or s["text"]).strip().lower() in carried]
    if echoes:                                                                                        # 'click 36 pt' next to a format step that sets 36 pt (live Nov-02: that one click
        out = [s for s in out if s not in echoes]                                                     # sent the whole Word plan off the object model to the window route)
        added.append(f"dropped {len(echoes)} click that repeats a format step")
    for w in _FORMAT_WORDS:
        if re.search(rf"\b{w}\b", text, re.I) and typed and not any(w in (s["format"] + s["text"] + s["target"]).lower() for s in out if s["do"] in ("format", "press", "click")):
            at = out.index(typed[-1]) + 1
            out.insert(at, {"do": "format", "text": typed[-1]["text"], "target": typed[-1]["target"], "format": w})
            added.append(f"format {w}")
    if any(s["do"] == "draw" for s in out):                                                          # a colour moved into a 'format' step ('make Red fill') is the colour to pick before drawing
        out = [s for s in out if not (s["do"] == "format" and s["text"].strip().lower() in _COLOURS)]
    for i, s in enumerate(list(out)):
        if s["do"] == "draw":
            col = next((c for c in _COLOURS if re.search(rf"\b{c}\b", s["text"] + " " + text, re.I)), "")
            prev = out[out.index(s) - 1] if out.index(s) > 0 else {}
            if col and not (prev.get("do") == "click" and col in (prev.get("target", "") + prev.get("text", "")).lower()):
                out.insert(out.index(s), {"do": "click", "text": "", "target": col.capitalize(), "format": ""})
                added.append(f"choose {col}")
    keys = {"bold": "ctrl+b", "italic": "ctrl+i", "underline": "ctrl+u"}
    fmts = {w for s in out if s["do"] == "format" for w in keys if w in s["format"].lower()}
    toggles = [s for s in out if s["do"] in ("press", "click") and any((s["text"] + s["target"]).lower().replace(" ", "") in (keys[w], w) for w in fmts)]
    if toggles:                                                                                       # a format step already does it (and is read back); the same key again would toggle it OFF
        out = [s for s in out if s not in toggles]
        added.append(f"dropped {len(toggles)} repeat of a format")
    targets = {s["text"].strip().lower() for s in out if s["do"] == "save_as"}
    ghosts = [s for s in out if s["do"] == "open_file" and s["text"].strip().lower() in targets and not os.path.isfile(s["text"].strip().strip("\"'"))]   # a missing file that is NOT the save target stays: its step fails honestly
    if ghosts:                                                                                        # live Oct-28: the planner 'opened' prices.xlsx, the file the task was about to SAVE
        out = [s for s in out if s not in ghosts]
        added.append(f"dropped {len(ghosts)} open of a file that does not exist yet")
    for m in re.finditer(r"\b(?:save|saved|store|export)\w*\b(?:\s+\w+){0,4}?\s+(?:as|to|in(?:to)?)\s+", text, re.I):
        pm = _PATH_RE.match(text, m.end())
        if pm and not any(s["do"] == "save_as" and s["text"].strip().lower() == pm.group(0).strip().lower() for s in out):
            # the words say where to save and the plan has no such save (live Oct-28: 'click Automatically Save' came instead, the plan left the object model,
            # and the window route typed into another open document): the save the words name is added and save-ish clicks go
            out = [s for s in out if not (s["do"] in ("click", "press", "select") and _SAVE_UI.match(_bare(s["target"] or s["text"])))]
            out.append({"do": "save_as", "text": pm.group(0).strip(), "target": "", "format": ""})
            added.append("save as the named file")
    saves = [s for s in out if s["do"] == "save_as"]
    if saves and out and out[0]["do"] == "type" and not any(s["do"] == "new_document" for s in out) and not os.path.exists(_PATH_RE.search(saves[0]["text"]).group(0) if _PATH_RE.search(saves[0]["text"]) else "x"):
        out.insert(0, {"do": "new_document", "text": "", "target": "", "format": ""})
        added.append("new document first")
    return out, added


def model_steps(clauses: List[str], app: str, ask: Optional[Callable[[str, str], Optional[str]]] = None, context: str = "") -> Tuple[List[Dict[str, str]], str]:
    """(steps, note). [] when the model gave nothing usable or dropped a value of the clause (then the word split stays)."""
    text = " ; ".join(c.strip() for c in clauses if c and c.strip())
    if not text:
        return [], ""
    paths = {f"PATH{i + 1}": p for i, p in enumerate(dict.fromkeys(_PATH_RE.findall(text)))}            # a Windows path inside JSON breaks it ('\n' in D:\new...): the model sees a name for it
    shown = text
    for k, p in paths.items():
        shown = shown.replace(p, k)
    note = ""
    known = app_commands(app, shown) if ask is None else ""
    for _attempt in range(2):                                                                         # one retry, told what was wrong with the first answer
        prompt = (f"Kept by the apps before this one (use these names in read / insert / paste steps):\n{context}\n" if context else "") + \
                 (f"Commands {app} is known to have (from scanning it; use these exact names in click steps):\n{known}\n" if known else "") + \
                 f"Instruction: \"{shown}\"\n" + (f"Your previous answer was not usable: {note}. Answer again.\n" if note else "") + "JSON:"
        steps, note = _parse_steps((ask or _ask_planner)(STEP_SYSTEM.replace("APP", app), prompt) or "", paths, text)
        if steps:
            return steps, note
    return [], note


_FORMAT_WORDS = ("bold", "italic", "underline")
# the names a 7B planner uses for the step kinds it was given (measured: 'save' for save_as)
_STEP_ALIASES = {"open_document": "open_file", "open_workbook": "open_file", "load": "open_file", "save": "save_as", "saveas": "save_as", "export": "save_as", "write": "type", "enter": "type", "input": "type", "new": "new_document",
                 "new_file": "new_document", "insert_image": "insert_picture", "add_picture": "insert_picture", "add_image": "insert_picture",
                 "insert_photo": "insert_picture", "new_slide": "add_slide", "copy": "read", "get": "read", "extract": "read", "sketch": "draw"}


def _parse_steps(raw: str, paths: Dict[str, str], text: str) -> Tuple[List[Dict[str, str]], str]:
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return [], "it was not one JSON object"
    for s in d.get("steps") or []:
        if isinstance(s, dict):
            for k in ("text", "target"):
                for name, p in paths.items():
                    if isinstance(s.get(k), str) and name in s[k]:
                        s[k] = s[k].replace(name, p)
    steps = []
    for s in d.get("steps") or []:
        if not isinstance(s, dict):
            continue
        do = str(s.get("do") or "").strip().lower().replace(" ", "_")
        do = _STEP_ALIASES.get(do, do)
        if do not in STEP_KINDS:
            return [], f"the planner used an unknown step '{do}'"
        st = {k: str(s.get(k) or "").strip() for k in ("text", "target", "format")}
        if do == "open_file" and not st["text"]:
            continue                                                                                  # an 'open' naming no file is noise, not a reason to throw the whole plan away (live Oct-28)
        if do in ("type", "draw", "save_as", "press", "insert_table", "insert_picture", "paste") and not st["text"]:
            return [], f"a '{do}' step had no text"
        steps.append({"do": do, **st})
    steps, added = complete_steps(tidy_steps(steps), text)
    if not steps:
        return [], "the planner gave no steps"
    blob = " ".join(v for s in steps for v in s.values())
    lost = [v for v in _values_of(text) if v not in blob]
    lost += [w for w in _FORMAT_WORDS if re.search(rf"\b{w}\b", text, re.I) and not any(s["do"] in ("format", "press", "click") and w in (s["format"] + s["text"] + s["target"]).lower() for s in steps)]
    if lost:
        return [], f"the steps left out {lost[:4]}"
    return steps, f"model plan: {len(steps)} step(s)" + (f" (+ from the words: {', '.join(added)})" if added else "")


def refine_plan(plan: AppPlan, ask: Optional[Callable[[str, str], Optional[str]]] = None, context: str = "") -> AppPlan:
    """The model's steps replace the word split when they keep every value; each step becomes a goal with its own postcondition.
    A plan whose words already carry an exact result check (arithmetic: each key pressed, the answer must show) is kept as it is."""
    if any("name_visible" in e for e in plan.expect_map.values()):
        plan.notes.append("kept the arithmetic plan: its result is checked on screen")
        return plan
    steps, note = model_steps(plan.clauses or plan.goals, plan.app, ask, context)
    if note:
        plan.notes.append(note)
    if not steps:
        return plan
    kept_from = {t.lower(): a.lower() for t, a in re.findall(r"table '([^']+)'[^\n]*? from ([\w .\-]+)", context or "")}
    kept_tables = set(kept_from) | {t.lower() for t in re.findall(r"table '([^']+)'", context or "")}
    for s in steps:                                                                                   # paste / click / select on a kept TABLE's name is an insert_table: Oct-28 plans walked
        name = (s["text"] or s["target"]).strip().lower() if s["do"] == "paste" else (s["target"] or s["text"]).strip().lower()   # 'Insert > Table > paste' and 'Insert > Table > click cities'
        name = re.sub(r"^(?:the|that|this)\s+|\s+table$", "", name)
        moved = s["do"] == "read" and kept_from.get(name, plan.app.lower()) != plan.app.lower()     # 'read the cities' in PowerPoint, the table Excel kept: it is brought IN here
        if (s["do"] in ("paste", "click", "select") or moved) and name in kept_tables:
            s.update(do="insert_table", text=name, target="")
    seen_ins: set = set()
    steps = [s for s in steps if not (s["do"] in ("insert_table", "insert_picture") and ((s["do"], s["text"].strip().lower()) in seen_ins or seen_ins.add((s["do"], s["text"].strip().lower()))))]   # live Oct-28: two copies of one table on a slide
    with _suppress():
        from core_organs import office_om as _OM
        if _OM.kind_for_app(plan.app):                                                                 # live Oct-28: 'click Title Slide', 'click Insert' sent a PowerPoint plan to the clicking route
            is_cell = lambda s: re.fullmatch(r"\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?", (s["target"] or s["text"]).strip())
            nav, follower = [], False
            for k in range(len(steps) - 1, -1, -1):                                                   # a RUN of menu clicks ('click Insert', 'click Table') before a step that does the job
                s = steps[k]
                if s["do"] in ("click", "select") and not is_cell(s):
                    if follower:
                        nav.append(k)
                else:
                    follower = s["do"] in ("add_slide", "insert_table", "insert_picture", "type", "format", "new_document", "paste")
            if nav:
                steps = [s for k, s in enumerate(steps) if k not in nav]
                plan.notes.append(f"dropped {len(nav)} menu click(s) before a step that does the job itself")
    plan.steps = steps
    plan.goals = [render_step(s) for s in steps]
    plan.delegated = []
    plan.expect_map, plan.strength = {}, []
    for i, s in enumerate(steps):
        if s["do"] == "save_as" and _PATH_RE.search(s["text"]):
            plan.expect_map[i] = {"file_created": _PATH_RE.search(s["text"]).group(0)}
        plan.strength.append("strong" if s["do"] in ("type", "save_as", "draw") else "weak")
    return plan


def _protect_quotes(text: str) -> Tuple[str, Dict[str, str]]:
    """Quoted payloads may contain commas / 'and' / 'then'; hide them while the clause is split."""
    vault: Dict[str, str] = {}

    def _hide(m: "re.Match[str]") -> str:
        key = f"\x00Q{len(vault)}\x00"
        vault[key] = m.group(0)
        return key
    return re.sub(r"(\"[^\"]*\"|“[^”]*”|'[^']{2,}')", _hide, text), vault


def _restore_quotes(text: str, vault: Dict[str, str]) -> str:
    for k, v in vault.items():
        text = text.replace(k, v)
    return text


def _shield_same_length(text: str) -> str:
    """Blank out quoted payloads WITHOUT changing offsets (compiler positions index the original command)."""
    return re.sub(r"(\"[^\"]*\"|“[^”]*”|'[^']{2,}')", lambda m: "\x01" * len(m.group(0)), text)


def _clause_spans(text: str) -> List[Tuple[int, int]]:
    spans, pos = [], 0
    for m in _BOUNDARY_RE.finditer(text):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _surface_word(command: str, pos: int) -> str:
    m = re.match(r"[A-Za-z0-9+_\-]+", command[pos:pos + 40] or "")
    return m.group(0) if m else ""


def _mention_variants(app: str, command: str, pos: int) -> List[str]:
    """Regex fragments that name `app` inside the command: the normalized name, the word the user actually
    wrote at the compiler's detected position, and each word of a multi-word name."""
    raw = {app.strip(), _surface_word(command, pos)}
    raw.update(w for w in re.findall(r"[A-Za-z0-9+_\-]+", app) if len(w) >= 4)
    out = [re.escape(v).replace(r"\ ", r"\s+") for v in sorted((r for r in raw if r), key=len, reverse=True)]
    return out


def _strip_app_phrases(text: str, mentions: List[str]) -> str:
    t = text
    for m in mentions:
        t = re.sub(rf"\b(?:open|launch|start|run|switch\s+to|go\s+to|use)\s+(?:the\s+)?{m}(?:\s+(?:app|application|window|program))?\b\s*(?:,|and\b|then\b)?\s*",
                   " ", t, flags=re.I)
        t = re.sub(rf"\b(?:in|into|on|inside|using|with|within)\s+(?:the\s+)?{m}(?:\s+(?:app|application|window|program))?\b",
                   " ", t, flags=re.I)
        t = re.sub(rf"\b{m}\b", " ", t, flags=re.I)
    for _ in range(3):
        t = re.sub(r"^\s*(?:and|then|also|next|after that|afterwards|,)\s+", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" ,.;")


def _split_goals(text: str) -> List[str]:
    """Split one cleaned clause into micro-goals at a comma / 'and' / 'then' that is followed by a verb."""
    if not text:
        return []
    shielded, vault = _protect_quotes(text)
    parts = re.split(rf"\s*(?:,|;|\band\b|\bthen\b)\s*(?=(?:{_VERB_ALT})\b)", shielded, flags=re.I)
    return [_restore_quotes(p, vault).strip(" ,.;") for p in parts if p and p.strip(" ,.;")]


def _safe_eval(expr: str) -> Optional[float]:
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.USub: operator.neg}

    def ev(n: "ast.AST") -> float:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.operand))
        raise ValueError("unsupported")
    try:
        return ev(ast.parse(expr.replace("x", "*").replace("X", "*"), mode="eval"))
    except Exception:
        return None


def _arith_goals(expr: str) -> Tuple[List[str], Optional[str]]:
    """Button-press goals for an arithmetic expression, using the generic UI vocabulary shared with
    task_runner ('5' -> Five, '*' -> Multiply by, '=' -> Equals). Also returns the result text that must
    appear on screen afterwards (only for exact integers; otherwise None => the last goal stays weak)."""
    from core_organs.task_runner import _DIGIT_WORDS, _SYMBOL_WORDS
    compact = re.sub(r"\s+", "", expr)
    goals: List[str] = []
    for ch in compact:
        if ch in "xX":
            ch = "*"
        word = _DIGIT_WORDS.get(ch) or _SYMBOL_WORDS.get(ch)
        if word:
            goals.append(f"press {word[:1].upper()}{word[1:]}")
    goals.append("press Equals")
    value = _safe_eval(compact)
    result = None
    if value is not None and abs(value) < 1e12 and float(value).is_integer():
        result = str(int(value))
    return goals, result


def _literal_typing_goal(goal: str) -> str:
    """'type hello world' -> 'type "hello world"' so the judge types the user's exact words without
    an LLM rewrite. Instructions that need composing (a haiku, a summary...) are left for the judge."""
    m = re.match(r"^(type|write|enter|input)\s+(?:the\s+text\s+|that\s+)?(.+)$", goal.strip(), re.I)
    if not m:
        return goal
    payload = m.group(2).strip()
    if re.match(r"^[\"“'].*[\"”']$", payload):
        return goal
    if len(payload.split()) > 12 or _COMPOSE_CUES.search(payload) or _PATH_RE.search(payload):
        return goal
    return f'{m.group(1).lower()} "{payload}"'


def plan_app_goals(command: str, app_spans: List[Tuple[str, int]]) -> List[AppPlan]:
    """Per-app micro-goals from the command. `app_spans` = [(normalized_app, position_in_command)], in the
    compiler's order. Pure function: no I/O, unit-testable."""
    plans: Dict[str, AppPlan] = {}
    order: List[str] = []
    desktop = [(a, p) for a, p in app_spans if a and not is_browser_app(a)]
    for a, _p in desktop:
        if a not in plans:
            plans[a] = AppPlan(app=a)
            order.append(a)
    if not desktop:
        return []
    pos_of = {a: p for a, p in desktop}
    all_pos = [(p, a) for a, p in app_spans if a]          # includes browsers: their clauses are not ours
    spans = _clause_spans(_shield_same_length(command))
    current: Optional[str] = None
    pending: List[str] = []                                 # clauses seen before any app is known
    for s, e in spans:
        raw = command[s:e]
        here = [a for p, a in sorted(all_pos) if s <= p < e]
        mine = [a for a in here if a in plans]
        if len(here) > 1 and len(mine) >= 1 and len(set(here)) > 1:
            # one clause names several apps: sequence only, never guess which one the verbs belong to
            for a in mine:
                plans[a].notes.append(f"clause names several apps ('{raw[:50]}'): launched in order, goals not guessed")
            current = mine[-1]
            continue
        if mine:
            target = mine[0]
        elif here:                                          # a browser clause: someone else's work
            current = None
            continue
        else:
            target = current
        if target is None:
            pending.append(raw)
            continue
        current = target
        for pc in pending:
            plans[target].clauses.append(pc)
        pending = []
        plans[target].clauses.append(raw)

    for a in order:
        plan = plans[a]
        mentions = _mention_variants(a, command, pos_of[a])
        for clause in plan.clauses:
            cleaned = _strip_app_phrases(clause, mentions)
            if not cleaned:
                continue
            if _DRAW_CUES.search(cleaned):
                plan.delegated.append(cleaned)
                continue
            for goal in _split_goals(cleaned):
                m = _ARITH_RE.search(goal)
                # an expression inside a file name / path / typed text (2024-10-05.txt) is not arithmetic to press
                if m and not _PATH_RE.search(goal) and not re.match(
                        r"^(?:type|write|enter|input|save|export|open|rename|name|call)\b", goal, re.I):
                    seq, result = _arith_goals(m.group(1))
                    base = len(plan.goals)
                    for g in seq:
                        plan.goals.append(g)
                        plan.strength.append("weak")
                    if result is not None:
                        plan.expect_map[len(plan.goals) - 1] = {"name_visible": result}
                        plan.strength[-1] = "strong"
                    else:
                        plan.notes.append(f"'{m.group(1)}': result not an exact integer; final press stays weak")
                    continue
                goal = _literal_typing_goal(goal)
                plan.goals.append(goal)
                pm = _PATH_RE.search(goal)
                if pm and re.search(r"\bsave\b|\bexport\b", goal, re.I):
                    plan.expect_map[len(plan.goals) - 1] = {"file_created": pm.group(0)}
                    plan.strength.append("strong")
                elif re.match(r"^(?:type|write|enter|input)\b", goal, re.I):
                    plan.strength.append("strong")           # the loop adds text_contains for what it typed
                else:
                    plan.strength.append("weak")
        if not plan.goals and not plan.delegated:
            plan.notes.append("pure launch: no goals in the command")
    return [plans[a] for a in order]


# ---------------------------------------------------------------------------------------------- execution

APP_HANDLES: Dict[str, Dict[str, Any]] = {}      # app -> {hwnd, title, trace_tail, ts}: later stages may look these up


def handle_for(app: str) -> int:
    return int((APP_HANDLES.get(app) or {}).get("hwnd") or 0)


@dataclass
class AppRun:
    app: str
    plan: AppPlan
    status: str = "PENDING"        # COMPLETED | BLOCKED | NEEDS_HUMAN | READY | ERROR | DELEGATED | SKIPPED
    result: Dict[str, Any] = field(default_factory=dict)
    hwnd: int = 0
    elapsed_s: float = 0.0
    goal_verdicts: List[str] = field(default_factory=list)
    cursor_id: str = ""                                         # the child virtual cursor that drove this app (parallel runs)
    cursor_path: List[Tuple[int, int]] = field(default_factory=list)
    t_start: float = 0.0
    t_end: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        r = self.result
        return {"app": self.app, "status": self.status, "hwnd": self.hwnd, "elapsed_s": round(self.elapsed_s, 2),
                "cursor": self.cursor_id, "cursor_points": len(self.cursor_path),
                "steps": r.get("steps", 0), "completed": r.get("completed"), "awaiting_human": r.get("awaiting_human"),
                "blocked_at_goal": r.get("blocked_at_goal"), "goals": self.plan.goals,
                "strength": self.plan.strength, "goal_verdicts": self.goal_verdicts,
                "delegated": self.plan.delegated, "notes": self.plan.notes,
                "trace_tail": [(t.get("verb"), (t.get("element") or "")[:24], t.get("verdict"))
                               for t in (r.get("trace") or [])[-6:]]}


@dataclass
class LoopFirstResult:
    ran: bool = False
    reason: str = ""
    runs: List[AppRun] = field(default_factory=list)
    halted_for_human: bool = False
    capsule: str = ""
    elapsed_s: float = 0.0
    parallel: Dict[str, Any] = field(default_factory=dict)

    @property
    def all_completed(self) -> bool:
        return bool(self.runs) and all(r.status in ("COMPLETED", "READY") for r in self.runs) \
            and not self.halted_for_human

    def apps_touched(self) -> List[str]:
        return [r.app for r in self.runs if r.status in ("COMPLETED", "BLOCKED", "NEEDS_HUMAN", "READY")]

    def as_dict(self) -> Dict[str, Any]:
        return {"ran": self.ran, "reason": self.reason, "halted_for_human": self.halted_for_human,
                "capsule": self.capsule, "elapsed_s": round(self.elapsed_s, 2),
                "all_completed": self.all_completed, "parallel": dict(self.parallel), "apps": [r.as_dict() for r in self.runs]}

    def evidence_text(self) -> str:
        """The block the crew receives. Plain facts: what was DONE and VERIFIED, what was weak, what is left."""
        if not self.ran:
            return f"DETERMINISTIC DESKTOP PASS: not run ({self.reason or 'disabled'}). Plan every step yourself."
        lines = ["DETERMINISTIC DESKTOP PASS (the verified autonomy loop ran BEFORE you; every step was judged by a "
                 "postcondition verifier, not by a language model):"]
        for i, r in enumerate(self.runs, 1):
            head = f"  App {i} '{r.app}': {r.status}"
            if r.hwnd:
                head += f" (window hwnd={r.hwnd})"
            if r.result.get("steps"):
                head += f", {r.result.get('steps')} verified-loop steps in {r.elapsed_s:.1f}s"
            lines.append(head)
            for gi, g in enumerate(r.plan.goals):
                v = r.goal_verdicts[gi] if gi < len(r.goal_verdicts) else "NOT RUN"
                st = r.plan.strength[gi] if gi < len(r.plan.strength) else "weak"
                tag = {"PASS": "DONE", "NOT RUN": "NOT DONE"}.get(v, "NOT DONE")
                weak = "" if st == "strong" else " [WEAK evidence: the UI changed, nothing more was proven]"
                lines.append(f"    - '{g[:70]}' -> {tag} ({v}){weak if tag == 'DONE' else ''}")
            for d in r.plan.delegated:
                lines.append(f"    - '{d[:70]}' -> DELEGATED to the drawing tools (not an element-level goal); NOT DONE yet")
            for n in r.plan.notes:
                lines.append(f"    note: {n}")
            if r.status == "ERROR":
                lines.append(f"    error: {r.result.get('error', '')[:120]}")
        if self.halted_for_human:
            lines.append(f"  STOPPED: a human decision is required ({self.capsule}). Later apps were NOT started.")
        lines.append("  RULES: do NOT redo a goal marked DONE; do NOT re-type text that is already present. Work only on goals "
                     "marked NOT DONE or WEAK. No data was copied between apps; if the task needs that, do it yourself.")
        return "\n".join(lines)


class _OwnedFx:
    """The effector gate for a window this run opened itself (the gesture driver refuses without one)."""
    allowed = True
    owned = True
    visible_ok = False
    overlay = None

    def why_not(self) -> str:
        return ""


def draw_on(app: str, hwnd: int, what: str, ask: Optional[Callable[[str, str], Optional[str]]] = None) -> Tuple[bool, str]:
    """A 'draw' step on the app's canvas through the virtual mouse (the person's cursor never moves): the strokes come from the shape's geometry or
    the model's sketch; the result is checked by pixels on the surface."""
    from core_organs import fast_uia
    from core_organs.professor import gestures as GE
    drv = GE.GestureDriver(re.sub(r"\W+", "_", app.lower()), hwnd, _OwnedFx(), lambda: fast_uia.snapshot(hwnd, timeout_ms=3000) or [])
    res = drv.draw(what, ask=ask)
    return bool(res.ok), f"{res.route}: {res.why}"[:300]


def _run_steps(plan: AppPlan, run: "AppRun", *, operate, prepare, capsule_cb, cursor_cb, allow_destructive, max_steps_per_goal,
               om: Any = None, draw: Optional[Callable[[str, int, str], Tuple[bool, str]]] = None) -> None:
    """The model's steps, in order. Each goes to the most direct route that can do it AND prove it: the app's own object model (Office: typing,
    formatting, slides, Save As - read back), the drawing tools for 'draw', the verified autonomy loop for everything else. A run of loop goals
    is handed over together so the loop keeps its own context."""
    if om is None:
        from core_organs import office_om as om
    hk = om.kind_for_app(plan.app) if hasattr(om, "kind_for_app") else ""
    headless = bool(hk) and os.environ.get("HOJAIGA_OFFICE_HEADLESS", "1") != "0" and \
        all(om.can_do(hk, s) or (s["do"] in DATA_STEPS and s["do"] != "paste") for s in plan.steps)
    sess = None
    if headless:                                                                                      # every step is the object model's: an invisible instance of its own, no window at all
        try:
            sess = om.Headless(hk)
            if plan.steps and plan.steps[0]["do"] not in ("new_document", "open_file") and not sess.has_document():
                om.do_step(sess, {"do": "new_document"})
        except Exception as exc:
            logger.warning("[loop-first] invisible %s instance failed (%s): the window route is used", hk, exc)
            sess = None
    try:
        _run_steps_inner(plan, run, operate=operate, prepare=prepare, capsule_cb=capsule_cb, cursor_cb=cursor_cb, allow_destructive=allow_destructive,
                         max_steps_per_goal=max_steps_per_goal, om=om, draw=draw, session=sess, session_kind=hk)
    finally:
        if sess is not None:
            sess.close()
            run.result["route"] = (f"a new {hk} instance ON SCREEN through its object model" if sess.visible else
                                   f"an invisible {hk} instance through its object model (no window)")
            if sess.shots:
                run.result["screenshots"] = list(sess.shots)


def _run_steps_inner(plan: AppPlan, run: "AppRun", *, operate, prepare, capsule_cb, cursor_cb, allow_destructive, max_steps_per_goal,
                     om: Any, draw: Optional[Callable[[str, int, str], Tuple[bool, str]]] = None, session: Any = None, session_kind: str = "") -> None:
    draw = draw or draw_on
    if session is not None:
        run.hwnd, kind, target = 0, session_kind, session
    else:
        res = prepare(plan.app, capsule_cb=capsule_cb, cursor_cb=cursor_cb) or {}
        if not res.get("hwnd") and not res.get("awaiting_human"):
            time.sleep(3.0)                                                                           # live Oct-27: Excel's start window was replaced while it loaded ('window-not-found'); look again once
            res = prepare(plan.app, capsule_cb=capsule_cb, cursor_cb=cursor_cb) or {}
        run.hwnd = int(res.get("hwnd") or 0)
        if res.get("awaiting_human"):
            run.status, run.result = "NEEDS_HUMAN", res
            return
        kind = ""
        with _suppress():
            kind = om.app_kind(run.hwnd) if run.hwnd else ""
            if not kind and run.hwnd and hasattr(om, "frame_kind") and om.frame_kind(run.hwnd) and om.open_blank(run.hwnd):
                kind = om.app_kind(run.hwnd)                                                          # an Office start screen: a blank document first, then its object model
        target = run.hwnd
    verdicts: List[str] = ["NOT RUN"] * len(plan.steps)
    evidence: List[str] = [""] * len(plan.steps)
    pending: List[int] = []
    trace: List[Dict[str, Any]] = []

    def flush() -> bool:
        if not pending:
            return True
        goals = [plan.goals[i] for i in pending]
        r = operate(plan.app, goals, allow_destructive=allow_destructive, capsule_cb=capsule_cb, cursor_cb=cursor_cb,
                    max_steps_per_goal=max_steps_per_goal, expect_map={j: plan.expect_map[i] for j, i in enumerate(pending) if i in plan.expect_map} or None) or {}
        trace.extend(r.get("trace") or [])
        last = {str(t.get("goal", "")): str(t.get("verdict", "")) for t in (r.get("trace") or [])}
        for i in pending:
            verdicts[i] = last.get(plan.goals[i], "NOT RUN")
        run.result.update({k: r.get(k) for k in ("awaiting_human", "ready_reason", "window_title") if r.get(k)})
        pending.clear()
        return not r.get("awaiting_human") and all(verdicts[i] == "PASS" for i in range(len(verdicts)) if verdicts[i] != "NOT RUN")

    for i, s in enumerate(plan.steps):
        if s["do"] in DATA_STEPS:                                                                    # data between apps (the blackboard): read / insert_table / insert_picture / paste
            if not flush():
                break
            ok, ev, typed = _data_step(s, target, kind, om, plan.app)
            if typed is not None:                                                                    # kept text into an app with no object model: the loop types it
                plan.goals[i] = f'type "{typed}"'
                pending.append(i)
                continue
            verdicts[i], evidence[i] = ("PASS" if ok else "FAIL"), ev
            trace.append({"goal": plan.goals[i], "verb": s["do"], "element": s.get("target", ""), "verdict": verdicts[i], "evidence": evidence[i]})
            if not ok:
                break
            continue
        if s["do"] == "save_as" and not allow_destructive and os.path.exists(_PATH_RE.search(s["text"]).group(0) if _PATH_RE.search(s["text"]) else ""):
            if not flush():
                break
            verdicts[i], evidence[i] = "NEEDS_HUMAN", "the file already exists: overwriting it needs your yes"
            run.result["awaiting_human"] = True
            break
        if kind and om.can_do(kind, s):
            if not flush():
                break
            ok, ev = om.do_step(target, s)
            if getattr(target, "visible", False):                                                     # on screen: the person can follow each step, and each one leaves a picture
                time.sleep(float(os.environ.get("HOJAIGA_STEP_PAUSE", "1.2")))
                target.shot(f"step{i + 1}_{s['do']}")
            verdicts[i], evidence[i] = ("PASS" if ok else "FAIL"), "object model: " + ev
            trace.append({"goal": plan.goals[i], "verb": s["do"], "element": s.get("target", ""), "verdict": verdicts[i], "evidence": evidence[i]})
            if not ok:
                break
        elif s["do"] == "draw":
            if not flush():
                break
            ok, ev = draw(plan.app, run.hwnd, s["text"]) if run.hwnd else (False, "no window of the app was found to draw on")
            verdicts[i], evidence[i] = ("PASS" if ok else "FAIL"), "drawing: " + ev
            trace.append({"goal": plan.goals[i], "verb": "draw", "element": "", "verdict": verdicts[i], "evidence": evidence[i]})
            if not ok:
                break
        else:
            pending.append(i)
    flush()
    for i, s in enumerate(plan.steps):                                                               # a file saved here is what the next app may use
        m = _PATH_RE.search(s["text"]) if s["do"] == "save_as" else None
        if m and verdicts[i] == "PASS" and os.path.isfile(m.group(0)):
            keep(os.path.basename(m.group(0)), {"kind": "file", "path": m.group(0), "from": plan.app})
    run.goal_verdicts = verdicts
    run.result.update({"trace": trace, "steps": len(trace), "hwnd": run.hwnd, "step_evidence": evidence})
    if run.result.get("awaiting_human"):
        run.status = "NEEDS_HUMAN"
    else:
        run.status = "COMPLETED" if verdicts and all(v == "PASS" for v in verdicts) else "BLOCKED"
    run.result["completed"] = run.status == "COMPLETED"


def _suppress():
    import contextlib
    return contextlib.suppress(Exception)


# ---------------------------------------------------------------------------------------------- the blackboard (after microsoft/UFO)
# UFO's host agent splits a request into one sub-task per app and hands each the information it needs; its agents share a blackboard. Here the
# blackboard holds what one app PRODUCED (a saved file, a table read from a page or a sheet, a text) so a later app's steps can use it by name:
# Chrome -> Excel, Paint -> Word, Excel -> PowerPoint. It lives for one run_loop_first call.
DATA_STEPS = ("read", "insert_table", "insert_picture", "paste")
BLACKBOARD: Dict[str, Dict[str, Any]] = {}
KEEP_BOARD = {"on": False}                                                                         # hojaiga_run.run sets it: its web and desktop tickets share one board
LAST_PLANS: List[Dict[str, Any]] = []                                                              # the step plans of the last run_loop_first call (app, the words, the steps): what a proven run DID, kept for training


def keep(name: str, item: Dict[str, Any]) -> None:
    BLACKBOARD[(name or "data").strip().lower()] = item


def recall(name: str, kind: str = "") -> Optional[Dict[str, Any]]:
    """The item kept under this name; else, when exactly one item of the wanted kind exists, that one; else the newest of that kind."""
    key = (name or "").strip().lower()
    if key in BLACKBOARD and (not kind or BLACKBOARD[key]["kind"] == kind):
        return BLACKBOARD[key]
    if key:
        for k, v in BLACKBOARD.items():
            if (key in k or k in key) and (not kind or v["kind"] == kind):
                return v
    same = [v for v in BLACKBOARD.values() if not kind or v["kind"] == kind]
    return same[-1] if same else None


def plan_outputs(plan: AppPlan) -> List[Dict[str, str]]:
    """What this plan will leave on the blackboard, known before it runs: files it saves, data it reads."""
    out = []
    for s in plan.steps:
        m = _PATH_RE.search(s["text"]) if s["do"] == "save_as" else None
        if m:
            out.append({"name": os.path.basename(m.group(0)), "kind": "file", "detail": m.group(0), "app": plan.app})
        elif s["do"] == "read":
            out.append({"name": s["format"] or "data", "kind": "text" if "text" in s["target"].lower() else "table", "detail": s["target"], "app": plan.app})
    return out


def outputs_text(outputs: List[Dict[str, str]]) -> str:
    return "\n".join(f"- {o['kind']} '{o['name']}'" + (f" ({o['detail']})" if o["detail"] else "") + f" from {o['app']}" for o in outputs)


def _data_step(s: Dict[str, str], hwnd: int, kind: str, om: Any, app: str) -> Tuple[bool, str, Optional[str]]:
    """(ok, evidence, text for the loop to type or None)."""
    do, text, target = s["do"], s["text"], s["target"]
    name = s.get("format") or "data"
    if do == "read":
        url = _URL_RE.search(text)
        if url:
            from core_organs import web_executor as WE
            page = WE.read_page(url.group(0))
            if not page.get("ok"):
                return False, f"web: {page.get('why')}", None
            if "text" in target.lower() and "table" not in target.lower() or not page["tables"]:
                keep(name, {"kind": "text", "text": page["text"], "from": url.group(0)})
                return True, f"web: kept {len(page['text'])} chars of text as '{name}'", None
            rows = WE.best_table(page["tables"], target)
            keep(name, {"kind": "table", "rows": rows, "from": url.group(0)})
            return True, f"web: kept a {len(rows)}x{max(len(r) for r in rows)} table as '{name}' ({page['why']})", None
        if not kind:
            return False, f"{app} has no object model to read from", None
        got = om.read(hwnd, target)
        if not got:
            return False, "the document gave nothing to read", None
        keep(name, {**got, "from": app})
        return True, f"object model: kept {got['kind']} as '{name}'", None
    if do == "insert_table":
        item = recall(text, "table")
        if item is None:
            return False, f"no table '{text}' was kept by an earlier step", None
        if not kind:
            return False, f"{app} has no object model to insert a table into", None
        ok, ev = om.insert_table(hwnd, item["rows"], target)
        return ok, "object model: " + ev, None
    if do == "insert_picture":
        path = text if os.path.isfile(text) else ((recall(text, "file") or {}).get("path") or "")
        if not path:
            return False, f"no picture '{text}' exists or was kept", None
        if not kind:
            return False, f"{app} has no object model to insert a picture into", None
        ok, ev = om.insert_picture(hwnd, path)
        return ok, "object model: " + ev, None
    item = recall(text, "text") or recall(text)
    if item is None:
        return False, f"nothing '{text}' was kept to paste", None
    val = item.get("text") or "\n".join("\t".join(str(c) for c in r) for r in item.get("rows", []))
    if kind and om.can_do(kind, {"do": "type", "target": target}):
        ok, ev = om.do_step(hwnd, {"do": "type", "text": val, "target": target})
        return ok, "object model: " + ev, None
    return False, "", val


def _goal_verdicts(plan: AppPlan, trace: List[Dict[str, Any]]) -> List[str]:
    last: Dict[str, str] = {}
    for t in trace or []:
        last[str(t.get("goal", ""))] = str(t.get("verdict", ""))
    return [last.get(g, "NOT RUN") for g in plan.goals]


def plans_independent(plans: List["AppPlan"]) -> Tuple[bool, str]:
    """May these per-app plans run at the same time? Only when they touch DISJOINT apps and no plan talks about another plan's app (a
    clause that names two apps is data moving between them: order matters, so the run stays sequential). DATA-driven: the app names come
    from the plans themselves."""
    apps = [p.app.lower() for p in plans if p.goals]
    if len(apps) < 2:
        return False, "fewer than two apps have goals"
    if len(set(apps)) != len(apps):
        return False, "two plans target the same app"
    for p in plans:
        others = [a for a in apps if a != p.app.lower()]
        blob = " ".join(p.clauses or p.goals).lower()
        for o in others:
            if o in blob:
                return False, f"a clause of '{p.app}' names '{o}' (data may move between them)"
    return True, "disjoint apps, no cross-app clause"


def _run_plans_parallel(plans, *, operate, capsule_cb, allow_destructive, max_steps_per_goal, record, out, notify) -> None:
    """One CHILD virtual cursor per app, all running at once. Each child has its own loop (operate(..., isolated=True)), its own sprite id and
    its own cursor path; the verifier judges every child independently. Shared, focus-dependent state (the UIA worker, the popup policy's task
    context) is serialized inside the loop, so concurrency only overlaps the waits and the posted messages."""
    import threading
    runs = [AppRun(app=p.app, plan=p) for p in plans]
    out.runs.extend(runs)

    def child(run: AppRun, idx: int) -> None:
        plan = run.plan
        run.cursor_id = f"child:{idx}:{plan.app}"
        sprite = None
        try:
            from core_organs import visual_cursor as vc
            sprite = vc.for_agent(run.cursor_id, plan.app, ttl=None)
        except Exception:                                      # no overlay available: the path is still recorded
            sprite = None

        def cursor_cb(x, y, _run=run, _spr=sprite):
            _run.cursor_path.append((int(x), int(y)))
            try:
                if _spr is not None:
                    _spr.fly_to(float(x), float(y), _run.app, 0.15)
            except Exception:  # noqa: BLE001
                pass
        run.t_start = time.perf_counter()
        try:
            try:                                           # a worker thread needs its OWN COM apartment before any UI Automation call
                import uiautomation as _auto
                _com = _auto.UIAutomationInitializerInThread()
                _com.__enter__()
            except Exception:  # noqa: BLE001
                _com = None
            res = operate(plan.app, list(plan.goals), allow_destructive=allow_destructive, capsule_cb=capsule_cb, cursor_cb=cursor_cb,
                          max_steps_per_goal=max_steps_per_goal, expect_map=dict(plan.expect_map) or None, isolated=True)
            run.result = res or {}
            run.hwnd = int(run.result.get("hwnd") or 0)
            run.goal_verdicts = _goal_verdicts(plan, run.result.get("trace") or [])
            run.status = "NEEDS_HUMAN" if run.result.get("awaiting_human") else ("COMPLETED" if run.result.get("completed") else "BLOCKED")
        except Exception as exc:  # noqa: BLE001
            logger.exception("[loop-first] child %s failed", plan.app)
            run.status, run.result = "ERROR", {"error": f"{type(exc).__name__}: {exc}"}
        run.t_end = time.perf_counter()
        run.elapsed_s = run.t_end - run.t_start
        APP_HANDLES[plan.app] = {"hwnd": run.hwnd, "title": run.result.get("window_title", ""),
                                 "trace_tail": run.as_dict()["trace_tail"], "ts": time.time()}
        record("LOOP_FIRST", plan.app, f"{run.status} (child cursor {run.cursor_id}) goals={len(plan.goals)} steps={run.result.get('steps', 0)}")
        try:
            from core_organs import visual_cursor as vc
            vc.release_agent(run.cursor_id)
        except Exception:  # noqa: BLE001
            pass

    threads = [threading.Thread(target=child, args=(r, i), daemon=True, name=f"child-cursor-{r.app}") for i, r in enumerate(runs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if any(r.status == "NEEDS_HUMAN" for r in runs):
        out.halted_for_human = True
        bad = next(r for r in runs if r.status == "NEEDS_HUMAN")
        out.capsule = f"{bad.app}: {bad.result.get('ready_reason') or 'a dialog or an ambiguous choice needs you'}"
        try:
            notify("input_needed", f"Agent needs your input - {out.capsule}")
        except Exception:  # noqa: BLE001
            pass


def run_loop_first(command: str, app_spans: List[Tuple[str, int]], *,
                   operate: Optional[Callable[..., Dict[str, Any]]] = None,
                   prepare: Optional[Callable[..., Dict[str, Any]]] = None,
                   capsule_cb: Optional[Callable[[str, str], None]] = None,
                   cursor_cb: Optional[Callable[[float, float], None]] = None,
                   notify: Optional[Callable[[str, str], None]] = None,
                   record_action: Optional[Callable[[str, str, str], None]] = None,
                   allow_destructive: bool = False, max_steps_per_goal: int = 5,
                   plan_filter: Optional[Callable[[List[AppPlan]], List[AppPlan]]] = None,
                   parallel: bool = False, planner: Optional[Callable[[str, str], Optional[str]]] = None) -> LoopFirstResult:
    """Run operate_app for every detected desktop app, in the compiler's order. See the module docstring. `parallel=True` runs INDEPENDENT
    apps at the same time, one child virtual cursor each (see plans_independent / _run_plans_parallel); otherwise, or when the plans are not
    independent, the order is sequential exactly as before."""
    out = LoopFirstResult()
    if not loop_first_enabled():
        out.reason = "HOJAIGA_LOOP_FIRST=0"
        return out
    t0 = time.perf_counter()
    if not KEEP_BOARD["on"]:
        BLACKBOARD.clear()                                                                            # one task's hand-offs never leak into the next task (a front-door run keeps one board for all its tickets)
    try:
        plans = plan_app_goals(command, app_spans)
    except Exception as exc:                                  # a planning bug must not take the product down
        logger.exception("[loop-first] planning failed")
        out.reason = f"planning failed: {type(exc).__name__}: {exc}"
        return out
    # the model plans the steps on a real run (no injected operate) or when a planner is given; HOJAIGA_STEP_PLANNER=off keeps the word split
    if (planner is not None or operate is None) and os.environ.get("HOJAIGA_STEP_PLANNER", "on").lower() != "off":
        outputs: List[Dict[str, str]] = [{"name": k, "kind": v["kind"], "detail": str(v.get("path") or ""), "app": str(v.get("from") or "an earlier step")} for k, v in BLACKBOARD.items()]
        for p in plans:
            with _suppress():
                refine_plan(p, planner, outputs_text(outputs))
            outputs += plan_outputs(p)                                            # what this app will leave for the next (microsoft/UFO: the host passes each sub-task its message)
    if plan_filter is not None:                               # e.g. the lifecycle's risk gate removes goals it queued for a human
        plans = plan_filter(plans)
    LAST_PLANS[:] = [{"app": p.app, "clauses": list(p.clauses or p.goals), "steps": [dict(x) for x in (p.steps or [])]} for p in plans]
    if not plans:
        out.reason = "no desktop app detected"
        return out
    if operate is None or prepare is None:
        from core_organs import desktop_grounding as dg
        operate = operate or dg.operate_app
        prepare = prepare or dg.prepare_app
    out.ran = True
    notify = notify or (lambda state, detail: None)
    record = record_action or (lambda *a: None)
    if parallel:
        ok_par, why_par = plans_independent(plans)
        out.parallel = {"requested": True, "used": bool(ok_par), "why": why_par}
        if ok_par and not any(p.steps for p in plans):             # model-planned steps run in order through the object model / drawing / loop routes
            _run_plans_parallel([p for p in plans if p.goals], operate=operate, capsule_cb=capsule_cb, allow_destructive=allow_destructive,
                                max_steps_per_goal=max_steps_per_goal, record=record, out=out, notify=notify)
            out.elapsed_s = time.perf_counter() - t0
            return out
    for plan in plans:
        run = AppRun(app=plan.app, plan=plan)
        out.runs.append(run)
        ts = time.perf_counter()
        try:
            if plan.steps:
                _run_steps(plan, run, operate=operate, prepare=prepare, capsule_cb=capsule_cb, cursor_cb=cursor_cb,
                           allow_destructive=allow_destructive, max_steps_per_goal=max_steps_per_goal)
            elif plan.goals:
                res = operate(plan.app, list(plan.goals), allow_destructive=allow_destructive, capsule_cb=capsule_cb,
                              cursor_cb=cursor_cb, max_steps_per_goal=max_steps_per_goal,
                              expect_map=dict(plan.expect_map) or None)
                run.result = res or {}
                run.hwnd = int(run.result.get("hwnd") or 0)
                run.goal_verdicts = _goal_verdicts(plan, run.result.get("trace") or [])
                if run.result.get("awaiting_human"):
                    run.status = "NEEDS_HUMAN"
                elif run.result.get("completed"):
                    run.status = "COMPLETED"
                else:
                    run.status = "BLOCKED"
            elif plan.delegated:
                run.status = "DELEGATED"
            else:
                res = prepare(plan.app, capsule_cb=capsule_cb, cursor_cb=cursor_cb) or {}
                run.result = res
                run.hwnd = int(res.get("hwnd") or 0)
                run.status = "READY" if res.get("ready") else ("NEEDS_HUMAN" if res.get("awaiting_human") else "BLOCKED")
        except Exception as exc:
            logger.exception("[loop-first] %s failed", plan.app)
            run.status = "ERROR"
            run.result = {"error": f"{type(exc).__name__}: {exc}"}
        run.elapsed_s = time.perf_counter() - ts
        APP_HANDLES[plan.app] = {"hwnd": run.hwnd, "title": run.result.get("window_title", ""),
                                 "trace_tail": run.as_dict()["trace_tail"], "ts": time.time()}
        record("LOOP_FIRST", plan.app, f"{run.status} goals={len(plan.goals)} steps={run.result.get('steps', 0)} hwnd={run.hwnd}")
        if run.status == "NEEDS_HUMAN":
            out.halted_for_human = True
            why = run.result.get("ready_reason") or "a dialog or an ambiguous choice needs you"
            out.capsule = f"{plan.app}: {why}"
            try:
                notify("input_needed", f"Agent needs your input - {out.capsule}")
            except Exception:
                pass
            break
    out.elapsed_s = time.perf_counter() - t0
    return out
