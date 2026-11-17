"""
professor.harvest -- ZERO-RULEBOOK DISCOVERY: the application's own interface IS its manual. Read it, passively, in seconds.

Sources (all read-only; nothing is clicked unless the caller authorises hover, and then only in a window the Professor owns):
  1 native menus      Win32 HMENU tree: every item + accelerator + state, even the ones nobody opened          (professor.native_menu)
  2 accessibility     UI Automation tree: Name, role, HelpText (tooltip), AcceleratorKey, state of every control (professor.uia_source / the ScreenModel)
  3 stored maps       Atlas UI maps (menu / ribbon / dialog trees measured earlier) when the application was learned before
  4 tooltip strings   "Bevel Edges: Rounds selected mesh edges. (Ctrl+B)" -> description + shortcut, parsed wherever such a string appears
  5 status text       status-bar help lines
  6 hover (opt-in)    a posted pointer-move over unlabelled icons makes their tooltips appear; read from the tooltip window  (own windows only)
Output: a Catalog -- the Verb Registry (what the app can DO, grouped by menu path), the Shortcut Map (chord -> verbs, conflicts flagged), the Tooltip Dictionary,
and where each fact came from. Saved as JSON per application; no network, no model.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import config as CFG
from . import safety
from .schema import ScreenModel, UIElement, fold

CATALOG_DIR = os.path.join(CFG.DATA_DIR, "catalogs")

# ----------------------------------------------------------------------------------------------------- shortcut grammar
_MOD = {"control": "Ctrl", "ctrl": "Ctrl", "ctl": "Ctrl", "alt": "Alt", "option": "Alt", "opt": "Alt", "shift": "Shift", "win": "Win", "windows": "Win", "super": "Win",
        "cmd": "Cmd", "command": "Cmd", "meta": "Meta"}
_KEY = {"del": "Delete", "delete": "Delete", "esc": "Escape", "escape": "Escape", "return": "Enter", "enter": "Enter", "ins": "Insert", "insert": "Insert", "pgup": "PageUp",
        "pageup": "PageUp", "pgdn": "PageDown", "pagedown": "PageDown", "space": "Space", "spacebar": "Space", "tab": "Tab", "backspace": "Backspace", "bksp": "Backspace",
        "home": "Home", "end": "End", "up": "Up", "down": "Down", "left": "Left", "right": "Right", "plus": "+", "minus": "-", "comma": ",", "period": ".", "lmb": "LMB", "mmb": "MMB", "rmb": "RMB"}
_ORDER = ["Ctrl", "Alt", "Shift", "Win", "Cmd", "Meta"]
CHORD_RX = re.compile(r"(?<![\w+])((?:(?:ctrl|control|ctl|alt|option|shift|win|windows|cmd|command|meta)\s*\+\s*)+(?:f\d{1,2}|[a-z0-9]|del(?:ete)?|esc(?:ape)?|enter|return|space|tab|"
                      r"ins(?:ert)?|home|end|pgup|pgdn|page ?up|page ?down|backspace|up|down|left|right|plus|minus|[`~!@#$%^&*()_=\[\]{};:'\",.<>/?\\|+-]))", re.I)
KEY_PAREN_RX = re.compile(r"[\(\[]\s*((?:f\d{1,2})|(?:[a-z0-9])|(?:esc|del|tab|space|enter))\s*[\)\]]\s*$", re.I)


def _mouse_word(k: str) -> bool:
    """True when a 'key' is really a MOUSE event word (a keymap item of type LEFTMOUSE / RMBCLICK / WHEELUP read as a chord). A keyboard poster can never send one: such a 'chord' is not a chord."""
    s = re.sub(r"[^a-z]", "", (k or "").lower())
    return bool(s) and (s in {"click", "lmb", "rmb", "mmb", "dblclick", "leftmouse", "rightmouse", "middlemouse", "mouseleft", "mouseright", "mousemiddle",
                              "leftbutton", "rightbutton", "middlebutton", "leftclick", "rightclick", "middleclick", "wheelup", "wheeldown", "wheelmouse",
                              "lmbclick", "rmbclick", "mmbclick", "penbarrel", "eraser", "trackpaddown", "trackpadup", "numpadmouse"}
                        or s.startswith("mouse") or "click" in s or s.startswith("wheel"))


def normalize_chord(s: str) -> str:
    """'ctrl + shift+s' / 'Control-Shift-S' -> 'Ctrl+Shift+S'. Modifiers in a fixed order, one key last. '' when nothing sensible remains."""
    s = (s or "").strip().strip("()[] ")
    if not s:
        return ""
    s = re.sub(r"\s*\+\s*\+\s*$", "+plus", s)                  # 'Ctrl++'
    parts = [p.strip() for p in re.split(r"\s*\+\s*", s) if p.strip()]
    mods, key = [], ""
    for p in parts:
        low = p.lower()
        if low in _MOD:
            mods.append(_MOD[low])
        else:
            key = _KEY.get(low, p.upper() if len(p) == 1 else (p.upper() if re.fullmatch(r"f\d{1,2}", low) else p.capitalize()))
    if key and _mouse_word(key):
        return ""                                              # a mouse-button word is never a keyboard chord ('Ctrl+Rightmouse' cannot be posted): not a shortcut
    mods = sorted(set(mods), key=_ORDER.index)
    return "+".join(mods + ([key] if key else []))


def chords_in(text: str) -> List[str]:
    """Every shortcut written in a tooltip / label: 'Ctrl+B', 'Alt + E', and a trailing single key in brackets '(T)'."""
    out: List[str] = []
    for m in CHORD_RX.finditer(text or ""):
        c = normalize_chord(m.group(1))
        if c and c not in out:
            out.append(c)
    if not out:
        m = KEY_PAREN_RX.search(text or "")
        if m:
            out.append(normalize_chord(m.group(1)))
    return out


def split_tooltip(text: str) -> Tuple[str, str, str]:
    """'Bevel Edges: Rounds selected mesh edges. (Ctrl+B)' -> (name, description, chord)."""
    text = (text or "").strip()
    chord = (chords_in(text) or [""])[0]
    clean = re.sub(r"\s*[\(\[][^()\[\]]*(?:ctrl|alt|shift|cmd|win)[^()\[\]]*[\)\]]\s*$", "", text, flags=re.I)
    clean = KEY_PAREN_RX.sub("", clean).strip()
    name, _sep, desc = clean.partition(":")
    if not _sep:
        name, desc = clean, ""
    return name.strip(), desc.strip(), chord


# ------------------------------------------------------------------------------------------------------------ the catalog
@dataclass
class Verb:
    id: str
    label: str
    path: List[str] = field(default_factory=list)
    shortcut: str = ""
    desc: str = ""
    enabled: bool = True
    checked: bool = False
    leads_to: str = ""
    command_id: int = 0
    aid: str = ""
    role: str = ""
    sources: List[str] = field(default_factory=list)
    trust: str = "measured"
    safety: str = "safe"

    @property
    def text_path(self) -> str:
        return " > ".join(self.path + [self.label])


_CLASSES = {"safe", "unsafe", "commit", "sensitive", "runtime"}


def foreign_titles(process: str) -> set:
    """folded titles of the top-level windows on this desktop that a DIFFERENT process owns (visible or iconified; a hidden window is still proof of who owns its controls). A control read out
    of a window like that is not a command of the application under study - its own window just happened to hold a piece of it (an embedded pane) or a merged tree mixed the two.
    An unknown process => nothing is treated as foreign."""
    want = fold(os.path.basename(process or ""))
    if not want:
        return set()
    try:
        import ctypes
        import ctypes.wintypes as wt
        from core_organs import headless_input as hin
        k32 = ctypes.windll.kernel32
        cache: Dict[int, str] = {}

        def name_of(pid: int) -> str:
            if pid in cache:
                return cache[pid]
            got = ""
            h = k32.OpenProcess(0x1000, False, pid)                        # PROCESS_QUERY_LIMITED_INFORMATION: the name, not a handle into it
            if h:
                try:
                    buf = ctypes.create_unicode_buffer(1024)
                    n = wt.DWORD(1024)
                    if k32.QueryFullProcessImageNameW(int(h), 0, buf, ctypes.byref(n)):
                        got = fold(os.path.basename(buf.value))
                except Exception:                                          # noqa: BLE001
                    got = ""
                finally:
                    k32.CloseHandle(h)
            cache[pid] = got
            return got

        out: set = set()
        for h, t in hin.top_level_titles(visible_only=False):             # safe_window_text: a hung window answers '' instead of freezing the sweep
            try:
                if len((t or "").strip()) < 12:                            # a short caption collides too easily with a real control name
                    continue
                p = name_of(hin.window_pid(int(h)))
                if p and p != want:
                    out.add(fold(t))
            except Exception:                                              # noqa: BLE001
                continue
        return out
    except Exception:                                                      # noqa: BLE001
        return set()


DOCS_SOURCES = {"vendor-manifest", "knowledge", "convention", "guide"}     # written from a document, never from a live window: the ownership scrub leaves them alone

_HEX16 = re.compile(r"^[0-9a-f]{16}$")


def _fhash(title: str) -> str:
    """The ledger key of a foreign window. A browser's caption carries whatever the person was reading, so the catalog stores a digest of it and NEVER the text: a private title must not end
    up inside an application's knowledge file (measured: one run wrote a whole search query into Word's catalog as part of a leaked Chrome caption)."""
    return hashlib.sha1(fold(title or "").encode("utf-8")).hexdigest()[:16]


def recorded_foreign_hashes(cat: "Catalog") -> set:
    """the foreign windows a run MEASURED while harvesting this application, as digests (kept in the catalog's notes): they clean a file saved before the guard existed, long after that
    window was closed. A note written before this rule held the caption itself - it is folded into a digest and replaced in place, so the plain text leaves the file on the next save."""
    out, rebuilt, changed = set(), [], False
    for n in cat.notes or []:
        s = str(n)
        if not s.startswith("foreign-window|"):
            rebuilt.append(n)
            continue
        v = s.split("|", 1)[1].strip()
        h = v if _HEX16.match(v) else _fhash(v)
        if h:
            out.add(h)
        if h != v:
            changed = True
        rebuilt.append("foreign-window|" + h)
    if changed:
        cat.notes = rebuilt
    return out


def drop_foreign_verbs(cat: "Catalog", titles: Optional[set] = None) -> int:
    """Remove verbs that a window of ANOTHER application owns (their path runs through that window's caption). Returns how many were dropped; the catalog is edited in place."""
    hs = {_fhash(t) for t in (set(titles or ()) | recorded_foreign_hashes(cat))}
    if titles is None:
        hs |= {_fhash(t) for t in foreign_titles(cat.process)}
    if not hs:
        return 0
    keep = []
    gone = 0
    for v in cat.verbs:
        srcs = set(v.sources or [])
        if srcs and not (srcs - DOCS_SOURCES) and v.trust != "measured":
            keep.append(v)                                               # purely document-derived knowledge: an application's own manual, not a screen reading
            continue
        if any(_fhash(str(p)) in hs for p in (v.path or [])):
            gone += 1
            continue
        keep.append(v)
    if gone:
        cat.verbs = keep
        cat.notes.append(f"scrubbed: {gone} verb(s) of another application's window removed on load")
    return gone


def reclassify(verbs: Sequence["Verb"]) -> int:
    """A stored catalog keeps the safety class it was saved with; the rules can change since (measured: 'Format Text Effects' was stored 'unsafe'). Verbs whose class came from the
    classifier are classified again on load ('unknown' and any other deliberate class are left alone). Returns how many changed."""
    from . import safety as _s
    n = 0
    for v in verbs:
        if v.safety in _CLASSES:
            c = _s.classify(v.label, " ".join(str(p) for p in v.path))
            if c != v.safety:
                v.safety, n = c, n + 1
    return n


def verb_id(path: Sequence[str], label: str) -> str:
    return hashlib.sha1(("|".join(fold(p) for p in path) + "||" + fold(label)).encode("utf-8", "replace")).hexdigest()[:10]


@dataclass
class Catalog:
    app_key: str = ""
    title: str = ""
    process: str = ""
    created: float = field(default_factory=time.time)
    verbs: List[Verb] = field(default_factory=list)
    tooltips: Dict[str, str] = field(default_factory=dict)             # folded control name -> tooltip text
    status_texts: List[str] = field(default_factory=list)
    sources: Dict[str, int] = field(default_factory=dict)
    archetype: Dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0
    notes: List[str] = field(default_factory=list)

    # ---- indexes
    def by_label(self, label: str) -> List[Verb]:
        q = fold(label)
        exact = [v for v in self.verbs if fold(v.label) == q]
        return exact or [v for v in self.verbs if q and q in fold(v.label)]

    def shortcut_for(self, label: str) -> str:
        for v in self.by_label(label):
            if v.shortcut:
                return v.shortcut
        return ""

    def shortcut_map(self) -> Dict[str, List[str]]:
        m: Dict[str, List[str]] = {}
        for v in self.verbs:
            if v.shortcut:
                m.setdefault(v.shortcut, []).append(v.text_path)
        return m

    def conflicts(self) -> Dict[str, List[str]]:
        return {k: v for k, v in self.shortcut_map().items() if len(set(v)) > 1}

    def best(self, text: str, limit: int = 5) -> List[Verb]:
        """Verbs whose label / path words overlap the request (a tiny retrieval: enough to ground a plan step)."""
        qw = {w for w in fold(text).split() if len(w) > 2}
        scored = []
        for v in self.verbs:
            vw = set(fold(v.label).split()) | set(fold(" ".join(v.path)).split()) | set(fold(v.desc).split())
            ov = len(qw & vw)
            if ov and qw & set(fold(v.label).split()):
                scored.append((ov + (0.5 if v.shortcut else 0.0) + (0.3 if v.enabled else 0.0), v))
        scored.sort(key=lambda t: -t[0])
        return [v for _s, v in scored[:limit]]

    def summary(self) -> Dict[str, Any]:
        tops = sorted({v.path[0] for v in self.verbs if v.path})
        return {"app": self.app_key, "verbs": len(self.verbs), "with_shortcut": sum(1 for v in self.verbs if v.shortcut), "tooltips": len(self.tooltips), "menus": tops[:14],
                "sources": self.sources, "conflicts": len(self.conflicts()), "safety": {s: sum(1 for v in self.verbs if v.safety == s) for s in ("safe", "commit", "runtime", "sensitive", "unsafe")},
                "archetype": self.archetype.get("id") if self.archetype else None, "seconds": self.seconds}

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Catalog":
        c = Catalog(**{k: d[k] for k in ("app_key", "title", "process", "created", "tooltips", "status_texts", "sources", "archetype", "seconds", "notes") if k in d})
        c.verbs = [Verb(**v) for v in d.get("verbs", [])]
        reclassify(c.verbs)
        for v in c.verbs:
            if not v.desc:
                ctx = f" in {v.path[-1]}" if v.path else ""
                if v.role in ("toggle", "checkbox"):
                    v.desc = f"Toggles {v.label}{ctx}"
                elif v.role == "button":
                    v.desc = f"Selects {v.label}{ctx}"
                elif v.role == "tab":
                    v.desc = f"Switches to {v.label} tab"
                elif v.role in ("dropdown", "combobox"):
                    v.desc = f"Chooses {v.label} option"
                elif v.role == "menu_item":
                    v.desc = f"Executes {v.label} from {' > '.join(v.path) if v.path else 'menu'}"
                elif v.role in ("list_item", "tree_item"):
                    v.desc = f"Selects {v.label}{ctx}"
                elif v.role == "radio":
                    v.desc = f"Selects {v.label} option"
                elif v.label:
                    v.desc = f"Controls {v.label}{ctx}"
            if not v.leads_to:
                if v.label.endswith("...") or v.label.endswith("…"):
                    clean_lbl = v.label.rstrip(".… ").strip()
                    v.leads_to = f"opens the {clean_lbl} dialog"
                elif v.role in ("dropdown", "combobox"):
                    v.leads_to = f"opens the {v.label} choices"
                elif v.role == "tab":
                    v.leads_to = f"shows the {v.label} panel"
            if v.desc and fold(v.label) not in c.tooltips:
                c.tooltips[fold(v.label)] = v.desc
        return c

    def save(self, path: str = "") -> str:
        os.makedirs(CATALOG_DIR, exist_ok=True)
        path = path or os.path.join(CATALOG_DIR, (self.app_key or "app") + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=1, ensure_ascii=False)
        return path

    @staticmethod
    def load(app_key: str) -> Optional["Catalog"]:
        p = os.path.join(CATALOG_DIR, app_key + ".json")
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as fh:
                c = Catalog.from_dict(json.load(fh))
        except Exception:
            return None
        # A catalog written BEFORE the ownership guard existed can still hold another application's controls (measured: Word's file held a browser's omnibox, and the run searched for
        # 'Home' in it). Loaded is the last place a run can still be protected, so the stale entries are dropped here - live windows decide, and an app that is not open cannot be
        # recognized, so the harvest guard above is what keeps new files clean.
        if os.environ.get("HOJAIGA_CATALOG_SCRUB", "1") != "0":
            try:
                drop_foreign_verbs(c)
            except Exception:                                            # noqa: BLE001
                pass
        return c

    def prompt_lines(self, wanted: Iterable[str] = (), limit: int = 10) -> str:
        """HOTKEYS the teacher may quote: only the verbs the request touches (or the best-known ones), each with its measured chord."""
        picks: List[Verb] = []
        for w in wanted:
            picks.extend(self.best(w, 3))
        if not picks:
            picks = [v for v in self.verbs if v.shortcut][:limit]
        seen, out = set(), []
        for v in picks:
            if v.id in seen or not v.shortcut:
                continue
            seen.add(v.id)
            out.append(f"{v.text_path}: {v.shortcut}" + (f" - {v.desc[:60]}" if v.desc else ""))
            if len(out) >= limit:
                break
        return "\n".join(out)


# ------------------------------------------------------------------------------------------------------------------ build
class _Builder:
    def __init__(self) -> None:
        self.by_key: Dict[str, Verb] = {}
        self.sources: Dict[str, int] = {}
        self.tooltips: Dict[str, str] = {}

    def add(self, label: str, path: Sequence[str] = (), *, source: str, shortcut: str = "", desc: str = "", enabled: bool = True, checked: bool = False, leads_to: str = "",
            command_id: int = 0, aid: str = "", role: str = "", trust: str = "measured") -> Optional[Verb]:
        label = re.sub(r"\s+", " ", (label or "").replace("&", "")).strip()
        if not label or len(label) > 80:
            return None
        path = [re.sub(r"\s+", " ", p).strip() for p in path if p and p.strip()]
        key = fold(" > ".join(path + [label]))
        v = self.by_key.get(key)
        sc = normalize_chord(shortcut) if shortcut else ""
        desc = desc.strip()
        leads_to = leads_to.strip()
        if not desc:
            ctx = f" in {path[-1]}" if path else ""
            if role in ("toggle", "checkbox"):
                desc = f"Toggles {label}{ctx}"
            elif role == "button":
                desc = f"Selects {label}{ctx}"
            elif role == "tab":
                desc = f"Switches to {label} tab"
            elif role in ("dropdown", "combobox"):
                desc = f"Chooses {label} option"
            elif role == "menu_item":
                desc = f"Executes {label} from {' > '.join(path) if path else 'menu'}"
            elif role in ("list_item", "tree_item"):
                desc = f"Selects {label}{ctx}"
            elif role == "radio":
                desc = f"Selects {label} option"
            elif label:
                desc = f"Controls {label}{ctx}"
        if not leads_to:
            if label.endswith("...") or label.endswith("…"):
                clean_lbl = label.rstrip(".… ").strip()
                leads_to = f"opens the {clean_lbl} dialog"
            elif role in ("dropdown", "combobox"):
                leads_to = f"opens the {label} choices"
            elif role == "tab":
                leads_to = f"shows the {label} panel"
        if desc:
            self.tooltips.setdefault(fold(label), desc)
        if v is None:
            v = Verb(verb_id(path, label), label, path, sc, desc, enabled, checked, leads_to, command_id, aid, role, [source], trust, safety.classify(label, " ".join(path)))
            self.by_key[key] = v
        else:
            if source not in v.sources:
                v.sources.append(source)
            v.shortcut = v.shortcut or sc
            v.desc = v.desc or desc
            v.leads_to = v.leads_to or leads_to
            v.command_id = v.command_id or command_id
            v.aid = v.aid or aid
            v.role = v.role or role
        self.sources[source] = self.sources.get(source, 0) + 1
        return v


_VERB_ROLES = {"menu_item", "button", "dropdown", "toggle", "checkbox", "tab", "radio", "link", "list_item", "tree_item", "field"}


def harvest_model(sm: ScreenModel, hwnd: int = 0, atlas_key: str = "", *, hover: bool = False, allow_input: bool = False, owned: bool = False, budget_s: float = 30.0) -> Catalog:
    """Build the catalog from everything passively readable: the scan's tree-named controls, the window's native menus, stored Atlas maps, tooltip strings, status text."""
    t0 = time.time()
    b = _Builder()
    cat = Catalog(app_key=sm.app_key, title=sm.window_title, process=sm.process)
    # 1 native menus
    if hwnd:
        try:
            from . import native_menu
            for it in native_menu.harvest(hwnd):
                b.add(it.label, it.path, source="win32-menu", shortcut=it.shortcut, enabled=it.enabled, checked=it.checked, leads_to=("opens a submenu" if it.has_submenu else ""),
                      command_id=it.command_id, role="menu_item")
        except Exception as exc:
            cat.notes.append("native menus: " + type(exc).__name__)
    # 2 accessibility tree + 4 tooltip strings (every control the scan found, however it was found)
    for e in sm.elements:
        if not e.label or e.role not in _VERB_ROLES:
            continue
        region = sm.region(e.region_id)
        path = [p for p in (sm.region_path(e.region_id).split(" > ") if region else []) if p and fold(p) not in ("tabs", "menu bar", "tool bar", "group", "ribbon", "menubar")]
        src = "uia" if "uia" in e.sources else ("ocr" if "ocr" in e.sources else "vision")
        tt = e.hint or ""
        name, desc, chord = split_tooltip(tt) if tt else ("", "", "")
        b.add(e.label, path[-2:], source=src, shortcut=e.shortcut or chord, desc=desc or tt, enabled=e.enabled, checked=bool(e.selected), leads_to=e.leads_to, aid=e.aid, role=e.role,
              trust="measured" if src == "uia" else "inferred")
        if tt:
            b.tooltips[fold(e.label)] = tt
        for c in chords_in(e.label):
            b.add(re.sub(r"\s*\(.*$", "", e.label), path[-2:], source="label", shortcut=c, role=e.role)
    # 3 stored Atlas maps
    try:
        from .knowledge import app_knowledge as AK
        ak = AK.for_identity(atlas_key, sm.app_key, sm.process.replace(".exe", ""))
        for ent in ak.entries[:3000]:
            parts = [v for k, v in ent["path"] if k in ("surface", "group") and v]
            lt = ent.get("lt") or {}
            lead = (lt.get("dialog") and f"opens the {lt['dialog']} dialog") or (lt.get("type") in ("menu", "gallery") and "opens a menu") or ""
            b.add(ent["name"], parts, source="atlas-uimap", shortcut=ent.get("accel", ""), desc=ent.get("help", ""), enabled=ent.get("enabled", True), leads_to=lead or "", aid=ent.get("aid", ""),
                  role=ent.get("kind", ""), trust="measured")
    except Exception as exc:
        cat.notes.append("atlas maps: " + type(exc).__name__)
    # 5 status-bar help text
    for r in sm.regions:
        if r.kind == "statusbar":
            cat.status_texts = [e.label for e in sm.elements if e.region_id == r.id and e.label][:12]
    # 6 hover tooltips (opt-in, own windows only)
    if hover and allow_input and owned and hwnd:
        try:
            got = hover_tooltips(hwnd, sm, budget_s=max(5.0, budget_s - (time.time() - t0)))
            for name, text in got.items():
                nm, desc, chord = split_tooltip(text)
                b.tooltips[fold(name)] = text
                b.add(name, [], source="hover-tooltip", shortcut=chord, desc=desc or text, role="button")
        except Exception as exc:
            cat.notes.append("hover: " + type(exc).__name__)
    cat.verbs = sorted(b.by_key.values(), key=lambda v: (v.path, v.label.lower()))
    cat.tooltips = b.tooltips
    cat.sources = b.sources
    cat.seconds = round(time.time() - t0, 3)
    return cat


# --------------------------------------------------------------------------------------------------------------- hover
def hover_tooltips(hwnd: int, sm: ScreenModel, budget_s: float = 20.0, settle_s: float = 1.0) -> Dict[str, str]:
    """Posted pointer-move over each UNLABELLED-or-undescribed icon of a window the Professor OWNS, reading the tooltip window that appears. Never moves the real mouse,
    never activates anything (posted WM_MOUSEMOVE to the exact child window, like Atlas gestures). The caller must have checked ownership / authorisation."""
    from core_organs.atlas import gestures as G
    from core_organs import headless_input as hin
    out: Dict[str, str] = {}
    t0 = time.time()
    ptr = G.Pointer(hwnd)
    targets = [e for e in sm.elements if e.role in ("button", "toggle", "dropdown", "icon") and not e.hint and e.bbox.w >= 10 and e.bbox.h >= 10 and e.label][:40]
    for e in targets:
        if time.time() - t0 > budget_s:
            break
        before = set(w for w, _t in hin.top_level_titles(visible_only=False))
        cx, cy = int(e.bbox.cx), int(e.bbox.cy)
        ptr.move(cx - 3, cy - 3)
        ptr.move(cx, cy)
        end = time.time() + settle_s
        text = ""
        while time.time() < end and not text:
            time.sleep(0.1)
            text = _read_tooltip(before)
        ptr.move(cx + 400, cy + 400)                            # leave: the tooltip closes
        if text and fold(text) != fold(e.label):
            out[e.label] = text
    return out


def _read_tooltip(known: set) -> str:
    """Text of a tooltip window that appeared since `known` was taken (Win32 'tooltips_class32', or any new tool window of the same process owned by the hovered app)."""
    import ctypes
    import ctypes.wintypes as wt
    u = ctypes.WinDLL("user32", use_last_error=True)
    found: List[str] = []
    PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(h, _lp):
        try:
            if int(h) in known or not u.IsWindowVisible(h):
                return True
            cls = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(h, cls, 64)
            if "tooltip" in cls.value.lower():
                n = u.GetWindowTextLengthW(h)
                buf = ctypes.create_unicode_buffer(max(2, n + 2))
                u.GetWindowTextW(h, buf, n + 2)
                txt = buf.value.strip()
                if txt:
                    found.append(txt)
        except Exception:
            pass
        return True

    try:
        u.EnumWindows(PROC(cb), 0)
    except Exception:
        pass
    return found[0] if found else ""


_TREE_VERB_ROLES = {"button", "menuitem", "tabitem", "checkbox", "radiobutton", "splitbutton", "listitem", "treeitem", "combobox", "hyperlink", "edit", "slider"}
_RANGE_SUFFIX = re.compile(r"\s+Minimum\s*-?\d+\s+Maximum\s*-?\d+\s*$", re.I)
_GENERIC_CONTAINERS = {"", "pane", "group", "ribbon", "menu bar", "menubar", "tool bar", "toolbar", "tabs", "tab", "application", "lower ribbon", "upper ribbon"}


def harvest_tree(hwnd: int, app_key: str = "", title: str = "", process: str = "", nodes: Optional[list] = None, atlas_key: str = "") -> Catalog:
    """The same catalog, built from the accessibility tree and the native menus ALONE -- no screenshot, no model, milliseconds. Used where a visual scan is not needed
    (probing and executing in a window we already hold a tree for)."""
    from core_organs import fast_uia
    t0 = time.time()
    b = _Builder()
    cat = Catalog(app_key=app_key, title=title, process=process)
    try:
        from . import native_menu
        for it in native_menu.harvest(hwnd):
            b.add(it.label, it.path, source="win32-menu", shortcut=it.shortcut, enabled=it.enabled, checked=it.checked, leads_to=("opens a submenu" if it.has_submenu else ""),
                  command_id=it.command_id, role="menu_item")
    except Exception as exc:
        cat.notes.append("native menus: " + type(exc).__name__)
    nodes = list(nodes) if nodes is not None else (fast_uia.snapshot(hwnd, timeout_ms=4000) or [])
    # ONE WINDOW, ONE APPLICATION. A UIA subtree can contain a piece of ANOTHER process: an embedded browser pane, a render-process child, a reparented dock (measured: Word's left dock held a
    # whole browser window - omnibox, tabs, bookmarks - and the catalog saved it as Word's own commands, so the next run searched for 'Home' in a Chrome box and found nothing). Controls of
    # another process are a SCREEN the run may need to act on, never a list of THIS application's verbs.
    try:
        from core_organs import headless_input as hin
        own_pid = int(hin.window_pid(hwnd) or 0)
    except Exception:                                                    # noqa: BLE001
        own_pid = 0
    foreign = 0
    seen_foreign: List[str] = []
    if own_pid:
        for i, n in enumerate(nodes):
            pid = int(getattr(n, "pid", 0) or 0)
            if pid and pid != own_pid:
                par = int(getattr(n, "parent", -1) or -1)
                if par < 0 or par >= len(nodes) or nodes[par] is None:
                    nm = re.sub(r"\s+", " ", str(n.name or "")).strip()   # the ROOT of the foreign piece: the window title of the other application
                    if nm and len(nm) >= 12 and fold(nm) not in [fold(x) for x in seen_foreign]:
                        seen_foreign.append(nm)
                nodes[i] = None                                   # BLANKED, not removed: the path builder below walks this list BY INDEX, so its shape must stay
                foreign += 1
    if foreign:
        cat.notes.append(f"uia: {foreign} node(s) of another process left out of the catalog")
    for nm in seen_foreign[:6]:
        # The window that leaked is WRITTEN DOWN as a digest (never its caption: a browser title carries what the person was reading), so a catalog saved before this guard can be cleaned on
        # load long after that window was closed.
        cat.notes.append("foreign-window|" + _fhash(nm))
    for n in nodes:
        if n is None or n.role not in _TREE_VERB_ROLES or not n.name or n.offscreen:
            continue
        path: List[str] = []
        p = n.parent
        while p >= 0:
            q = nodes[p]
            if q is None:
                break                                             # the chain runs through a window that is not this application's
            if q.name and q.role in ("pane", "group", "tab", "toolbar", "list", "tree", "menubar", "custom") and fold(q.name) not in _GENERIC_CONTAINERS:
                path.insert(0, q.name)
            p = q.parent
        chord = n.accel or ""
        name, desc, tchord = split_tooltip(n.help) if n.help else ("", "", "")
        role = {"menuitem": "menu_item", "tabitem": "tab", "listitem": "list_item", "treeitem": "tree_item", "radiobutton": "radio", "splitbutton": "dropdown", "combobox": "dropdown",
                "edit": "field", "spinner": "field", "slider": "field"}.get(n.role, n.role)
        rng = re.search(r"Minimum\s*(-?\d+)\s+Maximum\s*(-?\d+)", n.name or "", re.I)
        b.add(_RANGE_SUFFIX.sub("", n.name), path[-2:], source="uia", shortcut=chord or tchord or (chords_in(n.name) or [""])[0], desc=(f"range {rng.group(1)}..{rng.group(2)}" if rng else (desc or n.help)), enabled=n.enabled, checked=bool(n.selected) or n.toggle_state == 1,
              leads_to=("opens a menu" if (n.role == "splitbutton" or "expand" in (n.pats or [])) else ""), aid=n.aid, role=role)
        if n.help:
            b.tooltips[fold(n.name)] = n.help
    cat.verbs = sorted(b.by_key.values(), key=lambda v: (v.path, v.label.lower()))
    cat.tooltips = b.tooltips
    cat.sources = b.sources
    cat.seconds = round(time.time() - t0, 3)
    return cat


def save_for(sm: ScreenModel, hwnd: int = 0, **kw: Any) -> Tuple[Catalog, str]:
    cat = harvest_model(sm, hwnd, **kw)
    return cat, cat.save()
