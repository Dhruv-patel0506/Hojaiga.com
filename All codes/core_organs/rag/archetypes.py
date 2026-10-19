"""
rag.archetypes -- 25 application archetypes: what a CLASS of apps looks like and how it is operated, so a never-seen app still gets a
usable procedure skeleton when the RAG has no pathway for it.

Each archetype carries
    signals     generic UI words (control names / window titles / roles) that identify the class - never an app name
    roles       control roles typical of the class (a table of cells, a canvas, a timeline ...)
    grammar     the ordered phases of a task in this class ("create -> edit -> format -> export")
    keys        conventions that hold across the class (Ctrl+S saves, Ctrl+Z undoes ...)
    traps       controls / actions that must NEVER be taken blind (send, delete all, publish, purchase ...)
    templates   generic goal templates with slots, usable as a Tier-3 seed
    train/test  7 + 3 example applications (the 70/30 split); used for bookkeeping and for the name prior only

    ArchetypeRouter.classify(signature)  -> ranked [(archetype, score)]   from the scanned app's own control words, no name needed
    ArchetypeRouter.fit(signatures)      learns per-archetype word weights from scanned TRAIN apps (centroids)
    hint(app, goal, rag_has_pathway)     -> procedure skeleton labelled source='archetype' (confidence <= 0.45) ONLY when the RAG has none
    evaluate_70_30_split()               honest numbers: name-only zero-shot (bookkeeping), signal-only, fitted, on real scanned apps

The matrix of example applications is a labelled list I wrote for the 25 classes; a held-out accuracy computed from names alone says nothing about
screens, so the evaluator measures the matcher on the control inventories that were really scanned (data/ai_root/harvest/training) and reports n.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
TRAIN_ROWS = os.path.join(DATA, "ai_root", "harvest", "training", "ui_training_dataset.jsonl")

_UNIVERSAL_TRAPS = ["send", "submit", "post", "publish", "pay", "purchase", "buy", "delete", "remove all", "empty", "format", "uninstall", "sign out", "log out"]
_STD_KEYS = {"save": "Ctrl+S", "undo": "Ctrl+Z", "redo": "Ctrl+Y", "find": "Ctrl+F", "open": "Ctrl+O", "new": "Ctrl+N", "copy": "Ctrl+C", "paste": "Ctrl+V", "select all": "Ctrl+A"}


def _A(aid, label, signals, roles, grammar, keys, traps, templates, train, test):
    return {"id": aid, "label": label, "signals": signals.split(), "roles": roles.split(), "grammar": grammar, "keys": keys, "traps": traps,
            "templates": templates, "train": train.split(","), "test": test.split(",")}


ARCHETYPES: List[Dict[str, Any]] = [
    _A("word_processor", "Document / word processor", "font paragraph styles heading page layout references review mailings margins spelling bold italic", "document edit",
       ["open or create", "type body text", "apply style / format", "insert object", "review", "save / export"], {"bold": "Ctrl+B", "italic": "Ctrl+I", "print": "Ctrl+P"},
       ["accept all changes", "reject all", "mail merge send"], ["type {text}", "make the first line a heading", "save as {file}"],
       "Word,Writer,Google Docs,Pages,WordPad,AbiWord,WPS Writer", "OnlyOffice Docs,Scrivener,Zoho Writer"),
    _A("spreadsheet", "Spreadsheet", "formulas cell sheet column row formula chart pivot filter sort cells name box data", "table dataitem edit",
       ["select cell", "type value / formula", "format cells", "sort / filter", "chart", "save"], {"edit cell": "F2", "fill down": "Ctrl+D", "sum": "Alt+="},
       ["delete sheet", "clear all"], ["put {text} in {cell}", "sum column {col}", "make a chart of {range}"],
       "Excel,Calc,Google Sheets,Numbers,WPS Spreadsheets,Gnumeric,Quip Sheets", "OnlyOffice Sheets,Zoho Sheet,LibreOffice Base Tables"),
    _A("presentation", "Slide presentation", "slide slides layout design transitions animations slideshow notes themes placeholder", "pane list",
       ["new slide", "pick layout", "fill placeholders", "insert media / shape", "transition", "present / save"], {"present": "F5", "new slide": "Ctrl+M"},
       ["start broadcast", "share online"], ["title the slide {text}", "add a slide about {text}", "insert a picture"],
       "PowerPoint,Impress,Google Slides,Keynote,Prezi,Canva Presentations,Beautiful.ai", "WPS Presentation,Pitch,Slides.com"),
    _A("text_editor", "Plain text editor", "edit view encoding word wrap line column replace find status bar zoom", "document edit",
       ["open or new tab", "type", "find / replace", "save"], {"replace": "Ctrl+H", "goto line": "Ctrl+G"},
       ["replace all in files"], ["type {text}", "replace {a} with {b}", "save as {file}"],
       "Notepad,Notepad++,Gedit,TextEdit,Kate,Sublime Text,EmEditor", "Notepad3,Mousepad,Pulsar"),
    _A("code_ide", "Code editor / IDE", "explorer terminal debug run extensions problems source control breakpoint output search commit", "tree tab edit",
       ["open folder", "edit file", "run / debug", "inspect output", "commit"], {"command palette": "Ctrl+Shift+P", "quick open": "Ctrl+P", "terminal": "Ctrl+`"},
       ["force push", "discard changes", "delete branch"], ["open the file {file}", "run the program", "find {text} in the project"],
       "VS Code,Visual Studio,IntelliJ IDEA,PyCharm,Eclipse,Android Studio,Atom", "Sublime Merge,CLion,Zed"),
    _A("raster_editor", "Raster image editor", "brush eraser layers filter canvas selection fill gradient opacity pencil colors size zoom crop", "canvas pane",
       ["new / open image", "pick tool", "draw or adjust", "layers", "export"], {"brush": "B", "eraser": "E", "zoom": "Z"},
       ["flatten", "clear image"], ["draw a {shape}", "fill with {color}", "crop the image"],
       "Paint,GIMP,Photoshop,Krita,Paint.NET,Affinity Photo,Pixlr", "MyPaint,Photopea,Corel PaintShop"),
    _A("vector_editor", "Vector / diagram drawing", "shape stroke path node pen anchor object align group arrange fill bezier artboard", "canvas pane",
       ["pick tool", "draw shape", "edit nodes", "align / group", "export"], {"group": "Ctrl+G", "rectangle": "R", "ellipse": "E"},
       ["delete page"], ["draw a {shape}", "align the shapes", "export as {format}"],
       "Illustrator,Inkscape,Affinity Designer,CorelDRAW,Figma,Sketch,Vectr", "Gravit Designer,Xara,Boxy SVG"),
    _A("diagram_whiteboard", "Whiteboard / diagram canvas", "rectangle ellipse arrow line text pencil eraser canvas library connector sticky whiteboard board", "canvas pane",
       ["pick tool", "drag on canvas", "label", "connect", "export"], {"rectangle": "R", "arrow": "A", "text": "T"},
       ["clear canvas", "reset the canvas"], ["draw a {shape} and label it {text}", "connect {a} to {b}"],
       "Excalidraw,draw.io,Miro,Whimsical,Lucidchart,Microsoft Whiteboard,FigJam", "tldraw,Mural,Jamboard"),
    _A("3d_modeler", "3D modeling / animation", "viewport mesh object modifier material vertex edge face render scene outliner properties timeline", "pane viewport",
       ["add object", "transform", "edit mesh", "material", "render"], {"move": "G", "rotate": "R", "scale": "S", "extrude": "E"},
       ["delete all", "clear scene", "apply all modifiers"], ["add a cube", "move it up {n}", "render the scene"],
       "Blender,Maya,3ds Max,Cinema 4D,SketchUp,Houdini,ZBrush", "Modo,Wings 3D,Rhino"),
    _A("cad_engineering", "CAD / engineering design", "sketch extrude dimension constraint assembly part feature mate drawing revolve fillet command line", "pane viewport",
       ["new part", "sketch", "constrain", "extrude / cut", "assemble", "drawing"], {"line": "L", "dimension": "D"},
       ["purge", "explode all"], ["sketch a rectangle {w} by {h}", "extrude it {n}"],
       "AutoCAD,SolidWorks,Fusion 360,FreeCAD,Inventor,Onshape,Revit", "Creo,CATIA,LibreCAD"),
    _A("video_editor", "Video editor", "timeline clip track trim cut transition preview export render playhead effects media bin", "pane list",
       ["import media", "place on timeline", "trim / cut", "effects", "export"], {"split": "Ctrl+K", "play": "Space"},
       ["delete project", "overwrite export"], ["trim the clip", "add a title", "export as {format}"],
       "Premiere Pro,DaVinci Resolve,Clipchamp,Shotcut,Kdenlive,OpenShot,iMovie", "Filmora,CapCut,Final Cut"),
    _A("audio_daw", "Audio editor / DAW", "track mixer record waveform plugin master volume pan solo mute tempo midi effects", "pane slider",
       ["new project", "record / import", "edit", "mix", "export"], {"record": "R", "play": "Space"},
       ["delete track", "overwrite master"], ["record a track", "trim the silence", "export as {format}"],
       "Audacity,Ableton Live,FL Studio,Reaper,GarageBand,Ardour,Cubase", "Logic Pro,Reason,LMMS"),
    _A("browser", "Web browser", "address bar tabs bookmarks history downloads extensions reload back forward new tab search settings", "tab edit",
       ["open tab", "navigate", "read / interact", "bookmark or download"], {"address bar": "Ctrl+L", "new tab": "Ctrl+T", "reload": "F5"},
       ["clear browsing data", "sign in", "save password", "buy"], ["open {url}", "search for {text}", "bookmark this page"],
       "Chrome,Edge,Firefox,Brave,Opera,Vivaldi,Safari", "Arc,Tor Browser,Waterfox"),
    _A("email_client", "Email client", "inbox compose reply forward folders drafts sent junk attachment send mail calendar search", "list edit",
       ["open mailbox", "read", "compose", "attach", "send"], {"new mail": "Ctrl+N", "reply": "Ctrl+R"},
       ["send", "delete", "empty deleted items", "report spam"], ["draft an email to {to}", "find the mail from {text}"],
       "Outlook,Thunderbird,Mail,Gmail,Mailbird,Spark,eM Client", "Proton Mail,Postbox,Mailspring"),
    _A("chat_messenger", "Chat / messaging", "message channel direct messages mentions threads send emoji attach call people status reactions", "list edit",
       ["open conversation", "read", "type message", "attach", "send"], {"quick switch": "Ctrl+K", "send": "Enter"},
       ["send", "post", "leave channel", "delete message", "start call"], ["draft a message to {to}", "find the conversation with {text}"],
       "Slack,Teams,Discord,WhatsApp,Telegram,Signal,Skype", "Zoom Chat,Element,Messenger"),
    _A("media_player", "Media player / streaming", "play pause next previous volume playlist queue shuffle repeat library now playing seek", "slider list",
       ["search or pick item", "play", "queue", "adjust volume"], {"play": "Space", "next": "Ctrl+Right"},
       ["delete playlist", "buy", "subscribe"], ["play {text}", "add to queue", "set the volume to {n}"],
       "Spotify,VLC,Windows Media Player,iTunes,Groove Music,foobar2000,MPC-HC", "Winamp,AIMP,PotPlayer"),
    _A("pdf_reader", "Document reader / PDF", "page zoom fit highlight annotate bookmarks thumbnails sign rotate print search document", "document pane",
       ["open document", "navigate pages", "search", "annotate", "export"], {"find": "Ctrl+F", "next page": "Right"},
       ["delete pages", "redact", "sign"], ["open {file}", "find {text}", "highlight this line"],
       "Acrobat Reader,SumatraPDF,Foxit Reader,Preview,Okular,Calibre,Edge PDF", "Sioyek,Zathura,Xodo"),
    _A("file_manager", "File manager / archiver", "folders quick access this pc name date modified size type new folder copy move rename extract compress", "tree list",
       ["navigate", "select", "copy / move", "rename", "compress"], {"rename": "F2", "delete": "Delete", "address": "Ctrl+L"},
       ["delete permanently", "empty recycle bin", "format drive"], ["create folder {text}", "move {file} to {folder}", "zip these files"],
       "File Explorer,Finder,Total Commander,Files,7-Zip,WinRAR,Nautilus", "Directory Opus,Double Commander,PeaZip"),
    _A("terminal", "Terminal / shell", "prompt command shell session profile tab split clear history copy paste font", "document edit",
       ["open session", "type command", "read output", "copy"], {"clear": "Ctrl+L", "interrupt": "Ctrl+C"},
       ["rm -rf", "format", "shutdown", "sudo"], ["run {text}", "change directory to {folder}"],
       "Windows Terminal,PowerShell,Command Prompt,iTerm,GNOME Terminal,PuTTY,Alacritty", "Hyper,Konsole,WezTerm"),
    _A("calculator", "Calculator", "equals clear backspace memory percent divide multiply add subtract digits square root history scientific", "button",
       ["clear", "enter number", "operator", "equals", "read result"], {"clear": "Esc", "equals": "Enter"},
       [], ["calculate {expression}", "convert {n} to {unit}"],
       "Calculator,Windows Calc,SpeedCrunch,Qalculate,Soulver,Numi,Calculator Plus", "Wolfram Alpha,GNOME Calculator,Kalker"),
    _A("settings_panel", "Settings / control panel", "system display sound network bluetooth personalization apps accounts privacy update toggle search settings", "list button",
       ["search a setting", "open page", "change toggle / value", "apply"], {"search": "Ctrl+F"},
       ["reset this pc", "factory reset", "remove account", "turn off firewall", "format"], ["turn {text} on", "open the {text} page"],
       "Windows Settings,Control Panel,System Preferences,GNOME Settings,Android Settings,Device Manager,Services", "Group Policy Editor,Registry Editor,msconfig"),
    _A("database_client", "Database / data client", "tables query execute schema connection results rows columns database sql run explorer", "table tree edit",
       ["connect", "browse schema", "write query", "run", "export"], {"run": "F5", "new query": "Ctrl+N"},
       ["drop", "truncate", "delete from", "update without where"], ["run the query {text}", "export the result"],
       "SSMS,DBeaver,pgAdmin,MySQL Workbench,DataGrip,TablePlus,HeidiSQL", "Beekeeper,Navicat,DB Browser for SQLite"),
    _A("note_taking", "Notes / knowledge base", "notebook notes page section tag checklist pin new note search sync outline", "list edit",
       ["new note", "type", "organize", "search"], {"new note": "Ctrl+N", "search": "Ctrl+E"},
       ["empty trash", "delete notebook", "share publicly"], ["add a note {text}", "find the note about {text}"],
       "OneNote,Evernote,Notion,Obsidian,Sticky Notes,Joplin,Bear", "Simplenote,Standard Notes,Apple Notes"),
    _A("screen_capture_stream", "Screen capture / recording / streaming", "record stop start streaming scenes sources capture screenshot snip delay region mixer output", "button pane",
       ["pick source", "set output", "start", "stop", "save"], {"snip": "Win+Shift+S", "record": "Win+Alt+R"},
       ["go live", "start streaming", "publish", "upload"], ["record the screen", "take a screenshot of {text}"],
       "OBS Studio,Snipping Tool,Xbox Game Bar,ShareX,Streamlabs,Camtasia,Greenshot", "Loom,Bandicam,Lightshot"),
    _A("system_utility", "System utility / clock / monitor", "timer alarm stopwatch world clock processes performance startup cleanup disk scan task monitor", "list tab",
       ["open tab", "read status", "set value", "start / stop"], {"refresh": "F5"},
       ["end task", "uninstall", "clean registry", "delete restore points"], ["set a timer for {n} minutes", "show running processes"],
       "Clock,Task Manager,Resource Monitor,CCleaner,Disk Cleanup,Sensors,Performance Monitor", "HWMonitor,Process Explorer,Windows Security"),
]
BY_ID = {a["id"]: a for a in ARCHETYPES}


def _toks(s: str) -> List[str]:
    return re.findall(r"[a-z][a-z0-9]{1,}", (s or "").lower())


def _idf() -> Dict[str, float]:
    df = Counter(w for a in ARCHETYPES for w in set(a["signals"]))
    n = len(ARCHETYPES)
    return {w: math.log(1 + n / c) for w, c in df.items()}


IDF = _idf()


class ArchetypeRouter:
    """Scores a scanned app against the 25 archetypes from the words of its own controls (no app name needed)."""

    def __init__(self) -> None:
        self.centroid: Dict[str, Counter] = {}
        self.fit_weight = 0.0      # measured: word-centroids fitted on ~15 sparse scans HURT held-out accuracy (0.56 -> 0.35 at weight 1.0); kept as an option, off by default

    @staticmethod
    def words(signature: Dict[str, Any]) -> Counter:
        c: Counter = Counter()
        for n in signature.get("controls", []):
            name = n[1] if isinstance(n, (list, tuple)) else str(n)
            for t in set(_toks(name)):
                c[t] += 1
        for t in _toks(signature.get("title", "")):
            c[t] += 2
        return c

    def prior_scores(self, words: Counter) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for a in ARCHETYPES:
            hit = [w for w in a["signals"] if w in words]
            out[a["id"]] = sum(IDF[w] for w in hit) / math.sqrt(len(a["signals"]))
        return out

    def fit(self, signatures: Iterable[Tuple[str, Dict[str, Any]]]) -> None:
        """Learn per-archetype word weights from SCANNED train apps: [(archetype_id, signature)]."""
        agg: Dict[str, Counter] = defaultdict(Counter)
        for aid, sig in signatures:
            for w, n in self.words(sig).items():
                agg[aid][w] += 1                                  # document frequency across the archetype's apps
        self.centroid = {aid: c for aid, c in agg.items()}

    def fitted_scores(self, words: Counter) -> Dict[str, float]:
        if not self.centroid:
            return {}
        out = {}
        vocab_df = Counter(w for c in self.centroid.values() for w in c)
        for aid, c in self.centroid.items():
            tot = sum(c.values()) or 1
            s = sum((c[w] / tot) * math.log(1 + len(self.centroid) / vocab_df[w]) for w in words if w in c)
            out[aid] = s
        m = max(out.values()) or 1
        return {k: v / m for k, v in out.items()}

    def classify(self, signature: Dict[str, Any], top: int = 3) -> List[Tuple[str, float]]:
        w = self.words(signature)
        pri = self.prior_scores(w)
        pm = max(pri.values()) or 1
        fit = self.fitted_scores(w)
        score = {k: pri[k] / pm + (self.fit_weight * fit.get(k, 0.0)) for k in pri}
        # a name that equals a known example application is a strong, but only supporting, signal
        nm = _norm_name(signature.get("app", ""))
        if nm:
            for a in ARCHETYPES:
                if nm in {_norm_name(x) for x in a["train"]}:
                    score[a["id"]] += 0.5
        return sorted(score.items(), key=lambda kv: -kv[1])[:top]


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def hint(app: str, goal: str, rag_has_pathway: bool, signature: Optional[Dict[str, Any]] = None, router: Optional[ArchetypeRouter] = None) -> Optional[Dict[str, Any]]:
    """Archetype fallback: a procedure SKELETON when the RAG has no pathway. Never replaces a pathway the RAG does have.
    The skeleton lists phases, class-wide keys and traps; steps are still resolved on the app's own scanned controls, so it never invents a control."""
    if rag_has_pathway:
        return None
    r = router or ArchetypeRouter()
    ranked = r.classify(signature or {"app": app, "title": app, "controls": []}, top=2)
    if not ranked or ranked[0][1] <= 0.0:
        return None
    a = BY_ID[ranked[0][0]]
    g = _toks(goal)
    template = max(a["templates"], key=lambda t: len(set(_toks(re.sub(r"\{[^}]*\}", " ", t))) & set(g)) if g else 0)
    return {"source": "archetype", "confidence": 0.45, "archetype": a["id"], "runner_up": ranked[1][0] if len(ranked) > 1 else "",
            "phases": a["grammar"], "keys": {**_STD_KEYS, **a["keys"]}, "traps": sorted(set(a["traps"]) | set(_UNIVERSAL_TRAPS)),
            "closest_template": template, "note": "skeleton only: every step must resolve to a control that exists in this app's scan"}


def is_trap(archetype_id: str, control_name: str) -> bool:
    """A control a class-wide guard blocks unless the person (or the standing allowlist) approved that action."""
    n = " ".join(_toks(control_name))
    a = BY_ID.get(archetype_id)
    words = set(_UNIVERSAL_TRAPS) | set(a["traps"] if a else [])
    return any(re.search(r"\b" + re.escape(w) + r"\b", n) for w in words)


# ---- evaluation ------------------------------------------------------------------------------------------------------
REAL_LABELS = {  # scanned desktop apps in the training harvest -> archetype (ground truth I assigned by what the app is)
    "calculator": "calculator", "notepad": "text_editor", "obs_studio": "screen_capture_stream", "ms_paint": "raster_editor", "paint": "raster_editor",
    "word": "word_processor", "powerpoint": "presentation", "excel": "spreadsheet", "slack": "chat_messenger", "teams": "chat_messenger",
    "discord": "chat_messenger", "whatsapp_desktop": "chat_messenger", "spotify": "media_player", "clock": "system_utility",
    "snippingtool": "screen_capture_stream", "windows_11_settings": "settings_panel", "code": "code_ide", "chrome": "browser",
    "google_chrome": "browser", "gimp": "raster_editor", "webapp:excalidraw.com": "diagram_whiteboard", "web:app.diagrams.net": "diagram_whiteboard",
}
_EL = re.compile(r'^#\d+\s+(\w+)\s+"([^"]+)"', re.M)


def real_signatures(path: str = TRAIN_ROWS) -> Dict[str, Dict[str, Any]]:
    sigs: Dict[str, Dict[str, Any]] = {}
    if not os.path.isfile(path):
        return sigs
    for line in open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        k = r.get("meta", {}).get("app_key")
        if k not in REAL_LABELS:
            continue
        t = r["messages"][1]["content"]
        t = "".join(p.get("text", "") for p in t if isinstance(p, dict)) if isinstance(t, list) else t
        s = sigs.setdefault(k, {"app": k, "title": "", "controls": []})
        s["controls"].extend((m.group(1), m.group(2)) for m in _EL.finditer(t))
    for s in sigs.values():
        s["controls"] = list(dict.fromkeys(s["controls"]))
    return sigs


def _name_only_zero_shot() -> Dict[str, Any]:
    """Bookkeeping, NOT evidence: classify each held-out example name by token overlap with the 7 train names of every class.
    Example names are mostly unrelated words, so a low number is expected; it is reported so nobody mistakes the matrix for a measured result."""
    ok = tot = 0
    for a in ARCHETYPES:
        for name in a["test"]:
            best = max(ARCHETYPES, key=lambda b: len(set(_toks(name)) & {t for x in b["train"] for t in _toks(x)}))
            ok += best["id"] == a["id"]
            tot += 1
    return {"n": tot, "accuracy": round(ok / tot, 3)}


def evaluate_70_30_split(seeds: int = 20, path: str = TRAIN_ROWS) -> Dict[str, Any]:
    sigs = real_signatures(path)
    keys = sorted(sigs)
    out: Dict[str, Any] = {"matrix": {"archetypes": len(ARCHETYPES), "train_apps": sum(len(a["train"]) for a in ARCHETYPES),
                                      "test_apps": sum(len(a["test"]) for a in ARCHETYPES), "name_only_zero_shot": _name_only_zero_shot()},
                           "real_apps": len(keys)}
    if len(keys) < 6:
        out["note"] = "too few scanned apps for a split"
        return out
    prior_ok = fit_ok = tot = top3 = 0
    for seed in range(seeds):
        rng = random.Random(seed)
        shuffled = keys[:]
        rng.shuffle(shuffled)
        cut = int(round(len(shuffled) * 0.7))
        train, test = shuffled[:cut], shuffled[cut:]
        base = ArchetypeRouter()
        fitted = ArchetypeRouter()
        fitted.fit((REAL_LABELS[k], sigs[k]) for k in train)
        for k in test:
            sig = {**sigs[k], "app": ""}                                 # held-out: the app's NAME is not given, only its scanned controls
            tot += 1
            prior_ok += base.classify(sig, 1)[0][0] == REAL_LABELS[k]
            ranked = fitted.classify(sig, 3)
            fit_ok += ranked[0][0] == REAL_LABELS[k]
            top3 += REAL_LABELS[k] in [a for a, _ in ranked]
    out.update({"splits": seeds, "held_out_predictions": tot,
                "signals_only_top1": round(prior_ok / tot, 3), "signals_plus_fitted_top1": round(fit_ok / tot, 3), "signals_plus_fitted_top3": round(top3 / tot, 3),
                "caveat": "labels for the scanned apps were assigned by me; classes with one scanned app cannot be learned when it is held out, so the fitted number is a floor"})
    return out


if __name__ == "__main__":
    print(json.dumps(evaluate_70_30_split(), indent=1))
